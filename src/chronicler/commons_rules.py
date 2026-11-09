"""L8: commons rules with enforceable costs on the L3 timber stock (default off).

``--commons-rules`` (requires ``--timber-stock``; see
:mod:`chronicler.livelihoods`). The controller of a region (the civilization
at index ``owner`` in ``world.civilizations``) may adopt one explicit rule on
a harvested timber slot: a **harvest quota with a rest period**, enforced by
wardens it pays for. Everything below is a declared modeling choice, not a
calibration. docs/integration/commons-rules.md.

Knowledge. Every decision reads only the owner's dated, local observation:
the timber stock's account settled in the previous turn's Phase 2 (stock,
cover-implied capacity, extraction, water gate), never the current opening
stock or a future yield. Without a fresh account a rule keeps its last one.

Adoption (Phase 2, before the native economy tick, deterministic in (region,
slot) order). The controller adopts a rule on a timber slot that has no rule
and no repeal cooldown when its observation shows a harvest (extraction > 0:
its subjects take wood from it) and a depleted stand (stock below
``ADOPT_BELOW`` of capacity), and only if its projected treasury, after every
other pending Phase 2 bill, can pay the first turn's administration in full.

Rule. While the observed stock is below ``REST_BELOW`` of capacity the stand
rests (quota 0) until it is back at ``REOPEN_AT``; otherwise the quota is
``QUOTA_SHARE`` times the stand's regrowth at the observed stock, taken at
most at the stock of maximum growth (harvest no more than the stand grows;
zero while the observed water gate is closed).

Enforcement. Each turn a rule needs ``ADMIN_COST`` coins of wardens. A
controller holding an enacted Commons Management institution supplies the
share ``legitimacy x this turn's institution funding ratio`` from the
enforcement governance already paid; its treasury is billed the rest (whole
coins, rounded up). The bill is planned before the native tick against the
projected treasury after pending grain-storage and workshop bills (never the
same coins twice) and charged once after the tick succeeded, as a disclosed
public cost (accumulator ``keep``); a failed tick charges nothing. A short
treasury pays what it can. ``coverage = min(1, share + paid / ADMIN_COST)``,
and the limit offered to the economy is ``coverage x quota + (1 - coverage) x
stock cap``: uncovered extraction is open access up to the standing stock. In
``enforced`` mode a limit below the stock cap lowers the native
``timber_harvest_cap_{slot}`` through :func:`chronicler.timber_stock.tighten_harvest_caps`.
``cost_only`` (the cost-retaining control) adopts, plans, pays and records
everything identically but never lowers the cap; its receipts record the
harvest above the limit the rule would have applied (``excess``).

Repeal. A rule is repealed when its observation shows the stand recovered
(``REPEAL_AT`` of capacity), after ``UNFUNDED_LIMIT`` consecutive turns
without any coverage or ``IDLE_LIMIT`` turns in which nobody could harvest
(no farmers or no timber yield), or when its region's city is at the revolt threshold
(``cities.REVOLT_UNREST``) after the rule added grievance there; a repealed
slot has a ``COOLDOWN_TURNS`` cooldown. A rule lapses, without cooldown, when
its region changes controller (the new controller decides afresh with its own
treasury; no bill is inherited) or the slot is no longer timber.

Conflict. When an enforced rule binds (the harvest reached a lowered limit;
a zero limit binds where farmers could have harvested), the region's largest
open city, the existing carrier of local grievance (``cities``), gains
``RULE_GRIEVANCE``, never raising it above ``GRIEVANCE_CEILING`` through this
channel; the city's unrest, revolts and concessions then follow the existing
mechanism. Nothing else (stability, factions, movements) is touched, and
hunger keeps its own city channel.

Observation only: neighbouring timber extraction outside an applied rule,
the protected region's raw-material imports, craft output, farmer income
modifier and food sufficiency, for the displacement and welfare evidence.
No RNG, no events.
"""
from __future__ import annotations

import math
from typing import Any

from chronicler.commons_rules_state import (
    COUNTER_KEYS, MAX_DECISIONS, CommonsCooldown, CommonsDecision, CommonsReceipt, CommonsRule,
    CommonsRulesState, StockObservation,
)
from chronicler.switch_state import sub_state_getter

#: Adopt a rule when the observed stock is below this share of capacity.
ADOPT_BELOW = 0.5
#: Rest (quota 0) below this share of capacity ...
REST_BELOW = 0.25
#: ... until the observed stock is back at this share.
REOPEN_AT = 0.4
#: Repeal: the stand has recovered to this share of capacity.
REPEAL_AT = 0.8
#: The quota as a share of the stand's regrowth at the observed stock.
QUOTA_SHARE = 1.0
#: Wardens' cost per rule per turn (treasury coins).
ADMIN_COST = 2
#: Repeal after this many consecutive turns with zero coverage ...
UNFUNDED_LIMIT = 3
#: ... or this many consecutive turns in which nobody could harvest the stand.
IDLE_LIMIT = 12
#: No new rule on a repealed slot for this many turns.
COOLDOWN_TURNS = 12
#: City grievance a binding enforced rule adds per turn ...
RULE_GRIEVANCE = 0.02
#: ... never raising the city's grievance above this through this channel.
GRIEVANCE_CEILING = 0.25
MODES = ("enforced", "cost_only")
SCHEMA_VERSION = 1


class _Row:
    __slots__ = ("rule", "new", "owner", "status", "observation", "quota", "stock_cap",
                 "share", "bill", "paid", "coverage", "limit", "applied", "possible")

    def __init__(self, **values):
        for name in self.__slots__:
            setattr(self, name, values.get(name))


class _Plan:
    def __init__(self, turn, rows, decisions, cooldowns, eligible, candidates, unaffordable):
        self.turn, self.rows, self.decisions, self.cooldowns = turn, rows, decisions, cooldowns
        self.eligible, self.candidates, self.unaffordable = eligible, candidates, unaffordable


# --- State and switch -----------------------------------------------------------

_state = sub_state_getter("commons_rules")


def _timber():
    from chronicler import timber_stock
    return timber_stock


def commons_rules_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and _timber().timber_stock_active(world)


def set_commons_rules_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--commons-rule-mode``, default enforced) or disable
    (rules freeze: no caps, no bills; re-enabling resumes them)."""
    mode = getattr(args, "commons_rule_mode", None) if args is not None else None
    if mode is not None and mode not in MODES:
        raise ValueError(f"commons_rule_mode must be one of {MODES}")
    state = _state(world)
    if state is None:
        if not value:
            return
        world.livelihoods.commons_rules = state = CommonsRulesState(mode=mode or "enforced")
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


# --- Pure rule arithmetic -------------------------------------------------------

def allowable_harvest(stock: float, capacity: float, gate_open: bool) -> float:
    """The quota: ``QUOTA_SHARE`` x the stand's regrowth at the observed stock,
    taken at most at the stock of maximum growth ``K (1 - a) / 2`` (a full
    stand may be cut down to its most productive level's growth). Zero
    without capacity or while the water gate is closed."""
    ts = _timber()
    if capacity <= 0.0 or not gate_open:
        return 0.0
    best = capacity * (1.0 - ts.SEED_FRACTION) / 2.0
    return QUOTA_SHARE * ts.regrowth(min(max(stock, 0.0), best), capacity, True)


def next_status(status: str | None, observation: StockObservation) -> str:
    """Rest below ``REST_BELOW`` of capacity until back at ``REOPEN_AT`` (hysteresis)."""
    if observation.capacity <= 0.0:
        return "rest"
    ratio = observation.stock / observation.capacity
    if status == "rest":
        return "quota" if ratio >= REOPEN_AT else "rest"
    return "rest" if ratio < REST_BELOW else "quota"


def coverage(share: float, paid: int) -> float:
    return min(1.0, share + paid / ADMIN_COST)


def effective_limit(quota: float, stock_cap: float, cover: float) -> float:
    """The float32 floor of ``cover x quota + (1 - cover) x stock_cap``,
    never above the stock cap."""
    ts = _timber()
    if quota >= stock_cap:
        return stock_cap
    return min(stock_cap, ts._f32_floor(cover * quota + (1.0 - cover) * stock_cap))


def institution_share(world, civ) -> float:
    """The wardens' share Commons Management supplies: legitimacy x the last
    settled institution funding ratio, for an institution enacted before this
    turn; 0 without one, with stale funding or with governance off.

    Rules are planned in Phase 2 before this turn's institutions are funded
    (``apply_automatic_effects``), so the last settled ratio is the previous
    turn's: a dated observation, like the stock. A lead review on 2026-11-05
    found that requiring this turn's funding made the share 0 in every real
    turn."""
    from chronicler.governance_runtime import governance_enabled
    gov = getattr(civ, "governance", None)
    funded = getattr(gov, "funding_turn", None) if gov is not None else None
    if gov is None or not governance_enabled(world) or funded is None or not world.turn - 1 <= funded <= world.turn:
        return 0.0
    for inst in gov.institutions:
        if inst.institution_type == "commons_management" and inst.enacted_turn < world.turn:
            share = max(0.0, min(1.0, float(inst.legitimacy))) * max(0.0, min(1.0, float(gov.last_institution_funding_ratio)))
            return share if math.isfinite(share) else 0.0
    return 0.0


def bill_for(share: float) -> int:
    return max(0, math.ceil((1.0 - share) * ADMIN_COST - 1e-9))


# --- Pending bills (never spend the same coins twice) ---------------------------

def _woodcut_output(world, economy_result, rid: int, slot: int) -> float:
    """PL1 seam: the woodcutting crews' harvest in that slot's output this turn
    (the region's first timber slot; 0.0 without ``--timber-supply``)."""
    cut = getattr(economy_result, "woodcut_output", None)
    if not cut or not cut.get(rid):
        return 0.0
    from chronicler.timber_supply import _timber_slot
    return float(cut[rid]) if _timber_slot(world.regions[rid]) == slot else 0.0


def pending_phase2_bills(world) -> list[int]:
    """What other Phase 2 spenders have planned against each civ's projected
    treasury and not yet charged: grain storage's pending plan (an upper bound)
    and the workshops' funded bills. Both settle before the commons bill."""
    from chronicler.workshops import _pending_storage_bills
    bills = list(_pending_storage_bills(world))
    workshops = getattr(getattr(world, "livelihoods", None), "workshops", None)
    plan = getattr(workshops, "_plan", None) if workshops is not None else None
    if plan is not None and plan.turn == world.turn:
        for site in plan.sites:
            if site.funded and site.payer is not None and 0 <= site.payer < len(bills):
                bills[site.payer] += sum(site.bill.values())
    return bills


# --- Observations -----------------------------------------------------------------

def _observations(world) -> dict[tuple[int, int], StockObservation]:
    """The previous turn's settled timber accounts (dated, local)."""
    stock = _timber()._state(world)
    if stock is None or stock.ledger_turn is None or stock.ledger_turn != world.turn - 1:
        return {}
    return {(row.region_id, row.slot): StockObservation(
                turn=stock.ledger_turn, stock=row.stock, capacity=row.capacity,
                extraction=row.extraction, water_gate_open=row.water_gate_open)
            for row in stock.ledger if row.removed == 0.0}


def _controller(world, rid: int) -> int:
    name = world.regions[rid].controller
    if name is None:
        return -1
    return world.civ_index_map.get(name, -1)


def carrier_city(world, rid: int):
    """The region's largest open city (rank, size, then lowest settlement id)."""
    from chronicler.cities_state import cities_on
    if not cities_on(world):
        return None
    cities = [c for c in world.cities.cities if c.region == rid]
    if not cities:
        return None
    return min(cities, key=lambda c: (-c.rank, -c.size, c.settlement_id))


def _repeal_reason(world, rule: CommonsRule, observation: StockObservation) -> str | None:
    if observation.capacity > 0.0 and observation.stock >= REPEAL_AT * observation.capacity:
        return "recovered"
    if rule.unfunded_turns >= UNFUNDED_LIMIT:
        return "unfunded"
    if rule.idle_turns >= IDLE_LIMIT:
        return "idle"
    if rule.grievance > 0.0:
        from chronicler.cities import REVOLT_UNREST
        city = carrier_city(world, rule.region_id)
        if city is not None and city.unrest >= REVOLT_UNREST:
            return "unrest"
    return None


# --- Protocol: Phase 2 ------------------------------------------------------------

def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Decide (adopt, repeal, lapse), plan the bills and the limits from dated
    observations; in enforced mode lower the native harvest caps. Charges
    nothing and changes no persisted state."""
    from chronicler.mutual_aid import _treasury_budget
    from chronicler.local_budgets import envelope   # L9 warden envelopes (None: the legacy rule)
    ts = _timber()
    state = _state(world)
    if state._plan is not None:
        raise RuntimeError("commons rule plan already pending")
    offered = ts.offered_caps(world)
    if offered is None:
        raise RuntimeError("commons rules require this turn's prepared timber stock")
    turn = world.turn
    observations = _observations(world)
    stock_caps = ts.harvest_caps(world)
    pending = pending_phase2_bills(world)
    budgets = [max(0, math.floor(_treasury_budget(world, civ, acc)) - pending[i])
               for i, civ in enumerate(world.civilizations)]
    decisions: list[CommonsDecision] = []
    cooldowns = [c for c in state.cooldowns if c.until > turn]
    rows: list[_Row] = []

    def payable(owner, rule):
        cap = envelope(world, owner, "wardens", claim=f"wardens:{rule.region_id}:{rule.slot}")
        return budgets[owner] if cap is None else min(budgets[owner], cap)

    def plan_row(rule, owner, observation, new):
        status = next_status(None if new else rule.status, observation)
        quota = 0.0 if status == "rest" else allowable_harvest(
            observation.stock, observation.capacity, observation.water_gate_open)
        share = institution_share(world, world.civilizations[owner])
        bill = bill_for(share)
        return _Row(rule=rule, new=new, owner=owner, status=status, observation=observation,
                    quota=quota, stock_cap=stock_caps[(rule.region_id, rule.slot)], share=share,
                    bill=bill, paid=0, coverage=0.0, limit=None, applied=False,
                    possible=offered[(rule.region_id, rule.slot)][1])

    # Existing rules: lapse, repeal or continue (commitments are funded first).
    for rule in state.rules:
        key = (rule.region_id, rule.slot)
        if key not in stock_caps:
            decisions.append(CommonsDecision(turn=turn, region_id=rule.region_id, slot=rule.slot,
                                             civ=rule.owner, kind="lapsed", reason="slot_removed"))
            continue
        owner = _controller(world, rule.region_id)
        if owner != rule.owner:
            decisions.append(CommonsDecision(turn=turn, region_id=rule.region_id, slot=rule.slot,
                                             civ=rule.owner, kind="lapsed", reason="owner_changed"))
            continue
        observation = observations.get(key, rule.observation)
        reason = _repeal_reason(world, rule, observation) if observation is not None else None
        if reason is not None:
            decisions.append(CommonsDecision(turn=turn, region_id=rule.region_id, slot=rule.slot,
                                             civ=rule.owner, kind="repealed", reason=reason))
            cooldowns = [c for c in cooldowns if (c.region_id, c.slot) != key]
            cooldowns.append(CommonsCooldown(region_id=rule.region_id, slot=rule.slot,
                                             until=turn + COOLDOWN_TURNS))
            continue
        if observation is None:
            raise RuntimeError("a commons rule has no stock observation")
        row = plan_row(rule, owner, observation, False)
        row.paid = min(row.bill, payable(owner, rule))
        budgets[owner] -= row.paid
        rows.append(row)

    # Adoption by the controller, from its dated observation.
    held = {(r.rule.region_id, r.rule.slot) for r in rows}
    cooling = {(c.region_id, c.slot) for c in cooldowns}
    eligible = candidates = unaffordable = 0
    for key in sorted(observations):
        if key not in stock_caps:
            continue
        rid, slot = key
        owner = _controller(world, rid)
        if owner < 0:
            continue
        eligible += 1
        observation = observations[key]
        if key in held or key in cooling or observation.extraction <= 0.0 or observation.capacity <= 0.0 \
                or observation.stock >= ADOPT_BELOW * observation.capacity:
            continue
        candidates += 1
        rule = CommonsRule(region_id=rid, slot=slot, owner=owner, adopted_turn=turn, observation=observation)
        row = plan_row(rule, owner, observation, True)
        if payable(owner, rule) < row.bill:
            unaffordable += 1
            continue
        row.paid = row.bill
        budgets[owner] -= row.paid
        rows.append(row)
        decisions.append(CommonsDecision(turn=turn, region_id=rid, slot=slot, civ=owner,
                                         kind="adopted", reason="depleted"))

    rows.sort(key=lambda r: (r.rule.region_id, r.rule.slot))
    limits = {}
    for row in rows:
        row.coverage = coverage(row.share, row.paid)
        row.limit = effective_limit(row.quota, row.stock_cap, row.coverage)
        row.applied = row.limit < row.stock_cap
        if row.applied and state.mode == "enforced":
            limits[(row.rule.region_id, row.rule.slot)] = row.limit
    if limits:
        region_input = ts.tighten_harvest_caps(world, region_input, limits)
    state._plan = _Plan(turn, rows, decisions, cooldowns, eligible, candidates, unaffordable)
    return region_input


def rollback_phase2(world) -> None:
    """A failed Phase 2 charged nothing and decided nothing; drop the plan."""
    state = _state(world)
    if state is not None:
        state._plan = None


def _bump(counters: dict, key: str, amount) -> None:
    counters[key] = counters.get(key, 0) + amount


def _region_value(table, name):
    value = table.get(name) if table else None
    return float(value) if value is not None else None


def finish_phase2(world, economy_result, agent_bridge, acc) -> list:
    """Charge the planned bills once, observe the harvest under each rule,
    route a binding rule's conflict to its region's city and commit."""
    from chronicler.mutual_aid import _treasury_budget
    state = _state(world)
    plan, state._plan = state._plan, None
    if plan is None or plan.turn != world.turn:
        raise RuntimeError("commons rule plan missing for this turn")
    outputs = getattr(economy_result, "slot_output", None) or {}
    enforced = state.mode == "enforced"
    applied_keys = {(r.rule.region_id, r.rule.slot) for r in plan.rows if r.applied and enforced}

    def extraction_of(rid, slot):
        name = world.regions[rid].name
        if name not in outputs:
            raise RuntimeError(f"commons rules require the economy's slot output (missing for {name!r})")
        value = float(outputs[name][slot])
        if not math.isfinite(value) or value < 0.0:
            raise RuntimeError(f"invalid timber output {value!r} in region {name!r}")
        return value

    # Validate everything before committing anything.
    totals_by_civ: dict[int, int] = {}
    for row in plan.rows:
        if _controller(world, row.rule.region_id) != row.owner:
            raise RuntimeError("commons rule payer changed while its bill was pending")
        if row.paid:
            totals_by_civ[row.owner] = totals_by_civ.get(row.owner, 0) + row.paid
    for owner, amount in totals_by_civ.items():
        civ = world.civilizations[owner]
        if _treasury_budget(world, civ, acc) < amount:
            # Planning left room for every other Phase 2 bill; a shortfall here
            # means another spender was missed.
            raise RuntimeError("commons rule bill exceeds the projected treasury at settlement")
    timber_slots = set(_timber().timber_slots(world))
    index = {r.name: i for i, r in enumerate(world.regions)}
    receipts: list[CommonsReceipt] = []
    grievance: dict[int, tuple[Any, float]] = {}   # settlement id -> (city, new grievance)
    for row in plan.rows:
        rid, slot = row.rule.region_id, row.rule.slot
        extraction = extraction_of(rid, slot)
        region = world.regions[rid]
        binding = None
        excess = 0.0
        if enforced:
            if row.applied and extraction > row.limit:
                raise RuntimeError(
                    f"the economy harvested {extraction!r} timber in region {region.name!r} slot {slot} "
                    f"against a commons limit of {row.limit!r}")
            # PL1 seam: a woodcutting crew from elsewhere harvests after the
            # residents, under the same limit; the rule binds (and the city's
            # grievance rises) only when the residents' own harvest reaches it.
            resident = extraction - _woodcut_output(world, economy_result, rid, slot)
            binding = bool(row.applied and (resident >= row.limit if row.limit > 0.0 else bool(row.possible)))
        elif row.applied:
            excess = max(0.0, extraction - row.limit)
        city = carrier_city(world, rid)
        added = 0.0
        current = grievance[city.settlement_id][1] if city is not None and city.settlement_id in grievance \
            else (city.grievance if city is not None else 0.0)
        if binding and city is not None and current < GRIEVANCE_CEILING:
            from chronicler.cities import _q
            new = _q(min(GRIEVANCE_CEILING, current + RULE_GRIEVANCE))
            added = max(0.0, new - current)
            if added > 0.0:
                grievance[city.settlement_id] = (city, new)
        neighbours = []
        for adj in region.adjacencies:
            j = index.get(adj)
            if j is None:
                continue
            neighbours += [(j, s) for s in range(3) if (j, s) in timber_slots and (j, s) not in applied_keys]
        receipts.append(CommonsReceipt(
            region_id=rid, slot=slot, owner=row.owner, new=row.new, status=row.status,
            observation=row.observation, quota=row.quota, stock_cap=row.stock_cap, required=ADMIN_COST,
            institution_share=row.share, bill=row.bill, paid=row.paid, coverage=row.coverage,
            limit=row.limit, applied=row.applied, possible=row.possible, extraction=extraction,
            binding=binding, excess=excess, city=None if city is None else city.settlement_id,
            grievance_added=added, neighbour_slots=len(neighbours),
            neighbour_open_extraction=math.fsum(extraction_of(j, s) for j, s in neighbours),
            raw_imports=(None if region.name not in economy_result.imports_by_region
                         else float(economy_result.imports_by_region[region.name].get("raw_material", 0.0))),
            craft_output=float(economy_result.craft_output.get(region.name, 0.0)) if outputs else None,
            farmer_income_modifier=_region_value(economy_result.farmer_income_modifiers, region.name),
            food_sufficiency=_region_value(economy_result.food_sufficiency, region.name),
        ))

    # Commit: charge once, then the rules, the city grievance and the record.
    for owner, amount in sorted(totals_by_civ.items()):
        civ = world.civilizations[owner]
        if acc is None:
            civ.treasury -= amount
        else:
            acc.add(owner, civ, "treasury", -amount, "keep")
    for city, value in grievance.values():
        city.grievance = value
    counters = state.counters
    for key in COUNTER_KEYS:
        counters.setdefault(key, 0)
    _bump(counters, "observed_turns", 1)
    _bump(counters, "eligible_slot_turns", plan.eligible)
    _bump(counters, "adoption_candidates", plan.candidates)
    _bump(counters, "adoption_unaffordable", plan.unaffordable)
    rules = []
    for row, receipt in zip(plan.rows, receipts, strict=True):
        rule = row.rule
        rule.status = row.status
        rule.observation = row.observation
        rule.unfunded_turns = rule.unfunded_turns + 1 if receipt.coverage <= 0.0 else 0
        rule.idle_turns = rule.idle_turns + 1 if receipt.possible is False else 0
        rule.paid += receipt.paid
        rule.binding_turns += 1 if receipt.binding else 0
        rule.grievance = rule.grievance + receipt.grievance_added
        rules.append(rule)
        _bump(counters, "adopted", 1 if row.new else 0)
        _bump(counters, "rule_slot_turns", 1)
        _bump(counters, f"{row.status}_turns", 1)
        _bump(counters, "required", receipt.required)
        _bump(counters, "institution_cover", receipt.institution_share)
        _bump(counters, "billed", receipt.bill)
        _bump(counters, "paid", receipt.paid)
        _bump(counters, "coverage_sum", receipt.coverage)
        kind = ("full" if receipt.coverage >= 1.0 else "zero" if receipt.coverage <= 0.0 else "partial")
        _bump(counters, f"{kind}_coverage_turns", 1)
        _bump(counters, "tightened_turns", 1 if receipt.applied and enforced else 0)
        _bump(counters, "binding_turns", 1 if receipt.binding else 0)
        _bump(counters, "would_bind_turns", 1 if receipt.excess > 0.0 else 0)
        _bump(counters, "excess", receipt.excess)
        _bump(counters, "extraction_under_rule", receipt.extraction)
        _bump(counters, "grievance_added", receipt.grievance_added)
        _bump(counters, "grievance_turns", 1 if receipt.grievance_added > 0.0 else 0)
    for decision in plan.decisions:
        if decision.kind != "adopted":
            _bump(counters, f"{decision.kind}_{decision.reason}", 1)
    state.rules = sorted(rules, key=lambda r: (r.region_id, r.slot))
    state.cooldowns = sorted(plan.cooldowns, key=lambda c: (c.region_id, c.slot))
    state.decisions = (state.decisions + plan.decisions)[-MAX_DECISIONS:]
    state.frame = receipts
    state.frame_turn = plan.turn
    return []


# --- Protocol: observation ------------------------------------------------------

def parameters() -> dict:
    return {"adopt_below": ADOPT_BELOW, "rest_below": REST_BELOW, "reopen_at": REOPEN_AT,
            "repeal_at": REPEAL_AT, "quota_share": QUOTA_SHARE, "admin_cost": ADMIN_COST,
            "unfunded_limit": UNFUNDED_LIMIT, "idle_limit": IDLE_LIMIT, "cooldown_turns": COOLDOWN_TURNS,
            "rule_grievance": RULE_GRIEVANCE, "grievance_ceiling": GRIEVANCE_CEILING}


def snapshot_summary(world) -> dict:
    """Copied record of the completed turn; never live state.

    ``observed`` is False (receipts None, not empty) when no Phase 2 was
    settled in the completed turn."""
    state = _state(world)
    source_turn = world.turn - 1
    observed = state.frame_turn == source_turn
    return {
        "schema_version": SCHEMA_VERSION,
        "units": {"timber": "timber_goods", "money": "treasury"},
        "mode": state.mode,
        "source_turn": source_turn,
        "completed_turn": world.turn,
        "parameters": parameters(),
        "observed": observed,
        "receipts": [r.model_dump() for r in state.frame] if observed else None,
        "decisions": [d.model_dump() for d in state.decisions if d.turn == source_turn] if observed else None,
        "rules": [r.model_dump() for r in state.rules],
        "counters": dict(state.counters),
    }
