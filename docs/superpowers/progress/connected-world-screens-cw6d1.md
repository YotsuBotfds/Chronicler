# Connected-world CW6-D1: preregistration for relief services and guild leagues (slice D1)

Status: **FROZEN before any held run**, 2026-11-07. Recovered D1a/b source
`7cfe289b2268d0d5011270c22fe80de0500f3ab6`, independently reviewed by the B3
worker from actual source/specification/tests. This documentation-only freeze
is the held source revision; no held outcome has been read. Fresh held cohorts:
template 3701–3706 and procedural 3801–3806, lead-reserved after registry union.

Native build: `/workspace/cw-d1-native/bin/python`, Python 3.13.5, own release
extension built from the unchanged main Rust in this worktree, SHA-256
`f2fb24f13c386c3965e485330499b9aa435f61a43e8fc02023f950fbf9664256`.
The branch changes no Rust. Recovered draft and earlier native identities
remain in Git history; this freeze replaces their unexecuted cohort proposal.

The four development worlds (template 7/42; procedural 13/21), five arms each,
passed the runner/extractor schema gate: **20/20 successful runs**, no missing
outcomes. Three bundle/package schema combinations were read (bundle 6,
livelihoods/package 1, food accounting/regional population 1). The timing pilot
(template 5/procedural 19, five arms) passed **10/10** before this freeze. Its
source/metrics are retained with the held receipt. All development/pilot worlds
are distinct from the held cohort.

Compute ceiling: 0.75 core-hours

Primary outcomes: cw6d1_priced_out, cw6d1_commons_grievance, cw6d1_member_purse

## Purpose and limits

Two default-off mechanisms ([reform services](../../integration/reform-services.md),
[guild leagues](../../integration/guild-leagues.md)):

- **D1a `--reform-services`.** A granted poor relief stops crediting every agent's material need for
  grievance (the label); in mode `service` the treasury's unchanged relief payment goes into a capped
  relief fund that buys owners' unsold food, paid by stable id, where the realm's own retail markets
  recorded people priced out, into the commons the next free rations draw on. Mode `cost_only` withholds
  the label and sinks the payment as without the switch.
- **D1b `--guild-leagues`.** Guilds of cities in different realms linked by recorded merchant
  deliveries form bounded leagues; members pay capped dues into a fund that pays a member city's
  recorded levy share or sack plunder. Mode `dues_only` collects the same dues and pays no claim.

The screen asks whether replacing the label with a real service changes who goes hungry and how
movements grieve, and whether pooled guild purses change member cities' purses and guild militancy, and
at what cost. It is a bounded screen on experimental source, not qualification: the 200-seed and
procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.

**Expected low activation** (development worlds template 7, 42 and procedural 13, 21; 200 turns;
retail `market` boundary; merged head with `main` `4ecfb54d`, native `43cbd22a`). Reliefs: 1-3 per world,
45-71 relief-turns. Purchases (`RS`): 0, 2, 2, 2 per world; food bought 0, 1.17, 0.20, 0.21 units;
delivered at most 0, 2.33, 0.40, 0.42 rations (at least 0, 2.26, 0.35, 0.33); most relief money is held to
the fund's cap (9-24 units paid in) and returned when the relief ends; the rest of each upkeep (90-160
units) is sunk as before. Where need was recorded, owners often held no food (`need_without_owned_food`
0-3 region-turns). Leagues (`GM`): template 7 two leagues, no levy or sack, dues 12 units (returned at
dissolution); template 42 one league, one levy claim (loss 0.087, paid 0.044: the fund was short);
procedural 13 ten leagues, 12 joins, 107 levy claims paid 4.70 units, dues 73.3 units, dissolutions by
war 4, guild dissolved 4 departures, dormancy 2, too few members 1; procedural 21 eight leagues, 107 levy
claims paid 7.31 units and one sack claim (loss 4.07, paid 0.05), dues 51.3 units. Living guild purses
end lower with leagues (procedural 13: 4.15 off, 3.34 `GD`, 3.18 `GM`; procedural 21: 4.02, 3.44, 3.22);
levies, threats, guild movements, revolts and sacks were the same in all three arms on these worlds. The
arms below therefore use the retail boundary `all` (every controlled region is a pilot, so a relief can buy
wherever its realm records hunger) and the activation rules decide what is reported.

## Arms (all hybrid, 200 turns; template 8 x 4 and procedural 32 x 10 strata)

Common flags: `--agents hybrid --food-allocation --household-retail --household-retail-boundary all
--grain-reserves` (granaries on, as in CW1-CW5, so relief buys after the granaries' procurement).

| Arm | Extra flags | Role |
| --- | --- | --- |
| `R0` | none | the label (default behaviour) |
| `RC` | `--reform-services --reform-services-mode cost_only` | label withheld, payment sunk (cost-only control) |
| `RS` | `--reform-services` | label withheld, payment buys food |
| `G0` | none (= `R0`, not rerun) | no-league control |
| `GD` | `--guild-leagues --guild-league-mode dues_only` | leagues and dues, no claim (cost control) |
| `GM` | `--guild-leagues` | leagues, dues and claims |

`R0` and `G0` are one run per world (the shared off arm): 5 runs per world, 60 runs in all.

## Primary outcomes (three)

1. **`cw6d1_priced_out` (D1a service effect), `RS - RC`.** Priced-out plus offer-short person-turns in
   the pilot regions of realms with a relief in force, per relief-region-turn (the retail frame's
   `priced_out_persons + offer_short_persons` over that realm's provisioned pilot regions, summed over
   the turns its relief is in force, divided by those region-turns). Read in each arm on its own relief
   turns (the arms grant reliefs at different turns once they diverge: a total effect).
2. **`cw6d1_commons_grievance` (D1a label and service), `RS - R0`, with `RC - R0` reported beside it.**
   Commons-movement member-turns per 1,000 resident-turns of the relief realms during their relief turns
   (the movements snapshot's members by creed; `RC - R0` isolates removing the label, `RS - RC` what the
   food adds back).
3. **`cw6d1_member_purse` (D1b claims), `GM - GD`.** The civic purse (`city.wealth`) of cities while
   their guild is a league member, mean over member city-turns.

Each primary: per-world difference, stratum means and sign counts over activated worlds;
nulls reported as nulls. With at least three activated worlds, exact sign flips are
descriptive only. The generic raw report can print sign flips at smaller n; the
evaluation receipt suppresses those primary summaries as insufficient activation.

## Fixed harm panel

Reported for every arm pair above, per stratum: treasury of relief realms (`RS - RC` should be about 0
until refunds: the payment is unchanged; refunds returned), owners' wealth and owned food in relief
regions (`RS - RC`: they sell surplus at the ask), food shortfall after relief (L2/retail), famine
region-turns, commons-movement risings and secessions, reforms granted and repealed (by cause), guild
purses (`GD - G0`: dues), guild wall help, guild movements founded, city unrest and revolts, free cities,
league dissolutions by reason, unclaimed league funds, population and migration.

## Mechanism checks (not primaries)

- D1a: relief money paid in, sunk, spent, refunded (closure `open + paid in - spent - refunded = close`
  per realm-turn); purchases, food bought, cost, ceiling residuals; deliveries with their bounds (at most
  `min(bought, given)`; at least only where the commons fell short); `need_without_owned_food`;
  `credit_rows_withheld`; `RC` buys nothing and holds no money.
- D1b: candidates, links, foundings, joins, departures by reason, dissolutions by reason; every claim
  answers a city history entry (`event_id`); claims paid at most the loss and the cap; `GD` pays no claim;
  fund closure per league-turn; one member per realm.

## Activation (decided before any held outcome is read)

- A world activates for D1a when, in `RS`, reliefs are in force for at least 10 civilization-turns and at least one
  purchase is made. A world activates for D1b when, in `GM`, a league holds members for at least 20 turns
  and at least one claim is paid.
- A primary is reported per stratum only over its activated worlds; with fewer than 3 activated worlds in
  a stratum the primary is reported as "not activated" (counts given), not tested.

## Recovery amendment 1 (before the freeze or held outcomes)

The fresh cohort is template 3701-3706 and procedural 3801-3806, reserved by the
lead after reconciling the full main and recovered-branch registry. CW5c already
used 3301-3306 and 3401-3406; those seeds are not reused.

The primary commons-members denominator is the recorded population of relief
realms. Exact adult counts per realm are absent from snapshots, so the proposed
adult denominator cannot be recovered honestly. This measures members per 1,000
residents, not an individual grievance rate; members abroad can contribute to a
targeted movement's recorded membership. The civic-purse primary uses the snapshot's
recorded purse rounded to 0.1, not unrecorded higher precision. No causal claims
are made from tiny activated cohorts. Sign-flip probabilities remain descriptive;
fewer than three activated worlds are reported as insufficient activation.

The standalone extractor/runner is `scripts/cw_d1_screen.py`, avoiding changes to
historical extractors. It checks both D1 record schemas, per-realm and per-league
fund closure, purchase residual closure and delivery upper bounds. The generic
fixed harm panel retains unknown values as unknown. Owner wealth by relief region,
exact wall help, and exact adult counts are not in snapshots and remain unmeasured,
not zero. The state machine verifies claim event ids against city history before
payout; bundle metrics retain those ids but cannot independently recover absent
city-history tuples.

## Extractor requirements (before the freeze)

Read only the bundles' records (`reform_services`, `guild_leagues`, `household_retail`, movements and
cities snapshots); verify every frame with the Python readers (`record_status`) and the closures above;
refuse a run whose record is malformed or unobserved on a turn that should be observed; record source,
native, extractor and schema identities. Validate on the four development worlds and record the check
counts here.

## Compute

Timing pilot on this source (10 runs, one worker) projects the 60-run held
screen, with the runner's 1.5 margin, below a **0.75 wall-summed core-hour
ceiling**. This revises the unexecuted draft's 0.5-hour proposal based on actual
container contention, before held outcomes. The source receipt records actual
per-arm times, projection and ceiling; held runs use one worker. No offline
chunk limit is raised. This is a bounded screen, not a qualification gate.

## Not tested here

The one-off grant relief every reform gives its movement (unchanged by D1a); relief transport between
regions; league payouts for occupation without a sack; aggregate modes (both switches are hybrid-only).
