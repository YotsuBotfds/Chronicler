# M19b Post-M24 Tuning Pass — Cici Session Prompt

> Copy this prompt into a fresh Cici session after M24 (Information Asymmetry) lands.
> This is the third M19b pass. The first pass (pre-M21) fixed the stability death spiral. The second pass (post-M22) tuned factions and left 6 criteria deferred. This pass validates M23 (Coupled Ecology) and M24 (Information Asymmetry) integration, addresses the deferred items, and tunes the new systems.

---

You are running the third M19b tuning pass for Chronicler. M23 (Coupled Ecology) and M24 (Information Asymmetry) have both landed. This pass has three goals:

1. Validate M23 ecology and M24 perception produce healthy distributions
2. Address the 6 deferred criteria from the post-M22 pass (focus scoring, weight base, pop@500)
3. Tune all systems together to exit-criteria convergence

## Context

**Second M19b pass results (post-M22, for comparison):**
- 10 of 19 criteria passed
- 6 criteria deferred: #6, #7, #9 (focus scoring rebalance), #15 (pop@500 — blocked on M23), #17, #19 (weight base value)
- 3 criteria marginally failing: #12 (power struggle 44%, target ≤40%), #14 (faction-succession 58%, target ≥70%)
- Power struggle thresholds tuned: gap 0.05→0.15, floor 0.30→0.40, cooldown 10 turns
- All influence shifts halved; normalization floor 0.05→0.10
- Succession resolution shift applied as raw post-normalization (+0.20)

**What M23 added (Coupled Ecology):**
- Three ecology variables per region: `soil` (0.0–1.0), `water` (0.0–1.0), `forest_cover` (0.0–1.0)
- Replaces single `fertility` float throughout
- `effective_capacity(region) = carrying_capacity × soil × water_factor` (where `water_factor = min(1.0, water / 0.5)`)
- Pressure-gated recovery: `multiplier = max(0.1, 1.0 - pop / effective_capacity)`
- Terrain-specific defaults and ceilings for 6 terrain types
- Famine trigger changed: `water < 0.20` (was `fertility < threshold`)
- Three named feedback loops: deforestation spiral, irrigation trap, mining collapse
- M21 integration: AGRICULTURE +0.02/turn soil, METALLURGY halves mine damage, MECHANIZATION doubles mine damage
- M18 terrain succession: deforestation at `forest_cover < 0.2`, rewilding at `forest_cover > 0.7`
- 13 tuning keys via `get_override()` (soil_degradation_rate, water_drought_rate, etc.)

**What M24 added (Information Asymmetry):**
- Perception system: `compute_accuracy(observer, target, world)` → 0.0–1.0
- Accuracy sources: adjacent (+0.3), trade (+0.2), federation (+0.4), vassal (+0.5), war (+0.3), merchant faction (+0.1), cultural faction (+0.05), merchant GP (+0.05), hostage (+0.3), grudge (+0.1)
- `get_perceived_stat()`: actual + Gaussian noise, σ = noise_range/2, noise_range = (1-accuracy) × 20
- 6 callsites: WAR target bias (perceived military), trade gains (perceived economy), tribute (perceived vassal economy), rebellion (perceived overlord strength), congress power ranking (organizer perception), intelligence failure events
- 2 new snapshot fields: `per_pair_accuracy`, `perception_errors`
- New event type: `intelligence_failure`

## Exit Criteria (all must pass simultaneously)

### Section A: Regression Checks (preserved from passes 1 & 2)

1. **Stability median > 30 at turn 100** (pass 1: 35, pass 2: 50)
2. **Stability σ > 15 at turn 100** (pass 1: ~22, pass 2: 18.8)
3. **Every M14-M18 mechanic fires in ≥ 10% of 200 runs**
4. **No degenerate 100% negative event pattern** (famine at 100% over 500 turns is expected; look for early-game 100% patterns like universal famine before turn 50)
5. **3+ tech eras at turn 500** (pass 2: 8 distinct)
8. **Action entropy ≥ 1.5 bits** per civ per era median (pass 2: 1.50)
10. **Faction dominance @ turn 100 < 50%** for any single faction type (pass 2: merchant 46%, cultural 47%)
11. **Faction dominance @ turn 500: ≥ 2 types each ≥ 20%** (pass 2: merchant 44%, cultural 53%)
13. **Power struggle resolution balance < 60%** for any single faction type (pass 2: cultural 49%)
16. **New event types ≥ 15%** — `power_struggle_started`, `power_struggle_resolved` each ≥ 15%; `faction_dominance_shift` ≥ 30% of 200 runs
18. **Merchant dominance ≤ 50% at turn 500** (pass 2: 44%)

### Section B: Previously Deferred — Now Unblocked

**Focus scoring (unblocked by focus scoring rebalance — code change required before tuning):**

6. **Focus distribution per era:** Each of the 3 focuses per era is selected by ≥ 15% of civs reaching that era. No single focus > 60% in any era. (Pass 2: agriculture 91% classical — monoculture.)
7. **Focus-geography correlation:** Coastal civs select NAVIGATION at ≥ 2× landlocked rate. Mountain/iron civs select METALLURGY at ≥ 2× plains rate. (Pass 2: both at 0–1%.)
9. **Focus capability firing:** Each unique capability fires in ≥ 5% of runs where a civ holds that focus for 20+ turns. (Pass 2: 4/15 capabilities dead due to monoculture.)

**Weight stacking (unblocked by weight base value change — code change required before tuning):**

17. **Weight cap fires 5–50%** of calculations; median pre-cap weight < 3.5×. (Pass 2: 0.1% fire rate on base=0.2.)
19. **Action persistence < 80%** — no civ maintains same top action for > 80% of turns in any 100-turn window. (Pass 2: 15% of civs locked — acceptable only because cap was inert.)

**Population (unblocked by M23 ecology):**

15. **Median civ population at turn 500 ≥ 12.** No more than 10% of surviving civs with total effective capacity < 10. (Pass 2: median 3 — famine system was broken.)

### Section C: M23 Coupled Ecology Validation

20. **Famine frequency per 500 turns:** Higher variance than pre-M23 baseline. Mean famines per run should be between 5 and 30 (too few = water threshold too high; too many = threshold too low or recovery too slow).
21. **Migration cascade length:** Mean cascade length ≥ 2.0 (at least some multi-hop migrations triggered by ecology collapse). Max observed cascade ≥ 4.
22. **Ecology variable distributions at turn 500:** Each of soil, water, forest_cover should show bimodal or wide distribution across regions — not all clustered at defaults. σ > 0.10 for each.
23. **Feedback loop convergence:** Each of the three named loops (deforestation spiral, irrigation trap, mining collapse) should terminate within 100 turns of onset. No perpetual runaway degradation.
24. **Terrain transition frequency:** Both deforestation (`forest → plains/desert`) and rewilding (`plains → forest`) occur in ≥ 5% of 200 runs each.
25. **Faction power struggle from ecology events:** Ecology-triggered events (famine, deforestation) cause at least 1 power struggle per 500 turns in ≥ 10% of runs.
26. **Effective capacity correlation:** Regions with soil > 0.7 AND water > 0.5 should have effective_capacity within 20% of carrying_capacity. Regions with soil < 0.3 OR water < 0.2 should have effective_capacity < 50% of carrying_capacity.

### Section D: M24 Information Asymmetry Validation

27. **Accuracy distribution at turn 250:** Mean per-pair accuracy across all known pairs should be 0.3–0.6. At least 10% of pairs should have accuracy ≥ 0.7 (allies/vassals). At least 20% should have accuracy ≤ 0.3 (distant strangers).
28. **Perception error sign balance:** Across all (observer, target, stat) triples at turn 250, the ratio of overestimates to underestimates should be between 0.4 and 0.6 (Gaussian noise is symmetric — significant skew indicates a bug).
29. **Intelligence failure event frequency:** `intelligence_failure` events fire in ≥ 5% of 200 runs by turn 500. (Too few = threshold too tight or accuracy too high; too many = accuracy too low.)
30. **War frequency stability:** Total wars per 500 turns should be within ±15% of pre-M24 baseline. Perception noise should create occasional mistaken wars but not dramatically increase or decrease war frequency.
31. **WAR target bias effect:** Among wars where attacker had 2+ hostile neighbors, the target selected should have lower perceived military than the non-selected target in ≥ 60% of cases.
32. **Trade gain variance:** Standard deviation of trade gains per event should be higher post-M24 than pre-M24 baseline (perception noise adds variance). But mean trade gain should be within ±10% of baseline.

### Section E: Combined System Interactions

33. **Ecology × perception:** Civs with low accuracy toward a neighbor should sometimes fail to anticipate ecology-driven migration into their territory. Check: migration events where the receiving civ has accuracy < 0.3 toward the source civ occur in ≥ 5% of runs.
34. **M21 focus × M23 ecology:** AGRICULTURE focus civs should have higher mean soil at turn 500 than non-AGRICULTURE civs (the +0.02/turn bonus should be measurable). MECHANIZATION focus civs with mines should have lower mean soil (the ×2.0 mine degradation should be visible).
12. **Power struggle frequency 15–40% per-civ** (pass 2: 44% — retune with M23/M24 context; ecology events and perception noise may shift this).
14. **Faction-succession correlation ≥ 70%** (pass 2: 58% — retune with updated succession resolution shift).

## Process

**Pre-Step: Code Changes Required**

Before running any batches, two code changes from the deferred list must land:

1. **Focus scoring rebalance** (`tech_focus.py`) — Widen terrain/state differentiation in scoring helpers so minority focuses get selected. Agriculture should not be 91% in classical. Propose changes and flag for Tate before implementing.

2. **Weight base value** (`action_engine.py` `compute_weights()`) — Change base from 0.2 to 1.0 (or lower the 2.5× cap proportionally). This makes the cap reachable and prevents single-action lock-in. Flag for Tate before implementing.

**Step 1: Pre-M23/M24 baseline.**

Run a 200-run batch on the current codebase (post-M23, post-M24, pre-tuning) to establish the new baseline:

```bash
chronicler --seed-range 1-200 --turns 500 --simulate-only --output output.md --state state.json --parallel 30
chronicler --analyze ./batch_1 --checkpoints 25,50,100,200,500
```

Save as `m19b_post_m24_baseline.json`.

**Parallelism:** Tate's machine is a 9950X — use `--parallel 30` on all batch runs.

**Step 2: Read analytics report.** For each of the 34 exit criteria, report the metric value and pass/fail. Present as a summary table. Flag regressions from pass 2.

**Step 3: New analytics queries.** Before running the first batch, verify the analytics module can compute all new criteria. You will likely need to add:

- `extract_ecology_distributions` — soil/water/forest σ at checkpoints (criteria 22, 26)
- `extract_famine_frequency` — famine count per run, variance (criterion 20)
- `extract_migration_cascades` — cascade length distribution (criterion 21)
- `extract_feedback_loop_convergence` — onset-to-recovery duration for each loop type (criterion 23)
- `extract_terrain_transitions` — deforestation and rewilding event counts (criterion 24)
- `extract_ecology_faction_interaction` — ecology events → power struggle causation (criterion 25)
- `extract_accuracy_distribution` — per-pair accuracy stats at checkpoints (criterion 27)
- `extract_perception_error_balance` — over/underestimate ratio (criterion 28)
- `extract_intelligence_failures` — event frequency (criterion 29)
- `extract_war_frequency` — total wars per run for baseline comparison (criterion 30)
- `extract_war_target_bias` — perceived military comparison for chosen vs unchosen targets (criterion 31)
- `extract_trade_variance` — trade gain σ and mean (criterion 32)
- `extract_ecology_perception_interaction` — migration with low-accuracy pairs (criterion 33)
- `extract_focus_ecology_correlation` — soil/water by focus type (criterion 34)

If any require new data in CivSnapshot or events_timeline beyond what M23 and M24 already populate, flag it.

**Step 4: Apply code changes.** Implement the focus scoring rebalance and weight base value change (from Pre-Step). Run a fresh batch to measure their impact before any constant tuning.

**🚩 FLAG FOR TATE** before applying either code change. Present proposed changes as diffs.

**Step 5: Propose tuning adjustments.** For each failing criterion, propose constant changes. Priority order:
1. Fix regressions from pass 2 first
2. Tune M23 ecology constants (13 keys in ecology.py)
3. Tune M24 perception constants (accuracy source weights, noise scaling)
4. Re-tune M22 faction constants if M23/M24 shifted the equilibrium
5. Combined interaction issues last

**🚩 FLAG FOR TATE** before applying any tuning.yaml. Present changes as a table.

**Steps 6–9:** Same iteration loop — run tuned batch, compare, adjust, iterate. Max 2–3 constants per iteration.

**🚩 FLAG FOR TATE** if:
- Fixing an ecology criterion breaks a stability criterion
- War frequency shifts by > 15% from pre-M24 baseline (perception noise too aggressive)
- Focus scoring rebalance creates a new monoculture (swaps agriculture dominance for another)
- Weight base change causes action entropy to drop below 1.5 bits
- Ecology feedback loops don't converge within 100 turns (runaway degradation)
- Perception accuracy mean is < 0.2 or > 0.7 (system is either blind or omniscient)
- Power struggle frequency per-civ is < 10% or > 50%
- You've done 5+ iterations without convergence
- Any ecology tuning key needs to go outside its terrain-specific bounds

**Step 10: Bake and verify.** Bake final values into defaults, run without --tuning, confirm all 34 criteria.

**Step 11: Write report.** Save as `docs/superpowers/analytics/m19b-post-m24-tuning-report.md`. Include:
- Baseline vs final for all 34 exit criteria
- Constants changed (with before/after values) — separated by module
- Code changes made (focus scoring, weight base) with rationale
- New analytics functions added
- Interaction effects observed
- Ecology feedback loop behavior summary
- Perception system behavioral summary (how often does bad intel cause wars? how often does deterrence from overestimation prevent wars?)
- Regressions from pass 2 (if any) and how they were resolved

## Available Tuning Constants

### From Pass 2 (may need re-tuning)
All stability drain constants (`K_DROUGHT_STABILITY`, `K_WAR_COST_STABILITY`, etc.), stability recovery (+20/turn), and all M22 faction constants (influence shifts, power struggle thresholds, normalization floor). See the post-M22 prompt for the full list.

### M23 Ecology Constants (ecology.py)
| Key | Default | Controls |
|-----|---------|----------|
| `ecology.soil_degradation_rate` | 0.005 | Soil loss per turn from overpopulation |
| `ecology.soil_recovery_rate` | 0.05 | Soil recovery per turn (× pressure multiplier) |
| `ecology.mine_soil_degradation_rate` | 0.03 | Soil loss per turn from mines |
| `ecology.water_drought_rate` | 0.04 | Water loss per turn during drought |
| `ecology.water_recovery_rate` | 0.03 | Water recovery per turn in temperate |
| `ecology.forest_clearing_rate` | 0.02 | Forest loss per turn from pop pressure |
| `ecology.forest_regrowth_rate` | 0.01 | Forest recovery per turn (natural) |
| `ecology.cooling_forest_damage_rate` | 0.01 | Forest loss from cooling climate |
| `ecology.irrigation_water_bonus` | 0.03 | Extra water recovery from irrigation |
| `ecology.irrigation_drought_multiplier` | 1.5 | Extra water loss for irrigated during drought |
| `ecology.agriculture_soil_bonus` | 0.02 | Soil recovery bonus from AGRICULTURE focus |
| `ecology.mechanization_mine_multiplier` | 2.0 | Mine damage multiplier with MECHANIZATION |
| `ecology.famine_water_threshold` | 0.20 | Water level below which famine triggers |

### M24 Perception Constants (intelligence.py)

These are currently hardcoded in `compute_accuracy()`. If tuning is needed, extract to `get_override()` calls:

| Constant | Default | Controls |
|----------|---------|----------|
| Adjacent bonus | 0.3 | Accuracy from sharing a border |
| Trade route bonus | 0.2 | Accuracy from active trade |
| Federation bonus | 0.4 | Accuracy from same federation |
| Vassal/overlord bonus | 0.5 | Accuracy from vassal relationship |
| War bonus | 0.3 | Accuracy from active conflict |
| Merchant faction bonus | 0.1 | Accuracy from merchant dominance |
| Cultural faction bonus | 0.05 | Accuracy from cultural dominance |
| Merchant GP bonus | 0.05 | Accuracy from merchant great person |
| Hostage bonus | 0.3 | Accuracy from holding a hostage |
| Grudge bonus | 0.1 | Accuracy from grudge intensity > 0.3 |
| Noise scaling factor | 20 | `noise_range = (1 - accuracy) × 20` |
| Intel failure threshold | 0.7 | `perceived_mil ≤ 0.7 × actual_mil` triggers event |
| `max_value` (per-callsite) | 100 / 500 | Upper clamp for perceived values (100 for stats, 500 for treasury at rebellion callsite) |

**Note:** `get_perceived_stat` uses SHA-256 hashing for deterministic RNG seeding (`f"{seed}:{observer}:{target}:{turn}:{stat}"`), not Python's `hash()`. This ensures cross-process determinism regardless of `PYTHONHASHSEED`.

### M21 Constants (tech_focus.py)
Focus stat modifier magnitudes, focus weight modifier values, scoring helper weights, GP/tradition bonuses, 2.5× weight cap. (See post-M22 prompt for details.)

### M22 Constants (factions.py, succession.py, politics.py)
All influence shift magnitudes, normalization floor (0.10), power struggle thresholds (gap 0.15, floor 0.40), cooldown (10 turns), resolution shifts (+0.35 normalized / +0.20 raw). (See post-M22 prompt for full table.)

## Important Notes

- All analytics should read from `chronicle_bundle.json` / CivSnapshot data — NOT import from simulation modules.
- M23 ecology variables are in `CivSnapshot` via region snapshots. The three ecology variables (soil, water, forest_cover) should appear in region data within each snapshot.
- M24 snapshot fields: `per_pair_accuracy` and `perception_errors` are top-level on TurnSnapshot.
- The `intelligence_failure` event type should appear in `events_timeline`. If it doesn't appear at all in 200 runs, the callsite wiring may be broken — check `action_engine.py` war resolution.
- Focus scoring rebalance is the highest-leverage code change. It unblocks 3 criteria and improves the narrative quality of simulations (less monoculture = more interesting histories).
- Weight base change is the second-highest-leverage code change. It makes the weight cap functional, which is the primary mechanism for preventing action lock-in.
- M23 ecology tuning is sensitive — small changes to degradation/recovery rates compound over 500 turns. Prefer 10–20% adjustments per iteration.
- M24 perception constants are less sensitive — accuracy is capped at 1.0, and noise is Gaussian with bounded range. Larger adjustments (±50%) are safe for accuracy source weights.
- When comparing pre-M24 and post-M24 war frequency, run the pre-M24 baseline from the commit just before M24 landed (or use the pass 2 baseline if available).
- CivSnapshot should now include `ecology` (M23) and `per_pair_accuracy` / `perception_errors` (M24) in addition to `active_focus` (M21) and `factions` (M22). If any are missing, that's a bug — flag it.
