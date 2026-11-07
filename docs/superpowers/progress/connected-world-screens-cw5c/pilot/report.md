# CW5c: S4 bounded epidemic care capacity (C2)

Cohort pilot. Runs: 6; failed: 0 (missing outcomes: 0); simulation and extraction seconds 153 (0.042 core-hours)
Projected held run time from this pilot: 0.255 core-hours (x1.5 = 0.382) for 36 runs

Identity digests: fbbe8d87971f9d2734982d5149ac22a639b8dbec49752ba7fa9fda2fec3ed539 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"epidemic_care": [1], "local_budgets": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"local_budgets": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| EC | t | 5: activated | 1 of 1 |
| EC | p | 19: activated | 1 of 1 |
| EF | t | 5: activated | 1 of 1 |
| EF | p | 19: activated | 1 of 1 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5c_covered_cfr: Realized deaths per new infection in covered region-turns (EF - EC; each arm's own covered region-turns) | t | 5: -0.06267 | -0.06267 [-0.06267, -0.06267] | 0 / 1 / 0 | 2/2 as extreme; means [-0.06267, +0.06267] |
| cw5c_covered_cfr: Realized deaths per new infection in covered region-turns (EF - EC; each arm's own covered region-turns) | p | 19: -0.01949 | -0.01949 [-0.01949, -0.01949] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01949, +0.01949] |
| cw5c_world_death_rate: World epidemic deaths per 1,000 person-turns over the whole run (EF - EC) | t | 5: -2.68 | -2.68 [-2.68, -2.68] | 0 / 1 / 0 | 2/2 as extreme; means [-2.68, +2.68] |
| cw5c_world_death_rate: World epidemic deaths per 1,000 person-turns over the whole run (EF - EC) | p | 19: -1.174 | -1.174 [-1.174, -1.174] | 0 / 1 / 0 | 2/2 as extreme; means [-1.174, +1.174] |
| cw5c_covered_death_rate: Epidemic deaths per 1,000 person-turns in covered region-turns (EF - EC; each arm's own covered region-turns) | t | 5: -8.426 | -8.426 [-8.426, -8.426] | 0 / 1 / 0 | 2/2 as extreme; means [-8.426, +8.426] |
| cw5c_covered_death_rate: Epidemic deaths per 1,000 person-turns in covered region-turns (EF - EC; each arm's own covered region-turns) | p | 19: -3.179 | -3.179 [-3.179, -3.179] | 0 / 1 / 0 | 2/2 as extreme; means [-3.179, +3.179] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5c_itt_cfr: Deaths per new infection in continuing-outbreak region-turns (EF - EC) | t | 5: -0.03687 | -0.03687 [-0.03687, -0.03687] | 0 / 1 / 0 | 2/2 as extreme; means [-0.03687, +0.03687] |
| cw5c_itt_cfr: Deaths per new infection in continuing-outbreak region-turns (EF - EC) | p | 19: -0.01462 | -0.01462 [-0.01462, -0.01462] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01462, +0.01462] |
| cw5c_itt_cfr_vs_none: Deaths per new infection in continuing-outbreak region-turns (EF - E0) | t | 5: -0.02769 | -0.02769 [-0.02769, -0.02769] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02769, +0.02769] |
| cw5c_itt_cfr_vs_none: Deaths per new infection in continuing-outbreak region-turns (EF - E0) | p | 19: -0.01304 | -0.01304 [-0.01304, -0.01304] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01304, +0.01304] |
| cw5c_world_deaths: World epidemic deaths, count (EF - EC) | t | 5: -77 | -77 [-77, -77] | 0 / 1 / 0 | 2/2 as extreme; means [-77, +77] |
| cw5c_world_deaths: World epidemic deaths, count (EF - EC) | p | 19: -40 | -40 [-40, -40] | 0 / 1 / 0 | 2/2 as extreme; means [-40, +40] |
| cw5c_world_death_rate_vs_none: World epidemic deaths per 1,000 person-turns (EF - E0) | t | 5: -2.665 | -2.665 [-2.665, -2.665] | 0 / 1 / 0 | 2/2 as extreme; means [-2.665, +2.665] |
| cw5c_world_death_rate_vs_none: World epidemic deaths per 1,000 person-turns (EF - E0) | p | 19: -0.5524 | -0.5524 [-0.5524, -0.5524] | 0 / 1 / 0 | 2/2 as extreme; means [-0.5524, +0.5524] |
| cw5c_cost_world_death_rate: World epidemic deaths per 1,000 person-turns (EC - E0: the cost effect) | t | 5: +0.01474 | +0.01474 [+0.01474, +0.01474] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01474, +0.01474] |
| cw5c_cost_world_death_rate: World epidemic deaths per 1,000 person-turns (EC - E0: the cost effect) | p | 19: +0.6212 | +0.6212 [+0.6212, +0.6212] | 1 / 0 / 0 | 2/2 as extreme; means [-0.6212, +0.6212] |
| cw5c_covered_region_turns: Covered region-turns (EF - EC; selection) | t | 5: -61 | -61 [-61, -61] | 0 / 1 / 0 | 2/2 as extreme; means [-61, +61] |
| cw5c_covered_region_turns: Covered region-turns (EF - EC; selection) | p | 19: +416 | +416 [+416, +416] | 1 / 0 / 0 | 2/2 as extreme; means [-416, +416] |
| cw5c_mean_coverage: Mean coverage over region-turns with capacity (EF) | t | 5: +1 | +1 [+1, +1] | 1 / 0 / 0 | n/a (no control) |
| cw5c_mean_coverage: Mean coverage over region-turns with capacity (EF) | p | 19: +0.9999 | +0.9999 [+0.9999, +0.9999] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time: Carer farm time removed, worker-turns (EF) | t | 5: +30.63 | +30.63 [+30.63, +30.63] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time: Carer farm time removed, worker-turns (EF) | p | 19: +931.5 | +931.5 [+931.5, +931.5] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time_cost: Carer farm time removed, worker-turns (EC) | t | 5: +45.37 | +45.37 [+45.37, +45.37] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time_cost: Carer farm time removed, worker-turns (EC) | p | 19: +678.6 | +678.6 [+678.6, +678.6] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_wages: Care wages paid, treasury units (EF) | t | 5: +15.31 | +15.31 [+15.31, +15.31] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_wages: Care wages paid, treasury units (EF) | p | 19: +465.7 | +465.7 [+465.7, +465.7] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld: Carers' ordinary income withheld, wealth units (EF) | t | 5: +3.622 | +3.622 [+3.622, +3.622] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld: Carers' ordinary income withheld, wealth units (EF) | p | 19: +107.6 | +107.6 [+107.6, +107.6] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_food_shortfall: Food shortfall after relief over the run (EF - EC) | t | 5: +471.6 | +471.6 [+471.6, +471.6] | 1 / 0 / 0 | 2/2 as extreme; means [-471.6, +471.6] |
| cw5c_h_food_shortfall: Food shortfall after relief over the run (EF - EC) | p | 19: +2899 | +2899 [+2899, +2899] | 1 / 0 / 0 | 2/2 as extreme; means [-2899, +2899] |
| cw5c_h_food_shortfall_cost: Food shortfall after relief over the run (EC - E0: the cost) | t | 5: -281.4 | -281.4 [-281.4, -281.4] | 0 / 1 / 0 | 2/2 as extreme; means [-281.4, +281.4] |
| cw5c_h_food_shortfall_cost: Food shortfall after relief over the run (EC - E0: the cost) | p | 19: -514.5 | -514.5 [-514.5, -514.5] | 0 / 1 / 0 | 2/2 as extreme; means [-514.5, +514.5] |
| cw5c_h_dearth: Dearth region-turns, sufficiency after relief below 1 (EC - E0) | t | 5: -26 | -26 [-26, -26] | 0 / 1 / 0 | 2/2 as extreme; means [-26, +26] |
| cw5c_h_dearth: Dearth region-turns, sufficiency after relief below 1 (EC - E0) | p | 19: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] |
| cw5c_h_famine: Famine region-turns, sufficiency after relief below 0.6 (EC - E0) | t | 5: +25 | +25 [+25, +25] | 1 / 0 / 0 | 2/2 as extreme; means [-25, +25] |
| cw5c_h_famine: Famine region-turns, sufficiency after relief below 0.6 (EC - E0) | p | 19: +78 | +78 [+78, +78] | 1 / 0 / 0 | 2/2 as extreme; means [-78, +78] |
| cw5c_h_dearth_care: Dearth region-turns (EF - EC) | t | 5: +70 | +70 [+70, +70] | 1 / 0 / 0 | 2/2 as extreme; means [-70, +70] |
| cw5c_h_dearth_care: Dearth region-turns (EF - EC) | p | 19: +104 | +104 [+104, +104] | 1 / 0 / 0 | 2/2 as extreme; means [-104, +104] |
| cw5c_h_care_coins: L9 coins awarded to care envelopes (EF) | t | 5: +92 | +92 [+92, +92] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins: L9 coins awarded to care envelopes (EF) | p | 19: +2083 | +2083 [+2083, +2083] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_other_coins: L9 coins awarded to every other service (EC - E0: displacement within L9) | t | 5: +7 | +7 [+7, +7] | 1 / 0 / 0 | 2/2 as extreme; means [-7, +7] |
| cw5c_h_other_coins: L9 coins awarded to every other service (EC - E0: displacement within L9) | p | 19: +15 | +15 [+15, +15] | 1 / 0 / 0 | 2/2 as extreme; means [-15, +15] |
| cw5c_h_relief_coins: L9 coins awarded to granary relief (EC - E0) | t | 5: +7 | +7 [+7, +7] | 1 / 0 / 0 | 2/2 as extreme; means [-7, +7] |
| cw5c_h_relief_coins: L9 coins awarded to granary relief (EC - E0) | p | 19: +15 | +15 [+15, +15] | 1 / 0 / 0 | 2/2 as extreme; means [-15, +15] |
| cw5c_h_treasury: Treasury at the end (EC - E0) | t | 5: +60 | +60 [+60, +60] | 1 / 0 / 0 | 2/2 as extreme; means [-60, +60] |
| cw5c_h_treasury: Treasury at the end (EC - E0) | p | 19: +448 | +448 [+448, +448] | 1 / 0 / 0 | 2/2 as extreme; means [-448, +448] |
| cw5c_h_treasury_care: Treasury at the end (EF - EC) | t | 5: -376 | -376 [-376, -376] | 0 / 1 / 0 | 2/2 as extreme; means [-376, +376] |
| cw5c_h_treasury_care: Treasury at the end (EF - EC) | p | 19: -1224 | -1224 [-1224, -1224] | 0 / 1 / 0 | 2/2 as extreme; means [-1224, +1224] |
| cw5c_h_stability: Mean civ stability over civ-turns (EC - E0) | t | 5: -0.9986 | -0.9986 [-0.9986, -0.9986] | 0 / 1 / 0 | 2/2 as extreme; means [-0.9986, +0.9986] |
| cw5c_h_stability: Mean civ stability over civ-turns (EC - E0) | p | 19: -1.954 | -1.954 [-1.954, -1.954] | 0 / 1 / 0 | 2/2 as extreme; means [-1.954, +1.954] |
| cw5c_h_stability_care: Mean civ stability over civ-turns (EF - EC) | t | 5: -3.052 | -3.052 [-3.052, -3.052] | 0 / 1 / 0 | 2/2 as extreme; means [-3.052, +3.052] |
| cw5c_h_stability_care: Mean civ stability over civ-turns (EF - EC) | p | 19: +2.94 | +2.94 [+2.94, +2.94] | 1 / 0 / 0 | 2/2 as extreme; means [-2.94, +2.94] |
| cw5c_h_unrest: Mean city unrest over city-turns (EC - E0) | t | 5: +0.1142 | +0.1142 [+0.1142, +0.1142] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1142, +0.1142] |
| cw5c_h_unrest: Mean city unrest over city-turns (EC - E0) | p | 19: -0.02869 | -0.02869 [-0.02869, -0.02869] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02869, +0.02869] |
| cw5c_h_unrest_care: Mean city unrest over city-turns (EF - EC) | t | 5: -0.1012 | -0.1012 [-0.1012, -0.1012] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1012, +0.1012] |
| cw5c_h_unrest_care: Mean city unrest over city-turns (EF - EC) | p | 19: +0.009522 | +0.009522 [+0.009522, +0.009522] | 1 / 0 / 0 | 2/2 as extreme; means [-0.009522, +0.009522] |
| cw5c_h_population: Population at the end (EF - EC) | t | 5: +10 | +10 [+10, +10] | 1 / 0 / 0 | 2/2 as extreme; means [-10, +10] |
| cw5c_h_population: Population at the end (EF - EC) | p | 19: +125 | +125 [+125, +125] | 1 / 0 / 0 | 2/2 as extreme; means [-125, +125] |
| cw5c_h_population_cost: Population at the end (EC - E0) | t | 5: -29 | -29 [-29, -29] | 0 / 1 / 0 | 2/2 as extreme; means [-29, +29] |
| cw5c_h_population_cost: Population at the end (EC - E0) | p | 19: -59 | -59 [-59, -59] | 0 / 1 / 0 | 2/2 as extreme; means [-59, +59] |
| cw5c_h_migration: Agents moving between regions over the run (EF - EC) | t | 5: +146 | +146 [+146, +146] | 1 / 0 / 0 | 2/2 as extreme; means [-146, +146] |
| cw5c_h_migration: Agents moving between regions over the run (EF - EC) | p | 19: +2347 | +2347 [+2347, +2347] | 1 / 0 / 0 | 2/2 as extreme; means [-2347, +2347] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EC - E0 | Population at the end (sum over civilizations) | t | 5: -29 | -29 [-29, -29] | 0 / 1 / 0 | 2/2 as extreme; means [-29, +29] | recorded |
| EC - E0 | Population at the end (sum over civilizations) | p | 19: -59 | -59 [-59, -59] | 0 / 1 / 0 | 2/2 as extreme; means [-59, +59] | recorded |
| EC - E0 | Treasury at the end (sum over civilizations) | t | 5: +60 | +60 [+60, +60] | 1 / 0 / 0 | 2/2 as extreme; means [-60, +60] | recorded |
| EC - E0 | Treasury at the end (sum over civilizations) | p | 19: +448 | +448 [+448, +448] | 1 / 0 / 0 | 2/2 as extreme; means [-448, +448] | recorded |
| EC - E0 | Food shortfall after relief over the run (food) | t | 5: -281.4 | -281.4 [-281.4, -281.4] | 0 / 1 / 0 | 2/2 as extreme; means [-281.4, +281.4] | recorded |
| EC - E0 | Food shortfall after relief over the run (food) | p | 19: -514.5 | -514.5 [-514.5, -514.5] | 0 / 1 / 0 | 2/2 as extreme; means [-514.5, +514.5] | recorded |
| EC - E0 | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EC - E0 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EC - E0 | Deaths by epidemic (the epidemic authority) | t | 5: -14 | -14 [-14, -14] | 0 / 1 / 0 | 2/2 as extreme; means [-14, +14] | recorded |
| EC - E0 | Deaths by epidemic (the epidemic authority) | p | 19: +54 | +54 [+54, +54] | 1 / 0 / 0 | 2/2 as extreme; means [-54, +54] | recorded |
| EC - E0 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EC - E0 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EC - E0 | Agents migrating between regions over the run | t | 5: -223 | -223 [-223, -223] | 0 / 1 / 0 | 2/2 as extreme; means [-223, +223] | recorded |
| EC - E0 | Agents migrating between regions over the run | p | 19: -162 | -162 [-162, -162] | 0 / 1 / 0 | 2/2 as extreme; means [-162, +162] | recorded |
| EC - E0 | Mean wealth Gini of living civilizations at the end | t | 5: +0.02176 | +0.02176 [+0.02176, +0.02176] | 1 / 0 / 0 | 2/2 as extreme; means [-0.02176, +0.02176] | recorded |
| EC - E0 | Mean wealth Gini of living civilizations at the end | p | 19: -0.04862 | -0.04862 [-0.04862, -0.04862] | 0 / 1 / 0 | 2/2 as extreme; means [-0.04862, +0.04862] | recorded |
| EC - E0 | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EC - E0 | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - EC | Population at the end (sum over civilizations) | t | 5: +10 | +10 [+10, +10] | 1 / 0 / 0 | 2/2 as extreme; means [-10, +10] | recorded |
| EF - EC | Population at the end (sum over civilizations) | p | 19: +125 | +125 [+125, +125] | 1 / 0 / 0 | 2/2 as extreme; means [-125, +125] | recorded |
| EF - EC | Treasury at the end (sum over civilizations) | t | 5: -376 | -376 [-376, -376] | 0 / 1 / 0 | 2/2 as extreme; means [-376, +376] | recorded |
| EF - EC | Treasury at the end (sum over civilizations) | p | 19: -1224 | -1224 [-1224, -1224] | 0 / 1 / 0 | 2/2 as extreme; means [-1224, +1224] | recorded |
| EF - EC | Food shortfall after relief over the run (food) | t | 5: +471.6 | +471.6 [+471.6, +471.6] | 1 / 0 / 0 | 2/2 as extreme; means [-471.6, +471.6] | recorded |
| EF - EC | Food shortfall after relief over the run (food) | p | 19: +2899 | +2899 [+2899, +2899] | 1 / 0 / 0 | 2/2 as extreme; means [-2899, +2899] | recorded |
| EF - EC | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - EC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - EC | Deaths by epidemic (the epidemic authority) | t | 5: -77 | -77 [-77, -77] | 0 / 1 / 0 | 2/2 as extreme; means [-77, +77] | recorded |
| EF - EC | Deaths by epidemic (the epidemic authority) | p | 19: -40 | -40 [-40, -40] | 0 / 1 / 0 | 2/2 as extreme; means [-40, +40] | recorded |
| EF - EC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - EC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - EC | Agents migrating between regions over the run | t | 5: +146 | +146 [+146, +146] | 1 / 0 / 0 | 2/2 as extreme; means [-146, +146] | recorded |
| EF - EC | Agents migrating between regions over the run | p | 19: +2347 | +2347 [+2347, +2347] | 1 / 0 / 0 | 2/2 as extreme; means [-2347, +2347] | recorded |
| EF - EC | Mean wealth Gini of living civilizations at the end | t | 5: -0.1968 | -0.1968 [-0.1968, -0.1968] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1968, +0.1968] | recorded |
| EF - EC | Mean wealth Gini of living civilizations at the end | p | 19: +0.06209 | +0.06209 [+0.06209, +0.06209] | 1 / 0 / 0 | 2/2 as extreme; means [-0.06209, +0.06209] | recorded |
| EF - EC | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - EC | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - E0 | Population at the end (sum over civilizations) | t | 5: -19 | -19 [-19, -19] | 0 / 1 / 0 | 2/2 as extreme; means [-19, +19] | recorded |
| EF - E0 | Population at the end (sum over civilizations) | p | 19: +66 | +66 [+66, +66] | 1 / 0 / 0 | 2/2 as extreme; means [-66, +66] | recorded |
| EF - E0 | Treasury at the end (sum over civilizations) | t | 5: -316 | -316 [-316, -316] | 0 / 1 / 0 | 2/2 as extreme; means [-316, +316] | recorded |
| EF - E0 | Treasury at the end (sum over civilizations) | p | 19: -776 | -776 [-776, -776] | 0 / 1 / 0 | 2/2 as extreme; means [-776, +776] | recorded |
| EF - E0 | Food shortfall after relief over the run (food) | t | 5: +190.3 | +190.3 [+190.3, +190.3] | 1 / 0 / 0 | 2/2 as extreme; means [-190.3, +190.3] | recorded |
| EF - E0 | Food shortfall after relief over the run (food) | p | 19: +2384 | +2384 [+2384, +2384] | 1 / 0 / 0 | 2/2 as extreme; means [-2384, +2384] | recorded |
| EF - E0 | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - E0 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - E0 | Deaths by epidemic (the epidemic authority) | t | 5: -91 | -91 [-91, -91] | 0 / 1 / 0 | 2/2 as extreme; means [-91, +91] | recorded |
| EF - E0 | Deaths by epidemic (the epidemic authority) | p | 19: +14 | +14 [+14, +14] | 1 / 0 / 0 | 2/2 as extreme; means [-14, +14] | recorded |
| EF - E0 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - E0 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - E0 | Agents migrating between regions over the run | t | 5: -77 | -77 [-77, -77] | 0 / 1 / 0 | 2/2 as extreme; means [-77, +77] | recorded |
| EF - E0 | Agents migrating between regions over the run | p | 19: +2185 | +2185 [+2185, +2185] | 1 / 0 / 0 | 2/2 as extreme; means [-2185, +2185] | recorded |
| EF - E0 | Mean wealth Gini of living civilizations at the end | t | 5: -0.1751 | -0.1751 [-0.1751, -0.1751] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1751, +0.1751] | recorded |
| EF - E0 | Mean wealth Gini of living civilizations at the end | p | 19: +0.01347 | +0.01347 [+0.01347, +0.01347] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01347, +0.01347] | recorded |
| EF - E0 | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - E0 | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| E0 | 10.1 [10.1, 10.1] | 41.4 [41.4, 41.4] |
| EC | 11.6 [11.6, 11.6] | 42.5 [42.5, 42.5] |
| EF | 12.1 [12.1, 12.1] | 35.2 [35.2, 35.2] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
