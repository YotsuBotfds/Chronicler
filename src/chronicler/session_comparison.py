"""Read-only comparison of two completely verified recorded experiments."""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import json
import os

from chronicler import experiment_sessions as es
from chronicler.campaign_logistics import Tick as CampaignTick
from chronicler.memome_experiment import Batch as MemomeBatch

CONTRACT = "chronicler-session-comparison-v1"
LIMITATIONS = (
    "Relationships compare recorded inputs; they do not establish physical copying or chronological file lineage.",
    "No original capture identity, shared session UUID, authentication, durability or currentness is established.",
    "The two public loads are separate observations, including when both paths are the same.",
    "No simultaneous multi-file snapshot, overwrite permission, retry or recovery decision is provided.",
    "Per-file transport limits do not bound combined memory, output size or execution time.",
)


@dataclass(frozen=True, slots=True)
class ObservedSession:
    path: str
    kernel: str
    kernel_contract: str
    generation: int
    latest_turn: int
    file_digest: str
    session_digest: str
    genesis_digest: str
    history_digest: str
    latest_digest: str
    source_head: str
    source_tree: str


@dataclass(frozen=True, slots=True)
class SessionComparison:
    enabled: bool
    relationship: str | None = None
    left: ObservedSession | None = None
    right: ObservedSession | None = None
    transport: es.TransportPolicy | None = None
    differing_genesis_dimensions: tuple[str, ...] = ()
    shared_committed_turn_count: int | None = None
    last_shared_committed_turn: int | None = None
    first_conflicting_turn: int | None = None
    left_conflicting_submission: CampaignTick | MemomeBatch | None = None
    right_conflicting_submission: CampaignTick | MemomeBatch | None = None
    file_digest_equal: bool | None = None
    generation_equal: bool | None = None


def _observed(loaded: es.LoadedSession, supplied_path) -> ObservedSession:
    envelope = loaded.envelope
    return ObservedSession(
        os.fspath(supplied_path), envelope.kernel, envelope.kernel_contract,
        loaded.generation, loaded.turn, loaded.digest, envelope.session_digest,
        envelope.genesis_digest, envelope.history_digest, envelope.latest_digest,
        envelope.source_head, envelope.source_tree)


def compare_sessions(left=None, right=None, *, enabled=False,
                     transport=None) -> SessionComparison:
    """Load each side once, then compare complete recorded genesis and submissions.

    Genesis equality is recorded-input equality, not normalization or behavioral
    equivalence. Every load reconstructs its complete history before a report can
    be returned, including an unmatched continuation. No writer is called.
    """
    if type(enabled) is not bool:
        raise es.SessionError("enabled must be an exact boolean")
    if not enabled:
        return SessionComparison(False)
    if left is None or right is None:
        raise es.SessionError("two explicit session paths are required")
    if type(transport) is not es.TransportPolicy:
        raise es.SessionError("an exact explicit TransportPolicy is required")
    es.transport_policy_from_payload(transport.as_payload())
    left_loaded = es.load_session(left, transport=transport)
    right_loaded = es.load_session(right, transport=transport)
    first, second = left_loaded.session, right_loaded.session
    common = dict(enabled=True, left=_observed(left_loaded, left),
                  right=_observed(right_loaded, right), transport=transport,
                  file_digest_equal=left_loaded.digest == right_loaded.digest,
                  generation_equal=left_loaded.generation == right_loaded.generation)
    supported = (es.CampaignSession, es.MemomeSession)
    if type(first) not in supported or type(second) not in supported:
        raise es.SessionError("unsupported validated session record")
    if type(first) is not type(second):
        return SessionComparison(relationship="different_kernel", **common)
    if type(first) is es.CampaignSession:
        dimensions = ("policy", "topology", "admission")
        left_history, right_history = first.history, second.history
    else:
        dimensions = ("policy", "genesis_turn", "genesis")
        left_history, right_history = first.batches, second.batches
    differing = tuple(name for name in dimensions
                      if getattr(first, name) != getattr(second, name))
    if differing:
        return SessionComparison(relationship="different_recorded_genesis",
                                 differing_genesis_dimensions=differing, **common)
    shared = 0
    last = None
    for left_submission, right_submission in zip(left_history, right_history):
        if left_submission != right_submission:
            return SessionComparison(
                relationship="conflicting_history", shared_committed_turn_count=shared,
                last_shared_committed_turn=last,
                first_conflicting_turn=left_submission.turn,
                left_conflicting_submission=left_submission,
                right_conflicting_submission=right_submission, **common)
        shared += 1
        last = left_submission.turn
    relationship = ("same_recorded_experiment" if len(left_history) == len(right_history)
                    else "left_history_prefix" if len(left_history) < len(right_history)
                    else "right_history_prefix")
    return SessionComparison(relationship=relationship, shared_committed_turn_count=shared,
                             last_shared_committed_turn=last, **common)


def _plain(value):
    if is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if type(value) is tuple:
        return [_plain(item) for item in value]
    return value


def comparison_document(report: SessionComparison) -> dict:
    """Fresh JSON containers, retaining all public submission fields and integers."""
    if type(report) is not SessionComparison:
        raise es.SessionError("an exact SessionComparison is required")
    if not report.enabled:
        return {"contract": CONTRACT, "enabled": False, "reads_files": False,
                "writes_files": False, "calls_kernels": False,
                "reason": "explicit --enable, --left, --right and --transport required"}
    return {"contract": CONTRACT, **_plain(report), "writes_files": False,
            "limitations": list(LIMITATIONS)}


def comparison_json(report: SessionComparison) -> str:
    return json.dumps(comparison_document(report), sort_keys=True,
                      separators=(",", ":"), allow_nan=False) + "\n"


def comparison_text(report: SessionComparison) -> str:
    """Deterministic text with complete observed identities and conflicting records."""
    document = comparison_document(report)
    if not document["enabled"]:
        return CONTRACT + ": disabled; no files read or written\n"
    lines = [CONTRACT + ": " + document["relationship"],
             "shared committed turns: " + str(document["shared_committed_turn_count"]),
             "last shared committed turn: " + str(document["last_shared_committed_turn"]),
             "first conflicting turn: " + str(document["first_conflicting_turn"])]
    for name in ("left", "right", "differing_genesis_dimensions",
                 "file_digest_equal", "generation_equal", "transport",
                 "left_conflicting_submission", "right_conflicting_submission"):
        lines.append(name + ": " + json.dumps(document[name], sort_keys=True,
                                               separators=(",", ":"), allow_nan=False))
    return "\n".join([*lines, "writes_files: false", *LIMITATIONS]) + "\n"
