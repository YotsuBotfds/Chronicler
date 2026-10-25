#!/usr/bin/env python3
"""Per-run diplomacy and war numbers for one or more run batches.

``python scripts/diplomacy_report.py LABEL=BATCH_DIR [LABEL=BATCH_DIR ...] [--json OUT]``

Each batch directory holds ``seed_*/`` run directories (``state.json`` and
``chronicle_bundle.json``), as written by ``chronicler.main --seed-range`` or
the validation gate. Works for diplomacy-off batches too (treaty and ladder
columns are then zero). Prints a markdown table of per-run means:

* treaties signed by kind and broken (from ``state.diplomacy``);
* wars (campaign war records) and their mean duration in turns;
* subject relations formed (vassalization events) and the mean number of
  subject relations alive per turn, by ladder stage when diplomacy is on;
* polity ends: twilight absorptions, union annexations and conquests;
* polities alive at the end, and extinct worlds (no living population).

See docs/integration/diplomacy.md.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from chronicler.bundle_codec import load_bundle

TREATY_KINDS = ("peace", "non_aggression", "alliance", "trade_pact", "tribute")


def run_numbers(run_dir: Path) -> dict:
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    events = Counter(e["event_type"] for e in state["events_timeline"])
    ws = state.get("war_state", {})
    wars = ws.get("ended_wars", []) + ws.get("wars", [])
    durations = [((w["ended_turn"] if w.get("ended_turn") is not None else state["turn"]) - w["start_turn"])
                 for w in wars]
    dip = state.get("diplomacy") or {}
    treaties = dip.get("treaties", [])
    signed = Counter(t["kind"] for t in treaties)
    broken = Counter(t["kind"] for t in treaties if t.get("status") == "broken")
    counts = dip.get("counts", {})
    alive = sum(1 for c in state["civilizations"] if c["regions"])
    population = sum(r.get("population", 0) for r in state["regions"])
    subjects_per_turn = 0.0
    stage_turns: Counter = Counter()
    bundle_path = run_dir / "chronicle_bundle.json"
    if bundle_path.exists():
        history = load_bundle(bundle_path).get("history", [])
        for snap in history:
            rels = snap.get("vassal_relations", [])
            subjects_per_turn += len(rels)
            for vr in rels:
                stage_turns[vr.get("stage") or "legacy"] += 1
        if history:
            subjects_per_turn /= len(history)
            stage_turns = Counter({k: v / len(history) for k, v in stage_turns.items()})
    return {
        "seed": run_dir.name,
        "signed": {k: signed.get(k, 0) for k in TREATY_KINDS},
        "broken": sum(broken.values()),
        "broken_by_kind": dict(broken),
        "rejected": sum(v for k, v in counts.items() if k.startswith("rejected:")),
        "renewed": sum(v for k, v in counts.items() if k.startswith("renewed:")),
        "calls_to_arms": events.get("call_to_arms", 0),
        "aid_convoys": events.get("aid_convoy", 0),
        "wars": len(wars),
        "war_turns": sum(durations),
        "subjects_formed": events.get("vassalization", 0),
        "subjects_per_turn": subjects_per_turn,
        "stage_turns": dict(stage_turns),
        "promotions": events.get("vassal_promoted", 0),
        "loosenings": events.get("vassal_loosened", 0),
        "revolts": events.get("vassal_rebellion", 0),
        "twilight_absorptions": events.get("twilight_absorption", 0),
        "union_annexations": events.get("union_annexation", 0),
        "conquests": events.get("civ_conquered", 0),
        "alive": alive,
        "extinct": population <= 0,
        "counts": counts,
    }


def batch_numbers(batch: Path) -> list[dict]:
    runs = sorted(p for p in batch.glob("seed_*") if (p / "state.json").exists())
    return [run_numbers(p) for p in runs]


def summarize(runs: list[dict]) -> dict:
    n = max(1, len(runs))

    def mean(key):
        return sum(r[key] for r in runs) / n

    wars = sum(r["wars"] for r in runs)
    stages: Counter = Counter()
    for r in runs:
        stages.update(r["stage_turns"])
    return {
        "runs": len(runs),
        **{f"signed_{k}": sum(r["signed"][k] for r in runs) / n for k in TREATY_KINDS},
        "broken": mean("broken"), "rejected": mean("rejected"), "renewed": mean("renewed"),
        "calls_to_arms": mean("calls_to_arms"), "aid_convoys": mean("aid_convoys"),
        "wars": wars / n,
        "war_duration": (sum(r["war_turns"] for r in runs) / wars) if wars else 0.0,
        "subjects_formed": mean("subjects_formed"), "subjects_per_turn": mean("subjects_per_turn"),
        **{f"stage_{k}": v / n for k, v in sorted(stages.items())},
        "promotions": mean("promotions"), "loosenings": mean("loosenings"), "revolts": mean("revolts"),
        "twilight_absorptions": mean("twilight_absorptions"),
        "union_annexations": mean("union_annexations"), "conquests": mean("conquests"),
        "alive": mean("alive"), "extinct_worlds": sum(1 for r in runs if r["extinct"]),
    }


ROWS = [
    ("Treaties signed: peace", "signed_peace"), ("non-aggression", "signed_non_aggression"),
    ("alliance", "signed_alliance"), ("trade pact", "signed_trade_pact"), ("tribute", "signed_tribute"),
    ("Treaties broken", "broken"), ("Offers rebuffed", "rejected"), ("Renewals", "renewed"),
    ("Calls to arms answered", "calls_to_arms"), ("Aid convoys", "aid_convoys"),
    ("Wars", "wars"), ("Mean war duration (turns)", "war_duration"),
    ("Subject relations formed", "subjects_formed"), ("Subjects alive per turn", "subjects_per_turn"),
    ("  of which client", "stage_client"), ("  of which vassal", "stage_vassal"),
    ("  of which union", "stage_union"), ("  of which legacy (no stage)", "stage_legacy"),
    ("Ladder promotions", "promotions"), ("Ladder loosenings", "loosenings"),
    ("Vassal revolts", "revolts"), ("Twilight absorptions", "twilight_absorptions"),
    ("Union annexations", "union_annexations"), ("Conquests (state extinguished)", "conquests"),
    ("Polities alive at the end", "alive"), ("Extinct worlds (count)", "extinct_worlds"),
]


def markdown(labels: list[str], summaries: list[dict]) -> str:
    lines = ["| Per run (mean) | " + " | ".join(labels) + " |",
             "| --- | " + " | ".join("---" for _ in labels) + " |"]
    for title, key in ROWS:
        vals = []
        for s in summaries:
            v = s.get(key, 0.0)
            vals.append(str(v) if key == "extinct_worlds" else f"{v:.2f}")
        lines.append(f"| {title} | " + " | ".join(vals) + " |")
    lines.append("| Runs | " + " | ".join(str(s["runs"]) for s in summaries) + " |")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    out_json = None
    if "--json" in argv:
        i = argv.index("--json")
        out_json = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__)
        return 2
    labels, summaries, detail = [], [], {}
    for item in argv:
        label, _, path = item.partition("=")
        runs = batch_numbers(Path(path))
        labels.append(label)
        summaries.append(summarize(runs))
        detail[label] = {"summary": summaries[-1], "runs": runs}
    print(markdown(labels, summaries))
    if out_json is not None:
        out_json.write_text(json.dumps(detail, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
