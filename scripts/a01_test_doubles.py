"""Explicit pytest-only slice-3 scaffolding, never a production fallback.

Enable with PYTHONPATH=scripts:src python -m pytest -p a01_test_doubles.
Remove the flag after slices 1/2 land. Importing this plugin aborts when either
real interface exists, so it cannot silently replace integrated implementation.
"""
from dataclasses import dataclass
from importlib.util import find_spec
import sys
from types import ModuleType


DOUBLE_MODE = "slice3 test-only contract doubles; NOT integrated acceptance"


def install():
    from chronicler import simulation
    if find_spec("chronicler.turn_artifacts") is not None or hasattr(simulation, "run_turn_result"):
        raise RuntimeError("A01 doubles require absent slices 1 and 2; run integrated tests without plugin")
    module = ModuleType("chronicler.turn_artifacts")

    @dataclass(frozen=True, slots=True)
    class Stamp:
        source_turn: int
        stage: str

    class AgentRows:
        def __init__(self, stamp, batch):
            self.stamp, self.batch = stamp, batch
            self._cache = {}

        def has(self, name):
            return name in self.batch.column_names

        def ints(self, name):
            if name not in self._cache:
                self._cache[name] = tuple(self.batch.column(name).to_pylist())
            return self._cache[name]

        floats = ints

    @dataclass(frozen=True, slots=True)
    class TurnObservation:
        source_turn: int
        completed_turn: int
        phase10_agents: object | None

    @dataclass(frozen=True, slots=True)
    class TurnResult:
        chronicle_text: str
        observation: TurnObservation

    for cls in (Stamp, AgentRows, TurnObservation, TurnResult):
        setattr(module, cls.__name__, cls)
    sys.modules[module.__name__] = module

    def result(world, *args, **kwargs):
        source_turn = world.turn
        text = simulation.run_turn(world, *args, **kwargs)
        batch = getattr(world, "_agent_snapshot", None)
        rows = None if batch is None else AgentRows(Stamp(source_turn, "phase10_entry"), batch)
        return TurnResult(text, TurnObservation(source_turn, world.turn, rows))

    simulation.run_turn_result = result


def pytest_report_header(config):
    return DOUBLE_MODE


install()
