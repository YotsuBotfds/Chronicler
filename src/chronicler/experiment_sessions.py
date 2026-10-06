"""Durable local sessions for the reviewed detached experiments.

Session contract ``chronicler-experiment-session-v1`` wraps the public
``campaign_logistics`` (M60a) and ``memome_experiment`` (M68a) APIs in a closed,
versioned, experiment-only envelope with an explicit transport policy and a
single-writer local file protocol.

Scope and limits:

* Standard library only. No production module, native code, snapshot or bundle
  schema, CLI registry entry, clock value, environment secret or simulation RNG
  is read or written. Nothing here generates a world, draws a draw, or starts a
  simulation.
* Serialization uses explicit whitelisted record field tables only. There is no
  pickle, no ``eval``/``exec`` and no dynamic import, so a session file cannot
  name a record outside the closed tables below.
* Kernel arithmetic, tuning and existing checkpoint semantics are untouched.
  ``memome_experiment.checkpoint_json``/``restore_checkpoint`` are reused as-is
  for M68a; M60a is restored by public ``admit`` plus public ``advance`` over
  every committed tick, then compared in full against the saved content.
* This is a supported *local transport subset* for review tables. It is not a
  security protocol, not a signature scheme and not a distributed lock service.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat

from chronicler import campaign_logistics as cl
from chronicler import memome_experiment as mm

try:  # POSIX-only writer lock. Absence is reported before any mutation.
    import fcntl
except ImportError:  # pragma: no cover - only reachable on non-POSIX platforms
    fcntl = None


# --------------------------------------------------------------- identities

CONTRACT = "chronicler-experiment-session-v1"
ENVELOPE_VERSION = 1

#: Reviewed baseline this companion was written against. A session written
#: against a different source head is a foreign artifact and is rejected, so
#: these constants may only move together with a re-review of both kernels.
BASELINE_SOURCE_HEAD = "208d140d47d9f2dee0788267f79fa7276df22b42"
BASELINE_SOURCE_TREE = "0762c7cff65e28ff326291ce31111b71e1d61ae3"

#: Closed kernel allow-list. Every session names exactly one ID and the matching
#: kernel contract string; anything else fails explicitly.
KERNEL_CONTRACTS = {
    "m60a": "chronicler-m60a-detached-v1",
    "m68a": "chronicler-m68a-detached-v1",
}

#: Closed transport-policy version allow-list.
SUPPORTED_TRANSPORT_VERSIONS = ("chronicler-session-transport-v1",)

#: An integer needs at most ``bits * log10(2) + 1`` decimal digits, so 14000 bits
#: is at most 4215 digits and every accepted value stays below CPython's default
#: 4300-digit integer/str conversion limit without changing that limit.
MAX_TRANSPORT_INT_BITS = 14000
MAX_TRANSPORT_BYTES = 1 << 26
MAX_TRANSPORT_RECORDS = 1 << 22
MAX_TRANSPORT_HISTORY = 1 << 20

_LOG10_2_NUMERATOR = 30103
_LOG10_2_DENOMINATOR = 100000

#: Documented order of the local commit protocol; every step must complete.
SESSION_COMMIT_ORDER = (
    "platform-support", "destination-shape", "writer-lock", "expected-generation",
    "checkpoint-validation", "temporary-write", "file-fsync", "atomic-replace",
    "directory-fsync",
)

_ENVELOPE_FIELDS = (
    "contract", "envelope_version", "kernel", "kernel_contract", "source_head",
    "source_tree", "transport", "generation", "turn", "genesis", "history", "latest",
    "genesis_digest", "history_digest", "latest_digest", "session_digest",
)
_TRANSPORT_FIELDS = ("version", "max_bytes", "max_records", "max_history", "max_int_bits")
_CAMPAIGN_GENESIS_FIELDS = ("policy", "topology", "admission")
_CAMPAIGN_LATEST_FIELDS = ("state", "cursor")
_MEMOME_GENESIS_FIELDS = ("genesis_turn", "participants", "policy")
_MEMOME_LATEST_FIELDS = ("checkpoint",)
_ADMISSION_FIELDS = ("campaign_id", "turn", "staging", "target", "soldiers", "stocks")


# -------------------------------------------------------------------- errors


class SessionError(ValueError):
    """Base class for every experiment-session failure."""


class ContractError(SessionError):
    """Foreign kernel, envelope version or source identity."""


class TransportDomainError(SessionError):
    """Requested or persisted state is outside the explicit transport domain."""


class IntegrityError(SessionError):
    """Reconstructed content disagrees with persisted content."""


class PersistenceError(SessionError):
    """A failure that provably preserved the prior destination bytes."""


class StaleGenerationError(PersistenceError):
    """The destination moved, or is not the generation the caller expected."""


class UnsupportedPlatformError(PersistenceError):
    """Local durable writes are unsupported here; raised before any mutation."""


class DurabilityUncertain(PersistenceError):
    """The replace succeeded but the commit gate did not; read back before retrying."""


class CommittedCleanupError(SessionError):
    """Publication is durable; cleanup failed. Never automatically retry the write.

    ``result`` identifies the completed publication, not necessarily the current
    head. ``cleanup_error`` and the exception cause retain the original failure.
    """

    def __init__(self, result: CommitResult, cleanup_error: OSError) -> None:
        self.result = result
        self.cleanup_error = cleanup_error
        super().__init__(
            f"session generation {result.generation} committed durably at {result.path!r} "
            f"with digest {result.digest}, but cleanup failed ({cleanup_error}); "
            "read the file back to reconcile current identity; do not automatically retry")


class _CleanupFailure(Exception):
    """Internal marker: cleanup failed after the protected operation completed."""

    def __init__(self, error: OSError) -> None:
        self.error = error


# ------------------------------------------------------------------- helpers


def _require(condition: object, message: str) -> None:
    if not condition:
        raise SessionError(message)


def _exact_int(value: object, name: str, *, minimum: int = 0) -> int:
    _require(type(value) is int, f"{name} must be an exact integer")
    _require(value >= minimum, f"invalid {name}")
    return value


def _exact_name(value: object, name: str) -> str:
    _require(type(value) is str and bool(value.strip()), f"invalid {name}")
    return value


def _require_integrity(condition: object, message: str) -> None:
    if not condition:
        raise IntegrityError(message)


def _require_contract(condition: object, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _max_digits(bits: int) -> int:
    return bits * _LOG10_2_NUMERATOR // _LOG10_2_DENOMINATOR + 1


def _canonical_json(payload: object) -> str:
    """Canonical text for already type-checked plain containers."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _strict_loads(text: str, max_digits: int, label: str) -> object:
    """Parse JSON rejecting duplicate keys, nonfinite values, floats and wide integers.

    ``parse_int`` receives the literal *text* first, so an over-wide integer is
    rejected before any decimal conversion occurs.
    """
    def parse_int(literal: str) -> int:
        if len(literal.lstrip("-")) > max_digits:
            raise TransportDomainError(
                f"{label} integer literal exceeds the {max_digits}-digit transport "
                "integer domain")
        return int(literal)

    def parse_float(literal: str) -> float:
        raise TransportDomainError(f"{label} rejects the non-integer number {literal!r}")

    def parse_constant(name: str) -> float:
        raise TransportDomainError(f"{label} rejects the nonfinite constant {name}")

    def object_pairs(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise TransportDomainError(f"{label} rejects the duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(text, parse_int=parse_int, parse_float=parse_float,
                          parse_constant=parse_constant, object_pairs_hook=object_pairs)
    except TransportDomainError:
        raise
    except ValueError as exc:
        raise SessionError(f"{label} is not valid JSON: {exc}") from exc


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Budget:
    """Explicit record-count accounting for one encode or decode pass."""

    __slots__ = ("limit", "used")

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def take(self, label: str) -> None:
        self.used += 1
        if self.used > self.limit:
            raise TransportDomainError(
                f"record count exceeds the {self.limit}-record transport limit at {label}")


# ------------------------------------------------------------ transport policy


@dataclass(frozen=True)
class TransportPolicy:
    """Explicit, versioned bounds for one session file or submission.

    ``max_bytes`` bounds the encoded file and every caller submission,
    ``max_records`` bounds whitelisted records including the records a reused
    kernel checkpoint persists, ``max_history`` bounds committed turns and the
    M68a genesis participant list, and ``max_int_bits`` bounds the exact bit width
    of every transported integer including kernel-derived values. Nothing is
    clamped silently; exceeding a bound raises :class:`TransportDomainError`, and
    an invalid *policy* raises :class:`SessionError`.
    """

    version: str
    max_bytes: int
    max_records: int
    max_history: int
    max_int_bits: int

    def as_payload(self) -> dict:
        return {name: getattr(self, name) for name in _TRANSPORT_FIELDS}

    def max_digits(self) -> int:
        return _max_digits(self.max_int_bits)


def _validate_transport(policy: object) -> TransportPolicy:
    _require(type(policy) is TransportPolicy,
             "an explicit versioned TransportPolicy is required")
    _require(policy.version in SUPPORTED_TRANSPORT_VERSIONS,
             f"unsupported transport policy version {policy.version!r}")
    _exact_int(policy.max_bytes, "max_bytes", minimum=1)
    _require(policy.max_bytes <= MAX_TRANSPORT_BYTES, "max_bytes exceeds the supported bound")
    _exact_int(policy.max_records, "max_records", minimum=1)
    _require(policy.max_records <= MAX_TRANSPORT_RECORDS,
             "max_records exceeds the supported bound")
    _exact_int(policy.max_history, "max_history", minimum=0)
    _require(policy.max_history <= MAX_TRANSPORT_HISTORY,
             "max_history exceeds the supported bound")
    _exact_int(policy.max_int_bits, "max_int_bits", minimum=1)
    _require(policy.max_int_bits <= MAX_TRANSPORT_INT_BITS,
             "max_int_bits exceeds the supported bound")
    return policy


def transport_policy_from_payload(payload: object) -> TransportPolicy:
    """Decode a transport policy from strict JSON with exact fields."""
    _require(type(payload) is dict, "transport policy must be a JSON object")
    _require(set(payload) == set(_TRANSPORT_FIELDS),
             f"transport policy fields must be exactly {sorted(_TRANSPORT_FIELDS)}")
    return _validate_transport(TransportPolicy(**payload))


def transport_policy_from_text(text: str) -> TransportPolicy:
    """Decode a caller-supplied transport policy from strict JSON text.

    This is the only parse that runs before a policy exists, so it cannot apply
    an integer width yet: the text length is bounded instead and every literal
    is still bounded afterwards by :func:`_validate_transport`.
    """
    _require(type(text) is str, "transport policy text must be a string")
    _require(len(text) <= 4096, "transport policy text exceeds 4096 characters")
    payload = _strict_loads(text, 64, "transport policy")
    return transport_policy_from_payload(payload)


def documented_transport_policy() -> TransportPolicy:
    """Illustrative local transport subset, wide enough for 121-bit integers."""
    return TransportPolicy(version=SUPPORTED_TRANSPORT_VERSIONS[0], max_bytes=1 << 23,
                           max_records=200_000, max_history=10_000, max_int_bits=4096)


# ------------------------------------------------- whitelisted record tables


@dataclass(frozen=True)
class _Field:
    name: str
    kind: str
    record: str = ""


_F = _Field


@dataclass(frozen=True)
class CampaignAdmission:
    """Complete M60a admission captured before the first tick."""

    campaign_id: str
    turn: int
    staging: int
    target: int
    soldiers: tuple[cl.Soldier, ...]
    stocks: tuple[cl.Stock, ...]


_M60A_SCHEMA: dict[str, tuple[type, tuple[_Field, ...]]] = {
    "policy": (cl.Policy, (
        _F("version", "str"), _F("ration_demand", "int"), _F("carried_limit", "int"),
        _F("distance_stress", "int"), _F("unreachable_stress", "int"),
        _F("hunger_stress", "int"), _F("needs_stress", "int"),
        _F("information_stress", "int"), _F("morale_recovery", "int"),
        _F("desertion_threshold", "int"), _F("desertion_chance", "int"),
        _F("movement_min_morale", "int"), _F("require_full_rations", "bool"),
        _F("ordering", "str_seq"), _F("rally_rule", "str"), _F("termination_rule", "str"),
    )),
    "topology": (cl.Topology, (
        _F("version", "str"), _F("regions", "record_seq", "region"),
    )),
    "region": (cl.Region, (
        _F("region_id", "int"), _F("neighbors", "int_seq"),
    )),
    "soldier": (cl.Soldier, (
        _F("agent_id", "int"), _F("region", "int"), _F("rations", "int"),
        _F("morale", "int"), _F("role", "str"), _F("status", "str"),
    )),
    "stock": (cl.Stock, (
        _F("region", "int"), _F("rations", "int"),
    )),
    "order": (cl.Order, (
        _F("order_id", "str"), _F("turn", "int"), _F("kind", "str"),
        _F("agent_ids", "int_seq"), _F("quantity", "int"),
    )),
    "credit": (cl.Credit, (
        _F("source_id", "str"), _F("turn", "int"), _F("region", "int"),
        _F("rations", "int"),
    )),
    "condition": (cl.Condition, (
        _F("agent_id", "int"), _F("unmet_needs", "int"),
        _F("information_quality", "int"),
    )),
    "draw": (cl.Draw, (
        _F("agent_id", "int"), _F("value", "int"),
    )),
    "tick": (cl.Tick, (
        _F("turn", "int"), _F("orders", "record_seq", "order"),
        _F("credits", "record_seq", "credit"),
        _F("conditions", "record_seq", "condition"),
        _F("draws", "record_seq", "draw"),
        _F("supply_sources", "int_seq"),
    )),
    "counts": (cl.Counts, (
        _F("active", "int"), _F("arrived_active", "int"), _F("returned", "int"),
        _F("deserted", "int"),
    )),
    "food": (cl.Food, (
        _F("initial", "int"), _F("credits", "int"), _F("local", "int"),
        _F("carried", "int"), _F("consumed", "int"), _F("deserted", "int"),
    )),
    "replenishment": (cl.Replenishment, (
        _F("order_id", "str"), _F("agent_id", "int"), _F("region", "int"),
        _F("requested", "int"), _F("granted", "int"), _F("stock_before", "int"),
        _F("stock_after", "int"), _F("reason", "str"),
    )),
    "member_receipt": (cl.MemberReceipt, (
        _F("agent_id", "int"), _F("region_before", "int"), _F("region_after", "int"),
        _F("status_before", "str"), _F("status_after", "str"), _F("path", "int_seq"),
        _F("supply_distance", "opt_int"), _F("ration_before", "int"),
        _F("replenished", "int"), _F("consumed", "int"), _F("ration_after", "int"),
        _F("released", "int"), _F("morale_before", "int"), _F("morale_after", "int"),
        _F("hunger_stress", "int"), _F("distance_stress", "int"),
        _F("needs_stress", "int"), _F("information_stress", "int"),
        _F("draw", "opt_int"), _F("deserted", "bool"), _F("reasons", "str_seq"),
    )),
    "receipt": (cl.Receipt, (
        _F("contract", "str"), _F("campaign_id", "str"), _F("turn", "int"),
        _F("policy_id", "str"), _F("policy_digest", "str"), _F("topology_id", "str"),
        _F("topology_digest", "str"), _F("payload_digest", "str"),
        _F("state_before_digest", "str"), _F("state_after_digest", "str"),
        _F("phase_before", "str"), _F("phase_after", "str"),
        _F("inputs", "record", "tick"), _F("orders", "record_seq", "order"),
        _F("credits", "record_seq", "credit"),
        _F("counts_before", "record", "counts"), _F("counts_after", "record", "counts"),
        _F("stocks_before", "record_seq", "stock"),
        _F("stocks_after", "record_seq", "stock"), _F("food", "record", "food"),
        _F("replenishments", "record_seq", "replenishment"),
        _F("members", "record_seq", "member_receipt"), _F("reasons", "str_seq"),
    )),
    "state": (cl.State, (
        _F("contract", "str"), _F("campaign_id", "str"), _F("admission_turn", "int"),
        _F("turn", "int"), _F("policy_id", "str"), _F("policy_digest", "str"),
        _F("topology_id", "str"), _F("topology_digest", "str"), _F("staging", "int"),
        _F("target", "int"), _F("phase", "str"), _F("original_ids", "int_seq"),
        _F("soldiers", "record_seq", "soldier"), _F("stocks", "record_seq", "stock"),
        _F("initial_food", "int"), _F("credited_food", "int"),
        _F("consumed_food", "int"), _F("deserted_food", "int"),
    )),
    "cursor": (cl.Cursor, (
        _F("initial_state_digest", "str"), _F("receipts", "record_seq", "receipt"),
        _F("receipt_digests", "str_seq"),
    )),
    "admission": (CampaignAdmission, (
        _F("campaign_id", "str"), _F("turn", "int"), _F("staging", "int"),
        _F("target", "int"), _F("soldiers", "record_seq", "soldier"),
        _F("stocks", "record_seq", "stock"),
    )),
}

_M68A_SCHEMA: dict[str, tuple[type, tuple[_Field, ...]]] = {
    "policy": (mm.Policy, (
        _F("version", "str"), _F("illustrative", "bool"), _F("traits", "int_seq"),
        _F("empty", "int"), _F("allowed", "int_seq_seq"),
        _F("compatibility", "int3_seq"), _F("diagonal", "int"),
        _F("draw_scale", "int"),
    )),
    "participant": (mm.Participant, (
        _F("agent_id", "str"), _F("group", "str"), _F("slots", "int_seq"),
        _F("prestige", "int"),
    )),
    "proposal": (mm.Proposal, (
        _F("proposal_id", "str"), _F("recipient", "str"), _F("slot", "int"),
        _F("candidate", "int"), _F("draw", "int"),
    )),
    "batch": (mm.Batch, (
        _F("turn", "int"), _F("proposals", "record_seq", "proposal"),
    )),
}


def _check_width(value: int, name: str, transport: TransportPolicy) -> int:
    width = value.bit_length()
    if width > transport.max_int_bits:
        raise TransportDomainError(
            f"{name} needs {width} bits, outside the {transport.max_int_bits}-bit "
            "transport integer domain")
    return value


def _encode_value(value: object, field: _Field, schema: dict, transport: TransportPolicy,
                  budget: _Budget, label: str) -> object:
    name = f"{label}.{field.name}"
    kind = field.kind
    if kind == "int":
        _exact_int(value, name)
        return _check_width(value, name, transport)
    if kind == "str":
        _exact_name(value, name)
        return value
    if kind == "bool":
        _require(type(value) is bool, f"{name} must be a boolean")
        return value
    if kind == "opt_int":
        if value is None:
            return None
        _exact_int(value, name)
        return _check_width(value, name, transport)
    if kind == "int_seq":
        _require(type(value) is tuple, f"{name} must be an immutable tuple")
        return [_check_width(_exact_int(item, f"{name}[]"), f"{name}[]", transport)
                for item in value]
    if kind == "str_seq":
        _require(type(value) is tuple, f"{name} must be an immutable tuple")
        return [_exact_name(item, f"{name}[]") for item in value]
    if kind == "int_seq_seq":
        _require(type(value) is tuple, f"{name} must be an immutable tuple")
        rows = []
        for row in value:
            _require(type(row) is tuple, f"{name}[] must be an immutable tuple")
            rows.append([_check_width(_exact_int(item, f"{name}[][]"), f"{name}[][]",
                                      transport) for item in row])
        return rows
    if kind == "int3_seq":
        _require(type(value) is tuple, f"{name} must be an immutable tuple")
        rows = []
        for row in value:
            _require(type(row) is tuple, f"{name}[] must be an immutable tuple")
            _require(len(row) == 3, f"{name}[] needs exactly three components")
            rows.append([_check_width(_exact_int(item, f"{name}[][]", minimum=-1),
                                      f"{name}[][]", transport) for item in row])
        return rows
    if kind == "record":
        return _encode_record(value, field.record, schema, transport, budget)
    if kind == "record_seq":
        _require(type(value) is tuple, f"{name} must be an immutable tuple")
        return [_encode_record(item, field.record, schema, transport, budget)
                for item in value]
    raise SessionError(f"unsupported field kind {kind!r}")  # pragma: no cover


def _encode_record(value: object, name: str, schema: dict, transport: TransportPolicy,
                   budget: _Budget) -> dict:
    budget.take(name)
    cls, fields = schema[name]
    _require(type(value) is cls, f"exact {name} record required")
    payload = {field.name: _encode_value(getattr(value, field.name), field, schema,
                                         transport, budget, name)
               for field in fields}
    _require(set(payload) == set(cls.__dataclass_fields__),
             f"{name} field table disagrees with the kernel record")  # pragma: no cover
    return payload


def _decode_value(raw: object, field: _Field, schema: dict, transport: TransportPolicy,
                  budget: _Budget, label: str) -> object:
    """Decode one whitelisted field; every transported integer is bit-bounded.

    The bit check is exact, not a digit-length approximation: a 4097-bit value
    shares the allowed digit length of the 4096-bit domain and must still fail.
    """
    name = f"{label}.{field.name}"
    kind = field.kind
    if kind == "int":
        return _check_width(_exact_int(raw, name), name, transport)
    if kind == "str":
        return _exact_name(raw, name)
    if kind == "bool":
        _require(type(raw) is bool, f"{name} must be a boolean")
        return raw
    if kind == "opt_int":
        return None if raw is None else _check_width(_exact_int(raw, name), name, transport)
    if kind == "int_seq":
        _require(type(raw) is list, f"{name} must be a JSON array")
        return tuple(_check_width(_exact_int(item, f"{name}[]"), f"{name}[]", transport)
                     for item in raw)
    if kind == "str_seq":
        _require(type(raw) is list, f"{name} must be a JSON array")
        return tuple(_exact_name(item, f"{name}[]") for item in raw)
    if kind == "int_seq_seq":
        _require(type(raw) is list, f"{name} must be a JSON array")
        rows = []
        for row in raw:
            _require(type(row) is list, f"{name}[] must be a JSON array")
            rows.append(tuple(_check_width(_exact_int(item, f"{name}[][]"), f"{name}[][]",
                                           transport) for item in row))
        return tuple(rows)
    if kind == "int3_seq":
        _require(type(raw) is list, f"{name} must be a JSON array")
        rows = []
        for row in raw:
            _require(type(row) is list, f"{name}[] must be a JSON array")
            _require(len(row) == 3, f"{name}[] needs exactly three components")
            rows.append(tuple(_check_width(_exact_int(item, f"{name}[][]", minimum=-1),
                                           f"{name}[][]", transport) for item in row))
        return tuple(rows)
    if kind == "record":
        return _decode_record(raw, field.record, schema, transport, budget)
    if kind == "record_seq":
        _require(type(raw) is list, f"{name} must be a JSON array")
        return tuple(_decode_record(item, field.record, schema, transport, budget)
                     for item in raw)
    raise SessionError(f"unsupported field kind {kind!r}")  # pragma: no cover


def _decode_record(raw: object, name: str, schema: dict, transport: TransportPolicy,
                   budget: _Budget) -> object:
    budget.take(name)
    cls, fields = schema[name]
    _require(type(raw) is dict, f"{name} must be a JSON object")
    _require(set(raw) == {field.name for field in fields},
             f"{name} fields must be exactly {sorted(field.name for field in fields)}")
    values = {field.name: _decode_value(raw[field.name], field, schema, transport,
                                        budget, name)
              for field in fields}
    return cls(**values)


# ------------------------------------------------------------ session records


@dataclass(frozen=True)
class CampaignSession:
    """Admission, configuration, committed history and the current M60a cursor."""

    policy: cl.Policy
    topology: cl.Topology
    admission: CampaignAdmission
    history: tuple[cl.Tick, ...]
    session: cl.Session


@dataclass(frozen=True)
class MemomeSession:
    """Genesis, admitted batches and the latest M68a ledger."""

    policy: mm.Policy
    genesis_turn: int
    genesis: tuple[mm.Participant, ...]
    batches: tuple[mm.Batch, ...]
    ledger: mm.Ledger


@dataclass(frozen=True)
class ApplyResult:
    """One explicit tick/batch submission. ``changed`` False writes nothing."""

    session: CampaignSession | MemomeSession
    changed: bool
    turn: int
    replayed: bool
    receipts: tuple


@dataclass(frozen=True)
class Envelope:
    """Closed, versioned, experiment-only session envelope."""

    contract: str
    envelope_version: int
    kernel: str
    kernel_contract: str
    source_head: str
    source_tree: str
    transport: TransportPolicy
    generation: int
    turn: int
    genesis: str
    history: str
    latest: str
    genesis_digest: str
    history_digest: str
    latest_digest: str
    session_digest: str

    def as_payload(self) -> dict:
        """Plain-JSON view with the transport policy expanded to its four bounds."""
        payload = {name: getattr(self, name) for name in _ENVELOPE_FIELDS}
        payload["transport"] = self.transport.as_payload()
        return payload


@dataclass(frozen=True)
class CommitResult:
    """Returned only after the parent-directory commit gate completed."""

    path: str
    generation: int
    turn: int
    digest: str
    envelope: Envelope


@dataclass(frozen=True)
class LoadedSession:
    """A read session. Reading always reconstructs by public kernel replay."""

    path: str
    generation: int
    turn: int
    digest: str
    envelope: Envelope
    session: CampaignSession | MemomeSession


# ------------------------------------------------------------- session creation


def create_campaign_session(*, policy: cl.Policy, topology: cl.Topology, campaign_id: str,
                           turn: int, staging: int, target: int,
                           soldiers: tuple[cl.Soldier, ...],
                           stocks: tuple[cl.Stock, ...]) -> CampaignSession:
    """Admit one explicit roster through the public M60a API and capture its inputs."""
    admission = CampaignAdmission(campaign_id, turn, staging, target,
                                  tuple(soldiers), tuple(stocks))
    session = cl.admit(policy=policy, topology=topology, campaign_id=admission.campaign_id,
                       turn=admission.turn, staging=admission.staging,
                       target=admission.target, soldiers=admission.soldiers,
                       stocks=admission.stocks)
    result = CampaignSession(policy, topology, admission, (), session)
    _validate_campaign_session(result)
    return result


def create_memome_session(*, policy: mm.Policy, genesis_turn: int,
                          participants: tuple[mm.Participant, ...]) -> MemomeSession:
    """Admit an explicit genesis roster, canonicalised through public APIs only."""
    ledger = mm.Ledger(genesis_turn, tuple(participants))
    canonical, canonical_policy = mm.restore_checkpoint(mm.checkpoint_json(ledger, policy))
    result = MemomeSession(canonical_policy, canonical.genesis_turn, canonical.genesis,
                           (), canonical)
    _validate_memome_session(result)
    return result


def _validate_campaign_session(session: CampaignSession) -> None:
    _require(type(session) is CampaignSession, "exact CampaignSession record required")
    _require(type(session.admission) is CampaignAdmission,
             "exact CampaignAdmission record required")
    _require(type(session.history) is tuple, "committed history must be an immutable tuple")
    _require(type(session.session) is cl.Session, "exact kernel Session record required")
    state, cursor = session.session.state, session.session.cursor
    _require(tuple(tick.turn for tick in session.history)
             == tuple(range(state.admission_turn + 1, state.turn + 1)),
             "committed history must be contiguous admitted ticks")
    _require(len(session.history) == len(cursor.receipts),
             "committed history and receipt cursor disagree")
    _require(all(tick == receipt.inputs
                 for tick, receipt in zip(session.history, cursor.receipts)),
             "committed history must equal the admitted tick inputs")


def _validate_memome_session(session: MemomeSession) -> None:
    _require(type(session) is MemomeSession, "exact MemomeSession record required")
    _require(type(session.batches) is tuple, "committed history must be an immutable tuple")
    _require(type(session.ledger) is mm.Ledger, "exact kernel Ledger record required")
    _require(session.ledger.genesis_turn == session.genesis_turn,
             "genesis turn disagrees with the kernel ledger")
    _require(session.ledger.genesis == session.genesis,
             "genesis roster disagrees with the kernel ledger")
    _require(tuple(tick.batch for tick in session.ledger.history) == session.batches,
             "committed history disagrees with the kernel ledger history")


def session_turn(session: CampaignSession | MemomeSession) -> int:
    """Latest committed turn for either supported kernel."""
    if type(session) is CampaignSession:
        _validate_campaign_session(session)
        return session.session.state.turn
    _require(type(session) is MemomeSession, "unknown session record")
    _validate_memome_session(session)
    return session.ledger.turn


# ------------------------------------------------------- caller-supplied inputs


def _payload_object(payload: object, label: str, fields: tuple[str, ...]) -> dict:
    _require(type(payload) is dict, f"{label} must be a JSON object")
    _require(set(payload) == set(fields), f"{label} fields must be exactly {sorted(fields)}")
    return payload


def _strict_submission_bytes(data: bytes, transport: TransportPolicy,
                             label: str) -> str:
    """Bound one explicit caller submission before it is parsed or applied."""
    _validate_transport(transport)
    _require(type(data) is bytes, f"{label} must be UTF-8 bytes")
    if len(data) > transport.max_bytes:
        raise TransportDomainError(
            f"the {label} exceeds the {transport.max_bytes}-byte transport limit")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SessionError(f"the {label} is not valid UTF-8") from exc


def submission_from_bytes(data: bytes, *, transport: TransportPolicy,
                          label: str = "submission") -> object:
    """Decode explicit CLI admission/batch bytes with bounded strict parsing.

    One bounded, duplicate-rejecting, nonfinite-rejecting, float-rejecting
    decoder serves every caller-supplied document, so a collapsed duplicate key
    or an over-wide integer literal can never reach the closed record tables or
    ordinary decimal conversion. Integer *bit* width is then enforced exactly by
    the record tables.
    """
    text = _strict_submission_bytes(data, transport, label)
    return _strict_loads(text, transport.max_digits(), label)


def campaign_session_from_payload(payload: object, *, transport: TransportPolicy,
                                  topology: cl.Topology | None = None,
                                  policy: cl.Policy | None = None) -> CampaignSession:
    """Build a fresh M60a session from caller-supplied typed admission JSON.

    ``policy``/``topology`` may be supplied programmatically instead of inside
    ``payload``; each configuration record must come from exactly one source.
    """
    _validate_transport(transport)
    budget = _Budget(transport.max_records)
    _require(type(payload) is dict, "admission must be a JSON object")
    inline = policy is None or topology is None
    expected = (("policy", "topology") + _ADMISSION_FIELDS) if inline else _ADMISSION_FIELDS
    _require(set(payload) == set(expected),
             f"admission fields must be exactly {sorted(expected)}")
    supplied_policy = (_decode_record(payload["policy"], "policy", _M60A_SCHEMA, transport,
                                     budget) if policy is None else policy)
    supplied_topology = (_decode_record(payload["topology"], "topology", _M60A_SCHEMA,
                                        transport, budget) if topology is None else topology)
    _require(type(supplied_policy) is cl.Policy, "an exact kernel Policy record is required")
    _require(type(supplied_topology) is cl.Topology,
             "an exact kernel Topology record is required")
    admission = _decode_record({name: payload[name] for name in _ADMISSION_FIELDS},
                               "admission", _M60A_SCHEMA, transport, budget)
    return create_campaign_session(policy=supplied_policy, topology=supplied_topology,
                                   campaign_id=admission.campaign_id, turn=admission.turn,
                                   staging=admission.staging, target=admission.target,
                                   soldiers=admission.soldiers, stocks=admission.stocks)


def memome_session_from_payload(payload: object, *, transport: TransportPolicy,
                                policy: mm.Policy | None = None) -> MemomeSession:
    """Build a fresh M68a session from caller-supplied typed admission JSON."""
    _validate_transport(transport)
    budget = _Budget(transport.max_records)
    _require(type(payload) is dict, "admission must be a JSON object")
    expected = (("policy", "genesis_turn", "participants") if policy is None
                else ("genesis_turn", "participants"))
    _require(set(payload) == set(expected),
             f"admission fields must be exactly {sorted(expected)}")
    supplied_policy = (_decode_record(payload["policy"], "policy", _M68A_SCHEMA, transport,
                                      budget) if policy is None else policy)
    _require(type(supplied_policy) is mm.Policy, "an exact kernel Policy record is required")
    genesis_turn = _check_width(_exact_int(payload["genesis_turn"], "genesis turn"),
                             "genesis turn", transport)
    _require(type(payload["participants"]) is list, "participants must be a JSON array")
    if len(payload["participants"]) > transport.max_history:
        raise TransportDomainError(
            f"{len(payload['participants'])} genesis participants exceed the "
            f"{transport.max_history}-entry transport subset")
    people = tuple(_decode_record(item, "participant", _M68A_SCHEMA, transport, budget)
                   for item in payload["participants"])
    for person in people:
        _bound_memome_participant(person, transport, "participants")
    return create_memome_session(policy=supplied_policy, genesis_turn=genesis_turn,
                                 participants=people)


def campaign_tick_from_payload(payload: object, *,
                               transport: TransportPolicy) -> cl.Tick:
    """Decode exactly one explicit M60a tick from caller-supplied JSON."""
    _validate_transport(transport)
    tick = _decode_record(payload, "tick", _M60A_SCHEMA, transport,
                          _Budget(transport.max_records))
    _require(type(tick) is cl.Tick, "exact kernel Tick record required")
    return tick


def memome_batch_from_payload(payload: object, *,
                              transport: TransportPolicy) -> mm.Batch:
    """Decode exactly one explicit M68a batch from caller-supplied JSON."""
    _validate_transport(transport)
    batch = _decode_record(payload, "batch", _M68A_SCHEMA, transport,
                           _Budget(transport.max_records))
    _require(type(batch) is mm.Batch, "exact kernel Batch record required")
    return batch


# --------------------------------------------------------------- batch / tick


def apply_campaign_tick(session: CampaignSession, tick: cl.Tick) -> ApplyResult:
    """Submit exactly one explicit M60a tick.

    An identical historical tick returns the kernel's original receipt and
    leaves the session object, cursor and history untouched. Every kernel
    rejection is atomic and leaves the caller's session unchanged.
    """
    _validate_campaign_session(session)
    _require(type(tick) is cl.Tick, "an exact kernel Tick record is required")
    before = session.session
    result = cl.advance(before, policy=session.policy, topology=session.topology, tick=tick)
    if tick.turn <= before.state.turn:
        index = tick.turn - before.state.admission_turn - 1
        _require_integrity(result.session is before,
                           "a replayed tick must return the unchanged session object")
        _require_integrity(0 <= index < len(session.history)
                           and session.history[index] == result.receipt.inputs,
                           "a replayed tick must match the retained admitted input")
        return ApplyResult(session, False, before.state.turn, True, (result.receipt,))
    advanced = CampaignSession(session.policy, session.topology, session.admission,
                               session.history + (result.receipt.inputs,), result.session)
    _validate_campaign_session(advanced)
    return ApplyResult(advanced, True, result.session.state.turn, False, (result.receipt,))


def apply_memome_batch(session: MemomeSession, batch: mm.Batch) -> ApplyResult:
    """Submit exactly one explicit M68a batch.

    The kernel returns a historical prefix when an older turn is replayed. That
    prefix is used as a receipt view only: the latest ledger, its admitted
    history and the persisted generation are never replaced by it. The replay is
    matched against the kernel's own canonical admitted batch, so the caller's
    original proposal order is accepted exactly as the kernel canonicalizes it.
    A contradictory replay raises and writes nothing.
    """
    _validate_memome_session(session)
    _require(type(batch) is mm.Batch, "an exact kernel Batch record is required")
    result = mm.advance(session.ledger, batch, session.policy, enabled=True)
    if result.replayed:
        index = batch.turn - session.genesis_turn - 1
        _require(0 <= index < len(session.batches),
                 "a replayed batch must already be admitted in this session")
        admitted = result.ledger.history[index].batch
        _require(session.ledger.history[index].batch == admitted,
                 "the retained kernel history disagrees with the replayed batch")
        _require(session.batches[index] == admitted,
                 "a replayed batch must match the retained admitted batch")
        _require(session.ledger.history[index].receipts == result.receipts,
                 "historical receipts disagree with the retained kernel history")
        return ApplyResult(session, False, session.ledger.turn, True, result.receipts)
    admitted = MemomeSession(result.ledger.policy, session.genesis_turn, session.genesis,
                             session.batches + (result.ledger.history[-1].batch,),
                             result.ledger)
    _validate_memome_session(admitted)
    return ApplyResult(admitted, True, result.ledger.turn, False, result.receipts)


# ------------------------------------------------------------------- payloads


def _campaign_payload(session: CampaignSession, transport: TransportPolicy,
                      budget: _Budget) -> tuple[str, str, str, int]:
    _validate_campaign_session(session)
    if len(session.history) > transport.max_history:
        raise TransportDomainError(
            f"committed history exceeds the {transport.max_history}-turn transport limit")
    genesis = _canonical_json({
        "policy": _encode_record(session.policy, "policy", _M60A_SCHEMA, transport, budget),
        "topology": _encode_record(session.topology, "topology", _M60A_SCHEMA, transport,
                                   budget),
        "admission": _encode_record(session.admission, "admission", _M60A_SCHEMA, transport,
                                    budget),
    })
    history = _canonical_json([_encode_record(tick, "tick", _M60A_SCHEMA, transport, budget)
                               for tick in session.history])
    latest = _canonical_json({
        "state": _encode_record(session.session.state, "state", _M60A_SCHEMA, transport,
                                budget),
        "cursor": _encode_record(session.session.cursor, "cursor", _M60A_SCHEMA, transport,
                                 budget),
    })
    return genesis, history, latest, session.session.state.turn


def _bound_memome_participant(person: object, transport: TransportPolicy, label: str) -> None:
    """Bit-bound one persisted M68a participant, including all eight slot traits."""
    _require(type(person) is mm.Participant, "exact participant record required")
    _exact_name(person.agent_id, "agent id")
    _require(type(person.slots) is tuple, "slots must be an immutable tuple")
    _require(len(person.slots) == 8, "exactly eight slots required")
    for slot, trait in enumerate(person.slots):
        _check_width(_exact_int(trait, f"{label} slot trait"), f"{label}.slot{slot}",
                     transport)
    _check_width(_exact_int(person.prestige, "prestige", minimum=1),
                 f"{label}.{person.agent_id}.prestige", transport)


def _bound_memome_ledger(ledger: object, transport: TransportPolicy) -> None:
    """Bit-bound every integer the reused M68a checkpoint persists.

    This includes the kernel's own derived receipt weights and thresholds, which
    can exceed the width of any input: two 121-bit prestige values produce a
    122-bit electorate weight. Nothing here calls the kernel, and the check runs
    before any decimal conversion in both directions.
    """
    _require(type(ledger) is mm.Ledger, "exact kernel Ledger record required")
    _check_width(_exact_int(ledger.genesis_turn, "genesis turn"), "genesis turn", transport)
    for person in ledger.genesis:
        _bound_memome_participant(person, transport, "genesis")
    for index, tick in enumerate(ledger.history):
        _require(type(tick) is mm.Tick, "exact kernel Tick record required")
        for person in tick.participants:
            _bound_memome_participant(person, transport, f"history[{index}]")
        _check_width(_exact_int(tick.batch.turn, "batch turn"), f"history[{index}].turn",
                     transport)
        for proposal in tick.batch.proposals:
            _require(type(proposal) is mm.Proposal, "exact proposal record required")
            for field in ("slot", "candidate", "draw"):
                _check_width(_exact_int(getattr(proposal, field), field),
                             f"history[{index}].proposal.{field}", transport)
        for position, receipt in enumerate(tick.receipts):
            _require(type(receipt) is mm.Receipt, "exact receipt record required")
            for field in ("slot", "previous", "candidate", "draw", "candidate_weight",
                          "electorate_weight", "threshold"):
                _check_width(_exact_int(getattr(receipt, field), field),
                             f"history[{index}].receipt[{position}].{field}", transport)


def _charge_memome_ledger(ledger: mm.Ledger, budget: _Budget) -> None:
    """Charge every record the reused kernel checkpoint persists to the budget."""
    budget.take("kernel_policy")
    budget.take("kernel_ledger")
    if ledger.policy is not None:
        budget.take("kernel_ledger_policy")
    for person in ledger.genesis:
        budget.take("kernel_genesis_participant")
    for tick in ledger.history:
        budget.take("kernel_tick")
        budget.take("kernel_batch")
        for _proposal in tick.batch.proposals:
            budget.take("kernel_proposal")
        for _person in tick.participants:
            budget.take("kernel_tick_participant")
        for _receipt in tick.receipts:
            budget.take("kernel_receipt")


def _memome_payload(session: MemomeSession, transport: TransportPolicy,
                    budget: _Budget) -> tuple[str, str, str, int]:
    _validate_memome_session(session)
    if len(session.batches) > transport.max_history:
        raise TransportDomainError(
            f"committed history exceeds the {transport.max_history}-turn transport limit")
    if len(session.genesis) > transport.max_history:
        raise TransportDomainError(
            f"{len(session.genesis)} genesis participants exceed the "
            f"{transport.max_history}-entry transport subset")
    _bound_memome_ledger(session.ledger, transport)
    _charge_memome_ledger(session.ledger, budget)
    genesis = _canonical_json({
        "genesis_turn": _check_width(_exact_int(session.genesis_turn, "genesis turn"),
                                     "genesis turn", transport),
        "participants": [_encode_record(person, "participant", _M68A_SCHEMA, transport,
                                        budget) for person in session.genesis],
        "policy": _encode_record(session.policy, "policy", _M68A_SCHEMA, transport, budget),
    })
    history = _canonical_json([_encode_record(batch, "batch", _M68A_SCHEMA, transport, budget)
                               for batch in session.batches])
    latest = _canonical_json({"checkpoint": mm.checkpoint_json(session.ledger, session.policy)})
    return genesis, history, latest, session.ledger.turn


def _payload_text(session: CampaignSession | MemomeSession, transport: TransportPolicy,
                  budget: _Budget) -> tuple[str, str, str]:
    if type(session) is CampaignSession:
        genesis, history, latest, _ = _campaign_payload(session, transport, budget)
    elif type(session) is MemomeSession:
        genesis, history, latest, _ = _memome_payload(session, transport, budget)
    else:
        raise SessionError("unknown session record")
    return genesis, history, latest


def session_digest(session: CampaignSession | MemomeSession,
                   transport: TransportPolicy) -> str:
    """Canonical digest of the complete persisted payload for one session."""
    genesis, history, latest = _payload_text(session, transport, _Budget(transport.max_records))
    return _digest_text(_canonical_json({"genesis": genesis, "history": history,
                                         "latest": latest}))


# -------------------------------------------------------------------- envelope


def _build_envelope(session: CampaignSession | MemomeSession, transport: TransportPolicy,
                    generation: int) -> Envelope:
    _check_width(_exact_int(generation, "generation", minimum=1), "generation", transport)
    budget = _Budget(transport.max_records)
    if type(session) is CampaignSession:
        kernel, kernel_contract = "m60a", KERNEL_CONTRACTS["m60a"]
    elif type(session) is MemomeSession:
        kernel, kernel_contract = "m68a", KERNEL_CONTRACTS["m68a"]
    else:
        raise SessionError("unknown session record")
    genesis, history, latest, turn = (_campaign_payload(session, transport, budget)
                                      if kernel == "m60a"
                                      else _memome_payload(session, transport, budget))
    _check_width(_exact_int(turn, "turn"), "turn", transport)
    payload_digest = _digest_text(_canonical_json({"genesis": genesis, "history": history,
                                                    "latest": latest}))
    return Envelope(CONTRACT, ENVELOPE_VERSION, kernel, kernel_contract,
                    BASELINE_SOURCE_HEAD, BASELINE_SOURCE_TREE, transport, generation,
                    turn, genesis, history, latest, _digest_text(genesis),
                    _digest_text(history), _digest_text(latest), payload_digest)


def encode_session(session: CampaignSession | MemomeSession, *, transport: TransportPolicy,
                   generation: int) -> Envelope:
    """Encode, bound and self-verify one session envelope.

    The proposed envelope is decoded again and the complete reconstructed
    session is compared with the caller's session, so a successful return means
    the bytes on the way to disk describe the caller's exact reviewed state.
    """
    _validate_transport(transport)
    envelope = _build_envelope(session, transport, generation)
    encode_envelope_text(envelope, transport)
    restored = decode_envelope(envelope)
    _require_integrity(session_digest(restored, transport) == envelope.session_digest,
                       "self-verified reconstruction disagrees with the encoded envelope")
    return envelope


def decode_envelope(envelope: Envelope) -> CampaignSession | MemomeSession:
    """Validate identity, digests, whitelisted records and the kernel reconstruction."""
    _require(type(envelope) is Envelope, "exact Envelope record required")
    transport = _validate_transport(envelope.transport)
    # Exact scalar types are checked before any equality or membership test, so
    # a malformed file raises a session error instead of an incidental TypeError.
    _exact_name(envelope.contract, "contract")
    _exact_int(envelope.envelope_version, "envelope version")
    _exact_name(envelope.kernel, "kernel")
    _exact_name(envelope.kernel_contract, "kernel contract")
    _exact_name(envelope.source_head, "source head")
    _exact_name(envelope.source_tree, "source tree")
    _require_contract(envelope.contract == CONTRACT, "unsupported session contract")
    _require_contract(envelope.envelope_version == ENVELOPE_VERSION,
                      "unsupported envelope version")
    _require_contract(envelope.kernel in KERNEL_CONTRACTS, "unsupported kernel identity")
    _require_contract(envelope.kernel_contract == KERNEL_CONTRACTS[envelope.kernel],
                      "kernel contract does not match the selected kernel")
    _require_contract(envelope.source_head == BASELINE_SOURCE_HEAD
                      and envelope.source_tree == BASELINE_SOURCE_TREE,
                      "session source identity does not match the reviewed baseline")
    _check_width(_exact_int(envelope.generation, "generation", minimum=1),
                 "generation", transport)
    _check_width(_exact_int(envelope.turn, "turn"), "turn", transport)
    for name in ("genesis", "history", "latest"):
        _exact_name(getattr(envelope, name), name)
    _require_integrity(envelope.genesis_digest == _digest_text(envelope.genesis),
                       "genesis digest mismatch")
    _require_integrity(envelope.history_digest == _digest_text(envelope.history),
                       "history digest mismatch")
    _require_integrity(envelope.latest_digest == _digest_text(envelope.latest),
                       "latest digest mismatch")
    _require_integrity(envelope.session_digest == _digest_text(_canonical_json(
        {"genesis": envelope.genesis, "history": envelope.history, "latest": envelope.latest})),
        "session digest mismatch")
    # The public record decoder obeys the same encoded byte cap as file reads.
    encode_envelope_text(envelope, transport)
    if envelope.kernel == "m60a":
        return _reconstruct_campaign(envelope, transport)
    return _reconstruct_memome(envelope, transport)


def _reconstruct_campaign(envelope: Envelope, transport: TransportPolicy) -> CampaignSession:
    """Restore M60a by public admit plus public advance, then compare everything."""
    budget = _Budget(transport.max_records)
    digits = transport.max_digits()
    genesis = _payload_object(_strict_loads(envelope.genesis, digits, "genesis"),
                              "genesis", _CAMPAIGN_GENESIS_FIELDS)
    policy = _decode_record(genesis["policy"], "policy", _M60A_SCHEMA, transport, budget)
    topology = _decode_record(genesis["topology"], "topology", _M60A_SCHEMA, transport, budget)
    admission = _decode_record(genesis["admission"], "admission", _M60A_SCHEMA, transport,
                               budget)
    history = _strict_loads(envelope.history, digits, "history")
    _require(type(history) is list, "history must be a JSON array")
    if len(history) > transport.max_history:
        raise TransportDomainError(
            f"committed history exceeds the {transport.max_history}-turn transport limit")
    ticks = tuple(_decode_record(item, "tick", _M60A_SCHEMA, transport, budget)
                  for item in history)
    latest = _payload_object(_strict_loads(envelope.latest, digits, "latest"),
                             "latest", _CAMPAIGN_LATEST_FIELDS)
    state = _decode_record(latest["state"], "state", _M60A_SCHEMA, transport, budget)
    cursor = _decode_record(latest["cursor"], "cursor", _M60A_SCHEMA, transport, budget)
    saved = cl.Session(state, cursor)

    rebuilt = cl.admit(policy=policy, topology=topology, campaign_id=admission.campaign_id,
                       turn=admission.turn, staging=admission.staging,
                       target=admission.target, soldiers=admission.soldiers,
                       stocks=admission.stocks)
    for tick in ticks:
        rebuilt = cl.advance(rebuilt, policy=policy, topology=topology, tick=tick).session
    _require_integrity(cl.canonical_bytes(rebuilt) == cl.canonical_bytes(saved),
                       "reconstructed campaign session disagrees with persisted state, "
                       "cursor and receipts")
    _require_integrity(rebuilt.state.turn == envelope.turn,
                       "envelope turn disagrees with the reconstructed campaign state")
    session = CampaignSession(policy, topology, admission, ticks, saved)
    _validate_campaign_session(session)
    return session


def _reconstruct_memome(envelope: Envelope, transport: TransportPolicy) -> MemomeSession:
    """Restore M68a with the kernel's own checkpoint decoder, then cross-check."""
    budget = _Budget(transport.max_records)
    digits = transport.max_digits()
    genesis = _payload_object(_strict_loads(envelope.genesis, digits, "genesis"),
                              "genesis", _MEMOME_GENESIS_FIELDS)
    genesis_turn = _exact_int(genesis["genesis_turn"], "genesis turn")
    _require(type(genesis["participants"]) is list,
             "genesis participants must be a JSON array")
    if len(genesis["participants"]) > transport.max_history:
        raise TransportDomainError(
            f"{len(genesis['participants'])} genesis participants exceed the "
            f"{transport.max_history}-entry transport subset")
    participants = tuple(_decode_record(item, "participant", _M68A_SCHEMA, transport, budget)
                         for item in genesis["participants"])
    policy = _decode_record(genesis["policy"], "policy", _M68A_SCHEMA, transport, budget)
    history = _strict_loads(envelope.history, digits, "history")
    _require(type(history) is list, "history must be a JSON array")
    if len(history) > transport.max_history:
        raise TransportDomainError(
            f"committed history exceeds the {transport.max_history}-turn transport limit")
    batches = tuple(_decode_record(item, "batch", _M68A_SCHEMA, transport, budget)
                    for item in history)
    latest = _payload_object(_strict_loads(envelope.latest, digits, "latest"),
                             "latest", _MEMOME_LATEST_FIELDS)
    checkpoint = _exact_name(latest["checkpoint"], "latest.checkpoint")
    if len(checkpoint.encode("utf-8")) > transport.max_bytes:
        raise TransportDomainError(
            f"the session file exceeds the {transport.max_bytes}-byte transport limit")

    # Check nested literal transport bounds before the kernel's decimal parser.
    # Reconstruction and checkpoint semantics remain with the public kernel API.
    _strict_loads(checkpoint, digits, "kernel checkpoint")
    ledger, kernel_policy = mm.restore_checkpoint(checkpoint)
    # The kernel replay is authoritative; bound and charge every integer and
    # record it re-derived, including the receipts it recomputed from genesis.
    _bound_memome_ledger(ledger, transport)
    _charge_memome_ledger(ledger, budget)
    _require_integrity(kernel_policy == policy,
                       "the kernel checkpoint policy disagrees with the session policy")
    _require_integrity(ledger.genesis_turn == genesis_turn,
                       "the kernel checkpoint genesis turn disagrees with the session "
                       "genesis turn")
    _require_integrity(ledger.genesis == participants,
                       "the kernel checkpoint genesis roster disagrees with the session "
                       "genesis roster")
    _require_integrity(tuple(tick.batch for tick in ledger.history) == batches,
                       "the kernel checkpoint history disagrees with the admitted batches")
    _require_integrity(ledger.turn == envelope.turn,
                       "envelope turn disagrees with the memome ledger")
    session = MemomeSession(policy, genesis_turn, participants, batches, ledger)
    _validate_memome_session(session)
    return session


def encode_envelope_text(envelope: Envelope, transport: TransportPolicy) -> bytes:
    """Canonical file bytes for one envelope, bounded by the transport policy."""
    _require(type(envelope) is Envelope, "exact Envelope record required")
    _validate_transport(transport)
    _require_contract(envelope.transport == transport,
                      "the envelope transport policy differs from the requested policy")
    text = _canonical_json(envelope.as_payload()) + "\n"
    data = text.encode("utf-8")
    if len(data) > transport.max_bytes:
        raise TransportDomainError(
            f"the session file exceeds the {transport.max_bytes}-byte transport limit")
    return data


def decode_envelope_text(data: bytes, transport: TransportPolicy) -> Envelope:
    """Decode file bytes with strict identity, digest and limit checks."""
    _validate_transport(transport)
    _require(type(data) is bytes, "session bytes required")
    if len(data) > transport.max_bytes:
        raise TransportDomainError(
            f"the session file exceeds the {transport.max_bytes}-byte transport limit")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SessionError("the session file is not valid UTF-8") from exc
    payload = _strict_loads(text, transport.max_digits(), "envelope")
    _require(type(payload) is dict and set(payload) == set(_ENVELOPE_FIELDS),
             f"envelope fields must be exactly {sorted(_ENVELOPE_FIELDS)}")
    # Decode the stored policy through exact typed validation before comparing it:
    # a boolean or string bound must not alias an equal integer through True == 1.
    stored = transport_policy_from_payload(payload["transport"])
    _require_contract(stored == transport,
                      "the envelope transport policy differs from the requested policy")
    values = dict(payload)
    values["transport"] = stored
    envelope = Envelope(**values)
    _require_contract(envelope.envelope_version == ENVELOPE_VERSION,
                      "unsupported envelope version")
    return envelope


# ---------------------------------------------------------------- persistence


def read_regular_file_bytes(path: str | os.PathLike, *, max_bytes: int,
                            label: str) -> bytes:
    """Read at most ``max_bytes + 1`` from one nonblocking regular-file descriptor.

    Type is checked on the opened descriptor, so a path substituted with a FIFO
    cannot block between a metadata check and open. Read symlinks keep their
    existing behavior. Ordinary open/read errors propagate unchanged.
    """
    _exact_int(max_bytes, "maximum file bytes", minimum=1)
    _require(max_bytes <= MAX_TRANSPORT_BYTES, "maximum file bytes exceeds transport domain")
    _exact_name(label, "file label")
    if not hasattr(os, "O_NONBLOCK"):
        raise UnsupportedPlatformError("bounded regular-file reads require nonblocking open")
    flags = os.O_RDONLY | os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags)
    try:
        handle = open(descriptor, "rb", closefd=True)
    except BaseException:
        os.close(descriptor)
        raise
    with handle:
        mode = os.fstat(handle.fileno()).st_mode
        if stat.S_ISDIR(mode):
            raise IsADirectoryError(f"the {label} is a directory: {path}")
        if not stat.S_ISREG(mode):
            raise SessionError(f"the {label} must be a regular file")
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise TransportDomainError(f"the {label} exceeds the {max_bytes}-byte transport limit")
    return raw


def _read_session_bytes(target: Path, transport: TransportPolicy) -> bytes:
    return read_regular_file_bytes(target, max_bytes=transport.max_bytes, label="session file")


def _require_destination_shape(target: Path) -> None:
    """The destination must be absent or a regular file, never a link or directory."""
    if target.is_symlink():
        raise PersistenceError("the session destination must not be a symbolic link")
    if target.exists():
        try:
            mode = os.lstat(target).st_mode
        except OSError as exc:
            raise PersistenceError(
                f"the session destination could not be inspected: {exc}") from exc
        if not stat.S_ISREG(mode):
            raise PersistenceError(
                "the session destination must be a regular file, not a directory")


def _require_supported_platform(target: Path) -> None:
    """Fail before any mutation when local durable writes are unsupported."""
    if not (os.name == "posix" and fcntl is not None
            and hasattr(os, "fsync") and hasattr(os, "replace")
            and hasattr(os, "O_DIRECTORY")):
        raise UnsupportedPlatformError(
            "local durable session files require a POSIX filesystem with an advisory "
            "lock, fsync, atomic replace and directory handles")
    if not target.parent.is_dir():
        raise PersistenceError(f"the session directory {str(target.parent)!r} does not exist")
    _require_destination_shape(target)


def _lock_path(target: Path) -> Path:
    return target.parent / f".{target.name}.lock"


@contextmanager
def _exclusive_lock(lock_path: Path):
    """Exclusive advisory lock on a private regular-file sibling.

    ``O_NOFOLLOW`` and the regular-file recheck refuse a lock path that is or
    becomes a link, so a substituted name cannot redirect the lock.
    """
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        # A link or a non-regular lock name is refused here, before any commit.
        raise PersistenceError(
            f"the session writer lock could not be opened: {exc}") from exc
    primary = None
    locked = False
    cleanup = None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PersistenceError("the session writer lock must be a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        yield
    except BaseException as exc:
        primary = exc
        raise
    finally:
        if locked:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError as exc:
                cleanup = exc
        try:
            os.close(descriptor)
        except OSError as exc:
            if cleanup is None:
                cleanup = exc
            else:
                cleanup.add_note(f"writer lock close also failed: {exc}")
        if cleanup is not None:
            if primary is not None:
                primary.add_note(f"writer lock cleanup also failed: {cleanup}")
                for note in getattr(cleanup, "__notes__", ()):
                    primary.add_note(note)
            else:
                raise _CleanupFailure(cleanup) from cleanup


def _create_temp_file(target: Path) -> tuple[int, Path]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for attempt in range(64):
        candidate = target.parent / f".{target.name}.{os.getpid()}.{attempt}.tmp"
        try:
            return os.open(candidate, flags, 0o600), candidate
        except FileExistsError:
            continue
    raise PersistenceError(f"could not create a unique temporary file beside {target}")


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    primary = None
    try:
        os.fsync(descriptor)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if primary is not None:
                primary.add_note(f"directory close also failed: {exc}")
            else:
                raise _CleanupFailure(exc) from exc


def _replace_durably(target: Path, data: bytes) -> None:
    """Write and fsync a temporary file, replace atomically, then fsync the directory."""
    temp_path = None
    try:
        descriptor, temp_path = _create_temp_file(target)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # A destination that became a link between the locked check and the
        # replace is refused rather than followed.
        _require_destination_shape(target)
        os.replace(temp_path, target)
        temp_path = None
    except OSError as exc:
        raise PersistenceError(
            f"the session write failed before the destination changed: {exc}") from exc
    finally:
        # A refused shape change is a PersistenceError raised above; it must pass
        # through unchanged, so only OSError is translated here.
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:  # pragma: no cover - temporary cleanup is best effort only
                pass
    try:
        _fsync_directory(target.parent)
    except OSError as exc:
        raise DurabilityUncertain(
            "the session bytes were replaced but the parent directory could not be "
            f"fsynced ({exc}); the new content may already be visible, so read the file "
            "back and reconcile it before retrying") from exc


def _require_expected(target: Path, expected_generation: int | None,
                      expected_digest: str | None, transport: TransportPolicy) -> None:
    exists = target.exists()
    if expected_generation is None:
        if exists:
            raise StaleGenerationError(
                "the session destination already exists; an absent session was expected")
        _require(expected_digest is None, "an absent session has no digest")
        return
    _exact_int(expected_generation, "expected generation", minimum=1)
    _require(type(expected_digest) is str and len(expected_digest) == 64,
             "a 64-character expected digest is required")
    if not exists:
        raise StaleGenerationError(
            "the session destination is absent while a committed generation was expected")
    raw = _read_session_bytes(target, transport)
    if _digest_bytes(raw) != expected_digest:
        raise StaleGenerationError(
            "the session destination digest differs from the expected digest")
    current = decode_envelope_text(raw, transport)
    if current.generation != expected_generation:
        raise StaleGenerationError(
            f"the session destination generation {current.generation} differs from the "
            f"expected {expected_generation}")


def commit_session(path: str | os.PathLike, session: CampaignSession | MemomeSession, *,
                   transport: TransportPolicy, expected_generation: int | None,
                   expected_digest: str | None) -> CommitResult:
    """Commit one session with a single writer and an explicit generation check.

    Order is exactly :data:`SESSION_COMMIT_ORDER`. A failure before the atomic
    replace raises :class:`PersistenceError` with the prior bytes intact. A
    failure of the parent-directory fsync raises :class:`DurabilityUncertain`,
    which forbids any claim about the previous content and requires readback.
    Cleanup failure after the commit gate raises :class:`CommittedCleanupError`
    with the completed result; this outcome never authorizes an automatic retry.
    """
    _validate_transport(transport)
    target = Path(path)
    _require_supported_platform(target)
    completed = None
    try:
        with _exclusive_lock(_lock_path(target)):
            # Recheck the destination under the lock before validation/publication.
            _require_destination_shape(target)
            _require_expected(target, expected_generation, expected_digest, transport)
            generation = 1 if expected_generation is None else expected_generation + 1
            envelope = encode_session(session, transport=transport, generation=generation)
            data = encode_envelope_text(envelope, transport)
            result = CommitResult(str(target), envelope.generation, envelope.turn,
                                  _digest_bytes(data), envelope)
            try:
                _replace_durably(target, data)
            except _CleanupFailure:
                # Only directory close after successful directory fsync emits this.
                completed = result
                raise
            completed = result
    except _CleanupFailure as exc:
        if completed is not None:
            error = CommittedCleanupError(completed, exc.error)
            for note in getattr(exc, "__notes__", ()):
                error.add_note(note)
            raise error from exc.error
        raise PersistenceError(f"session cleanup failed before publication: {exc.error}") from exc.error
    return completed


def load_session(path: str | os.PathLike, *,
                 transport: TransportPolicy) -> LoadedSession:
    """Read a session and reconstruct it from public kernel replay.

    No lock is taken and no byte is written: reading never mutates the file, and
    a successful read is already a verified resume of the committed history.
    """
    _validate_transport(transport)
    target = Path(path)
    raw = _read_session_bytes(target, transport)
    envelope = decode_envelope_text(raw, transport)
    session = decode_envelope(envelope)
    return LoadedSession(str(target), envelope.generation, envelope.turn,
                         _digest_bytes(raw), envelope, session)


# ------------------------------------------------------------------- reporting


def session_report(loaded: LoadedSession) -> dict:
    """Primitive-only summary of the latest committed state and receipts."""
    session = loaded.session
    common = {
        "contract": CONTRACT,
        "source_head": loaded.envelope.source_head,
        "generation": loaded.generation,
        "turn": loaded.turn,
        "file_digest": loaded.digest,
        "session_digest": loaded.envelope.session_digest,
        "history_length": len(session.history if type(session) is CampaignSession
                              else session.batches),
        "transport": loaded.envelope.transport.as_payload(),
        "commit_order": list(SESSION_COMMIT_ORDER),
    }
    if type(session) is CampaignSession:
        state = session.session.state
        receipts = session.session.cursor.receipts
        latest = receipts[-1] if receipts else None
        common.update({
            "kernel": "m60a",
            "kernel_contract": KERNEL_CONTRACTS["m60a"],
            "campaign_id": state.campaign_id,
            "admission_turn": state.admission_turn,
            "phase": state.phase,
            "staging": state.staging,
            "target": state.target,
            "roster": [{"agent_id": soldier.agent_id, "region": soldier.region,
                        "rations": soldier.rations, "morale": soldier.morale,
                        "status": soldier.status} for soldier in state.soldiers],
            "stocks": [{"region": stock.region, "rations": stock.rations}
                       for stock in state.stocks],
            "food": {"initial": state.initial_food, "credited": state.credited_food,
                     "consumed": state.consumed_food, "deserted": state.deserted_food},
            "turn_index": [{"turn": receipt.turn,
                            "phase": [receipt.phase_before, receipt.phase_after],
                            "state_after_digest": receipt.state_after_digest,
                            "counts_after": {
                                "active": receipt.counts_after.active,
                                "arrived_active": receipt.counts_after.arrived_active,
                                "returned": receipt.counts_after.returned,
                                "deserted": receipt.counts_after.deserted},
                            "consumed_food": receipt.food.consumed}
                           for receipt in receipts],
            "latest_receipt": None if latest is None else {
                "turn": latest.turn,
                "payload_digest": latest.payload_digest,
                "state_before_digest": latest.state_before_digest,
                "state_after_digest": latest.state_after_digest,
                "orders": [{"order_id": order.order_id, "turn": order.turn,
                            "kind": order.kind, "quantity": order.quantity}
                           for order in latest.orders],
                "credits": [{"source_id": credit.source_id, "region": credit.region,
                             "rations": credit.rations} for credit in latest.credits],
                "replenishments": [{"order_id": item.order_id, "agent_id": item.agent_id,
                                    "requested": item.requested, "granted": item.granted,
                                    "reason": item.reason}
                                   for item in latest.replenishments],
                "members": [{"agent_id": member.agent_id,
                             "region": [member.region_before, member.region_after],
                             "status": [member.status_before, member.status_after],
                             "rations": [member.ration_before, member.ration_after],
                             "consumed": member.consumed,
                             "morale": [member.morale_before, member.morale_after],
                             "reasons": list(member.reasons)} for member in latest.members],
                "reasons": list(latest.reasons)},
        })
        return common
    ledger = session.ledger
    latest_tick = ledger.history[-1] if ledger.history else None
    common.update({
        "kernel": "m68a",
        "kernel_contract": KERNEL_CONTRACTS["m68a"],
        "genesis_turn": ledger.genesis_turn,
        "participants": [{"agent_id": person.agent_id, "group": person.group,
                          "prestige_bits": person.prestige.bit_length(),
                          "slots": list(person.slots)} for person in ledger.participants],
        "turn_index": [{"turn": tick.batch.turn,
                        "proposals": [proposal.proposal_id
                                      for proposal in tick.batch.proposals],
                        "reasons": [receipt.reason for receipt in tick.receipts]}
                       for tick in ledger.history],
        "latest_receipt": None if latest_tick is None else [
            {"proposal_id": receipt.proposal_id, "recipient": receipt.recipient,
             "slot": receipt.slot, "previous": receipt.previous,
             "candidate": receipt.candidate, "draw": receipt.draw,
             "threshold": receipt.threshold, "reason": receipt.reason}
            for receipt in latest_tick.receipts],
    })
    return common


__all__ = [
    "ApplyResult", "BASELINE_SOURCE_HEAD", "BASELINE_SOURCE_TREE", "CampaignAdmission",
    "CampaignSession", "CommitResult", "CommittedCleanupError", "CONTRACT", "ContractError", "DurabilityUncertain",
    "ENVELOPE_VERSION", "Envelope", "IntegrityError", "KERNEL_CONTRACTS", "LoadedSession",
    "MAX_TRANSPORT_INT_BITS", "MemomeSession", "PersistenceError", "SESSION_COMMIT_ORDER",
    "SUPPORTED_TRANSPORT_VERSIONS", "SessionError", "StaleGenerationError",
    "TransportDomainError", "TransportPolicy", "UnsupportedPlatformError",
    "apply_campaign_tick", "apply_memome_batch", "campaign_session_from_payload",
    "campaign_tick_from_payload", "commit_session", "create_campaign_session",
    "create_memome_session", "decode_envelope", "decode_envelope_text",
    "documented_transport_policy", "encode_envelope_text", "encode_session",
    "load_session", "read_regular_file_bytes", "memome_batch_from_payload", "memome_session_from_payload",
    "session_digest", "session_report", "session_turn", "submission_from_bytes",
    "transport_policy_from_payload", "transport_policy_from_text",
]
