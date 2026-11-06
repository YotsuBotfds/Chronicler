"""The feature catalog behind Batch Lab and live new-world feature options.

Offline: no sockets, no subprocesses, no native extension (the agent bridge
and ecology runtime are replaced by a sentinel that marks "configuration
accepted"). The agreement tests run the real configuration path
(``main._configure_run``, and ``live._live_world`` before it) and compare its
refusals with the catalog's declared requirements.
"""
from __future__ import annotations

import argparse
import copy
import json
import threading
from pathlib import Path

import pytest

from chronicler import feature_catalog as fc
from chronicler.livelihoods import _HELP, LIVELIHOODS_ARG_KEYS, LIVELIHOODS_CHOICES
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES


def _parser():
    from chronicler.main import _build_parser
    return _build_parser()


def _base(path: Path, *flags: str) -> list[str]:
    return ["--seed", "42", "--turns", "4", "--regions", "8", "--civs", "4", "--simulate-only",
            "--output", str(path / "chronicle.md"), "--state", str(path / "state.json"), *flags]


@pytest.fixture
def fresh_catalog():
    fc._features.cache_clear()
    yield
    fc._features.cache_clear()


# --- catalog generation -----------------------------------------------------

def test_catalog_is_generated_from_the_registry_and_the_cli_parser():
    entries = fc.feature_entries()
    keys = [entry["key"] for entry in entries]
    assert len(keys) == len(set(keys))
    prerequisites = [k for k, options in fc.PREREQUISITES.items() for k in (k, *options)]
    assert keys == prerequisites + list(LIVELIHOODS_ARG_KEYS)
    actions = {action.dest: action for action in _parser()._actions}
    parent = None
    for entry in entries:
        key = entry["key"]
        action = actions[key]
        assert entry["flag"] == action.option_strings[0] == "--" + key.replace("_", "-")
        assert entry["default"] is None and action.default is None
        assert entry["label"] and entry["help"]
        if key in LIVELIHOODS_ARG_KEYS:
            assert entry["group"] == fc.LIVELIHOODS_GROUP and entry["experimental"] is True
            assert entry["help"] == _HELP[key] == action.help
        else:
            assert entry["group"] == fc.PREREQUISITES_GROUP and entry["experimental"] is False
            assert entry["help"] == action.help
        if entry["kind"] == "bool":
            assert isinstance(action, argparse.BooleanOptionalAction)
            assert entry["choices"] is None and entry["parent"] is None
            parent = key
        else:
            assert entry["kind"] == "choice"
            assert entry["choices"] == list(action.choices) and entry["choices"]
            # A mode belongs to the switch declared before it.
            assert entry["parent"] == parent
            assert entry["requires"] == [{"feature": parent, "reason": "requires " + fc._flag(parent)}]
    for switch in LIVELIHOODS_SWITCHES:
        assert next(e for e in entries if e["key"] == switch)["kind"] == "bool"
    for key, choices in LIVELIHOODS_CHOICES.items():
        assert next(e for e in entries if e["key"] == key)["choices"] == list(choices)
    json.dumps(entries)  # JSON-ready


def test_every_boolean_feature_declares_requirements_over_known_terms():
    entries = {entry["key"]: entry for entry in fc.feature_entries()}
    bools = {key for key, entry in entries.items() if entry["kind"] == "bool"}
    # A registry switch added without declared requirements fails here.
    assert set(fc.REQUIREMENTS) == bools

    def walk(condition):
        assert condition["reason"].startswith("requires ")
        kinds = [k for k in ("agents", "feature", "choice", "setting", "any") if k in condition]
        assert len(kinds) == 1
        if "agents" in condition:
            assert condition["agents"] and set(condition["agents"]) <= set(fc.AGENT_MODES)
        elif "feature" in condition:
            assert entries[condition["feature"]]["kind"] == "bool"
        elif "choice" in condition:
            assert set(condition["values"]) <= set(entries[condition["choice"]]["choices"])
        elif "setting" in condition:
            assert condition["setting"] in fc.SETTINGS
        else:
            for part in condition["any"]:
                walk(part)

    for entry in entries.values():
        for condition in entry["requires"]:
            walk(condition)


def test_lobby_catalog_shape_and_surfaces():
    catalog = fc.lobby_feature_catalog(argparse.Namespace(local_url=None))
    assert catalog["schema_version"] == 1
    assert catalog["settings"] == fc.SETTINGS
    assert set(catalog["surfaces"]) == {"live", "batch"}
    live, batch = catalog["surfaces"]["live"], catalog["surfaces"]["batch"]
    assert live["agents"] == "off" and live["agent_modes"] == ["off"] and live["values"] == {}
    assert batch["agent_modes"] == list(fc.AGENT_MODES)
    for surface in (live, batch):
        assert surface["new_worlds_only"] is True
        assert surface["settings"] == {"cities": True, "techniques": True,
                                       "no_household_mobility_liquid_requirement": True,
                                       "procedural_world": False}
    json.dumps(catalog)
    args = _parser().parse_args(["--agents", "hybrid", "--no-cities", "--grain-reserves", "--workshops",
                                 "--workshop-mode", "observe", "--household-mobility-liquid-requirement", "2"])
    live = fc.live_surface(args)
    assert live["agents"] == "hybrid"
    assert live["values"] == {"grain_reserves": True, "workshops": True, "workshop_mode": "observe"}
    assert live["settings"] == {"cities": False, "techniques": True,
                                "no_household_mobility_liquid_requirement": False,
                                "procedural_world": False}


def test_any_condition_reason_and_evaluation():
    condition = fc._with_reasons(fc._any(fc._feature("workshops"), fc._feature("grain_storage")))
    assert condition["reason"] == "requires one of: --workshops; --grain-storage"
    assert [part["reason"] for part in condition["any"]] == ["requires --workshops", "requires --grain-storage"]
    entries = fc._by_key()
    surface = fc.live_surface(argparse.Namespace(agents="hybrid"))
    assert not fc._satisfied(condition, {}, surface, entries)
    assert fc._satisfied(condition, {"grain_storage": True}, surface, entries)
    assert fc._satisfied(condition, {"workshops": True}, surface, entries)


def test_cli_arguments_and_apply_match_the_parser(tmp_path):
    features = {"workshops": True, "workshop_mode": "cost_only", "grain_reserves": False,
                "local_budget_mode": "fixed_shares", "local_budgets": True}
    flags = fc.feature_cli_arguments(features)
    assert flags == ["--no-grain-reserves", "--workshops", "--workshop-mode=cost_only",
                     "--local-budgets", "--local-budget-mode=fixed_shares"]
    parsed = _parser().parse_args(_base(tmp_path, *flags))
    applied = _parser().parse_args(_base(tmp_path))
    previous = fc.apply_features(applied, features)
    assert vars(applied) == vars(parsed)
    assert previous == {key: None for key in features}
    fc.apply_features(applied, previous)
    assert vars(applied) == vars(_parser().parse_args(_base(tmp_path)))


# --- validation -------------------------------------------------------------

HYBRID = fc.live_surface(argparse.Namespace(agents="hybrid"))


@pytest.mark.parametrize("features, message", [
    ([], "must be an object"),
    ({"bogus": True}, "unknown feature 'bogus'"),
    ({"workshops": 1}, "'workshops' must be a boolean"),
    ({"workshops": "true"}, "'workshops' must be a boolean"),
    ({"workshops": None}, "'workshops' must be a boolean"),
    ({"workshops": True, "workshop_mode": "fast"}, "'workshop_mode' must be one of operate, observe, cost_only"),
    ({"workshops": True, "workshop_mode": True}, "'workshop_mode' must be one of operate, observe, cost_only"),
    ({"workshop_mode": "observe"}, "'workshop_mode' (--workshop-mode) requires --workshops"),
    ({"workshop_payroll": True}, "'workshop_payroll' (--workshop-payroll) requires --workshops"),
    ({"workshops": True, "workshop_mode": "observe", "workshop_payroll": True},
     "'workshop_payroll' (--workshop-payroll) requires --workshop-mode operate"),
    ({"local_budgets": True}, "'local_budgets' (--local-budgets) requires --grain-reserves"),
    ({"commons_rules": True}, "'commons_rules' (--commons-rules) requires --timber-stock"),
    ({"grain_storage_policy": "maintain"}, "'grain_storage_policy' (--grain-storage-policy) requires --grain-storage"),
])
def test_validation_refuses_with_a_clear_message(features, message):
    assert fc.validate_features(features, HYBRID) == message


def test_validation_names_the_run_agent_mode():
    assert fc.validate_features({"food_allocation": True}, fc.live_surface(None)) == (
        "'food_allocation' (--food-allocation) requires --agents hybrid (this run uses --agents off)")
    shadow = fc.live_surface(argparse.Namespace(agents="shadow"))
    assert fc.validate_features({"timber_stock": True}, shadow) is None
    assert fc.validate_features({"food_allocation": True}, shadow).endswith("(this run uses --agents shadow)")


def test_validation_accepts_dependency_chains_and_reads_inherited_values():
    assert fc.validate_features({}, HYBRID) is None
    assert fc.validate_features({"grain_reserves": True, "public_grain_shipments": True,
                                 "grain_convoys": True, "convoy_route_policy": "safest"}, HYBRID) is None
    assert fc.validate_features({"scholarship": True, "academy_services": True,
                                 "learning_cohorts": True}, HYBRID) is None
    inherited = fc.live_surface(argparse.Namespace(agents="hybrid", timber_stock=True, grain_reserves=True))
    assert fc.validate_features({"commons_rules": True, "local_budgets": True}, inherited) is None
    # Explicitly disabling an inherited prerequisite refuses what depends on it.
    assert fc.validate_features({"timber_stock": False, "commons_rules": True}, inherited) == (
        "'commons_rules' (--commons-rules) requires --timber-stock")
    no_cities = fc.live_surface(argparse.Namespace(agents="hybrid", cities=False))
    assert fc.validate_features({"workshops": True}, no_cities).startswith(
        "'workshops' (--workshops) requires cities")
    mobility = fc.live_surface(argparse.Namespace(agents="hybrid", household_mobility_liquid_requirement=3.0))
    assert "household-mobility liquid requirement" in fc.validate_features({"relocation_costs": True}, mobility)


# --- agreement with the run's own checks -------------------------------------

class _Accepted(Exception):
    """Configuration got past every check (to the native runtimes)."""


_SETTING_FLAGS = {
    "cities": ("--no-cities",),
    "techniques": ("--no-techniques",),
    "no_household_mobility_liquid_requirement": ("--household-mobility-liquid-requirement", "1"),
}


def _closure(key: str) -> tuple[dict, list[str]]:
    """The smallest selection the catalog accepts with ``key`` on, and the
    agent modes it allows."""
    entries = fc._by_key()
    selection = {key: True}
    modes = list(fc.AGENT_MODES)
    stack = [key]

    def walk(condition):
        nonlocal modes
        if "agents" in condition:
            modes = [m for m in modes if m in condition["agents"]]
        elif "feature" in condition:
            if condition["feature"] not in selection:
                selection[condition["feature"]] = True
                stack.append(condition["feature"])
        elif "choice" in condition:
            default = entries[condition["choice"]]["choices"][0]
            if default not in condition["values"]:
                selection[condition["choice"]] = condition["values"][0]
        elif "any" in condition:
            walk(condition["any"][0])

    while stack:
        for condition in entries[stack.pop()]["requires"]:
            walk(condition)
    return selection, modes


def _variants(key: str):
    """Selections near the minimal one: every agent mode, each prerequisite
    dropped, each mode value of a selected switch, each setting flipped."""
    entries = fc._by_key()
    selection, modes = _closure(key)
    agents = "hybrid" if "hybrid" in modes else modes[0]
    for mode in fc.AGENT_MODES:
        yield selection, mode, ()
    for other in selection:
        if other != key and entries[other]["kind"] == "bool":
            yield ({k: v for k, v in selection.items() if k != other and entries[k]["parent"] != other},
                   agents, ())
    for entry in entries.values():
        if entry["parent"] in selection:
            for value in entry["choices"]:
                yield {**selection, entry["key"]: value}, agents, ()
    for flags in _SETTING_FLAGS.values():
        yield selection, agents, flags


def _disagreements(tmp_path: Path, keys) -> list[str]:
    from chronicler import live, main
    from chronicler.world_gen import generate_world

    parser = _parser()
    template = generate_world(seed=42, num_regions=8, num_civs=4)
    output = tmp_path / "chronicle.md"

    def run(path, args) -> str | None:
        try:
            if path == "cli":
                main._configure_run(args, template.model_copy(deep=True), True, output)
            else:
                world, _ = live._live_world(args, {"seed": 42, "regions": 8, "civs": 4})
                main._configure_run(args, world, False, output)
        except _Accepted:
            return None
        except ValueError as exc:
            return str(exc)
        return "configuration finished without reaching the runtimes"

    problems = []
    for key in keys:
        for selection, agents, setting_flags in _variants(key):
            base = ["--agents", agents, *setting_flags]
            catalog = fc.validate_features(selection, fc.live_surface(parser.parse_args(_base(tmp_path, *base))))
            flags = [*base, *fc.feature_cli_arguments(selection)]
            for path in ("cli", "live"):
                refusal = run(path, parser.parse_args(_base(tmp_path, *flags)))
                if (catalog is None) != (refusal is None):
                    problems.append(f"{path} {' '.join(flags)}: catalog {catalog!r}, run {refusal!r}")
    return problems


@pytest.fixture
def sentinel_runtimes(monkeypatch):
    from chronicler import agent_bridge, main

    def accepted(*args, **kwargs):
        raise _Accepted

    monkeypatch.setattr(agent_bridge, "AgentBridge", accepted)
    monkeypatch.setattr(main, "_create_ecology_runtime", accepted)


def test_catalog_requirements_agree_with_the_run(tmp_path, sentinel_runtimes):
    bools = [entry["key"] for entry in fc.feature_entries() if entry["kind"] == "bool"]
    assert _disagreements(tmp_path, bools) == []


def test_agreement_check_detects_wrong_declarations(tmp_path, sentinel_runtimes, fresh_catalog, monkeypatch):
    # A missing requirement (workshops without cities) and an invented one.
    monkeypatch.setitem(fc.REQUIREMENTS, "workshops", (fc._HYBRID,))
    monkeypatch.setitem(fc.REQUIREMENTS, "food_allocation", (fc._HYBRID, fc._feature("scholarship")))
    monkeypatch.setitem(fc.REQUIREMENTS, "timber_stock", (fc._HYBRID,))
    fc._features.cache_clear()
    problems = _disagreements(tmp_path, ["workshops", "food_allocation", "timber_stock"])
    runs = [problem.split(": catalog ")[0] for problem in problems]
    assert "cli --agents hybrid --no-cities --workshops" in runs
    assert "live --agents hybrid --food-allocation" in runs
    assert "cli --agents shadow --timber-stock" in runs
    assert all(problem.startswith(("cli ", "live ")) for problem in problems)


def test_live_world_applies_the_prerequisites_its_switches_need(tmp_path):
    from chronicler.live import _apply_live_prerequisites, _live_world
    parser = _parser()
    params = {"seed": 42, "regions": 8, "civs": 4}
    world, _ = _live_world(parser.parse_args(_base(
        tmp_path, "--agents", "hybrid", "--scholarship", "--academy-services", "--learning-cohorts")), params)
    assert world.livelihoods.learning_cohorts is not None
    world, _ = _live_world(parser.parse_args(_base(
        tmp_path, "--agents", "hybrid", "--grain-reserves", "--public-grain-shipments", "--grain-convoys",
        "--grain-storage")), params)
    assert world.livelihoods.grain_convoys is not None
    assert world.grain_reserves.shipments is not None and world.grain_reserves.storage is not None
    # Without those flags the helper changes nothing.
    world, _ = _live_world(parser.parse_args(_base(tmp_path, "--agents", "hybrid")), params)
    before = world.model_dump_json()
    _apply_live_prerequisites(world, parser.parse_args(_base(tmp_path, "--agents", "hybrid")), "hybrid")
    assert world.model_dump_json() == before


# --- live server: batch_start -------------------------------------------------

def _capture_batch(monkeypatch, server, config):
    from chronicler import batch

    received = []

    def capture(args, **kwargs):
        received.append(copy.copy(args))
        raise RuntimeError("configuration captured before batch execution")

    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def is_alive(self):
            return False

        def start(self):
            self.target()

    monkeypatch.setattr(batch, "run_batch", capture)
    monkeypatch.setattr(threading, "Thread", InlineThread)
    error = server._handle_batch_start({"type": "batch_start", "config": config})
    return error, received


def test_batch_config_feature_validation():
    from chronicler.live import LiveServer
    server = LiveServer()
    assert server._validate_batch_config({}) is None
    assert server._validate_batch_config({"features": None}) is None
    assert server._validate_batch_config({"features": {}}) is None
    assert server._validate_batch_config({"features": []}) == "batch_start config 'features': must be an object"
    assert server._validate_batch_config({"features": {"nope": True}}) == (
        "batch_start config 'features': unknown feature 'nope'")
    assert server._validate_batch_config({"features": {"workshops": True}}) == (
        "batch_start config 'features': 'workshops' (--workshops) requires --agents hybrid "
        "(this run uses --agents off)")
    assert server._validate_batch_config({"agents": "hybrid", "features": {"workshops": True}}) is None
    server._client_defaults["agents"] = "hybrid"
    assert server._validate_batch_config({"features": {"workshops": True}}) is None
    assert server._validate_batch_config({"features": {"local_budgets": True}}).endswith(
        "requires --grain-reserves")
    assert server._validate_batch_config({"grain_reserves": True, "features": {"local_budgets": True}}) is None
    server._client_defaults["grain_reserves"] = True
    assert server._validate_batch_config({"features": {"local_budgets": True}}) is None
    assert server._validate_batch_config({"grain_reserves": True, "features": {"grain_reserves": True}}) == (
        "batch_start config 'features': 'grain_reserves' is given both in features and at the top "
        "level of the config")
    # Invalid requests start nothing.
    assert server._handle_batch_start({"type": "batch_start", "config": {"features": {"x": 1}}}) == {
        "type": "batch_error", "message": "batch_start config 'features': unknown feature 'x'"}
    assert server._batch_thread is None


def test_batch_forwards_features_as_the_cli_would_and_the_manifest_records_them(tmp_path, monkeypatch):
    from chronicler.batch_manifest import simulation_config
    from chronicler.live import LiveServer

    features = {"grain_reserves": True, "local_budgets": True, "local_budget_mode": "fixed_shares",
                "workshops": True, "workshop_mode": "observe"}
    server = LiveServer()
    error, received = _capture_batch(monkeypatch, server, {"agents": "hybrid", "features": features})
    assert error is None and len(received) == 1
    parsed = _parser().parse_args(_base(tmp_path, *fc.feature_cli_arguments(features)))
    for key in fc.catalog_keys():
        assert getattr(received[0], key, None) == getattr(parsed, key), key
    recorded = simulation_config(received[0])
    for key, value in features.items():
        assert recorded[key] == value

    plain = [_capture_batch(monkeypatch, LiveServer(), config)[1][0]
             for config in ({"agents": "hybrid"}, {"agents": "hybrid", "features": None},
                            {"agents": "hybrid", "features": {}})]
    # Absent, null and empty features build the same namespace and manifest.
    assert vars(plain[0]) == vars(plain[1]) == vars(plain[2])
    assert simulation_config(plain[0]) == simulation_config(plain[1])
    for key in features:
        if key != "grain_reserves":
            assert not hasattr(plain[0], key) and key not in simulation_config(plain[0])


# --- live server: lobby start --------------------------------------------------

def test_start_feature_validation_before_starting():
    from chronicler.live import LiveServer
    start = {"type": "start", "turns": 5, "civs": 2, "regions": 3}
    server = LiveServer()
    error = server._handle_start({**start, "features": {"workshops": True}})
    assert error == {"type": "error", "message": "Start field 'features': 'workshops' (--workshops) "
                                                 "requires --agents hybrid (this run uses --agents off)"}
    assert server._server_state == "lobby" and not server.start_event.is_set()
    assert server._handle_start({**start, "features": "workshops"}) == {
        "type": "error", "message": "Start field 'features': must be an object"}
    server.feature_args = argparse.Namespace(agents="hybrid")
    assert server._handle_start({**start, "features": {"workshops": True},
                                 "resume_state": {"turn": 3}}) == {
        "type": "error",
        "message": "Start field 'features': applies to new worlds only, not with resume_state"}
    assert server._server_state == "lobby"
    msg = {**start, "features": {"workshops": True, "workshop_mode": "cost_only"}}
    assert server._handle_start(msg) is None
    assert server._server_state == "running" and server._start_params is msg


def test_start_without_features_is_unchanged():
    from chronicler.live import LiveServer
    for extra in ({}, {"features": None}, {"features": {}, "resume_state": {"turn": 1}}):
        server = LiveServer()
        msg = {"type": "start", "turns": 5, "civs": 2, "regions": 3, **extra}
        assert server._handle_start(msg) is None
        assert server._start_params is msg and server._server_state == "running"


class _Stop(Exception):
    pass


class _LobbyServer:
    """A LiveServer without sockets whose viewer sends ``starts`` in turn
    (the next one when the lobby reopens)."""

    def __new__(cls, starts):
        from chronicler.live import LiveServer

        class Server(LiveServer):
            def __init__(self):
                super().__init__(port=0)
                self.starts = list(starts)
                self.replies = []
                self.reopened = []

            def _send_next(self):
                self.replies.append(self._handle_start({"type": "start", **self.starts.pop(0)}))

            def start(self):
                self._actual_port = 0
                self._send_next()

            def stop(self):
                pass

            def reopen_lobby(self, message):
                super().reopen_lobby(message)
                self.reopened.append(message)
                self._send_next()

        return Server()


def _run_live_until_execute(tmp_path, monkeypatch, server, *flags):
    from chronicler import live, main
    seen = {}

    def execute_run(args, **kwargs):
        seen["args"] = copy.copy(args)
        seen["world"] = kwargs["world"]
        raise _Stop

    monkeypatch.setattr(main, "execute_run", execute_run)
    monkeypatch.setattr(live, "_get_available_models", lambda args: [""])
    args = _parser().parse_args(["--live", *_base(tmp_path, *flags)])
    with pytest.raises(_Stop):
        live.run_live(args, server=server)
    return args, seen


def test_lobby_start_forwards_features_and_serves_the_catalog(tmp_path, monkeypatch):
    features = {"grain_reserves": True, "local_budgets": True, "workshops": True, "workshop_mode": "observe"}
    server = _LobbyServer([{"turns": 3, "civs": 2, "regions": 3, "seed": 7, "features": features}])
    args, seen = _run_live_until_execute(tmp_path, monkeypatch, server, "--agents", "hybrid")
    assert server.replies == [None] and server.reopened == []
    catalog = server._lobby_init["feature_catalog"]
    assert server.feature_args is args
    assert catalog["features"] == fc.feature_entries()
    assert catalog["surfaces"]["live"] == fc.live_surface(_parser().parse_args(
        ["--live", *_base(tmp_path, "--agents", "hybrid")]))
    assert catalog["surfaces"]["batch"] == fc.batch_surface(server._client_defaults)
    parsed = _parser().parse_args(["--live", *_base(tmp_path, "--agents", "hybrid",
                                                    *fc.feature_cli_arguments(features))])
    for key in fc.catalog_keys():
        assert getattr(seen["args"], key) == getattr(parsed, key), key
    world = seen["world"]
    assert world.livelihoods.workshops is not None and world.livelihoods.local_budgets is not None
    from chronicler.batch_manifest import simulation_config
    assert simulation_config(seen["args"])["workshop_mode"] == "observe"


def test_lobby_reopens_when_the_run_refuses_requested_features(tmp_path, monkeypatch):
    from chronicler import live
    calls = []
    original = live._live_world

    def refuse_first(args, params):
        calls.append((params.get("features"), args.workshops))
        if len(calls) == 1:
            raise ValueError("--workshops requires cities")
        return original(args, params)

    monkeypatch.setattr(live, "_live_world", refuse_first)
    starts = [{"turns": 3, "civs": 2, "regions": 3, "seed": 7, "features": {"workshops": True}},
              {"turns": 3, "civs": 2, "regions": 3, "seed": 7}]
    server = _LobbyServer(starts)
    args, seen = _run_live_until_execute(tmp_path, monkeypatch, server, "--agents", "hybrid")
    assert server.reopened == ["Start field 'features': --workshops requires cities"]
    assert server.status_queue.get_nowait() == {
        "type": "error", "message": "Start field 'features': --workshops requires cities"}
    # The refused request left nothing behind: the second start has no workshops.
    assert calls == [({"workshops": True}, True), (None, None)]
    assert seen["args"].workshops is None and seen["world"].livelihoods is None


def test_a_refusal_without_features_still_fails_the_run(tmp_path, monkeypatch):
    from chronicler import live

    def refuse(args, params):
        raise ValueError("refused")

    monkeypatch.setattr(live, "_live_world", refuse)
    monkeypatch.setattr(live, "_get_available_models", lambda args: [""])
    server = _LobbyServer([{"turns": 3, "civs": 2, "regions": 3}])
    args = _parser().parse_args(["--live", *_base(tmp_path, "--agents", "hybrid")])
    with pytest.raises(ValueError, match="refused"):
        live.run_live(args, server=server)
    assert server.reopened == []


def test_household_retail_is_offered_and_forwarded_with_its_options(tmp_path, monkeypatch):
    """PL5b: ``--household-retail`` (L6b), its mode and its boundary are served
    from the registry, require --agents hybrid and --food-allocation, and reach
    the live run's namespace and world and the batch namespace and manifest
    through the generic forwarding, exactly as the CLI flags would."""
    from chronicler.batch_manifest import simulation_config
    from chronicler.live import LiveServer
    entries = {entry["key"]: entry for entry in fc.feature_entries()}
    assert [entries[k]["flag"] for k in ("household_retail", "household_retail_mode", "household_retail_boundary")] == [
        "--household-retail", "--household-retail-mode", "--household-retail-boundary"]
    assert entries["household_retail"]["requires"] == [
        {"agents": ["hybrid"], "reason": "requires --agents hybrid"},
        {"feature": "food_allocation", "reason": "requires --food-allocation"}]
    assert entries["household_retail_mode"]["choices"] == ["retail", "no_relief", "free_exchange", "record_only"]
    assert entries["household_retail_boundary"]["choices"] == ["market", "paid_work", "all"]
    assert {entries[k]["parent"] for k in ("household_retail_mode", "household_retail_boundary")} == {"household_retail"}
    assert all(entries[k]["default"] is None and entries[k]["experimental"]
               for k in ("household_retail", "household_retail_mode", "household_retail_boundary"))
    assert fc.validate_features({"household_retail": True}, HYBRID) == (
        "'household_retail' (--household-retail) requires --food-allocation")
    assert fc.validate_features({"household_retail_boundary": "all"}, HYBRID) == (
        "'household_retail_boundary' (--household-retail-boundary) requires --household-retail")
    assert fc.validate_features({"food_allocation": True, "household_retail": True},
                                fc.live_surface(None)).endswith("(this run uses --agents off)")
    features = {"food_allocation": True, "household_retail": True, "household_retail_mode": "free_exchange",
                "household_retail_boundary": "paid_work"}
    assert fc.validate_features(features, HYBRID) is None
    flags = fc.feature_cli_arguments(features)
    assert flags == ["--food-allocation", "--household-retail", "--household-retail-mode=free_exchange",
                     "--household-retail-boundary=paid_work"]

    # Live start: the requested values reach the namespace and the world.
    server = _LobbyServer([{"turns": 3, "civs": 2, "regions": 3, "seed": 7, "features": features}])
    args, seen = _run_live_until_execute(tmp_path, monkeypatch, server, "--agents", "hybrid")
    assert server.replies == [None] and server.reopened == []
    parsed = _parser().parse_args(["--live", *_base(tmp_path, "--agents", "hybrid", *flags)])
    for key in fc.catalog_keys():
        assert getattr(seen["args"], key) == getattr(parsed, key), key
    state = seen["world"].livelihoods.household_retail
    assert (state.enabled, state.mode, state.boundary, state.regions) == (True, "free_exchange", "paid_work", [])
    assert seen["world"].livelihoods.food_allocation is not None
    recorded = simulation_config(seen["args"])
    assert {key: recorded[key] for key in features} == features

    # Batch Lab: the namespace every child run copies, and its manifest.
    error, received = _capture_batch(monkeypatch, LiveServer(), {"agents": "hybrid", "features": features})
    assert error is None and len(received) == 1
    for key in fc.catalog_keys():
        assert getattr(received[0], key, None) == getattr(parsed, key), key
    recorded = simulation_config(received[0])
    assert {key: recorded[key] for key in features} == features
    error, plain = _capture_batch(monkeypatch, LiveServer(), {"agents": "hybrid"})
    assert error is None and not any(key in simulation_config(plain[0]) for key in features)
    error, refused = _capture_batch(monkeypatch, LiveServer(), {"agents": "hybrid", "features": {"household_retail": True}})
    assert error == {"type": "batch_error", "message": "batch_start config 'features': 'household_retail' "
                     "(--household-retail) requires --food-allocation"} and refused == []


def test_viewer_fixture_has_the_shape_the_server_sends():
    """viewer/src/__fixtures__/featureCatalog.json (lobby_feature_catalog for
    ``--live --agents hybrid``) drives the viewer's tests: it must keep the
    served shape. Its content may lag the registry (new switches)."""
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / "viewer/src/__fixtures__/featureCatalog.json").read_text(encoding="utf-8"))
    served = fc.lobby_feature_catalog(_parser().parse_args(["--live", "--agents", "hybrid"]))
    assert set(fixture) == set(served) and fixture["schema_version"] == served["schema_version"]
    assert fixture["settings"] == served["settings"]
    assert {name: set(surface) for name, surface in fixture["surfaces"].items()} == {
        name: set(surface) for name, surface in served["surfaces"].items()}
    assert fixture["surfaces"] == served["surfaces"]
    served_entries = {entry["key"]: entry for entry in served["features"]}
    for entry in fixture["features"]:
        assert set(entry) == set(served_entries[entry["key"]])
        for field in ("flag", "kind", "choices", "parent", "requires", "group", "experimental"):
            assert entry[field] == served_entries[entry["key"]][field], (entry["key"], field)
