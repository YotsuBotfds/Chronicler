# M57 Adjudication (2026-03-27)

## Decision

`REJECT_DIVERGENCE`

M57a is **not** closeable yet under either:

- the current absolute regression rule, or
- the old M54-style control-relative adjudication rule

## Why

Three fresh same-machine `main` controls were rerun with the same full-gate profile:

- `output/m57a_main_control_2026_03_27/full_gate/batch_1/validate_report_full.json`
- `output/m57a_main_control_2026_03_27_run2/full_gate/batch_1/validate_report_full.json`
- `output/m57a_main_control_2026_03_27_run3/full_gate/batch_1/validate_report_full.json`

All three are numerically identical on the regression metrics:

- `satisfaction_mean=0.4171`
- `migration_rate_per_agent_turn=0.098642`
- `rebellion_rate_per_agent_turn=0.069242`
- `gini_in_range_fraction=0.9489`

That confirms the baseline shift is real and reproducible on this machine.

But the M57a candidate at `output/m57a/full_gate/batch_1/validate_report_full.json` is still outside the old M54 control-match tolerance band:

- `delta_satisfaction=+0.0069` vs old tolerance `<= 0.005`
- `delta_migration=-0.005280` vs old tolerance `<= 0.001`
- `delta_rebellion=+0.001083` vs old tolerance `<= 0.001`
- `delta_gini=+0.0141` vs old tolerance `<= 0.005`

Also, both the candidate and the controls have `artifacts PARTIAL`, not `PASS`, so the old "core oracle suite passes" condition is not satisfied either.

## Interpretation

This is the strict answer:

1. M57a did **not** create the absolute floor miss.
2. M57a is **not** automatically acceptable under the previous M54 adjudication standard.
3. So the milestone still needs an explicit project-level closeout decision.

## Recommended next step

Choose one:

1. Define an M57-specific acceptance policy with explicit tolerances and rationale.
2. Retune the current runtime line until M57a returns to an absolute pass.

Until then, treat M57a as:

- implemented
- investigated
- adjudicated against controls
- not yet merged/closed

## Proposed M57 Acceptance Policy

If we want to close M57a without pretending the absolute gate is green, I recommend a narrow milestone-specific policy:

### `ACCEPT_M57_BASELINE_EXCEPTION`

Accept `M57a` if all of these are true:

1. Three fresh same-machine `main` controls, run with the exact canonical profile (`200` seeds, `500` turns, `hybrid`, sidecar, `--parallel 24`), reproduce the same absolute floor miss.
2. The candidate preserves the same oracle status vector as the controls.
   - For the current runtime line, that means:
     - `community PASS`
     - `needs PASS`
     - `era PASS`
     - `cohort PASS`
     - `artifacts PARTIAL`
     - `arcs PASS`
     - `determinism SKIP`
     - `regression FAIL`
3. `occupation_ok` remains `true`.
4. `satisfaction_mean` is not worse than the control mean.
5. `rebellion_rate_per_agent_turn` does not worsen by more than `+0.002`.
6. `migration_rate_per_agent_turn` does not worsen by more than `+0.003`; any improvement is allowed.
7. `gini_in_range_fraction` does not worsen by more than `-0.010`; any improvement is allowed.
8. Probe evidence shows the milestone's new systems are not the primary source of the floor miss.

### Why this policy is reasonable

- It does **not** loosen the absolute rule globally.
- It requires preserved same-machine evidence, not intuition.
- It is directional: improvements are allowed, bounded regressions are not.
- It acknowledges that M57a changes social and demographic structure more than the narrower M54 migration did.

## Evaluation Against The Proposed Policy

M57a would qualify under the proposed policy:

- controls: three fresh same-machine `main` runs reproduced the floor miss identically
- oracle vector: candidate matches controls exactly
- `occupation_ok=true`
- `satisfaction_mean`: `0.4240` vs control mean `0.4171` -> passes
- `rebellion delta`: `+0.001083` -> within `+0.002`
- `migration delta`: `-0.005280` -> improvement
- `gini delta`: `+0.0141` -> improvement
- probes: marriage disablement and stale-slot memory rollback both made the shape worse

So the policy decision becomes explicit:

- under current and old rules: `REJECT_DIVERGENCE`
- under the proposed M57-specific exception: `ACCEPT_M57_BASELINE_EXCEPTION`
