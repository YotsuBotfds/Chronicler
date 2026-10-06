"""One explicit detached-session submission and read-only outcome reconciliation.

This composes the accepted public session APIs. It adds no retries, lock service,
rollback, lock deletion, or storage format. Original typed failures are raised
with an immutable ``operation_receipt`` describing the attempted operation.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import os

from chronicler import experiment_sessions as es


CONTRACT = "chronicler-session-operation-v1"


@dataclass(frozen=True)
class SessionIdentity:
    """Distinct exact-file and payload identities at one generation and turn."""

    generation: int
    file_digest: str
    session_digest: str
    turn: int

    def as_payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ErrorInfo:
    error_type: str
    detail: str


@dataclass(frozen=True)
class ReconcileExpectation:
    """Closed caller declaration binding one textual local target and version pair."""

    target: str
    transport: es.TransportPolicy
    kernel: str
    kernel_contract: str
    base: SessionIdentity
    intended: SessionIdentity | None

    def as_payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OperationReceipt:
    status: str
    path: str
    kernel: str | None
    base: SessionIdentity | None
    intended: SessionIdentity | None
    error: ErrorInfo | None = None
    transport: es.TransportPolicy | None = None
    kernel_contract: str | None = None

    @property
    def expectation(self) -> ReconcileExpectation | None:
        if self.base is None:
            return None
        return ReconcileExpectation(self.path, self.transport, self.kernel,
                                    self.kernel_contract, self.base, self.intended)

    def as_payload(self) -> dict:
        return {"contract": CONTRACT, **asdict(self), "expectation": (
            None if self.expectation is None else self.expectation.as_payload())}


@dataclass(frozen=True)
class ReconciliationReceipt:
    status: str
    path: str
    expectation: ReconcileExpectation
    current: SessionIdentity | None
    missing: bool
    error: ErrorInfo | None = None

    def as_payload(self) -> dict:
        return {"contract": CONTRACT, "writes": False, **asdict(self)}


def _error_info(error: Exception) -> ErrorInfo:
    return ErrorInfo(type(error).__name__, str(error))


def _loaded_identity(loaded: es.LoadedSession) -> SessionIdentity:
    return SessionIdentity(loaded.generation, loaded.digest,
                           loaded.envelope.session_digest, loaded.turn)


def _validate_identity(identity: object) -> SessionIdentity:
    if type(identity) is not SessionIdentity:
        raise es.SessionError("an exact SessionIdentity record is required")
    if type(identity.generation) is not int or identity.generation < 1:
        raise es.SessionError("identity generation must be an exact positive integer")
    if type(identity.turn) is not int or identity.turn < 0:
        raise es.SessionError("identity turn must be an exact nonnegative integer")
    for label in ("file_digest", "session_digest"):
        digest = getattr(identity, label)
        if (type(digest) is not str or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)):
            raise es.SessionError(f"identity {label} must be a lowercase SHA-256 digest")
    return identity


def identity_from_payload(payload: object) -> SessionIdentity:
    """Validate declared comparison identities; this does not authenticate them."""
    fields = {"generation", "file_digest", "session_digest", "turn"}
    if type(payload) is not dict or set(payload) != fields:
        raise es.SessionError(f"identity fields must be exactly {sorted(fields)}")
    return _validate_identity(SessionIdentity(**payload))


def _validate_transport(transport: object) -> es.TransportPolicy:
    if type(transport) is not es.TransportPolicy:
        raise es.SessionError("an exact TransportPolicy record is required")
    return es.transport_policy_from_payload(transport.as_payload())


def _validate_expectation(expectation: object) -> ReconcileExpectation:
    if type(expectation) is not ReconcileExpectation:
        raise es.SessionError("an exact ReconcileExpectation record is required")
    if type(expectation.target) is not str or not expectation.target:
        raise es.SessionError("expectation target must be an explicit nonempty text path")
    _validate_transport(expectation.transport)
    if (type(expectation.kernel) is not str or expectation.kernel not in es.KERNEL_CONTRACTS
            or type(expectation.kernel_contract) is not str
            or expectation.kernel_contract != es.KERNEL_CONTRACTS[expectation.kernel]):
        raise es.ContractError("expectation kernel and kernel contract must match")
    _validate_identity(expectation.base)
    if expectation.intended is not None:
        _validate_identity(expectation.intended)
        if expectation.intended.generation != expectation.base.generation + 1:
            raise es.SessionError("intended generation must equal base generation + 1")
        if expectation.intended.turn != expectation.base.turn + 1:
            raise es.SessionError("intended turn must equal base turn + 1")
    return expectation


def expectation_from_payload(payload: object) -> ReconcileExpectation:
    """Decode exact declared linkage without treating it as authentication."""
    fields = {"target", "transport", "kernel", "kernel_contract", "base", "intended"}
    if type(payload) is not dict or set(payload) != fields:
        raise es.SessionError(f"expectation fields must be exactly {sorted(fields)}")
    return _validate_expectation(ReconcileExpectation(
        payload["target"], es.transport_policy_from_payload(payload["transport"]),
        payload["kernel"], payload["kernel_contract"], identity_from_payload(payload["base"]),
        None if payload["intended"] is None else identity_from_payload(payload["intended"])))


def _require_derivation(loaded: es.LoadedSession, applied: es.ApplyResult) -> None:
    """Refuse a candidate belonging to another genesis or committed prefix."""
    before, after = loaded.session, applied.session
    if not applied.changed:
        if after != before or applied.turn != loaded.turn:
            raise es.IntegrityError("replay must retain the complete observed session")
        return
    if type(after) is not type(before) or applied.turn != loaded.turn + 1:
        raise es.IntegrityError("candidate must advance the observed kernel by one turn")
    if type(before) is es.CampaignSession:
        same_genesis = (before.policy, before.topology, before.admission) == (
            after.policy, after.topology, after.admission)
        same_prefix = (len(after.history) == len(before.history) + 1
                       and after.history[:-1] == before.history)
    else:
        same_genesis = (before.policy, before.genesis_turn, before.genesis) == (
            after.policy, after.genesis_turn, after.genesis)
        same_prefix = (len(after.batches) == len(before.batches) + 1
                       and after.batches[:-1] == before.batches)
    if not same_genesis or not same_prefix:
        raise es.IntegrityError("candidate must derive from the observed genesis and history")


def apply_operation(path: str | os.PathLike, *, transport: es.TransportPolicy,
                    submission: bytes) -> OperationReceipt:
    """Load, strictly parse and apply once; commit changed state exactly once.

    Success is either ``committed_durable`` (the existing commit gate completed)
    or ``replay_no_write``. Failures keep their original type and carry an
    ``operation_receipt`` with ``stale_conflict``, ``durability_uncertain`` or
    ``rejected`` or ``commit_outcome_unknown`` status. Identities are absent if their validation
    stage was not reached. Replays have no intended new generation. Receipts
    describe the observed/committed version, without promising current-head
    freshness. An intended digest is calculated before commit.
    """
    base = intended = None
    kernel = kernel_contract = checked_transport = None
    commit_attempted = False
    target = os.fspath(path)
    try:
        if type(target) is not str or not target:
            raise es.SessionError("target must be an explicit nonempty text path")
        checked_transport = _validate_transport(transport)
        loaded = es.load_session(path, transport=transport)
        base = _loaded_identity(loaded)
        kernel = loaded.envelope.kernel
        kernel_contract = loaded.envelope.kernel_contract
        payload = es.submission_from_bytes(submission, transport=transport,
                                           label="session operation submission")
        if type(loaded.session) is es.CampaignSession:
            tick = es.campaign_tick_from_payload(payload, transport=transport)
            applied = es.apply_campaign_tick(loaded.session, tick)
        elif type(loaded.session) is es.MemomeSession:
            batch = es.memome_batch_from_payload(payload, transport=transport)
            applied = es.apply_memome_batch(loaded.session, batch)
        else:  # The closed accepted envelope cannot currently reach this branch.
            raise es.SessionError("the loaded session uses an unsupported kernel")
        _require_derivation(loaded, applied)
        if not applied.changed:
            return OperationReceipt("replay_no_write", target, kernel, base, None,
                                    transport=checked_transport, kernel_contract=kernel_contract)
        envelope = es.encode_session(applied.session, transport=transport,
                                     generation=loaded.generation + 1)
        data = es.encode_envelope_text(envelope, transport)
        intended = SessionIdentity(envelope.generation, hashlib.sha256(data).hexdigest(),
                                   envelope.session_digest, envelope.turn)
        _validate_expectation(ReconcileExpectation(target, checked_transport, kernel,
                                                   kernel_contract, base, intended))
        # Materialize machine-readable fields before crossing the publication seam.
        receipt = OperationReceipt("committed_durable", target, kernel, base, intended,
                                   transport=checked_transport, kernel_contract=kernel_contract)
        receipt.as_payload()
        commit_attempted = True
        result = es.commit_session(path, applied.session, transport=transport,
                                   expected_generation=loaded.generation,
                                   expected_digest=loaded.digest)
        committed = SessionIdentity(result.generation, result.digest,
                                    result.envelope.session_digest, result.turn)
        if committed != intended:
            raise RuntimeError("commit returned identities different from the intended file")
        return receipt
    except Exception as error:
        if isinstance(error, es.CommittedCleanupError):
            result = error.result
            committed = SessionIdentity(result.generation, result.digest,
                                        result.envelope.session_digest, result.turn)
            # Only the exact attempted publication can prove this operation durable.
            matches = (commit_attempted and committed == intended and result.path == target
                       and result.envelope == envelope)
            status = "committed_durable" if matches else "commit_outcome_unknown"
            if not matches:
                error.add_note("completed publication metadata differs from this operation's intended identity")
        elif isinstance(error, es.DurabilityUncertain):
            status = "durability_uncertain"
        elif isinstance(error, es.StaleGenerationError):
            status = "stale_conflict"
        elif commit_attempted and not isinstance(error, es.SessionError):
            # Unexpected commit exceptions provide no confirmed phase/identity,
            # so they cannot prove no write or completion of the durable gate.
            status = "commit_outcome_unknown"
        else:
            status = "rejected"
        error.operation_receipt = OperationReceipt(
            status, target, kernel, base, intended, _error_info(error),
            checked_transport, kernel_contract)
        raise


def reconcile_operation(path: str | os.PathLike, *, transport: es.TransportPolicy,
                        expectation: ReconcileExpectation) -> ReconciliationReceipt:
    """Observe one fully validated file, without writing or authorizing a retry.

    A visible intended file never proves a failed directory fsync completed.
    Invalid declared identities/policies raise before reading. Read/replay errors
    are observations with their original error type and explicit missing flag.
    """
    _validate_expectation(expectation)
    _validate_transport(transport)
    target = os.fspath(path)
    if type(target) is not str or target != expectation.target:
        raise es.SessionError("target must exactly match the declared expectation path")
    if transport != expectation.transport:
        raise es.ContractError("transport must match the declared expectation policy")
    try:
        loaded = es.load_session(path, transport=transport)
    except (es.SessionError, ValueError, OSError) as error:
        return ReconciliationReceipt(
            "unreadable_or_invalid", target, expectation, None,
            isinstance(error, FileNotFoundError), _error_info(error))
    current = _loaded_identity(loaded)
    same_kernel = ((loaded.envelope.kernel, loaded.envelope.kernel_contract)
                   == (expectation.kernel, expectation.kernel_contract))
    if same_kernel and expectation.intended is not None and current == expectation.intended:
        status = "intended_visible_durability_unknown"
    elif same_kernel and current == expectation.base:
        status = "base_visible"
    else:
        status = "different_valid_file"
    return ReconciliationReceipt(status, target, expectation, current, False)


__all__ = ["CONTRACT", "SessionIdentity", "ErrorInfo", "OperationReceipt",
           "ReconcileExpectation", "ReconciliationReceipt", "identity_from_payload",
           "expectation_from_payload", "apply_operation",
           "reconcile_operation"]
