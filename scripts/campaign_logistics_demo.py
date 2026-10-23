"""Explicit standalone M60a fixture driver. Default invocation is a no-op."""

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
import sys

# Supports direct invocation without installing or importing the production CLI.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler.campaign_logistics import (
    CONTRACT, Condition, Credit, Draw, Order, Policy, Region, Session,
    Soldier, Stock, Tick, Topology, admit, advance, canonical_bytes,
)


@dataclass(frozen=True)
class DisabledReceipt:
    contract: str = CONTRACT
    reason: str = "experiment_disabled"
    draws_consumed: int = 0
    food_consumed: int = 0
    moves: int = 0


def drive(session: Session, *, enabled: bool, policy: Policy, topology: Topology, tick: Tick):
    """Disabled requests return the identical supplied session and spend nothing."""
    if not enabled:
        return session, DisabledReceipt()
    result = advance(session, policy=policy, topology=topology, tick=tick)
    return result.session, result.receipt


def illustrative_policy():
    # Integer illustrative parameters, NOT calibrated production tuning.
    return Policy("m60a-demo-illustrative-v1", ration_demand=1, carried_limit=8,
                  distance_stress=10, unreachable_stress=100, hunger_stress=120,
                  needs_stress=100, information_stress=80, morale_recovery=20,
                  desertion_threshold=200, desertion_chance=5000,
                  movement_min_morale=100, require_full_rations=True)


def fixture_topology():
    # Adjacency ONLY from test_behavior.rs:41-66. Those native agents are farmers;
    # the separate explicit roster below contains illustrative soldier-role IDs.
    return Topology("existing-three-region-v1",
                    (Region(0, (1, 2)), Region(1, (0,)), Region(2, (0,))))


def fixture_session(policy, topology):
    return admit(policy=policy, topology=topology, campaign_id="m60a-table-demo", turn=0,
                 staging=1, target=2,
                 soldiers=(Soldier(101, 1, 8, 800), Soldier(202, 0, 8, 800)),
                 stocks=(Stock(0, 0), Stock(1, 0), Stock(2, 4)))


def fixture_tick(session, turn):
    orders = {
        2: (Order("march-2", 2, "march"),),
        4: (Order("hold-4", 4, "hold"), Order("kit-4", 4, "replenish", (202, 101), 2)),
        5: (Order("return-5", 5, "return"),),
    }.get(turn, ())
    credits = (Credit("local-demo-credit-4", 4, 2, 2),) if turn == 4 else ()
    active = tuple(s.agent_id for s in session.state.soldiers if s.status in ("active", "arrived"))
    return Tick(turn, orders, credits,
                tuple(Condition(agent, 0, 1000) for agent in active),
                tuple(Draw(agent, 9999) for agent in active), (1,))


def run_fixture():
    policy, topology = illustrative_policy(), fixture_topology()
    session = fixture_session(policy, topology)
    receipts = []
    for turn in range(1, 8):
        session, receipt = drive(session, enabled=True, policy=policy, topology=topology,
                                 tick=fixture_tick(session, turn))
        receipts.append(receipt)
    return {"contract": CONTRACT, "policy": asdict(policy),
            "receipts": [asdict(r) for r in receipts], "state": asdict(session.state)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", help="run the detached illustrative table")
    args = parser.parse_args()
    output = run_fixture() if args.enable else DisabledReceipt()
    sys.stdout.buffer.write(canonical_bytes(output) + b"\n")


if __name__ == "__main__":
    main()
