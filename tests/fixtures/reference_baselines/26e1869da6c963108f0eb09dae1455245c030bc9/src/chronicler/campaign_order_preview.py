"""Explicit next-turn campaign choices, calculated independently and never saved.

The immutable report retains the complete public kernel receipt as canonical
JSON text. It contains no advanced session, save generation or submission token.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json

from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es

CONTRACT = "chronicler-campaign-order-preview-v1"


class PreviewError(ValueError):
    """Invalid request; an alternative error names the failing label."""


@dataclass(frozen=True)
class Alternative:
    label: str
    tick: cl.Tick


@dataclass(frozen=True)
class PreviewRow:
    label: str
    proposed_turn: int
    receipt_json: str
    summary_json: str

    def as_payload(self) -> dict:
        return {"label": self.label, "proposed_turn": self.proposed_turn,
                "receipt": json.loads(self.receipt_json),
                "summary": json.loads(self.summary_json)}


@dataclass(frozen=True)
class PreviewReport:
    enabled: bool = False
    campaign_id: str | None = None
    base_turn: int | None = None
    base_session_digest: str | None = None
    policy_digest: str | None = None
    topology_digest: str | None = None
    alternatives: tuple[PreviewRow, ...] = ()

    def as_payload(self) -> dict:
        base = {"contract": CONTRACT, "enabled": self.enabled,
                "preview": True, "committed": False}
        if not self.enabled:
            return {**base, "reason": "experiment_disabled", "alternatives": []}
        return {**base, "campaign_id": self.campaign_id, "base_turn": self.base_turn,
                "base_session_digest": self.base_session_digest,
                "policy_digest": self.policy_digest,
                "topology_digest": self.topology_digest,
                "alternatives": [row.as_payload() for row in self.alternatives]}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreviewError(message)


def _summary(receipt: dict) -> dict:
    return {
        "phase_before": receipt["phase_before"], "phase_after": receipt["phase_after"],
        "members": [{key: member[key] for key in (
            "agent_id", "region_before", "region_after", "status_before", "status_after",
            "morale_before", "morale_after", "ration_before", "ration_after", "reasons")}
                    for member in receipt["members"]],
        "food": receipt["food"], "grants": receipt["replenishments"],
        "stocks_before": receipt["stocks_before"], "stocks_after": receipt["stocks_after"],
        "reasons": receipt["reasons"],
    }


def preview_orders(*, enabled=False, session=None, alternatives=None,
                   max_alternatives=None, transport=None) -> PreviewReport:
    """Validate all explicit alternatives and compare only their order choices.

    Bounds cover input bytes/count and each complete session's transport domain,
    not output size, global allocation or replay time. Generation 1 is used only
    as the public encoder's validation argument and is never reported.
    """
    _require(type(enabled) is bool, "enabled must be an exact boolean")
    if not enabled:
        return PreviewReport()
    _require(type(session) is es.CampaignSession, "exact CampaignSession required")
    _require(type(alternatives) is tuple, "alternatives must be an immutable tuple")
    _require(type(max_alternatives) is int and max_alternatives > 0,
             "max_alternatives must be an exact positive integer")
    _require(1 <= len(alternatives) <= max_alternatives,
             "alternative count must be between 1 and max_alternatives")
    # Public encode bounds and reconstructs the entire opening history. The
    # explicit second public decode makes reconstruction visible at this seam.
    envelope = es.encode_session(session, transport=transport, generation=1)
    es.decode_envelope(envelope)
    base_digest = es.session_digest(session, transport)
    next_turn = session.session.state.turn + 1
    labels = set()
    payloads = []
    for index, alternative in enumerate(alternatives):
        _require(type(alternative) is Alternative, f"alternative {index}: exact Alternative required")
        label = alternative.label
        _require(type(label) is str and bool(label.strip()) and len(label) <= 128,
                 f"alternative {index}: label must be nonempty and at most 128 characters")
        _require(label not in labels, f"alternative {label!r}: duplicate label")
        labels.add(label)
        try:
            _require(type(alternative.tick) is cl.Tick, "exact public Tick required")
            _require(type(alternative.tick.turn) is int and alternative.tick.turn == next_turn,
                     "tick must be exactly the next turn")
            encoded = cl.canonical_bytes(alternative.tick)
            payload = es.submission_from_bytes(encoded, transport=transport, label="tick")
            es.campaign_tick_from_payload(payload, transport=transport)
            payloads.append({"label": label, "tick": payload})
        except (ValueError, TypeError) as exc:
            raise PreviewError(f"alternative {label!r}: {exc}") from exc
    # Bound the whole supplied alternatives document, not merely each tick.
    es.submission_from_bytes(cl.canonical_bytes({"contract": CONTRACT, "alternatives": payloads}),
                             transport=transport, label="alternatives")
    rows = []
    common_inputs = before_digest = None
    for alternative in alternatives:
        try:
            result = es.apply_campaign_tick(session, alternative.tick)
            _require(result.changed is True and result.replayed is False and result.turn == next_turn,
                     "preview must advance exactly one hypothetical turn")
            # Derived arithmetic and the complete hypothetical history also
            # stay in the requested transport domain; discard the session.
            es.encode_session(result.session, transport=transport, generation=1)
            _require(len(result.receipts) == 1, "one public receipt required")
            receipt = result.receipts[0]
            observations = cl.canonical_bytes(replace(receipt.inputs, orders=()))
            if common_inputs is None:
                common_inputs = observations
                before_digest = receipt.state_before_digest
            _require(observations == common_inputs, "alternatives may differ only in orders")
            _require(receipt.state_before_digest == before_digest,
                     "alternatives must share the opening state")
            raw = cl.canonical_bytes(receipt).decode("utf-8")
            rows.append(PreviewRow(alternative.label, receipt.turn, raw,
                                   cl.canonical_bytes(_summary(json.loads(raw))).decode("utf-8")))
        except (ValueError, TypeError) as exc:
            raise PreviewError(f"alternative {alternative.label!r}: {exc}") from exc
    state = session.session.state
    return PreviewReport(True, state.campaign_id, state.turn, base_digest,
                         state.policy_digest, state.topology_digest, tuple(rows))


def preview_json(report: PreviewReport) -> str:
    return cl.canonical_bytes(report.as_payload()).decode("utf-8") + "\n"


def preview_text(report: PreviewReport) -> str:
    """Readable report including every raw receipt, without a ranking."""
    if not report.enabled:
        return preview_json(report)
    lines = [f"{CONTRACT}: preview=true committed=false",
             f"Campaign {report.campaign_id}, observed base turn {report.base_turn}",
             f"Base session digest: {report.base_session_digest}",
             f"Policy digest: {report.policy_digest}", f"Topology digest: {report.topology_digest}"]
    for row in report.alternatives:
        lines.extend((f"{row.label}: hypothetical turn {row.proposed_turn}",
                      f"Summary: {row.summary_json}", f"Receipt: {row.receipt_json}"))
    return "\n".join(lines) + "\n"
