#!/usr/bin/env python3
"""Generate three bounded, narration-free examples with the existing CLI.

Bulk outputs remain outside the repository. This does not install or build a
native runtime: use a native interpreter whose build matches this checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RECIPES = (
    ("aggregate-archive", "Repository template; aggregate populations, no native runtime",
     "aggregate", ["--seed", "7", "--turns", "24", "--regions", "6", "--civs", "3", "--agents", "off"]),
    ("grain-and-finance", "Repository template; naturally evolving native economy and granaries",
     "native", ["--seed", "42", "--turns", "60", "--regions", "8", "--civs", "4", "--agents", "hybrid",
                "--grain-reserves", "--transaction-receipts"]),
    ("procedural-health", "Procedurally generated geography; native care and learning records",
     "native", ["--seed", "11", "--turns", "40", "--regions", "12", "--civs", "4", "--agents", "hybrid",
                "--worldgen", "procedural", "--health-care", "--scholarship"]),
)
SETTINGS = {"PYTHONPATH": str(ROOT / "src"), "PYTHONHASHSEED": "0", "RAYON_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
PROBE = r'''
import hashlib, importlib.machinery, importlib.util, json, pathlib, sys, sysconfig
import chronicler
if sys.version_info < (3, 13):
    raise SystemExit("Python 3.13 or newer is required")
expected = sys.argv[1] == "native"
spec = importlib.util.find_spec("chronicler_agents")
if (spec is not None) != expected:
    raise SystemExit("Select separate native and native-absent Python interpreters")
result = dict(python=sys.version, abi=sysconfig.get_config_var("SOABI"), project_import=chronicler.__file__)
if expected:
    import chronicler_agents.chronicler_agents as native
    if not any(native.__file__.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES):
        raise SystemExit("A real compiled native module is required")
    if not all(isinstance(getattr(native, key, None), type) for key in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")):
        raise SystemExit("The native module lacks required simulator classes")
    result.update(native_import=native.__file__, native_sha256=hashlib.sha256(pathlib.Path(native.__file__).read_bytes()).hexdigest())
print(json.dumps(result))
'''


def command(python: str, args: list[str], folder: Path) -> list[str]:
    return [python, "-m", "chronicler.main", *args, "--simulate-only",
            "--output", str(folder / "chronicle.md"), "--state", str(folder / "state.json")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Fresh external output directory; existing paths are refused")
    parser.add_argument("--aggregate-python", required=True, help="Python 3.13+ with chronicler_agents absent")
    parser.add_argument("--native-python", required=True, help="Python 3.13+ with a matching real native extension")
    parser.add_argument("--commands-only", action="store_true", help="Print the exact shell-safe run commands without executing")
    options = parser.parse_args()
    output = options.output.expanduser().resolve()
    if output.is_relative_to(ROOT):
        parser.error("Keep generated worlds outside the source repository")
    interpreters = {"aggregate": options.aggregate_python, "native": options.native_python}
    commands = [command(interpreters[kind], args, output / name) for name, _, kind, args in RECIPES]
    lines = []
    for (name, _, _, _), cmd in zip(RECIPES, commands):
        folder = shlex.quote(str(output / name))
        lines.append(f"if test -e {folder}\nthen\n  echo 'Example folder exists; choose a fresh output path.' >&2\n  exit 1\nfi\n"
                     + shlex.join(["env", *(f"{key}={value}" for key, value in SETTINGS.items()), *cmd]))
    if options.commands_only:
        print("\n".join(lines))
        return
    if output.exists():
        parser.error(f"Output already exists; preserved unchanged: {output}. Choose a fresh directory.")
    env = dict(os.environ, **SETTINGS)
    probes = {}
    for kind, python in interpreters.items():
        probe = subprocess.run([python, "-c", PROBE, kind], cwd=ROOT, env=env, check=True, capture_output=True, text=True)
        probes[kind] = json.loads(probe.stdout)
        if not Path(probes[kind]["project_import"]).resolve().is_relative_to(ROOT):
            raise RuntimeError("Interpreter imported another Chronicler checkout")
    output.mkdir(parents=True, exist_ok=False)
    (output / "commands.sh").write_text("#!/usr/bin/env bash\nset -e\n" + "\n".join(lines) + "\n")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()
    native_tree = subprocess.check_output(["git", "rev-parse", "HEAD:chronicler-agents"], cwd=ROOT, text=True).strip()
    manifest = {"kind": "guided-chronicler-examples", "version": 1, "source_commit": source,
                "native_source_tree": native_tree,
                "source_status": dirty, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "runtime": probes, "settings": SETTINGS, "examples": []}
    sys.path.insert(0, str(ROOT / "src"))
    from chronicler.bundle_codec import load_bundle

    guide = ["# Guided Chronicler examples", "", f"Source: `{source}`.",
             "No manually edited state, market, treasury or event inputs. No narration/API calls.",
             "Template starts use the repository's existing map; the procedural start generates geography.",
             "These small selected examples are not evidence of general balance or a policy effect.", "",
             "Start the viewer, choose **Open Existing**, and choose each `chronicle_bundle.json` below.",
             "Saved world details explains mode and available history. Checkpoint and state files are different file types.",
             "Use **Compare turns and inspect history** after selecting the later turn; start with 1 versus 10.",
             "Use **Compare saved runs** for different examples; differences in seeds, horizons and modes are exploratory.", ""]
    for (name, description, kind, _), cmd in zip(RECIPES, commands):
        folder = output / name
        folder.mkdir()
        with (folder / "run.log").open("w") as log:
            subprocess.run(cmd, cwd=ROOT, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
        bundle_path = folder / "chronicle_bundle.json"
        data = load_bundle(bundle_path)
        turns = [row["turn"] for row in data["history"]]
        if not turns or max(turns) != data["metadata"]["total_turns"]:
            raise RuntimeError(f"Example {name} did not complete its declared horizon")
        row = {"name": name, "description": description, "runtime": kind, "command": cmd,
               "bundle": str(bundle_path), "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
               "seed": data["metadata"]["seed"], "snapshot_range": [min(turns), max(turns)],
               "events": len(data["events_timeline"]), "snapshots": len(turns)}
        manifest["examples"].append(row)
        (output / "examples.json").write_text(json.dumps(manifest, indent=2) + "\n")
        guide.extend([f"## {name}", "", description + ".", f"Bundle: `{bundle_path}`.",
                      f"Seed {row['seed']}; recorded snapshots {min(turns)}–{max(turns)}; {row['events']} timeline records.", ""])
        if name == "aggregate-archive":
            guide.append("Inspect population, territory and treasury. Food observations may be absent: unknown is not zero.")
        elif name == "grain-and-finance":
            guide.append("Choose Trade → Food and inspect granary purchases/releases; choose Finance for borrowing and debt. Neither shortage-first priority nor delayed public shipments is enabled.")
        else:
            guide.append("Inspect the generated map and region ownership. Choose Epidemics for the Health care panel and Learning for seats of learning; enabling a system does not guarantee a notable outcome.")
        seen = set()
        for event in data["events_timeline"]:
            if event["event_type"] not in {"war_declared", "loan_taken", "granary_opened", "occupational_injury", "seat_founded", "famine"} or event["event_type"] in seen:
                continue
            seen.add(event["event_type"])
            guide.append(f"- At snapshot {event['turn'] + 1}, inspect the record of step {event['turn']}: {event['description'].replace(chr(10), ' ')}")
            if len(seen) == 4:
                break
        guide.append("")
        print(f"Created {name}: {bundle_path}")
    (output / "WALKTHROUGH.md").write_text("\n".join(guide) + "\n")
    print(f"Guide and provenance: {output / 'WALKTHROUGH.md'}; {output / 'examples.json'}")


if __name__ == "__main__":
    main()
