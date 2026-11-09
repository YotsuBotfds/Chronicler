"""Default-off delayed harvest reports and paid granary preparedness.

Assessors use present/past measured production and public seasonality. They
never call a climate predictor or read the future. See the pre-registration
in docs/integration/harvest-forecasts-preregistration.md.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence
from chronicler.harvest_forecasts_state import (
    ForecastCredibilityEvidence, HarvestEstimatorMetadata, HarvestForecastState, HarvestObserver, HarvestReport,
    harvest_forecasts_on,
)
from chronicler.resources import SEASON_MOD, get_season_id
from chronicler.utils import stable_hash_int

DEFAULT_ENABLED_FOR_NEW_WORLDS = False
OBSERVATIONS = 6
MIN_OBSERVATIONS = 3
SIGNAL_CAP = 4.0
SHORTFALL_RATIO = 0.6
NOISE = 0.15
WARNING_THRESHOLD = 0.6
EXTRA_TURNS = 2.0
MAX_TOTAL_TURNS = 6.0
OUTCOME_CAP = 128
LOCAL_MEMORY_CAP = 4
CREDIBILITY_PRIOR = 2.0


def get_preparation_policy(state) -> str:
    """Old pickles genuinely lacking the new field retain fixed preparation."""
    policy = getattr(state, "preparation_policy", "fixed")
    if type(policy) is not str or policy not in ("fixed", "local_credibility"):
        raise ValueError("unknown harvest preparation policy")
    return policy



def get_report_delay(state) -> int:
    """Old pickles missing the optional field retain the original schedule."""
    delay = getattr(state, "report_delay", None)
    if delay is None:
        return 0
    if type(delay) is not int or not 0 <= delay <= 12:
        raise ValueError("harvest report delay must be an integer from 0 to 12")
    return delay


def set_report_delay(world, delay: int | None) -> None:
    """Set delay for future issues only; never reschedule an existing report."""
    if delay is not None and (type(delay) is not int or not 0 <= delay <= 12):
        raise ValueError("harvest report delay must be an integer from 0 to 12")
    if not harvest_forecasts_on(world):
        raise ValueError("harvest report delay requires an enabled system")
    state = world.harvest_forecasts
    normalized = 0 if delay is None else delay
    if get_report_delay(state) == normalized:
        return  # do not materialize a missing old-pickle field on no-op
    state.report_delay = normalized or None

def _observation_sum(observations):
    # Builtin sum(float) uses compensated arithmetic in newer CPython. Match
    # the existing report's chronological evaluation_sum += ratio operations.
    total = 0.0
    for _, value in observations:
        total += value
    return total


def _check_local_evidence(row, recipient):
    """Revalidate carried records, including arithmetic and visibility dates."""
    if type(row) is not ForecastCredibilityEvidence:
        raise ValueError("malformed local harvest evidence")
    if (type(row.observations) is not list or len(row.observations) != 3
            or any(type(pair) is not tuple or len(pair) != 2
                   or type(pair[0]) is not int or type(pair[1]) not in (int, float)
                   or not math.isfinite(pair[1]) or pair[1] < 0 for pair in row.observations)):
        raise ValueError("malformed local harvest observations")
    checked = ForecastCredibilityEvidence.model_validate(row.model_dump())
    year = checked.issued_turn // 12
    start, end = 12 * year + 9, 12 * year + 11
    expected_id = f"harvest:{year}:{checked.source_region}:{recipient}"
    observations = checked.observations
    if (checked.recipient_region != recipient or checked.report_id != expected_id
            or checked.issued_turn != 12 * year + 5
            or not checked.issued_turn < checked.delivered_turn < start
            or checked.delivered_turn < checked.issued_turn + (
                1 if checked.source_region == recipient else 2)
            or checked.resolved_turn <= end
            or [turn for turn, _ in observations] != list(range(start, end + 1))
            or any(type(turn) is not int or type(value) not in (int, float)
                   or not math.isfinite(value) or value < 0 for turn, value in observations)):
        raise ValueError("ineligible local harvest evidence dates or identity")
    # This is the same ordered addition used by the production observation.
    mean = _observation_sum(observations) / 3
    outcome = mean < SHORTFALL_RATIO
    if (not math.isfinite(mean) or checked.observed_ratio != mean
            or checked.outcome_shortfall is not outcome
            or checked.brier != (checked.probability - float(outcome)) ** 2):
        raise ValueError("local harvest evidence arithmetic differs")
    return checked


def _local_memory(observer):
    rows = getattr(observer, "credibility_memory", [])
    if type(rows) is not list or len(rows) > LOCAL_MEMORY_CAP:
        raise ValueError("local harvest memory exceeds its bound")
    checked = [_check_local_evidence(row, observer.region) for row in rows]
    if (len({row.report_id for row in checked}) != len(checked)
            or any(left.issued_turn >= right.issued_turn
                   for left, right in zip(checked, checked[1:]))):
        raise ValueError("local harvest memory is repeated or out of order")
    return checked


def set_preparation_policy(world, policy: str) -> None:
    """Validate first, restore a known increment within tolerance, then change policy.

    Restoration compares the current target with recorded base + increment
    using the inherited rel_tol=0.0, abs_tol=1e-9 policy. Targets outside that
    tolerance remain untouched.

    Reversion pauses learning/use, retaining local memory. A no-op does not
    materialize a missing old-pickle field or touch a prepared target.
    """
    if type(policy) is not str or policy not in ("fixed", "local_credibility"):
        raise ValueError("unknown harvest preparation policy")
    if not harvest_forecasts_on(world):
        raise ValueError("harvest preparation policy requires an enabled system")
    state = world.harvest_forecasts
    current = get_preparation_policy(state)
    if current == policy:
        return
    if state.last_tick_turn is not None and state.last_tick_turn >= world.turn:
        raise ValueError("harvest preparation policy changes require a pre-tick boundary")
    candidate = HarvestForecastState.model_validate({**state.model_dump(), "preparation_policy": policy})
    for observer in candidate.observers:
        _local_memory(observer)
    # Resolve every restoration read before the first target write. New normal
    # targets cannot be overwritten merely because an old record survives.
    granaries = getattr(getattr(world, "grain_reserves", None), "granaries", ())
    restores = []
    for row in state.preparedness:
        rid, base, extra = row["region"], row["base_target"], row["extra_target"]
        if (type(rid) is not int or type(base) not in (int, float)
                or type(extra) not in (int, float) or not math.isfinite(base)
                or not math.isfinite(extra) or base < 0 or extra < 0):
            raise ValueError("malformed harvest preparedness restoration")
        if 0 <= rid < len(granaries):
            granary = granaries[rid]
            if math.isclose(granary.target, base + extra, rel_tol=0.0, abs_tol=1e-9):
                restores.append((granary, base))
    for granary, base in restores:
        granary.target = base
    state.preparedness = []
    state.preparation_policy = policy


def _remember_local_result(world, state, report, observer_index=None):
    """Never learn from a score's mere presence in global calibration/history."""
    if get_preparation_policy(state) != "local_credibility":
        return
    rid = report.recipient_region
    if (report.status != "resolved" or report.delivered_turn is None
            or type(report.issued_event_id) is not str or not report.issued_event_id
            or type(report.delivered_event_id) is not str or not report.delivered_event_id
            or report.evaluation_count != 3 or report.observed_ratio is None
            or report.outcome_shortfall is None or report.brier is None
            or type(rid) is not int or not 0 <= rid < len(world.regions)
            or type(report.source_region) is not int
            or not 0 <= report.source_region < len(world.regions)
            or not 0 <= report.owner < len(world.civilizations)
            or world.civilizations[report.owner].name != report.owner_name
            or world.regions[rid].controller != report.owner_name
            or world.regions[rid].population <= 0):
        return
    rows = getattr(report, "credibility_observations", [])
    if type(rows) is not list or len(rows) != 3:
        return
    evidence = ForecastCredibilityEvidence(
        report_id=report.id, issued_event_id=report.issued_event_id,
        delivered_event_id=report.delivered_event_id,
        source_region=report.source_region, recipient_region=rid,
        owner=report.owner, owner_name=report.owner_name, issued_turn=report.issued_turn,
        delivered_turn=report.delivered_turn, resolved_turn=report.resolved_turn,
        probability=report.probability, observations=rows,
        observed_ratio=report.observed_ratio, outcome_shortfall=report.outcome_shortfall,
        brier=report.brier)
    _check_local_evidence(evidence, rid)
    if (report.target_start != report.issued_turn // 12 * 12 + 9
            or report.target_end != report.target_start + 2
            or report.evaluation_sum != _observation_sum(rows)
            or report.resolved_turn != world.turn):
        raise ValueError("local harvest result does not match its observations")
    observers = ({o.region: o for o in state.observers}
                 if observer_index is None else observer_index)
    observer = observers.get(rid)
    if observer is None:
        return
    memory = _local_memory(observer)
    for prior in memory:
        if prior.report_id == evidence.report_id:
            if prior != evidence:
                raise ValueError("conflicting local harvest result identity")
            return
    # The one-report-per-recipient/year source contract also makes a replay
    # older than the retained tail inert after its original ID was evicted.
    if memory and evidence.issued_turn <= memory[-1].issued_turn:
        return
    observer.credibility_memory = [*memory, evidence][-LOCAL_MEMORY_CAP:]


def local_preparation_discount(state, report, turn, observer_index=None):
    """Return an action discount plus its bounded earlier local evidence IDs."""
    if get_preparation_policy(state) == "fixed":
        return 1.0, []
    observers = ({o.region: o for o in state.observers}
                 if observer_index is None else observer_index)
    observer = observers.get(report.recipient_region)
    memory = [] if observer is None else _local_memory(observer)
    eligible = [row for row in memory
                if row.source_region == report.source_region
                and row.owner == report.owner and row.owner_name == report.owner_name
                and row.resolved_turn < report.issued_turn <= turn]
    return ((CREDIBILITY_PRIOR + sum(1.0 - row.brier for row in eligible))
            / (CREDIBILITY_PRIOR + len(eligible)), [row.report_id for row in eligible])


def validate_harvest_forecasts(world, *, agent_mode: str | None = None) -> None:
    if not harvest_forecasts_on(world):
        return
    from chronicler.grain_reserves_state import grain_reserves_on
    from chronicler.contact_ledger import ledger_enabled
    mode = world.agent_mode if agent_mode is None else agent_mode
    if not grain_reserves_on(world) or mode in (None, "off") or not ledger_enabled(world):
        raise ValueError("harvest forecasts require --grain-reserves, --contact-ledger "
                         "and an agent-backed goods economy")


def harvest_forecasts_active(world) -> bool:
    if not harvest_forecasts_on(world):
        return False
    from chronicler.grain_reserves_state import grain_reserves_on
    from chronicler.contact_ledger import ledger_enabled
    return (grain_reserves_on(world) and world.agent_mode not in (None, "off")
            and ledger_enabled(world))


def set_harvest_forecasts_enabled(world, enabled: bool, *, policy: str = "normal") -> None:
    if not enabled:
        if harvest_forecasts_on(world):
            _restore_targets(world, world.harvest_forecasts.preparedness)
        world.harvest_forecasts = None
    elif not harvest_forecasts_on(world):
        world.harvest_forecasts = HarvestForecastState(policy=policy)


def _restore_targets(world, rows) -> None:
    """Remove only our known previous increment, never a newly rebuilt target."""
    granaries = getattr(getattr(world, "grain_reserves", None), "granaries", ())
    for row in rows:
        rid = row["region"]
        if 0 <= rid < len(granaries):
            granary = granaries[rid]
            if math.isclose(granary.target, row["base_target"] + row["extra_target"],
                            rel_tol=0.0, abs_tol=1e-9):
                granary.target = row["base_target"]


def clear_stale_preparedness(world) -> None:
    """Before Phase 2 reads last turn's target, honor expiry and ownership."""
    if not harvest_forecasts_on(world):
        return
    state = world.harvest_forecasts
    live = {report.id for report in state.reports
            if report.status == "delivered" and report.expires_turn >= world.turn
            and 0 <= report.recipient_region < len(world.regions)
            and world.regions[report.recipient_region].controller == report.owner_name
            and world.regions[report.recipient_region].population > 0}
    active = harvest_forecasts_active(world)
    _restore_targets(world, [row for row in state.preparedness
                            if not active or row["forecast_id"] not in live])


def _noise(world, source: int) -> float:
    return random.Random(stable_hash_int("harvest_forecasts.observation", world.seed,
                                        world.turn, source)).uniform(-NOISE, NOISE)


def _emit(world, kind: str, report: HarvestReport, text: str, causes=()):
    from chronicler.models import Event
    from chronicler import provenance as prov
    event = Event(turn=world.turn, event_type=kind, actors=[report.owner_name],
                  region=report.recipient_region_name, description=text, importance=3)
    prov.cite(event, *causes)
    prov.observe_now(world, event)
    return event


def _ratios(world, economy_result) -> dict[int, float]:
    from chronicler.grain_reserves import _demand, _harvest
    out = {}
    for rid, region in enumerate(world.regions):
        demand = _demand(economy_result, region.name)
        # Missing output is not a zero harvest observation.
        if (region.controller and region.population > 0 and demand > 0
                and (region.name in economy_result.slot_output
                     or region.name in economy_result.forage_output)):
            value = _harvest(world, economy_result, region) / demand
            if math.isfinite(value) and value >= 0:
                out[rid] = value
    return out


def _finish_report(world, state, report, *, cancelled=False, observer_index=None):
    report.resolved_turn = world.turn
    if cancelled:
        report.status = "cancelled"
        state.counters["cancelled"] += 1
    elif report.evaluation_count == 3:
        report.status = "resolved"
        report.observed_ratio = report.evaluation_sum / 3
        report.outcome_shortfall = report.observed_ratio < SHORTFALL_RATIO
        report.brier = (report.probability - float(report.outcome_shortfall)) ** 2
        state.counters["resolved"] += 1
        state.counters["brier_sum"] += report.brier
        row = state.calibration[min(4, int(report.probability * 5))]
        row[0] += 1
        row[1] += report.probability
        row[2] += float(report.outcome_shortfall)
    else:
        report.status = "unscored"
        state.counters["unscored"] += 1
    _remember_local_result(world, state, report, observer_index)
    state.outcomes.append(report)
    state.outcomes[:] = state.outcomes[-OUTCOME_CAP:]
    text = (f"The harvest assessment for {report.recipient_region_name} is cancelled: its ruler changed."
            if cancelled else
            f"The winter harvest assessment for {report.recipient_region_name} is resolved: "
            + (f"production met {report.observed_ratio:.0%} of food demand."
               if report.observed_ratio is not None else "measurements were incomplete; it is unscored."))
    return _emit(world, "harvest_forecast_resolved", report, text,
                 (report.issued_event_id, report.delivered_event_id))


def _publish(world, state, index) -> list:
    from chronicler import contact_ledger as contact
    observers = {o.region: o for o in state.observers}
    names = {r.name: rid for rid, r in enumerate(world.regions)}
    estimates = {}
    for ci, civ in enumerate(world.civilizations):
        rid = names.get(civ.capital_region)
        if (not civ.regions or rid is None or world.regions[rid].controller != civ.name
                or rid not in observers):
            continue
        observations = [(turn, value) for turn, value in observers[rid].observations
                        if 0 <= world.turn - turn < OBSERVATIONS]
        if len(observations) < MIN_OBSERVATIONS:
            continue
        predicted = math.fsum(value for _, value in observations) / len(observations) * SEASON_MOD[0][3]
        noise = _noise(world, rid)
        probability = min(0.95, max(0.05, 0.5 + 0.5 * (SHORTFALL_RATIO - predicted)
                                      / SHORTFALL_RATIO + noise))
        estimates[rid] = (probability, len(observations) / OBSERVATIONS, predicted, rid, tuple(observations), noise)
    # A deterministic circular permutation is a signal-destruction control;
    # it does not consume another stream or inspect outcomes.
    if state.policy == "shuffle" and len(estimates) > 1:
        ids = sorted(estimates)
        values = [estimates[i] for i in ids]
        estimates = {rid: values[(j + 1) % len(ids)] for j, rid in enumerate(ids)}
    active = {r.recipient_region for r in state.reports}
    candidates = {}
    for source, estimate in sorted(estimates.items()):
        partners = contact.region_partners(world, source) if contact.ledger_enabled(world) else []
        recipients = {source, *(r for r in partners
                                 if contact.region_contact(world, source, r) > 0)}
        for recipient in sorted(recipients):
            if not 0 <= recipient < len(world.regions) or recipient in active:
                continue
            region = world.regions[recipient]
            if region.controller not in index or region.population <= 0:
                continue
            delay = 1 if recipient == source else 2
            rank = (estimate[1], -delay, -source)
            if recipient not in candidates or rank > candidates[recipient][0]:
                candidates[recipient] = (rank, source, delay, estimate)
    events = []
    year = world.turn // 12
    extra_delay = get_report_delay(state)
    for recipient, (_, source, delay, (probability, confidence, predicted, origin, observations, noise)) in sorted(candidates.items()):
        region = world.regions[recipient]
        report = HarvestReport(
            id=f"harvest:{year}:{source}:{recipient}", source_region=source,
            source_region_name=world.regions[source].name, recipient_region=recipient,
            recipient_region_name=region.name, owner=index[region.controller], owner_name=region.controller,
            issued_turn=world.turn, delivery_turn=world.turn + delay + extra_delay, expires_turn=12 * year + 11,
            target_start=12 * year + 9, target_end=12 * year + 11, probability=probability,
            confidence=confidence, predicted_ratio=predicted,
            estimator_metadata=HarvestEstimatorMetadata(
                issued_turn=world.turn, reported_issuer_region=source, estimate_origin_region=origin,
                policy=state.policy, preparation_policy=get_preparation_policy(state),
                base_delivery_lag=delay, extra_delivery_delay=extra_delay, observations=observations,
                season_multiplier=SEASON_MOD[0][3], shortfall_ratio=SHORTFALL_RATIO, noise_draw=noise,
                claimed_probability=probability, claimed_confidence=confidence, claimed_predicted_ratio=predicted),
        )
        event = _emit(world, "harvest_forecast_issued", report,
                      f"Assessors in {report.source_region_name} estimate a {probability:.0%} chance "
                      f"of winter production shortfall in {region.name}; the report is due on turn "
                      f"{report.delivery_turn}, not yet delivered.")
        report.issued_event_id = event.event_id
        state.reports.append(report)
        state.counters["issued"] += 1
        events.append(event)
    return events


def tick_harvest_forecasts(world, economy_result) -> list:
    """After present production and normal granary targets are measured.
    Contacts are the previous completed turn's ledger; no same-turn delivery.
    """
    if not harvest_forecasts_active(world):
        return []
    state = world.harvest_forecasts
    preparation_policy = get_preparation_policy(state)
    observer_index = ({o.region: o for o in state.observers}
                      if preparation_policy == "local_credibility" else None)
    if state.last_tick_turn is not None and state.last_tick_turn > world.turn:
        raise ValueError("harvest forecast state is ahead of the world turn")
    if state.last_tick_turn == world.turn:
        return []
    # _observe does not rebuild a base for empty/unobserved granaries. Remove
    # only their known old increment before discarding its restoration record.
    from chronicler.grain_reserves import _demand
    granaries = world.grain_reserves.granaries
    _restore_targets(world, [row for row in state.preparedness
        if 0 <= row["region"] < len(granaries) and (
            economy_result is None or granaries[row["region"]].owner < 0
            or world.regions[row["region"]].population <= 0
            or _demand(economy_result, world.regions[row["region"]].name) <= 0)])
    state.last_tick_turn = world.turn
    state.preparedness = []
    ratios = _ratios(world, economy_result) if economy_result is not None else {}
    index = {c.name: i for i, c in enumerate(world.civilizations)}
    events = []
    living = []
    for report in state.reports:
        rid = report.recipient_region
        if world.turn > report.expires_turn:
            events.append(_finish_report(world, state, report, observer_index=observer_index))
            continue
        if (rid >= len(world.regions) or index.get(world.regions[rid].controller) != report.owner):
            events.append(_finish_report(world, state, report, cancelled=True,
                                         observer_index=observer_index))
            continue
        if report.status == "pending" and world.turn >= report.delivery_turn:
            if state.policy == "withhold":
                report.status = "withheld"
                state.counters["withheld"] += 1
            else:
                report.status, report.delivered_turn = "delivered", world.turn
                event = _emit(world, "harvest_forecast_delivered", report,
                              f"The winter harvest assessment from {report.source_region_name} reaches "
                              f"{report.recipient_region_name} ({report.probability:.0%} shortfall risk).",
                              (report.issued_event_id,))
                report.delivered_event_id = event.event_id
                state.counters["delivered"] += 1
                events.append(event)
        if report.target_start <= world.turn <= report.target_end and rid in ratios:
            report.evaluation_sum += ratios[rid]
            report.evaluation_count += 1
            if (preparation_policy == "local_credibility" and report.status == "delivered"
                    and report.delivered_turn is not None
                    and report.delivered_turn < report.target_start):
                report.credibility_observations = [
                    *getattr(report, "credibility_observations", []), (world.turn, ratios[rid])]
        living.append(report)
    state.reports = living
    observers = {o.region: o for o in state.observers}
    factor = SEASON_MOD[0][get_season_id(world.turn)]
    for rid, ratio in sorted(ratios.items()):
        if rid not in observers:
            observers[rid] = HarvestObserver(region=rid)
        observer = observers[rid]
        observer.observations.append((world.turn, min(SIGNAL_CAP, ratio / factor)))
        observer.observations[:] = observer.observations[-OBSERVATIONS:]
    state.observers = [observers[rid] for rid in sorted(observers)]
    if world.turn % 12 == 5:
        events.extend(_publish(world, state, index))
    return events


def apply_preparedness(world, economy_result) -> None:
    """Rebuild only the target increment; ordinary procurement buys/pays."""
    if not harvest_forecasts_active(world):
        return
    from chronicler.grain_reserves import _demand
    state = world.harvest_forecasts
    preparation_policy = get_preparation_policy(state)
    observer_index = ({o.region: o for o in state.observers}
                      if preparation_policy == "local_credibility" else None)
    previous = {row["region"]: row for row in state.preparedness}
    for report in state.reports:
        if (report.status != "delivered" or report.probability < WARNING_THRESHOLD
                or report.delivered_turn is None or report.delivered_turn > world.turn
                or not report.delivery_turn <= world.turn <= report.expires_turn):
            continue
        rid = report.recipient_region
        region = world.regions[rid]
        granary = world.grain_reserves.granaries[rid]
        demand = _demand(economy_result, region.name)
        if granary.owner != report.owner or demand <= 0 or region.population <= 0:
            continue
        base = previous[rid]["base_target"] if rid in previous else granary.target
        wanted = max(0.0, min(EXTRA_TURNS, EXTRA_TURNS * report.probability * report.confidence)) * demand
        if preparation_policy == "local_credibility":
            discount, evidence_ids = local_preparation_discount(
                state, report, world.turn, observer_index)
            wanted *= discount
        # The cap limits our addition, never the existing base. Demand may
        # shrink after the economy measured it or before this helper repeats.
        extra = min(wanted, max(0.0, MAX_TOTAL_TURNS * demand - base))
        granary.target = base + extra
        if rid in previous:
            previous[rid]["extra_target"] = extra
            continue
        row = {
            "region": rid, "region_name": region.name, "owner": report.owner,
            "owner_name": report.owner_name, "forecast_id": report.id,
            "base_target": base, "extra_target": granary.target - base,
            "bought_during_warning": 0.0, "paid_during_warning": 0,
        }
        if preparation_policy == "local_credibility":
            row.update(preparation_policy=preparation_policy, credibility_discount=discount,
                       credibility_evidence_ids=evidence_ids)
        state.preparedness.append(row)



@dataclass(frozen=True, slots=True)
class KnownHarvestReport:
    """Only report information already visible at the decision boundary."""
    id: str
    source_region: int
    recipient_region: int
    issued_turn: int
    planned_delivery_turn: int
    delivered_turn: int
    expires_turn: int
    probability: float
    confidence: float
    predicted_ratio: float
    target_start: int
    target_end: int
    issued_event_id: str
    delivered_event_id: str


@dataclass(frozen=True, slots=True)
class ForecastDecision:
    region: int
    owner: int  # actual granary keeper, which may precede current control
    controller: int | None
    reports: tuple[KnownHarvestReport, ...]
    target_before: float | None
    requested_target: float
    feasible_target: float
    granary_stock: float
    food_demand: float | None
    pending_inbound: float | None
    opening_budget: int


@dataclass(frozen=True, slots=True)
class ForecastDecisionBatch:
    """Transient capture; cannot be moved across worlds, turns or flow resets."""
    turn: int
    decisions: tuple[ForecastDecision, ...]
    _world_id: int
    _flows_id: int
    _flow_start: int


@dataclass(frozen=True, slots=True)
class ForecastDecisionReceipt:
    turn: int
    decision: ForecastDecision
    purchased_grain: float
    committed_grain: float
    paid: int
    # Current procurement does not expose unsuccessful attempts.
    attempted: None = None


def _nonnegative_number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"invalid forecast decision {name}")
    return float(value)


def begin_forecast_decisions(world, economy_result, opening_budget: Sequence[int],
                             inbound: Sequence[float] | None = None, *,
                             target_before: Sequence[float | None] | None = None,
                             requested_targets: Sequence[float] | None = None,
                             capacity_records=None
                             ) -> ForecastDecisionBatch | None:
    """Capture a read-only, then-known Phase 10 procurement boundary.

    Call after forecast processing, target adjustment and paid arrivals, after
    computing the actual per-civ budget, immediately before purchase loops.
    `target_before` may supply targets captured before preparedness; absent
    values stay unknown unless the existing preparedness record supplies one.
    Freeze `requested_targets` immediately after forecast preparedness and pass
    the live same-turn storage receipts after its capacity settlement. Changed
    targets must match those receipts and the real current storage limit. With
    no cap, callers may omit both. An omitted inbound vector is unknown, not
    an invented zero. Do not retain a batch across turns/checkpoints.
    """
    if not harvest_forecasts_active(world):
        return None
    state = world.harvest_forecasts
    reserves = world.grain_reserves
    n = len(world.regions)
    if (state.last_tick_turn != world.turn or reserves.flows_turn != world.turn
            or len(reserves.granaries) != n or economy_result is None):
        raise ValueError("forecast decision requires the current procurement boundary")
    if (len(opening_budget) != len(world.civilizations)
            or any(type(x) is not int or x < 0 for x in opening_budget)):
        raise ValueError("invalid forecast decision opening budget")
    if inbound is not None and len(inbound) != n:
        raise ValueError("invalid forecast decision inbound vector")
    if target_before is not None and len(target_before) != n:
        raise ValueError("invalid forecast decision prior target vector")
    if requested_targets is not None and len(requested_targets) != n:
        raise ValueError("invalid forecast decision requested target vector")
    if capacity_records is not None and requested_targets is None:
        raise ValueError("capacity evidence requires requested targets")
    actual_targets = [_nonnegative_number(g.target, "feasible target") for g in reserves.granaries]
    requested_values = (actual_targets if requested_targets is None else
                        [_nonnegative_number(v, "requested target") for v in requested_targets])
    cap_by_region = {}
    if capacity_records is not None:
        from chronicler.grain_storage_state import StorageReceipt
        from chronicler.grain_storage import storage_limit
        storage = getattr(reserves, "storage", None)
        if (storage is None or getattr(storage, "receipt_turn", None) != world.turn
                or capacity_records is not storage.receipts):
            raise ValueError("storage cap evidence is not the current authoritative receipt list")
        for row in capacity_records:
            if (not isinstance(row, StorageReceipt) or type(row.region) is not int
                    or not 0 <= row.region < n or row.region in cap_by_region or row.turn != world.turn):
                raise ValueError("invalid or duplicate storage cap evidence")
            if row.target_requested is None or row.target_feasible is None:
                raise ValueError("storage cap evidence is incomplete")
            before = _nonnegative_number(row.target_requested, "storage requested target")
            after = _nonnegative_number(row.target_feasible, "storage feasible target")
            limit = storage_limit(world, row.region)
            if (limit is None or not math.isclose(before, requested_values[row.region], rel_tol=0, abs_tol=1e-9)
                    or not math.isclose(after, actual_targets[row.region], rel_tol=0, abs_tol=1e-9)
                    or not math.isclose(after, min(before, limit), rel_tol=0, abs_tol=1e-9)):
                raise ValueError("storage cap evidence conflicts with targets or capacity")
            cap_by_region[row.region] = row
    for rid, (requested, actual) in enumerate(zip(requested_values, actual_targets, strict=True)):
        if not math.isclose(requested, actual, rel_tol=0, abs_tol=1e-9) and rid not in cap_by_region:
            raise ValueError("changed forecast target lacks actual storage cap evidence")
    inbound_values = ([None] * n if inbound is None else
                      [_nonnegative_number(v, "inbound") for v in inbound])
    prior_values = ([None] * n if target_before is None else [
        None if v is None else _nonnegative_number(v, "prior target") for v in target_before])
    owners = {c.name: i for i, c in enumerate(world.civilizations)}
    selected = {}
    selected_ids = set()
    for report in state.reports:
        # This is the same visibility/threshold filter used by the decider.
        if (report.status != "delivered" or report.probability < WARNING_THRESHOLD
                or report.delivered_turn is None or report.delivered_turn > world.turn
                or not report.delivery_turn <= world.turn <= report.expires_turn):
            continue
        rid = report.recipient_region
        if type(rid) is not int or not 0 <= rid < n:
            raise ValueError("invalid forecast decision recipient")
        region, granary = world.regions[rid], reserves.granaries[rid]
        raw = economy_result.market_demand.get(region.name)
        demand = float(raw[0]) if raw else 0.0
        if granary.owner != report.owner or demand <= 0 or region.population <= 0:
            continue
        if (type(report.source_region) is not int or not 0 <= report.source_region < n
                or type(report.owner) is not int or not 0 <= report.owner < len(world.civilizations)
                or report.owner_name != world.civilizations[report.owner].name
                or report.recipient_region_name != region.name
                or report.source_region_name != world.regions[report.source_region].name
                or type(report.id) is not str or not report.id
                or any(type(t) is not int for t in (report.issued_turn, report.delivery_turn,
                                                     report.delivered_turn, report.expires_turn,
                                                     report.target_start, report.target_end))
                or not report.issued_turn < report.delivery_turn <= report.delivered_turn <= world.turn
                or not report.issued_turn < report.target_start <= report.target_end == report.expires_turn
                or not all(math.isfinite(x) and 0 <= x <= 1
                           for x in (report.probability, report.confidence))
                or not math.isfinite(report.predicted_ratio) or report.predicted_ratio < 0
                or type(report.issued_event_id) is not str or type(report.delivered_event_id) is not str):
            raise ValueError("contradictory forecast decision report")
        if rid in selected or report.id in selected_ids:
            raise ValueError("contradictory eligible forecast reports")
        selected_ids.add(report.id)
        selected[rid] = KnownHarvestReport(
            report.id, report.source_region, rid, report.issued_turn, report.delivery_turn,
            report.delivered_turn, report.expires_turn, report.probability, report.confidence,
            report.predicted_ratio, report.target_start, report.target_end,
            report.issued_event_id, report.delivered_event_id)
    prepared = {}
    for row in state.preparedness:
        rid = row.get("region")
        if type(rid) is not int or not 0 <= rid < n or rid in prepared:
            raise ValueError("contradictory forecast preparedness")
        report = selected.get(rid)
        if report is None or row.get("forecast_id") != report.id:
            raise ValueError("preparedness has no eligible forecast")
        base = _nonnegative_number(row.get("base_target"), "base target")
        extra = _nonnegative_number(row.get("extra_target"), "target increment")
        if not math.isclose(requested_values[rid], base + extra, rel_tol=0, abs_tol=1e-9):
            raise ValueError("preparedness conflicts with requested target")
        if prior_values[rid] is not None and not math.isclose(prior_values[rid], base, rel_tol=0, abs_tol=1e-9):
            raise ValueError("prior target conflicts with preparedness")
        prepared[rid] = base
    if set(selected) != set(prepared):
        raise ValueError("eligible forecast was not applied to preparedness")
    decisions = []
    for rid, (region, granary) in enumerate(zip(world.regions, reserves.granaries, strict=True)):
        owner = granary.owner
        if type(owner) is not int or not -1 <= owner < len(world.civilizations):
            raise ValueError("invalid forecast decision granary keeper")
        if owner < 0:
            continue
        controller = owners.get(region.controller)
        requested = requested_values[rid]
        feasible = actual_targets[rid]
        stock = _nonnegative_number(granary.grain, "stock")
        raw = economy_result.market_demand.get(region.name)
        demand = None if not raw else _nonnegative_number(raw[0], "food demand")
        report = selected.get(rid)
        decisions.append(ForecastDecision(
            rid, owner, controller, () if report is None else (report,),
            prepared.get(rid, prior_values[rid]), requested, feasible, stock, demand,
            inbound_values[rid], opening_budget[owner]))
    return ForecastDecisionBatch(world.turn, tuple(decisions), id(world), id(reserves.flows), len(reserves.flows))


def finish_forecast_decisions(world, batch: ForecastDecisionBatch | None) -> tuple[ForecastDecisionReceipt, ...]:
    """Freeze actual new purchase/dispatch flows; never infer an attempt or outcome."""
    if batch is None:
        return ()
    from chronicler.grain_reserves_state import BOUGHT, DISPATCHED
    reserves = world.grain_reserves
    if (batch._world_id != id(world) or batch.turn != world.turn
            or reserves.flows_turn != batch.turn or id(reserves.flows) != batch._flows_id
            or len(reserves.flows) < batch._flow_start):
        raise ValueError("forecast decision capture no longer matches procurement")
    totals = {row.region: [[], [], 0] for row in batch.decisions}
    owners = {row.region: row.owner for row in batch.decisions}
    for flow in reserves.flows[batch._flow_start:]:
        if flow.kind not in (BOUGHT, DISPATCHED) or flow.region not in totals:
            continue
        if flow.buyer != owners[flow.region] or type(flow.cost) is not int or flow.cost < 0:
            raise ValueError("contradictory forecast decision purchase")
        amount = _nonnegative_number(flow.amount, "purchase amount")
        row = totals[flow.region]
        row[0 if flow.kind == BOUGHT else 1].append(amount)
        row[2] += flow.cost
    return tuple(ForecastDecisionReceipt(batch.turn, row, math.fsum(totals[row.region][0]),
                                        math.fsum(totals[row.region][1]), totals[row.region][2])
                 for row in batch.decisions)

def record_preparedness_purchases(world) -> list:
    """Actual completed-turn purchases while warned, not causal excess."""
    if not harvest_forecasts_active(world):
        return []
    from chronicler.grain_reserves_state import ARRIVED, BOUGHT, DISPATCHED
    state = world.harvest_forecasts
    if world.grain_reserves.flows_turn != world.turn:
        return []
    events = []
    reports = {report.id: report for report in state.reports}
    purchases = {}
    shipment_purchases = {}
    shipment_state = getattr(world.grain_reserves, "shipments", None)
    for flow in world.grain_reserves.flows:
        if flow.kind == BOUGHT:
            row = purchases.setdefault(flow.region, [[], 0])
            row[0].append(flow.amount)
            row[1] += flow.cost
        elif shipment_state is not None and flow.kind in (DISPATCHED, ARRIVED):
            extra = shipment_purchases.setdefault(flow.region, [0.0, 0, 0.0])
            if flow.kind == DISPATCHED:
                extra[0] += flow.amount
                extra[1] += flow.cost
            else:
                extra[2] += flow.amount
    for row in state.preparedness:
        amounts, paid = purchases.get(row["region"], ((), 0))
        bought = math.fsum(amounts)
        if shipment_state is not None:
            values = shipment_purchases.get(row["region"], (0.0, 0, 0.0))
            keys = ("committed_during_warning", "paid_for_shipments_during_warning",
                    "arrived_during_warning")
            row["shipment_ids_during_warning"] = [transition.id for transition in shipment_state.frame
                if shipment_state.frame_turn == world.turn and transition.dest == row["region"]]
            old_paid = row.get(keys[1], 0)
            for key, value in zip(keys, values):
                state.counters[key] = state.counters.get(key, 0) - row.get(key, 0) + value
                row[key] = value
            if values[1] > 0 and old_paid != values[1] and row["forecast_id"] in reports:
                report = reports[row["forecast_id"]]
                events.append(_emit(world, "harvest_preparedness", report,
                    f"While warned of shortfall, {report.owner_name} pays {values[1]} treasury "
                    f"for {values[0]:.1f} grain still in transit; it is not yet in the granary.",
                    (report.delivered_event_id,)))
        if row["bought_during_warning"] == bought and row["paid_during_warning"] == paid:
            continue
        state.counters["bought_during_warning"] -= row["bought_during_warning"]
        state.counters["paid_during_warning"] -= row["paid_during_warning"]
        row["bought_during_warning"] = bought
        row["paid_during_warning"] = paid
        state.counters["bought_during_warning"] += row["bought_during_warning"]
        state.counters["paid_during_warning"] += row["paid_during_warning"]
        if paid > 0 and row["forecast_id"] in reports:
            report = reports[row["forecast_id"]]
            events.append(_emit(
                world, "harvest_preparedness", report,
                f"While warned of winter shortfall, {report.owner_name} buys {bought:.1f} grain "
                f"for the granary in {report.recipient_region_name} ({paid} treasury).",
                (report.delivered_event_id,),
            ))
    return events


def snapshot_summary(world) -> dict:
    if not harvest_forecasts_active(world):
        return {}
    state = world.harvest_forecasts
    source_turn = world.turn - 1
    if state.last_tick_turn != source_turn:
        return {}
    result = {"source_turn": source_turn,
            "reports": [r.model_dump() for r in state.reports],
            "outcomes": [r.model_dump() for r in state.outcomes],
            "preparedness": [dict(row) for row in state.preparedness]
            if state.last_tick_turn == source_turn else [],
            "counters": dict(state.counters), "calibration": [list(b) for b in state.calibration]}
    decisions = getattr(state, "procurement_decisions", None)
    if decisions is not None and decisions.get("source_turn") == source_turn:
        from copy import deepcopy
        result["procurement_decisions"] = deepcopy(decisions)
    delay = get_report_delay(state)
    if delay:
        result["report_delay"] = delay
    return result
