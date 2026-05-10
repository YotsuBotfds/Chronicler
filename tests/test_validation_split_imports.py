"""Regression smoke tests for the validation facade/module split."""


def test_validate_facade_imports_split_modules_and_reexports_core_api():
    from chronicler import validate

    assert callable(validate.scrubbed_equal)
    assert callable(validate.run_determinism_gate)
    assert callable(validate.detect_communities)
    assert callable(validate.run_oracles)
    assert hasattr(validate, "ValidationRequestError")
    assert hasattr(validate, "ValidationDependencyError")


def test_validation_io_and_oracle_modules_are_importable_for_monkeypatching():
    import chronicler.validation_io as validation_io
    import chronicler.validation_oracles as validation_oracles

    assert callable(validation_io._has_pyarrow)
    assert callable(validation_io.load_seed_runs)
    assert callable(validation_oracles.run_regression_summary)
