# CW-health: Connected public health: material care, water management and dated advice

Cohort pilot. Runs: 6; failed: 0 (missing outcomes: 0); simulation and extraction seconds 148 (0.041 core-hours)
Projected held run time from this pilot: 0.246 core-hours (x1.5 = 0.369) for 36 runs

Identity digests: 3365042f38a5fd1abfe620bc1f8949ba197e251b7a6ca3f68c088d4e0f5bbf15 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"epidemic_care": [1], "food_allocation": [1], "household_retail": [1], "infrastructure_condition": [1], "local_budgets": [1], "public_health": [1], "repair_projects": [1], "residence_ledger": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| PS | t | 5: activated | 1 of 1 |
| PS | p | 19: activated | 1 of 1 |
| PA | t | 5: activated | 1 of 1 |
| PA | p | 19: activated | 1 of 1 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| health_world_death_rate: World epidemic deaths per 1,000 end-turn person-turns (PA - PC) | t | 5: -0.6652 | -0.6652 [-0.6652, -0.6652] | 0 / 1 / 0 | 2/2 as extreme; means [-0.6652, +0.6652] |
| health_world_death_rate: World epidemic deaths per 1,000 end-turn person-turns (PA - PC) | p | 19: -0.4782 | -0.4782 [-0.4782, -0.4782] | 0 / 1 / 0 | 2/2 as extreme; means [-0.4782, +0.4782] |
| health_world_dpi: World epidemic deaths per infectious person-turn (PA - PC) | t | 5: +0.08527 | +0.08527 [+0.08527, +0.08527] | 1 / 0 / 0 | 2/2 as extreme; means [-0.08527, +0.08527] |
| health_world_dpi: World epidemic deaths per infectious person-turn (PA - PC) | p | 19: -0.0154 | -0.0154 [-0.0154, -0.0154] | 0 / 1 / 0 | 2/2 as extreme; means [-0.0154, +0.0154] |
| health_world_arrivals: World cross-polity epidemic arrivals (PA - PS) | t | 5: +5 | +5 [+5, +5] | 1 / 0 / 0 | 2/2 as extreme; means [-5, +5] |
| health_world_arrivals: World cross-polity epidemic arrivals (PA - PS) | p | 19: +9 | +9 [+9, +9] | 1 / 0 / 0 | 2/2 as extreme; means [-9, +9] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| health_h_food_consumed_milli: Actual patient grain consumed (milli-loads) (PA - PC) | t | 5: -1188 | -1188 [-1188, -1188] | 0 / 1 / 0 | 2/2 as extreme; means [-1188, +1188] |
| health_h_food_consumed_milli: Actual patient grain consumed (milli-loads) (PA - PC) | p | 19: +2.676e+04 | +2.676e+04 [+2.676e+04, +2.676e+04] | 1 / 0 / 0 | 2/2 as extreme; means [-2.676e+04, +2.676e+04] |
| health_h_supplies_cash_milli: Patient supply cash paid (milli-units) (PA - PC) | t | 5: +2000 | +2000 [+2000, +2000] | 1 / 0 / 0 | 2/2 as extreme; means [-2000, +2000] |
| health_h_supplies_cash_milli: Patient supply cash paid (milli-units) (PA - PC) | p | 19: +3.7e+04 | +3.7e+04 [+3.7e+04, +3.7e+04] | 1 / 0 / 0 | 2/2 as extreme; means [-3.7e+04, +3.7e+04] |
| health_h_supplies_internal_milli: Local patient grain allocated at dated prices (milli-units) (PA - PC) | t | 5: -4000 | -4000 [-4000, -4000] | 0 / 1 / 0 | 2/2 as extreme; means [-4000, +4000] |
| health_h_supplies_internal_milli: Local patient grain allocated at dated prices (milli-units) (PA - PC) | p | 19: +1.3e+04 | +1.3e+04 [+1.3e+04, +1.3e+04] | 1 / 0 / 0 | 2/2 as extreme; means [-1.3e+04, +1.3e+04] |
| health_h_care_paid_milli: Care wages paid (milli-units) (PA - PC) | t | 5: -2.108e+04 | -2.108e+04 [-2.108e+04, -2.108e+04] | 0 / 1 / 0 | 2/2 as extreme; means [-2.108e+04, +2.108e+04] |
| health_h_care_paid_milli: Care wages paid (milli-units) (PA - PC) | p | 19: +3.883e+04 | +3.883e+04 [+3.883e+04, +3.883e+04] | 1 / 0 / 0 | 2/2 as extreme; means [-3.883e+04, +3.883e+04] |
| health_h_care_income_withheld: Observed ordinary carer income withheld subtotal (PA - PC) | t | 5: -6.043 | -6.043 [-6.043, -6.043] | 0 / 1 / 0 | 2/2 as extreme; means [-6.043, +6.043] |
| health_h_care_income_withheld: Observed ordinary carer income withheld subtotal (PA - PC) | p | 19: +9.497 | +9.497 [+9.497, +9.497] | 1 / 0 / 0 | 2/2 as extreme; means [-9.497, +9.497] |
| health_h_care_income_unknown_person_turns: Paid carer person-turns without an income deduction observation (PA - PC) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| health_h_care_income_unknown_person_turns: Paid carer person-turns without an income deduction observation (PA - PC) | p | 19: -3 | -3 [-3, -3] | 0 / 1 / 0 | 2/2 as extreme; means [-3, +3] |
| health_h_guard_paid_milli: Guard wages paid (milli-units) (PA - PC) | t | 5: -1.1e+04 | -1.1e+04 [-1.1e+04, -1.1e+04] | 0 / 1 / 0 | 2/2 as extreme; means [-1.1e+04, +1.1e+04] |
| health_h_guard_paid_milli: Guard wages paid (milli-units) (PA - PC) | p | 19: -9.39e+04 | -9.39e+04 [-9.39e+04, -9.39e+04] | 0 / 1 / 0 | 2/2 as extreme; means [-9.39e+04, +9.39e+04] |
| health_h_guard_income_withheld: Observed ordinary guard income withheld subtotal (PA - PC) | t | 5: -2.795 | -2.795 [-2.795, -2.795] | 0 / 1 / 0 | 2/2 as extreme; means [-2.795, +2.795] |
| health_h_guard_income_withheld: Observed ordinary guard income withheld subtotal (PA - PC) | p | 19: -24.99 | -24.99 [-24.99, -24.99] | 0 / 1 / 0 | 2/2 as extreme; means [-24.99, +24.99] |
| health_h_guard_income_unknown_person_turns: Paid guard person-turns without an income deduction observation (PA - PC) | t | 5: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] |
| health_h_guard_income_unknown_person_turns: Paid guard person-turns without an income deduction observation (PA - PC) | p | 19: -3 | -3 [-3, -3] | 0 / 1 / 0 | 2/2 as extreme; means [-3, +3] |
| health_h_care_farm_time: Carer farm time removed (PA - PC) | t | 5: -42.16 | -42.16 [-42.16, -42.16] | 0 / 1 / 0 | 2/2 as extreme; means [-42.16, +42.16] |
| health_h_care_farm_time: Carer farm time removed (PA - PC) | p | 19: +77.71 | +77.71 [+77.71, +77.71] | 1 / 0 / 0 | 2/2 as extreme; means [-77.71, +77.71] |
| health_h_guard_farm_time: Guard farm time removed (PA - PC) | t | 5: -22 | -22 [-22, -22] | 0 / 1 / 0 | 2/2 as extreme; means [-22, +22] |
| health_h_guard_farm_time: Guard farm time removed (PA - PC) | p | 19: -187.8 | -187.8 [-187.8, -187.8] | 0 / 1 / 0 | 2/2 as extreme; means [-187.8, +187.8] |
| health_h_l9_envelope_milli: Gross single care/public-health envelopes (milli-units) (PA - PC) | t | 5: -4.3e+05 | -4.3e+05 [-4.3e+05, -4.3e+05] | 0 / 1 / 0 | 2/2 as extreme; means [-4.3e+05, +4.3e+05] |
| health_h_l9_envelope_milli: Gross single care/public-health envelopes (milli-units) (PA - PC) | p | 19: +9.66e+05 | +9.66e+05 [+9.66e+05, +9.66e+05] | 1 / 0 / 0 | 2/2 as extreme; means [-9.66e+05, +9.66e+05] |
| health_h_health_cash_milli: Actual whole-coin health cash funding (milli-units) (PA - PC) | t | 5: -3.2e+04 | -3.2e+04 [-3.2e+04, -3.2e+04] | 0 / 1 / 0 | 2/2 as extreme; means [-3.2e+04, +3.2e+04] |
| health_h_health_cash_milli: Actual whole-coin health cash funding (milli-units) (PA - PC) | p | 19: -1.9e+04 | -1.9e+04 [-1.9e+04, -1.9e+04] | 0 / 1 / 0 | 2/2 as extreme; means [-1.9e+04, +1.9e+04] |
| health_h_care_carry_change_milli: Change in prepaid care wage carry (milli-units) (PA - PC) | t | 5: -925 | -925 [-925, -925] | 0 / 1 / 0 | 2/2 as extreme; means [-925, +925] |
| health_h_care_carry_change_milli: Change in prepaid care wage carry (milli-units) (PA - PC) | p | 19: -1830 | -1830 [-1830, -1830] | 0 / 1 / 0 | 2/2 as extreme; means [-1830, +1830] |
| health_h_guard_carry_change_milli: Change in prepaid guard wage carry (milli-units) (PA - PC) | t | 5: -1000 | -1000 [-1000, -1000] | 0 / 1 / 0 | 2/2 as extreme; means [-1000, +1000] |
| health_h_guard_carry_change_milli: Change in prepaid guard wage carry (milli-units) (PA - PC) | p | 19: +900 | +900 [+900, +900] | 1 / 0 / 0 | 2/2 as extreme; means [-900, +900] |
| health_h_famine_region_turns: Region-turns below 0.6 food sufficiency (PA - PC) | t | 5: +9 | +9 [+9, +9] | 1 / 0 / 0 | 2/2 as extreme; means [-9, +9] |
| health_h_famine_region_turns: Region-turns below 0.6 food sufficiency (PA - PC) | p | 19: -316 | -316 [-316, -316] | 0 / 1 / 0 | 2/2 as extreme; means [-316, +316] |
| health_h_migrants_blocked: Refused civilian migration person-turns (PA - PC) | t | 5: -9 | -9 [-9, -9] | 0 / 1 / 0 | 2/2 as extreme; means [-9, +9] |
| health_h_migrants_blocked: Refused civilian migration person-turns (PA - PC) | p | 19: -6 | -6 [-6, -6] | 0 / 1 / 0 | 2/2 as extreme; means [-6, +6] |
| health_h_flight_blocked: Refused flight person-turns (PA - PC) | t | 5: -24 | -24 [-24, -24] | 0 / 1 / 0 | 2/2 as extreme; means [-24, +24] |
| health_h_flight_blocked: Refused flight person-turns (PA - PC) | p | 19: -11 | -11 [-11, -11] | 0 / 1 / 0 | 2/2 as extreme; means [-11, +11] |
| health_h_hunger_blocked: Refused hunger moves (PA - PC) | t | 5: +3 | +3 [+3, +3] | 1 / 0 / 0 | 2/2 as extreme; means [-3, +3] |
| health_h_hunger_blocked: Refused hunger moves (PA - PC) | p | 19: -2 | -2 [-2, -2] | 0 / 1 / 0 | 2/2 as extreme; means [-2, +2] |
| health_h_route_turns_removed: Removed partner route-turns (PA - PC) | t | 5: -4 | -4 [-4, -4] | 0 / 1 / 0 | 2/2 as extreme; means [-4, +4] |
| health_h_route_turns_removed: Removed partner route-turns (PA - PC) | p | 19: +3 | +3 [+3, +3] | 1 / 0 / 0 | 2/2 as extreme; means [-3, +3] |
| health_h_forgone_income: Forgone partner route income (PA - PC) | t | 5: -16 | -16 [-16, -16] | 0 / 1 / 0 | 2/2 as extreme; means [-16, +16] |
| health_h_forgone_income: Forgone partner route income (PA - PC) | p | 19: +8 | +8 [+8, +8] | 1 / 0 / 0 | 2/2 as extreme; means [-8, +8] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PS - PC | Population at the end (sum over civilizations) | t | 5: +28 | +28 [+28, +28] | 1 / 0 / 0 | 2/2 as extreme; means [-28, +28] | recorded |
| PS - PC | Population at the end (sum over civilizations) | p | 19: +38 | +38 [+38, +38] | 1 / 0 / 0 | 2/2 as extreme; means [-38, +38] | recorded |
| PS - PC | Treasury at the end (sum over civilizations) | t | 5: -153 | -153 [-153, -153] | 0 / 1 / 0 | 2/2 as extreme; means [-153, +153] | recorded |
| PS - PC | Treasury at the end (sum over civilizations) | p | 19: +1066 | +1066 [+1066, +1066] | 1 / 0 / 0 | 2/2 as extreme; means [-1066, +1066] | recorded |
| PS - PC | Food shortfall after relief over the run (food) | t | 5: -406 | -406 [-406, -406] | 0 / 1 / 0 | 2/2 as extreme; means [-406, +406] | recorded |
| PS - PC | Food shortfall after relief over the run (food) | p | 19: +366.3 | +366.3 [+366.3, +366.3] | 1 / 0 / 0 | 2/2 as extreme; means [-366.3, +366.3] | recorded |
| PS - PC | Priced-out person-turns | t | 5: +77 | +77 [+77, +77] | 1 / 0 / 0 | 2/2 as extreme; means [-77, +77] | recorded |
| PS - PC | Priced-out person-turns | p | 19: -86 | -86 [-86, -86] | 0 / 1 / 0 | 2/2 as extreme; means [-86, +86] | recorded |
| PS - PC | Priced-out child-turns | t | 5: +15 | +15 [+15, +15] | 1 / 0 / 0 | 2/2 as extreme; means [-15, +15] | recorded |
| PS - PC | Priced-out child-turns | p | 19: -10 | -10 [-10, -10] | 0 / 1 / 0 | 2/2 as extreme; means [-10, +10] | recorded |
| PS - PC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PS - PC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PS - PC | Deaths by epidemic (the epidemic authority) | t | 5: -22 | -22 [-22, -22] | 0 / 1 / 0 | 2/2 as extreme; means [-22, +22] | recorded |
| PS - PC | Deaths by epidemic (the epidemic authority) | p | 19: +109 | +109 [+109, +109] | 1 / 0 / 0 | 2/2 as extreme; means [-109, +109] | recorded |
| PS - PC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PS - PC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PS - PC | Agents migrating between regions over the run | t | 5: -139 | -139 [-139, -139] | 0 / 1 / 0 | 2/2 as extreme; means [-139, +139] | recorded |
| PS - PC | Agents migrating between regions over the run | p | 19: +632 | +632 [+632, +632] | 1 / 0 / 0 | 2/2 as extreme; means [-632, +632] | recorded |
| PS - PC | Mean wealth Gini of living civilizations at the end | t | 5: +0.04496 | +0.04496 [+0.04496, +0.04496] | 1 / 0 / 0 | 2/2 as extreme; means [-0.04496, +0.04496] | recorded |
| PS - PC | Mean wealth Gini of living civilizations at the end | p | 19: -0.001433 | -0.001433 [-0.001433, -0.001433] | 0 / 1 / 0 | 2/2 as extreme; means [-0.001433, +0.001433] | recorded |
| PS - PC | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PS - PC | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PA - PS | Population at the end (sum over civilizations) | t | 5: -31 | -31 [-31, -31] | 0 / 1 / 0 | 2/2 as extreme; means [-31, +31] | recorded |
| PA - PS | Population at the end (sum over civilizations) | p | 19: +20 | +20 [+20, +20] | 1 / 0 / 0 | 2/2 as extreme; means [-20, +20] | recorded |
| PA - PS | Treasury at the end (sum over civilizations) | t | 5: +143 | +143 [+143, +143] | 1 / 0 / 0 | 2/2 as extreme; means [-143, +143] | recorded |
| PA - PS | Treasury at the end (sum over civilizations) | p | 19: -2583 | -2583 [-2583, -2583] | 0 / 1 / 0 | 2/2 as extreme; means [-2583, +2583] | recorded |
| PA - PS | Food shortfall after relief over the run (food) | t | 5: +400.6 | +400.6 [+400.6, +400.6] | 1 / 0 / 0 | 2/2 as extreme; means [-400.6, +400.6] | recorded |
| PA - PS | Food shortfall after relief over the run (food) | p | 19: +1163 | +1163 [+1163, +1163] | 1 / 0 / 0 | 2/2 as extreme; means [-1163, +1163] | recorded |
| PA - PS | Priced-out person-turns | t | 5: -107 | -107 [-107, -107] | 0 / 1 / 0 | 2/2 as extreme; means [-107, +107] | recorded |
| PA - PS | Priced-out person-turns | p | 19: -20 | -20 [-20, -20] | 0 / 1 / 0 | 2/2 as extreme; means [-20, +20] | recorded |
| PA - PS | Priced-out child-turns | t | 5: -3 | -3 [-3, -3] | 0 / 1 / 0 | 2/2 as extreme; means [-3, +3] | recorded |
| PA - PS | Priced-out child-turns | p | 19: -6 | -6 [-6, -6] | 0 / 1 / 0 | 2/2 as extreme; means [-6, +6] | recorded |
| PA - PS | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PA - PS | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PA - PS | Deaths by epidemic (the epidemic authority) | t | 5: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] | recorded |
| PA - PS | Deaths by epidemic (the epidemic authority) | p | 19: -113 | -113 [-113, -113] | 0 / 1 / 0 | 2/2 as extreme; means [-113, +113] | recorded |
| PA - PS | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PA - PS | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PA - PS | Agents migrating between regions over the run | t | 5: +132 | +132 [+132, +132] | 1 / 0 / 0 | 2/2 as extreme; means [-132, +132] | recorded |
| PA - PS | Agents migrating between regions over the run | p | 19: +938 | +938 [+938, +938] | 1 / 0 / 0 | 2/2 as extreme; means [-938, +938] | recorded |
| PA - PS | Mean wealth Gini of living civilizations at the end | t | 5: -0.06859 | -0.06859 [-0.06859, -0.06859] | 0 / 1 / 0 | 2/2 as extreme; means [-0.06859, +0.06859] | recorded |
| PA - PS | Mean wealth Gini of living civilizations at the end | p | 19: +0.06945 | +0.06945 [+0.06945, +0.06945] | 1 / 0 / 0 | 2/2 as extreme; means [-0.06945, +0.06945] | recorded |
| PA - PS | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PA - PS | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PA - PC | Population at the end (sum over civilizations) | t | 5: -3 | -3 [-3, -3] | 0 / 1 / 0 | 2/2 as extreme; means [-3, +3] | recorded |
| PA - PC | Population at the end (sum over civilizations) | p | 19: +58 | +58 [+58, +58] | 1 / 0 / 0 | 2/2 as extreme; means [-58, +58] | recorded |
| PA - PC | Treasury at the end (sum over civilizations) | t | 5: -10 | -10 [-10, -10] | 0 / 1 / 0 | 2/2 as extreme; means [-10, +10] | recorded |
| PA - PC | Treasury at the end (sum over civilizations) | p | 19: -1517 | -1517 [-1517, -1517] | 0 / 1 / 0 | 2/2 as extreme; means [-1517, +1517] | recorded |
| PA - PC | Food shortfall after relief over the run (food) | t | 5: -5.327 | -5.327 [-5.327, -5.327] | 0 / 1 / 0 | 2/2 as extreme; means [-5.327, +5.327] | recorded |
| PA - PC | Food shortfall after relief over the run (food) | p | 19: +1530 | +1530 [+1530, +1530] | 1 / 0 / 0 | 2/2 as extreme; means [-1530, +1530] | recorded |
| PA - PC | Priced-out person-turns | t | 5: -30 | -30 [-30, -30] | 0 / 1 / 0 | 2/2 as extreme; means [-30, +30] | recorded |
| PA - PC | Priced-out person-turns | p | 19: -106 | -106 [-106, -106] | 0 / 1 / 0 | 2/2 as extreme; means [-106, +106] | recorded |
| PA - PC | Priced-out child-turns | t | 5: +12 | +12 [+12, +12] | 1 / 0 / 0 | 2/2 as extreme; means [-12, +12] | recorded |
| PA - PC | Priced-out child-turns | p | 19: -16 | -16 [-16, -16] | 0 / 1 / 0 | 2/2 as extreme; means [-16, +16] | recorded |
| PA - PC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PA - PC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| PA - PC | Deaths by epidemic (the epidemic authority) | t | 5: -23 | -23 [-23, -23] | 0 / 1 / 0 | 2/2 as extreme; means [-23, +23] | recorded |
| PA - PC | Deaths by epidemic (the epidemic authority) | p | 19: -4 | -4 [-4, -4] | 0 / 1 / 0 | 2/2 as extreme; means [-4, +4] | recorded |
| PA - PC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PA - PC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| PA - PC | Agents migrating between regions over the run | t | 5: -7 | -7 [-7, -7] | 0 / 1 / 0 | 2/2 as extreme; means [-7, +7] | recorded |
| PA - PC | Agents migrating between regions over the run | p | 19: +1570 | +1570 [+1570, +1570] | 1 / 0 / 0 | 2/2 as extreme; means [-1570, +1570] | recorded |
| PA - PC | Mean wealth Gini of living civilizations at the end | t | 5: -0.02363 | -0.02363 [-0.02363, -0.02363] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02363, +0.02363] | recorded |
| PA - PC | Mean wealth Gini of living civilizations at the end | p | 19: +0.06802 | +0.06802 [+0.06802, +0.06802] | 1 / 0 / 0 | 2/2 as extreme; means [-0.06802, +0.06802] | recorded |
| PA - PC | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| PA - PC | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| PC | 13.7 [13.7, 13.7] | 36.3 [36.3, 36.3] |
| PS | 14.1 [14.1, 14.1] | 31.8 [31.8, 31.8] |
| PA | 14.6 [14.6, 14.6] | 37.1 [37.1, 37.1] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
