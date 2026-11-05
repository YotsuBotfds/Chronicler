# Livelihoods, commons and collective choices — sprint 1 plan

Lead-owned plan for the bounded sprint **L0 + L1–L4**, each with its L10
viewer slice and L11 evidence. L5–L9 and the stretch ideas are next-sprint
design notes only. The operational board is
[livelihoods-commons-sprint1.json](../progress/livelihoods-commons-sprint1.json);
material milestones also go to [phase-6-progress.md](../progress/phase-6-progress.md).
This plan is the sanitized repository copy of the owner's private revision-5
planning packet (canonical prompt SHA-256 `1804c3b2…0b94284`); private storage
locators and logs are intentionally omitted.

Authority (owner instruction, 2026-11-05): execute the revision-5 sprint end to
end. Taken as: implement L0 and L1–L4 with their L10/L11 work, commit and push
sanitized source/tests/docs to non-main branches, open a draft PR. Not
authorized: merge, approval, writes to `main`, default changes, the 200-seed or
procedural qualification gates, Drive sharing changes, purchases, deployment,
or L5–L9 implementation.

## 1. Baseline (L0)

| Item | Value |
| --- | --- |
| Fetched `main` | `64863f1274e400c3898972fe0cd5df510d3bb06f` (not advanced at 2026-11-05T04:31Z) |
| Tree | `1b0cd0dcb5e5433af6aa4429a65e5dae2ec4e89e` |
| Main CI | run 41926433490, push, success, nine jobs (rechecked 2026-11-05) |
| Cleanup | PRs #71/#72 merged; not redone. CONTINUATION.md "open/unmerged" wording is stale. |
| Container | 4 cores, 15 GiB RAM, 30 GiB free disk; Python 3.13.18, cargo 1.97.0, Node 22.23.4 |
| No-native lane | `.venv`, `check_python_env.py --expect no-native` PASS |
| Native lane | `~/.venvs/chronicler-native`, fresh `maturin develop --release --locked` of the baseline in 210 s, `--expect native` PASS |

## 2. Ownership and hot-file reservations

One lead owns integration. Workers deliver feature patches in isolated
worktrees and never edit witness chains, `native_shards_manifest.json`,
`tests/test_native_ci_shards.py` or offline `CHUNKS`.

| Seam | Owner |
| --- | --- |
| `ffi/mod.rs`, `ffi/schema.rs`, `tick.rs`, `economy.rs`, `lib.rs`, `pool.rs` | lead (native owner); L1A lands before L2's native hooks |
| `src/chronicler/economy.py` (craft reporting, woodland timber capacity) | lead (shared Python economy owner) |
| `models.py`, `simulation.py`, `main.py`, `agent_bridge.py`, `batch_manifest.py`, `household.rs`, `viewer/src/types.ts` | lead |
| `ecology.rs`, `ffi/ecology_sim.rs`, `ecology.py`, `production_ledger.py`, `nomads.py`, new timber module | L3 ecology lane |
| New convoy module(s); hooks into `grain_reserves.py`/`simulation.py` as patches | L4 convoy lane |
| Witness layers, manifests, CHUNKS, board, landing order | lead only |

`public_grain_shipments.py`, `public_grain_shipments_state.py`,
`grain_storage.py`, `food_accounting.py`, `learning_services.py` and
`teaching_work.rs` are byte-pinned as `new_files` of historical inverse
fixtures. New behavior lives in new modules; those files are not edited.

## 3. Witness-layer landing procedure

Preflight on the planned shared paths (2026-11-05) found enforced inverse-chain
pins for `simulation.py`, `models.py`, `economy.py`, `agent_bridge.py`,
`main.py`, `grain_reserves.py`, `food_accounting.py`, `economy.rs`, `tick.rs`,
`ffi/mod.rs`, `ffi/schema.rs`, `household.rs`, `lib.rs`, `pool.rs` and
`viewer/src/types.ts`, and none for `ecology.py`, `ecology.rs`,
`ffi/ecology_sim.rs`, `guilds.py`, `cities.py`, `production_ledger.py`,
`agent.rs` or `snapshot_registry.py`. No pin is not a safety proof; the
preflight's blind spots (runtime-built paths, `inspect.getsource`, whole-tree
digests, behavioral goldens, Rust/TS module graphs) still need the test lanes.

1. Run `scripts/refactor_preflight.py` on every proposed path before editing
   and `--git-diff 64863f1` after.
2. Keep hook edits in pinned files small, contextual and few; new behavior goes
   into new modules.
3. The lead adds one reviewed exact-inverse layer per landing
   (`tests/fixtures/livelihoods_<landing>_source_inverse.json`) through
   `scripts/testing/livelihoods_sprint_witness.py`, following
   `scripts/testing/reviewed_main_witness.py`: each patch is a literal
   `(old, new)` pair with lexical context on both sides that occurs exactly
   once; the layer records the full current digest, the patches and the target
   historical digest (the baseline bytes). Layers apply newest first. Unknown
   digests pass through unchanged so the older layers keep rejecting them; the
   sprint's own test is strict and checks mutation rejection.
4. Every existing chain entry point (`before_gallery_candidate` and the other
   `before_*` functions that receive current source, plus the reviewed main
   witness functions) first applies the sprint projection. No historical hash
   is rewritten.
5. The lead enrolls new test modules in `native_shards_manifest.json`, the
   `additions` map/module count in `tests/test_native_ci_shards.py` and, when
   offline-safe, a bounded `CHUNKS` slot with headroom. Baseline: 348 modules,
   623 expected successful subtests.

## 4. Interface packet v1

Defined only for the first consumers; each has at least two concrete consumers.

1. **Work request/result** (`livelihoods.work`): source turn, stable agent ID,
   region index, settlement ID, category, available fraction, allocated
   fraction, realized fraction, exclusion reason, affected ordinary-income
   share. Exclusion order: dead/child/non-farmer/rural → army → trip → already
   assigned (care, storage, teaching) → cap. Fractions never exceed
   availability. Consumers: L1 workshop crews and the existing storage/teaching
   requests through compatibility adapters.
2. **Material transfer**: transfer ID, source/destination account (kind,
   identity), good, requested/committed/delivered/lost quantity, phase/turn,
   status. Consumers: L1 protected inputs, L2 allocation receipts, L4 convoy
   cargo.
3. **Money transfer**: typed payer/payee or named sink, amount, applied,
   residual, replay identity. Consumers: L1B upkeep/construction, L4 escort
   cost.
4. **Observations**: version, source/capture turn, applicability,
   known-zero versus unknown, coverage. Consumers: all four inspectors.

## 5. Workshop funding comparison (60-minute timebox)

Timebox opened 2026-11-05T04:35:41Z. Evidence: source reading of
`guilds.py`, `guilds_state.py`, `cities.py`, `domestic_credit.py`,
`grain_storage.py`, `learning_services.py`, plus three baseline pilots
(template seeds 7 and 11, procedural 8-region seed 7; 150–200 turns, hybrid).

| | Public treasury (controller civ) | Guild purse (`guild.wealth`) |
| --- | --- | --- |
| Account | `civ.treasury` (int), projected via `_treasury_budget`/`projected_treasury` | `Guild.wealth` (float), one per city that founded a craft guild |
| Observed balance at turn 150–200 | 242–1396 per civ | 0.2–7.2 per living guild (median ≈3); 0–2 living guilds in 2 of 3 worlds dissolved one or more |
| Source of funds | taxes/income, existing public spending | 5% (10% with monopoly) of city commerce, 2%/turn decay ⇒ steady state ≈2.5× per-turn commerce |
| Construction/upkeep debit | existing prepare/finish pattern (grain storage, academy services) charges once after native success, accumulator `keep` | new debit; competes with `wall_help` (Phase 10) and domestic-credit lending of guild purses |
| Recipient | disclosed public expenditure sink; no wages | sink as well (no private payee exists without L6) |
| Output title | shared regional inventory, as legacy craft output and public procurement | shared regional inventory — the guild would pay without owning output |
| Worker income | unchanged: crews use already-diverted urban farm time; no wage | unchanged; same |
| Failure/replay | grain-storage lifecycle: refuse on owner change mid-turn, no charge on failed tick, receipt per turn | must be built and tested |
| Conquest/ownership | payer follows region controller; arrears and asset persist with the site | guild survives conquest but may dissolve (20 turns below masters floor) |
| Circularity | none | guilds are founded from wares output, which the workshop itself changes |
| Missing prerequisites | none beyond L1A | settlement, priority against walls/credit, dissolution handling |

**Decision (staged route).** Stage 1 (L1B this sprint): public-treasury pilot.
The controller civilization pays construction and upkeep as a disclosed public
expenditure sink after successful native work; no wages; output enters the
region's shared inventory; ordinary farmer income is unchanged because crews
only use already-diverted urban time. Guild co-funding is deferred, not
rejected: at observed purse sizes it cannot fund a crew, its debit would
compete with wall and credit claims, and its existence depends on the same
wares output. It needs no L6 payroll, so it can be reconsidered when a
measured workload shows purses that cover upkeep. Private ownership of output
and wages remain L6.

## 6. Aggregate screen compute budget (frozen before screens)

Pilot cost (baseline source, one process): template 4-civ world 7–14 s per
150–200 turns, peak RSS 208 MiB, 5 MB output; procedural 32 regions/10 civs,
200 turns 17.6 s, 394 MiB, 15 MB.

| Item | Budget |
| --- | --- |
| Total CPU for all screens | 1.5 core-hours (includes 25% contingency) |
| Wall clock | ≤ 45 min with 3 concurrent processes |
| Peak RAM | ≤ 3 × 0.8 GiB |
| Transient disk | ≤ 4 GiB (raw outputs deleted after metric extraction; example worlds kept) |
| Cohorts | 4 package screens, 3 interaction comparisons (work × food allocation, timber use × workshop demand, convoy disruption × relief release), 1 all-in-sprint cohort |

Development cohort: seeds 1–3 (template). Held cohort, frozen now and not
inspected during tuning: template seeds 101–106 and procedural (32 regions,
10 civs) seeds 201–206, 200 turns. Arms per package: off, on, cost-retaining
ablation. Interaction arms reuse package arms and add the joint arm. If the
budget cannot cover a stratum, that stage is reported as incomplete rather
than shrunk silently. These are screens, not powered validation; the 200-seed
and procedural qualification gates are out of scope.

## 7. Landing order

approved contracts → L1A (native eligibility, reservation, raw-input
reporting; funded work disabled) + layer → L2 shared-native slice + layer.
L1B lands when its blockers close, without holding L2. L3 and L4 land in
independent windows; only their shared hooks serialize through the owners.
Final checks run on the combined final source.

## 8. Supersession map

| Earlier proposal | Disposition here |
| --- | --- |
| system-expansion-2026-10 §4 usable work / prime movers (watermill) | deferred; L1 supplies the manual work boundary first |
| §5 employers, customers and payroll (guild-funded workshop) | split: staffed public workshop is L1; payroll/customers are deferred L6; guild co-funding deferred (section 5) |
| §2 fallible harvest warnings | existing; watershed/flood stretch item stays deferred |
| §8 narrow contingent loss cover | deferred stretch (private cargo title after L6) |
| §9 domesticates as breeding capital | deferred stretch (after L3 grazing contract) |

The earlier roadmap remains historical; this plan is the single active queue
for sprint 1.

## 9. Sprint result and handoff (2026-11-05)

All packages in scope are implemented and integrated on
`claude/livelihoods-commons-sprint1` (draft PR #73). Each is default-off and
has its own switch. The board lists landing SHAs and inverse layers. The
screens are in
[livelihoods-sprint1-screens.md](../progress/livelihoods-sprint1-screens.md).

| Package | Status | Switch | Notes |
| --- | --- | --- | --- |
| L0 | integrated | — | Wiring, layer l0, funding route, compute budget |
| L1A | integrated | `--workshops --workshop-mode observe` | Native crews and actual craft inputs; layer l1a |
| L1B | integrated | `--workshops` (operate) / `cost_only` | Treasury-funded public cost, asset lifecycle; Python only |
| L2 | integrated | `--food-allocation [--food-allocation-regime …]` | Native allocation, person-level hunger; layer l2 |
| L3 | integrated | `--timber-stock` | Renewable stock and native harvest cap; layer l3 (tuning keys) |
| L4 | integrated | `--grain-convoys [--convoy-route-policy …]` | Multi-leg convoys; layer l4 (reserve hooks) |
| L10 | integrated | — | Livelihoods systems tab; browser journey at 1440 px and 390 px |
| L11 | screens done | — | 144 held runs; gates listed below |

What the evidence supports, and what it does not:

- **Mechanisms implemented and activating.** All four packages activate in the held worlds,
  most in every world. L4 has few natural dispatches and almost no natural risk outcomes.
- **Integration reliability.** Offline lane, Rust, native and viewer suites and the witness
  chains pass on the integrated source. The PR's CI and the identity suites are recorded
  in the board.
- **Observed behavior.**
  - Allocation rules produce the intended distributional differences: floor_means harms the
    poorer half, targeted relief favors it.
  - Workshops are bound by raw inputs, and the timber cap lowers their output.
  - Cover loss, not harvest, drives the timber stock.
  - None of this is a welfare or policy-efficacy claim.
- **Scientific and default readiness.** Not established. The 200-seed and procedural
  qualification gates were not run, and every switch stays off by default.

Known limits carried forward:

- The cross-version exact checkpoint is refused by source digest, as before. Old checkpoints
  continue only with `--resume-allow-mismatch`.
- Batch Lab and live new-world setup do not expose the four switches; the CLI and the gate
  runner do.
- The viewer's shared `types.ts` (pinned) is unchanged. The new records are read through
  strict loosely typed readers.
- Convoy payments happen after the granary pass, so transaction receipts and harvest-forecast
  procurement do not see them.
- L2 keeps the severe-hunger run regional.
- L1 replaces the whole regional craft ceiling with the site's: one site per region, no
  per-site split.

### Next-sprint recommendation (design only; needs a new instruction)

1. **L9, local collective budgets, on L1 and L2.** These two produce the strongest activation
   and the clearest distributional tradeoffs: workshop upkeep against targeted relief against
   granary maintenance, all from one treasury. Begin with one city decision point and the
   existing service APIs.
2. **Land-use authority before L8 commons rules.** The screens show cover loss is about 9–14×
   harvest. A commons quota acting only on extraction would have little leverage. First make
   the timber stock or forest cover the single authority for clearing as well as harvest, then
   add the quota.

Deferred and not started: L5 named learners, L6 payroll and household purchases, L7 costly
relocation, L8 commons rules, L9 budgets, and the stretch items. Before more L4 work, review
the reserve purchase rules (the one-coin floor and the surplus rule), which limit both
shipments and convoys.
