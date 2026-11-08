"""Retain every paired browser observation; bounded descriptive summaries."""
import json
import statistics
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
groups = []
for mode in report["config"]["worker_modes"]:
    for viewport in ("desktop", "phone"):
        rows = [r for r in report["measurements"] if r["mode"] == mode and r["viewport"] == viewport]
        group = {"mode": mode, "viewport": viewport, "metrics": {}}
        for metric in ("load", "cold_history", "warm_history"):
            samples = {variant: [r["timings_ms"][metric] for r in rows if r["variant"] == variant]
                       for variant in ("plain", "archive")}
            medians = {k: statistics.median(v) for k, v in samples.items()}
            paired = []
            for repeat in range(report["config"]["repeats"]):
                pair = {r["variant"]: r["timings_ms"][metric] for r in rows if r["repeat"] == repeat}
                paired.append(pair["archive"] - pair["plain"])
            allowed = (1.5 if metric == "load" else 1.2) * medians["plain"] + (500 if metric == "load" else 200)
            group["metrics"][metric] = {"samples_ms": samples, "medians_ms": medians,
                "ranges_ms": {k: [min(v), max(v)] for k, v in samples.items()},
                "paired_archive_minus_plain_ms": paired, "median_ratio": medians["archive"] / medians["plain"],
                "budget_archive_ms": allowed, "budget_met": medians["archive"] <= allowed}
        groups.append(group)
summary = {"samples": len(report["measurements"]), "elapsed_seconds": report["elapsed_seconds"],
           "all_visible_histories_equal": report.get("equal_visible_histories"), "groups": groups,
           "note": "Three repeats per pair; ranges and every adverse difference retained. Descriptive timing pilot, not statistical or simulation qualification."}
Path(sys.argv[2]).write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps([{k: g[k] for k in ("mode", "viewport")} | {
    metric: values["medians_ms"] for metric, values in g["metrics"].items()} for g in groups], indent=2))
