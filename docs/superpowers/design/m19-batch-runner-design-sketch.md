# M19 Batch Runner — Design Sketch

> Pre-spec design sketch for the M19 analytics pipeline. Written before M18 lands.
> Reference this when writing the full M19 spec.

---

## Design Decision: Option B + Thin C

**Option B (Post-Processing Analytics Pipeline):** New `analytics.py` reads existing bundle JSON files post-run. Since bundles already contain full `TurnSnapshot` history and `events_timeline`, analytics can compute most metrics without touching simulation code.

**Thin C (Snapshot Extension):** Extend `TurnSnapshot` with 5-6 fields that M13-M18 systems produce but don't currently capture in snapshots. This is the only simulation-side change — no `MetricsCollector` threading through phases.

**Why not full Option C (instrumented turn metrics)?** Threading a collector through `run_turn` and every phase is invasive, creates maintenance drag when phases change, and is unnecessary given that bundles already capture 90% of what analytics needs. The remaining 10% is cheaper to add via snapshot extension than via phase instrumentation.

**Why not pure Option A (extend RunResult)?** `RunResult` only captures run-level aggregates. M19b's tuning pass needs time-series visibility — "stability drops below 20 at turn 40 in 80% of runs" — which requires per-turn data. Bundles have it; RunResult doesn't.

---

## Architecture

```
chronicler batch --runs 200 --turns 500 --simulate-only --seed-range 1-200
    │
    ▼
┌──────────────────────────┐
│   Existing batch.py      │  Run N simulations in parallel
│   (ProcessPoolExecutor)  │  Each run produces:
│                          │    - chronicle_bundle.json (with extended snapshots)
│                          │    - RunResult (existing, kept for backward compat)
└────────────┬─────────────┘
             │ N bundle files on disk
             ▼
┌──────────────────────────┐
│   NEW: analytics.py      │  Post-processor reads bundles
│                          │    - Per-system metric extractors
│                          │    - Time-series aggregation
│                          │    - Distribution computation
│                          │    - Anomaly detection
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│   batch_report.json      │  Structured output
│   + CLI text report      │  Machine-readable + human-readable
└──────────────────────────┘
```

Key property: **analytics never imports simulation code.** It reads JSON bundles. This means analytics bugs can't break the sim, and you can re-analyze old bundles when you add new metrics.

---

## TurnSnapshot Extension

Current `TurnSnapshot` captures civ stats, region control, relationships, vassals, federations, proxy wars, capitals, movements. Missing fields needed for M13-M18 analytics:

```python
# Added to TurnSnapshot (captured in main.py's turn loop)
class TurnSnapshot(BaseModel):
    # ... existing fields ...

    # M13: Resource state
    active_trade_routes: list[tuple[str, str]]  # sorted civ pairs
    per_civ_treasury: dict[str, int]

    # M14½: Stability tracking (already in civ_stats but worth explicit call-out)
    # (stability is already captured via CivSnapshot — no new field needed)

    # M15: Climate & infrastructure
    climate_phase: str  # "warming", "cooling", "temperate", "drought"
    disaster_active: list[str]  # active condition types this turn

    # M16: Memetic state
    movement_count: int  # total active movements

    # M17: Great persons
    per_civ_great_person_count: dict[str, int]
    per_civ_tradition_count: dict[str, int]
    succession_crises_active: list[str]  # civ names in crisis

    # M18: Emergence (added when M18 lands)
    per_civ_stress_index: dict[str, float]  # 0-10 scale
    black_swan_this_turn: Optional[str]  # event type or None
    regression_active: list[str]  # civ names in regression
    terrain_transitions_this_turn: int  # deforestation/rewilding count
```

These are all cheap reads from `WorldState` at snapshot time — no computation, just field copies. The snapshot capture in `main.py` adds ~15 lines.

---

## Analytics Module Design

### Metric Extractors

Each subsystem gets a dedicated extractor function. Extractors take a list of bundles and return structured metric dicts. They share no state — pure functions.

```python
# analytics.py — sketch of public API

def extract_stability_metrics(bundles: list[Bundle]) -> StabilityReport:
    """Per-run and cross-run stability distributions at turn 25/50/100/200/500."""

def extract_resource_metrics(bundles: list[Bundle]) -> ResourceReport:
    """Trade route counts over time, famine timing, treasury distributions."""

def extract_politics_metrics(bundles: list[Bundle]) -> PoliticsReport:
    """Secession/federation/vassal rates, elimination timing, twilight entry."""

def extract_climate_metrics(bundles: list[Bundle]) -> ClimateReport:
    """Disaster frequency by type, climate phase correlations, migration rates."""

def extract_memetic_metrics(bundles: list[Bundle]) -> MemeticReport:
    """Movement lifecycle stats, paradigm shift rates, cultural assimilation."""

def extract_great_person_metrics(bundles: list[Bundle]) -> GreatPersonReport:
    """Generation rates per era, tradition crystallization, hostage exchanges."""

def extract_emergence_metrics(bundles: list[Bundle]) -> EmergenceReport:
    """Black swan frequency/type, stress index distributions, regression rates."""

def extract_general_metrics(bundles: list[Bundle]) -> GeneralReport:
    """Era progression curves, action diversity, interestingness distribution."""

def generate_full_report(bundles: list[Bundle]) -> AnalyticsReport:
    """Calls all extractors, assembles composite report with anomaly flags."""
```

### Time-Series Aggregation

The key capability that justifies Option B over Option A. Each extractor can produce percentile curves across runs:

```python
def stability_percentiles(bundles, turns=[25, 50, 100, 200, 500]):
    """
    Returns for each checkpoint turn:
      {turn: {p10: val, p25: val, median: val, p75: val, p90: val, min: val, max: val}}

    Computed from TurnSnapshot.civ_stats[civ].stability across all runs.
    Per-civ values are pooled (all civs from all runs at turn T form the distribution).
    """
```

This tells you: "At turn 100 across 200 runs, the median civ has stability 12, the 10th percentile is 0, the 90th is 45." That's the data M19b needs to know if stability recovery is working.

### Anomaly Detection

Pattern matchers that flag known degenerate states:

```python
ANOMALY_CHECKS = [
    # (name, condition, severity)
    ("stability_collapse", lambda r: r.stability.median_at(100) < 20, "CRITICAL"),
    ("universal_famine", lambda r: r.resources.famine_rate > 0.95, "CRITICAL"),
    ("dead_system", lambda r: any(rate < 0.05 for rate in r.firing_rates.values()), "WARNING"),
    ("single_dominant", lambda r: r.general.same_winner_rate > 0.8, "WARNING"),
    ("no_late_game", lambda r: r.general.median_era_at(500) < "MEDIEVAL", "WARNING"),
]
```

### Never-Fire Detection

Special case anomaly: mechanics that exist but never trigger across N runs. Directly answers "did we build dead code?"

```python
def detect_never_fire(bundles) -> list[str]:
    """
    Check each M13-M18 mechanic against event_timeline across all runs.
    Returns list of mechanic names that fired in <5% of runs.

    Checks:
      - embargo, federation_formed, vassal_imposed, secession
      - mercenary_spawn, proxy_war_started, twilight_entered
      - movement_created, paradigm_shift, cultural_assimilation
      - great_person_born, tradition_crystallized, hostage_taken
      - succession_crisis, folk_hero_created
      - black_swan (by type), tech_regression, terrain_transition
    """
```

---

## Output Format

### Machine-Readable: `batch_report.json`

```json
{
  "metadata": {
    "runs": 200,
    "turns_per_run": 500,
    "seed_range": [1, 200],
    "timestamp": "2026-03-15T14:30:00",
    "version": "post-M18"
  },
  "stability": {
    "percentiles_by_turn": {
      "25": {"p10": 0, "p25": 5, "median": 18, "p75": 35, "p90": 52},
      "50": {"p10": 0, "p25": 2, "median": 12, "p75": 28, "p90": 41},
      "100": {"p10": 0, "p25": 0, "median": 8, "p75": 22, "p90": 38}
    },
    "zero_stability_rate_at_100": 0.43
  },
  "firing_rates": {
    "famine": 0.99,
    "secession": 0.72,
    "federation": 0.12,
    "black_swan_pandemic": 0.52,
    "hostage_exchange": 0.00,
    "tech_regression": 0.06
  },
  "elimination": {
    "median_first_elimination_turn": 67,
    "runs_with_no_elimination": 12,
    "runs_with_all_eliminated": 3
  },
  "era_progression": {
    "median_turn_to_iron": 45,
    "median_turn_to_classical": 92,
    "runs_reaching_industrial_by_500": 0.34
  },
  "anomalies": [
    {"name": "stability_collapse", "severity": "CRITICAL", "detail": "median stability 8 at turn 100"},
    {"name": "dead_system", "severity": "WARNING", "detail": "hostage_exchange fired in 0/200 runs"}
  ]
}
```

### Human-Readable: CLI Report

Same format already sketched in the roadmap (lines 86-109). The `chronicler analyze` command reads `batch_report.json` and prints the text report. The text report is the primary interface — the JSON exists for diffing and scripting.

---

## Tuning YAML Integration

Already described in the roadmap. The key design point: `tuning.yaml` maps directly to simulation constants (GameConfig values, threshold floats, rate multipliers). The batch runner loads the YAML and patches constants before world generation. No intermediate abstraction — YAML keys are the actual variable paths.

```yaml
# tuning.yaml
stability_recovery_base: 0.03        # currently 0.02
famine_trigger_threshold: 0.25       # currently 0.3
military_maintenance_ratio: 0.4      # currently 0.5
federation_alliance_turns: 8         # currently 10
black_swan_base_probability: 0.015   # currently 0.02
```

`chronicler batch --tuning tuning.yaml` applies overrides. `chronicler analyze --compare baseline.json tuned.json` diffs two reports side by side.

---

## What This Sketch Does NOT Cover

These are full M19 spec decisions, not batch runner architecture:

- **Exact metric list per system.** Depends on what M18 actually exports. Sketched above as placeholders.
- **Report visualization.** M19 deliverable is CLI text + JSON. Whether to add HTML/chart output is a scope decision for the spec.
- **Parallel execution tuning.** Single-threaded is fine for 200 runs. ProcessPoolExecutor is available if needed. Not an architecture decision.
- **Integration with M19b exit criteria.** The exit criteria are in the roadmap. The analytics module produces the data; M19b interprets it. The boundary between them is the `batch_report.json` schema.

---

## Existing Infrastructure to Preserve

The current codebase already has:

- `batch.py` — parallel run execution, `RunResult` collection, `summary.md` output
- `interestingness.py` — per-run scoring with weighted event counts
- `types.py` — `RunResult` dataclass with basic metrics
- `TurnSnapshot` — per-turn state capture in `main.py`
- `chronicle_bundle.json` — full bundle with history, events, snapshots

M19 extends all of these. It does not replace them. `RunResult` and `interestingness.py` stay as-is for backward compatibility. The new `analytics.py` module reads bundles (which contain everything RunResult has and more) and produces the richer report.
