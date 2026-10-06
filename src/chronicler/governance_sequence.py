"""Bounded, default-off inspection of already-produced synthetic captures.

Continuity and declared policy correspondence are not execution authenticity.
This module performs no kernel execution, fixture import, I/O or shared writes.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from . import governance_capture as capture
from . import governance_measurements as gm

SEQUENCE_CONTRACT = "chronicler-governance-sequence-v1"
SUMMARY_METRICS = ("institution_count", "enact_count", "repeal_count",
                   "forced_repeal_count", "neglect_repeal_count")


@dataclass(frozen=True)
class SequenceTurn:
    """One measured N -> N+1 row; nets follow the owner's civilization order."""

    measurement: gm.GovernanceMeasurementFrame
    ownership_epoch: int
    net_capital_changes: tuple[gm.ExactFraction, ...]

    @property
    def source_turn(self) -> int:
        return self.measurement.source_turn

    @property
    def effective_turn(self) -> int:
        return self.measurement.effective_turn


@dataclass(frozen=True)
class GovernanceSequence:
    """An immutable inspection receipt, never a restore file or historical log."""

    enabled: bool
    rows: tuple[SequenceTurn, ...] = ()
    contract: str = SEQUENCE_CONTRACT

    @property
    def status(self) -> str:
        return "inspected" if self.rows else ("no_evidence" if self.enabled else "disabled_no_evidence")

    @property
    def frame_count(self) -> int:
        return len(self.rows)

    @property
    def adjacent_link_count(self) -> int:
        return max(0, self.frame_count - 1)

    @property
    def full_policy_equal(self) -> bool | None:
        # A singleton has a fixed declared policy, with zero adjacent checks.
        return True if self.rows else None


def inspect_sequence(*, enabled: bool = False, captures=None,
                     max_frames: int | None = None) -> GovernanceSequence:
    """Validate all supplied captures before publishing a complete receipt.

    Off ignores every optional input. Enabled takes an exact tuple and exact
    positive integer cap. The cap bounds frame count, not memory/bytes/runtime.
    Public C validation checks cached measurement correspondence; complete
    carry, policy, declaration and registry equality are additional checks here.
    """
    if type(enabled) is not bool:
        raise ValueError("enabled must be an explicit boolean")
    if not enabled:
        return GovernanceSequence(False)
    if type(captures) is not tuple:
        raise ValueError("enabled sequence requires an exact immutable tuple")
    if type(max_frames) is not int or max_frames <= 0:
        raise ValueError("max_frames must be an exact positive integer")
    if len(captures) > max_frames:
        raise ValueError("capture count exceeds max_frames")
    # Validate every entry before using any retained field in sequence checks.
    for item in captures:
        capture.validate_capture(item)
        if not item.enabled:
            raise ValueError("sequence entries must be enabled captures")
    if not captures:
        return GovernanceSequence(True)
    first = captures[0]
    previous = None
    for item in captures:
        if item.policy != first.policy:
            raise ValueError("complete sequence policy differs")
        if item.source_identity != first.source_identity or item.origin != first.origin:
            raise ValueError("declared sequence source/origin differs")
        if item.measurement.identity_registry != first.measurement.identity_registry:
            raise ValueError("sequence identity registry differs")
        if previous is not None:
            if item.frame.source_turn != previous.frame.source_turn + 1:
                raise ValueError("sequence source turns must be consecutive in input order")
            if item.opening != previous.result.carry:
                raise ValueError("complete adjacent carry differs")
        previous = item
    rows = tuple(SequenceTurn(item.measurement, item.frame.ownership_epoch, tuple(
        gm.ExactFraction.of(civ.published_capital.exact_balance.as_fraction()
                            - civ.opening_capital.exact_balance.as_fraction())
        for civ in item.measurement.civilizations)) for item in captures)
    return GovernanceSequence(True, rows)


def sequence_document(sequence: GovernanceSequence) -> dict:
    """Return a fresh report-only envelope using the public owner JSON encoder.

    Raw owner JSON is retained byte-for-byte as a string. Summary fields come
    from that same owner document; only net capital change is derived here.
    Standard decimal encoding failures propagate before any stdout publication.
    """
    if not isinstance(sequence, GovernanceSequence) or sequence.contract != SEQUENCE_CONTRACT:
        raise ValueError("unsupported GovernanceSequence")
    rows = []
    documents = []
    for row in sequence.rows:
        raw = gm.measurement_json(row.measurement)
        document = json.loads(raw)
        documents.append(document)
        civilizations = []
        for civ, net in zip(document["civilizations"], row.net_capital_changes, strict=True):
            civilizations.append(dict(
                civ_id=civ["civ_id"],
                opening_institution_count=civ["opening_institution_count"],
                published_institution_count=len(civ["institutions"]),
                opening_capital=civ["opening_capital"],
                spent_capital=civ["spend_total"],
                post_spend_capital=civ["capital_after_spend"],
                accrual=civ["accrual"], published_capital=civ["published_capital"],
                derived_net_capital_change={"fraction": [net.numerator, net.denominator]},
                opening_ruler_legitimacy=civ["opening_capital"]["ruler_legitimacy"],
                published_ruler_legitimacy=civ["published_capital"]["ruler_legitimacy"]))
        rows.append(dict(source_turn=row.source_turn, effective_turn=row.effective_turn,
            ownership_epoch=row.ownership_epoch,
            metrics=[metric for metric in document["metrics"] if metric["key"] in SUMMARY_METRICS],
            civilizations=civilizations,
            unavailable=[metric for metric in document["metrics"] if metric["status"] == "unavailable"],
            raw_measurement_json=raw))
    first = documents[0] if documents else None
    return dict(contract=sequence.contract, report_kind="governance-sequence-report",
        enabled=sequence.enabled, status=sequence.status, frame_count=sequence.frame_count,
        adjacent_link_count=sequence.adjacent_link_count,
        first_source_turn=sequence.rows[0].source_turn if sequence.rows else None,
        last_source_turn=sequence.rows[-1].source_turn if sequence.rows else None,
        first_effective_turn=sequence.rows[0].effective_turn if sequence.rows else None,
        last_effective_turn=sequence.rows[-1].effective_turn if sequence.rows else None,
        declared_source_identity=first["source_identity"] if first else None,
        declared_origin=first["origin"] if first else None,
        identity_registry=first["identity_registry"] if first else None,
        policy_id=first["policy_id"] if first else None,
        full_policy_equal=sequence.full_policy_equal,
        evidence_limit="Recorded correspondence and continuity; caller declarations, not authenticated execution.",
        rows=rows)


def sequence_json(sequence: GovernanceSequence) -> str:
    """Canonical report JSON; never a C capture decoder or policy restore file."""
    return json.dumps(sequence_document(sequence), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False) + "\n"


def render_report(sequence: GovernanceSequence) -> str:
    """Build the complete text before the caller writes any output."""
    document = sequence_document(sequence)
    lines = [f"SEQUENCE {sequence.contract}: {sequence.status}",
        f"frames={sequence.frame_count}; adjacent_links={sequence.adjacent_link_count}; full_policy_equal={sequence.full_policy_equal}",
        document["evidence_limit"]]
    if sequence.rows:
        lines.append(f"declared_source={document['declared_source_identity']}; declared_origin={document['declared_origin']}; policy_id={document['policy_id']}")
    for row in sequence.rows:
        lines.append(f"source_turn={row.source_turn} -> effective_turn={row.effective_turn}; ownership_epoch={row.ownership_epoch}")
        for civ, net in zip(row.measurement.civilizations, row.net_capital_changes, strict=True):
            lines.append(f"  civ={civ.civ_id}; opening_institutions={civ.opening_institution_count}; published_institutions={len(civ.institutions)}; derived_net_capital_change={net} (published minus opening)")
        lines.append(gm.render_report(row.measurement).rstrip("\n"))
    return "\n".join(lines) + "\n"
