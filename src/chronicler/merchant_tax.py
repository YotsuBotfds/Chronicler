"""The merchant tax: the treasury is paid what the merchants pay (2026-10).

In agent modes the goods economy assesses every living civ (one that
controls a region) at ``economy.TAX_RATE`` (5%) of the wealth of the living
merchant agents of its affinity (``EconomyResult.treasury_tax``), and Phase 2
pays it into the treasury (``simulation._apply_treasury_tax_from_economy``,
whole units with a fractional carry, ``keep``). Until 2026-10 nobody paid
it: the merchants kept their wealth, so the same wealth was taxed again every
turn it lasted (at the agents' 2% wealth decay a unit of merchant wealth
yielded about 2.5 units of revenue over its life, while staying with the
merchants).

Now the native economy tick takes the tax from the merchants who are
assessed, each paying the rate of its own wealth, once a tick
(``AgentSimulator.tick_economy``; ``chronicler-agents/src/tax.rs``), and
reports what they paid per civ (``EconomyResult.tax_collected``, f64). The
treasury is paid exactly that: whole units now, the fraction carried
(``world._treasury_tax_carry``, kept for a civ that is not taxed this turn).
So per civ and tick ``credited + carry after - carry before = what its
merchants paid``.

Tuning key ``economy.merchant_tax_debited`` (default 1): 0 restores the
earlier rule (the native tick takes nothing; the treasury is paid the
assessment), byte-identical to the simulation before the correction.
``--agents off`` has no merchant agents and no merchant tax; nothing changes
there. Nothing here persists or crosses a turn: the native call keeps no
state, and the carry is the existing persisted field.

``CHRONICLER_CHECK_RESOURCES=1`` checks every tick (:class:`TaxLedger`).
See docs/integration/money-credit.md.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import WorldState


def merchant_tax_debited(world: "WorldState") -> bool:
    """Whether the merchants pay the merchant tax (tuning key
    ``economy.merchant_tax_debited``, default 1)."""
    from chronicler.tuning import K_MERCHANT_TAX_DEBITED, get_override
    return bool(get_override(world, K_MERCHANT_TAX_DEBITED, 1.0))


def tax_rate(world: "WorldState") -> float:
    """The rate the native economy is configured with (``economy.tax_rate``)."""
    from chronicler.economy import TAX_RATE
    from chronicler.tuning import get_override
    return float(get_override(world, "economy.tax_rate", TAX_RATE))


_TOL = 1e-9          # pool and treasury books (f64 sums of f32 wealth)
_RATE_TOL = 1e-5     # what was paid against rate x wealth (f32 products)


class TaxLedger:
    """One tick's merchant-tax balances (``CHRONICLER_CHECK_RESOURCES=1``).

    Raises ``AssertionError("merchant tax ledger does not balance ...")``
    unless, per civ:

    * the merchant agents' wealth (read from the native pool by civ affinity
      before and after the economy tick) fell by exactly what the tick
      reports they paid, and nobody else's changed (under the earlier rule,
      nobody's);
    * what they paid is the tax rate of their wealth, and agrees with the
      assessment (``treasury_tax``);
    * the treasury was credited what they paid: whole units credited plus
      the change of the fractional carry equal it.
    """

    def __init__(self, world, sim, debited: bool) -> None:
        self.turn = world.turn
        self.sim = sim
        self.debited = debited
        self.rate = tax_rate(world)
        self.before = [float(w) for w in sim.merchant_wealth_by_civ()]
        self.problems: list[str] = []
        self.paid: dict[int, float] = {}

    @staticmethod
    def begin(world, sim, debited: bool) -> "TaxLedger | None":
        """The ledger of this tick when the check is on and the native
        runtime can be read, else None (no cost)."""
        from chronicler.production_ledger import resource_check_enabled
        if not resource_check_enabled() or sim is None or not hasattr(sim, "merchant_wealth_by_civ"):
            return None
        return TaxLedger(world, sim, debited)

    def after_economy(self, economy_result) -> None:
        """After the economy tick: the pool moved by what was paid."""
        after = [float(w) for w in self.sim.merchant_wealth_by_civ()]
        paid = getattr(economy_result, "tax_collected", None)
        if self.debited and paid is None:
            self.problems.append("the merchants were to pay but the tick reports no payment")
        paid = dict(paid or {})
        self.paid = paid
        assessed = economy_result.treasury_tax
        for civ in range(max(len(self.before), len(after))):
            before = self.before[civ] if civ < len(self.before) else 0.0
            now = after[civ] if civ < len(after) else 0.0
            moved = before - now
            want = paid.get(civ, 0.0)
            if abs(moved - want) > _TOL * max(1.0, before):
                self.problems.append(f"civ {civ}: merchant wealth {before} -> {now}, paid {want}")
            if civ in paid:
                if want < 0.0 or abs(want - self.rate * before) > _RATE_TOL * max(1.0, self.rate * before):
                    self.problems.append(f"civ {civ}: paid {want} on merchant wealth {before} at rate {self.rate}")
                tax = float(assessed.get(civ, 0.0))
                if abs(want - tax) > _RATE_TOL * max(1.0, tax):
                    self.problems.append(f"civ {civ}: paid {want}, assessed {tax}")
        if set(paid) - set(assessed):
            self.problems.append(f"paid by civs never assessed: {sorted(set(paid) - set(assessed))}")
        self._raise()

    def after_credit(self, taxes: dict, credited: dict, carry_before: dict, carry_after: dict) -> None:
        """After the treasury was paid: credited + carry change = paid."""
        source = self.paid if self.debited else taxes
        for civ, amount in source.items():
            got = credited.get(civ)
            if got is None:
                self.problems.append(f"civ {civ}: paid {amount}, nothing reached a treasury")
                continue
            moved = got + float(carry_after.get(civ, 0.0)) - float(carry_before.get(civ, 0.0))
            if abs(moved - float(amount)) > _TOL * max(1.0, abs(float(amount))):
                self.problems.append(f"civ {civ}: paid {amount}, credited {got} with carry "
                                     f"{carry_before.get(civ, 0.0)} -> {carry_after.get(civ, 0.0)}")
        if self.debited:
            for civ, carry in carry_before.items():
                if civ not in source and carry_after.get(civ) != carry:
                    self.problems.append(f"civ {civ}: untaxed carry {carry} -> {carry_after.get(civ)}")
        self._raise()

    def _raise(self) -> None:
        if self.problems:
            raise AssertionError(f"merchant tax ledger does not balance in turn {self.turn}: "
                                 + "; ".join(self.problems))
