# M57 Regression Investigation (2026-03-27)

## Decision

`HOLD_ABSOLUTE_GATE_FAIL_BASELINE_SHIFT_CONFIRMED`

M57a should **not** be called merged/closed under the current rule, because the absolute regression gate still fails. But the investigation also shows that the failure is **not** an M57a-specific regression relative to today's `main` runtime line.

## Inputs

- Candidate:
  - `output/m57a/full_gate/batch_1/validate_report_full.json`
- Fresh same-machine `main` control:
  - `output/m57a_main_control_2026_03_27/full_gate/batch_1/validate_report_full.json`
- Supporting probes:
  - `output/m57a_probe_match_fix/full_gate/batch_1/validate_report_full.json`
  - `output/m57a_probe_no_marriage_seq/full_gate/batch_1/validate_report_full.json`
  - `output/m57a_probe_no_marriage_old_memory/full_gate/batch_1/validate_report_full.json`
  - `output/m57a_probe_parent0_dynasty/full_gate/batch_1/validate_report_full.json`
  - `output/m57a_probe_social_fix/full_gate/batch_1/validate_report_full.json`

## Core Result

Both runs have the same oracle shape:

- `community PASS`
- `needs PASS`
- `era PASS`
- `cohort PASS`
- `artifacts PARTIAL`
- `arcs PASS`
- `determinism SKIP`
- `regression FAIL`

The failure is the same absolute floor in both cases: `satisfaction_mean >= 0.45`.

## 200-Seed Comparison

### Candidate (M57a)

- `satisfaction_mean=0.4240`
- `satisfaction_std=0.1393`
- `migration_rate_per_agent_turn=0.093362`
- `rebellion_rate_per_agent_turn=0.070325`
- `gini_in_range_fraction=0.9630`
- `occupation_ok=true`

### Fresh same-machine `main` control

- `satisfaction_mean=0.4171`
- `satisfaction_std=0.1468`
- `migration_rate_per_agent_turn=0.098642`
- `rebellion_rate_per_agent_turn=0.069242`
- `gini_in_range_fraction=0.9489`
- `occupation_ok=true`

### Candidate delta vs fresh `main`

- `satisfaction_mean=+0.0069`
- `satisfaction_std=-0.0075`
- `migration_rate_per_agent_turn=-0.005280`
- `rebellion_rate_per_agent_turn=+0.001083`
- `gini_in_range_fraction=+0.0141`

Interpretation:

- The absolute floor miss predates M57a on the current runtime line.
- M57a is **better** than fresh `main` on satisfaction.
- M57a also lowers migration and improves Gini coverage.
- M57a slightly raises rebellion versus fresh `main`.

So the investigation rules out the simple claim that "M57a introduced the satisfaction dip." It did not.

## Probe Findings

### Marriage formation is not the primary culprit

- The original marriage scoring had a real saturation issue, and a threshold/closeness probe reduced marriage incidence.
- That probe did **not** recover the regression materially.

### Removing marriage makes the shape worse

- No-marriage probe:
  - `satisfaction_mean=0.4238`
  - `migration_rate_per_agent_turn=0.102246`
  - `rebellion_rate_per_agent_turn=0.077943`
- This is worse than the live M57a branch.

Conclusion: marriage formation is currently a net positive offset, not the root cause.

### Reverting stale-slot memory validation makes the shape worse

- Old-memory probe:
  - `satisfaction_mean=0.4060`
  - `migration_rate_per_agent_turn=0.102424`
  - `rebellion_rate_per_agent_turn=0.077836`

Conclusion: `MemoryIntent.expected_agent_id` is also a net positive correction, not the source of the dip.

### Second-parent dynasty/succession widening is not the key driver

- Parent-0-only dynasty/succession probe stayed effectively identical to the live 50-seed M57a shape.

Conclusion: the always-on political widening is not where the regression miss is coming from.

## Conclusion

The investigation is complete enough to support a process decision:

1. Do **not** call M57a fully closed under the current absolute rule.
2. Do **not** keep rolling back M57a features in search of the floor miss.
3. Treat the remaining issue as a milestone closeout policy question:
   - either define an M57 control-relative adjudication rule against preserved same-machine controls,
   - or retune the current runtime line until the absolute floor passes again.

M57b spec work can proceed in parallel, but M57a merge/closeout should wait for that adjudication decision.

See also: `docs/superpowers/analytics/m57-adjudication-2026-03-27.md` for the stricter three-control closeout check.
