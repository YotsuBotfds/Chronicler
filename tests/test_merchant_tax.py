"""The merchant tax: the treasury is paid what the merchants paid
(chronicler.merchant_tax, docs/integration/money-credit.md). Python side:
the treasury credit and its carry, the economy result's payments, the tuning
key and the ledger, with stand-ins for the native pool."""
from __future__ import annotations

from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler.accumulator import StatAccumulator
from chronicler.merchant_tax import TaxLedger, merchant_tax_debited, tax_rate
from chronicler.simulation import _apply_treasury_tax_from_economy


def _credit(world, result, ledger=None) -> list[int]:
    acc = StatAccumulator()
    before = [c.treasury for c in world.civilizations]
    _apply_treasury_tax_from_economy(world, acc, result, tax_ledger=ledger)
    acc.apply_keep(world)
    return [c.treasury - b for c, b in zip(world.civilizations, before)]


def test_the_treasury_is_paid_what_the_merchants_paid(sample_world):
    sample_world._treasury_tax_carry = {}
    result = SimpleNamespace(treasury_tax={0: 5.3, 1: 2.0}, tax_collected={0: 5.25, 1: 1.5})
    gained = _credit(sample_world, result)
    assert gained[:2] == [5, 1]
    assert sample_world._treasury_tax_carry == {0: pytest.approx(0.25), 1: pytest.approx(0.5)}


def test_without_payments_the_assessment_is_paid_as_before(sample_world):
    """The Python oracle and the earlier rule (tax_collected None): the
    assessment is paid and only this turn's civs keep a carry."""
    sample_world._treasury_tax_carry = {0: 0.5, 1: 0.4}
    result = SimpleNamespace(treasury_tax={0: 5.3})
    gained = _credit(sample_world, result)
    assert gained[:2] == [5, 0]
    assert sample_world._treasury_tax_carry == {0: pytest.approx(0.8)}


def test_a_civ_not_taxed_this_turn_keeps_what_its_merchants_paid(sample_world):
    sample_world._treasury_tax_carry = {0: 0.5, 1: 0.4}
    result = SimpleNamespace(treasury_tax={0: 5.3}, tax_collected={0: 5.25})
    gained = _credit(sample_world, result)
    assert gained[:2] == [5, 0]
    assert sample_world._treasury_tax_carry == {0: pytest.approx(0.75), 1: pytest.approx(0.4)}


def test_payments_are_consumed_once_a_turn_and_the_carry_reaches_the_treasury(sample_world):
    """Multi-turn: each turn's payment is credited once (whole units, the
    fraction carried), nothing accumulates in the economy result, and over
    the turns the treasury receives everything paid but the carry."""
    sample_world._treasury_tax_carry = {}
    paid = [0.6, 0.6, 0.6, 2.45, 0.0]
    gained, carries = [], []
    for amount in paid:
        result = SimpleNamespace(treasury_tax={0: amount}, tax_collected={0: amount})
        gained.append(_credit(sample_world, result)[0])
        carries.append(sample_world._treasury_tax_carry[0])
        assert result.tax_collected == {0: amount}
    assert gained == [0, 1, 0, 3, 0]
    assert carries[-1] == pytest.approx(0.25)
    assert sum(gained) + carries[-1] == pytest.approx(sum(paid))


def _civ_batch(with_paid: bool):
    cols = {
        "civ_id": pa.array([0, 1], type=pa.uint8()),
        "treasury_tax": pa.array([5.0, 2.0], type=pa.float32()),
        "tithe_base": pa.array([100.0, 40.0], type=pa.float32()),
        "priest_tithe_share": pa.array([10.0, 4.0], type=pa.float32()),
    }
    if with_paid:
        cols["tax_collected"] = pa.array([4.999999, 2.0], type=pa.float64())
    return pa.record_batch(cols)


def _reconstruct(civ_batch, **kwargs):
    from test_economy_bridge import _make_mock_return_batches, _make_two_region_world
    from chronicler.economy import reconstruct_economy_result
    world = _make_two_region_world()
    region, _civ, obs, upstream, conservation = _make_mock_return_batches(world)
    return reconstruct_economy_result(region, civ_batch, obs, upstream, conservation, world, **kwargs)


def test_the_economy_result_reads_the_payments():
    debited = _reconstruct(_civ_batch(True), tax_debited=True)
    assert debited.tax_collected == {0: 4.999999, 1: 2.0}
    assert debited.treasury_tax[0] == pytest.approx(5.0)
    restored = _reconstruct(_civ_batch(True))
    assert restored.tax_collected is None
    with pytest.raises(RuntimeError, match="tax_collected"):
        _reconstruct(_civ_batch(False), tax_debited=True)


def test_the_tuning_key_restores_the_earlier_rule(sample_world):
    from chronicler.tuning import KNOWN_OVERRIDES, K_MERCHANT_TAX_DEBITED
    assert K_MERCHANT_TAX_DEBITED == "economy.merchant_tax_debited"
    assert K_MERCHANT_TAX_DEBITED in KNOWN_OVERRIDES
    sample_world.tuning_overrides = {}
    assert merchant_tax_debited(sample_world) is True
    sample_world.tuning_overrides = {K_MERCHANT_TAX_DEBITED: 0}
    assert merchant_tax_debited(sample_world) is False
    sample_world.tuning_overrides = {"economy.tax_rate": 0.08}
    assert tax_rate(sample_world) == pytest.approx(0.08)


class _Pool:
    """Stand-in for the native pool's merchant wealth by civ affinity."""

    def __init__(self, wealth):
        self.wealth = list(wealth) + [0.0] * (256 - len(wealth))

    def merchant_wealth_by_civ(self):
        return list(self.wealth)


def _ledger(world, pool, debited=True):
    return TaxLedger(world, pool, debited)


def test_the_ledger_balances_a_tick_whose_merchants_paid_the_treasury(sample_world):
    sample_world._treasury_tax_carry = {1: 0.3}
    pool = _Pool([100.0, 40.0])
    ledger = _ledger(sample_world, pool)
    pool.wealth[0], pool.wealth[1] = 95.0, 38.0
    result = SimpleNamespace(treasury_tax={0: 5.0, 1: 2.0}, tax_collected={0: 5.0, 1: 2.0})
    ledger.after_economy(result)
    assert _credit(sample_world, result, ledger)[:2] == [5, 2]


@pytest.mark.parametrize("broken", ["pool", "rate", "assessment", "unpaid", "carry", "restored"])
def test_the_ledger_catches_a_broken_book(sample_world, broken):
    sample_world._treasury_tax_carry = {2: 0.5}
    pool = _Pool([100.0, 40.0])
    ledger = _ledger(sample_world, pool, debited=broken != "restored")
    paid = {0: 5.0, 1: 2.0}
    assessed = {0: 5.0, 1: 2.0}
    pool.wealth[0], pool.wealth[1] = 95.0, 38.0
    if broken == "pool":
        pool.wealth[0] = 95.5          # the merchants lost less than they paid
    elif broken == "rate":
        paid[1], pool.wealth[1] = 3.0, 37.0   # 3 of 40 is not 5%
    elif broken == "assessment":
        assessed[0] = 5.5
    result = SimpleNamespace(treasury_tax=assessed, tax_collected=None if broken == "restored" else paid)
    if broken in ("pool", "rate", "assessment", "restored"):
        with pytest.raises(AssertionError, match="merchant tax ledger does not balance"):
            ledger.after_economy(result)
        return
    ledger.after_economy(result)
    if broken == "unpaid":
        with pytest.raises(AssertionError, match="nothing reached a treasury"):
            ledger.after_credit(result.tax_collected, {0: 5}, {}, {0: 0.0, 1: 0.0})
    else:
        with pytest.raises(AssertionError, match="untaxed carry"):
            ledger.after_credit(result.tax_collected, {0: 5, 1: 2}, {2: 0.5}, {0: 0.0, 1: 0.0})


def test_the_ledger_under_the_earlier_rule_expects_no_payment(sample_world):
    sample_world._treasury_tax_carry = {}
    pool = _Pool([100.0, 40.0])
    ledger = _ledger(sample_world, pool, debited=False)
    result = SimpleNamespace(treasury_tax={0: 5.0, 1: 2.0}, tax_collected=None)
    ledger.after_economy(result)
    assert _credit(sample_world, result, ledger)[:2] == [5, 2]


def test_the_ledger_is_off_without_the_check(sample_world, monkeypatch):
    monkeypatch.delenv("CHRONICLER_CHECK_RESOURCES", raising=False)
    assert TaxLedger.begin(sample_world, _Pool([1.0]), True) is None
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    assert isinstance(TaxLedger.begin(sample_world, _Pool([1.0]), True), TaxLedger)
    assert TaxLedger.begin(sample_world, None, True) is None
    assert TaxLedger.begin(sample_world, object(), True) is None
