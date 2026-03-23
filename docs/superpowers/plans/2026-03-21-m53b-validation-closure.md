# M53b Partial Validation Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix oracle function bugs, wire event data into the probe, generate the complete frozen YAML, and clean up scope documentation. This is partial M53b work — it does NOT claim spec-complete M53b closure.

**Architecture:** Fix pure oracle functions in `validate.py` (no architectural changes to the module). Fix the ad-hoc probe script to collect real events. Generate `m53a_frozen.yaml` with all M53-changed constants (tuning passes + demographic substrate). Amend spec and docs to reflect actual scope. `validate.py` remains a library of oracle functions — the spec-compliant CLI consumer is out of scope (requires sidecar pipeline).

**Tech Stack:** Python (validate.py, m53_oracle_probe.py), YAML (frozen snapshot)

**Scope narrowing (approved 2026-03-21):** Oracle 5 for M53 covers: creation rate, type diversity, loss/destruction rate. Deferred: relic conversion impact, narration visibility, Mule-origin rate (needs GP cross-referencing instrumentation).

**Out of scope (documented in "Remaining Work" section):**
- Making `validate.py` a live-simulation runner (violates spec architecture — validate.py is a post-processing consumer)
- Spec-compliant `python -m chronicler.validate` CLI wiring (requires sidecar export pipeline)
- 200-seed structural gate / 500-turn oracle runs
- Condensed community summaries (spec 8.2.5)

---

### Task 1: Fix Oracle 5 — Count LOST Artifacts in Loss Rate

**Files:**
- Modify: `src/chronicler/validate.py:537-565`
- Test: `tests/test_validate.py` (new)

Current `check_artifact_lifecycle()` only counts `status == "destroyed"`. `ArtifactStatus` has three values: `ACTIVE`, `LOST`, `DESTROYED`. The spec's 10-30% target covers loss OR destruction.

- [ ] **Step 1: Write failing test**

```python
# tests/test_validate.py
import json
from chronicler.validate import check_artifact_lifecycle, classify_civ_arc, scrubbed_equal

def test_artifact_lifecycle_counts_lost_and_destroyed():
    """Oracle 5 loss rate should include both LOST and DESTROYED artifacts."""
    bundles = [{
        "world_state": {"artifacts": [
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "monument", "status": "lost", "mule_origin": False},
            {"artifact_type": "treatise", "status": "destroyed", "mule_origin": False},
            {"artifact_type": "epic", "status": "active", "mule_origin": True},
        ]},
        "metadata": {"total_turns": 100},
    }]
    result = check_artifact_lifecycle(bundles)
    # 2 of 4 artifacts are lost or destroyed = 0.50
    assert result["loss_destruction_count"] == 2
    assert result["loss_destruction_rate"] == 0.50

def test_artifact_lifecycle_creation_rate():
    """Creation rate sanity check."""
    bundles = [{
        "world_state": {"artifacts": [
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "monument", "status": "active", "mule_origin": False},
        ]},
        "metadata": {"total_turns": 100},
    }]
    result = check_artifact_lifecycle(bundles, num_civs=4)
    # 2 artifacts / (4 civs * 100/100) = 0.5
    assert result["creation_rate_per_civ_per_100"] == 0.5

def test_artifact_lifecycle_type_diversity():
    """No single type > 50%."""
    bundles = [{
        "world_state": {"artifacts": [
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "epic", "status": "active", "mule_origin": False},
        ]},
        "metadata": {"total_turns": 100},
    }]
    result = check_artifact_lifecycle(bundles)
    assert result["type_diversity_ok"] is False  # relic = 75%
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validate.py -v`
Expected: FAIL — `loss_destruction_count` key missing

- [ ] **Step 3: Fix `check_artifact_lifecycle()`**

In `src/chronicler/validate.py`, make these changes:

1. Rename `destroyed_count` to `loss_destruction_count` (line 522 init)
2. Change the status check (line 538) from `if status == "destroyed"` to `if status in ("destroyed", "lost")`
3. Rename return dict keys: `destruction_rate` → `loss_destruction_rate`, `destruction_rate_ok` → `loss_destruction_rate_ok`, add `loss_destruction_count`
4. Remove old `destruction_rate` / `destruction_rate_ok` keys

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validate.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Update probe's Oracle 5 output**

In `scripts/m53_oracle_probe.py` line 227, change `destruction_rate` to `loss_destruction_rate`.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py scripts/m53_oracle_probe.py
git commit -m "fix(m53b): Oracle 5 counts LOST + DESTROYED artifacts in loss rate"
```

---

### Task 2: Fix Oracle 6 — Enforce 40% Dominance Cap

**Files:**
- Modify: `scripts/m53_oracle_probe.py:231-249`
- Test: `tests/test_validate.py`

The probe marks Oracle 6 as PASS if 5/6 arc families exist, but doesn't check the spec requirement: "No single arc dominates >40% of civs." The check applies to ALL arcs including "stable" — the spec makes no exception.

- [ ] **Step 1: Add arc classifier tests**

Add to `tests/test_validate.py`:

```python
def test_classify_civ_arc_monotone_down():
    traj = {"population": [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]}
    assert classify_civ_arc(traj) == "riches_to_rags"

def test_classify_civ_arc_monotone_up():
    traj = {"population": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]}
    assert classify_civ_arc(traj) == "rags_to_riches"

def test_classify_civ_arc_stable():
    traj = {"population": [50] * 30}
    assert classify_civ_arc(traj) == "stable"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_validate.py -v`
Expected: PASS (existing function behavior)

- [ ] **Step 3: Add dominance cap to probe's Oracle 6**

In `scripts/m53_oracle_probe.py`, replace the Oracle 6 summary (after line 248) with:

```python
    # Dominance cap: no non-stable arc > 40% of all civs
    total_civs = sum(arc_counts.values())
    dominance_ok = True
    if total_civs > 0:
        for arc, count in arc_counts.items():
            if count / total_civs > 0.40:
                print(f"  WARNING: {arc} dominates at {count/total_civs:.0%} (>40% cap)")
                dominance_ok = False
    o6_families_ok = len(arc_families) >= 5
    o6_pass = o6_families_ok and dominance_ok
    print(f"  Families: {'PASS' if o6_families_ok else 'FAIL'} ({len(arc_families)}/6, target >=5)")
    print(f"  Dominance cap: {'PASS' if dominance_ok else 'FAIL'} (no arc >40%)")
    print(f"  Overall: {'PASS' if o6_pass else 'FAIL'}")
```

- [ ] **Step 4: Commit**

```bash
git add scripts/m53_oracle_probe.py tests/test_validate.py
git commit -m "fix(m53b): Oracle 6 enforces 40% arc dominance cap"
```

---

### Task 3: Wire Event Collection Into Oracle Probe

**Files:**
- Modify: `scripts/m53_oracle_probe.py:33-46` (delete dead code)
- Modify: `scripts/m53_oracle_probe.py:49-146` (run_seed)
- Modify: `scripts/m53_oracle_probe.py:178-214` (Oracle 2 and 4 sections)

**IMPORTANT:** `collect_agent_events()` (lines 33-46) calls `bridge._sim.get_last_tick_events()` which does NOT exist on the Rust `AgentSimulator`. The actual event flow is: `self._sim.tick()` returns events → `bridge._convert_events()` → stored as `AgentEventRecord` objects in `world.agent_events_raw`. The probe should read from `world.agent_events_raw` after the simulation loop.

`AgentEventRecord` is a dataclass with fields: `turn`, `agent_id`, `event_type` (str), `region`, `target_region`, `civ_affinity`, `occupation`. The oracle functions expect `event_type` as int, so we need a str→int mapping.

- [ ] **Step 1: Delete dead `collect_agent_events()` and wire `world.agent_events_raw`**

In `scripts/m53_oracle_probe.py`:

Delete the `collect_agent_events()` function (lines 33-46). Keep the `import pyarrow as pa` — the probe still uses `pa.record_batch()` for relationship, needs, snapshot, and memory reads.

In `run_seed()`, after the simulation loop completes (after line 120, before the artifacts block), add:

```python
    # Convert AgentEventRecord objects to oracle-compatible dicts
    EVENT_TYPE_MAP = {"death": 0, "migration": 1, "rebellion": 2, "occupation_switch": 3,
                      "loyalty_flip": 4, "birth": 5, "dissolution": 6}
    all_events = []
    for e in world.agent_events_raw:
        et_int = EVENT_TYPE_MAP.get(e.event_type, -1)
        if et_int >= 0:
            all_events.append({"agent_id": e.agent_id, "event_type": et_int, "turn": e.turn})
```

Add `"events": all_events` to the return dict (after `"civ_trajectories"`).

- [ ] **Step 2: Pass real events to Oracle 2**

Replace lines 178-188 (Oracle 2 section). Add `total_rate_diff = 0` and `seeds_with_sign = 0` before the loop:

```python
    print("\n=== ORACLE 2: Needs Diversity ===")
    total_pairs = 0
    total_rate_diff = 0
    seeds_with_sign = 0
    for r in all_results:
        if not r["needs_data"] or "safety" not in r["needs_data"]:
            continue
        result = compute_needs_diversity(r["needs_data"], r["events"], "safety", 1)
        total_pairs += result.get("pairs_found", 0)
        total_rate_diff += result.get("rate_difference", 0)
        if result.get("rate_difference", 0) > 0:
            seeds_with_sign += 1
    mean_rate_diff = total_rate_diff / args.seeds if args.seeds > 0 else 0
    print(f"  Matched pairs (safety): {total_pairs} across {args.seeds} seeds")
    print(f"  Mean rate difference (low-high): {mean_rate_diff:.4f}")
    print(f"  Seeds with expected sign: {seeds_with_sign}/{args.seeds} — target >=60%")
    o2_pass = seeds_with_sign >= int(args.seeds * 0.60)
    print(f"  {'PASS' if o2_pass else 'FAIL'}")
```

- [ ] **Step 3: Pass real events to Oracle 4**

Replace lines 206-214 (Oracle 4 section):

```python
    print("\n=== ORACLE 4: Cohort Distinctiveness ===")
    seeds_expected_direction = 0
    seeds_analyzed = 0
    for r in all_results:
        communities = detect_communities(r["edges"], r["mem_sigs"])
        if communities and r["agent_data"] and r["events"]:
            seeds_analyzed += 1
            result = compute_cohort_distinctiveness(
                communities, r["events"], r["agent_data"], event_type=1
            )
            if result["effect_direction"] == "community_lower":
                seeds_expected_direction += 1
    print(f"  Seeds analyzed: {seeds_analyzed}/{args.seeds}")
    print(f"  Seeds with community_lower migration: "
          f"{seeds_expected_direction}/{args.seeds} — target >=60%")
    o4_pass = seeds_expected_direction >= int(args.seeds * 0.60)
    print(f"  {'PASS' if o4_pass else 'FAIL'}")
```

- [ ] **Step 4: Run probe to verify events are collected**

Run: `PYTHONPATH=src python scripts/m53_oracle_probe.py --seeds 2 --turns 50`
Expected: Output shows non-zero event counts, Oracles 2 and 4 produce rate comparisons (not "deferred" notes)

- [ ] **Step 5: Commit**

```bash
git add scripts/m53_oracle_probe.py
git commit -m "fix(m53b): wire world.agent_events_raw into Oracles 2 and 4"
```

---

### Task 4: Generate Complete `tuning/m53a_frozen.yaml`

**Files:**
- Create: `tuning/m53a_frozen.yaml`

This must include ALL constants changed on the M53 branch — both the 6 pass-tuned constants and the demographic/satisfaction substrate changes.

- [ ] **Step 1: Create the frozen YAML**

```yaml
# M53a Frozen Constant Snapshot
# Generated: 2026-03-21
# Branch: feat/m53-depth-tuning
# Status: All tuning passes complete, constants frozen
# Baseline: tuning/m53_baseline_v2.yaml

# ===================================================================
# DEMOGRAPHIC & SATISFACTION SUBSTRATE CHANGES
# These are structural fixes, not tuning-pass adjustments. They were
# required to make the depth systems (M48-M52) viable — without them,
# population collapsed before any depth system could activate.
# ===================================================================

substrate_changes:
  # --- Disease mortality formula (additive → multiplicative) ---
  - name: DISEASE_MORTALITY_SCALE
    file: chronicler-agents/src/agent.rs:114
    tier: HARD
    before: "N/A (additive formula: base*eco*war + disease)"
    after: "10.0 (multiplicative: base*eco*war*(1+disease*SCALE))"
    commit: 9e36df1
    reason: >
      Additive formula gave 16%/turn mortality at disease cap (0.15).
      Multiplicative gives 2.5x at cap. Primary cause of original
      population collapse across all seeds.

  # --- Mortality rates ---
  - name: MORTALITY_ADULT
    file: chronicler-agents/src/agent.rs:31
    tier: HARD
    before: 0.01
    after: 0.005
    commit: ebec710
    reason: >
      Combined fix with fertility. Original rates produced B/D=0.13
      (population unable to sustain itself). Halved adult mortality
      as part of the B+C+D demographic rebalance.

  - name: MORTALITY_ELDER
    file: chronicler-agents/src/agent.rs:32
    tier: HARD
    before: 0.05
    after: 0.03
    commit: ebec710
    reason: >
      Part of B+C+D combined fix. Elder mortality was too aggressive
      relative to fertility, preventing generational handoff.

  # --- Fertility rates ---
  - name: FERTILITY_BASE_FARMER
    file: chronicler-agents/src/agent.rs:42
    tier: HARD
    before: 0.03
    after: 0.05
    commit: ebec710
    reason: Part of B+C+D combined fix. Doubled farmer fertility to
      achieve B/D >= 0.20 at equilibrium.

  - name: FERTILITY_BASE_OTHER
    file: chronicler-agents/src/agent.rs:43
    tier: HARD
    before: 0.015
    after: 0.03
    commit: ebec710
    reason: Part of B+C+D combined fix. Doubled non-farmer fertility.

  # --- Fertility taper (replaces hard cutoff) ---
  - name: FERTILITY_FULL_AGE_MAX
    file: chronicler-agents/src/agent.rs:40
    tier: HARD
    before: "N/A (hard cutoff FERTILITY_AGE_MAX=45)"
    after: 50
    commit: ce3a3e4
    reason: >
      Hard cutoff at 45 caused entire cohorts to drop out of fertility
      simultaneously, creating generational handoff gaps. Taper from
      50 to 60 smooths the transition. Full=50 + taper to 60 confirmed
      across 40 seeds as the sweet spot.

  - name: FERTILITY_TAPER_AGE_MAX
    file: chronicler-agents/src/agent.rs:41
    tier: HARD
    before: "N/A (no taper existed)"
    after: 60
    commit: ce3a3e4
    reason: Linear taper endpoint. Fertility drops to zero at age 60.

  # --- Overcrowding penalty cap ---
  - name: OVERCROWDING_PENALTY_CAP
    file: chronicler-agents/src/agent.rs:122
    tier: HARD
    before: "N/A (uncapped)"
    after: 0.30
    commit: 84775f8
    reason: >
      Uncapped formula (pop/cap - 1.0) * 0.3 zeroed satisfaction at
      3-7x carrying capacity. This blocked all fertility and made
      M48-M52 depth systems completely inert. Cap at 0.30 preserves
      overcrowding pressure up to 2x while preventing runaway zeroing.
      Overcrowding is already punished via ecology, disease, and
      demography — the satisfaction penalty is supplementary, not the
      primary mechanism.

# ===================================================================
# PASS-TUNED CONSTANTS (6 total)
# Changed during M53 system passes 1a-1f.
# ===================================================================

pass_tuned_constants:
  # --- HARD freeze (cross-system, structural) ---
  - name: SOCIAL_BLEND_ALPHA
    file: chronicler-agents/src/agent.rs:344
    tier: HARD
    before: 0.0
    after: 0.3
    pass: 1c (Relationships)
    commit: ff63fbb
    reason: >
      Bond-based social restoration needed nonzero blend weight.
      Alpha alone did nothing because SOCIAL_RESTORE_BOND and
      SOCIAL_RESTORE_POP were equal — blend just interpolated between
      equal values.

  - name: SOCIAL_RESTORE_BOND
    file: chronicler-agents/src/agent.rs:345
    tier: HARD
    before: 0.010
    after: 0.030
    pass: 1c (Relationships)
    commit: ff63fbb
    reason: >
      Bond restoration rate needed to be 3x to outpace 0.008 decay
      through the multiplier chain. Safety has 3 sources summing to
      ~0.038; social had 1 source at ~0.006 effective.

  - name: AUTONOMY_DECAY
    file: chronicler-agents/src/agent.rs:242
    tier: HARD
    before: 0.015
    after: 0.010
    pass: 1b (Needs)
    commit: ff63fbb
    reason: >
      Was fastest-decaying need. Foreign-controlled agents had only
      NO_PERSC (0.010) available; 0.015 decay made equilibrium
      negative. Now aligns with spiritual decay rate.

  - name: AUTONOMY_RESTORE_NO_PERSC
    file: chronicler-agents/src/agent.rs:275
    tier: HARD
    before: 0.010
    after: 0.020
    pass: 1b (Needs)
    commit: ff63fbb
    reason: >
      Doubling restoration + reducing decay gives foreign-controlled
      agents viable equilibrium at 0.50, own-rule at 0.75.

  # --- SOFT freeze (system-local) ---
  - name: MULE_PROMOTION_PROBABILITY
    file: src/chronicler/agent_bridge.py:38
    tier: SOFT
    before: 0.07
    after: 0.12
    pass: 1d (Mule)
    commit: 6706dbe
    reason: >
      GP promotion is bursty — need higher hit rate to get Mules in
      50%+ of seeds (was 35%). Mean 1.9 at T50.

  - name: MULE_ACTIVE_WINDOW
    file: src/chronicler/action_engine.py:42
    tier: SOFT
    before: 25
    after: 30
    pass: 1d (Mule)
    commit: 6706dbe
    reason: >
      Extend Mule influence beyond initial GP burst. All Mules still
      expire by T100 (structural — cohort-based promotion).

# ===================================================================
# M49 CALIBRATION FLAGS (10 flags, each addressed)
# ===================================================================

m49_calibration_flags:
  - flag: Persecution triple-stacking
    status: DOCUMENTED
    pass: 1b
    finding: >
      M38b (0.30) + M48 memory (~0.10) + M49 Autonomy (up to 0.24)
      total can reach ~0.64 additive on rebel. Persecution is
      intentionally harsh — stacking reflects cumulative trauma.
      Rebellion rate stays within acceptable range. Monitored, not
      clamped.

  - flag: Famine double-counting
    status: PASS
    pass: 1b
    finding: >
      food_sufficiency penalty is outside the 0.40 non-ecological
      cap (material condition). Safety need restoration via
      SAFETY_RESTORE_FOOD is additive, not multiplicative with the
      penalty. No double-counting observed.

  - flag: Needs-only rebellion rate
    status: PASS
    pass: 1b
    finding: >
      Rebellion rate from needs alone is low. Needs supplement
      existing drivers (memory, satisfaction), not replace them.
      NEEDS_MODIFIER_CAP=0.30 prevents needs from dominating.

  - flag: Need activation fraction
    status: PASS
    pass: 1b
    finding: >
      Autonomy activation starts at 46% at T50 (many foreign-
      controlled agents), drops to 18% by T100 as agents settle.
      Social activation ~33% at T50. Safety near 0%. Pattern is
      healthy — activation tracks meaningful state.

  - flag: Migration sloshing
    status: PASS
    pass: 1b, 1c
    finding: >
      No region-pair oscillation observed. Migration rate of 138.5/seed
      over 200 turns is active but not oscillatory.

  - flag: Sawtooth oscillation
    status: PASS
    pass: 1b
    finding: >
      Linear decay + proportional restoration produces smooth curves,
      not sawtooth. No need cycling within <10 turns observed.

  - flag: Duty cycle per need
    status: PASS
    pass: 1b
    finding: >
      Each need spends meaningful time in both states. Safety is
      almost always satisfied (0% below threshold). Social and
      autonomy have real deficit periods. Spiritual and purpose
      track temple/occupation status.

  - flag: Social proxy adequacy
    status: PASS
    pass: 1c
    finding: >
      Blend formula with SOCIAL_BLEND_ALPHA=0.3 and
      SOCIAL_RESTORE_BOND=0.030 produces social_below_025=3.3%
      at T50. Proxy is adequate.

  - flag: Negative modifier trapping
    status: PASS
    pass: 1a
    finding: >
      Memory slot occupancy at 7.05/8 mean, intensity at 43.3.
      Memory decays normally. No permanent low-satisfaction trapping
      from memory-driven penalties.

  - flag: Autonomy assimilation loop
    status: MITIGATED
    pass: 1b
    finding: >
      Foreign-controlled agents now reach equilibrium at 0.50
      (was negative). Rebellion still occurs but doesn't trap agents
      in deficit->rebel->reconquered->deficit cycle. Autonomy
      improves to 18% below threshold by T100.

# ===================================================================
# CROSS-LANGUAGE SYNC OBLIGATION
# ===================================================================

cross_language_sync:
  - note: >
      _NEED_THRESHOLDS in narrative.py (Python) must stay synced with
      *_THRESHOLD constants in agent.rs (Rust). Both files define
      threshold values (0.3, 0.25, 0.35). No compile-time enforcement.
      If thresholds change, update both.
    files:
      - src/chronicler/narrative.py
      - chronicler-agents/src/agent.rs

# ===================================================================
# UNCHANGED CONSTANTS
# ===================================================================
# See agent.rs lines 185-352 for full list with [FROZEN M53 SOFT] tags.
# All memory intensities, half-lives, utility magnitudes, need
# decay/threshold/weight/restoration rates (except AUTONOMY_DECAY and
# AUTONOMY_RESTORE_NO_PERSC), relationship drift/formation constants,
# and Mule mapping weights remain at original values.
#
# Total tagged [FROZEN M53]: 137 constants (127 Rust + 10 Python).
# Changed: 6 pass-tuned + 7 substrate = 13 total.
# Unchanged: 124 constants at original defaults.
```

- [ ] **Step 2: Verify file exists**

Run: `ls tuning/m53a_frozen.yaml`

- [ ] **Step 3: Commit**

```bash
git add tuning/m53a_frozen.yaml
git commit -m "docs(m53a): frozen constant snapshot with substrate + pass changes + M49 flags"
```

---

### Task 5: Amend Spec and Docs — Clean Up Oracle 5 Scope

**Files:**
- Modify: `docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`
- Modify: `docs/superpowers/progress/phase-6-progress.md`

- [ ] **Step 1: Add deferral note to Oracle 5 spec section**

After the Oracle 5 acceptance criteria in the spec (around line 355), add:

```markdown
**M53 scope narrowing (2026-03-21):** For M53, Oracle 5 covers: creation rate,
type diversity, loss/destruction rate. Deferred to future milestones:
- **Relic conversion impact** (requires religion instrumentation) — candidate for M55
- **Narration visibility** (requires API narration runs) — candidate for M62
- **Mule-origin rate** (requires GP count cross-referencing) — candidate for M55

These deferrals are explicit and dated. The checks remain in the spec as
requirements for the full Oracle 5 contract; they are not removed.
```

- [ ] **Step 2: Update progress doc M53 status**

In `phase-6-progress.md`, update the "M53 validation gaps" section to reflect what this plan addresses vs what remains.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md docs/superpowers/progress/phase-6-progress.md
git commit -m "docs(m53b): narrow Oracle 5 scope, update progress status"
```

---

### Remaining Work for Full M53b Closure

This plan does NOT complete M53b. The following items remain for spec-complete closure:

1. **Sidecar export pipeline:** Build the validation sidecar that exports graph snapshots (edges + memory signatures every 10 turns) and per-turn agent events to files that `chronicler.validate` can consume as post-processing input. This is the prerequisite for items 2-5.

2. **`python -m chronicler.validate` consumer wiring:** Implement `run_oracles()` and `run_determinism_gate()` as consumers of exported sidecar/bundle data per spec architecture (Section 4: "lives outside the simulation pipeline, consumes exported data").

3. **200-seed structural gate (spec 8.2.5):** Run full 200-seed gate with condensed community summaries. Requires sidecar pipeline.

4. **500-turn oracle runs:** Oracle 5 loss/destruction rate target is "by turn 500" (spec line 355). Oracle 3 era inflection needs 500 turns for steady-state detection (spec line 285). Current results are 200-turn only.

5. **Refreshed validation report:** Regenerate `m53b-validation-report.md` from the canonical `python -m chronicler.validate` path, not from the ad-hoc probe.

These items are candidates for a dedicated "M53b Validation Pipeline" milestone or can be folded into the next implementation phase.
