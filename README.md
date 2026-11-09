# Chronicler

A Python CLI that generates entire civilization histories through deterministic simulation + LLM narration. Give it a seed, a scenario, and a turn count — get back a complete chronicle with wars, famines, cultural renaissances, political collapses, and technological breakthroughs, all emerging from interacting systems rather than scripted events.

## How It Works

Chronicler runs a 10-phase turn loop that simulates environment, economy, politics, military, diplomacy, culture, technology, actions, ecology, and consequences. Each phase reads and mutates a shared world state. The simulation is **fully deterministic** — the same seed always produces the same history.

An optional **agent layer** (written in Rust) runs per-agent computation for demographics, wealth, satisfaction, migration, occupation, and other Phase 6 "living society" systems, feeding emergent behavior back into the civilization-level simulation.

The LLM **only narrates** — it never makes simulation decisions. You can run with local inference (LM Studio), Claude API, or Gemini API for narrative generation, or skip narration entirely with `--simulate-only`.

## Requirements

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** (recommended: installs the exact versions in `uv.lock`)
- **Rust 1.85+ toolchain** (for the `chronicler-agents` crate — optional, needed for agent mode)
- **LM Studio** or an API key for narration (optional — simulation runs without it)

## Current Status

Start from **`main`**. The [current status block](docs/CONTINUATION.md#current-status)
records the latest verified `main` commit, merged pull request, Tests run and gate state.

Start with the [recovery and archive index](docs/RECOVERY.md),
[current status](docs/CONTINUATION.md) (its dated history is in
[continuation-history.md](docs/superpowers/progress/continuation-history.md)),
[Windows/Mac/Linux setup](docs/DEVELOPMENT.md), and [agent instructions](AGENTS.md).
The [documentation map](docs/README.md) lists the per-system references,
validation notes, viewer guides and where the dated milestone history lives
(`docs/superpowers/`).

## Installation

```bash
# Clone the repo
git clone https://github.com/YotsuBotfds/Chronicler.git
cd Chronicler
git switch main

# Run the setup script
bash setup.sh            # Linux / Mac / Git Bash
setup.bat                # Windows Command Prompt
```

The setup script installs the Python dependencies into `.venv`: exactly from `uv.lock` when [uv](https://docs.astral.sh/uv/) is installed (recommended, as CI does), otherwise with an unlocked `pip install -e .` and a warning. It first removes any `chronicler_agents` already in `.venv`; if Rust is installed it then builds a fresh agent crate into `.venv`, so agent mode (`--agents`) works there, and it finishes by checking the result with `scripts/check_python_env.py`. `--no-rust` leaves `.venv` verified extension-free. Developers who run the no-Rust test lanes pass `--native-venv` to build into a separate native venv (`~/.venvs/chronicler-native`; `CHRONICLER_NATIVE_VENV` moves it) and keep `.venv` extension-free. See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#python-environments). Optional flags:

| Flag | Effect |
|------|--------|
| `--no-rust` | Skip Rust agent crate build |
| `--api` | Install Claude API narration support |
| `--gemini` | Install Gemini API narration support |

### Manual Installation

If you prefer to install manually (Linux/Mac paths; on Windows use `.venv\Scripts\python.exe`):

```bash
# Locked install from uv.lock (add --extra api / --extra gemini for API narration)
uv sync --frozen
.venv/bin/python scripts/check_python_env.py --expect no-native

# Without uv: unlocked, versions are whatever the package index serves today
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install -e ".[api]"      # (Optional) Claude API
.venv/bin/python -m pip install -e ".[gemini]"   # (Optional) Gemini API

# (Optional) Rust agent crate / native extension, in its own venv
NATIVE=~/.venvs/chronicler-native
UV_PROJECT_ENVIRONMENT=$NATIVE uv sync --frozen
uv pip install --python $NATIVE/bin/python "maturin>=1.5,<2"
source $NATIVE/bin/activate
cd chronicler-agents
python -m maturin develop --release --locked
cd ..

# Verify the compiled extension and its classes
python scripts/check_python_env.py --expect native
```

Rebuild the Rust extension with the native venv active (or `VIRTUAL_ENV` set to it). `maturin develop` installs into `VIRTUAL_ENV`, or into `./.venv` when none is set, which would break the no-native lane. `uv sync --frozen` removes a stray extension from `.venv`, and `scripts/check_python_env.py --expect no-native` confirms it is gone.

## Quick Start

For a no-narration run with a real viewer bundle and an exact save/resume check,
see the [local simulate, view, and resume walkthrough](docs/local-simulate-view-resume.md).

```bash
# Basic run — 50 turns, 4 civilizations, deterministic simulation + local LM narration
chronicler --seed 42 --turns 50 --civs 4 --regions 8 --output output/chronicle.md

# Simulation only (no LLM needed)
chronicler --seed 42 --turns 100 --simulate-only

# Hybrid agent path with validation sidecars (requires the Rust crate; with --native-venv, run from the native venv)
chronicler --seed 42 --turns 100 --agents hybrid --simulate-only --validation-sidecar

# Use a scenario
chronicler --seed 42 --turns 80 --scenario scenarios/two_empires.yaml

# Post-run narration with Claude API (requires ANTHROPIC_API_KEY)
chronicler --seed 42 --turns 100 --simulate-only
chronicler --narrate output/chronicle_bundle.json --narrator api --budget 50

# Post-run narration with Gemini API (requires GOOGLE_API_KEY)
chronicler --narrate output/chronicle_bundle.json --narrator gemini --budget 50

# Check narrated passages against the facts their narrator was given (no LLM;
# docs/integration/narration-provenance.md)
python -m chronicler.narration_audit output/chronicle_bundle.json

```

## Run Modes

| Flag | Description |
|------|-------------|
| *(default)* | Single run — simulate + narrate |
| `--simulate-only` | Run simulation without LLM narration |
| `--batch N` | Run N chronicles with sequential seeds |
| `--parallel [N]` | Parallel workers for batch mode; omit `N` to use `cpu_count - 1` |
| `--seed-range START-END` | Convenience form for setting `--seed` and `--batch` together |
| `--fork state.json` | Fork from a saved state with a new seed |
| `--interactive` | Pause at intervals for commands |
| `--narrate bundle.json` | Narrate a simulate-only bundle after the fact |
| `--narrate-output path.json` | Write narrated bundle output to a custom path |
| `--no-citations` | Narrator prompts without fact ids or the request to cite them (each entry still records the facts it was given) |
| `--analyze dir/` | Analyze a batch directory and produce `batch_report.json` |
| `--compare report.json` | Compare an analysis run against a baseline report |
| `--checkpoints 25,50,100` | Add checkpoint turns to analytics output |
| `--resume state.json` | Resume from a saved state |
| `--state-every K` | Write the resumable state/memory checkpoint every K turns (default 10; `1` = every turn); Ctrl-C finishes the turn and checkpoints it |

## Agent Modes

| Mode | Description |
|------|-------------|
| `off` | Aggregate-only simulation (default) |
| `demographics-only` | Agents handle birth/death only |
| `shadow` | Run both, compare outputs |
| `hybrid` | Full agent-driven simulation |

## Tuning

Simulation behavior can be tuned via CLI flags or YAML files:

```bash
# CLI multipliers
chronicler --seed 42 --turns 100 --aggression-bias 1.5 --trade-friction 0.8

# YAML tuning file
chronicler --seed 42 --turns 100 --tuning my_tuning.yaml

# Presets
chronicler --seed 42 --turns 100 --preset dark-age
```

Top-level CLI multipliers: `--aggression-bias`, `--tech-diffusion-rate`, `--resource-abundance`, `--trade-friction`, `--severity-multiplier`, `--cultural-drift-speed`, `--religion-intensity`, and `--secession-likelihood`.

Available presets: `pangaea`, `archipelago`, `golden-age`, `dark-age`, `ice-age`, `silk-road`

## Testing and Validation

```bash
# No-Rust Python lane: run from an environment where chronicler_agents is absent
# (.venv after `setup.sh --no-rust` or `--native-venv`;
# `python scripts/check_python_env.py --expect no-native` confirms it).
# Pure-Python tests should pass; native-only tests should skip.
python -m pytest -q

# Native Python lane: activate the native venv (`setup.sh --native-venv` sets
# it up and installs maturin there) and build a fresh chronicler_agents into it.
source ~/.venvs/chronicler-native/bin/activate
cd chronicler-agents
python -m maturin develop --release --locked
cd ..

# Preload/verify the real extension, then run Python tests.
python - <<'PY'
from importlib import util
from importlib.machinery import EXTENSION_SUFFIXES
import chronicler_agents as ca
import pytest

spec = util.find_spec("chronicler_agents.chronicler_agents")
origin = spec.origin if spec else ""
if not origin.endswith(tuple(EXTENSION_SUFFIXES)):
    raise SystemExit(f"chronicler_agents native submodule is not a compiled extension: {origin!r}")

for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
    cls = getattr(ca, name, None)
    if not isinstance(cls, type):
        raise SystemExit(f"{name} is not a real native class: {cls!r}")

raise SystemExit(pytest.main(["-q"]))
PY

# Rust test suite. cargo-nextest is optional; cargo test is the portable default.
cargo test --manifest-path chronicler-agents/Cargo.toml --quiet
cargo nextest run --manifest-path chronicler-agents/Cargo.toml

# Validate a generated batch directory with bundled oracles
python -m chronicler.validate --batch-dir output/some_batch --oracles all

# Gate an existing validation report without rerunning simulation/oracles.
# Exit 0 = selected profile passes, 2 = required oracle failed, 1 = bad input.
python -m chronicler.validation_gate --profile full --report output/m53/full/full_gate/batch_42/validate_report_full.json
python -m chronicler.validation_gate --profile full --report output/m53/full/full_gate/batch_42/validate_report_full.json --require-strict-regression
python -m chronicler.validation_gate --profile full \
  --report output/m53/full/full_gate/batch_42/validate_report_full.json \
  --decision-output output/m53/full/full_gate/batch_42/gate_decision_full.json \
  --summary-output output/m53/full/full_gate/batch_42/gate_summary_full.md

# Compare two validation reports without rerunning simulation/oracles.
# Add --fail-on-regression to return exit 2 for new required failures or strict-regression downgrades.
python -m chronicler.validation_compare --profile full \
  --baseline-report output/m53/previous/full_gate/batch_42/validate_report_full.json \
  --current-report output/m53/full/full_gate/batch_42/validate_report_full.json \
  --decision-output output/m53/full/full_gate/batch_42/compare_decision_full.json \
  --summary-output output/m53/full/full_gate/batch_42/compare_summary_full.md

# Canonical profile gates. Omit --seeds/--turns to use profile defaults:
# subset = 20 seeds x 200 turns; full = 200 seeds x 500 turns;
# determinism profiles = two duplicate-seed runs x 200 turns.
python scripts/m53b_run_validation.py --profile subset --output-root output/m53/subset
python scripts/m53b_run_validation.py --profile full --output-root output/m53/full
python scripts/m53b_run_validation.py --profile full --output-root output/m53/full-strict --require-strict-regression
python scripts/m53b_run_validation.py --profile full --output-root output/m53/full-compare \
  --baseline-report output/m53/previous/full_gate/batch_42/validate_report_full.json \
  --fail-on-regression

# Procedural worlds (32 regions x 10 civs per seed; --regions/--civs override):
# subset = 20 seeds x 200 turns; full = 100 seeds x 300 turns. Compare a
# procedural report only with a procedural baseline of the same world size.
python scripts/m53b_run_validation.py --profile subset --worldgen procedural --output-root output/m53/procedural-subset
python scripts/m53b_run_validation.py --profile full --worldgen procedural --output-root output/m53/procedural-full

# Per-system activity of batches (from their bundles), side by side.
python scripts/archive/world_systems_report.py template=output/m53/full/full_gate/batch_42 \
  procedural=output/m53/procedural-full/full_gate/batch_42
```

For focused iteration, prefer targeted test runs and rebuild the Rust extension inside the active virtual environment before hybrid-mode validation. The native lane should verify the real extension in-process before pytest to avoid stale wheels or test stubs masking native coverage.

See [ecology/goods coupling validation](docs/validation/economy-coupling.md) for harvest timing, finite resource labor, reserve-aware famine, and reproducible paired/native accounting experiments.

## Project Structure

```
src/chronicler/       # Python simulation, CLI, narration, analytics, detached experiments
chronicler-agents/    # Rust/PyO3 agent, ecology and politics runtimes (+ tests/, benches/)
viewer/               # React/TypeScript viewer (see viewer/README.md)
tests/                # Python test suite and fixtures
scripts/              # Gates, CI lanes, identity checks, reports (see scripts/README.md)
docs/                 # Documentation (start at docs/README.md)
scenarios/            # YAML scenario files
tuning/               # Tuning override YAML used by the M53 calibration runs
examples/             # Standalone usage examples (detached governance kernels)
```

## Output

Each run produces:
- **chronicle.md** — the narrated history as readable text
- **chronicle_bundle.json** — structured run data for post-run narration, analysis, and the viewer.
  Version 6 stores the history as changes between snapshots; read it with
  `chronicler.bundle_codec.load_bundle`, or write the plain layout with
  `scripts/bundle_v6.py decode` (see `docs/performance/bundle-v6.md`)
- **state.json** — serialized world state (for resume/fork)
- **memories_*.json** — per-civilization memory streams

Batch analysis writes:
- **batch_report.json** — aggregated metrics and checkpoint summaries for a batch directory

Canonical validation gates also preserve:
- **validate_report_*.json** — raw oracle results for the selected profile
- **gate_decision_*.json** — machine-readable profile adjudication, required failures, informational non-PASS statuses, and exit code
- **gate_summary_*.md** — concise human-readable gate summary, also published to the GitHub Actions step summary
- **run_manifest.json** — profile, seed/turn scale, report paths, gate status, optional comparison status, and reproducibility metadata

Report comparison writes optional **compare_decision_*.json** and **compare_summary_*.md** artifacts for baseline-vs-current gate changes, new/resolved required failures, strict-regression downgrades, and numeric diagnostic deltas. Comparator hard failures follow the selected validation profile: subset and determinism comparisons still show optional full-profile regression diagnostics, but `--fail-on-regression` only exits nonzero for diagnostics required by that profile.

validation JSON artifacts are written with strict JSON serialization and atomic same-directory replacement: `NaN`/`Infinity` and duplicate JSON keys are rejected rather than preserved as misleading evidence, interrupted writes should not leave truncated report artifacts, existing artifact permissions are preserved, new artifact permissions respect the process umask without mutating it, and the parent directory is fsynced after replacement where supported.

Full-profile regression reports include strict-vs-calibrated diagnostics such as `strict_regression_failed_checks`, `calibrated_floor_relaxed_checks`, and `regression_floor_diagnostics` so calibrated-floor passes explain exactly which strict floors still need tuning.

## License

This project is not currently licensed for redistribution.
