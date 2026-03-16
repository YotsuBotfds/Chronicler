# M28: Oracle Gate — Design Spec

**Date:** 2026-03-15
**Status:** Approved
**Prerequisites:** M27 System Integration (landed, hybrid mode functional)
**Estimated size:** ~200 lines Python
**Phase:** 5 (Agent-Based Population Model) — fourth milestone

## Overview

Final validation that hybrid mode (`--agents=hybrid`) produces statistically compatible distributions to aggregate mode (`--agents=off`). This is a one-time pass/fail checkpoint, not a recurring gate or CI pipeline. The comparison framework was built in M26; M28 orchestrates the full 200-seed batch and reports results.

M28 does not build new simulation features. It does not tune constants. It does not modify the oracle framework. It runs the existing tools at scale and produces data for a human pass/fail decision.

### Design Principles

1. **Reuse, don't rebuild.** The oracle comparison (`shadow_oracle.py`) is unchanged. The simulation CLI (`--simulate-only`, `--seed`, `--agents`) is the execution interface. The batch analytics module evaluates the 34 M19b exit criteria separately. M28 adds only the orchestration script and a thin data adapter.
2. **Human decision, not automated gate.** The script presents raw statistics. Pass/fail classification is a human judgment informed by the data. No diagnostic heuristics, no automated retry limits.
3. **Retry-friendly.** The aggregate baseline can be reused across hybrid re-runs. When a behavior bug is fixed, only the hybrid batch needs to re-run.
4. **One-time validation.** This runs once to prove hybrid mode is compatible, then the project moves on. The script is not designed for recurring execution or CI integration.

### Design Decisions

**Subprocess execution, not programmatic.** The script invokes `python -m chronicler` via subprocess, same pattern as the M19b batch runner. No second programmatic entry point into the simulation.

**No new logging infrastructure.** Each run produces a `chronicle_bundle.json` with per-turn `TurnSnapshot` containing civ stats. The oracle script reads these bundles directly via a thin adapter — no Arrow IPC shadow logs needed.

**Oracle-only scope.** The 34 M19b exit criteria are evaluated separately using the existing batch analytics tooling. M28's script answers one new question: "do agent-derived stat distributions diverge from aggregate?" It does not duplicate analytics logic.

**No threshold tuning knobs.** Pass criteria (>=12/15 distribution tests, correlation delta < 0.15) are defined in `shadow_oracle.py` and not exposed as CLI arguments. If thresholds need adjusting, the constants are updated in code with documentation.

---

## Script Interface

### CLI

```
python scripts/run_oracle_gate.py [--aggregate-dir DIR] [--output-dir DIR] [--parallel N] [--seeds N] [--turns N]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--aggregate-dir` | *(none)* | Path to pre-existing aggregate batch. If provided, skip aggregate run. |
| `--output-dir` | `output/oracle_gate/` | Root output directory. |
| `--parallel` | `28` | Number of parallel subprocess workers. |
| `--seeds` | `200` | Number of seeds to run. |
| `--turns` | `500` | Turns per seed. |

### Execution Flow

1. **Aggregate phase** (skipped if `--aggregate-dir` provided):
   - Run `--seeds` seeds x `--turns` turns via subprocess: `python -m chronicler --simulate-only --seed N --agents off`
   - Output: `{output-dir}/aggregate/seed_{N}/chronicle_bundle.json`
   - Parallel: up to `--parallel` concurrent subprocesses

2. **Hybrid phase:**
   - Run `--seeds` seeds x `--turns` turns via subprocess: `python -m chronicler --simulate-only --seed N --agents hybrid`
   - Output: `{output-dir}/hybrid/seed_{N}/chronicle_bundle.json`
   - Parallel: up to `--parallel` concurrent subprocesses

3. **Comparison phase:**
   - Adapter loads both sets of bundles, extracts civ stats at checkpoints [100, 250, 500]
   - Reshapes into the columnar format `shadow_oracle_report()` expects
   - Runs oracle comparison
   - Prints terminal summary
   - Writes `{output-dir}/oracle_report.json`

### Seed Determinism

Both aggregate and hybrid runs use the same seed sequence (0 through N-1, or matching the existing batch runner convention). Same seed must produce the same RNG stream in both modes — the only difference is whether agent-derived stats overwrite aggregate stats.

### Performance Budget

- **Target:** Under 30 minutes wall-clock for full 200-seed x 500-turn run (both phases)
- **Parallelism:** `--parallel 28` on 9950X (16 physical cores, leave headroom)
- **Overhead estimate:** Hybrid adds ~10-20% over aggregate due to Rust agent tick + Arrow serialization. M25 benchmarked tick at ~174us (demographics-only); M26 full behavior model is somewhat higher but still sub-millisecond at 6K agents — negligible compared to Python turn loop.
- **Memory:** 28 parallel Python processes each holding a WorldState. Validated safe during M19b tuning passes at `--parallel 30`.
- **Flag if exceeded:** If wall-clock exceeds 30 minutes, investigate before proceeding.

---

## Data Adapter

### Purpose

Bridge between simulation bundle output and `shadow_oracle_report()` input format. This is the only new code beyond the orchestration script.

### Input

Per-seed `chronicle_bundle.json` from both aggregate and hybrid directories. Each bundle contains:

```json
{
  "history": [
    {
      "turn": 100,
      "civ_stats": {
        "CivName": {
          "population": 45,
          "military": 30,
          "economy": 25,
          "culture": 18,
          "stability": 52
        }
      }
    }
  ]
}
```

### Output

Column-oriented dict matching the format returned by `load_shadow_data()`:

```python
{
    "turn": [100, 100, 100, ...],          # one entry per civ per seed per checkpoint
    "agent_population": [45, 38, ...],      # hybrid values
    "agent_military": [30, 22, ...],
    "agent_economy": [25, 31, ...],
    "agent_culture": [18, 20, ...],
    "agent_stability": [52, 48, ...],
    "agg_population": [44, 39, ...],        # aggregate values
    "agg_military": [29, 23, ...],
    "agg_economy": [26, 30, ...],
    "agg_culture": [17, 21, ...],
    "agg_stability": [53, 47, ...],
}
```

### Matching Logic

For each seed, at each checkpoint turn, for each civ present in *both* the aggregate and hybrid snapshots: emit one row with both sets of stats. Civs that exist in one run but not the other (due to agent-driven secession or conquest divergence) are excluded from comparison — they represent legitimate emergent divergence, not statistical noise.

**Civ matching is by name**, consistent with how `TurnSnapshot.civ_stats` is keyed.

---

## Comparison & Reporting

### Oracle Comparison

Reuses `shadow_oracle_report()` from `shadow_oracle.py` unchanged:

- **5 metrics:** population, military, economy, culture, stability
- **3 checkpoints:** turns 100, 250, 500
- **15 distribution tests:** KS + Anderson-Darling, Bonferroni-corrected alpha = 0.003
- **Pass threshold:** >=12/15 pass both tests
- **2 correlation pairs:** (military, economy), (culture, stability) x 3 checkpoints
- **Correlation threshold:** delta < 0.15

### Terminal Summary

```
=== Oracle Gate Report ===
Seeds: 200  Turns: 500  Checkpoints: 100, 250, 500

--- Distribution Tests (KS + Anderson-Darling) ---
                 Turn 100        Turn 250        Turn 500
population       PASS (0.87)     PASS (0.42)     PASS (0.31)
military         PASS (0.65)     PASS (0.38)     FAIL (0.001)
economy          PASS (0.91)     PASS (0.55)     PASS (0.22)
culture          PASS (0.78)     PASS (0.61)     PASS (0.44)
stability        PASS (0.72)     PASS (0.29)     PASS (0.18)

Distribution: 14/15 passed (threshold: 12/15)

--- Correlation Structure ---
                 Turn 100        Turn 250        Turn 500
mil/econ         0.03            0.05            0.08
cult/stab        0.02            0.04            0.11

Correlation: ALL PASSED (threshold: delta < 0.15)

--- Summary ---
RESULT: PASS (14/15 distribution, correlation OK)

Aggregate dir: output/oracle_gate/aggregate/
Hybrid dir:    output/oracle_gate/hybrid/
Report:        output/oracle_gate/oracle_report.json
```

Parenthesized number is the KS p-value for quick scanning. Full statistics are in the JSON.

### `oracle_report.json` Schema

```json
{
  "metadata": {
    "seeds": 200,
    "turns": 500,
    "checkpoints": [100, 250, 500],
    "aggregate_dir": "output/oracle_gate/aggregate/",
    "hybrid_dir": "output/oracle_gate/hybrid/",
    "timestamp": "2026-03-XX..."
  },
  "distribution_tests": [
    {
      "metric": "population",
      "turn": 100,
      "ks_stat": 0.045,
      "ks_p": 0.87,
      "ad_p": 0.92,
      "alpha": 0.003,
      "passed": true
    }
  ],
  "correlation_tests": [
    {
      "metric1": "military",
      "metric2": "economy",
      "turn": 100,
      "agent_corr": 0.45,
      "agg_corr": 0.42,
      "delta": 0.03,
      "passed": true
    }
  ],
  "summary": {
    "distribution_passed": 14,
    "distribution_total": 15,
    "distribution_threshold": 12,
    "correlation_all_passed": true,
    "overall": "PASS"
  }
}
```

Correlation tests include raw correlation values (not just delta) so we can distinguish "real structural divergence" from "both correlations near zero, delta is noise" — a pattern encountered during M19b tuning.

---

## Failure Protocol

### Workflow

1. Review `oracle_report.json` — identify which metrics at which checkpoints failed
2. For drill-down: read per-seed bundles directly or M26 shadow IPC files (data already exists)
3. Classify: behavior bug (agent model wrong) vs. emergent divergence (agent model reveals something aggregate missed)
4. Behavior bugs: fix in `chronicler-agents/src/`, re-run hybrid only:
   ```
   python scripts/run_oracle_gate.py --aggregate-dir output/oracle_gate/aggregate/
   ```
5. Emergent divergences: document in post-gate analysis, adjust pass thresholds in `shadow_oracle.py` if the agent behavior is defensible
6. Repeat until human pass/fail decision is made

### Threshold Adjustments

- Pass criteria live in `shadow_oracle.py` constants, not CLI arguments
- Adjustments are documented in the post-gate analysis markdown (written collaboratively, not auto-generated)
- Rationale for each adjustment must explain why the agent behavior is correct and the original threshold was too restrictive

### Baseline Validity

**The aggregate baseline is only valid for the same codebase version.** M27's hard requirement is that `--agents=off` produces bit-identical output to pre-M27 code. If any code change affects aggregate-mode behavior, the aggregate baseline must be regenerated. Do not reuse a stale baseline across code changes.

---

## Expected Divergences

Context for interpreting the report, not code. These are known consequences of agent-based modeling that should not be treated as failures:

- **Population noise:** Agent demographic model adds stochastic variance to smooth aggregate curves. Mean should match within ~10%; variance will be higher. This is inherent to individual-level birth/death vs. aggregate rate application.
- **Secession geography:** Agent loyalty drift means secession regions may differ from the aggregate model's distance-based selection. Border populations shifting affinity is the whole point of the agent model.

If these patterns appear in the report, they confirm the agent model is working as designed. The question is whether the *magnitude* is within acceptable bounds.

---

## Relationship to Other Milestones

### Inputs from M26
- `shadow_oracle.py`: oracle comparison framework (KS + AD tests, OracleReport dataclass) — reused unchanged
- `shadow.py`: ShadowLogger and Arrow IPC shadow logs — available for drill-down but not used by M28 script directly

### Inputs from M27
- `--agents=hybrid` mode: agent-derived stats drive civ stats in the turn loop
- `--agents=off` bit-identity guarantee: aggregate baseline is trustworthy
- Test 15 (convergence diagnostic): early `DEMAND_SCALE_FACTOR` calibration. If test 15 shows gross miscalibration during M27, fix before running M28. Test 15 is the early warning; M28 is the full validation.

### Outputs to M29/M30
- Pass determination: confirms hybrid mode produces compatible distributions, unblocking M29 (scale) and M30 (narrative)
- `oracle_report.json`: archived as the Phase 5 validation checkpoint

---

## What This Milestone Does NOT Do

- No new simulation features — agents, behavior, integration are M25-M27
- No constant tuning — `DEMAND_SCALE_FACTOR` and agent thresholds are calibrated in M27
- No modifications to `shadow_oracle.py` — comparison framework is reused as-is
- No CI/CD integration — this is a local developer script
- No auto-generated markdown report — analysis document written collaboratively after reviewing data
- No diagnostic heuristics — raw numbers at checkpoints, human interpretation
- No recurring execution — one-time validation, then move on

---

## Deliverables

1. `scripts/run_oracle_gate.py` — orchestration script (~150 lines)
2. Data adapter function — bundle JSON to oracle input format (~50 lines)
3. `output/oracle_gate/oracle_report.json` — comparison results
4. Terminal summary — printed on completion
5. Post-gate analysis markdown — written collaboratively after reviewing results (not auto-generated, not part of the script deliverables)
