"""Default-off campaign snapshot plan driver.

Disabled by default: it prints a fixed receipt and opens no file, contacts no
native bridge and never calls the campaign kernel. ``--enable`` still requires
an explicitly supplied Arrow IPC snapshot path and an explicit JSON side-input
path. This driver never calls native ``get_snapshot``, never advances the
simulation and never registers a production CLI surface.

Side-input JSON keys are exactly: contract, source_turn, civ_id, selected_ids,
campaign_id, topology_version, staging, target, policy, region_bindings, kits,
morale, stocks. Kits and morale are keyed by stable agent id; stocks by bound
region id. Nothing is inferred: see docs/experiments/campaign-snapshot-adapter.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Supports direct invocation without installing or importing the production CLI.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow as pa

from chronicler.artifact_io import strict_json_loads
from chronicler.campaign_snapshot_adapter import (
    CONTRACT, STAGE, CampaignSnapshotError, admit_snapshot_plan, parse_side_inputs,
    plan_document,
)
from chronicler.turn_artifacts import AgentRows, Stamp


def disabled_receipt() -> dict:
    """Fixed default-off receipt. Opens nothing and calls no kernel seam."""
    return {"contract": CONTRACT, "enabled": False,
            "reason": "explicit --enable with --snapshot and --side-inputs required",
            "snapshot_read": False, "side_inputs_read": False,
            "kernel_admit_calls": 0, "turns_advanced": 0}


def _emit(document) -> None:
    sys.stdout.write(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")


def read_snapshot(path: Path):
    """Read one explicit Arrow IPC snapshot file into one owned record batch.

    The file must hold exactly one record batch with the native 23-field schema;
    the adapter's opt-in ratchet checks that schema, not this reader. The bytes
    are copied so the returned batch never borrows a memory map or an open file:
    this driver owns its snapshot, and the caller owns the path. A single
    zero-row batch is returned as-is, so the adapter reports the absent roster
    rather than this reader indexing an empty batch list.
    """
    reader = pa.ipc.open_file(pa.BufferReader(path.read_bytes()))
    if reader.num_record_batches != 1:
        raise CampaignSnapshotError(
            f"expected exactly one Arrow IPC record batch, found {reader.num_record_batches}")
    return reader.get_batch(0)


def run(*, enabled: bool, snapshot: Path | None, side_inputs: Path | None) -> dict:
    """Build one admission plan from explicit files, or the disabled receipt.

    Disabled means disabled: no path is read, no schema is checked and no kernel
    seam is called, whatever the caller passed.
    """
    if not enabled:
        return disabled_receipt()
    if snapshot is None or side_inputs is None:
        raise CampaignSnapshotError("--enable requires both --snapshot and --side-inputs")
    side = parse_side_inputs(
        strict_json_loads(side_inputs.read_text(encoding="utf-8"), label="side inputs"))
    batch = read_snapshot(snapshot)
    plan = admit_snapshot_plan(
        agent_rows=AgentRows(Stamp(side.source_turn, STAGE), batch),
        expected_source_turn=side.source_turn, civ_id=side.civ_id,
        selected_ids=side.selected_ids, region_bindings=side.region_bindings,
        topology_version=side.topology_version, policy=side.policy,
        campaign_id=side.campaign_id, staging=side.staging, target=side.target,
        kits=dict(side.kits), morale=dict(side.morale), stocks=dict(side.stocks),
    )
    return plan_document(plan)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true",
                        help="plan an admission from the explicitly supplied files")
    parser.add_argument("--snapshot", type=Path, help="Arrow IPC snapshot file (explicit)")
    parser.add_argument("--side-inputs", type=Path, help="explicit JSON side-input file")
    args = parser.parse_args(argv)
    try:
        document = run(enabled=args.enable, snapshot=args.snapshot,
                       side_inputs=args.side_inputs)
    except (CampaignSnapshotError, OSError, ValueError) as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 2
    _emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())