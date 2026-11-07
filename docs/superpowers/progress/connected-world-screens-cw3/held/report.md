# CW3: S3 watershed flow and upstream forest protection (B2)

Cohort held. Runs: 30; failed: 1 (missing outcomes: 0); simulation and extraction seconds 1148 (0.319 core-hours)
- FAILED F_CP p851 (rc 1): chronicler/artifact_io.py", line 190, in _atomic_write
    raise ArtifactIOError(f"could not write artifact {path}: {exc}") from exc
chronicler.artifact_io.ArtifactIOError: could not write artifact /home/user/evidence/cw3/held/runs/F_CP-p851/chronicle_bundle.json: [Errno 28] No space left on device


Identity digests: 4b61577c610776142bd76c6200d24e505d5ce230e50b30ac774dfed640ae579a (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"clearing_protection": [1], "watershed": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"watershed": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| F | p | 851: activated; 852: activated; 853: activated; 854: activated; 855: activated; 856: activated | 6 of 6 |
| R_CP | p | 851: activated; 852: activated; 853: activated; 854: activated; 855: activated; 856: activated | 6 of 6 |
| F_CPc | p | 851: activated; 852: activated; 853: activated; 854: activated; 855: activated; 856: activated | 6 of 6 |
| F_CP | p | 851: failed; 852: activated; 853: activated; 854: activated; 855: activated; 856: activated | 5 of 6 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw3_ds_water_flow: Downstream regions' water index used, mean over settled turns (F_CP - F: protection's downstream effect under flow) | p | 851: failed; 852: +0.0007665; 853: -0.007479; 854: -0.006422; 855: -0.003682; 856: +0.001392 | -0.003085 [-0.007479, +0.001392] | 2 / 3 / 0 | 8/32 as extreme; means [-0.003948, +0.003948] |
| cw3_ds_food_flow: Downstream regions' food shortfall share after relief over the run (F_CP - F) | p | 851: failed; 852: +0.02392; 853: +0.003136; 854: -0.01143; 855: +0.006001; 856: +0.01397 | +0.007118 [-0.01143, +0.02392] | 4 / 1 / 0 | 10/32 as extreme; means [-0.01169, +0.01169] |
| cw3_ds_water_interaction: Downstream water index used: (F_CP - F) - (R_CP - R), the part of protection's downstream water effect that exists only with flow | p | 851: failed; 852: +0.04271; 853: -0.01905; 854: -0.002891; 855: -0.01407; 856: +0.005068 | +0.002352 [-0.01905, +0.04271] | 2 / 3 / 0 | 28/32 as extreme; means [-0.01676, +0.01676] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw3_ds_water_old: Downstream water index used (R_CP - R: under the old index) | p | 851: +0.01243; 852: -0.04194; 853: +0.01157; 854: -0.003531; 855: +0.01039; 856: -0.003676 | -0.00246 [-0.04194, +0.01243] | 3 / 3 / 0 | 58/64 as extreme; means [-0.01392, +0.01392] |
| cw3_ds_food_old: Downstream food shortfall share (R_CP - R: under the old index) | p | 851: -0.01891; 852: -0.01664; 853: -0.006718; 854: +0.001463; 855: +0.002815; 856: -0.02385 | -0.01031 [-0.02385, +0.002815] | 2 / 4 / 0 | 8/64 as extreme; means [-0.01173, +0.01173] |
| cw3_ds_food_interaction: Downstream food shortfall share: (F_CP - F) - (R_CP - R) | p | 851: failed; 852: +0.04056; 853: +0.009854; 854: -0.0129; 855: +0.003187; 856: +0.03782 | +0.0157 [-0.0129, +0.04056] | 4 / 1 / 0 | 8/32 as extreme; means [-0.02086, +0.02086] |
| cw3_ds_water_mode: Downstream water index used (F - R: flow itself) | p | 851: +0.05633; 852: -0.008841; 853: +0.08549; 854: +0.05075; 855: +0.09823; 856: +0.02459 | +0.05109 [-0.008841, +0.09823] | 5 / 1 / 0 | 4/64 as extreme; means [-0.05404, +0.05404] |
| cw3_ds_food_mode: Downstream food shortfall share (F - R: flow itself) | p | 851: -0.03277; 852: -0.00853; 853: -0.02406; 854: -0.0425; 855: -0.01832; 856: -0.03035 | -0.02609 [-0.0425, -0.00853] | 0 / 6 / 0 | 2/64 as extreme; means [-0.02609, +0.02609] |
| cw3_ds_food_met_flow: Downstream demand-weighted mean of min(1, sufficiency) (F_CP - F) | p | 851: failed; 852: -0.02392; 853: -0.003136; 854: +0.01143; 855: -0.006001; 856: -0.01397 | -0.007118 [-0.02392, +0.01143] | 1 / 4 / 0 | 10/32 as extreme; means [-0.01169, +0.01169] |
| cw3_up_food_flow: Upstream regions' food shortfall share (F_CP - F) | p | 851: failed; 852: +0.02992; 853: +0.006301; 854: -0.01877; 855: -0.005299; 856: +0.01458 | +0.005346 [-0.01877, +0.02992] | 3 / 2 / 0 | 18/32 as extreme; means [-0.01497, +0.01497] |
| cw3_up_water_flow: Upstream water index used (F_CP - F) | p | 851: failed; 852: +0.001432; 853: +0.0006233; 854: -0.006426; 855: -0.0004958; 856: +0.0002493 | -0.0009235 [-0.006426, +0.001432] | 3 / 2 / 0 | 28/32 as extreme; means [-0.001845, +0.001845] |
| cw3_all_food_flow: All regions' food shortfall share (F_CP - F) | p | 851: failed; 852: +0.01879; 853: +0.01091; 854: -0.0009028; 855: +0.003615; 856: +0.005088 | +0.0075 [-0.0009028, +0.01879] | 4 / 1 / 0 | 4/32 as extreme; means [-0.007861, +0.007861] |
| cw3_floods_flow: Account flood events (onsets) (F_CP - F) | p | 851: failed; 852: +1; 853: +0; 854: +2; 855: +0; 856: +0 | +0.6 [+0, +2] | 2 / 0 / 3 | 16/32 as extreme; means [-0.6, +0.6] |
| cw3_floods_acted: Account flood events that acted (F_CP - F) | p | 851: failed; 852: +1; 853: +0; 854: +2; 855: +0; 856: +0 | +0.6 [+0, +2] | 2 / 0 / 3 | 16/32 as extreme; means [-0.6, +0.6] |
| cw3_ds_floods_flow: Account flood onsets in downstream regions (F_CP - F) | p | 851: failed; 852: +1; 853: +0; 854: +2; 855: +0; 856: +0 | +0.6 [+0, +2] | 2 / 0 / 3 | 16/32 as extreme; means [-0.6, +0.6] |
| cw3_droughts_flow: Droughts declared (F_CP - F) | p | 851: failed; 852: -5; 853: +1; 854: +10; 855: -1; 856: +1 | +1.2 [-5, +10] | 3 / 2 / 0 | 24/32 as extreme; means [-3.6, +3.6] |
| cw3_ds_droughts_flow: Droughts declared in downstream regions (F_CP - F) | p | 851: failed; 852: -3; 853: +1; 854: +4; 855: +0; 856: +0 | +0.4 [-3, +4] | 2 / 1 / 2 | 24/32 as extreme; means [-1.6, +1.6] |
| cw3_coastal_floods: Coastal floods (F_CP - F; a separate authority) | p | 851: failed; 852: +0; 853: +0; 854: +0; 855: +0; 856: +0 | +0 [+0, +0] | 0 / 0 / 5 | 32/32 as extreme; means [+0, +0] |
| cw3_superseded: River floods superseded (F_CP alone) | p | 851: failed; 852: +0; 853: +8; 854: +0; 855: +5; 856: +0 | +2.6 [+0, +8] | 2 / 0 / 3 | n/a (no control) |
| cw3_cover_up_flow: Upstream mean forest cover at the end (F_CP - F) | p | 851: failed; 852: +0.006153; 853: +0.0452; 854: +0.02624; 855: -0.01968; 856: +0.01442 | +0.01447 [-0.01968, +0.0452] | 4 / 1 / 0 | 8/32 as extreme; means [-0.02234, +0.02234] |
| cw3_cover_kept: Cover protection kept, total (F_CP alone) | p | 851: failed; 852: +25.61; 853: +22.82; 854: +10.57; 855: +15.55; 856: +18.9 | +18.69 [+10.57, +25.61] | 5 / 0 / 0 | n/a (no control) |
| cw3_cp_charged: Warden pay charged, total (F_CP alone) | p | 851: failed; 852: +2561; 853: +2282; 854: +1057; 855: +1555; 856: +1890 | +1869 [+1057, +2561] | 5 / 0 / 0 | n/a (no control) |
| cw3_cp_downstream: Regions downstream of a region F_CP protected (F_CP alone) | p | 851: failed; 852: +10; 853: +10; 854: +6; 855: +6; 856: +7 | +7.8 [+6, +10] | 5 / 0 / 0 | n/a (no control) |
| cw3_sel_food_below: Food shortfall share below F_CP's own protected regions (F_CP alone; selection) | p | 851: failed; 852: +0.06782; 853: +0.09309; 854: +0.1193; 855: +0.0405; 856: +0.09875 | +0.0839 [+0.0405, +0.1193] | 5 / 0 / 0 | n/a (no control) |
| cw3_sel_water_below: Water index below F_CP's own protected regions (F_CP alone; selection) | p | 851: failed; 852: +0.7234; 853: +0.6321; 854: +0.6064; 855: +0.6737; 856: +0.7172 | +0.6705 [+0.6064, +0.7234] | 5 / 0 / 0 | n/a (no control) |
| cw3_closure: Water account worst relative closure residual (F_CP alone; validity) | p | 851: failed; 852: +1.391e-15; 853: +7.749e-16; 854: +1.091e-15; 855: +1.87e-15; 856: +1.953e-15 | +1.416e-15 [+7.749e-16, +1.953e-15] | 5 / 0 / 0 | n/a (no control) |
| cw3_index_gap: Worst |index used - derived (capped)| (F_CP alone; validity) | p | 851: failed; 852: +5e-05; 853: +5e-05; 854: +5e-05; 855: +5e-05; 856: +5e-05 | +5e-05 [+5e-05, +5e-05] | 5 / 0 / 0 | n/a (no control) |
| cw3_cpc_ds_water: Downstream water index used (F_CP - F_CPc: the cover kept, cost held equal) | p | 851: failed; 852: -0.004503; 853: -0.003806; 854: -0.0007225; 855: -0.002105; 856: +0.001986 | -0.00183 [-0.004503, +0.001986] | 1 / 4 / 0 | 6/32 as extreme; means [-0.002625, +0.002625] |
| cw3_cpc_ds_food: Downstream food shortfall share (F_CP - F_CPc) | p | 851: failed; 852: +0.002064; 853: -0.003239; 854: -0.06744; 855: -0.01534; 856: +0.006089 | -0.01557 [-0.06744, +0.006089] | 2 / 3 / 0 | 12/32 as extreme; means [-0.01883, +0.01883] |
| cw3_cpc_cand_water: Water index below the turn-0 candidate set (F_CP - F_CPc) | p | 851: failed; 852: -0.01257; 853: -0.008594; 854: +0.007027; 855: -0.004209; 856: +0.003722 | -0.002925 [-0.01257, +0.007027] | 2 / 3 / 0 | 14/32 as extreme; means [-0.007225, +0.007225] |
| cw3_cpc_cand_food: Food shortfall share below the turn-0 candidate set (F_CP - F_CPc) | p | 851: failed; 852: -0.02461; 853: -0.003792; 854: -0.06013; 855: -0.02777; 856: +0.1289 | +0.002511 [-0.06013, +0.1289] | 1 / 4 / 0 | 32/32 as extreme; means [-0.04903, +0.04903] |
| cw3_cpc_up_water: Upstream water index used (F_CP - F_CPc) | p | 851: failed; 852: -0.001224; 853: +0.0005228; 854: -0.0009355; 855: -0.0002553; 856: -0.004097 | -0.001198 [-0.004097, +0.0005228] | 1 / 4 / 0 | 6/32 as extreme; means [-0.001407, +0.001407] |
| cw3_cpc_cover: Upstream mean forest cover at the end (F_CP - F_CPc) | p | 851: failed; 852: -0.01166; 853: +0.03744; 854: +0.07415; 855: -0.08456; 856: +0.1421 | +0.0315 [-0.08456, +0.1421] | 3 / 2 / 0 | 16/32 as extreme; means [-0.06998, +0.06998] |
| cw3_cpc_droughts: Droughts declared (F_CP - F_CPc) | p | 851: failed; 852: -1; 853: +2; 854: +1; 855: +0; 856: +0 | +0.4 [-1, +2] | 2 / 1 / 2 | 24/32 as extreme; means [-0.8, +0.8] |
| cw3_cost_ds_food: Downstream food shortfall share (F_CPc - F: protection's cost alone) | p | 851: +0.0119; 852: +0.02185; 853: +0.006375; 854: +0.056; 855: +0.02134; 856: +0.007877 | +0.02089 [+0.006375, +0.056] | 6 / 0 / 0 | 2/64 as extreme; means [-0.02089, +0.02089] |
| cw3_cost_ds_water: Downstream water index used (F_CPc - F: the cost alone) | p | 851: -0.00157; 852: +0.005269; 853: -0.003673; 854: -0.0057; 855: -0.001577; 856: -0.0005949 | -0.001307 [-0.0057, +0.005269] | 1 / 5 / 0 | 26/64 as extreme; means [-0.003064, +0.003064] |
| cw3_cost_treasury: Treasury at the end (F_CPc - F: the cost alone) | p | 851: -3618; 852: -554; 853: +2115; 854: +3512; 855: -1463; 856: +351 | +57.17 [-3618, +3512] | 3 / 3 / 0 | 62/64 as extreme; means [-1936, +1936] |
| cw3_cpc_would_keep: Cover protection would have kept (F_CPc alone; it keeps none) | p | 851: +5.78; 852: +5.38; 853: +4.46; 854: +6.15; 855: +5.14; 856: +6.91 | +5.637 [+4.46, +6.91] | 6 / 0 / 0 | n/a (no control) |
| cw3_h_food_shortfall: Food shortfall after relief over the run, world (F_CP - F) | p | 851: failed; 852: +2039; 853: +864.5; 854: -703.1; 855: +682.4; 856: +988.8 | +774.3 [-703.1, +2039] | 4 / 1 / 0 | 6/32 as extreme; means [-1055, +1055] |
| cw3_h_population: Population at the end (F_CP - F) | p | 851: failed; 852: +196; 853: +6; 854: -11; 855: +65; 856: +142 | +79.6 [-11, +196] | 4 / 1 / 0 | 6/32 as extreme; means [-84, +84] |
| cw3_h_treasury: Treasury at the end (F_CP - F) | p | 851: failed; 852: -1066; 853: +2706; 854: +1580; 855: -148; 856: +599 | +734.2 [-1066, +2706] | 3 / 2 / 0 | 12/32 as extreme; means [-1220, +1220] |
| cw3_h_out_migration: Agents moving between regions over the run (F_CP - F) | p | 851: failed; 852: +2236; 853: -483; 854: -1776; 855: -18; 856: +496 | +91 [-1776, +2236] | 2 / 3 / 0 | 30/32 as extreme; means [-1002, +1002] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F - R | Population at the end (sum over civilizations) | p | 851: -91; 852: +129; 853: +16; 854: -173; 855: +161; 856: -258 | -36 [-258, +161] | 3 / 3 / 0 | 42/64 as extreme; means [-138, +138] | recorded |
| F - R | Treasury at the end (sum over civilizations) | p | 851: +437; 852: +552; 853: -402; 854: -3789; 855: -87; 856: -203 | -582 [-3789, +552] | 2 / 4 / 0 | 40/64 as extreme; means [-911.7, +911.7] | recorded |
| F - R | Food shortfall after relief over the run (food) | p | 851: -2468; 852: -667.9; 853: -1659; 854: -1560; 855: +116.6; 856: -2527 | -1461 [-2527, +116.6] | 1 / 5 / 0 | 4/64 as extreme; means [-1500, +1500] | recorded |
| F - R | Priced-out person-turns | p | 851: not recorded; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F - R | Priced-out child-turns | p | 851: not recorded; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F - R | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F - R | Deaths by epidemic (the epidemic authority) | p | 851: +247; 852: -149; 853: +202; 854: +194; 855: +81; 856: +70 | +107.5 [-149, +247] | 5 / 1 / 0 | 8/64 as extreme; means [-157.2, +157.2] | recorded |
| F - R | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F - R | Agents migrating between regions over the run | p | 851: -1983; 852: -1611; 853: +737; 854: -292; 855: -300; 856: -454 | -650.5 [-1983, +737] | 1 / 5 / 0 | 12/64 as extreme; means [-896.2, +896.2] | recorded |
| F - R | Mean wealth Gini of living civilizations at the end | p | 851: +0.01682; 852: +0.1968; 853: +0.01939; 854: -0.04979; 855: +0.05868; 856: -0.09095 | +0.02516 [-0.09095, +0.1968] | 4 / 2 / 0 | 40/64 as extreme; means [-0.07207, +0.07207] | recorded |
| F - R | Timber stand share of capacity at the end | p | 851: not recorded; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| R_CP - R | Population at the end (sum over civilizations) | p | 851: -64; 852: +59; 853: -90; 854: -81; 855: +218; 856: -53 | -1.833 [-90, +218] | 2 / 4 / 0 | 62/64 as extreme; means [-94.17, +94.17] | recorded |
| R_CP - R | Treasury at the end (sum over civilizations) | p | 851: -847; 852: +1653; 853: +1102; 854: -5106; 855: +1289; 856: +3428 | +253.2 [-5106, +3428] | 4 / 2 / 0 | 54/64 as extreme; means [-2238, +2238] | recorded |
| R_CP - R | Food shortfall after relief over the run (food) | p | 851: -1904; 852: -406.2; 853: -1091; 854: +857.3; 855: +1601; 856: -464.4 | -234.5 [-1904, +1601] | 2 / 4 / 0 | 44/64 as extreme; means [-1054, +1054] | recorded |
| R_CP - R | Priced-out person-turns | p | 851: not recorded; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R_CP - R | Priced-out child-turns | p | 851: not recorded; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| R_CP - R | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| R_CP - R | Deaths by epidemic (the epidemic authority) | p | 851: +101; 852: +71; 853: +25; 854: -117; 855: -194; 856: +5 | -18.17 [-194, +101] | 4 / 2 / 0 | 48/64 as extreme; means [-85.5, +85.5] | recorded |
| R_CP - R | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| R_CP - R | Agents migrating between regions over the run | p | 851: -1794; 852: +352; 853: -1775; 854: -380; 855: +318; 856: -40 | -553.2 [-1794, +352] | 2 / 4 / 0 | 18/64 as extreme; means [-776.5, +776.5] | recorded |
| R_CP - R | Mean wealth Gini of living civilizations at the end | p | 851: -0.03127; 852: +0.1094; 853: +0.01186; 854: -0.1197; 855: -0.01666; 856: +0.1479 | +0.01693 [-0.1197, +0.1479] | 3 / 3 / 0 | 50/64 as extreme; means [-0.0728, +0.0728] | recorded |
| R_CP - R | Timber stand share of capacity at the end | p | 851: not recorded; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| F_CPc - F | Population at the end (sum over civilizations) | p | 851: -154; 852: -5; 853: -14; 854: +271; 855: -173; 856: +310 | +39.17 [-173, +310] | 2 / 4 / 0 | 48/64 as extreme; means [-154.5, +154.5] | recorded |
| F_CPc - F | Treasury at the end (sum over civilizations) | p | 851: -3618; 852: -554; 853: +2115; 854: +3512; 855: -1463; 856: +351 | +57.17 [-3618, +3512] | 3 / 3 / 0 | 62/64 as extreme; means [-1936, +1936] | recorded |
| F_CPc - F | Food shortfall after relief over the run (food) | p | 851: +514.8; 852: +1210; 853: +115.4; 854: +6385; 855: +485.2; 856: +1470 | +1697 [+115.4, +6385] | 6 / 0 / 0 | 2/64 as extreme; means [-1697, +1697] | recorded |
| F_CPc - F | Priced-out person-turns | p | 851: not recorded; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CPc - F | Priced-out child-turns | p | 851: not recorded; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CPc - F | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F_CPc - F | Deaths by epidemic (the epidemic authority) | p | 851: +10; 852: +9; 853: -89; 854: -354; 855: +90; 856: -59 | -65.5 [-354, +90] | 3 / 3 / 0 | 32/64 as extreme; means [-101.8, +101.8] | recorded |
| F_CPc - F | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F_CPc - F | Agents migrating between regions over the run | p | 851: +1124; 852: +2456; 853: -1605; 854: +3802; 855: +258; 856: +996 | +1172 [-1605, +3802] | 5 / 1 / 0 | 14/64 as extreme; means [-1707, +1707] | recorded |
| F_CPc - F | Mean wealth Gini of living civilizations at the end | p | 851: -0.1631; 852: +0.00998; 853: -0.01919; 854: +0.1184; 855: +0.01585; 856: +0.1478 | +0.01828 [-0.1631, +0.1478] | 4 / 2 / 0 | 52/64 as extreme; means [-0.07905, +0.07905] | recorded |
| F_CPc - F | Timber stand share of capacity at the end | p | 851: not recorded; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| F_CP - F_CPc | Population at the end (sum over civilizations) | p | 851: failed; 852: +201; 853: +20; 854: -282; 855: +238; 856: -168 | +1.8 [-282, +238] | 3 / 2 / 0 | 32/32 as extreme; means [-181.8, +181.8] | recorded |
| F_CP - F_CPc | Treasury at the end (sum over civilizations) | p | 851: failed; 852: -512; 853: +591; 854: -1932; 855: +1315; 856: +248 | -58 [-1932, +1315] | 3 / 2 / 0 | 30/32 as extreme; means [-919.6, +919.6] | recorded |
| F_CP - F_CPc | Food shortfall after relief over the run (food) | p | 851: failed; 852: +829.1; 853: +749.2; 854: -7088; 855: +197.2; 856: -480.8 | -1159 [-7088, +829.1] | 3 / 2 / 0 | 28/32 as extreme; means [-1869, +1869] | recorded |
| F_CP - F_CPc | Priced-out person-turns | p | 851: failed; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CP - F_CPc | Priced-out child-turns | p | 851: failed; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CP - F_CPc | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F_CP - F_CPc | Deaths by epidemic (the epidemic authority) | p | 851: failed; 852: -203; 853: +108; 854: +231; 855: -186; 856: +69 | +3.8 [-203, +231] | 3 / 2 / 0 | 32/32 as extreme; means [-159.4, +159.4] | recorded |
| F_CP - F_CPc | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F_CP - F_CPc | Agents migrating between regions over the run | p | 851: failed; 852: -220; 853: +1122; 854: -5578; 855: -276; 856: -500 | -1090 [-5578, +1122] | 1 / 4 / 0 | 18/32 as extreme; means [-1539, +1539] | recorded |
| F_CP - F_CPc | Mean wealth Gini of living civilizations at the end | p | 851: failed; 852: -0.03418; 853: -0.01658; 854: -0.3553; 855: -0.05803; 856: +0.07185 | -0.07844 [-0.3553, +0.07185] | 1 / 4 / 0 | 12/32 as extreme; means [-0.1072, +0.1072] | recorded |
| F_CP - F_CPc | Timber stand share of capacity at the end | p | 851: failed; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| F_CP - F | Population at the end (sum over civilizations) | p | 851: failed; 852: +196; 853: +6; 854: -11; 855: +65; 856: +142 | +79.6 [-11, +196] | 4 / 1 / 0 | 6/32 as extreme; means [-84, +84] | recorded |
| F_CP - F | Treasury at the end (sum over civilizations) | p | 851: failed; 852: -1066; 853: +2706; 854: +1580; 855: -148; 856: +599 | +734.2 [-1066, +2706] | 3 / 2 / 0 | 12/32 as extreme; means [-1220, +1220] | recorded |
| F_CP - F | Food shortfall after relief over the run (food) | p | 851: failed; 852: +2039; 853: +864.5; 854: -703.1; 855: +682.4; 856: +988.8 | +774.3 [-703.1, +2039] | 4 / 1 / 0 | 6/32 as extreme; means [-1055, +1055] | recorded |
| F_CP - F | Priced-out person-turns | p | 851: failed; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CP - F | Priced-out child-turns | p | 851: failed; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| F_CP - F | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| F_CP - F | Deaths by epidemic (the epidemic authority) | p | 851: failed; 852: -194; 853: +19; 854: -123; 855: -96; 856: +10 | -76.8 [-194, +19] | 2 / 3 / 0 | 8/32 as extreme; means [-88.4, +88.4] | recorded |
| F_CP - F | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| F_CP - F | Agents migrating between regions over the run | p | 851: failed; 852: +2236; 853: -483; 854: -1776; 855: -18; 856: +496 | +91 [-1776, +2236] | 2 / 3 / 0 | 30/32 as extreme; means [-1002, +1002] | recorded |
| F_CP - F | Mean wealth Gini of living civilizations at the end | p | 851: failed; 852: -0.0242; 853: -0.03576; 854: -0.2369; 855: -0.04218; 856: +0.2196 | -0.02388 [-0.2369, +0.2196] | 1 / 4 / 0 | 18/32 as extreme; means [-0.1117, +0.1117] | recorded |
| F_CP - F | Timber stand share of capacity at the end | p | 851: failed; 852: not recorded; 853: not recorded; 854: not recorded; 855: not recorded; 856: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | p |
| --- | --- |
| R | 38.0 [35.1, 40.9] |
| F | 35.4 [28.5, 37.9] |
| R_CP | 37.4 [31.5, 40.7] |
| F_CPc | 38.9 [34.9, 43.3] |
| F_CP | 41.7 [33.2, 48.5] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
