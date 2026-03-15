# M19: Simulation Analytics & Tuning — Design Spec

> Before building on Phase 3, prove Phase 3 works at scale. M19 is the profiler for game design — it identifies miscalibrated thresholds, degenerate patterns, and mechanics that never fire.

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Analytics architecture | Option B + Thin C (post-processing on bundles + minimal snapshot extension) | Bundles already capture 90%+ of what analytics needs. No simulation code imports. |
| CLI approach | Keep existing `--batch`, add `--analyze` flag | Batch runner works. Don't restructure for aesthetics. M19 value is in analytics, not CLI. |
| Batch → Analyze coupling | Separate steps (B) | Re-analyze without re-running. Analysis is seconds; simulation is minutes. Tweak anomaly thresholds without re-running 200 sims. |
| Tuning override mechanism | Overlay dict on WorldState (C) + `KNOWN_OVERRIDES` validation | Minimum-viable. No GameConfig refactor (Phase 5 concern). One guardrail: warn on unknown YAML keys at load time. |
| Tuning key resolution | Constants in `tuning.py`, callsites use constants not strings | Reduces typo surface. `KNOWN_OVERRIDES` is the set of constant values. One place to add, one place to validate. |
| Never-fire detection | Discover event types from data, flag < 5% | Auto-includes new milestone event types. `EXPECTED_EVENT_TYPES` is safety net only (catches zero-fire mechanics absent from all bundles). |
| Checkpoint turns | Configurable via `--checkpoints`, default 25/50/100/200/500, clamped to <= total_turns | A `--turns 100` batch makes 200/500 checkpoints meaningless. |
| Compare output | Delta-only with significance threshold | During M19b tuning iteration, you scan for "did my change work" — not re-reading the full report. |

---

## 1. TurnSnapshot Extension

Three new fields on `TurnSnapshot`, captured in `main.py` after each `run_turn()`:

```python
# models.py — add to TurnSnapshot
climate_phase: str = ""                              # "warming"/"cooling"/"temperate"/"drought"
active_conditions: list[dict] = Field(default_factory=list)  # [{type, severity, duration}]
per_civ_income: dict[str, int] = Field(default_factory=dict) # civ.last_income snapshot
```

Capture in `main.py` (~3 lines):

```python
snapshot = TurnSnapshot(
    # ... existing fields ...
    climate_phase=get_climate_phase(world.turn, world.climate_config).value,
    active_conditions=[
        {"type": c.condition_type, "severity": c.severity, "duration": c.duration}
        for c in world.active_conditions
    ],
    per_civ_income={civ.name: civ.last_income for civ in world.civilizations},
)
```

### What's Already Captured

The following are already on TurnSnapshot/CivSnapshot and do NOT need new fields:

- **Civ stats**: population, military, economy, culture, stability, treasury, asabiya, tech_era
- **Political state**: is_vassal, is_fallen_empire, in_twilight, federation_name, prestige
- **Trade/war**: trade_routes, active_wars, embargoes
- **Regions**: region_control, fertility, region_cultural_identity, capitals
- **M14**: mercenary_companies, vassal_relations, federations, proxy_wars, exile_modifiers
- **M16**: movements_summary
- **M17**: great_persons, traditions, folk_heroes, active_crisis (on CivSnapshot)
- **M18**: civ_stress (on CivSnapshot), stress_index (on TurnSnapshot), pandemic_regions

### What's Derived from events_timeline (No Snapshot Field Needed)

- **Black swan events**: `event_type` in `{"pandemic", "supervolcano", "resource_discovery", "tech_accident"}`
- **Terrain transitions**: `event_type == "terrain_transition"`
- **Tech regressions**: `event_type == "tech_regression"`

---

## 2. Analytics Module (`analytics.py`)

**Input**: a batch directory containing N `chronicle_bundle.json` files.

**Architecture**: bundle loader + per-system extractors + cross-run aggregator + anomaly detector + report formatter. All pure functions, no simulation imports.

### Bundle Loader

```python
def load_bundles(batch_dir: Path) -> list[dict]:
    """Glob batch_dir/*/chronicle_bundle.json, deserialize, return list."""
```

### Per-System Extractors

Eight extractor functions. Each takes a list of bundle dicts and a `checkpoints: list[int]` parameter (default `[25, 50, 100, 200, 500]`, clamped to `<= total_turns`). Returns a typed report dict.

| Extractor | Key Metrics |
|---|---|
| `extract_stability` | Percentiles at each checkpoint, zero-rate, recovery-from-zero rate |
| `extract_resources` | Turn-of-first-famine distribution, trade route count over time, treasury percentiles |
| `extract_politics` | Secession/federation/vassal/mercenary rates, elimination turn distribution, twilight entry rate |
| `extract_climate` | Disaster frequency by type, climate phase correlation with famine/migration |
| `extract_memetic` | Movement count over time, paradigm shift rate, assimilation rate |
| `extract_great_persons` | Generation rate per era, tradition count, succession crisis rate, hostage rate |
| `extract_emergence` | Black swan frequency by type, stress distribution, regression rate, terrain transition count |
| `extract_general` | Era distribution at final turn, action diversity, civs alive at end, turn-of-first-war |

### Cross-Run Aggregation Pattern

Each extractor internally aggregates across runs:

1. Extract per-run metric (e.g., "turn of first famine" for each of N runs)
2. Compute distribution: min, p10, p25, median, p75, p90, max
3. Compute firing rate: "N out of total runs had at least one occurrence"

Time-series metrics (stability, trade routes, population) use checkpoint turns. At each checkpoint, pool all civ values from all runs to form the distribution.

### Anomaly Detection

**Degenerate patterns** — conditions indicating broken mechanics:

```python
ANOMALY_CHECKS = [
    ("stability_collapse", lambda r: r["stability"]["zero_rate_at_100"] > 0.4, "CRITICAL"),
    ("universal_famine", lambda r: r["event_firing_rates"]["famine"] > 0.95, "CRITICAL"),
    ("single_dominant", lambda r: r["general"]["same_winner_rate"] > 0.8, "WARNING"),
    ("no_late_game", lambda r: r["general"]["median_era_at_final"] < "MEDIEVAL", "WARNING"),
]
```

**Never-fire detection** — discover event types from data:

1. Collect every distinct `event_type` from `events_timeline` across ALL bundles
2. Compute firing rate per type: fraction of runs where the type appears at least once
3. Flag types with < 5% firing rate as WARNING

**`EXPECTED_EVENT_TYPES` safety net** — hardcoded set of event types that should fire in healthy simulations. If any of these appear in zero bundles (not just < 5%, but truly absent), flag as CRITICAL. This catches mechanics that are completely broken — no events emitted at all.

### Report Assembly

```python
def generate_report(batch_dir: Path, checkpoints: list[int] | None = None) -> dict:
    """Load bundles, run all extractors, run anomaly checks, return composite report."""
```

---

## 3. CLI Integration

### New Flags on Existing Parser

```
chronicler --analyze BATCH_DIR [--checkpoints 25,50,100] [--compare OTHER_REPORT.json]
chronicler --batch N --tuning tuning.yaml [--seed-range START-END]
```

| Flag | Purpose |
|---|---|
| `--analyze BATCH_DIR` | Run analytics on a batch directory, write `batch_report.json`, print CLI text report |
| `--checkpoints` | Comma-separated checkpoint turns for time-series aggregation. Default: 25,50,100,200,500. Clamped to <= total_turns. |
| `--compare OLD_REPORT.json` | Delta-only output comparing baseline report to new report |
| `--tuning tuning.yaml` | Load tuning overrides for batch run |
| `--seed-range START-END` | Set base seed and run count from range (e.g., `1-200` → seed=1, runs=200) |

### `--analyze` Dispatch

In `main.py`, `--analyze` is mutually exclusive with `--batch`, `--fork`, `--interactive`, `--live`, `--resume`. It dispatches to:

```python
from chronicler.analytics import generate_report, format_text_report, format_delta_report

report = generate_report(args.analyze, checkpoints=args.checkpoints)
write_json(report, args.analyze / "batch_report.json")
if args.compare:
    baseline = load_json(args.compare)
    print(format_delta_report(baseline, report))
else:
    print(format_text_report(report))
```

### `--simulate-only` Wiring

Verify that `run_batch()` passes the `--simulate-only` flag through to `execute_run()`. Batch runs of 200 simulations must not spin up LLM clients. If not currently wired, fix during implementation.

### `--seed-range` Enhancement

One-line parse: `start, end = map(int, args.seed_range.split("-"))`, sets `base_seed = start`, `num_runs = end - start + 1`. Falls back to existing `--seed` + sequential behavior if `--seed-range` not provided.

---

## 4. Output Formats

### `batch_report.json`

Written to `BATCH_DIR/batch_report.json`:

```json
{
  "metadata": {
    "runs": 200,
    "turns_per_run": 500,
    "seed_range": [1, 200],
    "checkpoints": [25, 50, 100, 200, 500],
    "timestamp": "2026-03-15T14:30:00",
    "version": "post-M18",
    "tuning_file": "tuning.yaml or null"
  },
  "stability": {
    "percentiles_by_turn": {
      "25": {"p10": 0, "p25": 5, "median": 18, "p75": 35, "p90": 52},
      "50": {"p10": 0, "p25": 2, "median": 12, "p75": 28, "p90": 41},
      "100": {"p10": 0, "p25": 0, "median": 8, "p75": 22, "p90": 38}
    },
    "zero_rate_at_100": 0.43
  },
  "resources": {
    "famine_turn_distribution": {"min": 8, "p25": 22, "median": 34, "p75": 51, "max": 312},
    "trade_route_percentiles_by_turn": {},
    "treasury_percentiles_by_turn": {}
  },
  "politics": {
    "secession_rate": 0.72,
    "federation_rate": 0.12,
    "vassal_rate": 0.45,
    "mercenary_rate": 1.00,
    "twilight_rate": 0.34,
    "elimination_turn_distribution": {"min": 12, "median": 67, "max": 489}
  },
  "climate": {
    "disaster_frequency_by_type": {"drought": 0.85, "plague": 0.62, "earthquake": 0.31}
  },
  "memetic": {
    "movement_count_percentiles_by_turn": {},
    "paradigm_shift_rate": 0.15,
    "assimilation_rate": 0.42
  },
  "great_persons": {
    "generation_rate_by_era": {"TRIBAL": 0.1, "IRON": 0.8, "CLASSICAL": 1.2},
    "tradition_rate": 0.22,
    "succession_crisis_rate": 0.56,
    "hostage_rate": 0.0
  },
  "emergence": {
    "black_swan_frequency_by_type": {"pandemic": 0.52, "supervolcano": 0.28, "resource_discovery": 0.18, "tech_accident": 0.02},
    "stress_percentiles_by_turn": {},
    "regression_rate": 0.06,
    "terrain_transition_rate": 0.14
  },
  "general": {
    "era_distribution_at_final": {"TRIBAL": 0.05, "IRON": 0.15, "CLASSICAL": 0.35, "MEDIEVAL": 0.30, "RENAISSANCE": 0.10, "INDUSTRIAL": 0.05},
    "action_diversity_median": 7,
    "civs_alive_at_end_distribution": {"min": 0, "median": 3, "max": 4},
    "first_war_turn_distribution": {"min": 3, "median": 18, "max": 95}
  },
  "event_firing_rates": {
    "famine": 0.99, "secession": 0.72, "federation_formed": 0.12,
    "hostage_taken": 0.00, "tech_regression": 0.06
  },
  "anomalies": [
    {"name": "stability_collapse", "severity": "CRITICAL", "detail": "43% of civs at stability 0 by turn 100"},
    {"name": "never_fire", "severity": "WARNING", "detail": "hostage_taken fired in 0/200 runs"}
  ]
}
```

### CLI Text Report

Printed to stdout:

```
STABILITY:  median at turn 100 = 8, σ=12 — 43% of civs at zero by turn 100    ← CRITICAL
Famine:     198/200 runs (99%) — first occurrence median turn 34, σ=12
Secession:  145/200 runs (72%) — median turn 89
Mercenary:  200/200 runs (100%) — median turn 47                                ← EVERY RUN
Federation: 23/200 runs (12%)
Twilight:   67/200 runs (34%)
Black Swan: 4.2/run avg — pandemic 52%, supervolcano 28%, discovery 18%, accident 2%
Regression: 12/200 runs (6%)
GreatPerson: 3.1/civ avg at turn 200, 0.4 traditions/civ
...

DEGENERATE PATTERNS:
  ⚠ Stability universally near 0 by turn 100 — recovery formula insufficient
  ⚠ Mercenary spawn rate 100% — check military maintenance vs income curves

NEVER-FIRE CHECK (< 5% of runs):
  ⚠ hostage_taken: 0/200 runs
  ⚠ tech_accident: 2% of black swans
```

### Compare Output (Delta-Only)

```
DELTA REPORT (baseline → tuned)
═══════════════════════════════
stability.median_at_100:     8 → 31  (+287%)  ← FIXED
stability.zero_rate_at_100:  0.43 → 0.08  (-81%)
famine.first_turn_median:    34 → 67  (+97%)
mercenary.firing_rate:       1.00 → 0.74  (-26%)

ANOMALIES RESOLVED:
  ✓ stability_collapse (was CRITICAL)

ANOMALIES NEW:
  (none)

3 metrics unchanged (< 5% delta), 18 metrics omitted
```

Significance threshold: omit deltas under 5% change. Adjustable at implementation time.

---

## 5. Tuning Override System (`tuning.py`)

### Key Constants

Single module defines all tunable parameter keys:

```python
# tuning.py

# Stability drains
K_DROUGHT_STABILITY = "stability.drain.drought_immediate"
K_DROUGHT_ONGOING = "stability.drain.drought_ongoing"
K_PLAGUE_STABILITY = "stability.drain.plague_immediate"
K_FAMINE_STABILITY = "stability.drain.famine_immediate"
K_WAR_COST_STABILITY = "stability.drain.war_cost"
K_GOVERNING_COST = "stability.drain.governing_per_distance"

# Fertility
K_FERTILITY_DEGRADATION = "fertility.degradation_rate"
K_FERTILITY_RECOVERY = "fertility.recovery_rate"
K_FAMINE_THRESHOLD = "fertility.famine_threshold"

# Military
K_MILITARY_FREE_THRESHOLD = "military.maintenance_free_threshold"

# Emergence
K_BLACK_SWAN_BASE_PROB = "emergence.black_swan_base_probability"
K_BLACK_SWAN_COOLDOWN = "emergence.black_swan_cooldown_turns"

# ... additional keys added as M19b wires callsites

KNOWN_OVERRIDES: set[str] = {
    K_DROUGHT_STABILITY, K_DROUGHT_ONGOING, K_PLAGUE_STABILITY,
    K_FAMINE_STABILITY, K_WAR_COST_STABILITY, K_GOVERNING_COST,
    K_FERTILITY_DEGRADATION, K_FERTILITY_RECOVERY, K_FAMINE_THRESHOLD,
    K_MILITARY_FREE_THRESHOLD, K_BLACK_SWAN_BASE_PROB, K_BLACK_SWAN_COOLDOWN,
    # ...
}
```

### Loading and Validation

```python
def load_tuning(path: Path) -> dict[str, float]:
    """Load hierarchical YAML, flatten to dot-notation keys, validate."""
    raw = yaml.safe_load(path.read_text())
    flat = _flatten(raw)
    unknown = set(flat.keys()) - KNOWN_OVERRIDES
    if unknown:
        for key in sorted(unknown):
            warnings.warn(f"Unknown tuning key: {key}")
    return flat

def get_override(world: WorldState, key: str, default: float) -> float:
    """Read a tunable constant with override fallback."""
    return world.tuning_overrides.get(key, default)
```

### WorldState Extension

```python
# models.py — add to WorldState
tuning_overrides: dict[str, float] = Field(default_factory=dict)
```

Populated from `load_tuning()` before world gen. Persists in saved state so resumed runs use the same overrides.

### Consumption Pattern

At each callsite (one-line change):

```python
# Before:
stability -= 10  # drought immediate

# After:
from chronicler.tuning import K_DROUGHT_STABILITY, get_override
stability -= abs(get_override(world, K_DROUGHT_STABILITY, 10))
```

For helpers deeper in the call stack that don't have `world`: read the override in the phase function, pass the resolved value down as a parameter. Keeps helpers clean and override-unaware.

### M19 Scope

M19 builds the infrastructure and wires 5-10 example callsites as proof. M19b does the bulk wiring of ~250 constants.

---

## 6. Deliverables

### New Files

| File | Purpose | Est. Lines |
|---|---|---|
| `src/chronicler/analytics.py` | Bundle loader, 8 extractors, aggregator, anomaly detection, report formatter | ~350 |
| `src/chronicler/tuning.py` | Key constants, `KNOWN_OVERRIDES`, `load_tuning()`, `get_override()`, YAML flattener | ~80 |

### Modified Files

| File | Change | Est. Lines |
|---|---|---|
| `src/chronicler/models.py` | 3 new TurnSnapshot fields, `tuning_overrides` on WorldState | ~6 |
| `src/chronicler/main.py` | Snapshot capture (3 fields), `--analyze`/`--tuning`/`--seed-range`/`--checkpoints`/`--compare` CLI flags, analyze dispatch | ~50 |
| `src/chronicler/batch.py` | Verify/wire `--simulate-only` passthrough, tuning YAML loading + injection into WorldState | ~15 |
| `src/chronicler/simulation.py` | 5-10 example callsites wired to `get_override()` | ~15 |

### Not In Scope

- Bulk constant wiring (~250 callsites) → M19b
- GameConfig centralization → Phase 5
- CLI restructuring / subcommands → not needed
- HTML/chart report visualization → not needed
- Parallel batch optimization → existing `multiprocessing.Pool` sufficient
- Tuning YAML for non-numeric parameters (e.g., action weight tables) → M19b if needed

---

## 7. Testing Strategy

- **Unit tests for analytics extractors**: deterministic bundle fixtures with known metrics, verify computation
- **Unit tests for tuning**: YAML loading, hierarchical flattening, unknown key warnings, `get_override` fallback behavior
- **Integration test**: 5-turn batch run (small, fast), analyze output, verify `batch_report.json` schema and CLI text output
- **Never-fire detection test**: synthetic bundle with sparse event types, verify event type discovery and < 5% flagging
- **Compare test**: two reports with known deltas, verify delta-only output and significance threshold filtering
- **Tuning override test**: batch run with overrides, verify constants take effect in simulation output

---

## 8. Exit Criteria

- `chronicler --analyze BATCH_DIR` produces valid `batch_report.json` and readable CLI text report
- `chronicler --analyze BATCH_DIR --compare OLD_REPORT.json` produces delta-only output with significance filtering
- `chronicler --batch N --tuning tuning.yaml` applies overrides; unknown keys produce warnings
- All 8 extractors return valid metric dicts from real bundles
- Configurable checkpoint turns, clamped to <= total_turns
- Never-fire detection discovers event types from data, flags < 5% firing rate
- `EXPECTED_EVENT_TYPES` safety net catches zero-fire mechanics absent from all bundles
- `--simulate-only` confirmed wired through `run_batch()` (no LLM clients in batch mode)
- 5-10 simulation constants wired to `get_override()` as proof of tuning system

### Total Estimated Scope

~500 lines new code, ~85 lines modified. No simulation logic changes. No architectural changes.
