# CW2: S2 workshop economics and the owned-output rule (A3-1, A3-2)

Cohort held. Runs: 60; failed: 0 (missing outcomes: 0); simulation and extraction seconds 951 (0.264 core-hours)

Identity digests: 9798cd8836306582079a838408efa0560b0c3c926ec4efc6ea31b607894f63cf (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"wealth_accounting": [1], "workshop_economics": [1], "workshop_payroll": [1], "workshops": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"wealth_accounting": [1], "workshop_payroll": [1], "workshops": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| E1 | t | 741: activated; 742: activated; 743: activated; 744: activated; 745: activated; 746: activated | 6 of 6 |
| E1 | p | 841: activated; 842: activated; 843: activated; 844: activated; 845: activated; 846: activated | 6 of 6 |
| E2 | t | 741: activated; 742: activated; 743: activated; 744: activated; 745: activated; 746: activated | 6 of 6 |
| E2 | p | 841: activated; 842: activated; 843: activated; 844: activated; 845: activated; 846: activated | 6 of 6 |
| E2f | t | 741: activated; 742: activated; 743: activated; 744: activated; 745: activated; 746: activated | 6 of 6 |
| E2f | p | 841: activated; 842: activated; 843: activated; 844: activated; 845: activated; 846: activated | 6 of 6 |
| E2a | t | 741: activated; 742: activated; 743: activated; 744: activated; 745: activated; 746: activated | 6 of 6 |
| E2a | p | 841: activated; 842: activated; 843: activated; 844: activated; 845: activated; 846: activated | 6 of 6 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw2_active_share: Share of firm-turns since opening in which the firm produced or sold (idle and closed turns count against it) (E2 - E1) | t | 741: +0.02955; 742: -0.03591; 743: +0.0382; 744: -0.4952; 745: +0.08501; 746: -0.05769 | -0.07268 [-0.4952, +0.08501] | 3 / 3 / 0 | 44/64 as extreme; means [-0.1236, +0.1236] |
| cw2_active_share: Share of firm-turns since opening in which the firm produced or sold (idle and closed turns count against it) (E2 - E1) | p | 841: -0.06921; 842: +0.08586; 843: -0.1079; 844: -0.135; 845: +0.04136; 846: -0.278 | -0.07715 [-0.278, +0.08586] | 2 / 4 / 0 | 14/64 as extreme; means [-0.1196, +0.1196] |
| cw2_wages: Workshop wages credited to households over the run, units (A1 ledger) (E2 - P) | t | 741: +8.4; 742: -41.38; 743: -11.6; 744: +6.6; 745: +1.528; 746: +17.9 | -3.091 [-41.38, +17.9] | 4 / 2 / 0 | 52/64 as extreme; means [-14.57, +14.57] |
| cw2_wages: Workshop wages credited to households over the run, units (A1 ledger) (E2 - P) | p | 841: +37.95; 842: -2.1; 843: -18.3; 844: +49.02; 845: +46.85; 846: +30.1 | +23.92 [-18.3, +49.02] | 4 / 2 / 0 | 8/64 as extreme; means [-30.72, +30.72] |
| cw2_wares_sold: Wares sold to households over the run, loads (E2 - E1) | t | 741: -8.26; 742: -29.95; 743: +1.381; 744: -78.11; 745: +15.21; 746: -6.173 | -17.65 [-78.11, +15.21] | 2 / 4 / 0 | 20/64 as extreme; means [-23.18, +23.18] |
| cw2_wares_sold: Wares sold to households over the run, loads (E2 - E1) | p | 841: -8.082; 842: +27.21; 843: -19.1; 844: -77.2; 845: +7.857; 846: -30.39 | -16.62 [-77.2, +27.21] | 2 / 4 / 0 | 22/64 as extreme; means [-28.31, +28.31] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw2_free_use_e1: Firm output the people could draw free from the commons before title, upper bound, loads (E1; rules 1 only, none in E2) | t | 741: +6.026; 742: +3.031; 743: +13.65; 744: +3.243; 745: +2.185; 746: +1.632 | +4.962 [+1.632, +13.65] | 6 / 0 / 0 | n/a (no control) |
| cw2_free_use_e1: Firm output the people could draw free from the commons before title, upper bound, loads (E1; rules 1 only, none in E2) | p | 841: +8.446; 842: +12.39; 843: +35.62; 844: +10.57; 845: +11.06; 846: +3.839 | +13.66 [+3.839, +35.62] | 6 / 0 / 0 | n/a (no control) |
| cw2_active_share_p: Active share of firm-turns (E2 - P; worlds where L6a opens a firm) | t | 741: -0.03834; 742: -0.2939; 743: -0.06785; 744: -0.5554; 745: +0.2484; 746: +0.3877 | -0.05324 [-0.5554, +0.3877] | 2 / 4 / 0 | 46/64 as extreme; means [-0.2653, +0.2653] |
| cw2_active_share_p: Active share of firm-turns (E2 - P; worlds where L6a opens a firm) | p | 841: unknown; 842: -0.01698; 843: -0.1527; 844: +0.03185; 845: -0.1528; 846: unknown | -0.07265 [-0.1528, +0.03185] | 1 / 3 / 0 | 6/16 as extreme; means [-0.08858, +0.08858] |
| cw2_active_turns: Active firm-turns, produced or sold (E2 - P; defined on every world) | t | 741: +84; 742: -94; 743: -9; 744: +82; 745: +118; 746: +168 | +58.17 [-94, +168] | 4 / 2 / 0 | 16/64 as extreme; means [-92.5, +92.5] |
| cw2_active_turns: Active firm-turns, produced or sold (E2 - P; defined on every world) | p | 841: +307; 842: +110; 843: +185; 844: +333; 845: +331; 846: +325 | +265.2 [+110, +333] | 6 / 0 / 0 | 2/64 as extreme; means [-265.2, +265.2] |
| cw2_active_share_e1: Active share of firm-turns (E1 - P) | t | 741: -0.06788; 742: -0.258; 743: -0.1061; 744: -0.06016; 745: +0.1634; 746: +0.4454 | +0.01944 [-0.258, +0.4454] | 2 / 4 / 0 | 56/64 as extreme; means [-0.1835, +0.1835] |
| cw2_active_share_e1: Active share of firm-turns (E1 - P) | p | 841: unknown; 842: -0.1028; 843: -0.04475; 844: +0.1668; 845: -0.1942; 846: unknown | -0.04374 [-0.1942, +0.1668] | 1 / 3 / 0 | 10/16 as extreme; means [-0.1271, +0.1271] |
| cw2_wages_e1: Workshop wages credited (E1 - P) | t | 741: +28.8; 742: -25.57; 743: -19.7; 744: +40.9; 745: +8.778; 746: +26.2 | +9.901 [-25.57, +40.9] | 4 / 2 / 0 | 24/64 as extreme; means [-24.99, +24.99] |
| cw2_wages_e1: Workshop wages credited (E1 - P) | p | 841: +54.9; 842: -12.8; 843: +32.05; 844: +77.62; 845: +26.15; 846: +46.3 | +37.37 [-12.8, +77.62] | 5 / 1 / 0 | 4/64 as extreme; means [-41.64, +41.64] |
| cw2_wages_rules: Workshop wages credited (E2 - E1) | t | 741: -20.4; 742: -15.8; 743: +8.1; 744: -34.3; 745: -7.25; 746: -8.3 | -12.99 [-34.3, +8.1] | 1 / 5 / 0 | 6/64 as extreme; means [-15.69, +15.69] |
| cw2_wages_rules: Workshop wages credited (E2 - E1) | p | 841: -16.95; 842: +10.7; 843: -50.35; 844: -28.6; 845: +20.7; 846: -16.2 | -13.45 [-50.35, +20.7] | 2 / 4 / 0 | 18/64 as extreme; means [-23.92, +23.92] |
| cw2_paid_rules: Households' money paid for wares, units (E2 - E1) | t | 741: -15.93; 742: -28.45; 743: +5.379; 744: -70.03; 745: -8.694; 746: -9.458 | -21.2 [-70.03, +5.379] | 1 / 5 / 0 | 4/64 as extreme; means [-22.99, +22.99] |
| cw2_paid_rules: Households' money paid for wares, units (E2 - E1) | p | 841: -32.27; 842: +6.28; 843: -28.52; 844: -84.5; 845: -30.58; 846: -42.97 | -35.43 [-84.5, +6.28] | 1 / 5 / 0 | 4/64 as extreme; means [-37.52, +37.52] |
| cw2_price_rules: Households' price per load of wares (E2 - E1; rules 2 counts the firm's stock in the supply that sets it) | t | 741: -0.1904; 742: -0.3421; 743: +0.3776; 744: -0.4444; 745: -0.3522; 746: -0.1372 | -0.1814 [-0.4444, +0.3776] | 1 / 5 / 0 | 14/64 as extreme; means [-0.3073, +0.3073] |
| cw2_price_rules: Households' price per load of wares (E2 - E1; rules 2 counts the firm's stock in the supply that sets it) | p | 841: -0.397; 842: -0.1711; 843: -0.1513; 844: -0.3617; 845: -0.35; 846: -0.3442 | -0.2959 [-0.397, -0.1513] | 0 / 6 / 0 | 2/64 as extreme; means [-0.2959, +0.2959] |
| cw2_firms_rules: Firms opened (E2 - E1) | t | 741: +0; 742: +0; 743: -2; 744: +1; 745: +0; 746: +0 | -0.1667 [-2, +1] | 1 / 1 / 4 | 64/64 as extreme; means [-0.5, +0.5] |
| cw2_firms_rules: Firms opened (E2 - E1) | p | 841: -2; 842: -6; 843: -2; 844: +0; 845: +0; 846: +2 | -1.333 [-6, +2] | 1 / 3 / 2 | 32/64 as extreme; means [-2, +2] |
| cw2_closed_idle_rules: Firms closed idle (E2 - E1) | t | 741: +0; 742: -1; 743: -2; 744: +3; 745: +1; 746: +1 | +0.3333 [-2, +3] | 3 / 2 / 1 | 52/64 as extreme; means [-1.333, +1.333] |
| cw2_closed_idle_rules: Firms closed idle (E2 - E1) | p | 841: +1; 842: -6; 843: +2; 844: +1; 845: -1; 846: +2 | -0.1667 [-6, +2] | 4 / 2 / 0 | 64/64 as extreme; means [-2.167, +2.167] |
| cw2_net_income: Households' net income from firm work: wages credited less the model income they replaced, wealth units (E2 - P) | t | 741: +10.15; 742: -34.98; 743: -7.587; 744: +6.353; 745: -2.923; 746: +12.92 | -2.678 [-34.98, +12.92] | 3 / 3 / 0 | 52/64 as extreme; means [-12.48, +12.48] |
| cw2_net_income: Households' net income from firm work: wages credited less the model income they replaced, wealth units (E2 - P) | p | 841: +27.54; 842: +9.243; 843: -22.33; 844: +38.47; 845: +35.16; 846: +24.71 | +18.8 [-22.33, +38.47] | 5 / 1 / 0 | 6/64 as extreme; means [-26.24, +26.24] |
| cw2_academy: Wares sold to academies, loads (E2 - P) | t | 741: -16.2; 742: -145.9; 743: +4.509; 744: -12.16; 745: -42.87; 746: +0 | -35.44 [-145.9, +4.509] | 1 / 4 / 1 | 8/64 as extreme; means [-36.95, +36.95] |
| cw2_academy: Wares sold to academies, loads (E2 - P) | p | 841: +4.119; 842: -0.131; 843: -79.44; 844: +19.13; 845: -9.099; 846: +0 | -10.9 [-79.44, +19.13] | 2 / 3 / 1 | 44/64 as extreme; means [-18.65, +18.65] |
| cw2_firms: Firms opened (E2 - P) | t | 741: +3; 742: -3; 743: +0; 744: +3; 745: +0; 746: +1 | +0.6667 [-3, +3] | 3 / 1 / 2 | 40/64 as extreme; means [-1.667, +1.667] |
| cw2_firms: Firms opened (E2 - P) | p | 841: +11; 842: +7; 843: +9; 844: +11; 845: +9; 846: +9 | +9.333 [+7, +11] | 6 / 0 / 0 | 2/64 as extreme; means [-9.333, +9.333] |
| cw2_cost_active: Active share of firm-turns (E2 - E2f: the input cost) | t | 741: +0.3097; 742: +0.4916; 743: +0.007934; 744: +0.3067; 745: +0.2774; 746: -0.08102 | +0.2187 [-0.08102, +0.4916] | 5 / 1 / 0 | 6/64 as extreme; means [-0.2457, +0.2457] |
| cw2_cost_active: Active share of firm-turns (E2 - E2f: the input cost) | p | 841: +0.3407; 842: +0.05663; 843: +0.2533; 844: +0.3433; 845: +0.06155; 846: +0.3993 | +0.2425 [+0.05663, +0.3993] | 6 / 0 / 0 | 2/64 as extreme; means [-0.2425, +0.2425] |
| cw2_cost_firms: Firms opened (E2f - E2) | t | 741: -1; 742: +2; 743: +2; 744: +1; 745: +0; 746: -1 | +0.5 [-1, +2] | 3 / 2 / 1 | 36/64 as extreme; means [-1.167, +1.167] |
| cw2_cost_firms: Firms opened (E2f - E2) | p | 841: +0; 842: +2; 843: -1; 844: -3; 845: -1; 846: -3 | -1 [-3, +2] | 1 / 4 / 1 | 20/64 as extreme; means [-1.667, +1.667] |
| cw2_cost_closed_idle: Firms closed idle (E2f - E2) | t | 741: -1; 742: +0; 743: +2; 744: +0; 745: -1; 746: -1 | -0.1667 [-1, +2] | 1 / 3 / 2 | 64/64 as extreme; means [-0.8333, +0.8333] |
| cw2_cost_closed_idle: Firms closed idle (E2f - E2) | p | 841: -3; 842: +2; 843: -5; 844: -7; 845: -4; 846: -2 | -3.167 [-7, +2] | 1 / 5 / 0 | 6/64 as extreme; means [-3.833, +3.833] |
| cw2_cost_sold: Wares sold to households (E2f - E2; diagnostic) | t | 741: +59.09; 742: +144.6; 743: +1.952; 744: +38.25; 745: +28.09; 746: -4.258 | +44.63 [-4.258, +144.6] | 5 / 1 / 0 | 6/64 as extreme; means [-46.05, +46.05] |
| cw2_cost_sold: Wares sold to households (E2f - E2; diagnostic) | p | 841: +43.95; 842: +18.26; 843: +59.04; 844: +84.67; 845: +18.8; 846: +75.19 | +49.98 [+18.26, +84.67] | 6 / 0 / 0 | 2/64 as extreme; means [-49.98, +49.98] |
| cw2_cost_wages: Workshop wages credited (E2f - E2) | t | 741: +35.95; 742: +69.6; 743: +12.15; 744: +39.95; 745: +28.1; 746: +1.7 | +31.24 [+1.7, +69.6] | 6 / 0 / 0 | 2/64 as extreme; means [-31.24, +31.24] |
| cw2_cost_wages: Workshop wages credited (E2f - E2) | p | 841: +63.95; 842: +26.65; 843: +43.4; 844: +38.25; 845: +21.5; 846: +29.75 | +37.25 [+21.5, +63.95] | 6 / 0 / 0 | 2/64 as extreme; means [-37.25, +37.25] |
| cw2_cost_treasury: Treasury at the end (E2f - E2) | t | 741: +13; 742: -89; 743: -36; 744: -982; 745: +173; 746: +1844 | +153.8 [-982, +1844] | 3 / 3 / 0 | 46/64 as extreme; means [-522.8, +522.8] |
| cw2_cost_treasury: Treasury at the end (E2f - E2) | p | 841: +2397; 842: +1494; 843: -2586; 844: -73; 845: -3091; 846: -317 | -362.7 [-3091, +2397] | 2 / 4 / 0 | 42/64 as extreme; means [-1660, +1660] |
| cw2_collapse_active: Active share of firm-turns (E2a - E2: no household demand) | t | 741: -0.1885; 742: -0.3269; 743: -0.02204; 744: -0.1378; 745: -0.3325; 746: -0.3812 | -0.2315 [-0.3812, -0.02204] | 0 / 6 / 0 | 2/64 as extreme; means [-0.2315, +0.2315] |
| cw2_collapse_active: Active share of firm-turns (E2a - E2: no household demand) | p | 841: -0.161; 842: -0.08738; 843: -0.1755; 844: -0.1905; 845: -0.2269; 846: -0.2364 | -0.1796 [-0.2364, -0.08738] | 0 / 6 / 0 | 2/64 as extreme; means [-0.1796, +0.1796] |
| cw2_collapse_closed_idle: Firms closed idle (E2a - E2) | t | 741: +1; 742: +1; 743: +2; 744: +0; 745: +1; 746: +0 | +0.8333 [+0, +2] | 4 / 0 / 2 | 8/64 as extreme; means [-0.8333, +0.8333] |
| cw2_collapse_closed_idle: Firms closed idle (E2a - E2) | p | 841: +3; 842: +1; 843: +4; 844: +5; 845: +2; 846: +3 | +3 [+1, +5] | 6 / 0 / 0 | 2/64 as extreme; means [-3, +3] |
| cw2_collapse_wages: Workshop wages credited (E2a - E2) | t | 741: -7.65; 742: -5.5; 743: -3.4; 744: +0.7; 745: -5.7; 746: -8.9 | -5.075 [-8.9, +0.7] | 1 / 5 / 0 | 4/64 as extreme; means [-5.308, +5.308] |
| cw2_collapse_wages: Workshop wages credited (E2a - E2) | p | 841: -5.65; 842: -14.85; 843: +7.15; 844: -6.55; 845: -51.15; 846: -7.4 | -13.08 [-51.15, +7.15] | 1 / 5 / 0 | 8/64 as extreme; means [-15.46, +15.46] |
| cw2_collapse_unsold: Unsold firm inventory at the end, loads (E2a - E2) | t | 741: +0; 742: -11.97; 743: +0; 744: +0; 745: +0; 746: +0 | -1.996 [-11.97, +0] | 0 / 1 / 5 | 64/64 as extreme; means [-1.996, +1.996] |
| cw2_collapse_unsold: Unsold firm inventory at the end, loads (E2a - E2) | p | 841: +0; 842: +0; 843: +0; 844: +9.157; 845: -11.95; 846: -9.004 | -1.966 [-11.95, +9.157] | 1 / 2 / 3 | 48/64 as extreme; means [-5.018, +5.018] |
| cw2_collapse_liquidation: Wares handed to the owner at liquidation, loads (E2a - E2) | t | 741: +30.04; 742: +29.73; 743: +2.042; 744: +48.43; 745: +40.33; 746: +22.96 | +28.92 [+2.042, +48.43] | 6 / 0 / 0 | 2/64 as extreme; means [-28.92, +28.92] |
| cw2_collapse_liquidation: Wares handed to the owner at liquidation, loads (E2a - E2) | p | 841: +52.16; 842: +44.49; 843: +92.09; 844: +110.6; 845: +72.86; 846: +57.14 | +71.56 [+44.49, +110.6] | 6 / 0 / 0 | 2/64 as extreme; means [-71.56, +71.56] |
| cw2_producing_e2: Share of firm-turns producing (E2) | t | 741: +0.1516; 742: +0.2463; 743: +0.1258; 744: +0.1003; 745: +0.1857; 746: +0.2668 | +0.1794 [+0.1003, +0.2668] | 6 / 0 / 0 | n/a (no control) |
| cw2_producing_e2: Share of firm-turns producing (E2) | p | 841: +0.1315; 842: +0.1545; 843: +0.2171; 844: +0.146; 845: +0.2323; 846: +0.1823 | +0.1773 [+0.1315, +0.2323] | 6 / 0 / 0 | n/a (no control) |
| cw2_selling_e2: Share of firm-turns selling (E2) | t | 741: +0.2401; 742: +0.3645; 743: +0.09437; 744: +0.2093; 745: +0.3915; 746: +0.4135 | +0.2855 [+0.09437, +0.4135] | 6 / 0 / 0 | n/a (no control) |
| cw2_selling_e2: Share of firm-turns selling (E2) | p | 841: +0.2215; 842: +0.128; 843: +0.2525; 844: +0.2528; 845: +0.2822; 846: +0.3454 | +0.2471 [+0.128, +0.3454] | 6 / 0 / 0 | n/a (no control) |
| cw2_idle_e2: Share of firm-turns idle (E2) | t | 741: +0.07762; 742: +0.04926; 743: +0.03477; 744: +0.05363; 745: +0.07159; 746: +0.06971 | +0.05943 [+0.03477, +0.07762] | 6 / 0 / 0 | n/a (no control) |
| cw2_idle_e2: Share of firm-turns idle (E2) | p | 841: +0.06462; 842: +0.03864; 843: +0.0668; 844: +0.06125; 845: +0.06397; 846: +0.05864 | +0.05899 [+0.03864, +0.0668] | 6 / 0 / 0 | n/a (no control) |
| cw2_closed_share_e2: Share of firm-turns closed (E2) | t | 741: +0.6823; 742: +0.5714; 743: +0.8344; 744: +0.737; 745: +0.5347; 746: +0.4928 | +0.6421 [+0.4928, +0.8344] | 6 / 0 / 0 | n/a (no control) |
| cw2_closed_share_e2: Share of firm-turns closed (E2) | p | 841: +0.6992; 842: +0.7833; 843: +0.6587; 844: +0.6766; 845: +0.6128; 846: +0.5949 | +0.6709 [+0.5949, +0.7833] | 6 / 0 / 0 | n/a (no control) |
| cw2_closed_idle_e2: Firms closed idle (E2) | t | 741: +4; 742: +1; 743: +4; 744: +4; 745: +3; 746: +4 | +3.333 [+1, +4] | 6 / 0 / 0 | n/a (no control) |
| cw2_closed_idle_e2: Firms closed idle (E2) | p | 841: +10; 842: +10; 843: +13; 844: +9; 845: +11; 846: +4 | +9.5 [+4, +13] | 6 / 0 / 0 | n/a (no control) |
| cw2_closed_insolvent_e2: Firms closed insolvent (E2) | t | 741: +0; 742: +0; 743: +0; 744: +0; 745: +0; 746: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw2_closed_insolvent_e2: Firms closed insolvent (E2) | p | 841: +0; 842: +0; 843: +0; 844: +0; 845: +0; 846: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw2_closed_city_fell_e2: Firms closed when their city fell (E2) | t | 741: +0; 742: +0; 743: +0; 744: +0; 745: +0; 746: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw2_closed_city_fell_e2: Firms closed when their city fell (E2) | p | 841: +1; 842: +1; 843: +0; 844: +3; 845: +0; 846: +3 | +1.333 [+0, +3] | 4 / 0 / 2 | n/a (no control) |
| cw2_liquidation_e2: Wares handed to the owner at liquidation, loads (E2) | t | 741: +0; 742: +0; 743: +0; 744: +0; 745: +0; 746: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw2_liquidation_e2: Wares handed to the owner at liquidation, loads (E2) | p | 841: +6.588; 842: +0; 843: +0.747; 844: +18.66; 845: +0; 846: +8.593 | +5.765 [+0, +18.66] | 4 / 0 / 2 | n/a (no control) |
| cw2_inputs_charged_e2: Inputs bought from the commons owner, units (E2; never free) | t | 741: +38.17; 742: +18.58; 743: +181.7; 744: +26; 745: +37.22; 746: +51.61 | +58.88 [+18.58, +181.7] | 6 / 0 / 0 | n/a (no control) |
| cw2_inputs_charged_e2: Inputs bought from the commons owner, units (E2; never free) | p | 841: +104.4; 842: +148.8; 843: +183.6; 844: +112.3; 845: +252.2; 846: +32 | +138.9 [+32, +252.2] | 6 / 0 / 0 | n/a (no control) |
| cw2_owned_output_e2: Owned output titled whole, loads (E2) | t | 741: +65.44; 742: +49.94; 743: +109.9; 744: +46.58; 745: +59.55; 746: +47.89 | +63.22 [+46.58, +109.9] | 6 / 0 / 0 | n/a (no control) |
| cw2_owned_output_e2: Owned output titled whole, loads (E2) | p | 841: +85.64; 842: +79.19; 843: +148.3; 844: +177.3; 845: +205.4; 846: +107.5 | +133.9 [+79.19, +205.4] | 6 / 0 / 0 | n/a (no control) |
| cw2_h_food_shortfall: Food shortfall after relief over the run (E2 - P) | t | 741: +35.27; 742: +467.5; 743: -457; 744: -1105; 745: -165.8; 746: -329.1 | -258.9 [-1105, +467.5] | 2 / 4 / 0 | 22/64 as extreme; means [-426.5, +426.5] |
| cw2_h_food_shortfall: Food shortfall after relief over the run (E2 - P) | p | 841: -479.7; 842: -2131; 843: +553.6; 844: -1001; 845: +1100; 846: -401.6 | -393.2 [-2131, +1100] | 2 / 4 / 0 | 32/64 as extreme; means [-944.4, +944.4] |
| cw2_h_wage_arrears: Wages due but not paid over the run, units (E2 - P) | t | 741: -0.15; 742: -2.825; 743: -6.475; 744: +0.6; 745: -2.05; 746: -1.8 | -2.117 [-6.475, +0.6] | 1 / 5 / 0 | 6/64 as extreme; means [-2.317, +2.317] |
| cw2_h_wage_arrears: Wages due but not paid over the run, units (E2 - P) | p | 841: +0.7; 842: -3.55; 843: -2.94; 844: +0.25; 845: -1.704; 846: +0.6 | -1.107 [-3.55, +0.7] | 3 / 3 / 0 | 16/64 as extreme; means [-1.624, +1.624] |
| cw2_h_asset_arrears: Workshop asset arrears at the end (E2 - P) | t | 741: +0; 742: +0; 743: +0; 744: +0; 745: +0; 746: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] |
| cw2_h_asset_arrears: Workshop asset arrears at the end (E2 - P) | p | 841: -15; 842: +0; 843: +0; 844: +0; 845: +0; 846: +0 | -2.5 [-15, +0] | 0 / 1 / 5 | 64/64 as extreme; means [-2.5, +2.5] |
| cw2_h_unsold: Unsold firm inventory at the end, loads (E2 - P) | t | 741: +0; 742: +8.11; 743: +0; 744: -1.009; 745: +0; 746: +0 | +1.184 [-1.009, +8.11] | 1 / 1 / 4 | 64/64 as extreme; means [-1.52, +1.52] |
| cw2_h_unsold: Unsold firm inventory at the end, loads (E2 - P) | p | 841: +0; 842: +0; 843: +0; 844: +0; 845: +11.75; 846: +12.55 | +4.05 [+0, +12.55] | 2 / 0 / 4 | 32/64 as extreme; means [-4.05, +4.05] |
| cw2_h_priced_out: Household-turns priced out of firm wares (E2 - E1; none recorded in P) | t | 741: +0; 742: +0; 743: +0; 744: +0; 745: +0; 746: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] |
| cw2_h_priced_out: Household-turns priced out of firm wares (E2 - E1; none recorded in P) | p | 841: +0; 842: +0; 843: +0; 844: +0; 845: +0; 846: +0 | +0 [+0, +0] | 0 / 0 / 6 | 64/64 as extreme; means [+0, +0] |
| cw2_h_priced_out_e2: Household-turns priced out of firm wares (E2) | t | 741: +0; 742: +0; 743: +0; 744: +0; 745: +0; 746: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw2_h_priced_out_e2: Household-turns priced out of firm wares (E2) | p | 841: +0; 842: +0; 843: +0; 844: +0; 845: +0; 846: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw2_h_farm_time: Farm time diverted to crews, work units (E2 - P) | t | 741: -71.16; 742: -185.5; 743: -8.9; 744: -86.12; 745: -14.31; 746: -36.18 | -67.02 [-185.5, -8.9] | 0 / 6 / 0 | 2/64 as extreme; means [-67.02, +67.02] |
| cw2_h_farm_time: Farm time diverted to crews, work units (E2 - P) | p | 841: -27.89; 842: -35.69; 843: -109.2; 844: -192; 845: -94.62; 846: -176.8 | -106 [-192, -27.89] | 0 / 6 / 0 | 2/64 as extreme; means [-106, +106] |
| cw2_h_treasury: Treasury at the end (E2 - P) | t | 741: -285; 742: +2414; 743: -106; 744: -10; 745: -139; 746: -898 | +162.7 [-898, +2414] | 1 / 5 / 0 | 64/64 as extreme; means [-642, +642] |
| cw2_h_treasury: Treasury at the end (E2 - P) | p | 841: -928; 842: -2621; 843: +1171; 844: -1064; 845: +916; 846: +1015 | -251.8 [-2621, +1171] | 3 / 3 / 0 | 46/64 as extreme; means [-1286, +1286] |
| cw2_h_stability: Mean stability of living civilizations at the end (E2 - P) | t | 741: +0.6667; 742: +11; 743: -8.333; 744: +0.6667; 745: -11; 746: -19.5 | -4.417 [-19.5, +11] | 3 / 3 / 0 | 32/64 as extreme; means [-8.528, +8.528] |
| cw2_h_stability: Mean stability of living civilizations at the end (E2 - P) | p | 841: +6.714; 842: -9.191; 843: +5.889; 844: +5.033; 845: +7.2; 846: -4.125 | +1.92 [-9.191, +7.2] | 4 / 2 / 0 | 34/64 as extreme; means [-6.359, +6.359] |
| cw2_h_population: Population at the end (E2 - P) | t | 741: -1; 742: -39; 743: -18; 744: -52; 745: -41; 746: -13 | -27.33 [-52, -1] | 0 / 6 / 0 | 2/64 as extreme; means [-27.33, +27.33] |
| cw2_h_population: Population at the end (E2 - P) | p | 841: -88; 842: -225; 843: +35; 844: -138; 845: -34; 846: -174 | -104 [-225, +35] | 1 / 5 / 0 | 6/64 as extreme; means [-115.7, +115.7] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E1 - P | Population at the end (sum over civilizations) | t | 741: +9; 742: +30; 743: -15; 744: -21; 745: -26; 746: -4 | -4.5 [-26, +30] | 2 / 4 / 0 | 40/64 as extreme; means [-17.5, +17.5] | recorded |
| E1 - P | Population at the end (sum over civilizations) | p | 841: -46; 842: -52; 843: -16; 844: -3; 845: -52; 846: -161 | -55 [-161, -3] | 0 / 6 / 0 | 2/64 as extreme; means [-55, +55] | recorded |
| E1 - P | Treasury at the end (sum over civilizations) | t | 741: -234; 742: +2612; 743: -213; 744: +315; 745: -577; 746: +858 | +460.2 [-577, +2612] | 3 / 3 / 0 | 28/64 as extreme; means [-801.5, +801.5] | recorded |
| E1 - P | Treasury at the end (sum over civilizations) | p | 841: -166; 842: -1527; 843: -424; 844: +767; 845: -1154; 846: +1275 | -204.8 [-1527, +1275] | 2 / 4 / 0 | 42/64 as extreme; means [-885.5, +885.5] | recorded |
| E1 - P | Food shortfall after relief over the run (food) | t | 741: +159.7; 742: -714.3; 743: -251.8; 744: -528.7; 745: -89.22; 746: +433 | -165.2 [-714.3, +433] | 2 / 4 / 0 | 24/64 as extreme; means [-362.8, +362.8] | recorded |
| E1 - P | Food shortfall after relief over the run (food) | p | 841: +442.6; 842: -1412; 843: +2477; 844: -824.2; 845: +756.9; 846: -811.4 | +104.9 [-1412, +2477] | 3 / 3 / 0 | 58/64 as extreme; means [-1121, +1121] | recorded |
| E1 - P | Priced-out person-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E1 - P | Priced-out person-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E1 - P | Priced-out child-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E1 - P | Priced-out child-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E1 - P | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E1 - P | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E1 - P | Deaths by epidemic (the epidemic authority) | t | 741: +28; 742: -30; 743: +87; 744: +83; 745: +23; 746: -45 | +24.33 [-45, +87] | 4 / 2 / 0 | 22/64 as extreme; means [-49.33, +49.33] | recorded |
| E1 - P | Deaths by epidemic (the epidemic authority) | p | 841: +17; 842: +160; 843: -66; 844: -94; 845: -113; 846: +44 | -8.667 [-113, +160] | 3 / 3 / 0 | 54/64 as extreme; means [-82.33, +82.33] | recorded |
| E1 - P | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E1 - P | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E1 - P | Agents migrating between regions over the run | t | 741: +58; 742: -114; 743: +1; 744: -80; 745: +220; 746: -281 | -32.67 [-281, +220] | 3 / 3 / 0 | 40/64 as extreme; means [-125.7, +125.7] | recorded |
| E1 - P | Agents migrating between regions over the run | p | 841: +1068; 842: -238; 843: +1420; 844: -754; 845: -392; 846: -400 | +117.3 [-754, +1420] | 2 / 4 / 0 | 48/64 as extreme; means [-712, +712] | recorded |
| E1 - P | Mean wealth Gini of living civilizations at the end | t | 741: +0.02999; 742: +0.1778; 743: -0.02707; 744: -0.02336; 745: -0.1914; 746: -0.1361 | -0.02836 [-0.1914, +0.1778] | 2 / 4 / 0 | 40/64 as extreme; means [-0.09762, +0.09762] | recorded |
| E1 - P | Mean wealth Gini of living civilizations at the end | p | 841: -0.1108; 842: -0.0006945; 843: +0.1171; 844: -0.103; 845: -0.09037; 846: +0.08641 | -0.01689 [-0.1108, +0.1171] | 2 / 4 / 0 | 46/64 as extreme; means [-0.08474, +0.08474] | recorded |
| E1 - P | Timber stand share of capacity at the end | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E1 - P | Timber stand share of capacity at the end | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2 - E1 | Population at the end (sum over civilizations) | t | 741: -10; 742: -69; 743: -3; 744: -31; 745: -15; 746: -9 | -22.83 [-69, -3] | 0 / 6 / 0 | 2/64 as extreme; means [-22.83, +22.83] | recorded |
| E2 - E1 | Population at the end (sum over civilizations) | p | 841: -42; 842: -173; 843: +51; 844: -135; 845: +18; 846: -13 | -49 [-173, +51] | 2 / 4 / 0 | 20/64 as extreme; means [-72, +72] | recorded |
| E2 - E1 | Treasury at the end (sum over civilizations) | t | 741: -51; 742: -198; 743: +107; 744: -325; 745: +438; 746: -1756 | -297.5 [-1756, +438] | 2 / 4 / 0 | 32/64 as extreme; means [-479.2, +479.2] | recorded |
| E2 - E1 | Treasury at the end (sum over civilizations) | p | 841: -762; 842: -1094; 843: +1595; 844: -1831; 845: +2070; 846: -260 | -47 [-1831, +2070] | 2 / 4 / 0 | 58/64 as extreme; means [-1269, +1269] | recorded |
| E2 - E1 | Food shortfall after relief over the run (food) | t | 741: -124.4; 742: +1182; 743: -205.3; 744: -575.8; 745: -76.58; 746: -762 | -93.7 [-762, +1182] | 1 / 5 / 0 | 50/64 as extreme; means [-487.7, +487.7] | recorded |
| E2 - E1 | Food shortfall after relief over the run (food) | p | 841: -922.3; 842: -719.2; 843: -1924; 844: -176.3; 845: +343; 846: +409.8 | -498.1 [-1924, +409.8] | 2 / 4 / 0 | 16/64 as extreme; means [-749.1, +749.1] | recorded |
| E2 - E1 | Priced-out person-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - E1 | Priced-out person-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - E1 | Priced-out child-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - E1 | Priced-out child-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - E1 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2 - E1 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2 - E1 | Deaths by epidemic (the epidemic authority) | t | 741: +40; 742: +52; 743: -13; 744: -24; 745: -8; 746: +18 | +10.83 [-24, +52] | 3 / 3 / 0 | 28/64 as extreme; means [-25.83, +25.83] | recorded |
| E2 - E1 | Deaths by epidemic (the epidemic authority) | p | 841: -57; 842: +106; 843: -39; 844: +105; 845: +158; 846: +74 | +57.83 [-57, +158] | 4 / 2 / 0 | 10/64 as extreme; means [-89.83, +89.83] | recorded |
| E2 - E1 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2 - E1 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2 - E1 | Agents migrating between regions over the run | t | 741: +238; 742: -535; 743: -295; 744: -58; 745: -79; 746: -275 | -167.3 [-535, +238] | 1 / 5 / 0 | 10/64 as extreme; means [-246.7, +246.7] | recorded |
| E2 - E1 | Agents migrating between regions over the run | p | 841: -1892; 842: -1161; 843: -1201; 844: -785; 845: +319; 846: -43 | -793.8 [-1892, +319] | 1 / 5 / 0 | 6/64 as extreme; means [-900.2, +900.2] | recorded |
| E2 - E1 | Mean wealth Gini of living civilizations at the end | t | 741: +0.003023; 742: +0.02576; 743: -0.005561; 744: -0.01823; 745: -0.02363; 746: -0.1152 | -0.02231 [-0.1152, +0.02576] | 2 / 4 / 0 | 24/64 as extreme; means [-0.03191, +0.03191] | recorded |
| E2 - E1 | Mean wealth Gini of living civilizations at the end | p | 841: +0.1019; 842: -0.1332; 843: +0.1084; 844: +0.06986; 845: +0.09448; 846: -0.06817 | +0.02886 [-0.1332, +0.1084] | 4 / 2 / 0 | 32/64 as extreme; means [-0.096, +0.096] | recorded |
| E2 - E1 | Timber stand share of capacity at the end | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2 - E1 | Timber stand share of capacity at the end | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2f - E2 | Population at the end (sum over civilizations) | t | 741: +18; 742: +52; 743: -4; 744: +31; 745: +19; 746: +15 | +21.83 [-4, +52] | 5 / 1 / 0 | 4/64 as extreme; means [-23.17, +23.17] | recorded |
| E2f - E2 | Population at the end (sum over civilizations) | p | 841: +19; 842: +17; 843: -86; 844: -1; 845: +17; 846: +13 | -3.5 [-86, +19] | 4 / 2 / 0 | 62/64 as extreme; means [-25.5, +25.5] | recorded |
| E2f - E2 | Treasury at the end (sum over civilizations) | t | 741: +13; 742: -89; 743: -36; 744: -982; 745: +173; 746: +1844 | +153.8 [-982, +1844] | 3 / 3 / 0 | 46/64 as extreme; means [-522.8, +522.8] | recorded |
| E2f - E2 | Treasury at the end (sum over civilizations) | p | 841: +2397; 842: +1494; 843: -2586; 844: -73; 845: -3091; 846: -317 | -362.7 [-3091, +2397] | 2 / 4 / 0 | 42/64 as extreme; means [-1660, +1660] | recorded |
| E2f - E2 | Food shortfall after relief over the run (food) | t | 741: +531.2; 742: -1026; 743: -469.2; 744: +224; 745: +235; 746: +790.9 | +47.65 [-1026, +790.9] | 4 / 2 / 0 | 58/64 as extreme; means [-546, +546] | recorded |
| E2f - E2 | Food shortfall after relief over the run (food) | p | 841: +246.9; 842: +803.6; 843: -531; 844: -1722; 845: -1298; 846: -76.14 | -429.4 [-1722, +803.6] | 2 / 4 / 0 | 22/64 as extreme; means [-779.5, +779.5] | recorded |
| E2f - E2 | Priced-out person-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2f - E2 | Priced-out person-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2f - E2 | Priced-out child-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2f - E2 | Priced-out child-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2f - E2 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2f - E2 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2f - E2 | Deaths by epidemic (the epidemic authority) | t | 741: -80; 742: -78; 743: -15; 744: -27; 745: +28; 746: -23 | -32.5 [-80, +28] | 1 / 5 / 0 | 10/64 as extreme; means [-41.83, +41.83] | recorded |
| E2f - E2 | Deaths by epidemic (the epidemic authority) | p | 841: +28; 842: +180; 843: +87; 844: +280; 845: -242; 846: -151 | +30.33 [-242, +280] | 4 / 2 / 0 | 44/64 as extreme; means [-161.3, +161.3] | recorded |
| E2f - E2 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2f - E2 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2f - E2 | Agents migrating between regions over the run | t | 741: -229; 742: +718; 743: -48; 744: +51; 745: -15; 746: +257 | +122.3 [-229, +718] | 3 / 3 / 0 | 30/64 as extreme; means [-219.7, +219.7] | recorded |
| E2f - E2 | Agents migrating between regions over the run | p | 841: +849; 842: +1045; 843: -111; 844: +330; 845: -817; 846: -151 | +190.8 [-817, +1045] | 3 / 3 / 0 | 32/64 as extreme; means [-550.5, +550.5] | recorded |
| E2f - E2 | Mean wealth Gini of living civilizations at the end | t | 741: -0.06555; 742: -0.008267; 743: -0.001466; 744: -0.2014; 745: +0.01932; 746: +0.1542 | -0.0172 [-0.2014, +0.1542] | 2 / 4 / 0 | 42/64 as extreme; means [-0.07504, +0.07504] | recorded |
| E2f - E2 | Mean wealth Gini of living civilizations at the end | p | 841: +0.01076; 842: +0.2001; 843: -0.1916; 844: +0.02802; 845: -0.1027; 846: +0.06034 | +0.0008304 [-0.1916, +0.2001] | 4 / 2 / 0 | 64/64 as extreme; means [-0.09892, +0.09892] | recorded |
| E2f - E2 | Timber stand share of capacity at the end | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2f - E2 | Timber stand share of capacity at the end | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2a - E2 | Population at the end (sum over civilizations) | t | 741: +30; 742: +5; 743: -16; 744: +37; 745: +3; 746: -1 | +9.667 [-16, +37] | 4 / 2 / 0 | 20/64 as extreme; means [-15.33, +15.33] | recorded |
| E2a - E2 | Population at the end (sum over civilizations) | p | 841: +118; 842: +38; 843: +15; 844: +197; 845: -8; 846: +19 | +63.17 [-8, +197] | 5 / 1 / 0 | 4/64 as extreme; means [-65.83, +65.83] | recorded |
| E2a - E2 | Treasury at the end (sum over civilizations) | t | 741: -113; 742: +31; 743: -186; 744: +195; 745: -1255; 746: +1305 | -3.833 [-1255, +1305] | 3 / 3 / 0 | 64/64 as extreme; means [-514.2, +514.2] | recorded |
| E2a - E2 | Treasury at the end (sum over civilizations) | p | 841: +657; 842: +585; 843: -715; 844: +83; 845: -1198; 846: -1294 | -313.7 [-1294, +657] | 3 / 3 / 0 | 28/64 as extreme; means [-755.3, +755.3] | recorded |
| E2a - E2 | Food shortfall after relief over the run (food) | t | 741: +818; 742: -884.1; 743: -203.6; 744: +797.8; 745: -1.798; 746: -139.4 | +64.47 [-884.1, +818] | 2 / 4 / 0 | 64/64 as extreme; means [-474.1, +474.1] | recorded |
| E2a - E2 | Food shortfall after relief over the run (food) | p | 841: +463.7; 842: +932.5; 843: +1836; 844: -1322; 845: -680.6; 846: -28.9 | +200 [-1322, +1836] | 3 / 3 / 0 | 44/64 as extreme; means [-877.3, +877.3] | recorded |
| E2a - E2 | Priced-out person-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2a - E2 | Priced-out person-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2a - E2 | Priced-out child-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2a - E2 | Priced-out child-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2a - E2 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2a - E2 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2a - E2 | Deaths by epidemic (the epidemic authority) | t | 741: -81; 742: +56; 743: +28; 744: +22; 745: +13; 746: +4 | +7 [-81, +56] | 5 / 1 / 0 | 44/64 as extreme; means [-34, +34] | recorded |
| E2a - E2 | Deaths by epidemic (the epidemic authority) | p | 841: +11; 842: -95; 843: +9; 844: +149; 845: -125; 846: +12 | -6.5 [-125, +149] | 4 / 2 / 0 | 64/64 as extreme; means [-66.83, +66.83] | recorded |
| E2a - E2 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2a - E2 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2a - E2 | Agents migrating between regions over the run | t | 741: -157; 742: +662; 743: -47; 744: +185; 745: +253; 746: +75 | +161.8 [-157, +662] | 4 / 2 / 0 | 14/64 as extreme; means [-229.8, +229.8] | recorded |
| E2a - E2 | Agents migrating between regions over the run | p | 841: +1502; 842: +344; 843: +443; 844: -311; 845: -394; 846: -234 | +225 [-394, +1502] | 3 / 3 / 0 | 36/64 as extreme; means [-538, +538] | recorded |
| E2a - E2 | Mean wealth Gini of living civilizations at the end | t | 741: -0.07365; 742: -0.06758; 743: +0.009581; 744: +0.0302; 745: -0.0281; 746: +0.1507 | +0.003525 [-0.07365, +0.1507] | 3 / 3 / 0 | 58/64 as extreme; means [-0.05997, +0.05997] | recorded |
| E2a - E2 | Mean wealth Gini of living civilizations at the end | p | 841: -0.152; 842: +0.03886; 843: -0.3165; 844: +0.1008; 845: -0.03144; 846: +0.01649 | -0.0573 [-0.3165, +0.1008] | 3 / 3 / 0 | 30/64 as extreme; means [-0.1093, +0.1093] | recorded |
| E2a - E2 | Timber stand share of capacity at the end | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2a - E2 | Timber stand share of capacity at the end | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2 - P | Population at the end (sum over civilizations) | t | 741: -1; 742: -39; 743: -18; 744: -52; 745: -41; 746: -13 | -27.33 [-52, -1] | 0 / 6 / 0 | 2/64 as extreme; means [-27.33, +27.33] | recorded |
| E2 - P | Population at the end (sum over civilizations) | p | 841: -88; 842: -225; 843: +35; 844: -138; 845: -34; 846: -174 | -104 [-225, +35] | 1 / 5 / 0 | 6/64 as extreme; means [-115.7, +115.7] | recorded |
| E2 - P | Treasury at the end (sum over civilizations) | t | 741: -285; 742: +2414; 743: -106; 744: -10; 745: -139; 746: -898 | +162.7 [-898, +2414] | 1 / 5 / 0 | 64/64 as extreme; means [-642, +642] | recorded |
| E2 - P | Treasury at the end (sum over civilizations) | p | 841: -928; 842: -2621; 843: +1171; 844: -1064; 845: +916; 846: +1015 | -251.8 [-2621, +1171] | 3 / 3 / 0 | 46/64 as extreme; means [-1286, +1286] | recorded |
| E2 - P | Food shortfall after relief over the run (food) | t | 741: +35.27; 742: +467.5; 743: -457; 744: -1105; 745: -165.8; 746: -329.1 | -258.9 [-1105, +467.5] | 2 / 4 / 0 | 22/64 as extreme; means [-426.5, +426.5] | recorded |
| E2 - P | Food shortfall after relief over the run (food) | p | 841: -479.7; 842: -2131; 843: +553.6; 844: -1001; 845: +1100; 846: -401.6 | -393.2 [-2131, +1100] | 2 / 4 / 0 | 32/64 as extreme; means [-944.4, +944.4] | recorded |
| E2 - P | Priced-out person-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - P | Priced-out person-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - P | Priced-out child-turns | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - P | Priced-out child-turns | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - P | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2 - P | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2 - P | Deaths by epidemic (the epidemic authority) | t | 741: +68; 742: +22; 743: +74; 744: +59; 745: +15; 746: -27 | +35.17 [-27, +74] | 5 / 1 / 0 | 8/64 as extreme; means [-44.17, +44.17] | recorded |
| E2 - P | Deaths by epidemic (the epidemic authority) | p | 841: -40; 842: +266; 843: -105; 844: +11; 845: +45; 846: +118 | +49.17 [-105, +266] | 4 / 2 / 0 | 26/64 as extreme; means [-97.5, +97.5] | recorded |
| E2 - P | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2 - P | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2 - P | Agents migrating between regions over the run | t | 741: +296; 742: -649; 743: -294; 744: -138; 745: +141; 746: -556 | -200 [-649, +296] | 2 / 4 / 0 | 20/64 as extreme; means [-345.7, +345.7] | recorded |
| E2 - P | Agents migrating between regions over the run | p | 841: -824; 842: -1399; 843: +219; 844: -1539; 845: -73; 846: -443 | -676.5 [-1539, +219] | 1 / 5 / 0 | 6/64 as extreme; means [-749.5, +749.5] | recorded |
| E2 - P | Mean wealth Gini of living civilizations at the end | t | 741: +0.03301; 742: +0.2036; 743: -0.03263; 744: -0.04159; 745: -0.215; 746: -0.2514 | -0.05067 [-0.2514, +0.2036] | 2 / 4 / 0 | 24/64 as extreme; means [-0.1295, +0.1295] | recorded |
| E2 - P | Mean wealth Gini of living civilizations at the end | p | 841: -0.008932; 842: -0.1339; 843: +0.2255; 844: -0.03313; 845: +0.004112; 846: +0.01824 | +0.01197 [-0.1339, +0.2255] | 3 / 3 / 0 | 54/64 as extreme; means [-0.07064, +0.07064] | recorded |
| E2 - P | Timber stand share of capacity at the end | t | 741: not recorded; 742: not recorded; 743: not recorded; 744: not recorded; 745: not recorded; 746: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2 - P | Timber stand share of capacity at the end | p | 841: not recorded; 842: not recorded; 843: not recorded; 844: not recorded; 845: not recorded; 846: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| P | 7.8 [6.7, 9.2] | 22.8 [18.8, 28.7] |
| E1 | 8.8 [7.9, 9.9] | 24.9 [20.1, 30.4] |
| E2 | 8.4 [7.5, 9.6] | 23.4 [18.6, 29.7] |
| E2f | 8.5 [7.4, 9.5] | 23.7 [19.4, 30.6] |
| E2a | 7.9 [7.0, 9.4] | 22.2 [18.3, 26.7] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
