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
