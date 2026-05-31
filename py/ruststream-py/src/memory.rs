//! Python wrapper around [`ruststream::memory::MemoryBroker`]. Backs the Python
//! `MemoryBroker`, an in-process broker for applications, prototypes and tests.

use std::{sync::Arc, time::Duration};

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use ruststream::memory::MemoryBroker;
use ruststream::testing::TestClient;
use ruststream::{Broker, Headers, OutgoingMessage, Publisher, RawMessage};
use ruststream_pyo3::{pump_subscriber, to_pyerr};

use crate::subscriber::PySubscriber;

/// In-memory broker exposed to Python. Mirrors the Rust `ruststream::memory::MemoryBroker`.
#[pyclass(name = "MemoryBroker", frozen)]
pub struct PyMemoryBroker {
    inner: Arc<MemoryBroker>,
}

impl std::fmt::Debug for PyMemoryBroker {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PyMemoryBroker").finish_non_exhaustive()
    }
}

#[pymethods]
impl PyMemoryBroker {
    #[new]
    fn new() -> Self {
        Self {
            inner: Arc::new(MemoryBroker::new()),
        }
    }

    fn publish<'py>(
        &self,
        py: Python<'py>,
        topic: String,
        payload: Vec<u8>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let publisher = inner.publisher();
            publisher
                .publish(OutgoingMessage::new(topic.as_str(), payload.as_slice()))
                .await
                .map_err(|err| to_pyerr(&err))
        })
    }

    // `**_options` keeps the signature compatible with the `StubTransport` contract; the
    // memory broker has no broker-specific subscription options, so they are ignored.
    #[pyo3(signature = (topic, **_options))]
    fn subscribe<'py>(
        &self,
        py: Python<'py>,
        topic: String,
        _options: Option<Bound<'py, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let subscriber = inner.subscribe(topic.as_str());
            let (rx, cancel) = pump_subscriber(subscriber);
            Python::with_gil(|py| -> PyResult<Py<PyAny>> {
                let obj = Py::new(py, PySubscriber::new(rx, cancel))?;
                Ok(obj.into_any())
            })
        })
    }

    /// Awaits until `count` messages have been published on `topic` (or `timeout_secs` elapses)
    /// and returns the recorded payloads + headers as a list of dicts.
    #[pyo3(signature = (topic, count, timeout_secs=1.0))]
    fn expect_published<'py>(
        &self,
        py: Python<'py>,
        topic: String,
        count: usize,
        timeout_secs: f64,
    ) -> PyResult<Bound<'py, PyAny>> {
        if timeout_secs <= 0.0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "timeout_secs must be > 0",
            ));
        }
        let inner = Arc::clone(&self.inner);
        let timeout_dur = Duration::from_secs_f64(timeout_secs);
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let messages = inner
                .expect_published(topic.as_str(), count, timeout_dur)
                .await
                .map_err(|err| to_pyerr(&err))?;
            Python::with_gil(|py| -> PyResult<Py<PyAny>> {
                let list = PyList::empty(py);
                for msg in messages {
                    list.append(raw_message_to_pydict(py, &msg)?)?;
                }
                Ok(list.into_any().unbind())
            })
        })
    }

    fn shutdown<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            Broker::shutdown(&*inner)
                .await
                .map_err(|err| to_pyerr(&err))
        })
    }

    fn __repr__(&self) -> String {
        format!("MemoryBroker(id=0x{:x})", Arc::as_ptr(&self.inner) as usize)
    }
}

fn raw_message_to_pydict(py: Python<'_>, msg: &RawMessage) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("topic", msg.topic())?;
    dict.set_item("payload", PyBytes::new(py, msg.payload()))?;
    dict.set_item("headers", headers_to_pydict(py, msg.headers())?)?;
    Ok(dict.into_any().unbind())
}

fn headers_to_pydict(py: Python<'_>, headers: &Headers) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    for (name, value) in headers.iter() {
        dict.set_item(name, PyBytes::new(py, value))?;
    }
    Ok(dict.into_any().unbind())
}
