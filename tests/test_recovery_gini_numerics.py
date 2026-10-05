"""Numerical regressions for Python/native wealth inequality signals."""
from fractions import Fraction

import numpy as np
import pytest

from chronicler.agent_bridge import build_signals, compute_gini


def _exact_pairwise_gini(values):
    """Independent definition using rational arithmetic, not sorted-gap weights."""
    wealth = [Fraction(float(value)) for value in values]
    if not wealth or sum(wealth) == 0:
        return 0.0
    distances = sum(abs(a - b) for a in wealth for b in wealth)
    return float(distances / (2 * len(wealth) * sum(wealth)))


@pytest.mark.parametrize("count", [1, 3, 7, 64, 257])
@pytest.mark.parametrize("amount", [
    np.float32(0.0), np.float32(0.1), np.float32(1 / 3),
    np.nextafter(np.float32(0), np.float32(1)), np.finfo(np.float32).max,
])
def test_uniform_native_float32_wealth_has_exact_zero_gini(count, amount):
    wealth = np.full(count, amount, dtype=np.float32)
    before = wealth.tobytes()
    assert compute_gini(wealth) == 0.0
    assert wealth.tobytes() == before


@pytest.mark.parametrize("dtype", [np.int32, np.float32, np.float64])
@pytest.mark.parametrize("values,expected", [
    ([], 0.0), ([0, 0, 0], 0.0), ([5], 0.0), ([0, 1], 0.5),
    ([0, 0, 0, 10], 0.75), ([1, 2, 3], 2 / 9), ([2, 2, 4, 8], 0.3125),
])
def test_gini_matches_analytical_and_independent_pairwise_values(dtype, values, expected):
    wealth = np.array(values, dtype=dtype)
    assert compute_gini(wealth) == pytest.approx(expected, rel=1e-15, abs=0.0)
    assert compute_gini(wealth) == pytest.approx(_exact_pairwise_gini(wealth), rel=1e-15, abs=0.0)


def test_nearly_uniform_float32_inequality_is_positive_and_not_clipped():
    wealth = np.array([1.0, 1.0, np.nextafter(np.float32(1), np.float32(2))], dtype=np.float32)
    expected = _exact_pairwise_gini(wealth)
    assert 0.0 < expected < np.finfo(np.float32).eps
    assert compute_gini(wealth) == pytest.approx(expected, rel=1e-15, abs=0.0)


def test_gini_preserves_input_order_dtype_and_readonly_strided_storage():
    original = np.array([9.0, 111.0, 0.1, 222.0, 4.0, 333.0, 1.0], dtype=np.float32)
    wealth = original[::2]
    wealth.setflags(write=False)
    before = original.tobytes()
    expected = _exact_pairwise_gini(wealth)
    assert compute_gini(wealth) == pytest.approx(expected, rel=1e-15, abs=0.0)
    assert original.tobytes() == before
    assert wealth.dtype == np.float32 and not wealth.flags.writeable


def test_gini_is_scale_and_permutation_invariant_in_native_float_range():
    reference = np.array([0.0, 1.0, 2.0, 4.0], dtype=np.float64)
    expected = _exact_pairwise_gini(reference)
    for scale in (1e-40, 1.0, 1e38):
        wealth = (reference * scale)[::-1]
        actual = compute_gini(wealth)
        assert 0.0 <= actual <= 1.0
        assert actual == pytest.approx(expected, rel=1e-15, abs=0.0)


@pytest.mark.parametrize("invalid", [-np.finfo(np.float64).eps, 1.0 + np.finfo(np.float64).eps, float("nan")])
def test_signal_validator_still_rejects_out_of_range_gini(make_world, invalid):
    with pytest.raises(ValueError, match="gini_coefficient"):
        build_signals(make_world(num_civs=1), gini_by_civ={0: invalid})


@pytest.mark.parametrize("values", [
    [1e308, 1.1e308],
    [np.finfo(np.float64).max, np.finfo(np.float64).max],
    [0.0, 0.0, np.finfo(np.float64).max],
    [1e308, np.nextafter(1e308, np.inf)],
    [np.nextafter(np.finfo(np.float64).max, 0.0), np.finfo(np.float64).max],
    [np.nextafter(0.0, 1.0), np.finfo(np.float64).max],
    [np.nextafter(0.0, 1.0), np.nextafter(0.0, 1.0) * 2],
])
def test_finite_float64_extremes_match_exact_pairwise_gini(values):
    wealth = np.array(values, dtype=np.float64)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        actual = compute_gini(wealth)
    assert actual == pytest.approx(_exact_pairwise_gini(wealth), rel=1e-15, abs=0.0)


@pytest.mark.parametrize("values", [
    [np.inf], [-np.inf], [np.nan], [0.0, np.inf],
    [-np.inf, 1.0], [1.0, np.nan], [-np.inf, np.inf],
])
def test_nonfinite_wealth_remains_invalid_for_signals(make_world, values):
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        result = compute_gini(np.array(values, dtype=np.float64))
    assert np.isnan(result)
    with pytest.raises(ValueError, match="gini_coefficient"):
        build_signals(make_world(num_civs=1), gini_by_civ={0: result})
