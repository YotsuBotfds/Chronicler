# M53a/b: Depth Tuning Pass — Design Spec

> **Date:** 2026-03-21
> **Status:** Approved — Phoebe + user review complete, implementation plan in progress
> **Prerequisites:** M48 (merged), M49 (merged), M50a (merged), M50b (merged), M51 (merged), M52 (merged)
> **Depends on:** M48-M52 (all merged). Full scope is active — no pending substrates.

---

## 1. Goal

Calibrate ~145+ `[CALIBRATE M53]` constants across 5 depth systems (memory, needs, relationships, legacy, artifacts) and validate that the interconnected systems produce meaningful emergent social structure at 10-50K agent scale before the scale track begins. Constant inventory: ~114 Rust constants in `agent.rs` (41 memory + 37 needs + 8 relationship drift + 28 formation) plus ~30+ Python-side constants (3 Mule scalars + 9 Mule mapping entries with ~22 individual weight values + 2 legitimacy + 2 narrative thresholds + ~13 artifact constants in `artifacts.py`: 6 scalars + 7 `PRESTIGE_BY_TYPE` entries).

M53 is the explicit gate before M54a. If depth systems create unstable dynamics or oracles cannot confirm cohort/arc emergence, scaling does not begin.

## 2. Substrate Buckets

All work is categorized into three readiness buckets:

All M48-M52 substrates are merged. The full constant inventory is active scope — no pending substrates remain. All 6 system passes (1a-1f) are part of the M53a gate.

## 3. Canonical Benchmark Profile

All gates, oracles, and regression tables reference a single validation profile:

```
--scenario fantasy_default
--civs 4
--regions 8
--agents hybrid
--turns 500
--seed 42  (base seed; batch seeds = 42..42+N)
```

This matches `DEFAULT_CONFIG` in `main.py` (4 civs, 8 regions) and the existing batch validation baseline from M47.

**Run configurations:**

| Purpose | Command shape | Wall-clock estimate |
|---------|--------------|-------------------|
| Smoke gate | `--batch 5 --turns 50 --simulate-only --parallel 4` | ~5-10s |
| Scout loop | `--batch 40 --turns 200 --simulate-only --parallel 12` | ~30-60s |
| Full gate | `--batch 200 --turns 500 --simulate-only --parallel 12` | ~5-7 min |
| Oracle subset | 20 deterministic seeds from full gate (seeds 42-61), with raw sidecar | ~1-2 min |
| Narration sample | `--batch 10 --narrator api` on seeds 42-51 post-tuning | Variable (API latency) |

The oracle subset uses a **fixed seed range** (42-61, first 20 of the 200-seed gate) so reruns produce comparable results.

## 4. M53a.0 — Observability Substrate

Before any tuning, add the raw data feeds that both tuning metrics and M53b oracles consume.

### 4.1 Standard Analytics Extractors

Additions to `analytics.py`, run on every batch:

**`extract_bond_health()`** (extends or replaces existing `extract_relationship_metrics()` in `analytics.py` — do not create both)
- **Standard source:** `get_relationship_stats()` FFI (exists in `ffi.rs`, currently unwired from Python). Returns global-level stats: `mean_rel_count`, `mean_positive_sentiment`, `bond_type_count_0..7`, `cross_civ_bond_fraction`, plus last-tick formation counters (`bonds_formed`, `bonds_dissolved_structural`, `bonds_dissolved_death`, `bonds_evicted`, `pairs_evaluated`, `pairs_eligible`). No per-civ breakdown or sentiment quartiles in this API.
- **Standard output:** Global mean bonds/agent, bond-type distribution (8 types), last-tick formation/dissolution counts, cross-civ bond fraction.
- **Per-civ breakdown (validation runs only):** Derived from `get_all_relationships()` RecordBatch joined with agent `civ_affinity` column. Produces per-civ bond counts, per-civ sentiment quartiles, per-civ bond-type distributions. This join runs only during validation sidecar writes — too expensive for every-turn standard analytics.
- Wiring: connect `--relationship-stats` CLI flag → `get_relationship_stats()` → bundle metadata (global stats only)

**`extract_era_signals()`**
- Source: existing `CivSnapshot` time series from history
- Output: per-civ time series of population, territory count (`len(regions)`), prestige, treasury, stability, wealth Gini
- Format: dict of civ_name → dict of metric_name → list[float]

### 4.2 Validation-Only Primitives

Heavier exports, gated by a `--validation-sidecar` flag (or equivalent). Not run on production/narration batches.

**Bulk memory export — `get_all_memories()`**
- New Arrow FFI method on `AgentSimulator`, parallel to existing `get_all_relationships()`
- Returns RecordBatch: `agent_id: u32`, `slot: u8`, `event_type: u8`, `turn: u16`, `intensity: i8`, `is_legacy: u8`
- Plus join columns for matching: `civ_affinity: u8`, `region: u16`, `occupation: u8`
- Avoids 50K per-agent Python loops through `get_agent_memories(agent_id)`

**Bulk needs export — `get_all_needs()`**
- New Arrow FFI method on `AgentSimulator`
- Returns RecordBatch: `agent_id: u32` + 6 need floats (`safety`, `autonomy`, `social`, `spiritual`, `material`, `purpose`)
- Plus join columns: `civ_affinity: u8`, `region: u16`, `occupation: u8`, `satisfaction: f32`, `boldness: f32`, `ambition: f32`, `loyalty_trait: f32`
- Enables matched-cohort comparison without per-agent Python roundtrips

**Graph + memory sidecar**
- Arrow IPC file written alongside the bundle during validation runs
- Sampled every 10 turns (50 snapshots over 500 turns)
- Per snapshot: edge list (agent_a, agent_b, bond_type, sentiment) + per-agent memory signature (top 3 `(event_type, turn, valence_sign)` tuples)
- Valence sign included so "shared famine" and "shared victory" are distinguishable
- Size estimate at 50K agents, 3-5 bonds/agent: ~50 snapshots x ~150K edges x ~14 bytes ≈ ~105MB per seed (full raw)
- Condensed community summary: ~50-200KB per seed (cluster counts, size distributions, memory signatures per region per snapshot). At 200 seeds: ~10-40MB total for full gate — trivial.

**Condensed community summary**
- Computed in-run from sidecar snapshots at each sample point
- Per-region: cluster count, size distribution, dominant shared memory type
- Written to a `validation_summary` sidecar file (not bundle `metadata` — keeps bundle lightweight)
- Used for full 200-seed gate runs instead of raw sidecar

**Sidecar budget policy:**

| Run type | Raw sidecar | Condensed summary |
|----------|-------------|-------------------|
| Scout (40x200) | Yes | Yes |
| Oracle subset (seeds 42-61) | Yes | Yes |
| Full gate (200x500) | No | Yes |
| Debug/failing seeds | Yes | Yes |

### 4.3 Agent-Level Validation Summary

CivSnapshot lacks satisfaction distribution and occupation breakdown. Add a per-turn `AgentAggregate` to the `validation_summary` sidecar:

- Per civ per turn: satisfaction mean/std/quartiles, occupation counts (5 types), agent count (alive denominator), mean need levels (6 floats), memory slot occupancy mean
- Source: computed from agent snapshot during Phase 10, written only during validation runs
- This provides the denominators for "% of agent-turns" regression metrics and the satisfaction distribution baseline

### 4.4 Existing Substrate Reuse

- `agent_events.arrow` sidecar (already in `bundle.py`) — M53b's needs-diversity oracle consumes this to correlate need states with subsequent behavioral events
- `get_all_relationships()` RecordBatch (already in `ffi.rs:1133`) — foundation for graph sidecar snapshots
- `get_relationship_stats()` (already in `ffi.rs:1040`) — bond distribution data

### 4.5 Existing Artifact Extractor

`extract_artifacts()` in `analytics.py` (line 1654) already extracts: total/active/lost/destroyed counts, per-civ artifact counts, per-type distribution, total prestige contribution, Mule-origin artifact count. This is sufficient as the M53a baseline extractor. If tuning reveals gaps (e.g., per-turn creation rate time series, narrative visibility frequency), extend this extractor rather than creating a new one.

### 4.6 Legacy Extractor

**`extract_legacy_chain_metrics()`** — new extractor for M51 legacy system:
- Legacy memory persistence across generations (mean legacy intensity at 2nd/3rd generation)
- Dynasty memory chain length (how many generations carry inherited memories)
- Legitimacy activation rate (fraction of successions where `civ.leader.agent_id is not None`)
- Source: bulk memory export (`get_all_memories()` with `is_legacy` column) + `GreatPerson` dynasty data from bundles

## 5. M53a.1 — Tuning Pipeline

### 5.0 Prerequisite: Tag Normalization

Many `[CALIBRATE M53]` constants use block-header tags (one comment covering a group) rather than individual per-constant tags. The M50b formation constants (~28 values) have no individual tags at all. Before the freeze-tagging step can work via grep, add individual `[CALIBRATE M53]` tags to every constant that currently lacks one. This is a mechanical task in M53a.0 scope.

Additionally, `_NEED_THRESHOLDS` in `narrative.py` must stay synced with the corresponding constants in `agent.rs`. When M53 tunes the Rust threshold constants, the Python narrative thresholds must be updated in the same pass. Document this cross-language sync obligation in the frozen YAML.

### 5.1 Phase -1: Smoke Gate

Before investing in the baseline sweep, verify the observability substrate works:

1. Run 2 identical seeds (same seed, same config) → confirm deterministic output
2. Run `--batch 5 --turns 50 --simulate-only --parallel 4 --validation-sidecar`
3. Verify: no crashes, sidecar files written correctly, extractors produce non-empty output, no obvious degeneracy (all zeros, NaN, etc.)

### 5.2 Phase 0: Baseline Sweep

Run a full scout loop (`--batch 40 --turns 200 --simulate-only --parallel 12 --validation-sidecar`) with all current defaults unchanged. Extract all standard metrics + validation primitives.

This establishes the "before" snapshot (`tuning/m53_baseline.yaml`). No constants change.

**Key questions the baseline answers:**
- Which metrics are already in acceptable range vs wildly off?
- Are there degenerate states? (all memories at zero, needs permanently saturated, zero bonds forming, memory slot occupancy at 0 or 8/8)
- Does the simulation reach turn 200 stably across all 40 seeds?
- Which of M49's 10 calibration flags are already visible?

### 5.3 Phase 1: System Passes

Each pass tunes one system's constants while holding others fixed. Scout loops (40x200) for iteration; one full gate (200x500) to confirm before freezing.

**Working rhythm:** Many scout iterations per edit cycle. The full gate is a freeze confirmation, not a per-edit check.

| Pass | System | Key Constants (~count) | Primary Metrics | Depends On |
|------|--------|----------------------|-----------------|------------|
| 1a | Memory (M48) | Intensities (14 types), half-lives (14 types), `MEMORY_SATISFACTION_WEIGHT`, utility magnitudes (11 event→action mappings), legacy base constants (2) (~41 Rust) | Memory slot occupancy (target: 3-6 mean), intensity distribution (not degenerate), satisfaction contribution (within 0.40 cap budget as 5th priority) | Nothing — foundational |
| 1b | Needs (M49) | Decay rates (6), thresholds (6), weights (6), restoration rates (16), infrastructure constants (3) (~37 Rust) | Need activation fraction (peacetime 10-20%, crisis 40-70%), behavioral diversity, sawtooth check, duty cycle per need | 1a (memory feeds needs indirectly) |
| 1c | Relationships (M50) | Kin sentiments (2), co-location drift (4), strong-tie threshold/cadence (2), separation decay (2), formation gate constants (~28: similarity weights, rank crossing, per-type gates, triadic closure, scan limits, dissolution cadence), `SOCIAL_BLEND_ALPHA` (~36 Rust) | Bond count/agent (target: 3-5 at steady state), formation/dissolution rates, sentiment distribution, social-need restoration adequacy | 1a (shared memory → bond eligibility) |
| 1d | Mule (M48) | `MULE_PROMOTION_PROBABILITY`, `MULE_ACTIVE_WINDOW`, `MULE_FADE_TURNS` (3 scalars) + `MULE_MAPPING` (9 event-type entries with ~22 individual weight values) (~25 Python) | Mule frequency (~0-1 per 100 turns at 50K), impact window visibility (80%+ curator selection), civ action distribution shift during window | 1a-1c (Mule effects ripple through all systems) |
| 1e | Legacy (M51) | `LEGACY_HALF_LIFE`, `LEGACY_MIN_INTENSITY`, `LEGACY_MAX_MEMORIES` (3 Rust in `agent.rs`), `LEGITIMACY_DIRECT_HEIR`, `LEGITIMACY_SAME_DYNASTY` (2 Python in `dynasties.py`), regnal naming constants (~6 total) | Legacy persistence (2-3 generations), dynasty chain length, legitimacy activation rate (>20% of successions), inherited-cohort formation | 1a, 1c |
| 1f | Artifacts (M52) | `CULTURAL_PRODUCTION_CHANCE`, `GP_PRESTIGE_THRESHOLD`, `RELIC_CONVERSION_BONUS`, `PROSPERITY_STABILITY_THRESHOLD`, `PROSPERITY_TREASURY_THRESHOLD`, `HISTORY_CAP` (6 scalars) + `PRESTIGE_BY_TYPE` (7 type→value entries) (~13 Python in `artifacts.py`) | Artifact accumulation (1-3 per civ per 100 turns via `extract_artifacts()`), Mule artifact rate (~50-70% of Mules produce artifact), narrative visibility (artifact context in curated moments), relic conversion bonus impact | 1d (Mule artifacts) |

**M49 calibration flag checklist** — each system pass explicitly checks the relevant flags:

| Flag | Checked in Pass | What to verify |
|------|----------------|---------------|
| Persecution triple-stacking | 1b | M38b (0.30) + M48 memory (~0.10) + M49 Autonomy (up to 0.24) total rebel modifier <0.64 |
| Famine double-counting | 1b | food_sufficiency penalty + Safety need deficit don't stack beyond intended budget |
| Needs-only rebellion rate | 1b | <5% of rebellions driven solely by need deficits (needs supplement, not replace, existing drivers) |
| Need activation fraction | 1b | Peacetime 10-20%, crisis 40-70% of agents below at least one threshold |
| Migration sloshing | 1b, 1c | No region-pair oscillation pattern across consecutive turns |
| Sawtooth oscillation | 1b | No need cycling between depleted→restored→depleted within <10 turns |
| Duty cycle per need | 1b | Each need spends meaningful time in both satisfied and deficit states |
| Social proxy adequacy | 1c | M50b blend formula (`SOCIAL_BLEND_ALPHA`) produces reasonable social-need restoration |
| Negative modifier trapping | 1a | Memory-driven satisfaction penalty doesn't push agents into permanent low-satisfaction |
| Autonomy assimilation loop | 1b | Foreign-controlled agents don't get trapped in autonomy deficit → rebel → reconquered → autonomy deficit |

### 5.4 Phase 2: Integration Pass

After all 6 system passes (1a-1f), run a full gate (200x500) with all tuned constants active together.

**Cross-system checks:**
- Satisfaction floor-hitting rate: <30% of any region's agents at floor simultaneously
- Total rebel modifier from all penalty sources: verify within intended budget
- Migration cascade stability: no persistent sloshing patterns
- Overall rebellion rate: 2-8% of agent-turns
- Overall migration rate: 5-15% of agent-turns
- No occupation collapse (no occupation at 0% or >70% of civ population)

**Satisfaction.rs scope note:** The 0.40 penalty cap budget is shared across M36 cultural, M37 religious, M38b persecution, M41 class tension, M48 memory, and M49 needs. If integration reveals that memory + needs consume the entire budget leaving no room for existing penalties, the satisfaction.rs constants (e.g., `FOOD_SHORTAGE_WEIGHT`, `MERCHANT_MARGIN_WEIGHT`, temple priest bonus) are candidates for adjustment even though they currently carry generic `[CALIBRATE]` tags, not `[CALIBRATE M53]`. **If any such constant is adjusted during M53 integration:** promote its tag to `[CALIBRATE M53-INTEGRATION]`, include its before/after values in the frozen YAML, and assign it a SOFT freeze tier. This prevents the scope leak of M53 adjusting constants that are invisible to the M53 freeze/grep machinery.

**Integration failure protocol:** If cross-system problems emerge, identify the primary contributing system's constants, re-run that system pass with others at frozen values, then re-run integration.

### 5.5 Phase 3: Freeze

After integration passes, commit the frozen state:

**YAML snapshots:**
- `tuning/m53_baseline.yaml` — Phase 0 "before" snapshot (all defaults)
- `tuning/m53a_frozen.yaml` — all tuned constant values with tier tags

**Freeze tiers:**

| Tier | Scope | Examples | Change requires |
|------|-------|---------|----------------|
| **HARD** | Cross-system and structural constants | Satisfaction weights, 0.40 penalty cap, clamp priority order, rebellion/migration consideration thresholds, relationship slot budget, `SOCIAL_BLEND_ALPHA`, needs-only rebellion gates, Mule utility floor (if materially shifts civ action distributions) | Documented justification + full M53 regression suite + oracle subset re-run + explicit approval |
| **SOFT** | System-local tuning values | Individual memory half-lives, specific need restoration/decay rates, Mule window/fade, kin sentiment values, formation cadence thresholds, artifact production probabilities, legacy intensity cutoffs | Relevant system's regression metrics must hold |
All constants are eligible for HARD or SOFT freeze — no UNFROZEN tier needed since all substrates have landed.

**Source tag updates:** `[CALIBRATE M53]` → `[FROZEN M53 HARD]` or `[FROZEN M53 SOFT]`. The YAML snapshot is the authoritative freeze record; source tags are helpful but secondary.

**Scale-finding guardrail:** If a later scale milestone (M54+) discovers pressure on a depth constant:
1. Document the finding
2. Test whether a scale-local fix exists
3. Only reopen the frozen depth constant if the behavior is genuinely wrong, not just different under load
4. Default: scale findings → scale-local fixes, not depth constant reopening

## 6. M53b — Validation Oracles

Formal pass/fail oracles built over M53a.0 data pipes. Oracles run as a **post-processing pass** over completed batch output + sidecar data, not in the simulation loop.

**Entry point:** `python -m chronicler.validate --batch-dir <path> --oracles all`

The `chronicler.validate` module is new — lives outside the simulation pipeline, consumes exported data (bundles + sidecars + `validation_summary`), produces structured reports.

### 6.1 Oracle Execution Model

| Oracle | Data source | Runs on |
|--------|------------|---------|
| Community/Cohort | Raw graph+memory sidecar | Oracle subset (20 seeds) |
| Needs Diversity | `agent_events.arrow` + bulk needs export | Oracle subset (20 seeds) |
| Era Inflection | `extract_era_signals()` from bundles | Full gate (200 seeds) + narration sample (10 seeds) |
| Cohort Distinctiveness | Raw sidecar + `agent_events.arrow` | Oracle subset (20 seeds) |
| Artifact Lifecycle | `extract_artifacts()` + region conversion data + narrated prose | Full gate (200 seeds) + narration sample (10 seeds) |
| Six Emotional Arcs | `extract_era_signals()` from bundles | Full gate (200 seeds) |
| Partial Arc Detection | Event timeline from bundles + `arcs.py` substrate | Oracle subset — stretch |

### 6.2 Blocking Oracles

These must all pass before the scale track begins.

#### Oracle 1: Community / Cohort Emergence

**What it measures:** Do groups of 5+ agents with mutual bonds and shared memories form consistently?

**Method:** Deterministic label propagation community detection on the graph+memory sidecar. Run on each sampled snapshot (every 10 turns). Edge weights: friend + co-religionist + kin edges weighted by sentiment. Filter detected communities to those where >=80% of members share at least one memory `(event_type, turn, valence_sign)` tuple.

**Kin-only exclusion:** Qualifying communities must contain at least one non-kin positive-valence edge. Pure dynastic/family clumps do not count — they satisfy graph connectivity trivially once M51 lands.

**Acceptance criteria:**
- Qualifying communities appear in >=15/20 oracle-subset seeds (75%)
- Mean community count per seed at steady state (turns 100-500): 3-15
- Community size distribution: median 5-12 agents, no single community >5% of regional population

**Failure investigation (in order):**
1. Memory decay too fast → agents forget before bonds form → check half-lives
2. Formation threshold too high → shared memory exists but bonds don't form → check compatibility_score thresholds
3. Slot eviction too aggressive → bonds pruned before strengthening → check eviction policy
4. Formation cadence too low → not enough formation opportunities → check stagger interval

#### Oracle 2: Needs Behavioral Diversity

**What it measures:** Do agents with similar traits but different need states make different decisions?

**Method:** Matched-cohort comparison from bulk needs export + `agent_events.arrow`. Identify agent pairs matched on (civ, region, occupation, personality ±0.1) but divergent on at least one need (delta >0.2). Compare behavioral event rates (migration, occupation switch, rebellion) over the following 20 turns. Need-state matching uses the nearest prior sidecar sample point (every 10 turns); the 20-turn behavioral window starts from that sample point. Up to 10-turn lag between actual need state and matched snapshot is acceptable given the modest effect size threshold.

**Note:** `agent_events.arrow` contains death, rebellion, migration, occupation_switch, loyalty_flip, birth, and dissolution events. Bond formation is not recorded as an agent event (it happens Rust-side in formation_scan). Bond-formation correlation is measured separately via Oracle 4 (graph-diff between sidecar snapshots), not here.

**Statistical approach:** Per-seed effect sizes, not pooled p-values. With 50K agents, tiny useless effects look significant in pooled tests.
- Primary: median Cohen's d across oracle-subset seeds
- Secondary: fraction of seeds showing expected sign
- Tertiary: bootstrap CI for confirmation

**Acceptance criteria:**
- Median per-seed effect size >0.1 Cohen's d across 20 oracle-subset seeds
- >=12/20 seeds (60%) show expected sign (divergent needs → divergent behavior)
- Need activation fraction in peacetime: 10-20% of agents below at least one threshold
- Need activation fraction in crisis: 40-70%

**Failure investigation:**
1. Threshold values too high → needs never activate → check `NEED_*_THRESHOLD`
2. Threshold values too low → needs always active (no diversity) → check thresholds
3. Utility modifier magnitudes too small → drowned by other terms → check `NEED_*_WEIGHT`
4. Decay/restoration rates → sawtooth oscillation (needs cycling too fast to matter) → check rates

#### Oracle 3: Era Inflection Detection

**What it measures:** Does the simulation produce clear rise/collapse inflection points?

**Method:** Changepoint detection on `extract_era_signals()` time series (population, treasury, stability, territory). Uses mechanical changepoint detection (e.g., PELT or simple smoothed-derivative sign-change counting), not narrative parsing.

**Two-part structure:**
- **Blocking part:** Mechanical changepoint detection on full 200-seed gate
- **Informational part:** Narrator alignment check on 10-seed narration sample — compare detected inflection points against narrator era register boundaries. Valuable signal but not a gate failure condition (model variance should not block M53b).

**Acceptance criteria (blocking):**
- >=160/200 seeds (80%) produce >=2 inflection points detectable above noise threshold
- No "silent collapses" — population drops >30% that don't correspond to any detected inflection point in >10% of seeds

**Acceptance criteria (informational, narrator alignment):**
- >=60% of detected inflection points in narrated sample fall within ±5 turns of a narrator era boundary
- Misalignment logged for investigation but does not block

**Failure investigation:**
1. No inflections detected → simulation too stable or too noisy → check severity multiplier, emergence event frequency
2. Inflections exist but narrator misses them → era register signals under-exposed in bundle → check narrator context pipeline

#### Oracle 4: Cohort Behavioral Distinctiveness

**What it measures:** Do detected communities behave measurably differently from non-community agents?

**Method:** For each community detected by Oracle 1, construct a matched control group from non-community agents (same civ, region, occupation distribution, similar satisfaction). Compare: occupation switching rate, migration rate, rebellion participation, mean bond count.

**Statistical approach:** Same as Oracle 2 — per-seed effect sizes, median across seeds, fraction showing expected sign.

**Acceptance criteria:**
- >=12/20 oracle-subset seeds (60%) show expected behavioral difference direction
- Expected directions: community members show 15-30% less migration (social anchoring) OR 20-40% higher rebellion co-participation (collective action)
- At least one behavioral metric differs with median effect size >0.1

**Failure investigation:**
1. Communities exist but don't behave differently → bond effects on utility too weak → check relationship utility modifiers
2. Shared memory doesn't translate to coordinated behavior → memory→utility pipeline disconnected → check memory utility modifier magnitudes

### 6.3 Committed Oracles (Lighter Scope)

#### Oracle 5: Artifact Lifecycle

**What it measures:** Do artifacts create, persist, transfer, and generate narrative value at intended rates?

**Data sources:**
- `extract_artifacts()` from bundles — creation counts, type distribution, Mule origin, prestige, loss/destruction (full 200-seed gate)
- Region conversion rate data from `CivSnapshot` history or `religion.py` conversion events — relic conversion impact comparison (full 200-seed gate)
- 10-seed narration sample (`--narrator api`) — narrative visibility check (narrated prose scanned for artifact name references)

**Acceptance criteria:**
- Artifact creation rate: 1-3 per civ per 100 turns (mean across 200 seeds)
- Mule artifact rate: 50-70% of Mule characters produce an artifact during active window
- Relic conversion bonus measurable: regions with relics show higher conversion rate than matched control regions without relics (from CivSnapshot/event data, not narration)
- Artifact narrative visibility: in 10-seed narration sample, >=50% of curated moments involving an artifact-holding named character include artifact context in the prose
- No artifact type comprises >50% of total artifacts (type diversity)
- Artifact loss/destruction rate: 10-30% of artifacts lost or destroyed by turn 500 (not 0% = too stable, not >50% = too fragile)

**Failure investigation:**
1. Too few artifacts → `CULTURAL_PRODUCTION_CHANCE` or `GP_PRESTIGE_THRESHOLD` too restrictive
2. Too many → production chance too high or prestige threshold too low
3. No Mule artifacts → Mule action success rate too low (check Pass 1d)
4. No narrative visibility → `_get_relevant_artifacts()` or `render_artifact_context()` filtering too strict

#### Oracle 6: Six Emotional Arcs

**What it measures:** Do civ-level trajectories span the standard arc families?

**Method:** Classify each civ's population+territory+prestige trajectory into: Rags to Riches, Riches to Rags, Icarus, Oedipus, Cinderella, Man in a Hole. Uses mechanical trajectory shape (smoothed derivative sign changes), not narrative parsing.

**Acceptance criteria:**
- 5 of 6 arc families appear across 200 seeds (6 of 6 ideal)
- No single arc dominates >40% of civs
- At least 3 distinct arc types per seed (across all 4 civs)

Missing one family is borderline, not automatic fail. Two missing is a fail.

### 6.4 Stretch Oracle

#### Oracle 7: Partial Arc Detection

**What it measures:** Do character-level narrative arcs leave incomplete but recognizable patterns?

**Method:** Template-match on event timeline against incomplete arc patterns (betrayal setup without payoff, loyalty test without resolution, succession crisis without successor). Builds on existing `arcs.py` and M45 character-event machinery — does not invent a second arc vocabulary.

**Ships only if:** The event timeline query substrate is already in place from M53a work. If not, deferred to a future milestone.

## 7. Regression Suite

Separate from oracles. Regression guards determinism and Phase 6 calibrated behaviors. Runs on every full gate (200x500).

### 7.1 Determinism Smoke Gate

`--agents=off` bit-identity check. Guards determinism, not depth system health. Run as a standalone smoke gate before the behavioral regression suite.

**Environment:** `PYTHONHASHSEED=0` required for deterministic dict ordering. Set explicitly in the validation harness, not assumed from shell.

**Comparison target:** Scrubbed bundle comparison — exclude `metadata.generated_at` (fresh timestamp per run). Compare: `world_state`, `history`, `events_timeline`, `named_events`, `chronicle_entries`, `era_reflections`. The scrubbing logic lives in the `chronicler.validate` module alongside the oracle runner.

- 2 identical seeds with `--agents=off` → scrubbed output match
- 2 identical seeds with `--agents=hybrid` → scrubbed output match

### 7.2 Behavioral Regression

All metrics measured against M47 baseline (or M53 Phase 0 baseline if M47 baseline unavailable for a metric). Benchmark profile: 4 civs, 8 regions, `fantasy_default`.

| Metric | Source | Acceptable Range | Regression = |
|--------|--------|-----------------|--------------|
| Satisfaction distribution | `AgentAggregate` in `validation_summary` | Mean 0.45-0.65, std 0.10-0.25 | Mean shifts >0.05 or std shifts >0.05 from baseline |
| Rebellion rate | Event timeline | 2-8% of agent-turns | >2x or <0.5x baseline |
| Migration rate | Event timeline | 5-15% of agent-turns | >2x or <0.5x baseline |
| Wealth Gini | CivSnapshot `gini` field | 0.3-0.7 per civ at turn 500 | >80% of civs outside range |
| Occupation distribution | `AgentAggregate` in `validation_summary` | No occupation >60% or <5% of civ population | Any occupation at 0% or >70% |
| Civ survival | World state at turn 500 | 1-4 civs alive (from 4 starting) | 0 or all 4 surviving in >20% of seeds |
| Treasury stability | CivSnapshot `treasury` | No civ with negative treasury for >50 consecutive turns | >30% of surviving civs in perpetual deficit |

Note: "agent-turns" denominator comes from `AgentAggregate.agent_count` summed across turns in `validation_summary`.

## 8. Completion Criteria

### 8.1 M53a Completion

All must hold simultaneously:

1. Smoke gate passed (Phase -1)
2. Baseline sweep completed and documented (`tuning/m53_baseline.yaml`)
3. All 6 system passes (1a-1f) completed
4. Integration pass completed — no cross-system degeneracy
5. Regression suite passes (Section 7)
6. Frozen YAML snapshot committed (`tuning/m53a_frozen.yaml`)
7. Constants tagged in source: `[CALIBRATE M53]` → `[FROZEN M53 HARD]` or `[FROZEN M53 SOFT]`
8. M49's 10 calibration flags each explicitly addressed (passed, mitigated, or documented as acceptable with rationale)

### 8.2 M53b Completion

1. `chronicler.validate` module exists with structured `--oracles` entry point
2. Oracle subset (seeds 42-61 with raw sidecars) run; all 4 blocking oracles pass (Section 6.2)
3. Artifact lifecycle oracle passes on full 200-seed gate (Section 6.3)
4. Six-arc distribution: 5 of 6 arc families appear across 200 seeds (Section 6.3)
5. Full 200-seed gate with condensed community summaries confirms no structural issues
6. Validation report committed to `docs/superpowers/analytics/m53b-validation-report.md`

### 8.3 M53 Overall Gate

M53a + M53b both pass. This is the explicit gate before M54a begins.

### 8.4 Post-M53 Constant Discipline

- **HARD-frozen constant change:** Documented justification + full M53 regression suite + oracle subset re-run + explicit approval
- **SOFT-frozen constant change:** Relevant system's regression metrics must hold
- **Scale findings (M54+):** Default to scale-local fixes. Depth constant reopening requires explicit approval.
- All substrates merged — no supplement passes needed

## 9. New FFI Surface

| Method | Module | Returns | Purpose |
|--------|--------|---------|---------|
| `get_all_memories()` | `ffi.rs` | Arrow RecordBatch (agent_id, slot, event_type, turn, intensity, is_legacy, civ_affinity, region, occupation). Note: `is_legacy` is derived from per-agent `memory_is_legacy` bitmask via `(bitmask >> slot) & 1` extraction, not a per-slot u8 array. | Bulk memory export for validation |
| `get_all_needs()` | `ffi.rs` | Arrow RecordBatch (agent_id, safety, autonomy, social, spiritual, material, purpose, civ_affinity, region, occupation, satisfaction, boldness, ambition, loyalty_trait) | Bulk needs export with join columns |

Both methods are validation-only — called by the sidecar writer, not the simulation loop.

## 10. New Files

| File | Purpose |
|------|---------|
| `src/chronicler/validate.py` | Oracle runner module (`python -m chronicler.validate`) |
| `tuning/m53_baseline.yaml` | Phase 0 baseline snapshot |
| `tuning/m53a_frozen.yaml` | Frozen constant values with tier tags |
| `docs/superpowers/analytics/m53b-validation-report.md` | M53b oracle results |

## 11. Estimated Effort

| Sub-milestone | Scope | Est. Days |
|---------------|-------|-----------|
| M53a.0 | Observability: extractors, bulk FFI, sidecar format, validation_summary, tag normalization | 1-2 |
| M53a.1 | Tuning: smoke → baseline → 6 system passes (1a-1f) → integration → freeze | 3-4 |
| M53b | Oracles: validate module, 4 blocking + 2 committed oracles (artifact lifecycle + six arcs) + 1 stretch, reports | 2-3 |
| **Total** | | **6-9** |

## 12. Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Cross-system penalty stacking destabilizes during integration | High | M53a Phase 2 explicitly checks; individual system passes tune within budget before combining |
| Cohort oracle threshold structurally unreachable pre-M55 (no spatial proximity) | Medium | Threshold lowered to 5+ agents (not 10+); full validation deferred to M61 post-spatial |
| 125+ constants overwhelm manual tuning | Medium | Staged pipeline + scout loops keep iteration cheap; baseline reveals which defaults are already reasonable |
| Oracle statistical criteria too strict / too lenient | Medium | Per-seed effect sizes (not pooled p-values) avoid significance inflation; criteria calibrated against baseline |
| Raw sidecar disk usage during scout loops | Low | Sidecar policy: raw for scouts + oracle subset, condensed for full gates |
| Memory/needs bulk FFI methods add maintenance surface | Low | Validation-only methods, parallel to existing `get_all_relationships()` pattern |
