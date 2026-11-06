# CW4: S3 quarantine and public health (C1)

Cohort held. Runs: 48; failed: 0 (missing outcomes: 0); simulation and extraction seconds 551 (0.153 core-hours)

Identity digests: 158fbeb059f9775e99ca37e9bdfdf4f7e480ef852310224d8b719645cef3439d (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [], "packages": {}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| Q0 | t | 761: activated; 762: activated; 763: activated; 764: activated; 765: activated; 766: activated | 6 of 6 |
| Q0 | p | 861: activated; 862: activated; 863: activated; 864: activated; 865: activated; 866: activated | 6 of 6 |
| QC | t | 761: activated; 762: activated; 763: activated; 764: activated; 765: activated; 766: activated | 6 of 6 |
| QC | p | 861: activated; 862: activated; 863: activated; 864: activated; 865: activated; 866: activated | 6 of 6 |
| QR | t | 761: activated; 762: activated; 763: activated; 764: activated; 765: activated; 766: activated | 6 of 6 |
| QR | p | 861: activated; 862: activated; 863: activated; 864: activated; 865: activated; 866: activated | 6 of 6 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw4_world_arrivals: Cross-polity epidemic arrivals over the whole run, world (QR - QC) | t | 761: -9; 762: -2; 763: +0; 764: +12; 765: +5; 766: -1 | +0.8333 [-9, +12] | 2 / 3 / 1 | 52/64 as extreme; means [-4.833, +4.833] |
| cw4_world_arrivals: Cross-polity epidemic arrivals over the whole run, world (QR - QC) | p | 861: +11; 862: -48; 863: -7; 864: +62; 865: -7; 866: -8 | +0.5 [-48, +62] | 2 / 4 / 0 | 64/64 as extreme; means [-23.83, +23.83] |
| cw4_world_death_rate: World epidemic deaths (all) per 1,000 person-turns over the whole run (QR - QC) | t | 761: -0.1464; 762: -0.09526; 763: +0; 764: +0.5426; 765: -1.199; 766: -0.3413 | -0.2066 [-1.199, +0.5426] | 1 / 4 / 1 | 32/64 as extreme; means [-0.3874, +0.3874] |
| cw4_world_death_rate: World epidemic deaths (all) per 1,000 person-turns over the whole run (QR - QC) | p | 861: +0.1463; 862: -3.473; 863: +0.2481; 864: +3.549; 865: -5.609; 866: -3.605 | -1.457 [-5.609, +3.549] | 3 / 3 / 0 | 30/64 as extreme; means [-2.772, +2.772] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw4_world_arrival_rate: Cross-polity arrivals per 1,000 region-turns, world (QR - QC) | t | 761: -5.625; 762: -1.25; 763: +0; 764: +7.5; 765: +3.125; 766: -0.625 | +0.5208 [-5.625, +7.5] | 2 / 3 / 1 | 52/64 as extreme; means [-3.021, +3.021] |
| cw4_world_arrival_rate: Cross-polity arrivals per 1,000 region-turns, world (QR - QC) | p | 861: +1.719; 862: -7.5; 863: -1.094; 864: +9.688; 865: -1.094; 866: -1.25 | +0.07812 [-7.5, +9.688] | 2 / 4 / 0 | 64/64 as extreme; means [-3.724, +3.724] |
| cw4_world_deaths: World epidemic deaths, count (QR - QC) | t | 761: -5; 762: -3; 763: +0; 764: +18; 765: -29; 766: -15 | -5.667 [-29, +18] | 1 / 4 / 1 | 28/64 as extreme; means [-11.67, +11.67] |
| cw4_world_deaths: World epidemic deaths, count (QR - QC) | p | 861: +21; 862: -310; 863: +47; 864: +219; 865: -313; 866: -242 | -96.33 [-313, +219] | 3 / 3 / 0 | 20/64 as extreme; means [-192, +192] |
| cw4_sel_arrivals: Arrivals into closing civs' regions in their windows (QR - QC; conditioned on each arm's own closures: selection) | t | 761: -9; 762: -2; 763: +0; 764: +0; 765: -22; 766: -8 | -6.833 [-22, +0] | 0 / 4 / 2 | 8/64 as extreme; means [-6.833, +6.833] |
| cw4_sel_arrivals: Arrivals into closing civs' regions in their windows (QR - QC; conditioned on each arm's own closures: selection) | p | 861: -18; 862: -112; 863: +7; 864: +3; 865: -37; 866: -62 | -36.5 [-112, +7] | 2 / 4 / 0 | 8/64 as extreme; means [-39.83, +39.83] |
| cw4_sel_deaths: Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing civs in their windows (QR - QC; conditioned on each arm's own closures: selection) | t | 761: -0.4113; 762: -2.913; 763: +0; 764: +0.1565; 765: -1.472; 766: -0.3631 | -0.8339 [-2.913, +0.1565] | 1 / 4 / 1 | 8/64 as extreme; means [-0.886, +0.886] |
| cw4_sel_deaths: Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing civs in their windows (QR - QC; conditioned on each arm's own closures: selection) | p | 861: +0.997; 862: -2.417; 863: -0.7882; 864: +3.124; 865: -3.62; 866: -8.393 | -1.85 [-8.393, +3.124] | 2 / 4 / 0 | 22/64 as extreme; means [-3.223, +3.223] |
| cw4_sel_arrival_rate: Arrivals per 100 window civ-turns (QR - QC; conditioned on each arm's own closures: selection) | t | 761: -1.922; 762: -1.653; 763: +0; 764: +3.108; 765: -3.326; 766: -0.4748 | -0.7114 [-3.326, +3.108] | 1 / 4 / 1 | 28/64 as extreme; means [-1.747, +1.747] |
| cw4_sel_arrival_rate: Arrivals per 100 window civ-turns (QR - QC; conditioned on each arm's own closures: selection) | p | 861: -0.04328; 862: -1.602; 863: -3.98; 864: +1.196; 865: -0.1695; 866: -8.913 | -2.252 [-8.913, +1.196] | 1 / 5 / 0 | 10/64 as extreme; means [-2.651, +2.651] |
| cw4_sel_window: Window civ-turns (QR - QC; conditioned on each arm's own closures: selection) | t | 761: +7; 762: +14; 763: +0; 764: -46; 765: -135; 766: -73 | -38.83 [-135, +14] | 2 / 3 / 1 | 16/64 as extreme; means [-45.83, +45.83] |
| cw4_sel_window: Window civ-turns (QR - QC; conditioned on each arm's own closures: selection) | p | 861: -140; 862: -838; 863: +110; 864: -48; 865: -304; 866: -118 | -223 [-838, +110] | 1 / 5 / 0 | 6/64 as extreme; means [-259.7, +259.7] |
| cw4_cost_world_deaths: World epidemic deaths per 1,000 person-turns (QC - Q0: the cost effect) | t | 761: +0; 762: +0; 763: +1.276; 764: +0.1458; 765: +1.259; 766: +0.2342 | +0.4858 [+0, +1.276] | 4 / 0 / 2 | 8/64 as extreme; means [-0.4858, +0.4858] |
| cw4_cost_world_deaths: World epidemic deaths per 1,000 person-turns (QC - Q0: the cost effect) | p | 861: +1.195; 862: +0.3144; 863: +0.3293; 864: -5.089; 865: -0.8807; 866: -0.6985 | -0.805 [-5.089, +1.195] | 3 / 3 / 0 | 34/64 as extreme; means [-1.418, +1.418] |
| cw4_cost_world_arrivals: Cross-polity arrivals, world (QC - Q0: the cost effect) | t | 761: +0; 762: +0; 763: +7; 764: -1; 765: +17; 766: -8 | +2.5 [-8, +17] | 2 / 2 / 2 | 48/64 as extreme; means [-5.5, +5.5] |
| cw4_cost_world_arrivals: Cross-polity arrivals, world (QC - Q0: the cost effect) | p | 861: +32; 862: -11; 863: +55; 864: -99; 865: -4; 866: +5 | -3.667 [-99, +55] | 3 / 3 / 0 | 54/64 as extreme; means [-34.33, +34.33] |
| cw4_cost_treasury: World treasury at the end (QC - Q0: the cost effect) | t | 761: -69; 762: +0; 763: -501; 764: +386; 765: +789; 766: -117 | +81.33 [-501, +789] | 2 / 3 / 1 | 48/64 as extreme; means [-310.3, +310.3] |
| cw4_cost_treasury: World treasury at the end (QC - Q0: the cost effect) | p | 861: +414; 862: -213; 863: +1310; 864: -2464; 865: +86; 866: -30 | -149.5 [-2464, +1310] | 3 / 3 / 0 | 54/64 as extreme; means [-752.8, +752.8] |
| cw4_legacy_world_arrivals: Cross-polity arrivals, world (QR - QL) | t | 761: +13; 762: +0; 763: +18; 764: +13; 765: +21; 766: +12 | +12.83 [+0, +21] | 5 / 0 / 1 | 4/64 as extreme; means [-12.83, +12.83] |
| cw4_legacy_world_arrivals: Cross-polity arrivals, world (QR - QL) | p | 861: +75; 862: -64; 863: +6; 864: +16; 865: +14; 866: +4 | +8.5 [-64, +75] | 5 / 1 / 0 | 34/64 as extreme; means [-29.83, +29.83] |
| cw4_legacy_world_death_rate: World epidemic deaths per 1,000 person-turns (QR - QL) | t | 761: +0.4255; 762: +0.1549; 763: +2.245; 764: +0.9385; 765: -0.2894; 766: -0.3138 | +0.5269 [-0.3138, +2.245] | 4 / 2 / 0 | 18/64 as extreme; means [-0.7279, +0.7279] |
| cw4_legacy_world_death_rate: World epidemic deaths per 1,000 person-turns (QR - QL) | p | 861: +1.016; 862: -3.77; 863: -0.04049; 864: +3.182; 865: -1.429; 866: -3.174 | -0.7026 [-3.77, +3.182] | 2 / 4 / 0 | 32/64 as extreme; means [-2.102, +2.102] |
| cw4_h_forgone: Route income forgone, both sides (QR alone; structurally 0 in QC) | t | 761: +1220; 762: +264; 763: +0; 764: +68; 765: +300; 766: +1260 | +518.7 [+0, +1260] | 5 / 0 / 1 | n/a (no control) |
| cw4_h_forgone: Route income forgone, both sides (QR alone; structurally 0 in QC) | p | 861: +3636; 862: +704; 863: +924; 864: +1160; 865: +2040; 866: +2148 | +1769 [+704, +3636] | 6 / 0 / 0 | n/a (no control) |
| cw4_h_food: Net food transport into closing civs' regions in their windows (QR - QC) | t | 761: +2.078; 762: -5.852; 763: +0; 764: +6.426; 765: +7.085; 766: -14.08 | -0.7241 [-14.08, +7.085] | 3 / 2 / 1 | 60/64 as extreme; means [-5.921, +5.921] |
| cw4_h_food: Net food transport into closing civs' regions in their windows (QR - QC) | p | 861: +70.64; 862: +94.34; 863: -266.2; 864: +114.5; 865: +109.9; 866: -72.43 | +8.444 [-266.2, +114.5] | 4 / 2 / 0 | 58/64 as extreme; means [-121.3, +121.3] |
| cw4_h_replans: Merchant disruption replans, world (QR - QC) | t | 761: +0; 762: +0; 763: +0; 764: +0; 765: +0; 766: -1 | -0.1667 [-1, +0] | 0 / 1 / 5 | 64/64 as extreme; means [-0.1667, +0.1667] |
| cw4_h_replans: Merchant disruption replans, world (QR - QC) | p | 861: +5; 862: +10; 863: +26; 864: +12; 865: +37; 866: +52 | +23.67 [+5, +52] | 6 / 0 / 0 | 2/64 as extreme; means [-23.67, +23.67] |
| cw4_h_unwinds: Merchant unwinds, world (QR - QC) | t | 761: +0; 762: +5; 763: +0; 764: +18; 765: +20; 766: +62 | +17.5 [+0, +62] | 4 / 0 / 2 | 8/64 as extreme; means [-17.5, +17.5] |
| cw4_h_unwinds: Merchant unwinds, world (QR - QC) | p | 861: +131; 862: +88; 863: +58; 864: +30; 865: +152; 866: +94 | +92.17 [+30, +152] | 6 / 0 / 0 | 2/64 as extreme; means [-92.17, +92.17] |
| cw4_h_treasury: Closing civs' treasury at the end (QR - QC) | t | 761: -913; 762: +732; 763: +0; 764: -53; 765: +832; 766: -715 | -19.5 [-913, +832] | 2 / 3 / 1 | 56/64 as extreme; means [-540.8, +540.8] |
| cw4_h_treasury: Closing civs' treasury at the end (QR - QC) | p | 861: +596; 862: +907; 863: -1045; 864: -2612; 865: +551; 866: +471 | -188.7 [-2612, +907] | 4 / 2 / 0 | 52/64 as extreme; means [-1030, +1030] |
| cw4_h_stability: Closing civs' mean stability in their windows (QR - QC) | t | 761: -2.82; 762: +16.39; 763: +0; 764: -11.14; 765: -3.094; 766: -1.472 | -0.355 [-11.14, +16.39] | 1 / 4 / 1 | 60/64 as extreme; means [-5.818, +5.818] |
| cw4_h_stability: Closing civs' mean stability in their windows (QR - QC) | p | 861: -1.446; 862: -0.6844; 863: +0.3782; 864: -2.758; 865: -0.96; 866: +1.917 | -0.5924 [-2.758, +1.917] | 2 / 4 / 0 | 26/64 as extreme; means [-1.357, +1.357] |
| cw4_h_partner_population: Partner civs' population at the end (QR - QC) | t | 761: -2; 762: +16; 763: +0; 764: -22; 765: +27; 766: -23 | -0.6667 [-23, +27] | 2 / 3 / 1 | 60/64 as extreme; means [-15, +15] |
| cw4_h_partner_population: Partner civs' population at the end (QR - QC) | p | 861: -60; 862: +137; 863: +12; 864: -169; 865: +223; 866: +71 | +35.67 [-169, +223] | 4 / 2 / 0 | 36/64 as extreme; means [-112, +112] |
| cw4_h_partner_treasury: Partner civs' treasury at the end (QR - QC) | t | 761: -913; 762: +739; 763: +0; 764: -53; 765: +832; 766: -715 | -18.33 [-913, +832] | 2 / 3 / 1 | 56/64 as extreme; means [-542, +542] |
| cw4_h_partner_treasury: Partner civs' treasury at the end (QR - QC) | p | 861: +596; 862: +1665; 863: -1042; 864: -2983; 865: +551; 866: +471 | -123.7 [-2983, +1665] | 4 / 2 / 0 | 56/64 as extreme; means [-1218, +1218] |
| cw4_h_leaked: Deliveries still crossing a closed pair (QR alone) | t | 761: +9; 762: +0; 763: +0; 764: +6; 765: +14; 766: +19 | +8 [+0, +19] | 4 / 0 / 2 | n/a (no control) |
| cw4_h_leaked: Deliveries still crossing a closed pair (QR alone) | p | 861: +80; 862: +51; 863: +28; 864: +50; 865: +87; 866: +67 | +60.5 [+28, +87] | 6 / 0 / 0 | n/a (no control) |
| cw4_h_enforcement: Enforcement paid (QR - QC) | t | 761: -52; 762: +26; 763: +0; 764: -6; 765: -130; 766: -230 | -65.33 [-230, +26] | 1 / 4 / 1 | 12/64 as extreme; means [-74, +74] |
| cw4_h_enforcement: Enforcement paid (QR - QC) | p | 861: -178; 862: -1128; 863: +80; 864: -142; 865: -478; 866: -40 | -314.3 [-1128, +80] | 1 / 5 / 0 | 6/64 as extreme; means [-341, +341] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q0 - QL | Population at the end (sum over civilizations) | t | 761: +18; 762: -8; 763: +20; 764: +34; 765: -8; 766: +7 | +10.5 [-8, +34] | 4 / 2 / 0 | 14/64 as extreme; means [-15.83, +15.83] | recorded |
| Q0 - QL | Population at the end (sum over civilizations) | p | 861: +79; 862: +41; 863: +62; 864: -65; 865: -107; 866: +0 | +1.667 [-107, +79] | 3 / 2 / 1 | 64/64 as extreme; means [-59, +59] | recorded |
| Q0 - QL | Treasury at the end (sum over civilizations) | t | 761: +12; 762: +38; 763: +222; 764: +36; 765: -991; 766: +414 | -44.83 [-991, +414] | 5 / 1 / 0 | 64/64 as extreme; means [-285.5, +285.5] | recorded |
| Q0 - QL | Treasury at the end (sum over civilizations) | p | 861: +2252; 862: -38; 863: -946; 864: +2715; 865: -1226; 866: +1453 | +701.7 [-1226, +2715] | 3 / 3 / 0 | 20/64 as extreme; means [-1438, +1438] | recorded |
| Q0 - QL | Food shortfall after relief over the run (food) | t | 761: -112.9; 762: -11.32; 763: -505.7; 764: +1170; 765: +635.8; 766: +452.1 | +271.3 [-505.7, +1170] | 3 / 3 / 0 | 24/64 as extreme; means [-481.3, +481.3] | recorded |
| Q0 - QL | Food shortfall after relief over the run (food) | p | 861: +296.1; 862: -552.1; 863: -627.6; 864: -1966; 865: -322.9; 866: +58.32 | -519 [-1966, +296.1] | 2 / 4 / 0 | 10/64 as extreme; means [-637.1, +637.1] | recorded |
| Q0 - QL | Priced-out person-turns | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| Q0 - QL | Priced-out person-turns | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| Q0 - QL | Priced-out child-turns | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| Q0 - QL | Priced-out child-turns | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| Q0 - QL | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| Q0 - QL | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| Q0 - QL | Deaths by epidemic (the epidemic authority) | t | 761: +21; 762: +9; 763: +31; 764: +21; 765: -3; 766: +3 | +13.67 [-3, +31] | 5 / 1 / 0 | 6/64 as extreme; means [-14.67, +14.67] | recorded |
| Q0 - QL | Deaths by epidemic (the epidemic authority) | p | 861: +10; 862: -100; 863: -129; 864: +393; 865: +390; 866: +70 | +105.7 [-129, +393] | 4 / 2 / 0 | 26/64 as extreme; means [-182, +182] | recorded |
| Q0 - QL | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| Q0 - QL | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| Q0 - QL | Agents migrating between regions over the run | t | 761: +169; 762: -33; 763: -370; 764: +588; 765: +31; 766: +279 | +110.7 [-370, +588] | 4 / 2 / 0 | 30/64 as extreme; means [-245, +245] | recorded |
| Q0 - QL | Agents migrating between regions over the run | p | 861: +186; 862: +456; 863: -700; 864: +267; 865: +623; 866: -591 | +40.17 [-700, +623] | 4 / 2 / 0 | 54/64 as extreme; means [-470.5, +470.5] | recorded |
| Q0 - QL | Mean wealth Gini of living civilizations at the end | t | 761: -0.03043; 762: -0.2423; 763: +0.3591; 764: +0.2704; 765: -0.1852; 766: +0.1014 | +0.0455 [-0.2423, +0.3591] | 3 / 3 / 0 | 42/64 as extreme; means [-0.1981, +0.1981] | recorded |
| Q0 - QL | Mean wealth Gini of living civilizations at the end | p | 861: -9.943e-05; 862: +0.08666; 863: +0.01634; 864: +0.03079; 865: -0.04532; 866: -0.0293 | +0.009844 [-0.04532, +0.08666] | 3 / 3 / 0 | 40/64 as extreme; means [-0.03475, +0.03475] | recorded |
| Q0 - QL | Timber stand share of capacity at the end | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| Q0 - QL | Timber stand share of capacity at the end | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QC - Q0 | Population at the end (sum over civilizations) | t | 761: +0; 762: +0; 763: -6; 764: +18; 765: +21; 766: +6 | +6.5 [-6, +21] | 3 / 1 / 2 | 24/64 as extreme; means [-8.5, +8.5] | recorded |
| QC - Q0 | Population at the end (sum over civilizations) | p | 861: -90; 862: +13; 863: +10; 864: +102; 865: -70; 866: -79 | -19 [-90, +102] | 3 / 3 / 0 | 40/64 as extreme; means [-60.67, +60.67] | recorded |
| QC - Q0 | Treasury at the end (sum over civilizations) | t | 761: -69; 762: +0; 763: -501; 764: +386; 765: +789; 766: -117 | +81.33 [-501, +789] | 2 / 3 / 1 | 48/64 as extreme; means [-310.3, +310.3] | recorded |
| QC - Q0 | Treasury at the end (sum over civilizations) | p | 861: +414; 862: -213; 863: +1310; 864: -2464; 865: +86; 866: -30 | -149.5 [-2464, +1310] | 3 / 3 / 0 | 54/64 as extreme; means [-752.8, +752.8] | recorded |
| QC - Q0 | Food shortfall after relief over the run (food) | t | 761: +0; 762: +0; 763: +267.9; 764: -625.9; 765: -676.8; 766: +211.9 | -137.1 [-676.8, +267.9] | 2 / 2 / 2 | 32/64 as extreme; means [-297.1, +297.1] | recorded |
| QC - Q0 | Food shortfall after relief over the run (food) | p | 861: -46.86; 862: -281.3; 863: +412.5; 864: +2579; 865: +243.4; 866: +496.8 | +567.2 [-281.3, +2579] | 4 / 2 / 0 | 12/64 as extreme; means [-676.6, +676.6] | recorded |
| QC - Q0 | Priced-out person-turns | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QC - Q0 | Priced-out person-turns | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QC - Q0 | Priced-out child-turns | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QC - Q0 | Priced-out child-turns | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QC - Q0 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QC - Q0 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QC - Q0 | Deaths by epidemic (the epidemic authority) | t | 761: +0; 762: +0; 763: +51; 764: -4; 765: +33; 766: +12 | +15.33 [-4, +51] | 3 / 1 / 2 | 16/64 as extreme; means [-16.67, +16.67] | recorded |
| QC - Q0 | Deaths by epidemic (the epidemic authority) | p | 861: +54; 862: +68; 863: +84; 864: -416; 865: -135; 866: -30 | -62.5 [-416, +84] | 3 / 3 / 0 | 38/64 as extreme; means [-131.2, +131.2] | recorded |
| QC - Q0 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QC - Q0 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QC - Q0 | Agents migrating between regions over the run | t | 761: +0; 762: +0; 763: +292; 764: -301; 765: -103; 766: +22 | -15 [-301, +292] | 2 / 2 / 2 | 56/64 as extreme; means [-119.7, +119.7] | recorded |
| QC - Q0 | Agents migrating between regions over the run | p | 861: -934; 862: -623; 863: +372; 864: -563; 865: -1007; 866: +1208 | -257.8 [-1007, +1208] | 2 / 4 / 0 | 34/64 as extreme; means [-784.5, +784.5] | recorded |
| QC - Q0 | Mean wealth Gini of living civilizations at the end | t | 761: +0; 762: +0; 763: -0.0177; 764: -0.1236; 765: +0.1777; 766: +0.003174 | +0.00659 [-0.1236, +0.1777] | 2 / 2 / 2 | 56/64 as extreme; means [-0.0537, +0.0537] | recorded |
| QC - Q0 | Mean wealth Gini of living civilizations at the end | p | 861: -0.0962; 862: -0.1183; 863: -0.1168; 864: +0.1564; 865: -0.1133; 866: +0.1359 | -0.0254 [-0.1183, +0.1564] | 2 / 4 / 0 | 44/64 as extreme; means [-0.1228, +0.1228] | recorded |
| QC - Q0 | Timber stand share of capacity at the end | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QC - Q0 | Timber stand share of capacity at the end | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QR - QC | Population at the end (sum over civilizations) | t | 761: -2; 762: +16; 763: +0; 764: -23; 765: +27; 766: -23 | -0.8333 [-23, +27] | 2 / 3 / 1 | 60/64 as extreme; means [-15.17, +15.17] | recorded |
| QR - QC | Population at the end (sum over civilizations) | p | 861: -60; 862: +137; 863: +11; 864: -167; 865: +221; 866: +71 | +35.5 [-167, +221] | 4 / 2 / 0 | 36/64 as extreme; means [-111.2, +111.2] | recorded |
| QR - QC | Treasury at the end (sum over civilizations) | t | 761: -913; 762: +732; 763: +0; 764: -61; 765: +832; 766: -715 | -20.83 [-913, +832] | 2 / 3 / 1 | 56/64 as extreme; means [-542.2, +542.2] | recorded |
| QR - QC | Treasury at the end (sum over civilizations) | p | 861: +596; 862: +1665; 863: -1045; 864: -2898; 865: +406; 866: +471 | -134.2 [-2898, +1665] | 4 / 2 / 0 | 54/64 as extreme; means [-1180, +1180] | recorded |
| QR - QC | Food shortfall after relief over the run (food) | t | 761: +357; 762: -2.036; 763: +0; 764: +613.5; 765: +691.8; 766: -103.3 | +259.5 [-103.3, +691.8] | 3 / 2 / 1 | 16/64 as extreme; means [-294.6, +294.6] | recorded |
| QR - QC | Food shortfall after relief over the run (food) | p | 861: +11.35; 862: +3328; 863: +416.8; 864: -2693; 865: +2054; 866: +3145 | +1044 [-2693, +3328] | 5 / 1 / 0 | 18/64 as extreme; means [-1941, +1941] | recorded |
| QR - QC | Priced-out person-turns | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Priced-out person-turns | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Priced-out child-turns | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Priced-out child-turns | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QC | Deaths by epidemic (the epidemic authority) | t | 761: -5; 762: -3; 763: +0; 764: +18; 765: -29; 766: -15 | -5.667 [-29, +18] | 1 / 4 / 1 | 28/64 as extreme; means [-11.67, +11.67] | recorded |
| QR - QC | Deaths by epidemic (the epidemic authority) | p | 861: +21; 862: -310; 863: +47; 864: +219; 865: -313; 866: -242 | -96.33 [-313, +219] | 3 / 3 / 0 | 20/64 as extreme; means [-192, +192] | recorded |
| QR - QC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QC | Agents migrating between regions over the run | t | 761: +128; 762: +59; 763: +0; 764: +366; 765: +82; 766: +3 | +106.3 [+0, +366] | 5 / 0 / 1 | 4/64 as extreme; means [-106.3, +106.3] | recorded |
| QR - QC | Agents migrating between regions over the run | p | 861: +841; 862: +4218; 863: +674; 864: -956; 865: +2612; 866: +1233 | +1437 [-956, +4218] | 5 / 1 / 0 | 8/64 as extreme; means [-1756, +1756] | recorded |
| QR - QC | Mean wealth Gini of living civilizations at the end | t | 761: +0.01654; 762: +0.2182; 763: +0; 764: +0.2211; 765: -0.1872; 766: -0.1177 | +0.02516 [-0.1872, +0.2211] | 3 / 2 / 1 | 44/64 as extreme; means [-0.1268, +0.1268] | recorded |
| QR - QC | Mean wealth Gini of living civilizations at the end | p | 861: +0.01044; 862: +0.07814; 863: +0.1142; 864: -0.178; 865: +0.1589; 866: -0.05431 | +0.02158 [-0.178, +0.1589] | 4 / 2 / 0 | 42/64 as extreme; means [-0.09901, +0.09901] | recorded |
| QR - QC | Timber stand share of capacity at the end | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QR - QC | Timber stand share of capacity at the end | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QR - QL | Population at the end (sum over civilizations) | t | 761: +16; 762: +8; 763: +14; 764: +29; 765: +40; 766: -10 | +16.17 [-10, +40] | 5 / 1 / 0 | 6/64 as extreme; means [-19.5, +19.5] | recorded |
| QR - QL | Population at the end (sum over civilizations) | p | 861: -71; 862: +191; 863: +83; 864: -130; 865: +44; 866: -8 | +18.17 [-130, +191] | 3 / 3 / 0 | 48/64 as extreme; means [-87.83, +87.83] | recorded |
| QR - QL | Treasury at the end (sum over civilizations) | t | 761: -970; 762: +770; 763: -279; 764: +361; 765: +630; 766: -418 | +15.67 [-970, +770] | 3 / 3 / 0 | 60/64 as extreme; means [-571.3, +571.3] | recorded |
| QR - QL | Treasury at the end (sum over civilizations) | p | 861: +3262; 862: +1414; 863: -681; 864: -2647; 865: -734; 866: +1894 | +418 [-2647, +3262] | 3 / 3 / 0 | 46/64 as extreme; means [-1772, +1772] | recorded |
| QR - QL | Food shortfall after relief over the run (food) | t | 761: +244.1; 762: -13.35; 763: -237.8; 764: +1157; 765: +650.8; 766: +560.6 | +393.6 [-237.8, +1157] | 4 / 2 / 0 | 10/64 as extreme; means [-477.3, +477.3] | recorded |
| QR - QL | Food shortfall after relief over the run (food) | p | 861: +260.6; 862: +2495; 863: +201.7; 864: -2080; 865: +1975; 866: +3700 | +1092 [-2080, +3700] | 5 / 1 / 0 | 12/64 as extreme; means [-1785, +1785] | recorded |
| QR - QL | Priced-out person-turns | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QL | Priced-out person-turns | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QL | Priced-out child-turns | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QL | Priced-out child-turns | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QL | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QL | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QL | Deaths by epidemic (the epidemic authority) | t | 761: +16; 762: +6; 763: +82; 764: +35; 765: +1; 766: +0 | +23.33 [+0, +82] | 5 / 0 / 1 | 4/64 as extreme; means [-23.33, +23.33] | recorded |
| QR - QL | Deaths by epidemic (the epidemic authority) | p | 861: +85; 862: -342; 863: +2; 864: +196; 865: -58; 866: -202 | -53.17 [-342, +196] | 3 / 3 / 0 | 36/64 as extreme; means [-147.5, +147.5] | recorded |
| QR - QL | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QL | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QL | Agents migrating between regions over the run | t | 761: +297; 762: +26; 763: -78; 764: +653; 765: +10; 766: +304 | +202 [-78, +653] | 5 / 1 / 0 | 10/64 as extreme; means [-228, +228] | recorded |
| QR - QL | Agents migrating between regions over the run | p | 861: +93; 862: +4051; 863: +346; 864: -1252; 865: +2228; 866: +1850 | +1219 [-1252, +4051] | 5 / 1 / 0 | 10/64 as extreme; means [-1637, +1637] | recorded |
| QR - QL | Mean wealth Gini of living civilizations at the end | t | 761: -0.01389; 762: -0.02405; 763: +0.3414; 764: +0.3679; 765: -0.1947; 766: -0.01314 | +0.07725 [-0.1947, +0.3679] | 2 / 4 / 0 | 32/64 as extreme; means [-0.1592, +0.1592] | recorded |
| QR - QL | Mean wealth Gini of living civilizations at the end | p | 861: -0.08587; 862: +0.04647; 863: +0.01378; 864: +0.009187; 865: +0.0002872; 866: +0.05229 | +0.006025 [-0.08587, +0.05229] | 5 / 1 / 0 | 50/64 as extreme; means [-0.03465, +0.03465] | recorded |
| QR - QL | Timber stand share of capacity at the end | t | 761: not recorded; 762: not recorded; 763: not recorded; 764: not recorded; 765: not recorded; 766: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QR - QL | Timber stand share of capacity at the end | p | 861: not recorded; 862: not recorded; 863: not recorded; 864: not recorded; 865: not recorded; 866: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| QL | 5.9 [5.6, 6.2] | 17.5 [13.7, 22.2] |
| Q0 | 6.1 [5.6, 6.5] | 17.4 [13.5, 22.4] |
| QC | 6.1 [5.7, 6.4] | 16.4 [13.4, 20.0] |
| QR | 6.1 [5.5, 6.4] | 16.4 [13.5, 19.2] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
