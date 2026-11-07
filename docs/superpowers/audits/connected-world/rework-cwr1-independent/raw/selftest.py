#!/usr/bin/env python3
"""Constructed raw-reader mutations; no bundle/native/simulation imports."""
from collections import Counter
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("cwr_raw_check", Path(__file__).with_name("check.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def fixture(arm="AD", turns=1):
    mode, channel, crowding, health, retail = R.ARMS[arm]
    history = []
    for turn in range(turns):
        personal = [] if mode == "record_only" or channel == "no_migration_experience" else [[7, 1, -.1]]
        actual = [[7, 1, .1 if personal else .2]]
        a6 = {"schema_version": 1, "source_turn": turn, "rules": "3", "mode": mode, "decision_channels": channel,
              "counters": {}, "frame": {"turn": turn, "decision_channels": channel,
              "rows": actual, "rows_total": 1, "rows_installed": 1, "rows_dropped": 0,
              "a6_rows": personal, "a6_rows_total": len(personal), "d3_rows": [[7, 1, .2]], "d3_rows_total": 1,
              "migration_rows_would": [[7, 1, -.1]], "migration_rows_would_total": 1,
              "information_gate_installed": mode != "record_only" and channel != "no_information",
              "known_destinations": [[7, 1, 1]], "known_destinations_total": 1, "known_destinations_dropped": 0,
              "receipt": [turn, [], 1, 1], "refusals_total": 0, "refusals_dropped": 0,
              "offers": [], "work": [], "work_dropped": 0, "offers_dropped": 0, "trade_dropped": 0}}
        x1 = {"turn": turn, "arrival_diagnostics": {"window_turns": 20, "coverage_complete": True,
              "window_complete": turn >= 19, "complete": turn >= 19},
              "totals": {"observed": 2, "alive": 2, "deferred": 0, "displaced": 0,
                         "recent_residence_arrivals": 0, "recent_residence_arrivals_unknown_reason": 0},
              "regions": [{"region": r, "residents": 1, "displaced": 0, "recent_residence_arrivals": 0,
                           "recent_residence_arrivals_unknown_reason": 0} for r in range(2)]}
        ph = {"source_turn": turn, "environment_turn": turn, "mode": health, "crowding": crowding,
              "environment": [{"region": r, "source_turn": turn - 1, "residence_observed": turn > 0,
               "crowding_basis": crowding, "crowding_source_turn": turn if crowding == "density_only" else turn - 1,
               "displaced_share": 0, "crowding_factor": 1, "arrival_diagnostics_complete": None if turn == 0 else turn >= 20,
               "recent_arrival_share": 0 if turn >= 20 else None, "water_service": 0, "flux_factor": 1} for r in range(2)]}
        food_rows = []
        for rid in range(2):
            food_rows.append({"region_id": rid, "native_count": 1,
               "native": {"opening": 1, "produced": 0, "transport_net": 0, "craft_input": 0,
               "clamp_correction": 0, "pre_consumption": 1, "consumed": .5, "storage_loss": 0,
               "cap_overflow": 0, "closing": .5, "demand": .5, "sufficiency": 2,
               "balance_residual": 0, "balance_tolerance": 1.5e-5}, "sufficiency_after_relief": 2,
               "public": {"opening": 0, "released": 0, "spoiled": 0, "abandoned": 0,
                          "after_open": 0, "balance_residual": 0}})
        retail_state = {"source_turn": turn, "mode": retail, "boundary": "all", "rules_version": 2,
                        "parameters": {"theta": 1 if retail == "no_relief" else .9},
                        "regions": [{"region": r, "open_milli": 0, "close_milli": 0,
                                     "flows": {}, "provisioning": None} for r in range(2)]}
        history.append({"turn": turn + 1, "regional_population": {"source_turn": turn, "counts": [1, 1]},
             "migration": [], "food_accounting": {"source_turn": turn, "regions": food_rows},
             "epidemics": {"deaths": 0, "deaths_total": 0}, "livelihoods": {
             "wealth_accounting": {"source_turn": turn, "frame": {"turn": turn, "world": {"deaths": 0}}},
             "war_consequences": {"source_turn": turn, "mode": "active"}, "adaptive_livelihoods": a6,
             "residence_ledger": {"source_turn": turn, "frame": x1}, "public_health": ph,
             "household_retail": retail_state, "epidemic_care": {"source_turn": turn,
              "mode": "cost_only" if health == "cost_only" else "care", "tick": {"turn": turn, "regions": [], "applied": []}}}})
    return {"world_state": {"regions": [{}, {}]}, "history": history}


def verify(bundle, arm="AD"):
    return R.verify_history(bundle, arm, {"titled": 1, "sold": -1}, horizon=len(bundle["history"]))


class RawTests(unittest.TestCase):
    def test_all_declared_controls_accept_nonzero_record_only_d3(self):
        for arm in R.ARMS:
            with self.subTest(arm=arm):
                raw, _, _ = verify(fixture(arm), arm)
                self.assertEqual(raw["d3_input_rows"], 1)
                self.assertIsNone(raw["retail_access_deficit"])

    def test_control_and_source_mutations_fail(self):
        for mutation in ("a6_rules", "merge", "source", "future_ph", "same_turn_ratio", "window", "arrival_count",
                         "negative_native_count", "missing_native_count", "missing_public", "food_mint", "retail_mint"):
            with self.subTest(mutation=mutation):
                bundle = fixture()
                snap = bundle["history"][0]
                lv = snap["livelihoods"]
                if mutation == "a6_rules": lv["adaptive_livelihoods"]["rules"] = "2"
                elif mutation == "merge": lv["adaptive_livelihoods"]["frame"]["rows"][0][2] = .25
                elif mutation == "source": lv["adaptive_livelihoods"]["source_turn"] = 1
                elif mutation == "future_ph": lv["public_health"]["environment"][0]["source_turn"] = 0
                elif mutation == "same_turn_ratio": lv["public_health"]["environment"][0]["recent_arrival_share"] = 0
                elif mutation == "window": lv["residence_ledger"]["frame"]["arrival_diagnostics"].update(window_complete=True, complete=True)
                elif mutation == "arrival_count": lv["residence_ledger"]["frame"]["regions"][0]["recent_residence_arrivals"] = 2
                elif mutation == "negative_native_count": snap["food_accounting"]["regions"][0]["native_count"] = -1
                elif mutation == "missing_native_count": del snap["food_accounting"]["regions"][0]["native_count"]
                elif mutation == "missing_public": snap["food_accounting"]["regions"][0]["public"] = None
                elif mutation == "food_mint": snap["food_accounting"]["regions"][0]["native"]["closing"] += 1
                else: lv["household_retail"]["regions"][0]["close_milli"] = 1
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    verify(bundle)

    def test_capped_components_are_explicitly_unverified(self):
        bundle = fixture()
        f = bundle["history"][0]["livelihoods"]["adaptive_livelihoods"]["frame"]
        f.update(a6_rows=[[aid, 1, -.1] for aid in range(256)], a6_rows_total=257)
        raw, _, _ = verify(bundle)
        self.assertEqual(raw["merge_truncated_turns"], 1)
        self.assertEqual(raw["merge_validated_turns"], 0)

    def test_t_minus_one_window_completion_and_neutral_density(self):
        bundle = fixture(turns=21)
        raw, _, _ = verify(bundle)
        self.assertEqual(raw["arrival_complete_region_turns"], 2)
        self.assertEqual(raw["arrival_unknown_region_turns"], 2)
        # A complete current frame atT19 cannot supply that same turn's ratio.
        bundle["history"][19]["livelihoods"]["public_health"]["environment"][0]["recent_arrival_share"] = 0
        with self.assertRaises(ValueError): verify(bundle)

    def test_no_relief_retains_positive_free_food(self):
        bundle = fixture("RNR")
        p = {"region": 0, "mode": 1, "deficit": 0, "priced_out_deficit": 0, "offer_short_deficit": 0,
             "free_given": 1, "free_rations": 1, "free_unallocated": 0, "priority_households": 0,
             "free_to_priority": 0, "rations": 1, "persons": 1, "milli_food_per_ration": 500,
             "own_eaten_milli": 0, "sold_milli": 0, "unsold_milli": 0, "offered_milli": 0,
             "paid_milli": 0, "credited_milli": 0, "refunded_milli": 0}
        bundle["history"][0]["livelihoods"]["household_retail"]["regions"][0]["provisioning"] = p
        raw, _, _ = verify(bundle, "RNR")
        self.assertEqual(raw["retail_free_rations_observed"], 1)
        p["priority_households"] = 1
        with self.assertRaises(ValueError): verify(bundle, "RNR")

    def test_arrow_ids_routes_unknown_reason_and_death_are_distinct(self):
        columns = {"turn": [1, 2, 3, 4], "agent_id": [7, 7, 7, 8],
                   "event_type": ["migration", "migration", "death", "birth"],
                   "region": [0, 1, 0, 0], "target_region": [1, 0, 0, 0],
                   "migration_driver": [255, 0, 255, 255]}
        expected = Counter({(1, 0, 1): 1, (2, 1, 0): 1})
        result = R.verify_arrow(columns, {"migration", "death", "birth"}, tuple(range(20)), 2, expected, Counter({3: 1}))
        self.assertEqual((result["migration"], result["unknown"], result["deaths"]), (2, 1, 1))
        reused = deepcopy(columns)
        reused["agent_id"][-1] = 7
        with self.assertRaises(ValueError):
            R.verify_arrow(reused, {"migration", "death", "birth"}, tuple(range(20)), 2, expected, Counter({3: 1}))
        forged = deepcopy(columns)
        forged["migration_driver"][0] = 20
        with self.assertRaises(ValueError):
            R.verify_arrow(forged, {"migration", "death", "birth"}, tuple(range(20)), 2, expected, Counter({3: 1}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
