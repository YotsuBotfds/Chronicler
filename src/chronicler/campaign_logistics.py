"""Detached M60a experiment. Pure immutable records; no production adapters or RNG.

All amounts are integers. Morale/needs/quality use 0..1000; draws use
0..9999. Callers own the state AND cursor, policy, topology, and tick inputs.
"""

from collections import deque
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
import hashlib
import json


CONTRACT = "chronicler-m60a-detached-v1"
ORDERING = ("orders", "replenish", "consume", "stress", "desert", "move", "settle")
PHASES = ("rally", "ready", "marching", "arrived", "returning", "closed", "cancelled")
STATUSES = ("active", "arrived", "returned", "deserted")


@dataclass(frozen=True)
class Policy:
    version: str
    ration_demand: int
    carried_limit: int
    distance_stress: int
    unreachable_stress: int
    hunger_stress: int
    needs_stress: int
    information_stress: int
    morale_recovery: int
    desertion_threshold: int
    desertion_chance: int
    movement_min_morale: int
    require_full_rations: bool
    ordering: tuple[str, ...] = ORDERING
    rally_rule: str = "all-survivors-next-turn"
    termination_rule: str = "all-returned-or-deserted"


@dataclass(frozen=True)
class Region:
    region_id: int
    neighbors: tuple[int, ...]


@dataclass(frozen=True)
class Topology:
    version: str
    regions: tuple[Region, ...]


@dataclass(frozen=True)
class Soldier:
    agent_id: int
    region: int
    rations: int
    morale: int
    role: str = "soldier"
    status: str = "active"


@dataclass(frozen=True)
class Stock:
    region: int
    rations: int


@dataclass(frozen=True)
class Order:
    order_id: str
    turn: int
    kind: str
    agent_ids: tuple[int, ...] = ()
    quantity: int = 0


@dataclass(frozen=True)
class Credit:
    source_id: str
    turn: int
    region: int
    rations: int


@dataclass(frozen=True)
class Condition:
    agent_id: int
    unmet_needs: int
    information_quality: int


@dataclass(frozen=True)
class Draw:
    agent_id: int
    value: int


@dataclass(frozen=True)
class Tick:
    turn: int
    orders: tuple[Order, ...]
    credits: tuple[Credit, ...]
    conditions: tuple[Condition, ...]
    draws: tuple[Draw, ...]
    supply_sources: tuple[int, ...]


@dataclass(frozen=True)
class State:
    contract: str
    campaign_id: str
    admission_turn: int
    turn: int
    policy_id: str
    policy_digest: str
    topology_id: str
    topology_digest: str
    staging: int
    target: int
    phase: str
    original_ids: tuple[int, ...]
    soldiers: tuple[Soldier, ...]
    stocks: tuple[Stock, ...]
    initial_food: int
    credited_food: int = 0
    consumed_food: int = 0
    deserted_food: int = 0


@dataclass(frozen=True)
class Counts:
    active: int
    arrived_active: int
    returned: int
    deserted: int


@dataclass(frozen=True)
class Food:
    initial: int
    credits: int
    local: int
    carried: int
    consumed: int
    deserted: int


@dataclass(frozen=True)
class Replenishment:
    order_id: str
    agent_id: int
    region: int
    requested: int
    granted: int
    stock_before: int
    stock_after: int
    reason: str


@dataclass(frozen=True)
class MemberReceipt:
    agent_id: int
    region_before: int
    region_after: int
    status_before: str
    status_after: str
    path: tuple[int, ...]
    supply_distance: int | None
    ration_before: int
    replenished: int
    consumed: int
    ration_after: int
    released: int
    morale_before: int
    morale_after: int
    hunger_stress: int
    distance_stress: int
    needs_stress: int
    information_stress: int
    draw: int | None
    deserted: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Receipt:
    contract: str
    campaign_id: str
    turn: int
    policy_id: str
    policy_digest: str
    topology_id: str
    topology_digest: str
    payload_digest: str
    state_before_digest: str
    state_after_digest: str
    phase_before: str
    phase_after: str
    inputs: Tick
    orders: tuple[Order, ...]
    credits: tuple[Credit, ...]
    counts_before: Counts
    counts_after: Counts
    stocks_before: tuple[Stock, ...]
    stocks_after: tuple[Stock, ...]
    food: Food
    replenishments: tuple[Replenishment, ...]
    members: tuple[MemberReceipt, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Cursor:
    initial_state_digest: str
    receipts: tuple[Receipt, ...] = ()
    receipt_digests: tuple[str, ...] = ()


@dataclass(frozen=True)
class Session:
    state: State
    cursor: Cursor


@dataclass(frozen=True)
class Result:
    session: Session
    receipt: Receipt


def canonical_bytes(value) -> bytes:
    """Canonical encoding ONLY for these detached experiment records."""
    return json.dumps(asdict(value) if is_dataclass(value) else value,
                      sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _immutable(value):
    if is_dataclass(value):
        if not value.__dataclass_params__.frozen:
            raise ValueError("records must be frozen")
        for field in fields(value):
            _immutable(getattr(value, field.name))
    elif type(value) is tuple:
        for item in value:
            _immutable(item)
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError("only immutable integer/string/tuple records are accepted")


def _int(value, name, low=0, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError(f"invalid {name}")


def _name(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"invalid {name}")


def _records(value, cls):
    if type(value) is not tuple or any(type(item) is not cls for item in value):
        raise ValueError(f"expected tuple of {cls.__name__}")


def _unique(items, name):
    if len(items) != len(set(items)):
        raise ValueError(f"duplicate {name}")


def _config(policy, topology):
    if type(policy) is not Policy or type(topology) is not Topology:
        raise ValueError("explicit Policy and Topology required")
    _immutable(policy)
    _immutable(topology)
    _name(policy.version, "policy version")
    _name(topology.version, "topology version")
    _int(policy.ration_demand, "ration demand", 1)
    _int(policy.carried_limit, "carried limit", policy.ration_demand)
    for key in ("distance_stress", "unreachable_stress", "hunger_stress",
                "needs_stress", "information_stress", "morale_recovery",
                "desertion_threshold", "movement_min_morale"):
        _int(getattr(policy, key), key, 0, 1000)
    _int(policy.desertion_chance, "desertion chance", 0, 10000)
    if (type(policy.require_full_rations) is not bool or policy.ordering != ORDERING
            or policy.rally_rule != "all-survivors-next-turn"
            or policy.termination_rule != "all-returned-or-deserted"):
        raise ValueError("unsupported policy lifecycle/order")
    _records(topology.regions, Region)
    if not topology.regions:
        raise ValueError("empty topology")
    for region in topology.regions:
        _int(region.region_id, "region id")
        if type(region.neighbors) is not tuple:
            raise ValueError("neighbors must be immutable")
        for neighbor in region.neighbors:
            _int(neighbor, "neighbor")
        _unique(region.neighbors, "neighbor")
    _unique(tuple(r.region_id for r in topology.regions), "region")
    topology = replace(topology, regions=tuple(sorted(
        (replace(r, neighbors=tuple(sorted(r.neighbors))) for r in topology.regions),
        key=lambda r: r.region_id)))
    graph = {r.region_id: r.neighbors for r in topology.regions}
    for region, neighbors in graph.items():
        for neighbor in neighbors:
            if neighbor == region or neighbor not in graph or region not in graph[neighbor]:
                raise ValueError("edges must be known, reciprocal and non-self")
    return topology, graph


def _path(graph, start, goal):
    queue = deque([(start,)])
    seen = {start}
    while queue:
        path = queue.popleft()
        if path[-1] == goal:
            return path
        for neighbor in graph[path[-1]]:
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((*path, neighbor))
    return ()


def _counts(state):
    values = {status: sum(s.status == status for s in state.soldiers) for status in STATUSES}
    return Counts(values["active"], values["arrived"], values["returned"], values["deserted"])


def _food(state):
    return Food(state.initial_food, state.credited_food,
                sum(s.rations for s in state.stocks),
                sum(s.rations for s in state.soldiers),
                state.consumed_food, state.deserted_food)


def _validate_soldier(member, policy, graph):
    _int(member.agent_id, "agent id")
    _int(member.region, "member region")
    _int(member.rations, "kit", 0, policy.carried_limit)
    _int(member.morale, "morale", 0, 1000)
    if member.region not in graph or member.role != "soldier" or member.status not in STATUSES:
        raise ValueError("invalid member")


def _validate_state(state, policy, topology, graph):
    if type(state) is not State:
        raise ValueError("State required")
    _immutable(state)
    if (state.contract != CONTRACT or state.policy_id != policy.version
            or state.policy_digest != _digest(policy) or state.topology_id != topology.version
            or state.topology_digest != _digest(topology)):
        raise ValueError("state/config identity mismatch")
    _name(state.campaign_id, "campaign id")
    _int(state.admission_turn, "admission turn")
    _int(state.turn, "turn", state.admission_turn)
    for region in (state.staging, state.target):
        _int(region, "objective")
        if region not in graph:
            raise ValueError("unknown objective")
    if state.staging == state.target or state.phase not in PHASES:
        raise ValueError("invalid objective/phase")
    _records(state.soldiers, Soldier)
    _records(state.stocks, Stock)
    if not state.soldiers:
        raise ValueError("empty roster")
    for member in state.soldiers:
        _validate_soldier(member, policy, graph)
        if member.status in ("returned", "deserted") and member.rations:
            raise ValueError("settled member still carries kit")
        if member.status == "returned" and member.region != state.staging:
            raise ValueError("returned member outside staging")
        if member.status == "arrived" and member.region != state.target:
            raise ValueError("arrived member outside target")
    ids = tuple(s.agent_id for s in state.soldiers)
    for agent in state.original_ids:
        _int(agent, "original agent id")
    if ids != tuple(sorted(ids)) or ids != state.original_ids:
        raise ValueError("roster must match canonical original ids")
    _unique(ids, "agent id")
    for stock in state.stocks:
        _int(stock.region, "stock region")
        _int(stock.rations, "stock")
    if tuple(s.region for s in state.stocks) != tuple(graph):
        raise ValueError("stocks must cover canonical graph")
    for key in ("initial_food", "credited_food", "consumed_food", "deserted_food"):
        _int(getattr(state, key), key)
    food = _food(state)
    if food.initial + food.credits != food.local + food.carried + food.consumed + food.deserted:
        raise ValueError("food conservation violated")
    living = [s for s in state.soldiers if s.status in ("active", "arrived")]
    if state.phase == "closed" and living:
        raise ValueError("closed roster still active")
    if not living and state.phase not in ("closed", "cancelled"):
        raise ValueError("empty active roster not closed")
    if state.phase in ("rally", "ready", "marching", "returning") and any(s.status == "arrived" for s in living):
        raise ValueError("phase/status mismatch")
    if state.phase in ("ready", "marching", "arrived") and len({s.region for s in living}) != 1:
        raise ValueError("cohort is dispersed")
    if state.phase == "ready" and any(s.region != state.staging for s in living):
        raise ValueError("ready roster outside staging")
    if state.phase == "arrived" and any(s.status != "arrived" for s in living):
        raise ValueError("arrival not latched")


def _validate_session(session, policy, topology, graph):
    if type(session) is not Session or type(session.cursor) is not Cursor:
        raise ValueError("state and cursor required together")
    _immutable(session)
    _validate_state(session.state, policy, topology, graph)
    _records(session.cursor.receipts, Receipt)
    if (len(session.cursor.receipt_digests) != len(session.cursor.receipts)
            or session.cursor.receipt_digests != tuple(_digest(r) for r in session.cursor.receipts)):
        raise ValueError("cursor receipt digest mismatch")
    previous = session.cursor.initial_state_digest
    orders, credits = set(), set()
    for turn, receipt in enumerate(session.cursor.receipts, session.state.admission_turn + 1):
        if (receipt.turn != turn or receipt.state_before_digest != previous
                or receipt.campaign_id != session.state.campaign_id
                or receipt.contract != CONTRACT or receipt.policy_digest != _digest(policy)
                or receipt.topology_digest != _digest(topology)
                or receipt.payload_digest != _digest(receipt.inputs)
                or receipt.orders != receipt.inputs.orders or receipt.credits != receipt.inputs.credits):
            raise ValueError("invalid cursor chain")
        for order in receipt.orders:
            if order.order_id in orders:
                raise ValueError("reused order id in cursor")
            orders.add(order.order_id)
        for credit in receipt.credits:
            if credit.source_id in credits:
                raise ValueError("reused credit id in cursor")
            credits.add(credit.source_id)
        previous = receipt.state_after_digest
    if (session.state.turn != session.state.admission_turn + len(session.cursor.receipts)
            or previous != _digest(session.state)):
        raise ValueError("state/cursor mismatch")


def admit(*, policy: Policy, topology: Topology, campaign_id: str, turn: int,
          staging: int, target: int, soldiers: tuple[Soldier, ...],
          stocks: tuple[Stock, ...]) -> Session:
    """Admit exactly one fixed soldier roster; no publication on invalid input."""
    topology, graph = _config(policy, topology)
    _records(soldiers, Soldier)
    _records(stocks, Stock)
    _immutable(soldiers)
    _immutable(stocks)
    for stock in stocks:
        _int(stock.region, "stock region")
        _int(stock.rations, "stock")
        if stock.region not in graph:
            raise ValueError("unknown stock region")
    _unique(tuple(s.region for s in stocks), "stock region")
    for soldier in soldiers:
        _validate_soldier(soldier, policy, graph)
        if soldier.status != "active":
            raise ValueError("admission requires active soldiers")
    soldiers = tuple(sorted(soldiers, key=lambda s: s.agent_id))
    quantities = {s.region: s.rations for s in stocks}
    stocks = tuple(Stock(region, quantities.get(region, 0)) for region in graph)
    state = State(CONTRACT, campaign_id, turn, turn, policy.version, _digest(policy),
                  topology.version, _digest(topology), staging, target, "rally",
                  tuple(s.agent_id for s in soldiers), soldiers, stocks,
                  sum(s.rations for s in soldiers) + sum(s.rations for s in stocks))
    _validate_state(state, policy, topology, graph)
    return Session(state, Cursor(_digest(state)))


def _tick_input(tick, state, graph, *, replay=False):
    if type(tick) is not Tick:
        raise ValueError("explicit Tick required")
    _immutable(tick)
    _int(tick.turn, "tick turn", state.admission_turn + 1)
    for value, cls in ((tick.orders, Order), (tick.credits, Credit),
                       (tick.conditions, Condition), (tick.draws, Draw)):
        _records(value, cls)
    _unique(tuple(o.order_id for o in tick.orders), "order id")
    _unique(tuple(c.source_id for c in tick.credits), "credit id")
    _unique(tuple(c.agent_id for c in tick.conditions), "condition agent")
    _unique(tuple(d.agent_id for d in tick.draws), "draw agent")
    _unique(tick.supply_sources, "supply source")
    for region in tick.supply_sources:
        _int(region, "supply source")
        if region not in graph:
            raise ValueError("unknown supply source")
    controls = []
    for order in tick.orders:
        _name(order.order_id, "order id")
        _int(order.turn, "order turn")
        _int(order.quantity, "replenishment quantity")
        if order.turn != tick.turn or order.kind not in ("march", "hold", "return", "replenish", "cancel"):
            raise ValueError("invalid order/date")
        _unique(order.agent_ids, "replenishment agent")
        for agent in order.agent_ids:
            _int(agent, "order agent")
            if agent not in state.original_ids:
                raise ValueError("late recruitment/unknown agent")
        if order.kind == "replenish":
            if not order.agent_ids or not order.quantity:
                raise ValueError("empty replenishment")
        else:
            controls.append(order.kind)
            if order.agent_ids or order.quantity:
                raise ValueError("control order carries replenishment fields")
    if len(controls) > 1:
        raise ValueError("conflicting control orders")
    for credit in tick.credits:
        _name(credit.source_id, "credit source")
        _int(credit.turn, "credit turn")
        _int(credit.region, "credit region")
        _int(credit.rations, "credit amount", 1)
        if credit.turn != tick.turn or credit.region not in graph:
            raise ValueError("invalid credit/date")
    for condition in tick.conditions:
        _int(condition.agent_id, "condition agent")
        _int(condition.unmet_needs, "unmet needs", 0, 1000)
        _int(condition.information_quality, "information quality", 0, 1000)
    for draw in tick.draws:
        _int(draw.agent_id, "draw agent")
        _int(draw.value, "draw", 0, 9999)
    if not replay:
        terminal = state.phase in ("closed", "cancelled")
        cancel = controls == ["cancel"]
        active = {s.agent_id for s in state.soldiers if s.status in ("active", "arrived")}
        required = set() if terminal or cancel else active
        if {c.agent_id for c in tick.conditions} != required or {d.agent_id for d in tick.draws} != required:
            raise ValueError("exact active condition/draw coverage required")
        if terminal and (tick.orders or tick.credits):
            raise ValueError("terminal campaign rejects orders/credits")
        if cancel and (state.turn != state.admission_turn or tick.credits or len(tick.orders) != 1):
            raise ValueError("cancellation only before first advance, without replenishment/credits")
        if controls == ["march"] and state.phase not in ("rally", "ready", "marching"):
            raise ValueError("march not legal in this phase")
        for order in tick.orders:
            if order.kind == "replenish" and any(agent not in active for agent in order.agent_ids):
                raise ValueError("cannot replenish settled member")
    return replace(tick,
                   orders=tuple(sorted((replace(o, agent_ids=tuple(sorted(o.agent_ids)))
                                        for o in tick.orders), key=lambda o: o.order_id)),
                   credits=tuple(sorted(tick.credits, key=lambda c: c.source_id)),
                   conditions=tuple(sorted(tick.conditions, key=lambda c: c.agent_id)),
                   draws=tuple(sorted(tick.draws, key=lambda d: d.agent_id)),
                   supply_sources=tuple(sorted(tick.supply_sources)))


def advance(session: Session, *, policy: Policy, topology: Topology, tick: Tick) -> Result:
    """Validate the complete tick, calculate privately, then publish atomically.

    Exact historical tick replay returns the SAME historical receipt and the
    current session. It never rolls state backwards or spends/moves twice.
    """
    topology, graph = _config(policy, topology)
    _validate_session(session, policy, topology, graph)
    before = session.state
    tick = _tick_input(tick, before, graph, replay=(type(tick) is Tick
                       and type(tick.turn) is int and tick.turn <= before.turn))
    payload = _digest(tick)
    if tick.turn <= before.turn:
        entry = session.cursor.receipts[tick.turn - before.admission_turn - 1]
        if entry.payload_digest != payload:
            raise ValueError("contradictory tick replay")
        return Result(session, entry)
    if tick.turn != before.turn + 1:
        raise ValueError("future gap requires explicit intermediate ticks")
    used_orders = {o.order_id for r in session.cursor.receipts for o in r.orders}
    used_credits = {c.source_id for r in session.cursor.receipts for c in r.credits}
    if any(o.order_id in used_orders for o in tick.orders) or any(c.source_id in used_credits for c in tick.credits):
        raise ValueError("command/source id already committed")

    phase = before.phase
    control = next((o.kind for o in tick.orders if o.kind != "replenish"), None)
    terminal = phase in ("closed", "cancelled") or control == "cancel"
    reasons = []
    if control == "cancel":
        phase = "cancelled"
        reasons.append("cancelled_before_movement")
    elif not terminal and control == "return":
        phase = "returning"
    elif phase == "ready" and control == "march":
        phase = "marching"
    if terminal and not reasons:
        reasons.append("terminal_noop")
    stocks = {s.region: s.rations for s in before.stocks}
    members = {s.agent_id: s for s in before.soldiers}
    granted = {s.agent_id: 0 for s in before.soldiers}
    replenishments = []
    for credit in tick.credits:
        stocks[credit.region] += credit.rations
    for order in tick.orders:
        if order.kind != "replenish":
            continue
        for agent in order.agent_ids:
            member = members[agent]
            available = stocks[member.region]
            amount = min(order.quantity, policy.carried_limit - member.rations, available)
            members[agent] = replace(member, rations=member.rations + amount)
            stocks[member.region] -= amount
            granted[agent] += amount
            reason = "replenished" if amount == order.quantity else (
                "kit_limit" if policy.carried_limit - member.rations <= available else "local_stock_shortfall")
            replenishments.append(Replenishment(order.order_id, agent, member.region,
                                               order.quantity, amount, available, stocks[member.region], reason))

    conditions = {c.agent_id: c for c in tick.conditions}
    draws = {d.agent_id: d.value for d in tick.draws}
    consumed_total, deserted_total = 0, 0
    receipts = []
    cohort_can_move = True
    # All stress/decisions use start locations, before any survivor moves.
    for original in before.soldiers:
        member = members[original.agent_id]
        consumed = hunger = distance_stress = needs = information = released = 0
        distance = draw = None
        desert = False
        member_reasons = []
        if terminal or member.status in ("returned", "deserted"):
            member_reasons.append("terminal_noop" if terminal else "settled_noop")
        else:
            consumed = min(member.rations, policy.ration_demand)
            consumed_total += consumed
            shortfall = policy.ration_demand - consumed
            hunger = (policy.hunger_stress * shortfall + policy.ration_demand - 1) // policy.ration_demand
            routes = [_path(graph, member.region, source) for source in tick.supply_sources]
            distances = [len(path) - 1 for path in routes if path]
            distance = min(distances) if distances else None
            distance_stress = policy.unreachable_stress if distance is None else distance * policy.distance_stress
            condition = conditions[member.agent_id]
            needs = condition.unmet_needs * policy.needs_stress // 1000
            information = (1000 - condition.information_quality) * policy.information_stress // 1000
            stress = hunger + distance_stress + needs + information
            morale = max(0, min(1000, member.morale - stress if stress else member.morale + policy.morale_recovery))
            draw = draws[member.agent_id]
            desert = morale <= policy.desertion_threshold and draw < policy.desertion_chance
            member = replace(member, rations=member.rations - consumed, morale=morale)
            if shortfall:
                member_reasons.append("ration_shortfall")
            if distance is None:
                member_reasons.append("supply_unreachable")
            if desert:
                released = member.rations
                deserted_total += released
                member = replace(member, rations=0, status="deserted")
                member_reasons.append("deserted")
            elif (policy.require_full_rations and shortfall) or morale < policy.movement_min_morale:
                member_reasons.append("logistics_stall")
                if phase == "marching":
                    cohort_can_move = False
            members[member.agent_id] = member
        receipts.append(MemberReceipt(original.agent_id, original.region, member.region,
                                      original.status, member.status, (), distance,
                                      original.rations, granted[original.agent_id], consumed,
                                      member.rations, released, original.morale, member.morale,
                                      hunger, distance_stress, needs, information,
                                      draw, desert, tuple(member_reasons)))

    # Dispersed rally/return move independently. Marching survivors move as a cohort.
    for i, receipt in enumerate(receipts):
        member = members[receipt.agent_id]
        member_reasons = list(receipt.reasons)
        path = ()
        if not terminal and member.status in ("active", "arrived"):
            goal = before.staging if phase in ("rally", "returning", "ready") else before.target
            path = _path(graph, member.region, goal)
            if phase == "returning":
                member = replace(member, status="active")
            if not path:
                member_reasons.append("destination_unreachable")
            elif member.region == goal:
                member_reasons.append("at_objective")
            elif control == "hold" or phase in ("ready", "arrived"):
                member_reasons.append("hold" if control == "hold" else "await_march" if phase == "ready" else "arrival_latched")
            elif "logistics_stall" in member_reasons or not cohort_can_move:
                if "logistics_stall" not in member_reasons:
                    member_reasons.append("cohort_stall")
            else:
                member = replace(member, region=path[1])
                member_reasons.append("rally_move" if phase == "rally" else "return_move" if phase == "returning" else "march_move")
            if phase == "returning" and member.region == before.staging:
                receipt = replace(receipt, released=member.rations)
                stocks[before.staging] += member.rations
                member = replace(member, status="returned", rations=0)
                member_reasons.append("returned")
            elif phase in ("marching", "arrived") and member.region == before.target:
                member = replace(member, status="arrived")
                member_reasons.append("arrived" if phase == "marching" else "arrival_latched")
            members[member.agent_id] = member
        receipts[i] = replace(receipt, region_after=member.region, status_after=member.status,
                              ration_after=member.rations, path=path, reasons=tuple(member_reasons))

    living = [s for s in members.values() if s.status in ("active", "arrived")]
    if not terminal:
        if not living:
            phase = "closed"
            reasons.append("all_settled")
        elif phase == "rally" and all(s.region == before.staging for s in living):
            phase = "ready"
            reasons.append("rallied_march_next_turn")
        elif phase == "marching" and all(s.status == "arrived" for s in living):
            phase = "arrived"
            reasons.append("arrival_latched")
    after = replace(before, turn=tick.turn, phase=phase,
                    soldiers=tuple(members[s.agent_id] for s in before.soldiers),
                    stocks=tuple(Stock(region, stocks[region]) for region in graph),
                    credited_food=before.credited_food + sum(c.rations for c in tick.credits),
                    consumed_food=before.consumed_food + consumed_total,
                    deserted_food=before.deserted_food + deserted_total)
    _validate_state(after, policy, topology, graph)
    receipt = Receipt(CONTRACT, before.campaign_id, tick.turn, policy.version, _digest(policy),
                      topology.version, _digest(topology), payload, _digest(before), _digest(after),
                      before.phase, phase, tick, tick.orders, tick.credits, _counts(before), _counts(after),
                      before.stocks, after.stocks, _food(after), tuple(replenishments),
                      tuple(receipts), tuple(reasons))
    result = Session(after, replace(session.cursor, receipts=(*session.cursor.receipts, receipt),
                                   receipt_digests=(*session.cursor.receipt_digests, _digest(receipt))))
    _validate_session(result, policy, topology, graph)
    return Result(result, receipt)
