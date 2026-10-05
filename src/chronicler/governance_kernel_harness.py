"""Opt-in four-kernel experiment using explicit synthetic fixtures only.

No runtime/snapshot extraction, PSI, G05, models, bridge, or simulation imports.
The policy choices below are experimental contracts, never production defaults.
Pure immutable transactions provide rollback by publishing only a complete result.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction
import json
import math
import types
from typing import get_args, get_origin, get_type_hints

from . import institutions as g01
from . import elite_metrics as g02
from . import governance_capital as g03
from . import ruler_ambitions as g04

POLICY_ID = "synthetic-enact-repeal-mock-suppress-v1"


def _matches_type(value, annotation) -> bool:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is types.UnionType:
        return any(_matches_type(value, item) for item in args)
    if origin is tuple:
        return isinstance(value, tuple) and (all(_matches_type(v, args[0]) for v in value)
            if len(args) == 2 and args[1] is Ellipsis else
            len(value) == len(args) and all(_matches_type(v, t) for v, t in zip(value, args)))
    if annotation is float:
        return type(value) in (int, float) and math.isfinite(value)
    if annotation in (int, bool, str):
        return type(value) is annotation
    return isinstance(value, annotation)


def _validate_fields(cls, values) -> None:
    annotations = get_type_hints(cls)
    for name, value in values.items():
        if not _matches_type(value, annotations[name]):
            raise ValueError(f"{cls.__name__}.{name} has invalid type or nonfinite value")


def _validate_record(value) -> None:
    _validate_fields(type(value), {f.name: getattr(value, f.name) for f in fields(value)})


def _int(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _unique(values: tuple, name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {name}")


def contribution_id(key: g04.AmbitionContributionKey) -> str:
    """Collision-free, versioned identity; display names never stand in for IDs."""
    return json.dumps([1, key.civ_id, key.ruler_id, key.accession_turn,
                       key.accession_event_cursor, key.ambition_type.value],
                      separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class Contribution:
    key: g04.AmbitionContributionKey
    delta: float

    def __post_init__(self) -> None:
        _validate_record(self)
        k = self.key
        _validate_record(k)
        if not isinstance(k, g04.AmbitionContributionKey) or not isinstance(k.ambition_type, g04.AmbitionType):
            raise ValueError("invalid contribution key")
        _int(k.accession_turn, "accession turn")
        _int(k.accession_event_cursor, "accession cursor")
        if not k.civ_id or not k.ruler_id or type(self.delta) not in (int, float) or not math.isfinite(self.delta) or abs(self.delta) > 1:
            raise ValueError("invalid contribution identity/delta")


def merge_contributions(prior: tuple[Contribution, ...], incoming: tuple[Contribution, ...]
                        ) -> tuple[Contribution, ...]:
    """Same key/value is idempotent; contradictory terminal evidence aborts."""
    merged: dict[str, Contribution] = {}
    for item in prior + incoming:
        key = contribution_id(item.key)
        if key in merged and merged[key].delta != item.delta:
            raise ValueError("conflicting replayed ambition contribution")
        merged[key] = item
    return tuple(merged[key] for key in sorted(merged))


@dataclass(frozen=True)
class ReignArchive:
    reign: g04.RulerAmbitions
    contributions: tuple[Contribution, ...]

    def __post_init__(self) -> None:
        _validate_record(self)
        object.__setattr__(self, "contributions", tuple(sorted(self.contributions, key=lambda c: contribution_id(c.key))))


@dataclass(frozen=True)
class CivCarry:
    civ_id: int
    institutions: g01.InstitutionSnapshot
    ratchet: g02.EliteRatchetState
    governance: g03.GovernanceState
    reign: g04.RulerAmbitions | None
    contributions: tuple[Contribution, ...] = ()
    archives: tuple[ReignArchive, ...] = ()
    pending_events: tuple[g04.EvidenceEvent, ...] = ()
    evidence_cursor: int = 0
    evidence_log: tuple[g04.EvidenceEvent, ...] = ()

    def __post_init__(self) -> None:
        _validate_record(self)
        _int(self.civ_id, "civ_id")
        _int(self.ratchet.snapshot_turn, "ratchet turn", -1)
        if type(self.ratchet.conspicuous_consumption_index) not in (int, float) or not math.isfinite(self.ratchet.conspicuous_consumption_index) or self.ratchet.conspicuous_consumption_index < 0:
            raise ValueError("invalid ratchet")
        if self.institutions.effective_turn != self.governance.effective_turn or self.ratchet.snapshot_turn != self.governance.effective_turn - 1:
            raise ValueError("carry epochs disagree")
        if self.reign is None and (self.contributions or self.archives or self.pending_events):
            raise ValueError("uninitialized reign cannot own history")
        histories = self.archives + ((ReignArchive(self.reign, self.contributions),) if self.reign else ())
        _unique(tuple(a.reign.ruler_id for a in histories), "historical ruler ID")
        for archive in histories:
            r = archive.reign
            if r.civ_id != str(self.civ_id) or r.accession_turn >= self.governance.effective_turn or (r.last_evaluated_turn is not None and r.last_evaluated_turn >= self.governance.effective_turn):
                raise ValueError("reign identity/epoch disagrees with carry")
            _unique(tuple(contribution_id(c.key) for c in archive.contributions), "stored contribution key")
            terminal = {a.ambition_type for a in r.ambitions if a.completed or a.failed}
            if {c.key.ambition_type for c in archive.contributions} != terminal:
                raise ValueError("terminal objective/contribution ledger mismatch")
            for c in archive.contributions:
                if (c.key.civ_id, c.key.ruler_id, c.key.accession_turn, c.key.accession_event_cursor) != (r.civ_id, r.ruler_id, r.accession_turn, r.accession_event_cursor):
                    raise ValueError("contribution belongs to another reign")
                goal = next((a for a in r.ambitions if a.ambition_type == c.key.ambition_type), None)
                if goal is None or not (goal.completed or goal.failed):
                    raise ValueError("contribution lacks terminal objective")
                if (goal.completed and c.delta < 0) or (goal.failed and c.delta > 0):
                    raise ValueError("contribution sign disagrees with terminal objective")
        _int(self.evidence_cursor, "evidence cursor")
        if self.reign:
            cursor = self.reign.last_event_cursor if self.reign.last_event_cursor is not None else self.reign.accession_event_cursor
            if cursor > self.evidence_cursor:
                raise ValueError("carry evidence cursor precedes reign cursor")
        for event in self.pending_events:
            if event.civ_id != str(self.civ_id) or event.turn >= self.governance.effective_turn or event.sequence > self.evidence_cursor:
                raise ValueError("pending event identity/epoch/cursor mismatch")
        _unique(tuple(e.sequence for e in self.pending_events), "pending event sequence")
        _unique(tuple(e.sequence for e in self.evidence_log), "stored evidence sequence")
        for event in self.evidence_log:
            if event.civ_id != str(self.civ_id) or event.turn >= self.governance.effective_turn or event.sequence > self.evidence_cursor:
                raise ValueError("stored event identity/epoch/cursor mismatch")
        boundary = (self.reign.last_event_cursor if self.reign.last_event_cursor is not None
                    else self.reign.accession_event_cursor) if self.reign else self.evidence_cursor
        expected_pending = {e for e in self.evidence_log if e.sequence > boundary}
        if set(self.pending_events) != expected_pending:
            raise ValueError("pending evidence does not match unevaluated durable log")
        object.__setattr__(self, "contributions", tuple(sorted(self.contributions, key=lambda c: contribution_id(c.key))))
        object.__setattr__(self, "pending_events", tuple(sorted(self.pending_events, key=lambda e: e.sequence)))
        object.__setattr__(self, "evidence_log", tuple(sorted(self.evidence_log, key=lambda e: e.sequence)))


@dataclass(frozen=True)
class HarnessCarry:
    effective_turn: int
    last_committed_turn: int
    identity_registry: tuple[int, ...]
    civilizations: tuple[CivCarry, ...]

    def __post_init__(self) -> None:
        _validate_record(self)
        _int(self.effective_turn, "effective_turn")
        if self.last_committed_turn != self.effective_turn - 1:
            raise ValueError("commit watermark must precede effective turn")
        registry = tuple(sorted(self.identity_registry))
        for civ_id in registry:
            _int(civ_id, "registry civ ID")
        _unique(registry, "registry identity")
        civs = tuple(sorted(self.civilizations, key=lambda c: c.civ_id))
        if tuple(c.civ_id for c in civs) != registry:
            raise ValueError("carry does not match persisted identity registry")
        if any(c.governance.effective_turn != self.effective_turn for c in civs):
            raise ValueError("civilization epoch mismatch")
        for civ in civs:
            reigns = tuple(a.reign for a in civ.archives) + ((civ.reign,) if civ.reign else ())
            for reign in reigns:
                for ambition in reign.ambitions:
                    if ambition.ambition_type == g04.AmbitionType.ESTABLISH_TRADE:
                        _check_civ_reference(ambition.target, registry)
        object.__setattr__(self, "identity_registry", registry)
        object.__setattr__(self, "civilizations", civs)


def _check_civ_reference(value: str, registry: tuple[int, ...]) -> None:
    if value not in {str(civ_id) for civ_id in registry}:
        raise ValueError("trade partner must be a canonical registered civ ID")


@dataclass(frozen=True)
class HarnessPolicy:
    """Every choice is required, including unresolved fiscal/rounding/timing locks.

    Accepted strings document the one reviewed experimental algorithm. Unsupported
    choices fail; expanding policies requires a separate transaction review.
    """
    policy_id: str
    institutions: g01.InstitutionCoefficients
    elite_calibration: g02.EliteCalibration
    elite_conventions: g02.EliteConventions
    capital: g03.CapitalCoefficients
    spend_costs: g03.SpendCosts
    ambitions: g04.AmbitionCalibration
    funding: g01.FundingPolicy
    fiscal_rounding: str
    enforcement_pricing: str
    contribution_retention: str
    accession_evaluation: str
    capital_on_accession: str
    population_source: str
    missing_observations: str
    capital_limit: Fraction
    evidence_replay: str

    def __post_init__(self) -> None:
        _validate_record(self)
        required = dict(policy_id=POLICY_ID, fiscal_rounding="fractional_fixture_no_integer_treasury",
                        enforcement_pricing="persisted_enactment_cost", contribution_retention="reign_long_no_decay",
                        accession_evaluation="defer_new_objectives", population_source="synthetic_living_row_count",
                        missing_observations="abort_frame", evidence_replay="monotone_complete_cursor_log")
        for name, value in required.items():
            if getattr(self, name) != value:
                raise ValueError(f"unresolved/unsupported policy {name}; explicitly select {value}")
        if self.capital_on_accession not in ("carry_remaining", "reset_zero"):
            raise ValueError("capital_on_accession must explicitly select carry_remaining/reset_zero")
        if not isinstance(self.funding, g01.FundingPolicy):
            raise ValueError("explicit funding policy required")
        if not isinstance(self.capital_limit, Fraction) or self.capital_limit < 0:
            raise ValueError("explicit nonnegative Fraction capital_limit required")


@dataclass(frozen=True)
class MockSuppression:
    subject_key: str
    eligible: bool

    def __post_init__(self) -> None:
        _validate_record(self)
        if not isinstance(self.subject_key, str) or not self.subject_key or type(self.eligible) is not bool:
            raise ValueError("mock suppression requires stable key and explicit eligibility")


@dataclass(frozen=True)
class CivObservation:
    civ_id: int
    factions: g01.FactionWeights
    treasury: float
    base_governing_cost: float
    region_count: int
    trade_route_count: int
    proposals: tuple[g01.ProposalAttempt, ...]
    mock_suppressions: tuple[MockSuppression, ...]
    ambition_snapshot: g04.AmbitionSnapshot
    legitimacy: g03.LegitimacyInputs
    events: tuple[g04.EvidenceEvent, ...]
    accession: g03.SuccessionKind | None
    ambition_draws: tuple[g04.SelectionDraw, ...]
    accession_event_cursor: int | None
    external_funding: g01.FundingResult | None = None

    def __post_init__(self) -> None:
        _validate_record(self)


@dataclass(frozen=True)
class SyntheticFrame:
    source_turn: int
    ownership_epoch: int
    origin: str
    civilizations: tuple[CivObservation, ...]
    agents: tuple[g02.AgentEliteInput, ...]
    great_persons: tuple[g02.GreatPersonEliteInput, ...]

    def __post_init__(self) -> None:
        _validate_record(self)


@dataclass(frozen=True)
class RequestReceipt:
    request: g03.SpendRequest
    status: str
    approved: bool


@dataclass(frozen=True)
class CivReceipt:
    civ_id: int
    institutions: g01.InstitutionTurnResult
    spending: g03.SpendingResult
    accrual: g03.CapitalAccrual
    requests: tuple[RequestReceipt, ...]
    ambition_outcomes: tuple[g04.AmbitionOutcome, ...]


@dataclass(frozen=True)
class HarnessResult:
    carry: HarnessCarry
    policy_id: str | None
    receipts: tuple[CivReceipt, ...]
    elite_metrics: g02.EliteMetricsOutput | None
    diagnostics: tuple[str, ...]


def _request_id(turn: int, civ: int, action: g03.GovernanceAction, subject: str) -> str:
    return json.dumps([1, turn, civ, action.value, subject], separators=(",", ":"), ensure_ascii=False)


def _institution_transaction(carry: CivCarry, obs: CivObservation, policy: HarnessPolicy
                            ) -> tuple[g01.InstitutionTurnResult, g03.SpendingResult, tuple[RequestReceipt, ...]]:
    turn = carry.governance.effective_turn
    if policy.funding == g01.FundingPolicy.BASE_FIRST_FULL_DEBIT:
        if obs.external_funding is not None:
            raise ValueError("helper funding cannot also receive external payment")
        funding = g01.fund_institutions(turn=turn, snapshot=carry.institutions,
                    treasury=obs.treasury, base_governing_cost=obs.base_governing_cost, policy=policy.funding)
    else:
        funding = obs.external_funding
        if funding is None or funding.policy != policy.funding or funding.treasury_before != obs.treasury or funding.last_base_governing_cost != obs.base_governing_cost:
            raise ValueError("explicit matching external fiscal observation required")
    # G01 internally checks epoch, quoted demand, persisted opposition and draws.
    approvals: tuple[g01.InstitutionSpendDecision, ...] = ()

    def resolve(prefix):
        return g01.resolve_institutions(turn=turn, snapshot=carry.institutions,
            factions=obs.factions, funding=funding, coefficients=policy.institutions,
            region_count=obs.region_count, trade_route_count=obs.trade_route_count,
            proposals=obs.proposals, resolution_order=g01.ResolutionOrder.PROPOSE_THEN_REPEAL,
            spend_decisions=g01.InstitutionSpendDecisions(turn, prefix))

    # Validate frozen inputs even with an empty request roster.
    resolve(())
    types = tuple(g01.InstitutionType)
    roster = [(g01.InstitutionOperation.ENACT, p.institution_type, g03.GovernanceAction.ENACT_INSTITUTION)
              for p in sorted(obs.proposals, key=lambda p: types.index(p.institution_type))]
    roster += [(g01.InstitutionOperation.FORCE_REPEAL, i.institution_type, g03.GovernanceAction.FORCE_REPEAL_INSTITUTION)
               for i in carry.institutions.institutions]
    _unique(tuple((op, t) for op, t, _ in roster), "institution request")
    _unique(tuple(s.subject_key for s in obs.mock_suppressions), "mock suppression key")
    working = carry.governance
    eligible: list[g03.SpendRequest] = []
    decisions: list[g03.SpendDecision] = []
    receipts: list[RequestReceipt] = []
    for op, kind, action in roster:
        request = g03.SpendRequest(_request_id(turn, carry.civ_id, action, kind.value), action)
        approval = g01.InstitutionSpendDecision(op, kind, True)
        # Probe structural eligibility even when unaffordable. Only acknowledged
        # eligible requests, including affordability denials, join the final batch.
        probe = resolve(approvals + (approval,))
        if not set(approvals).issubset(probe.used_spend_decisions):
            raise ValueError("later request displaced an accepted institution prefix")
        if approval not in probe.used_spend_decisions:
            receipts.append(RequestReceipt(request, "structurally_unused", False))
            continue
        tentative = g03.resolve_spending(working, (request,), policy.spend_costs)
        decision = tentative.decisions[0]
        eligible.append(request)
        decisions.append(decision)
        if decision.approved:
            approvals += (approval,)
            working = tentative.state
        receipts.append(RequestReceipt(request, "acknowledged" if decision.approved else "insufficient_capital", decision.approved))
    final = resolve(approvals)
    if set(final.used_spend_decisions) != set(approvals) or len(final.used_spend_decisions) != len(approvals):
        raise ValueError("institution acknowledgements do not match final approvals")
    for mock in sorted(obs.mock_suppressions, key=lambda s: s.subject_key):
        request = g03.SpendRequest(_request_id(turn, carry.civ_id, g03.GovernanceAction.SUPPRESS_SECESSION, mock.subject_key),
                                  g03.GovernanceAction.SUPPRESS_SECESSION)
        if not mock.eligible:
            receipts.append(RequestReceipt(request, "ineligible_mock", False))
            continue
        tentative = g03.resolve_spending(working, (request,), policy.spend_costs)
        decision = tentative.decisions[0]
        eligible.append(request)
        decisions.append(decision)
        working = tentative.state
        receipts.append(RequestReceipt(request, "acknowledged_mock" if decision.approved else "insufficient_capital", decision.approved))
    reconciled = g03.resolve_spending(carry.governance, tuple(eligible), policy.spend_costs)
    if reconciled.state != working or reconciled.decisions != tuple(decisions):
        raise ValueError("complete ordered capital ledger failed reconciliation")
    return final, reconciled, tuple(receipts)


def _events(prior: tuple[g04.EvidenceEvent, ...], incoming: tuple[g04.EvidenceEvent, ...],
            snapshot: g04.AmbitionSnapshot) -> tuple[g04.EvidenceEvent, ...]:
    merged = {}
    for event in prior + incoming:
        if event.sequence in merged and event != merged[event.sequence]:
            raise ValueError("conflicting evidence sequence replay")
        if event.civ_id != snapshot.civ_id or event.turn > snapshot.turn or event.sequence > snapshot.event_cursor:
            raise ValueError("event identity/epoch exceeds observation")
        merged[event.sequence] = event
    return tuple(merged[k] for k in sorted(merged))


def run_kernel_frame(*, opening: HarnessCarry, enabled: bool = False,
                     observations: SyntheticFrame | None = None, policy: HarnessPolicy | None = None
                     ) -> HarnessResult:
    """Publish all civilizations atomically, or raise with opening untouched.

    Disabled calls do not inspect observations/policy or call any kernel. On replay
    against a committed carry, epoch/watermark validation rejects repeat spending,
    funding, credit and events. Re-running an old immutable opening is a pure preview.
    """
    if type(enabled) is not bool:
        raise ValueError("enabled must be an explicit boolean")
    if not enabled:
        return HarnessResult(opening, None, (), None, ("four-kernel experiment disabled",))
    if not isinstance(policy, HarnessPolicy) or not isinstance(observations, SyntheticFrame):
        raise ValueError("enabled harness requires complete policy and synthetic observations")
    frame = observations
    turn = opening.effective_turn
    if frame.origin != "explicit_synthetic_fixture":
        raise ValueError("only explicit synthetic fixtures are authorized")
    if type(frame.source_turn) is not int or frame.source_turn != turn or frame.source_turn <= opening.last_committed_turn:
        raise ValueError("frame epoch already committed or not effective")
    if type(frame.ownership_epoch) is not int or frame.ownership_epoch != turn:
        raise ValueError("synthetic ownership epoch must match source turn")
    by_id = {c.civ_id: c for c in frame.civilizations}
    if len(by_id) != len(frame.civilizations) or tuple(sorted(by_id)) != opening.identity_registry:
        raise ValueError("observations must match complete persisted registry")
    for obs in frame.civilizations:
        _int(obs.civ_id, "observation civ ID")
        if obs.ambition_snapshot.civ_id != str(obs.civ_id) or obs.ambition_snapshot.turn != turn:
            raise ValueError("ambition snapshot identity/epoch mismatch")
        for partner in obs.ambition_snapshot.active_trade_partners + obs.ambition_snapshot.attainable_trade_partners:
            _check_civ_reference(partner, opening.identity_registry)
        if obs.legitimacy.institutions or obs.legitimacy.ambition_contributions:
            raise ValueError("harness owns institutional support and ambition contributions")
    elite = g02.compute_elite_metrics(turn=turn,
        civilizations=tuple(g02.CivEliteInput(c.civ_id, sum(a.civ_id == c.civ_id for a in frame.agents), c.ratchet)
                            for c in opening.civilizations), agents=frame.agents, great_persons=frame.great_persons,
        calibration=policy.elite_calibration, conventions=policy.elite_conventions)
    elite_by_id = {c.civ_id: c for c in elite.civilizations}
    next_civs, receipts = [], []
    for carry in opening.civilizations:
        obs = by_id[carry.civ_id]
        if carry.governance.exact_political_capital > policy.capital_limit:
            raise ValueError("opening capital exceeds explicit experimental bound")
        institutions, spent, requests = _institution_transaction(carry, obs, policy)
        inputs = replace(obs.legitimacy, institutions=tuple(g03.InstitutionSupportInput(
            i.institution_type.value, i.faction_alignment.value, i.legitimacy) for i in institutions.next_state.institutions))
        snapshot = replace(obs.ambition_snapshot, legitimacy=carry.governance.ruler_legitimacy,
                           political_capital=spent.state.political_capital)
        if snapshot.event_cursor < carry.evidence_cursor:
            raise ValueError("observation evidence cursor moved backwards")
        known_events = {event.sequence: event for event in carry.evidence_log}
        for event in obs.events:
            if event.sequence <= carry.evidence_cursor and known_events.get(event.sequence) != event:
                raise ValueError("unknown or contradictory replay below committed evidence cursor")
        evidence_log = _events(carry.evidence_log, obs.events, snapshot)
        events = _events(carry.pending_events, obs.events, snapshot)
        contributions = carry.contributions
        archives = carry.archives
        accession = None
        outcomes = ()
        if carry.reign is None or carry.reign.ruler_id != snapshot.ruler_id:
            if not isinstance(obs.accession, g03.SuccessionKind):
                raise ValueError("new reign requires explicit succession kind")
            if snapshot.ruler_id in {a.reign.ruler_id for a in archives}:
                raise ValueError("historical reign ID cannot be reused")
            if carry.reign:
                archives += (ReignArchive(carry.reign, contributions),)
            contributions = ()
            balance = spent.state.exact_political_capital if policy.capital_on_accession == "carry_remaining" else Fraction()
            accession = g03.AccessionInput(obs.accession, float(balance), balance)
            legitimacy = g03.compute_legitimacy(inputs, policy.capital, obs.accession)
            snapshot = replace(snapshot, legitimacy=legitimacy.ruler_legitimacy, political_capital=float(balance))
            _int(obs.accession_event_cursor, "accession event cursor")
            if obs.accession_event_cursor < carry.evidence_cursor:
                raise ValueError("accession cursor precedes committed evidence cursor")
            if obs.accession_event_cursor > snapshot.event_cursor:
                raise ValueError("accession cursor exceeds frame cursor")
            accession_snapshot = replace(snapshot, event_cursor=obs.accession_event_cursor)
            reign = g04.start_reign(accession_snapshot, policy.ambitions, obs.ambition_draws, carry.reign)
            pending = tuple(e for e in events if e.sequence > obs.accession_event_cursor)
        else:
            if obs.accession is not None or obs.ambition_draws or obs.accession_event_cursor is not None:
                raise ValueError("existing reign cannot receive accession/draws")
            evaluation = g04.evaluate_ambitions(carry.reign, snapshot, policy.ambitions, events)
            reign, outcomes = evaluation.reign, evaluation.outcomes
            contributions = merge_contributions(contributions, tuple(Contribution(o.contribution_key, o.legitimacy_delta) for o in outcomes))
            pending = ()
        inputs = replace(inputs, ambition_contributions=tuple(g03.AmbitionLegitimacyInput(contribution_id(c.key), c.delta)
                                                              for c in contributions))
        accrual = g03.accrue_capital(spent.state, inputs, policy.capital, accession)
        if accrual.state.exact_political_capital > policy.capital_limit:
            raise ValueError("generated capital exceeds explicit experimental bound")
        next_civs.append(CivCarry(carry.civ_id, institutions.next_state, elite_by_id[carry.civ_id].next_ratchet_state,
                                 accrual.state, reign, contributions, archives, pending, snapshot.event_cursor, evidence_log))
        receipts.append(CivReceipt(carry.civ_id, institutions, spent, accrual, requests, outcomes))
    result = HarnessCarry(turn + 1, turn, opening.identity_registry, tuple(next_civs))
    return HarnessResult(result, policy.policy_id, tuple(receipts), elite,
        ("explicit synthetic fixtures; no actual simulation integration", "G05 permission-blocked; PSI/production disabled"))


# Strict tagged JSON, using a closed type registry rather than pickle or arbitrary
# imports. All Fraction values survive restart even below float-view resolution.
_CODEC_TYPES = (Contribution, ReignArchive, CivCarry, HarnessCarry,
    g01.InstitutionSnapshot, g01.InstitutionState, g01.InstitutionType, g01.Faction,
    g02.EliteRatchetState, g03.GovernanceState,
    g04.RulerAmbitions, g04.Ambition, g04.AmbitionType, g04.AmbitionContributionKey,
    g04.ConversionPredicate, g04.EvidenceEvent)
_TYPES = {t.__name__: t for t in _CODEC_TYPES}


def _encode(value):
    if isinstance(value, Enum):
        return {"enum": type(value).__name__, "value": value.value}
    if isinstance(value, Fraction):
        return {"fraction": [value.numerator, value.denominator]}
    if is_dataclass(value):
        return {"type": type(value).__name__, "fields": {f.name: _encode(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, tuple):
        return {"tuple": [_encode(v) for v in value]}
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise ValueError("unsupported persistence value")


def _decode(value):
    if not isinstance(value, dict):
        if value is None or type(value) in (str, int, float, bool):
            return value
        raise ValueError("invalid persistence value")
    if set(value) == {"fraction"}:
        pair = value["fraction"]
        if not isinstance(pair, list) or len(pair) != 2 or any(type(n) is not int for n in pair) or pair[1] <= 0:
            raise ValueError("invalid exact Fraction pair")
        return Fraction(*pair)
    if set(value) == {"tuple"} and isinstance(value["tuple"], list):
        return tuple(_decode(v) for v in value["tuple"])
    if set(value) == {"enum", "value"}:
        cls = _TYPES.get(value["enum"])
        if cls is None or not issubclass(cls, Enum):
            raise ValueError("unknown persisted enum")
        return cls(value["value"])
    if set(value) == {"type", "fields"}:
        cls = _TYPES.get(value["type"])
        if cls is None or not is_dataclass(cls) or not isinstance(value["fields"], dict) or set(value["fields"]) != {f.name for f in fields(cls)}:
            raise ValueError("unknown/incomplete persisted record")
        decoded = {k: _decode(v) for k, v in value["fields"].items()}
        _validate_fields(cls, decoded)
        return cls(**decoded)
    raise ValueError("invalid persistence tag")


def carry_to_json(carry: HarnessCarry) -> str:
    return json.dumps({"schema": 1, "carry": _encode(carry)}, sort_keys=True, separators=(",", ":"), allow_nan=False)


def carry_from_json(payload: str) -> HarnessCarry:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result
    data = json.loads(payload, object_pairs_hook=unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    if not isinstance(data, dict) or set(data) != {"schema", "carry"} or type(data["schema"]) is not int or data["schema"] != 1:
        raise ValueError("unsupported harness carry schema")
    carry = _decode(data["carry"])
    if not isinstance(carry, HarnessCarry):
        raise ValueError("payload is not harness carry")
    return carry
