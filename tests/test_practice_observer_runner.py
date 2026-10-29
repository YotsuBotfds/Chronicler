"""Explicit runner dispatch on scalar fakes; no ordinary World/native runtime."""
import ast
import hashlib
import inspect
from pathlib import Path
import signal
from types import SimpleNamespace as NS

import pytest

from chronicler import main as M


BASE = "1205b6e48215c3e5c44d2bcb6376ca65827a7aab"
# Untouched parent, CPython 3.13 with the explicit canonical options below.
BASE_MAIN_AST_SHA256 = "8e007835bad6dbc5dd3f327d8d5a3947777f806dd5adbb8436f57b0b483fefa6"
MODES = ("omitted", "none", "provided")


def ast_dump(node):
    return ast.dump(node, annotate_fields=True, include_attributes=False,
                    indent=None, show_empty=True)


def invoke(mode, observer, *args, **kwargs):
    if mode == "omitted":
        return M._run_turn_deferring_sigint(*args, **kwargs)
    return M._run_turn_deferring_sigint(
        *args, practice_observer=None if mode == "none" else observer, **kwargs)


def fake_deferral(monkeypatch, events, requested=False):
    class Deferral:
        def __enter__(self):
            self.requested = requested
            events.append("enter")
            return self

        def __exit__(self, kind, value, traceback):
            events.append(("exit", kind, value))
            return False

    monkeypatch.setattr(M, "_SigintDeferral", Deferral)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("requested", [False, True])
def test_real_helper_dispatches_once_with_exact_arguments_and_result(monkeypatch, mode, requested):
    events, calls, observed = [], [], []
    fake_deferral(monkeypatch, events, requested)
    result = object()
    args, kwargs = (object(), object()), {"seed": 43, "pending_injections": []}

    def physics(*received, **options):
        assert events == ["enter"]
        calls.append((received, options))
        return result

    def observe(*received, **options):
        observed.append((received, options))
        return physics(*received, **options)

    monkeypatch.setattr(M, "run_turn_result", physics)
    answer, interrupted = invoke(mode, NS(run_turn_result=observe), *args, **kwargs)
    assert answer is result and interrupted is requested
    assert calls == [(args, kwargs)]
    assert observed == ([(args, kwargs)] if mode == "provided" else [])
    assert events == ["enter", ("exit", None, None)]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_physics_exception_leaves_deferral_and_is_never_retried(monkeypatch, mode, error):
    events, calls = [], []
    fake_deferral(monkeypatch, events)
    failure = error("owner failed")

    def physics(*args, **kwargs):
        calls.append((args, kwargs))
        raise failure

    monkeypatch.setattr(M, "run_turn_result", physics)
    with pytest.raises(error) as caught:
        invoke(mode, NS(run_turn_result=physics), "input", seed=17)
    assert caught.value is failure
    assert calls == [(("input",), {"seed": 17})]
    assert events == ["enter", ("exit", error, failure)]


def test_broken_observer_after_physics_is_not_a_reason_to_replay(monkeypatch):
    events, calls = [], []
    fake_deferral(monkeypatch, events)

    def physics(*args, **kwargs):
        calls.append((args, kwargs))
        return object()

    def broken(*args, **kwargs):
        physics(*args, **kwargs)
        raise ValueError("broken observer contract")

    monkeypatch.setattr(M, "run_turn_result", physics)
    with pytest.raises(ValueError, match="broken observer contract"):
        invoke("provided", NS(run_turn_result=broken), "input")
    assert calls == [(("input",), {})]
    assert events[-1][0:2] == ("exit", ValueError)


def signal_fakes(monkeypatch, *, custom=False, main_thread=True):
    """Exercise the real deferral without touching OS handlers or threads."""
    original = (lambda *args: None) if custom else signal.default_int_handler
    state, writes = {"handler": original}, []

    def install(signum, handler):
        assert signum == signal.SIGINT
        prior, state["handler"] = state["handler"], handler
        writes.append(handler)
        return prior

    thread = object()
    monkeypatch.setattr(M, "signal", NS(
        SIGINT=signal.SIGINT, default_int_handler=signal.default_int_handler,
        getsignal=lambda signum: state["handler"], signal=install))
    monkeypatch.setattr(M, "threading", NS(
        current_thread=lambda: thread if main_thread else object(), main_thread=lambda: thread))
    return state, writes, original


@pytest.mark.parametrize("mode", ["omitted", "provided"])
def test_actual_deferral_finishes_the_first_interrupt_in_either_dispatch(monkeypatch, mode, capsys):
    state, writes, _ = signal_fakes(monkeypatch)
    result, calls = object(), []

    def physics(*args, **kwargs):
        calls.append(1)
        state["handler"](signal.SIGINT, None)
        assert state["handler"] is signal.default_int_handler
        return result

    monkeypatch.setattr(M, "run_turn_result", physics)
    answer, interrupted = invoke(mode, NS(run_turn_result=physics), "input")
    assert answer is result and interrupted is True and calls == [1]
    assert len(writes) == 2 and writes[-1] is signal.default_int_handler
    assert "finishing this turn" in capsys.readouterr().err


def test_second_interrupt_cancels_observed_owner_without_a_second_call(monkeypatch):
    state, writes, _ = signal_fakes(monkeypatch)
    calls = []

    def physics(*args, **kwargs):
        calls.append(1)
        state["handler"](signal.SIGINT, None)
        state["handler"](signal.SIGINT, None)

    monkeypatch.setattr(M, "run_turn_result", physics)
    with pytest.raises(KeyboardInterrupt):
        invoke("provided", NS(run_turn_result=physics), "input")
    assert calls == [1] and len(writes) == 2
    assert state["handler"] is signal.default_int_handler


@pytest.mark.parametrize("custom,main_thread", [(True, True), (False, False)])
def test_custom_handler_and_nonmain_identity_remain_inert(monkeypatch, custom, main_thread):
    state, writes, original = signal_fakes(monkeypatch, custom=custom, main_thread=main_thread)
    result = object()
    answer, interrupted = invoke("provided", NS(run_turn_result=lambda: result))
    assert answer is result and interrupted is False
    assert state["handler"] is original and writes == []


def module_tree():
    return ast.parse(Path(M.__file__).read_text())


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("interrupted", [False, True])
def test_actual_execute_run_dispatch_fragment_preserves_handoff(mode, interrupted):
    # Execute the literal production routing block, avoiding all World setup.
    owner = next(node for node in module_tree().body
                 if isinstance(node, ast.FunctionDef) and node.name == "execute_run")
    target = ast_dump(ast.parse("practice_observer is None", mode="eval").body)
    branch = [node for node in ast.walk(owner) if isinstance(node, ast.If)
              and ast_dump(node.test) == target]
    assert len(branch) == 1
    result, observer, calls = object(), object(), []

    def helper(*args, **kwargs):
        calls.append((args, kwargs))
        return result, interrupted

    values = {name: object() for name in ["world", "action_selector", "_noop_narrator",
              "agent_bridge", "economy_tracker", "ecology_runtime", "politics_runtime", "_pending"]}
    values.update(_run_turn_deferring_sigint=helper, practice_observer=observer if mode == "provided" else None,
                  seed=43, turn_num=5, num_turns=6)
    fragment = ast.fix_missing_locations(ast.Module(body=branch, type_ignores=[]))
    exec(compile(fragment, "main.execute_run::dispatch", "exec"), values)
    expected = {"action_selector": values["action_selector"], "narrator": values["_noop_narrator"],
        "seed": 48, "agent_bridge": values["agent_bridge"], "economy_tracker": values["economy_tracker"],
        "ecology_runtime": values["ecology_runtime"], "politics_runtime": values["politics_runtime"],
        "force_settlement_detection": True, "pending_injections": values["_pending"]}
    if mode == "provided":
        expected["practice_observer"] = observer
    assert calls == [((values["world"],), expected)]
    assert values["turn_result"] is result and values["_interrupt_requested"] is interrupted


def test_new_parameter_is_only_explicit_keyword_only_default_none():
    for function in (M.execute_run, M._run_turn_deferring_sigint):
        signature = inspect.signature(function)
        parameter = signature.parameters["practice_observer"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is None
        bound = signature.bind_partial()
        bound.apply_defaults()
        assert bound.arguments["practice_observer"] is None


def test_entire_default_main_AST_matches_qualified_parent():
    target = ast_dump(ast.parse("practice_observer is None", mode="eval").body)

    class Defaults(ast.NodeTransformer):
        active = False
        functions = branches = 0

        def visit_FunctionDef(self, node):
            prior = self.active
            self.active = node.name in {"execute_run", "_run_turn_deferring_sigint"}
            if self.active:
                pairs = list(zip(node.args.kwonlyargs, node.args.kw_defaults))
                selected = [(arg, value) for arg, value in pairs if arg.arg == "practice_observer"]
                assert len(selected) == 1 and isinstance(selected[0][1], ast.Constant)
                assert selected[0][1].value is None
                pairs = [(arg, value) for arg, value in pairs if arg.arg != "practice_observer"]
                node.args.kwonlyargs, node.args.kw_defaults = [p[0] for p in pairs], [p[1] for p in pairs]
                self.functions += 1
            node = self.generic_visit(node)
            self.active = prior
            return node

        def visit_If(self, node):
            if self.active and ast_dump(node.test) == target:
                self.branches += 1
                return [self.visit(child) for child in node.body]
            return self.generic_visit(node)

    projector = Defaults()
    projected = projector.visit(module_tree())
    assert (projector.functions, projector.branches) == (2, 2)
    actual = hashlib.sha256(ast_dump(projected).encode()).hexdigest()
    assert actual == BASE_MAIN_AST_SHA256, f"default main AST differs from {BASE}"
