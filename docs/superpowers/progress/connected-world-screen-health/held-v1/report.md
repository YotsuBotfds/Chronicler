# CW-health: Connected public health: material care, water management and dated advice

Cohort held. Runs: 36; failed: 0 (missing outcomes: 0); simulation and extraction seconds 820 (0.228 core-hours)

Identity digests: 25946961828ca27e20127e182af1ffd4b6375adef19aa3a47a343482518eaa3c (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"epidemic_care": [1], "food_allocation": [1], "household_retail": [1], "infrastructure_condition": [1], "local_budgets": [1], "public_health": [1], "repair_projects": [1], "residence_ledger": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| PS | t | 3901: activated; 3902: activated; 3903: activated; 3904: activated; 3905: activated; 3906: activated | 6 of 6 |
| PS | p | 4001: activated; 4002: activated; 4003: activated; 4004: activated; 4005: activated; 4006: activated | 6 of 6 |
| PA | t | 3901: activated; 3902: activated; 3903: activated; 3904: activated; 3905: activated; 3906: activated | 6 of 6 |
| PA | p | 4001: activated; 4002: activated; 4003: activated; 4004: activated; 4005: activated; 4006: activated | 6 of 6 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| health_world_death_rate: World epidemic deaths per 1,000 end-turn person-turns (PA - PC) | t | 3901: -1.66; 3902: +0.4938; 3903: -0.5611; 3904: +1.15; 3905: +0; 3906: -1.172 | -0.2914 [-1.66, +1.15] | 2 / 3 / 1 | 28/64 as extreme; means [-0.8395, +0.8395] |
| health_world_death_rate: World epidemic deaths per 1,000 end-turn person-turns (PA - PC) | p | 4001: -2.126; 4002: -0.1385; 4003: +2.158; 4004: +0.5195; 4005: +0.08477; 4006: -1.836 | -0.2229 [-2.126, +2.158] | 3 / 3 / 0 | 56/64 as extreme; means [-1.144, +1.144] |
| health_world_dpi: World epidemic deaths per infectious person-turn (PA - PC) | t | 3901: -0.03739; 3902: -0.000543; 3903: +0.009435; 3904: -0.04915; 3905: +0; 3906: +0.02226 | -0.009231 [-0.04915, +0.02226] | 2 / 3 / 1 | 28/64 as extreme; means [-0.0198, +0.0198] |
| health_world_dpi: World epidemic deaths per infectious person-turn (PA - PC) | p | 4001: -0.05264; 4002: -0.01895; 4003: +0.03863; 4004: -0.00296; 4005: -0.003319; 4006: -0.01781 | -0.009507 [-0.05264, +0.03863] | 1 / 5 / 0 | 28/64 as extreme; means [-0.02238, +0.02238] |
| health_world_arrivals: World cross-polity epidemic arrivals (PA - PS) | t | 3901: -7; 3902: +0; 3903: -18; 3904: -5; 3905: +1; 3906: -13 | -7 [-18, +1] | 1 / 4 / 1 | 8/64 as extreme; means [-7.333, +7.333] |
| health_world_arrivals: World cross-polity epidemic arrivals (PA - PS) | p | 4001: +13; 4002: +102; 4003: -5; 4004: +55; 4005: +5; 4006: -45 | +20.83 [-45, +102] | 4 / 2 / 0 | 22/64 as extreme; means [-37.5, +37.5] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| health_h_food_consumed_milli: Actual patient grain consumed (milli-loads) (PA - PC) | t | 3901: +1.252e+04; 3902: -3.661e+04; 3903: -3.036e+04; 3904: +2.97e+04; 3905: +0; 3906: +0 | -4124 [-3.661e+04, +2.97e+04] | 2 / 2 / 2 | 48/64 as extreme; means [-1.82e+04, +1.82e+04] |
| health_h_food_consumed_milli: Actual patient grain consumed (milli-loads) (PA - PC) | p | 4001: +8.498e+04; 4002: +6.588e+04; 4003: +3.787e+04; 4004: -6940; 4005: -3212; 4006: +2.799e+04 | +3.443e+04 [-6940, +8.498e+04] | 4 / 2 / 0 | 8/64 as extreme; means [-3.781e+04, +3.781e+04] |
| health_h_supplies_cash_milli: Patient supply cash paid (milli-units) (PA - PC) | t | 3901: +1000; 3902: +0; 3903: +1.2e+04; 3904: +9000; 3905: +0; 3906: +0 | +3667 [+0, +1.2e+04] | 3 / 0 / 3 | 16/64 as extreme; means [-3667, +3667] |
| health_h_supplies_cash_milli: Patient supply cash paid (milli-units) (PA - PC) | p | 4001: +1.36e+05; 4002: +3.2e+04; 4003: +2.8e+04; 4004: -2e+04; 4005: -6000; 4006: +3.3e+04 | +3.383e+04 [-2e+04, +1.36e+05] | 4 / 2 / 0 | 8/64 as extreme; means [-4.25e+04, +4.25e+04] |
| health_h_supplies_internal_milli: Local patient grain allocated at dated prices (milli-units) (PA - PC) | t | 3901: -6000; 3902: -2.4e+04; 3903: -1.9e+04; 3904: +7.7e+04; 3905: +0; 3906: +0 | +4667 [-2.4e+04, +7.7e+04] | 1 / 3 / 2 | 64/64 as extreme; means [-2.1e+04, +2.1e+04] |
| health_h_supplies_internal_milli: Local patient grain allocated at dated prices (milli-units) (PA - PC) | p | 4001: +1.6e+04; 4002: +3.1e+04; 4003: +3000; 4004: -6000; 4005: +6000; 4006: -1.8e+04 | +5333 [-1.8e+04, +3.1e+04] | 4 / 2 / 0 | 32/64 as extreme; means [-1.333e+04, +1.333e+04] |
| health_h_care_paid_milli: Care wages paid (milli-units) (PA - PC) | t | 3901: +1.206e+04; 3902: -8182; 3903: -3.369e+04; 3904: +2.539e+04; 3905: +0; 3906: -1.536e+04 | -3296 [-3.369e+04, +2.539e+04] | 2 / 3 / 1 | 48/64 as extreme; means [-1.578e+04, +1.578e+04] |
| health_h_care_paid_milli: Care wages paid (milli-units) (PA - PC) | p | 4001: -1.36e+04; 4002: +1.001e+05; 4003: -2.562e+04; 4004: +8.22e+04; 4005: +8450; 4006: -7.036e+04 | +1.354e+04 [-7.036e+04, +1.001e+05] | 3 / 3 / 0 | 44/64 as extreme; means [-5.006e+04, +5.006e+04] |
| health_h_care_income_withheld: Observed ordinary carer income withheld subtotal (PA - PC) | t | 3901: -0.7844; 3902: -1.073; 3903: -5.338; 3904: +6.612; 3905: +0; 3906: -4.891 | -0.9125 [-5.338, +6.612] | 1 / 4 / 1 | 44/64 as extreme; means [-3.117, +3.117] |
| health_h_care_income_withheld: Observed ordinary carer income withheld subtotal (PA - PC) | p | 4001: -0.7604; 4002: +19.18; 4003: -6.268; 4004: +27.36; 4005: +2.223; 4006: -28.07 | +2.277 [-28.07, +27.36] | 3 / 3 / 0 | 56/64 as extreme; means [-13.98, +13.98] |
| health_h_care_income_unknown_person_turns: Paid carer person-turns without an income deduction observation (PA - PC) | t | 3901: -1; 3902: +4; 3903: -4; 3904: +1; 3905: +0; 3906: -4 | -0.6667 [-4, +4] | 2 / 3 / 1 | 52/64 as extreme; means [-2.333, +2.333] |
| health_h_care_income_unknown_person_turns: Paid carer person-turns without an income deduction observation (PA - PC) | p | 4001: -8; 4002: -1; 4003: +5; 4004: +24; 4005: -2; 4006: -13 | +0.8333 [-13, +24] | 2 / 4 / 0 | 58/64 as extreme; means [-8.833, +8.833] |
| health_h_guard_paid_milli: Guard wages paid (milli-units) (PA - PC) | t | 3901: -4.9e+04; 3902: -1650; 3903: -2e+04; 3904: -3500; 3905: +0; 3906: -1.85e+04 | -1.544e+04 [-4.9e+04, +0] | 0 / 5 / 1 | 4/64 as extreme; means [-1.544e+04, +1.544e+04] |
| health_h_guard_paid_milli: Guard wages paid (milli-units) (PA - PC) | p | 4001: -1.698e+05; 4002: +2.851e+05; 4003: -2.91e+04; 4004: +4.855e+04; 4005: -3500; 4006: -1.515e+05 | -3375 [-1.698e+05, +2.851e+05] | 2 / 4 / 0 | 62/64 as extreme; means [-1.146e+05, +1.146e+05] |
| health_h_guard_income_withheld: Observed ordinary guard income withheld subtotal (PA - PC) | t | 3901: -26.99; 3902: -0.1632; 3903: -3.868; 3904: +0.9429; 3905: +0; 3906: -4.748 | -5.804 [-26.99, +0.9429] | 1 / 4 / 1 | 12/64 as extreme; means [-6.119, +6.119] |
| health_h_guard_income_withheld: Observed ordinary guard income withheld subtotal (PA - PC) | p | 4001: -80.6; 4002: +67.09; 4003: +21.67; 4004: +34.96; 4005: +1.671; 4006: -69.83 | -4.174 [-80.6, +67.09] | 4 / 2 / 0 | 56/64 as extreme; means [-45.97, +45.97] |
| health_h_guard_income_unknown_person_turns: Paid guard person-turns without an income deduction observation (PA - PC) | t | 3901: -2; 3902: +1; 3903: +0; 3904: +0; 3905: +0; 3906: -1 | -0.3333 [-2, +1] | 1 / 2 / 3 | 48/64 as extreme; means [-0.6667, +0.6667] |
| health_h_guard_income_unknown_person_turns: Paid guard person-turns without an income deduction observation (PA - PC) | p | 4001: -7; 4002: +6; 4003: -4; 4004: +8; 4005: +1; 4006: -4 | +0 [-7, +8] | 3 / 3 / 0 | 64/64 as extreme; means [-5, +5] |
| health_h_care_farm_time: Carer farm time removed (PA - PC) | t | 3901: +24.15; 3902: -16.38; 3903: -67.39; 3904: +50.78; 3905: +0; 3906: -30.87 | -6.619 [-67.39, +50.78] | 2 / 3 / 1 | 48/64 as extreme; means [-31.59, +31.59] |
| health_h_care_farm_time: Carer farm time removed (PA - PC) | p | 4001: -27.16; 4002: +200.3; 4003: -51.28; 4004: +164.4; 4005: +16.92; 4006: -140.7 | +27.08 [-140.7, +200.3] | 3 / 3 / 0 | 44/64 as extreme; means [-100.1, +100.1] |
| health_h_guard_farm_time: Guard farm time removed (PA - PC) | t | 3901: -98; 3902: -3.3; 3903: -40; 3904: -7; 3905: +0; 3906: -37 | -30.88 [-98, +0] | 0 / 5 / 1 | 4/64 as extreme; means [-30.88, +30.88] |
| health_h_guard_farm_time: Guard farm time removed (PA - PC) | p | 4001: -339.6; 4002: +570.2; 4003: -58.2; 4004: +97.8; 4005: -7; 4006: -303 | -6.634 [-339.6, +570.2] | 2 / 4 / 0 | 62/64 as extreme; means [-229.3, +229.3] |
| health_h_l9_envelope_milli: Gross single care/public-health envelopes (milli-units) (PA - PC) | t | 3901: +4.77e+05; 3902: -1.77e+05; 3903: -4.99e+05; 3904: +5.49e+05; 3905: +0; 3906: -3.63e+05 | -2167 [-4.99e+05, +5.49e+05] | 2 / 3 / 1 | 64/64 as extreme; means [-3.442e+05, +3.442e+05] |
| health_h_l9_envelope_milli: Gross single care/public-health envelopes (milli-units) (PA - PC) | p | 4001: -3.61e+05; 4002: +2.501e+06; 4003: -1.007e+06; 4004: +1.469e+06; 4005: -5.6e+04; 4006: -1.968e+06 | +9.633e+04 [-1.968e+06, +2.501e+06] | 2 / 4 / 0 | 56/64 as extreme; means [-1.227e+06, +1.227e+06] |
| health_h_health_cash_milli: Actual whole-coin health cash funding (milli-units) (PA - PC) | t | 3901: -3.8e+04; 3902: -1e+04; 3903: -4.2e+04; 3904: +3.2e+04; 3905: +0; 3906: -3.4e+04 | -1.533e+04 [-4.2e+04, +3.2e+04] | 1 / 4 / 1 | 12/64 as extreme; means [-2.6e+04, +2.6e+04] |
| health_h_health_cash_milli: Actual whole-coin health cash funding (milli-units) (PA - PC) | p | 4001: -4.7e+04; 4002: +4.2e+05; 4003: -2.3e+04; 4004: +1.09e+05; 4005: -1000; 4006: -1.9e+05 | +4.467e+04 [-1.9e+05, +4.2e+05] | 2 / 4 / 0 | 48/64 as extreme; means [-1.317e+05, +1.317e+05] |
| health_h_care_carry_change_milli: Change in prepaid care wage carry (milli-units) (PA - PC) | t | 3901: -1065; 3902: +182; 3903: -1307; 3904: +608; 3905: +0; 3906: +360 | -203.7 [-1307, +608] | 3 / 2 / 1 | 36/64 as extreme; means [-587, +587] |
| health_h_care_carry_change_milli: Change in prepaid care wage carry (milli-units) (PA - PC) | p | 4001: +596; 4002: +867; 4003: +1615; 4004: -1203; 4005: +550; 4006: +355 | +463.3 [-1203, +1615] | 5 / 1 / 0 | 18/64 as extreme; means [-864.3, +864.3] |
| health_h_guard_carry_change_milli: Change in prepaid guard wage carry (milli-units) (PA - PC) | t | 3901: -1000; 3902: -350; 3903: +1000; 3904: +500; 3905: +0; 3906: -500 | -58.33 [-1000, +1000] | 2 / 3 / 1 | 64/64 as extreme; means [-558.3, +558.3] |
| health_h_guard_carry_change_milli: Change in prepaid guard wage carry (milli-units) (PA - PC) | p | 4001: -198; 4002: +1900; 4003: +2100; 4004: -550; 4005: -500; 4006: -1500 | +208.7 [-1500, +2100] | 2 / 4 / 0 | 52/64 as extreme; means [-1125, +1125] |
| health_h_famine_region_turns: Region-turns below 0.6 food sufficiency (PA - PC) | t | 3901: +77; 3902: +1; 3903: -14; 3904: -34; 3905: +0; 3906: +38 | +11.33 [-34, +77] | 3 / 2 / 1 | 36/64 as extreme; means [-27.33, +27.33] |
| health_h_famine_region_turns: Region-turns below 0.6 food sufficiency (PA - PC) | p | 4001: -190; 4002: -120; 4003: +15; 4004: -45; 4005: +27; 4006: +13 | -50 [-190, +27] | 3 / 3 / 0 | 18/64 as extreme; means [-68.33, +68.33] |
| health_h_migrants_blocked: Refused civilian migration person-turns (PA - PC) | t | 3901: +4; 3902: +88; 3903: -158; 3904: +66; 3905: +0; 3906: -71 | -11.83 [-158, +88] | 3 / 2 / 1 | 52/64 as extreme; means [-64.5, +64.5] |
| health_h_migrants_blocked: Refused civilian migration person-turns (PA - PC) | p | 4001: +265; 4002: +308; 4003: +44; 4004: -48; 4005: -51; 4006: -450 | +11.33 [-450, +308] | 3 / 3 / 0 | 62/64 as extreme; means [-194.3, +194.3] |
| health_h_flight_blocked: Refused flight person-turns (PA - PC) | t | 3901: -13; 3902: +56; 3903: -90; 3904: +33; 3905: +0; 3906: -56 | -11.67 [-90, +56] | 2 / 3 / 1 | 40/64 as extreme; means [-41.33, +41.33] |
| health_h_flight_blocked: Refused flight person-turns (PA - PC) | p | 4001: +164; 4002: +213; 4003: +48; 4004: +10; 4005: -45; 4006: -302 | +14.67 [-302, +213] | 4 / 2 / 0 | 54/64 as extreme; means [-130.3, +130.3] |
| health_h_hunger_blocked: Refused hunger moves (PA - PC) | t | 3901: +39; 3902: +24; 3903: -62; 3904: +36; 3905: +0; 3906: -42 | -0.8333 [-62, +39] | 3 / 2 / 1 | 60/64 as extreme; means [-33.83, +33.83] |
| health_h_hunger_blocked: Refused hunger moves (PA - PC) | p | 4001: +38; 4002: +85; 4003: -14; 4004: -12; 4005: +0; 4006: -43 | +9 [-43, +85] | 2 / 3 / 1 | 48/64 as extreme; means [-32, +32] |
| health_h_route_turns_removed: Removed partner route-turns (PA - PC) | t | 3901: -1; 3902: +0; 3903: -7; 3904: -1; 3905: +0; 3906: +4 | -0.8333 [-7, +4] | 1 / 3 / 2 | 40/64 as extreme; means [-2.167, +2.167] |
| health_h_route_turns_removed: Removed partner route-turns (PA - PC) | p | 4001: +23; 4002: +94; 4003: +40; 4004: +71; 4005: -12; 4006: -131 | +14.17 [-131, +94] | 4 / 2 / 0 | 44/64 as extreme; means [-61.83, +61.83] |
| health_h_forgone_income: Forgone partner route income (PA - PC) | t | 3901: -4; 3902: +0; 3903: -28; 3904: -4; 3905: +0; 3906: +16 | -3.333 [-28, +16] | 1 / 3 / 2 | 40/64 as extreme; means [-8.667, +8.667] |
| health_h_forgone_income: Forgone partner route income (PA - PC) | p | 4001: +108; 4002: +360; 4003: +172; 4004: +280; 4005: -40; 4006: -524 | +59.33 [-524, +360] | 4 / 2 / 0 | 44/64 as extreme; means [-247.3, +247.3] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PS - PC | Population at the end (sum over civilizations) | t | 3901: +71; 3902: -4; 3903: -25; 3904: -18; 3905: +15; 3906: -7 | +5.333 [-25, +71] | 2 / 4 / 0 | 56/64 as extreme; means [-23.33, +23.33] | recorded |
| PS - PC | Population at the end (sum over civilizations) | p | 4001: +59; 4002: +19; 4003: -21; 4004: -25; 4005: -96; 4006: +157 | +15.5 [-96, +157] | 3 / 3 / 0 | 46/64 as extreme; means [-62.83, +62.83] | recorded |
| PS - PC | Treasury at the end (sum over civilizations) | t | 3901: +79; 3902: -10; 3903: -284; 3904: +759; 3905: -478; 3906: +44 | +18.33 [-478, +759] | 3 / 3 / 0 | 56/64 as extreme; means [-275.7, +275.7] | recorded |
| PS - PC | Treasury at the end (sum over civilizations) | p | 4001: +530; 4002: -2544; 4003: +170; 4004: -1090; 4005: +1545; 4006: -513 | -317 [-2544, +1545] | 3 / 3 / 0 | 42/64 as extreme; means [-1065, +1065] | recorded |
| PS - PC | Food shortfall after relief over the run (food) | t | 3901: +737.2; 3902: -222.3; 3903: -819.1; 3904: -10.07; 3905: +96.81; 3906: +72.35 | -24.17 [-819.1, +737.2] | 3 / 3 / 0 | 54/64 as extreme; means [-326.3, +326.3] | recorded |
| PS - PC | Food shortfall after relief over the run (food) | p | 4001: +478.6; 4002: +781.6; 4003: +45.49; 4004: -485.3; 4005: -9.088; 4006: +797.1 | +268.1 [-485.3, +797.1] | 4 / 2 / 0 | 16/64 as extreme; means [-432.9, +432.9] | recorded |
| PS - PC | Priced-out person-turns | t | 3901: +30; 3902: -43; 3903: +27; 3904: -19; 3905: -34; 3906: +80 | +6.833 [-43, +80] | 3 / 3 / 0 | 48/64 as extreme; means [-38.83, +38.83] | recorded |
| PS - PC | Priced-out person-turns | p | 4001: -45; 4002: -5; 4003: -5; 4004: -81; 4005: -39; 4006: +13 | -27 [-81, +13] | 1 / 5 / 0 | 10/64 as extreme; means [-31.33, +31.33] | recorded |
| PS - PC | Priced-out child-turns | t | 3901: -10; 3902: -1; 3903: +6; 3904: -1; 3905: -4; 3906: -7 | -2.833 [-10, +6] | 1 / 5 / 0 | 18/64 as extreme; means [-4.833, +4.833] | recorded |
| PS - PC | Priced-out child-turns | p | 4001: -9; 4002: -4; 4003: +1; 4004: +0; 4005: -8; 4006: +2 | -3 [-9, +2] | 2 / 3 / 1 | 16/64 as extreme; means [-4, +4] | recorded |
| PS - PC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PS - PC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PS - PC | Deaths by epidemic (the epidemic authority) | t | 3901: -53; 3902: -13; 3903: -41; 3904: +27; 3905: +11; 3906: -27 | -16 [-53, +27] | 2 / 4 / 0 | 16/64 as extreme; means [-28.67, +28.67] | recorded |
| PS - PC | Deaths by epidemic (the epidemic authority) | p | 4001: -75; 4002: +7; 4003: +52; 4004: -39; 4005: -55; 4006: -205 | -52.5 [-205, +52] | 2 / 4 / 0 | 14/64 as extreme; means [-72.17, +72.17] | recorded |
| PS - PC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PS - PC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PS - PC | Agents migrating between regions over the run | t | 3901: +102; 3902: -120; 3903: -43; 3904: +556; 3905: -88; 3906: +22 | +71.5 [-120, +556] | 3 / 3 / 0 | 48/64 as extreme; means [-155.2, +155.2] | recorded |
| PS - PC | Agents migrating between regions over the run | p | 4001: +63; 4002: -368; 4003: +22; 4004: -551; 4005: +665; 4006: +603 | +72.33 [-551, +665] | 4 / 2 / 0 | 42/64 as extreme; means [-378.7, +378.7] | recorded |
| PS - PC | Mean wealth Gini of living civilizations at the end | t | 3901: -0.05499; 3902: -0.04412; 3903: +0.04076; 3904: -0.1715; 3905: +0.05648; 3906: -0.2209 | -0.06571 [-0.2209, +0.05648] | 2 / 4 / 0 | 16/64 as extreme; means [-0.09813, +0.09813] | recorded |
| PS - PC | Mean wealth Gini of living civilizations at the end | p | 4001: -0.06585; 4002: +0.1494; 4003: -0.08536; 4004: -0.07936; 4005: -0.2318; 4006: -0.1457 | -0.07645 [-0.2318, +0.1494] | 1 / 5 / 0 | 14/64 as extreme; means [-0.1263, +0.1263] | recorded |
| PS - PC | Timber stand share of capacity at the end | t | 3901: not recorded; 3902: not recorded; 3903: not recorded; 3904: not recorded; 3905: not recorded; 3906: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PS - PC | Timber stand share of capacity at the end | p | 4001: not recorded; 4002: not recorded; 4003: not recorded; 4004: not recorded; 4005: not recorded; 4006: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PA - PS | Population at the end (sum over civilizations) | t | 3901: -26; 3902: +20; 3903: -1; 3904: +21; 3905: -15; 3906: -3 | -0.6667 [-26, +21] | 2 / 4 / 0 | 60/64 as extreme; means [-14.33, +14.33] | recorded |
| PA - PS | Population at the end (sum over civilizations) | p | 4001: +142; 4002: +45; 4003: -59; 4004: -29; 4005: +56; 4006: +1 | +26 [-59, +142] | 4 / 2 / 0 | 30/64 as extreme; means [-55.33, +55.33] | recorded |
| PA - PS | Treasury at the end (sum over civilizations) | t | 3901: -253; 3902: +103; 3903: +51; 3904: -346; 3905: +478; 3906: -352 | -53.17 [-352, +478] | 3 / 3 / 0 | 44/64 as extreme; means [-263.8, +263.8] | recorded |
| PA - PS | Treasury at the end (sum over civilizations) | p | 4001: -1744; 4002: +3434; 4003: +3006; 4004: +2521; 4005: -731; 4006: +1442 | +1321 [-1744, +3434] | 4 / 2 / 0 | 12/64 as extreme; means [-2146, +2146] | recorded |
| PA - PS | Food shortfall after relief over the run (food) | t | 3901: +410.4; 3902: +53.38; 3903: +541.6; 3904: +580.9; 3905: -96.81; 3906: +138.5 | +271.3 [-96.81, +580.9] | 5 / 1 / 0 | 6/64 as extreme; means [-303.6, +303.6] | recorded |
| PA - PS | Food shortfall after relief over the run (food) | p | 4001: +23.07; 4002: +894.7; 4003: -700.6; 4004: +527.5; 4005: +92.48; 4006: -1395 | -93.04 [-1395, +894.7] | 4 / 2 / 0 | 56/64 as extreme; means [-605.6, +605.6] | recorded |
| PA - PS | Priced-out person-turns | t | 3901: -54; 3902: -2; 3903: +65; 3904: +19; 3905: +34; 3906: -87 | -4.167 [-87, +65] | 3 / 3 / 0 | 54/64 as extreme; means [-43.5, +43.5] | recorded |
| PA - PS | Priced-out person-turns | p | 4001: +11; 4002: +29; 4003: -2; 4004: +11; 4005: +32; 4006: -40 | +6.833 [-40, +32] | 4 / 2 / 0 | 36/64 as extreme; means [-20.83, +20.83] | recorded |
| PA - PS | Priced-out child-turns | t | 3901: -3; 3902: -1; 3903: +1; 3904: +1; 3905: +4; 3906: +0 | +0.3333 [-3, +4] | 3 / 2 / 1 | 52/64 as extreme; means [-1.667, +1.667] | recorded |
| PA - PS | Priced-out child-turns | p | 4001: +6; 4002: +7; 4003: -3; 4004: +0; 4005: +8; 4006: -8 | +1.667 [-8, +8] | 3 / 2 / 1 | 40/64 as extreme; means [-5.333, +5.333] | recorded |
| PA - PS | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PA - PS | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PA - PS | Deaths by epidemic (the epidemic authority) | t | 3901: +23; 3902: +19; 3903: +2; 3904: +19; 3905: -11; 3906: -10 | +7 [-11, +23] | 4 / 2 / 0 | 22/64 as extreme; means [-14, +14] | recorded |
| PA - PS | Deaths by epidemic (the epidemic authority) | p | 4001: -46; 4002: +108; 4003: +30; 4004: +111; 4005: +62; 4006: +67 | +55.33 [-46, +111] | 5 / 1 / 0 | 6/64 as extreme; means [-70.67, +70.67] | recorded |
| PA - PS | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PA - PS | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PA - PS | Agents migrating between regions over the run | t | 3901: +208; 3902: +78; 3903: +39; 3904: -96; 3905: +88; 3906: +35 | +58.67 [-96, +208] | 5 / 1 / 0 | 14/64 as extreme; means [-90.67, +90.67] | recorded |
| PA - PS | Agents migrating between regions over the run | p | 4001: +197; 4002: +237; 4003: -664; 4004: +673; 4005: -565; 4006: -604 | -121 [-664, +673] | 3 / 3 / 0 | 40/64 as extreme; means [-490, +490] | recorded |
| PA - PS | Mean wealth Gini of living civilizations at the end | t | 3901: +0.0002933; 3902: +0.09194; 3903: -0.04445; 3904: +0.02233; 3905: -0.05648; 3906: +0.1239 | +0.02293 [-0.05648, +0.1239] | 4 / 2 / 0 | 30/64 as extreme; means [-0.05657, +0.05657] | recorded |
| PA - PS | Mean wealth Gini of living civilizations at the end | p | 4001: -0.1143; 4002: -0.004158; 4003: -0.2413; 4004: +0.05129; 4005: +0.1972; 4006: +0.05016 | -0.01018 [-0.2413, +0.1972] | 3 / 3 / 0 | 58/64 as extreme; means [-0.1097, +0.1097] | recorded |
| PA - PS | Timber stand share of capacity at the end | t | 3901: not recorded; 3902: not recorded; 3903: not recorded; 3904: not recorded; 3905: not recorded; 3906: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PA - PS | Timber stand share of capacity at the end | p | 4001: not recorded; 4002: not recorded; 4003: not recorded; 4004: not recorded; 4005: not recorded; 4006: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PA - PC | Population at the end (sum over civilizations) | t | 3901: +45; 3902: +16; 3903: -26; 3904: +3; 3905: +0; 3906: -10 | +4.667 [-26, +45] | 3 / 2 / 1 | 44/64 as extreme; means [-16.67, +16.67] | recorded |
| PA - PC | Population at the end (sum over civilizations) | p | 4001: +201; 4002: +64; 4003: -80; 4004: -54; 4005: -40; 4006: +158 | +41.5 [-80, +201] | 3 / 3 / 0 | 28/64 as extreme; means [-99.5, +99.5] | recorded |
| PA - PC | Treasury at the end (sum over civilizations) | t | 3901: -174; 3902: +93; 3903: -233; 3904: +413; 3905: +0; 3906: -308 | -34.83 [-308, +413] | 2 / 3 / 1 | 52/64 as extreme; means [-203.5, +203.5] | recorded |
| PA - PC | Treasury at the end (sum over civilizations) | p | 4001: -1214; 4002: +890; 4003: +3176; 4004: +1431; 4005: +814; 4006: +929 | +1004 [-1214, +3176] | 5 / 1 / 0 | 10/64 as extreme; means [-1409, +1409] | recorded |
| PA - PC | Food shortfall after relief over the run (food) | t | 3901: +1148; 3902: -168.9; 3903: -277.5; 3904: +570.9; 3905: +0; 3906: +210.9 | +247.2 [-277.5, +1148] | 3 / 2 / 1 | 24/64 as extreme; means [-396, +396] | recorded |
| PA - PC | Food shortfall after relief over the run (food) | p | 4001: +501.7; 4002: +1676; 4003: -655.1; 4004: +42.25; 4005: +83.39; 4006: -598.3 | +175 [-655.1, +1676] | 4 / 2 / 0 | 48/64 as extreme; means [-592.9, +592.9] | recorded |
| PA - PC | Priced-out person-turns | t | 3901: -24; 3902: -45; 3903: +92; 3904: +0; 3905: +0; 3906: -7 | +2.667 [-45, +92] | 1 / 3 / 2 | 64/64 as extreme; means [-28, +28] | recorded |
| PA - PC | Priced-out person-turns | p | 4001: -34; 4002: +24; 4003: -7; 4004: -70; 4005: -7; 4006: -27 | -20.17 [-70, +24] | 1 / 5 / 0 | 10/64 as extreme; means [-28.17, +28.17] | recorded |
| PA - PC | Priced-out child-turns | t | 3901: -13; 3902: -2; 3903: +7; 3904: +0; 3905: +0; 3906: -7 | -2.5 [-13, +7] | 1 / 3 / 2 | 32/64 as extreme; means [-4.833, +4.833] | recorded |
| PA - PC | Priced-out child-turns | p | 4001: -3; 4002: +3; 4003: -2; 4004: +0; 4005: +0; 4006: -6 | -1.333 [-6, +3] | 1 / 3 / 2 | 32/64 as extreme; means [-2.333, +2.333] | recorded |
| PA - PC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PA - PC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PA - PC | Deaths by epidemic (the epidemic authority) | t | 3901: -30; 3902: +6; 3903: -39; 3904: +46; 3905: +0; 3906: -37 | -9 [-39, +46] | 2 / 3 / 1 | 40/64 as extreme; means [-26.33, +26.33] | recorded |
| PA - PC | Deaths by epidemic (the epidemic authority) | p | 4001: -121; 4002: +115; 4003: +82; 4004: +72; 4005: +7; 4006: -138 | +2.833 [-138, +115] | 4 / 2 / 0 | 60/64 as extreme; means [-89.17, +89.17] | recorded |
| PA - PC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PA - PC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PA - PC | Agents migrating between regions over the run | t | 3901: +310; 3902: -42; 3903: -4; 3904: +460; 3905: +0; 3906: +57 | +130.2 [-42, +460] | 3 / 2 / 1 | 16/64 as extreme; means [-145.5, +145.5] | recorded |
| PA - PC | Agents migrating between regions over the run | p | 4001: +260; 4002: -131; 4003: -642; 4004: +122; 4005: +100; 4006: -1 | -48.67 [-642, +260] | 3 / 3 / 0 | 50/64 as extreme; means [-209.3, +209.3] | recorded |
| PA - PC | Mean wealth Gini of living civilizations at the end | t | 3901: -0.0547; 3902: +0.04782; 3903: -0.003685; 3904: -0.1492; 3905: +0; 3906: -0.09695 | -0.04279 [-0.1492, +0.04782] | 1 / 4 / 1 | 12/64 as extreme; means [-0.05873, +0.05873] | recorded |
| PA - PC | Mean wealth Gini of living civilizations at the end | p | 4001: -0.1802; 4002: +0.1453; 4003: -0.3266; 4004: -0.02807; 4005: -0.03466; 4006: -0.09553 | -0.08663 [-0.3266, +0.1453] | 1 / 5 / 0 | 16/64 as extreme; means [-0.135, +0.135] | recorded |
| PA - PC | Timber stand share of capacity at the end | t | 3901: not recorded; 3902: not recorded; 3903: not recorded; 3904: not recorded; 3905: not recorded; 3906: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PA - PC | Timber stand share of capacity at the end | p | 4001: not recorded; 4002: not recorded; 4003: not recorded; 4004: not recorded; 4005: not recorded; 4006: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| PC | 11.4 [9.6, 13.1] | 33.8 [27.7, 44.9] |
| PS | 11.1 [9.6, 12.4] | 36.9 [29.8, 55.4] |
| PA | 11.5 [9.9, 13.5] | 32.0 [28.5, 39.9] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
