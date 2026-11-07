# CW3b: S3 infrastructure condition and repair (B3)

Cohort held. Runs: 72; failed: 0 (missing outcomes: 0); simulation and extraction seconds 1036 (0.288 core-hours)

Identity digests: 9b5c4f4121c8ac43cff0ad3073d42395b734a31a955ee4060b0fa9195c6b58e9 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"infrastructure_condition": [1], "local_budgets": [1], "maintenance_obligation": [1], "repair_projects": [1], "timber_stock": [1], "timber_supply": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"infrastructure_condition": [1], "repair_projects": [1], "timber_stock": [1], "timber_supply": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"local_budgets": [1], "maintenance_obligation": [1], "repair_projects": [1], "timber_stock": [1], "timber_supply": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| R | t | 3501: activated; 3502: activated; 3503: activated; 3504: activated; 3505: activated; 3506: activated | 6 of 6 |
| R | p | 3601: activated; 3602: activated; 3603: activated; 3604: activated; 3605: activated; 3606: activated | 6 of 6 |
| W | t | 3501: activated; 3502: activated; 3503: activated; 3504: activated; 3505: activated; 3506: activated | 6 of 6 |
| W | p | 3601: activated; 3602: activated; 3603: activated; 3604: activated; 3605: activated; 3606: activated | 6 of 6 |
| C | t | 3501: activated; 3502: activated; 3503: activated; 3504: activated; 3505: activated; 3506: activated | 6 of 6 |
| C | p | 3601: activated; 3602: activated; 3603: activated; 3604: activated; 3605: activated; 3606: activated | 6 of 6 |
| W_T | t | 3501: activated; 3502: activated; 3503: activated; 3504: activated; 3505: activated; 3506: activated | 6 of 6 |
| W_T | p | 3601: activated; 3602: activated; 3603: activated; 3604: activated; 3605: activated; 3606: activated | 6 of 6 |
| C_T | t | 3501: activated; 3502: activated; 3503: activated; 3504: activated; 3505: activated; 3506: activated | 6 of 6 |
| C_T | p | 3601: activated; 3602: activated; 3603: activated; 3604: activated; 3605: activated; 3606: activated | 6 of 6 |

## Pre-treatment check at snapshot 28 and the irrigated-region set

| Stratum | World | Arm | Check | Set (regions; sha) |
| --- | --- | --- | --- | --- |
| t | 3501 | R | pass | 0,1,5,6,7 ; d12bb5fbbc1eefdf |
| t | 3501 | W | pass | 0,1,5,6,7 ; d12bb5fbbc1eefdf |
| t | 3501 | C | pass | 0,1,5,6,7 ; d12bb5fbbc1eefdf |
| t | 3501 | W_T | pass | 0,5,6,7 ; 0887b461daed79be |
| t | 3501 | C_T | pass | 0,5,6,7 ; 0887b461daed79be |
| t | 3502 | R | pass | 2,4,5,7 ; bb4a0e44a52d5e41 |
| t | 3502 | W | pass | 2,4,5,7 ; bb4a0e44a52d5e41 |
| t | 3502 | C | pass | 2,4,5,7 ; bb4a0e44a52d5e41 |
| t | 3502 | W_T | pass | 2,4,5,7 ; bb4a0e44a52d5e41 |
| t | 3502 | C_T | pass | 2,4,5,7 ; bb4a0e44a52d5e41 |
| t | 3503 | R | pass | 3 ; 4e07408562bedb8b |
| t | 3503 | W | pass | 3 ; 4e07408562bedb8b |
| t | 3503 | C | FAIL: works opened by turn 27: [0] | 3 ; 4e07408562bedb8b |
| t | 3503 | W_T | pass | 3,7 ; adc0d2b391a5218d |
| t | 3503 | C_T | FAIL: works opened by turn 27: [0, 1] | 3,7 ; adc0d2b391a5218d |
| t | 3504 | R | pass | 3,5,6 ; ec35495512cd6a18 |
| t | 3504 | W | pass | 3,5,6 ; ec35495512cd6a18 |
| t | 3504 | C | pass | 3,5,6 ; ec35495512cd6a18 |
| t | 3504 | W_T | pass | 3,5,6 ; ec35495512cd6a18 |
| t | 3504 | C_T | pass | 3,5,6 ; ec35495512cd6a18 |
| t | 3505 | R | pass | 4,7 ; 0d2593f5780fad83 |
| t | 3505 | W | pass | 4,7 ; 0d2593f5780fad83 |
| t | 3505 | C | pass | 4,7 ; 0d2593f5780fad83 |
| t | 3505 | W_T | pass | 4,5,7 ; 9ce2cee67f8f3004 |
| t | 3505 | C_T | pass | 4,5,7 ; 9ce2cee67f8f3004 |
| t | 3506 | R | pass | 0,4 ; d20465aa92ad20bd |
| t | 3506 | W | pass | 0,4 ; d20465aa92ad20bd |
| t | 3506 | C | FAIL: work delivered by snapshot 28: 4.0; works opened by turn 27: [0, 1] | 0,4 ; d20465aa92ad20bd |
| t | 3506 | W_T | pass | 0,7 ; 80a41b68e6da9b32 |
| t | 3506 | C_T | pass | 0,7 ; 80a41b68e6da9b32 |
| p | 3601 | R | pass | 3,4,9,11,15,18,21,28 ; 2d2162dbd3d4067c |
| p | 3601 | W | pass | 3,4,9,11,15,18,21,28 ; 2d2162dbd3d4067c |
| p | 3601 | C | pass | 3,4,9,11,15,18,21,28 ; 2d2162dbd3d4067c |
| p | 3601 | W_T | pass | 3,4,8,12,15,18,26,28 ; 54f19e87916b6283 |
| p | 3601 | C_T | pass | 3,4,8,12,15,18,26,28 ; 54f19e87916b6283 |
| p | 3602 | R | pass | 2,11 ; 5ebf82661d7f4bdf |
| p | 3602 | W | pass | 2,11 ; 5ebf82661d7f4bdf |
| p | 3602 | C | pass | 2,11 ; 5ebf82661d7f4bdf |
| p | 3602 | W_T | pass | 8,11,13,24 ; 434045a8aeb024fc |
| p | 3602 | C_T | FAIL: work delivered by snapshot 28: 3.0100708603858948; works opened by turn 27: [0, 1] | 8,11,14,24,25 ; 587bfcd72f1eddfb |
| p | 3603 | R | pass | 19,21,25,29,31 ; 0782479866b6c3f7 |
| p | 3603 | W | pass | 19,21,25,29,31 ; 0782479866b6c3f7 |
| p | 3603 | C | pass | 19,21,25,29,31 ; 0782479866b6c3f7 |
| p | 3603 | W_T | pass | 9,19,29 ; 7cbabae582dce08f |
| p | 3603 | C_T | pass | 9,19,29 ; 7cbabae582dce08f |
| p | 3604 | R | pass | 1,6,9,27,29 ; 3b67004bf01dc9cb |
| p | 3604 | W | pass | 1,6,9,27,29 ; 3b67004bf01dc9cb |
| p | 3604 | C | FAIL: works opened by turn 27: [0] | 1,6,9,27,29 ; 3b67004bf01dc9cb |
| p | 3604 | W_T | pass | 1,27,29 ; fd7eee91c1257857 |
| p | 3604 | C_T | FAIL: work delivered by snapshot 28: 5.399999618530273; works opened by turn 27: [0] | 1,27,29 ; fd7eee91c1257857 |
| p | 3605 | R | pass | 2,3,13,26 ; 40a274f46670cf82 |
| p | 3605 | W | pass | 2,3,13,26 ; 40a274f46670cf82 |
| p | 3605 | C | pass | 2,3,13,26 ; 40a274f46670cf82 |
| p | 3605 | W_T | pass | 2,3,13,26 ; 40a274f46670cf82 |
| p | 3605 | C_T | pass | 2,3,13,26 ; 40a274f46670cf82 |
| p | 3606 | R | pass | 11,15,16,17,24 ; dde9337b6c0499b3 |
| p | 3606 | W | pass | 11,15,16,17,24 ; dde9337b6c0499b3 |
| p | 3606 | C | FAIL: works opened by turn 27: [0, 1] | 11,15,16,17,24 ; dde9337b6c0499b3 |
| p | 3606 | W_T | pass | 11,15,16,19,24 ; f8452c94c6fabeda |
| p | 3606 | C_T | pass | 11,15,16,19,24 ; f8452c94c6fabeda |

| Stratum | World | Pair | Set | Primaries |
| --- | --- | --- | --- | --- |
| t | 3501 | C - W | same set | in the primaries |
| t | 3501 | C_T - W_T | same set | in the primaries |
| t | 3502 | C - W | same set | in the primaries |
| t | 3502 | C_T - W_T | same set | in the primaries |
| t | 3503 | C - W | same set | excluded from the primaries |
| t | 3503 | C_T - W_T | same set | excluded from the primaries |
| t | 3504 | C - W | same set | in the primaries |
| t | 3504 | C_T - W_T | same set | in the primaries |
| t | 3505 | C - W | same set | in the primaries |
| t | 3505 | C_T - W_T | same set | in the primaries |
| t | 3506 | C - W | same set | excluded from the primaries |
| t | 3506 | C_T - W_T | same set | in the primaries |
| p | 3601 | C - W | same set | in the primaries |
| p | 3601 | C_T - W_T | same set | in the primaries |
| p | 3602 | C - W | same set | in the primaries |
| p | 3602 | C_T - W_T | DIFFERENT SETS | excluded from the primaries |
| p | 3603 | C - W | same set | in the primaries |
| p | 3603 | C_T - W_T | same set | in the primaries |
| p | 3604 | C - W | same set | excluded from the primaries |
| p | 3604 | C_T - W_T | same set | excluded from the primaries |
| p | 3605 | C - W | same set | in the primaries |
| p | 3605 | C_T - W_T | same set | in the primaries |
| p | 3606 | C - W | same set | excluded from the primaries |
| p | 3606 | C_T - W_T | same set | in the primaries |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw3b_service_l9: Irrigation asset-turns at service >= 0.5 after snapshot 28, share (C - W: works funded only through their own L9 proposal, against none) | t | 3501: -0.001148; 3502: +0; 3503: unknown; 3504: +0.01048; 3505: +0.07164; 3506: unknown | +0.02024 [-0.001148, +0.07164] | 2 / 1 / 1 | 8/16 as extreme; means [-0.02082, +0.02082] |
| cw3b_service_l9: Irrigation asset-turns at service >= 0.5 after snapshot 28, share (C - W: works funded only through their own L9 proposal, against none) | p | 3601: +0.1429; 3602: +0.1131; 3603: +0.09809; 3604: unknown; 3605: +0.01405; 3606: unknown | +0.09202 [+0.01405, +0.1429] | 4 / 0 / 0 | 2/16 as extreme; means [-0.09202, +0.09202] |
| cw3b_food_l9: Food shortfall share after relief after snapshot 28, in the regions irrigated at snapshot 28 (C - W) | t | 3501: -0.003909; 3502: +0; 3503: unknown; 3504: -0.0022; 3505: -0.0162; 3506: unknown | -0.005578 [-0.0162, +0] | 0 / 3 / 1 | 4/16 as extreme; means [-0.005578, +0.005578] |
| cw3b_food_l9: Food shortfall share after relief after snapshot 28, in the regions irrigated at snapshot 28 (C - W) | p | 3601: -0.005851; 3602: -0.03125; 3603: -0.02312; 3604: unknown; 3605: -0.003735; 3606: unknown | -0.01599 [-0.03125, -0.003735] | 0 / 4 / 0 | 2/16 as extreme; means [-0.01599, +0.01599] |
| cw3b_service_treasury: Irrigation asset-turns at service >= 0.5 after snapshot 28, share (C_T - W_T: works funded by the treasury against none) | t | 3501: +0.1223; 3502: +0; 3503: unknown; 3504: +0.04454; 3505: +0.08947; 3506: +0.004444 | +0.05214 [+0, +0.1223] | 4 / 0 / 1 | 4/32 as extreme; means [-0.05214, +0.05214] |
| cw3b_service_treasury: Irrigation asset-turns at service >= 0.5 after snapshot 28, share (C_T - W_T: works funded by the treasury against none) | p | 3601: +0.1769; 3602: unknown; 3603: +0.1222; 3604: unknown; 3605: +0.02211; 3606: +0.1444 | +0.1164 [+0.02211, +0.1769] | 4 / 0 / 0 | 2/16 as extreme; means [-0.1164, +0.1164] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw3b_food_treasury: Food shortfall share after snapshot 28 in the irrigated regions (C_T - W_T; C_T also repairs roads, which C does not: the works' L9 proposal is irrigation-only) | t | 3501: +0.01861; 3502: +0; 3503: unknown; 3504: +0.0131; 3505: -0.01976; 3506: -0.01231 | -7.195e-05 [-0.01976, +0.01861] | 2 / 2 / 1 | 32/32 as extreme; means [-0.01276, +0.01276] |
| cw3b_food_treasury: Food shortfall share after snapshot 28 in the irrigated regions (C_T - W_T; C_T also repairs roads, which C does not: the works' L9 proposal is irrigation-only) | p | 3601: -0.007894; 3602: unknown; 3603: +0.001266; 3604: unknown; 3605: +0.01173; 3606: -0.01236 | -0.001816 [-0.01236, +0.01173] | 2 / 2 / 0 | 14/16 as extreme; means [-0.008312, +0.008312] |
| cw3b_service_l9_all: Irrigation serving share over the whole run (C - W) | t | 3501: -0.0006152; 3502: +0; 3503: +0; 3504: +0.01042; 3505: +0.0702; 3506: +0.02422 | +0.01737 [-0.0006152, +0.0702] | 3 / 1 / 2 | 16/64 as extreme; means [-0.01757, +0.01757] |
| cw3b_service_l9_all: Irrigation serving share over the whole run (C - W) | p | 3601: +0.1416; 3602: +0.1122; 3603: +0.09624; 3604: +0.1482; 3605: +0.01379; 3606: +0.01624 | +0.08803 [+0.01379, +0.1482] | 6 / 0 / 0 | 2/64 as extreme; means [-0.08803, +0.08803] |
| cw3b_food_l9_all: Food shortfall share over the whole run in the irrigated regions (C - W) | t | 3501: -0.004078; 3502: +0; 3503: +0.02498; 3504: -0.002932; 3505: -0.01299; 3506: -0.04175 | -0.006129 [-0.04175, +0.02498] | 1 / 4 / 1 | 36/64 as extreme; means [-0.01445, +0.01445] |
| cw3b_food_l9_all: Food shortfall share over the whole run in the irrigated regions (C - W) | p | 3601: -0.005079; 3602: -0.02601; 3603: -0.01935; 3604: -0.03546; 3605: -0.002773; 3606: +0.003114 | -0.01426 [-0.03546, +0.003114] | 1 / 5 / 0 | 6/64 as extreme; means [-0.0153, +0.0153] |
| cw3b_service_treasury_all: Irrigation serving share over the whole run (C_T - W_T) | t | 3501: +0.1169; 3502: +0; 3503: +0.1979; 3504: +0.04422; 3505: +0.08739; 3506: +0.00434 | +0.07512 [+0, +0.1979] | 5 / 0 / 1 | 4/64 as extreme; means [-0.07512, +0.07512] |
| cw3b_service_treasury_all: Irrigation serving share over the whole run (C_T - W_T) | p | 3601: +0.175; 3602: +0.07651; 3603: +0.1214; 3604: +0.1782; 3605: +0.02193; 3606: +0.143 | +0.1194 [+0.02193, +0.1782] | 6 / 0 / 0 | 2/64 as extreme; means [-0.1194, +0.1194] |
| cw3b_service_wear: Irrigation serving share after snapshot 28 (W - R: what wear alone costs) | t | 3501: +0.03668; 3502: +0; 3503: -0.007029; 3504: +0.000839; 3505: +0.002918; 3506: -0.007118 | +0.004381 [-0.007118, +0.03668] | 3 / 2 / 1 | 52/64 as extreme; means [-0.009097, +0.009097] |
| cw3b_service_wear: Irrigation serving share after snapshot 28 (W - R: what wear alone costs) | p | 3601: -0.03794; 3602: +0.008286; 3603: +0.0001451; 3604: -0.01755; 3605: -0.01554; 3606: +0.004122 | -0.009746 [-0.03794, +0.008286] | 3 / 3 / 0 | 16/64 as extreme; means [-0.01393, +0.01393] |
| cw3b_food_wear: Food shortfall share after snapshot 28 in the irrigated regions (W - R) | t | 3501: +0.01049; 3502: +0.01017; 3503: +0.01511; 3504: -0.005739; 3505: +0.02604; 3506: +0.02102 | +0.01285 [-0.005739, +0.02604] | 5 / 1 / 0 | 4/64 as extreme; means [-0.01476, +0.01476] |
| cw3b_food_wear: Food shortfall share after snapshot 28 in the irrigated regions (W - R) | p | 3601: +0.019; 3602: +0.02405; 3603: -0.01925; 3604: +0.03846; 3605: -0.002702; 3606: +0.02516 | +0.01412 [-0.01925, +0.03846] | 4 / 2 / 0 | 12/64 as extreme; means [-0.02144, +0.02144] |
| cw3b_food_met_l9: Demand-weighted mean of min(1, sufficiency) after snapshot 28 in the irrigated regions (C - W) | t | 3501: +0.003909; 3502: +0; 3503: -0.02799; 3504: +0.0022; 3505: +0.0162; 3506: +0.0579 | +0.008704 [-0.02799, +0.0579] | 4 / 1 / 1 | 36/64 as extreme; means [-0.01803, +0.01803] |
| cw3b_food_met_l9: Demand-weighted mean of min(1, sufficiency) after snapshot 28 in the irrigated regions (C - W) | p | 3601: +0.005851; 3602: +0.03125; 3603: +0.02312; 3604: +0.04581; 3605: +0.003735; 3606: -0.004329 | +0.01757 [-0.004329, +0.04581] | 5 / 1 / 0 | 6/64 as extreme; means [-0.01902, +0.01902] |
| cw3b_failed_l9: Assets failed over the run (C - W) | t | 3501: +0; 3502: +0; 3503: +0; 3504: +0; 3505: +0; 3506: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] |
| cw3b_failed_l9: Assets failed over the run (C - W) | p | 3601: -6; 3602: -4; 3603: -1; 3604: -4; 3605: +2; 3606: +3 | -1.667 [-6, +3] | 2 / 4 / 0 | 22/64 as extreme; means [-3.333, +3.333] |
| cw3b_failed_treasury: Assets failed over the run (C_T - W_T) | t | 3501: +10; 3502: +0; 3503: -2; 3504: +0; 3505: +0; 3506: +8 | +2.667 [-2, +10] | 2 / 1 / 3 | 32/64 as extreme; means [-3.333, +3.333] |
| cw3b_failed_treasury: Assets failed over the run (C_T - W_T) | p | 3601: +1; 3602: +0; 3603: -6; 3604: -7; 3605: +0; 3606: +6 | -1 [-7, +6] | 2 / 2 / 2 | 56/64 as extreme; means [-3.333, +3.333] |
| cw3b_works_opened: Works opened on irrigation assets (C alone) | t | 3501: +9; 3502: +7; 3503: +9; 3504: +8; 3505: +10; 3506: +8 | +8.5 [+7, +10] | 6 / 0 / 0 | n/a (no control) |
| cw3b_works_opened: Works opened on irrigation assets (C alone) | p | 3601: +42; 3602: +45; 3603: +30; 3604: +40; 3605: +30; 3606: +35 | +37 [+30, +45] | 6 / 0 / 0 | n/a (no control) |
| cw3b_works_delivered: Work the works delivered (C alone; the farm time removed) | t | 3501: +3.457; 3502: +0; 3503: +1.538; 3504: +2.518; 3505: +17.56; 3506: +9.618 | +5.782 [+0, +17.56] | 5 / 0 / 1 | n/a (no control) |
| cw3b_works_delivered: Work the works delivered (C alone; the farm time removed) | p | 3601: +140.2; 3602: +112.3; 3603: +71.53; 3604: +104.3; 3605: +1.208; 3606: +41.91 | +78.57 [+1.208, +140.2] | 6 / 0 / 0 | n/a (no control) |
| cw3b_works_delivered_t: Work the works delivered (C_T alone) | t | 3501: +39.08; 3502: +0; 3503: +80.66; 3504: +19.46; 3505: +30; 3506: +1.606 | +28.47 [+0, +80.66] | 5 / 0 / 1 | n/a (no control) |
| cw3b_works_delivered_t: Work the works delivered (C_T alone) | p | 3601: +271.6; 3602: +168.8; 3603: +241.9; 3604: +388.4; 3605: +13.46; 3606: +245.5 | +221.6 [+13.46, +388.4] | 6 / 0 / 0 | n/a (no control) |
| cw3b_works_awards: L9 awards to the works' own proposal (C alone) | t | 3501: +2; 3502: +0; 3503: +1; 3504: +2; 3505: +11; 3506: +4 | +3.333 [+0, +11] | 5 / 0 / 1 | n/a (no control) |
| cw3b_works_awards: L9 awards to the works' own proposal (C alone) | p | 3601: +56; 3602: +39; 3603: +31; 3604: +32; 3605: +2; 3606: +21 | +30.17 [+2, +56] | 6 / 0 / 0 | n/a (no control) |
| cw3b_stalled_envelope: Work-turns stalled without an envelope (C alone) | t | 3501: +1214; 3502: +1199; 3503: +1286; 3504: +980; 3505: +1022; 3506: +1126 | +1138 [+980, +1286] | 6 / 0 / 0 | n/a (no control) |
| cw3b_stalled_envelope: Work-turns stalled without an envelope (C alone) | p | 3601: +4178; 3602: +4144; 3603: +2782; 3604: +3129; 3605: +3861; 3606: +4457 | +3758 [+2782, +4457] | 6 / 0 / 0 | n/a (no control) |
| cw3b_stalled_timber: Work-turns stalled without timber (C alone) | t | 3501: +1211; 3502: +1199; 3503: +1271; 3504: +980; 3505: +988; 3506: +1050 | +1116 [+980, +1271] | 6 / 0 / 0 | n/a (no control) |
| cw3b_stalled_timber: Work-turns stalled without timber (C alone) | p | 3601: +3806; 3602: +3897; 3603: +2447; 3604: +2279; 3605: +3861; 3606: +4229 | +3420 [+2279, +4229] | 6 / 0 / 0 | n/a (no control) |
| cw3b_stalled_timber_t: Work-turns stalled without timber (C_T alone) | t | 3501: +1367; 3502: +1201; 3503: +913; 3504: +810; 3505: +925; 3506: +1316 | +1089 [+810, +1367] | 6 / 0 / 0 | n/a (no control) |
| cw3b_stalled_timber_t: Work-turns stalled without timber (C_T alone) | p | 3601: +3300; 3602: +3537; 3603: +2547; 3604: +2379; 3605: +4137; 3606: +3232 | +3189 [+2379, +4137] | 6 / 0 / 0 | n/a (no control) |
| cw3b_story: Works stalled 20+ turns on an asset that failed (C alone: the underfunded public works story) | t | 3501: +5; 3502: +7; 3503: +6; 3504: +8; 3505: +9; 3506: +6 | +6.833 [+5, +9] | 6 / 0 / 0 | n/a (no control) |
| cw3b_story: Works stalled 20+ turns on an asset that failed (C alone: the underfunded public works story) | p | 3601: +21; 3602: +16; 3603: +17; 3604: +20; 3605: +20; 3606: +29 | +20.5 [+16, +29] | 6 / 0 / 0 | n/a (no control) |
| cw3b_pl1_delivered: Timber the woodcutters delivered to the store (C alone; PL1 serves RS2's needs first, then the works') | t | 3501: +9.522; 3502: +0; 3503: +37.89; 3504: +6.537; 3505: +15.37; 3506: +5.137 | +12.41 [+0, +37.89] | 5 / 0 / 1 | n/a (no control) |
| cw3b_pl1_delivered: Timber the woodcutters delivered to the store (C alone; PL1 serves RS2's needs first, then the works') | p | 3601: +403.2; 3602: +285.9; 3603: +195.4; 3604: +259.3; 3605: +47.41; 3606: +103.3 | +215.8 [+47.41, +403.2] | 6 / 0 / 0 | n/a (no control) |
| cw3b_pl1_works_launched: Expeditions PL1 launched for the works' timber need (C alone) | t | 3501: +3; 3502: +0; 3503: +0; 3504: +3; 3505: +2; 3506: +0 | +1.333 [+0, +3] | 3 / 0 / 3 | n/a (no control) |
| cw3b_pl1_works_launched: Expeditions PL1 launched for the works' timber need (C alone) | p | 3601: +15; 3602: +14; 3603: +10; 3604: +6; 3605: +1; 3606: +5 | +8.5 [+1, +15] | 6 / 0 / 0 | n/a (no control) |
| cw3b_pl1_works_launched_t: Expeditions PL1 launched for the works' timber need (C_T alone) | t | 3501: +1; 3502: +0; 3503: +2; 3504: +0; 3505: +2; 3506: +0 | +0.8333 [+0, +2] | 3 / 0 / 3 | n/a (no control) |
| cw3b_pl1_works_launched_t: Expeditions PL1 launched for the works' timber need (C_T alone) | p | 3601: +15; 3602: +11; 3603: +12; 3604: +21; 3605: +2; 3606: +9 | +11.67 [+2, +21] | 6 / 0 / 0 | n/a (no control) |
| cw3b_pl1_works_person_turns: Woodcutter person-turns of the works' expeditions (C alone) | t | 3501: +34; 3502: +0; 3503: +0; 3504: +29; 3505: +45; 3506: +0 | +18 [+0, +45] | 3 / 0 / 3 | n/a (no control) |
| cw3b_pl1_works_person_turns: Woodcutter person-turns of the works' expeditions (C alone) | p | 3601: +194; 3602: +159; 3603: +115; 3604: +49; 3605: +12; 3606: +74 | +100.5 [+12, +194] | 6 / 0 / 0 | n/a (no control) |
| cw3b_timber_refused: The works' timber need rows PL1 refused, every reason (C alone) | t | 3501: +507; 3502: +627; 3503: +547; 3504: +479; 3505: +497; 3506: +528 | +530.8 [+479, +627] | 6 / 0 / 0 | n/a (no control) |
| cw3b_timber_refused: The works' timber need rows PL1 refused, every reason (C alone) | p | 3601: +1325; 3602: +1525; 3603: +912; 3604: +500; 3605: +1871; 3606: +1974 | +1351 [+500, +1974] | 6 / 0 / 0 | n/a (no control) |
| cw3b_h_rs2_displaced: RS2 repair work delivered (C - W: the L9 envelope displacement) | t | 3501: -42.72; 3502: +0; 3503: -27.79; 3504: +0; 3505: -8.851; 3506: -14.49 | -15.64 [-42.72, +0] | 0 / 4 / 2 | 8/64 as extreme; means [-15.64, +15.64] |
| cw3b_h_rs2_displaced: RS2 repair work delivered (C - W: the L9 envelope displacement) | p | 3601: -91.91; 3602: -74.5; 3603: -178; 3604: +55.67; 3605: -0.1367; 3606: -116.2 | -67.51 [-178, +55.67] | 1 / 5 / 0 | 6/64 as extreme; means [-86.07, +86.07] |
| cw3b_h_rs2_displaced_t: RS2 repair work delivered (C_T - W_T) | t | 3501: +20.62; 3502: +0; 3503: +71.01; 3504: +1.857; 3505: +2.071; 3506: +26.07 | +20.27 [+0, +71.01] | 5 / 0 / 1 | 4/64 as extreme; means [-20.27, +20.27] |
| cw3b_h_rs2_displaced_t: RS2 repair work delivered (C_T - W_T) | p | 3601: -30.32; 3602: -9.912; 3603: -58.96; 3604: +138.6; 3605: -0.1596; 3606: -61.53 | -3.715 [-61.53, +138.6] | 1 / 5 / 0 | 58/64 as extreme; means [-49.91, +49.91] |
| cw3b_h_rs2_timber: RS2 work-turns stalled without timber (C - W: woodcutters and forests the works' expeditions took from RS2's later needs) | t | 3501: -100; 3502: +0; 3503: -5; 3504: +0; 3505: -38; 3506: +16 | -21.17 [-100, +16] | 1 / 3 / 2 | 24/64 as extreme; means [-26.5, +26.5] |
| cw3b_h_rs2_timber: RS2 work-turns stalled without timber (C - W: woodcutters and forests the works' expeditions took from RS2's later needs) | p | 3601: +259; 3602: -78; 3603: +49; 3604: -47; 3605: +19; 3606: -86 | +19.33 [-86, +259] | 3 / 3 / 0 | 54/64 as extreme; means [-89.67, +89.67] |
| cw3b_h_rs2_timber_t: RS2 work-turns stalled without timber (C_T - W_T) | t | 3501: +33; 3502: +0; 3503: -134; 3504: -16; 3505: -39; 3506: +6 | -25 [-134, +33] | 2 / 3 / 1 | 28/64 as extreme; means [-38, +38] |
| cw3b_h_rs2_timber_t: RS2 work-turns stalled without timber (C_T - W_T) | p | 3601: +162; 3602: +42; 3603: +87; 3604: -211; 3605: +42; 3606: +4 | +21 [-211, +162] | 5 / 1 / 0 | 46/64 as extreme; means [-91.33, +91.33] |
| cw3b_h_woodcutter_turns: Woodcutter person-turns away from home, every expedition (C - W) | t | 3501: +59; 3502: +0; 3503: +0; 3504: +29; 3505: +16; 3506: +92 | +32.67 [+0, +92] | 4 / 0 / 2 | 8/64 as extreme; means [-32.67, +32.67] |
| cw3b_h_woodcutter_turns: Woodcutter person-turns away from home, every expedition (C - W) | p | 3601: +202; 3602: -40; 3603: -212; 3604: -61; 3605: -11; 3606: -284 | -67.67 [-284, +202] | 1 / 5 / 0 | 18/64 as extreme; means [-135, +135] |
| cw3b_h_woodcutter_turns_t: Woodcutter person-turns away from home (C_T - W_T) | t | 3501: +10; 3502: +0; 3503: +66; 3504: +0; 3505: +12; 3506: +0 | +14.67 [+0, +66] | 3 / 0 / 3 | 16/64 as extreme; means [-14.67, +14.67] |
| cw3b_h_woodcutter_turns_t: Woodcutter person-turns away from home (C_T - W_T) | p | 3601: +121; 3602: +171; 3603: +260; 3604: +410; 3605: +30; 3606: +88 | +180 [+30, +410] | 6 / 0 / 0 | 2/64 as extreme; means [-180, +180] |
| cw3b_h_farm_time: Farm time removed by the works, work units (C alone) | t | 3501: +3.457; 3502: +0; 3503: +1.538; 3504: +2.518; 3505: +17.56; 3506: +9.618 | +5.782 [+0, +17.56] | 5 / 0 / 1 | n/a (no control) |
| cw3b_h_farm_time: Farm time removed by the works, work units (C alone) | p | 3601: +140.2; 3602: +112.3; 3603: +71.53; 3604: +104.3; 3605: +1.208; 3606: +41.91 | +78.57 [+1.208, +140.2] | 6 / 0 / 0 | n/a (no control) |
| cw3b_h_coins_destroyed: Coins destroyed by the public-works sink (C alone) | t | 3501: +3; 3502: +0; 3503: +1; 3504: +2; 3505: +11; 3506: +6 | +3.833 [+0, +11] | 5 / 0 / 1 | n/a (no control) |
| cw3b_h_coins_destroyed: Coins destroyed by the public-works sink (C alone) | p | 3601: +88; 3602: +70; 3603: +46; 3604: +67; 3605: +1; 3606: +30 | +50.33 [+1, +88] | 6 / 0 / 0 | n/a (no control) |
| cw3b_h_coins_destroyed_t: Coins destroyed by the public-works sink (C_T alone) | t | 3501: +24; 3502: +0; 3503: +46; 3504: +11; 3505: +18; 3506: +3 | +17 [+0, +46] | 5 / 0 / 1 | n/a (no control) |
| cw3b_h_coins_destroyed_t: Coins destroyed by the public-works sink (C_T alone) | p | 3601: +158; 3602: +101; 3603: +139; 3604: +224; 3605: +9; 3606: +145 | +129.3 [+9, +224] | 6 / 0 / 0 | n/a (no control) |
| cw3b_h_treasury: Treasury at the end (C - W) | t | 3501: +251; 3502: +0; 3503: +10; 3504: -145; 3505: -253; 3506: +362 | +37.5 [-253, +362] | 3 / 2 / 1 | 48/64 as extreme; means [-170.2, +170.2] |
| cw3b_h_treasury: Treasury at the end (C - W) | p | 3601: +1898; 3602: -3317; 3603: -2905; 3604: -302; 3605: -1702; 3606: -1923 | -1375 [-3317, +1898] | 1 / 5 / 0 | 8/64 as extreme; means [-2008, +2008] |
| cw3b_h_stability: Mean stability of living civs at the end (C - W) | t | 3501: -9; 3502: +0; 3503: -4; 3504: +3; 3505: -17; 3506: +6.417 | -3.431 [-17, +6.417] | 2 / 3 / 1 | 28/64 as extreme; means [-6.569, +6.569] |
| cw3b_h_stability: Mean stability of living civs at the end (C - W) | p | 3601: -10.1; 3602: +6; 3603: +3.617; 3604: +6.194; 3605: -9; 3606: +1.697 | -0.2653 [-10.1, +6.194] | 4 / 2 / 0 | 60/64 as extreme; means [-6.101, +6.101] |
| cw3b_h_food_shortfall: Food shortfall after relief over the run, world (C - W) | t | 3501: -186.5; 3502: +0; 3503: +30.97; 3504: +157.6; 3505: -414.7; 3506: +33.72 | -63.14 [-414.7, +157.6] | 3 / 2 / 1 | 44/64 as extreme; means [-137.2, +137.2] |
| cw3b_h_food_shortfall: Food shortfall after relief over the run, world (C - W) | p | 3601: -704; 3602: -2032; 3603: -503.1; 3604: -4.317; 3605: +227.2; 3606: -913.2 | -654.9 [-2032, +227.2] | 1 / 5 / 0 | 6/64 as extreme; means [-730.6, +730.6] |
| cw3b_h_population: Population at the end (C - W) | t | 3501: -6; 3502: +0; 3503: -15; 3504: -3; 3505: -12; 3506: -20 | -9.333 [-20, +0] | 0 / 5 / 1 | 4/64 as extreme; means [-9.333, +9.333] |
| cw3b_h_population: Population at the end (C - W) | p | 3601: +66; 3602: -27; 3603: +14; 3604: +35; 3605: +38; 3606: -175 | -8.167 [-175, +66] | 4 / 2 / 0 | 60/64 as extreme; means [-59.17, +59.17] |
| cw3b_h_food_shortfall_t: Food shortfall after relief, world (C_T - W_T) | t | 3501: +504.1; 3502: +0; 3503: +154.8; 3504: +222.7; 3505: -494.8; 3506: +126.1 | +85.48 [-494.8, +504.1] | 4 / 1 / 1 | 32/64 as extreme; means [-250.4, +250.4] |
| cw3b_h_food_shortfall_t: Food shortfall after relief, world (C_T - W_T) | p | 3601: +448.1; 3602: +566.4; 3603: -344.7; 3604: -412.5; 3605: +20.6; 3606: -1201 | -153.9 [-1201, +566.4] | 3 / 3 / 0 | 44/64 as extreme; means [-498.9, +498.9] |
| cw3b_h_population_t: Population at the end (C_T - W_T) | t | 3501: +28; 3502: +0; 3503: +33; 3504: +2; 3505: -10; 3506: +39 | +15.33 [-10, +39] | 4 / 1 / 1 | 12/64 as extreme; means [-18.67, +18.67] |
| cw3b_h_population_t: Population at the end (C_T - W_T) | p | 3601: +37; 3602: +27; 3603: -5; 3604: -3; 3605: +42; 3606: +26 | +20.67 [-5, +42] | 4 / 2 / 0 | 8/64 as extreme; means [-23.33, +23.33] |
| cw3b_h_forest_stand: Timber stand share of capacity at the end (C - W) | t | 3501: +0.1974; 3502: unknown; 3503: +0.04143; 3504: +0; 3505: -0.0382; 3506: +0.1301 | +0.06615 [-0.0382, +0.1974] | 3 / 1 / 1 | 8/32 as extreme; means [-0.08143, +0.08143] |
| cw3b_h_forest_stand: Timber stand share of capacity at the end (C - W) | p | 3601: +0.2175; 3602: +0.03149; 3603: +0.009463; 3604: +0.09426; 3605: +0.007529; 3606: +0.1334 | +0.08228 [+0.007529, +0.2175] | 6 / 0 / 0 | 2/64 as extreme; means [-0.08228, +0.08228] |
| cw3b_h_record_only: Food shortfall after relief, world (R - B: the record changes nothing; structurally 0) | t | 3501: +0; 3502: +0; 3503: +0; 3504: +0; 3505: +0; 3506: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] |
| cw3b_h_record_only: Food shortfall after relief, world (R - B: the record changes nothing; structurally 0) | p | 3601: +0; 3602: +0; 3603: +0; 3604: +0; 3605: +0; 3606: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R - B | Population at the end (sum over civilizations) | t | 3501: +0; 3502: +0; 3503: +0; 3504: +0; 3505: +0; 3506: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Population at the end (sum over civilizations) | p | 3601: +0; 3602: +0; 3603: +0; 3604: +0; 3605: +0; 3606: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Treasury at the end (sum over civilizations) | t | 3501: +0; 3502: +0; 3503: +0; 3504: +0; 3505: +0; 3506: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Treasury at the end (sum over civilizations) | p | 3601: +0; 3602: +0; 3603: +0; 3604: +0; 3605: +0; 3606: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Food shortfall after relief over the run (food) | t | 3501: +0; 3502: +0; 3503: +0; 3504: +0; 3505: +0; 3506: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Food shortfall after relief over the run (food) | p | 3601: +0; 3602: +0; 3603: +0; 3604: +0; 3605: +0; 3606: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Priced-out person-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R - B | Priced-out person-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R - B | Priced-out child-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R - B | Priced-out child-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| R - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| R - B | Deaths by epidemic (the epidemic authority) | t | 3501: +0; 3502: +0; 3503: +0; 3504: +0; 3505: +0; 3506: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Deaths by epidemic (the epidemic authority) | p | 3601: +0; 3602: +0; 3603: +0; 3604: +0; 3605: +0; 3606: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| R - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| R - B | Agents migrating between regions over the run | t | 3501: +0; 3502: +0; 3503: +0; 3504: +0; 3505: +0; 3506: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Agents migrating between regions over the run | p | 3601: +0; 3602: +0; 3603: +0; 3604: +0; 3605: +0; 3606: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Mean wealth Gini of living civilizations at the end | t | 3501: +0; 3502: +0; 3503: +0; 3504: +0; 3505: +0; 3506: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Mean wealth Gini of living civilizations at the end | p | 3601: +0; 3602: +0; 3603: +0; 3604: +0; 3605: +0; 3606: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| R - B | Timber stand share of capacity at the end | t | 3501: +0; 3502: not recorded; 3503: +0; 3504: +0; 3505: +0; 3506: +0 | +0 [+0, +0] | 0 / 0 / 5 | 32/32 as extreme; means [+0, +0] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| R - B | Timber stand share of capacity at the end | p | 3601: +0; 3602: +0; 3603: +0; 3604: +0; 3605: +0; 3606: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] | recorded |
| W - R | Population at the end (sum over civilizations) | t | 3501: +23; 3502: -5; 3503: -37; 3504: -6; 3505: -19; 3506: +34 | -1.667 [-37, +34] | 2 / 4 / 0 | 54/64 as extreme; means [-20.67, +20.67] | recorded |
| W - R | Population at the end (sum over civilizations) | p | 3601: -63; 3602: -106; 3603: -103; 3604: -79; 3605: -35; 3606: -84 | -78.33 [-106, -35] | 0 / 6 / 0 | 2/64 as extreme; means [-78.33, +78.33] | recorded |
| W - R | Treasury at the end (sum over civilizations) | t | 3501: +560; 3502: -4; 3503: -538; 3504: +208; 3505: +459; 3506: +951 | +272.7 [-538, +951] | 4 / 2 / 0 | 16/64 as extreme; means [-453.3, +453.3] | recorded |
| W - R | Treasury at the end (sum over civilizations) | p | 3601: -1507; 3602: -446; 3603: +1681; 3604: -721; 3605: +1220; 3606: -1101 | -145.7 [-1507, +1681] | 2 / 4 / 0 | 52/64 as extreme; means [-1113, +1113] | recorded |
| W - R | Food shortfall after relief over the run (food) | t | 3501: +56.42; 3502: +87.43; 3503: -445.6; 3504: -41.4; 3505: +441.7; 3506: +273.4 | +61.99 [-445.6, +441.7] | 4 / 2 / 0 | 40/64 as extreme; means [-224.3, +224.3] | recorded |
| W - R | Food shortfall after relief over the run (food) | p | 3601: +863.2; 3602: +538.3; 3603: -519.1; 3604: +101.2; 3605: +146.4; 3606: +736.1 | +311 [-519.1, +863.2] | 5 / 1 / 0 | 10/64 as extreme; means [-484.1, +484.1] | recorded |
| W - R | Priced-out person-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W - R | Priced-out person-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W - R | Priced-out child-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W - R | Priced-out child-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W - R | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| W - R | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| W - R | Deaths by epidemic (the epidemic authority) | t | 3501: -7; 3502: -16; 3503: -9; 3504: -6; 3505: +6; 3506: -33 | -10.83 [-33, +6] | 1 / 5 / 0 | 6/64 as extreme; means [-12.83, +12.83] | recorded |
| W - R | Deaths by epidemic (the epidemic authority) | p | 3601: -39; 3602: +58; 3603: +33; 3604: +59; 3605: +49; 3606: +77 | +39.5 [-39, +77] | 5 / 1 / 0 | 6/64 as extreme; means [-52.5, +52.5] | recorded |
| W - R | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| W - R | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| W - R | Agents migrating between regions over the run | t | 3501: -212; 3502: -54; 3503: -390; 3504: -99; 3505: -7; 3506: +348 | -69 [-390, +348] | 1 / 5 / 0 | 30/64 as extreme; means [-185, +185] | recorded |
| W - R | Agents migrating between regions over the run | p | 3601: +108; 3602: -126; 3603: -1155; 3604: -139; 3605: -501; 3606: +502 | -218.5 [-1155, +502] | 2 / 4 / 0 | 24/64 as extreme; means [-421.8, +421.8] | recorded |
| W - R | Mean wealth Gini of living civilizations at the end | t | 3501: +0.08924; 3502: -0.02232; 3503: -0.01226; 3504: -0.008763; 3505: +0.16; 3506: -0.03805 | +0.02797 [-0.03805, +0.16] | 2 / 4 / 0 | 32/64 as extreme; means [-0.0551, +0.0551] | recorded |
| W - R | Mean wealth Gini of living civilizations at the end | p | 3601: +0.009045; 3602: -0.006575; 3603: +0.04146; 3604: +0.04218; 3605: -0.01363; 3606: -0.07381 | -0.0002215 [-0.07381, +0.04218] | 3 / 3 / 0 | 64/64 as extreme; means [-0.03112, +0.03112] | recorded |
| W - R | Timber stand share of capacity at the end | t | 3501: -0.07046; 3502: not recorded; 3503: -0.05658; 3504: +0; 3505: +0.03746; 3506: -0.1097 | -0.03986 [-0.1097, +0.03746] | 1 / 3 / 1 | 8/32 as extreme; means [-0.05485, +0.05485] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| W - R | Timber stand share of capacity at the end | p | 3601: -0.1389; 3602: +0.03965; 3603: +0.1291; 3604: -0.0756; 3605: -0.007529; 3606: -0.231 | -0.04739 [-0.231, +0.1291] | 2 / 4 / 0 | 26/64 as extreme; means [-0.1036, +0.1036] | recorded |
| C - W | Population at the end (sum over civilizations) | t | 3501: -6; 3502: +0; 3503: -15; 3504: -3; 3505: -12; 3506: -20 | -9.333 [-20, +0] | 0 / 5 / 1 | 4/64 as extreme; means [-9.333, +9.333] | recorded |
| C - W | Population at the end (sum over civilizations) | p | 3601: +66; 3602: -27; 3603: +14; 3604: +35; 3605: +38; 3606: -175 | -8.167 [-175, +66] | 4 / 2 / 0 | 60/64 as extreme; means [-59.17, +59.17] | recorded |
| C - W | Treasury at the end (sum over civilizations) | t | 3501: +251; 3502: +0; 3503: +10; 3504: -145; 3505: -253; 3506: +362 | +37.5 [-253, +362] | 3 / 2 / 1 | 48/64 as extreme; means [-170.2, +170.2] | recorded |
| C - W | Treasury at the end (sum over civilizations) | p | 3601: +1898; 3602: -3317; 3603: -2905; 3604: -302; 3605: -1702; 3606: -1923 | -1375 [-3317, +1898] | 1 / 5 / 0 | 8/64 as extreme; means [-2008, +2008] | recorded |
| C - W | Food shortfall after relief over the run (food) | t | 3501: -186.5; 3502: +0; 3503: +30.97; 3504: +157.6; 3505: -414.7; 3506: +33.72 | -63.14 [-414.7, +157.6] | 3 / 2 / 1 | 44/64 as extreme; means [-137.2, +137.2] | recorded |
| C - W | Food shortfall after relief over the run (food) | p | 3601: -704; 3602: -2032; 3603: -503.1; 3604: -4.317; 3605: +227.2; 3606: -913.2 | -654.9 [-2032, +227.2] | 1 / 5 / 0 | 6/64 as extreme; means [-730.6, +730.6] | recorded |
| C - W | Priced-out person-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C - W | Priced-out person-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C - W | Priced-out child-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C - W | Priced-out child-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C - W | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C - W | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C - W | Deaths by epidemic (the epidemic authority) | t | 3501: -82; 3502: +0; 3503: +25; 3504: +4; 3505: -36; 3506: +14 | -12.5 [-82, +25] | 3 / 2 / 1 | 40/64 as extreme; means [-26.83, +26.83] | recorded |
| C - W | Deaths by epidemic (the epidemic authority) | p | 3601: -39; 3602: +360; 3603: +62; 3604: -175; 3605: -27; 3606: +112 | +48.83 [-175, +360] | 3 / 3 / 0 | 42/64 as extreme; means [-129.2, +129.2] | recorded |
| C - W | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C - W | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C - W | Agents migrating between regions over the run | t | 3501: -218; 3502: +0; 3503: +113; 3504: +98; 3505: -159; 3506: -11 | -29.5 [-218, +113] | 2 / 3 / 1 | 36/64 as extreme; means [-99.83, +99.83] | recorded |
| C - W | Agents migrating between regions over the run | p | 3601: -99; 3602: -711; 3603: +512; 3604: -291; 3605: +525; 3606: -1124 | -198 [-1124, +525] | 2 / 4 / 0 | 32/64 as extreme; means [-543.7, +543.7] | recorded |
| C - W | Mean wealth Gini of living civilizations at the end | t | 3501: -0.1764; 3502: +0; 3503: -0.02021; 3504: +0.01682; 3505: -0.1965; 3506: +0.02118 | -0.05918 [-0.1965, +0.02118] | 2 / 3 / 1 | 24/64 as extreme; means [-0.07185, +0.07185] | recorded |
| C - W | Mean wealth Gini of living civilizations at the end | p | 3601: -0.004239; 3602: +0.01588; 3603: +0.06393; 3604: +0.07266; 3605: +0.005431; 3606: -0.09202 | +0.01027 [-0.09202, +0.07266] | 4 / 2 / 0 | 50/64 as extreme; means [-0.04236, +0.04236] | recorded |
| C - W | Timber stand share of capacity at the end | t | 3501: +0.1974; 3502: not recorded; 3503: +0.04143; 3504: +0; 3505: -0.0382; 3506: +0.1301 | +0.06615 [-0.0382, +0.1974] | 3 / 1 / 1 | 8/32 as extreme; means [-0.08143, +0.08143] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| C - W | Timber stand share of capacity at the end | p | 3601: +0.2175; 3602: +0.03149; 3603: +0.009463; 3604: +0.09426; 3605: +0.007529; 3606: +0.1334 | +0.08228 [+0.007529, +0.2175] | 6 / 0 / 0 | 2/64 as extreme; means [-0.08228, +0.08228] | recorded |
| W_T - W | Population at the end (sum over civilizations) | t | 3501: -16; 3502: -18; 3503: -15; 3504: +21; 3505: -13; 3506: -115 | -26 [-115, +21] | 1 / 5 / 0 | 12/64 as extreme; means [-33, +33] | recorded |
| W_T - W | Population at the end (sum over civilizations) | p | 3601: -49; 3602: -176; 3603: +49; 3604: +79; 3605: -12; 3606: -137 | -41 [-176, +79] | 2 / 4 / 0 | 24/64 as extreme; means [-83.67, +83.67] | recorded |
| W_T - W | Treasury at the end (sum over civilizations) | t | 3501: +316; 3502: -304; 3503: -41; 3504: -676; 3505: -1090; 3506: -1811 | -601 [-1811, +316] | 1 / 5 / 0 | 8/64 as extreme; means [-706.3, +706.3] | recorded |
| W_T - W | Treasury at the end (sum over civilizations) | p | 3601: +846; 3602: -38; 3603: +666; 3604: +1951; 3605: -2007; 3606: -522 | +149.3 [-2007, +1951] | 3 / 3 / 0 | 48/64 as extreme; means [-1005, +1005] | recorded |
| W_T - W | Food shortfall after relief over the run (food) | t | 3501: +37.17; 3502: -223.7; 3503: -801.3; 3504: -417.3; 3505: -577.1; 3506: -835.7 | -469.7 [-835.7, +37.17] | 1 / 5 / 0 | 4/64 as extreme; means [-482, +482] | recorded |
| W_T - W | Food shortfall after relief over the run (food) | p | 3601: -603.3; 3602: -1901; 3603: -839.2; 3604: +607.5; 3605: +239.8; 3606: -1537 | -672.2 [-1901, +607.5] | 2 / 4 / 0 | 14/64 as extreme; means [-954.7, +954.7] | recorded |
| W_T - W | Priced-out person-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W_T - W | Priced-out person-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W_T - W | Priced-out child-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W_T - W | Priced-out child-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| W_T - W | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| W_T - W | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| W_T - W | Deaths by epidemic (the epidemic authority) | t | 3501: -245; 3502: +7; 3503: -9; 3504: -40; 3505: -59; 3506: -83 | -71.5 [-245, +7] | 1 / 5 / 0 | 4/64 as extreme; means [-73.83, +73.83] | recorded |
| W_T - W | Deaths by epidemic (the epidemic authority) | p | 3601: -136; 3602: +281; 3603: +271; 3604: +27; 3605: -42; 3606: -51 | +58.33 [-136, +281] | 3 / 3 / 0 | 30/64 as extreme; means [-134.7, +134.7] | recorded |
| W_T - W | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| W_T - W | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| W_T - W | Agents migrating between regions over the run | t | 3501: -529; 3502: -177; 3503: -403; 3504: -241; 3505: -170; 3506: -592 | -352 [-592, -170] | 0 / 6 / 0 | 2/64 as extreme; means [-352, +352] | recorded |
| W_T - W | Agents migrating between regions over the run | p | 3601: -825; 3602: -651; 3603: +653; 3604: +1364; 3605: +373; 3606: -2280 | -227.7 [-2280, +1364] | 3 / 3 / 0 | 46/64 as extreme; means [-1024, +1024] | recorded |
| W_T - W | Mean wealth Gini of living civilizations at the end | t | 3501: -0.08898; 3502: +0.01948; 3503: +0.1436; 3504: -0.07953; 3505: -0.1841; 3506: -0.02137 | -0.03515 [-0.1841, +0.1436] | 2 / 4 / 0 | 28/64 as extreme; means [-0.08952, +0.08952] | recorded |
| W_T - W | Mean wealth Gini of living civilizations at the end | p | 3601: -0.06772; 3602: -0.1175; 3603: +0.0905; 3604: +0.08507; 3605: -0.002318; 3606: +0.05508 | +0.007178 [-0.1175, +0.0905] | 3 / 3 / 0 | 56/64 as extreme; means [-0.06971, +0.06971] | recorded |
| W_T - W | Timber stand share of capacity at the end | t | 3501: -0.05572; 3502: not recorded; 3503: +0.05874; 3504: +0; 3505: -0.03826; 3506: +0.1091 | +0.01477 [-0.05572, +0.1091] | 2 / 2 / 1 | 20/32 as extreme; means [-0.05237, +0.05237] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| W_T - W | Timber stand share of capacity at the end | p | 3601: +0.07399; 3602: -0.2491; 3603: +0.01658; 3604: -0.009971; 3605: -0.1225; 3606: +0.2156 | -0.01258 [-0.2491, +0.2156] | 3 / 3 / 0 | 54/64 as extreme; means [-0.1146, +0.1146] | recorded |
| C_T - W_T | Population at the end (sum over civilizations) | t | 3501: +28; 3502: +0; 3503: +33; 3504: +2; 3505: -10; 3506: +39 | +15.33 [-10, +39] | 4 / 1 / 1 | 12/64 as extreme; means [-18.67, +18.67] | recorded |
| C_T - W_T | Population at the end (sum over civilizations) | p | 3601: +37; 3602: +27; 3603: -5; 3604: -3; 3605: +42; 3606: +26 | +20.67 [-5, +42] | 4 / 2 / 0 | 8/64 as extreme; means [-23.33, +23.33] | recorded |
| C_T - W_T | Treasury at the end (sum over civilizations) | t | 3501: -239; 3502: +0; 3503: -248; 3504: +505; 3505: +281; 3506: +241 | +90 [-248, +505] | 3 / 2 / 1 | 28/64 as extreme; means [-252.3, +252.3] | recorded |
| C_T - W_T | Treasury at the end (sum over civilizations) | p | 3601: +1114; 3602: -3409; 3603: -1934; 3604: -1433; 3605: +1388; 3606: +227 | -674.5 [-3409, +1388] | 3 / 3 / 0 | 26/64 as extreme; means [-1584, +1584] | recorded |
| C_T - W_T | Food shortfall after relief over the run (food) | t | 3501: +504.1; 3502: +0; 3503: +154.8; 3504: +222.7; 3505: -494.8; 3506: +126.1 | +85.48 [-494.8, +504.1] | 4 / 1 / 1 | 32/64 as extreme; means [-250.4, +250.4] | recorded |
| C_T - W_T | Food shortfall after relief over the run (food) | p | 3601: +448.1; 3602: +566.4; 3603: -344.7; 3604: -412.5; 3605: +20.6; 3606: -1201 | -153.9 [-1201, +566.4] | 3 / 3 / 0 | 44/64 as extreme; means [-498.9, +498.9] | recorded |
| C_T - W_T | Priced-out person-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C_T - W_T | Priced-out person-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C_T - W_T | Priced-out child-turns | t | 3501: not recorded; 3502: not recorded; 3503: not recorded; 3504: not recorded; 3505: not recorded; 3506: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C_T - W_T | Priced-out child-turns | p | 3601: not recorded; 3602: not recorded; 3603: not recorded; 3604: not recorded; 3605: not recorded; 3606: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| C_T - W_T | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C_T - W_T | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C_T - W_T | Deaths by epidemic (the epidemic authority) | t | 3501: +24; 3502: +0; 3503: +17; 3504: +4; 3505: -3; 3506: -4 | +6.333 [-4, +24] | 3 / 2 / 1 | 24/64 as extreme; means [-8.667, +8.667] | recorded |
| C_T - W_T | Deaths by epidemic (the epidemic authority) | p | 3601: +169; 3602: -67; 3603: +16; 3604: -7; 3605: -50; 3606: -43 | +3 [-67, +169] | 2 / 4 / 0 | 60/64 as extreme; means [-58.67, +58.67] | recorded |
| C_T - W_T | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C_T - W_T | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C_T - W_T | Agents migrating between regions over the run | t | 3501: +252; 3502: +0; 3503: +345; 3504: -60; 3505: -116; 3506: -164 | +42.83 [-164, +345] | 2 / 3 / 1 | 40/64 as extreme; means [-156.2, +156.2] | recorded |
| C_T - W_T | Agents migrating between regions over the run | p | 3601: +1190; 3602: -1155; 3603: +226; 3604: -1438; 3605: -111; 3606: -210 | -249.7 [-1438, +1190] | 2 / 4 / 0 | 32/64 as extreme; means [-721.7, +721.7] | recorded |
| C_T - W_T | Mean wealth Gini of living civilizations at the end | t | 3501: +0.085; 3502: +0; 3503: -0.2716; 3504: +0.09687; 3505: -0.01451; 3506: +0.04271 | -0.01026 [-0.2716, +0.09687] | 3 / 2 / 1 | 60/64 as extreme; means [-0.08512, +0.08512] | recorded |
| C_T - W_T | Mean wealth Gini of living civilizations at the end | p | 3601: -0.0773; 3602: +0.07081; 3603: +0.005582; 3604: +0.1277; 3605: +0.000674; 3606: -0.008281 | +0.01987 [-0.0773, +0.1277] | 4 / 2 / 0 | 42/64 as extreme; means [-0.0484, +0.0484] | recorded |
| C_T - W_T | Timber stand share of capacity at the end | t | 3501: +0.1053; 3502: not recorded; 3503: not recorded; 3504: +0; 3505: +0.0001929; 3506: -0.05455 | +0.01274 [-0.05455, +0.1053] | 2 / 1 / 1 | 12/16 as extreme; means [-0.04002, +0.04002] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| C_T - W_T | Timber stand share of capacity at the end | p | 3601: +0.1451; 3602: +0.09893; 3603: +0.05948; 3604: +0.005895; 3605: +0.113; 3606: +0.01995 | +0.07372 [+0.005895, +0.1451] | 6 / 0 / 0 | 2/64 as extreme; means [-0.07372, +0.07372] | recorded |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| B | 7.8 [7.2, 9.1] | 19.9 [17.3, 22.4] |
| R | 8.3 [7.7, 8.8] | 20.4 [17.3, 23.5] |
| W | 8.2 [7.7, 9.0] | 20.3 [17.3, 21.9] |
| C | 8.8 [7.9, 9.3] | 22.1 [19.4, 23.5] |
| W_T | 7.9 [7.3, 8.8] | 19.9 [17.3, 22.2] |
| C_T | 8.1 [7.4, 9.1] | 21.0 [18.5, 21.9] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
