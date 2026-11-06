# CW1: S1 accounting and wages (A1-A2): the wage and paid_work enrollment

Cohort pilot. Runs: 18; failed: 0 (missing outcomes: 0); simulation and extraction seconds 333 (0.092 core-hours)
Projected held run time from this pilot: 0.555 core-hours (x1.5 = 0.833) for 108 runs

Identity digests: dd296c16d86cd77e9ce7c9ae9a0cc785254bbba18b11d30f6209ad979713106a (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"food_allocation": [1], "household_retail": [1], "operating_wear": [1], "recovery_crews": [1], "remittances": [1], "repair_projects": [1], "timber_stock": [1], "timber_supply": [1], "wealth_accounting": [1], "workshops": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"food_allocation": [1], "household_retail": [1], "operating_wear": [1], "recovery_crews": [1], "remittances": [1], "repair_projects": [1], "timber_stock": [1], "wealth_accounting": [1], "workshops": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| A | t | 5: activated | 1 of 1 |
| A | p | 19: activated | 1 of 1 |
| C | t | 5: activated | 1 of 1 |
| C | p | 19: activated | 1 of 1 |
| D | t | 5: activated | 1 of 1 |
| D | p | 19: activated | 1 of 1 |
| E | t | 5: activated | 1 of 1 |
| E | p | 19: activated | 1 of 1 |
| F | t | 5: activated | 1 of 1 |
| F | p | 19: activated | 1 of 1 |
| G | t | 5: activated | 1 of 1 |
| G | p | 19: activated | 1 of 1 |
| H | t | 5: activated | 1 of 1 |
| H | p | 19: activated | 1 of 1 |
| CH_noTS | t | 5: activated | 1 of 1 |
| CH_noTS | p | 19: activated | 1 of 1 |

## CW1 validity per world (enrollment, wages, schedules; before any effect)

| World | Arm | Regions | Pilot region-turns | Granary crew wages | Woodcut wages | Unlocated wages and remittances | Schedule |
| --- | --- | --- | --- | --- | --- | --- | --- |
| t5 | A | 4 | 682 | 163.1 | 38.5 | 0.000 | made S_A e7bf7a363a0c (4 regions) |
| t5 | B | 3 | 306 | 0.0 | 25.5 | 0.000 | made S_B 68fb118bf107 (3 regions) |
| t5 | C | 4 | 682 | 0.0 | 20.0 | 0.000 | replays S_A e7bf7a363a0c: exact |
| t5 | D | 3 | 306 | 239.3 | 26.5 | 0.000 | replays S_B 68fb118bf107: exact |
| t5 | E | 8 | 1588 | 239.2 | 128.5 | 0.000 |  |
| t5 | F | 8 | 1588 | 0.0 | 72.0 | 0.000 |  |
| t5 | G | 7 | 1237 | 200.4 | 88.5 | 0.000 |  |
| t5 | H | 7 | 1237 | 0.0 | 139.0 | 0.000 |  |
| t5 | CH_noTS | 4 | 546 | 230.9 | 0.0 | 0.000 |  |
| p19 | A | 16 | 2732 | 1269.2 | 687.5 | 0.000 | made S_A 33192152fde8 (16 regions) |
| p19 | B | 14 | 2230 | 0.0 | 518.5 | 0.000 | made S_B 240856d6bd77 (14 regions) |
| p19 | C | 16 | 2732 | 0.0 | 597.0 | 0.000 | replays S_A 33192152fde8: exact |
| p19 | D | 14 | 2230 | 1309.4 | 754.5 | 0.000 | replays S_B 240856d6bd77: exact |
| p19 | E | 32 | 5727 | 960.0 | 352.5 | 0.000 |  |
| p19 | F | 32 | 5690 | 0.0 | 364.0 | 0.000 |  |
| p19 | G | 18 | 2990 | 1412.9 | 740.0 | 0.000 |  |
| p19 | H | 17 | 2825 | 0.0 | 571.0 | 0.000 |  |
| p19 | CH_noTS | 16 | 2614 | 666.2 | 0.0 | 0.000 |  |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw1_p1_wage_money: Money credited to households over S_A, wealth units: wages + remittances + procurement - farm income replaced (A - C: the wage at A's enrollment) | t | 5: +211.8 | +211.8 [+211.8, +211.8] | 1 / 0 / 0 | 2/2 as extreme; means [-211.8, +211.8] |
| cw1_p1_wage_money: Money credited to households over S_A, wealth units: wages + remittances + procurement - farm income replaced (A - C: the wage at A's enrollment) | p | 19: +1680 | +1680 [+1680, +1680] | 1 / 0 / 0 | 2/2 as extreme; means [-1680, +1680] |
| cw1_p2_enrollment_money: Money credited to households, world, wealth units (C - B: A's enrollment against B's, no wage) | t | 5: -817.9 | -817.9 [-817.9, -817.9] | 0 / 1 / 0 | 2/2 as extreme; means [-817.9, +817.9] |
| cw1_p2_enrollment_money: Money credited to households, world, wealth units (C - B: A's enrollment against B's, no wage) | p | 19: -422.2 | -422.2 [-422.2, -422.2] | 0 / 1 / 0 | 2/2 as extreme; means [-422.2, +422.2] |
| cw1_p3_wage_priced_out: Priced-out person-turns per pilot person-turn over S_A (A - C) | t | 5: +0.00116 | +0.00116 [+0.00116, +0.00116] | 1 / 0 / 0 | 2/2 as extreme; means [-0.00116, +0.00116] |
| cw1_p3_wage_priced_out: Priced-out person-turns per pilot person-turn over S_A (A - C) | p | 19: -0.000394 | -0.000394 [-0.000394, -0.000394] | 0 / 1 / 0 | 2/2 as extreme; means [-0.000394, +0.000394] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw1_sa_money_world: Money credited to households, world (A - C) | t | 5: +210.6 | +210.6 [+210.6, +210.6] | 1 / 0 / 0 | 2/2 as extreme; means [-210.6, +210.6] |
| cw1_sa_money_world: Money credited to households, world (A - C) | p | 19: +1689 | +1689 [+1689, +1689] | 1 / 0 / 0 | 2/2 as extreme; means [-1689, +1689] |
| cw1_sa_wages: Wages credited, world, all wage channels (A - C) | t | 5: +170.8 | +170.8 [+170.8, +170.8] | 1 / 0 / 0 | 2/2 as extreme; means [-170.8, +170.8] |
| cw1_sa_wages: Wages credited, world, all wage channels (A - C) | p | 19: +1350 | +1350 [+1350, +1350] | 1 / 0 / 0 | 2/2 as extreme; means [-1350, +1350] |
| cw1_sa_granary_wages: Granary crew wages credited, world (A - C) | t | 5: +163.1 | +163.1 [+163.1, +163.1] | 1 / 0 / 0 | 2/2 as extreme; means [-163.1, +163.1] |
| cw1_sa_granary_wages: Granary crew wages credited, world (A - C) | p | 19: +1269 | +1269 [+1269, +1269] | 1 / 0 / 0 | 2/2 as extreme; means [-1269, +1269] |
| cw1_sa_remittances: Remittances credited, world (A - C) | t | 5: +65.21 | +65.21 [+65.21, +65.21] | 1 / 0 / 0 | 2/2 as extreme; means [-65.21, +65.21] |
| cw1_sa_remittances: Remittances credited, world (A - C) | p | 19: +145.3 | +145.3 [+145.3, +145.3] | 1 / 0 / 0 | 2/2 as extreme; means [-145.3, +145.3] |
| cw1_sa_procurement: Procurement credited, world (A - C) | t | 5: +1 | +1 [+1, +1] | 1 / 0 / 0 | 2/2 as extreme; means [-1, +1] |
| cw1_sa_procurement: Procurement credited, world (A - C) | p | 19: -3 | -3 [-3, -3] | 0 / 1 / 0 | 2/2 as extreme; means [-3, +3] |
| cw1_sa_income_replaced: Farm income replaced over S_A (A - C) | t | 5: +26.39 | +26.39 [+26.39, +26.39] | 1 / 0 / 0 | 2/2 as extreme; means [-26.39, +26.39] |
| cw1_sa_income_replaced: Farm income replaced over S_A (A - C) | p | 19: -196 | -196 [-196, -196] | 0 / 1 / 0 | 2/2 as extreme; means [-196, +196] |
| cw1_sa_priced_out: Priced-out person-turns over S_A (A - C) | t | 5: +23 | +23 [+23, +23] | 1 / 0 / 0 | 2/2 as extreme; means [-23, +23] |
| cw1_sa_priced_out: Priced-out person-turns over S_A (A - C) | p | 19: -30 | -30 [-30, -30] | 0 / 1 / 0 | 2/2 as extreme; means [-30, +30] |
| cw1_sa_ration: Mean ration per pilot person-turn over S_A (A - C) | t | 5: -0.02179 | -0.02179 [-0.02179, -0.02179] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02179, +0.02179] |
| cw1_sa_ration: Mean ration per pilot person-turn over S_A (A - C) | p | 19: +0.01371 | +0.01371 [+0.01371, +0.01371] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01371, +0.01371] |
| cw1_sb_money: Money credited to households over S_B (D - B: the wage at B's enrollment) | t | 5: +14.89 | +14.89 [+14.89, +14.89] | 1 / 0 / 0 | 2/2 as extreme; means [-14.89, +14.89] |
| cw1_sb_money: Money credited to households over S_B (D - B: the wage at B's enrollment) | p | 19: +1266 | +1266 [+1266, +1266] | 1 / 0 / 0 | 2/2 as extreme; means [-1266, +1266] |
| cw1_sb_priced_out: Priced-out person-turns per pilot person-turn over S_B (D - B) | t | 5: +0.0003655 | +0.0003655 [+0.0003655, +0.0003655] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0003655, +0.0003655] |
| cw1_sb_priced_out: Priced-out person-turns per pilot person-turn over S_B (D - B) | p | 19: +1.103e-05 | +1.103e-05 [+1.103e-05, +1.103e-05] | 1 / 0 / 0 | 2/2 as extreme; means [-1.103e-05, +1.103e-05] |
| cw1_interaction_money: Money credited over each schedule's set: (A - C) - (D - B) | t | 5: +196.9 | +196.9 [+196.9, +196.9] | 1 / 0 / 0 | 2/2 as extreme; means [-196.9, +196.9] |
| cw1_interaction_money: Money credited over each schedule's set: (A - C) - (D - B) | p | 19: +413.5 | +413.5 [+413.5, +413.5] | 1 / 0 / 0 | 2/2 as extreme; means [-413.5, +413.5] |
| cw1_interaction_priced_out: Priced-out person-turns per pilot person-turn over each schedule's set: (A - C) - (D - B) | t | 5: +0.0007948 | +0.0007948 [+0.0007948, +0.0007948] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0007948, +0.0007948] |
| cw1_interaction_priced_out: Priced-out person-turns per pilot person-turn over each schedule's set: (A - C) - (D - B) | p | 19: -0.000405 | -0.000405 [-0.000405, -0.000405] | 0 / 1 / 0 | 2/2 as extreme; means [-0.000405, +0.000405] |
| cw1_all_money: Money credited to households, world (E - F: the wage at the all boundary) | t | 5: +226.1 | +226.1 [+226.1, +226.1] | 1 / 0 / 0 | 2/2 as extreme; means [-226.1, +226.1] |
| cw1_all_money: Money credited to households, world (E - F: the wage at the all boundary) | p | 19: +946.6 | +946.6 [+946.6, +946.6] | 1 / 0 / 0 | 2/2 as extreme; means [-946.6, +946.6] |
| cw1_all_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (E - F) | t | 5: +0.002073 | +0.002073 [+0.002073, +0.002073] | 1 / 0 / 0 | 2/2 as extreme; means [-0.002073, +0.002073] |
| cw1_all_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (E - F) | p | 19: -7.585e-05 | -7.585e-05 [-7.585e-05, -7.585e-05] | 0 / 1 / 0 | 2/2 as extreme; means [-7.585e-05, +7.585e-05] |
| cw1_all_ration: Mean ration per pilot person-turn (E - F) | t | 5: +0.01661 | +0.01661 [+0.01661, +0.01661] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01661, +0.01661] |
| cw1_all_ration: Mean ration per pilot person-turn (E - F) | p | 19: -0.007141 | -0.007141 [-0.007141, -0.007141] | 0 / 1 / 0 | 2/2 as extreme; means [-0.007141, +0.007141] |
| cw1_mkt_money: Money credited to households, world (G - H: the wage at the market boundary) | t | 5: +0.06109 | +0.06109 [+0.06109, +0.06109] | 1 / 0 / 0 | 2/2 as extreme; means [-0.06109, +0.06109] |
| cw1_mkt_money: Money credited to households, world (G - H: the wage at the market boundary) | p | 19: +1790 | +1790 [+1790, +1790] | 1 / 0 / 0 | 2/2 as extreme; means [-1790, +1790] |
| cw1_mkt_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (G - H) | t | 5: -0.0005228 | -0.0005228 [-0.0005228, -0.0005228] | 0 / 1 / 0 | 2/2 as extreme; means [-0.0005228, +0.0005228] |
| cw1_mkt_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (G - H) | p | 19: -0.0004582 | -0.0004582 [-0.0004582, -0.0004582] | 0 / 1 / 0 | 2/2 as extreme; means [-0.0004582, +0.0004582] |
| cw1_total_money: Money credited to households, world (A - B: CP3's CH - CH_unpaid) | t | 5: -607.3 | -607.3 [-607.3, -607.3] | 0 / 1 / 0 | 2/2 as extreme; means [-607.3, +607.3] |
| cw1_total_money: Money credited to households, world (A - B: CP3's CH - CH_unpaid) | p | 19: +1266 | +1266 [+1266, +1266] | 1 / 0 / 0 | 2/2 as extreme; means [-1266, +1266] |
| cw1_total_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (A - B) | t | 5: +0.001527 | +0.001527 [+0.001527, +0.001527] | 1 / 0 / 0 | 2/2 as extreme; means [-0.001527, +0.001527] |
| cw1_total_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (A - B) | p | 19: -6.365e-05 | -6.365e-05 [-6.365e-05, -6.365e-05] | 0 / 1 / 0 | 2/2 as extreme; means [-6.365e-05, +6.365e-05] |
| cw1_coverage_enrollment: Coverage: pilot region-turns per region-turn (C - B) | t | 5: +0.235 | +0.235 [+0.235, +0.235] | 1 / 0 / 0 | 2/2 as extreme; means [-0.235, +0.235] |
| cw1_coverage_enrollment: Coverage: pilot region-turns per region-turn (C - B) | p | 19: +0.07844 | +0.07844 [+0.07844, +0.07844] | 1 / 0 / 0 | 2/2 as extreme; means [-0.07844, +0.07844] |
| cw1_coverage_total: Coverage: pilot region-turns per region-turn (A - B) | t | 5: +0.235 | +0.235 [+0.235, +0.235] | 1 / 0 / 0 | 2/2 as extreme; means [-0.235, +0.235] |
| cw1_coverage_total: Coverage: pilot region-turns per region-turn (A - B) | p | 19: +0.07844 | +0.07844 [+0.07844, +0.07844] | 1 / 0 / 0 | 2/2 as extreme; means [-0.07844, +0.07844] |
| cw1_enrollment_priced_out: Priced-out person-turns, world (C - B; only pilot regions price anyone out) | t | 5: +7 | +7 [+7, +7] | 1 / 0 / 0 | 2/2 as extreme; means [-7, +7] |
| cw1_enrollment_priced_out: Priced-out person-turns, world (C - B; only pilot regions price anyone out) | p | 19: +26 | +26 [+26, +26] | 1 / 0 / 0 | 2/2 as extreme; means [-26, +26] |
| cw1_enrollment_income_replaced: Farm income replaced, world (C - B) | t | 5: +849.9 | +849.9 [+849.9, +849.9] | 1 / 0 / 0 | 2/2 as extreme; means [-849.9, +849.9] |
| cw1_enrollment_income_replaced: Farm income replaced, world (C - B) | p | 19: +366.2 | +366.2 [+366.2, +366.2] | 1 / 0 / 0 | 2/2 as extreme; means [-366.2, +366.2] |
| cw1_rl5_sa_crew_rate: RL5 crew households (members and co-resident children): priced-out person-turns per person-turn (A - C) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw1_rl5_sa_crew_rate: RL5 crew households (members and co-resident children): priced-out person-turns per person-turn (A - C) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw1_rl5_sa_nonfarm_rate: RL5 non-farm adults: priced-out person-turns per person-turn (A - C) | t | 5: +0.001536 | +0.001536 [+0.001536, +0.001536] | 1 / 0 / 0 | 2/2 as extreme; means [-0.001536, +0.001536] |
| cw1_rl5_sa_nonfarm_rate: RL5 non-farm adults: priced-out person-turns per person-turn (A - C) | p | 19: -0.001245 | -0.001245 [-0.001245, -0.001245] | 0 / 1 / 0 | 2/2 as extreme; means [-0.001245, +0.001245] |
| cw1_rl5_sa_children_alone_rate: RL5 children without a co-resident adult: priced-out person-turns per person-turn (A - C) | t | 5: +0.004402 | +0.004402 [+0.004402, +0.004402] | 1 / 0 / 0 | 2/2 as extreme; means [-0.004402, +0.004402] |
| cw1_rl5_sa_children_alone_rate: RL5 children without a co-resident adult: priced-out person-turns per person-turn (A - C) | p | 19: +0.0002928 | +0.0002928 [+0.0002928, +0.0002928] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0002928, +0.0002928] |
| cw1_rl5_sb_crew_rate: RL5 crew households (members and co-resident children): priced-out person-turns per person-turn (D - B) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw1_rl5_sb_crew_rate: RL5 crew households (members and co-resident children): priced-out person-turns per person-turn (D - B) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw1_rl5_sb_nonfarm_rate: RL5 non-farm adults: priced-out person-turns per person-turn (D - B) | t | 5: +0.000891 | +0.000891 [+0.000891, +0.000891] | 1 / 0 / 0 | 2/2 as extreme; means [-0.000891, +0.000891] |
| cw1_rl5_sb_nonfarm_rate: RL5 non-farm adults: priced-out person-turns per person-turn (D - B) | p | 19: +0.0003384 | +0.0003384 [+0.0003384, +0.0003384] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0003384, +0.0003384] |
| cw1_rl5_sb_children_alone_rate: RL5 children without a co-resident adult: priced-out person-turns per person-turn (D - B) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw1_rl5_sb_children_alone_rate: RL5 children without a co-resident adult: priced-out person-turns per person-turn (D - B) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw1_rl5_sa_crew_count: RL5 crew households: priced-out person-turns (A - C) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw1_rl5_sa_crew_count: RL5 crew households: priced-out person-turns (A - C) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw1_rl5_sa_nonfarm_count: RL5 non-farm adults: priced-out person-turns (A - C) | t | 5: +11 | +11 [+11, +11] | 1 / 0 / 0 | 2/2 as extreme; means [-11, +11] |
| cw1_rl5_sa_nonfarm_count: RL5 non-farm adults: priced-out person-turns (A - C) | p | 19: -30 | -30 [-30, -30] | 0 / 1 / 0 | 2/2 as extreme; means [-30, +30] |
| cw1_rl5_sa_children_alone_count: RL5 children without a co-resident adult: priced-out person-turns (A - C) | t | 5: +7 | +7 [+7, +7] | 1 / 0 / 0 | 2/2 as extreme; means [-7, +7] |
| cw1_rl5_sa_children_alone_count: RL5 children without a co-resident adult: priced-out person-turns (A - C) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw1_nots_money: Money credited to households, world (CH_noTS - A) | t | 5: +436.4 | +436.4 [+436.4, +436.4] | 1 / 0 / 0 | 2/2 as extreme; means [-436.4, +436.4] |
| cw1_nots_money: Money credited to households, world (CH_noTS - A) | p | 19: -1403 | -1403 [-1403, -1403] | 0 / 1 / 0 | 2/2 as extreme; means [-1403, +1403] |
| cw1_nots_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (CH_noTS - A) | t | 5: -0.001527 | -0.001527 [-0.001527, -0.001527] | 0 / 1 / 0 | 2/2 as extreme; means [-0.001527, +0.001527] |
| cw1_nots_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (CH_noTS - A) | p | 19: +0.0002789 | +0.0002789 [+0.0002789, +0.0002789] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0002789, +0.0002789] |
| cw1_nots_coverage: Coverage (CH_noTS - A) | t | 5: -0.085 | -0.085 [-0.085, -0.085] | 0 / 1 / 0 | 2/2 as extreme; means [-0.085, +0.085] |
| cw1_nots_coverage: Coverage (CH_noTS - A) | p | 19: -0.01844 | -0.01844 [-0.01844, -0.01844] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01844, +0.01844] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A - C | Population at the end (sum over civilizations) | t | 5: -18 | -18 [-18, -18] | 0 / 1 / 0 | 2/2 as extreme; means [-18, +18] | recorded |
| A - C | Population at the end (sum over civilizations) | p | 19: -3 | -3 [-3, -3] | 0 / 1 / 0 | 2/2 as extreme; means [-3, +3] | recorded |
| A - C | Treasury at the end (sum over civilizations) | t | 5: +92 | +92 [+92, +92] | 1 / 0 / 0 | 2/2 as extreme; means [-92, +92] | recorded |
| A - C | Treasury at the end (sum over civilizations) | p | 19: -74 | -74 [-74, -74] | 0 / 1 / 0 | 2/2 as extreme; means [-74, +74] | recorded |
| A - C | Food shortfall after relief over the run (food) | t | 5: +307.7 | +307.7 [+307.7, +307.7] | 1 / 0 / 0 | 2/2 as extreme; means [-307.7, +307.7] | recorded |
| A - C | Food shortfall after relief over the run (food) | p | 19: -510.2 | -510.2 [-510.2, -510.2] | 0 / 1 / 0 | 2/2 as extreme; means [-510.2, +510.2] | recorded |
| A - C | Priced-out person-turns | t | 5: +23 | +23 [+23, +23] | 1 / 0 / 0 | 2/2 as extreme; means [-23, +23] | recorded |
| A - C | Priced-out person-turns | p | 19: -30 | -30 [-30, -30] | 0 / 1 / 0 | 2/2 as extreme; means [-30, +30] | recorded |
| A - C | Priced-out child-turns | t | 5: +11 | +11 [+11, +11] | 1 / 0 / 0 | 2/2 as extreme; means [-11, +11] | recorded |
| A - C | Priced-out child-turns | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| A - C | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| A - C | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| A - C | Deaths by epidemic (the epidemic authority) | t | 5: +19 | +19 [+19, +19] | 1 / 0 / 0 | 2/2 as extreme; means [-19, +19] | recorded |
| A - C | Deaths by epidemic (the epidemic authority) | p | 19: -58 | -58 [-58, -58] | 0 / 1 / 0 | 2/2 as extreme; means [-58, +58] | recorded |
| A - C | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| A - C | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| A - C | Agents migrating between regions over the run | t | 5: -88 | -88 [-88, -88] | 0 / 1 / 0 | 2/2 as extreme; means [-88, +88] | recorded |
| A - C | Agents migrating between regions over the run | p | 19: +101 | +101 [+101, +101] | 1 / 0 / 0 | 2/2 as extreme; means [-101, +101] | recorded |
| A - C | Mean wealth Gini of living civilizations at the end | t | 5: -0.02459 | -0.02459 [-0.02459, -0.02459] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02459, +0.02459] | recorded |
| A - C | Mean wealth Gini of living civilizations at the end | p | 19: +0.08717 | +0.08717 [+0.08717, +0.08717] | 1 / 0 / 0 | 2/2 as extreme; means [-0.08717, +0.08717] | recorded |
| A - C | Timber stand share of capacity at the end | t | 5: -0.007023 | -0.007023 [-0.007023, -0.007023] | 0 / 1 / 0 | 2/2 as extreme; means [-0.007023, +0.007023] | recorded |
| A - C | Timber stand share of capacity at the end | p | 19: +0.08955 | +0.08955 [+0.08955, +0.08955] | 1 / 0 / 0 | 2/2 as extreme; means [-0.08955, +0.08955] | recorded |
| C - B | Population at the end (sum over civilizations) | t | 5: +17 | +17 [+17, +17] | 1 / 0 / 0 | 2/2 as extreme; means [-17, +17] | recorded |
| C - B | Population at the end (sum over civilizations) | p | 19: +34 | +34 [+34, +34] | 1 / 0 / 0 | 2/2 as extreme; means [-34, +34] | recorded |
| C - B | Treasury at the end (sum over civilizations) | t | 5: -211 | -211 [-211, -211] | 0 / 1 / 0 | 2/2 as extreme; means [-211, +211] | recorded |
| C - B | Treasury at the end (sum over civilizations) | p | 19: +1702 | +1702 [+1702, +1702] | 1 / 0 / 0 | 2/2 as extreme; means [-1702, +1702] | recorded |
| C - B | Food shortfall after relief over the run (food) | t | 5: +96.73 | +96.73 [+96.73, +96.73] | 1 / 0 / 0 | 2/2 as extreme; means [-96.73, +96.73] | recorded |
| C - B | Food shortfall after relief over the run (food) | p | 19: +519.6 | +519.6 [+519.6, +519.6] | 1 / 0 / 0 | 2/2 as extreme; means [-519.6, +519.6] | recorded |
| C - B | Priced-out person-turns | t | 5: +7 | +7 [+7, +7] | 1 / 0 / 0 | 2/2 as extreme; means [-7, +7] | recorded |
| C - B | Priced-out person-turns | p | 19: +26 | +26 [+26, +26] | 1 / 0 / 0 | 2/2 as extreme; means [-26, +26] | recorded |
| C - B | Priced-out child-turns | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| C - B | Priced-out child-turns | p | 19: +5 | +5 [+5, +5] | 1 / 0 / 0 | 2/2 as extreme; means [-5, +5] | recorded |
| C - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C - B | Deaths by epidemic (the epidemic authority) | t | 5: -58 | -58 [-58, -58] | 0 / 1 / 0 | 2/2 as extreme; means [-58, +58] | recorded |
| C - B | Deaths by epidemic (the epidemic authority) | p | 19: +63 | +63 [+63, +63] | 1 / 0 / 0 | 2/2 as extreme; means [-63, +63] | recorded |
| C - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C - B | Agents migrating between regions over the run | t | 5: +219 | +219 [+219, +219] | 1 / 0 / 0 | 2/2 as extreme; means [-219, +219] | recorded |
| C - B | Agents migrating between regions over the run | p | 19: +772 | +772 [+772, +772] | 1 / 0 / 0 | 2/2 as extreme; means [-772, +772] | recorded |
| C - B | Mean wealth Gini of living civilizations at the end | t | 5: -0.02476 | -0.02476 [-0.02476, -0.02476] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02476, +0.02476] | recorded |
| C - B | Mean wealth Gini of living civilizations at the end | p | 19: +0.02383 | +0.02383 [+0.02383, +0.02383] | 1 / 0 / 0 | 2/2 as extreme; means [-0.02383, +0.02383] | recorded |
| C - B | Timber stand share of capacity at the end | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| C - B | Timber stand share of capacity at the end | p | 19: -0.03002 | -0.03002 [-0.03002, -0.03002] | 0 / 1 / 0 | 2/2 as extreme; means [-0.03002, +0.03002] | recorded |
| D - B | Population at the end (sum over civilizations) | t | 5: +14 | +14 [+14, +14] | 1 / 0 / 0 | 2/2 as extreme; means [-14, +14] | recorded |
| D - B | Population at the end (sum over civilizations) | p | 19: -25 | -25 [-25, -25] | 0 / 1 / 0 | 2/2 as extreme; means [-25, +25] | recorded |
| D - B | Treasury at the end (sum over civilizations) | t | 5: +491 | +491 [+491, +491] | 1 / 0 / 0 | 2/2 as extreme; means [-491, +491] | recorded |
| D - B | Treasury at the end (sum over civilizations) | p | 19: -1068 | -1068 [-1068, -1068] | 0 / 1 / 0 | 2/2 as extreme; means [-1068, +1068] | recorded |
| D - B | Food shortfall after relief over the run (food) | t | 5: +256.2 | +256.2 [+256.2, +256.2] | 1 / 0 / 0 | 2/2 as extreme; means [-256.2, +256.2] | recorded |
| D - B | Food shortfall after relief over the run (food) | p | 19: -139.7 | -139.7 [-139.7, -139.7] | 0 / 1 / 0 | 2/2 as extreme; means [-139.7, +139.7] | recorded |
| D - B | Priced-out person-turns | t | 5: +3 | +3 [+3, +3] | 1 / 0 / 0 | 2/2 as extreme; means [-3, +3] | recorded |
| D - B | Priced-out person-turns | p | 19: +1 | +1 [+1, +1] | 1 / 0 / 0 | 2/2 as extreme; means [-1, +1] | recorded |
| D - B | Priced-out child-turns | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| D - B | Priced-out child-turns | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| D - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| D - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| D - B | Deaths by epidemic (the epidemic authority) | t | 5: -63 | -63 [-63, -63] | 0 / 1 / 0 | 2/2 as extreme; means [-63, +63] | recorded |
| D - B | Deaths by epidemic (the epidemic authority) | p | 19: -44 | -44 [-44, -44] | 0 / 1 / 0 | 2/2 as extreme; means [-44, +44] | recorded |
| D - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| D - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| D - B | Agents migrating between regions over the run | t | 5: +171 | +171 [+171, +171] | 1 / 0 / 0 | 2/2 as extreme; means [-171, +171] | recorded |
| D - B | Agents migrating between regions over the run | p | 19: -497 | -497 [-497, -497] | 0 / 1 / 0 | 2/2 as extreme; means [-497, +497] | recorded |
| D - B | Mean wealth Gini of living civilizations at the end | t | 5: +0.0167 | +0.0167 [+0.0167, +0.0167] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0167, +0.0167] | recorded |
| D - B | Mean wealth Gini of living civilizations at the end | p | 19: -0.003636 | -0.003636 [-0.003636, -0.003636] | 0 / 1 / 0 | 2/2 as extreme; means [-0.003636, +0.003636] | recorded |
| D - B | Timber stand share of capacity at the end | t | 5: -0.02783 | -0.02783 [-0.02783, -0.02783] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02783, +0.02783] | recorded |
| D - B | Timber stand share of capacity at the end | p | 19: +0.002117 | +0.002117 [+0.002117, +0.002117] | 1 / 0 / 0 | 2/2 as extreme; means [-0.002117, +0.002117] | recorded |
| E - F | Population at the end (sum over civilizations) | t | 5: -15 | -15 [-15, -15] | 0 / 1 / 0 | 2/2 as extreme; means [-15, +15] | recorded |
| E - F | Population at the end (sum over civilizations) | p | 19: +171 | +171 [+171, +171] | 1 / 0 / 0 | 2/2 as extreme; means [-171, +171] | recorded |
| E - F | Treasury at the end (sum over civilizations) | t | 5: -653 | -653 [-653, -653] | 0 / 1 / 0 | 2/2 as extreme; means [-653, +653] | recorded |
| E - F | Treasury at the end (sum over civilizations) | p | 19: -1168 | -1168 [-1168, -1168] | 0 / 1 / 0 | 2/2 as extreme; means [-1168, +1168] | recorded |
| E - F | Food shortfall after relief over the run (food) | t | 5: -419.4 | -419.4 [-419.4, -419.4] | 0 / 1 / 0 | 2/2 as extreme; means [-419.4, +419.4] | recorded |
| E - F | Food shortfall after relief over the run (food) | p | 19: +903.2 | +903.2 [+903.2, +903.2] | 1 / 0 / 0 | 2/2 as extreme; means [-903.2, +903.2] | recorded |
| E - F | Priced-out person-turns | t | 5: +39 | +39 [+39, +39] | 1 / 0 / 0 | 2/2 as extreme; means [-39, +39] | recorded |
| E - F | Priced-out person-turns | p | 19: +95 | +95 [+95, +95] | 1 / 0 / 0 | 2/2 as extreme; means [-95, +95] | recorded |
| E - F | Priced-out child-turns | t | 5: -22 | -22 [-22, -22] | 0 / 1 / 0 | 2/2 as extreme; means [-22, +22] | recorded |
| E - F | Priced-out child-turns | p | 19: +2 | +2 [+2, +2] | 1 / 0 / 0 | 2/2 as extreme; means [-2, +2] | recorded |
| E - F | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E - F | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E - F | Deaths by epidemic (the epidemic authority) | t | 5: +20 | +20 [+20, +20] | 1 / 0 / 0 | 2/2 as extreme; means [-20, +20] | recorded |
| E - F | Deaths by epidemic (the epidemic authority) | p | 19: -129 | -129 [-129, -129] | 0 / 1 / 0 | 2/2 as extreme; means [-129, +129] | recorded |
| E - F | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E - F | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E - F | Agents migrating between regions over the run | t | 5: -194 | -194 [-194, -194] | 0 / 1 / 0 | 2/2 as extreme; means [-194, +194] | recorded |
| E - F | Agents migrating between regions over the run | p | 19: +1319 | +1319 [+1319, +1319] | 1 / 0 / 0 | 2/2 as extreme; means [-1319, +1319] | recorded |
| E - F | Mean wealth Gini of living civilizations at the end | t | 5: -0.1279 | -0.1279 [-0.1279, -0.1279] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1279, +0.1279] | recorded |
| E - F | Mean wealth Gini of living civilizations at the end | p | 19: +0.1473 | +0.1473 [+0.1473, +0.1473] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1473, +0.1473] | recorded |
| E - F | Timber stand share of capacity at the end | t | 5: -0.299 | -0.299 [-0.299, -0.299] | 0 / 1 / 0 | 2/2 as extreme; means [-0.299, +0.299] | recorded |
| E - F | Timber stand share of capacity at the end | p | 19: +0.001795 | +0.001795 [+0.001795, +0.001795] | 1 / 0 / 0 | 2/2 as extreme; means [-0.001795, +0.001795] | recorded |
| F - B | Population at the end (sum over civilizations) | t | 5: -33 | -33 [-33, -33] | 0 / 1 / 0 | 2/2 as extreme; means [-33, +33] | recorded |
| F - B | Population at the end (sum over civilizations) | p | 19: -41 | -41 [-41, -41] | 0 / 1 / 0 | 2/2 as extreme; means [-41, +41] | recorded |
| F - B | Treasury at the end (sum over civilizations) | t | 5: +164 | +164 [+164, +164] | 1 / 0 / 0 | 2/2 as extreme; means [-164, +164] | recorded |
| F - B | Treasury at the end (sum over civilizations) | p | 19: -776 | -776 [-776, -776] | 0 / 1 / 0 | 2/2 as extreme; means [-776, +776] | recorded |
| F - B | Food shortfall after relief over the run (food) | t | 5: +1353 | +1353 [+1353, +1353] | 1 / 0 / 0 | 2/2 as extreme; means [-1353, +1353] | recorded |
| F - B | Food shortfall after relief over the run (food) | p | 19: +1189 | +1189 [+1189, +1189] | 1 / 0 / 0 | 2/2 as extreme; means [-1189, +1189] | recorded |
| F - B | Priced-out person-turns | t | 5: +717 | +717 [+717, +717] | 1 / 0 / 0 | 2/2 as extreme; means [-717, +717] | recorded |
| F - B | Priced-out person-turns | p | 19: +1371 | +1371 [+1371, +1371] | 1 / 0 / 0 | 2/2 as extreme; means [-1371, +1371] | recorded |
| F - B | Priced-out child-turns | t | 5: +131 | +131 [+131, +131] | 1 / 0 / 0 | 2/2 as extreme; means [-131, +131] | recorded |
| F - B | Priced-out child-turns | p | 19: +137 | +137 [+137, +137] | 1 / 0 / 0 | 2/2 as extreme; means [-137, +137] | recorded |
| F - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F - B | Deaths by epidemic (the epidemic authority) | t | 5: -45 | -45 [-45, -45] | 0 / 1 / 0 | 2/2 as extreme; means [-45, +45] | recorded |
| F - B | Deaths by epidemic (the epidemic authority) | p | 19: -220 | -220 [-220, -220] | 0 / 1 / 0 | 2/2 as extreme; means [-220, +220] | recorded |
| F - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F - B | Agents migrating between regions over the run | t | 5: +556 | +556 [+556, +556] | 1 / 0 / 0 | 2/2 as extreme; means [-556, +556] | recorded |
| F - B | Agents migrating between regions over the run | p | 19: +217 | +217 [+217, +217] | 1 / 0 / 0 | 2/2 as extreme; means [-217, +217] | recorded |
| F - B | Mean wealth Gini of living civilizations at the end | t | 5: -0.1056 | -0.1056 [-0.1056, -0.1056] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1056, +0.1056] | recorded |
| F - B | Mean wealth Gini of living civilizations at the end | p | 19: -0.07491 | -0.07491 [-0.07491, -0.07491] | 0 / 1 / 0 | 2/2 as extreme; means [-0.07491, +0.07491] | recorded |
| F - B | Timber stand share of capacity at the end | t | 5: +0.07086 | +0.07086 [+0.07086, +0.07086] | 1 / 0 / 0 | 2/2 as extreme; means [-0.07086, +0.07086] | recorded |
| F - B | Timber stand share of capacity at the end | p | 19: -0.007484 | -0.007484 [-0.007484, -0.007484] | 0 / 1 / 0 | 2/2 as extreme; means [-0.007484, +0.007484] | recorded |
| G - H | Population at the end (sum over civilizations) | t | 5: +28 | +28 [+28, +28] | 1 / 0 / 0 | 2/2 as extreme; means [-28, +28] | recorded |
| G - H | Population at the end (sum over civilizations) | p | 19: +95 | +95 [+95, +95] | 1 / 0 / 0 | 2/2 as extreme; means [-95, +95] | recorded |
| G - H | Treasury at the end (sum over civilizations) | t | 5: +451 | +451 [+451, +451] | 1 / 0 / 0 | 2/2 as extreme; means [-451, +451] | recorded |
| G - H | Treasury at the end (sum over civilizations) | p | 19: -1363 | -1363 [-1363, -1363] | 0 / 1 / 0 | 2/2 as extreme; means [-1363, +1363] | recorded |
| G - H | Food shortfall after relief over the run (food) | t | 5: -161.3 | -161.3 [-161.3, -161.3] | 0 / 1 / 0 | 2/2 as extreme; means [-161.3, +161.3] | recorded |
| G - H | Food shortfall after relief over the run (food) | p | 19: +452.5 | +452.5 [+452.5, +452.5] | 1 / 0 / 0 | 2/2 as extreme; means [-452.5, +452.5] | recorded |
| G - H | Priced-out person-turns | t | 5: -20 | -20 [-20, -20] | 0 / 1 / 0 | 2/2 as extreme; means [-20, +20] | recorded |
| G - H | Priced-out person-turns | p | 19: -12 | -12 [-12, -12] | 0 / 1 / 0 | 2/2 as extreme; means [-12, +12] | recorded |
| G - H | Priced-out child-turns | t | 5: +8 | +8 [+8, +8] | 1 / 0 / 0 | 2/2 as extreme; means [-8, +8] | recorded |
| G - H | Priced-out child-turns | p | 19: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] | recorded |
| G - H | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| G - H | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| G - H | Deaths by epidemic (the epidemic authority) | t | 5: +67 | +67 [+67, +67] | 1 / 0 / 0 | 2/2 as extreme; means [-67, +67] | recorded |
| G - H | Deaths by epidemic (the epidemic authority) | p | 19: +56 | +56 [+56, +56] | 1 / 0 / 0 | 2/2 as extreme; means [-56, +56] | recorded |
| G - H | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| G - H | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| G - H | Agents migrating between regions over the run | t | 5: -13 | -13 [-13, -13] | 0 / 1 / 0 | 2/2 as extreme; means [-13, +13] | recorded |
| G - H | Agents migrating between regions over the run | p | 19: +308 | +308 [+308, +308] | 1 / 0 / 0 | 2/2 as extreme; means [-308, +308] | recorded |
| G - H | Mean wealth Gini of living civilizations at the end | t | 5: +0.05742 | +0.05742 [+0.05742, +0.05742] | 1 / 0 / 0 | 2/2 as extreme; means [-0.05742, +0.05742] | recorded |
| G - H | Mean wealth Gini of living civilizations at the end | p | 19: -0.05562 | -0.05562 [-0.05562, -0.05562] | 0 / 1 / 0 | 2/2 as extreme; means [-0.05562, +0.05562] | recorded |
| G - H | Timber stand share of capacity at the end | t | 5: +0.2843 | +0.2843 [+0.2843, +0.2843] | 1 / 0 / 0 | 2/2 as extreme; means [-0.2843, +0.2843] | recorded |
| G - H | Timber stand share of capacity at the end | p | 19: +0.02303 | +0.02303 [+0.02303, +0.02303] | 1 / 0 / 0 | 2/2 as extreme; means [-0.02303, +0.02303] | recorded |
| H - B | Population at the end (sum over civilizations) | t | 5: -19 | -19 [-19, -19] | 0 / 1 / 0 | 2/2 as extreme; means [-19, +19] | recorded |
| H - B | Population at the end (sum over civilizations) | p | 19: +113 | +113 [+113, +113] | 1 / 0 / 0 | 2/2 as extreme; means [-113, +113] | recorded |
| H - B | Treasury at the end (sum over civilizations) | t | 5: +309 | +309 [+309, +309] | 1 / 0 / 0 | 2/2 as extreme; means [-309, +309] | recorded |
| H - B | Treasury at the end (sum over civilizations) | p | 19: +1224 | +1224 [+1224, +1224] | 1 / 0 / 0 | 2/2 as extreme; means [-1224, +1224] | recorded |
| H - B | Food shortfall after relief over the run (food) | t | 5: +656.3 | +656.3 [+656.3, +656.3] | 1 / 0 / 0 | 2/2 as extreme; means [-656.3, +656.3] | recorded |
| H - B | Food shortfall after relief over the run (food) | p | 19: +3200 | +3200 [+3200, +3200] | 1 / 0 / 0 | 2/2 as extreme; means [-3200, +3200] | recorded |
| H - B | Priced-out person-turns | t | 5: +154 | +154 [+154, +154] | 1 / 0 / 0 | 2/2 as extreme; means [-154, +154] | recorded |
| H - B | Priced-out person-turns | p | 19: +256 | +256 [+256, +256] | 1 / 0 / 0 | 2/2 as extreme; means [-256, +256] | recorded |
| H - B | Priced-out child-turns | t | 5: +21 | +21 [+21, +21] | 1 / 0 / 0 | 2/2 as extreme; means [-21, +21] | recorded |
| H - B | Priced-out child-turns | p | 19: +27 | +27 [+27, +27] | 1 / 0 / 0 | 2/2 as extreme; means [-27, +27] | recorded |
| H - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| H - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| H - B | Deaths by epidemic (the epidemic authority) | t | 5: -65 | -65 [-65, -65] | 0 / 1 / 0 | 2/2 as extreme; means [-65, +65] | recorded |
| H - B | Deaths by epidemic (the epidemic authority) | p | 19: -346 | -346 [-346, -346] | 0 / 1 / 0 | 2/2 as extreme; means [-346, +346] | recorded |
| H - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| H - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| H - B | Agents migrating between regions over the run | t | 5: +372 | +372 [+372, +372] | 1 / 0 / 0 | 2/2 as extreme; means [-372, +372] | recorded |
| H - B | Agents migrating between regions over the run | p | 19: +2981 | +2981 [+2981, +2981] | 1 / 0 / 0 | 2/2 as extreme; means [-2981, +2981] | recorded |
| H - B | Mean wealth Gini of living civilizations at the end | t | 5: -0.06457 | -0.06457 [-0.06457, -0.06457] | 0 / 1 / 0 | 2/2 as extreme; means [-0.06457, +0.06457] | recorded |
| H - B | Mean wealth Gini of living civilizations at the end | p | 19: +0.1027 | +0.1027 [+0.1027, +0.1027] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1027, +0.1027] | recorded |
| H - B | Timber stand share of capacity at the end | t | 5: -0.2843 | -0.2843 [-0.2843, -0.2843] | 0 / 1 / 0 | 2/2 as extreme; means [-0.2843, +0.2843] | recorded |
| H - B | Timber stand share of capacity at the end | p | 19: +0.02848 | +0.02848 [+0.02848, +0.02848] | 1 / 0 / 0 | 2/2 as extreme; means [-0.02848, +0.02848] | recorded |
| CH_noTS - A | Population at the end (sum over civilizations) | t | 5: -9 | -9 [-9, -9] | 0 / 1 / 0 | 2/2 as extreme; means [-9, +9] | recorded |
| CH_noTS - A | Population at the end (sum over civilizations) | p | 19: -55 | -55 [-55, -55] | 0 / 1 / 0 | 2/2 as extreme; means [-55, +55] | recorded |
| CH_noTS - A | Treasury at the end (sum over civilizations) | t | 5: +176 | +176 [+176, +176] | 1 / 0 / 0 | 2/2 as extreme; means [-176, +176] | recorded |
| CH_noTS - A | Treasury at the end (sum over civilizations) | p | 19: -1190 | -1190 [-1190, -1190] | 0 / 1 / 0 | 2/2 as extreme; means [-1190, +1190] | recorded |
| CH_noTS - A | Food shortfall after relief over the run (food) | t | 5: -266.9 | -266.9 [-266.9, -266.9] | 0 / 1 / 0 | 2/2 as extreme; means [-266.9, +266.9] | recorded |
| CH_noTS - A | Food shortfall after relief over the run (food) | p | 19: -110.7 | -110.7 [-110.7, -110.7] | 0 / 1 / 0 | 2/2 as extreme; means [-110.7, +110.7] | recorded |
| CH_noTS - A | Priced-out person-turns | t | 5: -30 | -30 [-30, -30] | 0 / 1 / 0 | 2/2 as extreme; means [-30, +30] | recorded |
| CH_noTS - A | Priced-out person-turns | p | 19: +22 | +22 [+22, +22] | 1 / 0 / 0 | 2/2 as extreme; means [-22, +22] | recorded |
| CH_noTS - A | Priced-out child-turns | t | 5: -11 | -11 [-11, -11] | 0 / 1 / 0 | 2/2 as extreme; means [-11, +11] | recorded |
| CH_noTS - A | Priced-out child-turns | p | 19: -2 | -2 [-2, -2] | 0 / 1 / 0 | 2/2 as extreme; means [-2, +2] | recorded |
| CH_noTS - A | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| CH_noTS - A | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| CH_noTS - A | Deaths by epidemic (the epidemic authority) | t | 5: +49 | +49 [+49, +49] | 1 / 0 / 0 | 2/2 as extreme; means [-49, +49] | recorded |
| CH_noTS - A | Deaths by epidemic (the epidemic authority) | p | 19: -93 | -93 [-93, -93] | 0 / 1 / 0 | 2/2 as extreme; means [-93, +93] | recorded |
| CH_noTS - A | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| CH_noTS - A | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| CH_noTS - A | Agents migrating between regions over the run | t | 5: +16 | +16 [+16, +16] | 1 / 0 / 0 | 2/2 as extreme; means [-16, +16] | recorded |
| CH_noTS - A | Agents migrating between regions over the run | p | 19: -1411 | -1411 [-1411, -1411] | 0 / 1 / 0 | 2/2 as extreme; means [-1411, +1411] | recorded |
| CH_noTS - A | Mean wealth Gini of living civilizations at the end | t | 5: +0.04861 | +0.04861 [+0.04861, +0.04861] | 1 / 0 / 0 | 2/2 as extreme; means [-0.04861, +0.04861] | recorded |
| CH_noTS - A | Mean wealth Gini of living civilizations at the end | p | 19: -0.02159 | -0.02159 [-0.02159, -0.02159] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02159, +0.02159] | recorded |
| CH_noTS - A | Timber stand share of capacity at the end | t | 5: -0.1386 | -0.1386 [-0.1386, -0.1386] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1386, +0.1386] | recorded |
| CH_noTS - A | Timber stand share of capacity at the end | p | 19: -0.05949 | -0.05949 [-0.05949, -0.05949] | 0 / 1 / 0 | 2/2 as extreme; means [-0.05949, +0.05949] | recorded |
| A - B | Population at the end (sum over civilizations) | t | 5: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] | recorded |
| A - B | Population at the end (sum over civilizations) | p | 19: +31 | +31 [+31, +31] | 1 / 0 / 0 | 2/2 as extreme; means [-31, +31] | recorded |
| A - B | Treasury at the end (sum over civilizations) | t | 5: -119 | -119 [-119, -119] | 0 / 1 / 0 | 2/2 as extreme; means [-119, +119] | recorded |
| A - B | Treasury at the end (sum over civilizations) | p | 19: +1628 | +1628 [+1628, +1628] | 1 / 0 / 0 | 2/2 as extreme; means [-1628, +1628] | recorded |
| A - B | Food shortfall after relief over the run (food) | t | 5: +404.4 | +404.4 [+404.4, +404.4] | 1 / 0 / 0 | 2/2 as extreme; means [-404.4, +404.4] | recorded |
| A - B | Food shortfall after relief over the run (food) | p | 19: +9.381 | +9.381 [+9.381, +9.381] | 1 / 0 / 0 | 2/2 as extreme; means [-9.381, +9.381] | recorded |
| A - B | Priced-out person-turns | t | 5: +30 | +30 [+30, +30] | 1 / 0 / 0 | 2/2 as extreme; means [-30, +30] | recorded |
| A - B | Priced-out person-turns | p | 19: -4 | -4 [-4, -4] | 0 / 1 / 0 | 2/2 as extreme; means [-4, +4] | recorded |
| A - B | Priced-out child-turns | t | 5: +11 | +11 [+11, +11] | 1 / 0 / 0 | 2/2 as extreme; means [-11, +11] | recorded |
| A - B | Priced-out child-turns | p | 19: +5 | +5 [+5, +5] | 1 / 0 / 0 | 2/2 as extreme; means [-5, +5] | recorded |
| A - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| A - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| A - B | Deaths by epidemic (the epidemic authority) | t | 5: -39 | -39 [-39, -39] | 0 / 1 / 0 | 2/2 as extreme; means [-39, +39] | recorded |
| A - B | Deaths by epidemic (the epidemic authority) | p | 19: +5 | +5 [+5, +5] | 1 / 0 / 0 | 2/2 as extreme; means [-5, +5] | recorded |
| A - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| A - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| A - B | Agents migrating between regions over the run | t | 5: +131 | +131 [+131, +131] | 1 / 0 / 0 | 2/2 as extreme; means [-131, +131] | recorded |
| A - B | Agents migrating between regions over the run | p | 19: +873 | +873 [+873, +873] | 1 / 0 / 0 | 2/2 as extreme; means [-873, +873] | recorded |
| A - B | Mean wealth Gini of living civilizations at the end | t | 5: -0.04935 | -0.04935 [-0.04935, -0.04935] | 0 / 1 / 0 | 2/2 as extreme; means [-0.04935, +0.04935] | recorded |
| A - B | Mean wealth Gini of living civilizations at the end | p | 19: +0.111 | +0.111 [+0.111, +0.111] | 1 / 0 / 0 | 2/2 as extreme; means [-0.111, +0.111] | recorded |
| A - B | Timber stand share of capacity at the end | t | 5: -0.007023 | -0.007023 [-0.007023, -0.007023] | 0 / 1 / 0 | 2/2 as extreme; means [-0.007023, +0.007023] | recorded |
| A - B | Timber stand share of capacity at the end | p | 19: +0.05953 | +0.05953 [+0.05953, +0.05953] | 1 / 0 / 0 | 2/2 as extreme; means [-0.05953, +0.05953] | recorded |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| A | 9.5 [9.5, 9.5] | 28.1 [28.1, 28.1] |
| B | 8.8 [8.8, 8.8] | 26.6 [26.6, 26.6] |
| C | 9.8 [9.8, 9.8] | 27.4 [27.4, 27.4] |
| D | 9.2 [9.2, 9.2] | 25.6 [25.6, 25.6] |
| E | 10.9 [10.9, 10.9] | 29.9 [29.9, 29.9] |
| F | 10.8 [10.8, 10.8] | 28.4 [28.4, 28.4] |
| G | 10.5 [10.5, 10.5] | 26.0 [26.0, 26.0] |
| H | 10.6 [10.6, 10.6] | 28.2 [28.2, 28.2] |
| CH_noTS | 9.1 [9.1, 9.1] | 23.6 [23.6, 23.6] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
