"""Development activation report: ``--watershed-mode flow`` against ``record_only``.

For each procedural development world, compares a flow run with a
record_only run of the same seed and length (record_only changes nothing, so
its world is the world without the account): the water index (headwater
regions and regions with upstream inflow), food sufficiency and shortfall,
the water factor of effective capacity (``min(1, water / 0.5)``), soil, the
final effective capacity and population, droughts and floods (the account's,
what they did, the superseded river floods, the old river and coastal floods
of the record_only run), the flood spells (events and their lengths, the
consequences applied and withheld; ``flood_spells`` also reads the first B2
draft's records, where every turn above the channel acted), and the
downstream link (the water of regions with upstream inflow against their
upstream irrigation withdrawals). Development
worlds only (it refuses any other seed); labelled development-only evidence,
not an evaluation.

    python scripts/watershed_activation.py FLOW_DIR:RECORD_DIR [...] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

DEVELOPMENT_PROCEDURAL = (7, 11, 13, 17, 21, 31, 302, 303)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return math.fsum(xs) / len(xs) if xs else None


def _load(folder: Path) -> dict:
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(folder / "chronicle_bundle.json")
    seed = bundle["metadata"].get("seed")
    if seed not in DEVELOPMENT_PROCEDURAL or bundle["world_state"].get("geography") is None:
        raise SystemExit(f"refused: seed {seed!r} is not a procedural development world")
    return bundle


def _summary(bundle: dict) -> dict:
    regions = [r["name"] for r in bundle["world_state"]["regions"]]
    history = bundle["history"]
    first = next(s["livelihoods"]["watershed"] for s in history if "graph" in (s.get("livelihoods") or {}).get("watershed", {}))
    down = first["graph"]["down"]
    upstream = [r for r in range(len(regions)) if any(d == r for d in down)]
    headwater = [r for r in range(len(regions)) if r not in upstream]
    water = lambda s, rs: _mean(s["ecology"][regions[r]]["water"] for r in rs)
    out = {
        "water_all": _mean(water(s, range(len(regions))) for s in history),
        "water_headwater": _mean(water(s, headwater) for s in history),
        "water_upstream": _mean(water(s, upstream) for s in history),
        "water_factor": _mean(min(1.0, s["ecology"][n]["water"] / 0.5) for s in history for n in regions),
        "soil": _mean(s["ecology"][n]["soil"] for s in history for n in regions),
        "food_sufficiency": _mean(v for s in history for v in (s.get("food") or {}).get("sufficiency", [])),
        "food_shortfall_share": _mean((1.0 if v < 1.0 else 0.0) for s in history
                                      for v in (s.get("food") or {}).get("sufficiency", []) if v is not None),
    }
    ws = bundle["world_state"]["regions"]
    out["effective_capacity_end"] = math.fsum(
        max(int(r["carrying_capacity"] * r["capacity_modifier"] * r["ecology"]["soil"]
                * min(1.0, r["ecology"]["water"] / 0.5)), 1) for r in ws)
    counts = (history[-1].get("regional_population") or {}).get("counts")
    out["population_end"] = math.fsum(counts) if counts else None
    record = history[-1]["livelihoods"]["watershed"]
    out["counters"] = record["counters"]
    events = bundle["events_timeline"]
    out["river_floods"] = sum(1 for e in events if e.get("event_type") == "flood" and "river floods" in e.get("description", ""))
    out["coastal_floods"] = sum(1 for e in events if e.get("event_type") == "flood"
                                and "Flooding devastates" in e.get("description", ""))
    out["famines"] = sum(1 for e in events if "famine" in str(e.get("event_type", "")))
    # Downstream: water of regions with upstream inflow against their upstream withdrawals (the account's columns).
    pairs = []
    for s in history:
        w = s["livelihoods"]["watershed"]
        if not w.get("observed"):
            continue
        cols = w["regions"]
        for r in upstream:
            ups = [u for u in range(len(regions)) if _drains_into(down, u, r)]
            pairs.append((math.fsum(cols["withdrawal"][u] for u in ups), cols["index_derived"][r]))
    with_w = [d for w, d in pairs if w > 0]
    without = [d for w, d in pairs if w == 0]
    out["flood_spells"] = flood_spells(history)
    out["downstream_index_with_upstream_irrigation"] = _mean(with_w)
    out["downstream_index_without_upstream_irrigation"] = _mean(without)
    return out


def flood_spells(history: list[dict]) -> dict:
    """Flood spells of a flow history. A B2 record keeps flood events (onset
    records, open and ended events); a record of the first B2 draft (before
    the review) listed every region-turn above the channel, each with a
    consequence, so its spells are runs of consecutive flood turns."""
    records = [s["livelihoods"]["watershed"] for s in history]
    events = "flood_events" in records[-1]
    lengths, consequences, withheld = [], 0, 0
    if events:
        open_at = {}
        for w in records:
            if not w.get("observed"):
                continue
            for f in w["floods"]:
                consequences += 1 if "consequence" in f else 0
                withheld += 1 if "withheld_by" in f else 0
            lengths += [e["turns"] for e in w["flood_events"]["ended"]]
            open_at = {e["region"]: e["turns"] for e in w["flood_events"]["open"]}
        lengths += list(open_at.values())
    else:
        run: dict[int, int] = {}
        for w in records:
            if not w.get("observed"):
                continue
            flooded = {f["region"] for f in w["floods"]}
            consequences += sum(1 for f in w["floods"] if f.get("consequence"))
            for r in list(run):
                if r not in flooded:
                    lengths.append(run.pop(r))
            for r in flooded:
                run[r] = run.get(r, 0) + 1
        lengths += list(run.values())
    lengths.sort()
    return {"format": "events" if events else "region-turns", "spells": len(lengths),
            "median": lengths[len(lengths) // 2] if lengths else 0, "longest": lengths[-1] if lengths else 0,
            "consequences": consequences, "withheld": withheld}


def _drains_into(down, u, r):
    node, hops = down[u], 0
    while node >= 0 and hops <= len(down):
        if node == r:
            return True
        node, hops = down[node], hops + 1
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pairs", nargs="+", help="FLOW_DIR:RECORD_DIR")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    rows = []
    for pair in args.pairs:
        flow_dir, record_dir = (Path(p) for p in pair.split(":"))
        flow, record = _load(flow_dir), _load(record_dir)
        if flow["metadata"]["seed"] != record["metadata"]["seed"]:
            raise SystemExit("a pair must be one seed")
        rows.append({"seed": flow["metadata"]["seed"], "flow": _summary(flow), "record_only": _summary(record)})
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    keys = ["water_all", "water_headwater", "water_upstream", "water_factor", "soil", "food_sufficiency",
            "food_shortfall_share", "effective_capacity_end", "population_end"]
    print("Development worlds only; flow against record_only (the world without the account).\n")
    print("| World | " + " | ".join(keys) + " |")
    print("| --- | " + " | ".join("---" for _ in keys) + " |")
    for row in rows:
        cells = []
        for k in keys:
            f, r = row["flow"][k], row["record_only"][k]
            cells.append("-" if f is None or r is None else f"{f:.3g} / {r:.3g}")
        print(f"| procedural {row['seed']} | " + " | ".join(cells) + " |")
    print("\n| World | Droughts (flow / record-only account) | Floods that acted (flow) | Superseded river floods | "
          "River floods (record only) | Coastal floods (flow / record only) | Downstream index with / without upstream irrigation (flow) |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        f, r = row["flow"], row["record_only"]
        dw, dn = f["downstream_index_with_upstream_irrigation"], f["downstream_index_without_upstream_irrigation"]
        print(f"| procedural {row['seed']} | {f['counters']['droughts_declared']} / {r['counters']['droughts_declared']} | "
              f"{f['counters'].get('flood_consequences')} | {f['counters'].get('superseded_river_floods')} | "
              f"{r['river_floods']} | {f['coastal_floods']} / {r['coastal_floods']} | "
              f"{'-' if dw is None else f'{dw:.3f}'} / {'-' if dn is None else f'{dn:.3f}'} |")
    print("\n| World | Flood spells (flow) | Median / longest spell, turns | Consequences applied | Withheld |")
    print("| --- | --- | --- | --- | --- |")
    for row in rows:
        s = row["flow"]["flood_spells"]
        print(f"| procedural {row['seed']} | {s['spells']} ({s['format']}) | {s['median']} / {s['longest']} | "
              f"{s['consequences']} | {s['withheld']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
