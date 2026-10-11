"""Deterministic overlap gates for invocation-local example recording."""
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path
import runpy
import sys
from threading import Barrier, Event
from types import ModuleType, SimpleNamespace

import pytest

from chronicler import governance_kernel_harness as h
from chronicler import governance_measurements as gm

from test_governance_measurements import carry, initial, frame, enact_and_suppress, policy, IDENTITY, ORIGIN

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/governance_measurement_report.py'


def script_module():
    # A distinct script invocation namespace; its accepted public harness is h.
    namespace = runpy.run_path(str(SCRIPT))
    return SimpleNamespace(**namespace)


def experiment_for(*, marker, ready, release, original):
    """Synthetic calls distinguish final openings without executing a kernel."""
    source = '''
def experiment():
    assert h.run_kernel_frame is not original
    first = h.run_kernel_frame(opening=(marker, 'first'))
    ready.wait(timeout=10)
    release.wait(timeout=10)
    assert h.run_kernel_frame is not original
    return h.run_kernel_frame(opening=(marker, 'last'))
'''
    bindings = dict(h=h, marker=marker, ready=ready, release=release, original=original)
    exec(compile(source, '<synthetic overlap experiment>', 'exec'), bindings)
    return bindings['experiment'], bindings


def test_overlapping_calls_capture_only_their_own_final_opening(monkeypatch):
    # Two wrappers overlap while an unrelated direct caller remains unwrapped.
    # Barriers assert overlap instead of relying on scheduler timing or sleeps.
    ready, release = Barrier(3), Barrier(3)
    observed = []

    def original(*, opening):
        observed.append(opening)
        return ('result', opening)

    monkeypatch.setattr(h, 'run_kernel_frame', original)
    script = script_module()
    first, first_globals = experiment_for(marker='one', ready=ready,
                                          release=release, original=original)
    second, second_globals = experiment_for(marker='two', ready=ready,
                                            release=release, original=original)
    # Use a thread's marker to choose its own function. No global source edit.
    from threading import current_thread
    by_thread = {}

    def run_path(*args, **kwargs):
        return {'experiment': by_thread[current_thread().name]}

    monkeypatch.setitem(script.run_example.__globals__, 'runpy', SimpleNamespace(run_path=run_path))

    def call(experiment):
        by_thread[current_thread().name] = experiment
        return script.run_example()

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(call, experiment) for experiment in (first, second)]
        try:
            ready.wait(timeout=10)
            assert h.run_kernel_frame is original
            assert h.run_kernel_frame(opening=('unrelated', 'direct')) == (
                'result', ('unrelated', 'direct'))
        finally:
            release.wait(timeout=10)
        pairs = [future.result(timeout=10) for future in pending]
    assert pairs == [(('one', 'last'), ('result', ('one', 'last'))),
                     (('two', 'last'), ('result', ('two', 'last')))]
    assert h.run_kernel_frame is original
    assert first_globals['h'] is second_globals['h'] is h
    assert len(observed) == 5


def test_failure_during_overlap_cannot_restore_or_leak_another_call(monkeypatch):
    entered, release = Event(), Event()

    def original(*, opening):
        return opening

    monkeypatch.setattr(h, 'run_kernel_frame', original)
    bindings = dict(h=h, entered=entered, release=release)
    exec('''
def experiment():
    h.run_kernel_frame(opening='failure-opening')
    entered.set()
    assert release.wait(timeout=10)
    raise RuntimeError('synthetic failure')
''', bindings)
    script = script_module()
    monkeypatch.setitem(script.run_example.__globals__, 'runpy',
                        SimpleNamespace(run_path=lambda *a, **k: {'experiment': bindings['experiment']}))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(script.run_example)
        try:
            assert entered.wait(timeout=10)
            assert h.run_kernel_frame is original
            assert h.run_kernel_frame(opening='unrelated-success') == 'unrelated-success'
        finally:
            release.set()
        with pytest.raises(RuntimeError, match='synthetic failure'):
            pending.result(timeout=10)
    assert h.run_kernel_frame is original and bindings['h'] is h


def test_real_example_bytes_and_original_function_bindings_are_preserved(monkeypatch):
    script = script_module()
    example = runpy.run_path(str(script.EXAMPLE_PATH))
    function = example['experiment']
    original_globals = dict(function.__globals__)
    original = h.run_kernel_frame
    monkeypatch.setitem(script.run_example.__globals__, 'runpy',
                        SimpleNamespace(run_path=lambda *a, **k: example))
    opening, result = script.run_example()
    assert opening.effective_turn == 1 and result.carry.effective_turn == 2
    assert function.__globals__ == original_globals
    assert function.__globals__['h'] is h
    assert h.run_kernel_frame is original


def test_no_observed_calls_and_non_function_examples_are_refused(monkeypatch):
    script = script_module()
    original = h.run_kernel_frame
    monkeypatch.setitem(script.run_example.__globals__, 'runpy',
                        SimpleNamespace(run_path=lambda *a, **k: {'experiment': lambda: 'nothing'}))
    with pytest.raises(SystemExit, match='no kernel frame'):
        script.run_example()
    class CallableExample:
        def __call__(self):
            return None

    monkeypatch.setitem(script.run_example.__globals__, 'runpy',
                        SimpleNamespace(run_path=lambda *a, **k: {'experiment': CallableExample()}))
    with pytest.raises(SystemExit, match='Python function'):
        script.run_example()
    assert h.run_kernel_frame is original


@pytest.mark.parametrize("fail_a", [False, True])
def test_actual_overlapping_source_loads_preserve_argv_module_slot_and_pairing(monkeypatch, tmp_path, fail_a):
    """Default loader executes real files with deterministically crossed loads.

    A starts loading, then B starts loading, then A exits before B. That ordering
    exposes runpy's process-global restore race without sleeps or a mocked loader.
    """
    script = script_module()
    assert script.runpy.run_path is script._load_trusted_source
    original = h.run_kernel_frame
    argv_object, argv_before = sys.argv, tuple(sys.argv)
    sentinel = ModuleType("existing_run_path_slot")
    monkeypatch.setitem(sys.modules, "<run_path>", sentinel)
    sync = ModuleType("governance_loader_test_sync")
    sync.openings = {"A": carry(initial(balance=Fraction(1, 10))),
                     "B": carry(initial(balance=Fraction(3, 10)))}
    sync.observations = frame(enact_and_suppress())
    sync.policy = policy()
    a_loading, b_loading, a_finished = Event(), Event(), Event()
    def unchanged():
        assert sys.argv is argv_object and tuple(sys.argv) == argv_before
        assert sys.modules.get("<run_path>") is sentinel
        assert h.run_kernel_frame is original
    def loading(name):
        unchanged()
        if name == "A":
            a_loading.set()
            assert b_loading.wait(10), "B did not enter actual module loading"
            unchanged()
            if fail_a:
                raise RuntimeError("actual A module-load failure")
        else:
            b_loading.set()
            assert a_finished.wait(10), "A did not finish loading/execution"
            unchanged()
    sync.loading = loading
    monkeypatch.setitem(sys.modules, sync.__name__, sync)
    paths = {}
    for name in ("A", "B"):
        paths[name] = tmp_path / ("load_" + name + ".py")
        paths[name].write_text(
            "import governance_loader_test_sync as sync\n"
            "sync.loading(" + repr(name) + ")\n"
            "from chronicler import governance_kernel_harness as h\n"
            "def experiment():\n"
            " return h.run_kernel_frame(enabled=True,opening=sync.openings[" + repr(name) +
            "],observations=sync.observations,policy=sync.policy)\n", encoding="utf-8")
    serial = {name: h.run_kernel_frame(enabled=True, opening=opening,
        observations=sync.observations, policy=sync.policy) for name, opening in sync.openings.items()}
    def call(name):
        try:
            if name == "B":
                assert a_loading.wait(10), "A did not start actual module loading"
            return script.run_example(paths[name])
        finally:
            if name == "A":
                a_finished.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {name: pool.submit(call, name) for name in ("A", "B")}
        if fail_a:
            with pytest.raises(RuntimeError, match="actual A module-load failure"):
                pending["A"].result(timeout=15)
        else:
            opening, result = pending["A"].result(timeout=15)
            assert opening is sync.openings["A"] and result == serial["A"]
            gm.measure_governance_result(opening=opening, result=result,
                                         origin=ORIGIN, source_identity=IDENTITY)
        opening, result = pending["B"].result(timeout=15)
        assert opening is sync.openings["B"] and result == serial["B"]
        gm.measure_governance_result(opening=opening, result=result,
                                     origin=ORIGIN, source_identity=IDENTITY)
    unchanged()


def test_actual_loader_preserves_source_metadata_encoding_and_exception_semantics(tmp_path):
    script = script_module()
    source = tmp_path / "encoded.py"
    source.write_bytes(b"# coding: latin-1\nlabel = 'caf\xe9'\n")
    argv_before, slot_before = tuple(sys.argv), sys.modules.get("<run_path>")
    namespace = script._load_trusted_source(str(source))
    assert namespace["label"] == "caf\u00e9"
    assert namespace["__name__"] == "<run_path>"
    assert namespace["__file__"] == str(source)
    assert namespace["__package__"] == "" and namespace["__spec__"] is None
    assert tuple(sys.argv) == argv_before and sys.modules.get("<run_path>") is slot_before
    source.write_text("raise RuntimeError('actual source failure')\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="actual source failure") as raised:
        script.run_example(source)
    traceback = raised.value.__traceback__
    filenames = []
    while traceback is not None:
        filenames.append(traceback.tb_frame.f_code.co_filename)
        traceback = traceback.tb_next
    assert str(source) in filenames
    source.write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(SyntaxError) as raised:
        script.run_example(source)
    assert raised.value.filename == str(source)
    assert tuple(sys.argv) == argv_before and sys.modules.get("<run_path>") is slot_before
