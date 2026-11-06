# Connected-world program — plan of record

Owner instruction (2026-11-06, after PR #82): take ownership of the next major development
program end to end — a connected livelihoods and trade economy (A), living watersheds and
infrastructure (B), public health and the cost of protection (C), institutions, war and human
consequences (D), and stories, integration and evidence (E) — integrating and evaluating each
stage and continuing across stage boundaries. The owner's amendment of the same day sets the
sequencing and execution rules summarized in section 1. Board:
[connected-world.json](../progress/connected-world.json).

Terms (owner instruction and amendment):
- branches, commits, PRs; merges of this program's slices are authorized once an independent
  review from the actual source, diff, specification and tests is done, premerge Tests are green
  on the reviewed head, and main CI is verified afterwards. `main` has no enforced branch
  protection, so the rule is explicit: merge only through a PR with green checks; never push to
  `main` directly; no force-push;
- new behaviour opt-in and off by default; feature-off identity to the original reference
  `8abc1acb3adf978ea212a570fb1dfbbfe9723ec3` **and** to the preceding integrated `main`;
- any intentional change to default-path output, bug fixes included, goes behind an opt-in switch
  or a rules version and is recorded for the owner's later default-promotion decision;
- no default promotion; the full 200-seed gate and the procedural qualification gate stay
  restricted. Bounded held screens, including procedural worlds, are authorized;
- no purchases, new paid credits, deployments, credential or sharing changes; no paid narration
  APIs (provenance is tested without the API narrator);
- the preserved desktop foundation line is left untouched.

## 1. Execution rules

- **Scope.** The whole A–E program is the assignment. The sequence below orders work; it is not
  a set of stopping points. If interrupted, leave a coherent checkpoint and the exact next task.
- **Failures block the affected merge or run, not the program.** A failed identity check, a
  broken old bundle, red CI or an exhausted screen budget is diagnosed and repaired within scope
  while independent lanes continue. If `main` goes red, feature merges freeze until it is
  repaired or reverted through a PR.
- **Pins.** Never rewrite a historical pin to bless changed source; use the reviewed
  exact-inverse witness procedure (`docs/DEVELOPMENT.md`, "Before refactoring") and correct test
  enrollment. Run `scripts/refactor_preflight.py --git-diff origin/main` before every PR.
- **Offline lane.** The 110-second chunk limit stays. A timeout is investigated and rerun under
  controlled load, never fixed by raising the limit.
- **Resources.** The cloud container has 4 cores, 15 GB of memory and about 30 GB of writable
  disk. Native builds are isolated (one native venv per checkout that changes Rust) and run at
  most two at a time; heavy jobs (oracle lane, identity runs, screens) are scheduled so they do
  not contend.
- **Shared contracts (one integration owner, the lead):** stable identity, budgets and payers,
  displacement, schemas, turn order, native hooks/FFI and witness layers. Lanes propose changes to
  these; the lead integrates them.
- **Every slice carries** its tests, viewer evidence and evaluation; nothing is deferred to a
  final program.

## 2. Shared contracts

- **Turn order.** One table (section 6, maintained as slices land) gives every phase a program
  slice adds or changes, its position relative to existing phases and its owner.
- **Identity.** Region identity is its index in `world.regions`, civilization identity its index
  in `world.civilizations`, agents by stable id. New entities (firms, shipments, public works,
  branches, quarantines) get stable, checkpointed, never-reused ids.
- **Randomness.** Deterministic, system-specific draws (`stable_hash_int`-style namespaces, as
  epidemiology uses) that never consume an unrelated stream, so enabling one switch does not
  perturb another system's draws.
- **Modes.** Hybrid-only experimental mechanisms are acceptable when unsupported modes are
  rejected clearly at startup and on resume.
- **Authorities.** Reuse the existing injury (health care episodes), work, mortality (epidemic
  deaths, casualty path), food and resource authorities; never a competing store.
- **Switches.** Every new switch is registered in `feature_catalog.REQUIREMENTS` with its
  prerequisites; the compatibility matrix is generated from the catalog and checked by tests,
  including invalid combinations and compatible all-enabled checkpoint cases. No target count.
- **Compatibility.** Supported old bundles and historical imports stay loadable; unsupported
  resumes and malformed data are rejected explicitly.

## 3. Sequence (dependency-aware queue)

The detailed packages, seams and tests come from the contract audits (section 5). Lanes run in
parallel where they do not share a contract.

| Slice | Contents | Depends on |
| --- | --- | --- |
| S0 | Baseline verification; board; dependency map; seed registry; contract audits A1–A2, B1, C1, D2, A5/D4, E | — |
| S1 | A1 income and wealth accounting; A2 wage vs `paid_work` enrollment with fixed cohorts; recorded-limit dispositions that need no new mechanism | S0 |
| S2 | A3 workshop economics; A5 owned-stock lifecycle (siege, occupation, conquest, death, inheritance, migration, same-turn transitions) | S1 accounting |
| S3 | B1–B3 initial watershed and infrastructure slice; C1 quarantine with dated effects and costs | S1 accounting (repair budgets, trade costs) |
| S4 | A4 merchants and owned cargo; B4 forest cover and water; B5 water/infrastructure viewer; C2 care and sanitation capacity; D2 attribution; D4 requisition, restitution, reconstruction | S2, S3 |
| S5 | A6 adaptive livelihood decisions; D1 cross-border branches and guild cooperation; D3 war's human consequences; C4 evidence-informed public-health choices | S4 |
| E | Linked histories, story worlds, provenance, identity/checkpoint coverage, browser journeys, profiling — carried in every slice; an integrated evaluation at the end | every slice |

## 4. Recorded limits carried from productive recovery

Each is classified (defect / missing capability / evidence gap / intentional boundary) and given
a documented, tested disposition in the slice named.

| Limit (checkpoints 2–3) | Class | Slice | Disposition |
| --- | --- | --- | --- |
| Two conquests in one turn destroy owned stock once (same-turn conquest vs duplicate processing) | defect (reachable with `--no-campaigns`) | S2 (A5-1) | Retail rules version 2 (default of a new state; `--household-retail-rules 1` keeps checkpoints 2–3): `apply_region_conquest` calls `household_retail.on_conquest` at each conquest, with actor and victim, so two conquests take the share twice like the commons; the turn-inferred path became a "conquest not observed" check. Tests: `test_household_retail_war.py::test_two_conquests_in_one_turn_take_the_conquest_share_twice_like_the_commons`, `::test_one_conquest_seen_at_phase2_and_before_the_tick_is_applied_once`, `::test_a_conquest_the_hook_did_not_see_is_refused`, `::test_rules_1_keeps_the_once_per_turn_conquest_of_checkpoints_2_and_3` |
| Occupation and siege do not requisition owned stock | missing capability | S2 (A5-1), S4 (D4) | Rules version 2: `war.occupation._requisition` (each siege turn 0.85, occupation start 0.8) calls `household_retail.on_war_loss` with cause and actor, once per event, as destruction like the commons; transfer to army rations and restitution stay D4; treaty cessions and annexations keep the commons' handling (open D4 question); the timber store and a controller-less region's confiscation are intentional boundaries. Tests: `test_household_retail_war.py::test_a_requisition_takes_the_commons_share_of_owned_stock_once_per_call`, `::test_siege_turns_and_an_occupation_start_reach_owned_stock_through_the_war_path`; natural sieges, occupation and cession resumed exactly in `test_household_retail_war_native.py` |
| A legacy JSON state-file resume runs neither L2 nor retail hooks | evidence gap (with `--agents hybrid` both run) + defect (a saved L2 outside hybrid ran silently inert; a saved retail world raised a traceback) + intentional boundary (an inexact resume closes id-bound claims) | S2 (A5-1) | A saved L2 outside hybrid is refused with a `--no-food-allocation` hint; both saved-switch refusals exit cleanly (`LivelihoodsRefusal`, no traceback). Open item for the lead: the stale `world.agent_mode` on the default path. Tests: `test_household_retail_war.py::test_a_saved_food_allocation_outside_hybrid_is_refused_cleanly_with_its_hint`, `::test_a_legacy_resume_of_a_saved_retail_world_without_hybrid_exits_without_a_traceback`; `test_household_retail_war_native.py::test_a_legacy_state_file_resume_with_hybrid_settles_every_resumed_turn` |
| A pilot region can hold up to one turn's harvest above the storage cap between close and the next opening (storage-cap timing) | pending audit A | S1/S2 | — |
| Purchases by person are not in the snapshot (person-level purchase evidence) | evidence gap | S1 | — |
| The labour cost of expeditions is not separated from a no-expedition arm (expedition labour controls) | evidence gap | S1 | — |
| PL3's withheld income does not split granary from workshop crews | evidence gap | S1 | — |
| Five viewer readers return null for both an absent and a malformed record | defect (viewer) | S1 | — |

The wage investigation (A2) starts from checkpoint 3's explanation — the farm income retail
replaces outweighs the wages, and paid crews bring more regions under retail at the `paid_work`
boundary (coverage 0.83 against 0.51 in procedural worlds) — and tests it with fixed eligible
cohorts and a separate enrollment analysis.

## 5. Contract audits (S0)

Filled in from the audit lanes: A1–A2 income and wealth; B watershed and infrastructure; C public
health; D institutions, war, attribution and the owned-stock lifecycle; E verification playbook,
seed registry and observability.

## 6. Turn-order table

Maintained as slices land.

## 7. Seeds

Development worlds (inspected freely) are unchanged: template 1, 3, 7, 9, 11, 23, 42;
procedural 7, 11, 13, 17, 21, 31, 302, 303; viewer QA batches template 12, 13, 14. Every cohort
below is reserved before any program run and checked disjoint from the full historical registry
(section 5, audit E) by the program screen runner before each run.

## 8. Recovery

A reclaimed container does not restart itself. To resume: clone `main` (or fetch), read this
plan and the board's `next` field, check out the branches the board lists under `lanes`, rebuild
the native extension into a fresh native venv per `docs/DEVELOPMENT.md`, verify its SHA-256
against the board, and continue the named next task.
