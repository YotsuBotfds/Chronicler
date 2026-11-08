#!/usr/bin/env python3
"""Constructed checker regressions; no simulation, native import or held data."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("cwr_independent", Path(__file__).with_name("check.py"))
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)
SOURCE = "a" * 40
LINES = [f"source {SOURCE}", "dirty 0 tracked files", "dirty-code 0 tracked code files",
         "chronicler /synthetic/src/chronicler/__init__.py", f"native /synthetic/native.so {C.NATIVE}",
         "interpreter /synthetic/python", f"runner {'b' * 64} scripts/screen_runner.py",
         f"screens {'c' * 64} scripts/cw_rework_screen.py", f"registry {'d' * 64} scripts/seed_registry.json",
         f"registry-content {'e' * 64} (cohorts and seeds)"]
TEXT = "\n".join(LINES) + "\nrun: screen CWR1; cohort pilot; synthetic fixture\n"
IDENTITY = hashlib.sha256("\n".join(LINES).encode()).hexdigest()


def fixture():
    rows = []
    for index, (arm, (mode, channel, crowding, _health, retail)) in enumerate(C.ARMS.items()):
        for tag, seeds in C.SEEDS["pilot"].items():
            seed = seeds[0]
            regions = {"t": 8, "p": 32}[tag]
            metrics = {key: 0 for key in C.SUPPORTING}
            metrics.update(turns=120, regions=regions, seed=seed, person_turns=12000,
                           world_person_turns=12000, world_infectious_pt=100,
                           food_shortfall=200 + 10 * index, epidemic_deaths=10 + index,
                           world_epidemic_deaths=10 + index, deaths=20, all_migrations=20,
                           unknown_migration_drivers=10, unknown_migration_share=.5,
                           native_food_produced=100, native_food_consumed=80, public_relief_food=2,
                           retail_access_unknown_region_turns=0, retail_deficit_observed=4,
                           retail_access_deficit=4, retail_free_rations_observed=2,
                           retail_free_pool_observed=3,
                           retail_priority_household_turns=0 if retail == "no_relief" else 1,
                           retail_free_to_priority_observed=0 if retail == "no_relief" else 1,
                           a6_personal_rows=0 if mode == "record_only" or channel == "no_migration_experience" else 5,
                           d3_input_rows=3, combined_migration_input_rows=3,
                           combined_native_choice_changes=2,
                           a6_offer_declines=0 if mode == "record_only" or channel == "no_work" else 2,
                           a6_information_turns=0 if mode == "record_only" or channel == "no_information" else 120,
                           trade_unknown_destination=0, trade_personal_return_refusal=0,
                           added_crowding_factor_sum=0 if crowding == "density_only" else 2,
                           arrival_complete_region_turns=100 * regions,
                           arrival_incomplete_region_turns=19 * regions,
                           arrival_unknown_region_turns=regions,
                           merge_validated_turns=120, merge_truncated_turns=0,
                           event_sidecar={"present": True, "migration": 20, "unknown": 10, "deaths": 20,
                                          "bytes": 1, "sha256": "f" * 64})
            metrics.update(food_shortfall_per_1000_pt=1000 * metrics["food_shortfall"] / 12000,
                           epidemic_deaths_per_1000_pt=1000 * metrics["epidemic_deaths"] / 12000,
                           world_deaths_per_ipt=metrics["epidemic_deaths"] / 100,
                           deaths_per_1000_pt=1000 * 20 / 12000)
            harm = {key: {"state": "recorded", "value": 1} for key in
                    ("population", "treasury", "priced_out_persons", "priced_out_children", "wealth_gini")}
            harm.update({key: {"state": "requires_slice_extractor", "value": None}
                         for key in ("deaths_famine", "deaths_war")})
            harm.update(food_shortfall={"state": "recorded", "value": metrics["food_shortfall"]},
                        deaths_epidemic={"state": "recorded", "value": metrics["epidemic_deaths"]},
                        out_migration={"state": "recorded", "value": 20},
                        forest_stand={"state": "not_recorded", "value": None})
            rows.append({"screen": "CWR1", "cohort": "pilot", "arm": arm, "stratum": tag, "seed": seed,
                         "rc": 0, "pk": {}, "identity": IDENTITY, "wall_s": 1, "extract_s": .1,
                         "activation": {"activated": None, "evidence": "root arm"} if arm == "RD" else
                            {"activated": True, "evidence": "Every enrolled world enters; actual mechanism activation is reported separately"},
                         "schemas": {"bundle": 6, "livelihoods": [1], "packages": {key: [1] for key in
                            ("adaptive_livelihoods", "public_health", "residence_ledger", "household_retail",
                             "war_consequences", "war_requisition", "wealth_accounting", "timber_orders")},
                            "records": {"food_accounting": [1], "regional_population": [1]}},
                         "m": metrics, "harm": harm})
    return rows


def run(rows, **kwargs):
    return C.audit(rows, TEXT, "pilot", SOURCE, C.NATIVE, draws=16, **kwargs)


class CheckerTests(unittest.TestCase):
    def test_complete_pilot_positive_free_food_and_d3_record_only_are_valid(self):
        result = run(fixture())
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["primaries"]["cwr_food:t"]["worlds"][0]["value"], 10)
        self.assertEqual(result["primaries"]["cwr_epidemic:p"]["worlds"][0]["value"], 1)
        self.assertEqual(result["primaries"]["cwr_crowding_interaction:t"]["worlds"][0]["value"], 0)
        self.assertAlmostEqual(result["pilot_held_projection_with_1_5_margin"], 24 * 1.1 * 9 / 3600)

    def test_mutations_fail_and_withhold_incomplete_world_summaries(self):
        for mutation in ("duplicate", "missing", "failure", "horizon", "metric_seed", "denominator", "famine_zero",
                         "density_crowding", "personal_off", "work_off", "trade_off", "info_off", "access_unknown",
                         "schema", "sidecar", "null_harm", "bad_regions", "unknown_ratio", "malformed_row"):
            with self.subTest(mutation=mutation):
                rows = fixture()
                row = next(r for r in rows if r["arm"] == "RD" and r["stratum"] == "t")
                if mutation == "duplicate": rows.append(deepcopy(row))
                elif mutation == "missing": rows.remove(row)
                elif mutation == "failure": row["rc"] = 3
                elif mutation == "horizon": row["m"]["turns"] = 119
                elif mutation == "metric_seed": row["m"]["seed"] = 6
                elif mutation == "denominator": row["m"]["food_shortfall_per_1000_pt"] = 0
                elif mutation == "famine_zero": row["harm"]["deaths_famine"] = {"state": "recorded", "value": 0}
                elif mutation == "density_crowding": row["m"]["added_crowding_factor_sum"] = .1
                elif mutation == "personal_off": row["m"]["a6_personal_rows"] = 1
                elif mutation == "work_off": row["m"]["a6_offer_declines"] = 1
                elif mutation == "trade_off": row["m"]["trade_unknown_destination"] = 1
                elif mutation == "info_off": row["m"]["a6_information_turns"] = 120
                elif mutation == "access_unknown": row["m"]["retail_access_unknown_region_turns"] = 1
                elif mutation == "schema": row["schemas"]["packages"]["adaptive_livelihoods"] = [2]
                elif mutation == "sidecar": row["m"]["event_sidecar"] = None
                elif mutation == "null_harm": row["harm"]["deaths_war"] = None
                elif mutation == "bad_regions": row["m"]["regions"] = None
                elif mutation == "unknown_ratio": row["m"]["unknown_migration_share"] = 0
                else: rows[0] = None
                result = run(rows)
                self.assertEqual(result["status"], "FAIL")
                self.assertTrue(result["errors"])
                self.assertIsNone(result["primaries"]["cwr_food:t"]["summary"])

    def test_cardinalities_cannot_be_fractional_but_food_and_infectious_time_can(self):
        for metric in ("person_turns", "unknown_migration_drivers", "retail_access_unknown_region_turns",
                       "a6_personal_rows", "retail_priority_household_turns", "arrival_complete_region_turns"):
            with self.subTest(metric=metric):
                rows = fixture()
                rows[0]["m"][metric] = .5
                self.assertEqual(run(rows)["status"], "FAIL")
        rows = fixture()
        row = rows[0]
        row["m"].update(world_infectious_pt=100.5, world_deaths_per_ipt=row["m"]["epidemic_deaths"] / 100.5,
                        retail_free_pool_observed=3.25, retail_free_rations_observed=2.75)
        self.assertEqual(run(rows)["status"], "PASS")

    def test_source_identity_failure_precedes_effect_summary(self):
        result = C.audit(fixture(), TEXT, "pilot", "b" * 40, C.NATIVE, draws=16)
        self.assertEqual(result["status"], "FAIL")
        self.assertIsNone(result["primaries"]["cwr_food:t"]["summary"])

    def test_legitimate_unknown_access_is_retained_without_dropping_world(self):
        rows = fixture()
        rows[0]["m"].update(retail_access_unknown_region_turns=1, retail_access_deficit=None)
        result = run(rows)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["primaries"]["cwr_food:t"]["complete"])
        access = result["supporting"]["AD-RD:retail_access_deficit:t"]
        self.assertFalse(access["complete"])
        self.assertIsNone(access["summary"])
        self.assertEqual(access["worlds"][0]["value"], None)

    def test_zero_infectious_denominator_remains_null(self):
        rows = fixture()
        row = rows[0]
        row["m"].update(epidemic_deaths=0, world_epidemic_deaths=0, world_infectious_pt=0,
                        epidemic_deaths_per_1000_pt=0, world_deaths_per_ipt=None)
        row["harm"]["deaths_epidemic"]["value"] = 0
        self.assertEqual(run(rows)["status"], "PASS")
        row["m"]["world_deaths_per_ipt"] = 0
        self.assertEqual(run(rows)["status"], "FAIL")

    def test_descriptive_signs_and_analysis_rng(self):
        result = C.describe([1] * 6, draws=16)
        self.assertEqual((result["sign_flip_extreme"], result["sign_flip_assignments"]), (2, 64))
        self.assertEqual(result["bootstrap_95"], [1, 1])
        self.assertEqual(C.describe([-1, 1], draws=16)["sign_flip_extreme"], 4)
        self.assertEqual(C.describe([0] * 6, draws=16)["sign_flip_extreme"], 64)

    def test_frozen_held_protocol_and_registry_source_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            (checkout / "scripts").mkdir()
            (checkout / "scripts/screen_runner.py").write_text("synthetic generic runner bytes")
            (checkout / "scripts/cw_rework_screen.py").write_text("synthetic screen bytes")
            registry = {"restricted_ranges": {"both": [[1000, 1999]], "template": [[42, 241]], "procedural": [[42, 141]]},
                        "entries": []}
            for stratum, tag in (("template", "t"), ("procedural", "p")):
                seeds = C.SEEDS["held"][tag]
                registry["entries"].append({"id": f"held-{tag}", "stratum": stratum, "seeds": [[seeds[0], seeds[-1]]],
                    "cohort": "held", "screen": "CWR1", "status": "reserved"})
                registry["entries"].append({"id": f"pilot-{tag}", "stratum": stratum, "seeds": list(C.SEEDS["pilot"][tag]),
                    "cohort": "pilot", "screen": None, "status": "reserved"})
            registry_path = checkout / "scripts/seed_registry.json"
            registry_path.write_text(json.dumps(registry))
            protocol = checkout / "protocol.md"
            protocol_text = "Status: FROZEN\nCompute ceiling: 2.0 core-hours\nPrimary outcomes: cwr_food, cwr_epidemic, cwr_crowding_interaction\n"
            protocol.write_text(protocol_text)
            lines = [line for line in LINES if not line.startswith(("runner ", "screens ", "registry ", "registry-content "))]
            lines += [f"runner {C.sha(checkout / 'scripts/screen_runner.py')} scripts/screen_runner.py",
                      f"screens {C.sha(checkout / 'scripts/cw_rework_screen.py')} scripts/cw_rework_screen.py",
                      f"registry {C.sha(registry_path)} scripts/seed_registry.json",
                      f"registry-content {C.registry_content(registry)} (cohorts and seeds)",
                      f"preregistration {C.sha(protocol)} protocol.md"]
            identity = hashlib.sha256("\n".join(lines).encode()).hexdigest()
            text = "\n".join(lines) + "\nrun: synthetic held fixture\n"
            rows = []
            for original in fixture():
                for seed in C.SEEDS["held"][original["stratum"]]:
                    row = deepcopy(original)
                    row.update(cohort="held", seed=seed, identity=identity)
                    row["m"]["seed"] = seed
                    rows.append(row)
            result = C.audit(rows, text, "held", SOURCE, C.NATIVE, checkout, protocol, draws=16)
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["observed_rows"], 144)
            self.assertEqual(result["primaries"]["cwr_epidemic:t"]["summary"]["sign_flip_extreme"], 2)
            protocol.write_text(protocol_text.replace("FROZEN", "DRAFT"))
            self.assertEqual(C.audit(rows, text, "held", SOURCE, C.NATIVE, checkout, protocol, draws=16)["status"], "FAIL")
            protocol.write_text(protocol_text)
            (checkout / "scripts/cw_rework_screen.py").write_text("different source")
            self.assertEqual(C.audit(rows, text, "held", SOURCE, C.NATIVE, checkout, protocol, draws=16)["status"], "FAIL")
            registry["entries"].append({"id": "collision", "stratum": "template", "seeds": [4101]})
            self.assertTrue(C.reservation_errors(registry))

    def test_primary_report_rendering_is_independently_checked(self):
        result = run(fixture())
        lines = []
        for key, record in result["primaries"].items():
            outcome, tag = key.split(":")
            d = record["summary"]
            worlds = "; ".join(f"{r['seed']}: {r['value']:+.4g}" for r in record["worlds"])
            lines.append(f"| {outcome}: synthetic label | {tag} | {worlds} | {d['mean']:+.4g} "
                         f"[{d['min']:+.4g}, {d['max']:+.4g}] | {d['positive']} / {d['negative']} / {d['zero']} | "
                         f"{d['sign_flip_extreme']}/{d['sign_flip_assignments']} as extreme; means "
                         f"[{d['sign_flip_min']:+.4g}, {d['sign_flip_max']:+.4g}] |")
        text = "\n".join(lines)
        self.assertEqual(C.check_primary_report(text, result), ([], 6))
        errors, checked = C.check_primary_report(text.replace("5: +10", "5: -10"), result)
        self.assertTrue(errors)
        self.assertEqual(checked, 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
