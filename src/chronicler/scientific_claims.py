"""Paid academy trials, contextual evidence and bounded adoption effort.

Default off. Experiments measure existing physical functions on a read-only
single-region view; they never harvest goods or create technique truth flags.
See docs/experiments/scientific-claims-2026-10.md for the prospective contract.
"""
from __future__ import annotations

import math
import random

from chronicler.scientific_claims_state import (
    AdoptionEffort, ClaimContext, EvidenceReceipt, MAX_SEATS, MAX_TRIALS,
    ProposalReceipt, ScienceMessage, ScientificClaim, ScientificClaimsState,
    ScientificTrial, scientific_claims_on, LEGACY_PUBLICATION, FUNDED_CONTEXT_PUBLICATION,
)
from chronicler.scholarship_state import ACADEMY, scholarship_on
from chronicler.techniques_state import GRAIN, TECHNIQUE_INDEX, TechniqueState, techniques_on
from chronicler.utils import stable_hash_int

DEFAULT_ENABLED_FOR_NEW_WORLDS = False
RECIPES = ("irrigation", "masonry")
TRIAL_COST = 2
TREASURY_FLOOR = 20
MEASUREMENT_NOISE = 0.03
REPLICATION_LAG = 12
EFFORT_CADENCE = 6
EFFORT_COST = 1
EFFORT_ALLOWANCE = 0.01
ALLOCATION_EVENT_DELTA = 0.05  # observation only; does not control paid effort
MAX_HOPS = 3
DELIVERY_LIFETIME = 6


def set_scientific_claims_enabled(world, enabled: bool) -> None:
    if enabled:
        if not scientific_claims_on(world):
            world.scientific_claims = ScientificClaimsState()
    else:
        world.scientific_claims = None


def scientific_claims_active(world) -> bool:
    """Persisted state is dormant without both existing host systems."""
    return scientific_claims_on(world) and scholarship_on(world) and techniques_on(world)


def _academy(world, seat_id: int):
    if not scholarship_on(world) or not 0 <= seat_id < len(world.scholarship.seats):
        return None
    seat = world.scholarship.seats[seat_id]
    if (seat.kind != ACADEMY or seat.founded_turn > world.turn
            or seat.fallen_turn is not None or seat.level <= 0
            or not 0 <= seat.region < len(world.regions)):
        return None
    return seat


def _payer(world, seat) -> int:
    owner = world.regions[seat.region].controller
    return next((i for i, c in enumerate(world.civilizations) if c.name == owner), -1)


def _context(world, seat_id: int) -> ClaimContext | None:
    seat = _academy(world, seat_id)
    if seat is None:
        return None
    region = world.regions[seat.region]
    ci = _payer(world, seat)
    if ci < 0 or region.population <= 0 or GRAIN not in region.resource_types:
        return None
    from chronicler.nomads_state import SEDENTARY, nomads_on
    if nomads_on(world) and world.nomads.mode(ci) != SEDENTARY:
        return None
    from chronicler.climate import get_climate_phase
    from chronicler.resources import get_season_id
    return ClaimContext(soil_band=min(3, max(0, int(region.ecology.soil * 4))),
                        water_band=min(3, max(0, int(region.ecology.water * 4))),
                        season=get_season_id(world.turn),
                        climate_phase=get_climate_phase(world.turn, world.climate_config).value)


def _applicable(world, seat_id: int, claim: ScientificClaim) -> bool:
    ctx = _context(world, seat_id)
    if ctx is None or ctx != claim.context:
        return False
    region = world.scholarship.seats[seat_id].region
    k = TECHNIQUE_INDEX.get(claim.recipe)
    return k is not None and any(r == region and kk == k and p > 0
                                 for r, kk, p, *_ in world.techniques.rows)


class _TrialView:
    """Only a bounded local copy and fresh technique/cache lookups are mutable.

    Other world attributes are read through. The evaluated physical path is
    explicitly read-only (including deplete_reserves=False); a local region
    copy also prevents an accidental reserve write reaching production state.
    No full-world fork, random-stream copy or actual worker allocation occurs.
    """
    def __init__(self, world, region_id: int, recipe: str, level: float):
        self._world = world
        self.regions = list(world.regions)
        self.regions[region_id] = world.regions[region_id].model_copy(deep=True)
        self.civ_index_map = {c.name: i for i, c in enumerate(world.civilizations)}
        k = TECHNIQUE_INDEX[recipe]
        rows = [row for row in world.techniques.rows if row[0] == region_id and row[1] != k]
        rows.append((region_id, k, level, -1, 0, -1))
        self.techniques = TechniqueState(rows=sorted(rows))

    def __getattr__(self, name):
        return getattr(self._world, name)


def evaluate_trial(world, region_id: int, claim: ScientificClaim) -> tuple[float, float, dict]:
    """Measure paired physical grain outputs without touching simulation state.

    Full-serialization/RNG/cache preservation is checked in acceptance tests;
    expensive whole-world snapshots are intentionally outside this turn path.
    The recorded input fingerprint is source identity, never evidential weight.
    """
    from chronicler.climate import climate_clusters, get_climate_phase, HARVEST_YEAR
    from chronicler.ecology import compute_resource_yields, goods_per_worker
    from chronicler.economy import compute_allocated_production
    from chronicler.resources import get_season_id
    region = world.regions[region_id]
    season = get_season_id(world.turn)
    phase = get_climate_phase(world.turn, world.climate_config)
    slot = region.resource_types.index(GRAIN)
    outputs = []
    for level in (claim.comparator, claim.intervention):
        view = _TrialView(world, region_id, claim.recipe, level)
        harvest = compute_resource_yields(view.regions[region_id], season, phase, 0, view,
                                          deplete_reserves=False)
        grain = goods_per_worker(GRAIN, harvest[slot])
        outputs.append(compute_allocated_production([GRAIN, 255, 255], [grain, 0., 0.],
                                                   claim.context.crew).get("grain", 0.))
    block = f"{world.seed}:{climate_clusters(world)[region_id]}:{world.turn // HARVEST_YEAR}"
    from chronicler.ecology import yield_penalty_reaches_goods
    inputs = {
        "region": region_id, "name": region.name, "turn": world.turn,
        "context": claim.context.model_dump(), "season": season, "phase": phase.value,
        "ecology": region.ecology.model_dump(), "types": list(region.resource_types),
        "base": list(region.resource_base_yields), "effective": list(region.resource_effective_yields),
        "reserves": list(region.resource_reserves), "suspended": dict(region.resource_suspensions),
        "practice": [list(row) for row in world.techniques.rows if row[0] == region_id],
        "climate": world.climate_config.model_dump(), "tuning": dict(world.tuning_overrides),
        "yield_penalties": yield_penalty_reaches_goods(world), "environment": block,
    }
    return outputs[0], outputs[1], inputs


def _pay(world, seat_id: int, cost: int, acc) -> int:
    seat = _academy(world, seat_id)
    if seat is None:
        return -1
    ci = _payer(world, seat)
    if ci < 0:
        return -1
    from chronicler.finance import _projections
    if _projections(world, acc)[ci] - cost < TREASURY_FLOOR:
        return -1
    civ = world.civilizations[ci]
    if acc is None:
        civ.treasury -= cost
    else:
        acc.add(ci, civ, "treasury", -cost, "keep")
    return ci


def _emit(world, events, kind: str, seat_id: int, description: str, *, causes=(), payer=None):
    """Assign ordinary timeline identity; domain claim/trial IDs stay separate.

    Phase owners append returned records to their event list. Standalone
    helpers may omit the destination, but still get deterministic references.
    No cause is inferred from a recipe's physical diagnostic or its label.
    """
    from chronicler import provenance
    from chronicler.models import Event
    seat = world.scholarship.seats[seat_id]
    region = world.regions[seat.region]
    if payer is None:
        payer = _payer(world, seat)
    actors = ([world.civilizations[payer].name] if 0 <= payer < len(world.civilizations) else [])
    event = Event(turn=world.turn, event_type=kind, actors=actors + [seat.name],
                  region=region.name, description=description, importance=3)
    provenance.cite(event, *causes)
    provenance.observe_now(world, event)
    if events is not None:
        events.append(event)
    return event


def _fund_trial(world, claim, seat_id: int, parent: int, acc, events=None, *, research_cycle=None) -> None:
    state = world.scientific_claims
    if len(state.trials) >= MAX_TRIALS:
        return
    payer = _pay(world, seat_id, TRIAL_COST, acc)
    if payer < 0:
        state.unfunded_trials += 1
        return
    trial = ScientificTrial(id=len(state.trials), claim=claim.id, seat=seat_id, payer=payer,
                            funded_turn=world.turn, completion_turn=world.turn + 1,
                            cost=TRIAL_COST, parent=parent)
    state.trials.append(trial)
    if research_cycle is not None:
        research_cycle.trials.append(trial.id)
    state.trial_spent += TRIAL_COST
    parent_trial = next((t for t in state.trials if t.id == parent), None)
    funded = _emit(world, events, "scientific_trial_funded", seat_id,
                   f"{world.scholarship.seats[seat_id].name} pays {TRIAL_COST} treasury units "
                   f"for trial #{trial.id} of its contextual {claim.recipe} grain-output claim",
                   causes=(claim.event_id, parent_trial.funded_event_id if parent_trial else "",
                           research_cycle.announcement_event_id if research_cycle is not None else ""), payer=payer)
    trial.funded_event_id = funded.event_id
    try:
        region_id = world.scholarship.seats[seat_id].region
        control, treatment, inputs = evaluate_trial(world, region_id, claim)
        if not all(math.isfinite(v) and v >= 0 for v in (control, treatment)):
            raise ValueError("non-finite or negative physical output")
        trial.control_output, trial.treatment_output, trial.inputs = control, treatment, inputs
        trial.source_data = f"source-{stable_hash_int(claim.recipe, inputs):016x}"
        trial.environment_block = inputs["environment"]
        trial.dependence_group = f"{claim.id}:{trial.method}:{trial.environment_block}"
    except (ValueError, ArithmeticError) as exc:
        trial.status, trial.reason = "failed", str(exc)
        trial.resolved_turn = world.turn
        state.failed += 1
        trial.event_id = _emit(world, events, "scientific_trial_failed", seat_id,
                               f"Paid trial #{trial.id} at {world.scholarship.seats[seat_id].name} "
                               "fails to produce valid physical measurements",
                               causes=(trial.funded_event_id,), payer=payer).event_id


def _record_receipt(world, receipt: EvidenceReceipt, events=None) -> None:
    state = world.scientific_claims
    trial = next(t for t in state.trials if t.id == receipt.trial)
    forwarded = next((r for r in state.receipts
                      if r.seat == receipt.sender and r.trial == receipt.trial), None)
    receipt.event_id = _emit(world, events, "scientific_evidence_received", receipt.seat,
                             f"{world.scholarship.seats[receipt.seat].name} receives the recorded "
                             f"result of trial #{receipt.trial} as local evidence",
                             causes=(trial.event_id, forwarded.event_id if forwarded else "")).event_id
    state.receipts.append(receipt)


def _valid_funded_measurement(trial, claim) -> bool:
    """Validate recorded evidence without rereading current physical truth."""
    return (trial.method == claim.context.protocol
            and trial.inputs.get("context") == claim.context.model_dump()
            and trial.inputs.get("turn") == trial.funded_turn
            and trial.inputs.get("environment") == trial.environment_block
            and bool(trial.source_data) and bool(trial.environment_block)
            and trial.dependence_group == f"{claim.id}:{trial.method}:{trial.environment_block}"
            and all(math.isfinite(value) and value >= 0
                    for value in (trial.control_output, trial.treatment_output)))


def _trial_available(trial, turn: int) -> bool:
    """A completed record is available only after all its actual dates."""
    return (trial.status == "completed" and trial.resolved_turn is not None
            and trial.funded_turn < trial.completion_turn <= trial.resolved_turn <= turn)


def _finish_trials(world, events=None) -> None:
    state = world.scientific_claims
    claims = {c.id: c for c in state.claims}
    for trial in state.trials:
        if trial.status != "running" or world.turn < trial.completion_turn:
            continue
        claim = claims[trial.claim]
        if world.turn <= trial.funded_turn or claim.proposed_turn > world.turn:
            continue
        funded_rule = getattr(state, "publication_rule", LEGACY_PUBLICATION) == FUNDED_CONTEXT_PUBLICATION
        if funded_rule:
            seat = _academy(world, trial.seat)
            access = seat is not None and world.regions[seat.region].population > 0
            cancellation_subject = "academy or publication access"
        else:
            access = _applicable(world, trial.seat, claim)
            cancellation_subject = "academy or registered context"
        if not access:
            trial.status, trial.reason = "cancelled", cancellation_subject + " unavailable"
            trial.resolved_turn = world.turn
            state.cancelled += 1
            trial.event_id = _emit(world, events, "scientific_trial_cancelled", trial.seat,
                                   f"Paid trial #{trial.id} at {world.scholarship.seats[trial.seat].name} "
                                   f"is cancelled because its {cancellation_subject} is unavailable",
                                   causes=(trial.funded_event_id,), payer=trial.payer).event_id
            continue
        if funded_rule and not _valid_funded_measurement(trial, claim):
            trial.status, trial.reason = "failed", "funded measurement record unavailable or invalid"
            trial.resolved_turn = world.turn
            state.failed += 1
            trial.event_id = _emit(world, events, "scientific_trial_failed", trial.seat,
                                   f"Paid trial #{trial.id} at {world.scholarship.seats[trial.seat].name} "
                                   "has no valid recorded funded-context measurement to publish",
                                   causes=(trial.funded_event_id,), payer=trial.payer).event_id
            continue
        rng = random.Random(stable_hash_int("scientific_claims.measurement", world.seed,
                                           state.cohort, trial.id, trial.source_data))
        sigma = MEASUREMENT_NOISE * trial.control_output
        trial.observed_control = max(0., trial.control_output + rng.gauss(0., sigma))
        center = trial.control_output if state.uninformative_tests else trial.treatment_output
        trial.observed_treatment = max(0., center + rng.gauss(0., sigma))
        trial.informative = trial.control_output > 0. and trial.observed_control > 0.
        if trial.informative:
            trial.supports = ((trial.observed_treatment - trial.observed_control)
                              / trial.observed_control >= claim.threshold)
        trial.status = "completed"
        trial.resolved_turn = world.turn
        seat_name = world.scholarship.seats[trial.seat].name
        withheld = "; its result is withheld from institutional belief updates" if state.withhold_information else ""
        trial.event_id = _emit(world, events, "scientific_trial_completed", trial.seat,
                               f"{seat_name} completes paid trial #{trial.id} of {claim.recipe}, "
                               f"recording local test outputs of {trial.observed_control:.3f} and "
                               f"{trial.observed_treatment:.3f} grain{withheld}",
                               causes=(trial.funded_event_id,), payer=trial.payer).event_id
        if state.withhold_information:
            state.withheld_results += 1
        else:
            _record_receipt(world, EvidenceReceipt(seat=trial.seat, trial=trial.id,
                                                  received_turn=world.turn, sender=trial.seat), events)


def _receive(world, events=None) -> None:
    state = world.scientific_claims
    if not state.transmission_enabled:
        state.expired_messages += len(state.messages)
        state.messages = []
        return
    pending = []
    for msg in state.messages:
        if world.turn > msg.expires_turn:
            state.expired_messages += 1
            continue
        if world.turn < msg.delivery_turn:
            pending.append(msg)
            continue
        if _academy(world, msg.recipient) is None:
            state.expired_messages += 1
            continue
        if msg.kind == "proposal":
            if not any(p.seat == msg.recipient and p.claim == msg.record for p in state.proposals):
                state.proposals.append(ProposalReceipt(seat=msg.recipient, claim=msg.record,
                                                        received_turn=world.turn, hops=msg.hops))
        elif not state.withhold_information:
            if not any(r.seat == msg.recipient and r.trial == msg.record for r in state.receipts):
                _record_receipt(world, EvidenceReceipt(seat=msg.recipient, trial=msg.record,
                                                      received_turn=world.turn, sender=msg.sender,
                                                      hops=msg.hops), events)
    state.messages = pending


def _transmit(world) -> None:
    state = world.scientific_claims
    if not state.transmission_enabled:
        return
    seats = [(i, _academy(world, i)) for i in state.seat_ids]
    seats = [(i, s) for i, s in seats if s is not None]
    claims = {c.id: c for c in state.claims}
    trials = {t.id: t for t in state.trials}
    known = {("proposal", p.claim, p.seat) for p in state.proposals}
    known.update(("evidence", r.trial, r.seat) for r in state.receipts)
    known.update((m.kind, m.record, m.recipient) for m in state.messages)
    records = [("proposal", p.claim, p.seat, p.hops, claims[p.claim].proposed_turn)
               for p in state.proposals if p.received_turn <= world.turn
               and claims[p.claim].proposed_turn <= world.turn]
    if not state.withhold_information:
        records += [("evidence", r.trial, r.seat, r.hops, trials[r.trial].resolved_turn)
                    for r in state.receipts if r.received_turn <= world.turn
                    and _trial_available(trials[r.trial], world.turn)
                    and r.received_turn >= trials[r.trial].resolved_turn
                    and claims[trials[r.trial].claim].proposed_turn <= world.turn]
    for kind, record, sender, hops, published in sorted(records):
        source = _academy(world, sender)
        if source is None or hops >= MAX_HOPS or world.turn + 1 > published + DELIVERY_LIFETIME:
            continue
        adjacent = world.regions[source.region].adjacencies
        for recipient, seat in seats:
            key = (kind, record, recipient)
            if (recipient == sender or key in known
                    or world.regions[seat.region].name not in adjacent):
                continue
            state.messages.append(ScienceMessage(kind=kind, record=record, sender=sender,
                                                  recipient=recipient, sent_turn=world.turn,
                                                  delivery_turn=world.turn + 1,
                                                  expires_turn=published + DELIVERY_LIFETIME,
                                                  hops=hops + 1))
            known.add(key)


def tick_scientific_claims(world, acc=None) -> list:
    """Phase 10 after academy updates: finish, receive, fund, send, once/turn."""
    if not scientific_claims_active(world):
        return []
    state = world.scientific_claims
    plan = state.research_agendas
    if plan is not None:
        from chronicler.scientific_research import tick_research_agendas
        return tick_research_agendas(world, acc, plan)
    if state.last_tick_turn == world.turn:
        return []
    state.last_tick_turn = world.turn
    events = []
    for i, seat in enumerate(world.scholarship.seats):
        if len(state.seat_ids) >= MAX_SEATS:
            break
        if i not in state.seat_ids and _academy(world, i) is not None:
            state.seat_ids.append(i)
    _finish_trials(world, events)
    _receive(world, events)
    if not state.claims:
        for seat_id in state.seat_ids:
            ctx = _context(world, seat_id)
            if ctx is None:
                continue
            candidates = [ScientificClaim(id=k, recipe=recipe, origin_seat=seat_id,
                                          proposed_turn=world.turn, context=ctx)
                          for k, recipe in enumerate(RECIPES)]
            if not all(_applicable(world, seat_id, c) for c in candidates):
                continue
            state.started_turn = world.turn
            state.claims = candidates
            for claim in candidates:
                claim.event_id = _emit(world, events, "scientific_claim_proposed", seat_id,
                                       f"{world.scholarship.seats[seat_id].name} proposes claim #{claim.id}: "
                                       f"{claim.recipe} practice raises grain output by at least "
                                       f"{100 * claim.threshold:.0f}% under its recorded local protocol").event_id
            state.proposals = [ProposalReceipt(seat=seat_id, claim=c.id, received_turn=world.turn)
                               for c in candidates]
            break
    for claim in state.claims:
        if claim.proposed_turn > world.turn:
            continue
        originals = [t for t in state.trials if t.claim == claim.id and t.parent < 0]
        if not originals:
            if _applicable(world, claim.origin_seat, claim):
                _fund_trial(world, claim, claim.origin_seat, -1, acc, events)
            continue
        original = originals[0]
        if (world.turn < original.funded_turn + REPLICATION_LAG
                or any(t.claim == claim.id and t.parent >= 0 for t in state.trials)):
            continue
        for seat_id in state.seat_ids:
            if (seat_id != original.seat and _applicable(world, seat_id, claim)
                    and any(p.seat == seat_id and p.claim == claim.id and p.received_turn <= world.turn
                            for p in state.proposals)):
                _fund_trial(world, claim, seat_id, original.id, acc, events)
                break
    _transmit(world)
    return events


def _received_evidence(world, seat_id: int, claim: ScientificClaim):
    """Policy-visible receipts only, with duplicate source data removed."""
    state = world.scientific_claims
    if (state.withhold_information or claim.proposed_turn > world.turn
            or not _applicable(world, seat_id, claim)):
        return []
    trials = {t.id: t for t in state.trials}
    visible = []
    sources = set()
    for receipt in sorted(state.receipts, key=lambda r: (r.received_turn, r.trial)):
        if receipt.seat != seat_id or receipt.received_turn > world.turn:
            continue
        trial = trials.get(receipt.trial)
        if (trial is None or trial.claim != claim.id or not _trial_available(trial, world.turn)
                or receipt.received_turn < trial.resolved_turn
                or not trial.informative or trial.supports is None
                or not trial.source_data or not trial.dependence_group
                or trial.inputs.get("context") != claim.context.model_dump()
                or trial.source_data in sources):
            continue
        sources.add(trial.source_data)
        visible.append(receipt)
    return visible


def _received_groups(world, seat_id: int, claim: ScientificClaim):
    """Return policy-visible source groups and the last informative receipt."""
    trials = {t.id: t for t in world.scientific_claims.trials}
    receipts = _received_evidence(world, seat_id, claim)
    groups: dict[str, list[float]] = {}
    for receipt in receipts:
        trial = trials[receipt.trial]
        groups.setdefault(trial.dependence_group, []).append(float(trial.supports))
    return groups, receipts[-1].received_turn if receipts else None


def confidence(world, seat_id: int, claim_id: int) -> float:
    """Only received information, deduped source data and capped block weight."""
    if not scientific_claims_active(world):
        return 0.5
    plan = world.scientific_claims.research_agendas
    if plan is not None:
        from chronicler.scientific_research import confidence as research_confidence
        return research_confidence(world, seat_id, claim_id, plan)
    claim = next((c for c in world.scientific_claims.claims if c.id == claim_id), None)
    if claim is None:
        return 0.5
    groups, _ = _received_groups(world, seat_id, claim)
    support = sum(sum(values) / len(values) for values in groups.values())
    return (1. + support) / (2. + len(groups))


def prepare_adoption_effort(world, acc=None, *, events=None) -> dict[tuple[int, int], float]:
    """Phase 4 fixed paid effort; beliefs change allocation, not its budget.

    Returning the saved same-turn allocation is idempotent for the debit.
    Existing practice dynamics alone apply the grant and all their gates.
    """
    if not scientific_claims_active(world):
        return {}
    state = world.scientific_claims
    plan = state.research_agendas
    if plan is not None:
        from chronicler import scientific_research as research
        research.validate_state(world, plan)
    if state.last_effort_turn != world.turn:
        state.last_effort_turn = world.turn
        state.last_effort = []
        if (state.started_turn is not None and world.turn >= state.started_turn
                and (world.turn - state.started_turn) % EFFORT_CADENCE == 0):
            used_regions = set()
            for seat_id in state.seat_ids:
                seat = _academy(world, seat_id)
                if seat is None or seat.region in used_regions:
                    continue
                known = {p.claim for p in state.proposals if p.seat == seat_id
                         and p.received_turn <= world.turn}
                claims = [c for c in state.claims if c.id in known and c.proposed_turn <= world.turn
                          and _applicable(world, seat_id, c)]
                if plan is not None:
                    claims = research.policy_claims(world, seat_id, plan)
                if not claims:
                    continue
                used_regions.add(seat.region)
                if _pay(world, seat_id, EFFORT_COST, acc) < 0:
                    state.unfunded_effort += 1
                    continue
                state.effort_spent += EFFORT_COST
                beliefs = ([confidence(world, seat_id, c.id) for c in claims] if plan is None else
                           [research.confidence_from_evidence(world, seat_id, c) for c in claims])
                total = sum(beliefs)
                shares = {c.recipe: belief / total for c, belief in zip(claims, beliefs)}
                reported = state.reported_allocations.get(seat_id)
                changed = (reported is None or set(reported) != set(shares)
                           or any(abs(shares[k] - reported[k]) >= ALLOCATION_EVENT_DELTA for k in shares))
                allocation_id = ""
                if changed:
                    causes = [receipt.event_id for claim in claims
                              for receipt in _received_evidence(world, seat_id, claim)]
                    if not causes:
                        causes = [c.event_id for c in claims]
                    if plan is not None:
                        causes = research.allocation_causes(world, seat_id, claims, plan)
                    allocation_id = _emit(world, events, "scientific_adoption_allocated", seat_id,
                                           f"{seat.name} pays {EFFORT_COST} treasury unit for its fixed local "
                                           "adoption allowance: " + ", ".join(
                                               f"{100 * share:.0f}% to {recipe}" for recipe, share in shares.items()),
                                           causes=causes).event_id
                    state.reported_allocations[seat_id] = shares
                for i, (claim, belief) in enumerate(zip(claims, beliefs)):
                    effort = AdoptionEffort(seat=seat_id, region=seat.region,
                                            recipe=claim.recipe, share=belief / total,
                                            confidence=belief, paid=EFFORT_COST if i == 0 else 0,
                                            event_id=allocation_id)
                    if plan is not None:
                        effort._set_research_value(claim.id)
                    state.last_effort.append(effort)
    grants: dict[tuple[int, int], float] = {}
    used: dict[int, float] = {}
    for effort in state.last_effort:
        key = (effort.region, TECHNIQUE_INDEX[effort.recipe])
        prior = used.get(effort.region, 0.)
        amount = min(max(0., EFFORT_ALLOWANCE - prior), EFFORT_ALLOWANCE * effort.share)
        grants[key] = grants.get(key, 0.) + amount
        used[effort.region] = prior + amount
    return grants


def snapshot_summary(world) -> dict | None:
    if not scientific_claims_on(world):
        return None
    state = world.scientific_claims
    source_turn = world.turn - 1
    if source_turn < 0 or state.last_tick_turn != source_turn:
        return None
    plan = state.research_agendas
    if plan is not None:
        from chronicler.scientific_research import snapshot_summary as research_summary
        return research_summary(world, plan)
    active = scientific_claims_active(world)
    beliefs = []
    if active:
        view = _SummaryView(world, source_turn)
        for seat_id in state.seat_ids:
            seat = _academy(view, seat_id)
            if seat is None:
                continue
            region = world.regions[seat.region]
            for claim in state.claims:
                if claim.proposed_turn > source_turn or not any(
                        p.seat == seat_id and p.claim == claim.id and p.received_turn <= source_turn
                        for p in state.proposals):
                    continue
                # Context is evaluated at the completed turn, as it was for
                # that turn's policy. A view does not alter the real calendar.
                groups, last_date = _received_groups(view, seat_id, claim)
                visible = _received_evidence(view, seat_id, claim)
                support = sum(sum(v) / len(v) for v in groups.values())
                beliefs.append({"seat": seat_id, "seat_name": seat.name,
                                "region": seat.region, "region_name": region.name,
                                "owner": _payer(world, seat), "owner_name": region.controller,
                                "claim": claim.id, "confidence": (1. + support) / (2. + len(groups)),
                                "independent_groups": len(groups), "last_evidence_turn": last_date,
                                "last_evidence_event_id": visible[-1].event_id if visible else ""})
    result = {"source_turn": source_turn, "active": active, "seats": len(state.seat_ids),
            "claims": len(state.claims), "trials": len(state.trials),
            "completed": sum(t.status == "completed" for t in state.trials),
            "cancelled": state.cancelled, "failed": state.failed,
            "trial_spent": state.trial_spent, "effort_spent": state.effort_spent,
            "evidence_receipts": len(state.receipts), "pending_messages": len(state.messages),
            "expired_messages": state.expired_messages, "withheld_results": state.withheld_results,
            "controls": {"withhold_information": state.withhold_information,
                         "transmission_enabled": state.transmission_enabled,
                         "uninformative_tests": state.uninformative_tests},
            "propositions": [{"id": c.id, "recipe": c.recipe, "origin_seat": c.origin_seat,
                              "context": c.context.model_dump(), "threshold": c.threshold,
                              "proposed_turn": c.proposed_turn, "event_id": c.event_id}
                             for c in state.claims],
            "beliefs": beliefs[:MAX_SEATS * len(RECIPES)],
            "trials_resolved": [t.model_dump() for t in state.trials if t.resolved_turn == source_turn],
            "allocations": [e.model_dump() for e in state.last_effort]}
    rule = getattr(state, "publication_rule", LEGACY_PUBLICATION)
    if rule != LEGACY_PUBLICATION:
        result["publication_rule"] = rule
    return result


class _SummaryView:
    """Read the completed calendar without writing the live world turn."""
    def __init__(self, world, turn):
        self._world, self.turn = world, turn

    def __getattr__(self, name):
        return getattr(self._world, name)
