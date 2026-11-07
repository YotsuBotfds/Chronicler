# CW5: S4 titled trade (A4-1)

Cohort held. Runs: 24; failed: 0 (missing outcomes: 0); simulation and extraction seconds 435 (0.121 core-hours)

Identity digests: db04f4e3fc352dfe3a65aafb35993b2dc98aaa6905e23dcb8327526a6ff0bab8 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"food_allocation": [1], "household_retail": [1], "titled_trade": [1], "wealth_accounting": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"food_allocation": [1], "household_retail": [1], "wealth_accounting": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| T | t | 771: activated; 772: activated; 773: activated; 774: activated; 775: activated; 776: activated | 6 of 6 |
| T | p | 871: activated; 872: activated; 873: activated; 874: activated; 875: activated; 876: activated | 6 of 6 |

## Pre-treatment windows and region sets per world (world turns 0 .. min(19, f - 1))

| Stratum | World | T's first purchase (f) | Window turns | Deficit / surplus regions | Window records R = T | Status |
| --- | --- | --- | --- | --- | --- | --- |
| t | 771 | 10 | 10 | 5 / 1 | yes | valid |
| t | 772 | 8 | 8 | 2 / 4 | yes | valid |
| t | 773 | 4 | 4 | 4 / 2 | yes | excluded: first purchase in world turn 4, a window of 4 turns (< 5) |
| t | 774 | 7 | 7 | 4 / 2 | yes | valid |
| t | 775 | 4 | 4 | 6 / 2 | yes | excluded: first purchase in world turn 4, a window of 4 turns (< 5) |
| t | 776 | 9 | 9 | 4 / 2 | yes | valid |
| p | 871 | 5 | 5 | 7 / 8 | yes | valid |
| p | 872 | 5 | 5 | 8 / 7 | yes | valid |
| p | 873 | 8 | 8 | 8 / 9 | yes | valid |
| p | 874 | 8 | 8 | 8 / 8 | yes | valid |
| p | 875 | 6 | 6 | 7 / 7 | yes | valid |
| p | 876 | 4 | 4 | 8 / 7 | yes | excluded: first purchase in world turn 4, a window of 4 turns (< 5) |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5_food_in_deficit: Food into the deficit regions by trade over the run: titled cargo in less titled cargo bought there, plus native commons trade, food units (T - R) | t | 771: +107.1; 772: -131.3; 773: excluded by the window; 774: +229.6; 775: excluded by the window; 776: +81.31 | +71.67 [-131.3, +229.6] | 3 / 1 / 0 | 8/16 as extreme; means [-137.3, +137.3] |
| cw5_food_in_deficit: Food into the deficit regions by trade over the run: titled cargo in less titled cargo bought there, plus native commons trade, food units (T - R) | p | 871: -34.41; 872: -199.3; 873: +232.5; 874: -57.33; 875: +35.47; 876: excluded by the window | -4.602 [-199.3, +232.5] | 2 / 3 / 0 | 30/32 as extreme; means [-111.8, +111.8] |
| cw5_shortfall_deficit: Food shortfall share after relief in the deficit regions (T - R) | t | 771: +0.006978; 772: +0.002303; 773: excluded by the window; 774: +0.03539; 775: excluded by the window; 776: +0.01307 | +0.01443 [+0.002303, +0.03539] | 4 / 0 / 0 | 2/16 as extreme; means [-0.01443, +0.01443] |
| cw5_shortfall_deficit: Food shortfall share after relief in the deficit regions (T - R) | p | 871: -0.02862; 872: -0.01023; 873: -0.007732; 874: -0.002141; 875: -0.002833; 876: excluded by the window | -0.01031 [-0.02862, -0.002141] | 0 / 5 / 0 | 2/32 as extreme; means [-0.01031, +0.01031] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5_holder_balance: Merchants' balance on titled cargo: sales credited less owners paid, plus titled food still held at purchase cost (returned, aboard at the end, delivered unsold), less the model income withheld, wealth units (T) | t | 771: +148.8; 772: +186.6; 773: +112.5; 774: +265.5; 775: +262.6; 776: +55.95 | +172 [+55.95, +265.5] | 6 / 0 / 0 | n/a (no control) |
| cw5_holder_balance: Merchants' balance on titled cargo: sales credited less owners paid, plus titled food still held at purchase cost (returned, aboard at the end, delivered unsold), less the model income withheld, wealth units (T) | p | 871: +225.5; 872: +267; 873: +166.3; 874: +437.6; 875: +407.5; 876: +287.1 | +298.5 [+166.3, +437.6] | 6 / 0 / 0 | n/a (no control) |
| cw5_margin_vs_withheld: Merchants' realized margin less the model income withheld (T) | t | 771: +144.9; 772: +180.6; 773: +110; 774: +252.3; 775: +262.6; 776: +55.93 | +167.7 [+55.93, +262.6] | 6 / 0 / 0 | n/a (no control) |
| cw5_margin_vs_withheld: Merchants' realized margin less the model income withheld (T) | p | 871: +221; 872: +247.1; 873: +143.8; 874: +426.7; 875: +391.8; 876: +275.5 | +284.3 [+143.8, +426.7] | 6 / 0 / 0 | n/a (no control) |
| cw5_held_returned: Titled food returned to origins, at purchase cost (T) | t | 771: +0; 772: +0; 773: +0; 774: +1.041; 775: +0; 776: +0 | +0.1735 [+0, +1.041] | 1 / 0 / 5 | n/a (no control) |
| cw5_held_returned: Titled food returned to origins, at purchase cost (T) | p | 871: +2.062; 872: +4.925; 873: +10.09; 874: +3.127; 875: +7.217; 876: +7.048 | +5.746 [+2.062, +10.09] | 6 / 0 / 0 | n/a (no control) |
| cw5_held_aboard: Titled food aboard at the end, at purchase cost (T) | t | 771: +3.953; 772: +3.173; 773: +2.01; 774: +3.203; 775: +0.024; 776: +0 | +2.06 [+0, +3.953] | 5 / 0 / 1 | n/a (no control) |
| cw5_held_aboard: Titled food aboard at the end, at purchase cost (T) | p | 871: +1.42; 872: +8.495; 873: +6.072; 874: +4.15; 875: +5.293; 876: +2.605 | +4.672 [+1.42, +8.495] | 6 / 0 / 0 | n/a (no control) |
| cw5_titled_delivered_deficit: Titled food delivered into the deficit regions, food units (T - R; R has none by construction) | t | 771: +339.7; 772: +16.06; 773: excluded by the window; 774: +650.4; 775: excluded by the window; 776: +81.47 | +271.9 [+16.06, +650.4] | 4 / 0 / 0 | 2/16 as extreme; means [-271.9, +271.9] |
| cw5_titled_delivered_deficit: Titled food delivered into the deficit regions, food units (T - R; R has none by construction) | p | 871: +113.9; 872: +169.3; 873: +372.3; 874: +255.5; 875: +375.3; 876: excluded by the window | +257.3 [+113.9, +375.3] | 5 / 0 / 0 | 2/32 as extreme; means [-257.3, +257.3] |
| cw5_titled_net_deficit: Titled food into less out of the deficit regions (T - R; R has none by construction) | t | 771: +107.1; 772: -131.3; 773: excluded by the window; 774: +229.6; 775: excluded by the window; 776: +81.31 | +71.67 [-131.3, +229.6] | 3 / 1 / 0 | 8/16 as extreme; means [-137.3, +137.3] |
| cw5_titled_net_deficit: Titled food into less out of the deficit regions (T - R; R has none by construction) | p | 871: -34.41; 872: -199.3; 873: +232.5; 874: -57.33; 875: +36.06; 876: excluded by the window | -4.485 [-199.3, +232.5] | 2 / 3 / 0 | 30/32 as extreme; means [-111.9, +111.9] |
| cw5_native_net_deficit: Native commons trade into the deficit regions (T - R) | t | 771: +0; 772: +0; 773: excluded by the window; 774: +0; 775: excluded by the window; 776: +0 | +0 [+0, +0] | 0 / 0 / 4 | 16/16 as extreme; means [+0, +0] |
| cw5_native_net_deficit: Native commons trade into the deficit regions (T - R) | p | 871: +0; 872: +0; 873: +0; 874: +0; 875: -0.5843; 876: excluded by the window | -0.1169 [-0.5843, +0] | 0 / 1 / 4 | 32/32 as extreme; means [-0.1169, +0.1169] |
| cw5_met_deficit: Deficit regions' demand-weighted min(1, sufficiency) (T - R) | t | 771: -0.006978; 772: -0.002303; 773: excluded by the window; 774: -0.03539; 775: excluded by the window; 776: -0.01307 | -0.01443 [-0.03539, -0.002303] | 0 / 4 / 0 | 2/16 as extreme; means [-0.01443, +0.01443] |
| cw5_met_deficit: Deficit regions' demand-weighted min(1, sufficiency) (T - R) | p | 871: +0.02862; 872: +0.01023; 873: +0.007732; 874: +0.002141; 875: +0.002833; 876: excluded by the window | +0.01031 [+0.002141, +0.02862] | 5 / 0 / 0 | 2/32 as extreme; means [-0.01031, +0.01031] |
| cw5_priced_out_deficit: Priced-out person-turns in the deficit regions (T - R) | t | 771: +63; 772: +4; 773: excluded by the window; 774: -94; 775: excluded by the window; 776: +187 | +40 [-94, +187] | 3 / 1 / 0 | 10/16 as extreme; means [-87, +87] |
| cw5_priced_out_deficit: Priced-out person-turns in the deficit regions (T - R) | p | 871: +182; 872: +86; 873: -146; 874: -94; 875: +27; 876: excluded by the window | +11 [-146, +182] | 3 / 2 / 0 | 28/32 as extreme; means [-107, +107] |
| cw5_price_deficit: Mean retail price in the deficit regions, milli per ration (T - R) | t | 771: +27.4; 772: +119.2; 773: excluded by the window; 774: +178.7; 775: excluded by the window; 776: +68.83 | +98.53 [+27.4, +178.7] | 4 / 0 / 0 | 2/16 as extreme; means [-98.53, +98.53] |
| cw5_price_deficit: Mean retail price in the deficit regions, milli per ration (T - R) | p | 871: -129.7; 872: -62.21; 873: -29.14; 874: +5.183; 875: -42.98; 876: excluded by the window | -51.77 [-129.7, +5.183] | 1 / 4 / 0 | 4/32 as extreme; means [-53.84, +53.84] |
| cw5_shortfall_dest: Food shortfall share in the regions T delivered to (T; selection) | t | 771: +0.1176; 772: +0.1994; 773: +0.2024; 774: +0.1287; 775: +0.234; 776: +0.3303 | +0.2021 [+0.1176, +0.3303] | 6 / 0 / 0 | n/a (no control) |
| cw5_shortfall_dest: Food shortfall share in the regions T delivered to (T; selection) | p | 871: +0.1795; 872: +0.1141; 873: +0.09878; 874: +0.1007; 875: +0.07947; 876: +0.1191 | +0.1153 [+0.07947, +0.1795] | 6 / 0 / 0 | n/a (no control) |
| cw5_t0_food_in_deficit: Food into the turn-0 deficit regions by trade (T - R; sensitivity) | t | 771: +85.29; 772: +16.06; 773: +228.7; 774: +197.8; 775: +335.9; 776: +42.73 | +151.1 [+16.06, +335.9] | 6 / 0 / 0 | 2/64 as extreme; means [-151.1, +151.1] |
| cw5_t0_food_in_deficit: Food into the turn-0 deficit regions by trade (T - R; sensitivity) | p | 871: -51.83; 872: -280.7; 873: +87.1; 874: -233.9; 875: -82.29; 876: +331.2 | -38.41 [-280.7, +331.2] | 2 / 4 / 0 | 48/64 as extreme; means [-177.9, +177.9] |
| cw5_t0_shortfall_deficit: Food shortfall share in the turn-0 deficit regions (T - R; sensitivity) | t | 771: +0.01207; 772: +0.04543; 773: -0.02859; 774: +0.02348; 775: +0.03161; 776: -0.01765 | +0.01106 [-0.02859, +0.04543] | 4 / 2 / 0 | 26/64 as extreme; means [-0.02647, +0.02647] |
| cw5_t0_shortfall_deficit: Food shortfall share in the turn-0 deficit regions (T - R; sensitivity) | p | 871: -0.004022; 872: +0.001776; 873: -0.002273; 874: -0.007616; 875: -0.001644; 876: +0.005007 | -0.001462 [-0.007616, +0.005007] | 2 / 4 / 0 | 30/64 as extreme; means [-0.003723, +0.003723] |
| cw5_rr_food_in_deficit: Food into the deficit regions of R's whole-run production ratio by trade (T - R; sensitivity, regression-to-the-mean risk) | t | 771: +239.2; 772: +181; 773: +228.7; 774: +673.9; 775: +335.9; 776: +42.73 | +283.6 [+42.73, +673.9] | 6 / 0 / 0 | 2/64 as extreme; means [-283.6, +283.6] |
| cw5_rr_food_in_deficit: Food into the deficit regions of R's whole-run production ratio by trade (T - R; sensitivity, regression-to-the-mean risk) | p | 871: +172.9; 872: +174.9; 873: +285.9; 874: +556.8; 875: +387.5; 876: +424.5 | +333.7 [+172.9, +556.8] | 6 / 0 / 0 | 2/64 as extreme; means [-333.7, +333.7] |
| cw5_rr_shortfall_deficit: Food shortfall share in the deficit regions of R's whole-run production ratio (T - R; sensitivity, regression-to-the-mean risk) | t | 771: +0.009311; 772: +0.04252; 773: -0.0302; 774: +0.0283; 775: +0.03161; 776: -0.02491 | +0.009438 [-0.0302, +0.04252] | 4 / 2 / 0 | 28/64 as extreme; means [-0.02781, +0.02781] |
| cw5_rr_shortfall_deficit: Food shortfall share in the deficit regions of R's whole-run production ratio (T - R; sensitivity, regression-to-the-mean risk) | p | 871: -0.04823; 872: +0.002417; 873: -0.008498; 874: +0.006053; 875: -0.01391; 876: -0.0177 | -0.01331 [-0.04823, +0.006053] | 2 / 4 / 0 | 8/64 as extreme; means [-0.01613, +0.01613] |
| cw5_shortfall_surplus: Food shortfall share after relief in the surplus regions (T - R) | t | 771: -0.01895; 772: +0.01399; 773: excluded by the window; 774: -0.02566; 775: excluded by the window; 776: -0.03072 | -0.01533 [-0.03072, +0.01399] | 1 / 3 / 0 | 4/16 as extreme; means [-0.02233, +0.02233] |
| cw5_shortfall_surplus: Food shortfall share after relief in the surplus regions (T - R) | p | 871: +0.005951; 872: +0.01345; 873: +0.002036; 874: -0.0115; 875: +0.005979; 876: excluded by the window | +0.003183 [-0.0115, +0.01345] | 4 / 1 / 0 | 14/32 as extreme; means [-0.007785, +0.007785] |
| cw5_price_surplus: Mean retail price in the surplus regions (T - R) | t | 771: -42.4; 772: +2.177; 773: excluded by the window; 774: -38.39; 775: excluded by the window; 776: -30.74 | -27.34 [-42.4, +2.177] | 1 / 3 / 0 | 4/16 as extreme; means [-28.42, +28.42] |
| cw5_price_surplus: Mean retail price in the surplus regions (T - R) | p | 871: +28.19; 872: -20.89; 873: +48.36; 874: -39.98; 875: +40.38; 876: excluded by the window | +11.21 [-39.98, +48.36] | 3 / 2 / 0 | 16/32 as extreme; means [-35.56, +35.56] |
| cw5_priced_out_surplus: Priced-out person-turns in the surplus regions (T - R) | t | 771: -6; 772: +30; 773: excluded by the window; 774: -85; 775: excluded by the window; 776: +108 | +11.75 [-85, +108] | 2 / 2 / 0 | 12/16 as extreme; means [-57.25, +57.25] |
| cw5_priced_out_surplus: Priced-out person-turns in the surplus regions (T - R) | p | 871: -396; 872: +14; 873: -63; 874: +9; 875: +126; 876: excluded by the window | -62 [-396, +126] | 3 / 2 / 0 | 24/32 as extreme; means [-121.6, +121.6] |
| cw5_food_in_surplus: Food into the surplus regions by trade (T - R) | t | 771: -174; 772: -98.82; 773: excluded by the window; 774: -367.4; 775: excluded by the window; 776: -86.06 | -181.6 [-367.4, -86.06] | 0 / 4 / 0 | 2/16 as extreme; means [-181.6, +181.6] |
| cw5_food_in_surplus: Food into the surplus regions by trade (T - R) | p | 871: +104.2; 872: -55.62; 873: -167.6; 874: -280.4; 875: -117.7; 876: excluded by the window | -103.4 [-280.4, +104.2] | 1 / 4 / 0 | 6/32 as extreme; means [-145.1, +145.1] |
| cw5_shortfall_origin: Food shortfall share in the regions T bought from (T; selection) | t | 771: +0.1129; 772: +0.1843; 773: +0.1682; 774: +0.1146; 775: +0.1645; 776: +0.3027 | +0.1745 [+0.1129, +0.3027] | 6 / 0 / 0 | n/a (no control) |
| cw5_shortfall_origin: Food shortfall share in the regions T bought from (T; selection) | p | 871: +0.1591; 872: +0.1097; 873: +0.09219; 874: +0.09223; 875: +0.06839; 876: +0.1184 | +0.1067 [+0.06839, +0.1591] | 6 / 0 / 0 | n/a (no control) |
| cw5_shortfall_all: Food shortfall share after relief, all regions (T - R) | t | 771: -0.003245; 772: +0.02818; 773: +0.005056; 774: +0.004748; 775: +0.01617; 776: -0.01369 | +0.006203 [-0.01369, +0.02818] | 4 / 2 / 0 | 22/64 as extreme; means [-0.01185, +0.01185] |
| cw5_shortfall_all: Food shortfall share after relief, all regions (T - R) | p | 871: -0.009161; 872: +0.009359; 873: -0.004459; 874: -0.001665; 875: +0.0005553; 876: -0.01106 | -0.002739 [-0.01106, +0.009359] | 2 / 4 / 0 | 24/64 as extreme; means [-0.006044, +0.006044] |
| cw5_dispatched: Titled shipments bought (T) | t | 771: +336; 772: +285; 773: +215; 774: +598; 775: +256; 776: +83 | +295.5 [+83, +598] | 6 / 0 / 0 | n/a (no control) |
| cw5_dispatched: Titled shipments bought (T) | p | 871: +382; 872: +641; 873: +592; 874: +891; 875: +843; 876: +699 | +674.7 [+382, +891] | 6 / 0 / 0 | n/a (no control) |
| cw5_delivered: Titled shipments delivered (T) | t | 771: +322; 772: +269; 773: +207; 774: +570; 775: +251; 776: +82 | +283.5 [+82, +570] | 6 / 0 / 0 | n/a (no control) |
| cw5_delivered: Titled shipments delivered (T) | p | 871: +365; 872: +586; 873: +551; 874: +855; 875: +791; 876: +655 | +633.8 [+365, +855] | 6 / 0 / 0 | n/a (no control) |
| cw5_released_returned: Shipments returned after a carrier's release (T) | t | 771: +0; 772: +0; 773: +0; 774: +0; 775: +0; 776: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw5_released_returned: Shipments returned after a carrier's release (T) | p | 871: +0; 872: +0; 873: +0; 874: +0; 875: +0; 876: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw5_returned_route: Shipments returned because the route was lost (T) | t | 771: +0; 772: +0; 773: +0; 774: +2; 775: +0; 776: +0 | +0.3333 [+0, +2] | 1 / 0 / 5 | n/a (no control) |
| cw5_returned_route: Shipments returned because the route was lost (T) | p | 871: +1; 872: +6; 873: +11; 874: +0; 875: +9; 876: +9 | +6 [+0, +11] | 5 / 0 / 1 | n/a (no control) |
| cw5_returned_conquest: Shipments returned because the destination was conquered (T) | t | 771: +0; 772: +0; 773: +0; 774: +0; 775: +0; 776: +0 | +0 [+0, +0] | 0 / 0 / 6 | n/a (no control) |
| cw5_returned_conquest: Shipments returned because the destination was conquered (T) | p | 871: +1; 872: +0; 873: +0; 874: +4; 875: +2; 876: +0 | +1.167 [+0, +4] | 3 / 0 / 3 | n/a (no control) |
| cw5_escheated: Shipments escheated at the holder's death (T) | t | 771: +10; 772: +10; 773: +6; 774: +22; 775: +4; 776: +1 | +8.833 [+1, +22] | 6 / 0 / 0 | n/a (no control) |
| cw5_escheated: Shipments escheated at the holder's death (T) | p | 871: +13; 872: +37; 873: +20; 874: +24; 875: +31; 876: +31 | +26 [+13, +37] | 6 / 0 / 0 | n/a (no control) |
| cw5_margin: Merchants' realized margin on titled cargo, wealth units (T) | t | 771: +162.6; 772: +200.5; 773: +127.8; 774: +305.3; 775: +263.1; 776: +56.54 | +186 [+56.54, +305.3] | 6 / 0 / 0 | n/a (no control) |
| cw5_margin: Merchants' realized margin on titled cargo, wealth units (T) | p | 871: +261.1; 872: +319.9; 873: +155.2; 874: +521.3; 875: +427.6; 876: +363.9 | +341.5 [+155.2, +521.3] | 6 / 0 / 0 | n/a (no control) |
| cw5_withheld: Model income withheld from carriers, wealth units (T) | t | 771: +17.72; 772: +19.96; 773: +17.86; 774: +53.08; 775: +0.5383; 776: +0.6079 | +18.29 [+0.5383, +53.08] | 6 / 0 / 0 | n/a (no control) |
| cw5_withheld: Model income withheld from carriers, wealth units (T) | p | 871: +40.07; 872: +72.83; 873: +11.33; 874: +94.65; 875: +35.82; 876: +88.42 | +57.19 [+11.33, +94.65] | 6 / 0 / 0 | n/a (no control) |
| cw5_owner_receipts: Owners paid for their surplus food, wealth units (T) | t | 771: +223.3; 772: +202.2; 773: +145.7; 774: +436.8; 775: +192.6; 776: +48.87 | +208.2 [+48.87, +436.8] | 6 / 0 / 0 | n/a (no control) |
| cw5_owner_receipts: Owners paid for their surplus food, wealth units (T) | p | 871: +291; 872: +413.6; 873: +407.8; 874: +595.8; 875: +700.5; 876: +458.3 | +477.9 [+291, +700.5] | 6 / 0 / 0 | n/a (no control) |
| cw5_food_purchases: Households' food purchases credited to sellers, units (T - R) | t | 771: +165.8; 772: +349.4; 773: +396.7; 774: +438.7; 775: +373; 776: +137.3 | +310.2 [+137.3, +438.7] | 6 / 0 / 0 | 2/64 as extreme; means [-310.2, +310.2] |
| cw5_food_purchases: Households' food purchases credited to sellers, units (T - R) | p | 871: +710.7; 872: +1088; 873: +2.193; 874: +641; 875: +1794; 876: +378.4 | +769.1 [+2.193, +1794] | 6 / 0 / 0 | 2/64 as extreme; means [-769.1, +769.1] |
| cw5_transit_decay: Titled food lost to transit decay, food units (T) | t | 771: +19.34; 772: +18.62; 773: +13.95; 774: +40.92; 775: +18.6; 776: +4.747 | +19.36 [+4.747, +40.92] | 6 / 0 / 0 | n/a (no control) |
| cw5_transit_decay: Titled food lost to transit decay, food units (T) | p | 871: +22.91; 872: +32.87; 873: +36.55; 874: +59.69; 875: +53.45; 876: +36.87 | +40.39 [+22.91, +59.69] | 6 / 0 / 0 | n/a (no control) |
| cw5_region_turns: Region-turns with a titled shipment (T; activation) | t | 771: +395; 772: +412; 773: +340; 774: +613; 775: +282; 776: +99 | +356.8 [+99, +613] | 6 / 0 / 0 | n/a (no control) |
| cw5_region_turns: Region-turns with a titled shipment (T; activation) | p | 871: +778; 872: +1176; 873: +1028; 874: +1524; 875: +1341; 876: +1324 | +1195 [+778, +1524] | 6 / 0 / 0 | n/a (no control) |
| cw5_h_commons: Commons food at the end, world (T - R) | t | 771: +2.008; 772: +0.385; 773: -0.0005438; 774: +0; 775: +0; 776: -0.072 | +0.3867 [-0.072, +2.008] | 2 / 2 / 2 | 32/64 as extreme; means [-0.4109, +0.4109] |
| cw5_h_commons: Commons food at the end, world (T - R) | p | 871: +0; 872: -5.405; 873: +0.49; 874: +3.182; 875: -3.559; 876: +1.461 | -0.6385 [-5.405, +3.182] | 3 / 2 / 1 | 44/64 as extreme; means [-2.35, +2.35] |
| cw5_h_food_shortfall: Food shortfall after relief over the run, world (T - R) | t | 771: -125; 772: +801.2; 773: +258.8; 774: +229.7; 775: +669.1; 776: -34.93 | +299.8 [-125, +801.2] | 4 / 2 / 0 | 8/64 as extreme; means [-353.1, +353.1] |
| cw5_h_food_shortfall: Food shortfall after relief over the run, world (T - R) | p | 871: -390.8; 872: +780.2; 873: -398.1; 874: -181.6; 875: +499.1; 876: -108.3 | +33.42 [-398.1, +780.2] | 2 / 4 / 0 | 58/64 as extreme; means [-393, +393] |
| cw5_h_priced_out: Priced-out person-turns, world (T - R) | t | 771: -37; 772: +105; 773: -132; 774: -178; 775: +285; 776: +295 | +56.33 [-178, +295] | 3 / 3 / 0 | 36/64 as extreme; means [-172, +172] |
| cw5_h_priced_out: Priced-out person-turns, world (T - R) | p | 871: +25; 872: +193; 873: -338; 874: +12; 875: +298; 876: +29 | +36.5 [-338, +298] | 5 / 1 / 0 | 44/64 as extreme; means [-149.2, +149.2] |
| cw5_h_treasury: Treasury at the end (T - R) | t | 771: +85; 772: +355; 773: -31; 774: -938; 775: +1314; 776: -516 | +44.83 [-938, +1314] | 3 / 3 / 0 | 60/64 as extreme; means [-539.8, +539.8] |
| cw5_h_treasury: Treasury at the end (T - R) | p | 871: +4293; 872: +277; 873: +2289; 874: +1039; 875: +2451; 876: +2301 | +2108 [+277, +4293] | 6 / 0 / 0 | 2/64 as extreme; means [-2108, +2108] |
| cw5_h_stability: Mean stability of living civilizations at the end (T - R) | t | 771: +3; 772: +2; 773: +17.75; 774: +3.917; 775: +16.83; 776: +19 | +10.42 [+2, +19] | 6 / 0 / 0 | 2/64 as extreme; means [-10.42, +10.42] |
| cw5_h_stability: Mean stability of living civilizations at the end (T - R) | p | 871: -6.833; 872: -12.7; 873: +4.529; 874: +1.286; 875: +0; 876: -0.8 | -2.419 [-12.7, +4.529] | 2 / 3 / 1 | 28/64 as extreme; means [-4.357, +4.357] |
| cw5_h_population: Population at the end (T - R) | t | 771: -25; 772: -3; 773: +37; 774: +29; 775: +43; 776: +27 | +18 [-25, +43] | 4 / 2 / 0 | 10/64 as extreme; means [-27.33, +27.33] |
| cw5_h_population: Population at the end (T - R) | p | 871: -22; 872: -20; 873: -3; 874: +52; 875: +137; 876: +149 | +48.83 [-22, +149] | 3 / 3 / 0 | 16/64 as extreme; means [-63.83, +63.83] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T - R | Population at the end (sum over civilizations) | t | 771: -25; 772: -3; 773: +37; 774: +29; 775: +43; 776: +27 | +18 [-25, +43] | 4 / 2 / 0 | 10/64 as extreme; means [-27.33, +27.33] | recorded |
| T - R | Population at the end (sum over civilizations) | p | 871: -22; 872: -20; 873: -3; 874: +52; 875: +137; 876: +149 | +48.83 [-22, +149] | 3 / 3 / 0 | 16/64 as extreme; means [-63.83, +63.83] | recorded |
| T - R | Treasury at the end (sum over civilizations) | t | 771: +85; 772: +355; 773: -31; 774: -938; 775: +1314; 776: -516 | +44.83 [-938, +1314] | 3 / 3 / 0 | 60/64 as extreme; means [-539.8, +539.8] | recorded |
| T - R | Treasury at the end (sum over civilizations) | p | 871: +4293; 872: +277; 873: +2289; 874: +1039; 875: +2451; 876: +2301 | +2108 [+277, +4293] | 6 / 0 / 0 | 2/64 as extreme; means [-2108, +2108] | recorded |
| T - R | Food shortfall after relief over the run (food) | t | 771: -125; 772: +801.2; 773: +258.8; 774: +229.7; 775: +669.1; 776: -34.93 | +299.8 [-125, +801.2] | 4 / 2 / 0 | 8/64 as extreme; means [-353.1, +353.1] | recorded |
| T - R | Food shortfall after relief over the run (food) | p | 871: -390.8; 872: +780.2; 873: -398.1; 874: -181.6; 875: +499.1; 876: -108.3 | +33.42 [-398.1, +780.2] | 2 / 4 / 0 | 58/64 as extreme; means [-393, +393] | recorded |
| T - R | Priced-out person-turns | t | 771: -37; 772: +105; 773: -132; 774: -178; 775: +285; 776: +295 | +56.33 [-178, +295] | 3 / 3 / 0 | 36/64 as extreme; means [-172, +172] | recorded |
| T - R | Priced-out person-turns | p | 871: +25; 872: +193; 873: -338; 874: +12; 875: +298; 876: +29 | +36.5 [-338, +298] | 5 / 1 / 0 | 44/64 as extreme; means [-149.2, +149.2] | recorded |
| T - R | Priced-out child-turns | t | 771: +21; 772: +34; 773: +7; 774: -16; 775: +2; 776: +35 | +13.83 [-16, +35] | 5 / 1 / 0 | 10/64 as extreme; means [-19.17, +19.17] | recorded |
| T - R | Priced-out child-turns | p | 871: +50; 872: +61; 873: -11; 874: +133; 875: +44; 876: +32 | +51.5 [-11, +133] | 5 / 1 / 0 | 4/64 as extreme; means [-55.17, +55.17] | recorded |
| T - R | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| T - R | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| T - R | Deaths by epidemic (the epidemic authority) | t | 771: +86; 772: -23; 773: +73; 774: +89; 775: +6; 776: -22 | +34.83 [-23, +89] | 4 / 2 / 0 | 14/64 as extreme; means [-49.83, +49.83] | recorded |
| T - R | Deaths by epidemic (the epidemic authority) | p | 871: +58; 872: -6; 873: +12; 874: -28; 875: -28; 876: +196 | +34 [-28, +196] | 3 / 3 / 0 | 30/64 as extreme; means [-54.67, +54.67] | recorded |
| T - R | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| T - R | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| T - R | Agents migrating between regions over the run | t | 771: +185; 772: -116; 773: +553; 774: +474; 775: +64; 776: +153 | +218.8 [-116, +553] | 5 / 1 / 0 | 6/64 as extreme; means [-257.5, +257.5] | recorded |
| T - R | Agents migrating between regions over the run | p | 871: +57; 872: +377; 873: +459; 874: +1095; 875: +125; 876: +190 | +383.8 [+57, +1095] | 6 / 0 / 0 | 2/64 as extreme; means [-383.8, +383.8] | recorded |
| T - R | Mean wealth Gini of living civilizations at the end | t | 771: -0.03328; 772: -0.0407; 773: +0.04559; 774: +0.1947; 775: +0.1355; 776: -0.02422 | +0.04627 [-0.0407, +0.1947] | 3 / 3 / 0 | 24/64 as extreme; means [-0.07901, +0.07901] | recorded |
| T - R | Mean wealth Gini of living civilizations at the end | p | 871: +0.03499; 872: -0.04964; 873: +0.07615; 874: -0.004436; 875: +0.033; 876: -0.05588 | +0.005698 [-0.05588, +0.07615] | 3 / 3 / 0 | 50/64 as extreme; means [-0.04235, +0.04235] | recorded |
| T - R | Timber stand share of capacity at the end | t | 771: not recorded; 772: not recorded; 773: not recorded; 774: not recorded; 775: not recorded; 776: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| T - R | Timber stand share of capacity at the end | p | 871: not recorded; 872: not recorded; 873: not recorded; 874: not recorded; 875: not recorded; 876: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| R | 10.0 [8.3, 14.5] | 22.9 [19.0, 25.5] |
| T | 11.9 [8.9, 16.7] | 27.6 [22.9, 34.5] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
