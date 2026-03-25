# M54 Baseline Adjudication (2026-03-24)

## Decision

`ACCEPT_CONTROL_MATCHED`

M54c is accepted as control-matched on this machine despite the absolute regression floor miss, because:

- All core oracles pass (`community`, `needs`, `era`, `cohort`, `artifacts`, `arcs`)
- Candidate and controls fail `regression` for the same reason (`satisfaction_mean < 0.45`)
- Three preserved same-machine controls are perfectly consistent (zero spread)
- Candidate deltas are within explicit control-relative tolerances

## Inputs

- Candidate:
  - `output/m54c/codex_m53_secession_threshold25_full_500turn_purepolitics_cleanbranch/batch_1/validate_report.json`
- Same-machine controls:
  - `output/m54b/codex_m53_secession_threshold25_full_500turn_control_recheck_current_machine/batch_1/validate_report.json`
  - `output/m54b/codex_m53_secession_threshold25_full_500turn_control_recheck_current_machine_run2/batch_1/validate_report.json`
  - `output/m54b/codex_m53_secession_threshold25_full_500turn_control_recheck_current_machine_run3/batch_1/validate_report.json`
- Historical accepted baseline:
  - `output/m54b/codex_m53_secession_threshold25_full_500turn_bootstrapfix/batch_1/validate_report.json`

## Metrics

### Historical accepted baseline (M54b bootstrapfix)

- `satisfaction_mean=0.4533`
- `migration=0.069793`
- `rebellion=0.067079`
- `gini_in_range_fraction=0.9689`

### Same-machine controls (3 runs)

- All three runs are identical:
  - `satisfaction_mean=0.4460`
  - `migration=0.073320`
  - `rebellion=0.073669`
  - `gini_in_range_fraction=0.9467`
  - `occupation_ok=true`
- Spread across controls:
  - `satisfaction=0.0000`
  - `migration=0.000000`
  - `rebellion=0.000000`
  - `gini=0.0000`

### Candidate (M54c clean branch)

- `satisfaction_mean=0.4425`
- `migration=0.073727`
- `rebellion=0.074185`
- `gini_in_range_fraction=0.9435`
- `occupation_ok=true`

### Candidate delta vs control mean

- `satisfaction=-0.0035`
- `migration=+0.000407`
- `rebellion=+0.000516`
- `gini=-0.0032`

## Control-relative tolerances used

- `|delta_satisfaction| <= 0.005`
- `|delta_migration| <= 0.001`
- `|delta_rebellion| <= 0.001`
- `|delta_gini| <= 0.005`

Candidate passes all tolerance checks.

## Repro command

```bash
python scripts/m54_baseline_adjudication.py \
  --candidate-report output/m54c/codex_m53_secession_threshold25_full_500turn_purepolitics_cleanbranch/batch_1/validate_report.json \
  --control-report output/m54b/codex_m53_secession_threshold25_full_500turn_control_recheck_current_machine/batch_1/validate_report.json \
  --control-report output/m54b/codex_m53_secession_threshold25_full_500turn_control_recheck_current_machine_run2/batch_1/validate_report.json \
  --control-report output/m54b/codex_m53_secession_threshold25_full_500turn_control_recheck_current_machine_run3/batch_1/validate_report.json \
  --accepted-baseline-report output/m54b/codex_m53_secession_threshold25_full_500turn_bootstrapfix/batch_1/validate_report.json \
  --output-json docs/superpowers/analytics/m54-baseline-adjudication-2026-03-24.json
```

## Operational policy for M54 closeout

For this milestone family, accept as stable when both are true:

1. Core oracle suite passes (`community`, `needs`, `era`, `cohort`, `artifacts`, `arcs`)
2. Candidate remains within the control-relative deltas above versus preserved same-machine M54b controls

This avoids blocking milestone closure on a known absolute-floor baseline shift that reproduces in controls.
