# Local collective budgets and material bargaining (L9, `--local-budgets`)

Lane L9 of the [livelihoods sprint 2 plan](../superpowers/roadmaps/livelihoods-commons-sprint2.md).
Default off. Requires `--agents hybrid` and `--grain-reserves`. A service whose own
switch is off produces no proposal. `--local-budget-mode {bargained,fixed_shares}`
(default `bargained`) is read when given. Source: `src/chronicler/local_budgets.py`
(behavior) and `src/chronicler/local_budgets_state.py` (persisted data, under
`WorldState.livelihoods.local_budgets`).

## What it adds

One existing decision point per civilization makes a finite budget choice: its ruler,
judged at its seat city. It decides once a turn, in Phase 10 of turn T, for turn T+1.

- Governed services spend only through an accepted envelope. These are public granary
  purchases, granary works, L1 workshop bills and, through registered providers, L8 warden
  bills (`--commons-rules`) and academies' purchases from L6a workshop firms
  (`--workshop-payroll`).
- The council does not invent a politics simulator. It reuses existing factions' influence,
  existing city grievance, and the services' own costs and receipts.
- Political response follows observed delivery. It feeds the existing chain from city
  grievance to unrest, revolt, concession and free city. Those outcomes are the
  consequences; they are not new.

## Timeline

| When | What |
| --- | --- |
| Phase 10 of T, last livelihoods hook (after the granary pass, convoys and cities) | settle the envelopes that executed in T; apply the response; decide T+1 from the dated observations of T; install the storage policies |
| Phase 2 of T+1, storage plan | storage works within its envelope (policy `maintain`/`expand` with a work budget of envelope / 2 coins; every other storage region is set to `neglect`) |
| Phase 2 of T+1, workshop plan | a site's bill is paid only if its civ holds an envelope covering it (`workshops._plan_funding` → `local_budgets.workshop_funded`) |
| Phase 2 of T+1, commons rules plan | a rule's warden bill is paid, and a new rule adopted, only within the envelope for its stand (`commons_rules.prepare_phase2` → `local_budgets.envelope(..., "wardens", claim=...)`) |
| Phase 10 of T+1, granary pass | the civ's purchase budget is its relief envelope, at most its treasury above the floor (`grain_reserves.tick_grain_reserves` → `local_budgets.procurement_budget`); L4 convoys then spend only what the envelope left |
| Phase 10 of T+1, payroll hook (after academy procurement) | an academy's purchase from a workshop firm is paid only within the envelope for (ruler, site) (`workshop_payroll._sell` → `local_budgets.envelope(..., "teaching_supplies", site=...)`) |
| Phase 10 of T+1, L9 hook | settlement of T's envelopes, then the next decision |

Envelopes are persisted, so a checkpoint between turns resumes exactly. Execution traces
recorded by the services within a turn are cleared at that turn's settlement, so they are
empty at every turn boundary.

## Budget

`budget = floor(ENVELOPE_SHARE × max(0, projected − FLOOR − obligations − committed))`.

- `projected` is the civ's treasury after the `keep` changes already queued
  (`finance._projections`).
- `obligations` are coins a provider will spend next turn that it cannot cap, recorded by
  provider group in the decision (`reserved`).
- `committed` is any envelope still open (none for the built-in one-turn services).

Every accepted envelope of a civ is committed against this single budget, so two services
never spend the same coins. Settlement checks that no service spent more than its envelope.

**Teaching: one channel bargained, one reserved.** Academies get paid supplies in two
ways.

- **Their own market procurement** (`learning_services.procure_learning_supplies`) buys
  against the whole projected treasury in Phase 10, before any livelihoods hook. It takes no
  budget parameter and `learning_services.py` is byte-pinned, so it cannot be capped without
  a reviewed edit. Its dated upper bound is reserved first as an obligation: from the last
  procurement receipts of the civ's academies, the larger of what was paid and the full want
  `min(learners, 8 × scholars) × craft price`.
- **Their purchase from an L6a workshop firm** for the need left after that procurement is
  a ruler's Phase 10 treasury spend in a sprint module, so it is a bargained service:
  `teaching_supplies` (below).

L5 learning cohorts spend no treasury (learners pay with their attended time and seats come
from delivered teaching), so there is nothing of L5 to govern.

## Constituencies and measured burdens

Two existing constituencies bargain. Each measures its burden in its own unit, from turn
T's receipts only. An unknown observation stays `null`, never zero.

| Constituency | Voice (existing influence) | Measured burden (unit) | Its services |
| --- | --- | --- | --- |
| commons: the poorer households | the faction the movements model allies with the commons creed (`agent_movements._ally_faction(COMMONS)`, the cultural faction) | food shortfall of the poorer half by means (L2 receipts; without L2, the regional post-release shortfall). Plus the reserve gap: each granary's deficit, up to the harvest shortfall its own yearly harvest mean expects over `HORIZON` turns. Plus granary wear: extra spoilage of held grain over `HORIZON` turns, and the reserve target the worn capacity cannot hold (food) | relief, granary works |
| patricians: the towns' merchants and burghers | `cities._merchant_influence` (merchants, plus burghers with `--guilds`) | crew work standing idle at the civ's workshop sites (work) | workshops; teaching supplies bought from workshop firms (the crew's wages the sale covers); wardens (the timber kept for the towns' crafts) |

The existing movements model also lists the merchants as the opponents of poor relief
(`REFORM_OPPONENTS`). Here the two constituencies prefer different allocations only because
their measured burdens differ.

## Proposals

A civ gets at most `MAX_PROPOSALS` (8) proposals. Each has:

- an executable cost in whole coins;
- eligible recipients (region indices, and a workshop site id);
- exclusive claims;
- an expected delivery;
- the burden it relieves for each constituency.

The bound keeps each constituency's best items per coin in turn, never comparing units
across constituencies.

- **`relief`** (one per civ, divisible). Recipients are the civ's own granaries below
  target, net of grain already on the road. The cost and the grain are what the granary
  purchase rule could buy from the observed surpluses, simulated with an unlimited
  envelope:
  - the realm's markets within `MAX_HOPS`, nearest then cheapest;
  - then one step abroad, cheapest first, where a foreign market sells only beyond its
    own ruler's granary deficits (every ruler buys at home first);
  - whole coins per purchase, so a market worth less than a coin sells nothing;
  - transit loss off the granary's own market.

  The commons' relief is, per granary, the smaller of the grain it would get and its
  observed shortfall plus expected reserve gap. With no reachable surplus there is no
  proposal: the procurement could not execute it.
- **`granary_maintain` / `granary_expand`** (per storage asset of the civ, divisible). These
  are storage work. It is bounded by the asset's remaining batch, `MAX_WORK_BUDGET` (4), and
  the timber on hand net of merchant commitments, at 2 coins per work unit.
  - Maintenance relieves granary wear pro rata: `REPAIR_GAIN × work / REPAIR_WORK` of
    condition.
  - Expansion relieves only a reserve target cut by capacity.
  - Both claim `storage:<region>`, so they are incompatible.
- **`workshop`** (per open L1 site, indivisible). The cost is the site's next bill
  (`workshops._bill`). Funding an operating site puts its crew's diverted time to work: the
  stake is the crew's available work. A construction installment counts pro rata
  (`installment / CONSTRUCTION_COST`). In `cost_only` mode funding never puts a crew to
  work, so the patricians gain nothing from it.
- **`teaching_supplies`** (per open L6a firm in the civ's land, divisible; requires
  `--workshop-payroll` with a customer, so not `no_customer`). Recipients: the firm's region
  and site; claim `teaching:<site>`.
  - The cost and the crafts are what the firm could sell, by L6a's own sale rule, to the
    civ's academies whose procurement this turn was fully informed. Each academy has its
    remaining need, at its craft price, from the firm's wares: its inventory plus last
    turn's titled wares, because the firm titles the new output before it sells.
  - The patricians' stake is the firm crew's wages the sale's cash would cover: owed wages
    plus next turn's full-crew bill beyond the firm's cash, as crew work at
    `WAGE_PER_WORK`.
  - A flush firm's crew gains nothing; its surplus cash is distributed back to the ruler
    anyway. The learners have no separate voice (see Limits).
- **`wardens`** (per L8 commons rule of the civ, or per stand L8 would adopt; requires
  `--commons-rules`). Recipients: the stand's region; claim `wardens:<region>:<slot>`.
  - Proposals read the timber account the next planning reads, settled in this turn's
    Phase 2. A rule is proposed only if it would continue (no repeal reason). An adoption
    candidate must meet L8's own adoption test: harvested, depleted, not cooling. Adoption
    is indivisible, because L8 adopts only with the full first bill; continuation is
    divisible, because a partial payment gives partial coverage.
  - The cost is the full bill (`ADMIN_COST`). L8 applies Commons Management's share
    from the last settled funding ratio when it plans next turn, but the institution's
    legitimacy can change before then, so the full bill is promised (see Limits).
  - The patricians' stake is the timber the rule keeps from open access over `HORIZON`
    turns: the L3 reference crew's harvest above the quota, bounded by the standing stock
    and its regrowth, as the crew work its raw loads could supply the towns' crafts
    (`K_RAW_PER_WORK`). It is zero when the last receipt shows nobody could harvest.
  - The commons gain nothing: the rule restricts their timber access, and L8's own
    grievance channel already carries that side of the conflict.

## Arbitration (`bargained`)

The rule is fixed and deterministic.

1. Each constituency computes its own preferred feasible allocation. It funds greedily by
   its relieved burden per coin, with one award per claim. Only divisible services may be
   funded partially, with what is left.
2. A compromise allocation funds greedily by `Σ influence × relief / own best` per coin.
3. Each candidate's satisfaction for a constituency is the share of that constituency's own
   best relief it delivers. It is 1 for a constituency with nothing feasible to gain.
4. The ruler adopts the candidate with the highest `Σ influence × satisfaction`. Ties go to
   the compromise, then to the constituencies in declaration order.

Each award is a promise to the constituency with the largest weighted share in it.

No constituency can hold incompatible promises:

- one allocation is adopted, and its claims are unique (checked at commit);
- its sum never exceeds the budget (checked at commit).

Every decision records:

- the outcome: `none`, `uncontested`, `commons_first`, `patricians_first` or
  `compromise`;
- the constituencies' own allocations;
- satisfactions and scores;
- awards and refusals (`no_support`, `budget`, `incompatible`, `not_chosen`).

## Control (`fixed_shares`)

The control commits the same budget, split by declared shares:

- relief 0.4, granary 0.3, workshop 0.3 for the built-in groups;
- a registered group (teaching 0.15, wardens 0.15) adds its weight only while its provider
  is active (its switch is on), and every share is then divided by the active total. With
  only the built-in groups the split is exactly 0.4 / 0.3 / 0.3; with both registered groups
  active it is 0.31 / 0.23 / 0.23 / 0.115 / 0.115;
- within each group, items are funded in the fixed service and recipient order;
- an unused share stays unspent.

There is no bargaining and no political response. This is the cost-retaining comparison:
the same envelope rule and services, a different allocation rule.

## Delivery, deferral and response

At the next Phase 10 each envelope is settled from the service's own receipts.

- **Relief:** the grain bought or dispatched for the civ and the coins spent, including L4
  convoy purchases from the remaining envelope. It is kept at 95% of the expected grain or
  coins, or once every granary deficit of the civ is closed. Otherwise it is deferred:
  `treasury_shortfall` when the treasury above the floor capped the envelope, else
  `no_supply`. Convoys deduct both their purchase and their escort fee from the same
  procurement budget, so escort fees are spent inside the envelope; they are itemised per
  settlement. (A lead review on 2026-11-05 found the first landing counted convoy
  purchases twice, which raised in a procedural world; corrected with a regression test.)
- **Granary works:** the storage receipt's delivered work against the promised work. A
  shortfall is classed as follows: `treasury_shortfall` when the treasury at the storage
  plan could not cover it, `inputs_short` (timber or remaining batch), `work_short` (native
  delivery), `recipient_lost` (the region changed ruler).
- **Workshop:** the site was funded and paid, or deferred. Deferral reasons are
  `treasury_shortfall`, `cost_rose` (the bill grew beyond the envelope), `recipient_lost`
  (the site closed or the region changed ruler) or `service_off`.

A deferral is visible in three places:

- the settled commitment, with its decided and settled turns and reason;
- one `budget_deferral` event per civ and turn (importance 2);
- the viewer.

**Response (`bargained` only).** For each settled promise with a sponsor, the venue city's
grievance moves:

- `+BROKEN_GRIEVANCE × (1 − delivered share)` for a deferral;
- `−KEPT_GRIEVANCE` for a kept promise.

The venue is the site's city, else the civ's largest city in the single recipient region,
else the seat city. The seat city is the civ's city in its capital region, else its largest
city. The change is applied after selection, and only from observed delivery. Its sum is
capped at `RESPONSE_CAP` per city per turn. Grievance stays in [0, 1].

Settlement of the registered services:

- **Teaching supplies:** the firm's payroll receipt for the turn: sales in whole units
  (spent) and crafts delivered. It is kept at 95% of the envelope or the expected crafts, or
  when the sale met the academies' remaining need. Otherwise it is deferred:
  - `no_demand` when no informed order had need left;
  - `inputs_short` when the wares left are worth less than one coin at today's craft
    price;
  - `treasury_shortfall` otherwise;
  - `recipient_lost` when the firm closed or changed ruler.
- **Wardens:** L8's receipt for the stand. It is kept when the payment covered the
  promised share of the bill (`paid ≥ min(envelope, bill)`). Otherwise it is deferred with
  `treasury_shortfall`, or with `cost_rose` when the bill exceeded the proposal's cost.
  Without a receipt:
  - a rule repealed because its stand recovered is kept (the need ended);
  - a lapsed rule is `recipient_lost`;
  - another repeal is `service_off`;
  - a stand that was not adopted is `not_adopted`.

Grievance then decays and feeds unrest through `cities._unrest` next turn. No unrest is
added directly, so there is no second unrest signal.

## Declared parameters (modeling choices, not calibrated)

| Constant | Value | Proposed tuning key |
| --- | --- | --- |
| `ENVELOPE_SHARE` | 0.25 of the disposable treasury per turn | `livelihoods.budgets.envelope_share` |
| `FLOOR` | 20 (as grain reserves' `TREASURY_FLOOR`) | `livelihoods.budgets.floor` |
| `HORIZON` | 10 turns (granary wear, expected reserve gap) | `livelihoods.budgets.horizon` |
| `BROKEN_GRIEVANCE` | 0.10 × undelivered share | `livelihoods.budgets.broken_grievance` |
| `KEPT_GRIEVANCE` | 0.03 | `livelihoods.budgets.kept_grievance` |
| `RESPONSE_CAP` | 0.10 per city per turn | `livelihoods.budgets.response_cap` |
| `KEPT_RATIO` | 0.95 | (constant) |
| `MAX_PROPOSALS` | 8 per civ per turn | (constant) |
| `FIXED_SHARES` | relief 0.4, granary 0.3, workshop 0.3; registered teaching 0.15, wardens 0.15 (scaled while active) | (constant) |

The keys are read through `tuning.get_override`. Until they are added to
`KNOWN_OVERRIDES`, a YAML file naming them loads with an "unknown key" warning.

## Provider interface (L5, L6, L8)

A service joins the one budget by appending `"module:attribute"` to
`local_budgets.PROVIDERS`. The order is append-only. The attribute is an object with:

- `services`: its unique service names.
- `group`: its `FIXED_SHARES` group. It gets no share in the control unless declared there.
- `active(world) -> bool`: whether its service runs (its own switch). A registered group
  takes a fixed share only while active. The default is `True`.
- `proposals(world, civ, obs) -> list[dict]`: the `Proposal` fields (`service`,
  `recipients`, optional `site`, `claims`, `cost` ≥ 1 coin, `divisible`, `unit`,
  `expected`, `relief` by constituency, `detail`). They come from the dated observations of
  `obs.turn` only. `obs` carries `turn`, `economy`, `demand`, `price`, `surplus`, `hunger`
  and `held`.
- `install(world, commitments)`: called once per decision with this provider's new
  envelopes, possibly none. It must make the service spend only within them next turn.
  At execution the service reads its amount with
  `local_budgets.envelope(world, civ, service, site=..., region=..., claim=...)`. That is
  the sum of the civ's open envelopes for the service, optionally one site, recipient
  region or claim, and 0 without one. It returns `None` when L9 is inactive, which means
  keep the legacy rule. The service may record a trace
  with `local_budgets.record_execution(world, cid, service, **fields)`.
- `settle(world, commitment, obs) -> dict`: the observed delivery from the service's own
  receipts: `outcome` (`kept`/`deferred`), `reason` (one of `REASONS`), `spent` (never above
  the envelope), `delivered`, `ratio`, `detail`.
- `obligations(world, civ, obs) -> int`: coins it will spend next turn that it cannot cap.

Relief must be declared in an existing constituency's unit: food for commons, crew work
for patricians. A new constituency would extend `CONSTITUENCIES` (append-only) and
`_influence`.

Registered providers, all in `local_budgets.py`, use this interface:

- `RELIEF`, `GRANARY` and `WORKSHOP` (built-in);
- `TEACHING`: L6a firm purchases are bargained; academy market procurement is reserved;
- `WARDENS`: L8.

Registered from other modules (appended in order): RS5's clearing wardens, PL3's
maintenance obligation and C2's `chronicler.epidemic_care:BUDGET_PROVIDER` (service
`epidemic_care`, group `relief`, one divisible envelope per region with a reported outbreak;
the commons' relief is the deaths care would avert valued in food units;
[epidemic care](epidemic-care.md)).

Keeping the providers in `local_budgets.py` keeps the hooks in the services' own modules to
a single envelope read each.

## Shared-file hooks (each listed for the lead's inverse layer)

- `src/chronicler/livelihoods_state.py`: the `local_budgets` switch and field.
- `src/chronicler/livelihoods.py`: the CLI choice `local_budget_mode`, the two argument keys
  with help text, and the prerequisite check.
- `src/chronicler/workshops.py` (unpinned): `_plan_funding` asks `workshop_funded`. This is
  the identity when L9 is off.
- `src/chronicler/grain_reserves.py` (chain-pinned): three lines after the purchase budget
  is computed, guarded by `world.livelihoods`. This is the identity when L9 is off.
- `src/chronicler/batch_manifest.py` (pinned) and its mirror in
  `tests/test_batch_manifest.py` (pinned): `local_budgets` and `local_budget_mode` in
  `SIMULATION_ARG_KEYS` and in the omit-when-None tuple.
- Part 2, sprint modules, unpinned. Both are the identity when `envelope()` returns `None`.
  - `src/chronicler/commons_rules.py`, `prepare_phase2`: one import; a `payable(owner,
    rule)` helper (the treasury left, within the stand's warden envelope when L9 is
    active); and two uses of it, for a continuing rule's payment and the adoption test.
  - `src/chronicler/workshop_payroll.py`, `_sell`: the buyer's budget is capped by the
    `teaching_supplies` envelope for (ruler, site), less what this firm already sold it
    this turn.

## Evidence

Development evidence only. It uses template seeds 1–3; the held cohorts 301–306 and
401–406 were not run. Every run is a single world, not a population estimate. No 200-seed
or procedural gate was run.

### Tests

- `tests/test_local_budgets.py` (offline, 29 tests; guard-clean under the offline lane's
  guard, about 1.6 s with the workshop and wiring modules). It runs the real storage,
  workshop and granary-purchase code on the template world (seed 42). It covers:
  - proposals with costs, recipients and dated benefits;
  - the reserve gap and the rival-buyer rule;
  - each constituency's own allocation and the influence-decided choice;
  - incompatible promises refused;
  - one budget less obligations; teaching reserved; the proposal bound;
  - unfunded promises doing nothing;
  - a changed allocation moving goods, work and payments;
  - relief first with maintenance debt;
  - production first leaving the poorer households' next shortfall unrelieved;
  - budget loss giving a dated, visible deferral;
  - a response that follows delivery, not selection, and its cap;
  - the fixed-shares control;
  - identity hooks when off;
  - exact pickle resume;
  - unknown versus zero in the snapshot;
  - a registered provider;
  - switch-off lapses; CLI and prerequisites;
  - convoy relief counted once, inside the envelope (the lead's regression test);
  - part 2, on the L8 and L6a fixtures:
    - warden bills inside their envelope; `None` is byte-identical to the legacy rule;
      adoption refused without a full envelope;
    - wardens proposed from the dated stock account and settled from L8 receipts;
    - firm academy sales capped by the envelope, none without one, identity when off;
    - teaching-supplies proposals and settlement;
    - fixed shares scaled only while a registered group is active.
- `tests/test_local_budgets_native.py` (real extension, 4 tests):
  - every governed payment in a 60-turn hybrid run (seed 3) sits inside an accepted
    envelope of its payer for that turn: workshop bills, storage work, granary purchases.
    Awards never exceed the budget, and claims are unique;
  - bargained and fixed shares move different spending;
  - a world with open envelopes resumes exactly from a checkpoint for four turns: world
    JSON, native checkpoint state and the global RNG;
  - part 2: on seed 1 with every switch the providers need (200 turns), every warden
    payment and every firm academy sale sits inside an accepted envelope, and spent equals
    paid.
- Viewer: `localBudgets.test.ts` and `LocalBudgets.test.tsx` (6 tests after part 2). Full
  suite 124 files, 1,249 tests; lint and build pass.
- Bounded offline lane (`scripts/run_python_oracle_checks.py`) on the part-2 source:
  PASS, 57 chunks, 6,197 passed, 69 skipped, 0 failed, 233.7 s. The livelihoods chunk took
  3.2 s of 110.
- Feature-off identity against the base source (bd22f70d), on the native extension, 120
  turns:
  - seed 2 with `--grain-reserves --grain-storage --workshops --food-allocation` (L9 off);
  - seed 1 with no livelihoods switch.

  In both, `history` and `world_state` are equal and `state.json` is byte-identical. Only
  the bundle's `metadata` (source identity) differs.
- Part-2 switch-pair identity (L9 off, commons rules and workshop payroll on) against the
  integrated head 60b63f2, on the native extension, 200 turns, template seeds 1 and 3.
  - Flags: `--grain-reserves --public-grain-shipments --scholarship --techniques
    --academy-services --workshops --workshop-payroll --timber-stock --commons-rules
    --food-allocation`.
  - Result: `history` and `world_state` are equal and `state.json` is byte-identical.
  - Both runs exercise the hooked paths. Seed 1 adopted a rule and paid 214 coins of
    wardens, and its firms made 44 academy sales. Seed 3 adopted 4 rules and paid 298.
  - The same check on procedural seed 7 (32 × 10, adding `--grain-convoys
    --grain-storage`) is also identical. It adopted 7 rules, paid 522 coins of wardens
    and made 21 firm academy sales.

### Funnel, 200 turns

All arms use `--agents hybrid --grain-reserves --grain-storage --workshops
--food-allocation`. The bargained and fixed-share arms use the default share (0.25).
`targeted` adds `--food-allocation-regime targeted_relief`. `share03` sets
`livelihoods.budgets.envelope_share: 0.03` by tuning.

| Arm | Seed | Ruler decisions | With budget | With proposals | Proposals | Envelopes | Coins committed | Coins spent | Kept | Deferred (reasons) | Responses raised / eased | Commons first / patricians first / compromise |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bargained | 1 | 800 | 597 | 301 | 526 | 293 | 1104 | 1098 | 291 | 0 | 0 / 3 | 0 / 0 / 0 |
| bargained | 2 | 607 | 430 | 324 | 329 | 141 | 592 | 585 | 138 | 2 (relief no supply; workshop recipient lost) | 0 / 4 | 0 / 0 / 0 |
| bargained | 3 | 800 | 764 | 481 | 952 | 533 | 1994 | 1983 | 528 | 2 (relief no supply) | 2 / 24 | 0 / 0 / 0 |
| fixed_shares | 1 | 800 | 673 | 387 | 543 | 409 | 1122 | 1058 | 349 | 57 (granary work short) | — | — |
| fixed_shares | 2 | 607 | 355 | 290 | 327 | 43 | 211 | 204 | 40 | 3 (relief no supply; 2 workshop recipient lost) | — | — |
| fixed_shares | 3 | 671 | 602 | 553 | 1065 | 856 | 2366 | 2260 | 758 | 93 (91 granary work short; 2 relief no supply) | — | — |
| targeted | 1 | 800 | 613 | 354 | 672 | 287 | 1161 | 1158 | 286 | 0 | 0 / 29 | 1 / 0 / 0 |
| targeted | 2 | 607 | 413 | 363 | 371 | 173 | 723 | 681 | 170 | 1 (relief no supply) | 0 / 10 | 0 / 0 / 0 |
| targeted | 3 | 800 | 748 | 448 | 984 | 571 | 2043 | 2027 | 564 | 4 (2 granary work short; 2 relief no supply) | 2 / 19 | 0 / 0 / 0 |
| share03 | 1 | 800 | 452 | 295 | 559 | 268 | 973 | 967 | 266 | 0 | 0 / 11 | 0 / 0 / 0 |
| share03 | 2 | 607 | 268 | 290 | 327 | 1 | 1 | 0 | 0 | 1 (relief no supply) | 0 / 0 | 0 / 0 / 0 |
| share03 | 3 | 800 | 658 | 472 | 1096 | 501 | 1603 | 1601 | 499 | 2 (relief no supply) | 2 / 35 | 15 / 0 / 1 |

Actual spending from the services' own receipts over 200 turns. In the off arm, storage
runs under the default `neglect` policy.

| Arm | Seed | Workshop coins | Crew work allocated | Storage coins | Storage work | Relief coins | Relief grain |
| --- | --- | --- | --- | --- | --- | --- | --- |
| off | 1 / 2 / 3 | 1035 / 709 / 1677 | 205.5 / 45.6 / 523.2 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 1 / 1 | 0 / 5.2 / 5.6 |
| bargained | 1 / 2 / 3 | 1077 / 581 / 1655 | 181.4 / 64.6 / 329.0 | 19 / 0 / 325 | 8.3 / 0 / 143.8 | 2 / 4 / 3 | 12.5 / 30.5 / 23.0 |
| fixed_shares | 1 / 2 / 3 | 924 / 204 / 1668 | 160.8 / 0 / 468.8 | 134 / 0 / 589 | 56.6 / 0 / 237.5 | 0 / 0 / 3 | 0 / 0 / 18.0 |

What the runs show:

- **The mechanism activates in every world.** Spending stays inside its envelopes. Spent
  coins are 94–99.9% of committed coins wherever more than one envelope was awarded. Kept
  promises ease city grievance, and broken relief promises raise it.
- **The allocation rule changes what is actually done.** With the same envelope rule,
  bargaining spends little on granary works whose measured benefit is nil: 19 against 134
  coins on seed 1 and 325 against 589 on seed 3. Fixed shares fund those works anyway.
- **The budget rarely forces a choice in these worlds.** At the default share,
  treasuries are large (hundreds of coins), so most adopted allocations are `uncontested`
  or `none`. At a 0.03 share, seed 3 has 15 commons-first decisions and one compromise,
  and 154 workshop bills are refused for budget.
- **Relief is supply-bound.** Markets rarely hold grain beyond four turns of demand, so a
  world has 0 to 18 relief proposals in 200 turns. Natural runs had no budget-loss
  deferral: the 0.75 of disposable treasury left outside the envelope absorbed every
  shock. Deferrals came from supply (`no_supply`), work (`work_short`) and closed sites.

### Acceptance stories from real runs (CONSTRUCTED where marked)

Natural runs did not produce each story, so three paired cases were constructed on the
real seed-3 run. Each arm is the real simulation except one named intervention. It
reproduces the natural run snapshot for snapshot up to that intervention (90 or 91
identical snapshots).

1. **A changed allocation moves actual goods, work and payments; relief first with
   maintenance debt; production first leaving some households worse off.** CONSTRUCTED,
   share 0.03 world, decision of turn 91 for Dorrathi Clans (civ 0). The budget is set to
   3 coins and the two voices' influence to 0.6/0.1 or 0.1/0.6, restored right after.
   Proposals: relief 1 coin (granaries of regions 1, 3 and 4), granary works 1 coin each,
   two workshop bills of 3.
   - Relief first (`commons_first`): relief and granary expansion adopted, both workshop
     bills refused for budget. In turn 92 it bought 5.59 grain into region 1's granary
     and did 0.28 storage work. Both workshop sites stood idle with arrears of 3 and
     condition worn to 0.95 and 0.80: maintenance debt on the public workshops.
   - Production first (`patricians_first`): one workshop bill adopted, relief refused for
     budget. In turn 92 the workshop's upkeep was paid and its crew worked 0.4; no grain
     was bought.
   - Turn 95: region 1's granary released 2.24 grain under relief first, and the region
     was not short. Under production first the granary was empty. The region's poorer
     half (12 people) was short 3.03 rations, against 1.44 for the richer half (14
     people). Those 4.47 rations are the 2.24 food the release covered.
   - Turn 96 is short in both arms (poorer half 4.42).
2. **Budget loss forces a visible deferral; the response follows delivery, not
   selection.** CONSTRUCTED, default share. Dorrathi Clans' treasury (843) is seized at
   the start of turn 91's Phase 2, after the natural turn-90 decision: relief 1 and two
   workshop bills of 3, unchanged.
   - Both workshop envelopes were deferred with `treasury_shortfall`. The sites went idle
     with arrears 3.
   - The chronicle records: "Dorrathi Clans defers promised spending decided in turn 90:
     workshop (treasury shortfall); workshop (treasury shortfall)."
   - The site cities' grievance rose from 0 to 0.07 (one relief kept, one bill broken) and
     to 0.10.
   - In the natural run, the same selection was delivered. Every promise was kept, and
     the grievance answer was easing (already 0).
3. **Natural examples.**
   - Raised grievance after a broken relief promise: seed 3, turns 102 and 104, +0.07 and
     +0.01.
   - Easing after kept promises: e.g. seed 3, turn 51, city 4 from 0.25 to 0.22.
   - Contested commons-first choices: share 0.03, seed 3, 15 decisions.
   - Of the 12 kept relief envelopes in the bargained, targeted and share03 worlds, 4 were
     followed within 12 turns by a natural release at a recipient granary:
     - seed 1, decided at turns 77 and 79, released 0.7 at turn 90;
     - share03 seed 3, decided at turn 91, released at turns 95 and 96;
     - share03 seed 3, decided at turn 103, released at turn 108.

     Case 1 is built on the turn-91 one.

### Registered services (part 2) and the driver

The driver `local-budgets-evidence/driver.py` reproduces every row of this page: the base
arms above, the provider arms, procedural seed 7 and the constructed pairs with their
natural twins. Its metrics are in `local-budgets-evidence/metrics.jsonl`, and the source and
extension identity in `local-budgets-evidence/source.txt`. The base arms reproduce the
part-1 numbers above exactly.

**Provider arms**, 200 turns: every switch the providers need, `--grain-reserves
--public-grain-shipments --scholarship --techniques --academy-services --workshops
--workshop-payroll --timber-stock --commons-rules --food-allocation`. Procedural seed 7
(32 regions × 10 civilizations) adds `--grain-convoys --grain-storage`.

| Arm | Seed | Decisions | With budget | With proposals | Proposals | Envelopes | Coins committed / spent | Kept | Deferred (reasons) | Responses raised / eased | Awards by service |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bargained | 1 | 800 | 541 | 152 | 231 | 118 | 404 / 392 | 107 | 11 (8 relief no supply; 3 teaching supplies inputs short) | 11 / 12 | relief 17, teaching supplies 3, wardens 55, workshop 43 |
| fixed_shares | 1 | 800 | 566 | 214 | 427 | 244 | 786 / 745 | 227 | 16 (2 relief no supply; 13 teaching supplies inputs short; 1 no demand) | — | relief 12, teaching supplies 42, wardens 10, workshop 180 |
| bargained | 2 | 607 | 434 | 267 | 282 | 93 | 526 / 504 | 85 | 6 (5 relief no supply; 1 workshop recipient lost) | 1 / 19 | relief 16, workshop 77 |
| fixed_shares | 2 | 607 | 355 | 290 | 350 | 46 | 212 / 203 | 41 | 4 (2 relief no supply; 2 workshop recipient lost) | — | relief 6, workshop 40 |
| bargained | 3 | 671 | 617 | 311 | 472 | 401 | 1371 / 1358 | 393 | 7 (5 relief no supply; 2 workshop recipient lost) | 5 / 53 | relief 12, wardens 72, workshop 317 |
| fixed_shares | 3 | 800 | 748 | 367 | 568 | 520 | 1553 / 1542 | 513 | 5 (relief no supply) | — | relief 10, wardens 161, workshop 349 |
| procedural bargained | 7 | 1815 | 1607 | 1343 | 2698 | 1127 | 3713 / 3655 | 1105 | 17 (13 relief no supply; 1 relief treasury shortfall; 1 teaching inputs short; 2 workshop recipient lost) | 13 / 180 | granary expand 87, granary maintain 232, relief 44, teaching supplies 21, wardens 230, workshop 513 |
| procedural fixed_shares | 7 | 1658 | 1256 | 1000 | 2267 | 711 | 1907 / 1856 | 688 | 22 (13 granary work short; 2 relief no supply; 6 teaching inputs short; 1 no demand) | — | granary expand 21, granary maintain 366, relief 24, teaching supplies 22, wardens 73, workshop 205 |

Actual spending from the services' own receipts:

| Arm | Seed | Workshop coins | Crew work | Storage coins | Relief coins / grain | Warden coins (turns covered) | Teaching coins / crafts | Treasury at end |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L9 off | 1 | 951 | 215.3 | — | 19 / 131.3 | 214 (109) | 157 / 50.4 | 1580 |
| bargained | 1 | 270 | 18.9 | — | 12 / 93.6 | 110 (55) | 0 / 0 | 1964 |
| fixed_shares | 1 | 621 | 76.9 | — | 10 / 68.0 | 14 (10) | 100 / 39.8 | 1832 |
| L9 off | 2 | 633 | 39.5 | — | 15 / 93.7 | 0 | 0 | 1881 |
| bargained | 2 | 481 | 13.6 | — | 23 / 172.4 | 0 | 0 | 1653 |
| fixed_shares | 2 | 198 | 0 | — | 5 / 42.5 | 0 | 0 | 831 |
| L9 off | 3 | 1266 | 289.1 | — | 12 / 73.7 | 298 (149) | 0 | 1851 |
| bargained | 3 | 1208 | 291.9 | — | 8 / 49.1 | 142 (71) | 0 | 1963 |
| fixed_shares | 3 | 1212 | 252.0 | — | 10 / 64.2 | 320 (160) | 0 | 2165 |
| procedural bargained | 7 | 2221 | 345.0 | 869 | 46 / 320.4 | 460 (230) | 57 / 26.7 | 3382 |
| procedural fixed_shares | 7 | 825 | 70.6 | 834 | 26 / 177.6 | 144 (73) | 22 / 19.2 | 1945 |

What these runs show:

- **All six services run inside one budget.** In the procedural world, every governed
  payment is a settled envelope: relief, granary works, workshops, wardens and teaching
  supplies (the native test checks wardens and sales on seed 1). Every settled warden
  promise was kept: 55, 71 and 230, none deferred; one seed-3 envelope was still open at
  the end. The procedural world
  also shows a natural budget-loss deferral (relief, `treasury_shortfall`), which the
  template worlds never did.
- **The commons choice is real.** The ruler pays wardens only while the patricians'
  stake is positive. On seed 1, a resting rule whose stand nobody could harvest got no
  envelope, went unfunded and was repealed after three turns; L8 alone keeps paying until
  it is repealed as idle. Warden spending is 110 against 214 coins on seed 1, and 142
  against 298 on seed 3, against L9 off.
- **Teaching is supported only through the firms' crews.** Bargained mode funds academy
  purchases only where the firm owes wages.
  - Template worlds: rare. Seed 1 has 3 envelopes, all `inputs_short`: the craft price fell
    below what the firm's few wares could sell for.
  - Procedural world: 21 envelopes, 20 kept, 57 coins for 26.7 crafts.
  - Fixed shares fund them by rule: 42 envelopes on seed 1 (28 kept, 100 coins).
- **Budgets cascade on seed 1.** The poorer civs' envelopes cover few workshop bills (270
  against 951 coins with L9 off). Firms then rarely operate, and the academy purchases
  that L9 off made (157 coins) disappear. This is a consequence of the allocation and
  budget rule, not a welfare claim.

## Limits

- Relief is supply-bound in the development worlds. Their markets rarely hold grain beyond
  the reserve rule's four turns of demand, so relief is rarely executable whatever the
  budget. The surplus and one-coin purchase rules are unchanged.
- Teaching: academies' market procurement stays reserved (byte-pinned). The reservation is
  dated, not a bound: an academy whose scholars return after a turn with none buys more than
  was reserved (procedural seed 7, turn 60: 1 coin against 0; review R2, 2026-11-05). Their purchases from
  workshop firms are bargained, but the learners have no separate voice: the only existing
  scholarly voice is the cultural faction (scholarship focus, scientist agendas), and L9
  already uses it for the commons through the movements precedent. Counting it twice would
  double that faction. So in bargained mode teaching wins support only through the firm
  crew's wages. L4 escort fees are paid inside the relief envelope and itemised.
- Wardens: the full bill is promised. Since lead commit 957f47c9, L8 reads Commons
  Management's share (`institution_share`) from the last settled funding ratio, because
  rules are planned before that turn's institutions are funded. The share is therefore
  known at the decision except for changes in the institution's legitimacy before
  planning. Promising the full bill never under-commits: when the institution covers part
  of the bill, at most 2 coins per rule per turn stay unspent inside the envelope.
- A workshop envelope whose site sent no receipt is deferred as `recipient_lost` only if
  the site has closed; otherwise it is `no_economy` (no Phase 2 economy tick) or
  `service_off` (corrected after a lead review on 2026-11-05).
- L7 assisted relocation: the destination ruler's fare assistance depends on next turn's
  moves and is charged in Phase 10, so L9 cannot cap it. Its ceiling
  (`relocation_costs.ASSIST_SHARE` of the treasury) is reserved as an obligation before any
  envelope while relocation runs in assisted mode, so the two never claim the same coins
  (added after a lead review on 2026-11-05; other relocation modes reserve nothing). The
  next turn's gate installs at most that reservation: each decision records its
  obligations by provider group (`Decision.reserved`), and
  `relocation_costs.assistance_budgets` caps its ceiling by `local_budgets.reserved`.
  Review R2 (2026-11-05) found the ceiling recomputed on the next turn's larger treasury,
  beyond the reservation (4 to 9 charges per development world: template seeds 1 and 4,
  procedural seed 7); corrected with regression tests
  (`tests/test_livelihoods_shared_treasury.py`, `tests/test_livelihoods_closure_native.py`).
- A region's controller cannot change between L9's decision (the last Phase 10 hook) and the
  next Phase 2: control changes in Phase 10 politics, which run before the decision, and in
  Phase 5 conquest, after the storage plan. A granary-works policy is therefore paid by the
  ruler it was promised to (checked against `simulation.py` in the same review).
- L9 replaces the `--grain-storage-policy` setting while active. Its last policies remain
  if it is switched off. Switching it off lapses open envelopes.
- The political response reaches only cities: a civ without a city has no venue.
- Nothing here is a welfare or policy-efficacy claim. No 200-seed or procedural
  qualification gate has been run.
