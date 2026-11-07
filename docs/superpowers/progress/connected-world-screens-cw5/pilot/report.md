# CW5: S4 titled trade (A4-1)

Cohort pilot. Runs: 4; failed: 0 (missing outcomes: 0); simulation and extraction seconds 67 (0.019 core-hours)
Projected held run time from this pilot: 0.111 core-hours (x1.5 = 0.167) for 24 runs

Identity digests: e251c4286d26e1e1f493e6f0eeef4ecf11cf4654230cd4de3eec9015a1316cb1 (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"food_allocation": [1], "household_retail": [1], "titled_trade": [1], "wealth_accounting": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"food_allocation": [1], "household_retail": [1], "wealth_accounting": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| T | t | 5: activated | 1 of 1 |
| T | p | 19: activated | 1 of 1 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5_food_in_deficit: Food into the deficit regions by trade over the run: titled cargo in less titled cargo bought there, plus native commons trade, food units (T - R) | t | 5: +58.06 | +58.06 [+58.06, +58.06] | 1 / 0 / 0 | 2/2 as extreme; means [-58.06, +58.06] |
| cw5_food_in_deficit: Food into the deficit regions by trade over the run: titled cargo in less titled cargo bought there, plus native commons trade, food units (T - R) | p | 19: -270.6 | -270.6 [-270.6, -270.6] | 0 / 1 / 0 | 2/2 as extreme; means [-270.6, +270.6] |
| cw5_shortfall_deficit: Food shortfall share after relief in the deficit regions (T - R) | t | 5: -0.02101 | -0.02101 [-0.02101, -0.02101] | 0 / 1 / 0 | 2/2 as extreme; means [-0.02101, +0.02101] |
| cw5_shortfall_deficit: Food shortfall share after relief in the deficit regions (T - R) | p | 19: -0.01612 | -0.01612 [-0.01612, -0.01612] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01612, +0.01612] |
| cw5_margin_vs_withheld: Merchants' realized margin on titled cargo (sales credited less owners paid) less the model income withheld while carrying, wealth units (T) | t | 5: +18.83 | +18.83 [+18.83, +18.83] | 1 / 0 / 0 | n/a (no control) |
| cw5_margin_vs_withheld: Merchants' realized margin on titled cargo (sales credited less owners paid) less the model income withheld while carrying, wealth units (T) | p | 19: +348.5 | +348.5 [+348.5, +348.5] | 1 / 0 / 0 | n/a (no control) |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw5_titled_delivered_deficit: Titled food delivered into the deficit regions, food units (T) | t | 5: +69.17 | +69.17 [+69.17, +69.17] | 1 / 0 / 0 | n/a (no control) |
| cw5_titled_delivered_deficit: Titled food delivered into the deficit regions, food units (T) | p | 19: +180.8 | +180.8 [+180.8, +180.8] | 1 / 0 / 0 | n/a (no control) |
| cw5_titled_net_deficit: Titled food into less out of the deficit regions (T) | t | 5: +58.06 | +58.06 [+58.06, +58.06] | 1 / 0 / 0 | n/a (no control) |
| cw5_titled_net_deficit: Titled food into less out of the deficit regions (T) | p | 19: -270.6 | -270.6 [-270.6, -270.6] | 0 / 1 / 0 | n/a (no control) |
| cw5_native_net_deficit: Native commons trade into the deficit regions (T - R) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw5_native_net_deficit: Native commons trade into the deficit regions (T - R) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw5_met_deficit: Deficit regions' demand-weighted min(1, sufficiency) (T - R) | t | 5: +0.02101 | +0.02101 [+0.02101, +0.02101] | 1 / 0 / 0 | 2/2 as extreme; means [-0.02101, +0.02101] |
| cw5_met_deficit: Deficit regions' demand-weighted min(1, sufficiency) (T - R) | p | 19: +0.01612 | +0.01612 [+0.01612, +0.01612] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01612, +0.01612] |
| cw5_priced_out_deficit: Priced-out person-turns in the deficit regions (T - R) | t | 5: -84 | -84 [-84, -84] | 0 / 1 / 0 | 2/2 as extreme; means [-84, +84] |
| cw5_priced_out_deficit: Priced-out person-turns in the deficit regions (T - R) | p | 19: -247 | -247 [-247, -247] | 0 / 1 / 0 | 2/2 as extreme; means [-247, +247] |
| cw5_price_deficit: Mean retail price in the deficit regions, milli per ration (T - R) | t | 5: -62.33 | -62.33 [-62.33, -62.33] | 0 / 1 / 0 | 2/2 as extreme; means [-62.33, +62.33] |
| cw5_price_deficit: Mean retail price in the deficit regions, milli per ration (T - R) | p | 19: -14.54 | -14.54 [-14.54, -14.54] | 0 / 1 / 0 | 2/2 as extreme; means [-14.54, +14.54] |
| cw5_shortfall_dest: Food shortfall share in the regions T delivered to (T; selection) | t | 5: +0.1568 | +0.1568 [+0.1568, +0.1568] | 1 / 0 / 0 | n/a (no control) |
| cw5_shortfall_dest: Food shortfall share in the regions T delivered to (T; selection) | p | 19: +0.1376 | +0.1376 [+0.1376, +0.1376] | 1 / 0 / 0 | n/a (no control) |
| cw5_shortfall_surplus: Food shortfall share after relief in the surplus regions (T - R) | t | 5: -0.00512 | -0.00512 [-0.00512, -0.00512] | 0 / 1 / 0 | 2/2 as extreme; means [-0.00512, +0.00512] |
| cw5_shortfall_surplus: Food shortfall share after relief in the surplus regions (T - R) | p | 19: -0.0415 | -0.0415 [-0.0415, -0.0415] | 0 / 1 / 0 | 2/2 as extreme; means [-0.0415, +0.0415] |
| cw5_price_surplus: Mean retail price in the surplus regions (T - R) | t | 5: +26.28 | +26.28 [+26.28, +26.28] | 1 / 0 / 0 | 2/2 as extreme; means [-26.28, +26.28] |
| cw5_price_surplus: Mean retail price in the surplus regions (T - R) | p | 19: -1.423 | -1.423 [-1.423, -1.423] | 0 / 1 / 0 | 2/2 as extreme; means [-1.423, +1.423] |
| cw5_priced_out_surplus: Priced-out person-turns in the surplus regions (T - R) | t | 5: -17 | -17 [-17, -17] | 0 / 1 / 0 | 2/2 as extreme; means [-17, +17] |
| cw5_priced_out_surplus: Priced-out person-turns in the surplus regions (T - R) | p | 19: -334 | -334 [-334, -334] | 0 / 1 / 0 | 2/2 as extreme; means [-334, +334] |
| cw5_food_in_surplus: Food into the surplus regions by trade (T - R) | t | 5: +7.576 | +7.576 [+7.576, +7.576] | 1 / 0 / 0 | 2/2 as extreme; means [-7.576, +7.576] |
| cw5_food_in_surplus: Food into the surplus regions by trade (T - R) | p | 19: -132.4 | -132.4 [-132.4, -132.4] | 0 / 1 / 0 | 2/2 as extreme; means [-132.4, +132.4] |
| cw5_shortfall_origin: Food shortfall share in the regions T bought from (T; selection) | t | 5: +0.1488 | +0.1488 [+0.1488, +0.1488] | 1 / 0 / 0 | n/a (no control) |
| cw5_shortfall_origin: Food shortfall share in the regions T bought from (T; selection) | p | 19: +0.1141 | +0.1141 [+0.1141, +0.1141] | 1 / 0 / 0 | n/a (no control) |
| cw5_shortfall_all: Food shortfall share after relief, all regions (T - R) | t | 5: -0.0223 | -0.0223 [-0.0223, -0.0223] | 0 / 1 / 0 | 2/2 as extreme; means [-0.0223, +0.0223] |
| cw5_shortfall_all: Food shortfall share after relief, all regions (T - R) | p | 19: -0.01071 | -0.01071 [-0.01071, -0.01071] | 0 / 1 / 0 | 2/2 as extreme; means [-0.01071, +0.01071] |
| cw5_dispatched: Titled shipments bought (T) | t | 5: +111 | +111 [+111, +111] | 1 / 0 / 0 | n/a (no control) |
| cw5_dispatched: Titled shipments bought (T) | p | 19: +660 | +660 [+660, +660] | 1 / 0 / 0 | n/a (no control) |
| cw5_delivered: Titled shipments delivered (T) | t | 5: +104 | +104 [+104, +104] | 1 / 0 / 0 | n/a (no control) |
| cw5_delivered: Titled shipments delivered (T) | p | 19: +608 | +608 [+608, +608] | 1 / 0 / 0 | n/a (no control) |
| cw5_released_returned: Shipments returned after a carrier's release (T) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw5_released_returned: Shipments returned after a carrier's release (T) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw5_returned_route: Shipments returned because the route was lost (T) | t | 5: +6 | +6 [+6, +6] | 1 / 0 / 0 | n/a (no control) |
| cw5_returned_route: Shipments returned because the route was lost (T) | p | 19: +13 | +13 [+13, +13] | 1 / 0 / 0 | n/a (no control) |
| cw5_returned_conquest: Shipments returned because the destination was conquered (T) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw5_returned_conquest: Shipments returned because the destination was conquered (T) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw5_escheated: Shipments escheated at the holder's death (T) | t | 5: +1 | +1 [+1, +1] | 1 / 0 / 0 | n/a (no control) |
| cw5_escheated: Shipments escheated at the holder's death (T) | p | 19: +31 | +31 [+31, +31] | 1 / 0 / 0 | n/a (no control) |
| cw5_margin: Merchants' realized margin on titled cargo, wealth units (T) | t | 5: +22.07 | +22.07 [+22.07, +22.07] | 1 / 0 / 0 | n/a (no control) |
| cw5_margin: Merchants' realized margin on titled cargo, wealth units (T) | p | 19: +393 | +393 [+393, +393] | 1 / 0 / 0 | n/a (no control) |
| cw5_withheld: Model income withheld from carriers, wealth units (T) | t | 5: +3.242 | +3.242 [+3.242, +3.242] | 1 / 0 / 0 | n/a (no control) |
| cw5_withheld: Model income withheld from carriers, wealth units (T) | p | 19: +44.48 | +44.48 [+44.48, +44.48] | 1 / 0 / 0 | n/a (no control) |
| cw5_owner_receipts: Owners paid for their surplus food, wealth units (T) | t | 5: +53.27 | +53.27 [+53.27, +53.27] | 1 / 0 / 0 | n/a (no control) |
| cw5_owner_receipts: Owners paid for their surplus food, wealth units (T) | p | 19: +448 | +448 [+448, +448] | 1 / 0 / 0 | n/a (no control) |
| cw5_food_purchases: Households' food purchases credited to sellers, units (T - R) | t | 5: -263.7 | -263.7 [-263.7, -263.7] | 0 / 1 / 0 | 2/2 as extreme; means [-263.7, +263.7] |
| cw5_food_purchases: Households' food purchases credited to sellers, units (T - R) | p | 19: -110.2 | -110.2 [-110.2, -110.2] | 0 / 1 / 0 | 2/2 as extreme; means [-110.2, +110.2] |
| cw5_transit_decay: Titled food lost to transit decay, food units (T) | t | 5: +3.924 | +3.924 [+3.924, +3.924] | 1 / 0 / 0 | n/a (no control) |
| cw5_transit_decay: Titled food lost to transit decay, food units (T) | p | 19: +40.73 | +40.73 [+40.73, +40.73] | 1 / 0 / 0 | n/a (no control) |
| cw5_region_turns: Region-turns with a titled shipment (T; activation) | t | 5: +196 | +196 [+196, +196] | 1 / 0 / 0 | n/a (no control) |
| cw5_region_turns: Region-turns with a titled shipment (T; activation) | p | 19: +1277 | +1277 [+1277, +1277] | 1 / 0 / 0 | n/a (no control) |
| cw5_h_commons: Commons food at the end, world (T - R) | t | 5: +0.684 | +0.684 [+0.684, +0.684] | 1 / 0 / 0 | 2/2 as extreme; means [-0.684, +0.684] |
| cw5_h_commons: Commons food at the end, world (T - R) | p | 19: +1.496 | +1.496 [+1.496, +1.496] | 1 / 0 / 0 | 2/2 as extreme; means [-1.496, +1.496] |
| cw5_h_food_shortfall: Food shortfall after relief over the run, world (T - R) | t | 5: -559.9 | -559.9 [-559.9, -559.9] | 0 / 1 / 0 | 2/2 as extreme; means [-559.9, +559.9] |
| cw5_h_food_shortfall: Food shortfall after relief over the run, world (T - R) | p | 19: -688.8 | -688.8 [-688.8, -688.8] | 0 / 1 / 0 | 2/2 as extreme; means [-688.8, +688.8] |
| cw5_h_priced_out: Priced-out person-turns, world (T - R) | t | 5: -221 | -221 [-221, -221] | 0 / 1 / 0 | 2/2 as extreme; means [-221, +221] |
| cw5_h_priced_out: Priced-out person-turns, world (T - R) | p | 19: -400 | -400 [-400, -400] | 0 / 1 / 0 | 2/2 as extreme; means [-400, +400] |
| cw5_h_treasury: Treasury at the end (T - R) | t | 5: -146 | -146 [-146, -146] | 0 / 1 / 0 | 2/2 as extreme; means [-146, +146] |
| cw5_h_treasury: Treasury at the end (T - R) | p | 19: -2822 | -2822 [-2822, -2822] | 0 / 1 / 0 | 2/2 as extreme; means [-2822, +2822] |
| cw5_h_stability: Mean stability of living civilizations at the end (T - R) | t | 5: -7 | -7 [-7, -7] | 0 / 1 / 0 | 2/2 as extreme; means [-7, +7] |
| cw5_h_stability: Mean stability of living civilizations at the end (T - R) | p | 19: -4.758 | -4.758 [-4.758, -4.758] | 0 / 1 / 0 | 2/2 as extreme; means [-4.758, +4.758] |
| cw5_h_population: Population at the end (T - R) | t | 5: +1 | +1 [+1, +1] | 1 / 0 / 0 | 2/2 as extreme; means [-1, +1] |
| cw5_h_population: Population at the end (T - R) | p | 19: -36 | -36 [-36, -36] | 0 / 1 / 0 | 2/2 as extreme; means [-36, +36] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T - R | Population at the end (sum over civilizations) | t | 5: +1 | +1 [+1, +1] | 1 / 0 / 0 | 2/2 as extreme; means [-1, +1] | recorded |
| T - R | Population at the end (sum over civilizations) | p | 19: -36 | -36 [-36, -36] | 0 / 1 / 0 | 2/2 as extreme; means [-36, +36] | recorded |
| T - R | Treasury at the end (sum over civilizations) | t | 5: -146 | -146 [-146, -146] | 0 / 1 / 0 | 2/2 as extreme; means [-146, +146] | recorded |
| T - R | Treasury at the end (sum over civilizations) | p | 19: -2822 | -2822 [-2822, -2822] | 0 / 1 / 0 | 2/2 as extreme; means [-2822, +2822] | recorded |
| T - R | Food shortfall after relief over the run (food) | t | 5: -559.9 | -559.9 [-559.9, -559.9] | 0 / 1 / 0 | 2/2 as extreme; means [-559.9, +559.9] | recorded |
| T - R | Food shortfall after relief over the run (food) | p | 19: -688.8 | -688.8 [-688.8, -688.8] | 0 / 1 / 0 | 2/2 as extreme; means [-688.8, +688.8] | recorded |
| T - R | Priced-out person-turns | t | 5: -221 | -221 [-221, -221] | 0 / 1 / 0 | 2/2 as extreme; means [-221, +221] | recorded |
| T - R | Priced-out person-turns | p | 19: -400 | -400 [-400, -400] | 0 / 1 / 0 | 2/2 as extreme; means [-400, +400] | recorded |
| T - R | Priced-out child-turns | t | 5: +6 | +6 [+6, +6] | 1 / 0 / 0 | 2/2 as extreme; means [-6, +6] | recorded |
| T - R | Priced-out child-turns | p | 19: -29 | -29 [-29, -29] | 0 / 1 / 0 | 2/2 as extreme; means [-29, +29] | recorded |
| T - R | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| T - R | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| T - R | Deaths by epidemic (the epidemic authority) | t | 5: -53 | -53 [-53, -53] | 0 / 1 / 0 | 2/2 as extreme; means [-53, +53] | recorded |
| T - R | Deaths by epidemic (the epidemic authority) | p | 19: +291 | +291 [+291, +291] | 1 / 0 / 0 | 2/2 as extreme; means [-291, +291] | recorded |
| T - R | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| T - R | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| T - R | Agents migrating between regions over the run | t | 5: -347 | -347 [-347, -347] | 0 / 1 / 0 | 2/2 as extreme; means [-347, +347] | recorded |
| T - R | Agents migrating between regions over the run | p | 19: +809 | +809 [+809, +809] | 1 / 0 / 0 | 2/2 as extreme; means [-809, +809] | recorded |
| T - R | Mean wealth Gini of living civilizations at the end | t | 5: +0.01942 | +0.01942 [+0.01942, +0.01942] | 1 / 0 / 0 | 2/2 as extreme; means [-0.01942, +0.01942] | recorded |
| T - R | Mean wealth Gini of living civilizations at the end | p | 19: +0.0004949 | +0.0004949 [+0.0004949, +0.0004949] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0004949, +0.0004949] | recorded |
| T - R | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| T - R | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| R | 8.8 [8.8, 8.8] | 21.8 [21.8, 21.8] |
| T | 9.7 [9.7, 9.7] | 26.5 [26.5, 26.5] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
