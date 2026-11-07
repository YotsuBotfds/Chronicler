# CW4b: S3 quarantine closure of migration (C1b)

Cohort pilot. Runs: 6; failed: 0 (missing outcomes: 0); simulation and extraction seconds 71 (0.020 core-hours)
Projected held run time from this pilot: 0.118 core-hours (x1.5 = 0.177) for 36 runs

Identity digests: 50b37187ffa87e268b470c5d2eb94d8267e0d7741690995266fa1cf74317eeba (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [], "packages": {}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| QR | t | 5: activated | 1 of 1 |
| QR | p | 19: activated | 1 of 1 |
| QRM | t | 5: activated | 1 of 1 |
| QRM | p | 19: activated | 1 of 1 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw4b_world_arrivals: Cross-polity epidemic arrivals over the whole run, world (QRM - QC) | t | 5: +17 | +17 [+17, +17] | 1 / 0 / 0 | 2/2 as extreme; means [-17, +17] |
| cw4b_world_arrivals: Cross-polity epidemic arrivals over the whole run, world (QRM - QC) | p | 19: -54 | -54 [-54, -54] | 0 / 1 / 0 | 2/2 as extreme; means [-54, +54] |
| cw4b_world_death_rate: World epidemic deaths (all) per 1,000 person-turns over the whole run (QRM - QC) | t | 5: +2.374 | +2.374 [+2.374, +2.374] | 1 / 0 / 0 | 2/2 as extreme; means [-2.374, +2.374] |
| cw4b_world_death_rate: World epidemic deaths (all) per 1,000 person-turns over the whole run (QRM - QC) | p | 19: +0.433 | +0.433 [+0.433, +0.433] | 1 / 0 / 0 | 2/2 as extreme; means [-0.433, +0.433] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw4b_mig_world_arrivals: Cross-polity arrivals, world (QRM - QR: the migration channel's increment) | t | 5: +18 | +18 [+18, +18] | 1 / 0 / 0 | 2/2 as extreme; means [-18, +18] |
| cw4b_mig_world_arrivals: Cross-polity arrivals, world (QRM - QR: the migration channel's increment) | p | 19: -176 | -176 [-176, -176] | 0 / 1 / 0 | 2/2 as extreme; means [-176, +176] |
| cw4b_mig_world_death_rate: World epidemic deaths per 1,000 person-turns (QRM - QR: the migration channel's increment) | t | 5: +1.807 | +1.807 [+1.807, +1.807] | 1 / 0 / 0 | 2/2 as extreme; means [-1.807, +1.807] |
| cw4b_mig_world_death_rate: World epidemic deaths per 1,000 person-turns (QRM - QR: the migration channel's increment) | p | 19: -4.871 | -4.871 [-4.871, -4.871] | 0 / 1 / 0 | 2/2 as extreme; means [-4.871, +4.871] |
| cw4b_trade_world_arrivals: Cross-polity arrivals, world (QR - QC: trade closure alone) | t | 5: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] |
| cw4b_trade_world_arrivals: Cross-polity arrivals, world (QR - QC: trade closure alone) | p | 19: +122 | +122 [+122, +122] | 1 / 0 / 0 | 2/2 as extreme; means [-122, +122] |
| cw4b_trade_world_death_rate: World epidemic deaths per 1,000 person-turns (QR - QC: trade closure alone) | t | 5: +0.5672 | +0.5672 [+0.5672, +0.5672] | 1 / 0 / 0 | 2/2 as extreme; means [-0.5672, +0.5672] |
| cw4b_trade_world_death_rate: World epidemic deaths per 1,000 person-turns (QR - QC: trade closure alone) | p | 19: +5.304 | +5.304 [+5.304, +5.304] | 1 / 0 / 0 | 2/2 as extreme; means [-5.304, +5.304] |
| cw4b_world_arrival_rate: Cross-polity arrivals per 1,000 region-turns, world (QRM - QC) | t | 5: +10.62 | +10.62 [+10.62, +10.62] | 1 / 0 / 0 | 2/2 as extreme; means [-10.62, +10.62] |
| cw4b_world_arrival_rate: Cross-polity arrivals per 1,000 region-turns, world (QRM - QC) | p | 19: -8.438 | -8.438 [-8.438, -8.438] | 0 / 1 / 0 | 2/2 as extreme; means [-8.438, +8.438] |
| cw4b_world_deaths: World epidemic deaths, count (QRM - QC) | t | 5: +101 | +101 [+101, +101] | 1 / 0 / 0 | 2/2 as extreme; means [-101, +101] |
| cw4b_world_deaths: World epidemic deaths, count (QRM - QC) | p | 19: +134 | +134 [+134, +134] | 1 / 0 / 0 | 2/2 as extreme; means [-134, +134] |
| cw4b_sel_arrivals: Arrivals into closing civs' regions in their windows (QRM - QC; conditioned on each arm's own closures: selection) | t | 5: +12 | +12 [+12, +12] | 1 / 0 / 0 | 2/2 as extreme; means [-12, +12] |
| cw4b_sel_arrivals: Arrivals into closing civs' regions in their windows (QRM - QC; conditioned on each arm's own closures: selection) | p | 19: -2 | -2 [-2, -2] | 0 / 1 / 0 | 2/2 as extreme; means [-2, +2] |
| cw4b_sel_deaths: Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing civs in their windows (QRM - QC; conditioned on each arm's own closures: selection) | t | 5: -1.817 | -1.817 [-1.817, -1.817] | 0 / 1 / 0 | 2/2 as extreme; means [-1.817, +1.817] |
| cw4b_sel_deaths: Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing civs in their windows (QRM - QC; conditioned on each arm's own closures: selection) | p | 19: -0.8756 | -0.8756 [-0.8756, -0.8756] | 0 / 1 / 0 | 2/2 as extreme; means [-0.8756, +0.8756] |
| cw4b_sel_window: Window civ-turns (QRM - QC; conditioned on each arm's own closures: selection) | t | 5: +199 | +199 [+199, +199] | 1 / 0 / 0 | 2/2 as extreme; means [-199, +199] |
| cw4b_sel_window: Window civ-turns (QRM - QC; conditioned on each arm's own closures: selection) | p | 19: +192 | +192 [+192, +192] | 1 / 0 / 0 | 2/2 as extreme; means [-192, +192] |
| cw4b_refusals: Migrants refused, person-ticks (QRM alone) | t | 5: +1279 | +1279 [+1279, +1279] | 1 / 0 / 0 | n/a (no control) |
| cw4b_refusals: Migrants refused, person-ticks (QRM alone) | p | 19: +4237 | +4237 [+4237, +4237] | 1 / 0 / 0 | n/a (no control) |
| cw4b_refusal_spells: Refusal spells: consecutive refusals of one agent count once (QRM alone) | t | 5: +1075 | +1075 [+1075, +1075] | 1 / 0 / 0 | n/a (no control) |
| cw4b_refusal_spells: Refusal spells: consecutive refusals of one agent count once (QRM alone) | p | 19: +3554 | +3554 [+3554, +3554] | 1 / 0 / 0 | n/a (no control) |
| cw4b_refused_flight: Refusals of migrants fleeing war, famine or persecution, hunger-driven moves excluded (QRM alone) | t | 5: +1032 | +1032 [+1032, +1032] | 1 / 0 / 0 | n/a (no control) |
| cw4b_refused_flight: Refusals of migrants fleeing war, famine or persecution, hunger-driven moves excluded (QRM alone) | p | 19: +3277 | +3277 [+3277, +3277] | 1 / 0 / 0 | n/a (no control) |
| cw4b_refused_hunger: Refusals of hunger-driven migrants: food opportunity, material need (QRM alone) | t | 5: +205 | +205 [+205, +205] | 1 / 0 / 0 | n/a (no control) |
| cw4b_refused_hunger: Refusals of hunger-driven migrants: food opportunity, material need (QRM alone) | p | 19: +521 | +521 [+521, +521] | 1 / 0 / 0 | n/a (no control) |
| cw4b_h_food_shortfall: Food shortfall after relief over the run (QRM - QC) | t | 5: +845.5 | +845.5 [+845.5, +845.5] | 1 / 0 / 0 | 2/2 as extreme; means [-845.5, +845.5] |
| cw4b_h_food_shortfall: Food shortfall after relief over the run (QRM - QC) | p | 19: +1319 | +1319 [+1319, +1319] | 1 / 0 / 0 | 2/2 as extreme; means [-1319, +1319] |
| cw4b_h_out_migration: Agents moving between regions over the run (QRM - QC) | t | 5: -46 | -46 [-46, -46] | 0 / 1 / 0 | 2/2 as extreme; means [-46, +46] |
| cw4b_h_out_migration: Agents moving between regions over the run (QRM - QC) | p | 19: -990 | -990 [-990, -990] | 0 / 1 / 0 | 2/2 as extreme; means [-990, +990] |
| cw4b_h_population: Population at the end (QRM - QC) | t | 5: +23 | +23 [+23, +23] | 1 / 0 / 0 | 2/2 as extreme; means [-23, +23] |
| cw4b_h_population: Population at the end (QRM - QC) | p | 19: -97 | -97 [-97, -97] | 0 / 1 / 0 | 2/2 as extreme; means [-97, +97] |
| cw4b_h_treasury: Treasury at the end (QRM - QC) | t | 5: -259 | -259 [-259, -259] | 0 / 1 / 0 | 2/2 as extreme; means [-259, +259] |
| cw4b_h_treasury: Treasury at the end (QRM - QC) | p | 19: -1284 | -1284 [-1284, -1284] | 0 / 1 / 0 | 2/2 as extreme; means [-1284, +1284] |
| cw4b_h_partner_population: Partner civs' population at the end (QRM - QC) | t | 5: +22 | +22 [+22, +22] | 1 / 0 / 0 | 2/2 as extreme; means [-22, +22] |
| cw4b_h_partner_population: Partner civs' population at the end (QRM - QC) | p | 19: -97 | -97 [-97, -97] | 0 / 1 / 0 | 2/2 as extreme; means [-97, +97] |
| cw4b_h_partner_treasury: Partner civs' treasury at the end (QRM - QC) | t | 5: -521 | -521 [-521, -521] | 0 / 1 / 0 | 2/2 as extreme; means [-521, +521] |
| cw4b_h_partner_treasury: Partner civs' treasury at the end (QRM - QC) | p | 19: -1284 | -1284 [-1284, -1284] | 0 / 1 / 0 | 2/2 as extreme; means [-1284, +1284] |
| cw4b_h_forgone: Route income forgone, both sides (QRM alone; structurally 0 in QC) | t | 5: +500 | +500 [+500, +500] | 1 / 0 / 0 | n/a (no control) |
| cw4b_h_forgone: Route income forgone, both sides (QRM alone; structurally 0 in QC) | p | 19: +4796 | +4796 [+4796, +4796] | 1 / 0 / 0 | n/a (no control) |
| cw4b_h_forgone_trade: Route income forgone, both sides (QR alone) | t | 5: +312 | +312 [+312, +312] | 1 / 0 / 0 | n/a (no control) |
| cw4b_h_forgone_trade: Route income forgone, both sides (QR alone) | p | 19: +2392 | +2392 [+2392, +2392] | 1 / 0 / 0 | n/a (no control) |
| cw4b_h_unwinds: Merchant unwinds, world (QRM - QC) | t | 5: +3 | +3 [+3, +3] | 1 / 0 / 0 | 2/2 as extreme; means [-3, +3] |
| cw4b_h_unwinds: Merchant unwinds, world (QRM - QC) | p | 19: +407 | +407 [+407, +407] | 1 / 0 / 0 | 2/2 as extreme; means [-407, +407] |
| cw4b_h_leaked: Deliveries still crossing a closed pair (QRM alone) | t | 5: +21 | +21 [+21, +21] | 1 / 0 / 0 | n/a (no control) |
| cw4b_h_leaked: Deliveries still crossing a closed pair (QRM alone) | p | 19: +140 | +140 [+140, +140] | 1 / 0 / 0 | n/a (no control) |
| cw4b_h_enforcement: Enforcement paid (QRM - QC) | t | 5: +252 | +252 [+252, +252] | 1 / 0 / 0 | 2/2 as extreme; means [-252, +252] |
| cw4b_h_enforcement: Enforcement paid (QRM - QC) | p | 19: +694 | +694 [+694, +694] | 1 / 0 / 0 | 2/2 as extreme; means [-694, +694] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QR - QC | Population at the end (sum over civilizations) | t | 5: -9 | -9 [-9, -9] | 0 / 1 / 0 | 2/2 as extreme; means [-9, +9] | recorded |
| QR - QC | Population at the end (sum over civilizations) | p | 19: -160 | -160 [-160, -160] | 0 / 1 / 0 | 2/2 as extreme; means [-160, +160] | recorded |
| QR - QC | Treasury at the end (sum over civilizations) | t | 5: -82 | -82 [-82, -82] | 0 / 1 / 0 | 2/2 as extreme; means [-82, +82] | recorded |
| QR - QC | Treasury at the end (sum over civilizations) | p | 19: -1589 | -1589 [-1589, -1589] | 0 / 1 / 0 | 2/2 as extreme; means [-1589, +1589] | recorded |
| QR - QC | Food shortfall after relief over the run (food) | t | 5: -275.8 | -275.8 [-275.8, -275.8] | 0 / 1 / 0 | 2/2 as extreme; means [-275.8, +275.8] | recorded |
| QR - QC | Food shortfall after relief over the run (food) | p | 19: -3736 | -3736 [-3736, -3736] | 0 / 1 / 0 | 2/2 as extreme; means [-3736, +3736] | recorded |
| QR - QC | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QC | Deaths by epidemic (the epidemic authority) | t | 5: +14 | +14 [+14, +14] | 1 / 0 / 0 | 2/2 as extreme; means [-14, +14] | recorded |
| QR - QC | Deaths by epidemic (the epidemic authority) | p | 19: +534 | +534 [+534, +534] | 1 / 0 / 0 | 2/2 as extreme; means [-534, +534] | recorded |
| QR - QC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QC | Agents migrating between regions over the run | t | 5: +122 | +122 [+122, +122] | 1 / 0 / 0 | 2/2 as extreme; means [-122, +122] | recorded |
| QR - QC | Agents migrating between regions over the run | p | 19: -1353 | -1353 [-1353, -1353] | 0 / 1 / 0 | 2/2 as extreme; means [-1353, +1353] | recorded |
| QR - QC | Mean wealth Gini of living civilizations at the end | t | 5: +0.02703 | +0.02703 [+0.02703, +0.02703] | 1 / 0 / 0 | 2/2 as extreme; means [-0.02703, +0.02703] | recorded |
| QR - QC | Mean wealth Gini of living civilizations at the end | p | 19: -0.02736 | -0.02736 [-0.02736, -0.02736] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02736, +0.02736] | recorded |
| QR - QC | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QR - QC | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QRM - QR | Population at the end (sum over civilizations) | t | 5: +32 | +32 [+32, +32] | 1 / 0 / 0 | 2/2 as extreme; means [-32, +32] | recorded |
| QRM - QR | Population at the end (sum over civilizations) | p | 19: +63 | +63 [+63, +63] | 1 / 0 / 0 | 2/2 as extreme; means [-63, +63] | recorded |
| QRM - QR | Treasury at the end (sum over civilizations) | t | 5: -177 | -177 [-177, -177] | 0 / 1 / 0 | 2/2 as extreme; means [-177, +177] | recorded |
| QRM - QR | Treasury at the end (sum over civilizations) | p | 19: +305 | +305 [+305, +305] | 1 / 0 / 0 | 2/2 as extreme; means [-305, +305] | recorded |
| QRM - QR | Food shortfall after relief over the run (food) | t | 5: +1121 | +1121 [+1121, +1121] | 1 / 0 / 0 | 2/2 as extreme; means [-1121, +1121] | recorded |
| QRM - QR | Food shortfall after relief over the run (food) | p | 19: +5055 | +5055 [+5055, +5055] | 1 / 0 / 0 | 2/2 as extreme; means [-5055, +5055] | recorded |
| QRM - QR | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QR | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QR | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QR | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QR | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QRM - QR | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QRM - QR | Deaths by epidemic (the epidemic authority) | t | 5: +87 | +87 [+87, +87] | 1 / 0 / 0 | 2/2 as extreme; means [-87, +87] | recorded |
| QRM - QR | Deaths by epidemic (the epidemic authority) | p | 19: -400 | -400 [-400, -400] | 0 / 1 / 0 | 2/2 as extreme; means [-400, +400] | recorded |
| QRM - QR | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QRM - QR | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QRM - QR | Agents migrating between regions over the run | t | 5: -168 | -168 [-168, -168] | 0 / 1 / 0 | 2/2 as extreme; means [-168, +168] | recorded |
| QRM - QR | Agents migrating between regions over the run | p | 19: +363 | +363 [+363, +363] | 1 / 0 / 0 | 2/2 as extreme; means [-363, +363] | recorded |
| QRM - QR | Mean wealth Gini of living civilizations at the end | t | 5: -0.1845 | -0.1845 [-0.1845, -0.1845] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1845, +0.1845] | recorded |
| QRM - QR | Mean wealth Gini of living civilizations at the end | p | 19: +0.01733 | +0.01733 [+0.01733, +0.01733] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01733, +0.01733] | recorded |
| QRM - QR | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QRM - QR | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QRM - QC | Population at the end (sum over civilizations) | t | 5: +23 | +23 [+23, +23] | 1 / 0 / 0 | 2/2 as extreme; means [-23, +23] | recorded |
| QRM - QC | Population at the end (sum over civilizations) | p | 19: -97 | -97 [-97, -97] | 0 / 1 / 0 | 2/2 as extreme; means [-97, +97] | recorded |
| QRM - QC | Treasury at the end (sum over civilizations) | t | 5: -259 | -259 [-259, -259] | 0 / 1 / 0 | 2/2 as extreme; means [-259, +259] | recorded |
| QRM - QC | Treasury at the end (sum over civilizations) | p | 19: -1284 | -1284 [-1284, -1284] | 0 / 1 / 0 | 2/2 as extreme; means [-1284, +1284] | recorded |
| QRM - QC | Food shortfall after relief over the run (food) | t | 5: +845.5 | +845.5 [+845.5, +845.5] | 1 / 0 / 0 | 2/2 as extreme; means [-845.5, +845.5] | recorded |
| QRM - QC | Food shortfall after relief over the run (food) | p | 19: +1319 | +1319 [+1319, +1319] | 1 / 0 / 0 | 2/2 as extreme; means [-1319, +1319] | recorded |
| QRM - QC | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QC | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QC | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QC | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QRM - QC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QRM - QC | Deaths by epidemic (the epidemic authority) | t | 5: +101 | +101 [+101, +101] | 1 / 0 / 0 | 2/2 as extreme; means [-101, +101] | recorded |
| QRM - QC | Deaths by epidemic (the epidemic authority) | p | 19: +134 | +134 [+134, +134] | 1 / 0 / 0 | 2/2 as extreme; means [-134, +134] | recorded |
| QRM - QC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QRM - QC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QRM - QC | Agents migrating between regions over the run | t | 5: -46 | -46 [-46, -46] | 0 / 1 / 0 | 2/2 as extreme; means [-46, +46] | recorded |
| QRM - QC | Agents migrating between regions over the run | p | 19: -990 | -990 [-990, -990] | 0 / 1 / 0 | 2/2 as extreme; means [-990, +990] | recorded |
| QRM - QC | Mean wealth Gini of living civilizations at the end | t | 5: -0.1574 | -0.1574 [-0.1574, -0.1574] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1574, +0.1574] | recorded |
| QRM - QC | Mean wealth Gini of living civilizations at the end | p | 19: -0.01003 | -0.01003 [-0.01003, -0.01003] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01003, +0.01003] | recorded |
| QRM - QC | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QRM - QC | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| QC | 6.3 [6.3, 6.3] | 18.2 [18.2, 18.2] |
| QR | 5.9 [5.9, 5.9] | 18.1 [18.1, 18.1] |
| QRM | 6.1 [6.1, 6.1] | 16.2 [16.2, 16.2] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
