# CW5c: S4 bounded epidemic care capacity (C2)

Cohort held. Runs: 36; failed: 0 (missing outcomes: 0); simulation and extraction seconds 546 (0.152 core-hours)

Identity digests: 73d906ec8fcf3bfd0a919471d3c7714736f3ec44833061b64f5ae51d02fbeab3 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"epidemic_care": [1], "local_budgets": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"local_budgets": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| EC | t | 3301: activated; 3302: activated; 3303: activated; 3304: activated; 3305: activated; 3306: activated | 6 of 6 |
| EC | p | 3401: activated; 3402: activated; 3403: activated; 3404: activated; 3405: activated; 3406: activated | 6 of 6 |
| EF | t | 3301: activated; 3302: activated; 3303: activated; 3304: activated; 3305: activated; 3306: activated | 6 of 6 |
| EF | p | 3401: activated; 3402: activated; 3403: activated; 3404: activated; 3405: activated; 3406: activated | 6 of 6 |

## CW5c mechanism check (not evidence that care works: coverage is about 1 by construction)

Fatality per infectious person-turn in each arm's own covered region-turns, the EF/EC ratio, and the mean care factor EF applied there (combined / techniques: 1 - 0.3 x coverage under the floor) with its floored count. Within a pathogen the ratio should sit near the factor; pooled over pathogens it also carries the arms' different pathogen mix after they diverge (see the table by pathogen below).

| World | EC own covered | EF own covered | EF / EC | EF mean applied factor | EF floored | EF mean coverage |
| --- | --- | --- | --- | --- | --- | --- |
| t3301 | 0.263 | 0.1799 | 0.684 | 0.7013 | 0 | 0.9958 |
| t3302 | 0.3094 | 0.1867 | 0.6035 | 0.7021 | 0 | 0.993 |
| t3303 | 0.1252 | 0.07892 | 0.6304 | 0.7002 | 0 | 0.9994 |
| t3304 | 0.3464 | 0.1648 | 0.4759 | 0.7 | 0 | 1 |
| t3305 | 0.1453 | 0.1108 | 0.7622 | 0.7011 | 0 | 0.9964 |
| t3306 | 0.1998 | 0.1585 | 0.7933 | 0.7012 | 0 | 0.996 |
| p3401 | 0.2128 | 0.157 | 0.7378 | 0.7009 | 0 | 0.997 |
| p3402 | 0.209 | 0.1513 | 0.7242 | 0.7024 | 0 | 0.9921 |
| p3403 | 0.1852 | 0.1359 | 0.7334 | 0.7012 | 0 | 0.9959 |
| p3404 | 0.1813 | 0.2179 | 1.202 | 0.7008 | 0 | 0.9973 |
| p3405 | 0.1937 | 0.1182 | 0.6099 | 0.7008 | 0 | 0.9974 |
| p3406 | 0.2 | 0.1612 | 0.8057 | 0.7013 | 0 | 0.9955 |

## CW5c mechanism check by pathogen (EC's covered cells, both arms)

Deaths per infectious person-turn of each pathogen at the cells EC covered, in EC and in EF, and the EF/EC ratio (n/a: no infectious person-turn of that pathogen there in an arm).

| World | Pathogen | EC | EF | EF / EC |
| --- | --- | --- | --- | --- |
| t3301 | plague | 0.3945 | 0.31 | 0.7859 |
| t3301 | fever | 0.07051 | 0.05299 | 0.7515 |
| t3301 | pestilence | 0.8205 | 0.6441 | 0.7849 |
| t3302 | plague | 0.3686 | 0.2885 | 0.7826 |
| t3302 | pox | 0.4039 | 0.2366 | 0.5858 |
| t3302 | fever | 0.0865 | 0.06074 | 0.7021 |
| t3302 | pestilence | 1.446 | 1.001 | 0.6921 |
| t3303 | fever | 0.08364 | 0.05373 | 0.6424 |
| t3303 | flux | 0.1702 | 0.1079 | 0.6341 |
| t3304 | plague | 0.461 | 0.3153 | 0.684 |
| t3304 | fever | 0.1737 | 0.1011 | 0.5823 |
| t3305 | fever | 0.08547 | 0.06309 | 0.7381 |
| t3305 | flux | 0.1472 | 0.09899 | 0.6725 |
| t3305 | pestilence | 0.9235 | 0.6393 | 0.6923 |
| t3306 | plague | 0.3733 | 0.2979 | 0.7982 |
| t3306 | pox | 0.2702 | 0.1573 | 0.5822 |
| t3306 | fever | 0.08894 | 0.06212 | 0.6984 |
| t3306 | flux | 0.1605 | 0.126 | 0.7852 |
| p3401 | plague | 0.3748 | 0.2833 | 0.7558 |
| p3401 | pox | 0.2698 | 0.2347 | 0.8699 |
| p3401 | fever | 0.08818 | 0.0702 | 0.796 |
| p3402 | plague | 0.3735 | 0.3136 | 0.8396 |
| p3402 | pox | 0.296 | 0.222 | 0.7502 |
| p3402 | fever | 0.08141 | 0.06082 | 0.7471 |
| p3403 | plague | 0.4911 | 0.3764 | 0.7665 |
| p3403 | pox | 0.2883 | 0.2042 | 0.708 |
| p3403 | fever | 0.07487 | 0.04603 | 0.6147 |
| p3404 | plague | 0.4381 | 0.3898 | 0.8899 |
| p3404 | pox | 0.2989 | 0.2114 | 0.7073 |
| p3404 | fever | 0.07409 | 0.06382 | 0.8614 |
| p3404 | pestilence | n/a | 0.4586 | n/a |
| p3405 | plague | 0.4542 | 0.4272 | 0.9404 |
| p3405 | pox | 0.2957 | 0.2541 | 0.8593 |
| p3405 | fever | 0.07279 | 0.05301 | 0.7283 |
| p3406 | plague | 0.3724 | 0.2704 | 0.726 |
| p3406 | pox | 0.2973 | 0.2143 | 0.7209 |
| p3406 | fever | 0.06419 | 0.04943 | 0.7701 |

## CW5c reach and attenuation

Reach: the share of EC's epidemic deaths in EC's covered region-turns. Implied maximum: reach x (1 - EF's mean applied factor), the fall in world deaths if care cut every covered death by that factor and nothing else changed. Realized: the EF - EC change of the world epidemic death rate, relative to EC.

| World | EC reach | EF mean applied factor | Implied maximum fall | Realized change |
| --- | --- | --- | --- | --- |
| t3301 | 0.8585 | 0.7013 | -0.256 | -0.280 |
| t3302 | 0.4772 | 0.7021 | -0.142 | -0.420 |
| t3303 | 0.9077 | 0.7002 | -0.272 | -0.404 |
| t3304 | 0.5556 | 0.7 | -0.167 | -0.253 |
| t3305 | 0.821 | 0.7011 | -0.245 | -0.203 |
| t3306 | 0.6528 | 0.7012 | -0.195 | -0.007 |
| p3401 | 0.7984 | 0.7009 | -0.239 | +0.025 |
| p3402 | 0.7534 | 0.7024 | -0.224 | -0.066 |
| p3403 | 0.5778 | 0.7012 | -0.173 | -0.116 |
| p3404 | 0.8227 | 0.7008 | -0.246 | +0.573 |
| p3405 | 0.7005 | 0.7008 | -0.210 | -0.389 |
| p3406 | 0.7301 | 0.7013 | -0.218 | +0.078 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5c_world_death_rate: World epidemic deaths per 1,000 person-turns over the whole run (EF - EC) | t | 3301: -1.711; 3302: -3.752; 3303: -1.382; 3304: -0.2487; 3305: -0.8495; 3306: -0.05362 | -1.333 [-3.752, -0.05362] | 0 / 6 / 0 | 2/64 as extreme; means [-1.333, +1.333] |
| cw5c_world_death_rate: World epidemic deaths per 1,000 person-turns over the whole run (EF - EC) | p | 3401: +0.1702; 3402: -0.4366; 3403: -0.6227; 3404: +3.076; 3405: -2.157; 3406: +0.4642 | +0.08237 [-2.157, +3.076] | 3 / 3 / 0 | 54/64 as extreme; means [-1.154, +1.154] |
| cw5c_itt_cfr: Epidemic deaths per infectious person-turn in the region-turns EC covered, read at the same cells in both arms (EF - EC; intention to treat) | t | 3301: -0.0791; 3302: -0.1242; 3303: -0.04757; 3304: -0.1249; 3305: -0.04; 3306: -0.03898 | -0.0758 [-0.1249, -0.03898] | 0 / 6 / 0 | 2/64 as extreme; means [-0.0758, +0.0758] |
| cw5c_itt_cfr: Epidemic deaths per infectious person-turn in the region-turns EC covered, read at the same cells in both arms (EF - EC; intention to treat) | p | 3401: -0.0358; 3402: -0.04091; 3403: -0.04495; 3404: +0.03485; 3405: -0.06522; 3406: -0.03893 | -0.03182 [-0.06522, +0.03485] | 1 / 5 / 0 | 4/64 as extreme; means [-0.04344, +0.04344] |
| cw5c_world_dpi: World epidemic deaths per infectious person-turn over the whole run (EF - EC) | t | 3301: -0.07321; 3302: -0.1394; 3303: -0.03828; 3304: -0.06365; 3305: -0.03398; 3306: -0.03853 | -0.0645 [-0.1394, -0.03398] | 0 / 6 / 0 | 2/64 as extreme; means [-0.0645, +0.0645] |
| cw5c_world_dpi: World epidemic deaths per infectious person-turn over the whole run (EF - EC) | p | 3401: -0.02533; 3402: -0.03402; 3403: -0.03497; 3404: +0.05472; 3405: -0.06303; 3406: -0.02383 | -0.02108 [-0.06303, +0.05472] | 1 / 5 / 0 | 14/64 as extreme; means [-0.03932, +0.03932] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5c_world_deaths: World epidemic deaths, count (EF - EC) | t | 3301: -84; 3302: -100; 3303: -47; 3304: -5; 3305: -23; 3306: -11 | -45 [-100, -5] | 0 / 6 / 0 | 2/64 as extreme; means [-45, +45] |
| cw5c_world_deaths: World epidemic deaths, count (EF - EC) | p | 3401: +21; 3402: -11; 3403: -70; 3404: +199; 3405: -196; 3406: +80 | +3.833 [-196, +199] | 3 / 3 / 0 | 56/64 as extreme; means [-96.17, +96.17] |
| cw5c_world_death_rate_vs_none: World epidemic deaths per 1,000 person-turns (EF - E0) | t | 3301: -1.611; 3302: +0.0413; 3303: -1.758; 3304: -0.2409; 3305: -0.8478; 3306: -0.6216 | -0.8396 [-1.758, +0.0413] | 1 / 5 / 0 | 4/64 as extreme; means [-0.8534, +0.8534] |
| cw5c_world_death_rate_vs_none: World epidemic deaths per 1,000 person-turns (EF - E0) | p | 3401: +2.567; 3402: +1.987; 3403: +0.3167; 3404: +1.299; 3405: -2.354; 3406: -1.34 | +0.4127 [-2.354, +2.567] | 4 / 2 / 0 | 40/64 as extreme; means [-1.644, +1.644] |
| cw5c_cost_world_death_rate: World epidemic deaths per 1,000 person-turns (EC - E0: the cost's effect) | t | 3301: +0.09959; 3302: +3.793; 3303: -0.3754; 3304: +0.007783; 3305: +0.001645; 3306: -0.568 | +0.4932 [-0.568, +3.793] | 4 / 2 / 0 | 50/64 as extreme; means [-0.8076, +0.8076] |
| cw5c_cost_world_death_rate: World epidemic deaths per 1,000 person-turns (EC - E0: the cost's effect) | p | 3401: +2.396; 3402: +2.424; 3403: +0.9394; 3404: -1.777; 3405: -0.1968; 3406: -1.804 | +0.3303 [-1.804, +2.424] | 3 / 3 / 0 | 44/64 as extreme; means [-1.59, +1.59] |
| cw5c_continuing_deaths_per_case: Deaths per new infection in continuing-outbreak region-turns (EF - EC) | t | 3301: -0.02326; 3302: -0.04229; 3303: -0.01163; 3304: -0.01776; 3305: -0.00953; 3306: -0.01075 | -0.0192 [-0.04229, -0.00953] | 0 / 6 / 0 | 2/64 as extreme; means [-0.0192, +0.0192] |
| cw5c_continuing_deaths_per_case: Deaths per new infection in continuing-outbreak region-turns (EF - EC) | p | 3401: -0.008166; 3402: -0.008679; 3403: -0.01111; 3404: +0.01721; 3405: -0.01795; 3406: -0.007924 | -0.006105 [-0.01795, +0.01721] | 1 / 5 / 0 | 18/64 as extreme; means [-0.01184, +0.01184] |
| cw5c_continuing_deaths_per_case_vs_none: Deaths per new infection in continuing-outbreak region-turns (EF - E0) | t | 3301: -0.02574; 3302: -0.03308; 3303: -0.01264; 3304: -0.02175; 3305: -0.02188; 3306: -0.005034 | -0.02002 [-0.03308, -0.005034] | 0 / 6 / 0 | 2/64 as extreme; means [-0.02002, +0.02002] |
| cw5c_continuing_deaths_per_case_vs_none: Deaths per new infection in continuing-outbreak region-turns (EF - E0) | p | 3401: +0.005071; 3402: +0.001355; 3403: -0.0008829; 3404: -0.002864; 3405: -0.01875; 3406: -0.01444 | -0.005086 [-0.01875, +0.005071] | 2 / 4 / 0 | 22/64 as extreme; means [-0.007228, +0.007228] |
| cw5c_covered_region_turns: Covered region-turns (EF - EC; selection) | t | 3301: +25; 3302: +51; 3303: -12; 3304: -4; 3305: +49; 3306: +52 | +26.83 [-12, +52] | 4 / 2 / 0 | 8/64 as extreme; means [-32.17, +32.17] |
| cw5c_covered_region_turns: Covered region-turns (EF - EC; selection) | p | 3401: +48; 3402: -204; 3403: +339; 3404: -451; 3405: +167; 3406: +296 | +32.5 [-451, +339] | 4 / 2 / 0 | 50/64 as extreme; means [-250.8, +250.8] |
| cw5c_mech_covered_dpi: Mechanism check: deaths per infectious person-turn in each arm's own covered region-turns (EF - EC; selection; see the ratio table) | t | 3301: -0.0831; 3302: -0.1227; 3303: -0.04627; 3304: -0.1816; 3305: -0.03455; 3306: -0.04129 | -0.08491 [-0.1816, -0.03455] | 0 / 6 / 0 | 2/64 as extreme; means [-0.08491, +0.08491] |
| cw5c_mech_covered_dpi: Mechanism check: deaths per infectious person-turn in each arm's own covered region-turns (EF - EC; selection; see the ratio table) | p | 3401: -0.05579; 3402: -0.05762; 3403: -0.04939; 3404: +0.03664; 3405: -0.07558; 3406: -0.03887 | -0.0401 [-0.07558, +0.03664] | 1 / 5 / 0 | 4/64 as extreme; means [-0.05232, +0.05232] |
| cw5c_mech_factor: Mechanism check: mean care factor applied in covered region-turns (EF) | t | 3301: +0.7013; 3302: +0.7021; 3303: +0.7002; 3304: +0.7; 3305: +0.7011; 3306: +0.7012 | +0.701 [+0.7, +0.7021] | 6 / 0 / 0 | n/a (no control) |
| cw5c_mech_factor: Mechanism check: mean care factor applied in covered region-turns (EF) | p | 3401: +0.7009; 3402: +0.7024; 3403: +0.7012; 3404: +0.7008; 3405: +0.7008; 3406: +0.7013 | +0.7012 [+0.7008, +0.7024] | 6 / 0 / 0 | n/a (no control) |
| cw5c_mech_plague: Mechanism check by pathogen: plague deaths per infectious person-turn at EC's covered cells (EF - EC) | t | 3301: -0.08447; 3302: -0.08013; 3303: unknown; 3304: -0.1457; 3305: unknown; 3306: -0.07532 | -0.09639 [-0.1457, -0.07532] | 0 / 4 / 0 | 2/16 as extreme; means [-0.09639, +0.09639] |
| cw5c_mech_plague: Mechanism check by pathogen: plague deaths per infectious person-turn at EC's covered cells (EF - EC) | p | 3401: -0.09153; 3402: -0.05991; 3403: -0.1147; 3404: -0.04824; 3405: -0.02706; 3406: -0.102 | -0.07391 [-0.1147, -0.02706] | 0 / 6 / 0 | 2/64 as extreme; means [-0.07391, +0.07391] |
| cw5c_mech_pox: Mechanism check by pathogen: pox deaths per infectious person-turn at EC's covered cells (EF - EC) | t | 3301: unknown; 3302: -0.1673; 3303: unknown; 3304: unknown; 3305: unknown; 3306: -0.1129 | -0.1401 [-0.1673, -0.1129] | 0 / 2 / 0 | 2/4 as extreme; means [-0.1401, +0.1401] |
| cw5c_mech_pox: Mechanism check by pathogen: pox deaths per infectious person-turn at EC's covered cells (EF - EC) | p | 3401: -0.03511; 3402: -0.07392; 3403: -0.08419; 3404: -0.08747; 3405: -0.04162; 3406: -0.08298 | -0.06755 [-0.08747, -0.03511] | 0 / 6 / 0 | 2/64 as extreme; means [-0.06755, +0.06755] |
| cw5c_mech_fever: Mechanism check by pathogen: fever deaths per infectious person-turn at EC's covered cells (EF - EC) | t | 3301: -0.01752; 3302: -0.02577; 3303: -0.02991; 3304: -0.07257; 3305: -0.02239; 3306: -0.02682 | -0.0325 [-0.07257, -0.01752] | 0 / 6 / 0 | 2/64 as extreme; means [-0.0325, +0.0325] |
| cw5c_mech_fever: Mechanism check by pathogen: fever deaths per infectious person-turn at EC's covered cells (EF - EC) | p | 3401: -0.01799; 3402: -0.02059; 3403: -0.02885; 3404: -0.01027; 3405: -0.01978; 3406: -0.01476 | -0.01871 [-0.02885, -0.01027] | 0 / 6 / 0 | 2/64 as extreme; means [-0.01871, +0.01871] |
| cw5c_mech_flux: Mechanism check by pathogen: flux deaths per infectious person-turn at EC's covered cells (EF - EC) | t | 3301: unknown; 3302: unknown; 3303: -0.06228; 3304: unknown; 3305: -0.0482; 3306: -0.03447 | -0.04832 [-0.06228, -0.03447] | 0 / 3 / 0 | 2/8 as extreme; means [-0.04832, +0.04832] |
| cw5c_mech_flux: Mechanism check by pathogen: flux deaths per infectious person-turn at EC's covered cells (EF - EC) | p | 3401: unknown; 3402: unknown; 3403: unknown; 3404: unknown; 3405: unknown; 3406: unknown | n/a | 0 / 0 / 0 | n/a |
| cw5c_mech_pestilence: Mechanism check by pathogen: pestilence deaths per infectious person-turn at EC's covered cells (EF - EC) | t | 3301: -0.1765; 3302: -0.4453; 3303: unknown; 3304: unknown; 3305: -0.2842; 3306: unknown | -0.302 [-0.4453, -0.1765] | 0 / 3 / 0 | 2/8 as extreme; means [-0.302, +0.302] |
| cw5c_mech_pestilence: Mechanism check by pathogen: pestilence deaths per infectious person-turn at EC's covered cells (EF - EC) | p | 3401: unknown; 3402: unknown; 3403: unknown; 3404: unknown; 3405: unknown; 3406: unknown | n/a | 0 / 0 / 0 | n/a |
| cw5c_mean_coverage: Mean coverage over region-turns with capacity (EF) | t | 3301: +0.9958; 3302: +0.993; 3303: +0.9994; 3304: +1; 3305: +0.9964; 3306: +0.996 | +0.9968 [+0.993, +1] | 6 / 0 / 0 | n/a (no control) |
| cw5c_mean_coverage: Mean coverage over region-turns with capacity (EF) | p | 3401: +0.997; 3402: +0.9921; 3403: +0.9959; 3404: +0.9973; 3405: +0.9974; 3406: +0.9955 | +0.9959 [+0.9921, +0.9974] | 6 / 0 / 0 | n/a (no control) |
| cw5c_reach: Reach: share of EC's epidemic deaths in its covered region-turns (EC) | t | 3301: +0.8585; 3302: +0.4772; 3303: +0.9077; 3304: +0.5556; 3305: +0.821; 3306: +0.6528 | +0.7121 [+0.4772, +0.9077] | 6 / 0 / 0 | n/a (no control) |
| cw5c_reach: Reach: share of EC's epidemic deaths in its covered region-turns (EC) | p | 3401: +0.7984; 3402: +0.7534; 3403: +0.5778; 3404: +0.8227; 3405: +0.7005; 3406: +0.7301 | +0.7305 [+0.5778, +0.8227] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time: Carer farm time removed, worker-turns (EF) | t | 3301: +237.4; 3302: +159.7; 3303: +184.2; 3304: +11.81; 3305: +218; 3306: +183.1 | +165.7 [+11.81, +237.4] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time: Carer farm time removed, worker-turns (EF) | p | 3401: +764.4; 3402: +546.6; 3403: +656.8; 3404: +652.7; 3405: +522.1; 3406: +771.1 | +652.3 [+522.1, +771.1] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time_cost: Carer farm time removed, worker-turns (EC) | t | 3301: +227.1; 3302: +119.3; 3303: +198; 3304: +12.28; 3305: +193.4; 3306: +160.2 | +151.7 [+12.28, +227.1] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_farm_time_cost: Carer farm time removed, worker-turns (EC) | p | 3401: +714; 3402: +595.7; 3403: +487; 3404: +728; 3405: +490.3; 3406: +603 | +603 [+487, +728] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_carers_held: Carer-turns held from drafting and academy teaching (EF) | t | 3301: +695; 3302: +404; 3303: +506; 3304: +34; 3305: +707; 3306: +468 | +469 [+34, +707] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_carers_held: Carer-turns held from drafting and academy teaching (EF) | p | 3401: +1929; 3402: +1380; 3403: +1698; 3404: +1627; 3405: +1445; 3406: +1951 | +1672 [+1380, +1951] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_carers_held_cost: Carer-turns held from drafting and academy teaching (EC) | t | 3301: +664; 3302: +323; 3303: +527; 3304: +37; 3305: +644; 3306: +415 | +435 [+37, +664] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_carers_held_cost: Carer-turns held from drafting and academy teaching (EC) | p | 3401: +1870; 3402: +1580; 3403: +1312; 3404: +2075; 3405: +1275; 3406: +1640 | +1625 [+1275, +2075] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_wages: Care wages paid, treasury units (EF) | t | 3301: +118.6; 3302: +79.83; 3303: +92.02; 3304: +5.904; 3305: +109; 3306: +91.56 | +82.82 [+5.904, +118.6] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_wages: Care wages paid, treasury units (EF) | p | 3401: +382.2; 3402: +273.3; 3403: +328.4; 3404: +326.3; 3405: +260.9; 3406: +385.4 | +326.1 [+260.9, +385.4] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_wages_cost: Care wages paid, treasury units (EC) | t | 3301: +113.6; 3302: +59.26; 3303: +99; 3304: +6.14; 3305: +96.68; 3306: +80.11 | +75.79 [+6.14, +113.6] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_wages_cost: Care wages paid, treasury units (EC) | p | 3401: +357; 3402: +297.3; 3403: +243.2; 3404: +363.7; 3405: +245.1; 3406: +301.5 | +301.3 [+243.2, +363.7] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld: Carers' ordinary income withheld, wealth units (EF) | t | 3301: +36.16; 3302: +23.06; 3303: +30.29; 3304: +1.818; 3305: +14.63; 3306: +26.17 | +22.02 [+1.818, +36.16] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld: Carers' ordinary income withheld, wealth units (EF) | p | 3401: +92.95; 3402: +66.35; 3403: +91.26; 3404: +88.63; 3405: +81.14; 3406: +81.42 | +83.63 [+66.35, +92.95] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld_cost: Carers' ordinary income withheld, wealth units (EC) | t | 3301: +31.03; 3302: +19.31; 3303: +32.44; 3304: +1.831; 3305: +12.33; 3306: +21.69 | +19.77 [+1.831, +32.44] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_income_withheld_cost: Carers' ordinary income withheld, wealth units (EC) | p | 3401: +83.62; 3402: +74.9; 3403: +74.18; 3404: +101.9; 3405: +74.26; 3406: +64.2 | +78.84 [+64.2, +101.9] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_unpaid_bills: Care wage bills refused at payment (EF) | t | 3301: +0; 3302: +0; 3303: +0; 3304: +0; 3305: +0; 3306: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw5c_h_unpaid_bills: Care wage bills refused at payment (EF) | p | 3401: +0; 3402: +0; 3403: +0; 3404: +0; 3405: +0; 3406: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw5c_h_unpaid_bills_cost: Care wage bills refused at payment (EC) | t | 3301: +0; 3302: +0; 3303: +0; 3304: +0; 3305: +0; 3306: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw5c_h_unpaid_bills_cost: Care wage bills refused at payment (EC) | p | 3401: +0; 3402: +0; 3403: +0; 3404: +0; 3405: +0; 3406: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw5c_h_food_shortfall: Food shortfall after relief over the run (EF - EC) | t | 3301: +202.2; 3302: +990; 3303: +257.1; 3304: +460.6; 3305: +204.4; 3306: -348.8 | +294.3 [-348.8, +990] | 5 / 1 / 0 | 10/64 as extreme; means [-410.5, +410.5] |
| cw5c_h_food_shortfall: Food shortfall after relief over the run (EF - EC) | p | 3401: -1040; 3402: -936.5; 3403: +300; 3404: -1901; 3405: +1235; 3406: -447.3 | -465.1 [-1901, +1235] | 2 / 4 / 0 | 24/64 as extreme; means [-976.7, +976.7] |
| cw5c_h_food_shortfall_cost: Food shortfall after relief over the run (EC - E0: the cost) | t | 3301: +278.9; 3302: -404.2; 3303: -112.8; 3304: -266.6; 3305: -442.1; 3306: +357.3 | -98.25 [-442.1, +357.3] | 2 / 4 / 0 | 30/64 as extreme; means [-310.3, +310.3] |
| cw5c_h_food_shortfall_cost: Food shortfall after relief over the run (EC - E0: the cost) | p | 3401: -2423; 3402: +21.35; 3403: -241.3; 3404: +2431; 3405: +103; 3406: +1714 | +267.5 [-2423, +2431] | 4 / 2 / 0 | 50/64 as extreme; means [-1156, +1156] |
| cw5c_h_dearth: Dearth region-turns, sufficiency after relief below 1 (EC - E0) | t | 3301: +12; 3302: -25; 3303: +35; 3304: -7; 3305: +50; 3306: +26 | +15.17 [-25, +50] | 4 / 2 / 0 | 14/64 as extreme; means [-25.83, +25.83] |
| cw5c_h_dearth: Dearth region-turns, sufficiency after relief below 1 (EC - E0) | p | 3401: -95; 3402: +308; 3403: +104; 3404: -56; 3405: +24; 3406: +321 | +101 [-95, +321] | 4 / 2 / 0 | 18/64 as extreme; means [-151.3, +151.3] |
| cw5c_h_famine: Famine region-turns, sufficiency after relief below 0.6 (EC - E0) | t | 3301: +13; 3302: -55; 3303: +52; 3304: -6; 3305: +69; 3306: +33 | +17.67 [-55, +69] | 4 / 2 / 0 | 24/64 as extreme; means [-38, +38] |
| cw5c_h_famine: Famine region-turns, sufficiency after relief below 0.6 (EC - E0) | p | 3401: +20; 3402: +312; 3403: +160; 3404: -268; 3405: -24; 3406: +353 | +92.17 [-268, +353] | 4 / 2 / 0 | 22/64 as extreme; means [-189.5, +189.5] |
| cw5c_h_dearth_care: Dearth region-turns (EF - EC) | t | 3301: +43; 3302: +86; 3303: +4; 3304: +22; 3305: -24; 3306: -36 | +15.83 [-36, +86] | 4 / 2 / 0 | 28/64 as extreme; means [-35.83, +35.83] |
| cw5c_h_dearth_care: Dearth region-turns (EF - EC) | p | 3401: -161; 3402: -513; 3403: +38; 3404: -18; 3405: +114; 3406: -244 | -130.7 [-513, +114] | 2 / 4 / 0 | 14/64 as extreme; means [-181.3, +181.3] |
| cw5c_h_famine_care: Famine region-turns (EF - EC: more survivors to feed) | t | 3301: -11; 3302: +77; 3303: -69; 3304: +6; 3305: -39; 3306: -60 | -16 [-69, +77] | 2 / 4 / 0 | 34/64 as extreme; means [-43.67, +43.67] |
| cw5c_h_famine_care: Famine region-turns (EF - EC: more survivors to feed) | p | 3401: -174; 3402: -392; 3403: +0; 3404: +158; 3405: +106; 3406: -329 | -105.2 [-392, +158] | 2 / 3 / 1 | 20/64 as extreme; means [-193.2, +193.2] |
| cw5c_h_care_coins: L9 coins awarded to care envelopes (EF) | t | 3301: +424; 3302: +236; 3303: +288; 3304: +33; 3305: +374; 3306: +342 | +282.8 [+33, +424] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins: L9 coins awarded to care envelopes (EF) | p | 3401: +1186; 3402: +759; 3403: +1007; 3404: +914; 3405: +948; 3406: +1034 | +974.7 [+759, +1186] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins_cost: L9 coins awarded to care envelopes (EC) | t | 3301: +429; 3302: +203; 3303: +251; 3304: +35; 3305: +338; 3306: +349 | +267.5 [+35, +429] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins_cost: L9 coins awarded to care envelopes (EC) | p | 3401: +1128; 3402: +917; 3403: +807; 3404: +1059; 3405: +854; 3406: +981 | +957.7 [+807, +1128] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins_unspent: Care envelope coins executed but not paid out as wages (EC) | t | 3301: +312.4; 3302: +140.7; 3303: +151; 3304: +28.86; 3305: +240.3; 3306: +266.9 | +190 [+28.86, +312.4] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_care_coins_unspent: Care envelope coins executed but not paid out as wages (EC) | p | 3401: +765; 3402: +612.7; 3403: +559.8; 3404: +691.3; 3405: +603.9; 3406: +670.5 | +650.5 [+559.8, +765] | 6 / 0 / 0 | n/a (no control) |
| cw5c_h_other_coins: L9 coins awarded to every other service (EC - E0: displacement within L9) | t | 3301: -8; 3302: -18; 3303: +4; 3304: -2; 3305: -3; 3306: -3 | -5 [-18, +4] | 1 / 5 / 0 | 10/64 as extreme; means [-6.333, +6.333] |
| cw5c_h_other_coins: L9 coins awarded to every other service (EC - E0: displacement within L9) | p | 3401: +0; 3402: -13; 3403: -15; 3404: -10; 3405: -2; 3406: +31 | -1.5 [-15, +31] | 1 / 4 / 1 | 60/64 as extreme; means [-11.83, +11.83] |
| cw5c_h_other_coins_care: L9 coins awarded to every other service (EF - EC) | t | 3301: +1; 3302: -6; 3303: -2; 3304: +0; 3305: -6; 3306: +8 | -0.8333 [-6, +8] | 2 / 3 / 1 | 56/64 as extreme; means [-3.833, +3.833] |
| cw5c_h_other_coins_care: L9 coins awarded to every other service (EF - EC) | p | 3401: -11; 3402: +28; 3403: -6; 3404: -3; 3405: -19; 3406: +18 | +1.167 [-19, +28] | 2 / 4 / 0 | 60/64 as extreme; means [-14.17, +14.17] |
| cw5c_h_relief_coins: L9 coins awarded to granary relief (EC - E0) | t | 3301: -8; 3302: -18; 3303: +4; 3304: -2; 3305: -3; 3306: -3 | -5 [-18, +4] | 1 / 5 / 0 | 10/64 as extreme; means [-6.333, +6.333] |
| cw5c_h_relief_coins: L9 coins awarded to granary relief (EC - E0) | p | 3401: +0; 3402: -13; 3403: -15; 3404: -10; 3405: -2; 3406: +31 | -1.5 [-15, +31] | 1 / 4 / 1 | 60/64 as extreme; means [-11.83, +11.83] |
| cw5c_h_treasury: Treasury at the end (EC - E0) | t | 3301: +218; 3302: -405; 3303: -925; 3304: -492; 3305: +1661; 3306: +302 | +59.83 [-925, +1661] | 3 / 3 / 0 | 56/64 as extreme; means [-667.2, +667.2] |
| cw5c_h_treasury: Treasury at the end (EC - E0) | p | 3401: -636; 3402: +8; 3403: -391; 3404: -154; 3405: -217; 3406: +1240 | -25 [-636, +1240] | 2 / 4 / 0 | 62/64 as extreme; means [-441, +441] |
| cw5c_h_treasury_care: Treasury at the end (EF - EC) | t | 3301: -317; 3302: +658; 3303: +957; 3304: +266; 3305: -540; 3306: -659 | +60.83 [-659, +957] | 3 / 3 / 0 | 54/64 as extreme; means [-566.2, +566.2] |
| cw5c_h_treasury_care: Treasury at the end (EF - EC) | p | 3401: +206; 3402: -3071; 3403: -1017; 3404: +2854; 3405: +2433; 3406: -1703 | -49.67 [-3071, +2854] | 3 / 3 / 0 | 60/64 as extreme; means [-1881, +1881] |
| cw5c_h_stability: Mean civ stability over civ-turns (EC - E0) | t | 3301: -1.502; 3302: +3.483; 3303: +0.5772; 3304: -4.3; 3305: -8.069; 3306: +5.147 | -0.7774 [-8.069, +5.147] | 3 / 3 / 0 | 44/64 as extreme; means [-3.846, +3.846] |
| cw5c_h_stability: Mean civ stability over civ-turns (EC - E0) | p | 3401: +3.852; 3402: -6.007; 3403: +0.4721; 3404: -2.458; 3405: +0.8673; 3406: -1.786 | -0.8434 [-6.007, +3.852] | 3 / 3 / 0 | 38/64 as extreme; means [-2.574, +2.574] |
| cw5c_h_stability_care: Mean civ stability over civ-turns (EF - EC) | t | 3301: -0.5138; 3302: -1.595; 3303: +3.695; 3304: +4.242; 3305: +5.244; 3306: -0.5849 | +1.748 [-1.595, +5.244] | 3 / 3 / 0 | 16/64 as extreme; means [-2.646, +2.646] |
| cw5c_h_stability_care: Mean civ stability over civ-turns (EF - EC) | p | 3401: -4.919; 3402: -2.198; 3403: -1.684; 3404: +1.467; 3405: +1.856; 3406: +1.825 | -0.6089 [-4.919, +1.856] | 3 / 3 / 0 | 40/64 as extreme; means [-2.325, +2.325] |
| cw5c_h_unrest: Mean city unrest over city-turns (EC - E0) | t | 3301: -0.02254; 3302: -0.04832; 3303: -0.01296; 3304: -0.01137; 3305: -0.02765; 3306: -0.0007955 | -0.0206 [-0.04832, -0.0007955] | 0 / 6 / 0 | 2/64 as extreme; means [-0.0206, +0.0206] |
| cw5c_h_unrest: Mean city unrest over city-turns (EC - E0) | p | 3401: -0.05336; 3402: -0.004067; 3403: +0.005131; 3404: -0.006335; 3405: -0.04187; 3406: -0.008272 | -0.01813 [-0.05336, +0.005131] | 1 / 5 / 0 | 6/64 as extreme; means [-0.01984, +0.01984] |
| cw5c_h_unrest_care: Mean city unrest over city-turns (EF - EC) | t | 3301: +0.008123; 3302: +0.03859; 3303: +0.001568; 3304: -0.002735; 3305: +0.01018; 3306: -0.05473 | +0.0001647 [-0.05473, +0.03859] | 4 / 2 / 0 | 64/64 as extreme; means [-0.01932, +0.01932] |
| cw5c_h_unrest_care: Mean city unrest over city-turns (EF - EC) | p | 3401: +0.04074; 3402: -0.002886; 3403: -0.01619; 3404: +0.0009073; 3405: +0.01989; 3406: +0.02896 | +0.0119 [-0.01619, +0.04074] | 4 / 2 / 0 | 14/64 as extreme; means [-0.01826, +0.01826] |
| cw5c_h_population: Population at the end (EF - EC) | t | 3301: +20; 3302: +58; 3303: +40; 3304: +5; 3305: +52; 3306: -21 | +25.67 [-21, +58] | 5 / 1 / 0 | 8/64 as extreme; means [-32.67, +32.67] |
| cw5c_h_population: Population at the end (EF - EC) | p | 3401: +51; 3402: -31; 3403: +28; 3404: -218; 3405: +114; 3406: +34 | -3.667 [-218, +114] | 4 / 2 / 0 | 62/64 as extreme; means [-79.33, +79.33] |
| cw5c_h_population_cost: Population at the end (EC - E0) | t | 3301: +21; 3302: -56; 3303: -13; 3304: +8; 3305: -41; 3306: +13 | -11.33 [-56, +21] | 3 / 3 / 0 | 30/64 as extreme; means [-25.33, +25.33] |
| cw5c_h_population_cost: Population at the end (EC - E0) | p | 3401: -121; 3402: -108; 3403: -152; 3404: +69; 3405: -37; 3406: +29 | -53.33 [-152, +69] | 2 / 4 / 0 | 12/64 as extreme; means [-86, +86] |
| cw5c_h_migration: Agents moving between regions over the run (EF - EC) | t | 3301: -250; 3302: +548; 3303: +17; 3304: -19; 3305: +372; 3306: +22 | +115 [-250, +548] | 4 / 2 / 0 | 22/64 as extreme; means [-204.7, +204.7] |
| cw5c_h_migration: Agents moving between regions over the run (EF - EC) | p | 3401: +192; 3402: +1390; 3403: -233; 3404: -2471; 3405: +1047; 3406: +1110 | +172.5 [-2471, +1390] | 4 / 2 / 0 | 56/64 as extreme; means [-1074, +1074] |
| cw5c_h_migration_cost: Agents moving between regions over the run (EC - E0) | t | 3301: +427; 3302: -68; 3303: +70; 3304: -50; 3305: -599; 3306: +128 | -15.33 [-599, +427] | 3 / 3 / 0 | 58/64 as extreme; means [-223.7, +223.7] |
| cw5c_h_migration_cost: Agents moving between regions over the run (EC - E0) | p | 3401: -1855; 3402: -1242; 3403: -479; 3404: +2814; 3405: -897; 3406: +303 | -226 [-1855, +2814] | 2 / 4 / 0 | 50/64 as extreme; means [-1265, +1265] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EC - E0 | Population at the end (sum over civilizations) | t | 3301: +21; 3302: -56; 3303: -13; 3304: +8; 3305: -41; 3306: +13 | -11.33 [-56, +21] | 3 / 3 / 0 | 30/64 as extreme; means [-25.33, +25.33] | recorded |
| EC - E0 | Population at the end (sum over civilizations) | p | 3401: -121; 3402: -108; 3403: -152; 3404: +69; 3405: -37; 3406: +29 | -53.33 [-152, +69] | 2 / 4 / 0 | 12/64 as extreme; means [-86, +86] | recorded |
| EC - E0 | Treasury at the end (sum over civilizations) | t | 3301: +218; 3302: -405; 3303: -925; 3304: -492; 3305: +1661; 3306: +302 | +59.83 [-925, +1661] | 3 / 3 / 0 | 56/64 as extreme; means [-667.2, +667.2] | recorded |
| EC - E0 | Treasury at the end (sum over civilizations) | p | 3401: -636; 3402: +8; 3403: -391; 3404: -154; 3405: -217; 3406: +1240 | -25 [-636, +1240] | 2 / 4 / 0 | 62/64 as extreme; means [-441, +441] | recorded |
| EC - E0 | Food shortfall after relief over the run (food) | t | 3301: +278.9; 3302: -404.2; 3303: -112.8; 3304: -266.6; 3305: -442.1; 3306: +357.3 | -98.25 [-442.1, +357.3] | 2 / 4 / 0 | 30/64 as extreme; means [-310.3, +310.3] | recorded |
| EC - E0 | Food shortfall after relief over the run (food) | p | 3401: -2423; 3402: +21.35; 3403: -241.3; 3404: +2431; 3405: +103; 3406: +1714 | +267.5 [-2423, +2431] | 4 / 2 / 0 | 50/64 as extreme; means [-1156, +1156] | recorded |
| EC - E0 | Priced-out person-turns | t | 3301: not recorded; 3302: not recorded; 3303: not recorded; 3304: not recorded; 3305: not recorded; 3306: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Priced-out person-turns | p | 3401: not recorded; 3402: not recorded; 3403: not recorded; 3404: not recorded; 3405: not recorded; 3406: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Priced-out child-turns | t | 3301: not recorded; 3302: not recorded; 3303: not recorded; 3304: not recorded; 3305: not recorded; 3306: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Priced-out child-turns | p | 3401: not recorded; 3402: not recorded; 3403: not recorded; 3404: not recorded; 3405: not recorded; 3406: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EC - E0 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EC - E0 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EC - E0 | Deaths by epidemic (the epidemic authority) | t | 3301: +12; 3302: +111; 3303: -18; 3304: -1; 3305: -19; 3306: -5 | +13.33 [-19, +111] | 2 / 4 / 0 | 56/64 as extreme; means [-27.67, +27.67] | recorded |
| EC - E0 | Deaths by epidemic (the epidemic authority) | p | 3401: +216; 3402: +223; 3403: +69; 3404: -2; 3405: -28; 3406: -176 | +50.33 [-176, +223] | 3 / 3 / 0 | 24/64 as extreme; means [-119, +119] | recorded |
| EC - E0 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EC - E0 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EC - E0 | Agents migrating between regions over the run | t | 3301: +427; 3302: -68; 3303: +70; 3304: -50; 3305: -599; 3306: +128 | -15.33 [-599, +427] | 3 / 3 / 0 | 58/64 as extreme; means [-223.7, +223.7] | recorded |
| EC - E0 | Agents migrating between regions over the run | p | 3401: -1855; 3402: -1242; 3403: -479; 3404: +2814; 3405: -897; 3406: +303 | -226 [-1855, +2814] | 2 / 4 / 0 | 50/64 as extreme; means [-1265, +1265] | recorded |
| EC - E0 | Mean wealth Gini of living civilizations at the end | t | 3301: +0.009795; 3302: +0.003317; 3303: -0.2811; 3304: -0.1978; 3305: -0.391; 3306: +0.01084 | -0.141 [-0.391, +0.01084] | 3 / 3 / 0 | 16/64 as extreme; means [-0.149, +0.149] | recorded |
| EC - E0 | Mean wealth Gini of living civilizations at the end | p | 3401: -0.04122; 3402: -0.05841; 3403: +0.00837; 3404: -0.01459; 3405: +0.1074; 3406: -0.0003606 | +0.0001902 [-0.05841, +0.1074] | 2 / 4 / 0 | 64/64 as extreme; means [-0.03838, +0.03838] | recorded |
| EC - E0 | Timber stand share of capacity at the end | t | 3301: not recorded; 3302: not recorded; 3303: not recorded; 3304: not recorded; 3305: not recorded; 3306: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EC - E0 | Timber stand share of capacity at the end | p | 3401: not recorded; 3402: not recorded; 3403: not recorded; 3404: not recorded; 3405: not recorded; 3406: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - EC | Population at the end (sum over civilizations) | t | 3301: +20; 3302: +58; 3303: +40; 3304: +5; 3305: +52; 3306: -21 | +25.67 [-21, +58] | 5 / 1 / 0 | 8/64 as extreme; means [-32.67, +32.67] | recorded |
| EF - EC | Population at the end (sum over civilizations) | p | 3401: +51; 3402: -31; 3403: +28; 3404: -218; 3405: +114; 3406: +34 | -3.667 [-218, +114] | 4 / 2 / 0 | 62/64 as extreme; means [-79.33, +79.33] | recorded |
| EF - EC | Treasury at the end (sum over civilizations) | t | 3301: -317; 3302: +658; 3303: +957; 3304: +266; 3305: -540; 3306: -659 | +60.83 [-659, +957] | 3 / 3 / 0 | 54/64 as extreme; means [-566.2, +566.2] | recorded |
| EF - EC | Treasury at the end (sum over civilizations) | p | 3401: +206; 3402: -3071; 3403: -1017; 3404: +2854; 3405: +2433; 3406: -1703 | -49.67 [-3071, +2854] | 3 / 3 / 0 | 60/64 as extreme; means [-1881, +1881] | recorded |
| EF - EC | Food shortfall after relief over the run (food) | t | 3301: +202.2; 3302: +990; 3303: +257.1; 3304: +460.6; 3305: +204.4; 3306: -348.8 | +294.3 [-348.8, +990] | 5 / 1 / 0 | 10/64 as extreme; means [-410.5, +410.5] | recorded |
| EF - EC | Food shortfall after relief over the run (food) | p | 3401: -1040; 3402: -936.5; 3403: +300; 3404: -1901; 3405: +1235; 3406: -447.3 | -465.1 [-1901, +1235] | 2 / 4 / 0 | 24/64 as extreme; means [-976.7, +976.7] | recorded |
| EF - EC | Priced-out person-turns | t | 3301: not recorded; 3302: not recorded; 3303: not recorded; 3304: not recorded; 3305: not recorded; 3306: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Priced-out person-turns | p | 3401: not recorded; 3402: not recorded; 3403: not recorded; 3404: not recorded; 3405: not recorded; 3406: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Priced-out child-turns | t | 3301: not recorded; 3302: not recorded; 3303: not recorded; 3304: not recorded; 3305: not recorded; 3306: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Priced-out child-turns | p | 3401: not recorded; 3402: not recorded; 3403: not recorded; 3404: not recorded; 3405: not recorded; 3406: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - EC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - EC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - EC | Deaths by epidemic (the epidemic authority) | t | 3301: -84; 3302: -100; 3303: -47; 3304: -5; 3305: -23; 3306: -11 | -45 [-100, -5] | 0 / 6 / 0 | 2/64 as extreme; means [-45, +45] | recorded |
| EF - EC | Deaths by epidemic (the epidemic authority) | p | 3401: +21; 3402: -11; 3403: -70; 3404: +199; 3405: -196; 3406: +80 | +3.833 [-196, +199] | 3 / 3 / 0 | 56/64 as extreme; means [-96.17, +96.17] | recorded |
| EF - EC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - EC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - EC | Agents migrating between regions over the run | t | 3301: -250; 3302: +548; 3303: +17; 3304: -19; 3305: +372; 3306: +22 | +115 [-250, +548] | 4 / 2 / 0 | 22/64 as extreme; means [-204.7, +204.7] | recorded |
| EF - EC | Agents migrating between regions over the run | p | 3401: +192; 3402: +1390; 3403: -233; 3404: -2471; 3405: +1047; 3406: +1110 | +172.5 [-2471, +1390] | 4 / 2 / 0 | 56/64 as extreme; means [-1074, +1074] | recorded |
| EF - EC | Mean wealth Gini of living civilizations at the end | t | 3301: -0.01243; 3302: +0.02565; 3303: +0.347; 3304: +0.1426; 3305: +0.3941; 3306: +0.01079 | +0.1513 [-0.01243, +0.3941] | 5 / 1 / 0 | 6/64 as extreme; means [-0.1554, +0.1554] | recorded |
| EF - EC | Mean wealth Gini of living civilizations at the end | p | 3401: +0.01628; 3402: -0.007845; 3403: +0.009633; 3404: +0.01862; 3405: +0.04965; 3406: -0.02507 | +0.01021 [-0.02507, +0.04965] | 4 / 2 / 0 | 24/64 as extreme; means [-0.02118, +0.02118] | recorded |
| EF - EC | Timber stand share of capacity at the end | t | 3301: not recorded; 3302: not recorded; 3303: not recorded; 3304: not recorded; 3305: not recorded; 3306: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - EC | Timber stand share of capacity at the end | p | 3401: not recorded; 3402: not recorded; 3403: not recorded; 3404: not recorded; 3405: not recorded; 3406: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - E0 | Population at the end (sum over civilizations) | t | 3301: +41; 3302: +2; 3303: +27; 3304: +13; 3305: +11; 3306: -8 | +14.33 [-8, +41] | 5 / 1 / 0 | 6/64 as extreme; means [-17, +17] | recorded |
| EF - E0 | Population at the end (sum over civilizations) | p | 3401: -70; 3402: -139; 3403: -124; 3404: -149; 3405: +77; 3406: +63 | -57 [-149, +77] | 2 / 4 / 0 | 16/64 as extreme; means [-103.7, +103.7] | recorded |
| EF - E0 | Treasury at the end (sum over civilizations) | t | 3301: -99; 3302: +253; 3303: +32; 3304: -226; 3305: +1121; 3306: -357 | +120.7 [-357, +1121] | 3 / 3 / 0 | 50/64 as extreme; means [-348, +348] | recorded |
| EF - E0 | Treasury at the end (sum over civilizations) | p | 3401: -430; 3402: -3063; 3403: -1408; 3404: +2700; 3405: +2216; 3406: -463 | -74.67 [-3063, +2700] | 2 / 4 / 0 | 60/64 as extreme; means [-1713, +1713] | recorded |
| EF - E0 | Food shortfall after relief over the run (food) | t | 3301: +481.2; 3302: +585.8; 3303: +144.3; 3304: +193.9; 3305: -237.7; 3306: +8.495 | +196 [-237.7, +585.8] | 5 / 1 / 0 | 14/64 as extreme; means [-275.2, +275.2] | recorded |
| EF - E0 | Food shortfall after relief over the run (food) | p | 3401: -3463; 3402: -915.1; 3403: +58.7; 3404: +529.7; 3405: +1338; 3406: +1267 | -197.6 [-3463, +1338] | 4 / 2 / 0 | 56/64 as extreme; means [-1262, +1262] | recorded |
| EF - E0 | Priced-out person-turns | t | 3301: not recorded; 3302: not recorded; 3303: not recorded; 3304: not recorded; 3305: not recorded; 3306: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Priced-out person-turns | p | 3401: not recorded; 3402: not recorded; 3403: not recorded; 3404: not recorded; 3405: not recorded; 3406: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Priced-out child-turns | t | 3301: not recorded; 3302: not recorded; 3303: not recorded; 3304: not recorded; 3305: not recorded; 3306: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Priced-out child-turns | p | 3401: not recorded; 3402: not recorded; 3403: not recorded; 3404: not recorded; 3405: not recorded; 3406: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| EF - E0 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - E0 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| EF - E0 | Deaths by epidemic (the epidemic authority) | t | 3301: -72; 3302: +11; 3303: -65; 3304: -6; 3305: -42; 3306: -16 | -31.67 [-72, +11] | 1 / 5 / 0 | 6/64 as extreme; means [-35.33, +35.33] | recorded |
| EF - E0 | Deaths by epidemic (the epidemic authority) | p | 3401: +237; 3402: +212; 3403: -1; 3404: +197; 3405: -224; 3406: -96 | +54.17 [-224, +237] | 3 / 3 / 0 | 36/64 as extreme; means [-161.2, +161.2] | recorded |
| EF - E0 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - E0 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| EF - E0 | Agents migrating between regions over the run | t | 3301: +177; 3302: +480; 3303: +87; 3304: -69; 3305: -227; 3306: +150 | +99.67 [-227, +480] | 4 / 2 / 0 | 24/64 as extreme; means [-198.3, +198.3] | recorded |
| EF - E0 | Agents migrating between regions over the run | p | 3401: -1663; 3402: +148; 3403: -712; 3404: +343; 3405: +150; 3406: +1413 | -53.5 [-1663, +1413] | 4 / 2 / 0 | 58/64 as extreme; means [-738.2, +738.2] | recorded |
| EF - E0 | Mean wealth Gini of living civilizations at the end | t | 3301: -0.002635; 3302: +0.02897; 3303: +0.06583; 3304: -0.05515; 3305: +0.00305; 3306: +0.02163 | +0.01028 [-0.05515, +0.06583] | 4 / 2 / 0 | 36/64 as extreme; means [-0.02954, +0.02954] | recorded |
| EF - E0 | Mean wealth Gini of living civilizations at the end | p | 3401: -0.02494; 3402: -0.06625; 3403: +0.018; 3404: +0.004023; 3405: +0.157; 3406: -0.02543 | +0.0104 [-0.06625, +0.157] | 3 / 3 / 0 | 58/64 as extreme; means [-0.04928, +0.04928] | recorded |
| EF - E0 | Timber stand share of capacity at the end | t | 3301: not recorded; 3302: not recorded; 3303: not recorded; 3304: not recorded; 3305: not recorded; 3306: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| EF - E0 | Timber stand share of capacity at the end | p | 3401: not recorded; 3402: not recorded; 3403: not recorded; 3404: not recorded; 3405: not recorded; 3406: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| E0 | 10.2 [9.0, 10.8] | 18.8 [15.1, 21.9] |
| EC | 10.8 [8.2, 13.9] | 19.9 [16.6, 23.1] |
| EF | 10.8 [7.3, 13.8] | 20.4 [17.5, 24.7] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
