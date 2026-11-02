#!/usr/bin/env bash
# One fixed natural world, then the existing exact-resume live workflow.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
  cat >&2 <<'USAGE'
Usage: world-laboratory-example.sh generate|live|commands OUTPUT [NATIVE_PYTHON]
  generate  Create a fresh external seed-42 example and exact turn-8 checkpoint.
  live      Resume that checkpoint paused in the ordinary authenticated viewer.
  commands  Print the same CLI commands without generating or launching anything.
Use Python 3.13+ with a matching real chronicler_agents extension.
USAGE
  exit 2
fi
world_lab_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
world_lab_repo="$(cd -- "$world_lab_script_dir/.." && pwd)"
world_lab_python="${3:-${CHRONICLER_NATIVE_ENV:+$CHRONICLER_NATIVE_ENV/bin/python}}"
world_lab_python="${world_lab_python:-python3}"
export PYTHONPATH="$world_lab_repo/src"
export PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
"$world_lab_python" - "$world_lab_repo" "$1" "$2" <<'PY'
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from datetime import datetime, timezone

repo, mode, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]).expanduser().resolve()
if mode not in {"generate", "live", "commands"}:
    raise SystemExit("Choose generate, live, or commands.")
if output.is_relative_to(repo):
    raise SystemExit("Keep generated examples outside the source repository.")
base, live = output / "original", output / "live"
checkpoint = base / "checkpoints" / "turn_0008.ckpt"
base_command = [sys.executable, "-m", "chronicler.main", "--seed", "42", "--turns", "24",
                "--regions", "8", "--civs", "4", "--agents", "hybrid", "--grain-reserves",
                "--transaction-receipts", "--simulate-only", "--checkpoint-every", "8",
                "--checkpoint", str(base / "checkpoints" / "turn_{turn:04d}.ckpt"),
                "--output", str(base / "chronicle.md"), "--state", str(base / "state.json")]
live_command = [sys.executable, "-m", "chronicler.main", "--live", "--live-port", "0",
                "--resume", str(checkpoint), "--turns", "24", "--pause-every", "8",
                "--simulate-only", "--output", str(live / "chronicle.md"),
                "--state", str(live / "state.json")]
settings = {key: os.environ[key] for key in ("PYTHONPATH", "PYTHONHASHSEED", "RAYON_NUM_THREADS",
                                            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}

def shell_command(command):
    return shlex.join(["env", *(f"{key}={value}" for key, value in settings.items()), *command])

if mode == "commands":
    print("# Exact CLI argument lists. Use generate/live for provenance receipts and native/source probes.")
    print("umask 077")
    for destination, command in ((output, base_command), (live, live_command)):
        quoted = shlex.quote(str(destination))
        print(f"if test -e {quoted} || test -L {quoted}\nthen\n"
              "  echo 'Example destination exists; choose a fresh path.' >&2\n  exit 1\nfi")
        print(shell_command(command))
    raise SystemExit(0)
if mode == "generate" and (output.exists() or output.is_symlink()):
    raise SystemExit(f"Example destination already exists; preserved unchanged: {output}")
if mode == "live" and (live.exists() or live.is_symlink()):
    raise SystemExit(f"Live destination already exists; preserved unchanged: {live}")
if sys.version_info < (3, 13):
    raise SystemExit("Python 3.13 or newer is required.")
import chronicler
import chronicler_agents.chronicler_agents as native
from chronicler.batch_manifest import source_identity, native_identity, environment_identity
if importlib.util.find_spec("chronicler.what_if") is None:
    raise SystemExit("Integrate the what-if backend before generating or resuming this exact example.")
if not Path(chronicler.__file__).resolve().is_relative_to(repo):
    raise SystemExit("Python imported another Chronicler checkout.")
if (not any(native.__file__.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES)
        or not all(isinstance(getattr(native, name, None), type)
                   for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"))):
    raise SystemExit("A real compiled native runtime with all three simulator classes is required.")
source_status = subprocess.check_output(["git", "status", "--porcelain", "--", "src/chronicler", "chronicler-agents"], cwd=repo, text=True)
if source_status:
    raise SystemExit("Commit the simulation/native source before generating or resuming this exact example.")
os.umask(0o077)
identity = {"source": source_identity(), "native": native_identity(), "environment": environment_identity(),
            "native_source_tree": subprocess.check_output(["git", "rev-parse", "HEAD:chronicler-agents"], cwd=repo, text=True).strip(),
            "source_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).splitlines(),
            "script_sha256": hashlib.sha256((repo / "scripts/world-laboratory-example.sh").read_bytes()).hexdigest()}

def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def artifact(path):
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

if mode == "live":
    if not (output / "example-manifest.json").is_file() or not checkpoint.is_file():
        raise SystemExit("Generate this example first; its exact turn-8 checkpoint is required.")
    if live.exists() or live.is_symlink():
        raise SystemExit(f"Live destination already exists; preserved unchanged: {live}")
    # The ordinary checkpoint reader enforces package/native/environment identity.
    # Never add --resume-allow-mismatch to make a mismatched example appear exact.
    from chronicler.run_checkpoint import read_checkpoint
    loaded = read_checkpoint(checkpoint)
    if not loaded.exact or loaded.state.world.turn != 8:
        raise SystemExit("This example requires an exact checkpoint at turn 8.")
    live.mkdir(mode=0o700)
    write_json(live / "launch-receipt.json", {"state": "planned", "identity": identity,
               "checkpoint": artifact(checkpoint), "command": live_command, "settings": settings})
    os.chdir(repo)
    os.execvpe(sys.executable, live_command, os.environ)

if output.exists() or output.is_symlink():
    raise SystemExit(f"Example destination already exists; preserved unchanged: {output}")
output.mkdir(parents=True, mode=0o700, exist_ok=False)
manifest = {"schema_version": 1, "kind": "guided-world-laboratory-example", "state": "planned",
            "planned_at": datetime.now(timezone.utc).isoformat(), "identity": identity, "settings": settings,
            "command": base_command, "seed": 42, "mode": "hybrid", "turns": 24, "regions": 8, "civs": 4,
            "initial_state": "ordinary repository template; no manual state, stock or treasury edits",
            "intervention_example": {"constructed": True, "stat": "stability", "value": 70,
                                     "additional_turns": 8, "common_turn": 8},
            "limits": ["One fixed example is not a balance study or a population causal estimate.",
                       "Probe records native classes/hash; matching native build inputs require the active handoff.",
                       "The live what-if manifest is prepared separately before its two arms run."]}
write_json(output / "example-manifest.json", manifest)  # Durable plan precedes simulation.
write_json(output / "commands.json", {"generate": base_command, "live": live_command, "settings": settings})
base.mkdir(mode=0o700)
try:
    with (base / "run.log").open("w", encoding="utf-8") as log:
        subprocess.run(base_command, cwd=repo, check=True, stdout=log, stderr=subprocess.STDOUT)
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(base / "chronicle_bundle.json")
    turns = [row["turn"] for row in bundle["history"]]
    if turns != list(range(1, 25)) or not checkpoint.is_file():
        raise RuntimeError("The declared 24-turn history and turn-8 checkpoint did not complete.")
    if any("regional_population" not in row for row in bundle["history"]):
        raise RuntimeError("This checkout does not produce the required regional observations.")
    observations = {"snapshot_range": [1, 24], "events": len(bundle["events_timeline"]),
                    "checkpoint_turn": 8, "granary_flows": [], "event_examples": [],
                    "living_at_checkpoint": []}
    for row in bundle["history"]:
        for flow in (row.get("grain_reserves") or {}).get("flows", []):
            observations["granary_flows"].append({"snapshot": row["turn"], **flow})
        if row["turn"] == 8:
            observations["living_at_checkpoint"] = [name for name, civ in row["civ_stats"].items()
                                                    if civ.get("alive") and civ.get("regions")]
    observations["event_examples"] = [{"snapshot": e["turn"] + 1, "event_type": e["event_type"],
                                      "description": e["description"]}
                                     for e in bundle["events_timeline"]
                                     if e["event_type"] in {"loan_taken", "granary_opened", "famine", "war_declared"}][:12]
    write_json(output / "OBSERVATIONS.json", observations)
    manifest.update(state="completed", completed_at=datetime.now(timezone.utc).isoformat(),
                    observations=observations,
                    artifacts=[artifact(path) for path in sorted(base.rglob("*")) if path.is_file()])
    write_json(output / "example-manifest.json", manifest)
except BaseException as exc:
    manifest.update(state="failed", error=f"{type(exc).__name__}: {exc}")
    write_json(output / "example-manifest.json", manifest)
    raise
print(f"Created {base / 'chronicle_bundle.json'}")
print(f"Identity, hashes and actual observations: {output / 'example-manifest.json'}")
print("Resume paused at turn 8 using the same source/native environment:")
print(shlex.join([str(repo / "scripts/world-laboratory-example.sh"), "live", str(output), sys.executable]))
PY
