"""Illustrative candidate-only next-batch reports through public M68a APIs.

Every alternative uses the same complete opening session. No hypothetical
session, checkpoint, saved generation or submission token is returned.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from chronicler import experiment_sessions as es
from chronicler import memome_experiment as mm

CONTRACT = "chronicler-memome-candidate-preview-v1"


class PreviewError(ValueError):
    """An invalid alternative or comparison rejects the entire report."""


@dataclass(frozen=True)
class Alternative:
    label: str
    batch: mm.Batch


@dataclass(frozen=True)
class SlotPreview:
    receipt: mm.Receipt
    previous_slot_value: int
    resulting_slot_value: int

    def as_payload(self) -> dict:
        return {"receipt": asdict(self.receipt),
                "previous_slot_value": self.previous_slot_value,
                "resulting_slot_value": self.resulting_slot_value}


@dataclass(frozen=True)
class PreviewRow:
    label: str
    proposed_turn: int
    admitted_batch: mm.Batch
    receipts: tuple[SlotPreview, ...]

    def as_payload(self) -> dict:
        return {"label": self.label, "proposed_turn": self.proposed_turn,
                "admitted_batch": asdict(self.admitted_batch),
                "receipts": [item.as_payload() for item in self.receipts]}


@dataclass(frozen=True)
class PreviewReport:
    enabled: bool = False
    base_turn: int | None = None
    base_session_digest: str | None = None
    policy_version: str | None = None
    draw_scale: int | None = None
    alternatives: tuple[PreviewRow, ...] = ()

    def as_payload(self) -> dict:
        payload = {"contract": CONTRACT, "enabled": self.enabled, "illustrative": True,
                   "preview": True, "committed": False, "alternatives": []}
        if not self.enabled:
            return {**payload, "reason": "experiment_disabled"}
        return {**payload, "base_turn": self.base_turn,
                "base_session_digest": self.base_session_digest,
                "policy_version": self.policy_version, "draw_scale": self.draw_scale,
                "alternatives": [row.as_payload() for row in self.alternatives]}


def _json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreviewError(message)


def preview_candidates(*, enabled=False, session=None, alternatives=None,
                       max_alternatives=None, transport=None) -> PreviewReport:
    """Validate all explicit candidate choices before publishing one report.

    Public complete-history reconstruction is mandatory for both opening and
    hypothetical sessions. Generation 1 is only the encoder validation argument.
    Bounds cover input/count/session domain, not output size, time or allocation.
    """
    _require(type(enabled) is bool, "enabled must be an exact boolean")
    if not enabled:
        return PreviewReport()
    _require(type(session) is es.MemomeSession, "exact MemomeSession required")
    _require(type(transport) is es.TransportPolicy, "exact TransportPolicy required")
    _require(type(alternatives) is tuple, "alternatives must be an immutable tuple")
    _require(type(max_alternatives) is int and max_alternatives > 0,
             "max_alternatives must be an exact positive integer")
    _require(1 <= len(alternatives) <= max_alternatives,
             "alternative count must be between 1 and max_alternatives")
    envelope = es.encode_session(session, transport=transport, generation=1)
    es.decode_envelope(envelope)
    opening_digest = es.session_digest(session, transport)
    next_turn = session.ledger.turn + 1
    labels = set()
    supplied = []
    for index, alternative in enumerate(alternatives):
        _require(type(alternative) is Alternative, f"alternative {index}: exact Alternative required")
        label = alternative.label
        _require(type(label) is str and bool(label.strip()) and len(label) <= 128,
                 f"alternative {index}: label must be nonblank and at most 128 characters")
        _require(label not in labels, f"alternative {label!r}: duplicate label")
        labels.add(label)
        try:
            batch = alternative.batch
            _require(type(batch) is mm.Batch, "exact public Batch required")
            _require(type(batch.turn) is int and batch.turn == next_turn,
                     "batch must be exactly the next turn")
            payload = es.submission_from_bytes(_json(asdict(batch)).encode("utf-8"),
                                              transport=transport, label="batch")
            es.memome_batch_from_payload(payload, transport=transport)
            supplied.append({"label": label, "batch": payload})
        except (ValueError, TypeError) as exc:
            raise PreviewError(f"alternative {label!r}: {exc}") from exc
    es.submission_from_bytes(_json({"contract": CONTRACT, "alternatives": supplied}).encode("utf-8"),
                             transport=transport, label="alternatives")
    rows = []
    common = None
    opening = {person.agent_id: person for person in session.ledger.participants}
    for alternative in alternatives:
        try:
            result = es.apply_memome_batch(session, alternative.batch)
            _require(result.changed is True and result.replayed is False and result.turn == next_turn,
                     "preview must advance exactly one hypothetical turn")
            es.encode_session(result.session, transport=transport, generation=1)
            admitted = result.session.batches[-1]
            _require(admitted.turn == next_turn, "admitted batch must be the next turn")
            comparison = (admitted.turn, tuple((p.proposal_id, p.recipient, p.slot, p.draw)
                                               for p in admitted.proposals))
            if common is None:
                common = comparison
            _require(comparison == common, "alternatives may differ only in candidate")
            after = {person.agent_id: person for person in result.session.ledger.participants}
            views = tuple(SlotPreview(receipt, opening[receipt.recipient].slots[receipt.slot],
                                      after[receipt.recipient].slots[receipt.slot])
                          for receipt in result.receipts)
            row = PreviewRow(alternative.label, admitted.turn, admitted, views)
            # Refuse unsupported extreme integer rendering before any publication.
            # Never change global digit limits or coerce exact weights to floats.
            _json(row.as_payload())
            rows.append(row)
        except (ValueError, TypeError) as exc:
            raise PreviewError(f"alternative {alternative.label!r}: {exc}") from exc
    report = PreviewReport(True, session.ledger.turn, opening_digest, session.policy.version,
                           session.policy.draw_scale, tuple(rows))
    _json(report.as_payload())
    return report


def preview_json(report: PreviewReport) -> str:
    return _json(report.as_payload()) + "\n"


def preview_text(report: PreviewReport) -> str:
    """Readable complete report; threshold remains an illustrative integer."""
    if not report.enabled:
        return preview_json(report)
    lines = [f"{CONTRACT}: illustrative=true preview=true committed=false",
             f"Opening turn: {report.base_turn}; session digest: {report.base_session_digest}",
             f"Policy: {report.policy_version}; draw scale: {report.draw_scale}"]
    for row in report.alternatives:
        lines.extend((f"{row.label}: hypothetical turn {row.proposed_turn}",
                      "Admitted batch: " + _json(asdict(row.admitted_batch))))
        lines.extend("Slot receipt: " + _json(item.as_payload()) for item in row.receipts)
    return "\n".join(lines) + "\n"
