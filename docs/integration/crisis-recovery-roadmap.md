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
| M1 received/consumed | implementing | Native food kernel ledger; detached Phase2/public-relief observations; actual procurement-budget receipt; existing Food/history integration. | Abundant/empty/late-arrival/no-public-budget controls; separate wealth-access limit; native stock balance and public stock balance; old unknowns, behavior/RNG neutrality, actual native execution and exact continuation. |
| M2 logistics consequences | implementing | Genuine three-region private disruption fixture in isolated worktree; M1 observations then downstream evidence. | Actual reservation/transit/route loss/return/reopen/recovery, adverse diversion, ownership/accounting and in-flight checkpoint. Implement recovery only if demonstrated missing. |
| M3 storage choices | planned | Depends M1/M2. Public target lacks asset/capacity; select one opt-in public grain asset with paid work, condition, spoil/cap connection and custody. | Useful investment and opportunity-cost failure; default-off parity; partial work/damage/conquest persistence. |
| M4 household coping | planned | Depends accounting/logistics/care constraints. Audit native wealth, debt, household migration and actual work; choose one missing bounded coping interaction. | Legitimately different household trajectories; constrained transfers, time-known inputs and exact continuation; uneven costs. |
| M5 resource-backed service | planned | Depends work/resources. Choose supported learning/care institution and distinguish funded/attempted/delivered/interrupted. | Institution can exist and fail to serve; restored resources recover service with costs; identity and checkpoints. |
| M6 delayed information | planned | Depends authoritative procurement/service inputs. Reuse report/expiry/preparedness machinery. | Timely/delayed/misleading/absent controls change decisions from same initial truth; record decision inputs and costs; no future leaks. |
| M7 crisis suite | planned | After relevant M1–6 mechanics. Declare exploration cases and held evaluation cases before running. | A route-shortfall; B harvest+care; C constrained displacement; D institution loss/costly recovery; E unequal recovery. Verify shock application, baseline/alternatives, adverse/neutral results and shared-state accounting. |
| M8 usable laboratory | planned | Extend current views/interventions/comparison after contracts, not parallel panels. | Actual app journey and390px controls: detection → evidence → bounded what-if → comparison → private bookmark/export, old files/cancel preserved. |
| M9 package | planned | Integrated source/build/scenarios; compare starting baseline with same budgets. | Relevant Python/native/Rust/viewer, active-state checkpoints, runtime/memory/history/frame measurements, verified owner-only recovery; flags, limits and next tasks. Full scientific promotion is separate and unrun. |

## Current evidence and ownership

Integration owner edits Python coordinator/export and this ledger. Native worker
owns Rust economy/result/schema in its isolated worktree. Logistics worker owns
only a new native integration fixture in another worktree. No overlapping phase
writers or shared-wheel replacement. Viewer work starts after export agreement.

- Rust food ledger: three new balance cases and all19 focused economy cases
  passed; FFI/native integration and neutrality remain pending.
- A fresh locked baseline wheel was built from baseline Rust tree
  `edb263686adb7ea5e23864146a5f7d0c5a163da4`; real simulator classes verified.
  Separate baseline environment stays fixed; M1 builds into a separate environment.
- First logistics run genuinely reached transit, return and exact-resume checks,
  but failed the recovery precondition; preserved as negative evidence, not a
  demonstrated product defect or a neutral result. Fixture admission is in progress.
- Evidence root: `/workspace/shared/chronicler-crisis`; earlier verified private
  release backups remain intact. No new program backup publication claimed yet.

Next action: finish the M1 Python capture/schema and focused integration, then
attach the existing Food inspector. Run the real native controls against the
matching new wheel before claiming actual consumed-food coverage. Preserve a
verified source/evidence checkpoint before context becomes tight.
