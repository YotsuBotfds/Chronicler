"""Explicit opt-in memome unit-table demonstration; standard library only."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chronicler.memome_experiment import (  # noqa: E402
    CONTRACT, Batch, Ledger, Participant, Policy, Proposal, advance,
    checkpoint_json, restore_checkpoint,
)


def illustrative_policy():
    traits = tuple(range(6))
    # Knowledge/Cunning incompatibility is illustrative, not calibrated.
    table = tuple((a, b, -1 if {a, b} == {3, 5} else (1 if a == b else 0))
                  for a in traits for b in traits)
    return Policy(CONTRACT, True, traits, 255, (traits,) * 8, table, 1, 1000)


def unit_tables():
    # Stable labels for the five subjects in culture_tick.rs:204-239.
    rows = (("basic-0", "basic", (4, 3, 2), 1),
            ("basic-1", "basic", (4, 1, 0), 1),
            ("basic-2", "basic", (4, 5, 2), 1),
            ("named-0", "named-pair", (4, 3, 2), 5),
            ("ordinary-1", "named-pair", (0, 1, 5), 1))
    people = tuple(Participant(i, g, values + (255,) * 5, weight)
                   for i, g, values, weight in rows)
    # Each tick has at most one proposal for each recipient.
    batches = (
        Batch(1, (Proposal("minority", "basic-1", 1, 3, 199),
                  Proposal("prestige", "ordinary-1", 2, 2, 960),
                  Proposal("incompatible", "basic-2", 2, 3, 0))),
        Batch(2, (Proposal("minority-reject", "basic-0", 1, 5, 200),
                  Proposal("majority-adopt", "basic-1", 2, 2, 799))),
        Batch(3, (Proposal("absent", "basic-0", 0, 0, 0),)),
    )
    return people, batches


def run(enabled=False):
    policy = illustrative_policy()
    people, batches = unit_tables()
    ledger = Ledger(0, people)
    events = []
    for batch in batches:
        # Disabled demonstration only submits the next tick: cursors never move.
        if not enabled and batch.turn != ledger.turn + 1:
            break
        result = advance(ledger, batch, policy, enabled=enabled)
        ledger = result.ledger
        events.append({"turn": batch.turn, "disabled": result.disabled,
                       "receipts": [asdict(r) for r in result.receipts]})
        # Exercise serialization and resume at every actual tick.
        ledger, policy = restore_checkpoint(checkpoint_json(ledger, policy))
    return {"contract": CONTRACT, "enabled": enabled, "illustrative": True,
            "events": events, "checkpoint": json.loads(checkpoint_json(ledger, policy))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", help="explicitly run detached transmission")
    args = parser.parse_args()
    print(json.dumps(run(args.enable), sort_keys=True, separators=(",", ":"), allow_nan=False))
