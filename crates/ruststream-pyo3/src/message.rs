//! Object-safe forward of [`IncomingMessage`] used by wheel-specific `PyMessage` pyclasses.

use futures::future::BoxFuture;
use ruststream::{Headers, IncomingMessage};

/// Object-safe view of an [`IncomingMessage`]. Boxed so heterogeneous broker messages can sit
/// behind a single Python class.
pub trait PyIncomingMessage: Send + Sync {
    /// Returns the raw payload of the message.
    fn payload(&self) -> &[u8];

    /// Returns the headers attached to the message.
    fn headers(&self) -> &Headers;

    /// Acknowledges successful processing.
    fn ack(
        self: Box<Self>,
    ) -> BoxFuture<'static, Result<(), Box<dyn std::error::Error + Send + Sync>>>;

    /// Negatively acknowledges; `requeue=true` asks the broker to redeliver.
    fn nack(
        self: Box<Self>,
        requeue: bool,
    ) -> BoxFuture<'static, Result<(), Box<dyn std::error::Error + Send + Sync>>>;
}

impl<T> PyIncomingMessage for T
where
    T: IncomingMessage + 'static,
{
    fn payload(&self) -> &[u8] {
        IncomingMessage::payload(self)
    }

    fn headers(&self) -> &Headers {
        IncomingMessage::headers(self)
    }

    fn ack(
        self: Box<Self>,
    ) -> BoxFuture<'static, Result<(), Box<dyn std::error::Error + Send + Sync>>> {
        Box::pin(async move { (*self).ack().await.map_err(|err| Box::new(err) as _) })
    }

    fn nack(
        self: Box<Self>,
        requeue: bool,
    ) -> BoxFuture<'static, Result<(), Box<dyn std::error::Error + Send + Sync>>> {
        Box::pin(async move {
            (*self)
                .nack(requeue)
                .await
                .map_err(|err| Box::new(err) as _)
        })
    }
}
