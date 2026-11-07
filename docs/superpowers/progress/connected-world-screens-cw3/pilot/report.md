# CW3: S3 watershed flow and upstream forest protection (B2)

Cohort pilot. Runs: 5; failed: 0 (missing outcomes: 0); simulation and extraction seconds 119 (0.033 core-hours)
Projected held run time from this pilot: 0.198 core-hours (x1.5 = 0.297) for 30 runs

Identity digests: 2331fb2fe1d97c780b91fe762f96760f6f65ae6894db2b626ab1d37613ed74a1 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"clearing_protection": [1], "watershed": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"watershed": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| F | p | 19: activated | 1 of 1 |
| R_CP | p | 19: activated | 1 of 1 |
| F_CPc | p | 19: activated | 1 of 1 |
| F_CP | p | 19: activated | 1 of 1 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw3_ds_water_flow: Downstream regions' water index used, mean over settled turns (F_CP - F: protection's downstream effect under flow) | p | 19: -0.008912 | -0.008912 [-0.008912, -0.008912] | 0 / 1 / 0 | 2/2 as extreme; means [-0.008912, +0.008912] |
| cw3_ds_food_flow: Downstream regions' food shortfall share after relief over the run (F_CP - F) | p | 19: +0.01825 | +0.01825 [+0.01825, +0.01825] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01825, +0.01825] |
| cw3_ds_water_interaction: Downstream water index used: (F_CP - F) - (R_CP - R), the part of protection's downstream water effect that exists only with flow | p | 19: -0.02845 | -0.02845 [-0.02845, -0.02845] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02845, +0.02845] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw3_ds_water_old: Downstream water index used (R_CP - R: under the old index) | p | 19: +0.01954 | +0.01954 [+0.01954, +0.01954] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01954, +0.01954] |
| cw3_ds_food_old: Downstream food shortfall share (R_CP - R: under the old index) | p | 19: +0.02193 | +0.02193 [+0.02193, +0.02193] | 1 / 0 / 0 | 2/2 as extreme; means [-0.02193, +0.02193] |
| cw3_ds_food_interaction: Downstream food shortfall share: (F_CP - F) - (R_CP - R) | p | 19: -0.003671 | -0.003671 [-0.003671, -0.003671] | 0 / 1 / 0 | 2/2 as extreme; means [-0.003671, +0.003671] |
| cw3_ds_water_mode: Downstream water index used (F - R: flow itself) | p | 19: +0.06972 | +0.06972 [+0.06972, +0.06972] | 1 / 0 / 0 | 2/2 as extreme; means [-0.06972, +0.06972] |
| cw3_ds_food_mode: Downstream food shortfall share (F - R: flow itself) | p | 19: -0.01529 | -0.01529 [-0.01529, -0.01529] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01529, +0.01529] |
| cw3_ds_food_met_flow: Downstream demand-weighted mean of min(1, sufficiency) (F_CP - F) | p | 19: -0.01825 | -0.01825 [-0.01825, -0.01825] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01825, +0.01825] |
| cw3_up_food_flow: Upstream regions' food shortfall share (F_CP - F) | p | 19: +0.0198 | +0.0198 [+0.0198, +0.0198] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0198, +0.0198] |
| cw3_up_water_flow: Upstream water index used (F_CP - F) | p | 19: -0.004542 | -0.004542 [-0.004542, -0.004542] | 0 / 1 / 0 | 2/2 as extreme; means [-0.004542, +0.004542] |
| cw3_all_food_flow: All regions' food shortfall share (F_CP - F) | p | 19: +0.01352 | +0.01352 [+0.01352, +0.01352] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01352, +0.01352] |
| cw3_floods_flow: Account flood events (onsets) (F_CP - F) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3_floods_acted: Account flood events that acted (F_CP - F) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3_ds_floods_flow: Account flood onsets in downstream regions (F_CP - F) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3_droughts_flow: Droughts declared (F_CP - F) | p | 19: +3 | +3 [+3, +3] | 1 / 0 / 0 | 2/2 as extreme; means [-3, +3] |
| cw3_ds_droughts_flow: Droughts declared in downstream regions (F_CP - F) | p | 19: +1 | +1 [+1, +1] | 1 / 0 / 0 | 2/2 as extreme; means [-1, +1] |
| cw3_coastal_floods: Coastal floods (F_CP - F; a separate authority) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw3_superseded: River floods superseded (F_CP alone) | p | 19: +11 | +11 [+11, +11] | 1 / 0 / 0 | n/a (no control) |
| cw3_cover_up_flow: Upstream mean forest cover at the end (F_CP - F) | p | 19: +0.08477 | +0.08477 [+0.08477, +0.08477] | 1 / 0 / 0 | 2/2 as extreme; means [-0.08477, +0.08477] |
| cw3_cover_kept: Cover protection kept, total (F_CP alone) | p | 19: +20.35 | +20.35 [+20.35, +20.35] | 1 / 0 / 0 | n/a (no control) |
| cw3_cp_charged: Warden pay charged, total (F_CP alone) | p | 19: +2035 | +2035 [+2035, +2035] | 1 / 0 / 0 | n/a (no control) |
| cw3_cp_downstream: Regions downstream of a region F_CP protected (F_CP alone) | p | 19: +7 | +7 [+7, +7] | 1 / 0 / 0 | n/a (no control) |
| cw3_sel_food_below: Food shortfall share below F_CP's own protected regions (F_CP alone; selection) | p | 19: +0.112 | +0.112 [+0.112, +0.112] | 1 / 0 / 0 | n/a (no control) |
| cw3_sel_water_below: Water index below F_CP's own protected regions (F_CP alone; selection) | p | 19: +0.6514 | +0.6514 [+0.6514, +0.6514] | 1 / 0 / 0 | n/a (no control) |
| cw3_closure: Water account worst relative closure residual (F_CP alone; validity) | p | 19: +8.822e-16 | +8.822e-16 [+8.822e-16, +8.822e-16] | 1 / 0 / 0 | n/a (no control) |
| cw3_index_gap: Worst |index used - derived (capped)| (F_CP alone; validity) | p | 19: +5e-05 | +5e-05 [+5e-05, +5e-05] | 1 / 0 / 0 | n/a (no control) |
| cw3_cpc_ds_water: Downstream water index used (F_CP - F_CPc: the cover kept, cost held equal) | p | 19: -0.002279 | -0.002279 [-0.002279, -0.002279] | 0 / 1 / 0 | 2/2 as extreme; means [-0.002279, +0.002279] |
| cw3_cpc_ds_food: Downstream food shortfall share (F_CP - F_CPc) | p | 19: +0.0116 | +0.0116 [+0.0116, +0.0116] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0116, +0.0116] |
| cw3_cpc_cand_water: Water index below the turn-0 candidate set (F_CP - F_CPc) | p | 19: +0.003646 | +0.003646 [+0.003646, +0.003646] | 1 / 0 / 0 | 2/2 as extreme; means [-0.003646, +0.003646] |
| cw3_cpc_cand_food: Food shortfall share below the turn-0 candidate set (F_CP - F_CPc) | p | 19: +0.001886 | +0.001886 [+0.001886, +0.001886] | 1 / 0 / 0 | 2/2 as extreme; means [-0.001886, +0.001886] |
| cw3_cpc_up_water: Upstream water index used (F_CP - F_CPc) | p | 19: -0.001558 | -0.001558 [-0.001558, -0.001558] | 0 / 1 / 0 | 2/2 as extreme; means [-0.001558, +0.001558] |
| cw3_cpc_cover: Upstream mean forest cover at the end (F_CP - F_CPc) | p | 19: +0.07052 | +0.07052 [+0.07052, +0.07052] | 1 / 0 / 0 | 2/2 as extreme; means [-0.07052, +0.07052] |
| cw3_cpc_droughts: Droughts declared (F_CP - F_CPc) | p | 19: +2 | +2 [+2, +2] | 1 / 0 / 0 | 2/2 as extreme; means [-2, +2] |
| cw3_cost_ds_food: Downstream food shortfall share (F_CPc - F: protection's cost alone) | p | 19: +0.006655 | +0.006655 [+0.006655, +0.006655] | 1 / 0 / 0 | 2/2 as extreme; means [-0.006655, +0.006655] |
| cw3_cost_ds_water: Downstream water index used (F_CPc - F: the cost alone) | p | 19: -0.006634 | -0.006634 [-0.006634, -0.006634] | 0 / 1 / 0 | 2/2 as extreme; means [-0.006634, +0.006634] |
| cw3_cost_treasury: Treasury at the end (F_CPc - F: the cost alone) | p | 19: +1734 | +1734 [+1734, +1734] | 1 / 0 / 0 | 2/2 as extreme; means [-1734, +1734] |
| cw3_cpc_would_keep: Cover protection would have kept (F_CPc alone; it keeps none) | p | 19: +5.29 | +5.29 [+5.29, +5.29] | 1 / 0 / 0 | n/a (no control) |
| cw3_h_food_shortfall: Food shortfall after relief over the run, world (F_CP - F) | p | 19: +477.6 | +477.6 [+477.6, +477.6] | 1 / 0 / 0 | 2/2 as extreme; means [-477.6, +477.6] |
| cw3_h_population: Population at the end (F_CP - F) | p | 19: -22 | -22 [-22, -22] | 0 / 1 / 0 | 2/2 as extreme; means [-22, +22] |
| cw3_h_treasury: Treasury at the end (F_CP - F) | p | 19: +3586 | +3586 [+3586, +3586] | 1 / 0 / 0 | 2/2 as extreme; means [-3586, +3586] |
| cw3_h_out_migration: Agents moving between regions over the run (F_CP - F) | p | 19: -831 | -831 [-831, -831] | 0 / 1 / 0 | 2/2 as extreme; means [-831, +831] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F - R | Population at the end (sum over civilizations) | p | 19: +38 | +38 [+38, +38] | 1 / 0 / 0 | 2/2 as extreme; means [-38, +38] | recorded |
| F - R | Treasury at the end (sum over civilizations) | p | 19: +362 | +362 [+362, +362] | 1 / 0 / 0 | 2/2 as extreme; means [-362, +362] | recorded |
| F - R | Food shortfall after relief over the run (food) | p | 19: -144.4 | -144.4 [-144.4, -144.4] | 0 / 1 / 0 | 2/2 as extreme; means [-144.4, +144.4] | recorded |
| F - R | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F - R | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F - R | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F - R | Deaths by epidemic (the epidemic authority) | p | 19: -111 | -111 [-111, -111] | 0 / 1 / 0 | 2/2 as extreme; means [-111, +111] | recorded |
| F - R | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F - R | Agents migrating between regions over the run | p | 19: +1005 | +1005 [+1005, +1005] | 1 / 0 / 0 | 2/2 as extreme; means [-1005, +1005] | recorded |
| F - R | Mean wealth Gini of living civilizations at the end | p | 19: +0.06526 | +0.06526 [+0.06526, +0.06526] | 1 / 0 / 0 | 2/2 as extreme; means [-0.06526, +0.06526] | recorded |
| F - R | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| R_CP - R | Population at the end (sum over civilizations) | p | 19: +122 | +122 [+122, +122] | 1 / 0 / 0 | 2/2 as extreme; means [-122, +122] | recorded |
| R_CP - R | Treasury at the end (sum over civilizations) | p | 19: -1667 | -1667 [-1667, -1667] | 0 / 1 / 0 | 2/2 as extreme; means [-1667, +1667] | recorded |
| R_CP - R | Food shortfall after relief over the run (food) | p | 19: +1405 | +1405 [+1405, +1405] | 1 / 0 / 0 | 2/2 as extreme; means [-1405, +1405] | recorded |
| R_CP - R | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R_CP - R | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R_CP - R | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| R_CP - R | Deaths by epidemic (the epidemic authority) | p | 19: -372 | -372 [-372, -372] | 0 / 1 / 0 | 2/2 as extreme; means [-372, +372] | recorded |
| R_CP - R | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| R_CP - R | Agents migrating between regions over the run | p | 19: +1449 | +1449 [+1449, +1449] | 1 / 0 / 0 | 2/2 as extreme; means [-1449, +1449] | recorded |
| R_CP - R | Mean wealth Gini of living civilizations at the end | p | 19: +0.01496 | +0.01496 [+0.01496, +0.01496] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01496, +0.01496] | recorded |
| R_CP - R | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| F_CPc - F | Population at the end (sum over civilizations) | p | 19: +4 | +4 [+4, +4] | 1 / 0 / 0 | 2/2 as extreme; means [-4, +4] | recorded |
| F_CPc - F | Treasury at the end (sum over civilizations) | p | 19: +1734 | +1734 [+1734, +1734] | 1 / 0 / 0 | 2/2 as extreme; means [-1734, +1734] | recorded |
| F_CPc - F | Food shortfall after relief over the run (food) | p | 19: -96.52 | -96.52 [-96.52, -96.52] | 0 / 1 / 0 | 2/2 as extreme; means [-96.52, +96.52] | recorded |
| F_CPc - F | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CPc - F | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CPc - F | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F_CPc - F | Deaths by epidemic (the epidemic authority) | p | 19: -28 | -28 [-28, -28] | 0 / 1 / 0 | 2/2 as extreme; means [-28, +28] | recorded |
| F_CPc - F | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F_CPc - F | Agents migrating between regions over the run | p | 19: -792 | -792 [-792, -792] | 0 / 1 / 0 | 2/2 as extreme; means [-792, +792] | recorded |
| F_CPc - F | Mean wealth Gini of living civilizations at the end | p | 19: +0.002961 | +0.002961 [+0.002961, +0.002961] | 1 / 0 / 0 | 2/2 as extreme; means [-0.002961, +0.002961] | recorded |
| F_CPc - F | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| F_CP - F_CPc | Population at the end (sum over civilizations) | p | 19: -26 | -26 [-26, -26] | 0 / 1 / 0 | 2/2 as extreme; means [-26, +26] | recorded |
| F_CP - F_CPc | Treasury at the end (sum over civilizations) | p | 19: +1852 | +1852 [+1852, +1852] | 1 / 0 / 0 | 2/2 as extreme; means [-1852, +1852] | recorded |
| F_CP - F_CPc | Food shortfall after relief over the run (food) | p | 19: +574.1 | +574.1 [+574.1, +574.1] | 1 / 0 / 0 | 2/2 as extreme; means [-574.1, +574.1] | recorded |
| F_CP - F_CPc | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CP - F_CPc | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CP - F_CPc | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F_CP - F_CPc | Deaths by epidemic (the epidemic authority) | p | 19: +43 | +43 [+43, +43] | 1 / 0 / 0 | 2/2 as extreme; means [-43, +43] | recorded |
| F_CP - F_CPc | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F_CP - F_CPc | Agents migrating between regions over the run | p | 19: -39 | -39 [-39, -39] | 0 / 1 / 0 | 2/2 as extreme; means [-39, +39] | recorded |
| F_CP - F_CPc | Mean wealth Gini of living civilizations at the end | p | 19: -0.05524 | -0.05524 [-0.05524, -0.05524] | 0 / 1 / 0 | 2/2 as extreme; means [-0.05524, +0.05524] | recorded |
| F_CP - F_CPc | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| F_CP - F | Population at the end (sum over civilizations) | p | 19: -22 | -22 [-22, -22] | 0 / 1 / 0 | 2/2 as extreme; means [-22, +22] | recorded |
| F_CP - F | Treasury at the end (sum over civilizations) | p | 19: +3586 | +3586 [+3586, +3586] | 1 / 0 / 0 | 2/2 as extreme; means [-3586, +3586] | recorded |
| F_CP - F | Food shortfall after relief over the run (food) | p | 19: +477.6 | +477.6 [+477.6, +477.6] | 1 / 0 / 0 | 2/2 as extreme; means [-477.6, +477.6] | recorded |
| F_CP - F | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CP - F | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CP - F | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F_CP - F | Deaths by epidemic (the epidemic authority) | p | 19: +15 | +15 [+15, +15] | 1 / 0 / 0 | 2/2 as extreme; means [-15, +15] | recorded |
| F_CP - F | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F_CP - F | Agents migrating between regions over the run | p | 19: -831 | -831 [-831, -831] | 0 / 1 / 0 | 2/2 as extreme; means [-831, +831] | recorded |
| F_CP - F | Mean wealth Gini of living civilizations at the end | p | 19: -0.05228 | -0.05228 [-0.05228, -0.05228] | 0 / 1 / 0 | 2/2 as extreme; means [-0.05228, +0.05228] | recorded |
| F_CP - F | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | p |
| --- | --- |
| R | 25.2 [25.2, 25.2] |
| F | 28.5 [28.5, 28.5] |
| R_CP | 22.0 [22.0, 22.0] |
| F_CPc | 22.5 [22.5, 22.5] |
| F_CP | 20.8 [20.8, 20.8] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
