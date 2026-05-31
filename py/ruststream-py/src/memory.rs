//! Python wrapper around the conformance `MemoryBroker`. Lets Python users write
//! broker-agnostic tests without spinning up real infrastructure.

use std::sync::Arc;

use pyo3::prelude::*;
use ruststream::conformance::MemoryBroker;
use ruststream::{Broker, OutgoingMessage, Publisher};
use ruststream_pyo3::{pump_subscriber, to_pyerr};

use crate::subscriber::PySubscriber;

/// In-memory broker exposed to Python. Mirrors the Rust `ruststream::conformance::MemoryBroker`.
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

    fn subscribe<'py>(&self, py: Python<'py>, topic: String) -> PyResult<Bound<'py, PyAny>> {
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
