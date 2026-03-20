# Chronicler

A Python CLI that generates entire civilization histories through deterministic simulation + LLM narration. Give it a seed, a scenario, and a turn count — get back a complete chronicle with wars, famines, cultural renaissances, political collapses, and technological breakthroughs, all emerging from interacting systems rather than scripted events.

## How It Works

Chronicler runs a 10-phase turn loop that simulates environment, economy, politics, military, diplomacy, culture, technology, actions, ecology, and consequences. Each phase reads and mutates a shared world state. The simulation is **fully deterministic** — the same seed always produces the same history.

An optional **agent layer** (written in Rust) runs per-agent computation for demographics, satisfaction, wealth, migration, and occupation at the individual level, feeding emergent behavior back into the civilization-level simulation.

The LLM **only narrates** — it never makes simulation decisions. You can run with local inference (LM Studio), Claude API, or Gemini API for narrative generation, or skip narration entirely with `--simulate-only`.

A **React/TypeScript viewer** connects via WebSocket for real-time visualization of running simulations.

## Requirements

- **Python 3.13+**
- **Rust toolchain** (for the `chronicler-agents` crate — optional, needed for agent mode)
- **LM Studio** or an API key for narration (optional — simulation runs without it)
- **Node.js 18+** (optional — only for the viewer)

## Installation

```bash
# Clone the repo
git clone https://github.com/YotsuBotfds/Chronicler.git
cd Chronicler

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install Python dependencies
pip install -e .

# (Optional) Install API narration support
pip install -e ".[api]"      # Claude API
pip install -e ".[gemini]"   # Gemini API

# (Optional) Build the Rust agent crate
cd chronicler-agents
pip install maturin
maturin develop --release
cd ..

# (Optional) Set up the viewer
cd viewer
npm install
npm run dev
cd ..
```

## Quick Start

```bash
# Basic run — 50 turns, 4 civilizations, deterministic simulation + local LLM narration
chronicler --seed 42 --turns 50 --civs 4 --regions 8 --output output/chronicle.md

# Simulation only (no LLM needed)
chronicler --seed 42 --turns 100 --simulate-only

# With agent-driven demographics (requires Rust crate)
chronicler --seed 42 --turns 100 --agents hybrid --simulate-only

# Use a scenario
chronicler --seed 42 --turns 80 --scenario scenarios/two_empires.yaml

# API narration (requires ANTHROPIC_API_KEY env var)
chronicler --seed 42 --turns 100 --simulate-only
chronicler --narrate output/chronicle_bundle.json --narrator api --budget 50

# Live mode with viewer
chronicler --live --live-port 8765
```

## Run Modes

| Flag | Description |
|------|-------------|
| *(default)* | Single run — simulate + narrate |
| `--simulate-only` | Run simulation without LLM narration |
| `--batch N` | Run N chronicles with sequential seeds |
| `--parallel` | Parallel workers for batch mode |
| `--fork state.json` | Fork from a saved state with a new seed |
| `--interactive` | Pause at intervals for commands |
| `--live` | WebSocket server for real-time viewer |
| `--narrate bundle.json` | Narrate a simulate-only bundle after the fact |
| `--analyze dir/` | Analyze a batch directory and produce reports |
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

Available presets: `pangaea`, `archipelago`, `golden-age`, `dark-age`, `ice-age`, `silk-road`

## Project Structure

```
src/chronicler/       # Python simulation + narration (main codebase)
chronicler-agents/    # Rust agent crate (per-agent computation via PyO3/Arrow)
viewer/               # React/TypeScript real-time viewer
scenarios/            # YAML scenario files
tests/                # Python test suite
```

## Output

Each run produces:
- **chronicle.md** — the narrated history as readable text
- **chronicle_bundle.json** — structured data for the viewer (world state, events timeline, snapshots, named events, era reflections)
- **state.json** — serialized world state (for resume/fork)
- **memories_*.json** — per-civilization memory streams

## License

This project is not currently licensed for redistribution.
