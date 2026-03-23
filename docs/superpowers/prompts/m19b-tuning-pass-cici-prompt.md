# M19b Tuning Pass — Cici Session Prompt

> Copy this prompt into a fresh Cici session to run the M19b tuning pass.

---

You are running the M19b tuning pass for Chronicler. This is iterative constant adjustment using M19's analytics tooling — no new code, only YAML overrides and GameConfig updates.

## Goal

Adjust simulation constants until the exit criteria pass, then bake final values into the codebase.

## Exit Criteria (all must pass simultaneously)

1. Stability distribution at turn 100: median > 30, σ > 15
2. Every M14-M18 mechanic fires in at least 10% of 200 runs
3. No degenerate pattern (100% occurrence of any negative event type)
4. 3+ different tech eras represented at turn 500 across 200 runs
5. No never-fire anomalies for mechanics that should be reachable

## Process

**Step 1:** Run baseline.
```bash
chronicler --seed-range 1-200 --turns 500 --simulate-only --output output.md --state state.json
chronicler --analyze ./batch_1 --checkpoints 25,50,100,200,500
```
Save `batch_report.json` as `baseline_report.json`.

**Step 2:** Read the analytics report. List every anomaly, every never-fire, and every metric that fails exit criteria. Present this as a summary table to Tate.

**Step 3:** Propose a `tuning.yaml` with adjustments. For each change, state:
- Which constant you're changing and from what default to what value
- Which anomaly or exit criterion it targets
- What side effects you expect (e.g., "raising stability recovery may reduce secession rate")

**🚩 FLAG FOR TATE** before applying any tuning.yaml. Present the proposed changes as a table and wait for approval. Tate may veto or adjust individual values.

**Step 4:** Run tuned batch and compare.
```bash
chronicler --seed-range 1-200 --turns 500 --simulate-only --tuning tuning.yaml --output output.md --state state.json
chronicler --analyze ./batch_2 --compare baseline_report.json --checkpoints 25,50,100,200,500
```

**Step 5:** Read the delta report. For each metric, note whether it improved, degraded, or stayed flat. If any exit criterion regressed, identify which constant change caused it.

**Step 6:** If exit criteria not met, adjust `tuning.yaml` and repeat from Step 4. Each iteration should change at most 2-3 constants — don't shotgun.

**🚩 FLAG FOR TATE** if:
- Two constants conflict (fixing one metric breaks another)
- A mechanic never fires and you can't fix it with tuning alone (may need code changes)
- You've done 5+ iterations without convergence
- Any proposed change exceeds 3x the default value (extreme adjustment)

**Step 7:** Once all exit criteria pass, bake the final tuned values into `GameConfig` or the relevant simulation defaults. Remove the `tuning.yaml` dependency — the tuned values become the new defaults.

**Step 8:** Run one final baseline with the baked constants (no `--tuning` flag) to confirm the exit criteria still pass without YAML overrides.

**Step 9:** Commit the before/after analytics comparison as `docs/superpowers/analytics/m19b-tuning-report.md`. Include: baseline metrics, final metrics, constants changed, iterations taken.

## Known Issues to Expect

- Stability is likely near 0 by turn 50 in baseline — this is the primary problem
- Famine probably fires in 99%+ of runs — fertility/recovery balance is off
- Mercenary spawn may be 100% — military maintenance vs income curves
- Hostage exchange may never fire — eligibility too restrictive
- Federation formation may be very low — alliance threshold too high

## Available Tuning Constants (from `tuning.py` KNOWN_OVERRIDES)

- `K_DROUGHT_STABILITY` — immediate stability drain from drought
- `K_DROUGHT_ONGOING` — per-turn ongoing drought drain
- `K_PLAGUE_STABILITY` — immediate stability drain from plague
- `K_FAMINE_STABILITY` — stability drain from famine
- `K_WAR_COST_STABILITY` — stability drain when treasury hits 0 during war
- `K_GOVERNING_COST` — per-distance governing stability cost
- `K_CONDITION_ONGOING_DRAIN` — per-turn drain from active conditions (severity >= 50)
- `K_FERTILITY_DEGRADATION` — per-turn fertility degradation rate
- `K_FERTILITY_RECOVERY` — per-turn fertility recovery rate
- `K_FAMINE_THRESHOLD` — fertility threshold below which famine triggers
- `K_MILITARY_FREE_THRESHOLD` — military units before maintenance costs kick in
- `K_BLACK_SWAN_BASE_PROB` — base probability of black swan events
- `K_BLACK_SWAN_COOLDOWN` — turns between eligible black swan events

**If you need constants that aren't in KNOWN_OVERRIDES**, flag for Tate — that means adding new tunable hooks, which is a small code change outside M19b scope.
