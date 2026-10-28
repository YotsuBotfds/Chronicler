"""Default-off delayed harvest reports and paid granary preparedness.

Assessors use present/past measured production and public seasonality. They
never call a climate predictor or read the future. See the pre-registration
in docs/integration/harvest-forecasts-preregistration.md.
"""
from __future__ import annotations

import math
import random
from chronicler.harvest_forecasts_state import (
    HarvestForecastState, HarvestObserver, HarvestReport, harvest_forecasts_on,
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


def harvest_forecasts_enabled(world) -> bool:
    return harvest_forecasts_on(world)


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
            and world.regions[report.recipient_region].controller == report.owner_name}
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


def _finish_report(world, state, report, *, cancelled=False):
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
        probability = min(0.95, max(0.05, 0.5 + 0.5 * (SHORTFALL_RATIO - predicted)
                                      / SHORTFALL_RATIO + _noise(world, rid)))
        estimates[rid] = (probability, len(observations) / OBSERVATIONS, predicted)
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
    for recipient, (_, source, delay, (probability, confidence, predicted)) in sorted(candidates.items()):
        region = world.regions[recipient]
        report = HarvestReport(
            id=f"harvest:{year}:{source}:{recipient}", source_region=source,
            source_region_name=world.regions[source].name, recipient_region=recipient,
            recipient_region_name=region.name, owner=index[region.controller], owner_name=region.controller,
            issued_turn=world.turn, delivery_turn=world.turn + delay, expires_turn=12 * year + 11,
            target_start=12 * year + 9, target_end=12 * year + 11, probability=probability,
            confidence=confidence, predicted_ratio=predicted,
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
    if state.last_tick_turn is not None and state.last_tick_turn > world.turn:
        raise ValueError("harvest forecast state is ahead of the world turn")
    if state.last_tick_turn == world.turn:
        return []
    state.last_tick_turn = world.turn
    state.preparedness = []
    ratios = _ratios(world, economy_result) if economy_result is not None else {}
    index = {c.name: i for i, c in enumerate(world.civilizations)}
    events = []
    living = []
    for report in state.reports:
        rid = report.recipient_region
        if world.turn > report.expires_turn:
            events.append(_finish_report(world, state, report))
            continue
        if (rid >= len(world.regions) or index.get(world.regions[rid].controller) != report.owner):
            events.append(_finish_report(world, state, report, cancelled=True))
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
        if granary.owner != report.owner or demand <= 0:
            continue
        base = previous[rid]["base_target"] if rid in previous else granary.target
        extra = min(EXTRA_TURNS, EXTRA_TURNS * report.probability * report.confidence) * demand
        granary.target = min(MAX_TOTAL_TURNS * demand, base + extra)
        if rid in previous:
            continue
        state.preparedness.append({
            "region": rid, "region_name": region.name, "owner": report.owner,
            "owner_name": report.owner_name, "forecast_id": report.id,
            "base_target": base, "extra_target": granary.target - base,
            "bought_during_warning": 0.0, "paid_during_warning": 0,
        })


def record_preparedness_purchases(world) -> list:
    """Actual completed-turn purchases while warned, not causal excess."""
    if not harvest_forecasts_active(world):
        return []
    from chronicler.grain_reserves_state import BOUGHT
    state = world.harvest_forecasts
    if world.grain_reserves.flows_turn != world.turn:
        return []
    events = []
    reports = {report.id: report for report in state.reports}
    purchases = {}
    for flow in world.grain_reserves.flows:
        if flow.kind == BOUGHT:
            row = purchases.setdefault(flow.region, [[], 0])
            row[0].append(flow.amount)
            row[1] += flow.cost
    for row in state.preparedness:
        amounts, paid = purchases.get(row["region"], ((), 0))
        bought = math.fsum(amounts)
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
    return {"source_turn": source_turn,
            "reports": [r.model_dump() for r in state.reports],
            "outcomes": [r.model_dump() for r in state.outcomes],
            "preparedness": [dict(row) for row in state.preparedness]
            if state.last_tick_turn == source_turn else [],
            "counters": dict(state.counters), "calibration": [list(b) for b in state.calibration]}
