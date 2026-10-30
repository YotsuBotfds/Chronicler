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



# Intentional active-world admission is outside the historical observer/budget
# projection. Keep its exact two source/AST witnesses and precise setup sites;
# the immutable default-main digest below continues to cover every other node.
_CIV_ADMISSION_SOURCE = "from chronicler.ffi_constants import check_civ_capacity\ncheck_civ_capacity(world)\n"
_CIV_ADMISSION_RAW_SHA256 = "b8f4b0ece297d14642981b8c9c35aca29eb4b0194a6c01ece1f0190292e3590e"
_CIV_ADMISSION_AST_SHA256 = "57c08d72d627264c720f794adee0f952714e2f147019742f6e233468626004e5"


def _main_without_reviewed_civ_admissions(source):
    assert hashlib.sha256(_CIV_ADMISSION_SOURCE.encode()).hexdigest() == _CIV_ADMISSION_RAW_SHA256
    pair = ast.parse(_CIV_ADMISSION_SOURCE).body
    assert hashlib.sha256(ast_dump(ast.Module(body=pair, type_ignores=[])).encode()).hexdigest() == _CIV_ADMISSION_AST_SHA256
    # Exactly two unmodified import/call pairs, at the approved indentation.
    for indent in ("        ", "    "):
        raw = "".join(indent + line + "\n" for line in _CIV_ADMISSION_SOURCE.splitlines())
        assert source.count(raw) == 1, "reviewed capacity admission source changed"
    tree = ast.parse(source)
    owner = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "execute_run"]
    assert len(owner) == 1
    body = owner[0].body
    setup = [(i, n) for i, n in enumerate(body) if isinstance(n, ast.If)
             and ast_dump(n.test) == ast_dump(ast.parse("_resume_state is not None", mode="eval").body)
             and n.body and ast_dump(n.body[0]) == ast_dump(ast.parse("world = _resume_state.world").body[0])]
    assert len(setup) == 1
    setup_index, setup_node = setup[0]
    provided = setup_node.orelse
    assert len(provided) == 1 and isinstance(provided[0], ast.If)
    assert ast_dump(provided[0].test) == ast_dump(ast.parse("world is not None", mode="eval").body)
    resume = provided[0].orelse
    assert len(resume) == 1 and isinstance(resume[0], ast.If)
    assert ast_dump(resume[0].test) == ast_dump(ast.Name(id="resume_path", ctx=ast.Load()))
    fresh = resume[0].orelse
    sites = [(i, n) for i, n in enumerate(fresh) if isinstance(n, ast.If)
             and ast_dump(n.test) == ast_dump(ast.Name(id="scenario_config", ctx=ast.Load()))]
    assert len(sites) == 1
    fresh_index = sites[0][0] + 1
    for statements, index, next_test in (
        (fresh, fresh_index, "sim_client"),
        (body, setup_index + 1, "checkpoint_resume is None"),
    ):
        assert [ast_dump(n) for n in statements[index:index + 2]] == [ast_dump(n) for n in pair], "capacity admission moved or changed"
        following = statements[index + 2]
        assert isinstance(following, ast.If)
        assert ast_dump(following.test) == ast_dump(ast.parse(next_test, mode="eval").body)
    # Delete only the two witnessed pairs after both locations were checked.
    del fresh[fresh_index:fresh_index + 2]
    del body[setup_index + 1:setup_index + 3]
    return tree


_PUBLIC_GRAIN_SETUP = '    _shipments = getattr(args, "public_grain_shipments", None)\n    if _shipments is not None:\n        from chronicler.public_grain_shipments import set_public_grain_shipments_enabled\n        set_public_grain_shipments_enabled(world, _shipments, agent_mode=agent_mode)\n'
_PUBLIC_GRAIN_PARSER = '    parser.add_argument("--public-grain-shipments", action=argparse.BooleanOptionalAction, default=None,\n                        help="Default-off public grain: foreign direct-neighbor orders arrive next Phase10, "\n                             "after its opening; requires --grain-reserves and agents. Disabling drains paid cargo.")\n'


def _main_without_reviewed_public_grain_shipments(source):
    tree = ast.parse(source)
    for name, block, following in (
        ("_configure_run", _PUBLIC_GRAIN_SETUP, '    # Community anchoring switch (persisted on the world): community ties\n'),
        ("_build_parser", _PUBLIC_GRAIN_PARSER, '    parser.add_argument("--community-anchoring", action=argparse.BooleanOptionalAction, default=None,\n'),
    ):
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
        assert len(functions) == 1
        node = functions[0]
        text = "".join(source.splitlines(keepends=True)[node.lineno-1:node.end_lineno])
        assert source.count(block) == text.count(block) == 1
        assert text.count(block + following) == 1, "public grain optional source moved or changed"
    return source.replace(_PUBLIC_GRAIN_SETUP, "", 1).replace(_PUBLIC_GRAIN_PARSER, "", 1)

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
    # These are only the reviewed optional routing/admission additions. Keep the
    # original qualified module digest, including every unrelated docstring.
    parameters = {
        "_write_state_checkpoint": (("artifact_budget", None),),
        "_save_memory_streams": (("artifact_budget", None),),
        "_run_turn_deferring_sigint": (("practice_observer", None),),
        "execute_run": (("practice_observer", "Any | None"), ("artifact_budget", "Any | None")),
        "_configure_run": (("artifact_budget", None),),
    }
    # Exact canonical AST shapes, in lexical order within each explicit scope.
    # A changed enabled branch, predicate or retained call requires new review;
    # it cannot disappear behind a generic None-specialization rule.
    branches = {
        "_write_state_checkpoint": (
            "ce762ed89933e880dee18ae98cca0e954afd3050b3ed6e177c893f35130609d3",
        ),
        "_save_memory_streams": (
            "4b22c62f16ad584271e334020273e7d4e7a1072eee2747116afd6bc88a135faf",
            "848627863aca39c3e1d46da52ef45915c9aa4dba5148d77a20be56cd20cde074",
        ),
        "_run_turn_deferring_sigint": (
            "68f7ef6aa0ca84067b6c7aa2abb9b38c47d2fc6084de5755865ed2d09d15c506",
        ),
        "execute_run": (
            "971177e690979a664fa2dd2831fc22e1e68980fe4785964fd532b1041faa1113",
            "b821c7681e4e59a71a8b57082ffa614ef247257fb1df5010ef9ef88af4d2ea7f",
            "a0a95f8d7143f35a731efeb683e02ab7931ffb0c2223e2926907cc27aeb71221",
            "821d8f9bc41e3cd8e85a9fbf0b31c9ab3e0543931179fa3a03c458958e973eda",
            "35a182173c13023b14b1a4d6a34c8b9be73e7a51f7de4836755a5b162b02b58f",
            "7a1be2cf45d0c3385c86380d7cebd850dcfd21b3736122273c140a9c510ca798",
            "35a182173c13023b14b1a4d6a34c8b9be73e7a51f7de4836755a5b162b02b58f",
            "82529f78d5a11db9892f39bbbfad775e5e724472b3c734829aa9417a93b701a5",
            "81527809f85ab7b73e5a5ef129a0f68bbbaa99250c18e0dd4d16e807ce8a2001",
            "72896630165a2f42037bc22980bdc68432e355dda9783af4a70e196a93014a5c",
        ),
        "execute_run._save_exact": (
            "1d9cbe5ffb0745f6d0cd8d856a1f4f86c72eaeead7c01a72948073fdafeded94",
        ),
        "_configure_run": (
            "4c16a0633469d152077f65ae7aa3d808e0444c2931ab4f79bee72c33ff8f6749",
        ),
    }
    decisions = {
        ast_dump(ast.parse("artifact_budget is None", mode="eval").body): ("artifact_budget", True),
        ast_dump(ast.parse("artifact_budget is not None", mode="eval").body): ("artifact_budget", False),
        ast_dump(ast.parse("practice_observer is None", mode="eval").body): ("practice_observer", True),
    }
    budget_documentation = (
        "    artifact_budget : object or None\n"
        "        Explicit caller-owned ordinary-output admission. The optional path is\n"
        "        limited to fresh hybrid runs without exact checkpoints. It does not\n"
        "        implement owner/log admission or qualify an enabled study.\n"
    )

    class Defaults(ast.NodeTransformer):
        def __init__(self):
            self.scope = ()
            self.functions = set()
            self.parameters = {"artifact_budget": 0, "practice_observer": 0}
            self.branches = {scope: 0 for scope in branches}
            self.predicates = {"artifact_budget": 0, "practice_observer": 0}
            self.documentation = 0

        def visit_FunctionDef(self, node):
            prior = self.scope
            self.scope = (*prior, node.name)
            scope = ".".join(self.scope)
            if scope in parameters:
                assert scope not in self.functions, f"duplicate reviewed function: {scope}"
                expected = parameters[scope]
                assert len(node.args.kwonlyargs) == len(node.args.kw_defaults) == len(expected)
                for arg, default, (name, annotation) in zip(
                        node.args.kwonlyargs, node.args.kw_defaults, expected):
                    expected_arg = ast.arg(arg=name, annotation=(
                        ast.parse(annotation, mode="eval").body if annotation else None), type_comment=None)
                    assert ast_dump(arg) == ast_dump(expected_arg), f"reviewed keyword shape changed: {scope}"
                    assert ast_dump(default) == ast_dump(ast.Constant(value=None, kind=None))
                    self.parameters[name] += 1
                node.args.kwonlyargs, node.args.kw_defaults = [], []
                self.functions.add(scope)
            if scope == "execute_run":
                doc = node.body[0]
                assert isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant)
                assert type(doc.value.value) is str
                suffix = budget_documentation + "    "
                assert doc.value.value.count(budget_documentation) == 1
                assert doc.value.value.endswith(suffix), "exact reviewed budget documentation suffix changed"
                doc.value.value = doc.value.value[:-len(suffix)] + "    "
                self.documentation += 1
            node = self.generic_visit(node)
            self.scope = prior
            return node

        def visit_ClassDef(self, node):
            prior = self.scope
            self.scope = (*prior, node.name)
            node = self.generic_visit(node)
            self.scope = prior
            return node

        def visit_If(self, node):
            decision = decisions.get(ast_dump(node.test))
            if decision is None:
                return self.generic_visit(node)
            scope = ".".join(self.scope)
            assert scope in branches, f"unexpected optional predicate scope: {scope}"
            index = self.branches[scope]
            assert index < len(branches[scope]), f"extra optional branch: {scope}"
            shape = hashlib.sha256(ast_dump(node).encode()).hexdigest()
            assert shape == branches[scope][index], f"reviewed optional branch shape changed: {scope}[{index}]"
            self.branches[scope] += 1
            name, keep_body = decision
            self.predicates[name] += 1
            retained = []
            for child in node.body if keep_body else node.orelse:
                projected = self.visit(child)
                if isinstance(projected, list):
                    retained.extend(projected)
                elif projected is not None:
                    retained.append(projected)
            return retained

    projector = Defaults()
    projected = projector.visit(_main_without_reviewed_civ_admissions(
        _main_without_reviewed_public_grain_shipments(Path(M.__file__).read_text())))
    assert projector.functions == set(parameters)
    assert projector.parameters == {"artifact_budget": 4, "practice_observer": 2}
    assert projector.branches == {scope: len(expected) for scope, expected in branches.items()}
    assert projector.predicates == {"artifact_budget": 14, "practice_observer": 2}
    assert projector.documentation == 1
    actual = hashlib.sha256(ast_dump(projected).encode()).hexdigest()
    assert actual == BASE_MAIN_AST_SHA256, f"default main AST differs from {BASE}"

    # Two bounded literal mutations stay visible; no code object is executed.
    literal = 'def unrelated():\n    """Preserve unrelated documentation."""\n    return physics(41)\n'
    untouched = ast_dump(ast.parse(literal))
    assert ast_dump(Defaults().visit(ast.parse(literal))) == untouched
    for changed in (literal.replace("unrelated documentation", "changed documentation"),
                    literal.replace("physics(41)", "physics(42)")):
        assert changed != literal
        assert ast_dump(Defaults().visit(ast.parse(changed))) != untouched


@pytest.mark.parametrize("mutation", ["predicate", "location", "extra_effect", "parser"])
def test_public_grain_source_inverse_refuses_unreviewed_changes(mutation):
    source = Path(M.__file__).read_text()
    if mutation == "predicate":
        changed = source.replace("if _shipments is not None:", "if _shipments is None:", 1)
    elif mutation == "location":
        changed = source.replace(_PUBLIC_GRAIN_SETUP, "", 1)
        changed = changed.replace("    return parser\n", _PUBLIC_GRAIN_SETUP + "    return parser\n", 1)
    elif mutation == "extra_effect":
        changed = source.replace(_PUBLIC_GRAIN_SETUP, _PUBLIC_GRAIN_SETUP + "    world.turn += 1\n", 1)
    else:
        changed = source.replace("--public-grain-shipments", "--public-grain-shipping", 1)
    assert changed != source
    with pytest.raises(AssertionError):
        _main_without_reviewed_public_grain_shipments(changed)


@pytest.mark.parametrize("mutation", ["wrong_helper", "wrong_location", "between_pair", "extra_effect"])
def test_capacity_admission_projection_refuses_changed_shape_or_location(mutation):
    source = Path(M.__file__).read_text()
    pair = "".join("        " + line + "\n" for line in _CIV_ADMISSION_SOURCE.splitlines())
    assert source.count(pair) == 1
    if mutation == "wrong_helper":
        changed = source.replace(pair, pair.replace("check_civ_capacity(world)", "has_civ_capacity(world)"), 1)
    elif mutation == "wrong_location":
        changed = source.replace(pair, "", 1)
        marker = "        # Apply scenario overrides if provided\n"
        assert changed.count(marker) == 1
        changed = changed.replace(marker, pair + marker, 1)
    elif mutation == "between_pair":
        changed = source.replace(pair, pair.replace("        check_civ_capacity(world)", "        world.turn += 1\n        check_civ_capacity(world)"), 1)
    else:
        changed = source.replace(pair, pair + "        world.turn += 1\n", 1)
    with pytest.raises(AssertionError):
        _main_without_reviewed_civ_admissions(changed)
