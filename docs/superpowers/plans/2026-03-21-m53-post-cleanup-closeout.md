# M53 Post-Cleanup Closeout â€” Implementation Plan

> **For agentic workers:** Execute this only **after** `docs/superpowers/plans/2026-03-21-m53b-validation-closure.md` is complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Once the M53b partial-cleanup work lands, refresh the ad-hoc validation outputs, make M53 status honest everywhere, and spin out the remaining spec-complete M53b pipeline work as its own tracked follow-up.

**This plan does NOT attempt full M53b closure.** It is a closeout/transition plan:
- refresh the corrected 20-seed probe report
- sync progress/spec/roadmap status language
- create the next plan for the exported-data validation pipeline

**Architecture boundary:** `scripts/m53_oracle_probe.py` remains an ad-hoc live-sim tool. `src/chronicler/validate.py` remains a library of oracle functions until the sidecar/export pipeline exists. Do not turn `validate.py` into a simulation runner in this plan.

---

## Task 1: Preflight the Partial-Cleanup Outputs

**Files:**
- Verify: `scripts/m53_oracle_probe.py`
- Verify: `src/chronicler/validate.py`
- Verify: `tuning/m53a_frozen.yaml`
- Verify: `docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`

- [x] **Step 1: Run the focused validator tests**

Run:

```bash
pytest tests/test_validate.py -v
```

Expected:
- Oracle 5 tests pass with `loss_destruction_rate`
- arc classifier tests pass
- no test still refers to removed `destruction_rate` keys

- [x] **Step 2: Confirm frozen snapshot exists**

Verify:

```bash
ls tuning/m53a_frozen.yaml
```

Expected:
- file exists
- includes substrate changes and pass-tuned constants

- [x] **Step 3: Run a small probe smoke test**

Run:

```bash
PYTHONPATH=src python scripts/m53_oracle_probe.py --seeds 2 --turns 50 --seed-start 42
```

Expected:
- probe completes
- Oracles 2 and 4 no longer print deferred placeholders
- Oracle 5 prints `loss_destruction_rate`
- Oracle 6 prints families + dominance status

- [x] **Step 4: Commit only if a preflight fix was needed**

Preflight fixes landed during the cleanup pass; no separate preflight-only commit is required now. Reference commit text if a follow-up commit is still desired:

```bash
git add <files>
git commit -m "fix(m53): preflight corrections for post-cleanup closeout"
```

---

## Task 2: Refresh the Ad-Hoc M53b Validation Report

**Files:**
- Modify: `docs/superpowers/analytics/m53b-validation-report.md`
- Optional artifact: `output/m53/oracle_probe_post_cleanup_42_61.txt`

This report remains **ad-hoc** and **20-seed**, but it should reflect the corrected probe and no longer mention stale gaps already fixed by the partial-cleanup plan.

- [x] **Step 1: Run the cleaned probe on the canonical 20-seed batch**

Run:

```bash
PYTHONPATH=src python scripts/m53_oracle_probe.py --seeds 20 --turns 200 --seed-start 42 > output/m53/oracle_probe_post_cleanup_42_61.txt
```

Capture the key outputs:
- Oracle 1: community pass/fail
- Oracle 2: matched pairs, mean rate difference, expected-sign count
- Oracle 3: inflection count / percentage
- Oracle 4: analyzed seeds, expected-direction count
- Oracle 5: creation, type diversity, loss/destruction
- Oracle 6: family count and dominance status

- [x] **Step 2: Rewrite `m53b-validation-report.md` from the corrected probe**

Required edits:
- state clearly that this is an **ad-hoc 20-seed live-sim probe**, not the spec-required canonical runner
- remove stale â€œdeferred because events missingâ€ language if Oracles 2/4 now produce results
- rename artifact metric to `loss/destruction rate`
- if Oracle 6 still violates the dominance cap, report it as a fail/partial, not a pass
- keep explicit notes on what is still missing for full M53b closure

Recommended report structure:
1. Run profile
2. Oracle-by-oracle results
3. What this proves
4. What remains for canonical M53b closure

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/analytics/m53b-validation-report.md output/m53/oracle_probe_post_cleanup_42_61.txt
git commit -m "docs(m53b): refresh ad-hoc validation report after probe cleanup"
```

The refreshed report is in place. Commit remains optional in a dirty worktree; omit `output/m53/...` if this repo should not persist probe output.

---

## Task 3: Sync M53 Status Across Progress / Spec / Roadmap Docs

**Files:**
- Modify: `docs/superpowers/progress/phase-6-progress.md`
- Modify: `docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`
- Optional: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

The goal is to make the project state honest and consistent:
- `M53a`: complete / frozen
- `M53b`: partial / not spec-complete
- partial cleanup complete
- canonical validation pipeline still pending

- [x] **Step 1: Update progress doc**

In `phase-6-progress.md`:
- mark the partial-cleanup items as done
- replace stale â€œvalidate.py runner is a stubâ€ wording if the remaining problem is now architectural, not just missing code
- make the headline status explicit:
  - tuning complete
  - partial validation cleanup complete
  - full M53b closure still blocked on exported-data pipeline + canonical gates

- [x] **Step 2: Add a dated note to the M53 spec if needed**

Spec audit complete: no additional dated note was required; the narrowed Oracle 5 wording and M53b completion criteria already match the intended post-cleanup state.

- [x] **Step 3: Update roadmap language if it currently implies M53 is fully closed**

Roadmap audit complete: no wording change required; it still describes M53 as a gate, not a finished milestone

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/progress/phase-6-progress.md docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md docs/superpowers/roadmaps/chronicler-phase7-roadmap.md
git commit -m "docs(m53): sync status after partial validation cleanup"
```

Progress-doc sync is complete. Spec and roadmap edits were not needed in this pass.

---

## Task 4: Create the Follow-On Plan for Full M53b Pipeline Closure

**Files:**
- Create: `docs/superpowers/plans/2026-03-21-m53b-validation-pipeline.md`

This is the important handoff artifact. The current plan should end by opening the real remaining work as its own implementation plan instead of leaving it implicit.

- [x] **Step 1: Create the new plan**

Title:

```markdown
# M53b Validation Pipeline â€” Implementation Plan
```

The new plan should cover:

1. **Validation sidecar/export pipeline**
   - graph snapshots / community summary data
   - per-turn or per-window agent event export
   - memory signature export
   - validation-summary aggregation

2. **Canonical `python -m chronicler.validate` consumer path**
   - consume bundles + sidecars
   - determinism gate
   - oracle routing over exported data

3. **Gate-sized runs**
   - 20-seed oracle subset where appropriate
   - 200-seed structural gate
   - 500-turn runs for Oracle 3 / Oracle 5 checks that require them

4. **Canonical report regeneration**
   - rebuild `docs/superpowers/analytics/m53b-validation-report.md`
   - ensure report comes from `chronicler.validate`, not the probe

5. **Exit criteria**
   - what would need to be true to honestly mark `M53b` complete

- [x] **Step 2: Link it from the progress doc**

Add a short pointer in `phase-6-progress.md`:
- â€œFull M53b closure tracked in `docs/superpowers/plans/2026-03-21-m53b-validation-pipeline.md`â€

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-03-21-m53b-validation-pipeline.md docs/superpowers/progress/phase-6-progress.md
git commit -m "plan(m53b): spin out full validation pipeline follow-up"
```

---

## Task 5: Final Closeout Note

**Files:**
- Modify: `docs/superpowers/progress/phase-6-progress.md`

- [x] **Step 1: Add a short post-cleanup closeout note**

Add a short dated note summarizing:
- partial-cleanup plan complete
- ad-hoc report refreshed
- frozen YAML present
- full M53b closure intentionally deferred to the new validation-pipeline plan

This should be short and should avoid claiming M53 overall completion.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/progress/phase-6-progress.md
git commit -m "docs(m53): add post-cleanup closeout note"
```

---

## Acceptance Criteria

This post-cleanup closeout plan is complete when:

1. `tests/test_validate.py` passes after the partial-cleanup changes
2. `tuning/m53a_frozen.yaml` exists and reflects the full M53 change set
3. `docs/superpowers/analytics/m53b-validation-report.md` reflects the corrected ad-hoc probe
4. Progress/spec/roadmap docs no longer overstate M53 as spec-complete
5. A new follow-on plan exists for the real M53b exported-data validation pipeline

---

## Non-Goals

This plan does **not**:
- make `validate.py` a live-sim runner
- satisfy the specâ€™s canonical 200-seed / 500-turn M53b gate
- claim M53 overall completion
- replace the future exported-data validation pipeline

---

## Recommended Execution Order

1. Task 1 â€” Preflight partial-cleanup outputs
2. Task 2 â€” Refresh ad-hoc validation report
3. Task 3 â€” Sync status docs
4. Task 4 â€” Create full-pipeline follow-on plan
5. Task 5 â€” Add final closeout note

This ordering keeps the docs grounded in actual post-cleanup results before the follow-on pipeline plan is authored.

