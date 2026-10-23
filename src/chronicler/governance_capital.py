"""Standalone M66a legitimacy and single-pool political capital kernel.

Evidence: ``docs/superpowers/roadmaps/chronicler-phase8-governance-roadmap.md``
(Execution Ownership & Turn Ordering, M66a, and Determinism Guardrails), and
``dynasties.py:169-186``.
The existing direct-heir/same-dynasty candidate score is NOT a cognomen score.
No simulation model, trait mapping, RNG, bridge, or phase is imported here.

Phase contract: spend turn N's available state with ``resolve_spending``.
After institution and ambition resolution in late Phase 10, pass the remaining
state and resolved evidence to ``accrue_capital``. Its state is effective on
N+1; it cannot authorize the same turn's early politics or governance spends.
Replaying the same opening state or accruing the same epoch twice is a caller
error: this pure kernel does not maintain an event ledger or execute approved
actions. Distinct spend batches may use each returned remaining state.

Roadmap gaps are explicit inputs, not calibrated defaults: normalized cognomen
awards, institutional support conversion, base capital generation, victory and
defeat deltas, peaceful bonus, and contested penalty. The caller supplies an
already-resolved ruler faction and dominant faction (no threshold/tie policy).
Victory counts are caller-owned reign evidence; no retention/decay is assumed.
Ambition outcomes are separately keyed normalized contributions supplied by the
G04 adapter, using its completion/failure deltas rather than the war coefficients.
The caller chooses contribution persistence and must not also count ambition
outcomes as war victories. This kernel rejects duplicate contribution IDs within
a snapshot but does not retain an event ledger across snapshots or reigns.
Accession resets legitimacy to base + dynasty + institutions + succession, as
listed in M66a, without the former ruler's victories or faction bonus. Capital
inheritance/reset at accession is unspecified: ``AccessionInput`` requires the
caller to choose the incoming ruler's opening capital explicitly.

Only the three gated v1 consumers are supported. Overtures and army movements
are deferred because the roadmap says their discrete spend hooks do not exist.
Requests retain caller order, validated to place enact before suppress per the
roadmap's Determinism Guardrails. Forced-repeal placement is unspecified and
therefore supplied explicitly by the caller's sequence, as are same-action ties.
The caller must stage/reserve all competing requests to uphold priority across
separate calls: early suppression precedes late proposal discovery in the runtime,
and this kernel does not implement a phase scheduler or reservation protocol.
Evidence is summed in canonical identity order.
Budget arithmetic uses exact rational values of decimal float spellings, so a
0.30 pool can fund 0.10 + 0.20, without granting a tolerance-based overdraft.
Amounts have finite float views and explicit exact rational accounting fields.
Pass returned states intact between calls: reconstructing them from float views
loses accounting precision. Exact balances also support lossless serialization
as Fraction numerator/denominator pairs; no internal ledger is needed.

Example (illustrative coefficients, NOT runtime calibration):

>>> c = CapitalCoefficients(0.5, 0.1, 0.1, 0.05, 0.1, 0.1, 0.3, 0.1, 0.2)
>>> costs = SpendCosts(0.10, 0.20, 0.15)
>>> prior = GovernanceState(7, 0.5, 0.30)
>>> requests = (SpendRequest("law", GovernanceAction.ENACT_INSTITUTION),
...             SpendRequest("revolt", GovernanceAction.SUPPRESS_SECESSION))
>>> spent = resolve_spending(prior, requests, costs)
>>> [decision.approved for decision in spent.decisions]
[True, True]
>>> result = accrue_capital(spent.state, LegitimacyInputs(), c)
>>> (result.state.effective_turn, result.state.ruler_legitimacy,
...  result.state.political_capital)
(8, 0.5, 0.15)
>>> incoming = accrue_capital(spent.state, LegitimacyInputs(), c,
...                          AccessionInput(SuccessionKind.PEACEFUL, 0.0))
>>> incoming.state.ruler_legitimacy
0.6
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from fractions import Fraction
import math


def _finite(name: str, value: float, *, nonnegative: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (nonnegative and value < 0):
        raise ValueError(f"{name} must be finite" + (" and nonnegative" if nonnegative else ""))


def _count(name: str, value: int) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")


def _identity(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _decimal(value: float) -> Fraction:
    return Fraction(str(value))


def _as_float(value: Fraction) -> float:
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError("calculation exceeds finite float range") from exc
    if not math.isfinite(result):
        raise ValueError("calculation exceeds finite float range")
    return result


def _balance(view: float, exact: Fraction | None) -> Fraction:
    """Validate an optional exact balance against its float presentation."""
    if exact is None:
        return _decimal(view)
    if not isinstance(exact, Fraction):
        raise TypeError("exact capital balance must be a Fraction or None")
    if exact < 0 or _as_float(exact) != view:
        raise ValueError("exact capital balance must be nonnegative and match its float view")
    return exact


class GovernanceAction(str, Enum):
    ENACT_INSTITUTION = "enact_institution"
    SUPPRESS_SECESSION = "suppress_secession"
    FORCE_REPEAL_INSTITUTION = "force_repeal_institution"


class SuccessionKind(str, Enum):
    PEACEFUL = "peaceful"
    CONTESTED = "contested"


@dataclass(frozen=True, slots=True)
class CapitalCoefficients:
    """All calibration supplied by the owner; deltas are normalized units.

    ``institution_support_rate`` converts each aligned institution's clamped
    legitimacy to a ruler delta. ``legitimacy_to_capital_rate`` is capital per
    full-scale legitimacy, not a percentage or Old World point multiplier.
    Penalties are nonnegative magnitudes, subtracted by the kernel.
    """

    legitimacy_base: float
    political_capital_base: float
    legitimacy_to_capital_rate: float
    institution_support_rate: float
    victory_legitimacy_bonus: float
    defeat_legitimacy_penalty: float
    faction_alignment_bonus: float
    peaceful_succession_bonus: float
    contested_succession_penalty: float

    def __post_init__(self) -> None:
        for item in fields(self):
            _finite(item.name, getattr(self, item.name), nonnegative=True)
        if self.legitimacy_base > 1:
            raise ValueError("legitimacy_base must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class DynastyPrestigeInput:
    """One predecessor's caller-normalized cognomen total, weighted by 1/n.

    Number 1 receives full value, 2 receives half, 3 receives a third. The
    caller resolves the predecessor chain and aggregates awards per ruler;
    registry membership and direct-heir bonuses do not supply this evidence.
    """

    predecessor_number: int
    normalized_bonus: float

    def __post_init__(self) -> None:
        _count("predecessor_number", self.predecessor_number)
        if self.predecessor_number == 0:
            raise ValueError("predecessor_number must be positive")
        _finite("normalized_bonus", self.normalized_bonus, nonnegative=True)


@dataclass(frozen=True, slots=True)
class InstitutionSupportInput:
    institution_id: str
    faction_alignment: str
    legitimacy: float

    def __post_init__(self) -> None:
        _identity("institution_id", self.institution_id)
        _identity("faction_alignment", self.faction_alignment)
        _finite("institution legitimacy", self.legitimacy)


@dataclass(frozen=True, slots=True)
class AmbitionLegitimacyInput:
    """Detached G04 outcome contribution; no import of the sibling module.

    The adapter supplies a unique, ruler-scoped outcome key and signed normalized
    delta. M66b's completion/failure targets are +0.10/-0.05; this kernel does not
    choose calibration or whether these contributions persist across a reign.
    """

    contribution_id: str
    normalized_delta: float

    def __post_init__(self) -> None:
        _identity("contribution_id", self.contribution_id)
        _finite("normalized_delta", self.normalized_delta)


@dataclass(frozen=True, slots=True)
class LegitimacyInputs:
    """Resolved evidence snapshot; empty institutions and unknown factions work.

    ``successful_outcomes`` covers successful wars and conquests;
    ``failed_outcomes`` covers failed wars and lost territory. Ambitions use
    ``ambition_contributions`` separately to avoid coefficient confusion and
    double counting. These are resolved snapshots, not event classifiers.
    """

    dynasty: tuple[DynastyPrestigeInput, ...] = ()
    institutions: tuple[InstitutionSupportInput, ...] = ()
    ruler_faction: str | None = None
    dominant_faction: str | None = None
    successful_outcomes: int = 0
    failed_outcomes: int = 0
    ambition_contributions: tuple[AmbitionLegitimacyInput, ...] = ()

    def __post_init__(self) -> None:
        for name, kind, identity in (
            ("dynasty", DynastyPrestigeInput, "predecessor_number"),
            ("institutions", InstitutionSupportInput, "institution_id"),
            ("ambition_contributions", AmbitionLegitimacyInput, "contribution_id"),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(v, kind) for v in values):
                raise TypeError(f"{name} must be a tuple of {kind.__name__}")
            keys = [getattr(v, identity) for v in values]
            if len(set(keys)) != len(keys):
                raise ValueError(f"duplicate {name} identity")
        for name in ("ruler_faction", "dominant_faction"):
            value = getattr(self, name)
            if value is not None:
                _identity(name, value)
        _count("successful_outcomes", self.successful_outcomes)
        _count("failed_outcomes", self.failed_outcomes)


@dataclass(frozen=True, slots=True)
class LegitimacySources:
    """Pre-clamp contributions, in fixed narration order; may total outside [0, 1]."""

    base: float
    dynasty: float
    institutions: float
    victories: float
    ambitions: float
    faction_alignment: float
    succession: float


@dataclass(frozen=True, slots=True)
class LegitimacyResult:
    ruler_legitimacy: float
    sources: LegitimacySources


@dataclass(frozen=True, slots=True)
class GovernanceState:
    """One ruler's pool, with an exact balance and a float presentation.

    For initial float input the exact value is its decimal spelling. Returned
    states always carry the exact remainder; preserve it when copying/saving.
    ``exact_political_capital`` is normalized to a Fraction at construction.
    """

    effective_turn: int
    ruler_legitimacy: float
    political_capital: float
    exact_political_capital: Fraction | None = None

    def __post_init__(self) -> None:
        _count("effective_turn", self.effective_turn)
        _finite("ruler_legitimacy", self.ruler_legitimacy)
        _finite("political_capital", self.political_capital, nonnegative=True)
        if not 0 <= self.ruler_legitimacy <= 1:
            raise ValueError("state ruler_legitimacy must be in [0, 1]")
        object.__setattr__(self, "exact_political_capital",
                           _balance(self.political_capital, self.exact_political_capital))


@dataclass(frozen=True, slots=True)
class AccessionInput:
    """Explicit caller decision on the unspecified capital-transfer policy.

    ``opening_political_capital`` is the incoming ruler's pool before late-turn
    generation. It replaces the prior state's remaining pool only at N+1.
    Supply remaining capital to carry it, or zero to reset it; neither is default.
    To carry a returned state's balance without rounding, also supply its
    ``exact_political_capital`` as ``exact_opening_political_capital``.
    """

    kind: SuccessionKind
    opening_political_capital: float
    exact_opening_political_capital: Fraction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SuccessionKind):
            raise TypeError("kind must be a SuccessionKind")
        _finite("opening_political_capital", self.opening_political_capital, nonnegative=True)
        object.__setattr__(self, "exact_opening_political_capital",
                           _balance(self.opening_political_capital, self.exact_opening_political_capital))


@dataclass(frozen=True, slots=True)
class CapitalAccrual:
    state: GovernanceState
    legitimacy_sources: LegitimacySources
    opening_political_capital: float
    generated_capital: float
    exact_opening_political_capital: Fraction
    exact_generated_capital: Fraction


@dataclass(frozen=True, slots=True)
class SpendCosts:
    """Injected costs; roadmap v1 examples are 0.10, 0.20, 0.15 respectively."""

    enact_institution: float
    suppress_secession: float
    force_repeal_institution: float

    def __post_init__(self) -> None:
        for item in fields(self):
            _finite(item.name, getattr(self, item.name), nonnegative=True)


@dataclass(frozen=True, slots=True)
class SpendRequest:
    request_id: str
    action: GovernanceAction

    def __post_init__(self) -> None:
        _identity("request_id", self.request_id)
        if not isinstance(self.action, GovernanceAction):
            raise TypeError("action must be a GovernanceAction")


@dataclass(frozen=True, slots=True)
class SpendDecision:
    request: SpendRequest
    cost: float
    approved: bool
    capital_before: float
    capital_after: float
    exact_capital_before: Fraction
    exact_capital_after: Fraction


@dataclass(frozen=True, slots=True)
class SpendingResult:
    state: GovernanceState
    decisions: tuple[SpendDecision, ...]


def compute_legitimacy(
    inputs: LegitimacyInputs,
    coefficients: CapitalCoefficients,
    succession: SuccessionKind | None = None,
) -> LegitimacyResult:
    """Recompute normalized legitimacy; prior legitimacy is never added again.

    Finite institutional legitimacy is clamped individually before alignment
    weighting. Final ruler legitimacy is clamped after all source contributions.
    At accession victories, ambitions and faction alignment are excluded from
    the reset formula; cross-reign contribution retention remains caller policy.
    """
    if succession is not None and not isinstance(succession, SuccessionKind):
        raise TypeError("succession must be a SuccessionKind or None")
    dynasty = sum(
        (_decimal(d.normalized_bonus) / d.predecessor_number
         for d in sorted(inputs.dynasty, key=lambda d: d.predecessor_number)),
        Fraction(),
    )
    institutions = sum(
        (_decimal(min(1.0, max(0.0, i.legitimacy)))
         for i in sorted(inputs.institutions, key=lambda i: i.institution_id)
         if i.faction_alignment == inputs.ruler_faction),
        Fraction(),
    ) * _decimal(coefficients.institution_support_rate)
    victories = Fraction()
    ambitions = Fraction()
    faction = Fraction()
    succession_delta = Fraction()
    if succession is None:
        victories = (inputs.successful_outcomes * _decimal(coefficients.victory_legitimacy_bonus)
                     - inputs.failed_outcomes * _decimal(coefficients.defeat_legitimacy_penalty))
        ambitions = sum(
            (_decimal(a.normalized_delta) for a in sorted(
                inputs.ambition_contributions, key=lambda a: a.contribution_id)),
            Fraction(),
        )
        if inputs.ruler_faction is not None and inputs.ruler_faction == inputs.dominant_faction:
            faction = _decimal(coefficients.faction_alignment_bonus)
    elif succession is SuccessionKind.PEACEFUL:
        succession_delta = _decimal(coefficients.peaceful_succession_bonus)
    else:
        succession_delta = -_decimal(coefficients.contested_succession_penalty)
    parts = (_decimal(coefficients.legitimacy_base), dynasty, institutions,
             victories, ambitions, faction, succession_delta)
    sources = LegitimacySources(*(_as_float(part) for part in parts))
    return LegitimacyResult(_as_float(min(Fraction(1), max(Fraction(), sum(parts)))), sources)


def accrue_capital(
    prior: GovernanceState,
    inputs: LegitimacyInputs,
    coefficients: CapitalCoefficients,
    accession: AccessionInput | None = None,
) -> CapitalAccrual:
    """Late Phase 10 generation: base + normalized legitimacy * rate for N+1.

    ``prior`` should be the state remaining after turn N's spend decisions.
    Institution/ambition snapshots are resolved by the caller before this call.
    This operation neither spends nor mutates prior state or simulation objects.
    """
    legitimacy = compute_legitimacy(inputs, coefficients, accession.kind if accession else None)
    generated = (_decimal(coefficients.political_capital_base)
                 + _decimal(legitimacy.ruler_legitimacy)
                 * _decimal(coefficients.legitimacy_to_capital_rate))
    opening = accession.exact_opening_political_capital if accession else prior.exact_political_capital
    # Construction guarantees exact balances are Fraction values.
    assert isinstance(opening, Fraction)
    balance = opening + generated
    state = GovernanceState(prior.effective_turn + 1, legitimacy.ruler_legitimacy,
                            _as_float(balance), balance)
    return CapitalAccrual(state, legitimacy.sources, _as_float(opening), _as_float(generated),
                          opening, generated)


def resolve_spending(
    prior: GovernanceState,
    requests: tuple[SpendRequest, ...],
    costs: SpendCosts,
) -> SpendingResult:
    """Debit one pool in validated caller order, returning approval or denial.

    A denied request consumes nothing; later cheaper requests remain eligible.
    No action is executed. IDs must be unique within the batch to prevent
    accidental duplicate application. There is no hidden cross-call ledger.
    Enact requests after suppression are rejected before any allocation, as
    required by the roadmap's fixed action priority. Forced-repeal position and
    same-action tie order are explicit in the supplied sequence, not inferred.
    Cross-call priority requires caller-owned staging/reservation of the complete
    competing request set; preserving balances alone cannot enforce that policy.
    """
    if not isinstance(requests, tuple) or any(not isinstance(r, SpendRequest) for r in requests):
        raise TypeError("requests must be a tuple of SpendRequest")
    if len({r.request_id for r in requests}) != len(requests):
        raise ValueError("duplicate request_id")
    suppression_seen = False
    for request in requests:
        if request.action is GovernanceAction.SUPPRESS_SECESSION:
            suppression_seen = True
        elif request.action is GovernanceAction.ENACT_INSTITUTION and suppression_seen:
            raise ValueError("spend priority requires enact before suppress")
    remaining = prior.exact_political_capital
    assert isinstance(remaining, Fraction)
    decisions = []
    for request in requests:
        cost = getattr(costs, request.action.value)
        before = remaining
        approved = remaining >= _decimal(cost)
        if approved:
            remaining -= _decimal(cost)
        decisions.append(SpendDecision(request, cost, approved, _as_float(before), _as_float(remaining),
                                       before, remaining))
    state = GovernanceState(prior.effective_turn, prior.ruler_legitimacy, _as_float(remaining), remaining)
    return SpendingResult(state, tuple(decisions))
