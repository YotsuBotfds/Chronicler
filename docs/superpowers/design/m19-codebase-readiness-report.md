# M19 Codebase Readiness Report

> Post-M17 codebase review (pre-M18). Identifies what exists, what's missing, and what needs to change for M19 analytics.
> Written by Phoebe. Read this when writing the M19 spec.

---

## 1. Existing Infrastructure Assessment

### batch.py — Ready, Needs Extension

The batch runner works. `run_batch()` executes N seeds via `ProcessPoolExecutor` (or serial fallback), collects `RunResult` per run, writes `summary.md` sorted by interestingness score. Clean architecture — each run gets its own directory under `batch_{seed}/seed_{N}/`.

**What works today:**
- Parallel execution via `multiprocessing.Pool`
- Per-run `RunResult` collection
- `summary.md` with interestingness ranking
- `--parallel` flag for worker count control

**What's missing:**
- No `--simulate-only` integration (each run still tries to narrate)
- No `batch_report.json` output (only markdown)
- No aggregate statistics across runs (only per-run scores)
- No `--seed-range` flag (uses sequential `base_seed + i`)
- No `--tuning` override support

### types.py — RunResult Too Narrow

`RunResult` captures 12 fields: seed, output_dir, war_count, collapse_count, named_event_count, distinct_action_count, reflection_count, tech_advancement_count, max_stat_swing, action_distribution, dominant_faction, total_turns, boring_civs.

**Gaps for M19:**
- No per-system metrics (M13-M18 mechanic-specific counts)
- No timing data (turn-of-first-famine, turn-of-first-war, elimination turns)
- No stability/population distribution data
- No trade route or treasury metrics
- No great person, tradition, succession, or movement counts

**Decision: Don't expand RunResult.** Keep it for backward compat. The new `analytics.py` reads bundles directly, which contain everything.

### interestingness.py — Keep As-Is

7-weight linear scoring function. `find_boring_civs` detects action monoculture. Both are simple and correct. M19 doesn't need to change these — they serve the "pick the most interesting run" use case. Analytics serves a different use case (statistical distributions across all runs).

### TurnSnapshot + CivSnapshot — Rich but Incomplete

**Already captured per turn (good):**
- All 5 civ stats (population, military, economy, culture, stability)
- Treasury, asabiya, tech_era, trait, regions, leader name
- Is_vassal, is_fallen_empire, in_twilight, federation_name
- Prestige, capital, great_persons (active), traditions, folk_heroes, active_crisis
- Region control map, relationships (disposition only)
- Trade routes, active wars, embargoes, fertility per region
- Mercenary companies, vassal relations, federations, proxy wars, exile modifiers
- Capitals, peace_turns, region cultural identity, movements summary

**Missing for M19 analytics (need to add):**
- `climate_phase: str` — current climate phase (warming/cooling/etc.)
- `per_civ_stress_index: dict[str, float]` — M18 stress values (once M18 lands)
- `black_swan_this_turn: str | None` — M18 event type (once M18 lands)
- `active_conditions_summary: list[dict]` — condition types + severity + remaining duration
- `per_civ_last_income: dict[str, int]` — already on Civilization but not in snapshot
- `succession_crises_active: list[str]` — civ names in crisis (derivable from active_crisis but not aggregatable)

Notably, trade_routes is already on TurnSnapshot (good — we assumed it wasn't). Same for active_wars, embargoes, fertility, and movements_summary. The snapshot is richer than the design sketch expected.

### Bundle Format — Perfect for Analytics

`chronicle_bundle.json` contains:
- `world_state` — final WorldState JSON (full model dump)
- `history` — list of TurnSnapshot dicts (one per turn)
- `events_timeline` — every Event ever generated
- `named_events` — significant named events
- `chronicle_entries` — {turn: text} (narrative)
- `era_reflections` — {turn: text} (reflections)
- `metadata` — seed, total_turns, sim_model, narrative_model, scenario_name, interestingness_score

**This is the analytics input.** The bundle has everything: per-turn snapshots (time-series), full event log (firing rates), and final state (end-game distributions). Analytics never needs to import simulation code — it just reads JSON.

### Main Loop Snapshot Capture — Clean, Easy to Extend

Lines 212-261 in `main.py` build the TurnSnapshot after each `run_turn()` call. Adding new fields is ~1 line per field. No architectural change needed.

### Event Types Available for Analytics

From `events_timeline` event_type values across the codebase:
- **Environment:** drought, plague, earthquake, flood, wildfire, sandstorm
- **Climate:** migration (climate-driven)
- **Political:** war, rebellion, secession, collapse, coup, border_incident
- **Economic:** famine, embargo
- **Cultural:** cultural_work, cultural_renaissance, discovery, religious_movement
- **Tech:** tech_advancement
- **Leaders:** leader_death, trait_evolution
- **M17:** great_person_born, tradition_acquired, succession_crisis, exile_restoration, folk_hero_created, hostage_taken, hostage_ransomed, rivalry_formed, mentorship_formed, marriage_formed
- **M14:** mercenary_spawned, vassal_imposed, federation_formed, federation_dissolved, vassal_rebellion, proxy_war_started, proxy_war_detected, twilight_absorption, restoration
- **M16:** movement_emerged, paradigm_shift, cultural_assimilation

This is a rich event taxonomy. The analytics module can compute firing rates for every event type with a single pass over `events_timeline`.

---

## 2. Tunable Constants Catalog

The codebase has **~250+ hardcoded numeric constants** across 15+ modules. These are the tuning targets for M19b. Major categories:

### Critical Tuning Targets (Likely Broken)

Based on the universal stability-0 problem observed in the Qwen test run:

| Constant | File | Current Value | Likely Issue |
|---|---|---|---|
| Stability loss from conditions | simulation.py | -10/turn at severity ≥ 50 | Stacks with other -10 hits, no recovery mechanism |
| Population growth threshold | simulation.py | stability > 20 | If stability is always 0, population never grows |
| Stability loss from drought | simulation.py | -10 | Plus condition ongoing -10/turn = -20 total |
| Stability loss from plague | simulation.py | -10 | Plus condition ongoing -10/turn = -20 total |
| Stability loss from famine | simulation.py | -10 | Plus fertility threshold 0.3 is very generous |
| Stability loss from war costs | simulation.py | -5 when treasury ≤ 0 | Per-war-per-turn, compounds fast |
| Stability loss from governing | politics.py | -1 per distance unit | Large empires hemorrhage stability |
| Asabiya collapse threshold | simulation.py | asabiya < 0.1 AND stability ≤ 20 | Both hit simultaneously = cascade |
| Famine population loss | simulation.py | -15 | Very harsh, plus stability -10 |
| Black market stability loss | simulation.py | -3/turn | Embargoed civs spiral |

The pattern is clear: **dozens of -stability sources, almost no +stability sources.** The only stability gains are:
- Cultural renaissance event: +10 (rare, probability 0.03)
- Elected succession: +10 (one-time)
- Vassal rebellion success: +10 (one-time)
- Value drift can slightly increase stability in some cases

Meanwhile, stability drains from: drought (-10 + -10/turn), plague (-10 + -10/turn), famine (-10), war costs (-5/turn), governing costs (-1/distance), embargoes (-5), black market (-3/turn), rebellion (-20), border incident (-10), migration (-10), leader death (-20), usurper succession (-30), exile pretender drain (-2/turn), cultural assimilation drain (-3/turn), proxy wars, mercenary pressure...

**M19b's first task will be adding a stability recovery mechanism or dramatically reducing drain rates.**

### High-Impact Tuning Categories

1. **Stability economy** (~40 constants) — drains vs. gains, condition durations
2. **Military maintenance** (~15 constants) — free threshold (30), cost curve, mercenary spawn
3. **Fertility/Famine** (~12 constants) — degradation rate (0.02), recovery rate (0.01), famine threshold (0.3), cooldown (5)
4. **Trade income** (~8 constants) — per-route income (2), self-trade (3), specialization bonuses
5. **Great person generation** (~15 constants) — cooldowns, thresholds, lifespan, catch-up discount
6. **Succession crisis** (~12 constants) — base probability (0.15), modifiers, duration
7. **Action weights** (~50+ constants) — 12 leader traits × 11 action types = 132 weight values
8. **Event probabilities** (~10 constants) — base probabilities for each event type
9. **Climate multipliers** (~24 constants) — 6 terrains × 4 phases

### Tuning YAML Design Implication

The ~250 constants suggest the tuning YAML should be hierarchical:

```yaml
stability:
  drain:
    drought_immediate: -10
    drought_ongoing: -10
    plague_immediate: -10
    ...
  recovery:
    # currently empty — M19b will add these
  thresholds:
    population_growth_min: 20
    population_decline_max: 10
    collapse_asabiya: 0.1
    collapse_stability: 20

military:
  maintenance_free_threshold: 30
  maintenance_cost_divisor: 10
  ...

fertility:
  degradation_rate: 0.02
  recovery_rate: 0.01
  famine_threshold: 0.3
  ...
```

The M19 spec needs to decide whether tuning YAML overrides are hot-patched at runtime (dictionary merge before world gen) or compiled into a `GameConfig` dataclass. Hot-patching is simpler and sufficient for batch runner use.

---

## 3. TurnSnapshot Extension Plan

Minimal changes needed. Here's the exact diff for the spec:

```python
# models.py — add to TurnSnapshot
class TurnSnapshot(BaseModel):
    # ... existing fields ...

    # NEW: M19 analytics fields
    climate_phase: str = ""                           # from get_climate_phase()
    active_conditions: list[dict] = Field(default_factory=list)  # type + severity + duration
    per_civ_income: dict[str, int] = Field(default_factory=dict) # last_income snapshot

    # NEW: M18 fields (add when M18 lands)
    # per_civ_stress: dict[str, float] = Field(default_factory=dict)
    # black_swan_event: str | None = None
    # regressions_active: list[str] = Field(default_factory=list)
```

And in `main.py` snapshot capture (~3 lines):

```python
snapshot = TurnSnapshot(
    # ... existing ...
    climate_phase=get_climate_phase(world.turn, world.climate_config).value,
    active_conditions=[{"type": c.condition_type, "severity": c.severity, "duration": c.duration} for c in world.active_conditions],
    per_civ_income={civ.name: civ.last_income for civ in world.civilizations},
)
```

This is smaller than the design sketch predicted because TurnSnapshot already captures trade_routes, active_wars, embargoes, fertility, movements_summary, and great_persons. The sketch assumed those were missing — they aren't.

---

## 4. Analytics Module Architecture

Confirmed from codebase review: **Option B (post-processing on bundles) is correct.** The bundle format gives us everything:

- **Time-series data:** `history[turn].civ_stats[civ_name].stability` → stability curve per civ per run
- **Event firing rates:** `events_timeline` filtered by `event_type` → count per type per run
- **Distribution data:** aggregate across runs at checkpoint turns → percentiles
- **Elimination timing:** turn where `civ_stats[name]` disappears from history
- **Action diversity:** `world_state.civilizations[i].action_counts` → per-civ histograms

The analytics module needs:
1. **Bundle loader** — reads `chronicle_bundle.json`, returns typed dict
2. **Per-system extractors** — one function per M13-M18 system, returns metric dict
3. **Cross-run aggregator** — takes N metric dicts, computes distributions/percentiles
4. **Anomaly detector** — pattern matchers for known degenerate states
5. **Report formatter** — JSON output + CLI text output

---

## 5. Codebase Health Notes

### Positive Findings
- Clean separation between simulation and presentation
- Deterministic given seed (except LLM calls)
- Events are typed strings with consistent schema
- TurnSnapshot already captures most of what analytics needs
- Bundle format is JSON — no binary parsing needed
- Test suite at 800+ tests provides safety net for tuning changes

### Concerns for M19
- `simulation.py` is 874 lines — largest file, contains phases 1-10. Adding M18 wiring will push it further. Consider extracting phase functions to separate modules during M19b if it crosses 1000 LOC.
- `politics.py` is 1085 lines — already large. Analytics won't touch it, but M19b tuning might.
- No `GameConfig` centralization exists yet — constants are scattered across modules. M19's tuning YAML is the first step toward a centralized config, but it's an override layer, not a replacement.

### Bundle Size Estimate
At 500 turns with 4 civs and 8 regions:
- ~500 TurnSnapshots × ~2KB each = ~1MB for history
- ~2000 events × ~200B each = ~400KB for events_timeline
- Total bundle: ~2-3MB uncompressed JSON per run
- 200 runs = ~400-600MB total disk. Manageable.

---

## 6. Recommended M19 Spec Outline

Based on this review, the M19 spec should cover:

1. **TurnSnapshot extension** (3 new fields, ~15 lines)
2. **`analytics.py` module** — bundle loader, 8 system extractors, aggregator, anomaly detector
3. **`chronicler analyze` CLI command** — reads batch_report.json, prints text report
4. **`batch_report.json` schema** — per-system metrics, percentiles, anomalies
5. **Tuning YAML format** — hierarchical, hot-patched before world gen
6. **`--tuning` flag on batch runner** — applies overrides
7. **`--compare` flag on analyze** — diffs two batch reports
8. **`--simulate-only` integration** — skip narration in batch mode (already exists as flag, may not be wired through batch.py)

Estimated scope: ~400 lines of new code + ~15 lines snapshot extension. No simulation changes.
