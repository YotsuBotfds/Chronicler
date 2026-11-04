#!/usr/bin/env python3
"""Seats of learning: what they do to techniques and archives, per world.

``scholarship_probe.py extract BATCH_DIR OUT.json``
    For every ``seed_*`` run of a batch (``chronicle_bundle.json`` and
    ``agent_events.arrow``): technique inventions, adoptions by channel and
    losses (``world_state.techniques.counts``), techniques known per living
    civ (mean over the snapshots and at the end), the chronicles' accounts
    and losses (the bundle's ``historiography`` field: accounts lost, and
    per loss cause the accounts that survived an episode against those lost),
    agent migrations led by the learning pull, and the seats' counters.
    The courts' and temples' accounts and the share of them lost. For the
    war losses of courts' and temples' archives it also gives the
    accounts expected to survive with the copies kept and without the
    copies seats of learning kept (``seat_copies``), from ``SURVIVAL``.

``scholarship_probe.py compare OFF.json ON.json``
    Paired by seed: the mean of each measure in both arms and the mean
    difference with its standard error, as a Markdown table.

See docs/integration/scholarship.md.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

LEARNING_DRIVER = 19   # models.MIGRATION_DRIVER_NAMES index of "learning"


def _load(path: Path) -> dict:
    from chronicler.bundle_codec import load_bundle
    return load_bundle(path)


def _learning_moves(path: Path) -> int | None:
    if not path.exists():
        return None
    import pyarrow.ipc as ipc
    with ipc.open_file(str(path)) as f:
        table = f.read_all()
    if "migration_driver" not in table.column_names:
        return 0
    types = table.column("event_type").to_pylist()
    drivers = table.column("migration_driver").to_pylist()
    return sum(1 for t, d in zip(types, drivers) if t == "migration" and d == LEARNING_DRIVER)


def seed_metrics(run: Path) -> dict:
    bundle = _load(run / "chronicle_bundle.json")
    ws = bundle.get("world_state", {})
    out: dict[str, float] = {}
    counts = (ws.get("techniques") or {}).get("counts", {})
    out["invented"] = counts.get("invented", 0)
    out["adopted"] = sum(v for k, v in counts.items() if k.startswith("gained:"))
    out["adopted_scholars"] = counts.get("gained:scholars", 0)
    out["lost_decay"] = counts.get("lost:decay", 0)
    out["era_up"] = counts.get("era_up", 0)
    series = [h.get("techniques") for h in bundle.get("history", []) if h.get("techniques")]
    per_turn = [sum(s["known"].values()) / len(s["known"]) for s in series if s.get("known")]
    if per_turn:
        out["known_mean"] = sum(per_turn) / len(per_turn)
        out["known_final"] = per_turn[-1]
    hist = bundle.get("historiography") or {}
    hc = hist.get("counts", {})
    accounts = hc.get("accounts", 0)
    lost = sum(v for k, v in hc.items() if k.startswith("lost:"))
    out["accounts"] = accounts
    out["accounts_lost_share"] = lost / accounts if accounts else 0.0
    for cause in ("conquest", "sack", "collapse", "absorption"):
        survived = lost_n = 0
        for archive in hist.get("archives", []):
            for loss in archive.get("losses", []):
                if loss.get("cause") == cause:
                    survived += loss.get("survived", 0)
                    lost_n += loss.get("lost", 0)
        out[f"{cause}_episode_accounts"] = survived + lost_n
        out[f"{cause}_survived"] = survived
    # The courts' and temples' archives (not the seats' own): accounts that
    # survived a war loss (sack, conquest, collapse, absorption), episodes and
    # the copies the archive kept at each.
    from chronicler.historiography import SURVIVAL
    episodes = copies = kept = at_risk = seated = seated_risk = seated_kept = 0
    expect = expect_without = 0.0
    for archive in hist.get("archives", []):
        if archive.get("owner", "").startswith("seat:"):
            continue
        for loss in archive.get("losses", []):
            if loss.get("cause") in ("conquest", "sack", "collapse", "absorption"):
                n = loss.get("survived", 0) + loss.get("lost", 0)
                c = loss.get("copies", 1)
                episodes += 1
                copies += c
                kept += loss.get("survived", 0)
                at_risk += n
                k = loss.get("seat_copies") or 0
                if k:
                    s = SURVIVAL[loss["cause"]]
                    seated += 1
                    seated_risk += n
                    seated_kept += loss.get("survived", 0)
                    expect += n * (1.0 - (1.0 - s) ** max(1, c))
                    expect_without += n * (1.0 - (1.0 - s) ** max(1, c - k))
    out["war_loss_episodes"] = episodes
    out["war_loss_copies_sum"] = copies
    out["war_loss_accounts"] = at_risk
    out["war_loss_survived"] = kept
    out["war_loss_seat_episodes"] = seated
    out["war_loss_seat_accounts"] = seated_risk
    out["war_loss_seat_survived"] = seated_kept
    out["war_loss_seat_expected"] = expect
    out["war_loss_seat_expected_without"] = expect_without
    out["seat_chroniclers"] = sum(1 for c in hist.get("chroniclers", []) if c.get("kind") == "seat")
    # The courts' and temples' own accounts (every loss cause), lost share.
    kept_by = [c for c in hist.get("chroniclers", []) if c.get("kind") != "seat"]
    written = sum(c.get("accounts", 0) for c in kept_by)
    out["court_temple_accounts"] = written
    out["court_temple_lost_share"] = (
        1.0 - sum(c.get("surviving", 0) for c in kept_by) / written if written else 0.0)
    moves = _learning_moves(run / "agent_events.arrow")
    if moves is not None:
        out["learning_moves"] = moves
    snaps = [h.get("scholarship") for h in bundle.get("history", []) if h.get("scholarship")]
    if snaps:
        for k, v in snaps[-1].get("counters", {}).items():
            out[f"seats_{k}"] = v
        out["seats_living_mean"] = sum(len(s.get("seats", [])) for s in snaps) / len(snaps)
    return out


def extract(batch: Path) -> dict:
    result = {}
    for run in sorted(batch.glob("seed_*")):
        if (run / "chronicle_bundle.json").exists():
            result[run.name] = seed_metrics(run)
    return result


def compare(off: dict, on: dict) -> list[str]:
    seeds = sorted(set(off) & set(on))
    keys = sorted({k for s in seeds for k in off[s]} | {k for s in seeds for k in on[s]})
    lines = [f"Paired worlds: {len(seeds)}", "",
             "| measure | off | on | difference (SE) |", "| --- | ---: | ---: | ---: |"]
    for k in keys:
        a = [off[s].get(k, 0.0) for s in seeds]
        b = [on[s].get(k, 0.0) for s in seeds]
        d = [y - x for x, y in zip(a, b)]
        n = len(d)
        mean = sum(d) / n if n else 0.0
        se = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1) / n) if n > 1 else 0.0
        lines.append(f"| {k} | {sum(a) / n:.3f} | {sum(b) / n:.3f} | {mean:+.3f} ({se:.3f}) |")
    # Survival per account of an archive loss episode, pooled.
    for name, arm in (("off", off), ("on", on)):
        episodes = sum(arm[s].get("war_loss_episodes", 0) for s in seeds)
        if episodes:
            copies = sum(arm[s].get("war_loss_copies_sum", 0) for s in seeds) / episodes
            total = sum(arm[s].get("war_loss_accounts", 0) for s in seeds)
            kept = sum(arm[s].get("war_loss_survived", 0) for s in seeds)
            lines.append(f"- court and temple archives, war losses, {name}: {episodes} episodes, "
                         f"{copies:.2f} copies on average, {kept} of {total} accounts survived "
                         f"({kept / total:.1%})" if total else f"- {name}: {episodes} episodes")
    # Switched on: the episodes where seats kept copies, with and without them.
    seated = sum(on[s].get("war_loss_seat_episodes", 0) for s in seeds)
    if seated:
        total = sum(on[s].get("war_loss_seat_accounts", 0) for s in seeds)
        kept = sum(on[s].get("war_loss_seat_survived", 0) for s in seeds)
        expect = sum(on[s].get("war_loss_seat_expected", 0.0) for s in seeds)
        without = sum(on[s].get("war_loss_seat_expected_without", 0.0) for s in seeds)
        lines.append(f"- on, war losses where seats kept copies: {seated} episodes, {total} accounts; "
                     f"{kept} survived ({kept / total:.1%}); expected {expect / total:.1%} with "
                     f"the seats' copies and {without / total:.1%} without them" if total else
                     f"- on: {seated} seated episodes")
    for cause in ("conquest", "sack", "collapse", "absorption"):
        for name, arm in (("off", off), ("on", on)):
            total = sum(arm[s].get(f"{cause}_episode_accounts", 0) for s in seeds)
            kept = sum(arm[s].get(f"{cause}_survived", 0) for s in seeds)
            if total:
                lines.append(f"- {cause}, {name}: {kept} of {total} accounts survived ({kept / total:.1%})")
    return lines


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "extract":
        data = extract(Path(argv[1]))
        Path(argv[2]).write_text(json.dumps(data, indent=1, sort_keys=True))
        print(f"{argv[2]}: {len(data)} runs")
        return 0
    if len(argv) == 3 and argv[0] == "compare":
        off = json.loads(Path(argv[1]).read_text())
        on = json.loads(Path(argv[2]).read_text())
        print("\n".join(compare(off, on)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
