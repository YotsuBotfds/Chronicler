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
| A pilot region can hold up to one turn's harvest above the storage cap between close and the next opening (storage-cap timing) | defect (narrow: Phase 10 granary procurement bought owned grain above the cap that the next opening destroys); the title on offer whole at phase 0.7, before the cap, is an intentional boundary | S1 (A2R) | Reproduced on development worlds (template 7 and 42, procedural 13 and 21, retail everywhere, 200 turns): granaries bought 25.0, 17.6, 305.2 and 42.1 food units of owned grain from above the cap, 36-54% of the owned grain they bought. Rules version 2 with granaries on: `household_retail.phase10_before_reserves` cuts a pilot market's grain above this turn's storage cap before Phase 10 procurement, split pro rata between the commons net of merchants' committed grain (never cut) and owned stock as the native opening cap splits it (owned: flow `cap_overflow`, counter `owned_grain_above_cap_milli`; commons: `commons_grain_above_cap_milli`; once per turn, also when a convoy dumped cargo there first), so no grain above the cap is bought; it runs before the next opening's decay; resource checks PASS on four worlds (measured with the owners-only cut; one world, procedural 13, rerun by the S1 review under the pro-rata rule); version 1 unchanged. War losses come at Phase 5/5b, before the title is eaten, so they reach no cap-doomed stock. Residual boundaries, as without retail: a population that falls between Phase 2 and Phase 10, and commons raised above the cap by an escheat after the tick (pinned `grain_reserves.py` seam). Tests: `test_household_retail_evidence.py::test_owned_grain_above_the_cap_is_lost_before_the_granaries_buy`, `::test_without_granaries_or_within_the_cap_nothing_is_cut`, `::test_the_rl4_cut_splits_the_excess_pro_rata_and_runs_once_a_turn`, `::test_a_convoy_returned_into_a_pilot_market_before_retails_hook_is_cut_pro_rata` |
| Purchases by person are not in the snapshot (person-level purchase evidence) | evidence gap | S1 (A2R) | Rules version 2: household-group cohorts per provisioned pilot region-turn (crew members, their co-resident children, children without a co-resident adult, non-farm adults, other farm households; persons, priced out, paid, refunded, credited, income replaced, crew wages), computed at settlement from the money rows, income receipt, native sample, crew receipts and the Phase 2 roster; aggregates only, each field exact or null with its reason, never an estimate (paid, refunded, credited and income replaced are checked against the region's totals, persons by count; crew wages are exact by construction from the applied receipts and have no total to check). With the `schedule` boundary the wage can be compared at a frozen enrollment: an arm replays another's recorded pilot intervals exactly, closures and reopenings included, subject to the replaying world's controller filter (the first-turn schedule format is approximate once the source closes a region); first-turn replays matched exactly on template 7 and 23 and procedural 7, where no region closed. Tests: `test_household_retail_evidence.py::test_cohorts_partition_the_provisioned_people_and_sum_to_the_region_totals` and its unknown cases, `test_household_retail_evidence_native.py::test_cohorts_on_a_natural_paid_work_run_are_exact_or_marked_unknown`, `::test_replaying_the_paid_arms_openings_in_the_unpaid_arm_reproduces_its_enrollment`; viewer `householdRetailEvidence.test.ts` |
| The labour cost of expeditions is not separated from a no-expedition arm (expedition labour controls) | evidence gap | S1 | — |
| PL3's withheld income does not split granary from workshop crews | evidence gap | S1 | — |
| Five viewer readers return null for both an absent and a malformed record | defect (viewer) | S1 | — |

The wage investigation (A2) starts from checkpoint 3's explanation — the farm income retail
replaces outweighs the wages, and paid crews bring more regions under retail at the `paid_work`
boundary (coverage 0.83 against 0.51 in procedural worlds) — and tests it with fixed eligible
cohorts and a separate enrollment analysis.

## 5. Contract audits (S0)

Full audits (2026-11-06, source identical to `8abc1acb`) are under
[`docs/superpowers/audits/connected-world/`](../audits/connected-world/). Each was written from the
code with file and line evidence; unverified items are marked there. The lead's decisions on their
open questions follow each summary.

### 5.1 A1–A2 income and wealth ([audit](../audits/connected-world/audit-a1-a2-income-wealth.md))

- Agent `wealth` (native f32, checkpointed) is not conserved cash. On development worlds over 200
  turns, real transfers into households (wages and procurement, net of courier fees) are 2–12% of
  inflows; the rest is occupational income the model creates (about 3,700–15,700 coins per world),
  mostly removed by the 2% per-turn decay; each birth adds 0.5. The treasury tax (5% of merchant
  wealth) and the tithe pay the treasury and priests without debiting anyone, so part of the
  treasury that pays wages is itself created. No per-turn check covers agent wealth as a whole.
- Every package payment (wages, food purchases, procurement, remittances, fares, credit) is keyed,
  debits its payer and closes within its package. Defects and issues: estates without heirs are
  destroyed uncounted; income refused at the wealth ceiling is unrecorded; tax and tithe are
  labelled transfers but act as sources; milli-unit transfers applied to an f32 balance leave small
  rounding differences; each package handles ceiling-refused wage residuals its own way; in the
  checkpoint-3 screen design, payment decided which regions were enrolled. No double payment or lost
  refund was found.
- **A2 (exploratory, development worlds only, 40 runs, 0.25 core-hours):** paid and unpaid arms each
  replayed the other's recorded opening schedule (reproduced exactly 10 of 10). With enrollment
  fixed, the wage **raised** money credited to households in 5 of 5 worlds under both schedules;
  enrollment growth alone lowered it in 4 of 5 (about 1,700–2,100 more coins of farm income
  replaced per procedural world). Checkpoint 3's fall in household money comes from enrollment, not
  from the wage. The paid arm's wider enrollment raised priced-out person-turns in 5 of 5; the
  wage's own effect on being priced out was lower in 5 of 5 at the smaller schedule, mixed at the
  larger, lower in 4 of 5 at `all`. 76% of the priced-out are non-farm adults (merchants, soldiers,
  scholars, priests) and children with no parent in the region; paid crew members are 5% and sell
  about twice what they buy. These are development-world observations, to be tested on the CW1
  held cohort.
- **Decisions:**
  - `wealth` stays the one spendable balance; no second balance now (it would double purchasing
    power unless every reader were re-pointed, a default-path change). Model income is replaced by
    paid flows one source at a time, each behind its own switch, with the ledger showing the
    remaining model share.
  - `--wealth-accounting` (opt-in, hybrid-only, appended last among livelihoods switches) observes
    only: with it on, every output except its own record equals it off. Slice A1-1 is Python-only
    (opening/closing snapshots, typed flows from existing receipts, the no-hidden-writer check, the
    PL3 granary/workshop split — RL7); slice A1-2 is a transient native observer itemizing income,
    decay, the ceiling, births and estates (witness layers for the pinned Rust files).
  - New payers (A3, A4, B3, C2, D4) pay through one helper (`chronicler/money.py`) that validates the
    whole bill before moving anything and resolves refused credits by **returning them to the
    payer** unless a named sink is declared and recorded. Existing packages are not refactored
    onto it.
  - The wage question is screened on fixed cohorts: `--household-retail-boundary schedule` replays a
    frozen opening map, plus `all`/`market` with household-group cohorts; `paid_work` remains the
    enrollment story itself. These retail-side additions land after A5 (same files).
  - Recorded for later, with evidence from the ledger first: whether decay should be offset by food
    spending under retail (pilot households arguably pay for food twice); whether the treasury tax
    and tithe should debit their payers (a rules version, with A4's merchant work); relief for
    non-farm adults and for children living apart from parents.

### 5.2 B watershed and infrastructure ([audit](../audits/connected-world/audit-b-watershed-infrastructure.md))

- Rivers barely exist in screening worlds: none in template worlds; 5 of 8 procedural 32×10
  development worlds have none and the rest one short river. Everything keyed to rivers (the
  deforestation cascade, river floods, trade discounts, the migration bonus, the settlement
  attractor) is nearly inert there.
- A complete drainage graph (each inland region drains to its lowest lower neighbour, coastal
  regions to the sea) rebuilt from saved procedural geography reproduces every saved river step on
  10 of 10 worlds checked and gives 8–11 multi-region basins per 32×10 world.
- Water is a bounded per-region index driven by climate rates; nothing is conserved. The cascade
  (−0.05 per deforested upstream region against +0.03 recovery) can pin downstream regions near the
  floor; a tributary's cascade stops at its confluence (under-count, no double count).
- No infrastructure has condition, upkeep or repair; roads give no transport discount (a marked
  placeholder); maritime ignores ports; the river-flood event text claims damage that never happens.
- **Decisions:** the watershed is procedural-only (template worlds have no elevation; `--watershed`
  refuses them clearly) and its screen uses the procedural stratum; `record_only` (a conserved water
  account on the drainage graph with closure checks, no effect) lands first to calibrate, then `flow`
  replaces — not stacks on — the native water climate terms, the irrigation bonus and the cascade,
  deriving the old index from storage (its one pinned `agent_bridge.py` edit carries a reviewed
  layer; a switch change on resume is refused). Irrigation and road condition live in their own
  record keyed by infrastructure stable id (RS2's schema and viewer stay unchanged), repaired with
  the same crews, timber store and L9 envelope, so no budget is spent twice. Ports are deferred.
  In `flow` mode the old river-flood check keeps drawing from the shared environment stream but its
  effect is suppressed and recorded as superseded, so enabling the watershed does not shift other
  systems' draws. Roads gain service-gated range only; a transport discount would be a new bonus
  with its own mode. Constants are calibrated from `record_only` on development worlds only.

### 5.3 C public health ([audit](../audits/connected-world/audit-c-public-health.md))

- Epidemics are **on by default** for new worlds, so today's quarantine is default behaviour: any
  change needs a new opt-in rules switch, and identity is checked with epidemics on and with
  `--no-epidemiology`. The "Default: off" section of `docs/integration/epidemiology.md` is stale.
- Quarantine moves nothing: it multiplies foreign import pressure on all four channels (trade,
  migrants, soldiers, pilgrims) by 1 − efficacy and charges a flat 2 treasury that stands in for lost
  commerce. Two double-count traps: routing plus the multiplier, and the flat charge stacked on real
  route income loss.
- Trade closure is possible without Rust (route filtering in Python; native merchants already replan
  or unwind with RETURNED receipts when an edge disappears); migration closure needs a small native
  input. In the two pilot bundles migrants carried most hybrid cross-polity arrivals (direction only).
- The contact ledger is a decaying stock, not dated contacts; information is instant and omniscient
  today; nothing exists for disease care (health care covers rural injury only).
- **Decisions:** `--quarantine-mode none|cost_only|closure` (omitted = legacy); closure removes the
  multiplier for closed channels and replaces the flat charge with an enforcement cost; imports keep
  reading the decayed contact stock (closure stops new contacts — the lag is a real effect to
  measure); closures target only polities with reported outbreaks (information available at the
  time); relief grain convoys are exempt, with the exemption recorded; migration closure (C1b) is a
  separate, later native slice; care (C2) lowers the epidemic's own fatality, never a second
  mortality authority. Armies and hostages are not restricted by a closure (intentional boundary);
  the legacy multiplier stays the default reference until an owner promotion decision; C2's
  funding authority and C1b's gate placement are decided when those slices start.

### 5.4 D institutions, war, attribution and the owned-stock lifecycle ([audit](../audits/connected-world/audit-d-institutions-war-owned-stock.md))

- RL1 is a defect (owned stock is destroyed once per turn because retail infers conquests from an
  integer turn; the war-loss record names the later controller), reachable only with
  `--no-campaigns`. RL2 is a missing capability (today's commons "requisition" destroys food; plunder
  is minted treasury). RL3 was not reproduced as stated: with `--agents hybrid` both hooks run; without
  it a saved retail world fails with an uncaught traceback and a saved L2-only world runs silently in
  aggregate mode.
- Soldiers never move natively: they eat at home, levies farm at home and are titled for it, and
  army rations are minted on top. There are two war-death authorities (campaign casualties and the
  native ×2 Soldier mortality at war). An inexact resume can keep a roster whose ids now name
  strangers (code path, not reproduced).
- No person pays tax; at least six channels already turn grievance into influence; a restored civ
  reuses the dead civ's index and name.
- **Decisions:** owned stock follows the commons once per war event (retail rules version 2,
  `--household-retail-rules 1` reproduces checkpoints 2–3; the CLI key lands now with a lead-owned
  layer); treaty cessions keep conquest handling and are recorded as a D4 requisition question; a
  region without a controller confiscating claims to the commons is an intentional boundary; the
  timber store untouched by war is an intentional boundary until B/A4; soldiers' double-counted food
  is a documented boundary until D4, and D3's soldier-movement work waits for D4; new grievances must
  replace a proxy, not stack; the stale `agent_mode` after an agents-off legacy resume is recorded as
  an open default-path item, not changed.

### 5.5 E verification playbook, seed registry and observability ([audit](../audits/connected-world/audit-e-verification-playbook.md))

- The per-slice playbook (V0–V13) is the audit's Part 1: lane clone and venvs, preflight,
  enrollment, offline lane, native, feature-off identity against both references, enabled exact
  resume, catalog matrix, viewer and browser journeys, narration audit, held screens, profiling,
  PR/CI/merge, ledgers.
- Traps: the shared native venv's editable install points at the shared checkout (every lane exports
  `PYTHONPATH=$WT/src`); `checkpoint_identity.py` records no source or extension identity (lanes
  record it); every new switch edits pinned `batch_manifest.py` and its test.
- Pinned commonly edited files: `simulation.py`, `main.py`, `models.py`, `agent_bridge.py`,
  `ecology.py`, `batch_manifest.py`, `ffi/mod.rs`, `economy.rs`, `viewer/src/types.ts` and others;
  not pinned: `feature_catalog.py`, `household_retail.py`, `epidemiology.py`, `infrastructure.py`.
- The five null-only viewer readers are `repairProjectsAt`, `timberStockAt`, `remittancesAt`,
  `foodAllocationAt` and `granaryStorageAt`. Narration citations are checked for the snapshot, not
  the record.
- **Decisions:** lanes may build a provisional witness layer on their own branch; the lead
  regenerates one integrated layer per slice at integration. A new generic screen runner and a
  data seed registry (lane E1) replace copying the frozen productive-recovery runner. Feature-off
  identity uses `turn_speed_identity.py` with each side's own `git archive` tree and extension.

### 5.6 A3 workshop economics ([audit](../audits/connected-world/audit-a3-workshop-economics.md))

- A workshop today is a state-owned asset (the ruler pays build and upkeep into a declared sink)
  with a crew of up to 8 named city farmers; workshop payroll adds a firm by stable site id with
  cash, arrears and closure after 6 insolvent turns, whose only customer is academies paid from the
  treasury. Free or model-created parts: raw timber and ore are never paid for; 47.5% of the firm
  region's output is used free before the firm takes title; sites without a firm still produce with
  free inputs; the asset subsidy is off the firm's books. No money is minted into firm cash.
- Non-academy demand exists (0.01 wares per head per turn) but is drawn free from the shared stock.
- Central risk (development world): the wares price beat the raw-material price in only 12.6% of
  operating turns at firm cities; paid inputs will close most firms unless A4 opens scarce markets.
  This is reported as found, not tuned away.
- **Decisions:** `--workshop-economics` (requires `--workshop-payroll`; modes `market`,
  `free_inputs`, `academy_only`) with the shared `money.py` payment seam; inputs priced at the
  region's existing market price for the raw good and paid to the ruler as owner of the shared stock
  (producers as sellers later); the ruler keeps carrying asset build and upkeep, recorded as a
  subsidy in the ledger; one-off starting capital from the ruler, no rescue; households buy by id
  from adults' wealth; the module runs before `wealth_accounting`; A3-1 appends one native transfer
  purpose (`wares_purchase`); A3-2's native column that keeps firm output out of the shared stock is
  batched with A4's merchant payment operation into one later native build. CW2 runs after A3-2.

## 6. Turn-order table

Maintained as slices land.

## 7. Seeds

Development worlds (inspected freely) are unchanged: template 1, 3, 7, 9, 11, 23, 42;
procedural 7, 11, 13, 17, 21, 31, 302, 303; viewer QA batches template 12, 13, 14. Every cohort
below is reserved before any program run and checked disjoint from the full historical registry
(audit E section 5.3: every earlier held, pilot and development cohort, the restricted gate ranges
template 42–241 and procedural 42–141, and probes up to 1000–1999) by the program screen runner
before each run.

| Use | Template (8 × 4) | Procedural (32 × 10) |
| --- | --- | --- |
| Timing pilot (shared with productive recovery; never held) | 5 | 19 |
| CW1: S1 accounting and wages | 731–736 | 831–836 |
| CW2: S2 workshop economics and owned-stock lifecycle | 741–746 | 841–846 |
| CW3: S3 watershed and infrastructure (procedural stratum; template refused) | 751–756 | 851–856 |
| CW4: S3 quarantine and public health | 761–766 | 861–866 |
| CW5: S4 trade, forest and water, care, attribution, requisition | 771–776 | 871–876 |
| CW6: S5 adaptive decisions, cross-border organization, war; the integrated evaluation | 781–786 | 881–886 |
| Reserve (a held-run failure needs a new cohort) | 791–796 | 891–896 |

## 8. Baseline (S0, 2026-11-06)

- `main` = `8abc1acb3adf978ea212a570fb1dfbbfe9723ec3`; native extension built fresh from it
  (`maturin develop --release --locked`, 3 min 14 s on 4 cores): SHA-256 `101a4cd5…`, identical to
  the checkpoint-2/3 extension; `check_python_env.py --expect native` PASS.
- Offline oracle lane: PASS, 63 chunks in 295.5 s; slowest chunk 32.4 s of 110 s (under concurrent
  audit load).
- Feature-off reference outputs (`turn_speed_identity.py run`, 9 cases): 74 s; a second run compared
  against the first: 9 cases, 399 files, 0 differences.

## 9. Recovery

A reclaimed container does not restart itself. To resume: clone `main` (or fetch), read this
plan and the board's `next` field, check out the branches the board lists under `lanes`, rebuild
the native extension into a fresh native venv per `docs/DEVELOPMENT.md`, verify its SHA-256
against the board, and continue the named next task.
