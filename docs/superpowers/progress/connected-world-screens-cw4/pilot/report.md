# CW4: S3 quarantine and public health (C1)

Cohort pilot. Runs: 8; failed: 0 (missing outcomes: 0); simulation and extraction seconds 105 (0.029 core-hours)
Projected held run time from this pilot: 0.176 core-hours (x1.5 = 0.264) for 48 runs

Identity digests: 1640a09d6313e01ed9bd8411c6654d179282a0a3167efe9e326f579e71a83cac (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [], "packages": {}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| Q0 | t | 5: activated | 1 of 1 |
| Q0 | p | 19: activated | 1 of 1 |
| QC | t | 5: activated | 1 of 1 |
| QC | p | 19: activated | 1 of 1 |
| QR | t | 5: activated | 1 of 1 |
| QR | p | 19: activated | 1 of 1 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw4_world_arrivals: Cross-polity epidemic arrivals over the whole run, world (QR - QC) | t | 5: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] |
| cw4_world_arrivals: Cross-polity epidemic arrivals over the whole run, world (QR - QC) | p | 19: +122 | +122 [+122, +122] | 1 / 0 / 0 | 2/2 as extreme; means [-122, +122] |
| cw4_world_death_rate: World epidemic deaths (all) per 1,000 person-turns over the whole run (QR - QC) | t | 5: +0.5672 | +0.5672 [+0.5672, +0.5672] | 1 / 0 / 0 | 2/2 as extreme; means [-0.5672, +0.5672] |
| cw4_world_death_rate: World epidemic deaths (all) per 1,000 person-turns over the whole run (QR - QC) | p | 19: +5.304 | +5.304 [+5.304, +5.304] | 1 / 0 / 0 | 2/2 as extreme; means [-5.304, +5.304] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw4_world_arrival_rate: Cross-polity arrivals per 1,000 region-turns, world (QR - QC) | t | 5: -0.625 | -0.625 [-0.625, -0.625] | 0 / 1 / 0 | 2/2 as extreme; means [-0.625, +0.625] |
| cw4_world_arrival_rate: Cross-polity arrivals per 1,000 region-turns, world (QR - QC) | p | 19: +19.06 | +19.06 [+19.06, +19.06] | 1 / 0 / 0 | 2/2 as extreme; means [-19.06, +19.06] |
| cw4_world_deaths: World epidemic deaths, count (QR - QC) | t | 5: +14 | +14 [+14, +14] | 1 / 0 / 0 | 2/2 as extreme; means [-14, +14] |
| cw4_world_deaths: World epidemic deaths, count (QR - QC) | p | 19: +534 | +534 [+534, +534] | 1 / 0 / 0 | 2/2 as extreme; means [-534, +534] |
| cw4_sel_arrivals: Arrivals into closing civs' regions in their windows (QR - QC; conditioned on each arm's own closures: selection) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw4_sel_arrivals: Arrivals into closing civs' regions in their windows (QR - QC; conditioned on each arm's own closures: selection) | p | 19: +29 | +29 [+29, +29] | 1 / 0 / 0 | 2/2 as extreme; means [-29, +29] |
| cw4_sel_deaths: Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing civs in their windows (QR - QC; conditioned on each arm's own closures: selection) | t | 5: +0.08454 | +0.08454 [+0.08454, +0.08454] | 1 / 0 / 0 | 2/2 as extreme; means [-0.08454, +0.08454] |
| cw4_sel_deaths: Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing civs in their windows (QR - QC; conditioned on each arm's own closures: selection) | p | 19: +4.662 | +4.662 [+4.662, +4.662] | 1 / 0 / 0 | 2/2 as extreme; means [-4.662, +4.662] |
| cw4_sel_arrival_rate: Arrivals per 100 window civ-turns (QR - QC; conditioned on each arm's own closures: selection) | t | 5: -1.275 | -1.275 [-1.275, -1.275] | 0 / 1 / 0 | 2/2 as extreme; means [-1.275, +1.275] |
| cw4_sel_arrival_rate: Arrivals per 100 window civ-turns (QR - QC; conditioned on each arm's own closures: selection) | p | 19: +7.034 | +7.034 [+7.034, +7.034] | 1 / 0 / 0 | 2/2 as extreme; means [-7.034, +7.034] |
| cw4_sel_window: Window civ-turns (QR - QC; conditioned on each arm's own closures: selection) | t | 5: +58 | +58 [+58, +58] | 1 / 0 / 0 | 2/2 as extreme; means [-58, +58] |
| cw4_sel_window: Window civ-turns (QR - QC; conditioned on each arm's own closures: selection) | p | 19: -274 | -274 [-274, -274] | 0 / 1 / 0 | 2/2 as extreme; means [-274, +274] |
| cw4_cost_world_deaths: World epidemic deaths per 1,000 person-turns (QC - Q0: the cost effect) | t | 5: +0.6738 | +0.6738 [+0.6738, +0.6738] | 1 / 0 / 0 | 2/2 as extreme; means [-0.6738, +0.6738] |
| cw4_cost_world_deaths: World epidemic deaths per 1,000 person-turns (QC - Q0: the cost effect) | p | 19: -4.394 | -4.394 [-4.394, -4.394] | 0 / 1 / 0 | 2/2 as extreme; means [-4.394, +4.394] |
| cw4_cost_world_arrivals: Cross-polity arrivals, world (QC - Q0: the cost effect) | t | 5: +3 | +3 [+3, +3] | 1 / 0 / 0 | 2/2 as extreme; means [-3, +3] |
| cw4_cost_world_arrivals: Cross-polity arrivals, world (QC - Q0: the cost effect) | p | 19: -76 | -76 [-76, -76] | 0 / 1 / 0 | 2/2 as extreme; means [-76, +76] |
| cw4_cost_treasury: World treasury at the end (QC - Q0: the cost effect) | t | 5: -248 | -248 [-248, -248] | 0 / 1 / 0 | 2/2 as extreme; means [-248, +248] |
| cw4_cost_treasury: World treasury at the end (QC - Q0: the cost effect) | p | 19: +646 | +646 [+646, +646] | 1 / 0 / 0 | 2/2 as extreme; means [-646, +646] |
| cw4_legacy_world_arrivals: Cross-polity arrivals, world (QR - QL) | t | 5: -2 | -2 [-2, -2] | 0 / 1 / 0 | 2/2 as extreme; means [-2, +2] |
| cw4_legacy_world_arrivals: Cross-polity arrivals, world (QR - QL) | p | 19: +36 | +36 [+36, +36] | 1 / 0 / 0 | 2/2 as extreme; means [-36, +36] |
| cw4_legacy_world_death_rate: World epidemic deaths per 1,000 person-turns (QR - QL) | t | 5: -1.301 | -1.301 [-1.301, -1.301] | 0 / 1 / 0 | 2/2 as extreme; means [-1.301, +1.301] |
| cw4_legacy_world_death_rate: World epidemic deaths per 1,000 person-turns (QR - QL) | p | 19: +2.144 | +2.144 [+2.144, +2.144] | 1 / 0 / 0 | 2/2 as extreme; means [-2.144, +2.144] |
| cw4_h_forgone: Route income forgone, both sides (QR alone; structurally 0 in QC) | t | 5: +312 | +312 [+312, +312] | 1 / 0 / 0 | n/a (no control) |
| cw4_h_forgone: Route income forgone, both sides (QR alone; structurally 0 in QC) | p | 19: +2392 | +2392 [+2392, +2392] | 1 / 0 / 0 | n/a (no control) |
| cw4_h_food: Net food transport into closing civs' regions in their windows (QR - QC) | t | 5: -13.46 | -13.46 [-13.46, -13.46] | 0 / 1 / 0 | 2/2 as extreme; means [-13.46, +13.46] |
| cw4_h_food: Net food transport into closing civs' regions in their windows (QR - QC) | p | 19: +94.64 | +94.64 [+94.64, +94.64] | 1 / 0 / 0 | 2/2 as extreme; means [-94.64, +94.64] |
| cw4_h_replans: Merchant disruption replans, world (QR - QC) | t | 5: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] |
| cw4_h_replans: Merchant disruption replans, world (QR - QC) | p | 19: +63 | +63 [+63, +63] | 1 / 0 / 0 | 2/2 as extreme; means [-63, +63] |
| cw4_h_unwinds: Merchant unwinds, world (QR - QC) | t | 5: +18 | +18 [+18, +18] | 1 / 0 / 0 | 2/2 as extreme; means [-18, +18] |
| cw4_h_unwinds: Merchant unwinds, world (QR - QC) | p | 19: +142 | +142 [+142, +142] | 1 / 0 / 0 | 2/2 as extreme; means [-142, +142] |
| cw4_h_treasury: Closing civs' treasury at the end (QR - QC) | t | 5: -82 | -82 [-82, -82] | 0 / 1 / 0 | 2/2 as extreme; means [-82, +82] |
| cw4_h_treasury: Closing civs' treasury at the end (QR - QC) | p | 19: -1630 | -1630 [-1630, -1630] | 0 / 1 / 0 | 2/2 as extreme; means [-1630, +1630] |
| cw4_h_stability: Closing civs' mean stability in their windows (QR - QC) | t | 5: -2.663 | -2.663 [-2.663, -2.663] | 0 / 1 / 0 | 2/2 as extreme; means [-2.663, +2.663] |
| cw4_h_stability: Closing civs' mean stability in their windows (QR - QC) | p | 19: +1.9 | +1.9 [+1.9, +1.9] | 1 / 0 / 0 | 2/2 as extreme; means [-1.9, +1.9] |
| cw4_h_partner_population: Partner civs' population at the end (QR - QC) | t | 5: -9 | -9 [-9, -9] | 0 / 1 / 0 | 2/2 as extreme; means [-9, +9] |
| cw4_h_partner_population: Partner civs' population at the end (QR - QC) | p | 19: -178 | -178 [-178, -178] | 0 / 1 / 0 | 2/2 as extreme; means [-178, +178] |
| cw4_h_partner_treasury: Partner civs' treasury at the end (QR - QC) | t | 5: -82 | -82 [-82, -82] | 0 / 1 / 0 | 2/2 as extreme; means [-82, +82] |
| cw4_h_partner_treasury: Partner civs' treasury at the end (QR - QC) | p | 19: -1630 | -1630 [-1630, -1630] | 0 / 1 / 0 | 2/2 as extreme; means [-1630, +1630] |
| cw4_h_leaked: Deliveries still crossing a closed pair (QR alone) | t | 5: +2 | +2 [+2, +2] | 1 / 0 / 0 | n/a (no control) |
| cw4_h_leaked: Deliveries still crossing a closed pair (QR alone) | p | 19: +171 | +171 [+171, +171] | 1 / 0 / 0 | n/a (no control) |
| cw4_h_enforcement: Enforcement paid (QR - QC) | t | 5: +32 | +32 [+32, +32] | 1 / 0 / 0 | 2/2 as extreme; means [-32, +32] |
| cw4_h_enforcement: Enforcement paid (QR - QC) | p | 19: -254 | -254 [-254, -254] | 0 / 1 / 0 | 2/2 as extreme; means [-254, +254] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q0 - QL | Population at the end (sum over civilizations) | t | 5: +9 | +9 [+9, +9] | 1 / 0 / 0 | 2/2 as extreme; means [-9, +9] | recorded |
| Q0 - QL | Population at the end (sum over civilizations) | p | 19: -113 | -113 [-113, -113] | 0 / 1 / 0 | 2/2 as extreme; means [-113, +113] | recorded |
| Q0 - QL | Treasury at the end (sum over civilizations) | t | 5: +96 | +96 [+96, +96] | 1 / 0 / 0 | 2/2 as extreme; means [-96, +96] | recorded |
| Q0 - QL | Treasury at the end (sum over civilizations) | p | 19: -562 | -562 [-562, -562] | 0 / 1 / 0 | 2/2 as extreme; means [-562, +562] | recorded |
| Q0 - QL | Food shortfall after relief over the run (food) | t | 5: +653.9 | +653.9 [+653.9, +653.9] | 1 / 0 / 0 | 2/2 as extreme; means [-653.9, +653.9] | recorded |
| Q0 - QL | Food shortfall after relief over the run (food) | p | 19: -1865 | -1865 [-1865, -1865] | 0 / 1 / 0 | 2/2 as extreme; means [-1865, +1865] | recorded |
| Q0 - QL | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| Q0 - QL | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| Q0 - QL | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| Q0 - QL | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| Q0 - QL | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| Q0 - QL | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| Q0 - QL | Deaths by epidemic (the epidemic authority) | t | 5: -74 | -74 [-74, -74] | 0 / 1 / 0 | 2/2 as extreme; means [-74, +74] | recorded |
| Q0 - QL | Deaths by epidemic (the epidemic authority) | p | 19: -95 | -95 [-95, -95] | 0 / 1 / 0 | 2/2 as extreme; means [-95, +95] | recorded |
| Q0 - QL | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| Q0 - QL | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| Q0 - QL | Agents migrating between regions over the run | t | 5: +99 | +99 [+99, +99] | 1 / 0 / 0 | 2/2 as extreme; means [-99, +99] | recorded |
| Q0 - QL | Agents migrating between regions over the run | p | 19: -3154 | -3154 [-3154, -3154] | 0 / 1 / 0 | 2/2 as extreme; means [-3154, +3154] | recorded |
| Q0 - QL | Mean wealth Gini of living civilizations at the end | t | 5: -0.1785 | -0.1785 [-0.1785, -0.1785] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1785, +0.1785] | recorded |
| Q0 - QL | Mean wealth Gini of living civilizations at the end | p | 19: -0.004683 | -0.004683 [-0.004683, -0.004683] | 0 / 1 / 0 | 2/2 as extreme; means [-0.004683, +0.004683] | recorded |
| Q0 - QL | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| Q0 - QL | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QC - Q0 | Population at the end (sum over civilizations) | t | 5: -7 | -7 [-7, -7] | 0 / 1 / 0 | 2/2 as extreme; means [-7, +7] | recorded |
| QC - Q0 | Population at the end (sum over civilizations) | p | 19: +198 | +198 [+198, +198] | 1 / 0 / 0 | 2/2 as extreme; means [-198, +198] | recorded |
| QC - Q0 | Treasury at the end (sum over civilizations) | t | 5: -248 | -248 [-248, -248] | 0 / 1 / 0 | 2/2 as extreme; means [-248, +248] | recorded |
| QC - Q0 | Treasury at the end (sum over civilizations) | p | 19: +646 | +646 [+646, +646] | 1 / 0 / 0 | 2/2 as extreme; means [-646, +646] | recorded |
| QC - Q0 | Food shortfall after relief over the run (food) | t | 5: -682.4 | -682.4 [-682.4, -682.4] | 0 / 1 / 0 | 2/2 as extreme; means [-682.4, +682.4] | recorded |
| QC - Q0 | Food shortfall after relief over the run (food) | p | 19: +3466 | +3466 [+3466, +3466] | 1 / 0 / 0 | 2/2 as extreme; means [-3466, +3466] | recorded |
| QC - Q0 | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QC - Q0 | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QC - Q0 | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QC - Q0 | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QC - Q0 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QC - Q0 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QC - Q0 | Deaths by epidemic (the epidemic authority) | t | 5: +13 | +13 [+13, +13] | 1 / 0 / 0 | 2/2 as extreme; means [-13, +13] | recorded |
| QC - Q0 | Deaths by epidemic (the epidemic authority) | p | 19: -305 | -305 [-305, -305] | 0 / 1 / 0 | 2/2 as extreme; means [-305, +305] | recorded |
| QC - Q0 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QC - Q0 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QC - Q0 | Agents migrating between regions over the run | t | 5: -399 | -399 [-399, -399] | 0 / 1 / 0 | 2/2 as extreme; means [-399, +399] | recorded |
| QC - Q0 | Agents migrating between regions over the run | p | 19: +3564 | +3564 [+3564, +3564] | 1 / 0 / 0 | 2/2 as extreme; means [-3564, +3564] | recorded |
| QC - Q0 | Mean wealth Gini of living civilizations at the end | t | 5: +0.1435 | +0.1435 [+0.1435, +0.1435] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1435, +0.1435] | recorded |
| QC - Q0 | Mean wealth Gini of living civilizations at the end | p | 19: +0.07742 | +0.07742 [+0.07742, +0.07742] | 1 / 0 / 0 | 2/2 as extreme; means [-0.07742, +0.07742] | recorded |
| QC - Q0 | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QC - Q0 | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
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
| QR - QL | Population at the end (sum over civilizations) | t | 5: -7 | -7 [-7, -7] | 0 / 1 / 0 | 2/2 as extreme; means [-7, +7] | recorded |
| QR - QL | Population at the end (sum over civilizations) | p | 19: -75 | -75 [-75, -75] | 0 / 1 / 0 | 2/2 as extreme; means [-75, +75] | recorded |
| QR - QL | Treasury at the end (sum over civilizations) | t | 5: -234 | -234 [-234, -234] | 0 / 1 / 0 | 2/2 as extreme; means [-234, +234] | recorded |
| QR - QL | Treasury at the end (sum over civilizations) | p | 19: -1505 | -1505 [-1505, -1505] | 0 / 1 / 0 | 2/2 as extreme; means [-1505, +1505] | recorded |
| QR - QL | Food shortfall after relief over the run (food) | t | 5: -304.2 | -304.2 [-304.2, -304.2] | 0 / 1 / 0 | 2/2 as extreme; means [-304.2, +304.2] | recorded |
| QR - QL | Food shortfall after relief over the run (food) | p | 19: -2135 | -2135 [-2135, -2135] | 0 / 1 / 0 | 2/2 as extreme; means [-2135, +2135] | recorded |
| QR - QL | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QL | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QL | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QL | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QL | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QL | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QL | Deaths by epidemic (the epidemic authority) | t | 5: -47 | -47 [-47, -47] | 0 / 1 / 0 | 2/2 as extreme; means [-47, +47] | recorded |
| QR - QL | Deaths by epidemic (the epidemic authority) | p | 19: +134 | +134 [+134, +134] | 1 / 0 / 0 | 2/2 as extreme; means [-134, +134] | recorded |
| QR - QL | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QL | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QL | Agents migrating between regions over the run | t | 5: -178 | -178 [-178, -178] | 0 / 1 / 0 | 2/2 as extreme; means [-178, +178] | recorded |
| QR - QL | Agents migrating between regions over the run | p | 19: -943 | -943 [-943, -943] | 0 / 1 / 0 | 2/2 as extreme; means [-943, +943] | recorded |
| QR - QL | Mean wealth Gini of living civilizations at the end | t | 5: -0.008036 | -0.008036 [-0.008036, -0.008036] | 0 / 1 / 0 | 2/2 as extreme; means [-0.008036, +0.008036] | recorded |
| QR - QL | Mean wealth Gini of living civilizations at the end | p | 19: +0.04538 | +0.04538 [+0.04538, +0.04538] | 1 / 0 / 0 | 2/2 as extreme; means [-0.04538, +0.04538] | recorded |
| QR - QL | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QR - QL | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| QL | 7.0 [7.0, 7.0] | 17.9 [17.9, 17.9] |
| Q0 | 7.1 [7.1, 7.1] | 17.8 [17.8, 17.8] |
| QC | 7.1 [7.1, 7.1] | 21.0 [21.0, 21.0] |
| QR | 7.1 [7.1, 7.1] | 20.4 [20.4, 20.4] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
