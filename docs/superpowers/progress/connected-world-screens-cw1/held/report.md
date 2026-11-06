# CW1: S1 accounting and wages (A1-A2): the wage and paid_work enrollment

Cohort held. Runs: 108; failed: 0 (missing outcomes: 0); simulation and extraction seconds 2103 (0.584 core-hours)

Identity digests: 1be6247d5934bdb9ab68296631f541ddbca20a4b4fbb5e2e78692f5f09afeea4 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"food_allocation": [1], "household_retail": [1], "operating_wear": [1], "recovery_crews": [1], "remittances": [1], "repair_projects": [1], "timber_stock": [1], "timber_supply": [1], "wealth_accounting": [1], "workshops": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"food_allocation": [1], "household_retail": [1], "operating_wear": [1], "recovery_crews": [1], "remittances": [1], "repair_projects": [1], "timber_stock": [1], "wealth_accounting": [1], "workshops": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| A | t | 731: activated; 732: activated; 733: activated; 734: not activated; 735: activated; 736: activated | 5 of 6 |
| A | p | 831: activated; 832: activated; 833: activated; 834: activated; 835: activated; 836: activated | 6 of 6 |
| C | t | 731: activated; 732: activated; 733: activated; 734: not activated; 735: activated; 736: activated | 5 of 6 |
| C | p | 831: activated; 832: activated; 833: activated; 834: activated; 835: activated; 836: activated | 6 of 6 |
| D | t | 731: activated; 732: activated; 733: activated; 734: not activated; 735: activated; 736: activated | 5 of 6 |
| D | p | 831: activated; 832: activated; 833: activated; 834: activated; 835: activated; 836: activated | 6 of 6 |
| E | t | 731: activated; 732: activated; 733: activated; 734: not activated; 735: activated; 736: activated | 5 of 6 |
| E | p | 831: activated; 832: activated; 833: activated; 834: activated; 835: activated; 836: activated | 6 of 6 |
| F | t | 731: activated; 732: activated; 733: activated; 734: activated; 735: activated; 736: activated | 6 of 6 |
| F | p | 831: activated; 832: activated; 833: activated; 834: activated; 835: activated; 836: activated | 6 of 6 |
| G | t | 731: activated; 732: activated; 733: activated; 734: not activated; 735: activated; 736: activated | 5 of 6 |
| G | p | 831: activated; 832: activated; 833: activated; 834: activated; 835: activated; 836: activated | 6 of 6 |
| H | t | 731: activated; 732: activated; 733: activated; 734: activated; 735: activated; 736: activated | 6 of 6 |
| H | p | 831: activated; 832: activated; 833: activated; 834: activated; 835: activated; 836: activated | 6 of 6 |
| CH_noTS | t | 731: activated; 732: activated; 733: activated; 734: not activated; 735: activated; 736: activated | 5 of 6 |
| CH_noTS | p | 831: activated; 832: activated; 833: activated; 834: activated; 835: activated; 836: activated | 6 of 6 |

## CW1 validity per world (enrollment, wages, schedules; before any effect)

| World | Arm | Regions | Pilot region-turns | Granary crew wages | Woodcut wages | Unlocated wages and remittances | Schedule |
| --- | --- | --- | --- | --- | --- | --- | --- |
| t731 | A | 6 | 1060 | 222.5 | 66.0 | 0.000 | made S_A e522d35047c0 (6 regions) |
| t731 | B | 5 | 706 | 0.0 | 81.5 | 0.000 | made S_B 1beec1d4ed19 (5 regions) |
| t731 | C | 6 | 1060 | 0.0 | 90.5 | 0.000 | replays S_A e522d35047c0: exact |
| t731 | D | 5 | 706 | 265.1 | 121.0 | 0.000 | replays S_B 1beec1d4ed19: exact |
| t731 | E | 8 | 1599 | 344.9 | 181.0 | 0.000 |  |
| t731 | F | 8 | 1599 | 0.0 | 115.0 | 0.000 |  |
| t731 | G | 6 | 1157 | 217.2 | 109.5 | 0.000 |  |
| t731 | H | 5 | 996 | 0.0 | 145.0 | 0.000 |  |
| t731 | CH_noTS | 6 | 1060 | 157.3 | 0.0 | 0.000 |  |
| t732 | A | 6 | 1052 | 93.4 | 48.0 | 0.000 | made S_A 21d820ddbf7c (6 regions) |
| t732 | B | 4 | 618 | 0.0 | 70.0 | 0.000 | made S_B d61221d52150 (4 regions) |
| t732 | C | 6 | 1052 | 0.0 | 57.0 | 0.000 | replays S_A 21d820ddbf7c: exact |
| t732 | D | 4 | 618 | 112.2 | 59.5 | 0.000 | replays S_B d61221d52150: exact |
| t732 | E | 8 | 1600 | 268.0 | 180.0 | 0.000 |  |
| t732 | F | 8 | 1600 | 0.0 | 46.5 | 0.000 |  |
| t732 | G | 7 | 1354 | 75.4 | 32.5 | 0.000 |  |
| t732 | H | 7 | 1360 | 0.0 | 37.5 | 0.000 |  |
| t732 | CH_noTS | 5 | 878 | 75.2 | 0.0 | 0.000 |  |
| t733 | A | 5 | 814 | 172.9 | 17.5 | 0.000 | made S_A 8722477b5f97 (5 regions) |
| t733 | B | 3 | 464 | 0.0 | 44.0 | 0.000 | made S_B 415e824bfc43 (3 regions) |
| t733 | C | 5 | 814 | 0.0 | 14.0 | 0.000 | replays S_A 8722477b5f97: exact |
| t733 | D | 3 | 464 | 264.8 | 32.5 | 0.000 | replays S_B 415e824bfc43: exact |
| t733 | E | 7 | 1379 | 182.5 | 18.5 | 0.000 |  |
| t733 | F | 8 | 1418 | 0.0 | 27.0 | 0.000 |  |
| t733 | G | 6 | 990 | 164.9 | 4.0 | 0.000 |  |
| t733 | H | 5 | 832 | 0.0 | 9.5 | 0.000 |  |
| t733 | CH_noTS | 5 | 739 | 177.9 | 0.0 | 0.000 |  |
| t734 | A | 0 | 0 | 0.0 | 0.0 | 0.000 | made S_A 44136fa355b3 (0 regions) |
| t734 | B | 0 | 0 | 0.0 | 0.0 | 0.000 | made S_B 44136fa355b3 (0 regions) |
| t734 | C | 0 | 0 | 0.0 | 0.0 | 0.000 | replays S_A 44136fa355b3: exact |
| t734 | D | 0 | 0 | 0.0 | 0.0 | 0.000 | replays S_B 44136fa355b3: exact |
| t734 | E | 8 | 1599 | 0.0 | 0.0 | 0.000 |  |
| t734 | F | 8 | 1599 | 0.0 | 0.0 | 0.000 |  |
| t734 | G | 6 | 1149 | 0.0 | 0.0 | 0.000 |  |
| t734 | H | 6 | 1149 | 0.0 | 0.0 | 0.000 |  |
| t734 | CH_noTS | 0 | 0 | 0.0 | 0.0 | 0.000 |  |
| t735 | A | 6 | 966 | 112.0 | 16.0 | 0.000 | made S_A 87fcb4ac7ff7 (6 regions) |
| t735 | B | 4 | 530 | 0.0 | 23.0 | 0.000 | made S_B e8a0970a2618 (4 regions) |
| t735 | C | 6 | 966 | 0.0 | 23.0 | 0.000 | replays S_A 87fcb4ac7ff7: exact |
| t735 | D | 4 | 530 | 146.6 | 16.0 | 0.000 | replays S_B e8a0970a2618: exact |
| t735 | E | 8 | 1546 | 219.1 | 14.0 | 0.000 |  |
| t735 | F | 8 | 1546 | 0.0 | 18.0 | 0.000 |  |
| t735 | G | 5 | 982 | 112.6 | 8.0 | 0.000 |  |
| t735 | H | 5 | 982 | 0.0 | 8.0 | 0.000 |  |
| t735 | CH_noTS | 5 | 748 | 75.6 | 0.0 | 0.000 |  |
| t736 | A | 5 | 841 | 244.0 | 52.5 | 0.000 | made S_A 12c6dd62a66a (5 regions) |
| t736 | B | 5 | 600 | 0.0 | 59.5 | 0.000 | made S_B d33f89ad4bb2 (5 regions) |
| t736 | C | 5 | 841 | 0.0 | 84.0 | 0.000 | replays S_A 12c6dd62a66a: exact |
| t736 | D | 5 | 600 | 215.3 | 45.5 | 0.000 | replays S_B d33f89ad4bb2: exact |
| t736 | E | 8 | 1527 | 111.0 | 38.5 | 0.000 |  |
| t736 | F | 8 | 1548 | 0.0 | 76.5 | 0.000 |  |
| t736 | G | 7 | 1328 | 259.8 | 69.5 | 0.000 |  |
| t736 | H | 7 | 1328 | 0.0 | 71.5 | 0.000 |  |
| t736 | CH_noTS | 5 | 841 | 209.8 | 0.0 | 0.000 |  |
| p831 | A | 15 | 2598 | 810.1 | 389.5 | 0.000 | made S_A 85fd212eb34e (15 regions) |
| p831 | B | 10 | 1620 | 0.0 | 456.5 | 0.000 | made S_B cf642a121b0a (10 regions) |
| p831 | C | 15 | 2598 | 0.0 | 220.5 | 0.000 | replays S_A 85fd212eb34e: exact |
| p831 | D | 10 | 1620 | 1093.3 | 464.6 | 0.000 | replays S_B cf642a121b0a: exact |
| p831 | E | 31 | 5385 | 741.6 | 229.5 | 0.000 |  |
| p831 | F | 30 | 5294 | 0.0 | 517.0 | 0.000 |  |
| p831 | G | 12 | 2295 | 695.8 | 218.0 | 0.000 |  |
| p831 | H | 17 | 2743 | 0.0 | 313.0 | 0.000 |  |
| p831 | CH_noTS | 16 | 2763 | 541.7 | 0.0 | 0.000 |  |
| p832 | A | 14 | 2436 | 1017.0 | 481.5 | 0.000 | made S_A 40a7c0fe89d0 (14 regions) |
| p832 | B | 9 | 1446 | 0.0 | 508.4 | 0.000 | made S_B bb0f40035ee3 (9 regions) |
| p832 | C | 14 | 2436 | 0.0 | 476.5 | 0.000 | replays S_A 40a7c0fe89d0: exact |
| p832 | D | 9 | 1446 | 1028.6 | 539.5 | 0.000 | replays S_B bb0f40035ee3: exact |
| p832 | E | 32 | 5589 | 808.3 | 275.5 | 0.000 |  |
| p832 | F | 32 | 5671 | 0.0 | 252.5 | 0.000 |  |
| p832 | G | 19 | 3095 | 714.9 | 214.0 | 0.000 |  |
| p832 | H | 17 | 3025 | 0.0 | 248.5 | 0.000 |  |
| p832 | CH_noTS | 15 | 2520 | 568.5 | 0.0 | 0.000 |  |
| p833 | A | 15 | 2601 | 830.5 | 305.0 | 0.000 | made S_A faffe3714a83 (15 regions) |
| p833 | B | 8 | 1237 | 0.0 | 258.0 | 0.000 | made S_B 941dd992175b (8 regions) |
| p833 | C | 15 | 2601 | 0.0 | 371.5 | 0.000 | replays S_A faffe3714a83: exact |
| p833 | D | 8 | 1237 | 900.1 | 389.5 | 0.000 | replays S_B 941dd992175b: exact |
| p833 | E | 32 | 5586 | 717.5 | 252.5 | 0.000 |  |
| p833 | F | 32 | 5569 | 0.0 | 309.0 | 0.000 |  |
| p833 | G | 13 | 2410 | 812.8 | 350.5 | 0.000 |  |
| p833 | H | 13 | 2367 | 0.0 | 316.5 | 0.000 |  |
| p833 | CH_noTS | 17 | 2722 | 436.0 | 0.0 | 0.000 |  |
| p834 | A | 18 | 3143 | 425.0 | 44.0 | 0.000 | made S_A 75a6ed8750df (18 regions) |
| p834 | B | 6 | 922 | 0.0 | 54.0 | 0.000 | made S_B 1a09128e4025 (6 regions) |
| p834 | C | 18 | 3143 | 0.0 | 125.0 | 0.000 | replays S_A 75a6ed8750df: exact |
| p834 | D | 6 | 922 | 636.0 | 42.0 | 0.000 | replays S_B 1a09128e4025: exact |
| p834 | E | 32 | 6060 | 802.0 | 185.5 | 0.000 |  |
| p834 | F | 32 | 6025 | 0.0 | 218.0 | 0.000 |  |
| p834 | G | 22 | 3732 | 482.7 | 117.0 | 0.000 |  |
| p834 | H | 23 | 3509 | 0.0 | 39.0 | 0.000 |  |
| p834 | CH_noTS | 18 | 3143 | 571.1 | 0.0 | 0.000 |  |
| p835 | A | 14 | 2419 | 1279.5 | 290.0 | 0.000 | made S_A 84e1dbe45143 (14 regions) |
| p835 | B | 10 | 1460 | 0.0 | 274.0 | 0.000 | made S_B 936cc9b592e2 (10 regions) |
| p835 | C | 14 | 2419 | 0.0 | 276.0 | 0.000 | replays S_A 84e1dbe45143: exact |
| p835 | D | 10 | 1460 | 961.8 | 218.5 | 0.000 | replays S_B 936cc9b592e2: exact |
| p835 | E | 32 | 5426 | 993.4 | 115.0 | 0.000 |  |
| p835 | F | 28 | 5370 | 0.0 | 144.5 | 0.000 |  |
| p835 | G | 16 | 2852 | 1156.2 | 191.0 | 0.000 |  |
| p835 | H | 17 | 3025 | 0.0 | 230.0 | 0.000 |  |
| p835 | CH_noTS | 15 | 2444 | 1135.9 | 0.0 | 0.000 |  |
| p836 | A | 14 | 2456 | 946.3 | 183.0 | 0.000 | made S_A cc4471773993 (14 regions) |
| p836 | B | 10 | 1471 | 0.0 | 151.0 | 0.000 | made S_B 83e4343dd533 (10 regions) |
| p836 | C | 14 | 2456 | 0.0 | 238.5 | 0.000 | replays S_A cc4471773993: exact |
| p836 | D | 10 | 1471 | 1298.9 | 287.5 | 0.000 | replays S_B 83e4343dd533: exact |
| p836 | E | 32 | 5765 | 1203.2 | 343.5 | 0.000 |  |
| p836 | F | 32 | 5685 | 0.0 | 113.5 | 0.000 |  |
| p836 | G | 16 | 2924 | 1136.6 | 277.0 | 0.000 |  |
| p836 | H | 15 | 2736 | 0.0 | 119.0 | 0.000 |  |
| p836 | CH_noTS | 14 | 2442 | 1014.3 | 0.0 | 0.000 |  |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw1_p1_wage_money: Money credited to households over S_A, wealth units: wages + remittances - farm income replaced (A - C: the wage at A's enrollment) | t | 731: +264.6; 732: -138.6; 733: +120.5; 734: not activated; 735: +320.4; 736: +282.9 | +170 [-138.6, +320.4] | 4 / 1 / 0 | 6/32 as extreme; means [-225.4, +225.4] |
| cw1_p1_wage_money: Money credited to households over S_A, wealth units: wages + remittances - farm income replaced (A - C: the wage at A's enrollment) | p | 831: +486.1; 832: +645.4; 833: +774.4; 834: +922.4; 835: +1015; 836: +775.4 | +769.7 [+486.1, +1015] | 6 / 0 / 0 | 2/64 as extreme; means [-769.7, +769.7] |
| cw1_p2_enrollment_money: Money credited to households, world, wealth units (C - B: A's enrollment against B's, no wage) | t | 731: -500.7; 732: -616.1; 733: -346; 734: not activated; 735: -917.7; 736: -636.2 | -603.3 [-917.7, -346] | 0 / 5 / 0 | 2/32 as extreme; means [-603.3, +603.3] |
| cw1_p2_enrollment_money: Money credited to households, world, wealth units (C - B: A's enrollment against B's, no wage) | p | 831: -1666; 832: -1655; 833: -2574; 834: -4367; 835: -1079; 836: -1564 | -2151 [-4367, -1079] | 0 / 6 / 0 | 2/64 as extreme; means [-2151, +2151] |
| cw1_p3_wage_priced_out: Priced-out person-turns per pilot person-turn over S_A (A - C) | t | 731: +3.606e-05; 732: +0.002916; 733: -0.0001044; 734: not activated; 735: -0.0003302; 736: -0.0001539 | +0.0004727 [-0.0003302, +0.002916] | 2 / 3 / 0 | 30/32 as extreme; means [-0.0007081, +0.0007081] |
| cw1_p3_wage_priced_out: Priced-out person-turns per pilot person-turn over S_A (A - C) | p | 831: +0.0001766; 832: +0.0002324; 833: -0.0008161; 834: +0.004158; 835: -0.0004539; 836: -9.782e-05 | +0.0005331 [-0.0008161, +0.004158] | 3 / 3 / 0 | 52/64 as extreme; means [-0.0009891, +0.0009891] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw1_sa_money_world: Money credited to households, world (A - C) | t | 731: +269.7; 732: -166.6; 733: +170; 734: not activated; 735: +321.6; 736: +274.1 | +173.8 [-166.6, +321.6] | 4 / 1 / 0 | 4/32 as extreme; means [-240.4, +240.4] |
| cw1_sa_money_world: Money credited to households, world (A - C) | p | 831: +389.6; 832: +589.4; 833: +797.4; 834: +915.4; 835: +1074; 836: +803.1 | +761.6 [+389.6, +1074] | 6 / 0 / 0 | 2/64 as extreme; means [-761.6, +761.6] |
| cw1_sa_wages: Wages credited, world, all wage channels (A - C) | t | 731: +185.2; 732: +83.71; 733: +176.2; 734: not activated; 735: +91.8; 736: +217.9 | +151 [+83.71, +217.9] | 5 / 0 / 0 | 2/32 as extreme; means [-151, +151] |
| cw1_sa_wages: Wages credited, world, all wage channels (A - C) | p | 831: +967.5; 832: +1024; 833: +758.2; 834: +344.1; 835: +1302; 836: +866.1 | +876.9 [+344.1, +1302] | 6 / 0 / 0 | 2/64 as extreme; means [-876.9, +876.9] |
| cw1_sa_granary_wages: Granary crew wages credited, world (A - C) | t | 731: +222.5; 732: +93.36; 733: +172.9; 734: not activated; 735: +112; 736: +244 | +168.9 [+93.36, +244] | 5 / 0 / 0 | 2/32 as extreme; means [-168.9, +168.9] |
| cw1_sa_granary_wages: Granary crew wages credited, world (A - C) | p | 831: +810.1; 832: +1017; 833: +830.5; 834: +425; 835: +1279; 836: +946.3 | +884.7 [+425, +1279] | 6 / 0 / 0 | 2/64 as extreme; means [-884.7, +884.7] |
| cw1_sa_remittances: Remittances credited, world (A - C) | t | 731: -17.13; 732: +48.23; 733: +43.75; 734: not activated; 735: +18.64; 736: +14.29 | +21.55 [-17.13, +48.23] | 4 / 1 / 0 | 6/32 as extreme; means [-28.41, +28.41] |
| cw1_sa_remittances: Remittances credited, world (A - C) | p | 831: +324; 832: +75.11; 833: +216.2; 834: +7.315; 835: -50.98; 836: -50.92 | +86.78 [-50.98, +324] | 4 / 2 / 0 | 18/64 as extreme; means [-120.7, +120.7] |
| cw1_sa_procurement: Procurement credited, world (A - C) | t | 731: -7; 732: -11; 733: +2; 734: not activated; 735: +1; 736: -4 | -3.8 [-11, +2] | 2 / 3 / 0 | 8/32 as extreme; means [-5, +5] |
| cw1_sa_procurement: Procurement credited, world (A - C) | p | 831: -16; 832: +4; 833: -1; 834: -1; 835: -3; 836: +1 | -2.667 [-16, +4] | 2 / 4 / 0 | 38/64 as extreme; means [-4.333, +4.333] |
| cw1_sa_income_replaced: Farm income replaced over S_A (A - C) | t | 731: -108.7; 732: +287.5; 733: +51.97; 734: not activated; 735: -210.1; 736: -45.87 | -5.046 [-210.1, +287.5] | 2 / 3 / 0 | 32/32 as extreme; means [-140.9, +140.9] |
| cw1_sa_income_replaced: Farm income replaced over S_A (A - C) | p | 831: +885.8; 832: +513.4; 833: +176; 834: -565; 835: +173.4; 836: +13.05 | +199.4 [-565, +885.8] | 5 / 1 / 0 | 22/64 as extreme; means [-387.8, +387.8] |
| cw1_sa_priced_out: Priced-out person-turns over S_A (A - C) | t | 731: +1; 732: +76; 733: -2; 734: not activated; 735: -11; 736: -4 | +12 [-11, +76] | 2 / 3 / 0 | 30/32 as extreme; means [-18.8, +18.8] |
| cw1_sa_priced_out: Priced-out person-turns over S_A (A - C) | p | 831: +17; 832: +18; 833: -52; 834: +344; 835: -37; 836: -6 | +47.33 [-52, +344] | 3 / 3 / 0 | 52/64 as extreme; means [-79, +79] |
| cw1_sa_ration: Mean ration per pilot person-turn over S_A (A - C) | t | 731: -0.0223; 732: -0.01259; 733: -0.02921; 734: not activated; 735: +0.003902; 736: -0.002984 | -0.01264 [-0.02921, +0.003902] | 1 / 4 / 0 | 6/32 as extreme; means [-0.0142, +0.0142] |
| cw1_sa_ration: Mean ration per pilot person-turn over S_A (A - C) | p | 831: -0.0258; 832: -0.009526; 833: -0.0035; 834: +0.0008261; 835: -0.007148; 836: -0.01946 | -0.01077 [-0.0258, +0.0008261] | 1 / 5 / 0 | 4/64 as extreme; means [-0.01104, +0.01104] |
| cw1_sb_money: Money credited to households over S_B (D - B: the wage at B's enrollment) | t | 731: +302.7; 732: +153.8; 733: +170.3; 734: not activated; 735: +443.7; 736: +204.5 | +255 [+153.8, +443.7] | 5 / 0 / 0 | 2/32 as extreme; means [-255, +255] |
| cw1_sb_money: Money credited to households over S_B (D - B: the wage at B's enrollment) | p | 831: +934.5; 832: +800.5; 833: +598; 834: +142.8; 835: +641.3; 836: +1515 | +772.1 [+142.8, +1515] | 6 / 0 / 0 | 2/64 as extreme; means [-772.1, +772.1] |
| cw1_sb_priced_out: Priced-out person-turns per pilot person-turn over S_B (D - B) | t | 731: +0.0001654; 732: +0; 733: +0; 734: not activated; 735: -0.0008186; 736: +0.0002764 | -7.538e-05 [-0.0008186, +0.0002764] | 2 / 1 / 2 | 32/32 as extreme; means [-0.0002521, +0.0002521] |
| cw1_sb_priced_out: Priced-out person-turns per pilot person-turn over S_B (D - B) | p | 831: +1.552e-06; 832: -0.0001304; 833: +0.000171; 834: +0; 835: -9.32e-05; 836: +4.161e-05 | -1.559e-06 [-0.0001304, +0.000171] | 3 / 2 / 1 | 64/64 as extreme; means [-7.296e-05, +7.296e-05] |
| cw1_interaction_money: Money credited over each schedule's set: (A - C) - (D - B) | t | 731: -38.13; 732: -292.4; 733: -49.87; 734: not activated; 735: -123.3; 736: +78.39 | -85.06 [-292.4, +78.39] | 1 / 4 / 0 | 8/32 as extreme; means [-116.4, +116.4] |
| cw1_interaction_money: Money credited over each schedule's set: (A - C) - (D - B) | p | 831: -448.4; 832: -155; 833: +176.4; 834: +779.6; 835: +373.4; 836: -740.1 | -2.344 [-740.1, +779.6] | 3 / 3 / 0 | 64/64 as extreme; means [-445.5, +445.5] |
| cw1_interaction_priced_out: Priced-out person-turns per pilot person-turn over each schedule's set: (A - C) - (D - B) | t | 731: -0.0001293; 732: +0.002916; 733: -0.0001044; 734: not activated; 735: +0.0004884; 736: -0.0004303 | +0.000548 [-0.0004303, +0.002916] | 2 / 3 / 0 | 22/32 as extreme; means [-0.0008136, +0.0008136] |
| cw1_interaction_priced_out: Priced-out person-turns per pilot person-turn over each schedule's set: (A - C) - (D - B) | p | 831: +0.000175; 832: +0.0003627; 833: -0.0009872; 834: +0.004158; 835: -0.0003607; 836: -0.0001394 | +0.0005347 [-0.0009872, +0.004158] | 3 / 3 / 0 | 46/64 as extreme; means [-0.00103, +0.00103] |
| cw1_all_money: Money credited to households, world (E - F: the wage at the all boundary) | t | 731: +711; 732: +348.2; 733: +349.9; 734: not activated; 735: +445.1; 736: +54.11 | +381.7 [+54.11, +711] | 5 / 0 / 0 | 2/32 as extreme; means [-381.7, +381.7] |
| cw1_all_money: Money credited to households, world (E - F: the wage at the all boundary) | p | 831: +208.6; 832: +869.6; 833: +1132; 834: +1047; 835: +1243; 836: +1978 | +1080 [+208.6, +1978] | 6 / 0 / 0 | 2/64 as extreme; means [-1080, +1080] |
| cw1_all_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (E - F) | t | 731: +0.0008178; 732: -0.0003648; 733: -0.001286; 734: not activated; 735: -0.003624; 736: -0.002781 | -0.001448 [-0.003624, +0.0008178] | 1 / 4 / 0 | 6/32 as extreme; means [-0.001775, +0.001775] |
| cw1_all_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (E - F) | p | 831: -0.003494; 832: -0.001054; 833: -0.007464; 834: -0.005402; 835: -0.00061; 836: -0.002315 | -0.00339 [-0.007464, -0.00061] | 0 / 6 / 0 | 2/64 as extreme; means [-0.00339, +0.00339] |
| cw1_all_ration: Mean ration per pilot person-turn (E - F) | t | 731: +0.01509; 732: +0.007433; 733: +0.03329; 734: not activated; 735: -0.005736; 736: +0.003526 | +0.01072 [-0.005736, +0.03329] | 4 / 1 / 0 | 6/32 as extreme; means [-0.01302, +0.01302] |
| cw1_all_ration: Mean ration per pilot person-turn (E - F) | p | 831: +0.001481; 832: -1.803e-05; 833: +0.01375; 834: +0.01203; 835: +0.003916; 836: -0.009076 | +0.003682 [-0.009076, +0.01375] | 4 / 2 / 0 | 20/64 as extreme; means [-0.006713, +0.006713] |
| cw1_mkt_money: Money credited to households, world (G - H: the wage at the market boundary) | t | 731: -215.4; 732: +582; 733: +132; 734: not activated; 735: +102.6; 736: +577.9 | +235.8 [-215.4, +582] | 4 / 1 / 0 | 8/32 as extreme; means [-322, +322] |
| cw1_mkt_money: Money credited to households, world (G - H: the wage at the market boundary) | p | 831: +1880; 832: +226.5; 833: +1246; 834: +366.3; 835: +551.3; 836: +1005 | +879.3 [+226.5, +1880] | 6 / 0 / 0 | 2/64 as extreme; means [-879.3, +879.3] |
| cw1_mkt_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (G - H) | t | 731: +1.767e-05; 732: -0.001244; 733: -0.002968; 734: not activated; 735: +0.001543; 736: +0.001342 | -0.0002621 [-0.002968, +0.001543] | 3 / 2 / 0 | 28/32 as extreme; means [-0.001423, +0.001423] |
| cw1_mkt_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (G - H) | p | 831: -0.0004673; 832: -0.0007809; 833: +0.0007029; 834: -0.001376; 835: -0.000114; 836: +1.937e-05 | -0.000336 [-0.001376, +0.0007029] | 2 / 4 / 0 | 20/64 as extreme; means [-0.0005768, +0.0005768] |
| cw1_total_money: Money credited to households, world (A - B: CP3's CH - CH_unpaid) | t | 731: -231; 732: -782.7; 733: -176; 734: not activated; 735: -596.1; 736: -362.1 | -429.6 [-782.7, -176] | 0 / 5 / 0 | 2/32 as extreme; means [-429.6, +429.6] |
| cw1_total_money: Money credited to households, world (A - B: CP3's CH - CH_unpaid) | p | 831: -1277; 832: -1066; 833: -1776; 834: -3452; 835: -4.283; 836: -760.9 | -1389 [-3452, -4.283] | 0 / 6 / 0 | 2/64 as extreme; means [-1389, +1389] |
| cw1_total_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (A - B) | t | 731: +2.17e-05; 732: +0.002995; 733: +4.464e-05; 734: not activated; 735: -0.0009879; 736: +0 | +0.0004146 [-0.0009879, +0.002995] | 3 / 1 / 1 | 20/32 as extreme; means [-0.0008098, +0.0008098] |
| cw1_total_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (A - B) | p | 831: +0.0003401; 832: +0.0002337; 833: +0.00153; 834: +0.005055; 835: -4.779e-05; 836: +0.000145 | +0.001209 [-4.779e-05, +0.005055] | 5 / 1 / 0 | 4/64 as extreme; means [-0.001225, +0.001225] |
| cw1_coverage_enrollment: Coverage: pilot region-turns per region-turn (C - B) | t | 731: +0.2213; 732: +0.2712; 733: +0.2188; 734: not activated; 735: +0.2725; 736: +0.1506 | +0.2269 [+0.1506, +0.2725] | 5 / 0 / 0 | 2/32 as extreme; means [-0.2269, +0.2269] |
| cw1_coverage_enrollment: Coverage: pilot region-turns per region-turn (C - B) | p | 831: +0.1528; 832: +0.1547; 833: +0.2131; 834: +0.347; 835: +0.1498; 836: +0.1539 | +0.1952 [+0.1498, +0.347] | 6 / 0 / 0 | 2/64 as extreme; means [-0.1952, +0.1952] |
| cw1_coverage_total: Coverage: pilot region-turns per region-turn (A - B) | t | 731: +0.2213; 732: +0.2712; 733: +0.2188; 734: not activated; 735: +0.2725; 736: +0.1506 | +0.2269 [+0.1506, +0.2725] | 5 / 0 / 0 | 2/32 as extreme; means [-0.2269, +0.2269] |
| cw1_coverage_total: Coverage: pilot region-turns per region-turn (A - B) | p | 831: +0.1528; 832: +0.1547; 833: +0.2131; 834: +0.347; 835: +0.1498; 836: +0.1539 | +0.1952 [+0.1498, +0.347] | 6 / 0 / 0 | 2/64 as extreme; means [-0.1952, +0.1952] |
| cw1_enrollment_priced_out: Priced-out person-turns, world (C - B; only pilot regions price anyone out) | t | 731: +0; 732: +2; 733: +3; 734: not activated; 735: +0; 736: +4 | +1.8 [+0, +4] | 3 / 0 / 2 | 8/32 as extreme; means [-1.8, +1.8] |
| cw1_enrollment_priced_out: Priced-out person-turns, world (C - B; only pilot regions price anyone out) | p | 831: +13; 832: +4; 833: +155; 834: +76; 835: +41; 836: +16 | +50.83 [+4, +155] | 6 / 0 / 0 | 2/64 as extreme; means [-50.83, +50.83] |
| cw1_enrollment_income_replaced: Farm income replaced, world (C - B) | t | 731: +169.2; 732: +316.9; 733: +206.2; 734: not activated; 735: +694.3; 736: +401.2 | +357.6 [+169.2, +694.3] | 5 / 0 / 0 | 2/32 as extreme; means [-357.6, +357.6] |
| cw1_enrollment_income_replaced: Farm income replaced, world (C - B) | p | 831: +1123; 832: +1461; 833: +2318; 834: +3999; 835: +1094; 836: +1096 | +1848 [+1094, +3999] | 6 / 0 / 0 | 2/64 as extreme; means [-1848, +1848] |
| cw1_rl5_sa_crew_rate: RL5 crew households (members and co-resident children): priced-out person-turns per person-turn (A - C) | t | 731: +0; 732: +0; 733: +0; 734: not activated; 735: +0; 736: +0 | +0 [+0, +0] | 0 / 0 / 5 | 32/32 as extreme; means [+0, +0] |
| cw1_rl5_sa_crew_rate: RL5 crew households (members and co-resident children): priced-out person-turns per person-turn (A - C) | p | 831: +0; 832: +0; 833: +0; 834: +0; 835: +0; 836: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] |
| cw1_rl5_sa_nonfarm_rate: RL5 non-farm adults: priced-out person-turns per person-turn (A - C) | t | 731: +9.607e-05; 732: +0.007304; 733: -0.0001551; 734: not activated; 735: -0.001005; 736: -0.0003191 | +0.001184 [-0.001005, +0.007304] | 2 / 3 / 0 | 30/32 as extreme; means [-0.001776, +0.001776] |
| cw1_rl5_sa_nonfarm_rate: RL5 non-farm adults: priced-out person-turns per person-turn (A - C) | p | 831: +0.0002742; 832: +0.0009054; 833: -0.002243; 834: +0.009633; 835: -0.001568; 836: +0.0001315 | +0.001189 [-0.002243, +0.009633] | 4 / 2 / 0 | 50/64 as extreme; means [-0.002459, +0.002459] |
| cw1_rl5_sa_children_alone_rate: RL5 children without a co-resident adult: priced-out person-turns per person-turn (A - C) | t | 731: +0; 732: +0.0001395; 733: -0.001511; 734: not activated; 735: +0.0004455; 736: -0.0007564 | -0.0003364 [-0.001511, +0.0004455] | 2 / 2 / 1 | 16/32 as extreme; means [-0.0005704, +0.0005704] |
| cw1_rl5_sa_children_alone_rate: RL5 children without a co-resident adult: priced-out person-turns per person-turn (A - C) | p | 831: +0.000458; 832: +0; 833: +0.0007994; 834: +0.0007655; 835: -0.0008579; 836: -0.001262 | -1.618e-05 [-0.001262, +0.0007994] | 3 / 2 / 1 | 56/64 as extreme; means [-0.0006905, +0.0006905] |
| cw1_rl5_sb_crew_rate: RL5 crew households (members and co-resident children): priced-out person-turns per person-turn (D - B) | t | 731: +0; 732: +0; 733: +0; 734: not activated; 735: +0; 736: +0 | +0 [+0, +0] | 0 / 0 / 5 | 32/32 as extreme; means [+0, +0] |
| cw1_rl5_sb_crew_rate: RL5 crew households (members and co-resident children): priced-out person-turns per person-turn (D - B) | p | 831: +0; 832: -0.0004476; 833: +0; 834: +0; 835: +0; 836: +0 | -7.46e-05 [-0.0004476, +0] | 0 / 1 / 5 | 64/64 as extreme; means [-7.46e-05, +7.46e-05] |
| cw1_rl5_sb_nonfarm_rate: RL5 non-farm adults: priced-out person-turns per person-turn (D - B) | t | 731: +0.0001403; 732: +0; 733: +0; 734: not activated; 735: -0.002217; 736: +0.0007499 | -0.0002653 [-0.002217, +0.0007499] | 2 / 1 / 2 | 32/32 as extreme; means [-0.0006214, +0.0006214] |
| cw1_rl5_sb_nonfarm_rate: RL5 non-farm adults: priced-out person-turns per person-turn (D - B) | p | 831: +6.152e-05; 832: -0.0004436; 833: +0.0004677; 834: +0; 835: -0.0006657; 836: +3.077e-05 | -9.153e-05 [-0.0006657, +0.0004677] | 3 / 2 / 1 | 48/64 as extreme; means [-0.0002782, +0.0002782] |
| cw1_rl5_sb_children_alone_rate: RL5 children without a co-resident adult: priced-out person-turns per person-turn (D - B) | t | 731: +0.0007645; 732: +0; 733: +0; 734: not activated; 735: +0.001838; 736: +0 | +0.0005205 [+0, +0.001838] | 2 / 0 / 3 | 16/32 as extreme; means [-0.0005205, +0.0005205] |
| cw1_rl5_sb_children_alone_rate: RL5 children without a co-resident adult: priced-out person-turns per person-turn (D - B) | p | 831: +0; 832: +0.0005266; 833: -0.0004502; 834: +0; 835: +0.001486; 836: +0.0003111 | +0.0003122 [-0.0004502, +0.001486] | 3 / 1 / 2 | 24/64 as extreme; means [-0.0004622, +0.0004622] |
| cw1_rl5_sa_crew_count: RL5 crew households: priced-out person-turns (A - C) | t | 731: +0; 732: +0; 733: +0; 734: not activated; 735: +0; 736: +0 | +0 [+0, +0] | 0 / 0 / 5 | 32/32 as extreme; means [+0, +0] |
| cw1_rl5_sa_crew_count: RL5 crew households: priced-out person-turns (A - C) | p | 831: +0; 832: unknown; 833: +0; 834: +0; 835: +0; 836: +0 | +0 [+0, +0] | 0 / 0 / 5 | 32/32 as extreme; means [+0, +0] |
| cw1_rl5_sa_nonfarm_count: RL5 non-farm adults: priced-out person-turns (A - C) | t | 731: +1; 732: +72; 733: +0; 734: not activated; 735: -11; 736: -3 | +11.8 [-11, +72] | 2 / 2 / 1 | 28/32 as extreme; means [-17.4, +17.4] |
| cw1_rl5_sa_nonfarm_count: RL5 non-farm adults: priced-out person-turns (A - C) | p | 831: +12; 832: unknown; 833: -55; 834: +324; 835: -33; 836: +1 | +49.8 [-55, +324] | 3 / 2 / 0 | 26/32 as extreme; means [-85, +85] |
| cw1_rl5_sa_children_alone_count: RL5 children without a co-resident adult: priced-out person-turns (A - C) | t | 731: +0; 732: +0; 733: -2; 734: not activated; 735: +1; 736: -1 | -0.4 [-2, +1] | 1 / 2 / 2 | 24/32 as extreme; means [-0.8, +0.8] |
| cw1_rl5_sa_children_alone_count: RL5 children without a co-resident adult: priced-out person-turns (A - C) | p | 831: +6; 832: unknown; 833: +7; 834: +12; 835: -4; 836: -8 | +2.6 [-8, +12] | 3 / 2 / 0 | 18/32 as extreme; means [-7.4, +7.4] |
| cw1_nots_money: Money credited to households, world (CH_noTS - A) | t | 731: -81.2; 732: +374.1; 733: +177.9; 734: not activated; 735: +298.7; 736: -203.4 | +113.2 [-203.4, +374.1] | 3 / 2 / 0 | 12/32 as extreme; means [-227.1, +227.1] |
| cw1_nots_money: Money credited to households, world (CH_noTS - A) | p | 831: -819.3; 832: -1385; 833: -1941; 834: -246.5; 835: -235.3; 836: -43.26 | -778.4 [-1941, -43.26] | 0 / 6 / 0 | 2/64 as extreme; means [-778.4, +778.4] |
| cw1_nots_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (CH_noTS - A) | t | 731: +0.0004107; 732: -0.002922; 733: -4.464e-05; 734: not activated; 735: +0.0009893; 736: +0.0004586 | -0.0002215 [-0.002922, +0.0009893] | 3 / 2 / 0 | 30/32 as extreme; means [-0.000965, +0.000965] |
| cw1_nots_priced_out: Priced-out person-turns per pilot person-turn, each arm's own enrollment (CH_noTS - A) | p | 831: -2.703e-05; 832: +0.0002079; 833: +0.0008305; 834: -0.003456; 835: -0.0001125; 836: +6.116e-05 | -0.000416 [-0.003456, +0.0008305] | 3 / 3 / 0 | 54/64 as extreme; means [-0.0007826, +0.0007826] |
| cw1_nots_coverage: Coverage (CH_noTS - A) | t | 731: +0; 732: -0.1088; 733: -0.04688; 734: not activated; 735: -0.1362; 736: +0 | -0.05838 [-0.1362, +0] | 0 / 3 / 2 | 8/32 as extreme; means [-0.05838, +0.05838] |
| cw1_nots_coverage: Coverage (CH_noTS - A) | p | 831: +0.02578; 832: +0.01312; 833: +0.01891; 834: +0; 835: +0.003906; 836: -0.002187 | +0.009922 [-0.002187, +0.02578] | 4 / 1 / 1 | 8/64 as extreme; means [-0.01065, +0.01065] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A - C | Population at the end (sum over civilizations) | t | 731: -47; 732: +18; 733: +42; 734: not activated; 735: -27; 736: -28 | -8.4 [-47, +42] | 2 / 3 / 0 | 20/32 as extreme; means [-32.4, +32.4] | recorded |
| A - C | Population at the end (sum over civilizations) | p | 831: +92; 832: +2; 833: +3; 834: -69; 835: -49; 836: -106 | -21.17 [-106, +92] | 3 / 3 / 0 | 32/64 as extreme; means [-53.5, +53.5] | recorded |
| A - C | Treasury at the end (sum over civilizations) | t | 731: -27; 732: +835; 733: -178; 734: not activated; 735: -255; 736: -283 | +18.4 [-283, +835] | 1 / 4 / 0 | 32/32 as extreme; means [-315.6, +315.6] | recorded |
| A - C | Treasury at the end (sum over civilizations) | p | 831: +86; 832: +1628; 833: -1036; 834: +1518; 835: +699; 836: -1805 | +181.7 [-1805, +1628] | 4 / 2 / 0 | 50/64 as extreme; means [-1129, +1129] | recorded |
| A - C | Food shortfall after relief over the run (food) | t | 731: +278.4; 732: +190.1; 733: +592.7; 734: not activated; 735: -183.4; 736: -443 | +86.95 [-443, +592.7] | 3 / 2 / 0 | 20/32 as extreme; means [-337.5, +337.5] | recorded |
| A - C | Food shortfall after relief over the run (food) | p | 831: +1405; 832: +711.9; 833: +339.2; 834: -561.1; 835: -104.1; 836: +776.2 | +427.9 [-561.1, +1405] | 4 / 2 / 0 | 12/64 as extreme; means [-649.6, +649.6] | recorded |
| A - C | Priced-out person-turns | t | 731: +1; 732: +76; 733: -2; 734: not activated; 735: -11; 736: -4 | +12 [-11, +76] | 2 / 3 / 0 | 30/32 as extreme; means [-18.8, +18.8] | recorded |
| A - C | Priced-out person-turns | p | 831: +17; 832: +18; 833: -52; 834: +344; 835: -37; 836: -6 | +47.33 [-52, +344] | 3 / 3 / 0 | 52/64 as extreme; means [-79, +79] | recorded |
| A - C | Priced-out child-turns | t | 731: +1; 732: +3; 733: -2; 734: not activated; 735: +0; 736: -1 | +0.2 [-2, +3] | 2 / 2 / 1 | 32/32 as extreme; means [-1.4, +1.4] | recorded |
| A - C | Priced-out child-turns | p | 831: +5; 832: -1; 833: +2; 834: +16; 835: -4; 836: -7 | +1.833 [-7, +16] | 3 / 3 / 0 | 46/64 as extreme; means [-5.833, +5.833] | recorded |
| A - C | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| A - C | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| A - C | Deaths by epidemic (the epidemic authority) | t | 731: +44; 732: -1; 733: +19; 734: not activated; 735: -1; 736: -8 | +10.6 [-8, +44] | 2 / 3 / 0 | 16/32 as extreme; means [-14.6, +14.6] | recorded |
| A - C | Deaths by epidemic (the epidemic authority) | p | 831: -304; 832: +138; 833: -7; 834: +39; 835: -92; 836: +354 | +21.33 [-304, +354] | 3 / 3 / 0 | 52/64 as extreme; means [-155.7, +155.7] | recorded |
| A - C | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| A - C | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| A - C | Agents migrating between regions over the run | t | 731: -88; 732: -132; 733: +356; 734: not activated; 735: +93; 736: -32 | +39.4 [-132, +356] | 2 / 3 / 0 | 26/32 as extreme; means [-140.2, +140.2] | recorded |
| A - C | Agents migrating between regions over the run | p | 831: +1262; 832: +688; 833: -19; 834: -181; 835: +13; 836: +1095 | +476.3 [-181, +1262] | 4 / 2 / 0 | 14/64 as extreme; means [-543, +543] | recorded |
| A - C | Mean wealth Gini of living civilizations at the end | t | 731: +0.02937; 732: +0.05423; 733: +0.01492; 734: not activated; 735: +0.01893; 736: -0.008862 | +0.02172 [-0.008862, +0.05423] | 4 / 1 / 0 | 4/32 as extreme; means [-0.02526, +0.02526] | recorded |
| A - C | Mean wealth Gini of living civilizations at the end | p | 831: -0.02566; 832: -0.1056; 833: +0.0587; 834: -0.1415; 835: +0.03003; 836: -0.1705 | -0.05908 [-0.1705, +0.0587] | 2 / 4 / 0 | 14/64 as extreme; means [-0.08866, +0.08866] | recorded |
| A - C | Timber stand share of capacity at the end | t | 731: -0.0007712; 732: +0.007099; 733: +0.08265; 734: not activated; 735: +4.749e-05; 736: -0.2535 | -0.03289 [-0.2535, +0.08265] | 3 / 2 / 0 | 28/32 as extreme; means [-0.06881, +0.06881] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| A - C | Timber stand share of capacity at the end | p | 831: -0.05604; 832: -0.0311; 833: -0.08903; 834: -0.08047; 835: -0.1115; 836: -0.1859 | -0.09235 [-0.1859, -0.0311] | 0 / 6 / 0 | 2/64 as extreme; means [-0.09235, +0.09235] | recorded |
| C - B | Population at the end (sum over civilizations) | t | 731: -10; 732: +7; 733: -24; 734: not activated; 735: +6; 736: -22 | -8.6 [-24, +7] | 2 / 3 / 0 | 10/32 as extreme; means [-13.8, +13.8] | recorded |
| C - B | Population at the end (sum over civilizations) | p | 831: -39; 832: +5; 833: -60; 834: -151; 835: +90; 836: -90 | -40.83 [-151, +90] | 2 / 4 / 0 | 20/64 as extreme; means [-72.5, +72.5] | recorded |
| C - B | Treasury at the end (sum over civilizations) | t | 731: -50; 732: -35; 733: +587; 734: not activated; 735: -497; 736: -3 | +0.4 [-497, +587] | 1 / 4 / 0 | 32/32 as extreme; means [-234.4, +234.4] | recorded |
| C - B | Treasury at the end (sum over civilizations) | p | 831: -70; 832: -1536; 833: -1019; 834: -1943; 835: -145; 836: -1215 | -988 [-1943, -70] | 0 / 6 / 0 | 2/64 as extreme; means [-988, +988] | recorded |
| C - B | Food shortfall after relief over the run (food) | t | 731: -226.8; 732: -150.1; 733: -1048; 734: not activated; 735: -754.2; 736: -127.2 | -461.2 [-1048, -127.2] | 0 / 5 / 0 | 2/32 as extreme; means [-461.2, +461.2] | recorded |
| C - B | Food shortfall after relief over the run (food) | p | 831: -902.9; 832: -142.2; 833: -1165; 834: -566.8; 835: +231.7; 836: -1440 | -664.3 [-1440, +231.7] | 1 / 5 / 0 | 6/64 as extreme; means [-741.6, +741.6] | recorded |
| C - B | Priced-out person-turns | t | 731: +0; 732: +2; 733: +3; 734: not activated; 735: +0; 736: +4 | +1.8 [+0, +4] | 3 / 0 / 2 | 8/32 as extreme; means [-1.8, +1.8] | recorded |
| C - B | Priced-out person-turns | p | 831: +13; 832: +4; 833: +155; 834: +76; 835: +41; 836: +16 | +50.83 [+4, +155] | 6 / 0 / 0 | 2/64 as extreme; means [-50.83, +50.83] | recorded |
| C - B | Priced-out child-turns | t | 731: +0; 732: +1; 733: +2; 734: not activated; 735: +0; 736: +1 | +0.8 [+0, +2] | 3 / 0 / 2 | 8/32 as extreme; means [-0.8, +0.8] | recorded |
| C - B | Priced-out child-turns | p | 831: +5; 832: +0; 833: +17; 834: +11; 835: +10; 836: +7 | +8.333 [+0, +17] | 5 / 0 / 1 | 4/64 as extreme; means [-8.333, +8.333] | recorded |
| C - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| C - B | Deaths by epidemic (the epidemic authority) | t | 731: -117; 732: -45; 733: +2; 734: not activated; 735: +82; 736: -30 | -21.6 [-117, +82] | 2 / 3 / 0 | 20/32 as extreme; means [-55.2, +55.2] | recorded |
| C - B | Deaths by epidemic (the epidemic authority) | p | 831: +109; 832: -184; 833: +63; 834: -82; 835: -70; 836: -95 | -43.17 [-184, +109] | 2 / 4 / 0 | 24/64 as extreme; means [-100.5, +100.5] | recorded |
| C - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| C - B | Agents migrating between regions over the run | t | 731: -229; 732: -396; 733: -408; 734: not activated; 735: -294; 736: -224 | -310.2 [-408, -224] | 0 / 5 / 0 | 2/32 as extreme; means [-310.2, +310.2] | recorded |
| C - B | Agents migrating between regions over the run | p | 831: -121; 832: -602; 833: -1010; 834: -1512; 835: -243; 836: -1183 | -778.5 [-1512, -121] | 0 / 6 / 0 | 2/64 as extreme; means [-778.5, +778.5] | recorded |
| C - B | Mean wealth Gini of living civilizations at the end | t | 731: -0.001478; 732: -0.09501; 733: -0.2014; 734: not activated; 735: -0.00724; 736: +0.01069 | -0.05888 [-0.2014, +0.01069] | 1 / 4 / 0 | 10/32 as extreme; means [-0.06316, +0.06316] | recorded |
| C - B | Mean wealth Gini of living civilizations at the end | p | 831: +0.03467; 832: +0.09997; 833: -0.07702; 834: -0.01468; 835: +0.02399; 836: -0.1767 | -0.0183 [-0.1767, +0.09997] | 3 / 3 / 0 | 46/64 as extreme; means [-0.07117, +0.07117] | recorded |
| C - B | Timber stand share of capacity at the end | t | 731: +0.009648; 732: +0.002758; 733: -0.09111; 734: not activated; 735: -0.014; 736: +0.1442 | +0.01029 [-0.09111, +0.1442] | 3 / 2 / 0 | 26/32 as extreme; means [-0.05233, +0.05233] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| C - B | Timber stand share of capacity at the end | p | 831: -0.01658; 832: +0.0744; 833: +0.005342; 834: -0.1264; 835: +0.0354; 836: +0.1501 | +0.02038 [-0.1264, +0.1501] | 4 / 2 / 0 | 38/64 as extreme; means [-0.06803, +0.06803] | recorded |
| D - B | Population at the end (sum over civilizations) | t | 731: -15; 732: -3; 733: +34; 734: not activated; 735: -50; 736: -17 | -10.2 [-50, +34] | 1 / 4 / 0 | 16/32 as extreme; means [-23.8, +23.8] | recorded |
| D - B | Population at the end (sum over civilizations) | p | 831: -73; 832: +68; 833: +44; 834: -106; 835: +136; 836: -109 | -6.667 [-109, +136] | 3 / 3 / 0 | 58/64 as extreme; means [-89.33, +89.33] | recorded |
| D - B | Treasury at the end (sum over civilizations) | t | 731: -111; 732: +231; 733: +1242; 734: not activated; 735: -609; 736: -129 | +124.8 [-609, +1242] | 2 / 3 / 0 | 26/32 as extreme; means [-464.4, +464.4] | recorded |
| D - B | Treasury at the end (sum over civilizations) | p | 831: -25; 832: -2064; 833: -3124; 834: +611; 835: +282; 836: -1563 | -980.5 [-3124, +611] | 2 / 4 / 0 | 14/64 as extreme; means [-1278, +1278] | recorded |
| D - B | Food shortfall after relief over the run (food) | t | 731: -464.6; 732: +299.1; 733: -476.6; 734: not activated; 735: -1331; 736: -548.4 | -504.2 [-1331, +299.1] | 1 / 4 / 0 | 4/32 as extreme; means [-623.9, +623.9] | recorded |
| D - B | Food shortfall after relief over the run (food) | p | 831: +532.5; 832: +104.5; 833: +1260; 834: -386.4; 835: -1084; 836: -1341 | -152.4 [-1341, +1260] | 3 / 3 / 0 | 50/64 as extreme; means [-784.7, +784.7] | recorded |
| D - B | Priced-out person-turns | t | 731: +4; 732: +0; 733: +0; 734: not activated; 735: -15; 736: +5 | -1.2 [-15, +5] | 2 / 1 / 2 | 32/32 as extreme; means [-4.8, +4.8] | recorded |
| D - B | Priced-out person-turns | p | 831: +0; 832: -6; 833: +6; 834: +0; 835: -4; 836: +1 | -0.5 [-6, +6] | 2 / 2 / 2 | 64/64 as extreme; means [-2.833, +2.833] | recorded |
| D - B | Priced-out child-turns | t | 731: +3; 732: +0; 733: +0; 734: not activated; 735: +0; 736: +0 | +0.6 [+0, +3] | 1 / 0 / 4 | 32/32 as extreme; means [-0.6, +0.6] | recorded |
| D - B | Priced-out child-turns | p | 831: +0; 832: +1; 833: -1; 834: +0; 835: +5; 836: +1 | +1 [-1, +5] | 3 / 1 / 2 | 32/64 as extreme; means [-1.333, +1.333] | recorded |
| D - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| D - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| D - B | Deaths by epidemic (the epidemic authority) | t | 731: +51; 732: -51; 733: +7; 734: not activated; 735: +51; 736: -25 | +6.6 [-51, +51] | 3 / 2 / 0 | 26/32 as extreme; means [-37, +37] | recorded |
| D - B | Deaths by epidemic (the epidemic authority) | p | 831: +209; 832: -148; 833: +54; 834: +96; 835: -258; 836: +55 | +1.333 [-258, +209] | 4 / 2 / 0 | 60/64 as extreme; means [-136.7, +136.7] | recorded |
| D - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| D - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| D - B | Agents migrating between regions over the run | t | 731: -247; 732: -157; 733: +12; 734: not activated; 735: -893; 736: -233 | -303.6 [-893, +12] | 1 / 4 / 0 | 4/32 as extreme; means [-308.4, +308.4] | recorded |
| D - B | Agents migrating between regions over the run | p | 831: +490; 832: -191; 833: +688; 834: -1034; 835: -1213; 836: -1088 | -391.3 [-1213, +688] | 2 / 4 / 0 | 18/64 as extreme; means [-784, +784] | recorded |
| D - B | Mean wealth Gini of living civilizations at the end | t | 731: +0.06322; 732: -0.01463; 733: -0.07578; 734: not activated; 735: +0.06143; 736: +0.04169 | +0.01519 [-0.07578, +0.06322] | 3 / 2 / 0 | 20/32 as extreme; means [-0.05135, +0.05135] | recorded |
| D - B | Mean wealth Gini of living civilizations at the end | p | 831: +0.03702; 832: +0.0836; 833: -0.02326; 834: +0.045; 835: -0.1732; 836: -0.1744 | -0.0342 [-0.1744, +0.0836] | 3 / 3 / 0 | 30/64 as extreme; means [-0.08941, +0.08941] | recorded |
| D - B | Timber stand share of capacity at the end | t | 731: +0.0123; 732: -0.02943; 733: +0.06877; 734: not activated; 735: -0.007014; 736: -0.1139 | -0.01386 [-0.1139, +0.06877] | 2 / 3 / 0 | 22/32 as extreme; means [-0.04629, +0.04629] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| D - B | Timber stand share of capacity at the end | p | 831: -0.06761; 832: -0.02824; 833: -0.005223; 834: -0.2188; 835: +0.1845; 836: +0.1808 | +0.007573 [-0.2188, +0.1845] | 2 / 4 / 0 | 64/64 as extreme; means [-0.1142, +0.1142] | recorded |
| E - F | Population at the end (sum over civilizations) | t | 731: -57; 732: -4; 733: -16; 734: not activated; 735: -51; 736: -6 | -26.8 [-57, -4] | 0 / 5 / 0 | 2/32 as extreme; means [-26.8, +26.8] | recorded |
| E - F | Population at the end (sum over civilizations) | p | 831: -32; 832: +32; 833: -86; 834: +36; 835: +42; 836: -70 | -13 [-86, +42] | 3 / 3 / 0 | 40/64 as extreme; means [-49.67, +49.67] | recorded |
| E - F | Treasury at the end (sum over civilizations) | t | 731: +248; 732: -453; 733: -442; 734: not activated; 735: -144; 736: -10 | -160.2 [-453, +248] | 1 / 4 / 0 | 10/32 as extreme; means [-259.4, +259.4] | recorded |
| E - F | Treasury at the end (sum over civilizations) | p | 831: -2690; 832: -281; 833: -63; 834: +1443; 835: -164; 836: -1328 | -513.8 [-2690, +1443] | 1 / 5 / 0 | 22/64 as extreme; means [-994.8, +994.8] | recorded |
| E - F | Food shortfall after relief over the run (food) | t | 731: -450.6; 732: -332.2; 733: -1049; 734: not activated; 735: -173.5; 736: -1.799 | -401.5 [-1049, -1.799] | 0 / 5 / 0 | 2/32 as extreme; means [-401.5, +401.5] | recorded |
| E - F | Food shortfall after relief over the run (food) | p | 831: +277.6; 832: +462; 833: -1756; 834: -925.1; 835: -874.5; 836: +480.7 | -389.2 [-1756, +480.7] | 3 / 3 / 0 | 24/64 as extreme; means [-796, +796] | recorded |
| E - F | Priced-out person-turns | t | 731: +30; 732: -17; 733: -144; 734: not activated; 735: -219; 736: -98 | -89.6 [-219, +30] | 1 / 4 / 0 | 6/32 as extreme; means [-101.6, +101.6] | recorded |
| E - F | Priced-out person-turns | p | 831: -296; 832: -9; 833: -981; 834: -622; 835: -176; 836: -296 | -396.7 [-981, -9] | 0 / 6 / 0 | 2/64 as extreme; means [-396.7, +396.7] | recorded |
| E - F | Priced-out child-turns | t | 731: +19; 732: -2; 733: +1; 734: not activated; 735: -25; 736: +8 | +0.2 [-25, +19] | 3 / 2 / 0 | 32/32 as extreme; means [-11, +11] | recorded |
| E - F | Priced-out child-turns | p | 831: -31; 832: +0; 833: -14; 834: -79; 835: -22; 836: +10 | -22.67 [-79, +10] | 1 / 4 / 1 | 8/64 as extreme; means [-26, +26] | recorded |
| E - F | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E - F | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E - F | Deaths by epidemic (the epidemic authority) | t | 731: -33; 732: -15; 733: -13; 734: not activated; 735: +24; 736: -8 | -9 [-33, +24] | 1 / 4 / 0 | 14/32 as extreme; means [-18.6, +18.6] | recorded |
| E - F | Deaths by epidemic (the epidemic authority) | p | 831: +106; 832: -181; 833: +121; 834: +56; 835: -179; 836: +241 | +27.33 [-181, +241] | 4 / 2 / 0 | 48/64 as extreme; means [-147.3, +147.3] | recorded |
| E - F | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E - F | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E - F | Agents migrating between regions over the run | t | 731: -615; 732: -41; 733: -800; 734: not activated; 735: -854; 736: +67 | -448.6 [-854, +67] | 1 / 4 / 0 | 6/32 as extreme; means [-475.4, +475.4] | recorded |
| E - F | Agents migrating between regions over the run | p | 831: +279; 832: +1271; 833: -2032; 834: -672; 835: -952; 836: +477 | -271.5 [-2032, +1271] | 3 / 3 / 0 | 38/64 as extreme; means [-947.2, +947.2] | recorded |
| E - F | Mean wealth Gini of living civilizations at the end | t | 731: -0.001063; 732: -0.02364; 733: -0.1416; 734: not activated; 735: +0.08132; 736: -0.0664 | -0.03027 [-0.1416, +0.08132] | 1 / 4 / 0 | 14/32 as extreme; means [-0.0628, +0.0628] | recorded |
| E - F | Mean wealth Gini of living civilizations at the end | p | 831: +0.1151; 832: -0.01719; 833: -0.09958; 834: -0.003012; 835: -0.1236; 836: +0.05466 | -0.01227 [-0.1236, +0.1151] | 2 / 4 / 0 | 46/64 as extreme; means [-0.06885, +0.06885] | recorded |
| E - F | Timber stand share of capacity at the end | t | 731: +0.8433; 732: +0.4067; 733: -0.04421; 734: not activated; 735: +0.002785; 736: -0.00972 | +0.2398 [-0.04421, +0.8433] | 3 / 2 / 0 | 14/32 as extreme; means [-0.2613, +0.2613] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| E - F | Timber stand share of capacity at the end | p | 831: -0.01926; 832: +0.01471; 833: -0.112; 834: -0.1016; 835: +0.0611; 836: -0.06588 | -0.03715 [-0.112, +0.0611] | 2 / 4 / 0 | 14/64 as extreme; means [-0.06242, +0.06242] | recorded |
| F - B | Population at the end (sum over civilizations) | t | 731: +9; 732: +13; 733: +31; 734: +42; 735: +51; 736: -37 | +18.17 [-37, +51] | 5 / 1 / 0 | 12/64 as extreme; means [-30.5, +30.5] | recorded |
| F - B | Population at the end (sum over civilizations) | p | 831: -59; 832: -17; 833: +12; 834: -164; 835: +14; 836: +195 | -3.167 [-164, +195] | 3 / 3 / 0 | 58/64 as extreme; means [-76.83, +76.83] | recorded |
| F - B | Treasury at the end (sum over civilizations) | t | 731: +79; 732: +860; 733: +764; 734: +1113; 735: -657; 736: +111 | +378.3 [-657, +1113] | 5 / 1 / 0 | 10/64 as extreme; means [-597.3, +597.3] | recorded |
| F - B | Treasury at the end (sum over civilizations) | p | 831: +1758; 832: -1717; 833: -1780; 834: -191; 835: -686; 836: +1754 | -143.7 [-1780, +1758] | 2 / 4 / 0 | 48/64 as extreme; means [-1314, +1314] | recorded |
| F - B | Food shortfall after relief over the run (food) | t | 731: +288.8; 732: +372.8; 733: -210.2; 734: -1013; 735: -1046; 736: +636.3 | -162 [-1046, +636.3] | 3 / 3 / 0 | 38/64 as extreme; means [-594.6, +594.6] | recorded |
| F - B | Food shortfall after relief over the run (food) | p | 831: -1278; 832: +293.3; 833: +210.3; 834: -1674; 835: -578.8; 836: +289.9 | -456.2 [-1674, +293.3] | 3 / 3 / 0 | 20/64 as extreme; means [-720.7, +720.7] | recorded |
| F - B | Priced-out person-turns | t | 731: +63; 732: +123; 733: +819; 734: +1064; 735: +764; 736: +573 | +567.7 [+63, +1064] | 6 / 0 / 0 | 2/64 as extreme; means [-567.7, +567.7] | recorded |
| F - B | Priced-out person-turns | p | 831: +1729; 832: +1750; 833: +2678; 834: +1307; 835: +1235; 836: +1477 | +1696 [+1235, +2678] | 6 / 0 / 0 | 2/64 as extreme; means [-1696, +1696] | recorded |
| F - B | Priced-out child-turns | t | 731: +6; 732: +14; 733: +93; 734: +109; 735: +60; 736: +25 | +51.17 [+6, +109] | 6 / 0 / 0 | 2/64 as extreme; means [-51.17, +51.17] | recorded |
| F - B | Priced-out child-turns | p | 831: +201; 832: +199; 833: +239; 834: +133; 835: +151; 836: +137 | +176.7 [+133, +239] | 6 / 0 / 0 | 2/64 as extreme; means [-176.7, +176.7] | recorded |
| F - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F - B | Deaths by epidemic (the epidemic authority) | t | 731: -94; 732: -60; 733: -14; 734: +105; 735: -83; 736: -108 | -42.33 [-108, +105] | 1 / 5 / 0 | 16/64 as extreme; means [-77.33, +77.33] | recorded |
| F - B | Deaths by epidemic (the epidemic authority) | p | 831: -35; 832: -243; 833: -119; 834: +95; 835: -76; 836: -265 | -107.2 [-265, +95] | 1 / 5 / 0 | 8/64 as extreme; means [-138.8, +138.8] | recorded |
| F - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F - B | Agents migrating between regions over the run | t | 731: -51; 732: -475; 733: +261; 734: -888; 735: -664; 736: -43 | -310 [-888, +261] | 1 / 5 / 0 | 10/64 as extreme; means [-397, +397] | recorded |
| F - B | Agents migrating between regions over the run | p | 831: -399; 832: -2195; 833: +674; 834: -1428; 835: -394; 836: +508 | -539 [-2195, +674] | 2 / 4 / 0 | 22/64 as extreme; means [-933, +933] | recorded |
| F - B | Mean wealth Gini of living civilizations at the end | t | 731: -0.01633; 732: -0.04794; 733: -0.06904; 734: +0.06996; 735: -0.05702; 736: -0.2589 | -0.06321 [-0.2589, +0.06996] | 1 / 5 / 0 | 14/64 as extreme; means [-0.08653, +0.08653] | recorded |
| F - B | Mean wealth Gini of living civilizations at the end | p | 831: -0.1849; 832: +0.04756; 833: -0.09952; 834: +0.07933; 835: -0.01071; 836: -0.05297 | -0.03686 [-0.1849, +0.07933] | 2 / 4 / 0 | 26/64 as extreme; means [-0.07916, +0.07916] | recorded |
| F - B | Timber stand share of capacity at the end | t | 731: +0.0123; 732: +0.007048; 733: +0.08942; 734: not recorded; 735: -0.01456; 736: +0.1713 | +0.05311 [-0.01456, +0.1713] | 4 / 1 / 0 | 8/32 as extreme; means [-0.05893, +0.05893] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| F - B | Timber stand share of capacity at the end | p | 831: +0.1529; 832: +0.05539; 833: +0.09263; 834: -0.05125; 835: -0.1058; 836: +0.1625 | +0.05107 [-0.1058, +0.1625] | 4 / 2 / 0 | 20/64 as extreme; means [-0.1034, +0.1034] | recorded |
| G - H | Population at the end (sum over civilizations) | t | 731: -12; 732: -18; 733: +15; 734: not activated; 735: +34; 736: -21 | -0.4 [-21, +34] | 2 / 3 / 0 | 32/32 as extreme; means [-20, +20] | recorded |
| G - H | Population at the end (sum over civilizations) | p | 831: +26; 832: -12; 833: -229; 834: +37; 835: -14; 836: -92 | -47.33 [-229, +37] | 2 / 4 / 0 | 26/64 as extreme; means [-68.33, +68.33] | recorded |
| G - H | Treasury at the end (sum over civilizations) | t | 731: -196; 732: +200; 733: -82; 734: not activated; 735: +534; 736: -1000 | -108.8 [-1000, +534] | 2 / 3 / 0 | 24/32 as extreme; means [-402.4, +402.4] | recorded |
| G - H | Treasury at the end (sum over civilizations) | p | 831: +2063; 832: -1030; 833: -716; 834: -1041; 835: +840; 836: +853 | +161.5 [-1041, +2063] | 3 / 3 / 0 | 52/64 as extreme; means [-1090, +1090] | recorded |
| G - H | Food shortfall after relief over the run (food) | t | 731: +135.5; 732: -147; 733: +169.4; 734: not activated; 735: +193; 736: -248.5 | +20.48 [-248.5, +193] | 3 / 2 / 0 | 28/32 as extreme; means [-178.7, +178.7] | recorded |
| G - H | Food shortfall after relief over the run (food) | p | 831: -316.2; 832: +1375; 833: -1642; 834: +196.1; 835: -231.3; 836: +104.3 | -85.67 [-1642, +1375] | 3 / 3 / 0 | 44/64 as extreme; means [-644, +644] | recorded |
| G - H | Priced-out person-turns | t | 731: +1; 732: -34; 733: +16; 734: not activated; 735: +45; 736: +63 | +18.2 [-34, +63] | 4 / 1 / 0 | 10/32 as extreme; means [-31.8, +31.8] | recorded |
| G - H | Priced-out person-turns | p | 831: -61; 832: -44; 833: +7; 834: -88; 835: +8; 836: +3 | -29.17 [-88, +8] | 3 / 3 / 0 | 16/64 as extreme; means [-35.17, +35.17] | recorded |
| G - H | Priced-out child-turns | t | 731: +0; 732: -8; 733: -1; 734: not activated; 735: -3; 736: -1 | -2.6 [-8, +0] | 0 / 4 / 1 | 4/32 as extreme; means [-2.6, +2.6] | recorded |
| G - H | Priced-out child-turns | p | 831: -16; 832: +11; 833: +1; 834: -8; 835: -1; 836: -2 | -2.5 [-16, +11] | 2 / 4 / 0 | 38/64 as extreme; means [-6.5, +6.5] | recorded |
| G - H | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| G - H | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| G - H | Deaths by epidemic (the epidemic authority) | t | 731: -50; 732: -29; 733: -55; 734: not activated; 735: +108; 736: -16 | -8.4 [-55, +108] | 1 / 4 / 0 | 28/32 as extreme; means [-51.6, +51.6] | recorded |
| G - H | Deaths by epidemic (the epidemic authority) | p | 831: +55; 832: -157; 833: +238; 834: +79; 835: +52; 836: +115 | +63.67 [-157, +238] | 5 / 1 / 0 | 18/64 as extreme; means [-116, +116] | recorded |
| G - H | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| G - H | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| G - H | Agents migrating between regions over the run | t | 731: +228; 732: -159; 733: +34; 734: not activated; 735: +778; 736: -10 | +174.2 [-159, +778] | 3 / 2 / 0 | 12/32 as extreme; means [-241.8, +241.8] | recorded |
| G - H | Agents migrating between regions over the run | p | 831: +918; 832: +1121; 833: -1335; 834: +575; 835: -120; 836: +925 | +347.3 [-1335, +1121] | 4 / 2 / 0 | 24/64 as extreme; means [-832.3, +832.3] | recorded |
| G - H | Mean wealth Gini of living civilizations at the end | t | 731: -0.01609; 732: +0.05822; 733: -0.0138; 734: not activated; 735: -0.009775; 736: -0.1525 | -0.02679 [-0.1525, +0.05822] | 1 / 4 / 0 | 18/32 as extreme; means [-0.05008, +0.05008] | recorded |
| G - H | Mean wealth Gini of living civilizations at the end | p | 831: -0.05185; 832: +0.08922; 833: +0.08291; 834: +0.09195; 835: +0.07302; 836: +0.01056 | +0.0493 [-0.05185, +0.09195] | 5 / 1 / 0 | 6/64 as extreme; means [-0.06658, +0.06658] | recorded |
| G - H | Timber stand share of capacity at the end | t | 731: +0.03959; 732: -0.03351; 733: -0.03074; 734: not activated; 735: +0.009202; 736: -0.04509 | -0.01211 [-0.04509, +0.03959] | 2 / 3 / 0 | 18/32 as extreme; means [-0.03163, +0.03163] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| G - H | Timber stand share of capacity at the end | p | 831: +0.2133; 832: +0.004578; 833: -0.1314; 834: +0.04912; 835: -0.1849; 836: -0.3123 | -0.06025 [-0.3123, +0.2133] | 3 / 3 / 0 | 32/64 as extreme; means [-0.1493, +0.1493] | recorded |
| H - B | Population at the end (sum over civilizations) | t | 731: +12; 732: +33; 733: -1; 734: -27; 735: -18; 736: -55 | -9.333 [-55, +33] | 2 / 4 / 0 | 32/64 as extreme; means [-24.33, +24.33] | recorded |
| H - B | Population at the end (sum over civilizations) | p | 831: +122; 832: +43; 833: +103; 834: -162; 835: +156; 836: +16 | +46.33 [-162, +156] | 5 / 1 / 0 | 24/64 as extreme; means [-100.3, +100.3] | recorded |
| H - B | Treasury at the end (sum over civilizations) | t | 731: +146; 732: +1496; 733: +1208; 734: +682; 735: -1283; 736: -50 | +366.5 [-1283, +1496] | 4 / 2 / 0 | 24/64 as extreme; means [-810.8, +810.8] | recorded |
| H - B | Treasury at the end (sum over civilizations) | p | 831: -690; 832: -359; 833: +48; 834: -585; 835: +47; 836: +908 | -105.2 [-690, +908] | 3 / 3 / 0 | 46/64 as extreme; means [-439.5, +439.5] | recorded |
| H - B | Food shortfall after relief over the run (food) | t | 731: +946.5; 732: +695.2; 733: -685.9; 734: -718; 735: -844; 736: +1074 | +78.01 [-844, +1074] | 3 / 3 / 0 | 50/64 as extreme; means [-827.3, +827.3] | recorded |
| H - B | Food shortfall after relief over the run (food) | p | 831: +1301; 832: -295.7; 833: +1084; 834: -1798; 835: -1108; 836: +271.8 | -90.83 [-1798, +1301] | 3 / 3 / 0 | 52/64 as extreme; means [-976.2, +976.2] | recorded |
| H - B | Priced-out person-turns | t | 731: +0; 732: +62; 733: +437; 734: +350; 735: +107; 736: +192 | +191.3 [+0, +437] | 5 / 0 / 1 | 4/64 as extreme; means [-191.3, +191.3] | recorded |
| H - B | Priced-out person-turns | p | 831: +178; 832: +532; 833: +535; 834: +216; 835: +210; 836: +171 | +307 [+171, +535] | 6 / 0 / 0 | 2/64 as extreme; means [-307, +307] | recorded |
| H - B | Priced-out child-turns | t | 731: +0; 732: +8; 733: +43; 734: +46; 735: +16; 736: +15 | +21.33 [+0, +46] | 5 / 0 / 1 | 4/64 as extreme; means [-21.33, +21.33] | recorded |
| H - B | Priced-out child-turns | p | 831: +22; 832: +67; 833: +88; 834: +23; 835: +45; 836: +29 | +45.67 [+22, +88] | 6 / 0 / 0 | 2/64 as extreme; means [-45.67, +45.67] | recorded |
| H - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| H - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| H - B | Deaths by epidemic (the epidemic authority) | t | 731: -10; 732: -24; 733: +15; 734: +93; 735: -117; 736: -35 | -13 [-117, +93] | 2 / 4 / 0 | 38/64 as extreme; means [-49, +49] | recorded |
| H - B | Deaths by epidemic (the epidemic authority) | p | 831: -205; 832: -116; 833: +23; 834: -133; 835: -15; 836: +5 | -73.5 [-205, +23] | 2 / 4 / 0 | 12/64 as extreme; means [-82.83, +82.83] | recorded |
| H - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| H - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| H - B | Agents migrating between regions over the run | t | 731: +477; 732: -161; 733: -399; 734: -1138; 735: -1449; 736: +101 | -428.2 [-1449, +477] | 2 / 4 / 0 | 18/64 as extreme; means [-620.8, +620.8] | recorded |
| H - B | Agents migrating between regions over the run | p | 831: +2254; 832: -227; 833: +902; 834: -2877; 835: +340; 836: -508 | -19.33 [-2877, +2254] | 3 / 3 / 0 | 64/64 as extreme; means [-1185, +1185] | recorded |
| H - B | Mean wealth Gini of living civilizations at the end | t | 731: +0.001598; 732: -0.07144; 733: -0.1483; 734: -0.09673; 735: -0.01967; 736: -0.2726 | -0.1012 [-0.2726, +0.001598] | 1 / 5 / 0 | 4/64 as extreme; means [-0.1017, +0.1017] | recorded |
| H - B | Mean wealth Gini of living civilizations at the end | p | 831: +0.01978; 832: -0.03899; 833: -0.06062; 834: -0.06294; 835: -0.06969; 836: -0.08711 | -0.04993 [-0.08711, +0.01978] | 1 / 5 / 0 | 4/64 as extreme; means [-0.05652, +0.05652] | recorded |
| H - B | Timber stand share of capacity at the end | t | 731: +0.0123; 732: +0.1255; 733: +0.04521; 734: not recorded; 735: -0.01499; 736: +0.05195 | +0.044 [-0.01499, +0.1255] | 4 / 1 / 0 | 6/32 as extreme; means [-0.05, +0.05] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| H - B | Timber stand share of capacity at the end | p | 831: -0.2975; 832: +0.03638; 833: +0.1806; 834: -0.1629; 835: +0.08751; 836: +0.2796 | +0.02061 [-0.2975, +0.2796] | 4 / 2 / 0 | 52/64 as extreme; means [-0.1741, +0.1741] | recorded |
| CH_noTS - A | Population at the end (sum over civilizations) | t | 731: +27; 732: -30; 733: -14; 734: not activated; 735: +68; 736: +38 | +17.8 [-30, +68] | 3 / 2 / 0 | 14/32 as extreme; means [-35.4, +35.4] | recorded |
| CH_noTS - A | Population at the end (sum over civilizations) | p | 831: -212; 832: -33; 833: +133; 834: +166; 835: -91; 836: -80 | -19.5 [-212, +166] | 2 / 4 / 0 | 48/64 as extreme; means [-119.2, +119.2] | recorded |
| CH_noTS - A | Treasury at the end (sum over civilizations) | t | 731: +56; 732: -388; 733: +872; 734: not activated; 735: -64; 736: +305 | +156.2 [-388, +872] | 3 / 2 / 0 | 22/32 as extreme; means [-337, +337] | recorded |
| CH_noTS - A | Treasury at the end (sum over civilizations) | p | 831: -1023; 832: -2091; 833: +4716; 834: -2357; 835: -1304; 836: +3013 | +159 [-2357, +4716] | 2 / 4 / 0 | 58/64 as extreme; means [-2417, +2417] | recorded |
| CH_noTS - A | Food shortfall after relief over the run (food) | t | 731: -201.2; 732: +968.7; 733: -465.3; 734: not activated; 735: +894.7; 736: -70.04 | +225.4 [-465.3, +968.7] | 2 / 3 / 0 | 16/32 as extreme; means [-520, +520] | recorded |
| CH_noTS - A | Food shortfall after relief over the run (food) | p | 831: -980.9; 832: +456.9; 833: +2545; 834: -237.6; 835: -1128; 836: +82.45 | +123 [-1128, +2545] | 3 / 3 / 0 | 54/64 as extreme; means [-905.2, +905.2] | recorded |
| CH_noTS - A | Priced-out person-turns | t | 731: +14; 732: -76; 733: -1; 734: not activated; 735: +30; 736: +11 | -4.4 [-76, +30] | 3 / 2 / 0 | 30/32 as extreme; means [-26.4, +26.4] | recorded |
| CH_noTS - A | Priced-out person-turns | p | 831: -4; 832: +21; 833: +97; 834: -278; 835: -9; 836: +3 | -28.33 [-278, +97] | 3 / 3 / 0 | 52/64 as extreme; means [-68.67, +68.67] | recorded |
| CH_noTS - A | Priced-out child-turns | t | 731: +1; 732: -2; 733: +0; 734: not activated; 735: -2; 736: +1 | -0.4 [-2, +1] | 2 / 2 / 1 | 24/32 as extreme; means [-1.2, +1.2] | recorded |
| CH_noTS - A | Priced-out child-turns | p | 831: -10; 832: +4; 833: +7; 834: +4; 835: -4; 836: +1 | +0.3333 [-10, +7] | 4 / 2 / 0 | 58/64 as extreme; means [-5, +5] | recorded |
| CH_noTS - A | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| CH_noTS - A | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| CH_noTS - A | Deaths by epidemic (the epidemic authority) | t | 731: +20; 732: +90; 733: -21; 734: not activated; 735: -19; 736: +43 | +22.6 [-21, +90] | 3 / 2 / 0 | 12/32 as extreme; means [-38.6, +38.6] | recorded |
| CH_noTS - A | Deaths by epidemic (the epidemic authority) | p | 831: +340; 832: -192; 833: -173; 834: -116; 835: +157; 836: -84 | -11.33 [-192, +340] | 2 / 4 / 0 | 58/64 as extreme; means [-177, +177] | recorded |
| CH_noTS - A | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| CH_noTS - A | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| CH_noTS - A | Agents migrating between regions over the run | t | 731: +575; 732: +627; 733: -65; 734: not activated; 735: +624; 736: -15 | +349.2 [-65, +627] | 3 / 2 / 0 | 8/32 as extreme; means [-381.2, +381.2] | recorded |
| CH_noTS - A | Agents migrating between regions over the run | p | 831: -998; 832: +413; 833: +2103; 834: +985; 835: -711; 836: -589 | +200.5 [-998, +2103] | 3 / 3 / 0 | 48/64 as extreme; means [-966.5, +966.5] | recorded |
| CH_noTS - A | Mean wealth Gini of living civilizations at the end | t | 731: -0.0191; 732: -0.2885; 733: +0.0206; 734: not activated; 735: -0.00376; 736: -0.03005 | -0.06415 [-0.2885, +0.0206] | 1 / 4 / 0 | 8/32 as extreme; means [-0.07239, +0.07239] | recorded |
| CH_noTS - A | Mean wealth Gini of living civilizations at the end | p | 831: -0.04695; 832: +0.003867; 833: -0.1627; 834: +0.04734; 835: -0.06515; 836: +0.1197 | -0.01731 [-0.1627, +0.1197] | 3 / 3 / 0 | 48/64 as extreme; means [-0.07428, +0.07428] | recorded |
| CH_noTS - A | Timber stand share of capacity at the end | t | 731: +0.91; 732: -0.3685; 733: -0.06069; 734: not activated; 735: +0.002194; 736: +0.135 | +0.1236 [-0.3685, +0.91] | 3 / 2 / 0 | 22/32 as extreme; means [-0.2953, +0.2953] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| CH_noTS - A | Timber stand share of capacity at the end | p | 831: -0.1104; 832: +0.02577; 833: +0.007837; 834: +0.04716; 835: -0.01881; 836: +0.01761 | -0.005129 [-0.1104, +0.04716] | 4 / 2 / 0 | 58/64 as extreme; means [-0.03792, +0.03792] | recorded |
| A - B | Population at the end (sum over civilizations) | t | 731: -57; 732: +25; 733: +18; 734: not activated; 735: -21; 736: -50 | -17 [-57, +25] | 2 / 3 / 0 | 12/32 as extreme; means [-34.2, +34.2] | recorded |
| A - B | Population at the end (sum over civilizations) | p | 831: +53; 832: +7; 833: -57; 834: -220; 835: +41; 836: -196 | -62 [-220, +53] | 3 / 3 / 0 | 22/64 as extreme; means [-95.67, +95.67] | recorded |
| A - B | Treasury at the end (sum over civilizations) | t | 731: -77; 732: +800; 733: +409; 734: not activated; 735: -752; 736: -286 | +18.8 [-752, +800] | 2 / 3 / 0 | 30/32 as extreme; means [-464.8, +464.8] | recorded |
| A - B | Treasury at the end (sum over civilizations) | p | 831: +16; 832: +92; 833: -2055; 834: -425; 835: +554; 836: -3020 | -806.3 [-3020, +554] | 3 / 3 / 0 | 24/64 as extreme; means [-1027, +1027] | recorded |
| A - B | Food shortfall after relief over the run (food) | t | 731: +51.64; 732: +39.96; 733: -455; 734: not activated; 735: -937.6; 736: -570.3 | -374.3 [-937.6, +51.64] | 2 / 3 / 0 | 8/32 as extreme; means [-410.9, +410.9] | recorded |
| A - B | Food shortfall after relief over the run (food) | p | 831: +502.1; 832: +569.7; 833: -826.3; 834: -1128; 835: +127.6; 836: -664.1 | -236.5 [-1128, +569.7] | 3 / 3 / 0 | 28/64 as extreme; means [-636.3, +636.3] | recorded |
| A - B | Priced-out person-turns | t | 731: +1; 732: +78; 733: +1; 734: not activated; 735: -11; 736: +0 | +13.8 [-11, +78] | 3 / 1 / 1 | 20/32 as extreme; means [-18.2, +18.2] | recorded |
| A - B | Priced-out person-turns | p | 831: +30; 832: +22; 833: +103; 834: +420; 835: +4; 836: +10 | +98.17 [+4, +420] | 6 / 0 / 0 | 2/64 as extreme; means [-98.17, +98.17] | recorded |
| A - B | Priced-out child-turns | t | 731: +1; 732: +4; 733: +0; 734: not activated; 735: +0; 736: +0 | +1 [+0, +4] | 2 / 0 / 3 | 16/32 as extreme; means [-1, +1] | recorded |
| A - B | Priced-out child-turns | p | 831: +10; 832: -1; 833: +19; 834: +27; 835: +6; 836: +0 | +10.17 [-1, +27] | 4 / 1 / 1 | 8/64 as extreme; means [-10.5, +10.5] | recorded |
| A - B | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| A - B | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| A - B | Deaths by epidemic (the epidemic authority) | t | 731: -73; 732: -46; 733: +21; 734: not activated; 735: +81; 736: -38 | -11 [-73, +81] | 2 / 3 / 0 | 22/32 as extreme; means [-51.8, +51.8] | recorded |
| A - B | Deaths by epidemic (the epidemic authority) | p | 831: -195; 832: -46; 833: +56; 834: -43; 835: -162; 836: +259 | -21.83 [-195, +259] | 2 / 4 / 0 | 54/64 as extreme; means [-126.8, +126.8] | recorded |
| A - B | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| A - B | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| A - B | Agents migrating between regions over the run | t | 731: -317; 732: -528; 733: -52; 734: not activated; 735: -201; 736: -256 | -270.8 [-528, -52] | 0 / 5 / 0 | 2/32 as extreme; means [-270.8, +270.8] | recorded |
| A - B | Agents migrating between regions over the run | p | 831: +1141; 832: +86; 833: -1029; 834: -1693; 835: -230; 836: -88 | -302.2 [-1693, +1141] | 2 / 4 / 0 | 28/64 as extreme; means [-711.2, +711.2] | recorded |
| A - B | Mean wealth Gini of living civilizations at the end | t | 731: +0.02789; 732: -0.04078; 733: -0.1865; 734: not activated; 735: +0.01169; 736: +0.001832 | -0.03717 [-0.1865, +0.02789] | 3 / 2 / 0 | 18/32 as extreme; means [-0.05373, +0.05373] | recorded |
| A - B | Mean wealth Gini of living civilizations at the end | p | 831: +0.009012; 832: -0.005631; 833: -0.01832; 834: -0.1561; 835: +0.05402; 836: -0.3472 | -0.07738 [-0.3472, +0.05402] | 2 / 4 / 0 | 22/64 as extreme; means [-0.09839, +0.09839] | recorded |
| A - B | Timber stand share of capacity at the end | t | 731: +0.008877; 732: +0.009857; 733: -0.008457; 734: not activated; 735: -0.01396; 736: -0.1093 | -0.0226 [-0.1093, +0.009857] | 2 / 3 / 0 | 16/32 as extreme; means [-0.03009, +0.03009] | not_recorded, recorded (no timber capacity at the end (no slot)) |
| A - B | Timber stand share of capacity at the end | p | 831: -0.07262; 832: +0.0433; 833: -0.08369; 834: -0.2069; 835: -0.07615; 836: -0.0358 | -0.07197 [-0.2069, +0.0433] | 1 / 5 / 0 | 6/64 as extreme; means [-0.08641, +0.08641] | recorded |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| A | 9.8 [9.0, 10.6] | 28.0 [22.9, 32.7] |
| B | 9.7 [8.9, 10.5] | 27.9 [21.7, 33.4] |
| C | 9.9 [9.1, 10.5] | 30.5 [23.3, 35.4] |
| D | 9.6 [8.9, 10.8] | 28.8 [22.8, 34.4] |
| E | 10.6 [9.3, 11.1] | 31.2 [26.1, 36.9] |
| F | 11.1 [9.9, 12.5] | 30.3 [26.3, 36.7] |
| G | 10.7 [9.4, 13.0] | 27.5 [23.4, 33.1] |
| H | 10.3 [9.2, 11.1] | 27.9 [24.8, 33.0] |
| CH_noTS | 9.7 [8.6, 10.3] | 27.1 [22.2, 34.0] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
