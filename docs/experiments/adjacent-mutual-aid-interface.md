# Adjacent mutual aid interface manifest

Public base `edf7299`; isolated branch `experiment/social-aid`. Incorporates the
integration boundaries supplied by parent for contract
`task01a10d37-fd1f-74e5-8776-6c8e9afd3025` / `document14614a2`.
That separate document is not present in this checkout; no changes to it made.

| Surface | Ownership and contract |
|---|---|
| `WorldState.mutual_aid_enabled` | Python saved boolean, default `False`; new-world opt-in only |
| `WorldState.mutual_aid_state` | Python saved sparse mapping by region name; `MutualAidState(controller, stress_streak, last_observed_turn, food_sufficiency)` |
| `WorldState.mutual_aid_last_dispatch_turn` | Saved turn guard, default `None`; prevents double dispatch in one turn |
| `WorldState.mutual_aid_last_transfers` | Saved last-dispatch ledger, default empty; `MutualAidTransfer(turn, controller, donor, recipient, sent, received, transit_loss, treasury_cost)` |
| `--mutual-aid` / `--no-mutual-aid` | Explicit on/off; absent CLI value is `None` so saved setting survives; enabled agents-off rejected |
| `AgentSimulator.get_stockpile_commitments()` | New non-draining read-only Arrow query: stable `(region_id uint16, good_slot uint8)` rows, 8 fixed goods per region; `reserved float32`, `pending_departure float32`. Hybrid returns Loading reservations and current departure debits; abstract modes return zeros. No RNG advance, ledger mutation or planner edit |
| `read_stockpile_commitments(world, simulator)` | Requires complete finite nonnegative native rows in hybrid; maps fixed economy slots to per-region per-good reserved+departure commitments; missing native query raises before aid mutation |
| `dispatch_mutual_aid(world, snapshot, acc=None, *, commitments=None)` | Phase 2 before economy inputs; reads N−1 local sufficiency and live snapshot region counts, stocks, control/region membership, adjacency and treasury; mutates only regional food stocks, aid ledger/guard, events, and queued treasury `keep` costs |
| `observe_mutual_aid(world, economy_result, snapshot)` | After economy reconstruction at Phase 2 N; records regional stress for N+1; does not consume RNG or mutate economy signals |
| Existing `region.stockpile.goods` | Debit donor and credit recipient per good, net decrease equals aid transit loss; native economy receives modified stocks through existing input builder |
| Existing `economy.per_capita_food` | Resolve same tuning override as native economy; reject nonfinite/nonpositive configured demand for enabled aid |
| Existing `StatAccumulator` | Treasury debit in `keep`; projected spending uses unapplied pending `keep` treasury changes with matching per-change clamp and integer cast |
| Existing `Event` | `event_type="mutual_aid"`, controller actor, importance 3; ledger stores exact numbers while description rounds for display |

Reset/continuity rules: recovery to sufficiency >=0.8 resets streak; missing data,
zero agents, invalid/no owner, controller mismatch, or an observation gap resets
eligibility. Same-turn observations and dispatch are idempotent. No snapshot
means no dispatch; missing economy observations clear enabled memory. Disabled
functions are strict no-ops, including stale saved state. Freshness checks prevent
old memory activating after a gap. The ledger replaces on a new dispatch attempt;
historical aid events stay in the ordinary timeline. Dispatch guard intentionally
prevents retrying an already attempted same-turn budget.
There is no fixed timed cooldown. Recovery resets the stress streak; eligibility
returns only after three newly consecutive subthreshold observations.

Invariants:

- No production/yield/soil/fertility/migration/merchant-planning edits.
- Stock eligibility agrees with both controller and civilization region list.
- Same-controller, reciprocal physical adjacency, occupied donor and recipient.
- Donor retains two turns of **uncommitted** current configured demand at dispatch.
- Per-good transfers cannot touch reserved/pending-departure goods. Incoming
  deliveries/returns are not spendable before economy settlement. Old in-transit
  goods are not debited twice. No forwarding newly received aid in this dispatch.
- Sum(sent) = sum(received) + aid transit loss; capacities are shared across edges.
- Available treasury covers every rounded debit, including pending mutations;
  costs never borrow future receipts or disappear through accumulator clamping.
- Native conservation counters have an after-aid input boundary. Full stocks
  balance includes aid transit losses separately, native cargo `in_transit_delta`,
  and clamp-floor corrections with their actual mass-adding sign. No correction
  is evidence of aid-created benefit.
- Lagged observed sufficiency affects next-turn eligibility; aid cannot change
  yield-triggered famine checks or resource effective yields.
- Social memory serialization is proven; full hybrid persistence is not supplied
  by Python saves, which omit the live native pool/cargo/RNG buffers.
- Disabled comparisons use untouched public source/native baseline, never private
  `b665e198` or merely another edited variant.

Full explanation, tradeoffs and narrow experiment gates:
[`adjacent-mutual-aid.md`](adjacent-mutual-aid.md).

Validation-only follow-up: `scripts/mutual_aid_adversarial.py` runs 15 native
economy/agent-behavior turns with real evolving cargo; the fixture explicitly
applies a crop-yield schedule and a fixed initial relief budget. Native tax outputs
are reported without macro income credits. It supplies no production runtime
interface, no cargo injection, no new cooldown field, and no native checkpoint
restoration. Enabled cases treasury2/20 and disabled case treasury2 are bounded
adversarial fixtures, not a parameter sweep. The untouched disabled replay uses
`edf7299` Python plus its original native build; only the added cargo diagnostic
and four default aid metadata fields are excluded from equality checks.
Adjacent trips settle with zero net `in_transit_delta` in this replay; nonzero
multi-turn/multi-edge cargo deltas remain a validation limit. Existing synthetic
Rust query coverage does not turn that limit into a completed integration claim.
