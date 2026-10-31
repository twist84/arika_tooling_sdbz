use pyo3::prelude::*;

#[pyfunction]
fn ping() -> &'static str {
    "pong"
}

#[pymodule]
fn arika_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(ping, m)?)?;
    Ok(())
}
