//! Convert internal errors into Python exceptions.

use pyo3::{exceptions::PyRuntimeError, prelude::*};

/// Convert any `Display` error into a Python `RuntimeError`.
pub fn to_pyerr<E>(err: &E) -> PyErr
where
    E: std::fmt::Display + ?Sized,
{
    PyRuntimeError::new_err(format!("{err}"))
}
