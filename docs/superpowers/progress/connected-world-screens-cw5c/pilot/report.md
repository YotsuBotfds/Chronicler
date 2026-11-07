# CW5c: S4 bounded epidemic care capacity (C2)

Cohort pilot. Runs: 6; failed: 0 (missing outcomes: 0); simulation and extraction seconds 78 (0.022 core-hours)
Projected held run time from this pilot: 0.129 core-hours (x1.5 = 0.194) for 36 runs

Identity digests: a8bc22d97f324f5772f7a00f668263d63146444c068f64c1067eebda98a4b130 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"epidemic_care": [1], "local_budgets": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"local_budgets": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| EC | t | 5: activated | 1 of 1 |
| EC | p | 19: activated | 1 of 1 |
| EF | t | 5: activated | 1 of 1 |
| EF | p | 19: activated | 1 of 1 |

## CW5c mechanism check (not evidence that care works: coverage is about 1 by construction)

Fatality per infectious person-turn in each arm's own covered region-turns, the EF/EC ratio, and the mean care factor EF applied there (combined / techniques: 1 - 0.3 x coverage under the floor) with its floored count. The ratio should sit near the factor.

| World | EC own covered | EF own covered | EF / EC | EF mean applied factor | EF floored | EF mean coverage |
| --- | --- | --- | --- | --- | --- | --- |
| t5 | 0.5316 | 0.3153 | 0.5931 | 0.7 | 0 | 1 |
| p19 | 0.1979 | 0.1182 | 0.5976 | 0.7007 | 0 | 0.9975 |

## CW5c reach and attenuation

Reach: the share of EC's epidemic deaths in EC's covered region-turns. Implied maximum: reach x (1 - EF's mean applied factor), the fall in world deaths if care cut every covered death by that factor and nothing else changed. Realized: the EF - EC change of the world epidemic death rate, relative to EC.

| World | EC reach | EF mean applied factor | Implied maximum fall | Realized change |
| --- | --- | --- | --- | --- |
| t5 | 0.5952 | 0.7 | -0.179 | -0.320 |
| p19 | 0.7162 | 0.7007 | -0.214 | -0.397 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5c_world_death_rate: World epidemic deaths per 1,000 person-turns over the whole run (EF - EC) | t | 5: -1.708 | -1.708 [-1.708, -1.708] | 0 / 1 / 0 | 2/2 as extreme; means [-1.708, +1.708] |
| cw5c_world_death_rate: World epidemic deaths per 1,000 person-turns over the whole run (EF - EC) | p | 19: -2.627 | -2.627 [-2.627, -2.627] | 0 / 1 / 0 | 2/2 as extreme; means [-2.627, +2.627] |
| cw5c_itt_cfr: Epidemic deaths per infectious person-turn in the region-turns EC covered, read at the same cells in both arms (EF - EC; intention to treat) | t | 5: -0.2149 | -0.2149 [-0.2149, -0.2149] | 0 / 1 / 0 | 2/2 as extreme; means [-0.2149, +0.2149] |
| cw5c_itt_cfr: Epidemic deaths per infectious person-turn in the region-turns EC covered, read at the same cells in both arms (EF - EC; intention to treat) | p | 19: -0.08207 | -0.08207 [-0.08207, -0.08207] | 0 / 1 / 0 | 2/2 as extreme; means [-0.08207, +0.08207] |
| cw5c_world_dpi: World epidemic deaths per infectious person-turn over the whole run (EF - EC) | t | 5: -0.1333 | -0.1333 [-0.1333, -0.1333] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1333, +0.1333] |
| cw5c_world_dpi: World epidemic deaths per infectious person-turn over the whole run (EF - EC) | p | 19: -0.06487 | -0.06487 [-0.06487, -0.06487] | 0 / 1 / 0 | 2/2 as extreme; means [-0.06487, +0.06487] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5c_world_deaths: World epidemic deaths, count (EF - EC) | t | 5: -38 | -38 [-38, -38] | 0 / 1 / 0 | 2/2 as extreme; means [-38, +38] |
| cw5c_world_deaths: World epidemic deaths, count (EF - EC) | p | 19: -266 | -266 [-266, -266] | 0 / 1 / 0 | 2/2 as extreme; means [-266, +266] |
| cw5c_world_death_rate_vs_none: World epidemic deaths per 1,000 person-turns (EF - E0) | t | 5: -1.486 | -1.486 [-1.486, -1.486] | 0 / 1 / 0 | 2/2 as extreme; means [-1.486, +1.486] |
| cw5c_world_death_rate_vs_none: World epidemic deaths per 1,000 person-turns (EF - E0) | p | 19: -2.823 | -2.823 [-2.823, -2.823] | 0 / 1 / 0 | 2/2 as extreme; means [-2.823, +2.823] |
| cw5c_cost_world_death_rate: World epidemic deaths per 1,000 person-turns (EC - E0: the cost's effect) | t | 5: +0.2219 | +0.2219 [+0.2219, +0.2219] | 1 / 0 / 0 | 2/2 as extreme; means [-0.2219, +0.2219] |
| cw5c_cost_world_death_rate: World epidemic deaths per 1,000 person-turns (EC - E0: the cost's effect) | p | 19: -0.196 | -0.196 [-0.196, -0.196] | 0 / 1 / 0 | 2/2 as extreme; means [-0.196, +0.196] |
| cw5c_continuing_deaths_per_case: Deaths per new infection in continuing-outbreak region-turns (EF - EC) | t | 5: -0.04929 | -0.04929 [-0.04929, -0.04929] | 0 / 1 / 0 | 2/2 as extreme; means [-0.04929, +0.04929] |
| cw5c_continuing_deaths_per_case: Deaths per new infection in continuing-outbreak region-turns (EF - EC) | p | 19: -0.01896 | -0.01896 [-0.01896, -0.01896] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01896, +0.01896] |
| cw5c_continuing_deaths_per_case_vs_none: Deaths per new infection in continuing-outbreak region-turns (EF - E0) | t | 5: -0.03786 | -0.03786 [-0.03786, -0.03786] | 0 / 1 / 0 | 2/2 as extreme; means [-0.03786, +0.03786] |
| cw5c_continuing_deaths_per_case_vs_none: Deaths per new infection in continuing-outbreak region-turns (EF - E0) | p | 19: -0.02155 | -0.02155 [-0.02155, -0.02155] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02155, +0.02155] |
| cw5c_covered_region_turns: Covered region-turns (EF - EC; selection) | t | 5: +10 | +10 [+10, +10] | 1 / 0 / 0 | 2/2 as extreme; means [-10, +10] |
| cw5c_covered_region_turns: Covered region-turns (EF - EC; selection) | p | 19: +321 | +321 [+321, +321] | 1 / 0 / 0 | 2/2 as extreme; means [-321, +321] |
| cw5c_mech_covered_dpi: Mechanism check: deaths per infectious person-turn in each arm's own covered region-turns (EF - EC; selection; see the ratio table) | t | 5: -0.2163 | -0.2163 [-0.2163, -0.2163] | 0 / 1 / 0 | 2/2 as extreme; means [-0.2163, +0.2163] |
| cw5c_mech_covered_dpi: Mechanism check: deaths per infectious person-turn in each arm's own covered region-turns (EF - EC; selection; see the ratio table) | p | 19: -0.07963 | -0.07963 [-0.07963, -0.07963] | 0 / 1 / 0 | 2/2 as extreme; means [-0.07963, +0.07963] |
| cw5c_mech_factor: Mechanism check: mean care factor applied in covered region-turns (EF) | t | 5: +0.7 | +0.7 [+0.7, +0.7] | 1 / 0 / 0 | n/a (no control) |
| cw5c_mech_factor: Mechanism check: mean care factor applied in covered region-turns (EF) | p | 19: +0.7007 | +0.7007 [+0.7007, +0.7007] | 1 / 0 / 0 | n/a (no control) |
| cw5c_mean_coverage: Mean coverage over region-turns with capacity (EF) | t | 5: +1 | +1 [+1, +1] | 1 / 0 / 0 | n/a (no control) |
| cw5c_mean_coverage: Mean coverage over region-turns with capacity (EF) | p | 19: +0.9975 | +0.9975 [+0.9975, +0.9975] | 1 / 0 / 0 | n/a (no control) |
| cw5c_reach: Reach: share of EC's epidemic deaths in its covered region-turns (EC) | t | 5: +0.5952 | +0.5952 [+0.5952, +0.5952] | 1 / 0 / 0 | n/a (no control) |
| cw5c_reach: Reach: share of EC's epidemic deaths in its covered region-turns (EC) | p | 19: +0.7162 | +0.7162 [+0.7162, +0.7162] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time: Carer farm time removed, worker-turns (EF) | t | 5: +57.29 | +57.29 [+57.29, +57.29] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time: Carer farm time removed, worker-turns (EF) | p | 19: +699.8 | +699.8 [+699.8, +699.8] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time_cost: Carer farm time removed, worker-turns (EC) | t | 5: +47.45 | +47.45 [+47.45, +47.45] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time_cost: Carer farm time removed, worker-turns (EC) | p | 19: +644.8 | +644.8 [+644.8, +644.8] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_carers_held: Carer-turns held from drafting and academy teaching (EF) | t | 5: +177 | +177 [+177, +177] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_carers_held: Carer-turns held from drafting and academy teaching (EF) | p | 19: +1967 | +1967 [+1967, +1967] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_carers_held_cost: Carer-turns held from drafting and academy teaching (EC) | t | 5: +158 | +158 [+158, +158] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_carers_held_cost: Carer-turns held from drafting and academy teaching (EC) | p | 19: +1657 | +1657 [+1657, +1657] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_wages: Care wages paid, treasury units (EF) | t | 5: +28.64 | +28.64 [+28.64, +28.64] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_wages: Care wages paid, treasury units (EF) | p | 19: +349.9 | +349.9 [+349.9, +349.9] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_wages_cost: Care wages paid, treasury units (EC) | t | 5: +23.67 | +23.67 [+23.67, +23.67] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_wages_cost: Care wages paid, treasury units (EC) | p | 19: +322.2 | +322.2 [+322.2, +322.2] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld: Carers' ordinary income withheld, wealth units (EF) | t | 5: +5.298 | +5.298 [+5.298, +5.298] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld: Carers' ordinary income withheld, wealth units (EF) | p | 19: +94.05 | +94.05 [+94.05, +94.05] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld_cost: Carers' ordinary income withheld, wealth units (EC) | t | 5: +6.885 | +6.885 [+6.885, +6.885] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld_cost: Carers' ordinary income withheld, wealth units (EC) | p | 19: +81.18 | +81.18 [+81.18, +81.18] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_unpaid_bills: Care wage bills refused at payment (EF) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw5c_h_unpaid_bills: Care wage bills refused at payment (EF) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw5c_h_unpaid_bills_cost: Care wage bills refused at payment (EC) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw5c_h_unpaid_bills_cost: Care wage bills refused at payment (EC) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw5c_h_food_shortfall: Food shortfall after relief over the run (EF - EC) | t | 5: +705.6 | +705.6 [+705.6, +705.6] | 1 / 0 / 0 | 2/2 as extreme; means [-705.6, +705.6] |
| cw5c_h_food_shortfall: Food shortfall after relief over the run (EF - EC) | p | 19: +2312 | +2312 [+2312, +2312] | 1 / 0 / 0 | 2/2 as extreme; means [-2312, +2312] |
| cw5c_h_food_shortfall_cost: Food shortfall after relief over the run (EC - E0: the cost) | t | 5: -312.1 | -312.1 [-312.1, -312.1] | 0 / 1 / 0 | 2/2 as extreme; means [-312.1, +312.1] |
| cw5c_h_food_shortfall_cost: Food shortfall after relief over the run (EC - E0: the cost) | p | 19: +292.7 | +292.7 [+292.7, +292.7] | 1 / 0 / 0 | 2/2 as extreme; means [-292.7, +292.7] |
| cw5c_h_dearth: Dearth region-turns, sufficiency after relief below 1 (EC - E0) | t | 5: -27 | -27 [-27, -27] | 0 / 1 / 0 | 2/2 as extreme; means [-27, +27] |
| cw5c_h_dearth: Dearth region-turns, sufficiency after relief below 1 (EC - E0) | p | 19: +236 | +236 [+236, +236] | 1 / 0 / 0 | 2/2 as extreme; means [-236, +236] |
| cw5c_h_famine: Famine region-turns, sufficiency after relief below 0.6 (EC - E0) | t | 5: +18 | +18 [+18, +18] | 1 / 0 / 0 | 2/2 as extreme; means [-18, +18] |
| cw5c_h_famine: Famine region-turns, sufficiency after relief below 0.6 (EC - E0) | p | 19: +279 | +279 [+279, +279] | 1 / 0 / 0 | 2/2 as extreme; means [-279, +279] |
| cw5c_h_dearth_care: Dearth region-turns (EF - EC) | t | 5: +95 | +95 [+95, +95] | 1 / 0 / 0 | 2/2 as extreme; means [-95, +95] |
| cw5c_h_dearth_care: Dearth region-turns (EF - EC) | p | 19: -71 | -71 [-71, -71] | 0 / 1 / 0 | 2/2 as extreme; means [-71, +71] |
| cw5c_h_famine_care: Famine region-turns (EF - EC: more survivors to feed) | t | 5: +57 | +57 [+57, +57] | 1 / 0 / 0 | 2/2 as extreme; means [-57, +57] |
| cw5c_h_famine_care: Famine region-turns (EF - EC: more survivors to feed) | p | 19: -205 | -205 [-205, -205] | 0 / 1 / 0 | 2/2 as extreme; means [-205, +205] |
| cw5c_h_care_coins: L9 coins awarded to care envelopes (EF) | t | 5: +129 | +129 [+129, +129] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins: L9 coins awarded to care envelopes (EF) | p | 19: +1003 | +1003 [+1003, +1003] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins_cost: L9 coins awarded to care envelopes (EC) | t | 5: +122 | +122 [+122, +122] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins_cost: L9 coins awarded to care envelopes (EC) | p | 19: +1010 | +1010 [+1010, +1010] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins_unspent: Care envelope coins executed but not paid out as wages (EC) | t | 5: +97.33 | +97.33 [+97.33, +97.33] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins_unspent: Care envelope coins executed but not paid out as wages (EC) | p | 19: +683.8 | +683.8 [+683.8, +683.8] | 1 / 0 / 0 | n/a (no control) |
| cw5c_h_other_coins: L9 coins awarded to every other service (EC - E0: displacement within L9) | t | 5: +11 | +11 [+11, +11] | 1 / 0 / 0 | 2/2 as extreme; means [-11, +11] |
| cw5c_h_other_coins: L9 coins awarded to every other service (EC - E0: displacement within L9) | p | 19: -20 | -20 [-20, -20] | 0 / 1 / 0 | 2/2 as extreme; means [-20, +20] |
| cw5c_h_other_coins_care: L9 coins awarded to every other service (EF - EC) | t | 5: -22 | -22 [-22, -22] | 0 / 1 / 0 | 2/2 as extreme; means [-22, +22] |
| cw5c_h_other_coins_care: L9 coins awarded to every other service (EF - EC) | p | 19: +25 | +25 [+25, +25] | 1 / 0 / 0 | 2/2 as extreme; means [-25, +25] |
| cw5c_h_relief_coins: L9 coins awarded to granary relief (EC - E0) | t | 5: +11 | +11 [+11, +11] | 1 / 0 / 0 | 2/2 as extreme; means [-11, +11] |
| cw5c_h_relief_coins: L9 coins awarded to granary relief (EC - E0) | p | 19: -20 | -20 [-20, -20] | 0 / 1 / 0 | 2/2 as extreme; means [-20, +20] |
| cw5c_h_treasury: Treasury at the end (EC - E0) | t | 5: -150 | -150 [-150, -150] | 0 / 1 / 0 | 2/2 as extreme; means [-150, +150] |
| cw5c_h_treasury: Treasury at the end (EC - E0) | p | 19: +1575 | +1575 [+1575, +1575] | 1 / 0 / 0 | 2/2 as extreme; means [-1575, +1575] |
| cw5c_h_treasury_care: Treasury at the end (EF - EC) | t | 5: +576 | +576 [+576, +576] | 1 / 0 / 0 | 2/2 as extreme; means [-576, +576] |
| cw5c_h_treasury_care: Treasury at the end (EF - EC) | p | 19: -2238 | -2238 [-2238, -2238] | 0 / 1 / 0 | 2/2 as extreme; means [-2238, +2238] |
| cw5c_h_stability: Mean civ stability over civ-turns (EC - E0) | t | 5: -0.6423 | -0.6423 [-0.6423, -0.6423] | 0 / 1 / 0 | 2/2 as extreme; means [-0.6423, +0.6423] |
| cw5c_h_stability: Mean civ stability over civ-turns (EC - E0) | p | 19: +2.771 | +2.771 [+2.771, +2.771] | 1 / 0 / 0 | 2/2 as extreme; means [-2.771, +2.771] |
| cw5c_h_stability_care: Mean civ stability over civ-turns (EF - EC) | t | 5: -0.4011 | -0.4011 [-0.4011, -0.4011] | 0 / 1 / 0 | 2/2 as extreme; means [-0.4011, +0.4011] |
| cw5c_h_stability_care: Mean civ stability over civ-turns (EF - EC) | p | 19: -0.6866 | -0.6866 [-0.6866, -0.6866] | 0 / 1 / 0 | 2/2 as extreme; means [-0.6866, +0.6866] |
| cw5c_h_unrest: Mean city unrest over city-turns (EC - E0) | t | 5: +0.1201 | +0.1201 [+0.1201, +0.1201] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1201, +0.1201] |
| cw5c_h_unrest: Mean city unrest over city-turns (EC - E0) | p | 19: -0.03005 | -0.03005 [-0.03005, -0.03005] | 0 / 1 / 0 | 2/2 as extreme; means [-0.03005, +0.03005] |
| cw5c_h_unrest_care: Mean city unrest over city-turns (EF - EC) | t | 5: -0.09389 | -0.09389 [-0.09389, -0.09389] | 0 / 1 / 0 | 2/2 as extreme; means [-0.09389, +0.09389] |
| cw5c_h_unrest_care: Mean city unrest over city-turns (EF - EC) | p | 19: +0.002728 | +0.002728 [+0.002728, +0.002728] | 1 / 0 / 0 | 2/2 as extreme; means [-0.002728, +0.002728] |
| cw5c_h_population: Population at the end (EF - EC) | t | 5: +13 | +13 [+13, +13] | 1 / 0 / 0 | 2/2 as extreme; means [-13, +13] |
| cw5c_h_population: Population at the end (EF - EC) | p | 19: +78 | +78 [+78, +78] | 1 / 0 / 0 | 2/2 as extreme; means [-78, +78] |
| cw5c_h_population_cost: Population at the end (EC - E0) | t | 5: -13 | -13 [-13, -13] | 0 / 1 / 0 | 2/2 as extreme; means [-13, +13] |
| cw5c_h_population_cost: Population at the end (EC - E0) | p | 19: +28 | +28 [+28, +28] | 1 / 0 / 0 | 2/2 as extreme; means [-28, +28] |
| cw5c_h_migration: Agents moving between regions over the run (EF - EC) | t | 5: +154 | +154 [+154, +154] | 1 / 0 / 0 | 2/2 as extreme; means [-154, +154] |
| cw5c_h_migration: Agents moving between regions over the run (EF - EC) | p | 19: +1406 | +1406 [+1406, +1406] | 1 / 0 / 0 | 2/2 as extreme; means [-1406, +1406] |
| cw5c_h_migration_cost: Agents moving between regions over the run (EC - E0) | t | 5: -229 | -229 [-229, -229] | 0 / 1 / 0 | 2/2 as extreme; means [-229, +229] |
| cw5c_h_migration_cost: Agents moving between regions over the run (EC - E0) | p | 19: +355 | +355 [+355, +355] | 1 / 0 / 0 | 2/2 as extreme; means [-355, +355] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EC - E0 | Population at the end (sum over civilizations) | t | 5: -13 | -13 [-13, -13] | 0 / 1 / 0 | 2/2 as extreme; means [-13, +13] | recorded |
| EC - E0 | Population at the end (sum over civilizations) | p | 19: +28 | +28 [+28, +28] | 1 / 0 / 0 | 2/2 as extreme; means [-28, +28] | recorded |
| EC - E0 | Treasury at the end (sum over civilizations) | t | 5: -150 | -150 [-150, -150] | 0 / 1 / 0 | 2/2 as extreme; means [-150, +150] | recorded |
| EC - E0 | Treasury at the end (sum over civilizations) | p | 19: +1575 | +1575 [+1575, +1575] | 1 / 0 / 0 | 2/2 as extreme; means [-1575, +1575] | recorded |
| EC - E0 | Food shortfall after relief over the run (food) | t | 5: -312.1 | -312.1 [-312.1, -312.1] | 0 / 1 / 0 | 2/2 as extreme; means [-312.1, +312.1] | recorded |
| EC - E0 | Food shortfall after relief over the run (food) | p | 19: +292.7 | +292.7 [+292.7, +292.7] | 1 / 0 / 0 | 2/2 as extreme; means [-292.7, +292.7] | recorded |
| EC - E0 | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EC - E0 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EC - E0 | Deaths by epidemic (the epidemic authority) | t | 5: -7 | -7 [-7, -7] | 0 / 1 / 0 | 2/2 as extreme; means [-7, +7] | recorded |
| EC - E0 | Deaths by epidemic (the epidemic authority) | p | 19: -35 | -35 [-35, -35] | 0 / 1 / 0 | 2/2 as extreme; means [-35, +35] | recorded |
| EC - E0 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EC - E0 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EC - E0 | Agents migrating between regions over the run | t | 5: -229 | -229 [-229, -229] | 0 / 1 / 0 | 2/2 as extreme; means [-229, +229] | recorded |
| EC - E0 | Agents migrating between regions over the run | p | 19: +355 | +355 [+355, +355] | 1 / 0 / 0 | 2/2 as extreme; means [-355, +355] | recorded |
| EC - E0 | Mean wealth Gini of living civilizations at the end | t | 5: +0.0362 | +0.0362 [+0.0362, +0.0362] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0362, +0.0362] | recorded |
| EC - E0 | Mean wealth Gini of living civilizations at the end | p | 19: -0.03572 | -0.03572 [-0.03572, -0.03572] | 0 / 1 / 0 | 2/2 as extreme; means [-0.03572, +0.03572] | recorded |
| EC - E0 | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EC - E0 | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - EC | Population at the end (sum over civilizations) | t | 5: +13 | +13 [+13, +13] | 1 / 0 / 0 | 2/2 as extreme; means [-13, +13] | recorded |
| EF - EC | Population at the end (sum over civilizations) | p | 19: +78 | +78 [+78, +78] | 1 / 0 / 0 | 2/2 as extreme; means [-78, +78] | recorded |
| EF - EC | Treasury at the end (sum over civilizations) | t | 5: +576 | +576 [+576, +576] | 1 / 0 / 0 | 2/2 as extreme; means [-576, +576] | recorded |
| EF - EC | Treasury at the end (sum over civilizations) | p | 19: -2238 | -2238 [-2238, -2238] | 0 / 1 / 0 | 2/2 as extreme; means [-2238, +2238] | recorded |
| EF - EC | Food shortfall after relief over the run (food) | t | 5: +705.6 | +705.6 [+705.6, +705.6] | 1 / 0 / 0 | 2/2 as extreme; means [-705.6, +705.6] | recorded |
| EF - EC | Food shortfall after relief over the run (food) | p | 19: +2312 | +2312 [+2312, +2312] | 1 / 0 / 0 | 2/2 as extreme; means [-2312, +2312] | recorded |
| EF - EC | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - EC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - EC | Deaths by epidemic (the epidemic authority) | t | 5: -38 | -38 [-38, -38] | 0 / 1 / 0 | 2/2 as extreme; means [-38, +38] | recorded |
| EF - EC | Deaths by epidemic (the epidemic authority) | p | 19: -266 | -266 [-266, -266] | 0 / 1 / 0 | 2/2 as extreme; means [-266, +266] | recorded |
| EF - EC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - EC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - EC | Agents migrating between regions over the run | t | 5: +154 | +154 [+154, +154] | 1 / 0 / 0 | 2/2 as extreme; means [-154, +154] | recorded |
| EF - EC | Agents migrating between regions over the run | p | 19: +1406 | +1406 [+1406, +1406] | 1 / 0 / 0 | 2/2 as extreme; means [-1406, +1406] | recorded |
| EF - EC | Mean wealth Gini of living civilizations at the end | t | 5: -0.007893 | -0.007893 [-0.007893, -0.007893] | 0 / 1 / 0 | 2/2 as extreme; means [-0.007893, +0.007893] | recorded |
| EF - EC | Mean wealth Gini of living civilizations at the end | p | 19: +0.0453 | +0.0453 [+0.0453, +0.0453] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0453, +0.0453] | recorded |
| EF - EC | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - EC | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - E0 | Population at the end (sum over civilizations) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] | recorded |
| EF - E0 | Population at the end (sum over civilizations) | p | 19: +106 | +106 [+106, +106] | 1 / 0 / 0 | 2/2 as extreme; means [-106, +106] | recorded |
| EF - E0 | Treasury at the end (sum over civilizations) | t | 5: +426 | +426 [+426, +426] | 1 / 0 / 0 | 2/2 as extreme; means [-426, +426] | recorded |
| EF - E0 | Treasury at the end (sum over civilizations) | p | 19: -663 | -663 [-663, -663] | 0 / 1 / 0 | 2/2 as extreme; means [-663, +663] | recorded |
| EF - E0 | Food shortfall after relief over the run (food) | t | 5: +393.5 | +393.5 [+393.5, +393.5] | 1 / 0 / 0 | 2/2 as extreme; means [-393.5, +393.5] | recorded |
| EF - E0 | Food shortfall after relief over the run (food) | p | 19: +2605 | +2605 [+2605, +2605] | 1 / 0 / 0 | 2/2 as extreme; means [-2605, +2605] | recorded |
| EF - E0 | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - E0 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - E0 | Deaths by epidemic (the epidemic authority) | t | 5: -45 | -45 [-45, -45] | 0 / 1 / 0 | 2/2 as extreme; means [-45, +45] | recorded |
| EF - E0 | Deaths by epidemic (the epidemic authority) | p | 19: -301 | -301 [-301, -301] | 0 / 1 / 0 | 2/2 as extreme; means [-301, +301] | recorded |
| EF - E0 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - E0 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - E0 | Agents migrating between regions over the run | t | 5: -75 | -75 [-75, -75] | 0 / 1 / 0 | 2/2 as extreme; means [-75, +75] | recorded |
| EF - E0 | Agents migrating between regions over the run | p | 19: +1761 | +1761 [+1761, +1761] | 1 / 0 / 0 | 2/2 as extreme; means [-1761, +1761] | recorded |
| EF - E0 | Mean wealth Gini of living civilizations at the end | t | 5: +0.02831 | +0.02831 [+0.02831, +0.02831] | 1 / 0 / 0 | 2/2 as extreme; means [-0.02831, +0.02831] | recorded |
| EF - E0 | Mean wealth Gini of living civilizations at the end | p | 19: +0.009575 | +0.009575 [+0.009575, +0.009575] | 1 / 0 / 0 | 2/2 as extreme; means [-0.009575, +0.009575] | recorded |
| EF - E0 | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - E0 | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| E0 | 7.0 [7.0, 7.0] | 19.1 [19.1, 19.1] |
| EC | 6.6 [6.6, 6.6] | 20.2 [20.2, 20.2] |
| EF | 6.8 [6.8, 6.8] | 17.8 [17.8, 17.8] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
