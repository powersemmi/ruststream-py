//! Native extension for the `ruststream` Python package.

#![allow(clippy::missing_errors_doc, clippy::needless_pass_by_value)]

use pyo3::prelude::*;

mod memory;
mod message;
mod subscriber;

#[pymodule]
fn _native(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    ruststream_pyo3::install_runtime();
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<memory::PyMemoryBroker>()?;
    m.add_class::<message::PyMessage>()?;
    m.add_class::<subscriber::PySubscriber>()?;
    Ok(())
}
