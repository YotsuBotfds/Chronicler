# CW3b: S3 infrastructure condition and repair (B3)

Cohort pilot. Runs: 12; failed: 0 (missing outcomes: 0); simulation and extraction seconds 168 (0.047 core-hours)
Projected held run time from this pilot: 0.280 core-hours (x1.5 = 0.419) for 72 runs

Identity digests: af0777e614a549312caafab29e458945b805b766c2b2cdf89e8d878608458f9f (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"infrastructure_condition": [1], "local_budgets": [1], "maintenance_obligation": [1], "repair_projects": [1], "timber_stock": [1], "timber_supply": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"infrastructure_condition": [1], "repair_projects": [1], "timber_stock": [1], "timber_supply": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"local_budgets": [1], "maintenance_obligation": [1], "repair_projects": [1], "timber_stock": [1], "timber_supply": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| R | t | 5: activated | 1 of 1 |
| R | p | 19: activated | 1 of 1 |
| W | t | 5: activated | 1 of 1 |
| W | p | 19: activated | 1 of 1 |
| C | t | 5: activated | 1 of 1 |
| C | p | 19: activated | 1 of 1 |
| W_T | t | 5: activated | 1 of 1 |
| W_T | p | 19: activated | 1 of 1 |
| C_T | t | 5: activated | 1 of 1 |
| C_T | p | 19: activated | 1 of 1 |

## Pre-treatment check at snapshot 28 and the irrigated-region set

| Stratum | World | Arm | Check | Set (regions; sha) |
| --- | --- | --- | --- | --- |
| t | 5 | R | pass | 0,5,7 ; 17c065eec106012a |
| t | 5 | W | pass | 0,5,7 ; 17c065eec106012a |
| t | 5 | C | pass | 0,5,7 ; 17c065eec106012a |
| t | 5 | W_T | pass | 0,5,7 ; 17c065eec106012a |
| t | 5 | C_T | pass | 0,5,7 ; 17c065eec106012a |
| p | 19 | R | pass | 1,9,11 ; bb38cb68f9cb7a7b |
| p | 19 | W | pass | 1,9,11 ; bb38cb68f9cb7a7b |
| p | 19 | C | pass | 1,9,11 ; bb38cb68f9cb7a7b |
| p | 19 | W_T | pass | 1,9,11,18,26 ; 7fe89d567f0d4c0f |
| p | 19 | C_T | pass | 1,9,11,18,26 ; 7fe89d567f0d4c0f |

| Stratum | World | Pair | Set | Primaries |
| --- | --- | --- | --- | --- |
| t | 5 | C - W | same set | in the primaries |
| t | 5 | C_T - W_T | same set | in the primaries |
| p | 19 | C - W | same set | in the primaries |
| p | 19 | C_T - W_T | same set | in the primaries |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw3b_service_l9: Irrigation asset-turns at service >= 0.5 after snapshot 28, share (C - W: works funded only through their own L9 proposal, against none) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_service_l9: Irrigation asset-turns at service >= 0.5 after snapshot 28, share (C - W: works funded only through their own L9 proposal, against none) | p | 19: +0.1932 | +0.1932 [+0.1932, +0.1932] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1932, +0.1932] |
| cw3b_food_l9: Food shortfall share after relief after snapshot 28, in the regions irrigated at snapshot 28 (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_food_l9: Food shortfall share after relief after snapshot 28, in the regions irrigated at snapshot 28 (C - W) | p | 19: -0.01437 | -0.01437 [-0.01437, -0.01437] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01437, +0.01437] |
| cw3b_service_treasury: Irrigation asset-turns at service >= 0.5 after snapshot 28, share (C_T - W_T: works funded by the treasury against none) | t | 5: +0.01544 | +0.01544 [+0.01544, +0.01544] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01544, +0.01544] |
| cw3b_service_treasury: Irrigation asset-turns at service >= 0.5 after snapshot 28, share (C_T - W_T: works funded by the treasury against none) | p | 19: +0.2181 | +0.2181 [+0.2181, +0.2181] | 1 / 0 / 0 | 2/2 as extreme; means [-0.2181, +0.2181] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw3b_food_treasury: Food shortfall share after snapshot 28 in the irrigated regions (C_T - W_T; C_T also repairs roads, which C does not: the works' L9 proposal is irrigation-only) | t | 5: -4.946e-05 | -4.946e-05 [-4.946e-05, -4.946e-05] | 0 / 1 / 0 | 2/2 as extreme; means [-4.946e-05, +4.946e-05] |
| cw3b_food_treasury: Food shortfall share after snapshot 28 in the irrigated regions (C_T - W_T; C_T also repairs roads, which C does not: the works' L9 proposal is irrigation-only) | p | 19: +0.0196 | +0.0196 [+0.0196, +0.0196] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0196, +0.0196] |
| cw3b_service_l9_all: Irrigation serving share over the whole run (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_service_l9_all: Irrigation serving share over the whole run (C - W) | p | 19: +0.1918 | +0.1918 [+0.1918, +0.1918] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1918, +0.1918] |
| cw3b_food_l9_all: Food shortfall share over the whole run in the irrigated regions (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_food_l9_all: Food shortfall share over the whole run in the irrigated regions (C - W) | p | 19: -0.01285 | -0.01285 [-0.01285, -0.01285] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01285, +0.01285] |
| cw3b_service_treasury_all: Irrigation serving share over the whole run (C_T - W_T) | t | 5: +0.01423 | +0.01423 [+0.01423, +0.01423] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01423, +0.01423] |
| cw3b_service_treasury_all: Irrigation serving share over the whole run (C_T - W_T) | p | 19: +0.2158 | +0.2158 [+0.2158, +0.2158] | 1 / 0 / 0 | 2/2 as extreme; means [-0.2158, +0.2158] |
| cw3b_service_wear: Irrigation serving share after snapshot 28 (W - R: what wear alone costs) | t | 5: -0.01039 | -0.01039 [-0.01039, -0.01039] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01039, +0.01039] |
| cw3b_service_wear: Irrigation serving share after snapshot 28 (W - R: what wear alone costs) | p | 19: -0.01426 | -0.01426 [-0.01426, -0.01426] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01426, +0.01426] |
| cw3b_food_wear: Food shortfall share after snapshot 28 in the irrigated regions (W - R) | t | 5: -0.003122 | -0.003122 [-0.003122, -0.003122] | 0 / 1 / 0 | 2/2 as extreme; means [-0.003122, +0.003122] |
| cw3b_food_wear: Food shortfall share after snapshot 28 in the irrigated regions (W - R) | p | 19: +0.0122 | +0.0122 [+0.0122, +0.0122] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0122, +0.0122] |
| cw3b_food_met_l9: Demand-weighted mean of min(1, sufficiency) after snapshot 28 in the irrigated regions (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_food_met_l9: Demand-weighted mean of min(1, sufficiency) after snapshot 28 in the irrigated regions (C - W) | p | 19: +0.01437 | +0.01437 [+0.01437, +0.01437] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01437, +0.01437] |
| cw3b_failed_l9: Assets failed over the run (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_failed_l9: Assets failed over the run (C - W) | p | 19: -7 | -7 [-7, -7] | 0 / 1 / 0 | 2/2 as extreme; means [-7, +7] |
| cw3b_failed_treasury: Assets failed over the run (C_T - W_T) | t | 5: +3 | +3 [+3, +3] | 1 / 0 / 0 | 2/2 as extreme; means [-3, +3] |
| cw3b_failed_treasury: Assets failed over the run (C_T - W_T) | p | 19: -7 | -7 [-7, -7] | 0 / 1 / 0 | 2/2 as extreme; means [-7, +7] |
| cw3b_works_opened: Works opened on irrigation assets (C alone) | t | 5: +8 | +8 [+8, +8] | 1 / 0 / 0 | n/a (no control) |
| cw3b_works_opened: Works opened on irrigation assets (C alone) | p | 19: +65 | +65 [+65, +65] | 1 / 0 / 0 | n/a (no control) |
| cw3b_works_delivered: Work the works delivered (C alone; the farm time removed) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw3b_works_delivered: Work the works delivered (C alone; the farm time removed) | p | 19: +215.3 | +215.3 [+215.3, +215.3] | 1 / 0 / 0 | n/a (no control) |
| cw3b_works_delivered_t: Work the works delivered (C_T alone) | t | 5: +36.9 | +36.9 [+36.9, +36.9] | 1 / 0 / 0 | n/a (no control) |
| cw3b_works_delivered_t: Work the works delivered (C_T alone) | p | 19: +372.6 | +372.6 [+372.6, +372.6] | 1 / 0 / 0 | n/a (no control) |
| cw3b_works_awards: L9 awards to the works' own proposal (C alone) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw3b_works_awards: L9 awards to the works' own proposal (C alone) | p | 19: +65 | +65 [+65, +65] | 1 / 0 / 0 | n/a (no control) |
| cw3b_stalled_envelope: Work-turns stalled without an envelope (C alone) | t | 5: +1232 | +1232 [+1232, +1232] | 1 / 0 / 0 | n/a (no control) |
| cw3b_stalled_envelope: Work-turns stalled without an envelope (C alone) | p | 19: +4034 | +4034 [+4034, +4034] | 1 / 0 / 0 | n/a (no control) |
| cw3b_stalled_timber: Work-turns stalled without timber (C alone) | t | 5: +1232 | +1232 [+1232, +1232] | 1 / 0 / 0 | n/a (no control) |
| cw3b_stalled_timber: Work-turns stalled without timber (C alone) | p | 19: +3142 | +3142 [+3142, +3142] | 1 / 0 / 0 | n/a (no control) |
| cw3b_stalled_timber_t: Work-turns stalled without timber (C_T alone) | t | 5: +1307 | +1307 [+1307, +1307] | 1 / 0 / 0 | n/a (no control) |
| cw3b_stalled_timber_t: Work-turns stalled without timber (C_T alone) | p | 19: +2445 | +2445 [+2445, +2445] | 1 / 0 / 0 | n/a (no control) |
| cw3b_story: Works stalled 20+ turns on an asset that failed (C alone: the underfunded public works story) | t | 5: +6 | +6 [+6, +6] | 1 / 0 / 0 | n/a (no control) |
| cw3b_story: Works stalled 20+ turns on an asset that failed (C alone: the underfunded public works story) | p | 19: +15 | +15 [+15, +15] | 1 / 0 / 0 | n/a (no control) |
| cw3b_pl1_delivered: Timber the woodcutters delivered to the store (C alone; PL1 serves RS2's needs first, then the works') | t | 5: +21.94 | +21.94 [+21.94, +21.94] | 1 / 0 / 0 | n/a (no control) |
| cw3b_pl1_delivered: Timber the woodcutters delivered to the store (C alone; PL1 serves RS2's needs first, then the works') | p | 19: +517.4 | +517.4 [+517.4, +517.4] | 1 / 0 / 0 | n/a (no control) |
| cw3b_pl1_works_launched: Expeditions PL1 launched for the works' timber need (C alone) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw3b_pl1_works_launched: Expeditions PL1 launched for the works' timber need (C alone) | p | 19: +15 | +15 [+15, +15] | 1 / 0 / 0 | n/a (no control) |
| cw3b_pl1_works_launched_t: Expeditions PL1 launched for the works' timber need (C_T alone) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw3b_pl1_works_launched_t: Expeditions PL1 launched for the works' timber need (C_T alone) | p | 19: +16 | +16 [+16, +16] | 1 / 0 / 0 | n/a (no control) |
| cw3b_pl1_works_person_turns: Woodcutter person-turns of the works' expeditions (C alone) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw3b_pl1_works_person_turns: Woodcutter person-turns of the works' expeditions (C alone) | p | 19: +160 | +160 [+160, +160] | 1 / 0 / 0 | n/a (no control) |
| cw3b_timber_refused: The works' timber need rows PL1 refused, every reason (C alone) | t | 5: +526 | +526 [+526, +526] | 1 / 0 / 0 | n/a (no control) |
| cw3b_timber_refused: The works' timber need rows PL1 refused, every reason (C alone) | p | 19: +991 | +991 [+991, +991] | 1 / 0 / 0 | n/a (no control) |
| cw3b_h_rs2_displaced: RS2 repair work delivered (C - W: the L9 envelope displacement) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_h_rs2_displaced: RS2 repair work delivered (C - W: the L9 envelope displacement) | p | 19: +82.79 | +82.79 [+82.79, +82.79] | 1 / 0 / 0 | 2/2 as extreme; means [-82.79, +82.79] |
| cw3b_h_rs2_displaced_t: RS2 repair work delivered (C_T - W_T) | t | 5: -7.469 | -7.469 [-7.469, -7.469] | 0 / 1 / 0 | 2/2 as extreme; means [-7.469, +7.469] |
| cw3b_h_rs2_displaced_t: RS2 repair work delivered (C_T - W_T) | p | 19: -30.39 | -30.39 [-30.39, -30.39] | 0 / 1 / 0 | 2/2 as extreme; means [-30.39, +30.39] |
| cw3b_h_rs2_timber: RS2 work-turns stalled without timber (C - W: woodcutters and forests the works' expeditions took from RS2's later needs) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_h_rs2_timber: RS2 work-turns stalled without timber (C - W: woodcutters and forests the works' expeditions took from RS2's later needs) | p | 19: +8 | +8 [+8, +8] | 1 / 0 / 0 | 2/2 as extreme; means [-8, +8] |
| cw3b_h_rs2_timber_t: RS2 work-turns stalled without timber (C_T - W_T) | t | 5: +42 | +42 [+42, +42] | 1 / 0 / 0 | 2/2 as extreme; means [-42, +42] |
| cw3b_h_rs2_timber_t: RS2 work-turns stalled without timber (C_T - W_T) | p | 19: +87 | +87 [+87, +87] | 1 / 0 / 0 | 2/2 as extreme; means [-87, +87] |
| cw3b_h_woodcutter_turns: Woodcutter person-turns away from home, every expedition (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_h_woodcutter_turns: Woodcutter person-turns away from home, every expedition (C - W) | p | 19: +168 | +168 [+168, +168] | 1 / 0 / 0 | 2/2 as extreme; means [-168, +168] |
| cw3b_h_woodcutter_turns_t: Woodcutter person-turns away from home (C_T - W_T) | t | 5: -14 | -14 [-14, -14] | 0 / 1 / 0 | 2/2 as extreme; means [-14, +14] |
| cw3b_h_woodcutter_turns_t: Woodcutter person-turns away from home (C_T - W_T) | p | 19: +186 | +186 [+186, +186] | 1 / 0 / 0 | 2/2 as extreme; means [-186, +186] |
| cw3b_h_farm_time: Farm time removed by the works, work units (C alone) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw3b_h_farm_time: Farm time removed by the works, work units (C alone) | p | 19: +215.3 | +215.3 [+215.3, +215.3] | 1 / 0 / 0 | n/a (no control) |
| cw3b_h_coins_destroyed: Coins destroyed by the public-works sink (C alone) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw3b_h_coins_destroyed: Coins destroyed by the public-works sink (C alone) | p | 19: +133 | +133 [+133, +133] | 1 / 0 / 0 | n/a (no control) |
| cw3b_h_coins_destroyed_t: Coins destroyed by the public-works sink (C_T alone) | t | 5: +22 | +22 [+22, +22] | 1 / 0 / 0 | n/a (no control) |
| cw3b_h_coins_destroyed_t: Coins destroyed by the public-works sink (C_T alone) | p | 19: +215 | +215 [+215, +215] | 1 / 0 / 0 | n/a (no control) |
| cw3b_h_treasury: Treasury at the end (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_h_treasury: Treasury at the end (C - W) | p | 19: -1353 | -1353 [-1353, -1353] | 0 / 1 / 0 | 2/2 as extreme; means [-1353, +1353] |
| cw3b_h_stability: Mean stability of living civs at the end (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_h_stability: Mean stability of living civs at the end (C - W) | p | 19: -5.732 | -5.732 [-5.732, -5.732] | 0 / 1 / 0 | 2/2 as extreme; means [-5.732, +5.732] |
| cw3b_h_food_shortfall: Food shortfall after relief over the run, world (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_h_food_shortfall: Food shortfall after relief over the run, world (C - W) | p | 19: -515.9 | -515.9 [-515.9, -515.9] | 0 / 1 / 0 | 2/2 as extreme; means [-515.9, +515.9] |
| cw3b_h_population: Population at the end (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_h_population: Population at the end (C - W) | p | 19: -9 | -9 [-9, -9] | 0 / 1 / 0 | 2/2 as extreme; means [-9, +9] |
| cw3b_h_food_shortfall_t: Food shortfall after relief, world (C_T - W_T) | t | 5: +346.4 | +346.4 [+346.4, +346.4] | 1 / 0 / 0 | 2/2 as extreme; means [-346.4, +346.4] |
| cw3b_h_food_shortfall_t: Food shortfall after relief, world (C_T - W_T) | p | 19: +349.3 | +349.3 [+349.3, +349.3] | 1 / 0 / 0 | 2/2 as extreme; means [-349.3, +349.3] |
| cw3b_h_population_t: Population at the end (C_T - W_T) | t | 5: -17 | -17 [-17, -17] | 0 / 1 / 0 | 2/2 as extreme; means [-17, +17] |
| cw3b_h_population_t: Population at the end (C_T - W_T) | p | 19: -2 | -2 [-2, -2] | 0 / 1 / 0 | 2/2 as extreme; means [-2, +2] |
| cw3b_h_forest_stand: Timber stand share of capacity at the end (C - W) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_h_forest_stand: Timber stand share of capacity at the end (C - W) | p | 19: +0.03456 | +0.03456 [+0.03456, +0.03456] | 1 / 0 / 0 | 2/2 as extreme; means [-0.03456, +0.03456] |
| cw3b_h_record_only: Food shortfall after relief, world (R - B: the record changes nothing; structurally 0) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3b_h_record_only: Food shortfall after relief, world (R - B: the record changes nothing; structurally 0) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R - B | Population at the end (sum over civilizations) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Population at the end (sum over civilizations) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Treasury at the end (sum over civilizations) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Treasury at the end (sum over civilizations) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Food shortfall after relief over the run (food) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Food shortfall after relief over the run (food) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R - B | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R - B | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R - B | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| R - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| R - B | Deaths by epidemic (the epidemic authority) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Deaths by epidemic (the epidemic authority) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| R - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| R - B | Agents migrating between regions over the run | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Agents migrating between regions over the run | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Mean wealth Gini of living civilizations at the end | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Mean wealth Gini of living civilizations at the end | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Timber stand share of capacity at the end | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| R - B | Timber stand share of capacity at the end | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| W - R | Population at the end (sum over civilizations) | t | 5: -9 | -9 [-9, -9] | 0 / 1 / 0 | 2/2 as extreme; means [-9, +9] | recorded |
| W - R | Population at the end (sum over civilizations) | p | 19: -126 | -126 [-126, -126] | 0 / 1 / 0 | 2/2 as extreme; means [-126, +126] | recorded |
| W - R | Treasury at the end (sum over civilizations) | t | 5: -215 | -215 [-215, -215] | 0 / 1 / 0 | 2/2 as extreme; means [-215, +215] | recorded |
| W - R | Treasury at the end (sum over civilizations) | p | 19: +646 | +646 [+646, +646] | 1 / 0 / 0 | 2/2 as extreme; means [-646, +646] | recorded |
| W - R | Food shortfall after relief over the run (food) | t | 5: -243.6 | -243.6 [-243.6, -243.6] | 0 / 1 / 0 | 2/2 as extreme; means [-243.6, +243.6] | recorded |
| W - R | Food shortfall after relief over the run (food) | p | 19: +192 | +192 [+192, +192] | 1 / 0 / 0 | 2/2 as extreme; means [-192, +192] | recorded |
| W - R | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W - R | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W - R | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W - R | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W - R | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| W - R | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| W - R | Deaths by epidemic (the epidemic authority) | t | 5: +12 | +12 [+12, +12] | 1 / 0 / 0 | 2/2 as extreme; means [-12, +12] | recorded |
| W - R | Deaths by epidemic (the epidemic authority) | p | 19: +105 | +105 [+105, +105] | 1 / 0 / 0 | 2/2 as extreme; means [-105, +105] | recorded |
| W - R | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| W - R | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| W - R | Agents migrating between regions over the run | t | 5: -77 | -77 [-77, -77] | 0 / 1 / 0 | 2/2 as extreme; means [-77, +77] | recorded |
| W - R | Agents migrating between regions over the run | p | 19: +142 | +142 [+142, +142] | 1 / 0 / 0 | 2/2 as extreme; means [-142, +142] | recorded |
| W - R | Mean wealth Gini of living civilizations at the end | t | 5: +0.02018 | +0.02018 [+0.02018, +0.02018] | 1 / 0 / 0 | 2/2 as extreme; means [-0.02018, +0.02018] | recorded |
| W - R | Mean wealth Gini of living civilizations at the end | p | 19: -0.1658 | -0.1658 [-0.1658, -0.1658] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1658, +0.1658] | recorded |
| W - R | Timber stand share of capacity at the end | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| W - R | Timber stand share of capacity at the end | p | 19: -0.02751 | -0.02751 [-0.02751, -0.02751] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02751, +0.02751] | recorded |
| C - W | Population at the end (sum over civilizations) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| C - W | Population at the end (sum over civilizations) | p | 19: -9 | -9 [-9, -9] | 0 / 1 / 0 | 2/2 as extreme; means [-9, +9] | recorded |
| C - W | Treasury at the end (sum over civilizations) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| C - W | Treasury at the end (sum over civilizations) | p | 19: -1353 | -1353 [-1353, -1353] | 0 / 1 / 0 | 2/2 as extreme; means [-1353, +1353] | recorded |
| C - W | Food shortfall after relief over the run (food) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| C - W | Food shortfall after relief over the run (food) | p | 19: -515.9 | -515.9 [-515.9, -515.9] | 0 / 1 / 0 | 2/2 as extreme; means [-515.9, +515.9] | recorded |
| C - W | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C - W | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C - W | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C - W | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C - W | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C - W | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C - W | Deaths by epidemic (the epidemic authority) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| C - W | Deaths by epidemic (the epidemic authority) | p | 19: +83 | +83 [+83, +83] | 1 / 0 / 0 | 2/2 as extreme; means [-83, +83] | recorded |
| C - W | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C - W | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C - W | Agents migrating between regions over the run | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| C - W | Agents migrating between regions over the run | p | 19: +578 | +578 [+578, +578] | 1 / 0 / 0 | 2/2 as extreme; means [-578, +578] | recorded |
| C - W | Mean wealth Gini of living civilizations at the end | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| C - W | Mean wealth Gini of living civilizations at the end | p | 19: +0.1714 | +0.1714 [+0.1714, +0.1714] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1714, +0.1714] | recorded |
| C - W | Timber stand share of capacity at the end | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| C - W | Timber stand share of capacity at the end | p | 19: +0.03456 | +0.03456 [+0.03456, +0.03456] | 1 / 0 / 0 | 2/2 as extreme; means [-0.03456, +0.03456] | recorded |
| W_T - W | Population at the end (sum over civilizations) | t | 5: +30 | +30 [+30, +30] | 1 / 0 / 0 | 2/2 as extreme; means [-30, +30] | recorded |
| W_T - W | Population at the end (sum over civilizations) | p | 19: -15 | -15 [-15, -15] | 0 / 1 / 0 | 2/2 as extreme; means [-15, +15] | recorded |
| W_T - W | Treasury at the end (sum over civilizations) | t | 5: +555 | +555 [+555, +555] | 1 / 0 / 0 | 2/2 as extreme; means [-555, +555] | recorded |
| W_T - W | Treasury at the end (sum over civilizations) | p | 19: -1334 | -1334 [-1334, -1334] | 0 / 1 / 0 | 2/2 as extreme; means [-1334, +1334] | recorded |
| W_T - W | Food shortfall after relief over the run (food) | t | 5: +364 | +364 [+364, +364] | 1 / 0 / 0 | 2/2 as extreme; means [-364, +364] | recorded |
| W_T - W | Food shortfall after relief over the run (food) | p | 19: -963.5 | -963.5 [-963.5, -963.5] | 0 / 1 / 0 | 2/2 as extreme; means [-963.5, +963.5] | recorded |
| W_T - W | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W_T - W | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W_T - W | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W_T - W | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W_T - W | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| W_T - W | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| W_T - W | Deaths by epidemic (the epidemic authority) | t | 5: -58 | -58 [-58, -58] | 0 / 1 / 0 | 2/2 as extreme; means [-58, +58] | recorded |
| W_T - W | Deaths by epidemic (the epidemic authority) | p | 19: -5 | -5 [-5, -5] | 0 / 1 / 0 | 2/2 as extreme; means [-5, +5] | recorded |
| W_T - W | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| W_T - W | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| W_T - W | Agents migrating between regions over the run | t | 5: -242 | -242 [-242, -242] | 0 / 1 / 0 | 2/2 as extreme; means [-242, +242] | recorded |
| W_T - W | Agents migrating between regions over the run | p | 19: -139 | -139 [-139, -139] | 0 / 1 / 0 | 2/2 as extreme; means [-139, +139] | recorded |
| W_T - W | Mean wealth Gini of living civilizations at the end | t | 5: -0.1682 | -0.1682 [-0.1682, -0.1682] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1682, +0.1682] | recorded |
| W_T - W | Mean wealth Gini of living civilizations at the end | p | 19: +0.1576 | +0.1576 [+0.1576, +0.1576] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1576, +0.1576] | recorded |
| W_T - W | Timber stand share of capacity at the end | t | 5: -0.1141 | -0.1141 [-0.1141, -0.1141] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1141, +0.1141] | recorded |
| W_T - W | Timber stand share of capacity at the end | p | 19: +0.1349 | +0.1349 [+0.1349, +0.1349] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1349, +0.1349] | recorded |
| C_T - W_T | Population at the end (sum over civilizations) | t | 5: -17 | -17 [-17, -17] | 0 / 1 / 0 | 2/2 as extreme; means [-17, +17] | recorded |
| C_T - W_T | Population at the end (sum over civilizations) | p | 19: -2 | -2 [-2, -2] | 0 / 1 / 0 | 2/2 as extreme; means [-2, +2] | recorded |
| C_T - W_T | Treasury at the end (sum over civilizations) | t | 5: -444 | -444 [-444, -444] | 0 / 1 / 0 | 2/2 as extreme; means [-444, +444] | recorded |
| C_T - W_T | Treasury at the end (sum over civilizations) | p | 19: +1716 | +1716 [+1716, +1716] | 1 / 0 / 0 | 2/2 as extreme; means [-1716, +1716] | recorded |
| C_T - W_T | Food shortfall after relief over the run (food) | t | 5: +346.4 | +346.4 [+346.4, +346.4] | 1 / 0 / 0 | 2/2 as extreme; means [-346.4, +346.4] | recorded |
| C_T - W_T | Food shortfall after relief over the run (food) | p | 19: +349.3 | +349.3 [+349.3, +349.3] | 1 / 0 / 0 | 2/2 as extreme; means [-349.3, +349.3] | recorded |
| C_T - W_T | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C_T - W_T | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C_T - W_T | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C_T - W_T | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C_T - W_T | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C_T - W_T | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C_T - W_T | Deaths by epidemic (the epidemic authority) | t | 5: +45 | +45 [+45, +45] | 1 / 0 / 0 | 2/2 as extreme; means [-45, +45] | recorded |
| C_T - W_T | Deaths by epidemic (the epidemic authority) | p | 19: -28 | -28 [-28, -28] | 0 / 1 / 0 | 2/2 as extreme; means [-28, +28] | recorded |
| C_T - W_T | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C_T - W_T | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C_T - W_T | Agents migrating between regions over the run | t | 5: -122 | -122 [-122, -122] | 0 / 1 / 0 | 2/2 as extreme; means [-122, +122] | recorded |
| C_T - W_T | Agents migrating between regions over the run | p | 19: -94 | -94 [-94, -94] | 0 / 1 / 0 | 2/2 as extreme; means [-94, +94] | recorded |
| C_T - W_T | Mean wealth Gini of living civilizations at the end | t | 5: +0.1467 | +0.1467 [+0.1467, +0.1467] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1467, +0.1467] | recorded |
| C_T - W_T | Mean wealth Gini of living civilizations at the end | p | 19: -0.003097 | -0.003097 [-0.003097, -0.003097] | 0 / 1 / 0 | 2/2 as extreme; means [-0.003097, +0.003097] | recorded |
| C_T - W_T | Timber stand share of capacity at the end | t | 5: -0.2766 | -0.2766 [-0.2766, -0.2766] | 0 / 1 / 0 | 2/2 as extreme; means [-0.2766, +0.2766] | recorded |
| C_T - W_T | Timber stand share of capacity at the end | p | 19: -0.0085 | -0.0085 [-0.0085, -0.0085] | 0 / 1 / 0 | 2/2 as extreme; means [-0.0085, +0.0085] | recorded |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| B | 7.4 [7.4, 7.4] | 19.3 [19.3, 19.3] |
| R | 7.3 [7.3, 7.3] | 20.5 [20.5, 20.5] |
| W | 7.8 [7.8, 7.8] | 21.0 [21.0, 21.0] |
| C | 8.1 [8.1, 8.1] | 21.8 [21.8, 21.8] |
| W_T | 7.6 [7.6, 7.6] | 19.7 [19.7, 19.7] |
| C_T | 7.7 [7.7, 7.7] | 19.6 [19.6, 19.6] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
