"""Detached M68a demonstration. No production imports, sampling, or defaults.

All public records use frozen dataclasses and tuples. Checkpoints retain the
genesis ledger plus every admitted tick so replay and resume share one history.
"""

from dataclasses import asdict, dataclass, replace
import json


CONTRACT = "chronicler-m68a-detached-v1"


@dataclass(frozen=True)
class Policy:
    version: str
    illustrative: bool
    traits: tuple[int, ...]
    empty: int
    allowed: tuple[tuple[int, ...], ...]
    compatibility: tuple[tuple[int, int, int], ...]
    diagonal: int
    draw_scale: int


@dataclass(frozen=True)
class Participant:
    agent_id: str
    group: str
    slots: tuple[int, ...]
    prestige: int


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    recipient: str
    slot: int
    candidate: int
    draw: int


@dataclass(frozen=True)
class Batch:
    turn: int
    proposals: tuple[Proposal, ...]


@dataclass(frozen=True)
class Receipt:
    proposal_id: str
    recipient: str
    slot: int
    previous: int
    candidate: int
    draw: int
    candidate_weight: int
    electorate_weight: int
    threshold: int
    reason: str


@dataclass(frozen=True)
class Tick:
    batch: Batch
    participants: tuple[Participant, ...]
    receipts: tuple[Receipt, ...]


@dataclass(frozen=True)
class Ledger:
    genesis_turn: int
    genesis: tuple[Participant, ...]
    policy: Policy | None = None
    history: tuple[Tick, ...] = ()

    @property
    def turn(self) -> int:
        return self.history[-1].batch.turn if self.history else self.genesis_turn

    @property
    def participants(self) -> tuple[Participant, ...]:
        return self.history[-1].participants if self.history else self.genesis


@dataclass(frozen=True)
class Result:
    ledger: Ledger
    receipts: tuple[Receipt, ...]
    replayed: bool = False
    disabled: bool = False


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _integer(value: object, label: str, minimum: int | None = None) -> None:
    _require(type(value) is int, f"{label} must be an exact integer")
    _require(minimum is None or value >= minimum, f"invalid {label}")


def _name(value: object, label: str) -> None:
    _require(type(value) is str and bool(value.strip()), f"invalid {label}")


def _tuple(value: object, label: str) -> None:
    _require(type(value) is tuple, f"{label} must be an immutable tuple")


def _policy(policy: Policy) -> Policy:
    _require(type(policy) is Policy, "policy required")
    _require(policy.version == CONTRACT, "unsupported policy version")
    _require(policy.illustrative is True, "explicit illustrative policy required")
    _integer(policy.empty, "empty sentinel", 0)
    _integer(policy.draw_scale, "draw scale", 1)
    _integer(policy.diagonal, "diagonal")
    _require(policy.diagonal in (0, 1), "diagonal must permit repeated traits")
    _tuple(policy.traits, "traits")
    _require(bool(policy.traits), "trait domain is empty")
    for t in policy.traits:
        _integer(t, "trait", 0)
        _require(t <= 255, "trait exceeds byte domain")
    _require(policy.empty <= 255 and policy.empty not in policy.traits,
             "empty sentinel must be distinct and byte-sized")
    _require(len(set(policy.traits)) == len(policy.traits), "duplicate traits")
    _tuple(policy.allowed, "slot domains")
    _require(len(policy.allowed) == 8, "eight slot domains required")
    for domain in policy.allowed:
        _tuple(domain, "slot domain")
        for t in domain:
            _integer(t, "allowed trait", 0)
        _require(len(set(domain)) == len(domain) and set(domain) <= set(policy.traits),
                 "invalid slot domain")
    _tuple(policy.compatibility, "compatibility")
    pairs = {}
    for entry in policy.compatibility:
        _tuple(entry, "compatibility entry")
        _require(len(entry) == 3, "compatibility entry needs two traits and a value")
        a, b, value = entry
        for t in (a, b, value):
            _integer(t, "compatibility component")
        _require(a in policy.traits and b in policy.traits and value in (-1, 0, 1),
                 "invalid compatibility entry")
        _require((a, b) not in pairs, "duplicate compatibility entry")
        pairs[a, b] = value
    _require(set(pairs) == {(a, b) for a in policy.traits for b in policy.traits},
             "complete compatibility table required")
    _require(all(pairs[a, b] == pairs[b, a] for a, b in pairs), "asymmetric compatibility")
    _require(all(pairs[t, t] == policy.diagonal for t in policy.traits),
             "diagonal semantics mismatch")
    return replace(policy, traits=tuple(sorted(policy.traits)),
                   allowed=tuple(tuple(sorted(d)) for d in policy.allowed),
                   compatibility=tuple(sorted(policy.compatibility)))


def _participants(participants: tuple[Participant, ...], policy: Policy) -> tuple[Participant, ...]:
    _tuple(participants, "participants")
    seen = set()
    table = {(a, b): v for a, b, v in policy.compatibility}
    for person in participants:
        _require(type(person) is Participant, "invalid participant record")
        _name(person.agent_id, "agent ID")
        _name(person.group, "contact group")
        _require(person.agent_id not in seen, "duplicate agent ID")
        seen.add(person.agent_id)
        _integer(person.prestige, "prestige", 1)
        _tuple(person.slots, "slots")
        _require(len(person.slots) == 8, "exactly eight slots required")
        for slot, trait in enumerate(person.slots):
            _integer(trait, "slot trait", 0)
            _require(trait == policy.empty or trait in policy.allowed[slot], "illegal slot trait")
        nonempty = [t for t in person.slots if t != policy.empty]
        _require(all(table[a, b] != -1 for a in nonempty for b in nonempty),
                 "incompatible ledger")
    return tuple(sorted(participants, key=lambda p: p.agent_id))


def _batch(batch: Batch, participants: tuple[Participant, ...], policy: Policy) -> Batch:
    _require(type(batch) is Batch, "invalid batch")
    _integer(batch.turn, "batch turn", 0)
    _tuple(batch.proposals, "proposals")
    people = {p.agent_id: p for p in participants}
    ids, recipients = set(), set()
    for proposal in batch.proposals:
        _require(type(proposal) is Proposal, "invalid proposal record")
        _name(proposal.proposal_id, "proposal ID")
        _name(proposal.recipient, "recipient")
        _require(proposal.proposal_id not in ids, "duplicate proposal ID")
        _require(proposal.recipient not in recipients, "one proposal per recipient per tick")
        ids.add(proposal.proposal_id)
        recipients.add(proposal.recipient)
        _require(proposal.recipient in people, "unknown recipient")
        _integer(proposal.slot, "proposal slot", 0)
        _require(proposal.slot < 8, "slot out of range")
        _integer(proposal.candidate, "candidate", 0)
        _require(proposal.candidate in policy.allowed[proposal.slot], "illegal candidate")
        _integer(proposal.draw, "draw", 0)
        _require(proposal.draw < policy.draw_scale, "draw out of range")
    return replace(batch, proposals=tuple(sorted(batch.proposals, key=lambda p: p.proposal_id)))


def _transmit(participants: tuple[Participant, ...], batch: Batch, policy: Policy) -> Tick:
    """Frequency is slot-local: each nonempty participant casts one prestige vote."""
    frozen = {p.agent_id: p for p in participants}
    updated = dict(frozen)
    table = {(a, b): v for a, b, v in policy.compatibility}
    receipts = []
    for proposal in batch.proposals:
        person = frozen[proposal.recipient]
        electorate = [p for p in participants if p.group == person.group
                      and p.slots[proposal.slot] != policy.empty]
        total = sum(p.prestige for p in electorate)
        weight = sum(p.prestige for p in electorate if p.slots[proposal.slot] == proposal.candidate)
        threshold = (policy.draw_scale * weight * weight //
                     (weight * weight + (total - weight) ** 2)) if total else 0
        previous = person.slots[proposal.slot]
        if previous == proposal.candidate:
            reason = "unchanged"
        elif any(t != policy.empty and table[proposal.candidate, t] == -1
                 for i, t in enumerate(person.slots) if i != proposal.slot):
            reason = "incompatible"
        elif total == 0:
            reason = "empty_electorate"
        elif weight == 0:
            reason = "absent_candidate"
        elif proposal.draw >= threshold:
            reason = "probability_rejected"
        else:
            reason = "accepted"
            slots = list(person.slots)
            slots[proposal.slot] = proposal.candidate
            updated[person.agent_id] = replace(person, slots=tuple(slots))
        receipts.append(Receipt(proposal.proposal_id, person.agent_id, proposal.slot,
                                previous, proposal.candidate, proposal.draw,
                                weight, total, threshold, reason))
    return Tick(batch, tuple(updated[p.agent_id] for p in participants), tuple(receipts))


def _ledger(ledger: Ledger, policy: Policy) -> Ledger:
    """Validate persisted admission history against its genesis before publication."""
    _require(type(ledger) is Ledger, "invalid ledger")
    _integer(ledger.genesis_turn, "genesis turn", 0)
    people = genesis = _participants(ledger.genesis, policy)
    _tuple(ledger.history, "history")
    if ledger.policy is not None:
        _require(_policy(ledger.policy) == policy, "policy changed within ledger")
    _require(not ledger.history or ledger.policy is not None, "history needs policy")
    history, admitted = [], set()
    turn = ledger.genesis_turn
    for tick in ledger.history:
        _require(type(tick) is Tick, "invalid tick")
        _participants(tick.participants, policy)
        _tuple(tick.receipts, "receipts")
        for receipt in tick.receipts:
            _require(type(receipt) is Receipt, "invalid receipt")
            for field in ("proposal_id", "recipient", "reason"):
                _name(getattr(receipt, field), field)
            for field in ("slot", "previous", "candidate", "draw", "candidate_weight",
                          "electorate_weight", "threshold"):
                _integer(getattr(receipt, field), field, 0)
        batch = _batch(tick.batch, people, policy)
        _require(batch.turn == turn + 1, "nonconsecutive history")
        ids = {p.proposal_id for p in batch.proposals}
        _require(not ids & admitted, "proposal ID reused in history")
        expected = _transmit(people, batch, policy)
        _require(tick == expected, "history does not match admitted transaction")
        admitted.update(ids)
        people, turn = expected.participants, batch.turn
        history.append(expected)
    return Ledger(ledger.genesis_turn, genesis,
                  policy if ledger.policy is not None else None, tuple(history))


def advance(ledger: Ledger, batch: Batch, policy: Policy, *, enabled: bool = False) -> Result:
    """Validate atomically, then advance exactly one tick or return an original replay.

    Disabled calls validate the transaction but return the caller's exact ledger
    without receipts or admissions. Policies remain fixed once a tick is admitted.
    """
    _require(type(enabled) is bool, "enabled must be boolean")
    policy = _policy(policy)
    canonical = _ledger(ledger, policy)
    batch = _batch(batch, canonical.participants, policy)
    if batch.turn <= canonical.turn:
        original = next((t for t in canonical.history if t.batch.turn == batch.turn), None)
        _require(original is not None and original.batch == batch, "conflicting or stale tick replay")
        if not enabled:
            return Result(ledger, (), disabled=True)
        prefix = tuple(t for t in canonical.history if t.batch.turn <= batch.turn)
        return Result(replace(canonical, history=prefix), original.receipts, replayed=True)
    _require(batch.turn == canonical.turn + 1, "exact next turn required")
    admitted = {p.proposal_id for t in canonical.history for p in t.batch.proposals}
    _require(not admitted & {p.proposal_id for p in batch.proposals}, "proposal ID already admitted")
    if not enabled:
        return Result(ledger, (), disabled=True)
    tick = _transmit(canonical.participants, batch, policy)
    return Result(replace(canonical, policy=policy, history=canonical.history + (tick,)), tick.receipts)


def checkpoint_json(ledger: Ledger, policy: Policy) -> str:
    """Canonical experiment-only JSON; never a production snapshot format."""
    policy = _policy(policy)
    ledger = _ledger(ledger, policy)
    payload = {"format": CONTRACT, "policy": asdict(policy), "ledger": asdict(ledger)}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def restore_checkpoint(text: str) -> tuple[Ledger, Policy]:
    """Reject duplicate keys, unknown fields and tampered state/receipts on restore."""
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def record(cls, data, **conversions):
        _require(type(data) is dict and set(data) == set(cls.__dataclass_fields__), "invalid checkpoint fields")
        values = dict(data)
        for key, convert in conversions.items():
            values[key] = convert(values[key])
        return cls(**values)

    def sequence(value, convert=lambda x: x):
        _require(type(value) is list, "checkpoint array required")
        return tuple(convert(x) for x in value)

    def policy_record(data):
        return record(Policy, data, traits=sequence,
                      allowed=lambda v: sequence(v, sequence),
                      compatibility=lambda v: sequence(v, sequence))

    def person(data):
        return record(Participant, data, slots=sequence)

    def tick(data):
        return record(Tick, data,
                      batch=lambda v: record(Batch, v, proposals=lambda x: sequence(x, lambda p: record(Proposal, p))),
                      participants=lambda v: sequence(v, person),
                      receipts=lambda v: sequence(v, lambda r: record(Receipt, r)))

    payload = json.loads(text, object_pairs_hook=object_pairs,
                         parse_constant=lambda v: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    _require(type(payload) is dict and set(payload) == {"format", "policy", "ledger"}, "invalid checkpoint envelope")
    _require(payload["format"] == CONTRACT, "unsupported checkpoint format")
    policy = _policy(policy_record(payload["policy"]))
    ledger = record(Ledger, payload["ledger"], genesis=lambda v: sequence(v, person),
                    policy=lambda v: None if v is None else policy_record(v),
                    history=lambda v: sequence(v, tick))
    return _ledger(ledger, policy), policy
