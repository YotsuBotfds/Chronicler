Runs: 144; failed: 0; wall seconds total 1936

### Paired differences vs off (mean [min, max] over worlds)

| Arm | Stratum | Worlds | Population | Treasury |
| --- | --- | --- | --- | --- |
| L1_operate | t | 6 | +4.5 [-39, +63] | +174.7 [-1105, +1976] |
| L1_operate | p | 6 | -10.5 [-173, +172] | -207.3 [-1341, +1338] |
| L1_cost_only | t | 6 | +8.5 [-49, +53] | -175.2 [-1419, +1741] |
| L1_cost_only | p | 6 | +25.2 [-153, +217] | -73.2 [-2524, +2689] |
| L2_floor_means | t | 6 | -0.7 [-31, +30] | +454.5 [-795, +1899] |
| L2_floor_means | p | 6 | +29.7 [-86, +147] | +267.8 [-2154, +3852] |
| L2_targeted | t | 6 | +1.2 [-39, +58] | +317.3 [-536, +2080] |
| L2_targeted | p | 6 | +32.0 [-41, +148] | +487.7 [-785, +1850] |
| L3_timber | t | 6 | -3.8 [-18, +0] | +217.3 [-201, +1505] |
| L3_timber | p | 6 | -31.0 [-125, +18] | -534.5 [-3290, +920] |
| L3_ablation | t | 6 | +0.0 [+0, +0] | +0.0 [+0, +0] |
| L3_ablation | p | 6 | +0.0 [+0, +0] | +0.0 [+0, +0] |
| L4_convoys | t | 6 | +0.8 [-15, +30] | +158.2 [-340, +1333] |
| L4_convoys | p | 6 | -19.5 [-229, +138] | +88.8 [-1935, +1755] |
| I1_work_food | t | 6 | -16.5 [-76, +48] | -712.0 [-1462, +199] |
| I1_work_food | p | 6 | -53.3 [-185, +131] | -453.3 [-2086, +691] |
| I2_timber_work | t | 6 | -7.0 [-65, +34] | +187.2 [-557, +1648] |
| I2_timber_work | p | 6 | +47.0 [-118, +226] | +34.2 [-1341, +3222] |
| I3_convoy_relief | t | 6 | -12.0 [-93, +64] | +98.2 [-1181, +1610] |
| I3_convoy_relief | p | 6 | +37.3 [-64, +229] | -95.5 [-2408, +1110] |
| ALL | t | 6 | -14.8 [-61, +16] | -293.3 [-1384, +545] |
| ALL | p | 6 | -9.7 [-200, +176] | +34.0 [-2130, +1653] |

### Activation funnels and primary outcomes (sum or mean per world)


**template 8x4 (seeds 101-106)**

- L1_operate: workshops: worlds operating 6/6, site-turns 535, operating 440, building 24, idle 2, work alloc/real 432.8/129.8, site-region craft out 259.6, paid 1752
- L1_cost_only: workshops: worlds operating 0/6, site-turns 554, operating 0, building 25, idle 2, work alloc/real 0.0/0.0, site-region craft out 232.6, paid 1814
- L2_floor_means: food: scarce region-turns/world 536, mean shortfall poorer 0.476 vs richer 0.375 (poorer worse in 6/6 worlds), children 0.462, relief to targeted/world 0.00, unallocated/world 56.2
- L2_targeted: food: scarce region-turns/world 548, mean shortfall poorer 0.408 vs richer 0.441 (poorer worse in 0/6 worlds), children 0.417, relief to targeted/world 259.37, unallocated/world 58.8
- L3_timber: timber: extraction/world 246.8, regrowth 204.2, cleared 2117.7, overdraft 0.000, capped slot-turns 8.5 (worlds binding 4/6)
- L3_ablation: timber: extraction/world 254.7, regrowth 205.3, cleared 2117.5, overdraft 6.768, capped slot-turns 0.0 (worlds binding 0/6)
- L4_convoys: convoys (sum over worlds): eligible 247, no_budget 17, unaffordable 236, dispatched 24, arrived 24, delivered 245, captured 0, lost 0, returned 0, stranded 0, escorted 0, escort_wasted 0
- I1_work_food: workshops: worlds operating 6/6, site-turns 568, operating 462, building 25, idle 8, work alloc/real 384.6/120.6, site-region craft out 241.2, paid 1864; food: scarce region-turns/world 511, mean shortfall poorer 0.470 vs richer 0.370 (poorer worse in 6/6 worlds), children 0.459, relief to targeted/world 0.00, unallocated/world 61.6
- I2_timber_work: workshops: worlds operating 6/6, site-turns 542, operating 450, building 25, idle 2, work alloc/real 426.8/120.4, site-region craft out 240.8, paid 1781; timber: extraction/world 237.2, regrowth 124.0, cleared 2166.0, overdraft 0.000, capped slot-turns 10.2 (worlds binding 4/6)
- I3_convoy_relief: food: scarce region-turns/world 528, mean shortfall poorer 0.397 vs richer 0.432 (poorer worse in 0/6 worlds), children 0.405, relief to targeted/world 239.21, unallocated/world 55.9; convoys (sum over worlds): eligible 259, no_budget 17, unaffordable 254, dispatched 27, arrived 25, delivered 241, captured 0, lost 0, returned 0, stranded 0, escorted 0, escort_wasted 0
- ALL: workshops: worlds operating 6/6, site-turns 555, operating 440, building 27, idle 4, work alloc/real 361.3/118.2, site-region craft out 236.4, paid 1837; food: scarce region-turns/world 512, mean shortfall poorer 0.470 vs richer 0.369 (poorer worse in 6/6 worlds), children 0.459, relief to targeted/world 0.00, unallocated/world 61.6; timber: extraction/world 249.0, regrowth 212.3, cleared 2155.8, overdraft 0.000, capped slot-turns 10.3 (worlds binding 4/6); convoys (sum over worlds): eligible 203, no_budget 26, unaffordable 174, dispatched 26, arrived 26, delivered 248, captured 0, lost 0, returned 0, stranded 0, escorted 0, escort_wasted 0

**procedural 32x10 (seeds 201-206)**

- L1_operate: workshops: worlds operating 6/6, site-turns 731, operating 488, building 37, idle 87, work alloc/real 496.8/182.4, site-region craft out 364.9, paid 2316
- L1_cost_only: workshops: worlds operating 0/6, site-turns 731, operating 0, building 34, idle 88, work alloc/real 0.0/0.0, site-region craft out 346.3, paid 2316
- L2_floor_means: food: scarce region-turns/world 1982, mean shortfall poorer 0.433 vs richer 0.328 (poorer worse in 6/6 worlds), children 0.416, relief to targeted/world 0.00, unallocated/world 235.0
- L2_targeted: food: scarce region-turns/world 1978, mean shortfall poorer 0.356 vs richer 0.380 (poorer worse in 0/6 worlds), children 0.354, relief to targeted/world 324.14, unallocated/world 236.5
- L3_timber: timber: extraction/world 1430.2, regrowth 6675.5, cleared 19406.5, overdraft 0.000, capped slot-turns 30.2 (worlds binding 6/6)
- L3_ablation: timber: extraction/world 1493.2, regrowth 6743.4, cleared 19234.8, overdraft 27.370, capped slot-turns 0.0 (worlds binding 0/6)
- L4_convoys: convoys (sum over worlds): eligible 965, no_budget 263, unaffordable 720, dispatched 39, arrived 37, delivered 342, captured 0, lost 0, returned 0, stranded 0, escorted 0, escort_wasted 0
- I1_work_food: workshops: worlds operating 6/6, site-turns 726, operating 510, building 32, idle 62, work alloc/real 495.0/206.1, site-region craft out 412.3, paid 2328; food: scarce region-turns/world 1886, mean shortfall poorer 0.440 vs richer 0.338 (poorer worse in 6/6 worlds), children 0.423, relief to targeted/world 0.00, unallocated/world 229.2
- I2_timber_work: workshops: worlds operating 6/6, site-turns 731, operating 506, building 32, idle 87, work alloc/real 488.4/174.1, site-region craft out 348.3, paid 2287; timber: extraction/world 1366.8, regrowth 6556.6, cleared 19204.8, overdraft 0.000, capped slot-turns 34.5 (worlds binding 5/6)
- I3_convoy_relief: food: scarce region-turns/world 1985, mean shortfall poorer 0.359 vs richer 0.384 (poorer worse in 0/6 worlds), children 0.358, relief to targeted/world 296.95, unallocated/world 238.0; convoys (sum over worlds): eligible 741, no_budget 71, unaffordable 682, dispatched 41, arrived 40, delivered 307, captured 0, lost 0, returned 0, stranded 0, escorted 0, escort_wasted 0
- ALL: workshops: worlds operating 6/6, site-turns 734, operating 498, building 29, idle 85, work alloc/real 541.4/207.6, site-region craft out 415.1, paid 2270; food: scarce region-turns/world 1968, mean shortfall poorer 0.437 vs richer 0.332 (poorer worse in 6/6 worlds), children 0.418, relief to targeted/world 0.00, unallocated/world 225.1; timber: extraction/world 1420.6, regrowth 6153.3, cleared 19424.0, overdraft 0.000, capped slot-turns 39.3 (worlds binding 6/6); convoys (sum over worlds): eligible 841, no_budget 201, unaffordable 747, dispatched 35, arrived 33, delivered 244, captured 0, lost 1, returned 0, stranded 0, escorted 0, escort_wasted 0
