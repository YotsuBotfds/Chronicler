"""Explicit finite research agendas; legacy worlds never enter this module."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math

from chronicler import scientific_claims as C
from chronicler.scientific_claims_state import (
    MAX_CLAIMS, MAX_MESSAGES, MAX_SEATS, MAX_TRIALS, ProposalReceipt,
    ScienceMessage, ScientificClaim,
)
from chronicler.scientific_research_state import (
    FUNDING_WINDOW, MAX_CYCLES, OPENING_INTERVAL, ORIGINAL_WINDOW,
    ResearchAgendas, ResearchCycle, ResearchHostIdentity, ResearchSeatBirth,
)


def topic_key(claim):
    return (claim.recipe, tuple(sorted(claim.context.model_dump().items())), claim.metric,
            claim.threshold, claim.comparator, claim.intervention, claim.horizon)


def _cycle_for_trial(plan, trial_id):
    return next(cycle for cycle in plan.cycles if trial_id in cycle.trials)


def _audience(state, cycle):
    return state.seat_ids if cycle.legacy_adopted else cycle.participants


def _seat_birth(seat_id, seat):
    return ResearchSeatBirth(seat=seat_id, region=seat.region, kind=seat.kind,
        founded_turn=seat.founded_turn, founder=seat.founder, name=seat.name)


def _host_seal(world):
    """Deterministic source identity; no simulation RNG or process identities."""
    data = dict(rule="research-host-v1", seed=world.seed, activated_turn=world.turn,
        cohort=world.scientific_claims.cohort,
        births=[dict(seat=i, region=s.region, kind=s.kind, founded_turn=s.founded_turn,
                     founder=s.founder, name=s.name) for i, s in enumerate(world.scholarship.seats)])
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_host(world, plan, *, candidate_host=False, allow_absent_host=False):
    state = world.scientific_claims
    births = {birth.seat: birth for birth in plan.academy_births}
    if [birth.seat for birth in plan.academy_births] != state.seat_ids:
        raise ValueError("retained academy births do not match enrolled identities")
    if not C.scholarship_on(world):
        if allow_absent_host:
            return births
        raise ValueError("retained research requires its original scholarship registry")
    identity = world.scholarship.scientific_research_identity
    if not candidate_host and (identity is None or identity.seal != plan.host_seal):
        raise ValueError("scholarship registry does not match retained research host")
    for seat_id, birth in births.items():
        if not 0 <= seat_id < len(world.scholarship.seats) or birth != _seat_birth(
                seat_id, world.scholarship.seats[seat_id]):
            raise ValueError("enrolled academy birth changed beneath retained research")
    return births


def validate_state(world, plan=None, *, candidate_host=False, allow_absent_host=False):
    """Reject unsupported archives before any guard, money or state mutation."""
    state = world.scientific_claims
    plan = state.research_agendas if plan is None else plan
    if plan is None:
        raise ValueError("research archive validation requires explicit agenda state")
    ResearchAgendas.model_validate(plan, strict=True)
    try:
        births = _validate_host(world, plan, candidate_host=candidate_host,
                                allow_absent_host=allow_absent_host)
        for name in ("trial_spent", "effort_spent", "cancelled", "failed", "expired_messages",
                     "withheld_results", "unfunded_trials", "unfunded_effort"):
            if type(getattr(state, name)) is not int or getattr(state, name) < 0:
                raise ValueError("invalid research lifetime counter")
        if (any(type(getattr(state, name)) is not bool for name in
                ("withhold_information", "transmission_enabled", "uninformative_tests"))
                or state.publication_rule not in (C.LEGACY_PUBLICATION, C.FUNDED_CONTEXT_PUBLICATION)):
            raise ValueError("invalid research information or publication controls")
        if (any(type(getattr(state, name)) is not int or getattr(state, name) < -1
                for name in ("last_tick_turn", "last_effort_turn"))
                or state.started_turn is not None and type(state.started_turn) is not int):
            raise ValueError("invalid research guard or effort anchor")
        if plan.enabled_turn > world.turn or plan.blocked_turn is not None and plan.blocked_turn > world.turn:
            raise ValueError("future actual research activation or blocked date")
        if (state.last_tick_turn > world.turn or state.last_effort_turn > world.turn
                or state.started_turn is not None and not 0 <= state.started_turn <= world.turn):
            raise ValueError("research guards or effort anchor are ahead of the actual world")
        if (len(state.seat_ids) > MAX_SEATS or len(state.claims) > MAX_CLAIMS
                or len(state.trials) > MAX_TRIALS or len(state.proposals) > MAX_SEATS * MAX_CLAIMS
                or len(state.receipts) > MAX_SEATS * MAX_TRIALS or len(state.messages) > MAX_MESSAGES
                or len(state.last_effort) > MAX_SEATS * len(C.RECIPES)
                or len(state.reported_allocations) > MAX_SEATS):
            raise ValueError("retained research archive exceeds its row capacity")
        if len(set(state.seat_ids)) != len(state.seat_ids) or any(
                type(s) is not int or s not in births for s in state.seat_ids):
            raise ValueError("invalid retained academy identity")
        if [c.id for c in state.claims] != list(range(len(state.claims))):
            raise ValueError("canonical topic IDs must be append-only")
        if [t.id for t in state.trials] != list(range(len(state.trials))):
            raise ValueError("paid trial IDs must be append-only")
        keys = set()
        for claim in state.claims:
            if (claim.recipe not in C.RECIPES or claim.metric != "grain_output" or claim.threshold != .02
                    or claim.comparator != 0. or claim.intervention != 1. or claim.horizon != 1
                    or claim.context.crew != 4 or not 0 <= claim.proposed_turn <= world.turn
                    or claim.origin_seat not in state.seat_ids):
                raise ValueError("unsupported retained proposition protocol or identity")
            key = topic_key(claim)
            if key in keys:
                raise ValueError("duplicate canonical proposition")
            keys.add(key)
        claims = {c.id: c for c in state.claims}
        trials = {t.id: t for t in state.trials}
        membership = [tid for cycle in plan.cycles for tid in cycle.trials]
        if sorted(membership) != list(trials) or len(membership) != len(set(membership)):
            raise ValueError("every retained trial must belong to exactly one agenda")
        if sum(cycle.closed_turn is None for cycle in plan.cycles) > 1:
            raise ValueError("multiple research agendas are open for funding")
        previous_cycle = None
        for cycle in plan.cycles:
            if (cycle.origin_seat not in state.seat_ids or any(s not in state.seat_ids for s in cycle.participants)
                    or any(cid not in claims for cid in cycle.claims)
                    or {claims[cid].recipe for cid in cycle.claims} != set(C.RECIPES)
                    or len({tuple(sorted(claims[cid].context.model_dump().items())) for cid in cycle.claims}) != 1
                    or cycle.opened_turn is not None and cycle.opened_turn > world.turn
                    or cycle.closed_turn is not None and cycle.closed_turn > world.turn):
                raise ValueError("invalid agenda participants, topics or actual dates")
            if cycle.legacy_adopted and (cycle.id != 0 or cycle.opening_roster_complete):
                raise ValueError("legacy opening participants are not retrospectively known")
            if cycle.legacy_adopted and cycle.closed_turn != plan.enabled_turn:
                raise ValueError("adopted legacy funding closes only at actual activation")
            if previous_cycle is not None and (previous_cycle.closed_turn is None
                    or previous_cycle.closed_turn > cycle.opened_turn):
                raise ValueError("agenda funding windows overlap in recorded history")
            if not cycle.legacy_adopted:
                earliest = (plan.enabled_turn + OPENING_INTERVAL if previous_cycle is not None
                    and previous_cycle.legacy_adopted else previous_cycle.opened_turn + OPENING_INTERVAL
                    if previous_cycle is not None else plan.enabled_turn)
                if cycle.opened_turn < earliest:
                    raise ValueError("agenda opened before its actual earliest opening")
            previous_cycle = cycle
            for tid in cycle.trials:
                trial = trials[tid]
                if trial.claim not in cycle.claims:
                    raise ValueError("trial has a topic outside its agenda")
                if not cycle.legacy_adopted and trial.seat not in cycle.participants:
                    raise ValueError("trial institution is outside its frozen agenda")
                if trial.parent >= 0 and (trial.parent not in cycle.trials
                        or trials[trial.parent].parent >= 0 or trials[trial.parent].claim != trial.claim):
                    raise ValueError("replication parent must be an original in the same agenda")
                if trial.parent >= 0 and (trial.seat == trials[trial.parent].seat
                        or trial.funded_turn < trials[trial.parent].funded_turn + C.REPLICATION_LAG
                        or not any(p.seat == trial.seat and p.claim == trial.claim
                            and p.agenda_id == cycle.id and p.received_turn <= trial.funded_turn
                            for p in state.proposals)):
                    raise ValueError("replication preceded its lag or actual agenda question")
                if not cycle.legacy_adopted:
                    if not cycle.opened_turn <= trial.funded_turn < cycle.opened_turn + FUNDING_WINDOW:
                        raise ValueError("trial was funded outside its agenda window")
                    if trial.parent < 0 and (trial.seat != cycle.origin_seat
                            or trial.funded_turn >= cycle.opened_turn + ORIGINAL_WINDOW):
                        raise ValueError("original was funded outside its origin or original window")
            for cid in cycle.claims:
                rows = [trials[tid] for tid in cycle.trials if trials[tid].claim == cid]
                if sum(t.parent < 0 for t in rows) > 1 or sum(t.parent >= 0 for t in rows) > 1:
                    raise ValueError("agenda repeats an original or replication slot")
        if plan.cycles:
            last = plan.cycles[-1]
            earliest = plan.enabled_turn + OPENING_INTERVAL if last.legacy_adopted else last.opened_turn + OPENING_INTERVAL
            if plan.next_open_turn < earliest:
                raise ValueError("next agenda opening plan violates the minimum interval")
        elif plan.next_open_turn < plan.enabled_turn:
            raise ValueError("first opening plan precedes activation")
        for trial in state.trials:
            if (trial.claim not in claims or trial.seat not in state.seat_ids
                    or trial.status not in ("running", "completed", "cancelled", "failed")
                    or not 0 <= trial.payer < len(world.civilizations) or trial.cost != C.TRIAL_COST
                    or not claims[trial.claim].proposed_turn <= trial.funded_turn <= world.turn
                    or trial.completion_turn <= trial.funded_turn):
                raise ValueError("invalid paid trial identity, expense or planning date")
            if trial.status == "running":
                if trial.resolved_turn is not None:
                    raise ValueError("running trial has a terminal date")
            elif (trial.resolved_turn is None or not trial.funded_turn <= trial.resolved_turn <= world.turn
                  or (trial.resolved_turn < trial.completion_turn and not (
                      trial.status == "failed" and trial.resolved_turn == trial.funded_turn))):
                raise ValueError("invalid terminal trial chronology")
        if (state.trial_spent != sum(t.cost for t in state.trials)
                or state.cancelled != sum(t.status == "cancelled" for t in state.trials)
                or state.failed != sum(t.status == "failed" for t in state.trials)):
            raise ValueError("retained research expense or terminal counters disagree")
        allocation_keys, region_seats, payments, shares = set(), {}, Counter(), Counter()
        for allocation in state.last_effort:
            if (type(allocation.seat) is not int or allocation.seat not in state.seat_ids or type(allocation.region) is not int
                    or not 0 <= allocation.region < len(world.regions)
                    or allocation.region != births[allocation.seat].region
                    or allocation.recipe not in C.RECIPES
                    or type(allocation.paid) is not int or allocation.paid not in (0, 1)
                    or any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
                           for value in (allocation.share, allocation.confidence))):
                raise ValueError("invalid retained paid allocation")
            key = (allocation.seat, allocation.recipe)
            if key in allocation_keys or allocation.region in region_seats and region_seats[allocation.region] != allocation.seat:
                raise ValueError("duplicate recipe vote or regional paid allowance")
            allocation_keys.add(key)
            region_seats[allocation.region] = allocation.seat
            payments[allocation.seat] += allocation.paid
            shares[allocation.seat] += allocation.share
            cid = allocation.claim_id
            if cid is not None and (cid not in claims or claims[cid].recipe != allocation.recipe):
                raise ValueError("paid allocation references the wrong canonical topic")
            if cid is None and state.last_effort_turn >= plan.enabled_turn and not (
                    plan.cycles and plan.cycles[0].legacy_adopted and state.last_effort_turn == plan.enabled_turn):
                raise ValueError("new agenda-mode payment lacks its actual canonical topic")
        if any(payments[seat] != 1 or not math.isclose(share, 1., rel_tol=1e-8, abs_tol=1e-7)
               for seat, share in shares.items()) or state.effort_spent < sum(payments.values()):
            raise ValueError("retained allocation shares or current payment totals disagree")
        for seat, reported in state.reported_allocations.items():
            if (type(seat) is not int or seat not in state.seat_ids or not isinstance(reported, dict)
                    or not reported or any(recipe not in C.RECIPES or type(share) not in (int, float)
                        or not math.isfinite(share) or not 0 <= share <= 1 for recipe, share in reported.items())
                    or not math.isclose(sum(reported.values()), 1., rel_tol=1e-8, abs_tol=1e-7)):
                raise ValueError("invalid retained reported allocation split")
        proposal_keys, receipt_keys = set(), set()
        for proposal in state.proposals:
            if proposal.agenda_id >= len(plan.cycles):
                raise ValueError("proposal references an unknown agenda")
            cycle = plan.cycles[proposal.agenda_id]
            key = (proposal.agenda_id, proposal.claim, proposal.seat)
            if (key in proposal_keys or proposal.claim not in cycle.claims or proposal.seat not in state.seat_ids
                    or not claims[proposal.claim].proposed_turn <= proposal.received_turn <= world.turn
                    or not cycle.legacy_adopted and (proposal.seat not in cycle.participants
                        or proposal.received_turn < cycle.opened_turn)):
                raise ValueError("invalid or relabelled proposal receipt")
            proposal_keys.add(key)
        for receipt in state.receipts:
            trial = trials.get(receipt.trial)
            key = (receipt.seat, receipt.trial)
            if (key in receipt_keys or trial is None or not C._trial_available(trial, world.turn)
                    or receipt.seat not in state.seat_ids or receipt.sender not in state.seat_ids
                    or not trial.resolved_turn <= receipt.received_turn <= world.turn
                    or receipt.seat not in _audience(state, _cycle_for_trial(plan, trial.id))):
                raise ValueError("invalid retained evidence receipt")
            receipt_keys.add(key)
        message_keys = set()
        for msg in state.messages:
            msg._research_value()
            key = (msg.kind, msg.record, msg.recipient, msg.agenda_id if msg.kind == "proposal" else None)
            if key in message_keys:
                raise ValueError("duplicate pending research delivery")
            message_keys.add(key)
            if (msg.kind not in ("proposal", "evidence") or msg.sender not in state.seat_ids
                    or msg.recipient not in state.seat_ids or not 0 <= msg.sent_turn <= world.turn
                    or msg.delivery_turn != msg.sent_turn + 1 or not 1 <= msg.hops <= C.MAX_HOPS):
                raise ValueError("invalid pending research message")
            if msg.kind == "proposal":
                if msg.agenda_id >= len(plan.cycles):
                    raise ValueError("message references an unknown agenda")
                cycle = plan.cycles[msg.agenda_id]
                if msg.record not in cycle.claims:
                    raise ValueError("message topic is outside its agenda")
                if not any(p.seat == msg.sender and p.claim == msg.record and p.agenda_id == msg.agenda_id
                           and p.received_turn <= msg.sent_turn for p in state.proposals):
                    raise ValueError("proposal was relayed before its actual receipt")
                published = claims[msg.record].proposed_turn if cycle.legacy_adopted else cycle.opened_turn
            else:
                trial = trials.get(msg.record)
                if trial is None or not C._trial_available(trial, msg.sent_turn):
                    raise ValueError("message precedes actual evidence publication")
                if not any(r.seat == msg.sender and r.trial == msg.record and r.received_turn <= msg.sent_turn
                           for r in state.receipts):
                    raise ValueError("evidence was relayed before its actual receipt")
                cycle, published = _cycle_for_trial(plan, trial.id), trial.resolved_turn
            if (msg.recipient not in _audience(state, cycle) or msg.expires_turn != published + C.DELIVERY_LIFETIME
                    or not published <= msg.sent_turn < msg.delivery_turn <= msg.expires_turn):
                raise ValueError("message expiry or frozen recipients changed")
    except (AttributeError, KeyError, TypeError, StopIteration) as exc:
        raise ValueError("unsupported or incomplete retained research archive") from exc
    return plan


def capacities(world, plan):
    state = world.scientific_claims
    proposals = Counter(p.agenda_id for p in state.proposals)
    receipts = Counter(r.trial for r in state.receipts)
    reserved_trials = reserved_proposals = reserved_receipts = 0
    for cycle in plan.cycles:
        audience = MAX_SEATS if cycle.legacy_adopted else len(cycle.participants)
        if cycle.closed_turn is None:
            unpaid = 4 - len(cycle.trials)
            reserved_trials += unpaid
            reserved_receipts += unpaid * audience
        if cycle.opened_turn is not None and world.turn <= cycle.opened_turn + C.DELIVERY_LIFETIME:
            reserved_proposals += max(0, 2 * audience - proposals[cycle.id])
        for tid in cycle.trials:
            trial = state.trials[tid]
            published = any(r.trial == tid for r in state.receipts) or any(
                m.kind == "evidence" and m.record == tid for m in state.messages)
            if trial.status == "running" or (trial.status == "completed" and published
                    and world.turn <= trial.resolved_turn + C.DELIVERY_LIFETIME):
                reserved_receipts += max(0, audience - receipts[tid])
    owed_messages = reserved_proposals + reserved_receipts
    live_pending = sum(msg.expires_turn >= world.turn for msg in state.messages)
    return {"topics": {"used": len(state.claims), "reserved": 0, "limit": MAX_CLAIMS},
        "trials": {"used": len(state.trials), "reserved": reserved_trials, "limit": MAX_TRIALS},
        "proposals": {"used": len(state.proposals), "reserved": reserved_proposals, "limit": MAX_SEATS * MAX_CLAIMS},
        "receipts": {"used": len(state.receipts), "reserved": reserved_receipts, "limit": MAX_SEATS * MAX_TRIALS},
        "messages": {"used": len(state.messages), "reserved": max(0, owed_messages - live_pending), "limit": MAX_MESSAGES},
        "cycles": {"used": len(plan.cycles), "reserved": 0, "limit": MAX_CYCLES},
        "seats": {"used": len(state.seat_ids), "reserved": 0, "limit": MAX_SEATS}}


def set_research_agendas_enabled(world, enabled: bool):
    """Internal explicit activation/pause API; never discards retained data."""
    if type(enabled) is not bool:
        raise ValueError("research agenda switch must be a boolean")
    state = getattr(world, "scientific_claims", None)
    if not enabled and (state is None or state.research_agendas is None):
        return
    if state is None:
        raise ValueError("research agendas require enabled science, scholarship and techniques")
    plan = state.research_agendas
    if plan is not None:
        validate_state(world, plan, allow_absent_host=not enabled)
        if enabled and not C.scientific_claims_active(world):
            raise ValueError("research agendas require enabled science, scholarship and techniques")
        plan.enabled = enabled
        return
    if not C.scientific_claims_active(world):
        raise ValueError("research agendas require enabled science, scholarship and techniques")
    cycles = []
    if state.claims:
        if len(state.claims) != 2:
            raise ValueError("unsupported legacy pilot topic archive")
        cycles.append(ResearchCycle(id=0, legacy_adopted=True, opening_roster_complete=False,
            opened_turn=state.started_turn, origin_seat=state.claims[0].origin_seat,
            participants=list(state.seat_ids), claims=[claim.id for claim in state.claims],
            trials=[trial.id for trial in state.trials], announcement_event_id="", closed_turn=world.turn,
            close_reason="legacy funding closed prospectively at activation", unfunded_originals=[],
            unfunded_replications=[], slot_reasons={}))
    plan = ResearchAgendas(schema_version=1, rule="finite-retained-v1", enabled=True,
        enabled_turn=world.turn, next_open_turn=world.turn + OPENING_INTERVAL if cycles else world.turn,
        origin_cursor=cycles[0].origin_seat if cycles else -1, cycles=cycles, blocked_reason="", blocked_turn=None,
        host_seal=_host_seal(world), academy_births=[_seat_birth(i, world.scholarship.seats[i])
                                                  for i in state.seat_ids])
    validate_state(world, plan, candidate_host=True)
    identity = ResearchHostIdentity(schema_version=1, seal=plan.host_seal)
    world.scholarship._set_research_value(identity)
    state._set_research_value(plan)


def policy_claims(world, seat_id, plan):
    state = world.scientific_claims
    known = {p.claim for p in state.proposals if p.seat == seat_id and p.received_turn <= world.turn}
    selected = [claim for claim in state.claims if claim.id in known
                and claim.proposed_turn <= world.turn and C._applicable(world, seat_id, claim)]
    if len({claim.recipe for claim in selected}) != len(selected):
        raise ValueError("multiple canonical questions would vote for one recipe")
    return selected


def confidence(world, seat_id, claim_id, plan):
    validate_state(world, plan)
    claim = next((c for c in policy_claims(world, seat_id, plan) if c.id == claim_id), None)
    if claim is None:
        return .5
    return confidence_from_evidence(world, seat_id, claim)


def confidence_from_evidence(world, seat_id, claim):
    groups, _ = C._received_groups(world, seat_id, claim)
    return (1. + sum(sum(values) / len(values) for values in groups.values())) / (2. + len(groups))


def allocation_causes(world, seat_id, claims, plan):
    """Cite the actual local question announcement and evidence used now."""
    causes = []
    for claim in claims:
        known = [p for p in world.scientific_claims.proposals if p.seat == seat_id
                 and p.claim == claim.id and p.received_turn <= world.turn]
        latest = max(known, key=lambda p: (p.received_turn, p.agenda_id))
        announcement = plan.cycles[latest.agenda_id].announcement_event_id
        causes.append(announcement or claim.event_id)
        causes.extend(receipt.event_id for receipt in C._received_evidence(world, seat_id, claim))
    return causes


def _block(world, plan, reason, events):
    if plan.blocked_reason != reason:
        plan.blocked_reason, plan.blocked_turn = reason, world.turn
        if reason.endswith("_capacity") and plan.cycles:
            C._emit(world, events, "scientific_research_capacity_blocked", plan.cycles[-1].origin_seat,
                    f"New paid research is blocked by retained {reason.removesuffix('_capacity')} capacity; old evidence remains retained")


def _close(world, cycle, reason, events):
    if cycle.closed_turn is not None:
        return
    trials = [world.scientific_claims.trials[tid] for tid in cycle.trials]
    for cid in cycle.claims:
        original = next((t for t in trials if t.claim == cid and t.parent < 0), None)
        if original is None:
            cycle.unfunded_originals.append(cid)
            cycle.slot_reasons.setdefault(f"original:{cid}", reason)
        if not any(t.claim == cid and t.parent >= 0 for t in trials):
            cycle.unfunded_replications.append(cid)
            cycle.slot_reasons.setdefault(f"replication:{cid}", "original_not_funded" if original is None else reason)
    cycle.closed_turn, cycle.close_reason = world.turn, reason
    C._emit(world, events, "scientific_research_agenda_closed", cycle.origin_seat,
            f"Research agenda #{cycle.id} closes to new funding: {reason}; paid work and received evidence remain retained",
            causes=(cycle.announcement_event_id,))


def _candidate(world, plan):
    state = world.scientific_claims
    order = sorted(state.seat_ids, key=lambda seat: (seat <= plan.origin_cursor, seat))
    for seat in order:
        context = C._context(world, seat)
        if context is None:
            continue
        questions = [ScientificClaim(id=0, recipe=recipe, origin_seat=seat,
            proposed_turn=world.turn, context=context) for recipe in C.RECIPES]
        if all(C._applicable(world, seat, claim) for claim in questions):
            return seat, questions
    return None


def _open(world, plan, events):
    if len(plan.cycles) >= MAX_CYCLES:
        _block(world, plan, "cycle_capacity", events)
        return
    candidate = _candidate(world, plan)
    if candidate is None:
        _block(world, plan, "no_eligible_academy", events)
        return
    seat, questions = candidate
    state = world.scientific_claims
    participants = [sid for sid in state.seat_ids if C._academy(world, sid) is not None]
    existing = {topic_key(claim): claim for claim in state.claims}
    needed = sum(topic_key(claim) not in existing for claim in questions)
    requested = dict(topics=needed, trials=4, proposals=2 * len(participants),
                     receipts=4 * len(participants), messages=6 * len(participants), cycles=1)
    capacity = capacities(world, plan)
    for name, extra in requested.items():
        row = capacity[name]
        if row["used"] + row["reserved"] + extra > row["limit"]:
            _block(world, plan, name.removesuffix("s") + "_capacity", events)
            return
    claims = []
    for question in questions:
        claim = existing.get(topic_key(question))
        if claim is None:
            question.id = len(state.claims)
            state.claims.append(question)
            question.event_id = C._emit(world, events, "scientific_claim_proposed", seat,
                f"{world.scholarship.seats[seat].name} proposes claim #{question.id}: {question.recipe} practice raises grain output by at least 2% under its recorded local protocol").event_id
            claim = question
        claims.append(claim.id)
    cycle = ResearchCycle(id=len(plan.cycles), legacy_adopted=False, opening_roster_complete=True,
        opened_turn=world.turn, origin_seat=seat, participants=participants, claims=claims, trials=[],
        announcement_event_id="", closed_turn=None, close_reason="", unfunded_originals=[],
        unfunded_replications=[], slot_reasons={})
    cycle.announcement_event_id = C._emit(world, events, "scientific_research_agenda_opened", seat,
        f"{world.scholarship.seats[seat].name} opens paid research agenda #{cycle.id} for contextual claims {claims}",
        causes=tuple(state.claims[cid].event_id for cid in claims)).event_id
    plan.cycles.append(cycle)
    plan.next_open_turn, plan.origin_cursor = world.turn + OPENING_INTERVAL, seat
    plan.blocked_reason, plan.blocked_turn = "", None
    if state.started_turn is None and not any(cycle.legacy_adopted for cycle in plan.cycles):
        state.started_turn = world.turn
    for cid in claims:
        receipt = ProposalReceipt(seat=seat, claim=cid, received_turn=world.turn)
        receipt._set_research_value(cycle.id)
        state.proposals.append(receipt)


def _fund(world, plan, cycle, acc, events):
    state = world.scientific_claims
    age = world.turn - cycle.opened_turn
    for cid in cycle.claims:
        claim = state.claims[cid]
        rows = [state.trials[tid] for tid in cycle.trials if state.trials[tid].claim == cid]
        original = next((trial for trial in rows if trial.parent < 0), None)
        if original is None:
            if age >= ORIGINAL_WINDOW:
                continue
            seat, parent, slot = cycle.origin_seat, -1, f"original:{cid}"
            if not C._applicable(world, seat, claim):
                cycle.slot_reasons[slot] = "registered_context_or_access_unavailable"
                continue
        else:
            if world.turn < original.funded_turn + C.REPLICATION_LAG or any(t.parent >= 0 for t in rows):
                continue
            slot = f"replication:{cid}"
            candidates = [seat for seat in cycle.participants if seat != original.seat
                and C._applicable(world, seat, claim) and any(p.seat == seat and p.claim == cid
                    and p.agenda_id == cycle.id and p.received_turn <= world.turn for p in state.proposals)]
            if not candidates:
                cycle.slot_reasons[slot] = "no_eligible_received_question"
                continue
            seat, parent = candidates[0], original.id
        capacity = capacities(world, plan)
        if any(row["used"] + row["reserved"] > row["limit"] for row in capacity.values()):
            _block(world, plan, "reserved_record_capacity", events)
            continue
        before = len(state.trials)
        C._fund_trial(world, claim, seat, parent, acc, events, research_cycle=cycle)
        if len(state.trials) == before:
            cycle.slot_reasons[slot] = "projected_treasury_floor"
        else:
            cycle.slot_reasons.pop(slot, None)


def _receive(world, plan, events):
    state = world.scientific_claims
    if not state.transmission_enabled:
        state.expired_messages += len(state.messages)
        state.messages = []
        return
    pending = []
    for msg in state.messages:
        if world.turn > msg.expires_turn:
            state.expired_messages += 1
        elif world.turn < msg.delivery_turn:
            pending.append(msg)
        elif C._academy(world, msg.recipient) is None:
            state.expired_messages += 1
        elif msg.kind == "proposal":
            if not any(p.seat == msg.recipient and p.claim == msg.record and p.agenda_id == msg.agenda_id
                       for p in state.proposals):
                receipt = ProposalReceipt(seat=msg.recipient, claim=msg.record,
                    received_turn=world.turn, hops=msg.hops)
                receipt._set_research_value(msg.agenda_id)
                state.proposals.append(receipt)
        elif not state.withhold_information and not any(r.seat == msg.recipient and r.trial == msg.record for r in state.receipts):
            from chronicler.scientific_claims_state import EvidenceReceipt
            C._record_receipt(world, EvidenceReceipt(seat=msg.recipient, trial=msg.record,
                received_turn=world.turn, sender=msg.sender, hops=msg.hops), events)
    state.messages = pending


def _transmit(world, plan):
    state = world.scientific_claims
    if not state.transmission_enabled:
        return
    known = {("proposal", p.claim, p.seat, p.agenda_id) for p in state.proposals}
    known.update(("evidence", r.trial, r.seat, None) for r in state.receipts)
    known.update((m.kind, m.record, m.recipient, m.agenda_id if m.kind == "proposal" else None) for m in state.messages)
    records = []
    for receipt in state.proposals:
        cycle = plan.cycles[receipt.agenda_id]
        published = state.claims[receipt.claim].proposed_turn if cycle.legacy_adopted else cycle.opened_turn
        if receipt.received_turn <= world.turn:
            records.append(("proposal", receipt.claim, receipt.seat, receipt.hops, published, cycle.id))
    if not state.withhold_information:
        for receipt in state.receipts:
            trial = state.trials[receipt.trial]
            if receipt.received_turn <= world.turn and C._trial_available(trial, world.turn):
                records.append(("evidence", trial.id, receipt.seat, receipt.hops, trial.resolved_turn,
                                _cycle_for_trial(plan, trial.id).id))
    for kind, record, sender, hops, published, cycle_id in sorted(records):
        seat = C._academy(world, sender)
        if seat is None or hops >= C.MAX_HOPS or world.turn + 1 > published + C.DELIVERY_LIFETIME:
            continue
        adjacent = world.regions[seat.region].adjacencies
        for recipient in _audience(state, plan.cycles[cycle_id]):
            key = (kind, record, recipient, cycle_id if kind == "proposal" else None)
            destination = C._academy(world, recipient)
            if (recipient == sender or key in known or destination is None
                    or world.regions[destination.region].name not in adjacent):
                continue
            msg = ScienceMessage(kind=kind, record=record, sender=sender, recipient=recipient,
                sent_turn=world.turn, delivery_turn=world.turn + 1,
                expires_turn=published + C.DELIVERY_LIFETIME, hops=hops + 1)
            if kind == "proposal":
                msg._set_research_value(cycle_id)
            state.messages.append(msg)
            known.add(key)


def tick_research_agendas(world, acc, plan):
    validate_state(world, plan)
    state = world.scientific_claims
    if state.last_tick_turn == world.turn:
        return []
    state.last_tick_turn = world.turn
    events = []
    for seat in range(len(world.scholarship.seats)):
        if len(state.seat_ids) >= MAX_SEATS:
            break
        if seat not in state.seat_ids and C._academy(world, seat) is not None:
            birth = _seat_birth(seat, world.scholarship.seats[seat])
            state.seat_ids.append(seat)
            plan.academy_births.append(birth)
    C._finish_trials(world, events)
    _receive(world, plan, events)
    for cycle in plan.cycles:
        if cycle.closed_turn is None and (not plan.enabled or world.turn >= cycle.opened_turn + FUNDING_WINDOW):
            _close(world, cycle, "research_paused" if not plan.enabled else "funding_window_elapsed", events)
    if plan.enabled:
        if not any(c.closed_turn is None for c in plan.cycles) and world.turn >= plan.next_open_turn:
            _open(world, plan, events)
        for cycle in plan.cycles:
            if cycle.closed_turn is None:
                _fund(world, plan, cycle, acc, events)
    _transmit(world, plan)
    validate_state(world, plan)
    return events


def snapshot_summary(world, plan):
    state = world.scientific_claims
    source = world.turn - 1
    if (plan.enabled_turn > source or state.last_effort_turn > source
            or not C.scientific_claims_active(world)):
        return None
    view = C._SummaryView(world, source)
    validate_state(view, plan)
    beliefs = []
    for seat_id in state.seat_ids:
        seat = C._academy(view, seat_id)
        if seat is None:
            continue
        region = world.regions[seat.region]
        for claim in policy_claims(view, seat_id, plan):
            groups, last = C._received_groups(view, seat_id, claim)
            visible = C._received_evidence(view, seat_id, claim)
            beliefs.append(dict(seat=seat_id, seat_name=seat.name, region=seat.region, region_name=region.name,
                owner=C._payer(world, seat), owner_name=region.controller, claim=claim.id,
                confidence=confidence_from_evidence(view, seat_id, claim), independent_groups=len(groups),
                last_evidence_turn=last, last_evidence_event_id=visible[-1].event_id if visible else ""))
    if len(beliefs) > MAX_SEATS * len(C.RECIPES):
        raise ValueError("current canonical policy rows exceed the declared bound")
    cycle_rows = []
    for cycle in plan.cycles:
        row = cycle.model_dump(mode="json")
        row.update(original_deadline=None if cycle.legacy_adopted else cycle.opened_turn + ORIGINAL_WINDOW - 1,
            funding_deadline=None if cycle.legacy_adopted else cycle.opened_turn + FUNDING_WINDOW - 1,
            next_open_not_before=None if cycle.legacy_adopted else cycle.opened_turn + OPENING_INTERVAL,
            opening_roster_scope="observed_at_legacy_activation" if cycle.legacy_adopted else "frozen_at_actual_opening")
        cycle_rows.append(row)
    from chronicler.resources import get_season_id
    research = dict(schema_version=1, rule=plan.rule, enabled=plan.enabled, enabled_turn=plan.enabled_turn,
        current_cycle_id=next((cycle.id for cycle in plan.cycles if cycle.closed_turn is None), None),
        next_open_turn=plan.next_open_turn, opening_interval=OPENING_INTERVAL, funding_window=FUNDING_WINDOW,
        original_window=ORIGINAL_WINDOW, effort_started_turn=state.started_turn, effort_cadence=C.EFFORT_CADENCE,
        paid_use_seasons=sorted({get_season_id(state.started_turn + k * C.EFFORT_CADENCE) for k in (0, 1)})
            if state.started_turn is not None else [], origin_cursor=plan.origin_cursor,
        blocked_reason=plan.blocked_reason, blocked_turn=plan.blocked_turn, capacity=capacities(view, plan),
        archive=dict(retained_topics=len(state.claims), retained_trials=len(state.trials),
            retained_proposals=len(state.proposals), retained_receipts=len(state.receipts), raw_records_retained=True,
            trial_details_scope="resolved_this_source_turn_only", historical_export_completeness="not_inferred"),
        cycles=cycle_rows)
    result = dict(source_turn=source, active=True, seats=len(state.seat_ids), claims=len(state.claims),
        trials=len(state.trials), completed=sum(trial.status == "completed" for trial in state.trials),
        cancelled=state.cancelled, failed=state.failed, trial_spent=state.trial_spent, effort_spent=state.effort_spent,
        evidence_receipts=len(state.receipts), pending_messages=len(state.messages), expired_messages=state.expired_messages,
        withheld_results=state.withheld_results, controls=dict(withhold_information=state.withhold_information,
            transmission_enabled=state.transmission_enabled, uninformative_tests=state.uninformative_tests),
        propositions=[dict(id=c.id, recipe=c.recipe, origin_seat=c.origin_seat, context=c.context.model_dump(),
            threshold=c.threshold, proposed_turn=c.proposed_turn, event_id=c.event_id, metric=c.metric,
            comparator=c.comparator, intervention=c.intervention, horizon=c.horizon) for c in state.claims],
        beliefs=beliefs, trials_resolved=[trial.model_dump(mode="json") for trial in state.trials if trial.resolved_turn == source],
        allocations=[row.model_dump(mode="json") for row in state.last_effort]
            if state.last_effort_turn == source else [], research_agendas=research)
    if state.publication_rule != C.LEGACY_PUBLICATION:
        result["publication_rule"] = state.publication_rule
    return result
