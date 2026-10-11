"""Explicit captured snapshot admission into unchanged portable M60a sessions.

Preparation is read-only and retains no Arrow view. Persistence remains solely
the public experiment_sessions.commit_session contract. Snapshot provenance is
a separate receipt; it is not added to the session envelope.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa

from chronicler.campaign_logistics import canonical_bytes
from chronicler.campaign_snapshot_adapter import (
    CONTRACT, AdmissionPlan, CampaignSnapshotError, SideInputs, admit_snapshot_plan,
)
from chronicler.experiment_sessions import (
    CampaignSession, Envelope, IntegrityError, SessionError, TransportDomainError,
    TransportPolicy, create_campaign_session, decode_envelope, encode_session,
    transport_policy_from_payload,
)
from chronicler.turn_artifacts import AgentRows

MAX_SNAPSHOT_BYTES = 67_108_864


@dataclass(frozen=True, slots=True)
class PreparedSnapshotSession:
    """Copied admission, managed session and self-verified generation-one envelope."""

    plan: AdmissionPlan
    session: CampaignSession
    envelope: Envelope


def prepare_snapshot_session(*, agent_rows: AgentRows, side_inputs: SideInputs,
                             transport: TransportPolicy) -> PreparedSnapshotSession:
    """Re-admit an explicit snapshot plan, check complete equality, then bound it.

    Re-admission is not advancement: no tick or draw is supplied. All kernel
    semantics and all transport validation come from the existing public APIs.
    This entry point accepts exact SideInputs and TransportPolicy records only;
    it deliberately has no API accepting a caller-forged AdmissionPlan.
    """
    if type(side_inputs) is not SideInputs:
        raise CampaignSnapshotError("exact public SideInputs record required")
    if type(side_inputs.contract) is not str or side_inputs.contract != CONTRACT:
        raise CampaignSnapshotError(f"side inputs: expected contract {CONTRACT!r}")
    if type(transport) is not TransportPolicy:
        raise SessionError("exact public TransportPolicy record required")
    transport_policy_from_payload(transport.as_payload())
    side = side_inputs
    plan = admit_snapshot_plan(
        agent_rows=agent_rows, expected_source_turn=side.source_turn,
        civ_id=side.civ_id, selected_ids=side.selected_ids,
        campaign_id=side.campaign_id, topology_version=side.topology_version,
        staging=side.staging, target=side.target, policy=side.policy,
        region_bindings=side.region_bindings, kits=side.kits,
        morale=side.morale, stocks=side.stocks,
    )
    managed = create_campaign_session(
        policy=plan.policy, topology=plan.topology, campaign_id=plan.campaign_id,
        turn=plan.admission_turn, staging=plan.staging, target=plan.target,
        soldiers=plan.soldiers, stocks=plan.stocks,
    )
    if canonical_bytes(managed.session) != canonical_bytes(plan.session):
        raise IntegrityError("managed re-admission differs from the complete snapshot admission")
    envelope = encode_session(managed, transport=transport, generation=1)
    restored = decode_envelope(envelope)
    if type(restored) is not CampaignSession or restored != managed:
        raise IntegrityError("prepared envelope differs from the complete managed session")
    return PreparedSnapshotSession(plan, managed, envelope)


def validate_snapshot_byte_limit(max_snapshot_bytes: int) -> int:
    """Require an explicit exact positive byte bound; never infer or clamp it."""
    if type(max_snapshot_bytes) is not int or not 1 <= max_snapshot_bytes <= MAX_SNAPSHOT_BYTES:
        raise CampaignSnapshotError(
            f"max_snapshot_bytes must be an exact integer in 1..{MAX_SNAPSHOT_BYTES}")
    return max_snapshot_bytes


def read_bounded_bytes(path: Path, *, limit: int, label: str) -> bytes:
    """Bound the actual opened stream, independent of stale or misleading stat."""
    if type(limit) is not int or limit < 1:
        raise SessionError("file read limit must be a positive exact integer")
    with Path(path).open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise TransportDomainError(f"the {label} exceeds the {limit}-byte limit")
    return data


def read_snapshot(path: Path, *, max_snapshot_bytes: int) -> pa.RecordBatch:
    """Read exactly one supplied Arrow IPC file batch, bounded before parsing.

    The returned batch owns copied bytes after both the file and Arrow reader
    have closed. Schema admission belongs to the reviewed snapshot adapter.
    No native snapshot acquisition occurs here.
    """
    limit = validate_snapshot_byte_limit(max_snapshot_bytes)
    data = read_bounded_bytes(path, limit=limit, label="snapshot")
    with pa.BufferReader(data) as source:
        with pa.ipc.open_file(source) as reader:
            if reader.num_record_batches != 1:
                raise CampaignSnapshotError(
                    "expected exactly one Arrow IPC record batch, "
                    f"found {reader.num_record_batches}")
            batch = reader.get_batch(0)
            # Copy Arrow buffers out of the reader, including variable-width
            # fields, without converting native values through Python floats.
            copied = batch.serialize().to_pybytes()
            schema = batch.schema
    with pa.BufferReader(copied) as source:
        return pa.ipc.read_record_batch(source, schema)
