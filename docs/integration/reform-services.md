# Poor relief as a real service (D1a, `--reform-services`)

Default off. Connected-world program D1 ("reforms change a real service or decision, not only a
label"); design from AUDIT-D section 7.4(a)
([audit](../superpowers/audits/connected-world/audit-d-institutions-war-owned-stock.md)). Module
`chronicler.reform_services` (state `reform_services_state.py`); seams in `agent_movements.py`
(the reform table and the relief upkeep), `governance_runtime.py` (the institution's enforcement
payment), `household_retail.py` (the purchase), `money.py` (the relief fund account) and
`wealth_accounting.py` (the ledger channel).

## Why

A granted poor relief (the lasting reform of a `commons` movement) changes a label today: every agent
of the realm reads its material need as `need + 0.3 (1 - need)` for grievance and commitment
(`movements.rs` `REFORM_NEED_CREDIT`), while the needs themselves are untouched; the realm's relief
upkeep (`ceil(0.75 x regions)` a turn, or the Commons Management institution's enforcement cost when
the reform enacted or upholds it) is a sink. Nothing is bought and nobody eats more.

## The switch

| | label credit | relief payment | food |
| --- | --- | --- | --- |
| off (default) | every agent of the realm | sunk | none |
| `--reform-services` (mode `service`) | withheld | into the realm's relief fund (capped; the rest sunk) | the fund buys owners' unsold food into the commons the next free rations draw on |
| `--reform-services-mode cost_only` | withheld | sunk, as off | none |

Requires `--agents hybrid`, `--household-retail` in mode `retail` or `no_relief` (owners are paid at a
price; `free_exchange` and `record_only` are refused) and agent movements (on by default; refused with
`--no-agent-movements`). A saved switch is checked on every resume and refused, with a hint to pass
`--no-reform-services`, when one of these is gone. `--no-reform-services` returns every fund to its
treasury (whole units now, the sub-unit rest as the seam's carry), dated. Feature catalog:
`REQUIREMENTS["reform_services"]`, with the new setting `agent_movements`.

Hybrid only, because the channel needs named owners: the relief buys owned food from the retail
claims of stable ids and pays those ids through the native wealth transfer.

**Channel.** Of the two channels AUDIT-D names, the retail free pool is used: owners' surplus bought
through the payment seam (paid by id) into the commons. The granary alternative was not chosen: a
relief purchase into a granary would release only under the granary's own shortage rule (Phase 2,
sufficiency below 1), its procurement and release live in the pinned `grain_reserves.py`, and its
target and budget rules would have to be widened there. The free pool reaches exactly the people the
provisioning records as unable to buy, through an existing allocation.

**Unchanged.** The other reforms (home rule, toleration, guild charter) and the one-off grant relief
every reform gives its movement's members on the first tick (`relief_age`: half the creed need's
deficit and a satisfaction fading over 20 turns). That one-shot is shared by all reforms and carries
the members' satisfaction for winning; withholding it for relief would need the movement table to
split the two, and is left for the owner (recorded boundary).

## Mechanism (service mode)

1. **Label.** `agent_movements.reform_table` omits relief rows while the switch is on (both modes;
   counter `credit_rows_withheld`).
2. **Money in.** The treasury pays the same amount at the same time as without the switch:
   - a standalone relief's upkeep in Phase 10 (`_tick_reforms`, when the treasury can pay it; the
     arrears rule is unchanged);
   - a relief whose institution is Commons Management: the institution's share of the Phase 2
     enforcement payment (`fund_institutions_phase2`), `floor(paid x cost / demand)`.

   Up to the fund's cap (`FUND_CAP_TURNS` = 4 turns of `ceil(0.75 x regions)`), that amount is paid
   into the realm's relief fund through the payment seam (`money.pay`, purpose `relief_budget`,
   treasury -> `relief_fund(civ)`, key `(turn, relief_budget, 2 x reform [+ 1 for the institution
   share])`); the rest is sunk exactly as without the switch.
3. **Purchase** (Phase 10, after the granaries' procurement and before retail closes the turn's
   frame: the switch is declared before `household_retail`). For each realm with a relief in force
   and money in its fund, in civilization order, its own pilot regions where this turn's provisioning
   recorded people priced out or short of offer, neediest first (persons minus rations, then region
   index): buy `min(unmet rations x ration, owned food held there, what the fund can pay)` at the
   region's installed ask, cost `ceil(food x price / ration)`. The owners are those holding retail
   claims now (their unsold surplus); each gives food pro rata to its claim (largest remainder, ties by
   ascending id) and is paid pro rata to what it gave, by stable id (`money.pay`, purpose
   `relief_purchase`, keyed natively under `food_procurement` at batch `1 + region`; household retail's
   own procurement credit keeps batch 0). A wealth ceiling's residual returns to the fund. Retail then
   debits the claims (`relief_bought`, a flow of the owned pool in the retail frame) and moves the food
   into the region's commons.
4. **Delivery.** At the next opening the economy eats the commons; the free pool (commons consumed
   plus granary release) goes at phase 0.7 to those who cannot buy. Read the next turn per region (see
   below).
5. **Money out.** When a realm's relief is no longer in force (repealed, lapsed, its civilization
   gone), the fund is returned to the treasury (`relief_refund`).

## Exactly once, conservation, information

- Every seam bill settles once per `(turn, purpose, batch)` (persisted keys refuse a repeat after an
  exact resume); the native key log refuses a repeated `(turn, code, batch)`. Phase 10 commits once a
  turn (a second commit raises).
- No money is created: the fund holds only treasury payments, spends only on owners and returns only to
  its treasury; `money.check_book` runs every turn and the ledger checks `open + paid in - purchases -
  refunds = close`. No food is created: owned food moves to the commons at a paid price, and the free
  pool gives only food the economy ate.
- A realm reads only its own pilot markets' recorded provisioning of this turn (who was priced out,
  the rations they lacked) and the installed ask; never provenance or attribution records.
- No random draws. Grievance responds only through the needs the food changes; no grievance channel is
  added.

## Delivery bounds

Relief food is pooled with the commons, so what reached people is bounded per region, never attributed
to persons. At the next provisioning: at most `min(rations bought, free rations given)`.
Gross outbound food is not observed. The native food ledger records net transport, so equal
outbound and inbound food can hide an export of the prior relief, even when the final commons
falls short and total cap overflow is zero. No positive lower delivery bound is established
(`delivered_at_least: null`). A region not provisioned the next turn reads as unobserved, not zero.
Historical positive lower estimates remain in original saved evidence; the viewer retains readable
records but suppresses those estimates with an explicit reason. They must not support efficacy claims.

## Record (`snapshot.livelihoods.reform_services`, schema 1, stage `D1a`)

`mode`, `source_turn`, `frame` (null: the turn was not observed) with `civs` (per realm: fund open,
paid in, sunk, spent, ceiling residual, refunded, close, cap, path), `purchases` (region, realm, unmet
rations, ask, food per good, rations, cost, credited, residual, sellers) and `deliveries` (bought turn,
rations bought, free pool, bounds, priced out and unmet at delivery); `funds`, `counters` (fixed key
set), a bounded dated `log`, `parameters`. Python reader: `reform_services.record_status`; viewer:
`viewer/src/lib/reformServices.ts` (through `recordReading.ts`: disabled, absent, malformed, unobserved,
recorded zero, recorded) and the Livelihoods tab panel `ReformServices.tsx`. The retail panel shows the
`relief_bought` flow under "To commons".

The A1 ledger (`--wealth-accounting`) reads the purchases as channel `relief_purchase` and the funds'
treasury side (`treasury.relief_fund`) with three closures.

## Boundaries

- The relief buys only in the needy region and only owned food held there; a region whose owners hold
  nothing is counted (`need_without_owned_food`), not served from elsewhere (no transport).
- Only retail pilot regions are served (the default `market` boundary adds capitals; `all` serves every
  controlled region).
- With an institution, only Commons Management's pro-rata share of the enforcement payment (as covered
  that turn) is redirected; if the reform names the institution and the payment covered none, nothing
  is (`institution_share_unknown`).
- Turn order: the purchase sees this turn's provisioning and feeds the next turn's free pool. With A4's
  `--titled-trade`, whose purchases run inside retail's Phase 10, relief buys first: merchants buy from
  the owners' surplus that remains.

## Tests

`tests/test_reform_services.py` (offline: label, deposits and cap, cost-only, institution share,
governance cost identity, purchase, refusals, deliveries, refunds, switch-off, record states) in oracle
chunk `connected-world-d1`; `tests/test_money.py::test_a_relief_fund_is_its_treasurys_purse_and_pays_agents_or_back`;
`tests/test_reform_services_native.py` (template 7: identity before the first relief; template 42:
service vs cost-only with resource checks, exact resume with an open purchase and a holding fund); viewer
`reformServices.test.ts`, `ReformServices.test.tsx`.

## Recovery review (2026-11-07)

The D1 recovery review added a runtime check of each realm's relief fund closure and
strict nested-frame validation in both D1 readers. Its first correction required zero total
cap overflow, after finding that checking owned overflow alone missed a commons-only cut.
Independent follow-up review then established that net transport cannot prove relief survival
through gross exports. The final candidate therefore reports only an upper delivery bound.
CW6D1 held source remains frozen at `808726b8`: its historical lower estimates are invalidated,
not rewritten. None of its preregistered primary metrics uses the delivery lower estimate.
This changes observation only; food, payments, needs and decisions are unchanged.
