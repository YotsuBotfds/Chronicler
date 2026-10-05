"""Standalone M63a kernel; no simulation, persistence, RNG, or action modifiers.

Source: docs/superpowers/roadmaps/chronicler-phase8-governance-roadmap.md,
M63a, M63b governing costs, and Determinism Guardrails. Political-capital
allocation belongs exclusively to G03; this kernel consumes detached approvals.
Before M66a the caller can explicitly authorize the roadmap's free decisions.

Contracts:
* ``fund_institutions`` requires an explicit ``FundingPolicy``. Its standalone
  BASE_FIRST_FULL_DEBIT option measures coverage before a full base + institution
  debit, with base costs taking priority. This is a named, opt-in fiscal
  convention, NOT an integration policy lock. Alternatively the caller supplies
  an EXTERNAL_AGGREGATE_RECORD from the actual funding step; its recorded ratio
  is authoritative and is not inferred again from treasury or affordability.
* ``resolve_institutions`` runs late in N, after politics and tick_factions.
  It consumes that exact funding record, never later treasury. Aggregate
  coverage < 1 erodes all institutions; full coverage recovers all, as specified
  by the per-civ last_institution_funding_ratio. Zero demand is fully funded.
* Only the returned snapshot may feed N+1 consumers. A snapshot cannot be
  funded on another turn, including the turn in which it was produced.
* ``InstitutionSpendDecisions`` is required and applies to resolution turn N.
  Missing/denied approvals prevent enact/forced repeal; neglect is automatic.
  Results acknowledge used approvals, without allocating, charging, refunding,
  or checking capital affordability. G03 and integration own those operations.

Genuine roadmap gaps, deliberately supplied by the caller:
* Sixteen opposing-faction assignments and sixteen cost coefficients have no
  specified table. ``InstitutionCoefficients`` requires the complete table.
* Candidate selection and the angry/neutral stall algorithm are unspecified.
  ``ProposalAttempt`` supplies a chosen type and a [0, 1) proposal draw;
  only the documented raw-influence > .30 veto is implemented. No mood or
  stall probability is inferred from the 1.5/.5 weights.
* Same-turn repeal/proposal slot reuse is unspecified. ``ResolutionOrder``
  must be supplied; it also controls whether repeal removes a conflict before
  proposals. Funding-driven neglect collapse precedes both late decisions.
* Attempt multiplicity is not spelled out. This boundary accepts one chosen
  institution and one per-turn draw per faction, matching the per-turn proposal
  chance. Multi-candidate roll semantics require a later specification.
* Fiscal allocation/partial payment and per-institution coverage remain open.
  This version consumes the roadmap's aggregate funding ratio. Monetary values
  are finite float currency units; integer treasury rounding and denominator
  observation time belong to the future adapter, not an implicit conversion.
* Early suppression versus late enact discovery and forced-repeal spending
  priority remain unresolved. Supplied approvals do not settle chronology.

Threshold comparisons use ordinary binary floating-point arithmetic, with no
decimal rounding or tolerance (e.g. .06 - .01 is just below .05).

The two explicitly named conflict pairs are implemented; additional regime
families, literacy eligibility, sanctions, modifier buckets and all
native/phase wiring require later specs/owners. No calibration has defaults.

Example (fixture coefficients, NOT proposed production calibration):

    >>> coefficients = InstitutionCoefficients(
    ...     proposal_probability=1.0, legitimacy_erosion_rate=0.1,
    ...     legitimacy_recovery_rate=0.02,
    ...     rules=tuple(InstitutionRule(t, Faction.MERCHANT
    ...                 if alignment(t) != Faction.MERCHANT else Faction.MILITARY,
    ...                 2.0) for t in InstitutionType),
    ... )
    >>> current = InstitutionSnapshot(7, ())
    >>> funding = fund_institutions(turn=7, snapshot=current, treasury=20.0,
    ...     base_governing_cost=3.0, policy=FundingPolicy.BASE_FIRST_FULL_DEBIT)
    >>> spending = InstitutionSpendDecisions(7, (
    ...     InstitutionSpendDecision(InstitutionOperation.ENACT,
    ...                              InstitutionType.CONSCRIPTION, True),))
    >>> result = resolve_institutions(
    ...     turn=7, snapshot=current, factions=FactionWeights(.6, .1, .2, .1),
    ...     funding=funding, coefficients=coefficients, region_count=4,
    ...     trade_route_count=0,
    ...     proposals=(ProposalAttempt(InstitutionType.CONSCRIPTION, 0.0),),
    ...     resolution_order=ResolutionOrder.REPEAL_THEN_PROPOSE,
    ...     spend_decisions=spending,
    ... )
    >>> assert result.next_state.effective_turn == 8
    >>> assert result.next_state.institutions[0].enforcement_cost == 8.0
    >>> assert funding.last_institution_enforcement_cost == 0.0
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math
from types import MappingProxyType


class Faction(str, Enum):
    """Boundary values/order match the existing FactionType, without importing it."""

    MILITARY = "military"
    MERCHANT = "merchant"
    CULTURAL = "cultural"
    CLERGY = "clergy"


class InstitutionType(str, Enum):
    MILITARY_ACCLAMATION = "military_acclamation"
    CONSCRIPTION = "conscription"
    FRONTIER_GARRISONS = "frontier_garrisons"
    MARTIAL_LAW = "martial_law"
    PROPERTY_RIGHTS = "property_rights"
    FREE_TRADE = "free_trade"
    MERCHANT_COURTS = "merchant_courts"
    TAX_CODE = "tax_code"
    WRITTEN_LAW = "written_law"
    PATRONAGE_SYSTEM = "patronage_system"
    EDUCATION = "education"
    REPUBLICAN_VIRTUE = "republican_virtue"
    TEMPLE_TITHE = "temple_tithe"
    DIVINE_RIGHT = "divine_right"
    HOLY_INQUISITION = "holy_inquisition"
    COMMONS_MANAGEMENT = "commons_management"


MAX_ACTIVE_INSTITUTIONS = 3
FACTION_DOMINANCE_THRESHOLD = 0.35
FACTION_BLOCK_THRESHOLD = 0.30
FACTION_REPEAL_THRESHOLD = 0.40
LEGITIMACY_COLLAPSE_THRESHOLD = 0.05

_TYPES = tuple(InstitutionType)
_FACTIONS = tuple(Faction)
_INDEX = MappingProxyType({t: i for i, t in enumerate(_TYPES)})
_CONFLICT_PAIRS = (
    (InstitutionType.REPUBLICAN_VIRTUE, InstitutionType.DIVINE_RIGHT),
    (InstitutionType.FREE_TRADE, InstitutionType.HOLY_INQUISITION),
)
INSTITUTION_CONFLICTS = MappingProxyType({
    t: frozenset(b if a == t else a for a, b in _CONFLICT_PAIRS if t in (a, b))
    for t in _TYPES
})
_PER_REGION = frozenset((InstitutionType.FRONTIER_GARRISONS,
                         InstitutionType.CONSCRIPTION, InstitutionType.COMMONS_MANAGEMENT))
_PER_ROUTE = frozenset((InstitutionType.FREE_TRADE,
                        InstitutionType.MERCHANT_COURTS, InstitutionType.TAX_CODE))


def _number(name: str, value: float, *, minimum: float | None = None,
            maximum: float | None = None) -> None:
    try:
        finite = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be finite")
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValueError(f"{name} out of range")


def _count(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _enum(name: str, value: Enum, cls: type[Enum]) -> None:
    if not isinstance(value, cls):
        raise ValueError(f"{name} must be a {cls.__name__}")


def alignment(institution_type: InstitutionType) -> Faction:
    """Four consecutive institutions per faction in roadmap enum order."""
    _enum("institution_type", institution_type, InstitutionType)
    return _FACTIONS[_INDEX[institution_type] // 4]


@dataclass(frozen=True)
class FactionWeights:
    military: float
    merchant: float
    cultural: float
    clergy: float

    def __post_init__(self) -> None:
        values = tuple(self.weight(f) for f in _FACTIONS)
        for value in values:
            _number("faction influence", value, minimum=0.0, maximum=1.0)
        if not math.isclose(math.fsum(values), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("faction influences must sum to one; no implicit normalization")

    def weight(self, faction: Faction) -> float:
        _enum("faction", faction, Faction)
        return getattr(self, faction.value)


@dataclass(frozen=True)
class InstitutionRule:
    institution_type: InstitutionType
    opposing_faction: Faction
    enforcement_coefficient: float

    def __post_init__(self) -> None:
        _enum("institution_type", self.institution_type, InstitutionType)
        _enum("opposing_faction", self.opposing_faction, Faction)
        if self.opposing_faction == alignment(self.institution_type):
            raise ValueError("opposition cannot be the aligned faction")
        _number("enforcement_coefficient", self.enforcement_coefficient, minimum=0.0)


@dataclass(frozen=True)
class InstitutionCoefficients:
    proposal_probability: float
    legitimacy_erosion_rate: float
    legitimacy_recovery_rate: float
    rules: tuple[InstitutionRule, ...]

    def __post_init__(self) -> None:
        for name in ("proposal_probability", "legitimacy_erosion_rate", "legitimacy_recovery_rate"):
            _number(name, getattr(self, name), minimum=0.0, maximum=1.0)
        rules = tuple(self.rules)
        if any(not isinstance(r, InstitutionRule) for r in rules):
            raise ValueError("rules must contain InstitutionRule values")
        if len(rules) != len(_TYPES) or {r.institution_type for r in rules} != set(_TYPES):
            raise ValueError("exactly one coefficient/opposition rule per institution is required")
        object.__setattr__(self, "rules", tuple(sorted(rules, key=lambda r: _INDEX[r.institution_type])))

    def rule(self, institution_type: InstitutionType) -> InstitutionRule:
        _enum("institution_type", institution_type, InstitutionType)
        return self.rules[_INDEX[institution_type]]


@dataclass(frozen=True)
class InstitutionState:
    institution_type: InstitutionType
    enacted_turn: int
    legitimacy: float
    enforcement_cost: float
    opposing_faction: Faction

    def __post_init__(self) -> None:
        _enum("institution_type", self.institution_type, InstitutionType)
        _enum("opposing_faction", self.opposing_faction, Faction)
        _count("enacted_turn", self.enacted_turn)
        _number("legitimacy", self.legitimacy, minimum=0.0, maximum=1.0)
        _number("enforcement_cost", self.enforcement_cost, minimum=0.0)
        if self.opposing_faction == self.faction_alignment:
            raise ValueError("opposition cannot be the aligned faction")

    @property
    def faction_alignment(self) -> Faction:
        return alignment(self.institution_type)


@dataclass(frozen=True)
class InstitutionSnapshot:
    effective_turn: int
    institutions: tuple[InstitutionState, ...]

    def __post_init__(self) -> None:
        _count("effective_turn", self.effective_turn)
        institutions = tuple(self.institutions)
        if any(not isinstance(i, InstitutionState) for i in institutions):
            raise ValueError("institutions must contain InstitutionState values")
        types = {i.institution_type for i in institutions}
        if len(institutions) > MAX_ACTIVE_INSTITUTIONS or len(types) != len(institutions):
            raise ValueError("at most three distinct institutions may be active")
        if any(i.enacted_turn >= self.effective_turn for i in institutions):
            raise ValueError("enactment on N is only effective on N+1")
        if any(INSTITUTION_CONFLICTS[t] & types for t in types):
            raise ValueError("conflicting active institutions")
        object.__setattr__(self, "institutions", tuple(sorted(institutions, key=lambda i: _INDEX[i.institution_type])))


class FundingPolicy(str, Enum):
    BASE_FIRST_FULL_DEBIT = "base_first_full_debit"
    EXTERNAL_AGGREGATE_RECORD = "external_aggregate_record"


@dataclass(frozen=True)
class FundingResult:
    """Detached funding-step observation; no later treasury is inferred.

    Helper-policy records are checked against its explicit convention in the
    resolver. External records trust the recorded coverage, validate finite
    amounts/ranges and demand identity, and do not recheck affordability.
    """

    charged_snapshot: InstitutionSnapshot
    treasury_before: float
    treasury_after: float
    last_base_governing_cost: float
    last_institution_enforcement_cost: float
    last_institution_funding_ratio: float
    policy: FundingPolicy

    def __post_init__(self) -> None:
        _enum("funding policy", self.policy, FundingPolicy)
        if not isinstance(self.charged_snapshot, InstitutionSnapshot):
            raise ValueError("funding requires an InstitutionSnapshot")
        for name in ("treasury_before", "treasury_after"):
            _number(name, getattr(self, name))
        for name in ("last_base_governing_cost", "last_institution_enforcement_cost"):
            _number(name, getattr(self, name), minimum=0.0)
        _number("last_institution_funding_ratio", self.last_institution_funding_ratio,
                minimum=0.0, maximum=1.0)
        if self.last_institution_enforcement_cost == 0 and self.last_institution_funding_ratio != 1:
            raise ValueError("zero institutional demand must be fully funded")


def fund_institutions(*, turn: int, snapshot: InstitutionSnapshot,
                      treasury: float, base_governing_cost: float,
                      policy: FundingPolicy) -> FundingResult:
    """Explicit standalone full-debit convention, including debt.

    External observations are constructed as FundingResult instead. This
    helper does not manufacture external coverage or pick a policy by default.

    Supplied enforcement_cost is the persisted per-turn demand, computed at
    enactment. The roadmap does not specify repricing existing institutions
    when region/route counts change, so this helper does not silently do so.
    """
    _count("turn", turn)
    _enum("funding policy", policy, FundingPolicy)
    if policy != FundingPolicy.BASE_FIRST_FULL_DEBIT:
        raise ValueError("external funding requires a supplied FundingResult")
    if snapshot.effective_turn != turn:
        raise ValueError("snapshot is not effective for this funding turn")
    _number("treasury", treasury)
    _number("base_governing_cost", base_governing_cost, minimum=0.0)
    try:
        demand = math.fsum(i.enforcement_cost for i in snapshot.institutions)
    except OverflowError as exc:
        raise ValueError("institutional demand overflow") from exc
    total = base_governing_cost + demand
    treasury_after = treasury - total
    _number("total governing cost", total, minimum=0.0)
    _number("treasury_after", treasury_after)
    ratio = min(1.0, max(0.0, treasury - base_governing_cost) / demand) if demand else 1.0
    return FundingResult(snapshot, treasury, treasury_after, base_governing_cost, demand, ratio, policy)


def enforcement_cost(*, institution_type: InstitutionType,
                     coefficients: InstitutionCoefficients,
                     region_count: int, trade_route_count: int) -> float:
    """Rate * regions/routes, otherwise flat, exactly as M63a classifies."""
    _count("region_count", region_count)
    _count("trade_route_count", trade_route_count)
    units = region_count if institution_type in _PER_REGION else (
        trade_route_count if institution_type in _PER_ROUTE else 1)
    try:
        cost = coefficients.rule(institution_type).enforcement_coefficient * units
    except OverflowError as exc:
        raise ValueError("enforcement cost overflow") from exc
    _number("enforcement cost", cost, minimum=0.0)
    return cost


def proposal_candidates(snapshot: InstitutionSnapshot, factions: FactionWeights
                        ) -> tuple[InstitutionType, ...]:
    """Canonical (faction index, institution index) list, before opposition veto.

    The cap and explicit conflicts filter candidates; influences never order
    them. Call again after repeal if the caller elects to reuse freed slots.
    """
    if len(snapshot.institutions) == MAX_ACTIVE_INSTITUTIONS:
        return ()
    active = {i.institution_type for i in snapshot.institutions}
    return tuple(t for t in _TYPES if t not in active and
                 not INSTITUTION_CONFLICTS[t] & active and
                 factions.weight(alignment(t)) > FACTION_DOMINANCE_THRESHOLD)


@dataclass(frozen=True)
class ProposalAttempt:
    institution_type: InstitutionType
    draw: float

    def __post_init__(self) -> None:
        _enum("institution_type", self.institution_type, InstitutionType)
        _number("proposal draw", self.draw, minimum=0.0, maximum=1.0)
        if self.draw == 1.0:
            raise ValueError("proposal draw must be less than one")


class ResolutionOrder(str, Enum):
    REPEAL_THEN_PROPOSE = "repeal_then_propose"
    PROPOSE_THEN_REPEAL = "propose_then_repeal"


class ProposalStatus(str, Enum):
    ENACTED = "enacted"
    NOT_DOMINANT = "not_dominant"
    ALREADY_ACTIVE = "already_active"
    CAP_REACHED = "cap_reached"
    CONFLICT = "conflict"
    ROLL_FAILED = "roll_failed"
    OPPOSED = "opposed"
    SPEND_DENIED = "spend_denied"


class InstitutionOperation(str, Enum):
    ENACT = "enact"
    FORCE_REPEAL = "force_repeal"


@dataclass(frozen=True)
class InstitutionSpendDecision:
    """An external approval, not a capital balance or affordability estimate."""

    operation: InstitutionOperation
    institution_type: InstitutionType
    allowed: bool

    def __post_init__(self) -> None:
        _enum("operation", self.operation, InstitutionOperation)
        _enum("institution_type", self.institution_type, InstitutionType)
        if type(self.allowed) is not bool:
            raise ValueError("spend decision must be an explicit boolean")


@dataclass(frozen=True)
class InstitutionSpendDecisions:
    """Per-polity approvals for N; key is (turn, operation, institution_type).

    Polity identity/grouping is owned by the caller. Empty or missing keys deny.
    Canonical order here is serialization order, not capital spending priority.
    """

    turn: int
    decisions: tuple[InstitutionSpendDecision, ...]

    def __post_init__(self) -> None:
        _count("spend decision turn", self.turn)
        decisions = tuple(self.decisions)
        if any(not isinstance(d, InstitutionSpendDecision) for d in decisions):
            raise ValueError("decisions must contain InstitutionSpendDecision values")
        if len({(d.operation, d.institution_type) for d in decisions}) != len(decisions):
            raise ValueError("duplicate institution spend decision key")
        order = tuple(InstitutionOperation)
        object.__setattr__(self, "decisions", tuple(sorted(decisions, key=lambda d: (
            order.index(d.operation), _INDEX[d.institution_type]))))

    def permits(self, operation: InstitutionOperation, institution_type: InstitutionType) -> bool:
        _enum("operation", operation, InstitutionOperation)
        _enum("institution_type", institution_type, InstitutionType)
        return any(d.operation == operation and d.institution_type == institution_type and d.allowed
                   for d in self.decisions)


class RepealStatus(str, Enum):
    REPEALED = "repealed"
    SPEND_DENIED = "spend_denied"


@dataclass(frozen=True)
class RepealOutcome:
    """Only faction-eligible forced repeals; neglect uses narrative events."""

    institution_type: InstitutionType
    status: RepealStatus


@dataclass(frozen=True)
class ProposalOutcome:
    institution_type: InstitutionType
    status: ProposalStatus


@dataclass(frozen=True)
class InstitutionEvent:
    """Narrative event names from M63; no invented severity calibration."""

    event_type: str
    institution_type: InstitutionType
    turn: int
    effective_turn: int
    reason: str


@dataclass(frozen=True)
class InstitutionTurnResult:
    """Used approvals are acknowledgements in lifecycle order, not allocations.

    No acknowledgements for denied/unused approvals; integration reconciles
    these with G03's staged requests. They never debit or refund its ledger.
    """

    next_state: InstitutionSnapshot
    funding: FundingResult
    events: tuple[InstitutionEvent, ...]
    proposal_outcomes: tuple[ProposalOutcome, ...]
    repeal_outcomes: tuple[RepealOutcome, ...]
    used_spend_decisions: tuple[InstitutionSpendDecision, ...]


def resolve_institutions(*, turn: int, snapshot: InstitutionSnapshot,
                         factions: FactionWeights, funding: FundingResult,
                         coefficients: InstitutionCoefficients, region_count: int,
                         trade_route_count: int, proposals: tuple[ProposalAttempt, ...],
                         resolution_order: ResolutionOrder,
                         spend_decisions: InstitutionSpendDecisions) -> InstitutionTurnResult:
    """Pure late-N lifecycle; empty proposals explicitly means no attempts.

    One supplied attempt per faction, sorted by roadmap enum order. Multiple
    factions above .35 qualify even if their influences differ. Forced repeal
    uses the supplied state's opposing faction; proposals use injected rules.
    Calibration must retain that opposition assignment for existing states.
    Repealed/neglected institutions may be proposed again only if the caller
    explicitly requests them; there is no implicit replacement selection.
    Required approvals are applied after structural eligibility, never priced
    or rechecked against treasury/capital. Unknown/missing approval keys deny.
    """
    _count("turn", turn)
    _count("region_count", region_count)
    _count("trade_route_count", trade_route_count)
    _enum("resolution_order", resolution_order, ResolutionOrder)
    if snapshot.effective_turn != turn or funding.charged_snapshot != snapshot:
        raise ValueError("funding must match this turn and exact institution snapshot")
    if not isinstance(spend_decisions, InstitutionSpendDecisions) or spend_decisions.turn != turn:
        raise ValueError("spend decisions must apply to this resolution turn")
    try:
        demand = math.fsum(i.enforcement_cost for i in snapshot.institutions)
    except OverflowError as exc:
        raise ValueError("institutional demand overflow") from exc
    if funding.last_institution_enforcement_cost != demand:
        raise ValueError("inconsistent funding bookkeeping")
    if funding.policy == FundingPolicy.BASE_FIRST_FULL_DEBIT:
        expected = fund_institutions(turn=turn, snapshot=snapshot,
                                     treasury=funding.treasury_before,
                                     base_governing_cost=funding.last_base_governing_cost,
                                     policy=funding.policy)
        if funding != expected:
            raise ValueError("inconsistent funding bookkeeping")
    if any(i.opposing_faction != coefficients.rule(i.institution_type).opposing_faction
           for i in snapshot.institutions):
        raise ValueError("coefficient opposition disagrees with supplied institution state")
    attempts = tuple(proposals)
    if any(not isinstance(p, ProposalAttempt) for p in attempts):
        raise ValueError("proposals must contain ProposalAttempt values")
    if len({alignment(p.institution_type) for p in attempts}) != len(attempts):
        raise ValueError("at most one proposal attempt per faction per turn")
    attempts = tuple(sorted(attempts, key=lambda p: _INDEX[p.institution_type]))
    active: dict[InstitutionType, InstitutionState] = {}
    events: list[InstitutionEvent] = []
    outcomes: list[ProposalOutcome] = []
    repeal_outcomes: list[RepealOutcome] = []
    used: list[InstitutionSpendDecision] = []

    def emit(event_type: str, t: InstitutionType, reason: str) -> None:
        events.append(InstitutionEvent(event_type, t, turn, turn + 1, reason))

    for state in snapshot.institutions:
        if funding.last_institution_funding_ratio < 1.0:
            legitimacy = max(0.0, state.legitimacy - coefficients.legitimacy_erosion_rate)
            emit("institution_enforcement_lapse", state.institution_type, "underfunded")
        else:
            legitimacy = min(1.0, state.legitimacy + coefficients.legitimacy_recovery_rate)
        if legitimacy < LEGITIMACY_COLLAPSE_THRESHOLD:
            emit("institution_repealed", state.institution_type, "neglect")
        else:
            active[state.institution_type] = replace(state, legitimacy=legitimacy)

    def repeal() -> None:
        for t in _TYPES:
            state = active.get(t)
            # Newly enacted institutions cannot be force-repealed in their
            # enactment turn: proposal veto .30 already excludes > .40.
            if state is not None and factions.weight(state.opposing_faction) > FACTION_REPEAL_THRESHOLD:
                if spend_decisions.permits(InstitutionOperation.FORCE_REPEAL, t):
                    del active[t]
                    emit("institution_repealed", t, "faction_opposition")
                    repeal_outcomes.append(RepealOutcome(t, RepealStatus.REPEALED))
                    used.append(InstitutionSpendDecision(InstitutionOperation.FORCE_REPEAL, t, True))
                else:
                    repeal_outcomes.append(RepealOutcome(t, RepealStatus.SPEND_DENIED))

    def propose() -> None:
        for attempt in attempts:
            t = attempt.institution_type
            rule = coefficients.rule(t)
            if factions.weight(alignment(t)) <= FACTION_DOMINANCE_THRESHOLD:
                status = ProposalStatus.NOT_DOMINANT
            elif t in active:
                status = ProposalStatus.ALREADY_ACTIVE
            elif len(active) >= MAX_ACTIVE_INSTITUTIONS:
                status = ProposalStatus.CAP_REACHED
            elif INSTITUTION_CONFLICTS[t] & active.keys():
                status = ProposalStatus.CONFLICT
            elif attempt.draw >= coefficients.proposal_probability:
                status = ProposalStatus.ROLL_FAILED
            elif factions.weight(rule.opposing_faction) > FACTION_BLOCK_THRESHOLD:
                status = ProposalStatus.OPPOSED
            elif not spend_decisions.permits(InstitutionOperation.ENACT, t):
                status = ProposalStatus.SPEND_DENIED
            else:
                active[t] = InstitutionState(t, turn, 1.0, enforcement_cost(
                    institution_type=t, coefficients=coefficients,
                    region_count=region_count, trade_route_count=trade_route_count),
                    rule.opposing_faction)
                status = ProposalStatus.ENACTED
                emit("institution_enacted", t, "faction_proposal")
                used.append(InstitutionSpendDecision(InstitutionOperation.ENACT, t, True))
            outcomes.append(ProposalOutcome(t, status))

    if resolution_order == ResolutionOrder.REPEAL_THEN_PROPOSE:
        repeal()
        propose()
    else:
        propose()
        repeal()
    return InstitutionTurnResult(InstitutionSnapshot(turn + 1, tuple(active.values())),
                                 funding, tuple(events), tuple(outcomes), tuple(repeal_outcomes), tuple(used))
