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
| M1 received/consumed | integrated | Native food kernel ledger; detached Phase2/public-relief observations; actual procurement-budget receipt; existing Food/history integration. | Abundant/empty/late-arrival/no-public-budget controls; separate wealth-access limit; native stock balance and public stock balance; old unknowns, behavior/RNG neutrality, actual native execution and exact continuation. |
| M2 logistics consequences | partially covered | Genuine three-region private disruption fixture in isolated worktree; M1 observations then downstream evidence. | Actual reservation/transit/route loss/return/reopen/recovery, adverse diversion, ownership/accounting and in-flight checkpoint. Implement recovery only if demonstrated missing. |
| M3 storage choices | implementing | Depends M1/M2. Public target lacks asset/capacity; select one opt-in public grain asset with paid work, condition, spoil/cap connection and custody. | Useful investment and opportunity-cost failure; default-off parity; partial work/damage/conquest persistence. |
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

- M1 [food contract and verification](food-accounting.md):502 focused Python/native
  passes/one existing skip,9 guarded offline passes; full Rust1,181/two ignored;
  viewer1,115 broad plus4 precision-focused checks, lint/build and actual desktop/
  390px inspection. Four-mode baseline/current pairs preserve decisions/RNG/native
  state/world/39 prior artifacts after only the new export is removed. Exact
  hybrid4→8 retains complete new observations. Physical household access is not
  claimed; aggregate has no mass ledger.
- M2 existing mechanics genuinely executed: reservation/departure, interruption/
  return, alternate-path replan, ownership unwind, exact checkpoint and reopened
  delivery with a supplying-region harm. Private cash semantics are regional
  margin signals, not public paid orders. A concrete diagnostic defect remains:
  conquest return lacks a per-voyage receipt. A separate correction is implementing;
  a combined public/private substitution scenario remains pending. Do not call
  the entire logistics epic complete from the private fixtures alone.
- M3 native aggregate land-work hook and pure asset module are committed in
  isolated branches but **not integrated or native-qualified as an asset**.
  They reserve existing farmer-equivalent work after city/health deductions;
  no person-level work roster is invented. Construction/repair costs, custody,
  capacity/spoilage hooks, combined conservation and actual paired qualification
  are still next. Neglect/investment are explicit candidate policies, off by default.
- Evidence root: `/workspace/shared/chronicler-crisis`; older verified private
  backups remain intact. Current program source/evidence recovery index is prepared
  at integration checkpoints. Cloud publication/fresh provisioning remain deferred.

CI at d4893de4 (41452525060) passed Viewer/Rust/current native wheel build but
failed old frozen snapshot projections (15 shared hash cases) and the optional
snapshot-system field registry (one case). Frozen expected hashes remain fixed;
a strict independently validated food-v1 projection and registry integration are
corrected with246 focused compatibility passes and26 strict new projection regressions.
The old expected hashes are unchanged. Fresh combined CI remains pending.
The actual four-mode behavior/RNG/state comparisons remain positive evidence.

Next action: run fresh combined CI on the compatibility correction, regenerate
the qualified example/checkpoint, then integrate the opt-in M3 asset/work hooks and the now
native-tested M2 controller-return receipt.
Then qualify a declared investment and opportunity-cost pair, including active
work checkpoints. M4–9 remain planned, not complete. No scientific/default
promotion gate has been claimed.
