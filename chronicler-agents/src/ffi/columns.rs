//! Typed Arrow column lookup shared by the FFI readers.
//!
//! `col` replaces the per-function `col!`/`col_u16!`-style macros. Errors are
//! `ValueError`s: `{ctx}missing column {name}` when the column is absent and
//! `{ctx}column {name} not {LABEL}` when it has another Arrow type. `ctx` is a
//! short prefix naming the input (`""`, `"civ input "`, `"region input "`,
//! `"topology "`, `"patch "`).

use arrow::array::{
    Array, BooleanArray, Float32Array, Float64Array, Int32Array, Int8Array, ListArray,
    StringArray, UInt16Array, UInt32Array, UInt8Array,
};
use arrow::record_batch::RecordBatch;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Arrow type name used in the wrong-type message.
pub(crate) trait ArrowLabel {
    const LABEL: &'static str;
}

macro_rules! arrow_label {
    ($($ty:ty => $label:literal),* $(,)?) => {
        $(impl ArrowLabel for $ty { const LABEL: &'static str = $label; })*
    };
}

arrow_label! {
    UInt8Array => "UInt8",
    UInt16Array => "UInt16",
    UInt32Array => "UInt32",
    Int8Array => "Int8",
    Int32Array => "Int32",
    Float32Array => "Float32",
    Float64Array => "Float64",
    BooleanArray => "Boolean",
    StringArray => "Utf8",
    ListArray => "List",
}

/// Look up column `name` in `rb` and downcast it to `T`.
pub(crate) fn col<'a, T: Array + ArrowLabel + 'static>(
    rb: &'a RecordBatch,
    name: &str,
    ctx: &str,
) -> PyResult<&'a T> {
    rb.column_by_name(name)
        .ok_or_else(|| PyValueError::new_err(format!("{ctx}missing column {name}")))?
        .as_any()
        .downcast_ref::<T>()
        .ok_or_else(|| PyValueError::new_err(format!("{ctx}column {name} not {}", T::LABEL)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    use arrow::datatypes::{DataType, Field, Schema};

    fn batch() -> RecordBatch {
        let schema = Schema::new(vec![Field::new("region_id", DataType::UInt16, false)]);
        RecordBatch::try_new(
            Arc::new(schema),
            vec![Arc::new(UInt16Array::from(vec![3u16, 5]))],
        )
        .unwrap()
    }

    #[test]
    fn col_reads_a_column_of_the_requested_type() {
        let rb = batch();
        let ids = col::<UInt16Array>(&rb, "region_id", "").unwrap();
        assert_eq!(ids.values().to_vec(), vec![3u16, 5]);
    }

    #[test]
    fn col_reports_missing_and_wrong_type_columns() {
        let rb = batch();
        Python::initialize();
        Python::attach(|py| {
            let cases = [
                (col::<UInt16Array>(&rb, "population", "").unwrap_err(),
                    "missing column population"),
                (col::<UInt16Array>(&rb, "population", "patch ").unwrap_err(),
                    "patch missing column population"),
                (col::<UInt8Array>(&rb, "region_id", "").unwrap_err(),
                    "column region_id not UInt8"),
                (col::<BooleanArray>(&rb, "region_id", "topology ").unwrap_err(),
                    "topology column region_id not Boolean"),
                (col::<StringArray>(&rb, "region_id", "civ input ").unwrap_err(),
                    "civ input column region_id not Utf8"),
            ];
            for (error, message) in cases {
                assert!(error.is_instance_of::<PyValueError>(py));
                assert_eq!(error.value(py).to_string(), message);
            }
        });
    }
}
