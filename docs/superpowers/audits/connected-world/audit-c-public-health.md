# Audit C: public health and what protection costs (Program C)

Audit lane for Program C, S0 contract audit. Read-only against `/home/user/Chronicler` at
`8abc1acb` (main, PR #82). The working tree is on the lead's branch `claude/connected-world`
(`a955e42`, which adds the plan of record). No tracked file was modified. The only new files are
under this directory (`tools/`, `preflight*.txt`).

Each claim carries one of four labels:
- **[code]**: read directly in the source at the cited `file:line`;
- **[doc]**: taken from project documentation;
- **[pilot]**: measured from bundles that other audit lanes had already produced (development seed
  7, one world each; see section 3.4). This lane ran no simulation;
- **[inferred]**: reasoned from the code but not exercised by a run.

---

## 0. Summary of findings

1. **Epidemics are on by default.** Epidemiology runs by default for new worlds that have the
   contact ledger (`epidemiology.py:64`, `DEFAULT_ENABLED_FOR_NEW_WORLDS = True`) [code]. The
   current quarantine is therefore default-path behaviour. Any change to it must sit behind a new
   opt-in rules switch. "Feature-off identity" means the default run with epidemics on (and
   separately `--no-epidemiology`) stays identical to `8abc1acb`. The *Default* section of
   `docs/integration/epidemiology.md` still says "Off". That is a stale-doc defect: the header of
   the same page and `wave3-defaults.md` say on.
2. **Today's quarantine changes no journey.** Its only consumer is the import-pressure loop
   (`epidemiology.py:610-637`), plus the snapshot and viewer [code]. It works by multiplying all
   four ledger channels by `1 − efficacy` (0.7, or up to 0.9 with techniques), and only for
   foreign sources. It also charges a flat 2 treasury per turn, which the doc says "stands in for
   lost commerce" [doc].
3. **There are two double-count traps in a routing-based quarantine.** (a) The multiplier would
   cut exposure again on the same stock that routing already stops growing. It would also cut
   channels that routing never touched (migrants, soldiers). (b) The flat 2-treasury "lost
   commerce" charge would stack on the real loss of route income, which the route system already
   pays at +2 per route per side per turn (`simulation.py:326-345`) [code].
4. **Trade can be closed without touching Rust.** The real journey systems already handle edge
   removal:
   - agent merchants follow a route graph that Python builds every tick;
   - native merchants in transit replan or unwind with `RETURNED` receipts when an edge
     disappears (`merchant.rs:1438-1467`) [code];
   - economy routes and income come from `resources._compute_active_trade_routes`, an unpinned
     file.

   Migration has no Python-side gate: Rust picks targets from region adjacency
   (`behavior.rs:273`). A border closure for migrants therefore needs a small native input, or a
   pinned adjacency filter with side effects on news diffusion [code].
5. **Channel coverage decides whether quarantine matters** [pilot]. In the existing hybrid
   procedural-7 pilot, 147 of 177 cross-polity epidemic arrivals were carried by migrants and 28
   by merchants. In the aggregate run on the same seed, merchants carried 53 of 70. So a
   trade-only closure should be visible in aggregate worlds and probably weak in hybrid worlds
   until migration closure (C1b) exists.
6. **The ledger has no individual dated contacts.** It stores decayed stock per edge and channel
   (`DECAY` 0.9 / 0.9 / 0.8 / 0.9). If journeys are stopped, exposure decays as 0.9^k (still 59%
   after 5 turns), where the old multiplier cut 70% at once. A real closure is therefore weaker
   and slower than the abstract cut, unless the import basis itself changes (open question Q-C1).
7. **Nothing for disease care exists today.** No care capacity, sanitation, healers or supplies
   exist for disease. Practised medicine techniques lower CFR region by region without workers
   (`techniques.py:150-153, 1096-1103`) [code]. `health_care.py` covers only rural occupational
   injury with spouse or kin care. It leaves disease, combat and mortality alone
   (`health_care.py:1-7`) [code]. A Python seam for diverting labour does exist
   (`recovery_crews.remove_farm_time`, the `farm_labor_factor` column, `recovery_crews.py:575-596`),
   as does a budget authority (L9 `local_budgets.PROVIDERS`) [code, doc]. C2 can use both without
   Rust.
8. **Information is instant and omniscient.** A civ closes the same tick a foreign outbreak
   becomes reportable, wherever any ledger edge links them (`epidemiology.py:1013-1027`) [code].
   The `harvest_forecasts` module is a working dated-report template to copy for C4: ledger-routed
   recipients, delivery delay, and a signal-destroying shuffle control (`harvest_forecasts.py:354-420`,
   pinned, so copy the pattern rather than edit the file).

---

## 1. The epidemic model

### 1.1 State (`EpidemicState`, `epidemiology.py:192-232`) [code]
- `rows: list[RegionInfection]` holds one row per (region index, pathogen index) that has
  infection or immunity. Each row has:
  - `n` and the S/E/I/R shares (rounded to 1e-9, `_normalize` at :308);
  - `burden`, the mean infectious share over the last tick, which drives exports;
  - `cases`, new infections in people;
  - `virgin` and `reported`;
  - `cause` (the event id the next onset cites);
  - a pending import's `source` region and `channel`, persisted so the arrival event is emitted
    with the onset.
- `homelands` and `seen` are (region, pathogen) lists.
- `strains`, `quarantine` (civ indices), `scarcity` (civ index, share), `last_deaths`,
  `deaths_total`, `initialized_turn`, `last_tick_turn`.
- Identity follows the shared contract: region index and civ index, never names. The pathogen
  index is append-only (`PATHOGENS`, :90-108).
- It is persisted in world JSON. `None` is omitted, so old saves load with the feature off
  (`models.py:1173-1174`). The checkpoint header records the flag (`run_checkpoint.py:274`).
  There is a save/load-mid-epidemic test at `tests/test_epidemiology.py:136`.

### 1.2 Turn position [code]
`simulation.py:1989-1996`: Phase 1 runs `phase_environment`, then `tick_epidemics(world, acc)`,
then black swans (`check_black_swans`, which may call `seed_pandemic`), then M35b environmental
events. The rest of the turn:
- Phase 2 trade routes and the goods economy (`:2014`, `:2090-2120`);
- automatic effects, including trade income (`:2185`);
- Phases 3–8, including the TRADE action;
- Phase 9 ecology;
- the agent tick, where merchants move and migrants decide (`:2295-2365`);
- Phase 10, including pilgrimages (`:1329-1345`) and the livelihoods/L9 hooks;
- at the very end, `update_contact_ledger` (`:2727-2731`).

### 1.3 The order inside one tick (`tick_epidemics`, `:505-581`) [code]
1. **Absorb population change** (`_absorb_population`, :584). Newcomers are susceptible; losses
   are proportional.
2. **Modifiers** (`_modifiers`, :342-364):
   - Agent modes (`_hunger_aware`, :367): susceptibility `1 + 0.15·dearth + 0.35·famine`, CFR
     `×(1 + 0.10·dearth + 0.40·famine)` from `ecology.region_hunger`.
   - Aggregate mode: the flat `famine_cooldown` terms +0.2 and ×1.25.
   - Crowding: `+0.5·clamp(pop/carrying_capacity − 0.8, 0, 1)`.
   - Techniques (default on): CFR × `epidemic_cfr_factors` (:533-538).
   - Cities (default on): susceptibility × urban factor (:539-544,
     `cities.epidemic_susceptibility_factors` :1179, `URBAN_SUSCEPTIBILITY 0.5`).
3. **Introductions** (`_introduce`, :602-677), the only randomness. For each pathogen and each
   populated region where it is not already circulating:
   - Spillover in a homeland: `h = spillover·susc·min(3, endemic_severity/disease_baseline)`, one
     draw `epidemic_spillover` (seed, turn, k, t) at :654.
   - Otherwise an import:
     `h = 0.1·r0·susc·S·Σ_j contact(j,t)·burden_j·[1−eff if quarantined & foreign]`, one draw
     `epidemic_import` at :664-665. `contact = contact_ledger.region_contact`: weighted
     (1, 1, 0.25, 2), undirected, all four channels, decayed stock as of the end of the previous
     turn.
   - Each introduction exposes one person. The arrival's channel is the argmax over the dominant
     source edge (:671-673).
4. **SEIRS** (`_step`, :711-735): four seasons, deterministic.
   `new_E = S(1−e^{−βI})`, `β = r0·recovery·susc`, CFR from `_effective_cfr` (:706: pathogen CFR ×
   modifier × 1.5 if virgin, capped at 0.9).
5. **Deaths** (`_apply_deaths`, :738-804):
   - integer deaths are the floor plus a draw `epidemic_deaths` (:769) on the fraction, capped at
     25% of the region per turn (excess recovers, :760-764);
   - `utils.drain_region_pop` (:777);
   - `utils.stage_region_catastrophe_deaths` when the pool tracks population (:778-779;
     demographics-only, shadow, hybrid; `simulation.py:126-128`);
   - `sync_civ_population`, then the labour-scarcity update.
   - In hybrid the staged count goes to Rust in the next region batch (`agent_bridge.py:535-544,
     714`) and Rust kills that many agents of the region.
6. Extinction and compaction (:557-573), reports (`_reports` :840, threshold
   `cases ≥ max(2, 3%·n)`), mutation (`epidemic_mutation`), civ responses (`_civ_responses` :903:
   `plague` event and condition, `signal` stability, hazard cascade, `epidemic_leader` draw for
   leader death), then `_decide_quarantine` (:1001) for the next turn.

### 1.4 Randomness [code]
`_draw(ns, world, *parts) = random.Random(stable_hash_int(ns, seed, turn, *parts)).random()`
(:285-287). The namespaces are `epidemic_spillover|import|deaths|mutation|leader`, plus
`epidemic_homeland` at initialization. There is no global stream, so introduction draws do not
depend on draw order. This meets the program randomness contract as it stands.

### 1.5 Other effects [code]
- **Labour scarcity.** The decayed share of a civ's people killed (×0.9 per turn) divides the
  governance MMP by `1 + 5·scarcity` (`governance_runtime.py:1328-1331`). This is not a labour
  market.
- **Stress.** `emergence.py:82-86` counts epidemic regions.
- **Default-off switch.** `test_feature_off_never_runs_epidemiology_code` (`tests/test_epidemiology.py:156`).

### 1.6 Modes [code]
- All modes run the same Python tick.
- Aggregate mode (`--agents off`): Python owns population and the deaths are drained only.
  The "people" ledger channel holds only hostages, because there are no agent migrations
  (`contact_ledger.py:345-351, 374-378`). Trade contact is the route proxy.
- Hybrid: deaths are staged into Rust; hunger-aware modifiers apply; trade contact is native
  merchant deliveries; "people" is agent migration events.
- **A second disease mortality path already exists in agent modes.** M35b endemic severity
  multiplies native agent mortality (`demographics.rs:175-183`, fed by
  `agent_bridge.py:628`) [code]. It predates this program and is separate from epidemic deaths.
  C2 must not add a third (see section 6).

---

## 2. Quarantine today

| Aspect | What the code does |
| --- | --- |
| **Decision** (`_decide_quarantine`, :1001-1047) | Each living civ, after this tick's reports, closes when all of these hold: some reportable outbreak this tick lies in a region it does not control (uncontrolled regions count as foreign); that region is a **ledger neighbour** of any of the civ's regions (any channel, any direction, any stock ≥ 0.01, adjacent or not; `neighbors()` at :1025); stability ≥ 30; treasury ≥ 2 (:1030). The first match in sorted (region, pathogen) order is the "threat" named in the event. Pathogen severity, contact volume, dependence and cost play no part. There is no hysteresis: the decision is remade every turn. |
| **Cost** | 2 treasury per closed turn in the `keep` category, charged at decision time (:1032-1036). `QUARANTINE_COST`, :172. |
| **Efficacy** | `QUARANTINE_EFFICACY = 0.7` (:173). With `--techniques` (default on): `+0.05·law_codes + 0.15·lazarets` (civ practice levels), capped at 0.9 (`techniques.py:154-155, 1106-1110`; applied at `epidemiology.py:613-616`). |
| **What it multiplies** | Only the import pressure `contact(j,t)·burden_j` into regions controlled by a quarantined civ, from a source with a different controller (:635-637). That covers **all four channels together** (trade, people, soldiers, pilgrims) and both directions of each edge, because `region_contact` is undirected. It also cuts the civ's **own armies'** contact with foreign regions (home→foreign soldiers edge). It does not touch spillover, the civ's exports to others, or spread inside the civ. |
| **Timing** | Decided in Phase 1 of turn t, stored in `state.quarantine`, read by `_introduce` in Phase 1 of t+1. The cost is paid in t. |
| **Effect on actual movement** | **None.** A `grep` for "quarantine" over `src/` finds only epidemiology, techniques (bonus), provenance (`ChronicSpec(1, False, None, "border closure")`, `provenance.py:853`), narration lists and the CLI help. Trade routes, the merchant graph, migration, armies, pilgrims and convoys are untouched. The doc says so plainly: "Cut on purpose … trade embargoes or route closures from quarantine (the treasury cost stands in for lost commerce)". |
| **Labour, food or trade costs** | None beyond the 2 treasury. |
| **Tests** | `test_states_quarantine_against_a_foreign_epidemic` (:483) and `test_quarantine_cuts_foreign_imports` (:511, closed < 0.6 × open). Both are legacy-path tests and must keep passing unchanged. |

### 2.1 Where a routing restriction would double-count [code + inferred]

1. **Same channel, two cuts.** If routing stops the trade journeys of a closed pair from turn t,
   those flows never enter the ledger. If the multiplier stayed, the next import step would cut
   another 70–90% of whatever trade stock remains: the decayed pre-closure stock plus any leaks.
   **Rule:** under any new mode, no multiplier on a restricted channel.
2. **Channels not restricted.** The multiplier also cuts people, soldiers and pilgrims. If C1
   restricts only trade, keeping the multiplier on the other channels keeps an abstract cut with
   no journey behind it. **Recommendation:** new modes drop the multiplier entirely. Unrestricted
   channels pass at full pressure, and coverage grows slice by slice (C1 trade, C1b people).
3. **Cost.** The flat 2 treasury "stands in for lost commerce", while the route system already
   pays +2 per route per side per turn (`simulation.py:331-345`). Closing routes forgoes that
   income for **both** sides. **Rule:** in new modes the flat charge becomes a declared
   *administration/enforcement* cost, or guard wages (C1.2). It is never a proxy for commerce.
4. **The technique bonus.** Under the new modes, law codes and lazarets have no multiplier to
   raise. They must not be stacked on routing. They are either dropped there, or given a real
   meaning later (C4 option: lazarets allow inspected passage with delay and fee). Record this as
   a deliberate disposition.
5. **Embargo overlap.** A pair that is both embargoed and quarantined loses its route once (set
   membership). The harm accounting must attribute forgone income to quarantine only when the
   route would exist without the closure.

### 2.2 Dated lag of a real closure [inferred from code order]
- A closure decided at Phase 1 of t blocks Phase 2 routes, the TRADE action and agent-tick
  merchant journeys of **t**. The ledger update at the end of t omits them.
- **Aggregate trade proxy and migrants:** the first reduced import step is t+1. This matches the
  legacy "for next turn".
- **Agent merchants:** deliveries made during the agent tick of t are read by `observe_phase2` at
  Phase 2 of **t+1** (`contact_ledger.py:283-295`; `get_pending_arrivals` reads deliveries "the
  next economy tick consumes"). So the first reduced import step is **t+2**.
- Stock from before the closure then decays as `DECAY^k` (`contact_ledger.py:61`).
- Unverified by run.

---

## 3. Contacts and journeys

### 3.1 What the contact ledger records [code]
- A sparse directed region×region matrix of **decayed stock** per channel. Rows are
  `(src, dst, trade, people, soldiers, pilgrims)` (`contact_ledger.py:146-157`).
- Civ-pair aggregates and commerce, `last_inflow` (four channel totals for the last turn) and
  `last_update_turn`.
- **No individual or dated contact records**: no who, no turn, no journey id. Pending inputs are
  transient and cleared at the end of each turn (`:396-398`).
- Retention per turn is `(0.9, 0.9, 0.8, 0.9)`. Edges are pruned when every channel is below 0.01.

| Channel | Generated by | Dated individual source available elsewhere? |
| --- | --- | --- |
| trade (agent modes) | native merchant deliveries, `get_pending_arrivals` (source, dest, good, qty) at Phase 2 (`:283-295`) | merchant trip stats per tick (`get_merchant_trip_stats`: replans, unwinds, stalled; `ffi/mod.rs:4184-4196`, history at `agent_bridge.py:1633`); opt-in `transaction_receipts` (reserved, departed, cancelled, replanned, returned, arrived by voyage; pinned module) |
| trade (aggregate) | route proxy per boundary pair of each goods route, `off_mode_trade_rows` (`:309-338`) | route set per turn (`resources.get_active_trade_routes`) |
| trade (both) | +1 on the capital edge per successful TRADE action (`record_trade_action` :235, from `action_engine.py:946`) | TRADE events |
| people | agent migration events of the turn (`:345-351`); hostages capital→capital (`:374-378`) | `agent_events_raw` (turn, agent id, region, target) |
| soldiers | campaign armies home→current, weight = soldiers (`:354-359`) | `war_state.armies` |
| pilgrims | great persons on pilgrimage, current→shrine, each turn on the road (`:362-372`); ritual gatherings' arrivals, capped at 8 (`record_gathering_arrivals` :248, default-off feature) | GP pilgrimage fields and deeds |

**Movement that never enters the ledger** [code, by grep for `_contact_pending` and
`record_*`]:
- public grain shipments, grain convoys and mutual-aid dispatch;
- timber expeditions (inside the civ);
- aggregate famine flight and overflow refugees (`refugee_routing`);
- Python-owned migration in aggregate mode;
- displacement on conquest.

### 3.2 Could quarantine block or delay real journeys, and at what cost?

| Journey | Gate available | Pinning | Cost that would emerge |
| --- | --- | --- | --- |
| Economy trade routes (all modes: Rust goods flows in agent modes, route proxy in aggregate) | post-filter at the end of `resources._compute_active_trade_routes` (`resources.py:155-261`; covers adjacency, two-hop, techniques extension and federation routes in one place) | `resources.py` unpinned | −2 treasury per closed route per side per turn (`simulation.py:331-345`); goods and food imports in the Rust economy (`trade_route_input`, `simulation.py:2090`); specialization (`:372`); TRADE partner search (`action_engine.py:261-265`); ledger dependence and warmth decline (diplomatic second-order effects). Must invalidate the route cache when closures change. |
| Agent merchants (hybrid, shadow, demographics-only) | drop cross-border edges of closed pairs from the merchant graph before `set_merchant_route_graph`. Today this is composed at `agent_bridge.py:1486-1494` and `:1523-1531`: `economy.build_merchant_route_graph` → maritime filter → `_city_route_graph`. Precedent: `maritime.merchant_route_graph` / `filter_boundary_batch` | `agent_bridge.py` and `economy.py` both **ENFORCED** (witness chains) | Rust already handles it (`merchant.rs:1438-1467`): a transit merchant whose next hop is gone does a BFS replan (`REPLANNED`) or unwinds its cargo to origin (`RETURNED`, stalled + unwind counters); loading reservations whose route vanished are cancelled (`:1221`). Lost or longer trips mean lost margins and stalled supply to importers. No native change needed. |
| Public grain shipments and convoys | they read the same graph composition through `grain_reserves._route_graph` (`grain_reserves.py:450-465`, ENFORCED) | — | If the filter sits inside `build_merchant_route_graph` or `_city_route_graph`, convoys reroute, wait, turn back or strand (`grain_convoys.py:31-40`). These journeys are **not ledger contact**, so blocking them is pure harm in the model. Recommendation: exempt them in C1 by filtering only at the two agent-tick sites (open question Q-C3). |
| Migration (hybrid) | **none in Python.** Rust targets come from `RegionState.adjacency` (`behavior.rs:273, 704`). Adjacency is also read by household follow (`household.rs:293`), relocation (`relocation.rs:220`), migration drivers (`migration_drivers.rs:333`) and **movement-news diffusion** (`knowledge.rs:636`). | a native optional input (C1b) or a pinned adjacency filter in `agent_bridge.build_region_batch` (`:451-454`) | Migrants held at origin (hunger and crowding there), lost labour reallocation. Filtering adjacency would also stop movement news crossing the border, a confounding side effect, so a dedicated native closure input is cleaner (section 6.5). |
| Pilgrims | `great_persons.check_pilgrimages` departures (`great_persons.py:495-560`), Phase 10, hybrid only (needs agent belief) | unpinned | Lost Prophet transformation. **Very small channel** in practice (pilot: pilgrim stock about 1.5 against people about 547 at turn 50, P7 hybrid), so it is deferred. |
| Armies | war system | — | Out of scope. Quarantine does not halt campaigns. Soldiers stay unrestricted. |
| Hostages, timber expeditions | — | — | Not restricted (diplomatic, inside the civ). |

### 3.3 Accounting [code]
- The treasury is the civ account. Route income is a model-created `keep` income.
- Under A1's audit, household wealth flows (guard or carer wages) need whatever A1 decides
  between existing wealth and a separate spendable balance (dependency, section 8).

### 3.4 Evidence from existing bundles [pilot]
Read-only parsers: `tools/ledger_channels.py`, `tools/epi_events.py`, `tools/arrivals_cross.py`.
The bundles came from other lanes' development runs: procedural seed 7, 200 turns, default
features (epidemics, ledger, techniques, cities on) plus those lanes' arms.

| Run | Cross-polity arrivals by carrier | Cross-controller weighted ledger contact, final turn | Quarantine events | Epidemic deaths |
| --- | --- | --- | --- | --- |
| `audit-a/pilot/runs/CH_pw-p7` (hybrid) | migrants 147, merchants 28, soldiers 2 (98 more migrant arrivals within one polity or from uncontrolled regions) | people 0.655, trade 0.345 | 83 | 698 |
| `audit-b/runs/p7off` (aggregate) | merchants 53, migrants 15, soldiers 2 | trade 0.759, people 0.21, soldiers 0.031 | 218 | 193 |

Reading: in hybrid about 16% of cross-polity arrivals are trade-borne, in aggregate about 76%.
This is one world per mode on a development seed and only indicates direction. Arrival "carrier"
is the argmax channel of the dominant edge, not a full split of the hazard.

---

## 4. Care and crowding

### 4.1 `health_care.py` [code, doc]
- **Scope.** Default-off (`:14`), hybrid-only (`health_care_active`, :25-26). Each episode is
  `InjuryEpisode(agent_id, onset_turn, remaining, origin_region)` (`health_care_state.py:10-14`).
- **Exposure.** Rural adult farmers who are not travelling, enlisted or urban, in regions with
  realized production. The draw is 0.01 per worker-turn on a native RNG offset (0x4843).
- **Labour cost.** Impairment of 0.5 worker-turn. Recovery work 2. Care by a co-resident spouse,
  or optionally reciprocal retained kin, of 0.2 worker-turn. Recovery progress is
  `1 + min(1, 5·care)` (`:154-156`).
- **Budgets.** Only manual farm work. Lost time is subtracted natively from regional farm labour,
  and income is scaled once (`prepare_health_work` / `finish_health_work`, `:103-126, 129-188`).
  There is **no treasury, supply or wage budget**.
- **What it does not touch** (`:1-7`; doc "Scope and ownership"): disease, battle resolution,
  mortality rates, fertility, military rosters and migration rules. Deaths only *censor* episodes.
- **Pins.** `health_care.py` and `health_care_state.py` are **digest-pinned**
  (`tests/test_health_care_policy.py:1023-1024`).

### 4.2 Care capacity, sanitation, healers, supplies today [code]
- **Healers.** Only abstract medicine *practice*: herbalism 0.05, physicians 0.10, lazarets 0.05,
  vaccination 0.30, each times a regional practice level, floor 0.5 on the CFR factor
  (`techniques.py:150-153, 1096-1103`). No workers, supplies or cost.
- **Sanitation.** None. `InfrastructureType` is roads, fortifications, irrigation, ports, mines,
  temples (`models.py:215-221`). "Aqueducts" is a technique that only discounts builds. Water
  enters disease only through M35b endemic flares (low water or a sharp water drop raises
  `endemic_severity`, `ecology.py:906-916`). Those flares raise the spillover hazard (cap ×3) and
  native agent mortality.
- **Supplies.** No medicinal good. Botanicals are a food good (`economy.py:51`).
- **Care workers for disease.** None.
- **Reusable seams:**
  - `recovery_crews.remove_farm_time` lowers the `farm_labor_factor` column so that named crews'
    farm time leaves native farm labour (`recovery_crews.py:575-596`; cities use the same column);
  - the livelihoods hook framework (`reserve_first`, `prepare_phase2`, `finish_phase2`,
    before/after agent tick, `phase10`; `livelihoods.py:624-700`);
  - L9 budget envelopes through `local_budgets.PROVIDERS` (doc "Provider interface").

### 4.3 Crowding and displacement [code]

| Source | Where | Reaches epidemics? |
| --- | --- | --- |
| pop / carrying capacity | `epidemiology._modifiers` :356-358 | yes: susceptibility +0.5·clamp(ratio−0.8) |
| urban share | `cities.epidemic_susceptibility_factors` :1179-1186 | yes: ×(1 + 0.5·urban share) |
| M35b overcrowding and army passage flares | `ecology.py:886-904` | indirectly (spillover hazard; native mortality) |
| aggregate refugees and overflow | `refugee_routing.apportion_refugees` (destinations only); toll and arrivals by callers | only through destination population (crowding term; newcomers susceptible). Not recorded as contact. |
| hybrid displacement | `AgentBridge.displacement_by_region`, computed from the snapshot's `displacement_turn > 0` (`agent_bridge.py:1340-1345, 1384-1391`) | **no.** Narration only, and a transient bridge attribute that is not checkpointed. Feeding it to epidemics would first need a dated copy persisted in Python state, or a resume would diverge. |

---

## 5. Information and decision-makers

### 5.1 What a civ knows today, and when [code]
- Outbreak *reports* are the `epidemic` events of this tick (`_reports` :840). Their threshold is
  `cases ≥ max(2, 3%·n)`.
- Quarantine reads them **in the same tick** for any foreign region linked by any ledger edge.
  There is no delivery delay, no noise and no link to the observer's own customs.
- The ledger matrix is world-global; a civ is treated as knowing third-party edges.
- Agents do not perceive epidemics as information: no knowledge packets. They feel only the
  `plague` condition and catastrophe deaths.

### 5.2 Decision points that could carry public-health choices with dated information

| Decision-maker | When | Notes |
| --- | --- | --- |
| Epidemic civ rule (`_decide_quarantine`) | Phase 1 of t, for journeys of t | All modes. The natural owner of C1 and C4 closure decisions. |
| L9 ruler at the seat city (`--local-budgets`) | Phase 10 of T, decides envelopes for T+1 from dated observations of T | Hybrid and `--grain-reserves` only. A provider registers `services`, `proposals`, `install`, `settle` and `obligations`. Relief must be in an existing constituency's unit (food for commons, crew work for patricians), or a new constituency must be appended. The natural owner of C2 carer and supply envelopes and C1.2 guard wages. |
| Civ AI actions (`ActionType`, `models.py:201-212`) | Phase 5 | Not recommended: adding an enum value changes action distributions on the default path (enum order, capped weights). |
| Governance (Phase 8 institutions and reforms) | Phase 8 | A possible later host ("a public-health office"). This is D1's territory: a reform must change a real service. |
| Cities (grievance and charters) | Phase 10 | Grievance already responds to L9 delivery. Kept and broken promises on care could reuse it. |

**Reusable pattern for dated reports** [code]: `harvest_forecasts._publish`
(`harvest_forecasts.py:354-420`):
- recipients are the source region plus its ledger partners with contact > 0;
- `delivery_turn = issued + (1 own / 2 partner) + report_delay`;
- reports expire and are persisted with ids;
- a `shuffle` policy gives a signal-destruction control.

The module is ENFORCED (information-candidate witness), so copy the pattern and do not edit it.

---

## 6. Design proposal, C1–C4

Principles: opt-in rules switches; legacy behaviour byte-identical when the switch is omitted;
Python first; reuse the epidemic death path, the existing journey systems and the existing budget
authorities.

### 6.1 C1: quarantine with real, dated restriction and costs

**Switch.** `--quarantine-mode {none,cost_only,closure}`.
- Omitted means **legacy**, today's multiplier rule.
- It requires epidemiology on and the contact ledger. An explicit mode with
  `--no-epidemiology` or `--no-contact-ledger` raises `ValueError`.
- It is valid in every agent mode (trade closure is Python-side).
- Saved on the world. A resume conflict is rejected the way `livelihoods_resume_conflicts`
  rejects one.
- Registered in `feature_catalog.REQUIREMENTS`, `batch_manifest` and the gate-runner forwarding.

**State.** A new optional sub-model, `EpidemicState.quarantine_rules: QuarantineRulesState | None`,
`exclude_if` None. It is read with `getattr(..., None)` so old pickles without the field load
(the retained-kin lesson). Fields:
- `mode`;
- `closures`: `QuarantineClosure(id, civ, targets: list[civ idx], opened_turn,
  last_renewed_turn, cause: event id, channels: ["trade"])`. Ids come from `next_closure_id`;
  they are stable, checkpointed and never reused, per the program identity contract. A lapse
  followed by a reclosure gets a new id;
- `receipt`, the last completed turn: `source_turn`, closed pairs, forgone route income per civ
  (counterfactual route set minus actual), merchant-graph edges removed, merchant
  disruption-stat deltas, enforcement paid;
- cumulative counters.

`state.quarantine` (civ indices) stays filled in every mode, so the viewer and analytics
(`quarantine_turns`) keep working.

**Decision.** In C1 it keeps the legacy trigger (stability ≥ 30, treasury ≥ cost, a reported
foreign outbreak in ledger contact), so the mechanism change is isolated from any change in the
decision. Targets are the polities that control the reported threat regions; uncontrolled
sources have no route to close. Scope "targeted" versus legacy "all foreign" is open question
Q-C2. Closures are renewed each turn while the trigger holds, and lapse otherwise.

**Effects by mode:**

| Mode | Decisions | Cost | Journeys restricted | Import multiplier |
| --- | --- | --- | --- | --- |
| legacy (omitted) | as today | 2 treasury | none | 0.7–0.9 |
| `none` | none | none | none | none |
| `cost_only` | as `closure` | declared enforcement cost (2 treasury, `keep`) | none | **none** |
| `closure` | as `cost_only` | enforcement cost; real lost route income and trade emerge | trade: economy routes, TRADE action, agent merchant graph (both directions of closed pairs' border edges) | **none** |

**Hooks:**
1. `epidemiology._introduce`: apply the multiplier only when `quarantine_rules is None`. Unpinned.
2. `epidemiology._decide_quarantine`: branch by mode; invalidate the route cache when closures
   change. Unpinned.
3. `resources._compute_active_trade_routes`: one guarded post-filter,
   `routes -= closed_pairs(world)`, at `:261`. Unpinned.
4. Merchant graph: one helper call at the two `agent_bridge` tick sites, next to
   `_city_route_graph`. **ENFORCED file**: needs the lead's reviewed inverse layer. This placement
   leaves grain shipments and convoys open (Q-C3).
5. A new module `src/chronicler/quarantine_rules.py` for the helpers, receipts, snapshot and
   metrics.

No new random draws: selection is deterministic in sorted order.

**C1.2 (labour cost, hybrid).** Border guards, `GUARDS_PER_CLOSED_EDGE` farmer-equivalents
(declared, not calibrated), named by lowest stable id among eligible adult farmers of the border
region. Their farm time comes out through the `farm_labor_factor` seam, and they are paid an
enforcement wage from the treasury that **replaces** the flat 2. This needs a Phase 2 hook: either
registration as a livelihoods-style package or a pinned `simulation.py` hook (lead decision).
Aggregate mode keeps the treasury cost only.

**Food cost** emerges from lost cross-border goods imports (`economy_result.imports_by_region`
food category) and, if Q-C3 decides to close them, from blocked relief grain.

### 6.2 C1b: migration closure (hybrid, native)
- An optional region-batch input listing, per region, the source civs closed to entry, applied in
  both directions for closed pairs. Absent input means identity.
- Checked in every migration path:
  - the target loops at `behavior.rs:273` and `:704`;
  - household follow (`household.rs:293`);
  - relocation (`relocation.rs:220`);
  - migration drivers (`migration_drivers.rs:333`).
- It returns a blocked-migrant count for the receipts.
- It is rebuilt from Python every turn, so there is no persisted native field: use the `transient`
  persistence clause that health care established (doc "State and phase contract"). No schema
  change.
- **Why native:** no Python gate exists. Filtering adjacency instead would also stop
  movement-news packets (`knowledge.rs:636`) and change the frontier logic
  (`behavior.rs:756`, `has_internal_neighbour`).
- **Why soon:** the pilot shows migrants carry most cross-polity arrivals in hybrid.

### 6.3 C2: bounded care and sanitation capacity
- **Switch:** `--epidemic-care {care,cost_only}`. Hybrid only (named carers and wages), rejected
  in other modes. Optionally L9-funded.
- **Carers.** Named adult farmers by stable id. Their farm time is removed through
  `farm_labor_factor` during Phase 2 of T, and they are paid wages through the existing transfer
  path. They are funded by an L9 envelope (provider `epidemic_care`), or under a declared cap on
  the treasury when L9 is off (lead decision, Q-C5).
- **Exclusion.** People in health care's prepared caregiver or patient rows for that turn are
  excluded, so nobody is booked twice.
- **Supplies (optional C2b).** Patient rations drawn from market grain: a real food cost, with
  receipts.
- **Capacity applies to the next epidemic tick** (Phase 1 of T+1), stored as dated state:
  `care_capacity[region] = (source_turn T, patients served)`. This keeps resume exact.
- **Effect.** Coverage `c = min(1, capacity / infectious people)`, where infectious people are
  `burden·n` summed over pathogens from the last tick. Then
  `CFR × (1 − CARE_CFR_REDUCTION·c)`, applied in the `mods` list exactly as the techniques factor
  is (`epidemiology.py:533-538`), with one combined floor (no stacking below the techniques
  floor). Deaths still go through `_apply_deaths` only: **no new mortality path**.
- **Sanitation (C2c, with Program B).** A transmission factor for water-borne pathogens (`flux`;
  possibly `fever` for drainage) from an infrastructure service level that **B3 owns** (condition,
  workers, materials, budgets). C2 does not invent infrastructure. It must not touch M35b endemic
  severity, which is a separate existing native mortality path.
- **Crowding and displacement.** Optionally a susceptibility term from a *persisted dated copy* of
  the hybrid displaced share, and from aggregate refugee arrivals this turn. The displacement
  contract is shared with D3 and A6 and owned by the lead.

### 6.4 C3: keep regional and individual separate (invariants)
- Epidemic rows are regional S/E/I/R shares. No `InjuryEpisode` is ever created or closed by
  epidemic code, and health care never reads or writes epidemic rows or CFR.
- Care changes **parameters** (CFR, transmission), never deaths directly.
- The epidemic owns disease deaths. Rust only executes staged counts.
- Carers are not injury caregivers in the same turn.
- Native endemic mortality is unchanged.
- Tests assert each of these.

### 6.5 C4: evidence-informed choices with dated information

**Outbreak reports** (a copied pattern, new module):
- issued at each reported onset, and refreshed while the outbreak is reported;
- delivered to civs whose regions share a ledger edge with the source region (the civ's own
  customs knowledge), after `1 own / 2 foreign + report_delay` turns;
- expire when the source episode ends plus k turns;
- each report carries the reported prevalence and cases, and the pathogen's CFR as this civ has
  observed it in its own past outbreaks.

**Decision.** Close against polity P only on delivered reports. The rule compares the expected
averted import hazard on *restrictable* channels (computed from the civ's own edges) with the
expected costs: forgone routes (2 per route), guard wages, and last turn's food imports from P.
A declared exchange-rate parameter makes the policy explicit, with a sensitivity arm. Lazarets
could reduce leakage through inspected passage with a delay and a fee.

**Arms:**
- `none`: no intervention;
- `cost_only`: same decisions and costs, no restriction;
- `closure`: contact reduction;
- legacy reference (QL) for continuity;
- `closure` with shuffled reports: the signal-destruction control.

**Primary outcomes (2–3):**
1. Cross-polity epidemic arrivals into the closing civs' regions, during closure and for the
   following k turns.
2. Epidemic deaths per 1,000 person-turns, for closing civs and for the world.
3. (C2) Realized deaths among infections (CFR) in covered regions.

**Fixed harm panel:**
- Trade: forgone route income, both sides; goods and food imports into closing civs; merchant
  replans, unwinds, stalled and cancelled trips, and returned cargo.
- Mobility: migrants blocked (C1b); convoy reroutes and strandings, if closed.
- Food and labour: hunger region-turns (dearth and famine components); households priced out,
  if retail is on; guard and carer farm time removed.
- Fiscal and political: treasury, stability, rebellion and unrest.
- Partner civs' harms, an explicit externality.
- Population and survival.

### 6.6 Placement, randomness, pins

| Piece | Placement | Files and pin status (preflight, `preflight.txt` / `preflight2.txt`) |
| --- | --- | --- |
| C1 core | Python | `epidemiology.py` (ref), new `quarantine_rules.py`, `resources.py` (ref), `feature_catalog.py` (ref), `analytics.py` and `bundle.py` (ref) |
| C1 merchant graph | Python, pinned file | `agent_bridge.py` **ENFORCED** (`livelihoods_rv1` matches current), or `economy.py` **ENFORCED** (`livelihoods_pl4` matches current) |
| CLI, manifest, header, live | Python, pinned | `main.py` ENFORCED (r3), `batch_manifest.py` ENFORCED (pl4), `tests/test_batch_manifest.py` ENFORCED, `run_checkpoint.py` ENFORCED (s2r, only if a header field is added), `live.py` ENFORCED (rs6) |
| C1.2 guards, C2 carers | Python | `livelihoods.py` and `livelihoods_state.py` (ref), or a `simulation.py` hook (**ENFORCED**, rv2); reuse `recovery_crews.remove_farm_time` (ref) |
| C1b migration | Rust plus one bridge column | `chronicler-agents` behavior, household, relocation, migration_drivers; `agent_bridge.py` ENFORCED |
| Avoid editing | — | `health_care*.py` (DIGEST), `harvest_forecasts.py` and `transaction_receipts.py` (ENFORCED; copy patterns, read outputs), `grain_reserves.py` (ENFORCED), `models.py` (ENFORCED; keep state inside `EpidemicState`), `simulation.py` (ENFORCED) |
| Test files | — | `tests/test_epidemiology.py` is in native shard 0 (moving it needs a manifest update). New native tests need `scripts/testing/native_shards_manifest.json`. New offline tests need a new oracle chunk in `scripts/run_python_oracle_checks.py`. |

**Randomness.** C1, C1b and C2 need no draws: selection is deterministic in sorted stable-id
order. If a draw is ever needed, the reserved namespaces are `quarantine_guard`,
`epidemic_care` and `outbreak_report_noise`, keyed by (seed, turn, civ/region), never shared.
Closure legitimately changes native merchant and migration behaviour. It does not consume any
Python stream.

---

## 7. Smallest first slice (C1) and test plan

**Contents.** `--quarantine-mode` with legacy / `none` / `cost_only` / `closure`:
- trade closure through routes and the merchant graph;
- no multiplier in any new mode;
- enforcement cost replaces the "lost commerce" proxy;
- closures with ids and receipts;
- a viewer panel row that keeps unknown, absent and zero distinct, and labels "legacy multiplier"
  separately from "closure";
- docs.

Out of C1: guards (C1.2), migration (C1b), pilgrims (minor), convoys (Q-C3).

**Tests:**
1. **Feature-off identity.** Omitted mode against `8abc1acb` and the preceding integrated main,
   using `turn_speed_identity` (template and procedural, aggregate and hybrid), once with the
   default epidemics on and once with `--no-epidemiology`. State JSON omits `quarantine_rules`.
   Old saves and old `.ckpt` files load. The legacy tests at `:483` and `:511` pass unchanged.
2. **Mode units** (offline guard, new chunk):
   - `none`: no closures, no cost, import pressure = open pressure;
   - `cost_only`: the same closures and cost as `closure`, routes unchanged, no multiplier;
   - `closure`:
     - only closed pairs lose routes, including two-hop, techniques-extended and federation
       routes;
     - routes inside the civ and other pairs are unchanged;
     - the TRADE action cannot choose a closed partner;
     - forgone income equals 2 per closed route per side;
     - reopening restores the routes;
     - the route cache is invalidated.
3. **Double-count guards.** With closure active and the ledger unchanged, `_introduce` pressure
   equals the no-quarantine pressure. After journeys stop, a closed pair's trade stock follows
   `0.9^k`. The techniques bonus is not applied in new modes. Embargo plus closure removes a route
   once, and income is attributed once.
4. **Dated effect.** Aggregate: closure decided at t, the proxy flow is missing from the ledger at
   the end of t, and the hazard at t+1 is lower. Hybrid (native): merchant deliveries drop from
   the tick of t, the ledger at t+1, imports at t+2. In-transit merchants across a closed edge are
   `replanned` or `returned` (transaction receipts on).
5. **Checkpoint and resume during an outbreak with an active closure:**
   - aggregate `state.json` resume mid-closure;
   - hybrid exact `.ckpt` resume with merchants in transit across the closed border;
   - both compared to a continuous run: world JSON, native checkpoint state, global RNG,
     receipts, closure ids;
   - plus a lapse and reclosure across the boundary (a new id);
   - a resume with a conflicting mode is rejected;
   - a legacy-JSON resume follows a defined, tested behaviour.
6. **Catalog and invalid combinations.** Mode without epidemiology or ledger; all-enabled
   compatible checkpoint case.
7. **Screen**, after the timing pilot on development seeds:
   - arms QL, Q0, QC, QR;
   - aggregate and hybrid, template and procedural;
   - preregistered held cohort reserved by the lead;
   - the primary outcomes and harm panel of section 6.5.

   Predicted [inferred]: QR differs from QC noticeably in aggregate worlds and little in hybrid
   until C1b. Report that as a result, not a failure.

---

## 8. Dependencies on other programs

- **A1 (accounting).** What counts as treasury and household money: forgone route income is
  forgone model income, not a transfer; guard and carer wages are transfers (spendable balance or
  wealth). C1.2 and C2 wait on A1's decision.
- **A4 (merchants, owned cargo, journeys).**
  - Closure unwinds become A4 "returns". Any fee or loss settlement belongs to A4.
  - If A4 reconciles economy-route trade with merchant trips (proxy against real), the closure
    must filter the reconciled authority only.
  - A4's journey records are the natural dated contact evidence.
- **A6, D3 (displacement and migration).** C1b shares the migration paths with A6's adaptive
  migration. Displacement, evacuation and family separation (D3) and the displaced share as a
  crowding input (C2) need one lead-owned displacement contract. Wounded-soldier care (D3), injury
  care (health care) and epidemic carers (C2) must draw from one labour reservation without
  booking anyone twice.
- **B2 and B3 (water and infrastructure).** Sanitation service levels come from B3. B2 water
  changes move M35b endemic flares (spillover and native mortality): B must attribute that, and C
  must not double it.
- **D1 (institutions).** A reform that creates a public-health office must change a real service
  (closure rule, care envelope), not a label.
- **E (evidence).** Seed reservation, extractor validation for arrivals by channel and closure
  receipts, viewer distinctions, checkpoint coverage "at outbreaks".
- **Lead (integration owner).** Pinned hooks in `agent_bridge.py`, `main.py`, `batch_manifest.py`
  and possibly `simulation.py`; the turn-order table rows below; the native hook for C1b.

**Turn-order rows to add** [proposed]:

| Step | Owner |
| --- | --- |
| Phase 1 epidemic tick → C1/C4 decisions (closures for this turn's journeys) | C |
| Phase 2 route post-filter and receipts | C |
| Agent tick: merchant graph filter (and C1b migration input) | lead hook |
| Phase 2: C1.2 guards / C2 carers (farm time) | C via livelihoods hooks |
| Phase 10: L9 envelopes for T+1 | A/L9 |
| End of turn: ledger update, unchanged | — |

---

## 9. Open questions

- **Q-C1. Import basis.**
  - Today the decayed stock carries pre-closure contact for about 10 turns.
  - Keep it (honest lag, weaker quarantine), or add a separately versioned epidemic import rule
    that uses recent inflow?
  - Recommendation: keep it for C1 and report the lag. Any basis change is its own
    rules-versioned decision.
- **Q-C2. Closure scope.** Targeted (polities with reported outbreaks; cheaper; dated-information
  consistent) or all foreign polities (like-for-like with legacy)? Recommendation: targeted, with
  "all" as a later option.
- **Q-C3. Relief grain.** Should closure block public grain shipments and convoys? They are not
  ledger contact, so blocking them is harm with no modeled benefit. Recommendation: exempt in C1
  (filter only at the agent-tick sites) and record it as an intentional boundary.
- **Q-C4. Hostages and armies.** Leave them unrestricted (assumed)?
- **Q-C5. Funding authority for C2.** Extend L9 with a new constituency ("the sick", in expected
  deaths averted), or use a capped direct treasury charge? L9 forces hybrid plus grain reserves.
- **Q-C6. Where the C1b gate lives.** A native closure input (recommended), or an adjacency filter
  in the pinned bridge that also stops news crossing the border?
- **Q-C7. Defaults.** Should the legacy multiplier stay the default reference indefinitely? Under
  the owner's rules, yes, until a promotion decision.
- **Q-C8. Stale doc.** Fix the stale *Default: Off* section of `epidemiology.md` (doc defect) in
  the C1 PR.

## 10. Not verified here

- No run was made by this lane. The dated-lag claims (2.2) and the predicted effect sizes (7) are
  inferred.
- The pilot channel shares come from one world per mode, produced by other lanes with their own
  arms.
- I did not inspect whether native unwinds during conquest and closure interact. Both use
  `ledger.unwind` (`merchant.rs:1313, 1367, 1460`).
- I did not measure the cost of computing the route set twice for the forgone-income receipt.
