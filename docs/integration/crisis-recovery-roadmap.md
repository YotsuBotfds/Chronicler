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
| M4 household coping | validated | Opt-in native liquid gate, persisted controls, bounded history and Migration inspector; corrected omitted/mock/no-native boundaries. All nine CI jobs passed at4dddb88b. | This establishes constrained native moves and exact continuation in declared controls, not a new household food/credit/care model or general unequal recovery. M7–9 retain those limits. |
| M5 resource-backed service | validated | Actual paid academy supplies, native exclusive Scholar work/income cost, prior-turn learning effect, dated Learning inspector and material balances. All nine CI jobs passed atd7061f42. | Nine native controls, funded/no-stock/restock/ownership/adverse cases, exact held-supplies continuation, off parity and browser journey pass. General efficacy, rebuilding suite and Scholar illness remain outside this bounded qualification. |
| M6 delayed information | partially covered | Report delay, real decision-boundary inputs/costs, issue-time construction records and Harvest inspector integrated; all nine CI jobs passed at3e852333. See forecast-decisions-candidate.md. | Actual timing/purchases, expiry, caps, exact continuation, observer neutrality and browser checks pass. Both the earlier and additional scarce-budget shuffle cases are purchase/food-neutral; misleading harm/food outcome criterion remains unmet. |
| M7 crisis suite | partially covered | [Constructed A/B/C/D cases and E analysis](crisis-scenarios.md) execute shared native state. Regional shock now uses the existing exact pair coordinator; explicit paid academy restoration has a tested boundary API. | Development admissions pass within stated limits. Receiving services, complete common-point alternatives for each case and held evaluation remain unfinished. Supported drought injection is not a crop-yield shock; recorded migration is not proof of forced eviction. |
| M8 usable laboratory | implementing | Regional closure preview → actual exact pair → native food comparison works in Chromium at desktop/390px. Old manifests stay supported; exported v3 provenance is readable and omits the internal command value. | One live client is the existing server contract. Academy restoration still needs coordinator/UI wiring; broader integrated crisis gallery and private export journey remain unfinished. |
| M9 package | implementing | Quiet paired runtime/memory/history comparison and checkpoint controls recorded; periodic owner-only source/evidence recovery verified. Browser latency and combined final CI next. | Pending-shipment/partial-work/care/service checkpoints have bounded evidence, not full scientific qualification. Final flag matrix, held scenarios, package and handoff remain unfinished. |

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
  journey passed. The initial browser paging failure is retained. CI048ed0dd
  exposed a no-native collection omission and optional-observation mock/legacy
  compatibility defects; production defaults now skip the disabled observer,
  older optional handoffs stay unknown, and native collection skips only when
  the extension is absent.81 actual-native/factory checks,79 no-native checks
  with one expected module absence, and80 guarded passes qualify the fix. All
  nine jobs passed at4dddb88b in run41477763575; failures remain retained.
- M5 [contract, commands and actual limits](academy-services-candidate.md): the
  original alive-scholar proxy was replaced by native reserved/delivered work
  and prior-paid craft holdings. Nine actual-native cases execute purchases,
  material use/income cost, shortage/restock, peaceful and destructive patron
  transitions, exact checkpoint and the actual technique-phase consumer.
 389 combined focused tests passed before the final additional native test;
 241 guarded contracts/metadata and135 no-native tests/three expected native
 absences pass. Four-mode disabled pairs retain39 artifacts/24 native states;
 a standing-academy pair adds eight unchanged artifacts/native states. Viewer
 1,131 broad tests and six final focused checks, lint/build and desktop/390px
 production journeys pass. All nine combined jobs passed atd7061f42 in
 [run41481053005](https://github.com/YotsuBotfds/Chronicler/actions/runs/41481053005).
- M6 [actual controls and limits](forecast-decisions-candidate.md):477 combined
  Python/native/source checks,240 guarded contracts/metadata,539 focused frozen/
  compatibility checks with61 subtests, and four actual-native control/checkpoint
  tests pass.14-turn normal-delay0 old/new behavior/RNG/native hashes match after
  removing only the new observations. Viewer1,137 broad tests, seven final guard
  checks, lint/build and real desktop/390px normal/delay/legacy/shuffle journeys
  pass. An initial null fixture remains null; a separately designed, post-null
  finite-stock development case admits warning purchases50.719/six coins with
  timely information versus none under delayed/withheld warnings. Shuffle changes
  claims but has the same purchase total; no food benefit or harm was demonstrated.
  This is partial acceptance, not a policy or scientific victory.
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

M9 starting measurement is retained under `m9-baseline`: actual6ff45ec3/native,
procedural32 regions/10 civilizations/40 turns, seed42 hybrid, three sequential
fixed-thread runs. Median2.802s/max RSS163,372KiB;16 files/4,853,141 bytes per run,
including bundle2,224,098 bytes. No warmup and no current-source speedup claim.

Owner-only checkpointd7061f42 is independently verified: downloaded source bundle
restores the exact clean commit/1,894 tracked files and25 refs;462 incremental
evidence members match, and26 omitted identical members were checked in the prior
verified598-file archive. Recovery instructions/index were independently downloaded
and matched. CI was pending at archive capture; its subsequent green receipt is
retained locally and in GitHub. Newer M6 source/evidence needs the next checkpoint.

M6 all-nine CI success is independently read from GitHub run41489913862 and
retained in`m6-forecast/ci-final-receipt.json`. An additional predeclared20-turn
45-coin starting-treasury case has identical normal/shuffle purchases and native
food outcomes. Its scarcity is transient (initial procurement budget1 per ruler;
one owner has0 when warnings arrive). Two reports score actual shortfalls and
one remains unscored. It establishes no harmful misinformation or budget
crowdout, and does not close M6.

M7/M8 source includes actual loaded-cargo admission, bounded closure and recovery,
real care/food opportunity cost, constrained receiving-market migration and
explicit paid restoration after the natural founding lottery failed. See
`crisis-scenarios.md` for executed admissions and exact unmet boundaries. The
new paused-restoration API cannot independently detect an active accumulator:
its coordinator must attest a safe boundary; no web caller is wired yet.
Browser testing also reproduced fresh live output preparation failing before
the output root existed. Creation of that private root plus a focused regression
fixes the actual workflow; earlier failures are retained.

Combined M7/M8 local verification:327 focused Python/native/ownership/source
checks pass without skips;652 frozen source/compatibility checks plus61 subtests
and six offline layered witnesses pass. Viewer1,146 tests/106 files, lint and
production build pass. Actual Chromium verifies preparation from an absent
output root, readable v3 preview, both native continuations, regional native
food comparison, desktop and390px keyboard scrolling without page errors. A
second simultaneous client receives the existing explicit one-client refusal.
Original missing-directory and overly rounded browser assertions are retained.
These checks do not close the unfinished M6–9 boundaries or replace fresh CI.

M9 [paired measurements](../performance/crisis-development-2026-11-02.md) use the
same32-region/10-civ/40-turn seed42 hybrid case and matching separate native
builds. Quiet alternating median wall2.729→2.682s does not establish a speedup
or rule out a regression. Median RSS rises7,208KiB/4.4%; compact history rises
248,034bytes/28.2%, exactly the intentional food-accounting observations. A first
busy sample suggested85% slower wall time; paired profiles and quiet runs did
not reproduce it. No speculative optimization was accepted.

Owner-only checkpoint8beb6e4f preserves M6 dev3e852333 plus43 WIP refs and161
incremental evidence members. Source and evidence were independently downloaded,
size/SHA checked, every member verified, and the downloaded source restored a
clean M6 tree/1,904 tracked files. Its [remote recovery instructions](https://drive.google.com/file/d/1IkWe1bSHpxao7V041Jfb576wvF6VOR5Z/view)
and [verification index](https://drive.google.com/file/d/18dJ0vMzeLl5RkVuIZ5q3lUNWcNCa6Ps-/view)
were also independently downloaded and matched. Later M7/M8 work needs the next
checkpoint. This is source/evidence recovery, not fresh environment provisioning.

Next: complete combined M7/M8 checks and browser latency measurements, commit/push
this bounded slice and verify a new private backup. Then wire deliberate academy
restoration at the real paused coordinator, complete C's receiving-service and
matched alternatives, freeze/run modest held evaluations, and address M6's
misleading-information acceptance without forcing favorable outcomes. The
roadmap remains unfinished; no scientific gate, default promotion or reusable-
environment publication has been claimed.
