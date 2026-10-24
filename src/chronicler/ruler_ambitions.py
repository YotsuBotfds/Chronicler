"""Standalone M66b kernel; no simulation, shared-model, G03, or agent imports.

Evidence: governance roadmap lines 744-851; baseline infrastructure.py emits
``infrastructure_completed``; culture.py emits ``invest_culture``; religion.py
exposes belief distributions and conversion deltas; resources.py exposes routes.

Call ``start_reign`` at accession using a unique reign ID (not ruler name), then
``evaluate_ambitions`` once in late Phase 10 after action resolution. Returned
legitimacy is a clamped preview for this evaluation, effective for governance at
N+1. G03 consumes keyed outcome deltas; it alone allocates capital. Capital is
passed through, never charged by ambitions. Reign-long contribution retention
is an unresolved integration policy: do not use the preview to overwrite G03's
legitimacy computation or count an ambition again as a victory. The caller
owns any succession legitimacy reset before supplying the accession snapshot.

Policy gaps are explicit inputs: military/clergy eligibility, attainable targets,
arts/build capability, religious predicate thresholds, and trait-aligned weights.
No diplomacy predicate exists in the roadmap, so diplomatic triumph is excluded.
Expansion uses the existing ownership surface for a supplied frontier target.
Fewer than two live types yields fewer ambitions, never fabricated objectives.
The caller supplies independent uniform draws in [0, 1); no RNG is consumed here.

Events have caller-assigned monotonically increasing sequence numbers, including
an accession cursor. This distinguishes pre/post-accession events in one turn.
Supply completed build events, not build_started; actor must be the beneficiary
civ (for cultural_work, adapt NamedEvent into EvidenceEvent). Event targets are
optional for untargeted art goals and required for targeted builds. Event-chain
tags persist as a sorted, deduplicated civ-level vocabulary across reigns. The
roadmap gives no recent-window duration; retention/curator policy stays external.
Agent-memory mirroring is optional and is not performed here.

Example (illustrative calibration, not a runtime default)::

    config = AmbitionCalibration(2, 20, 40, .10, .05,
        ((AmbitionType.CONQUER_REGION, 2.), (AmbitionType.PATRON_OF_ARTS, 1.)))
    snapshot = AmbitionSnapshot('Civ', 'reign-1', 7, 10, .5, .2,
        owned_regions=('Home',), conquerable_regions=('Border',),
        military_eligible=True, arts_available=True)
    reign = start_reign(snapshot, config, (SelectionDraw(.2, .5, 0.),) * 2)
    result = evaluate_ambitions(reign, replace(snapshot, turn=8,
        owned_regions=('Home', 'Border')), config)
    assert result.requested_legitimacy_delta == .10

The example needs ``from dataclasses import replace``. Persist ``result.reign``
between calls; outputs are immutable and no caller object is mutated. A skipped
state check cannot reconstruct historical ownership: after a deadline, only
explicit on-time event evidence can complete an ambition, otherwise it fails.

Great-person agendas (``chronicler.gp_agendas``, ``--gp-agendas``) reuse this
kernel with the appended ``GP_AGENDA_TYPES``: one objective per record, keyed
by the person rather than a civ, a 10-40 turn window, and early failure on the
thwarting evidence in ``GP_THWARTING_EVENTS``. Ruler objectives, their pools,
windows and completion rules are unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from fractions import Fraction
import math


class AmbitionType(str, Enum):
    CONQUER_REGION = 'conquer_region'
    BUILD_MONUMENT = 'build_monument'
    ESTABLISH_TRADE = 'establish_trade'
    RELIGIOUS_CONVERSION = 'religious_conversion'
    EXPAND_TERRITORY = 'expand_territory'
    PATRON_OF_ARTS = 'patron_of_arts'
    DIPLOMATIC_TRIUMPH = 'diplomatic_triumph'
    # Great-person agendas (``chronicler.gp_agendas``), appended: declaration
    # order is the canonical sort order. ``generate_ambitions`` never builds a
    # pool for them, so ruler reigns are unchanged; the great-person adapter
    # constructs these objectives itself and resolves them here.
    LEAD_CAMPAIGN = 'lead_campaign'              # take a region (ownership)
    SEIZE_THRONE = 'seize_throne'                # a general's coup (evidence)
    OPEN_TRADE_ROUTE = 'open_trade_route'        # a route with a civ (route surface)
    PROTECT_TRADE_ROUTE = 'protect_trade_route'  # keep a route to the deadline
    FOUND_TRADING_HOUSE = 'found_trading_house'  # evidence
    LEND_TO_CROWN = 'lend_to_crown'              # evidence (finance)
    SPREAD_FAITH = 'spread_faith'                # belief share predicate
    FOUND_SHRINE = 'found_shrine'                # completed temple in a region
    ADVANCE_LEARNING = 'advance_learning'        # the civ's next era (evidence)
    INVENT_TECHNIQUE = 'invent_technique'        # a technique (evidence; techniques)


_AMBITION_INDEX = {kind: index for index, kind in enumerate(AmbitionType)}

#: Great-person agenda kinds. They keep the kernel's evidence, cursor and
#: deadline rules but use a shorter window (great persons live 20-30 turns)
#: and may also end early on thwarting evidence (``GP_THWARTING_EVENTS``).
GP_AGENDA_TYPES = frozenset({
    AmbitionType.LEAD_CAMPAIGN, AmbitionType.SEIZE_THRONE, AmbitionType.OPEN_TRADE_ROUTE,
    AmbitionType.PROTECT_TRADE_ROUTE, AmbitionType.FOUND_TRADING_HOUSE, AmbitionType.LEND_TO_CROWN,
    AmbitionType.SPREAD_FAITH, AmbitionType.FOUND_SHRINE, AmbitionType.ADVANCE_LEARNING,
    AmbitionType.INVENT_TECHNIQUE,
})
GP_AGENDA_MIN_DURATION = 10
GP_AGENDA_MAX_DURATION = 40
_UNTARGETED = frozenset({AmbitionType.PATRON_OF_ARTS, AmbitionType.SEIZE_THRONE,
                         AmbitionType.FOUND_TRADING_HOUSE, AmbitionType.LEND_TO_CROWN})
_RELIGIOUS = frozenset({AmbitionType.RELIGIOUS_CONVERSION, AmbitionType.SPREAD_FAITH})
# Event goals: the evidence types that complete them (targeted goals also
# need the event's target). The two ruler entries are the roadmap's.
_EVENT_GOALS: dict[AmbitionType, tuple[str, ...]] = {
    AmbitionType.BUILD_MONUMENT: ('infrastructure_completed',),
    AmbitionType.PATRON_OF_ARTS: ('cultural_work', 'invest_culture'),
    AmbitionType.SEIZE_THRONE: ('gp_coup',),
    AmbitionType.FOUND_TRADING_HOUSE: ('trading_house_founded',),
    AmbitionType.LEND_TO_CROWN: ('crown_loan',),
    AmbitionType.FOUND_SHRINE: ('infrastructure_completed',),
    AmbitionType.ADVANCE_LEARNING: ('tech_advancement',),
    AmbitionType.INVENT_TECHNIQUE: ('technique_invented',),
}
#: Evidence that ends a great-person agenda in failure before its deadline:
#: the holder's death or retirement for every kind, plus kind-specific
#: setbacks (a crushed coup, a broken route). Ruler ambitions never fail early.
GP_THWARTING_EVENTS: dict[AmbitionType, tuple[str, ...]] = {
    kind: ('holder_gone',) for kind in GP_AGENDA_TYPES
}
GP_THWARTING_EVENTS[AmbitionType.SEIZE_THRONE] = ('holder_gone', 'gp_coup_failed')
GP_THWARTING_EVENTS[AmbitionType.PROTECT_TRADE_ROUTE] = ('holder_gone', 'trade_route_broken')

def _integer(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a nonnegative integer')


def _number(value: float, name: str, *, upper: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a finite number')
    if not math.isfinite(value) or value < 0 or (upper is not None and value > upper):
        raise ValueError(f'{name} is outside its finite nonnegative range')


def _name(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty string')


def _names(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    for value in values:
        _name(value, label)
    return tuple(sorted(set(values)))


@dataclass(frozen=True)
class ConversionPredicate:
    """One concrete predicate, supplied for a stable region/civ and faith ID.

    ``minimum_delta`` tests that turn's positive conversion count, not a hidden
    accumulated total. ``minimum_share`` tests the current belief proportion.
    Exactly one must be provided; the roadmap does not calibrate either value.
    """
    target: str
    faith_id: int
    minimum_share: float | None = None
    minimum_delta: int | None = None

    def __post_init__(self) -> None:
        _name(self.target, 'conversion target')
        _integer(self.faith_id, 'faith_id')
        if self.faith_id == 255:
            raise ValueError('faith_id 255 is the unknown-faith sentinel')
        if (self.minimum_share is None) == (self.minimum_delta is None):
            raise ValueError('supply exactly one conversion predicate')
        if self.minimum_share is not None:
            _number(self.minimum_share, 'minimum_share', upper=1.)
            if self.minimum_share == 0:
                raise ValueError('minimum_share must be positive')
        if self.minimum_delta is not None:
            _integer(self.minimum_delta, 'minimum_delta')
            if self.minimum_delta == 0:
                raise ValueError('minimum_delta must be positive')


@dataclass(frozen=True)
class ConversionObservation:
    target: str
    faith_id: int
    belief_share: float | None = None
    conversion_delta: int | None = None

    def __post_init__(self) -> None:
        _name(self.target, 'conversion target')
        _integer(self.faith_id, 'faith_id')
        if self.belief_share is not None:
            _number(self.belief_share, 'belief_share', upper=1.)
        if self.conversion_delta is not None:
            _integer(self.conversion_delta, 'conversion_delta')


def _converted(predicate: ConversionPredicate, observations: tuple[ConversionObservation, ...]) -> bool:
    for observation in observations:
        if (observation.target, observation.faith_id) != (predicate.target, predicate.faith_id):
            continue
        if predicate.minimum_share is not None:
            return observation.belief_share is not None and observation.belief_share >= predicate.minimum_share
        return observation.conversion_delta is not None and observation.conversion_delta >= predicate.minimum_delta
    return False


@dataclass(frozen=True)
class AmbitionSnapshot:
    """Civ-local copied inputs; capability/target sets are caller-attested.

    ``event_cursor`` is the highest event sequence already observed at this
    snapshot. At accession it becomes the exclusion boundary for event goals.
    Potential trade partners are attainable but inactive routes, not merely all
    foreign civs. ``trade_routes_exist`` attests the existing route surface required
    by roadmap line 760; the roadmap does not specify a minimum route count or
    require those existing routes to involve this civ. Conquerable/frontier/build
    regions already obey live sim rules.
    """
    civ_id: str
    ruler_id: str
    turn: int
    event_cursor: int
    legitimacy: float
    political_capital: float
    owned_regions: tuple[str, ...] = ()
    conquerable_regions: tuple[str, ...] = ()
    frontier_regions: tuple[str, ...] = ()
    active_trade_partners: tuple[str, ...] = ()
    attainable_trade_partners: tuple[str, ...] = ()
    buildable_regions: tuple[str, ...] = ()
    military_eligible: bool = False
    clergy_eligible: bool = False
    arts_available: bool = False
    trade_routes_exist: bool = False
    conversion_predicates: tuple[ConversionPredicate, ...] = ()
    conversion_observations: tuple[ConversionObservation, ...] = ()

    def __post_init__(self) -> None:
        _name(self.civ_id, 'civ_id')
        _name(self.ruler_id, 'ruler_id')
        _integer(self.turn, 'turn')
        _integer(self.event_cursor, 'event_cursor')
        _number(self.legitimacy, 'legitimacy', upper=1.)
        _number(self.political_capital, 'political_capital')
        for field in ('owned_regions', 'conquerable_regions', 'frontier_regions',
                      'active_trade_partners', 'attainable_trade_partners', 'buildable_regions'):
            object.__setattr__(self, field, _names(getattr(self, field), field))
        for field in ('military_eligible', 'clergy_eligible', 'arts_available', 'trade_routes_exist'):
            if type(getattr(self, field)) is not bool:
                raise ValueError(f'{field} must be boolean')
        for field in ('conversion_predicates', 'conversion_observations'):
            values = tuple(sorted(getattr(self, field), key=lambda item: (item.target, item.faith_id)))
            keys = [(item.target, item.faith_id) for item in values]
            if len(set(keys)) != len(keys):
                raise ValueError(f'duplicate {field} target/faith')
            object.__setattr__(self, field, values)


@dataclass(frozen=True)
class AmbitionCalibration:
    """Required roadmap constants plus caller-calibrated trait-aligned weights.

    Omitted/zero-weight types are disabled. Supply final weights for this ruler;
    the kernel does not invent a trait mapping or military/clergy threshold.
    """
    ambitions_per_ruler: int
    minimum_duration: int
    maximum_duration: int
    completion_legitimacy: float
    failure_legitimacy: float
    weights: tuple[tuple[AmbitionType, float], ...]

    def __post_init__(self) -> None:
        if type(self.ambitions_per_ruler) is not int or self.ambitions_per_ruler not in (2, 3):
            raise ValueError('ambitions_per_ruler must be 2 or 3')
        _integer(self.minimum_duration, 'minimum_duration')
        _integer(self.maximum_duration, 'maximum_duration')
        if not 20 <= self.minimum_duration <= self.maximum_duration <= 40:
            raise ValueError('durations must stay in the roadmap 20-40 turn range')
        _number(self.completion_legitimacy, 'completion_legitimacy', upper=1.)
        _number(self.failure_legitimacy, 'failure_legitimacy', upper=1.)
        weights = tuple((kind, weight) for kind, weight in self.weights)
        if any(not isinstance(kind, AmbitionType) for kind, _ in weights):
            raise ValueError('weights require AmbitionType keys')
        if len({kind for kind, _ in weights}) != len(weights):
            raise ValueError('duplicate ambition weight')
        for _, weight in weights:
            _number(weight, 'weight')
        object.__setattr__(self, 'weights', tuple(sorted(weights, key=lambda item: _AMBITION_INDEX[item[0]])))


@dataclass(frozen=True)
class SelectionDraw:
    ambition: float
    target: float
    duration: float

    def __post_init__(self) -> None:
        for field in ('ambition', 'target', 'duration'):
            value = getattr(self, field)
            _number(value, field, upper=1.)
            if value == 1:
                raise ValueError('selection draws must be in [0, 1)')


@dataclass(frozen=True)
class Ambition:
    ambition_type: AmbitionType
    target: str | None
    generated_turn: int
    deadline_turn: int
    generated_event_cursor: int
    conversion_predicate: ConversionPredicate | None = None
    completed: bool = False
    failed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.ambition_type, AmbitionType):
            raise ValueError('ambition_type must be AmbitionType')
        _integer(self.generated_turn, 'generated_turn')
        _integer(self.deadline_turn, 'deadline_turn')
        _integer(self.generated_event_cursor, 'generated_event_cursor')
        if self.ambition_type in GP_AGENDA_TYPES:
            if not GP_AGENDA_MIN_DURATION <= self.deadline_turn - self.generated_turn <= GP_AGENDA_MAX_DURATION:
                raise ValueError('agenda deadline must be 10-40 turns after generation')
        elif not 20 <= self.deadline_turn - self.generated_turn <= 40:
            raise ValueError('deadline must be 20-40 turns after generation')
        if type(self.completed) is not bool or type(self.failed) is not bool or (self.completed and self.failed):
            raise ValueError('ambition must have at most one terminal flag')
        if self.ambition_type in _UNTARGETED:
            if self.target is not None:
                raise ValueError(f'{self.ambition_type.value} is untargeted')
        else:
            _name(self.target, 'ambition target')
        if self.ambition_type == AmbitionType.DIPLOMATIC_TRIUMPH:
            raise ValueError('diplomatic_triumph has no live predicate')
        if self.ambition_type in _RELIGIOUS:
            if self.conversion_predicate is None or self.conversion_predicate.target != self.target:
                raise ValueError('religious ambition requires matching concrete predicate')
        elif self.conversion_predicate is not None:
            raise ValueError('conversion predicate requires religious ambition')


@dataclass(frozen=True)
class RulerAmbitions:
    civ_id: str
    ruler_id: str
    accession_turn: int
    accession_event_cursor: int
    ambitions: tuple[Ambition, ...]
    ruler_event_tags: tuple[str, ...] = ()
    last_evaluated_turn: int | None = None
    last_event_cursor: int | None = None

    def __post_init__(self) -> None:
        _name(self.civ_id, 'civ_id')
        _name(self.ruler_id, 'ruler_id')
        _integer(self.accession_turn, 'accession_turn')
        _integer(self.accession_event_cursor, 'accession_event_cursor')
        ambitions = tuple(sorted(self.ambitions, key=lambda item: _AMBITION_INDEX[item.ambition_type]))
        if len(ambitions) > 3 or len({a.ambition_type for a in ambitions}) != len(ambitions):
            raise ValueError('reign requires at most three distinct ambition types')
        if any((a.generated_turn, a.generated_event_cursor) != (self.accession_turn, self.accession_event_cursor) for a in ambitions):
            raise ValueError('all ambitions must belong to this accession')
        for value, floor, label in ((self.last_evaluated_turn, self.accession_turn, 'last_evaluated_turn'),
                                    (self.last_event_cursor, self.accession_event_cursor, 'last_event_cursor')):
            if value is not None:
                _integer(value, label)
                if value < floor:
                    raise ValueError(f'{label} precedes accession')
        object.__setattr__(self, 'ambitions', ambitions)
        object.__setattr__(self, 'ruler_event_tags', _names(self.ruler_event_tags, 'tag'))


@dataclass(frozen=True)
class EvidenceEvent:
    turn: int
    sequence: int
    civ_id: str
    event_type: str
    target: str | None = None

    def __post_init__(self) -> None:
        _integer(self.turn, 'event turn')
        _integer(self.sequence, 'event sequence')
        _name(self.civ_id, 'event civ_id')
        _name(self.event_type, 'event_type')
        if self.target is not None:
            _name(self.target, 'event target')


@dataclass(frozen=True)
class AmbitionContributionKey:
    """Stable identity for one objective's terminal contribution to G03.

    Integration can deduplicate by this key across retries and serialization.
    A globally unique caller reign ID distinguishes even same-turn accessions.
    Terminal success/failure shares one key because an objective settles once.
    """
    civ_id: str
    ruler_id: str
    accession_turn: int
    accession_event_cursor: int
    ambition_type: AmbitionType


@dataclass(frozen=True)
class AmbitionOutcome:
    """Adapter-ready named event and prerequisite tag; no shared Event writes."""
    contribution_key: AmbitionContributionKey
    turn: int
    civ_id: str
    ruler_id: str
    ambition_type: AmbitionType
    target: str | None
    event_type: str
    tag: str
    legitimacy_delta: float


@dataclass(frozen=True)
class AmbitionEvaluation:
    reign: RulerAmbitions
    outcomes: tuple[AmbitionOutcome, ...]
    requested_legitimacy_delta: float
    applied_legitimacy_delta: float
    legitimacy: float
    political_capital: float
    governance_effective_turn: int


def generate_ambitions(snapshot: AmbitionSnapshot, calibration: AmbitionCalibration,
                       draws: tuple[SelectionDraw, ...]) -> tuple[Ambition, ...]:
    """Weighted types without replacement; canonical targets and inclusive durations.

    Provide exactly ambitions_per_ruler draws, even when eligible pool is small.
    Inputs attest live attainability; ownership/routes/fulfilled religious
    predicates are independently excluded here. Build/art are future event goals.
    """
    if len(draws) != calibration.ambitions_per_ruler:
        raise ValueError('one selection draw required per requested ambition')
    owned = set(snapshot.owned_regions)
    pool: dict[AmbitionType, tuple[tuple[str | None, ConversionPredicate | None], ...]] = {}
    if snapshot.military_eligible:
        pool[AmbitionType.CONQUER_REGION] = tuple((name, None) for name in snapshot.conquerable_regions if name not in owned)
    pool[AmbitionType.EXPAND_TERRITORY] = tuple((name, None) for name in snapshot.frontier_regions if name not in owned)
    pool[AmbitionType.BUILD_MONUMENT] = tuple((name, None) for name in snapshot.buildable_regions if name in owned)
    if snapshot.trade_routes_exist:
        pool[AmbitionType.ESTABLISH_TRADE] = tuple((name, None) for name in snapshot.attainable_trade_partners
            if name != snapshot.civ_id and name not in snapshot.active_trade_partners)
    if snapshot.clergy_eligible:
        pool[AmbitionType.RELIGIOUS_CONVERSION] = tuple((p.target, p) for p in snapshot.conversion_predicates
            if not _converted(p, snapshot.conversion_observations))
    if snapshot.arts_available:
        pool[AmbitionType.PATRON_OF_ARTS] = ((None, None),)
    eligible = [(kind, weight) for kind, weight in calibration.weights if weight > 0 and pool.get(kind)]
    result = []
    for draw in draws:
        if not eligible:
            break
        # Exact ratios preserve even subnormal positive support without overflow.
        weights = [Fraction(weight) for _, weight in eligible]
        point = Fraction(draw.ambition) * sum(weights)
        index = len(eligible) - 1
        cumulative = Fraction(0)
        for i, weight in enumerate(weights):
            cumulative += weight
            if point < cumulative:
                index = i
                break
        kind, _ = eligible.pop(index)
        targets = pool[kind]
        target, predicate = targets[min(int(draw.target * len(targets)), len(targets) - 1)]
        span = calibration.maximum_duration - calibration.minimum_duration + 1
        duration = calibration.minimum_duration + min(int(draw.duration * span), span - 1)
        result.append(Ambition(kind, target, snapshot.turn, snapshot.turn + duration,
                               snapshot.event_cursor, predicate))
    return tuple(sorted(result, key=lambda item: _AMBITION_INDEX[item.ambition_type]))


def start_reign(snapshot: AmbitionSnapshot, calibration: AmbitionCalibration,
                draws: tuple[SelectionDraw, ...], previous: RulerAmbitions | None = None,
                *, event_tags: tuple[str, ...] = ()) -> RulerAmbitions:
    """Reset objectives on ruler-ID change; preserve civ tags and append new_ruler.

    Repeated calls for the same reign return its existing objectives. Callers
    must not reuse a historical ruler ID for a later accession or another civ.
    """
    if previous is not None:
        _check_snapshot(previous, snapshot, require_ruler=False)
        tags = previous.ruler_event_tags + event_tags
        if previous.ruler_id == snapshot.ruler_id:
            return replace(previous, ruler_event_tags=_names(tags, 'tag'))
    else:
        tags = event_tags
    return RulerAmbitions(snapshot.civ_id, snapshot.ruler_id, snapshot.turn, snapshot.event_cursor,
                          generate_ambitions(snapshot, calibration, draws), tags + ('new_ruler',))


def _check_snapshot(reign: RulerAmbitions, snapshot: AmbitionSnapshot, *, require_ruler: bool = True) -> None:
    if reign.civ_id != snapshot.civ_id:
        raise ValueError('snapshot belongs to another civilization')
    if require_ruler and reign.ruler_id != snapshot.ruler_id:
        raise ValueError('ruler changed; call start_reign before evaluation')
    if snapshot.turn < (reign.last_evaluated_turn if reign.last_evaluated_turn is not None else reign.accession_turn):
        raise ValueError('snapshot turn moved backwards')
    if snapshot.event_cursor < (reign.last_event_cursor if reign.last_event_cursor is not None else reign.accession_event_cursor):
        raise ValueError('event cursor moved backwards')


def _evidence(ambition: Ambition, snapshot: AmbitionSnapshot, events: tuple[EvidenceEvent, ...],
              wanted: tuple[str, ...]) -> bool:
    """On-time evidence of one of ``wanted`` after the generation cursor."""
    return any(event.civ_id == snapshot.civ_id and event.event_type in wanted
               and ambition.generated_turn <= event.turn <= min(snapshot.turn, ambition.deadline_turn)
               and ambition.generated_event_cursor < event.sequence <= snapshot.event_cursor
               and (ambition.target is None or event.target == ambition.target) for event in events)


def _complete(ambition: Ambition, snapshot: AmbitionSnapshot, events: tuple[EvidenceEvent, ...]) -> bool:
    kind = ambition.ambition_type
    wanted = _EVENT_GOALS.get(kind)
    if wanted is not None:
        return _evidence(ambition, snapshot, events, wanted)
    # A late snapshot does not prove that a state predicate was true by deadline.
    if snapshot.turn > ambition.deadline_turn:
        return False
    if kind in (AmbitionType.CONQUER_REGION, AmbitionType.EXPAND_TERRITORY, AmbitionType.LEAD_CAMPAIGN):
        return ambition.target in snapshot.owned_regions
    if kind in (AmbitionType.ESTABLISH_TRADE, AmbitionType.OPEN_TRADE_ROUTE):
        return ambition.target in snapshot.active_trade_partners
    if kind == AmbitionType.PROTECT_TRADE_ROUTE:
        # Sustained goal: the route must still stand on the deadline itself.
        return snapshot.turn == ambition.deadline_turn and ambition.target in snapshot.active_trade_partners
    if kind in _RELIGIOUS:
        return _converted(ambition.conversion_predicate, snapshot.conversion_observations)
    return False


def _thwarted(ambition: Ambition, snapshot: AmbitionSnapshot, events: tuple[EvidenceEvent, ...]) -> bool:
    """Great-person agendas only: on-time thwarting evidence ends them early.

    Thwarting evidence for a targeted agenda must carry its target, except
    ``holder_gone`` (the holder's death or retirement), which is untargeted.
    """
    wanted = GP_THWARTING_EVENTS.get(ambition.ambition_type)
    if not wanted:
        return False
    return any(event.civ_id == snapshot.civ_id and event.event_type in wanted
               and ambition.generated_turn <= event.turn <= min(snapshot.turn, ambition.deadline_turn)
               and ambition.generated_event_cursor < event.sequence <= snapshot.event_cursor
               and (event.event_type == 'holder_gone' or ambition.target is None
                    or event.target == ambition.target) for event in events)


def evaluate_ambitions(reign: RulerAmbitions, snapshot: AmbitionSnapshot,
                       calibration: AmbitionCalibration, events: tuple[EvidenceEvent, ...] = (),
                       *, event_tags: tuple[str, ...] = ()) -> AmbitionEvaluation:
    """Resolve each active goal once; completion wins on the inclusive deadline.

    Clamp the combined normalized delta once, rather than ordering completions
    and failures around the bounds. Persist the returned reign and send keyed
    outcome deltas to G03; legitimacy is only the clamped preview for this call.
    Outcomes use the evaluation turn; historical evidence retains its own turn.
    """
    _check_snapshot(reign, snapshot)
    events = tuple(sorted(events, key=lambda event: event.sequence))
    if len({event.sequence for event in events}) != len(events):
        raise ValueError('event sequences must be unique')
    if any(event.turn > snapshot.turn or event.sequence > snapshot.event_cursor for event in events):
        raise ValueError('event evidence is newer than the snapshot')
    ambitions, outcomes = [], []
    tags = reign.ruler_event_tags + event_tags
    for ambition in reign.ambitions:
        if ambition.completed or ambition.failed:
            ambitions.append(ambition)
            continue
        completed = _complete(ambition, snapshot, events)
        failed = not completed and (snapshot.turn >= ambition.deadline_turn
                                    or _thwarted(ambition, snapshot, events))
        ambitions.append(replace(ambition, completed=completed, failed=failed))
        if completed or failed:
            event_type = 'ambition_fulfilled' if completed else 'ambition_failed'
            tag = f'ambition_{"completed" if completed else "failed"}_{ambition.ambition_type.value}'
            delta = calibration.completion_legitimacy if completed else -calibration.failure_legitimacy
            key = AmbitionContributionKey(reign.civ_id, reign.ruler_id, reign.accession_turn,
                                          reign.accession_event_cursor, ambition.ambition_type)
            outcomes.append(AmbitionOutcome(key, snapshot.turn, snapshot.civ_id, snapshot.ruler_id,
                                            ambition.ambition_type, ambition.target, event_type, tag, delta))
            tags += (tag,)
    delta = math.fsum(outcome.legitimacy_delta for outcome in outcomes)
    legitimacy = min(1., max(0., snapshot.legitimacy + delta))
    updated = replace(reign, ambitions=tuple(ambitions), ruler_event_tags=tags,
                      last_evaluated_turn=snapshot.turn, last_event_cursor=snapshot.event_cursor)
    return AmbitionEvaluation(updated, tuple(outcomes), delta, legitimacy - snapshot.legitimacy,
                              legitimacy, snapshot.political_capital, snapshot.turn + 1)
