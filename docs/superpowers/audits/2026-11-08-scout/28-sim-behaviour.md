## 28 Simulation behaviour and performance
**Map**
- Aggregate runs (`chronicler --simulate-only`, no `--agents`) drive `run_turn_result` (`src/chronicler/simulation.py:1891`), 150 turns, 10-phase loop; `phase_consequences` (`simulation.py:1185`) and `tick_governance` (`governance_runtime.py:1522`) are the heaviest per-turn pieces.
- Event types come from `events.py` (`ENVIRONMENT_EVENTS` :47, `RANDOM_EVENT_TYPES` :50, `EVENT_CASCADE_RULES` :61, `_DRIVERS` :601), feature modules, and string-built names (`capability_*`, `*_ended`). Named events are a separate list (`named_events.py`, `models.py:767`).
- Output: bundle `history` is delta-encoded (`bundle_codec.py:235-335`); `decode_bundle` is needed before reading per-turn stats.
- `--epidemiology`, `--finance`, `--diplomacy` default **on** for new worlds (`main.py:2164-2174`), so "experimental" switches were a no-op. `--health-care`, `--war-consequences` and `--public-health` refuse without `--agents hybrid` (`expansion_features.py:101`).
- Runs: seeds 42, 7, 1234 (5 civs, 14 regions, 150 turns), one default-on ablation (`--no-epidemiology --no-finance --no-diplomacy`). Work dir: `scratchpad/scout/work-28/`.

**Findings**
1. [med] fragile — Simulate-only runs write final state relative to cwd. My first run created `output/` (3 files, gitignored, 22:07) despite the read-only brief; I did not delete it. Action: owner deletes it; make `--state` default to the `--output` directory.
2. [med] dead-code — `gini` is always 0 in aggregate mode (0 of 3,565 civ-turns non-zero). Field default `models.py:1387`; only the agent bridge sets it (`agent_bridge.py:1406`, `:1460`). Action: compute an aggregate inequality measure or mark the field n/a.
3. [med] sim-depth — Culture pins at the 100 cap for 73–84% of civ-turns (`simulation.py:1039, 1049, 1057, 1653`; `succession.py:273`). Economy sits at 100 for 24–48%, asabiya at 1.0 for 20–31%. Saturated stats hide differences. Action: diminishing returns or decay near the cap.
4. [med] sim-depth — Military is 0 for 39–68% of civ-turns, max 50–70. Wars are 10–27 per run, median 5–11 turns, yet most civs field no army. Action: tie mustering and attrition to the war state.
5. [med] sim-depth — Famine is background noise: 77–95 starts per run (~0.5–0.6/turn), median 5 turns, max 20–55. Zero famine named events in all runs. Action: promote persistent famines to named events and audit the trigger rate (`ecology.py:263`).
6. [med] sim-depth — Named events are monotonous: `propaganda_campaign` is 34–42% of named events (203/543, 151/363, 165/486). Action: audit the named-event generator for dominance.
7. [med] perf — Profiled run 16.6 s; `run_turn_result` 10.3 s cumulative (~68 ms/turn under cProfile). About 31k `random.Random(stable_hash_int(...))` constructions per run (`intelligence.py:190` 12k calls; `epidemiology.py:297` 6k; `simulation.py:887` 5.5k), about 0.34 s in `Random.__init__`.
8. [med] perf — Bundle encode+write ~2.2 s cumulative: `bundle_codec._diff_dict` ~1.0 s with 479k `same()` calls, `write_bundle` 1.2 s including fsync. Import ~1.8 s, mostly pydantic class construction (344 classes, 1.5 s). Pydantic `__setattr__` 355k calls, 0.7 s.
9. [low] dead-code — `sandstorm` is named only in `analytics.py:364` and `historiography.py:173`; no emitter found. Other never-fired types have emitters gated by features or agents, e.g. `loyalty_flip` (`agent_bridge.py:91`), `locust_swarm` (`emergence.py:913`), `first_contact` (`exploration.py:172`), `martyrdom` (`traditions.py:233`), `dynasty_founded` (`dynasties.py:91`). Gating is unverified.
10. [low] sim-depth — War share of actions is only 0.6–1.5% (`war` 70–217 out of 10.9k–14.7k picks). Develop, invest_culture, trade and diplomacy dominate.
11. [low] test-gap — Ablation (epidemiology, finance, diplomacy off): epidemic and quarantine go to 0 (vs 62 and 66), treaties 19 vs 52 named, treasury max 4275 vs 1434. The three default-on systems carry most of the event volume and cut hoards roughly 3x. The ablation confirms they are live, not decorative.
12. [low] sim-depth — `chronicle_entries` have empty `narrative` in simulate-only mode, so narrative quality cannot be judged from these runs.

**Simulation depth**
- Replace hard caps with saturating curves for culture, economy and asabiya so differences survive long runs.
- Give military a stock tied to wars, with attrition and mustering, so a 0 means something.
- Make famine a tracked episode (start, peak, recovery) with named-event output and a trigger-rate audit.
- Rebalance the named-event generator so propaganda does not dominate.

**Event coverage (approximate).** Literal scan finds 177 `event_type` references; 167 fired in at least one run. The 82 never-fired names are inflated by named-event types and string-built names (e.g. `capability_metallurgy` fired 63 times but is not a literal). Only `sandstorm` looks fully unused.

**Confidence** — Verified: four runs (seeds 42, 7, 1234 plus ablation), decoded via `decode_bundle`, with stat ranges, cap fractions and event counts computed from the bundles; profile from `prof.out`. Wall times: 4.4–6.1 s per 150-turn run after warm-up (first cold run 8.2 s), 16.6 s under cProfile. Inferred: gating of never-fired event emitters, and whether the 0.6/turn famine rate is intended.

**Streamlining candidates**

| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| `sandstorm` in `analytics.py:364`, `historiography.py:173` | delete entries | 1–2 | grep found no emitter; check `tests/` before deleting | low |
| `Civilization.gini` (`models.py:1387`) and aggregate gini paths | rewrite or merge (agent-only field) | ~10 | Old bundles and `validation_regression.py:98` read `gini`; keep the field for bundle compatibility | med |
| Hashed per-draw `random.Random(stable_hash_int(...))` sites (`simulation.py:216, 906, 955, 1005`, `techniques.py:209`, `epidemiology.py:297`) | extract one helper | ~20 | RNG streams are determinism-pinned; a refactor must reproduce the same hash inputs exactly; check pins | high |
| `bundle_codec._diff_dict` / `same()` | rewrite for speed | ~0 (perf) | Encoded layout must stay byte-identical for version-6 files | med |
