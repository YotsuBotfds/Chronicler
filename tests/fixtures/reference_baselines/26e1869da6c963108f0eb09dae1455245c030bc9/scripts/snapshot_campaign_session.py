"""Default-off durable creation from explicitly supplied snapshot and side files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler.campaign_snapshot_adapter import (
    CONTRACT, STAGE, CampaignSnapshotError, parse_side_inputs, plan_document,
)
from chronicler.experiment_sessions import (
    commit_session, submission_from_bytes, transport_policy_from_text,
)
from chronicler.snapshot_campaign_sessions import (
    prepare_snapshot_session, read_bounded_bytes, read_snapshot,
    validate_snapshot_byte_limit,
)
from chronicler.turn_artifacts import AgentRows, Stamp


def disabled_receipt() -> dict:
    """Fixed receipt independent of supplied paths; no reads or kernel calls."""
    return {
        "contract": CONTRACT, "enabled": False,
        "reason": "explicit --enable, --snapshot, --side-inputs, --transport, --path and --max-snapshot-bytes required",
        "snapshot_read": False, "side_inputs_read": False, "transport_read": False,
        "kernel_admit_calls": 0, "turns_advanced": 0, "committed": False,
    }


def run(*, enabled: bool, snapshot: Path | None, side_inputs: Path | None,
        transport: Path | None, path: Path | None,
        max_snapshot_bytes: int | None) -> dict:
    """Prepare completely before committing one absent destination, with no retry."""
    if not enabled:
        return disabled_receipt()
    if any(value is None for value in (snapshot, side_inputs, transport, path,
                                       max_snapshot_bytes)):
        raise CampaignSnapshotError(
            "--enable requires --snapshot, --side-inputs, --transport, --path "
            "and --max-snapshot-bytes")
    validate_snapshot_byte_limit(max_snapshot_bytes)
    # Bootstrap policy text has the public parser's fixed 4096-character cap.
    # Use the stricter byte cap before UTF-8 decoding or parsing.
    policy = transport_policy_from_text(
        read_bounded_bytes(transport, limit=4096, label="transport policy").decode("utf-8"))
    side = parse_side_inputs(submission_from_bytes(
        read_bounded_bytes(side_inputs, limit=policy.max_bytes, label="side inputs"),
        transport=policy, label="side inputs"))
    batch = read_snapshot(snapshot, max_snapshot_bytes=max_snapshot_bytes)
    prepared = prepare_snapshot_session(
        agent_rows=AgentRows(Stamp(side.source_turn, STAGE), batch),
        side_inputs=side, transport=policy)
    # There is one durable object. The receipt is not a persisted sidecar.
    provenance = plan_document(prepared.plan)
    committed = commit_session(path, prepared.session, transport=policy,
                               expected_generation=None, expected_digest=None)
    return {
        "enabled": True, "committed": True, "path": committed.path,
        "generation": committed.generation, "turn": committed.turn, "kernel": "m60a",
        "file_digest": committed.digest,
        "session_digest": committed.envelope.session_digest,
        "plan": provenance, "plan_provenance_persisted": False,
        "turns_advanced": 0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--side-inputs", type=Path)
    parser.add_argument("--transport", type=Path)
    parser.add_argument("--path", type=Path)
    parser.add_argument("--max-snapshot-bytes", type=int)
    args = parser.parse_args(argv)
    try:
        document = run(enabled=args.enable, snapshot=args.snapshot,
                       side_inputs=args.side_inputs, transport=args.transport,
                       path=args.path, max_snapshot_bytes=args.max_snapshot_bytes)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        sys.stderr.write(json.dumps({"error": type(exc).__name__, "detail": str(exc)},
                                    sort_keys=True, separators=(",", ":")) + "\n")
        return 3
    sys.stdout.write(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
