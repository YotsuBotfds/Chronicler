# M53b Validation Pipeline — Implementation Plan

> **For agentic workers:** This plan is the follow-on after `docs/superpowers/plans/2026-03-21-m53b-validation-closure.md` and `docs/superpowers/plans/2026-03-21-m53-post-cleanup-closeout.md`. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution note (2026-03-22):** The canonical pipeline was implemented on 2026-03-21 and initially recorded failed subset/full gates. A follow-on rerun on 2026-03-22 using `tuning/codex_m53_secession_threshold25.yaml` produced a passing full canonical gate at `output/m53/codex_m53_secession_threshold25_full/batch_1`. This plan now serves as the implementation record for both the pipeline and the final passing rerun.

**Goal:** Build the missing exported-data validation pipeline so M53b can be evaluated through the spec-required `python -m chronicler.validate` post-processing path instead of ad-hoc live-sim probes.

**This plan is the real path to full M53b closure.** It covers:
- validation sidecar/export pipeline
- canonical `chronicler.validate` consumer wiring
- gate-sized 20-seed / 200-seed / 500-turn runs where required
- canonical report regeneration

**Architecture constraint:** `src/chronicler/validate.py` must remain a **post-processing consumer** of exported bundle + sidecar + summary data. It must not run the simulation loop itself.

---

## Scope

### In Scope
- Exported validation artifacts for Oracles 1/2/4
- `validation_summary` aggregation for regression and gate metrics
- Canonical `python -m chronicler.validate` CLI consumer
- Determinism smoke gate
- Canonical M53b report generation from exported data
- Gate scripts / commands for oracle subset and full gate

### Out of Scope
- Re-tuning M53 constants
- Reopening M53a freeze decisions
- Reworking oracle math unless implementation reveals a real bug
- Viewer/UI work beyond what is needed to persist validation artifacts

---

## Deliverables

1. Validation sidecar files written during designated validation runs
2. `validation_summary` export available per batch
3. `python -m chronicler.validate` consumes bundle + sidecar data and produces structured JSON reports
4. Determinism smoke gate implemented through exported bundles
5. Canonical M53b validation report regenerated from the official runner
6. Progress/spec docs updated to mark M53b complete only if all gates pass

---

## Task 1: Design and Lock the Validation Artifact Contract

**Files:**
- Modify: `docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`
- Optional reference note: `docs/superpowers/analytics/` or `docs/superpowers/reviews/`

Before implementation, make the exported-data contract explicit so workers do not invent incompatible sidecar formats.

- [x] **Step 1: Specify the on-disk validation artifacts**

Document the required files produced for validation runs:
- `chronicle_bundle.json`
- `agent_events.arrow`
- `validation_summary.json` or `.arrow`
- graph/memory sidecar (sampled every 10 turns)
- optional community-summary sidecar for full 200-seed gate

- [x] **Step 2: Lock the minimum schema**

Required payloads:
- graph snapshots: `turn`, `agent_id`, `target_id`, `bond_type`, `sentiment`
- memory signatures: `turn`, `agent_id`, `event_type`, `memory_turn`, `valence_sign` or equivalent
- needs snapshot join fields: `agent_id`, `civ_affinity`, `region`, `occupation`, `satisfaction`, `boldness`, `ambition`, `loyalty_trait`, 6 needs
- agent aggregate summary: counts, satisfaction stats, occupation shares

- [x] **Step 3: Clarify which artifacts are raw-sidecar subset only vs full gate**

Lock the split:
- Oracle subset (20 seeds): raw graph+memory sidecar + needs/event data
- Full gate (200 seeds): condensed community summaries + bundle-derived oracles + regression summary

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md
git commit -m "docs(m53b): lock validation artifact contract for pipeline implementation"
```

---

## Task 2: Build Sidecar Export for Community / Cohort Oracles

**Files:**
- Modify: `src/chronicler/bundle.py`
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `src/chronicler/models.py` if needed for run flags / metadata
- Possibly modify FFI wiring if additional bulk exports are needed

This task produces the missing exported-data path for Oracles 1 and 4.

- [x] **Step 1: Define validation-run trigger**

Add or reuse a flag / mode so raw validation sidecars are written only for designated validation runs, not every normal batch.

- [x] **Step 2: Export graph snapshots**

At the agreed cadence (every 10 turns), export:
- `turn`
- `agent_id`
- `target_id`
- `bond_type`
- `sentiment`

Format:
- Arrow IPC sidecar next to the bundle

- [x] **Step 3: Export memory signatures aligned to snapshots**

At the same sampled turns, export a compact memory-signature view per agent suitable for community detection:
- `turn`
- `agent_id`
- `event_type`
- `memory_turn_bucket` or exact turn
- `valence_sign`

- [ ] **Step 4: Add condensed community summary mode for full gates**

For the 200-seed full gate, avoid raw-sidecar bloat by writing summary outputs such as:
- communities detected
- community size distribution
- dominant shared-memory type
- max community fraction per region

- [x] **Step 5: Verify sidecar write path**

Run a small validation batch and confirm sidecars exist with sane row counts.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/bundle.py src/chronicler/agent_bridge.py src/chronicler/models.py
git commit -m "feat(m53b): export graph and memory validation sidecars"
```

---

## Task 3: Build Validation Summary Export

**Files:**
- Modify: `src/chronicler/bundle.py`
- Modify: `src/chronicler/analytics.py`
- Possibly add helper in `scripts/` if aggregation is too bulky for bundle assembly

This task supports the regression suite and full-gate metrics.

- [x] **Step 1: Define `validation_summary` schema**

Minimum fields:
- `agent_count_by_turn`
- satisfaction mean/std by turn
- occupation distribution by turn or at sampled turns
- rebellion / migration / birth / death totals
- community summary rollups for full gates
- denominator fields needed for “agent-turn” metrics

- [x] **Step 2: Export `validation_summary` alongside bundles**

Format may be JSON for readability or Arrow for scale; choose one and document it.

- [ ] **Step 3: Ensure summary can be aggregated across a batch**

Either:
- one summary per seed plus batch-level aggregator in `validate.py`, or
- batch-level summary writer

- [ ] **Step 4: Verify regression fields cover spec Section 7**

Explicitly check support for:
- satisfaction distribution
- migration / rebellion rates
- occupation distribution
- civ survival
- treasury stability

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/bundle.py src/chronicler/analytics.py
git commit -m "feat(m53b): export validation_summary for regression and gate metrics"
```

---

## Task 4: Implement Determinism Gate as Exported-Data Consumer

**Files:**
- Modify: `src/chronicler/validate.py`
- Modify: `tests/test_validate.py`
- Optional: add a dedicated test fixture directory

- [x] **Step 1: Implement `run_determinism_gate()`**

Requirements:
- load exported bundles from `--batch-dir`
- group by duplicate seed
- compare via `scrubbed_equal()`
- return structured PASS / FAIL / SKIP report

- [x] **Step 2: Keep comparison strictly post-processing**

Do not rerun sim. Use already-written bundle JSON only.

- [x] **Step 3: Add tests**

Cover:
- matching bundles with different `generated_at`
- mismatched world state
- no duplicate-seed pairs

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py
git commit -m "feat(m53b): implement determinism smoke gate from exported bundles"
```

---

## Task 5: Implement Canonical Oracle Routing in `validate.py`

**Files:**
- Modify: `src/chronicler/validate.py`
- Modify: `tests/test_validate.py`

This is the canonical consumer path. It must load exported artifacts, not run live sim.

- [x] **Step 1: Add bundle + sidecar loaders**

Implement helpers to load:
- bundles from `--batch-dir`
- `agent_events.arrow`
- graph/memory sidecars
- `validation_summary`

- [x] **Step 2: Wire Oracle 1**

Inputs:
- graph sidecar
- memory-signature sidecar

Output:
- qualifying community count
- pass/fail against oracle-subset threshold

- [x] **Step 3: Wire Oracle 2**

Inputs:
- needs snapshot export
- `agent_events.arrow`

Output:
- matched pairs
- effect-size summary
- expected-sign fraction

Note:
- if effect-size computation is missing from current helper, extend the helper here rather than faking it in the runner

- [x] **Step 4: Wire Oracle 3**

Inputs:
- `extract_era_signals()` from bundles

Output:
- per-seed inflection counts
- silent-collapse checks

- [x] **Step 5: Wire Oracle 4**

Inputs:
- community detection output
- `agent_events.arrow`
- agent demographic snapshot

Output:
- cohort vs matched control behavior comparison

- [x] **Step 6: Wire Oracle 5**

Inputs:
- `extract_artifacts()`
- any approved M53-scope artifact checks still in spec

If Oracle 5 remains scope-narrowed for M53, the router should report only the narrowed checks and note deferred subchecks explicitly.

- [x] **Step 7: Wire Oracle 6**

Inputs:
- `extract_era_signals()` or equivalent civ trajectories

Output:
- family count
- dominance-cap evaluation
- per-seed arc diversity if implemented

- [x] **Step 8: Implement CLI output format**

`python -m chronicler.validate --batch-dir <path> --oracles all`
should emit structured JSON with:
- per-oracle status
- counts / metrics
- enough detail to build the report mechanically

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py
git commit -m "feat(m53b): wire canonical oracle runner over exported validation artifacts"
```

---

## Task 6: Add Batch/Gate Runner Support

**Files:**
- Create or modify helper scripts in `scripts/`
- Optional: update plan/progress docs with canonical commands

The goal is to make gate execution repeatable by workers.

- [x] **Step 1: Add an oracle-subset runner command or script**

Target profile:
- 20 seeds
- raw sidecars enabled
- turns long enough for oracle-subset checks

- [x] **Step 2: Add a full-gate runner command or script**

Target profile:
- 200 seeds
- condensed summaries enabled
- 500 turns where required for Oracle 3 / Oracle 5 checks

- [x] **Step 3: Document deterministic env requirements**

Include:
- `PYTHONHASHSEED=0`
- exact output roots to avoid directory collisions

- [ ] **Step 4: Commit**

```bash
git add scripts/<runner-files>
git commit -m "feat(m53b): add canonical oracle-subset and full-gate runner scripts"
```

---

## Task 7: Run Canonical Gates

**Files:**
- Generated outputs in `output/m53/...`
- Possibly checked-in summary artifacts if the repo convention allows

- [x] **Step 1: Run determinism smoke gate**

Required:
- duplicate-seed `agents=off`
- duplicate-seed `agents=hybrid`

- [x] **Step 2: Run oracle subset**

Use the canonical exported-data path for:
- Oracles 1, 2, 4
- optionally 3/5/6 too if convenient

- [x] **Step 3: Run full gate**

Use the canonical exported-data path for:
- Oracle 3
- Oracle 5
- Oracle 6
- regression summary

- [x] **Step 4: Record results in machine-readable form**

Store the JSON outputs from `python -m chronicler.validate` for both:
- oracle subset
- full gate

- [x] **Step 5: If gates fail, classify failure honestly**

Allowed classifications:
- tuning issue
- instrumentation/runner issue
- spec mismatch

Do not auto-declare M53b complete if any blocking gate still fails.

Result:
- Determinism smoke: PASS for dedicated `agents=off` and `agents=hybrid` duplicate-seed exported-data runs
- Initial oracle subset / full gate run (2026-03-21): FAIL
- Final full gate rerun (2026-03-22, `tuning/codex_m53_secession_threshold25.yaml`): PASS
- Classification: the initial failure exposed real tuning / hybrid-parity issues, not a validator-path blocker

---

## Task 8: Regenerate Canonical M53b Report

**Files:**
- Modify: `docs/superpowers/analytics/m53b-validation-report.md`

This version replaces the ad-hoc probe report as the canonical M53b report only if it is built from `python -m chronicler.validate`.

- [x] **Step 1: Rewrite report from official runner outputs**

Report must clearly distinguish:
- oracle subset results
- full gate results
- informational vs blocking checks
- any deferred Oracle 5 checks still intentionally out of scope

- [x] **Step 2: Include exact run profile**

State:
- seed ranges
- turn counts
- whether raw sidecars or condensed summaries were used
- exact date of run

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/analytics/m53b-validation-report.md
git commit -m "docs(m53b): regenerate canonical validation report from exported-data runner"
```

---

## Task 9: Close the Loop in Progress / Spec Docs

**Files:**
- Modify: `docs/superpowers/progress/phase-6-progress.md`
- Modify: `docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`
- Optional: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

- [x] **Step 1: If all canonical gates pass, mark M53b complete**

Update status language carefully:
- `M53a` complete/frozen
- `M53b` complete only if spec gates are actually met

- [x] **Step 2: If gates do not pass, leave M53b open with explicit blockers until a passing rerun exists**

Do not soften failures into “likely passes” in the status docs.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/progress/phase-6-progress.md docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md docs/superpowers/roadmaps/chronicler-phase7-roadmap.md
git commit -m "docs(m53b): update canonical validation status after pipeline gate"
```

---

## Acceptance Criteria

This plan is complete when:

1. Validation sidecars exist for oracle-subset runs
2. `validation_summary` exists and supports the regression suite
3. `python -m chronicler.validate` consumes exported data and returns structured oracle reports
4. Determinism smoke gate works via exported bundles
5. Canonical oracle subset and full-gate runs have been executed
6. `docs/superpowers/analytics/m53b-validation-report.md` is regenerated from the canonical path
7. Project docs honestly reflect whether M53b is complete or still blocked

Current outcome:
- Criteria 1-7 are met.
- The 2026-03-21 canonical failure exposed real behavioral issues on the exported-data path.
- The 2026-03-22 rerun cleared all blocking oracles on that same canonical path.
- The pipeline work and M53b closeout are complete.

---

## Non-Goals

This plan does **not**:
- tune M53 constants again unless canonical gates prove a real tuning failure
- replace the ad-hoc probe for quick experimentation
- do viewer-facing polish beyond what sidecar export requires

---

## Recommended Execution Order

1. Task 1 — Lock artifact contract
2. Task 2 — Build sidecar export for graph/memory
3. Task 3 — Build validation summary export
4. Task 4 — Determinism gate
5. Task 5 — Canonical oracle routing
6. Task 6 — Runner scripts
7. Task 7 — Canonical gate runs
8. Task 8 — Canonical report regeneration
9. Task 9 — Status/doc closeout

This ordering keeps implementation aligned with the spec’s intended architecture and avoids reintroducing the live-simulation shortcut into `validate.py`.
