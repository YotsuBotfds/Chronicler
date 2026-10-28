#!/usr/bin/env python3
"""The merchant tax: what paying it does to merchants, revenue, treasuries,
fiscal crises and agents (docs/integration/money-credit.md, "The merchant
tax").

``merchant_tax_probe.py run RUN_DIR -- <chronicler.main arguments>``
    Runs one simulation in this process (an agent mode), reading only:
    every turn, the merchant tax the economy assessed, what the merchants
    paid (absent before the correction) and what reached the treasuries,
    and the tithe base of the turn, and the tithe each civ's clergy pays
    into its treasury; every ``--every`` turns after the agent
    tick, the native pool (``domestic_credit_probe``'s measures: merchants,
    their wealth and satisfaction, Ginis) plus each occupation's share of
    agents and of their wealth. Works on trees before and after the
    correction. Writes ``RUN_DIR/probe_turns.jsonl``,
    ``RUN_DIR/tax_turns.jsonl``, ``RUN_DIR/tithe.jsonl`` and ``domestic_credit_probe``'s
    ``borrow.jsonl``; the CLI writes its usual files (give ``--output
    RUN_DIR/chronicle.md``).

``merchant_tax_probe.py summarize RUN_DIR [RUN_DIR ...] --json OUT``
    Per run: ``domestic_credit_probe``'s summary (credit, defaults, fiscal
    strain, PSI crises, revolts, the probe's means), the tax totals, the
    occupation shares and the wealth of each occupation (means over the
    sampled turns), the treasury and revenue over living civ-turns, and the
    agent rates per agent-turn as the regression oracle counts them
    (``agent_events.arrow`` over the probe's mean agent count).

``merchant_tax_probe.py compare OFF.json ON.json``
    Paired by seed (``domestic_credit_probe compare``).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import domestic_credit_probe as dcp  # noqa: E402

OCCUPATIONS = ("farmer", "soldier", "merchant", "scholar", "priest")
EVENT_CODES = {"migration": 1, "rebellion": 2, "occupation_switch": 3}


def _observe(world, bridge) -> dict:
    import numpy as np
    from chronicler.columnar import pylist
    row = dcp._observe(world, bridge)
    snap = bridge._sim.get_snapshot()
    occ = np.asarray(pylist(snap.column("occupation")))
    wealth = np.asarray(pylist(snap.column("wealth")), dtype=np.float64)
    total = float(wealth.sum())
    for code, name in enumerate(OCCUPATIONS):
        m = occ == code
        row[f"share_{name}"] = round(float(m.mean()), 6) if len(occ) else None
        row[f"wealth_share_{name}"] = round(float(wealth[m].sum()) / total, 6) if total > 0 else None
        row[f"wealth_mean_{name}"] = round(float(wealth[m].mean()), 6) if m.any() else None
    return row


def _merchant_income(world, economy_result) -> float | None:
    """This turn's merchant income (what the agent tick will pay them): each
    region's per-merchant trade income times the merchants standing there
    (from the live pool; approximate, as merchants may move before the
    agent tick)."""
    bridge = getattr(world, "_agent_bridge", None)
    if bridge is None:
        return None
    import numpy as np
    from chronicler.columnar import pylist
    snap = bridge._sim.get_snapshot()
    occ = np.asarray(pylist(snap.column("occupation")))
    reg = np.asarray(pylist(snap.column("region")))
    income = 0.0
    for r, region in enumerate(world.regions):
        per = economy_result.merchant_trade_incomes.get(region.name, 0.0)
        if per:
            income += per * int(((occ == 2) & (reg == r)).sum())
    return round(income, 6)


def _record_tax(out):
    """Wrap the Phase 2 treasury tax: per turn, the assessment, what the
    merchants paid (when the tree debits them) and what the treasuries were
    credited; and the tithe base."""
    import chronicler.simulation as sim
    orig = sim._apply_treasury_tax_from_economy

    def apply(world, acc, economy_result, *args, **kwargs):
        start = len(acc._changes) if acc is not None else 0
        result = orig(world, acc, economy_result, *args, **kwargs)
        if economy_result is not None and acc is not None:
            credited = sum(c.delta for c in acc._changes[start:] if c.stat == "treasury")
            paid = getattr(economy_result, "tax_collected", None)
            out.write(json.dumps({
                "turn": world.turn,
                "assessed": round(sum(economy_result.treasury_tax.values()), 6),
                "paid": None if paid is None else round(sum(paid.values()), 6),
                "credited": credited,
                "tithe_base": round(sum(economy_result.tithe_base.values()), 6),
                "carry": round(sum((getattr(world, "_treasury_tax_carry", {}) or {}).values()), 6),
                "merchant_income": _merchant_income(world, economy_result),
            }, separators=(",", ":")) + "\n")
        return result

    sim._apply_treasury_tax_from_economy = apply


def _record_tithe(out):
    """Wrap the clergy's tithe (``factions.compute_tithe_base``, called when
    a civ's clergy collects it): per collection, what reached the treasury."""
    import chronicler.factions as factions
    orig = factions.compute_tithe_base

    def compute(civ, economy_result=None, civ_idx=None):
        base = orig(civ, economy_result=economy_result, civ_idx=civ_idx)
        out.write(json.dumps({"civ": civ_idx, "tithe": int(factions.TITHE_RATE * base)},
                             separators=(",", ":")) + "\n")
        return base

    factions.compute_tithe_base = compute


def _run(run_dir: Path, main_args: list[str], every: int) -> None:
    import chronicler.simulation as sim
    run_dir.mkdir(parents=True, exist_ok=True)
    out = open(run_dir / "probe_turns.jsonl", "w")
    tax_out = open(run_dir / "tax_turns.jsonl", "w")
    borrow_out = open(run_dir / "borrow.jsonl", "w")
    tithe_out = open(run_dir / "tithe.jsonl", "w")
    dcp._record_borrowing(borrow_out)
    _record_tax(tax_out)
    _record_tithe(tithe_out)
    orig_turn = sim.run_turn_result

    def run_turn_result(world, action_selector, narrator, seed=0, agent_bridge=None, *a, **k):
        result = orig_turn(world, action_selector, narrator, seed, agent_bridge, *a, **k)
        if agent_bridge is not None and world.turn % every == 0:
            out.write(json.dumps(_observe(world, agent_bridge), separators=(",", ":")) + "\n")
            out.flush()
        return result

    sim.run_turn_result = run_turn_result
    import chronicler.main as cm
    sys.argv = ["chronicler"] + main_args
    try:
        cm.main()
    finally:
        out.close()
        tax_out.close()
        tithe_out.close()
        borrow_out.close()


def _rates(run_dir: Path, turns: int, agents: list[int]) -> dict:
    events = run_dir / "agent_events.arrow"
    if not events.exists() or not agents:
        return {}
    import pyarrow.ipc as ipc
    types = ipc.open_file(events).read_all().column("event_type").to_pylist()
    agent_turns = sum(agents) / len(agents) * turns
    return {f"rate_{k}": sum(1 for t in types if t == c or t == k) / agent_turns
            for k, c in EVENT_CODES.items()}


def summarize_run(run_dir: Path) -> dict:
    from chronicler.bundle_codec import load_bundle
    out = dcp.summarize_run(run_dir)
    rows = [json.loads(line) for line in (run_dir / "probe_turns.jsonl").read_text().splitlines() if line] \
        if (run_dir / "probe_turns.jsonl").exists() else []
    for name in OCCUPATIONS:
        for key in (f"share_{name}", f"wealth_share_{name}", f"wealth_mean_{name}"):
            vals = [r[key] for r in rows if r.get(key) is not None]
            out[f"{key}_mean"] = sum(vals) / len(vals) if vals else None
    tax = [json.loads(line) for line in (run_dir / "tax_turns.jsonl").read_text().splitlines() if line] \
        if (run_dir / "tax_turns.jsonl").exists() else []
    out["tax_assessed"] = sum(r["assessed"] for r in tax)
    out["tax_paid"] = sum(r["paid"] or 0.0 for r in tax)
    out["tax_credited"] = sum(r["credited"] for r in tax)
    out["tithe_base_mean"] = sum(r["tithe_base"] for r in tax) / len(tax) if tax else None
    tithe = run_dir / "tithe.jsonl"
    out["tithe_treasury"] = (sum(json.loads(line)["tithe"] for line in tithe.read_text().splitlines() if line)
                             if tithe.exists() else None)
    income = [r["merchant_income"] for r in tax if r.get("merchant_income") is not None]
    out["merchant_income"] = sum(income) if income else None
    out["tax_over_merchant_income"] = (out["tax_credited"] / out["merchant_income"]
                                       if out["merchant_income"] else None)
    bundle = load_bundle(run_dir / "chronicle_bundle.json")
    history = bundle.get("history") or []
    treasury, revenue = [], []
    for snap in history:
        alive = {n: c for n, c in (snap.get("civ_stats") or {}).items() if c.get("alive")}
        treasury += [c.get("treasury", 0) for c in alive.values()]
        fin = (snap.get("finance") or {}).get("civs") or {}
        revenue += [row.get("revenue", 0) for n, row in fin.items() if n in alive]
    out["treasury_mean"] = sum(treasury) / len(treasury) if treasury else None
    out["revenue_mean"] = sum(revenue) / len(revenue) if revenue else None
    out["tax_share_of_revenue"] = (out["tax_credited"] / sum(revenue)) if revenue and sum(revenue) else None
    turns = len(history)
    out.update(_rates(run_dir, turns, [r["agents"] for r in rows if r.get("agents")]))
    return out


def _summarize(dirs: list[Path], out_path: Path) -> None:
    found = []
    for d in dirs:
        found += [d] if (d / "chronicle_bundle.json").exists() else sorted(d.glob("seed_*"))
    runs = [summarize_run(d) for d in found if (d / "chronicle_bundle.json").exists()]
    out_path.write_text(json.dumps(runs, indent=1))
    print(f"{len(runs)} runs -> {out_path}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "run":
        rest = argv[1:]
        split = rest.index("--") if "--" in rest else len(rest)
        p = argparse.ArgumentParser(prog="merchant_tax_probe.py run")
        p.add_argument("run_dir", type=Path)
        p.add_argument("--every", type=int, default=10)
        a = p.parse_args(rest[:split])
        _run(a.run_dir, rest[split + 1:], a.every)
        return 0
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summarize")
    s.add_argument("dirs", nargs="+", type=Path)
    s.add_argument("--json", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("off", type=Path)
    c.add_argument("on", type=Path)
    a = parser.parse_args(argv)
    if a.cmd == "summarize":
        _summarize(a.dirs, a.json)
    else:
        print(dcp.compare(json.loads(a.off.read_text()), json.loads(a.on.read_text())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
