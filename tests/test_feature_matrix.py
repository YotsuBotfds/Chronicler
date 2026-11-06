"""The switch compatibility matrix and the catalog's group and exclusion extensions.

Offline: catalog only, plus the run's own configuration path
(``main._configure_run``) under sentinel runtimes for the all-enabled selections
and the prerequisite drops. No simulation runs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import types
from pathlib import Path

import pytest

from chronicler import feature_catalog as fc

ROOT = Path(__file__).resolve().parents[1]

#: The catalog served at 8abc1acb (and a955e426): its keys in order, and SHA-256 digests
#: of ``json.dumps`` of its entries, of the lobby catalog (``--live --agents hybrid`` and
#: no arguments) and of the declared requirements, all computed from the unchanged
#: module before ``FEATURE_GROUPS`` and the ``not`` condition were added.
REFERENCE_KEYS = (
    "grain_reserves", "public_grain_shipments", "grain_storage", "grain_storage_policy", "scholarship",
    "academy_services", "workshops", "workshop_mode", "food_allocation", "food_allocation_regime", "timber_stock",
    "grain_convoys", "convoy_route_policy", "commons_rules", "commons_rule_mode", "learning_cohorts",
    "learning_cohort_mode", "workshop_payroll", "workshop_payroll_mode", "relocation_costs", "relocation_mode",
    "local_budgets", "local_budget_mode", "apprenticeship", "apprenticeship_mode", "apprenticeship_rules",
    "repair_projects", "repair_mode", "veteran_reintegration", "veteran_mode", "remittances", "remittance_mode",
    "clearing_protection", "clearing_protection_mode", "operating_wear", "timber_supply", "timber_supply_mode",
    "recovery_crews", "recovery_crew_mode", "maintenance_obligation", "maintenance_obligation_mode",
    "household_retail", "household_retail_mode", "household_retail_boundary")
REFERENCE_SETTINGS = ("cities", "techniques", "no_household_mobility_liquid_requirement")
REFERENCE_DIGESTS = {
    "entries": "7dab988eb79a812b7af00c4c9b2394563cc3b12d4c13d0a30f4fd2077055455a",
    "lobby_hybrid": "71f8ba652221b9e87ca155aaee959d3a58bd72c28b945a52be0b6d6b823e4d6f",
    "lobby_none": "c361cd780192a6a27b83bb23222f19fdabf28475a45f9cab0cd8d954014a75ef",
    "requirements": "252099f382ca4a5fc81b05b0468a40450ce8ec768ca6b1f1c735cd4d0e70dcee",
}


@pytest.fixture(scope="module")
def M():
    path = ROOT / "scripts" / "feature_matrix.py"
    spec = importlib.util.spec_from_file_location("feature_matrix_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fresh_catalog():
    fc._features.cache_clear()
    yield
    fc._features.cache_clear()


def _parser():
    from chronicler.main import _build_parser
    return _build_parser()


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def _reference_view(catalog: dict) -> dict:
    return {"schema_version": catalog["schema_version"],
            "features": [e for e in catalog["features"] if e["key"] in REFERENCE_KEYS],
            "settings": {k: catalog["settings"][k] for k in REFERENCE_SETTINGS},
            "surfaces": catalog["surfaces"]}


def _assert_reference_catalog_unchanged():
    entries = [e for e in fc.feature_entries() if e["key"] in REFERENCE_KEYS]
    assert tuple(e["key"] for e in entries) == REFERENCE_KEYS
    assert _digest(entries) == REFERENCE_DIGESTS["entries"]
    hybrid = fc.lobby_feature_catalog(_parser().parse_args(["--live", "--agents", "hybrid"]))
    assert _digest(_reference_view(hybrid)) == REFERENCE_DIGESTS["lobby_hybrid"]
    assert _digest(_reference_view(fc.lobby_feature_catalog(None))) == REFERENCE_DIGESTS["lobby_none"]
    bools = [k for k in REFERENCE_KEYS if k in fc.REQUIREMENTS]
    assert _digest({k: fc.REQUIREMENTS[k] for k in bools}) == REFERENCE_DIGESTS["requirements"]


def test_existing_catalog_output_is_byte_identical():
    """The served catalog of every existing switch is the 8abc1acb catalog, byte for byte."""
    assert fc.CATALOG_SCHEMA_VERSION == 1
    assert fc.FEATURE_GROUPS == {}
    _assert_reference_catalog_unchanged()


# --- Switch groups after livelihoods -----------------------------------------------------

def _fake_actions(monkeypatch, *specs):
    """Real parser actions plus fake ones: (key, choices or None)."""
    real = fc._parser_actions()
    fake = {key: types.SimpleNamespace(dest=key, option_strings=["--" + key.replace("_", "-")],
                                       help=f"Test switch {key}.", choices=choices)
            for key, choices in specs}
    monkeypatch.setattr(fc, "_parser_actions", lambda: {**real, **fake})


def test_a_new_group_is_listed_after_livelihoods_without_touching_existing_entries(monkeypatch, fresh_catalog):
    _fake_actions(monkeypatch, ("test_water_model", None), ("test_water_mode", ["flow", "index_only"]),
                  ("test_quarantine", None))
    monkeypatch.setattr(fc, "FEATURE_GROUPS", {"Watersheds": {"test_water_model": ("test_water_mode",)},
                                               "Public health": {"test_quarantine": ()}})
    monkeypatch.setitem(fc.REQUIREMENTS, "test_water_model", (fc._HYBRID, fc._feature("timber_stock")))
    monkeypatch.setitem(fc.REQUIREMENTS, "test_quarantine", ())
    entries = fc.feature_entries()
    keys = [e["key"] for e in entries]
    # The reference entries first, then any later livelihoods keys (A5's rules option, ...),
    # then the new groups.
    from chronicler.livelihoods import LIVELIHOODS_ARG_KEYS
    prerequisites = [k for key, options in fc.PREREQUISITES.items() for k in (key, *options)]
    assert keys[:len(REFERENCE_KEYS)] == list(REFERENCE_KEYS)
    assert keys == [*prerequisites, *LIVELIHOODS_ARG_KEYS, "test_water_model", "test_water_mode", "test_quarantine"]
    by = {e["key"]: e for e in entries}
    assert by["test_water_model"] == {
        "key": "test_water_model", "flag": "--test-water-model", "label": "Test water model",
        "help": "Test switch test_water_model.", "kind": "bool", "choices": None, "default": None, "parent": None,
        "requires": [{"agents": ["hybrid"], "reason": "requires --agents hybrid"},
                     {"feature": "timber_stock", "reason": "requires --timber-stock"}],
        "group": "Watersheds", "experimental": True}
    assert by["test_water_mode"]["parent"] == "test_water_model" and by["test_water_mode"]["choices"] == ["flow", "index_only"]
    assert by["test_quarantine"]["group"] == "Public health"
    _assert_reference_catalog_unchanged()
    hybrid = fc.live_surface(argparse.Namespace(agents="hybrid"))
    assert fc.validate_features({"test_water_model": True}, hybrid) == (
        "'test_water_model' (--test-water-model) requires --timber-stock")
    assert fc.validate_features({"test_water_mode": "flow"}, hybrid) == (
        "'test_water_mode' (--test-water-mode) requires --test-water-model")
    assert fc.validate_features({"timber_stock": True, "test_water_model": True, "test_water_mode": "flow"}, hybrid) is None
    assert fc.feature_cli_arguments({"test_water_mode": "flow", "test_quarantine": False}) == [
        "--test-water-mode=flow", "--no-test-quarantine"]


@pytest.mark.parametrize("groups, message", [
    ({"Livelihoods": {"test_water_model": ()}}, "reserved"),
    ({"Prerequisites": {"test_water_model": ()}}, "reserved"),
    ({"Watersheds": {"workshops": ()}}, "listed twice"),
    ({"Watersheds": {"test_water_model": ()}, "Ports": {"test_water_model": ()}}, "listed twice"),
])
def test_group_declaration_errors(monkeypatch, fresh_catalog, groups, message):
    _fake_actions(monkeypatch, ("test_water_model", None))
    monkeypatch.setattr(fc, "FEATURE_GROUPS", groups)
    with pytest.raises(ValueError, match=message):
        fc.feature_entries()


# --- The not condition and mutually exclusive switches --------------------------------------

def test_not_condition_reason_and_evaluation():
    condition = fc._with_reasons(fc._excludes("workshops"))
    assert condition == {"not": {"feature": "workshops", "reason": "requires --workshops"},
                         "reason": "requires --workshops off"}
    nested = fc._with_reasons(fc._not(fc._agents("off")))
    assert nested["reason"] == "requires not (--agents off)"
    entries = fc._by_key()
    hybrid = fc.live_surface(argparse.Namespace(agents="hybrid"))
    assert fc._satisfied(condition, {}, hybrid, entries)
    assert not fc._satisfied(condition, {"workshops": True}, hybrid, entries)
    assert fc._satisfied(nested, {}, hybrid, entries)
    assert not fc._satisfied(nested, {}, fc.live_surface(None), entries)


def _exclusive(monkeypatch, *, both=True):
    _fake_actions(monkeypatch, ("test_water_a", None), ("test_water_b", None))
    monkeypatch.setattr(fc, "FEATURE_GROUPS", {"Watersheds": {"test_water_a": (), "test_water_b": ()}})
    monkeypatch.setitem(fc.REQUIREMENTS, "test_water_a", (fc._HYBRID, fc._excludes("test_water_b")))
    monkeypatch.setitem(fc.REQUIREMENTS, "test_water_b",
                        (fc._HYBRID, fc._excludes("test_water_a")) if both else (fc._HYBRID,))


def test_mutually_exclusive_switches_refuse_each_other(monkeypatch, fresh_catalog, M):
    _exclusive(monkeypatch)
    hybrid = fc.live_surface(argparse.Namespace(agents="hybrid"))
    assert fc.validate_features({"test_water_a": True}, hybrid) is None
    assert fc.validate_features({"test_water_b": True}, hybrid) is None
    assert fc.validate_features({"test_water_a": True, "test_water_b": True}, hybrid) == (
        "'test_water_a' (--test-water-a) requires --test-water-b off")
    assert fc.exclusion_problems() == []
    m = M.matrix()
    pair = next(p for p in m["pairs_refused"] if p["pair"] == ["test_water_a", "test_water_b"])
    assert pair["expected_refusal"] and pair["refusal"].endswith("requires --test-water-b off")
    assert m["pairs_refused_unexpectedly"] == [] and M.problems(m) == []
    hybrid_all = m["all_enabled"]["hybrid"]
    assert "test_water_b" in hybrid_all["switches"] and "test_water_a" not in hybrid_all["switches"]
    assert hybrid_all["refusal"] is None
    _assert_reference_catalog_unchanged()


def test_a_one_sided_exclusion_is_a_declaration_error(monkeypatch, fresh_catalog, M):
    _exclusive(monkeypatch, both=False)
    assert fc.exclusion_problems() == ["'test_water_a' excludes 'test_water_b' but 'test_water_b' does not exclude "
                                       "'test_water_a'"]
    assert any("does not exclude" in p for p in M.problems(M.matrix()))


# --- The matrix of the current catalog -----------------------------------------------------

def test_matrix_of_the_catalog(M):
    m = M.matrix()
    bools = [e["key"] for e in fc.feature_entries() if e["kind"] == "bool"]
    assert m["switches"] == len(bools) and m["pairs_total"] == len(bools) * (len(bools) - 1) // 2
    assert m["groups"][:2] == [fc.PREREQUISITES_GROUP, fc.LIVELIHOODS_GROUP]
    assert M.problems(m) == []
    assert m["drops_not_refused"] == [] and m["pairs_refused_unexpectedly"] == []
    assert len(m["pairs_valid"]) + len(m["pairs_refused"]) == m["pairs_total"]
    # Every prerequisite switch of a minimal selection is dropped once.
    assert len(m["drops"]) == sum(sum(1 for k in f["closure"] if k != key and fc._by_key()[k]["kind"] == "bool")
                                  for key, f in m["features"].items())
    assert m["features"]["maintenance_obligation"]["closure"] == {
        "maintenance_obligation": True, "repair_projects": True, "workshops": True, "local_budgets": True,
        "grain_reserves": True}
    assert m["features"]["maintenance_obligation"]["modes"] == ["hybrid"]
    assert m["features"]["timber_stock"]["modes"] == ["demographics-only", "shadow", "hybrid"]
    reference = {mode: [k for k in e["switches"] if k in REFERENCE_KEYS] for mode, e in m["all_enabled"].items()}
    economy = ["grain_reserves", "public_grain_shipments", "scholarship", "timber_stock", "grain_convoys",
               "commons_rules", "clearing_protection"]
    assert reference == {"off": ["scholarship", "clearing_protection"], "demographics-only": economy,
                         "shadow": economy, "hybrid": [k for k in REFERENCE_KEYS if k in fc.REQUIREMENTS]}
    assert all(e["refusal"] is None for e in m["all_enabled"].values())


class _Accepted(Exception):
    """Configuration got past every check (to the native runtimes)."""


@pytest.fixture
def sentinel_runtimes(monkeypatch):
    from chronicler import agent_bridge, main

    def accepted(*args, **kwargs):
        raise _Accepted

    monkeypatch.setattr(agent_bridge, "AgentBridge", accepted)
    monkeypatch.setattr(main, "_create_ecology_runtime", accepted)


@pytest.fixture(scope="module")
def template():
    from chronicler.world_gen import generate_world
    return generate_world(seed=42, num_regions=8, num_civs=4)


def _configure(tmp_path, template, mode, flags) -> str | None:
    from chronicler import main
    args = _parser().parse_args(["--seed", "42", "--turns", "4", "--regions", "8", "--civs", "4", "--simulate-only",
                                 "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json"),
                                 "--agents", mode, *flags])
    try:
        main._configure_run(args, template.model_copy(deep=True), True, tmp_path / "chronicle.md")
    except _Accepted:
        return None
    except ValueError as error:
        return str(error)
    return "configuration finished without reaching the runtimes"


@pytest.mark.parametrize("mode", fc.AGENT_MODES)
def test_all_enabled_selections_pass_the_run_configuration(M, tmp_path, template, sentinel_runtimes, mode):
    enabled = M.matrix()["all_enabled"][mode]
    assert enabled["refusal"] is None
    assert _configure(tmp_path, template, mode, enabled["flags"]) is None


def test_every_prerequisite_drop_is_refused_by_the_run(M, tmp_path, template, sentinel_runtimes):
    accepted = []
    for d in M.matrix()["drops"]:
        selection = M._without(M.closure(d["feature"])[0], d["dropped"])
        if _configure(tmp_path, template, d["mode"], fc.feature_cli_arguments(selection)) is None:
            accepted.append(f"{d['feature']} without {d['dropped']}")
    assert accepted == []


def test_cli_writes_json_and_markdown(M, tmp_path, capsys):
    assert M.main(["--json", str(tmp_path / "m.json"), "--markdown", str(tmp_path / "m.md")]) == 0
    data = json.loads((tmp_path / "m.json").read_text())
    assert data["drops_not_refused"] == [] and data["all_enabled"]["hybrid"]["refusal"] is None
    text = (tmp_path / "m.md").read_text()
    assert text.startswith("# Switch compatibility matrix (catalog schema 1)")
    assert "## All enabled, per agent mode" in text and "- hybrid: accepted; --grain-reserves" in text
    assert "0 accepted" in capsys.readouterr().out


def test_m7_the_catalog_term_walk_accepts_exclusions(monkeypatch, fresh_catalog):
    """tests/test_feature_catalog.py's requirement walk accepts a switch declaring a
    mutual exclusion (review m7), so the first exclusion does not fail it."""
    import tests.test_feature_catalog as catalog_tests          # its import fills the catalog cache
    _exclusive(monkeypatch)
    fc._features.cache_clear()
    assert any("not" in c for e in fc.feature_entries() for c in e["requires"])
    catalog_tests.test_every_boolean_feature_declares_requirements_over_known_terms()
