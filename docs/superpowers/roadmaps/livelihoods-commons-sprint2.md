# Livelihoods, commons and collective choices — sprint 2 plan (L5–L9)

The owner instructed on 2026-11-05 that the rest of the roadmap continue end to end, including
L5–L9 with their viewer, integration and evidence work. Sprint boundaries are checkpoints,
not stops. Rules carried over:

- branches and draft PRs only;
- every feature off by default;
- no merge;
- no 200-seed or procedural qualification gate without the owner's approval.

This sprint stacks on sprint 1. Its branch is `claude/livelihoods-sprint2`, based on the
sprint-1 head after the review fixes. Its draft PR targets
`claude/livelihoods-commons-sprint1`, so the PR shows only sprint-2 changes and CI runs on it.
The board is [livelihoods-commons-sprint2.json](../progress/livelihoods-commons-sprint2.json).
Sprint 1's plan, contracts and witness procedure still apply
([sprint 1 plan](livelihoods-commons-sprint1.md), sections 2–4). New pinned-file hooks get
further layers in `scripts/testing/livelihoods_sprint_witness.py`.

## Sprint-1 review checkpoint

An independent review of sprint 1's acceptance evidence found six gaps. All were fixed before
sprint 2 started (layer `s1r`):

1. Work reservations were kept apart only by disjoint predicates. A native per-turn registry
   is now the single authority:
   - crews are planned after health work exists;
   - teaching excludes people in the registry;
   - the tick refuses an overlap;
   - a real-path test runs workshops with health care, academy teaching and grain storage.
2. Grain storage and workshops could spend the same coins. The workshop budget now subtracts
   storage's pending bill, and settlement re-checks the treasury.
3. Convoys had no cost-retaining risk ablation. Added `livelihoods.convoys.threat_scale`, plus
   a test isolating delay's effect on actual granary release.
4. Food allocation recorded unknown relief as zero. It now records it as unknown, and the
   lifecycle unit tests are added.
5. Screen artifacts lived only in scratch. The runner (`scripts/livelihoods_screens.py`) and
   the per-world metrics are now committed.
6. The L1 resume, and the case of a crew member dying or leaving, now have tests.

## Waves and lanes

| Wave | Package | Lane | Native? | Depends on |
| --- | --- | --- | --- | --- |
| 2A | L5 named learners, participation, skill transmission | learners | yes | L1 work registry, academy services |
| 2A | L6a workshop payroll with an actual public customer | finance | yes (wages, income share) | L1B |
| 2A | L8 commons rules with enforceable costs | commons | Python (+ optional ecology) | L3 |
| 2B | L7 costly voluntary relocation and receiving pressure | learners lane, after L5 | yes | L2, L6a wealth-transfer surface |
| 2B | L9 local collective budgets and material bargaining | commons lane, after L8 | Python | L1, L2, plus L5/L6/L8 services as they land |
| 2B | L6b household food purchases (if responsibly feasible) | finance lane | yes | L2, L6a, explicit inventory title |

L10 viewer slices and L11 evidence attach to every landing, as in sprint 1. Stretch ideas
(watershed, draft animals, cargo cover, apprenticeship/diaspora, reconstruction) follow L5–L9
only if they stay bounded. Each starts with a written design.

## Ownership

- **Lead (this session):** native hot files (`ffi/mod.rs`, `ffi/schema.rs`, `tick.rs`,
  `economy.rs`, `pool.rs`, `lib.rs`), `models.py`, `simulation.py`, `main.py`,
  `agent_bridge.py`, `economy.py`, `tuning.py`, `livelihoods.py` and its state container,
  `viewer/src/types.ts` and shared viewer mounts. Also witness layers, manifests, CHUNKS,
  the board and the landing order.
- **Workers:** each owns its package's new modules, tests, docs and viewer reader/component.
  - A worker may edit a shared hot file in its own branch only as a narrow, listed hook.
  - The lead merges, resolves conflicts, rebuilds and adds the layer.
  - Each worker builds native code only into its own venv and target directory.
  - At most two native builds run at once.

## Shared seams this sprint adds

- **Work registry** (sprint-1 review): `AgentSimulator.reserve_work(turn, category, rows)`,
  with categories `workshop` (0) and `learning` (1); categories are append-only. Payroll
  crews remain workshop reservations.
- **Wealth transfer** (L6a, reused by L7): one native method credits or debits stable agent
  ids exactly once, keeps unapplied residuals at wealth limits, and records a typed receipt.
  No firm or agent is ever placed in finance's civilization-borrower field.
- **Income share replacement** (L6a): a one-tick per-agent deduction of ordinary
  occupational income for paid workshop time, consumed by the wealth phase, like
  `health_work_loss`. It is never stacked on top of wages.

## Evidence and budget

- **Development cohort:** template seeds 1–3.
- **Held cohort for sprint 2, fresh and frozen now:** template seeds 301–306 and procedural
  (32 regions × 10 civs) seeds 401–406, 200 turns.
- **Aggregate screen budget:** 2.0 core-hours, at most 3 concurrent processes, ≤ 6 GiB
  transient disk. Arms per package are off, on and a cost-retaining ablation. Interactions:
  learning × workshop payroll, commons × workshop timber demand, budgets × relief and
  maintenance, and relocation × food allocation. One all-switches cohort.
- **Per-slice checks:**
  - feature-off identity (`turn_speed_identity`) against the sprint-1 head;
  - enabled exact resume (`checkpoint_identity`);
  - bounded offline lane, `cargo test`, native module tests;
  - viewer tests, lint and build, and a browser journey;
  - PR CI.

## Handoff (2026-11-05)

### Delivered

Integrated on `claude/livelihoods-sprint2` (draft PR #74, stacked on #73). Every switch is off
by default.

| Package | Switch | Lane head | Integration | Layer |
| --- | --- | --- | --- | --- |
| L5 named learners | `--learning-cohorts` | `0075103d` | `a26954e5` | l5 |
| L6a workshop payroll | `--workshop-payroll` | `c3356f16` | `e555b0db` | l6 |
| L7 relocation costs | `--relocation-costs` | `13c3ad3e` | `83e21af5` | l7 |
| L8 commons rules | `--commons-rules` | `494460d7` | `727ed5dc` | l8 |
| L9 local budgets (+ wardens, teaching supplies) | `--local-budgets` | `591b0350`, `1461686e` | `60b63f25`, `2441edb5` | l9 |
| L6b household purchases | — | `9fbe6585` (design) | `90591762` | — |

L6b is left open, as the roadmap allows. Real retail needs producer title, per-agent
inventories and income replacement in the native economy. The bounded granary-only fallback
would not test whether lack of cash reaches food access
([design note](../../integration/household-purchases-design.md)).

### Review fixes before the held cohort

Each fix has a regression test that fails on the previous code.

- `e7d18444`: L9 counted L4 convoy spending twice. Found by the timing pilot.
- `957f47c9`: L8 read the Commons Management funding ratio before it was set each turn.
- `aea7972f`, from an independent review:
  - the screen runner missed L7's snapshot key;
  - L6a shared wage cash with dead workers;
  - L7 assistance sat outside L9's one budget;
  - a workshop deferral reason was wrong.

### Evidence on the final source (`aea7972f`, native extension `70587268…`)

- Feature-off `turn_speed_identity` against pre-sprint `main` with its own extension: 9 cases,
  399 files, 0 differences.
- Enabled exact resume, `checkpoint_identity` `hybrid_s42_long` with every switch on and
  assisted relocation: PASS at 11 resume points on this commit. An earlier commit passed at
  33 more, including points inside live firms, cohorts and commons rules.
- Bounded offline lane PASS; `cargo test` 1,235 passed; sprint native suites pass.
- Viewer: 126 files, 1,256 tests, lint and build pass.
- Browser journey on the production build at desktop and phone width: every panel, re-dated
  on rewind, no overflow, no console errors, and no tab for feature-off bundles.
- Held screens: 21 arms × 12 worlds, 0 failed, 1.08 of the 2.0 core-hours.
  [Results](../progress/livelihoods-sprint2-screens.md).
- Not run: the 200-seed and procedural qualification gates.

### Known limits carried forward

- L5: delivered teaching, not learners or supplies, limits completions.
- L7: assistance is reserved before the tick and charged in Phase 10. Refusals are recorded;
  L9 reserves the ceiling.
- L8: clearing, at 10–20× extraction, is outside the rule's reach. A clearing moratorium needs
  Python and native ecology parity and a declared cost (proposal in
  [commons rules](../../integration/commons-rules.md)).
- L9: contested choices are rare. Its relief side delivers little while workshops lose
  output.
- Granary condition: the base storage policy maintains nothing, so end condition is 0 in every
  arm.

### Recommended next candidates

From the roadmap's stretch notes: at most two, ranked by activation, narrative payoff,
dependencies and performance. Neither is started. Each needs a new owner instruction and a
written design first.

1. **Apprenticeship in workshops, then knowledge loss and diaspora remittances.**
   - Activation: the screens show L5 is limited by academy teaching seats. Workshop crews
     already exist in the shared work registry, and payroll firms pay wages through the
     native transfer seam. Crew-taught apprentices would add teaching where work already
     happens, instead of a second school model.
   - Later remittances can reuse L7 movers and the wealth transfer.
   - Cost: low; one native consumer in the wealth phase.
2. **Postwar reconstruction and veteran reintegration.**
   - Wars and occupation are frequent, so activation is high.
   - Reconstruction is a consumer of the systems built here: repair work through the
     registry, funding through L9 envelopes, skills through L5, and households through L2
     and L7.
   - Payoff: visible recovery stories.
   - Needs care not to add a second combat event generator.

Deferred: watershed storage (needs conserved water units and forcing first), draft animals
(needs reconciled herds), and private cargo cover (needs L6b-style private title and
voyage identity).
