# Chronicler

A Python CLI that generates entire civilization histories through deterministic simulation + LLM narration. Give it a seed, a scenario, and a turn count — get back a complete chronicle with wars, famines, cultural renaissances, political collapses, and technological breakthroughs, all emerging from interacting systems rather than scripted events.

## How It Works

Chronicler runs a 10-phase turn loop that simulates environment, economy, politics, military, diplomacy, culture, technology, actions, ecology, and consequences. Each phase reads and mutates a shared world state. The simulation is **fully deterministic** — the same seed always produces the same history.

An optional **agent layer** (written in Rust) runs per-agent computation for demographics, wealth, satisfaction, migration, occupation, and other Phase 6 "living society" systems, feeding emergent behavior back into the civilization-level simulation.

The LLM **only narrates** — it never makes simulation decisions. You can run with local inference (LM Studio), Claude API, or Gemini API for narrative generation, or skip narration entirely with `--simulate-only`.

## Requirements

- **Python 3.13+**
- **Rust toolchain** (for the `chronicler-agents` crate — optional, needed for agent mode)
- **LM Studio** or an API key for narration (optional — simulation runs without it)

## Current Status

Phase 6, "Living Society," is the active workstream. If you are developing in the repo, start with:

- `docs/superpowers/progress/phase-6-progress.md`
- `docs/superpowers/roadmaps/`
- `docs/superpowers/specs/`
- `docs/superpowers/plans/`

## Installation

```bash
# Clone the repo
git clone https://github.com/YotsuBotfds/Chronicler.git
cd Chronicler

# Run the setup script
bash setup.sh            # Linux / Mac / Git Bash
setup.bat                # Windows Command Prompt
```

The setup script creates a virtual environment, installs Python dependencies, and builds the Rust agent crate if Rust is installed. Optional flags:

| Flag | Effect |
|------|--------|
| `--no-rust` | Skip Rust agent crate build |
| `--api` | Install Claude API narration support |
| `--gemini` | Install Gemini API narration support |

### Manual Installation

If you prefer to install manually:

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

python -m pip install -e .

# (Optional) API narration support
python -m pip install -e ".[api]"      # Claude API
python -m pip install -e ".[gemini]"   # Gemini API

# (Optional) Rust agent crate
cd chronicler-agents
python -m pip install maturin
maturin develop --release
cd ..

```

When rebuilding the Rust extension, use the virtual environment's Python (`.venv\Scripts\python.exe` on Windows) or Python may load a stale `chronicler_agents` build.

## Quick Start

```bash
# Basic run — 50 turns, 4 civilizations, deterministic simulation + local LM narration
chronicler --seed 42 --turns 50 --civs 4 --regions 8 --output output/chronicle.md

# Simulation only (no LLM needed)
chronicler --seed 42 --turns 100 --simulate-only

# Hybrid agent path with validation sidecars (requires Rust crate)
chronicler --seed 42 --turns 100 --agents hybrid --simulate-only --validation-sidecar

# Use a scenario
chronicler --seed 42 --turns 80 --scenario scenarios/two_empires.yaml

# Post-run narration with Claude API (requires ANTHROPIC_API_KEY)
chronicler --seed 42 --turns 100 --simulate-only
chronicler --narrate output/chronicle_bundle.json --narrator api --budget 50

# Post-run narration with Gemini API (requires GOOGLE_API_KEY)
chronicler --narrate output/chronicle_bundle.json --narrator gemini --budget 50

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
| `--analyze dir/` | Analyze a batch directory and produce `batch_report.json` |
| `--compare report.json` | Compare an analysis run against a baseline report |
| `--checkpoints 25,50,100` | Add checkpoint turns to analytics output |
| `--resume state.json` | Resume from a saved state |

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
# Python test suite
pytest

# Rust test suite
cargo nextest run

# Validate a generated batch directory with bundled oracles
python -m chronicler.validate --batch-dir output/some_batch --oracles all
```

For focused iteration, prefer targeted test runs and rebuild the Rust extension inside the active virtual environment before hybrid-mode validation.

## Project Structure

```
src/chronicler/       # Python simulation + narration (main codebase)
chronicler-agents/    # Rust agent crate (per-agent computation via PyO3/Arrow)
chronicler-agents/tests/  # Rust integration tests
docs/superpowers/     # Roadmaps, specs, plans, and current progress notes
scenarios/            # YAML scenario files
tests/                # Python test suite
```

## Output

Each run produces:
- **chronicle.md** — the narrated history as readable text
- **chronicle_bundle.json** — structured run data for post-run narration, analysis, and the viewer
- **state.json** — serialized world state (for resume/fork)
- **memories_*.json** — per-civilization memory streams

Batch analysis writes:
- **batch_report.json** — aggregated metrics and checkpoint summaries for a batch directory

## License

This project is not currently licensed for redistribution.
