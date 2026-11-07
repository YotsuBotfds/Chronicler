# CW2: S2 workshop economics and the owned-output rule (A3-1, A3-2)

Cohort pilot. Runs: 10; failed: 0 (missing outcomes: 0); simulation and extraction seconds 307 (0.085 core-hours)
Projected held run time from this pilot: 0.512 core-hours (x1.5 = 0.768) for 60 runs

Identity digests: f0d08bbcb6a5272750db5bfa8a06079314f4e49f652bfe3d62035958fb592ceb (source.txt holds the lines)
Schema versions read: {"bundle": 6, "livelihoods": [1], "packages": {"wealth_accounting": [1], "workshop_economics": [1], "workshop_payroll": [1], "workshops": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}; {"bundle": 6, "livelihoods": [1], "packages": {"wealth_accounting": [1], "workshop_payroll": [1], "workshops": [1]}, "records": {"food_accounting": [1], "regional_population": [1]}}

## Activation per world (before any effect)

| Arm | Stratum | Per world | Activated |
| --- | --- | --- | --- |
| E1 | t | 5: activated | 1 of 1 |
| E1 | p | 19: activated | 1 of 1 |
| E2 | t | 5: activated | 1 of 1 |
| E2 | p | 19: activated | 1 of 1 |
| E2f | t | 5: activated | 1 of 1 |
| E2f | p | 19: activated | 1 of 1 |
| E2a | t | 5: activated | 1 of 1 |
| E2a | p | 19: activated | 1 of 1 |

## Primary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw2_active_share: Share of firm-turns since opening in which the firm produced or sold (idle and closed turns count against it) (E2 - E1) | t | 5: -0.261 | -0.261 [-0.261, -0.261] | 0 / 1 / 0 | 2/2 as extreme; means [-0.261, +0.261] |
| cw2_active_share: Share of firm-turns since opening in which the firm produced or sold (idle and closed turns count against it) (E2 - E1) | p | 19: +0.0704 | +0.0704 [+0.0704, +0.0704] | 1 / 0 / 0 | 2/2 as extreme; means [-0.0704, +0.0704] |
| cw2_wages: Workshop wages credited to households over the run, units (A1 ledger) (E2 - P) | t | 5: +2.825 | +2.825 [+2.825, +2.825] | 1 / 0 / 0 | 2/2 as extreme; means [-2.825, +2.825] |
| cw2_wages: Workshop wages credited to households over the run, units (A1 ledger) (E2 - P) | p | 19: +123.5 | +123.5 [+123.5, +123.5] | 1 / 0 / 0 | 2/2 as extreme; means [-123.5, +123.5] |
| cw2_wares_sold: Wares sold to households over the run, loads (E2 - E1) | t | 5: -29.29 | -29.29 [-29.29, -29.29] | 0 / 1 / 0 | 2/2 as extreme; means [-29.29, +29.29] |
| cw2_wares_sold: Wares sold to households over the run, loads (E2 - E1) | p | 19: +2.429 | +2.429 [+2.429, +2.429] | 1 / 0 / 0 | 2/2 as extreme; means [-2.429, +2.429] |

## Secondary outcomes (arm minus control on each world; non-activated worlds excluded)

| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |
| --- | --- | --- | --- | --- | --- |
| cw2_free_use_e1: Firm output the people could draw free from the commons before title, upper bound, loads (E1; rules 1 only, none in E2) | t | 5: +1.344 | +1.344 [+1.344, +1.344] | 1 / 0 / 0 | n/a (no control) |
| cw2_free_use_e1: Firm output the people could draw free from the commons before title, upper bound, loads (E1; rules 1 only, none in E2) | p | 19: +16.16 | +16.16 [+16.16, +16.16] | 1 / 0 / 0 | n/a (no control) |
| cw2_active_share_p: Active share of firm-turns (E2 - P; worlds where L6a opens a firm) | t | 5: -0.05187 | -0.05187 [-0.05187, -0.05187] | 0 / 1 / 0 | 2/2 as extreme; means [-0.05187, +0.05187] |
| cw2_active_share_p: Active share of firm-turns (E2 - P; worlds where L6a opens a firm) | p | 19: unknown | n/a | 0 / 0 / 0 | n/a |
| cw2_active_turns: Active firm-turns, produced or sold (E2 - P; defined on every world) | t | 5: +22 | +22 [+22, +22] | 1 / 0 / 0 | 2/2 as extreme; means [-22, +22] |
| cw2_active_turns: Active firm-turns, produced or sold (E2 - P; defined on every world) | p | 19: +557 | +557 [+557, +557] | 1 / 0 / 0 | 2/2 as extreme; means [-557, +557] |
| cw2_active_share_e1: Active share of firm-turns (E1 - P) | t | 5: +0.2091 | +0.2091 [+0.2091, +0.2091] | 1 / 0 / 0 | 2/2 as extreme; means [-0.2091, +0.2091] |
| cw2_active_share_e1: Active share of firm-turns (E1 - P) | p | 19: unknown | n/a | 0 / 0 / 0 | n/a |
| cw2_wages_e1: Workshop wages credited (E1 - P) | t | 5: +16.27 | +16.27 [+16.27, +16.27] | 1 / 0 / 0 | 2/2 as extreme; means [-16.27, +16.27] |
| cw2_wages_e1: Workshop wages credited (E1 - P) | p | 19: +104.9 | +104.9 [+104.9, +104.9] | 1 / 0 / 0 | 2/2 as extreme; means [-104.9, +104.9] |
| cw2_wages_rules: Workshop wages credited (E2 - E1) | t | 5: -13.45 | -13.45 [-13.45, -13.45] | 0 / 1 / 0 | 2/2 as extreme; means [-13.45, +13.45] |
| cw2_wages_rules: Workshop wages credited (E2 - E1) | p | 19: +18.6 | +18.6 [+18.6, +18.6] | 1 / 0 / 0 | 2/2 as extreme; means [-18.6, +18.6] |
| cw2_paid_rules: Households' money paid for wares, units (E2 - E1) | t | 5: -21.84 | -21.84 [-21.84, -21.84] | 0 / 1 / 0 | 2/2 as extreme; means [-21.84, +21.84] |
| cw2_paid_rules: Households' money paid for wares, units (E2 - E1) | p | 19: -28.18 | -28.18 [-28.18, -28.18] | 0 / 1 / 0 | 2/2 as extreme; means [-28.18, +28.18] |
| cw2_price_rules: Households' price per load of wares (E2 - E1; rules 2 counts the firm's stock in the supply that sets it) | t | 5: -0.3121 | -0.3121 [-0.3121, -0.3121] | 0 / 1 / 0 | 2/2 as extreme; means [-0.3121, +0.3121] |
| cw2_price_rules: Households' price per load of wares (E2 - E1; rules 2 counts the firm's stock in the supply that sets it) | p | 19: -0.1752 | -0.1752 [-0.1752, -0.1752] | 0 / 1 / 0 | 2/2 as extreme; means [-0.1752, +0.1752] |
| cw2_firms_rules: Firms opened (E2 - E1) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw2_firms_rules: Firms opened (E2 - E1) | p | 19: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] |
| cw2_closed_idle_rules: Firms closed idle (E2 - E1) | t | 5: +1 | +1 [+1, +1] | 1 / 0 / 0 | 2/2 as extreme; means [-1, +1] |
| cw2_closed_idle_rules: Firms closed idle (E2 - E1) | p | 19: -3 | -3 [-3, -3] | 0 / 1 / 0 | 2/2 as extreme; means [-3, +3] |
| cw2_net_income: Households' net income from firm work: wages credited less the model income they replaced, wealth units (E2 - P) | t | 5: +2.531 | +2.531 [+2.531, +2.531] | 1 / 0 / 0 | 2/2 as extreme; means [-2.531, +2.531] |
| cw2_net_income: Households' net income from firm work: wages credited less the model income they replaced, wealth units (E2 - P) | p | 19: +103.5 | +103.5 [+103.5, +103.5] | 1 / 0 / 0 | 2/2 as extreme; means [-103.5, +103.5] |
| cw2_academy: Wares sold to academies, loads (E2 - P) | t | 5: -4.423 | -4.423 [-4.423, -4.423] | 0 / 1 / 0 | 2/2 as extreme; means [-4.423, +4.423] |
| cw2_academy: Wares sold to academies, loads (E2 - P) | p | 19: +193 | +193 [+193, +193] | 1 / 0 / 0 | 2/2 as extreme; means [-193, +193] |
| cw2_firms: Firms opened (E2 - P) | t | 5: +1 | +1 [+1, +1] | 1 / 0 / 0 | 2/2 as extreme; means [-1, +1] |
| cw2_firms: Firms opened (E2 - P) | p | 19: +12 | +12 [+12, +12] | 1 / 0 / 0 | 2/2 as extreme; means [-12, +12] |
| cw2_cost_active: Active share of firm-turns (E2 - E2f: the input cost) | t | 5: +0.3566 | +0.3566 [+0.3566, +0.3566] | 1 / 0 / 0 | 2/2 as extreme; means [-0.3566, +0.3566] |
| cw2_cost_active: Active share of firm-turns (E2 - E2f: the input cost) | p | 19: +0.2718 | +0.2718 [+0.2718, +0.2718] | 1 / 0 / 0 | 2/2 as extreme; means [-0.2718, +0.2718] |
| cw2_cost_firms: Firms opened (E2f - E2) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw2_cost_firms: Firms opened (E2f - E2) | p | 19: -6 | -6 [-6, -6] | 0 / 1 / 0 | 2/2 as extreme; means [-6, +6] |
| cw2_cost_closed_idle: Firms closed idle (E2f - E2) | t | 5: -2 | -2 [-2, -2] | 0 / 1 / 0 | 2/2 as extreme; means [-2, +2] |
| cw2_cost_closed_idle: Firms closed idle (E2f - E2) | p | 19: -5 | -5 [-5, -5] | 0 / 1 / 0 | 2/2 as extreme; means [-5, +5] |
| cw2_cost_sold: Wares sold to households (E2f - E2; diagnostic) | t | 5: +40.77 | +40.77 [+40.77, +40.77] | 1 / 0 / 0 | 2/2 as extreme; means [-40.77, +40.77] |
| cw2_cost_sold: Wares sold to households (E2f - E2; diagnostic) | p | 19: +80.77 | +80.77 [+80.77, +80.77] | 1 / 0 / 0 | 2/2 as extreme; means [-80.77, +80.77] |
| cw2_cost_wages: Workshop wages credited (E2f - E2) | t | 5: +20 | +20 [+20, +20] | 1 / 0 / 0 | 2/2 as extreme; means [-20, +20] |
| cw2_cost_wages: Workshop wages credited (E2f - E2) | p | 19: -31.05 | -31.05 [-31.05, -31.05] | 0 / 1 / 0 | 2/2 as extreme; means [-31.05, +31.05] |
| cw2_cost_treasury: Treasury at the end (E2f - E2) | t | 5: -134 | -134 [-134, -134] | 0 / 1 / 0 | 2/2 as extreme; means [-134, +134] |
| cw2_cost_treasury: Treasury at the end (E2f - E2) | p | 19: -26 | -26 [-26, -26] | 0 / 1 / 0 | 2/2 as extreme; means [-26, +26] |
| cw2_collapse_active: Active share of firm-turns (E2a - E2: no household demand) | t | 5: -0.08409 | -0.08409 [-0.08409, -0.08409] | 0 / 1 / 0 | 2/2 as extreme; means [-0.08409, +0.08409] |
| cw2_collapse_active: Active share of firm-turns (E2a - E2: no household demand) | p | 19: -0.2557 | -0.2557 [-0.2557, -0.2557] | 0 / 1 / 0 | 2/2 as extreme; means [-0.2557, +0.2557] |
| cw2_collapse_closed_idle: Firms closed idle (E2a - E2) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw2_collapse_closed_idle: Firms closed idle (E2a - E2) | p | 19: +5 | +5 [+5, +5] | 1 / 0 / 0 | 2/2 as extreme; means [-5, +5] |
| cw2_collapse_wages: Workshop wages credited (E2a - E2) | t | 5: +0.35 | +0.35 [+0.35, +0.35] | 1 / 0 / 0 | 2/2 as extreme; means [-0.35, +0.35] |
| cw2_collapse_wages: Workshop wages credited (E2a - E2) | p | 19: -0.7 | -0.7 [-0.7, -0.7] | 0 / 1 / 0 | 2/2 as extreme; means [-0.7, +0.7] |
| cw2_collapse_unsold: Unsold firm inventory at the end, loads (E2a - E2) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw2_collapse_unsold: Unsold firm inventory at the end, loads (E2a - E2) | p | 19: -12.01 | -12.01 [-12.01, -12.01] | 0 / 1 / 0 | 2/2 as extreme; means [-12.01, +12.01] |
| cw2_collapse_liquidation: Wares handed to the owner at liquidation, loads (E2a - E2) | t | 5: +22.81 | +22.81 [+22.81, +22.81] | 1 / 0 / 0 | 2/2 as extreme; means [-22.81, +22.81] |
| cw2_collapse_liquidation: Wares handed to the owner at liquidation, loads (E2a - E2) | p | 19: +88 | +88 [+88, +88] | 1 / 0 / 0 | 2/2 as extreme; means [-88, +88] |
| cw2_producing_e2: Share of firm-turns producing (E2) | t | 5: +0.09044 | +0.09044 [+0.09044, +0.09044] | 1 / 0 / 0 | n/a (no control) |
| cw2_producing_e2: Share of firm-turns producing (E2) | p | 19: +0.3204 | +0.3204 [+0.3204, +0.3204] | 1 / 0 / 0 | n/a (no control) |
| cw2_selling_e2: Share of firm-turns selling (E2) | t | 5: +0.1473 | +0.1473 [+0.1473, +0.1473] | 1 / 0 / 0 | n/a (no control) |
| cw2_selling_e2: Share of firm-turns selling (E2) | p | 19: +0.4057 | +0.4057 [+0.4057, +0.4057] | 1 / 0 / 0 | n/a (no control) |
| cw2_idle_e2: Share of firm-turns idle (E2) | t | 5: +0.03876 | +0.03876 [+0.03876, +0.03876] | 1 / 0 / 0 | n/a (no control) |
| cw2_idle_e2: Share of firm-turns idle (E2) | p | 19: +0.06362 | +0.06362 [+0.06362, +0.06362] | 1 / 0 / 0 | n/a (no control) |
| cw2_closed_share_e2: Share of firm-turns closed (E2) | t | 5: +0.7984 | +0.7984 [+0.7984, +0.7984] | 1 / 0 / 0 | n/a (no control) |
| cw2_closed_share_e2: Share of firm-turns closed (E2) | p | 19: +0.5043 | +0.5043 [+0.5043, +0.5043] | 1 / 0 / 0 | n/a (no control) |
| cw2_closed_idle_e2: Firms closed idle (E2) | t | 5: +3 | +3 [+3, +3] | 1 / 0 / 0 | n/a (no control) |
| cw2_closed_idle_e2: Firms closed idle (E2) | p | 19: +7 | +7 [+7, +7] | 1 / 0 / 0 | n/a (no control) |
| cw2_closed_insolvent_e2: Firms closed insolvent (E2) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw2_closed_insolvent_e2: Firms closed insolvent (E2) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw2_closed_city_fell_e2: Firms closed when their city fell (E2) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw2_closed_city_fell_e2: Firms closed when their city fell (E2) | p | 19: +1 | +1 [+1, +1] | 1 / 0 / 0 | n/a (no control) |
| cw2_liquidation_e2: Wares handed to the owner at liquidation, loads (E2) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw2_liquidation_e2: Wares handed to the owner at liquidation, loads (E2) | p | 19: +23.95 | +23.95 [+23.95, +23.95] | 1 / 0 / 0 | n/a (no control) |
| cw2_inputs_charged_e2: Inputs bought from the commons owner, units (E2; never free) | t | 5: +8.707 | +8.707 [+8.707, +8.707] | 1 / 0 / 0 | n/a (no control) |
| cw2_inputs_charged_e2: Inputs bought from the commons owner, units (E2; never free) | p | 19: +284.1 | +284.1 [+284.1, +284.1] | 1 / 0 / 0 | n/a (no control) |
| cw2_owned_output_e2: Owned output titled whole, loads (E2) | t | 5: +21.46 | +21.46 [+21.46, +21.46] | 1 / 0 / 0 | n/a (no control) |
| cw2_owned_output_e2: Owned output titled whole, loads (E2) | p | 19: +417.5 | +417.5 [+417.5, +417.5] | 1 / 0 / 0 | n/a (no control) |
| cw2_h_food_shortfall: Food shortfall after relief over the run (E2 - P) | t | 5: +400.4 | +400.4 [+400.4, +400.4] | 1 / 0 / 0 | 2/2 as extreme; means [-400.4, +400.4] |
| cw2_h_food_shortfall: Food shortfall after relief over the run (E2 - P) | p | 19: +2673 | +2673 [+2673, +2673] | 1 / 0 / 0 | 2/2 as extreme; means [-2673, +2673] |
| cw2_h_wage_arrears: Wages due but not paid over the run, units (E2 - P) | t | 5: -0.925 | -0.925 [-0.925, -0.925] | 0 / 1 / 0 | 2/2 as extreme; means [-0.925, +0.925] |
| cw2_h_wage_arrears: Wages due but not paid over the run, units (E2 - P) | p | 19: +2.7 | +2.7 [+2.7, +2.7] | 1 / 0 / 0 | 2/2 as extreme; means [-2.7, +2.7] |
| cw2_h_asset_arrears: Workshop asset arrears at the end (E2 - P) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw2_h_asset_arrears: Workshop asset arrears at the end (E2 - P) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw2_h_unsold: Unsold firm inventory at the end, loads (E2 - P) | t | 5: -0.182 | -0.182 [-0.182, -0.182] | 0 / 1 / 0 | 2/2 as extreme; means [-0.182, +0.182] |
| cw2_h_unsold: Unsold firm inventory at the end, loads (E2 - P) | p | 19: +12.12 | +12.12 [+12.12, +12.12] | 1 / 0 / 0 | 2/2 as extreme; means [-12.12, +12.12] |
| cw2_h_priced_out: Household-turns priced out of firm wares (E2 - E1; none recorded in P) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw2_h_priced_out: Household-turns priced out of firm wares (E2 - E1; none recorded in P) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | 2/2 as extreme; means [+0, +0] |
| cw2_h_priced_out_e2: Household-turns priced out of firm wares (E2) | t | 5: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw2_h_priced_out_e2: Household-turns priced out of firm wares (E2) | p | 19: +0 | +0 [+0, +0] | 0 / 0 / 1 | n/a (no control) |
| cw2_h_farm_time: Farm time diverted to crews, work units (E2 - P) | t | 5: -92.13 | -92.13 [-92.13, -92.13] | 0 / 1 / 0 | 2/2 as extreme; means [-92.13, +92.13] |
| cw2_h_farm_time: Farm time diverted to crews, work units (E2 - P) | p | 19: -74.36 | -74.36 [-74.36, -74.36] | 0 / 1 / 0 | 2/2 as extreme; means [-74.36, +74.36] |
| cw2_h_treasury: Treasury at the end (E2 - P) | t | 5: -13 | -13 [-13, -13] | 0 / 1 / 0 | 2/2 as extreme; means [-13, +13] |
| cw2_h_treasury: Treasury at the end (E2 - P) | p | 19: +2940 | +2940 [+2940, +2940] | 1 / 0 / 0 | 2/2 as extreme; means [-2940, +2940] |
| cw2_h_stability: Mean stability of living civilizations at the end (E2 - P) | t | 5: +2 | +2 [+2, +2] | 1 / 0 / 0 | 2/2 as extreme; means [-2, +2] |
| cw2_h_stability: Mean stability of living civilizations at the end (E2 - P) | p | 19: +2.182 | +2.182 [+2.182, +2.182] | 1 / 0 / 0 | 2/2 as extreme; means [-2.182, +2.182] |
| cw2_h_population: Population at the end (E2 - P) | t | 5: +24 | +24 [+24, +24] | 1 / 0 / 0 | 2/2 as extreme; means [-24, +24] |
| cw2_h_population: Population at the end (E2 - P) | p | 19: -9 | -9 [-9, -9] | 0 / 1 / 0 | 2/2 as extreme; means [-9, +9] |

## Harm panel beside every comparison (each arm minus its control; non-activated worlds excluded)

| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E1 - P | Population at the end (sum over civilizations) | t | 5: -13 | -13 [-13, -13] | 0 / 1 / 0 | 2/2 as extreme; means [-13, +13] | recorded |
| E1 - P | Population at the end (sum over civilizations) | p | 19: -8 | -8 [-8, -8] | 0 / 1 / 0 | 2/2 as extreme; means [-8, +8] | recorded |
| E1 - P | Treasury at the end (sum over civilizations) | t | 5: -508 | -508 [-508, -508] | 0 / 1 / 0 | 2/2 as extreme; means [-508, +508] | recorded |
| E1 - P | Treasury at the end (sum over civilizations) | p | 19: +2806 | +2806 [+2806, +2806] | 1 / 0 / 0 | 2/2 as extreme; means [-2806, +2806] | recorded |
| E1 - P | Food shortfall after relief over the run (food) | t | 5: -183.4 | -183.4 [-183.4, -183.4] | 0 / 1 / 0 | 2/2 as extreme; means [-183.4, +183.4] | recorded |
| E1 - P | Food shortfall after relief over the run (food) | p | 19: +1835 | +1835 [+1835, +1835] | 1 / 0 / 0 | 2/2 as extreme; means [-1835, +1835] | recorded |
| E1 - P | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E1 - P | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E1 - P | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E1 - P | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E1 - P | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E1 - P | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E1 - P | Deaths by epidemic (the epidemic authority) | t | 5: -26 | -26 [-26, -26] | 0 / 1 / 0 | 2/2 as extreme; means [-26, +26] | recorded |
| E1 - P | Deaths by epidemic (the epidemic authority) | p | 19: +7 | +7 [+7, +7] | 1 / 0 / 0 | 2/2 as extreme; means [-7, +7] | recorded |
| E1 - P | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E1 - P | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E1 - P | Agents migrating between regions over the run | t | 5: -52 | -52 [-52, -52] | 0 / 1 / 0 | 2/2 as extreme; means [-52, +52] | recorded |
| E1 - P | Agents migrating between regions over the run | p | 19: +2070 | +2070 [+2070, +2070] | 1 / 0 / 0 | 2/2 as extreme; means [-2070, +2070] | recorded |
| E1 - P | Mean wealth Gini of living civilizations at the end | t | 5: -0.3373 | -0.3373 [-0.3373, -0.3373] | 0 / 1 / 0 | 2/2 as extreme; means [-0.3373, +0.3373] | recorded |
| E1 - P | Mean wealth Gini of living civilizations at the end | p | 19: -0.04012 | -0.04012 [-0.04012, -0.04012] | 0 / 1 / 0 | 2/2 as extreme; means [-0.04012, +0.04012] | recorded |
| E1 - P | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E1 - P | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2 - E1 | Population at the end (sum over civilizations) | t | 5: +37 | +37 [+37, +37] | 1 / 0 / 0 | 2/2 as extreme; means [-37, +37] | recorded |
| E2 - E1 | Population at the end (sum over civilizations) | p | 19: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] | recorded |
| E2 - E1 | Treasury at the end (sum over civilizations) | t | 5: +495 | +495 [+495, +495] | 1 / 0 / 0 | 2/2 as extreme; means [-495, +495] | recorded |
| E2 - E1 | Treasury at the end (sum over civilizations) | p | 19: +134 | +134 [+134, +134] | 1 / 0 / 0 | 2/2 as extreme; means [-134, +134] | recorded |
| E2 - E1 | Food shortfall after relief over the run (food) | t | 5: +583.8 | +583.8 [+583.8, +583.8] | 1 / 0 / 0 | 2/2 as extreme; means [-583.8, +583.8] | recorded |
| E2 - E1 | Food shortfall after relief over the run (food) | p | 19: +838.6 | +838.6 [+838.6, +838.6] | 1 / 0 / 0 | 2/2 as extreme; means [-838.6, +838.6] | recorded |
| E2 - E1 | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - E1 | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - E1 | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - E1 | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - E1 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2 - E1 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2 - E1 | Deaths by epidemic (the epidemic authority) | t | 5: -1 | -1 [-1, -1] | 0 / 1 / 0 | 2/2 as extreme; means [-1, +1] | recorded |
| E2 - E1 | Deaths by epidemic (the epidemic authority) | p | 19: -70 | -70 [-70, -70] | 0 / 1 / 0 | 2/2 as extreme; means [-70, +70] | recorded |
| E2 - E1 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2 - E1 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2 - E1 | Agents migrating between regions over the run | t | 5: +313 | +313 [+313, +313] | 1 / 0 / 0 | 2/2 as extreme; means [-313, +313] | recorded |
| E2 - E1 | Agents migrating between regions over the run | p | 19: +544 | +544 [+544, +544] | 1 / 0 / 0 | 2/2 as extreme; means [-544, +544] | recorded |
| E2 - E1 | Mean wealth Gini of living civilizations at the end | t | 5: +0.3446 | +0.3446 [+0.3446, +0.3446] | 1 / 0 / 0 | 2/2 as extreme; means [-0.3446, +0.3446] | recorded |
| E2 - E1 | Mean wealth Gini of living civilizations at the end | p | 19: -0.03187 | -0.03187 [-0.03187, -0.03187] | 0 / 1 / 0 | 2/2 as extreme; means [-0.03187, +0.03187] | recorded |
| E2 - E1 | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2 - E1 | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2f - E2 | Population at the end (sum over civilizations) | t | 5: -2 | -2 [-2, -2] | 0 / 1 / 0 | 2/2 as extreme; means [-2, +2] | recorded |
| E2f - E2 | Population at the end (sum over civilizations) | p | 19: +48 | +48 [+48, +48] | 1 / 0 / 0 | 2/2 as extreme; means [-48, +48] | recorded |
| E2f - E2 | Treasury at the end (sum over civilizations) | t | 5: -134 | -134 [-134, -134] | 0 / 1 / 0 | 2/2 as extreme; means [-134, +134] | recorded |
| E2f - E2 | Treasury at the end (sum over civilizations) | p | 19: -26 | -26 [-26, -26] | 0 / 1 / 0 | 2/2 as extreme; means [-26, +26] | recorded |
| E2f - E2 | Food shortfall after relief over the run (food) | t | 5: -833.6 | -833.6 [-833.6, -833.6] | 0 / 1 / 0 | 2/2 as extreme; means [-833.6, +833.6] | recorded |
| E2f - E2 | Food shortfall after relief over the run (food) | p | 19: -440.4 | -440.4 [-440.4, -440.4] | 0 / 1 / 0 | 2/2 as extreme; means [-440.4, +440.4] | recorded |
| E2f - E2 | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2f - E2 | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2f - E2 | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2f - E2 | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2f - E2 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2f - E2 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2f - E2 | Deaths by epidemic (the epidemic authority) | t | 5: +4 | +4 [+4, +4] | 1 / 0 / 0 | 2/2 as extreme; means [-4, +4] | recorded |
| E2f - E2 | Deaths by epidemic (the epidemic authority) | p | 19: +97 | +97 [+97, +97] | 1 / 0 / 0 | 2/2 as extreme; means [-97, +97] | recorded |
| E2f - E2 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2f - E2 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2f - E2 | Agents migrating between regions over the run | t | 5: -236 | -236 [-236, -236] | 0 / 1 / 0 | 2/2 as extreme; means [-236, +236] | recorded |
| E2f - E2 | Agents migrating between regions over the run | p | 19: +831 | +831 [+831, +831] | 1 / 0 / 0 | 2/2 as extreme; means [-831, +831] | recorded |
| E2f - E2 | Mean wealth Gini of living civilizations at the end | t | 5: -0.002602 | -0.002602 [-0.002602, -0.002602] | 0 / 1 / 0 | 2/2 as extreme; means [-0.002602, +0.002602] | recorded |
| E2f - E2 | Mean wealth Gini of living civilizations at the end | p | 19: +0.09953 | +0.09953 [+0.09953, +0.09953] | 1 / 0 / 0 | 2/2 as extreme; means [-0.09953, +0.09953] | recorded |
| E2f - E2 | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2f - E2 | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2a - E2 | Population at the end (sum over civilizations) | t | 5: -20 | -20 [-20, -20] | 0 / 1 / 0 | 2/2 as extreme; means [-20, +20] | recorded |
| E2a - E2 | Population at the end (sum over civilizations) | p | 19: -46 | -46 [-46, -46] | 0 / 1 / 0 | 2/2 as extreme; means [-46, +46] | recorded |
| E2a - E2 | Treasury at the end (sum over civilizations) | t | 5: -236 | -236 [-236, -236] | 0 / 1 / 0 | 2/2 as extreme; means [-236, +236] | recorded |
| E2a - E2 | Treasury at the end (sum over civilizations) | p | 19: +47 | +47 [+47, +47] | 1 / 0 / 0 | 2/2 as extreme; means [-47, +47] | recorded |
| E2a - E2 | Food shortfall after relief over the run (food) | t | 5: -543.4 | -543.4 [-543.4, -543.4] | 0 / 1 / 0 | 2/2 as extreme; means [-543.4, +543.4] | recorded |
| E2a - E2 | Food shortfall after relief over the run (food) | p | 19: -596.5 | -596.5 [-596.5, -596.5] | 0 / 1 / 0 | 2/2 as extreme; means [-596.5, +596.5] | recorded |
| E2a - E2 | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2a - E2 | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2a - E2 | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2a - E2 | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2a - E2 | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2a - E2 | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2a - E2 | Deaths by epidemic (the epidemic authority) | t | 5: +53 | +53 [+53, +53] | 1 / 0 / 0 | 2/2 as extreme; means [-53, +53] | recorded |
| E2a - E2 | Deaths by epidemic (the epidemic authority) | p | 19: +66 | +66 [+66, +66] | 1 / 0 / 0 | 2/2 as extreme; means [-66, +66] | recorded |
| E2a - E2 | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2a - E2 | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2a - E2 | Agents migrating between regions over the run | t | 5: -57 | -57 [-57, -57] | 0 / 1 / 0 | 2/2 as extreme; means [-57, +57] | recorded |
| E2a - E2 | Agents migrating between regions over the run | p | 19: -983 | -983 [-983, -983] | 0 / 1 / 0 | 2/2 as extreme; means [-983, +983] | recorded |
| E2a - E2 | Mean wealth Gini of living civilizations at the end | t | 5: -0.144 | -0.144 [-0.144, -0.144] | 0 / 1 / 0 | 2/2 as extreme; means [-0.144, +0.144] | recorded |
| E2a - E2 | Mean wealth Gini of living civilizations at the end | p | 19: +0.1221 | +0.1221 [+0.1221, +0.1221] | 1 / 0 / 0 | 2/2 as extreme; means [-0.1221, +0.1221] | recorded |
| E2a - E2 | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2a - E2 | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2 - P | Population at the end (sum over civilizations) | t | 5: +24 | +24 [+24, +24] | 1 / 0 / 0 | 2/2 as extreme; means [-24, +24] | recorded |
| E2 - P | Population at the end (sum over civilizations) | p | 19: -9 | -9 [-9, -9] | 0 / 1 / 0 | 2/2 as extreme; means [-9, +9] | recorded |
| E2 - P | Treasury at the end (sum over civilizations) | t | 5: -13 | -13 [-13, -13] | 0 / 1 / 0 | 2/2 as extreme; means [-13, +13] | recorded |
| E2 - P | Treasury at the end (sum over civilizations) | p | 19: +2940 | +2940 [+2940, +2940] | 1 / 0 / 0 | 2/2 as extreme; means [-2940, +2940] | recorded |
| E2 - P | Food shortfall after relief over the run (food) | t | 5: +400.4 | +400.4 [+400.4, +400.4] | 1 / 0 / 0 | 2/2 as extreme; means [-400.4, +400.4] | recorded |
| E2 - P | Food shortfall after relief over the run (food) | p | 19: +2673 | +2673 [+2673, +2673] | 1 / 0 / 0 | 2/2 as extreme; means [-2673, +2673] | recorded |
| E2 - P | Priced-out person-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - P | Priced-out person-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - P | Priced-out child-turns | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - P | Priced-out child-turns | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (household retail is off in this run (no priced-out frames)) |
| E2 - P | Deaths by famine (the famine authority) | t | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2 - P | Deaths by famine (the famine authority) | p | requires slice extractor | n/a | n/a | n/a | the slice that records deaths by authority (A1-A2 accounting or E) |
| E2 - P | Deaths by epidemic (the epidemic authority) | t | 5: -27 | -27 [-27, -27] | 0 / 1 / 0 | 2/2 as extreme; means [-27, +27] | recorded |
| E2 - P | Deaths by epidemic (the epidemic authority) | p | 19: -63 | -63 [-63, -63] | 0 / 1 / 0 | 2/2 as extreme; means [-63, +63] | recorded |
| E2 - P | Deaths by war (the casualty authority) | t | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2 - P | Deaths by war (the casualty authority) | p | requires slice extractor | n/a | n/a | n/a | slice D3 (war's human consequences) |
| E2 - P | Agents migrating between regions over the run | t | 5: +261 | +261 [+261, +261] | 1 / 0 / 0 | 2/2 as extreme; means [-261, +261] | recorded |
| E2 - P | Agents migrating between regions over the run | p | 19: +2614 | +2614 [+2614, +2614] | 1 / 0 / 0 | 2/2 as extreme; means [-2614, +2614] | recorded |
| E2 - P | Mean wealth Gini of living civilizations at the end | t | 5: +0.007241 | +0.007241 [+0.007241, +0.007241] | 1 / 0 / 0 | 2/2 as extreme; means [-0.007241, +0.007241] | recorded |
| E2 - P | Mean wealth Gini of living civilizations at the end | p | 19: -0.07199 | -0.07199 [-0.07199, -0.07199] | 0 / 1 / 0 | 2/2 as extreme; means [-0.07199, +0.07199] | recorded |
| E2 - P | Timber stand share of capacity at the end | t | 5: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |
| E2 - P | Timber stand share of capacity at the end | p | 19: not recorded | n/a | 0 / 0 / 0 | n/a | not_recorded (the timber stock is off in this run (no stand record)) |

## Run time per arm (simulation and extraction seconds per run: mean [min, max])

| Arm | t | p |
| --- | --- | --- |
| P | 7.5 [7.5, 7.5] | 58.5 [58.5, 58.5] |
| E1 | 15.8 [15.8, 15.8] | 61.4 [61.4, 61.4] |
| E2 | 11.7 [11.7, 11.7] | 50.6 [50.6, 50.6] |
| E2f | 12.2 [12.2, 12.2] | 49.1 [49.1, 49.1] |
| E2a | 10.2 [10.2, 10.2] | 30.4 [30.4, 30.4] |

Descriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as far from zero as the observed mean, with the range of those means; it is not a significance test.
