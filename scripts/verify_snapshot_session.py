"""Default-off admission comparison against explicit captured snapshot evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from pyarrow import ArrowException

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler.campaign_snapshot_adapter import (
    STAGE, CampaignSnapshotError, parse_side_inputs,
)
from chronicler.experiment_sessions import (
    CampaignSession, decode_envelope, decode_envelope_text,
    submission_from_bytes, transport_policy_from_text,
)
from chronicler.snapshot_campaign_sessions import (
    prepare_snapshot_session, read_bounded_bytes, read_snapshot,
    validate_snapshot_byte_limit,
)
from chronicler.turn_artifacts import AgentRows, Stamp

CONTRACT = "chronicler-snapshot-session-check-v1"


class InputParser(argparse.ArgumentParser):
    """CLI syntax failures belong to the same exit3 input-error contract."""

    def error(self, message):
        raise CampaignSnapshotError(message)


def disabled_report() -> dict:
    """Fixed off result; supplied values are neither examined nor opened."""
    return {
        "contract": CONTRACT, "enabled": False,
        "reason": "explicit --enable, --snapshot, --side-inputs, --transport, --path and --max-snapshot-bytes required",
        "original_provenance": "unverified", "committed": False,
        "session_changed": False,
    }


def run(*, enabled: bool, snapshot: Path | None, side_inputs: Path | None,
        transport: Path | None, path: Path | None,
        max_snapshot_bytes: int | None,
        expected_plan_digest: str | None = None) -> dict:
    """Compare genesis after complete public replay of one observed byte string."""
    if not enabled:
        return disabled_report()
    if any(value is None for value in (snapshot, side_inputs, transport, path,
                                       max_snapshot_bytes)):
        raise CampaignSnapshotError(
            "--enable requires --snapshot, --side-inputs, --transport, --path "
            "and --max-snapshot-bytes")
    if expected_plan_digest is not None and (
            type(expected_plan_digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_plan_digest) is None):
        raise CampaignSnapshotError("expected plan digest must be exactly 64 lowercase hex characters")
    validate_snapshot_byte_limit(max_snapshot_bytes)
    policy = transport_policy_from_text(read_bounded_bytes(
        transport, limit=4096, label="transport policy").decode("utf-8"))
    side = parse_side_inputs(submission_from_bytes(read_bounded_bytes(
        side_inputs, limit=policy.max_bytes, label="side inputs"),
        transport=policy, label="side inputs"))
    batch = read_snapshot(snapshot, max_snapshot_bytes=max_snapshot_bytes)
    prepared = prepare_snapshot_session(
        agent_rows=AgentRows(Stamp(side.source_turn, STAGE), batch),
        side_inputs=side, transport=policy)
    observed = read_bounded_bytes(path, limit=policy.max_bytes, label="session")
    envelope = decode_envelope_text(observed, policy)
    saved = decode_envelope(envelope)
    if type(saved) is not CampaignSession:
        raise CampaignSnapshotError("saved session must use the M60a campaign kernel")
    dimensions = {
        "policy": saved.policy == prepared.session.policy,
        "topology": saved.topology == prepared.session.topology,
        "admission": saved.admission == prepared.session.admission,
    }
    equivalent = all(dimensions.values())
    plan = prepared.plan
    expectation = ("not_supplied" if expected_plan_digest is None else
                   "match" if plan.plan_digest == expected_plan_digest else "mismatch")
    admission_label = "admission equivalent" if equivalent else "admission differs"
    expectation_label = {
        "not_supplied": "no caller plan expectation supplied",
        "match": "supplied plan matches caller expectation",
        "mismatch": "supplied plan differs from caller expectation",
    }[expectation]
    return {
        "contract": CONTRACT, "enabled": True,
        "result": admission_label + "; " + expectation_label + "; original provenance unverified",
        "admission_equivalent": equivalent, "comparison": dimensions,
        "plan_expectation": expectation, "expected_plan_digest": expected_plan_digest,
        "original_provenance": "unverified",
        "observed_session": {
            "path": str(path), "byte_count": len(observed),
            "file_digest": hashlib.sha256(observed).hexdigest(),
            "kernel": envelope.kernel, "generation": envelope.generation,
            "latest_turn": envelope.turn, "genesis_turn": saved.admission.turn,
            "genesis_digest": envelope.genesis_digest,
            "session_digest": envelope.session_digest,
            "history_digest": envelope.history_digest, "latest_digest": envelope.latest_digest,
        },
        "supplied_plan": {
            "plan_digest": plan.plan_digest,
            "source_content_digest": plan.source.content_digest,
            "region_binding_digest": plan.region_binding_digest,
            "declared_source_turn": plan.source.source_turn,
            "declared_stage": plan.source.stage,
            "source_identity": "content of demanded columns; turn and stage are declarations",
        },
        "committed": False, "session_changed": False,
        "limitations": [
            "Origin, historical creation, freshness and durability are unverified.",
            "Inputs are read separately; no simultaneous multi-file snapshot is established.",
            "Results bind to observed session bytes; the path may subsequently be replaced.",
            "Source byte caps do not bound Arrow expansion, allocation, execution time or output size.",
            "Preparation performs admission; verification may replay saved history. No new turn is submitted.",
            "No scientific or native validity is certified.",
        ],
    }


def render(document: dict, output_format: str) -> str:
    """Build the entire report before the caller writes anything to stdout."""
    if output_format == "json":
        return json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    if not document["enabled"]:
        return CONTRACT + ": disabled; original provenance unverified; no session change\n"
    observed = document["observed_session"]
    return "\n".join([
        document["result"],
        "comparison: " + json.dumps(document["comparison"], sort_keys=True),
        "observed session: " + json.dumps(observed, sort_keys=True),
        "supplied plan: " + json.dumps(document["supplied_plan"], sort_keys=True),
        "caller expected plan digest: " + str(document["expected_plan_digest"]),
        "committed: false; session_changed: false",
        *document["limitations"],
    ]) + "\n"


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = InputParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--enable", action="store_true")
    for name in ("snapshot", "side-inputs", "transport", "path"):
        parser.add_argument("--" + name, type=Path)
    # Defer optional value validation until the explicit enabled boundary.
    parser.add_argument("--max-snapshot-bytes")
    parser.add_argument("--expected-plan-digest")
    parser.add_argument("--format", default="json")
    # Exact activation/help dispatch precedes all optional syntax and values.
    # Disabled optional arguments are opaque, including missing option values.
    if "--help" in raw or "-h" in raw:
        parser.parse_args(["--help"])
    try:
        if "--enable" not in raw:
            document = disabled_report()
            output_format = "json"
        else:
            args = parser.parse_args(raw)
            if args.format not in ("json", "text"):
                raise CampaignSnapshotError("format must be json or text")
            bound = args.max_snapshot_bytes
            if bound is not None:
                if re.fullmatch(r"[0-9]+", bound) is None:
                    raise CampaignSnapshotError("max snapshot bytes must be a positive integer")
                bound = int(bound)
            document = run(
                enabled=True, snapshot=args.snapshot, side_inputs=args.side_inputs,
                transport=args.transport, path=args.path, max_snapshot_bytes=bound,
                expected_plan_digest=args.expected_plan_digest)
            output_format = args.format
        output = render(document, output_format)
    except (ValueError, OSError, KeyError, TypeError, ArrowException) as exc:
        error = json.dumps({"error": type(exc).__name__, "detail": str(exc)},
                           sort_keys=True, separators=(",", ":")) + "\n"
        sys.stderr.write(error)
        return 3
    sys.stdout.write(output)
    if not document["enabled"]:
        return 0
    return 0 if (document["admission_equivalent"]
                 and document["plan_expectation"] != "mismatch") else 1


if __name__ == "__main__":
    raise SystemExit(main())
