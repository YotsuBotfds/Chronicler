# War requisition and restitution (D4 / A4-2)

Opt-in `--war-requisition`, off by default, hybrid campaign worlds only. Modes:
`transfer` (default when enabled) and `cost_only`. The latter pays the physical
food costs but keeps legacy ration credits, allowing the food-transfer effect
to be compared with its cost. Neither mode changes default-off runs.

## Physical authorities

One model food unit equals two existing army ration kits. The army's existing
`Army.rations` remains the sole carried ration store. Existing siege,
occupation and conquest paths still debit commons, granaries and retail owned
food once per event. D4 measures those exact before/after debits and credits
whole kits to the acting civilization's armies physically in the affected
region, sorted by stable army id, up to carried capacity. Food that cannot be
carried, and fractions smaller than one kit, are explicitly recorded as
destruction. A distant claimant or a changed controller is not custody.

In transfer mode initial kits, ordinary refill and hostile foraging withdraw
real commons food rather than creating food. Friendly sources are reachable
within the existing three-edge supply range, sorted by distance and region
index. Merchant commitments are excluded through the established native
read-only commitment interface. Refill and foraging share the remaining kit
capacity, so a requisition cannot stack free supply above that capacity. A
second logistics supply call for one army/turn is refused, with the guard
preserved by exact checkpoints. Cost-only removes physical supply but retains
the legacy kit credit and destroys requisitioned food.

Food cargo can be seized only where a hostile field army stands, before or
after a trade hop. The trade shipment closes once with outcome `seized` and a
`war_seizure` custody loss; D4's linked shipment record states the kit credit
and destroyed residual. A distant conquest of the destination continues to
return cargo. The ordinary titled-trade grain decay and sea-loss rules remain
in force. Timber is not food and must not be converted into kits.

## Soldiers: residence, attachment and actual feeding

The original D audit's statement that enlisted agents never migrate is
incorrect. Current `behavior.rs::evaluate_region_decisions_observer` skips
native trips and titled carriers, but has no roster exclusion. The A6 audit's
30 roster migrations in 120 turns agrees with that source. Native residence
and native migration remain authoritative; a Python army attachment is a
separate record. D4 never moves a native agent or writes X1.

The roster ids frozen at Phase 2 are excluded from civilian farm work, title
and civilian food demand under the opt-in native service input. Later recruits
remain in the civilian work/food census until the next turn. Army consumption is dated
and supplies the native food term its actual `consumed / demand` fraction,
including hunger. Released people retain that turn's already-consumed meal so
a release cannot yield both an army meal and a civilian meal. Phase 2 uses the
last dated meal and live roster for work exclusion; the before-tick input is
refreshed after logistics without consuming food. A new army raised after
Phase 2 consumes no military meal until the following turn, since its people
already counted toward civilian food and production this turn. This changes neither mortality authority
nor native residence. D3 may suppress the existing general Soldier war
mortality multiplier only through its own explicit rules path.

## Restitution

Seized owned food creates a personal liability owed by the acting state's
existing treasury, priced by the observed retail price when available and an
explicit parity tariff of 1,000 milli-wealth per ration otherwise. Cargo uses
its actual recorded acquisition cost pro rata to surviving cargo. No person
is paid for commons or public granary losses. Promises are not spendable money.
`money.py` makes actual payments using appended native purpose `restitution`
(code 10), one `(turn, purpose, payer batch)` key. It pays oldest claim ids
first, aggregates lines by owner and returns wealth-ceiling refusals to the
payer's prepaid carry. Arrears remain due; insolvency never mints payment.

Personal promises lapse explicitly when the claimant dies or the native pool
is rebuilt; they do not invent heirs or a reconstructed identity. Existing
owned food and native wealth inheritance keep their existing authorities.
Claims merge by payer, owner, region and source under a stable claim id. At
4,096 claims, additional liabilities are explicitly counted as unrecorded;
no payment is inferred. Completed claims remain bounded by this cap, so a
long-run cap requires a later archival policy. State carries remain attached
to the payer's money book if a promise lapses or the switch is disabled.

The completed-turn record contains physical source events, stable owner,
shipment, army and region references, explicit truncation, and a bounded claim
sample. `due_milli` is the original cumulative liability; the remaining amount
is `due_milli - paid_milli` for status `open`. A region context is not evidence
that a particular person suffered or received a transfer.

## Recovery and verification status

The durable board named `claude/cw-d4-requisition`, but no such remote branch
or matching accessible worktree was found at takeover. The original clean
checkout and recovered B3/D1 branches were available. This implementation is
reconstructed from the durable audits and current source; that search does
not establish whether unpushed work exists in an inaccessible Claude container.

Focused constructed tests cover physical requisition, capacity, no-food
supply, disabled and cost-only paths, actual hostile cargo custody,
liability/claim-id persistence, ceiling-refused restitution, native feeding
rows and owned-stock liabilities. The lane's preceding focused run passed
182 existing/new tests before the feeding and civilian-exclusion additions;
the final integrated checks, native service tests, feature-off identity,
transition resume, browser evidence and fresh held screen must be recorded by
the integration owner. No qualification, held-screen or browser result is
claimed by this page.
