# Chronicler Phase 4 — Deepened Simulation & Narrative Architecture

> Phase 3 (M13-M18) gives the simulation material foundations — economics, politics, geography, culture, and characters. Phase 4 validates those systems at scale, redesigns the narration pipeline for batch processing with full-history context, grounds population in geography, and adds divergent technology, internal politics, coupled ecology, and imperfect information. Every new system interacts with existing mechanics through stats, events, and action weights — no architectural changes.
>
> All mechanics remain **pure Python simulation** — no LLM calls required. The narrative engine describes what happened; it doesn't decide what happens. The narration pipeline redesign (M20) changes *when* and *how* the LLM is called, not *what* it decides.

---

## Hardware Architecture

The simulation runs on the 9950X (16C/32T, 192GB DDR5). The 4090 (24GB VRAM) runs LLM inference via LM Studio for narration. These workloads are completely decoupled — the CPU never waits for the GPU and vice versa.

**Phase 4 does not need parallelism.** Single-threaded Python handles hundreds of regions and dozens of civs trivially. The 9950X is underutilized — intentionally. Parallelism is a Phase 5 concern (agent-based simulation in Rust + rayon).

**The real architectural win is the simulation/narration pipeline split:**
- Simulation: runs to completion on CPU in seconds (`--simulate-only`)
- Narration: batch post-processing on GPU in minutes, with full history context
- The user inspects simulation results before spending GPU time narrating

---

## Dependency Graph

```
Phase 3 complete
  │
  ├── M19 (Simulation Analytics) ──┐
  │                                │
  │                          M19b (Tuning Pass)
  │                                │
  ├── M20 (Narration Pipeline v2) ─┤
  │                                │
  └── P4 (Regional Population) ────┤
        │                          │
        ├── M21 (Tech Specialization)
        │     │                    │
        │     └── M22 (Factions) ──┤
        │           │              │
        │           └── M24 (Info Asymmetry)
        │                          │
        └── M23 (Coupled Ecology) ─┘
                                   ▼
                             Phase 4 complete

Parallelism:
  - M19 and M20 can run in parallel (independent)
  - M19b starts after M19 (requires analytics tooling to exist)
  - P4 starts after M19b (tuning must stabilize constants before formula rewrites)
  - M21 and M23 can run in parallel after P4
  - M22 after M21 (faction influence interacts with tech focus)
  - M24 after M22 (intelligence quality is a faction output)
  - M20 can start immediately — it touches narration, not simulation
```

---

## M19: Simulation Analytics & Tuning

*Before building on Phase 3, prove Phase 3 works at scale.*

This is the most important milestone in Phase 4. 40+ interconnected systems have never been run together at scale with statistical rigor. M19 tells you which constants are wrong before you build new systems on top of them.

### Batch Runner

```
chronicler batch --runs 200 --turns 500 --scenario minnesota --seed-range 1-200
```

- Runs N simulations with sequential seeds, `--simulate-only` mode
- Outputs per-run summary JSON with metrics across all Phase 3 systems:
  - **M13 (Resources/Economics):** turn-of-first-famine, max-treasury-reached, trade-route-count-at-turn-100/250/500, embargo-frequency
  - **M14 (Politics):** secession-count, federation-count, vassal-count, mercenary-spawns, civs-alive-at-end, elimination-turn-distribution
  - **M14½ (Dynamics):** twilight-entry-turn, balance-of-power-turns, stability-distribution-at-turn-50/100/200/500
  - **M15 (Living World):** migration-frequency, disaster-frequency-by-type, infrastructure-build-distribution, climate-phase-correlations
  - **M16 (Memetic Warfare):** movement-lifecycle (creation→paradigm-shift→death), cultural-assimilation-rate, propaganda-frequency
  - **M17 (Great Persons):** great-person-generation-rate-per-era, tradition-crystallization-frequency, succession-crisis-count, hostage-exchange-frequency, grudge/rivalry-formation-rates, folk-hero-count
  - **M18 (Emergence):** black-swan-frequency-and-type-distribution, stress-index-distribution-over-time, tech-regression-frequency, pandemic-spread-patterns, terrain-transition-count
  - **General:** tech-era-distribution-at-turn-500, turn-of-first-war
- Aggregates into `batch_report.json` with distributions
- Single-threaded is fine. 200 runs × ~5 seconds = ~17 minutes. Could parallelize across runs with `ProcessPoolExecutor` (each run is independent) but not necessary — this is a tool you run overnight, not interactively.

### Statistical Dashboard

CLI report. Plain text, grep-friendly.

```
$ chronicler analyze batch_report.json

STABILITY:  median at turn 50 = 12, σ=8 — 73% of civs below 20 by turn 50  ← CRITICAL
Famine:     198/200 runs (99%) — first occurrence median turn 34, σ=12
Secession:  145/200 runs (72%) — median turn 89
Mercenary:  200/200 runs (100%) — median turn 47  ← EVERY RUN
Federation: 23/200 runs (12%)
Twilight:   67/200 runs (34%)
Black Swan: 4.2/run avg — pandemic 52%, supervolcano 28%, discovery 18%, accident 2%
Regression: 12/200 runs (6%)
GreatPerson: 3.1/civ avg at turn 200, 0.4 traditions/civ
...

DEGENERATE PATTERNS:
  ⚠ Stability universally near 0 by turn 50 — recovery formula insufficient
  ⚠ Mercenary spawn rate 100% — check military maintenance vs income curves
  ⚠ Famine before turn 50 in 99% of runs — starting fertility 0.8 may be too low
  ⚠ Federation formation 12% — alliance threshold may be too high
  ⚠ Great person generation 0 in tribal era — catch-up logic may need earlier triggers
NEVER-FIRE CHECK:
  ⚠ Hostage exchange: 0/200 runs — eligibility may be too restrictive
  ⚠ Tech accident: 2% of black swans — INDUSTRIAL gate means near-zero early game
```

The "profiler for game design." Identifies miscalibrated thresholds, degenerate patterns, and mechanics that never fire.

### Tuning Surface

```yaml
# tuning.yaml — extracted from simulation constants
fertility_degradation_rate: 0.02
fertility_recovery_rate: 0.01
military_maintenance_threshold: 30
famine_trigger_threshold: 0.3
secession_stability_threshold: 20
mercenary_pressure_turns: 3
federation_alliance_duration: 10
...
```

`chronicler batch --tuning modified_tuning.yaml` overrides defaults. Compare two batch reports side by side.

### Architecture

Design sketch: `docs/superpowers/design/m19-batch-runner-design-sketch.md`

**Approach: Option B (post-processing analytics on bundles) + thin Option C (extend TurnSnapshot with M13-M18 fields).** Analytics module reads bundle JSON files — never imports simulation code. TurnSnapshot gets ~15 lines of new field captures for stress index, trade routes, climate phase, great person counts, and black swan events. See design sketch for full rationale, module API sketch, output schema, and tuning YAML integration.

### Deliverables

- `src/chronicler/analytics.py`: post-processing report generator (reads bundles, not simulation)
- `TurnSnapshot` extension: ~6 new fields for M13-M18 system state
- `chronicler batch` and `chronicler analyze` CLI subcommands
- `batch_report.json` schema: per-system metrics, time-series percentiles, anomaly flags, never-fire detection
- Tuning YAML override support with `--compare` diffing
- ~400 lines of tooling, ~15 lines snapshot extension

---

## M19b: Phase 3 Tuning Pass

*M19 builds the instrument panel. M19b is the actual flight correction.*

M19's batch runner will surface broken feedback loops — the universal stability-0 problem observed in the Qwen 3 30B test run (4/4 civs at stability 0 by turn 9) is the known example, but there will be others. M19b is the work of actually running iterations, adjusting constants, and confirming fixes via before/after analytics comparison.

### Scope

This is NOT new code. It's constant adjustment, threshold tuning, and formula rebalancing using M19's `tuning.yaml` override system:

- Run baseline: `chronicler batch --runs 200 --turns 500`
- Identify degenerate patterns from `chronicler analyze`
- Adjust constants in `tuning.yaml` (stability recovery rates, famine thresholds, mercenary pressure curves, etc.)
- Re-run batch, compare distributions
- Iterate until analytics show healthy distributions: stability has meaningful variance, all M13-M18 mechanics fire at reasonable rates, no civ type is systematically dominant or eliminated
- Bake final tuned constants into `GameConfig` / simulation defaults

### Exit criteria

- Stability distribution at turn 100: median > 30, σ > 15 (not collapsed to zero)
- Every M14-M18 mechanic fires in at least 10% of 200 runs (no dead systems)
- No degenerate pattern (100% occurrence of any negative event type)
- 3+ different tech eras represented at turn 500 across 200 runs
- Before/after analytics report committed as `docs/superpowers/analytics/m19b-tuning-report.md`

### Deliverables

- Tuned constants committed to codebase
- Before/after analytics comparison report
- ~0 new lines of code, potentially significant constant changes across GameConfig
- **Must complete before P4 starts** — P4 rewrites formulas that depend on these constants being correct

---

## M20: Narration Pipeline v2

*Narration with full history context, not turn-by-turn isolation.*

The current narrator calls the LLM once per turn, in isolation. The new narrator runs after the simulation completes, selects the most narratively interesting moments, and narrates them with full before/after context. Better output, fewer LLM calls, natural use of the CPU/GPU split.

### Architecture Change

**Current:**
```python
for turn in range(num_turns):
    events = simulate_turn(world)
    narrative = narrator.narrate(world, events)  # one LLM call per turn
    bundle.chronicle_entries.append(narrative)
```

**New:**
```python
# Phase 1: Simulate everything (CPU, seconds)
all_events = []
for turn in range(num_turns):
    events = simulate_turn(world)
    all_events.extend(events)

# Phase 2: Curate (CPU, milliseconds)
selected = narrative_curator.select(all_events, budget=50)

# Phase 3: Batch narrate (GPU, minutes)
chronicles = narrator.narrate_batch(selected, full_history=all_events)
bundle.chronicle_entries = chronicles  # sparse — not one per turn
```

### Narrative Curator

Heuristic scorer. Fast, deterministic, runs on CPU. Not an LLM.

```python
def select(events: list[Event], budget: int) -> list[Event]:
    """
    Select the N most narratively interesting events.

    Scoring heuristics:
    - Base: event.importance (already 1-10)
    - Bonus: +3 if event is first-of-type in the run
    - Bonus: +2 if event involves the current dominant power
    - Bonus: +2 if event is causally linked to a future high-importance event
      (famine in region X, and later secession in region X → the famine gets +2)
    - Bonus: +1 per cascading event within 5 turns (clusters of crisis)
    - Penalty: -2 if similar event narrated within last 10 selected events
    """
```

The causal linking is the key innovation. The curator has the full event history — it promotes the *causes* of important outcomes, not just the outcomes. "The drought of turn 134" gets narrated because the curator knows it leads to the secession of turn 147.

### Bundle Format Change

```python
class ChronicleEntry(BaseModel):
    turn: int                      # which turn this narrates
    covers_turns: tuple[int, int]  # range this entry spans (e.g., 134-147)
    events: list[Event]            # the curated events being narrated
    narrative: str                 # LLM output
    importance: float              # curator score
```

Entries are sparse. A 500-turn run produces 40-60 chronicle entries, each covering 1-15 turns.

### Batch Narration Context

Each narration call includes:
- The events being narrated (the selected cluster)
- Summary of the 20 turns before (compressed context)
- Summary of the 20 turns after (so the narrator can foreshadow)
- Full civ stats at the narrated turn (snapshot)

Bigger context window per call but far fewer calls. 50 calls × 2000 tokens context vs. 500 calls × 500 tokens. Total throughput similar, narrative quality dramatically better.

### LM Studio Integration

- Queues all narration requests
- Sends sequentially (LM Studio saturates the 4090 with a single request)
- Progress bar with ETA based on tokens/sec
- At ~40 tok/s with a 13B model: 50 events × ~500 tokens = ~10 minutes

### Viewer Changes

The timeline becomes a segmented bar, not a scrollable list:

```
Turn  1────────30  31──────45  46────────────90  91───────120
      [narrated]   [mechanic]  [narrated]        [mechanic]
      ▼ expand     ▸ 15 events ▼ expand          ▸ 30 events
```

- **Narrated segments**: collapsible, show full prose with event list. Default expanded for importance ≥ 8.
- **Mechanical segments**: collapsed single row showing event count + most important event summary. Click to expand into the existing event log view (stats, events, territory changes — no prose).
- **"Narrate this" button**: on mechanical segments. Sends the turn range to the narration pipeline. Result inserts into the bundle; viewer updates in place.
- **Timeline scrubber**: tick marks at narrated segment boundaries. Scrubbing through mechanical segments shows stat graphs and territory map updating but no chronicle panel content.

### Architecture

Design sketch: `docs/superpowers/design/m20-narrative-curator-design-sketch.md`

**Three-phase pipeline: Simulate (CPU) → Curate (CPU) → Narrate (GPU).** Curator uses three-pass scoring (base importance, causal linking via 20-turn forward scan, cluster detection with budget allocation). Outputs `NarrativeMoment` objects with narrative roles (inciting/escalation/climax/resolution/coda). Gap summaries provide mechanical context between narrated moments. See design sketch for full curator algorithm, causal pattern table, narration context window design, bundle format change, and viewer segmented timeline spec.

**Open questions (for spec):** Should reflections go through the curator? Should live mode buffer turns for curation? What's the right causal link window depth?

### Batch Runner GUI (M12c Setup Lobby Integration)

The M12c setup lobby already exists as a React/TS SPA for configuring individual runs. M20 extends it with a **Batch Run** tab that exposes M19's CLI tooling through the browser, so batch analytics can be driven from the GUI instead of terminal commands.

**Batch Configuration Panel:**
- Seed range input (start seed, count — maps to `--seed-range`)
- Turn count slider (default 500, maps to `--turns`)
- Simulate-only toggle (default on for batch — maps to `--simulate-only`)
- Tuning YAML file picker (load/edit/save overrides — maps to `--tuning`)
- Worker count selector (maps to `--parallel`)
- Run button with progress bar (tracks completed/total seeds)

**Analytics Display (inline, below config):**
- Stability distribution charts (sparklines per checkpoint turn: 50, 100, 200, 500)
- Event firing rate table (per event type: count, % of runs, median turn)
- Anomaly flags panel (degenerate patterns from `anomaly_detector`, color-coded severity)
- Never-fire warnings (mechanics that triggered in 0% of runs)
- Per-system metric cards (collapsible, one per M13-M18 system extractor)

**Compare Mode:**
- `--compare` delta overlay: load two `batch_report.json` files, display side-by-side distributions
- Diff highlighting: green/red for improved/degraded metrics
- Useful for M19b tuning iterations — adjust YAML, re-run, compare in browser

**Architecture:**
- Backend: thin Flask/FastAPI endpoint wrapping existing `run_batch()` and `analyze_batch()` calls
- Frontend: new `BatchPanel` component in the setup lobby, consumes `batch_report.json` schema directly
- WebSocket progress: reuses the live mode WebSocket for batch progress updates (seed completion events)
- No new Python analytics code — the GUI is a presentation layer over M19's CLI output

**Scope note:** The batch GUI is a testing accelerator, not a prerequisite for M19b tuning. M19b can proceed with CLI-only. The GUI makes iterative tuning faster and more visual, which is why it lives in M20 (viewer work) rather than M19 (analytics tooling).

### Deliverables

- `src/chronicler/curator.py`: event selection, causal linking, cluster detection, role assignment
- `NarrativeEngine` interface change: `narrate_batch()` with `NarrationContext` per moment
- Bundle format: sparse `ChronicleEntry` with `covers_turns`, `narrative_role`, `causal_links`
- `GapSummary` model for mechanical segments
- Viewer: segmented timeline with role-colored segments, causal link overlay, "narrate this" button
- Viewer: batch runner GUI tab in M12c setup lobby (config panel, analytics display, compare mode)
- Backward compatibility: viewer detects old dict-format bundles and renders legacy mode
- ~600 lines Python, ~400 lines TypeScript (was ~300 before batch GUI)

---

## P4: Regional Population

*The prerequisite that everything else sits on. A model change + formula rewrite, not a new system.*

### Model Change

```python
class Region(BaseModel):
    # ... existing fields ...
    population: int = Field(default=0, ge=0)
```

`Civilization.population` stays as a denormalized field, synced once per turn from `sum(r.population for r in civ_regions)`. Every existing reference to `civ.population` keeps working. The sync is one line per turn — invisible.

A computed property requiring WorldState access would infect every function signature in the codebase. Denormalization is the pragmatic choice.

### Formula Rewrites

**Civ-level formulas (keep reading `civ.population`):**
- Tech advancement checks
- Action engine weight calculations
- Asabiya computation
- Balance of power calculations

**Region-level formulas (rewrite to `region.population`):**
- Fertility degradation: `region.population > effective_capacity(region)`
- Famine trigger: per-region, based on that region's population vs. capacity
- Migration: surplus = `region.population - effective_capacity(region)`, refugees move to adjacent regions
- Military recruitment: war draws from frontier region populations first
- Production: regional economic output = f(region.population, region.infrastructure, region.resources)

This is the largest diff in Phase 4. Each rewrite replaces a crude proxy (`civ.population // len(civ.regions)`) with a direct read. No new logic — more precise existing logic.

### Population Distribution at World Gen

```python
region.population = int(effective_capacity(region) * 0.6)  # 60% of capacity
```

Existing scenarios: total civ population distributed across regions proportional to effective capacity.

### Regional Migration

```python
# Before (M15c): civ-level abstraction
civ.population -= surplus

# After (P4): region-to-region
source_region.population -= surplus
for receiving_region in eligible_adjacent:
    receiving_region.population += share
    # receiving region may belong to a DIFFERENT civ → stability impact
```

### Regional Military Recruitment

Military stays civ-level (regionalizing military is Phase 5). But recruitment draws from regional population:

```python
def recruit_for_war(civ, world):
    """War costs population from border regions first."""
    border_regions = get_border_regions(civ, world)
    recruitment = min(war_cost, sum(r.population for r in border_regions))
    for r in border_regions:
        r.population -= recruitment // len(border_regions)
```

A civ fighting on two fronts drains two sets of border regions.

### Deliverables

- `Region.population` field
- Population sync in phase 0
- Formula rewrites across all 10 phases
- Population distribution at world gen
- Migration rewrite (region-to-region)
- Military recruitment from regional population
- ~300 lines changed, ~100 lines new

---

## M21: Tech Specialization

*Divergent development paths from deterministic state-based selection. A civ doesn't choose — its history chooses for it.*

### Focus System

When a civ advances to a new tech era, it gains a **tech focus** — a specialization selected deterministically from civ state at the moment of advancement.

```python
class TechFocus(str, Enum):
    # Classical era
    NAVIGATION = "navigation"       # maritime civs
    METALLURGY = "metallurgy"       # mountain/mining civs
    AGRICULTURE = "agriculture"     # plains/grain civs

    # Medieval era
    FORTIFICATION = "fortification" # defensive/territorial civs
    COMMERCE = "commerce"           # trade-heavy civs
    SCHOLARSHIP = "scholarship"     # high-culture civs

    # Renaissance era
    EXPLORATION = "exploration"     # expansionist civs
    BANKING = "banking"             # high-treasury civs
    PRINTING = "printing"           # movement-adopting civs

    # Industrial era
    MECHANIZATION = "mechanization" # mining civs
    RAILWAYS = "railways"           # road-infrastructure civs
    NAVAL_POWER = "naval_power"     # coastal port civs

    # Information era
    NETWORKS = "networks"           # high trade route count
    SURVEILLANCE = "surveillance"   # large stable empires
    MEDIA = "media"                 # high culture, movements
```

### Selection Logic

Each era has 3 options. Score each based on civ's current stats, geography, infrastructure, and history. Highest score wins. Ties broken by `hash(world.seed, civ.name)`.

Example — Classical era:
- NAVIGATION: `coastal_regions × 3 + sea_trade_routes × 5`
- METALLURGY: `iron_regions × 4 + mine_count × 5`
- AGRICULTURE: `grain_regions × 3 + irrigated_regions × 5 + total_regional_pop × 0.1`

### Focus Effects

Each focus provides:
1. **Stat modifier** (permanent while in that era)
2. **Action weight modifier** (biases future decisions)
3. **Unique capability** (something only this focus enables)

Example — NAVIGATION (Classical):
- Stat: sea trade routes +2 income each
- Weight: EXPLORE +1.5×, TRADE +1.3×
- Capability: trade routes across 2 sea hops (not just direct adjacency)

Example — METALLURGY (Classical):
- Stat: military +15
- Weight: WAR +1.3×, BUILD +1.2×
- Capability: mine fertility degradation reduced by 50%

### M17 Interaction

Great persons influence tech focus scoring — they represent the institutional knowledge that shapes a civilization's development path:
- Active scientist GP: +5 to SCHOLARSHIP/PRINTING/NETWORKS scoring
- Active merchant GP: +5 to COMMERCE/BANKING/RAILWAYS scoring
- Active general GP: +5 to METALLURGY/FORTIFICATION/MECHANIZATION scoring
- Traditions (M17) also contribute: scholarly tradition adds +3 to culture-adjacent focuses, warrior tradition adds +3 to military-adjacent focuses

These bonuses are small relative to the geography/infrastructure scores (which range ~10-30) but enough to tip close decisions — a civ with a brilliant scientist is slightly more likely to invest in scholarship.

### Faction Interaction (M22)

Tech focus biases which faction gains influence:
- NAVIGATION, COMMERCE, BANKING → merchant faction +0.05
- METALLURGY, FORTIFICATION, NAVAL_POWER → military faction +0.05
- SCHOLARSHIP, PRINTING, MEDIA → cultural faction +0.05

Creates path dependence: NAVIGATION → COMMERCE → BANKING produces a merchant-dominated government by Industrial era.

### Deliverables

- `src/chronicler/tech_focus.py`: definitions, selection, effects
- `Civilization.tech_focuses: list[TechFocus]` (history)
- `Civilization.active_focus: TechFocus | None` (current)
- Integration with action engine and automatic effects
- ~350 lines new code

---

## M22: Factions

*Internal politics from competing weight vectors. Zero-sum normalized influence creates tipping points and path dependence.*

### Model

```python
class FactionType(str, Enum):
    MILITARY = "military"
    MERCHANT = "merchant"
    CULTURAL = "cultural"

class FactionState(BaseModel):
    influence: dict[FactionType, float] = Field(
        default_factory=lambda: {
            FactionType.MILITARY: 0.33,
            FactionType.MERCHANT: 0.33,
            FactionType.CULTURAL: 0.34,
        }
    )
    power_struggle: bool = False
    power_struggle_turns: int = 0
```

Influence always sums to 1.0 (normalized after every modification). Zero-sum competition.

### Influence Shifts

Checked in consequences phase. Each outcome shifts influence:

```
Outcome                         | MIL    | MER    | CUL
Win war                         | +0.10  |   —    |   —
Lose war                        | -0.10  | +0.05  | +0.05
Trade income > military cost    |   —    | +0.08  |   —
Treasury bankruptcy             |   —    | -0.15  | +0.05
Cultural work / movement adopt  |   —    |   —    | +0.08
Successful expansion            | +0.05  | +0.03  |   —
Famine in controlled region     | -0.03  | -0.03  | +0.06
Tech focus matches faction      | +0.05 for matching faction
```

Multiple shifts per turn. All applied, then normalized.

### Action Weight Integration

```python
FACTION_WEIGHTS: dict[FactionType, dict[ActionType, float]] = {
    FactionType.MILITARY: {WAR: 1.8, EXPAND: 1.5, DIPLOMACY: 0.6, TRADE: 0.7},
    FactionType.MERCHANT: {TRADE: 1.8, BUILD: 1.5, EMBARGO: 1.3, WAR: 0.5},
    FactionType.CULTURAL: {DEVELOP: 1.8, DIPLOMACY: 1.5, WAR: 0.4, EXPAND: 0.6},
}

# Applied: weight × leader_trait_mod × faction_weight ^ faction_influence
# Exponentiation creates nonlinear tipping points
```

A faction at 0.6 influence has much more weight impact than at 0.33. Once above ~0.5, a faction's weight advantage accelerates its own success. The only brake is failure.

### M17 Interaction

Great persons shift faction influence directly — they are the faction's champions:
- Active general GP: military faction +0.03/turn
- Active merchant GP: merchant faction +0.03/turn
- Active prophet GP: cultural faction +0.03/turn
- Scientist GP: +0.02 to whichever faction matches the civ's active tech focus
- Character rivalries (M17) between GPs of different roles can accelerate power struggles — if a general and a merchant GP are rivals, their factions become more competitive
- Great person death removes the per-turn faction bonus, potentially triggering a power shift

### Power Struggles

Triggered when two factions are within 0.05 influence and both above 0.3:

- `stability -= 3/turn`
- Action effectiveness -20%
- If `power_struggle_turns > 5`: forced resolution

**Resolution: faction with more recent "wins" takes +0.15.**

Win definitions per faction type (counted over last 10 turns):
- **Military wins:** wars won + successful expansions
- **Merchant wins:** turns where treasury increased by ≥ 10
- **Cultural wins:** cultural works + movement adoptions + tech advancements

Ties: faction whose most recent win is more recent. Still tied: military wins (the generals have swords).

### Succession Integration with M17

M17 landed a full succession crisis system: multi-turn state machine, general-to-leader ascension, crisis candidates, exiled leaders. M22 does **not** replace this. Instead, the dominant faction biases which candidate wins the existing crisis:

- MIL dominant → general/military candidates get +0.15 weight in crisis resolution
- MER dominant → cautious/mercantile candidates get +0.15 weight
- CUL dominant → visionary/diplomatic candidates get +0.15 weight
- 10% chance of "outsider" — random candidate regardless of faction (populist surprise)
- Great person candidates (M17's general-to-leader pathway) get an additional +0.10 if their role matches the dominant faction

The crisis mechanics (duration, stability drain, rival leader generation) stay unchanged. Factions influence the outcome, not the process.

### Faction–Succession Interaction Design

Design sketch: `docs/superpowers/design/m22-faction-succession-design-sketch.md`

Covers: leader–faction alignment scoring (trait → faction mapping), faction-weighted candidate generation (internal + external + GP candidates), weighted resolution with 10% outsider chance, simultaneous power-struggle + crisis rules (crisis pauses power struggle timer, no double stability drain), exile restoration faction check, faction-aware grudge inheritance (0.3–0.7 rate instead of flat 0.5). All changes are additive to M17's state machine — trigger/tick/resolve flow preserved.

### Deliverables

- `src/chronicler/factions.py`: influence model, shifts, weights, power struggles
- `FactionState` on `Civilization`
- Succession integration with M17's crisis state machine (candidate weighting, not replacement)
- Leader–faction alignment scoring (trait → faction map)
- Faction-weighted candidate generation and resolution
- Power struggle ↔ crisis interaction rules
- Integration with consequences and action phases
- ~450 lines new code

---

## M23: Coupled Ecology

*Three coupled variables replacing single fertility float. Run M19 analytics before shipping.*

### Model Change

```python
class RegionEcology(BaseModel):
    soil: float = Field(default=0.8, ge=0.0, le=1.0)
    water: float = Field(default=0.7, ge=0.0, le=1.0)
    forest_cover: float = Field(default=0.5, ge=0.0, le=1.0)
```

On `Region`:
```python
ecology: RegionEcology = Field(default_factory=RegionEcology)
# fertility: float — REMOVED, replaced by ecology.soil
```

### Effective Capacity

```python
def effective_capacity(region: Region) -> int:
    water_factor = min(1.0, region.ecology.water / 0.5)
    soil_factor = region.ecology.soil
    return max(1, int(region.carrying_capacity * soil_factor * water_factor))
```

Water below 0.5 reduces capacity. Water at 0.0 = zero capacity regardless of soil.

### Variable Interactions

```
Variable      | Degrades from                    | Recovers from              | Cross-effects
--------------|----------------------------------|----------------------------|---------------
soil          | overpopulation (-0.02/turn)       | fallowing (+0.01/turn)     | forest_cover > 0.5 → recovery ×2
              | mining (-0.03/turn)               | irrigation (+0.005/turn)   | forest_cover < 0.2 → degradation ×1.5
water         | drought climate (-0.04/turn)      | cooling/temperate (+0.02)  | irrigation consumes (-0.01/turn)
              | overuse (pop > cap, -0.01)         | river terrain floor: 0.4   | deforestation increases runoff
forest_cover  | timber harvest (-0.05/event)      | depopulation (+0.005/turn) | affects soil recovery rate
              | pop pressure (-0.01/turn           | replanting (BUILD variant) | affects water retention
              |   when pop > cap × 0.7)            |                           |
```

### Feedback Loops

1. **Deforestation spiral:** timber harvest → low forest → soil recovery slows → soil degrades → capacity drops → migration → depopulation → forest slowly recovers (~50+ turns).
2. **Irrigation trap:** irrigation raises soil cap but consumes water. Drought → water drops → irrigation stops working → soil degrades → famine. Dependency on infrastructure that requires the resource drought removes.
3. **Mining collapse:** mines degrade soil (-0.03/turn). Without irrigation (+0.005 soil, -0.01 water), mines hit famine in ~25 turns. With irrigation, sustainable — until drought kills water supply.

### Terrain Defaults

```
Terrain    | Soil | Water | Forest Cover
-----------|------|-------|-------------
plains     | 0.9  | 0.6   | 0.2
forest     | 0.7  | 0.7   | 0.9
mountains  | 0.4  | 0.8   | 0.3
coast      | 0.7  | 0.8   | 0.3
desert     | 0.2  | 0.1   | 0.05
tundra     | 0.15 | 0.5   | 0.1
river      | 0.8  | 0.9   | 0.4
```

### Climate Integration

M15c's climate multipliers now affect water instead of fertility:
- **Drought:** water degradation ×2. Soil degrades indirectly when water collapse causes population die-off.
- **Warming:** coastal flood risk affects water (+0.1 temporary). Tundra water +0.1 (melt) — the new "tundra warming trap."
- **Cooling:** water -0.02/turn (freezing). Forest cover recovery halved.

### M19 Validation (Required)

Run 200 simulations with coupled ecology, compare to 200 with single-fertility. Validate:
- Do all three variables matter, or does one dominate?
- Does the irrigation trap actually fire?
- Does the deforestation spiral terminate (forest recovery) or run away?
- Are cascading ecological collapses too frequent? Too rare?

**Do not ship M23 without M19 confirming the coupled system produces better behavior than single-fertility.**

### M18 Migration Path

M18 introduced `Region.low_fertility_turns` and two terrain transition rules keyed to `fertility < 0.3`. When M23 replaces `fertility` with `RegionEcology`, the M18 ecological succession system must migrate:

- **Deforestation trigger:** `fertility < 0.3 for 50 turns` → `ecology.soil < 0.3 for 50 turns` (direct rename — soil replaces fertility as the primary degradation signal)
- **`Region.low_fertility_turns`** → rename to `Region.low_soil_turns` for clarity, or keep the name and update the threshold check
- **Rewilding trigger:** `depopulated for 100 turns` → no change needed (not fertility-dependent)
- **M18's `tick_terrain_succession` and `update_low_fertility_counters`** in `emergence.py` → update to read `ecology.soil` instead of `fertility`
- **Deforestation could become richer:** instead of a flat threshold, deforestation triggers when `forest_cover < 0.2` (M23's explicit variable) rather than inferring from low fertility. The `low_fertility_turns` counter could be replaced by directly reading `forest_cover`. Design decision for implementer, but the coupled ecology model makes the proxy unnecessary.

### Deliverables

- `RegionEcology` model replacing `fertility`
- `effective_capacity` rewrite
- Phase 9 rewrite: three-variable tick with cross-effects
- Climate, infrastructure, and disaster interaction updates
- Terrain defaults and migration path from `fertility` → `ecology.soil`
- M18 ecological succession migration: update `emergence.py` triggers to use coupled ecology variables
- ~250 lines replacing ~80, plus ~100 lines updating call sites

---

## M24: Information Asymmetry

*The lightest milestone. The best lines-of-code to narrative-impact ratio in the project.*

### Model

```python
class IntelligenceState(BaseModel):
    known_civs: dict[str, float] = Field(default_factory=dict)
    # key: civ name, value: accuracy (0.0 = no intel, 1.0 = perfect)
```

### Perceived Stats

```python
def get_perceived_stat(observer: Civilization, target: Civilization,
                       stat: str, world: WorldState) -> int:
    """
    actual_value ± (1.0 - accuracy) × 20

    Deterministic from seed + observer + target + turn.
    Same observer sees same perceived value all turn.
    """
    accuracy = observer.intelligence.known_civs.get(target.name, 0.3)
    noise_range = int((1.0 - accuracy) * 20)
    noise = deterministic_noise(world.seed, observer.name, target.name,
                                world.turn, stat, range=noise_range)
    return clamp(getattr(target, stat) + noise, 0, 100)
```

Default accuracy 0.3 = ±14 noise. A civ at military 50 appears as 36-64.

### Accuracy Sources

```
Source                              | Accuracy change
------------------------------------|----------------
Adjacent regions                    | +0.3
Active trade route                  | +0.2
Same federation                     | +0.4
Vassal/overlord                     | +0.5
At war                              | +0.3
Merchant faction dominant (M22)     | +0.1 to all
No contact (fog of war)             | 0.0
```

Capped at 1.0. Sources stack.

### Action Engine Integration

Replace direct stat reads with `get_perceived_stat` when evaluating targets for WAR, EXPAND, EMBARGO, and proxy wars (~5 callsites). Creates:
- Surprise attacks that succeed (target looked weak, was weak)
- Surprise attacks that fail (target looked weak, wasn't)
- Deterrence from perception (target looks strong, civ doesn't attack)
- Declining empire survival (nobody knows they're collapsing)
- Intelligence as strategic advantage (high-accuracy civs decide better)

### Faction Interaction

- Military dominant: no intel bonus
- Merchant dominant: +0.1 accuracy to all (trade networks = intel networks)
- Cultural dominant: +0.05 accuracy (cultural exchange)

### M17 Interaction

- Active merchant GP: +0.05 accuracy toward all known civs (personal trade connections = intelligence network, stacks with merchant faction bonus)
- Hostage GP held by another civ: +0.3 accuracy toward the holding civ (the hostage reports home)
- Grudges (M17): +0.1 accuracy toward the grudge target (you study your enemies closely)

### Design Decisions

Design sketch: `docs/superpowers/design/m24-information-asymmetry-design-sketch.md`

**Locked decisions:** Accuracy does not decay (recomputed from state each turn). Espionage is not an action type (passive computation only). Perceived stats affect decisions, not outcomes (war resolution uses actual military; trade uses perceived economy). Noise distribution is Gaussian with σ = noise_range/2, seeded deterministically per observer/target/turn/stat.

**Callsite map (6 integration points):** NEW war target evaluation in action weights, resolve_trade (economy), collect_tribute (economy), check_vassal_rebellion (stability + treasury), check_congress (military + economy), plus one new WAR weight callsite comparing perceived military of neighbors. War resolution, congress host, and mercenary hiring stay on actual stats. See design sketch for exact function/line references and rationale.

### Deliverables

- `IntelligenceState` on `Civilization` (simplified: no per-pair persistence needed)
- `get_perceived_stat()` function with Gaussian noise
- `compute_accuracy()` function (recomputed from state, no decay)
- Action engine integration: 5 existing callsites + 1 new WAR target evaluation
- TurnSnapshot extension: per-pair accuracy and perception error fields for M19 analytics
- ~150 lines new code

---

## Phase 4 Summary

| Code | Name | Lines | Integration |
|------|------|-------|-------------|
| M19 | Simulation Analytics | ~400 | Tooling only, no sim changes |
| M19b | Phase 3 Tuning Pass | ~0 | Constant changes across GameConfig |
| M20 | Narration Pipeline v2 | ~900 | Architectural, narrator + viewer |
| P4 | Regional Population | ~400 | Mechanical rewrite, all phases |
| M21 | Tech Specialization | ~350 | New system, moderate integration, M17 hooks |
| M22 | Factions | ~450 | New system, deep integration, M17 succession integration |
| M23 | Coupled Ecology | ~350 | Rewrite of existing system + M18 migration |
| M24 | Info Asymmetry | ~150 | Lightweight, high impact, M17 hooks |
| **Total** | | **~3,000** | |

No architectural changes. No new dependencies. No parallelism. Single-threaded Python on the 9950X. The 4090's role changes from turn-by-turn narrator to batch narrator with full history context. All negative stat modifications go through M18's severity multiplier.

---

## Phase 5 Preview

Phase 5 is where the 9950X earns its keep. Agent-based population simulation in Rust (PyO3 + rayon), 10,000+ agents across 32 threads. Agent state as contiguous arrays exposed to Python via numpy-compatible buffers or Arrow tables — the FFI boundary is a flat data buffer, not Pydantic objects. Python orchestrates; Rust computes.

Phase 5 requires Phase 4's aggregate simulation to be exhaustively validated first (via M19 analytics at scale). The aggregate model is the test oracle for the agent model.

---

## Cross-Cutting Notes

### M18 Severity Multiplier

M18's cascade failure system (`get_severity_multiplier(civ)`, range 1.0×–1.5× based on stress index) amplifies all negative stat modifications. Every Phase 4 milestone that produces negative stat changes must wrap them with the severity multiplier:

- **P4 (Regional Population):** military recruitment population drain, cross-border migration stability impact
- **M21 (Tech Specialization):** if focus loss on era change produces stat penalties
- **M22 (Factions):** power struggle stability drain (`-3/turn` → `int(-3 * get_severity_multiplier(civ))`), action effectiveness reduction
- **M23 (Coupled Ecology):** soil/water/forest degradation rates (multiply the per-turn degradation amounts)
- **M24 (Info Asymmetry):** no negative stat changes — does not apply

Rule: if a new mechanic subtracts from population, military, economy, culture, or stability, it goes through the severity multiplier. If it subtracts from treasury, ecology variables, or non-stat fields, it does not. This matches M18's design: "Do NOT apply to treasury costs — those are fixed structural costs, not event damage."

### Action Weight Composition

M17 traditions, M21 tech focuses, and M22 faction weights all feed multipliers into the action engine's `compute_weights()`. Three separate multiplier systems could produce extreme bias if they align (e.g., warrior tradition × METALLURGY focus × military faction dominance → WAR weight 1.3 × 1.3 × 1.8 = 3.04×). The action engine should cap the combined multiplier at 2.5× to prevent any single action from completely dominating selection. Flag for M19b tuning — the cap value may need adjustment based on analytics.

### Testing Philosophy

Each milestone testable in isolation with deterministic seeds. M19's batch runner provides statistical validation for every subsequent milestone — run analytics before and after each milestone lands. Regression = analytics distributions shift significantly.

### Scenario Compatibility

All new fields have defaults. Existing scenarios work unchanged:
- Missing `Region.population` → distributed from civ population at world gen
- Missing `tech_focuses` → empty (selected on advancement)
- Missing `factions` → default equal influence
- Missing `ecology` → migrated from `fertility` field
- Missing `intelligence` → default 0.3 accuracy

### Narrative Engine

M20 changes when and how the narrator is called, not what events exist. Each simulation milestone (M21-M24) adds new event types with importance scores. The narrator handles them through existing template expansion.

### Viewer Extensions

- M20: segmented timeline, mechanical gap views, "narrate this" button (~300 lines TS)
- M21: tech focus badge on civ panel
- M22: faction influence bar on civ panel
- M23: ecology variables on region hover (soil/water/forest as bars)
- M24: "intelligence quality" indicator on civ-to-civ relationship view
