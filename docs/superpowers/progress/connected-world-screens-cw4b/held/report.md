# CW4b: S3 quarantine closure of migration (C1b)

Cohort held. Runs: 36; failed: 0 (missing outcomes: 0); simulation and extraction seconds 387 (0.107 core-hours)

Identity digests: a4f31b133759bf6c861aa3800ba151c87a68de5cdc85a682898451728ea1f9b5 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [], "packages": {}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| QR | t | 3101: activated; 3102: activated; 3103: activated; 3104: activated; 3105: activated; 3106: activated | 6 of 6 |
| QR | p | 3201: activated; 3202: activated; 3203: activated; 3204: activated; 3205: activated; 3206: activated | 6 of 6 |
| QRM | t | 3101: activated; 3102: activated; 3103: activated; 3104: activated; 3105: activated; 3106: activated | 6 of 6 |
| QRM | p | 3201: activated; 3202: activated; 3203: activated; 3204: activated; 3205: activated; 3206: activated | 6 of 6 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw4b_world_arrivals: Cross-polity epidemic arrivals over the whole run, world (QRM - QC) | t | 3101: -14; 3102: -16; 3103: +2; 3104: +9; 3105: -5; 3106: -12 | -6 [-16, +9] | 2 / 4 / 0 | 12/64 as extreme; means [-9.667, +9.667] |
| cw4b_world_arrivals: Cross-polity epidemic arrivals over the whole run, world (QRM - QC) | p | 3201: -49; 3202: -99; 3203: -22; 3204: -9; 3205: +34; 3206: -34 | -29.83 [-99, +34] | 1 / 5 / 0 | 12/64 as extreme; means [-41.17, +41.17] |
| cw4b_world_death_rate: World epidemic deaths (all) per 1,000 person-turns over the whole run (QRM - QC) | t | 3101: -0.8271; 3102: -2.457; 3103: +0.7506; 3104: -2.792; 3105: -0.175; 3106: -1.266 | -1.128 [-2.792, +0.7506] | 1 / 5 / 0 | 6/64 as extreme; means [-1.378, +1.378] |
| cw4b_world_death_rate: World epidemic deaths (all) per 1,000 person-turns over the whole run (QRM - QC) | p | 3201: -0.1867; 3202: -2.242; 3203: -0.6427; 3204: -0.7236; 3205: +3.87; 3206: -1.748 | -0.2787 [-2.242, +3.87] | 1 / 5 / 0 | 50/64 as extreme; means [-1.569, +1.569] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw4b_mig_world_arrivals: Cross-polity arrivals, world (QRM - QR: the migration channel's increment) | t | 3101: -7; 3102: -15; 3103: -6; 3104: -2; 3105: -6; 3106: -16 | -8.667 [-16, -2] | 0 / 6 / 0 | 2/64 as extreme; means [-8.667, +8.667] |
| cw4b_mig_world_arrivals: Cross-polity arrivals, world (QRM - QR: the migration channel's increment) | p | 3201: -24; 3202: -57; 3203: +14; 3204: -35; 3205: +27; 3206: -20 | -15.83 [-57, +27] | 2 / 4 / 0 | 18/64 as extreme; means [-29.5, +29.5] |
| cw4b_mig_world_death_rate: World epidemic deaths per 1,000 person-turns (QRM - QR: the migration channel's increment) | t | 3101: -0.4472; 3102: -0.6435; 3103: -0.4283; 3104: -0.7897; 3105: -0.3487; 3106: -1.535 | -0.6987 [-1.535, -0.3487] | 0 / 6 / 0 | 2/64 as extreme; means [-0.6987, +0.6987] |
| cw4b_mig_world_death_rate: World epidemic deaths per 1,000 person-turns (QRM - QR: the migration channel's increment) | p | 3201: -0.5225; 3202: -1.883; 3203: +0.6912; 3204: -0.3315; 3205: -0.4938; 3206: -1.239 | -0.6297 [-1.883, +0.6912] | 1 / 5 / 0 | 10/64 as extreme; means [-0.8601, +0.8601] |
| cw4b_trade_world_arrivals: Cross-polity arrivals, world (QR - QC: trade closure alone) | t | 3101: -7; 3102: -1; 3103: +8; 3104: +11; 3105: +1; 3106: +4 | +2.667 [-7, +11] | 4 / 2 / 0 | 24/64 as extreme; means [-5.333, +5.333] |
| cw4b_trade_world_arrivals: Cross-polity arrivals, world (QR - QC: trade closure alone) | p | 3201: -25; 3202: -42; 3203: -36; 3204: +26; 3205: +7; 3206: -14 | -14 [-42, +26] | 2 / 4 / 0 | 16/64 as extreme; means [-25, +25] |
| cw4b_trade_world_death_rate: World epidemic deaths per 1,000 person-turns (QR - QC: trade closure alone) | t | 3101: -0.3799; 3102: -1.813; 3103: +1.179; 3104: -2.002; 3105: +0.1737; 3106: +0.269 | -0.429 [-2.002, +1.179] | 3 / 3 / 0 | 26/64 as extreme; means [-0.9695, +0.9695] |
| cw4b_trade_world_death_rate: World epidemic deaths per 1,000 person-turns (QR - QC: trade closure alone) | p | 3201: +0.3358; 3202: -0.359; 3203: -1.334; 3204: -0.392; 3205: +4.364; 3206: -0.5088 | +0.351 [-1.334, +4.364] | 2 / 4 / 0 | 62/64 as extreme; means [-1.216, +1.216] |
| cw4b_world_arrival_rate: Cross-polity arrivals per 1,000 region-turns, world (QRM - QC) | t | 3101: -8.75; 3102: -10; 3103: +1.25; 3104: +5.625; 3105: -3.125; 3106: -7.5 | -3.75 [-10, +5.625] | 2 / 4 / 0 | 12/64 as extreme; means [-6.042, +6.042] |
| cw4b_world_arrival_rate: Cross-polity arrivals per 1,000 region-turns, world (QRM - QC) | p | 3201: -7.656; 3202: -15.47; 3203: -3.438; 3204: -1.406; 3205: +5.312; 3206: -5.312 | -4.661 [-15.47, +5.312] | 1 / 5 / 0 | 12/64 as extreme; means [-6.432, +6.432] |
| cw4b_world_deaths: World epidemic deaths, count (QRM - QC) | t | 3101: -24; 3102: -121; 3103: +18; 3104: -28; 3105: -1; 3106: -19 | -29.17 [-121, +18] | 1 / 5 / 0 | 6/64 as extreme; means [-35.17, +35.17] |
| cw4b_world_deaths: World epidemic deaths, count (QRM - QC) | p | 3201: -21; 3202: -72; 3203: -60; 3204: -6; 3205: +245; 3206: -223 | -22.83 [-223, +245] | 1 / 5 / 0 | 40/64 as extreme; means [-104.5, +104.5] |
| cw4b_sel_arrivals: Arrivals into closing civs' regions in their windows (QRM - QC; conditioned on each arm's own closures: selection) | t | 3101: -14; 3102: -15; 3103: +1; 3104: +9; 3105: -2; 3106: -11 | -5.333 [-15, +9] | 2 / 4 / 0 | 12/64 as extreme; means [-8.667, +8.667] |
| cw4b_sel_arrivals: Arrivals into closing civs' regions in their windows (QRM - QC; conditioned on each arm's own closures: selection) | p | 3201: -6; 3202: -5; 3203: +9; 3204: -28; 3205: +14; 3206: -91 | -17.83 [-91, +14] | 2 / 4 / 0 | 24/64 as extreme; means [-25.5, +25.5] |
| cw4b_sel_deaths: Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing civs in their windows (QRM - QC; conditioned on each arm's own closures: selection) | t | 3101: -1.512; 3102: -1.444; 3103: -0.05595; 3104: -4.732; 3105: +3.681; 3106: -1.225 | -0.8813 [-4.732, +3.681] | 1 / 5 / 0 | 30/64 as extreme; means [-2.108, +2.108] |
| cw4b_sel_deaths: Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing civs in their windows (QRM - QC; conditioned on each arm's own closures: selection) | p | 3201: -1.461; 3202: -3.008; 3203: -1.029; 3204: -1.046; 3205: -0.9663; 3206: -1.993 | -1.584 [-3.008, -0.9663] | 0 / 6 / 0 | 2/64 as extreme; means [-1.584, +1.584] |
| cw4b_sel_window: Window civ-turns (QRM - QC; conditioned on each arm's own closures: selection) | t | 3101: -78; 3102: -309; 3103: -39; 3104: +302; 3105: -6; 3106: +13 | -19.5 [-309, +302] | 2 / 4 / 0 | 42/64 as extreme; means [-124.5, +124.5] |
| cw4b_sel_window: Window civ-turns (QRM - QC; conditioned on each arm's own closures: selection) | p | 3201: +211; 3202: +287; 3203: +409; 3204: -87; 3205: +327; 3206: -152 | +165.8 [-152, +409] | 4 / 2 / 0 | 10/64 as extreme; means [-245.5, +245.5] |
| cw4b_refusals: Migrants refused, person-ticks (QRM alone) | t | 3101: +502; 3102: +1074; 3103: +330; 3104: +825; 3105: +100; 3106: +2348 | +863.2 [+100, +2348] | 6 / 0 / 0 | n/a (no control) |
| cw4b_refusals: Migrants refused, person-ticks (QRM alone) | p | 3201: +830; 3202: +4311; 3203: +4129; 3204: +2765; 3205: +1118; 3206: +3906 | +2843 [+830, +4311] | 6 / 0 / 0 | n/a (no control) |
| cw4b_refusal_spells: Refusal spells: consecutive refusals of one agent count once (QRM alone) | t | 3101: +439; 3102: +856; 3103: +242; 3104: +688; 3105: +99; 3106: +1805 | +688.2 [+99, +1805] | 6 / 0 / 0 | n/a (no control) |
| cw4b_refusal_spells: Refusal spells: consecutive refusals of one agent count once (QRM alone) | p | 3201: +745; 3202: +3581; 3203: +3459; 3204: +2402; 3205: +981; 3206: +3255 | +2404 [+745, +3581] | 6 / 0 / 0 | n/a (no control) |
| cw4b_refused_flight: Refusals of migrants fleeing war, famine or persecution, hunger-driven moves excluded (QRM alone) | t | 3101: +412; 3102: +504; 3103: +179; 3104: +446; 3105: +76; 3106: +1077 | +449 [+76, +1077] | 6 / 0 / 0 | n/a (no control) |
| cw4b_refused_flight: Refusals of migrants fleeing war, famine or persecution, hunger-driven moves excluded (QRM alone) | p | 3201: +691; 3202: +2981; 3203: +2719; 3204: +1559; 3205: +613; 3206: +2563 | +1854 [+613, +2981] | 6 / 0 / 0 | n/a (no control) |
| cw4b_refused_hunger: Refusals of hunger-driven migrants: food opportunity, material need (QRM alone) | t | 3101: +74; 3102: +260; 3103: +129; 3104: +231; 3105: +21; 3106: +1147 | +310.3 [+21, +1147] | 6 / 0 / 0 | n/a (no control) |
| cw4b_refused_hunger: Refusals of hunger-driven migrants: food opportunity, material need (QRM alone) | p | 3201: +79; 3202: +595; 3203: +561; 3204: +492; 3205: +128; 3206: +673 | +421.3 [+79, +673] | 6 / 0 / 0 | n/a (no control) |
| cw4b_h_food_shortfall: Food shortfall after relief over the run (QRM - QC) | t | 3101: +718.4; 3102: +1355; 3103: +232.9; 3104: +467; 3105: -915.6; 3106: +1892 | +624.9 [-915.6, +1892] | 5 / 1 / 0 | 12/64 as extreme; means [-930.1, +930.1] |
| cw4b_h_food_shortfall: Food shortfall after relief over the run (QRM - QC) | p | 3201: +16.79; 3202: +2297; 3203: +1450; 3204: +2712; 3205: -2314; 3206: +1321 | +913.9 [-2314, +2712] | 5 / 1 / 0 | 18/64 as extreme; means [-1685, +1685] |
| cw4b_h_out_migration: Agents moving between regions over the run (QRM - QC) | t | 3101: -113; 3102: -10; 3103: +79; 3104: +741; 3105: -225; 3106: -574 | -17 [-574, +741] | 2 / 4 / 0 | 58/64 as extreme; means [-290.3, +290.3] |
| cw4b_h_out_migration: Agents moving between regions over the run (QRM - QC) | p | 3201: -650; 3202: +340; 3203: -1669; 3204: -463; 3205: -2822; 3206: -1491 | -1126 [-2822, +340] | 1 / 5 / 0 | 4/64 as extreme; means [-1239, +1239] |
| cw4b_h_population: Population at the end (QRM - QC) | t | 3101: +1; 3102: -53; 3103: +2; 3104: +154; 3105: +78; 3106: +23 | +34.17 [-53, +154] | 5 / 1 / 0 | 18/64 as extreme; means [-51.83, +51.83] |
| cw4b_h_population: Population at the end (QRM - QC) | p | 3201: +23; 3202: +151; 3203: -21; 3204: +62; 3205: -244; 3206: +119 | +15 [-244, +151] | 4 / 2 / 0 | 52/64 as extreme; means [-103.3, +103.3] |
| cw4b_h_treasury: Treasury at the end (QRM - QC) | t | 3101: +233; 3102: -2002; 3103: -429; 3104: +557; 3105: +385; 3106: -619 | -312.5 [-2002, +557] | 3 / 3 / 0 | 34/64 as extreme; means [-704.2, +704.2] |
| cw4b_h_treasury: Treasury at the end (QRM - QC) | p | 3201: +445; 3202: -128; 3203: +2737; 3204: +1484; 3205: +1134; 3206: +3054 | +1454 [-128, +3054] | 5 / 1 / 0 | 4/64 as extreme; means [-1497, +1497] |
| cw4b_h_partner_population: Partner civs' population at the end (QRM - QC) | t | 3101: +1; 3102: -53; 3103: +2; 3104: +154; 3105: +78; 3106: +23 | +34.17 [-53, +154] | 5 / 1 / 0 | 18/64 as extreme; means [-51.83, +51.83] |
| cw4b_h_partner_population: Partner civs' population at the end (QRM - QC) | p | 3201: +23; 3202: +151; 3203: -21; 3204: +62; 3205: -243; 3206: +119 | +15.17 [-243, +151] | 4 / 2 / 0 | 52/64 as extreme; means [-103.2, +103.2] |
| cw4b_h_partner_treasury: Partner civs' treasury at the end (QRM - QC) | t | 3101: +233; 3102: -2002; 3103: -429; 3104: +557; 3105: +385; 3106: -619 | -312.5 [-2002, +557] | 3 / 3 / 0 | 34/64 as extreme; means [-704.2, +704.2] |
| cw4b_h_partner_treasury: Partner civs' treasury at the end (QRM - QC) | p | 3201: +445; 3202: -128; 3203: +2737; 3204: +1484; 3205: +1136; 3206: +3054 | +1455 [-128, +3054] | 5 / 1 / 0 | 4/64 as extreme; means [-1497, +1497] |
| cw4b_h_forgone: Route income forgone, both sides (QRM alone; structurally 0 in QC) | t | 3101: +356; 3102: +252; 3103: +492; 3104: +800; 3105: +160; 3106: +196 | +376 [+160, +800] | 6 / 0 / 0 | n/a (no control) |
| cw4b_h_forgone: Route income forgone, both sides (QRM alone; structurally 0 in QC) | p | 3201: +1520; 3202: +4628; 3203: +3472; 3204: +3108; 3205: +1420; 3206: +3744 | +2982 [+1420, +4628] | 6 / 0 / 0 | n/a (no control) |
| cw4b_h_forgone_trade: Route income forgone, both sides (QR alone) | t | 3101: +700; 3102: +168; 3103: +268; 3104: +484; 3105: +356; 3106: +356 | +388.7 [+168, +700] | 6 / 0 / 0 | n/a (no control) |
| cw4b_h_forgone_trade: Route income forgone, both sides (QR alone) | p | 3201: +816; 3202: +2468; 3203: +1444; 3204: +3040; 3205: +700; 3206: +3412 | +1980 [+700, +3412] | 6 / 0 / 0 | n/a (no control) |
| cw4b_h_unwinds: Merchant unwinds, world (QRM - QC) | t | 3101: +60; 3102: +5; 3103: +21; 3104: +51; 3105: +1; 3106: +2 | +23.33 [+1, +60] | 6 / 0 / 0 | 2/64 as extreme; means [-23.33, +23.33] |
| cw4b_h_unwinds: Merchant unwinds, world (QRM - QC) | p | 3201: +34; 3202: +246; 3203: +221; 3204: +277; 3205: +142; 3206: +317 | +206.2 [+34, +317] | 6 / 0 / 0 | 2/64 as extreme; means [-206.2, +206.2] |
| cw4b_h_leaked: Deliveries still crossing a closed pair (QRM alone) | t | 3101: +17; 3102: +0; 3103: +0; 3104: +13; 3105: +0; 3106: +0 | +5 [+0, +17] | 2 / 0 / 4 | n/a (no control) |
| cw4b_h_leaked: Deliveries still crossing a closed pair (QRM alone) | p | 3201: +36; 3202: +153; 3203: +128; 3204: +175; 3205: +58; 3206: +143 | +115.5 [+36, +175] | 6 / 0 / 0 | n/a (no control) |
| cw4b_h_enforcement: Enforcement paid (QRM - QC) | t | 3101: -160; 3102: -412; 3103: -82; 3104: +496; 3105: +20; 3106: +110 | -4.667 [-412, +496] | 3 / 3 / 0 | 64/64 as extreme; means [-213.3, +213.3] |
| cw4b_h_enforcement: Enforcement paid (QRM - QC) | p | 3201: +306; 3202: +794; 3203: +864; 3204: -136; 3205: +484; 3206: -164 | +358 [-164, +864] | 4 / 2 / 0 | 8/64 as extreme; means [-458, +458] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QR - QC | Population at the end (sum over civilizations) | t | 3101: +18; 3102: -58; 3103: -14; 3104: +58; 3105: +12; 3106: +18 | +5.667 [-58, +58] | 4 / 2 / 0 | 44/64 as extreme; means [-29.67, +29.67] | recorded |
| QR - QC | Population at the end (sum over civilizations) | p | 3201: -15; 3202: +5; 3203: -12; 3204: -17; 3205: -304; 3206: +21 | -53.67 [-304, +21] | 2 / 4 / 0 | 20/64 as extreme; means [-62.33, +62.33] | recorded |
| QR - QC | Treasury at the end (sum over civilizations) | t | 3101: -494; 3102: -1427; 3103: -1110; 3104: +331; 3105: -388; 3106: -147 | -539.2 [-1427, +331] | 1 / 5 / 0 | 6/64 as extreme; means [-649.5, +649.5] | recorded |
| QR - QC | Treasury at the end (sum over civilizations) | p | 3201: -572; 3202: +173; 3203: +1007; 3204: +1914; 3205: +543; 3206: +1106 | +695.2 [-572, +1914] | 5 / 1 / 0 | 8/64 as extreme; means [-885.8, +885.8] | recorded |
| QR - QC | Food shortfall after relief over the run (food) | t | 3101: +709.5; 3102: +1267; 3103: +211.7; 3104: +1130; 3105: +91.28; 3106: -46.16 | +560.6 [-46.16, +1267] | 5 / 1 / 0 | 4/64 as extreme; means [-576, +576] | recorded |
| QR - QC | Food shortfall after relief over the run (food) | p | 3201: +1078; 3202: +594.1; 3203: +1562; 3204: +382.7; 3205: -2829; 3206: +518.3 | +217.7 [-2829, +1562] | 5 / 1 / 0 | 50/64 as extreme; means [-1161, +1161] | recorded |
| QR - QC | Priced-out person-turns | t | 3101: not recorded; 3102: not recorded; 3103: not recorded; 3104: not recorded; 3105: not recorded; 3106: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Priced-out person-turns | p | 3201: not recorded; 3202: not recorded; 3203: not recorded; 3204: not recorded; 3205: not recorded; 3206: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Priced-out child-turns | t | 3101: not recorded; 3102: not recorded; 3103: not recorded; 3104: not recorded; 3105: not recorded; 3106: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Priced-out child-turns | p | 3201: not recorded; 3202: not recorded; 3203: not recorded; 3204: not recorded; 3205: not recorded; 3206: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QR - QC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QR - QC | Deaths by epidemic (the epidemic authority) | t | 3101: -4; 3102: -92; 3103: +32; 3104: +1; 3105: +8; 3106: +13 | -7 [-92, +32] | 4 / 2 / 0 | 60/64 as extreme; means [-25, +25] | recorded |
| QR - QC | Deaths by epidemic (the epidemic authority) | p | 3201: +49; 3202: +13; 3203: -152; 3204: -29; 3205: +267; 3206: -153 | -0.8333 [-153, +267] | 3 / 3 / 0 | 64/64 as extreme; means [-110.5, +110.5] | recorded |
| QR - QC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QR - QC | Agents migrating between regions over the run | t | 3101: +516; 3102: +610; 3103: +215; 3104: +1039; 3105: -88; 3106: +293 | +430.8 [-88, +1039] | 5 / 1 / 0 | 4/64 as extreme; means [-460.2, +460.2] | recorded |
| QR - QC | Agents migrating between regions over the run | p | 3201: +429; 3202: +0; 3203: +653; 3204: -78; 3205: -2199; 3206: -1049 | -374 [-2199, +653] | 2 / 3 / 1 | 32/64 as extreme; means [-734.7, +734.7] | recorded |
| QR - QC | Mean wealth Gini of living civilizations at the end | t | 3101: +0.09093; 3102: -0.02329; 3103: -0.04644; 3104: +0.2856; 3105: +0.02604; 3106: +0.173 | +0.0843 [-0.04644, +0.2856] | 4 / 2 / 0 | 12/64 as extreme; means [-0.1075, +0.1075] | recorded |
| QR - QC | Mean wealth Gini of living civilizations at the end | p | 3201: +0.1417; 3202: -0.1086; 3203: -0.02871; 3204: -0.03651; 3205: +0.06993; 3206: +0.03285 | +0.01178 [-0.1086, +0.1417] | 3 / 3 / 0 | 48/64 as extreme; means [-0.06971, +0.06971] | recorded |
| QR - QC | Timber stand share of capacity at the end | t | 3101: not recorded; 3102: not recorded; 3103: not recorded; 3104: not recorded; 3105: not recorded; 3106: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QR - QC | Timber stand share of capacity at the end | p | 3201: not recorded; 3202: not recorded; 3203: not recorded; 3204: not recorded; 3205: not recorded; 3206: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QRM - QR | Population at the end (sum over civilizations) | t | 3101: -17; 3102: +5; 3103: +16; 3104: +96; 3105: +66; 3106: +5 | +28.5 [-17, +96] | 5 / 1 / 0 | 12/64 as extreme; means [-34.17, +34.17] | recorded |
| QRM - QR | Population at the end (sum over civilizations) | p | 3201: +38; 3202: +146; 3203: -9; 3204: +79; 3205: +60; 3206: +98 | +68.67 [-9, +146] | 5 / 1 / 0 | 4/64 as extreme; means [-71.67, +71.67] | recorded |
| QRM - QR | Treasury at the end (sum over civilizations) | t | 3101: +727; 3102: -575; 3103: +681; 3104: +226; 3105: +773; 3106: -472 | +226.7 [-575, +773] | 4 / 2 / 0 | 26/64 as extreme; means [-575.7, +575.7] | recorded |
| QRM - QR | Treasury at the end (sum over civilizations) | p | 3201: +1017; 3202: -301; 3203: +1730; 3204: -430; 3205: +591; 3206: +1948 | +759.2 [-430, +1948] | 4 / 2 / 0 | 10/64 as extreme; means [-1003, +1003] | recorded |
| QRM - QR | Food shortfall after relief over the run (food) | t | 3101: +8.904; 3102: +87.05; 3103: +21.24; 3104: -662.6; 3105: -1007; 3106: +1938 | +64.34 [-1007, +1938] | 4 / 2 / 0 | 50/64 as extreme; means [-620.9, +620.9] | recorded |
| QRM - QR | Food shortfall after relief over the run (food) | p | 3201: -1062; 3202: +1703; 3203: -111.8; 3204: +2329; 3205: +515.8; 3206: +803 | +696.2 [-1062, +2329] | 4 / 2 / 0 | 16/64 as extreme; means [-1087, +1087] | recorded |
| QRM - QR | Priced-out person-turns | t | 3101: not recorded; 3102: not recorded; 3103: not recorded; 3104: not recorded; 3105: not recorded; 3106: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QR | Priced-out person-turns | p | 3201: not recorded; 3202: not recorded; 3203: not recorded; 3204: not recorded; 3205: not recorded; 3206: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QR | Priced-out child-turns | t | 3101: not recorded; 3102: not recorded; 3103: not recorded; 3104: not recorded; 3105: not recorded; 3106: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QR | Priced-out child-turns | p | 3201: not recorded; 3202: not recorded; 3203: not recorded; 3204: not recorded; 3205: not recorded; 3206: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QR | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QRM - QR | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QRM - QR | Deaths by epidemic (the epidemic authority) | t | 3101: -20; 3102: -29; 3103: -14; 3104: -29; 3105: -9; 3106: -32 | -22.17 [-32, -9] | 0 / 6 / 0 | 2/64 as extreme; means [-22.17, +22.17] | recorded |
| QRM - QR | Deaths by epidemic (the epidemic authority) | p | 3201: -70; 3202: -85; 3203: +92; 3204: +23; 3205: -22; 3206: -70 | -22 [-85, +92] | 2 / 4 / 0 | 36/64 as extreme; means [-60.33, +60.33] | recorded |
| QRM - QR | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QRM - QR | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QRM - QR | Agents migrating between regions over the run | t | 3101: -629; 3102: -620; 3103: -136; 3104: -298; 3105: -137; 3106: -867 | -447.8 [-867, -136] | 0 / 6 / 0 | 2/64 as extreme; means [-447.8, +447.8] | recorded |
| QRM - QR | Agents migrating between regions over the run | p | 3201: -1079; 3202: +340; 3203: -2322; 3204: -385; 3205: -623; 3206: -442 | -751.8 [-2322, +340] | 1 / 5 / 0 | 4/64 as extreme; means [-865.2, +865.2] | recorded |
| QRM - QR | Mean wealth Gini of living civilizations at the end | t | 3101: -0.02977; 3102: -0.05719; 3103: +0.02018; 3104: +0.0374; 3105: +0.03691; 3106: -0.0284 | -0.003478 [-0.05719, +0.0374] | 3 / 3 / 0 | 54/64 as extreme; means [-0.03497, +0.03497] | recorded |
| QRM - QR | Mean wealth Gini of living civilizations at the end | p | 3201: +0.01099; 3202: +0.09717; 3203: -0.02996; 3204: +0.04927; 3205: +0.05711; 3206: -0.01067 | +0.02899 [-0.02996, +0.09717] | 4 / 2 / 0 | 12/64 as extreme; means [-0.04253, +0.04253] | recorded |
| QRM - QR | Timber stand share of capacity at the end | t | 3101: not recorded; 3102: not recorded; 3103: not recorded; 3104: not recorded; 3105: not recorded; 3106: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QRM - QR | Timber stand share of capacity at the end | p | 3201: not recorded; 3202: not recorded; 3203: not recorded; 3204: not recorded; 3205: not recorded; 3206: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QRM - QC | Population at the end (sum over civilizations) | t | 3101: +1; 3102: -53; 3103: +2; 3104: +154; 3105: +78; 3106: +23 | +34.17 [-53, +154] | 5 / 1 / 0 | 18/64 as extreme; means [-51.83, +51.83] | recorded |
| QRM - QC | Population at the end (sum over civilizations) | p | 3201: +23; 3202: +151; 3203: -21; 3204: +62; 3205: -244; 3206: +119 | +15 [-244, +151] | 4 / 2 / 0 | 52/64 as extreme; means [-103.3, +103.3] | recorded |
| QRM - QC | Treasury at the end (sum over civilizations) | t | 3101: +233; 3102: -2002; 3103: -429; 3104: +557; 3105: +385; 3106: -619 | -312.5 [-2002, +557] | 3 / 3 / 0 | 34/64 as extreme; means [-704.2, +704.2] | recorded |
| QRM - QC | Treasury at the end (sum over civilizations) | p | 3201: +445; 3202: -128; 3203: +2737; 3204: +1484; 3205: +1134; 3206: +3054 | +1454 [-128, +3054] | 5 / 1 / 0 | 4/64 as extreme; means [-1497, +1497] | recorded |
| QRM - QC | Food shortfall after relief over the run (food) | t | 3101: +718.4; 3102: +1355; 3103: +232.9; 3104: +467; 3105: -915.6; 3106: +1892 | +624.9 [-915.6, +1892] | 5 / 1 / 0 | 12/64 as extreme; means [-930.1, +930.1] | recorded |
| QRM - QC | Food shortfall after relief over the run (food) | p | 3201: +16.79; 3202: +2297; 3203: +1450; 3204: +2712; 3205: -2314; 3206: +1321 | +913.9 [-2314, +2712] | 5 / 1 / 0 | 18/64 as extreme; means [-1685, +1685] | recorded |
| QRM - QC | Priced-out person-turns | t | 3101: not recorded; 3102: not recorded; 3103: not recorded; 3104: not recorded; 3105: not recorded; 3106: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QC | Priced-out person-turns | p | 3201: not recorded; 3202: not recorded; 3203: not recorded; 3204: not recorded; 3205: not recorded; 3206: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QC | Priced-out child-turns | t | 3101: not recorded; 3102: not recorded; 3103: not recorded; 3104: not recorded; 3105: not recorded; 3106: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QC | Priced-out child-turns | p | 3201: not recorded; 3202: not recorded; 3203: not recorded; 3204: not recorded; 3205: not recorded; 3206: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| QRM - QC | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QRM - QC | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| QRM - QC | Deaths by epidemic (the epidemic authority) | t | 3101: -24; 3102: -121; 3103: +18; 3104: -28; 3105: -1; 3106: -19 | -29.17 [-121, +18] | 1 / 5 / 0 | 6/64 as extreme; means [-35.17, +35.17] | recorded |
| QRM - QC | Deaths by epidemic (the epidemic authority) | p | 3201: -21; 3202: -72; 3203: -60; 3204: -6; 3205: +245; 3206: -223 | -22.83 [-223, +245] | 1 / 5 / 0 | 40/64 as extreme; means [-104.5, +104.5] | recorded |
| QRM - QC | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QRM - QC | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| QRM - QC | Agents migrating between regions over the run | t | 3101: -113; 3102: -10; 3103: +79; 3104: +741; 3105: -225; 3106: -574 | -17 [-574, +741] | 2 / 4 / 0 | 58/64 as extreme; means [-290.3, +290.3] | recorded |
| QRM - QC | Agents migrating between regions over the run | p | 3201: -650; 3202: +340; 3203: -1669; 3204: -463; 3205: -2822; 3206: -1491 | -1126 [-2822, +340] | 1 / 5 / 0 | 4/64 as extreme; means [-1239, +1239] | recorded |
| QRM - QC | Mean wealth Gini of living civilizations at the end | t | 3101: +0.06116; 3102: -0.08048; 3103: -0.02626; 3104: +0.323; 3105: +0.06295; 3106: +0.1446 | +0.08083 [-0.08048, +0.323] | 4 / 2 / 0 | 16/64 as extreme; means [-0.1164, +0.1164] | recorded |
| QRM - QC | Mean wealth Gini of living civilizations at the end | p | 3201: +0.1526; 3202: -0.01139; 3203: -0.05867; 3204: +0.01277; 3205: +0.127; 3206: +0.02219 | +0.04076 [-0.05867, +0.1526] | 4 / 2 / 0 | 20/64 as extreme; means [-0.06412, +0.06412] | recorded |
| QRM - QC | Timber stand share of capacity at the end | t | 3101: not recorded; 3102: not recorded; 3103: not recorded; 3104: not recorded; 3105: not recorded; 3106: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| QRM - QC | Timber stand share of capacity at the end | p | 3201: not recorded; 3202: not recorded; 3203: not recorded; 3204: not recorded; 3205: not recorded; 3206: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| QC | 6.0 [5.6, 6.6] | 15.5 [14.3, 16.4] |
| QR | 6.1 [5.7, 6.7] | 15.4 [14.4, 16.3] |
| QRM | 6.2 [5.6, 7.1] | 15.4 [14.3, 16.6] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
