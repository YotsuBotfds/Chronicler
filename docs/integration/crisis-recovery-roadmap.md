# Societies under pressure — development contract

Starting dev baseline: `6ff45ec33a86ff72b84d0d493fefcc3cd3a89601`.
Refreshed remote was identical; worktree clean. Main stays untouched. Existing
closeout remediation remains complete within its corrected limits. This is a
new simulation program; reusable environment publication stays deferred.

States: planned → implementing → integrated → validated; partially covered,
blocked and deferred name unfinished boundaries. A focused kernel pass does not
validate an epic. Runtime changes remain opt-in until evaluated. No paid narration.

## Authority and dependency map

| Boundary | Runtime/authority, units and timing | Dependency / limit |
| --- | --- | --- |
| People | Python `Region.population` is model population; native alive agents are independent pool counts. Phase-2 demand uses the latter; completed population follows later births/deaths/migration/conquest. | Existing regional population records keep counts and epochs separate. Never apportion civ totals. |
| Native goods | `economy.rs`/FFI: Phase 2, model goods per region; food goods share the kernel's demand convention (default 0.5 per native alive agent). Production, physical net transport or abstract flows, craft input, proportional food drawdown, storage decay and per-good cap. | Pre-consumption sufficiency is stock / max(demand,0.1), clamped0–2. It is not a measured meal, calories or household purchasing access. |
| Private transport | Rust `merchant.rs`, trips/graph/buffer. Reservation is not stock debit; actual departure queues a debit; mobility arrivals/returns are consumed in the **following** Phase2 economy. Hybrid uses physical cargo; other backed modes use abstract allocation. | Grain arrival loses5%; no second payment. A three-node trip is needed to interrupt mid-transit. Existing unwind/return and reopen behavior must be executed, not inferred from names. |
| Public reserves | Python `grain_reserves.py`: distinct public grain/keeper. Phase2 normalizes custody, directly allocates release to sufficiency, then3% spoilage. Native consumption has already happened. | Release is modeled as eaten directly, not added to native consumed stock. Procurement target is not capacity. Late Phase10 buys surplus with whole-coin treasury budgets; pending paid public cargo is neither reserve nor private cargo. |
| Work/care/households | Rust `health_care.rs` deducts real eligible farmer work before production; Python persists episodes. Households are derived marriage/parent identities, not another persisted inventory economy. | Mobility/care/urban exclusion gates matter. No personal food-purchase constraint may be invented for observational explanations. |
| Institutions/politics | Existing scholarship seats have distinct patron/upkeep, host identity and recovery rules; governing institutions have their own funding snapshot and late-phase decisions. | Existence, funding and actual delivery differ. Start with one supported service; no universal bonus/framework. |
| Information | Forecast reports/preparedness and contacts have dated observations/delivery/expiry; decisions must use their then-known input. | Direct policy changes are separate from information availability. |
| Persistence | `run_checkpoint.py` exact identity: Python package, native binary/state layouts, interpreter/packages/thread settings. History observations persist with normal history. | New observational fields version exports; existing native state/RNG must remain neutral. Old mismatched exact checkpoints must refuse; old viewable bundles remain unknown. |

## Reviewable queue and acceptance

| Milestone | State | Dependencies and next bounded tasks | Acceptance before validated |
| --- | --- | --- | --- |
| M0 contract | integrated | Bounded source assessment above; first implementation is M1. | Authority/units/phases, budgets and explicit missing mechanisms recorded; not an epic-delivery claim. |
| M1 received/consumed | validated | Native food ledger, separate public relief and procurement observations in the existing Food inspector; all nine CI jobs passed at ecfa06ac. | Controlled native/aggregate cases, balances, actual exact continuation and four-mode neutrality passed. Physical household food purchasing remains outside this model; integrated crisis/distributional qualification belongs to M7–9. |
| M2 logistics consequences | validated | Actual native interruption, return, reroute, reopening, supplier harm and in-flight restore; controller-change receipt and combined public/private shortage executed. All nine combined CI jobs passed at fc50bf8e. | This establishes the specified bounded mechanics, not general transport economics. The declared integrated crisis suite remains M7. |
| M3 storage choices | validated | Opt-in paid work, timber/treasury costs, capacity, condition, spoilage, custody and existing inspector integration. All nine combined CI jobs passed at fc50bf8e. | Actual benefit/harm pair, total goods balance, partial-work exact continuation and four-mode default-off parity passed. Care/work interaction and held scenario evaluation remain M7–9. |
| M4 household coping | integrated | Opt-in native liquid gate for existing household migration, persisted controls, bounded dated history and existing Migration inspector. No household food inventory or new credit model. | Fresh wheel, actual unequal constrained moves, disabled four-mode parity, exact continuation and real desktop/phone journey passed. Combined CI next; long-run/care-obligation/distributional limits stay explicit. |
| M5 resource-backed service | implementing | Isolated academy-service helper and explicit upkeep/staff integration hooks; not active on dev. | Phase hooks, real service interruption/restoration, dated learning effect, supplies/costs, identity and exact continuation remain required. |
| M6 delayed information | planned | Depends authoritative procurement/service inputs. Reuse report/expiry/preparedness machinery. | Timely/delayed/misleading/absent controls change decisions from same initial truth; record decision inputs and costs; no future leaks. |
| M7 crisis suite | planned | After relevant M1–6 mechanics. Declare exploration cases and held evaluation cases before running. | A route-shortfall; B harvest+care; C constrained displacement; D institution loss/costly recovery; E unequal recovery. Verify shock application, baseline/alternatives, adverse/neutral results and shared-state accounting. |
| M8 usable laboratory | planned | Extend current views/interventions/comparison after contracts, not parallel panels. | Actual app journey and390px controls: detection → evidence → bounded what-if → comparison → private bookmark/export, old files/cancel preserved. |
| M9 package | planned | Integrated source/build/scenarios; compare starting baseline with same budgets. | Relevant Python/native/Rust/viewer, active-state checkpoints, runtime/memory/history/frame measurements, verified owner-only recovery; flags, limits and next tasks. Full scientific promotion is separate and unrun. |

## Current evidence and ownership

Integration owner edits Python coordinator/export and this ledger. Native worker
owns Rust economy/result/schema in its isolated worktree. Logistics worker owns
only a new native integration fixture in another worktree. No overlapping phase
writers or shared-wheel replacement. Viewer work starts after export agreement.

- M1 [food contract and verification](food-accounting.md):502 focused Python/native
  passes/one existing skip,9 guarded offline passes; full Rust1,181/two ignored;
  viewer1,115 broad plus4 precision-focused checks, lint/build and actual desktop/
  390px inspection. Four-mode baseline/current pairs preserve decisions/RNG/native
  state/world/39 prior artifacts after only the new export is removed. Exact
  hybrid4→8 retains complete new observations. Physical household access is not
  claimed; aggregate has no mass ledger. All nine jobs passed on
  [ecfa06ac](https://github.com/YotsuBotfds/Chronicler/actions/runs/41462372701).
- M2 existing mechanics genuinely executed: reservation/departure, interruption/
  return, alternate-path replan, ownership unwind, exact checkpoint and reopened
  delivery with a supplying-region harm. Private cash semantics are regional
  margin signals, not public paid orders. Conquest now records its queued gross
  return with `return_reason=controller_change`; 88 matching-native focused tests
  passed with no skips. Receipt-disabled old/new worlds/native/RNG match. A further
  101-test native selection passes the combined shortage case: private reservation20,
  paid public gross26.008/net24.708, two-coin treasury transfer, distinct arrivals
  and later15.17 public release, with real resource checks. The same-boundary
  arithmetic alternative is not a second simulated arm or general policy ranking.
- M3 [storage contract and evidence](grain-storage-candidate.md): five actual
  native controls cover investment benefit, opportunity-cost harm, whole-goods
  accounting, partial-work exact continuation, damage and conquest. The 276-test
  combined focused selection passed; two additional config/pending-plan tests
  passed in the 13-test guarded chunk with no native imports or blocked IO.
  Default-off seed42/eight-turn pairs in all four modes retain all 39 artifacts,
  decisions, RNG and 24 native states without stripping M1 observations.
  The combined viewer passed1,120 tests/103 files; focused lint/build and actual
  desktop/390px checks include positive capacity return, selected-turn navigation
  and old bundles. Full combined CI remains a separate gate.
- M4 [contract, commands and limits](household-mobility-candidate.md):384 focused
  combined tests,239 guarded contracts/metadata, actual fixed-threshold paired
  moves and exact history/native/RNG continuation passed. Source lineage and
  four-mode actual disabled parity are separate proofs. Viewer1,124 broad tests,
  five focused final paging/format checks, lint/build and real desktop/390px
  journey passed. The initial browser paging failure is retained. Fresh CI next.
- M5 isolated helpers `a3d0aecb`/`ce419f7f` have82 pure service/scholarship passes,
  but an audit found alive-scholar counts do not establish available work. This
  prototype is not a completed service. A real native Scholar-day income/work
  budget and prior-paid supply inventory are implementing in separate branches.
  Actual phase scheduling, enablement/export and native execution remain gates.
- M6 report-delay/decision-receipt candidate `b405717c` is isolated WIP:227 focused
  tests passed, one immutable source inverse was explicitly deselected after its
  retained failure. No final phase integration/native impact claim. A later exact
  source composition must account for its edits without changing frozen witnesses.
- Evidence root: `/workspace/shared/chronicler-crisis`; older verified private
  backups remain intact. Current program source/evidence recovery index is prepared
  at integration checkpoints. Cloud publication/fresh provisioning remain deferred.

Retained negative evidence: CI at d4893de4 (41452525060) passed Viewer/Rust/current native wheel build but
failed old frozen snapshot projections (15 shared hash cases) and the optional
snapshot-system field registry (one case). Frozen expected hashes remain fixed;
a strict independently validated food-v1 projection and registry integration are
corrected with246 focused compatibility passes and26 strict new projection regressions.
The old expected hashes are unchanged.
The actual four-mode behavior/RNG/state comparisons remain positive evidence.

Compatibility follow-up: CI4963c379 reached9,168 no-native passes but rejected
one missing exact registry inverse; Viewer had1,115 passes and one historical
fixture/current-contract mismatch. Both are corrected without changing old
fixtures or expected hashes:76 focused Python passes, five viewer transport
passes, lint/build. The subsequent ecfa06ac CI passed all nine jobs. The failures
remain recorded rather than being relabeled as successful checks.

Combined M2/M3 CI60bbbcf7 failed repeated pickle/live checkpoint checks: the new
serialization filter mutated Pydantic's live dictionary. The actual failure is
retained. A copied dictionary fixes it,101 focused checks passed, the guarded
selection passed102 and16 actual native live/process tests passed. All nine
jobs subsequently passed atfc50bf8e in
[run41470386347](https://github.com/YotsuBotfds/Chronicler/actions/runs/41470386347).

Owner-only checkpoint8ad00910 includes source/six WIP refs and598 evidence files;
both remote objects and recovery instructions were independently downloaded,
size/SHA checked, and every archive member verified. It explicitly preserves a
failed-CI checkpoint, not a claimed release. Newer source and M4/M6 evidence need
their next checkpoint; keep local originals.

Next action: push and CI the qualified M4 candidate, checkpoint source/evidence,
then integrate M5 paid materials and actual work. M6 production decision/delay
hooks follow; M7–9 are still planned. No scientific gate, full-roadmap completion,
default promotion or reusable-environment publication has been claimed.
