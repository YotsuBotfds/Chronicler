"""Standalone M65a kernel (governance roadmap, lines 413–486).

Call in late Phase 10 with post-tick rows and the *active* GreatPerson roster.
Rows must already have resolved polity civ IDs and current-occupation skill;
this module neither extracts wealth (agent_bridge.py owns that) nor touches
WorldState, Rust, analytics, or persistence. Turn N outputs are marked usable
at N+1, never by the already-completed turn N politics pass.

Spec gaps are explicit: the draft does not lock wealth percentile tie semantics,
rounding population/100 into offices, or agent-vs-synthetic equal-wealth ties.
EliteConventions therefore has no defaults. The provided lower/upper empirical
CDF conventions keep equal wealth at equal percentiles; agent ID only breaks
*office ranking* ties. The draft also supplies no wealth/satisfaction fallback
for absent-backed GPs: callers must provide both, or classification fails.
These are adapter choices to review before integration, not promoted policy.

Calibration rates/cap are mandatory. The other calibration defaults are the
roadmap's specified constants. Civ population is explicitly supplied, not
inferred from snapshot row counts or inflated by synthetic GPs. GP stable keys
are caller-owned identities, not roster positions or generated hashes.

Runnable example (illustrative calibration, not a recommended runtime preset):

>>> conventions = EliteConventions(
...     WealthPercentileConvention.LOWER, PositionRounding.FLOOR,
...     EqualWealthOrder.AGENTS_FIRST)
>>> calibration = EliteCalibration(ratchet_up_rate=0.4,
...                                ratchet_down_rate=0.1, ratchet_cap=3.0)
>>> civ = CivEliteInput(0, 200, EliteRatchetState(6, 1.0))
>>> rows = tuple(AgentEliteInput(i, 0, float(i), Occupation.MERCHANT,
...                             0.8, 0.2) for i in range(3))
>>> batch = compute_elite_metrics(turn=7, civilizations=(civ,), agents=rows,
...     great_persons=(), calibration=calibration, conventions=conventions)
>>> result = batch.civilizations[0]
>>> (batch.snapshot_turn, batch.effective_turn, result.elite_positions)
(7, 8, 2)
>>> (result.elite_qualifier_count, result.elite_office_holder_count,
...  result.frustrated_aspirant_count)
(3, 2, 1)
>>> round(result.emp, 6)
0.55
>>> result.next_ratchet_state.snapshot_turn
7
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from math import isfinite


class Occupation(str, Enum):
    """Names corresponding to snapshot occupation codes 0 through 4."""

    FARMER = "farmer"
    SOLDIER = "soldier"
    MERCHANT = "merchant"
    SCHOLAR = "scholar"
    PRIEST = "priest"


class WealthPercentileConvention(str, Enum):
    LOWER = "lower"  # count(wealth < this wealth) / snapshot civ row count
    UPPER = "upper"  # count(wealth <= this wealth) / snapshot civ row count


class PositionRounding(str, Enum):
    FLOOR = "floor"
    CEIL = "ceil"


class EqualWealthOrder(str, Enum):
    AGENTS_FIRST = "agents_first"
    GREAT_PERSONS_FIRST = "great_persons_first"


@dataclass(frozen=True)
class EliteConventions:
    wealth_percentile: WealthPercentileConvention
    position_rounding: PositionRounding
    equal_wealth_order: EqualWealthOrder


@dataclass(frozen=True)
class EliteCalibration:
    ratchet_up_rate: float
    ratchet_down_rate: float
    ratchet_cap: float
    elite_wealth_percentile: float = 0.90
    elite_skill_threshold: float = 0.8
    elite_positions_divisor: int = 100
    elite_positions_min: int = 2
    frustrated_aspirant_satisfaction_threshold: float = 0.3


@dataclass(frozen=True)
class EliteRatchetState:
    """Explicit prior-turn state; use snapshot_turn=-1 to initialize turn 0."""

    snapshot_turn: int
    conspicuous_consumption_index: float


@dataclass(frozen=True)
class CivEliteInput:
    civ_id: int
    population: int
    previous_ratchet: EliteRatchetState


@dataclass(frozen=True)
class AgentEliteInput:
    agent_id: int
    civ_id: int
    wealth: float
    occupation: Occupation
    skill: float
    satisfaction: float


@dataclass(frozen=True)
class GreatPersonEliteInput:
    """One active GP, with a stable unique key and optional backing agent.

    For present backing agents, snapshot wealth/satisfaction are authoritative
    and overlay values are ignored. For missing or aggregate backing agents,
    wealth and satisfaction must be explicit finite values. Repeated GP keys
    and repeated backing IDs are deduplicated; inconsistent effective records
    are rejected. Cross-civ backing mismatches are errors for the adapter to
    resolve, rather than guessed transfers. Caller filters alive/active status.
    """

    great_person_key: str
    civ_id: int
    agent_id: int | None
    wealth: float | None
    satisfaction: float | None


@dataclass(frozen=True)
class EliteIdentity:
    """Exactly one field is populated: real agent or synthetic GP key."""

    agent_id: int | None
    great_person_key: str | None


@dataclass(frozen=True)
class CivEliteMetrics:
    civ_id: int
    elite_positions: int
    qualifiers: tuple[EliteIdentity, ...]
    office_holders: tuple[EliteIdentity, ...]
    frustrated_aspirants: tuple[EliteIdentity, ...]
    conspicuous_consumption_index: float
    emp: float
    next_ratchet_state: EliteRatchetState

    @property
    def elite_qualifier_count(self) -> int:
        return len(self.qualifiers)

    @property
    def elite_office_holder_count(self) -> int:
        return len(self.office_holders)

    @property
    def frustrated_aspirant_count(self) -> int:
        return len(self.frustrated_aspirants)


@dataclass(frozen=True)
class EliteMetricsOutput:
    snapshot_turn: int
    effective_turn: int
    civilizations: tuple[CivEliteMetrics, ...]


@dataclass(frozen=True)
class _Candidate:
    identity: EliteIdentity
    civ_id: int
    wealth: float
    satisfaction: float


def _integer(name: str, value: int, *, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _number(name: str, value: object, *, unit: bool = False,
            nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    if unit and not 0 <= numeric <= 1:
        raise ValueError(f"{name} must be in [0, 1]")
    if nonnegative and numeric < 0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _validate_configuration(calibration: EliteCalibration,
                            conventions: EliteConventions) -> None:
    for name in ("ratchet_up_rate", "ratchet_down_rate", "ratchet_cap"):
        _number(name, getattr(calibration, name), nonnegative=True)
    for name in ("elite_wealth_percentile", "elite_skill_threshold",
                 "frustrated_aspirant_satisfaction_threshold"):
        _number(name, getattr(calibration, name), unit=True)
    _integer("elite_positions_divisor", calibration.elite_positions_divisor,
             minimum=1)
    _integer("elite_positions_min", calibration.elite_positions_min, minimum=1)
    for name, enum in (("wealth_percentile", WealthPercentileConvention),
                       ("position_rounding", PositionRounding),
                       ("equal_wealth_order", EqualWealthOrder)):
        if not isinstance(getattr(conventions, name), enum):
            raise ValueError(f"{name} must be an explicit {enum.__name__}")


def _wealth_qualifiers(rows: Sequence[AgentEliteInput],
                       threshold: float,
                       convention: WealthPercentileConvention) -> set[int]:
    """Sort each civ once; equal wealth gets equal empirical percentiles."""
    ordered = sorted(rows, key=lambda row: (row.wealth, row.agent_id))
    result: set[int] = set()
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end].wealth == ordered[start].wealth:
            end += 1
        rank = start if convention is WealthPercentileConvention.LOWER else end
        if rank / len(ordered) > threshold:
            result.update(row.agent_id for row in ordered[start:end])
        start = end
    return result


def compute_elite_metrics(
    *, turn: int, civilizations: Sequence[CivEliteInput],
    agents: Sequence[AgentEliteInput],
    great_persons: Sequence[GreatPersonEliteInput],
    calibration: EliteCalibration, conventions: EliteConventions,
) -> EliteMetricsOutput:
    """Classify, rank, advance the ratchet once, and return N+1 EMP signals.

    All explicit civs, including empty ones, appear sorted by civ_id. Within a
    civ, lists are ordered by descending wealth, numeric agent ID or lexical
    synthetic GP key, and the explicit cross-kind tie convention. Qualifiers
    include holders and surplus; only dissatisfied surplus counts as aspirants.
    No inputs, RNG, global configuration, or shared models are mutated.

    Reject duplicate snapshot/civ IDs, unknown civs, nonfinite inputs, invalid
    normalized skill/satisfaction, ambiguous GP records, and prior states not
    from N-1. No snapshot-count/population equality is required. GP overlays
    never enter the snapshot wealth-percentile denominator. Numeric overflow
    fails explicitly rather than publishing a nonfinite signal.
    """
    _integer("turn", turn)
    _validate_configuration(calibration, conventions)
    civs: dict[int, CivEliteInput] = {}
    rows_by_civ: dict[int, list[AgentEliteInput]] = {}
    for civ in civilizations:
        _integer("civ_id", civ.civ_id)
        _integer("population", civ.population)
        _integer("previous snapshot_turn", civ.previous_ratchet.snapshot_turn,
                 minimum=-1)
        if civ.previous_ratchet.snapshot_turn != turn - 1:
            raise ValueError("previous ratchet must come from turn N-1")
        _number("previous consumption index",
                civ.previous_ratchet.conspicuous_consumption_index,
                nonnegative=True)
        if civ.civ_id in civs:
            raise ValueError(f"duplicate civ_id {civ.civ_id}")
        civs[civ.civ_id] = civ
        rows_by_civ[civ.civ_id] = []

    agents_by_id: dict[int, AgentEliteInput] = {}
    for row in agents:
        _integer("agent_id", row.agent_id)
        _integer("civ_id", row.civ_id)
        if row.civ_id not in civs:
            raise ValueError(f"unknown civ_id {row.civ_id}")
        if row.agent_id in agents_by_id:
            raise ValueError(f"duplicate agent_id {row.agent_id}")
        if not isinstance(row.occupation, Occupation):
            raise ValueError("occupation must be an Occupation")
        _number("wealth", row.wealth)
        _number("skill", row.skill, unit=True)
        _number("satisfaction", row.satisfaction, unit=True)
        agents_by_id[row.agent_id] = row
        rows_by_civ[row.civ_id].append(row)

    # Present-backed GPs add status, never a second person. Absent-backed GPs
    # collapse by backing ID (or GP key for aggregate GPs); lexical minimum
    # key represents aliases, independent of roster traversal order.
    gp_keys: dict[str, tuple[object, ...]] = {}
    gp_candidates: dict[tuple[str, int | str], _Candidate] = {}
    gp_agent_ids: set[int] = set()
    for gp in great_persons:
        if not isinstance(gp.great_person_key, str) or not gp.great_person_key:
            raise ValueError("great_person_key must be a nonempty stable string")
        _integer("civ_id", gp.civ_id)
        if gp.civ_id not in civs:
            raise ValueError(f"unknown civ_id {gp.civ_id}")
        if gp.agent_id is not None:
            _integer("GP agent_id", gp.agent_id)
        backing = agents_by_id.get(gp.agent_id) if gp.agent_id is not None else None
        if backing is not None:
            if backing.civ_id != gp.civ_id:
                raise ValueError("GP backing agent civ mismatch")
            wealth, satisfaction = backing.wealth, backing.satisfaction
            gp_agent_ids.add(backing.agent_id)
        else:
            wealth = _number("absent GP wealth", gp.wealth)
            satisfaction = _number("absent GP satisfaction", gp.satisfaction, unit=True)
        signature = (gp.civ_id, gp.agent_id, wealth, satisfaction)
        if gp.great_person_key in gp_keys and gp_keys[gp.great_person_key] != signature:
            raise ValueError("conflicting duplicate GreatPerson key")
        gp_keys[gp.great_person_key] = signature
        if backing is not None:
            continue
        key = ("agent", gp.agent_id) if gp.agent_id is not None else (
            "gp", gp.great_person_key)
        candidate = _Candidate(EliteIdentity(None, gp.great_person_key),
                               gp.civ_id, wealth, satisfaction)
        previous = gp_candidates.get(key)
        if previous is not None:
            if (previous.civ_id, previous.wealth, previous.satisfaction) != (
                    candidate.civ_id, candidate.wealth, candidate.satisfaction):
                raise ValueError("conflicting duplicate GreatPerson backing ID")
            if (previous.identity.great_person_key or "") < gp.great_person_key:
                continue
        gp_candidates[key] = candidate

    candidates_by_civ: dict[int, list[_Candidate]] = {
        civ_id: [] for civ_id in civs}
    for candidate in gp_candidates.values():
        candidates_by_civ[candidate.civ_id].append(candidate)

    def rank(candidate: _Candidate) -> tuple[float, int, int, str]:
        identity = candidate.identity
        synthetic = identity.agent_id is None
        kind = int(synthetic)
        if conventions.equal_wealth_order is EqualWealthOrder.GREAT_PERSONS_FIRST:
            kind = 1 - kind
        return (-candidate.wealth, kind,
                identity.agent_id if identity.agent_id is not None else 0,
                identity.great_person_key or "")

    outputs: list[CivEliteMetrics] = []
    skilled_occupations = (Occupation.MERCHANT, Occupation.SCHOLAR, Occupation.PRIEST)
    for civ_id in sorted(civs):
        civ = civs[civ_id]
        rows = rows_by_civ[civ_id]
        wealthy = _wealth_qualifiers(rows, calibration.elite_wealth_percentile,
                                     conventions.wealth_percentile)
        candidates = candidates_by_civ[civ_id]
        for row in rows:
            if (row.agent_id in wealthy or row.agent_id in gp_agent_ids
                    or (row.occupation in skilled_occupations
                        and row.skill >= calibration.elite_skill_threshold)):
                candidates.append(_Candidate(EliteIdentity(row.agent_id, None),
                                             civ_id, row.wealth, row.satisfaction))
        candidates.sort(key=rank)
        quotient, remainder = divmod(civ.population, calibration.elite_positions_divisor)
        if conventions.position_rounding is PositionRounding.CEIL and remainder:
            quotient += 1
        positions = max(calibration.elite_positions_min, quotient)
        qualifiers = tuple(candidate.identity for candidate in candidates)
        holders = qualifiers[:positions]
        frustrated = tuple(candidate.identity for candidate in candidates[positions:]
                           if candidate.satisfaction
                           < calibration.frustrated_aspirant_satisfaction_threshold)
        pressure = len(qualifiers) / max(positions, 1)
        index = (civ.previous_ratchet.conspicuous_consumption_index
                 + calibration.ratchet_up_rate * max(0.0, pressure - 1.0)
                 - calibration.ratchet_down_rate)
        if not isfinite(index):
            raise ValueError("ratchet arithmetic overflow")
        index = min(calibration.ratchet_cap, max(0.0, index))
        emp = (len(frustrated) / max(positions, 1)) * index
        if not isfinite(emp):
            raise ValueError("EMP arithmetic overflow")
        outputs.append(CivEliteMetrics(
            civ_id, positions, qualifiers, holders, frustrated, index, emp,
            EliteRatchetState(turn, index)))
    return EliteMetricsOutput(turn, turn + 1, tuple(outputs))
