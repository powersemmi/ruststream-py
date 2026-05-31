//! Generic helper that drives any `Subscriber::stream()` into an mpsc channel for Python.

use std::sync::Arc;

use futures::StreamExt;
use ruststream::Subscriber;
use tokio::sync::{Mutex, mpsc};
use tokio_util::sync::CancellationToken;
use tracing::warn;

use crate::message::PyIncomingMessage;

/// Receiver half of the pump channel feeding the per-wheel `PySubscriber` pyclass.
pub type DeliveryRx = Arc<Mutex<mpsc::Receiver<Box<dyn PyIncomingMessage>>>>;

/// Spawns a background Tokio task that drives `subscriber.stream()`.
///
/// Forwards every delivery into an mpsc channel; the returned receiver and cancellation token
/// are consumed by each wheel's `PySubscriber` pyclass.
pub fn pump_subscriber<S>(mut subscriber: S) -> (DeliveryRx, CancellationToken)
where
    S: Subscriber + Send + 'static,
    S::Message: PyIncomingMessage + 'static,
    S::Error: std::fmt::Display + Send + 'static,
{
    let (tx, rx) = mpsc::channel::<Box<dyn PyIncomingMessage>>(4096);
    let cancel = CancellationToken::new();
    let cancel_clone = cancel.clone();
    tokio::spawn(async move {
        let mut stream = std::pin::pin!(subscriber.stream());
        loop {
            tokio::select! {
                () = cancel_clone.cancelled() => break,
                next = stream.next() => match next {
                    Some(Ok(msg)) => {
                        if tx.send(Box::new(msg)).await.is_err() {
                            break;
                        }
                    }
                    Some(Err(err)) => {
                        warn!(target: "ruststream::py", error = %err, "subscriber stream error");
                    }
                    None => break,
                }
            }
        }
    });
    (Arc::new(Mutex::new(rx)), cancel)
}
