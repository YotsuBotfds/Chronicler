#!/usr/bin/env python3
"""Domestic credit: what real lenders do to debt, defaults, fiscal crises and
the distribution of merchant wealth.

``domestic_credit_probe.py run RUN_DIR -- <chronicler.main arguments>``
    Runs one simulation in this process (an agent mode) and, every
    ``--every`` turns after the agent tick, reads the native pool (reading
    only): the merchants' number, total wealth and mean satisfaction, all
    agents' mean satisfaction, the Gini of merchant agents' wealth (the
    world's merchants, and the mean over civs by affinity), the Gini of
    all agents' wealth, and how merchant
    wealth is spread over regions (its Gini over populated regions and the
    share of the richest region). Works with the switch on or off and with
    an extension that predates it. Writes ``RUN_DIR/probe_turns.jsonl``,
    and ``RUN_DIR/borrow.jsonl`` with one row per borrowing call of the
    fiscal tick (turn, civ, at war, the request and its peacetime part,
    domestic and foreign amounts raised); the CLI writes its usual files
    (give ``--output RUN_DIR/chronicle.md``).

``domestic_credit_probe.py summarize RUN_DIR [RUN_DIR ...] --json OUT``
    Per run: the means of the probe's measures over its sampled turns (and
    at the last one), and from the bundle and final state: domestic and
    foreign issuance (finance totals), loans, defaults and debasements at
    the end, debt over revenue (median and 90th percentile over living
    civ-turns), fiscal-strain onsets, PSI crises, revolts, and the
    domestic-credit books (lent, interest, repaid and written off by kind of
    lender, defaults that hit lenders, grievance region-turns); from the
    turn snapshots, domestic and foreign issuance before turns 30 and 60,
    the largest city and guild purses, the longest stretch a civ carries
    debt of eight turns of revenue and the civ-turns paying half the
    revenue in interest; from ``borrow.jsonl`` (run mode), what domestic
    and foreign lenders raised at war and the part beyond the peacetime
    request (the war chest).

``domestic_credit_probe.py compare OFF.json ON.json``
    Paired by seed: each measure's mean in both arms and the mean
    difference with its standard error, as a Markdown table.

See docs/integration/domestic-credit.md.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path


def gini(values) -> float:
    xs = sorted(max(0.0, float(v)) for v in values)
    n = len(xs)
    total = sum(xs)
    if n == 0 or total <= 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2.0 * cum) / (n * total) - (n + 1.0) / n


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def _observe(world, bridge) -> dict:
    import numpy as np
    from chronicler.columnar import pylist
    snap = bridge._sim.get_snapshot()
    occ = np.asarray(pylist(snap.column("occupation")))
    reg = np.asarray(pylist(snap.column("region")))
    civ = np.asarray(pylist(snap.column("civ_affinity")))
    wealth = np.asarray(pylist(snap.column("wealth")), dtype=np.float64)
    sat = np.asarray(pylist(snap.column("satisfaction")), dtype=np.float64)
    m = occ == 2
    by_region = []
    for r, region in enumerate(world.regions):
        if region.population > 0:
            by_region.append(float(wealth[m & (reg == r)].sum()))
    civ_ginis = [gini(wealth[m & (civ == c)]) for c in sorted(set(civ[m].tolist()))
                 if int((m & (civ == c)).sum()) >= 3]
    total = float(wealth[m].sum())
    return {
        "turn": world.turn,
        "merchants": int(m.sum()),
        "merchant_wealth": round(total, 4),
        "merchant_satisfaction": round(float(sat[m].mean()), 6) if m.any() else None,
        "satisfaction": round(float(sat.mean()), 6) if len(sat) else None,
        "merchant_gini": round(gini(wealth[m]), 6),
        "merchant_gini_civ": round(sum(civ_ginis) / len(civ_ginis), 6) if civ_ginis else None,
        "agent_gini": round(gini(wealth), 6),
        "region_gini": round(gini(by_region), 6),
        "top_region_share": round(max(by_region) / total, 6) if total > 0 and by_region else None,
        "agents": int(len(occ)),
    }


def _peace_request(world, civ_idx: int, civ, f, proj: int) -> int:
    """What the fiscal tick would ask for at peace (obligations plus a turn
    of upkeep, and the buffer), recomputed from the books before they are
    paid; the upkeep is approximate (its fractional carry is not known)."""
    from chronicler import finance as F
    upkeep = int((F.ARMY_UPKEEP_PER_MILITARY * max(0, civ.military)
                  + F.ADMIN_PER_REGION * len(civ.regions)
                  + F.ADMIN_PER_100_POP * max(0, civ.population) / 100.0) * f.price_index)
    service = 0
    for loan in world.finance.loans:
        if loan.borrower == civ_idx and loan.principal > 0:
            service += int(loan.principal * loan.rate + loan.interest_carry)
            service += min(loan.principal, int(math.ceil(loan.original / max(1, loan.term))))
    target = upkeep + service + int(F.MIN_RESERVE_TURNS * upkeep)
    return target - proj + int(F.BORROW_BUFFER_TURNS * upkeep) if proj < target else 0


def _record_borrowing(out):
    """Wrap ``finance._borrow``: one row per call (turn, civ, at war, the
    request and its peacetime part, domestic and foreign amounts raised)."""
    from chronicler import finance as F
    orig = F._borrow

    def _borrow(world, civ_idx, civ, f, gap, book, *args, **kwargs):
        totals = world.finance.totals
        dom0, for0 = totals["issued_domestic"], totals["issued_foreign"]
        proj = book.proj[civ_idx]
        row = {"turn": world.turn, "civ": civ_idx,
               "war": any(civ.name in pair for pair in world.active_wars),
               "gap": gap, "peace_gap": _peace_request(world, civ_idx, civ, f, proj),
               "revenue": round(f.revenue_ema, 3)}
        raised = orig(world, civ_idx, civ, f, gap, book, *args, **kwargs)
        row["dom"] = totals["issued_domestic"] - dom0
        row["foreign"] = totals["issued_foreign"] - for0
        out.write(json.dumps(row, separators=(",", ":")) + "\n")
        return raised

    F._borrow = _borrow


def _run(run_dir: Path, main_args: list[str], every: int) -> None:
    import chronicler.simulation as sim
    run_dir.mkdir(parents=True, exist_ok=True)
    out = open(run_dir / "probe_turns.jsonl", "w")
    borrow_out = open(run_dir / "borrow.jsonl", "w")
    _record_borrowing(borrow_out)
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
        borrow_out.close()


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------

PROBE_KEYS = ("merchants", "merchant_wealth", "merchant_satisfaction", "satisfaction", "merchant_gini",
              "merchant_gini_civ", "agent_gini", "region_gini", "top_region_share")


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


HEAVY_DEBT_TURNS = 8.0   # debt of this many turns of revenue (four fifths of finance's ceiling)
EARLY_TURNS = (30, 60)


def _history_measures(history: list) -> dict:
    """From the bundle's turn snapshots: domestic issuance early in the run
    (finance's cumulative totals), the largest city and guild purses, and
    how long civs carry heavy debt or pay half their revenue in interest."""
    out: dict = {}
    for limit in EARLY_TURNS:
        rows = [s for s in history if isinstance(s, dict) and s.get("turn", 0) < limit and s.get("finance")]
        totals = rows[-1]["finance"].get("totals", {}) if rows else {}
        out[f"issued_domestic_before_{limit}"] = totals.get("issued_domestic", 0)
        out[f"issued_foreign_before_{limit}"] = totals.get("issued_foreign", 0)
    city_max = guild_max = 0.0
    streak: dict[str, int] = {}
    longest = heavy_turns = half_turns = 0
    for snap in history:
        if not isinstance(snap, dict):
            continue
        for c in ((snap.get("cities") or {}).get("cities") or []):
            city_max = max(city_max, float(c.get("wealth") or 0.0))
        for g in ((snap.get("guilds") or {}).get("guilds") or []):
            guild_max = max(guild_max, float(g.get("wealth") or 0.0))
        civs = ((snap.get("finance") or {}).get("civs") or {})
        for name, row in civs.items():
            rev = max(row.get("revenue_ema", 0.0), 1.0)
            if row.get("debt", 0) >= HEAVY_DEBT_TURNS * rev:
                streak[name] = streak.get(name, 0) + 1
                heavy_turns += 1
                longest = max(longest, streak[name])
            else:
                streak[name] = 0
            if row.get("interest", 0) >= 0.5 * rev:
                half_turns += 1
        for name in list(streak):
            if name not in civs:
                streak[name] = 0
    out["city_purse_max"] = city_max
    out["guild_purse_max"] = guild_max
    out["heavy_debt_streak_max"] = longest
    out["heavy_debt_civ_turns"] = heavy_turns
    out["interest_over_half_revenue_civ_turns"] = half_turns
    return out


def _borrow_measures(path: Path) -> dict:
    """From ``borrow.jsonl`` (run mode): what was raised at war, and the part
    of it beyond the peacetime request (the war chest; domestic lenders are
    asked first, so they fund the peacetime part first)."""
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    dom = sum(r["dom"] for r in rows)
    war = [r for r in rows if r["war"]]
    out = {
        "borrow_calls": len(rows),
        "dom_issued_at_war": sum(r["dom"] for r in war),
        "dom_war_chest": sum(max(0, r["dom"] - r["peace_gap"]) for r in war),
        "foreign_issued_at_war": sum(r["foreign"] for r in war),
        "foreign_war_chest": sum(max(0, r["dom"] + r["foreign"] - max(r["peace_gap"], r["dom"])) for r in war),
    }
    out["dom_war_share"] = out["dom_issued_at_war"] / dom if dom else None
    out["dom_war_chest_share"] = out["dom_war_chest"] / dom if dom else None
    return out


def summarize_run(run_dir: Path) -> dict:
    from chronicler.bundle_codec import load_bundle
    probe = run_dir / "probe_turns.jsonl"
    rows = [json.loads(line) for line in probe.read_text().splitlines() if line] if probe.exists() else []
    out: dict = {"run": run_dir.name}
    for key in PROBE_KEYS:
        vals = [r[key] for r in rows if r.get(key) is not None]
        out[f"{key}_mean"] = sum(vals) / len(vals) if vals else None
        out[f"{key}_last"] = vals[-1] if vals else None
    bundle = load_bundle(run_dir / "chronicle_bundle.json")
    seed = (bundle.get("metadata") or {}).get("seed")
    out["seed"] = seed
    events = bundle.get("events_timeline") or []
    types = Counter(e["event_type"] for e in events)
    out["loans"] = types.get("loan_taken", 0)
    domestic = [e for e in events if e["event_type"] == "loan_taken" and len(e.get("civs") or []) <= 1]
    out["domestic_loans"] = len(domestic)
    out["domestic_loans_before_30"] = sum(1 for e in domestic if e["turn"] < 30)
    out["defaults"] = types.get("state_default", 0)
    out["debasements"] = types.get("debasement", 0)
    out["fiscal_strain_onsets"] = sum(1 for e in events if e["event_type"] == "fiscal_strain"
                                      and e.get("episode") in (None, "onset"))
    out["psi_crises"] = types.get("psi_crisis", 0)
    out["fiscal_psi_crises"] = sum(1 for e in events if e["event_type"] == "psi_crisis"
                                   and "fiscal" in (e.get("description") or ""))
    out["revolts"] = types.get("revolt", 0) + types.get("urban_revolt", 0)
    out["guild_movements_after_default"] = sum(
        1 for e in events if e["event_type"] == "movement_founded"
        and "repudiated its loans" in (e.get("description") or ""))
    ratios = []
    for snap in bundle.get("history") or []:
        for row in ((snap.get("finance") or {}).get("civs") or {}).values():
            ratios.append(row["debt"] / max(row["revenue_ema"], 1.0))
    out["debt_ratio_p50"] = _pct(ratios, 0.5)
    out["debt_ratio_p90"] = _pct(ratios, 0.9)
    out["debt_ratio_mean"] = sum(ratios) / len(ratios) if ratios else 0.0
    out.update(_history_measures(bundle.get("history") or []))
    out.update(_borrow_measures(run_dir / "borrow.jsonl"))
    state_path = run_dir / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else bundle.get("world_state") or {}
    totals = (state.get("finance") or {}).get("totals") or {}
    for key in ("issued_domestic", "issued_foreign", "interest_domestic", "interest_foreign",
                "written_off", "seigniorage"):
        out[key] = totals.get(key, 0)
    issued = out["issued_domestic"] + out["issued_foreign"]
    out["foreign_share"] = out["issued_foreign"] / issued if issued else None
    books = state.get("domestic_credit") or {}
    for key, value in (books.get("totals") or {}).items():
        out[f"dc_{key}"] = value
    out["dc_defaults_on_lenders"] = books.get("defaults_on_lenders", 0)
    out["dc_merchant_due"] = round(sum(books.get("merchant_due") or []), 6)
    grievance = 0
    for snap in bundle.get("history") or []:
        grievance += len(((snap.get("finance") or {}).get("domestic_credit") or {}).get("grievance") or {})
    out["dc_grievance_region_turns"] = grievance
    last = (bundle.get("history") or [{}])[-1]
    alive = [c for c in (last.get("civ_stats") or {}).values() if c.get("alive")]
    out["polities_alive"] = len(alive)
    out["population_end"] = sum(c.get("population", 0) for c in alive)
    return out


def _summarize(dirs: list[Path], out_path: Path) -> None:
    found = []
    for d in dirs:   # run directories, or batch directories holding seed_*/
        found += [d] if (d / "chronicle_bundle.json").exists() else sorted(d.glob("seed_*"))
    runs = [summarize_run(d) for d in found if (d / "chronicle_bundle.json").exists()]
    out_path.write_text(json.dumps(runs, indent=1))
    print(f"{len(runs)} runs -> {out_path}")


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

def compare(off: list[dict], on: list[dict]) -> str:
    a = {r["seed"]: r for r in off}
    b = {r["seed"]: r for r in on}
    seeds = sorted(set(a) & set(b))
    keys = [k for k in on[0] if k not in ("run", "seed")] if on else []
    lines = [f"Paired runs: {len(seeds)}", "",
             "| measure | off | on | on - off | SE |", "| --- | ---: | ---: | ---: | ---: |"]
    for key in keys:
        pairs = []
        for s in seeds:
            x, y = a[s].get(key), b[s].get(key)
            if key.startswith("dc_"):   # the books of the switch: none while off
                x, y = (0 if x is None else x), (0 if y is None else y)
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                pairs.append((float(x), float(y)))
        if not pairs:
            continue
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        ds = [y - x for x, y in pairs]
        mean_d = sum(ds) / len(ds)
        se = (math.sqrt(sum((d - mean_d) ** 2 for d in ds) / (len(ds) - 1)) / math.sqrt(len(ds))
              if len(ds) > 1 else 0.0)
        lines.append(f"| {key} | {sum(xs) / len(xs):.4g} | {sum(ys) / len(ys):.4g} | {mean_d:+.4g} | {se:.3g} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "run":
        rest = argv[1:]
        split = rest.index("--") if "--" in rest else len(rest)
        p = argparse.ArgumentParser(prog="domestic_credit_probe.py run")
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
        print(compare(json.loads(a.off.read_text()), json.loads(a.on.read_text())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
