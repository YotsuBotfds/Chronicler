"""Shadow mode: Arrow IPC logger for agent-vs-aggregate comparison."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
import pyarrow as pa
import pyarrow.ipc as ipc

if TYPE_CHECKING:
    from chronicler.models import WorldState

SHADOW_SCHEMA = pa.schema([
    ("turn", pa.uint32()),
    ("civ_id", pa.uint16()),
    ("agent_population", pa.uint32()),
    ("agent_military", pa.uint32()),
    ("agent_economy", pa.uint32()),
    ("agent_culture", pa.uint32()),
    ("agent_stability", pa.uint32()),
    ("agg_population", pa.uint32()),
    ("agg_military", pa.uint32()),
    ("agg_economy", pa.uint32()),
    ("agg_culture", pa.uint32()),
    ("agg_stability", pa.uint32()),
])


class ShadowLogger:
    """Writes per-turn agent-vs-aggregate comparison data as Arrow IPC."""

    def __init__(self, output_path: Path):
        self._path = output_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._writer: ipc.RecordBatchFileWriter | None = None
        # Each logged turn's columns, so an exact checkpoint can carry the
        # file's content and a resumed run rewrite it (see ``retarget``).
        self._logged: list[dict[str, list[int]]] = []

    def log_turn(self, turn: int, agent_aggs: pa.RecordBatch, world: WorldState) -> None:
        if self._writer is None:
            sink = pa.OSFile(str(self._path), "wb")
            self._writer = ipc.new_file(sink, SHADOW_SCHEMA)

        civ_map = {i: c for i, c in enumerate(world.civilizations)}
        agent_civ_ids = agent_aggs.column("civ_id").to_pylist()
        agent_pops = agent_aggs.column("population").to_pylist()
        agent_mils = agent_aggs.column("military").to_pylist()
        agent_econs = agent_aggs.column("economy").to_pylist()
        agent_cults = agent_aggs.column("culture").to_pylist()
        agent_stabs = agent_aggs.column("stability").to_pylist()

        turns, civ_ids = [], []
        a_pop, a_mil, a_econ, a_cult, a_stab = [], [], [], [], []
        g_pop, g_mil, g_econ, g_cult, g_stab = [], [], [], [], []

        for idx in range(len(agent_civ_ids)):
            civ_id = agent_civ_ids[idx]
            civ = civ_map.get(civ_id)
            if civ is None:
                continue
            turns.append(turn)
            civ_ids.append(civ_id)
            a_pop.append(agent_pops[idx])
            a_mil.append(agent_mils[idx])
            a_econ.append(agent_econs[idx])
            a_cult.append(agent_cults[idx])
            a_stab.append(agent_stabs[idx])
            g_pop.append(civ.population)
            g_mil.append(civ.military)
            g_econ.append(civ.economy)
            g_cult.append(civ.culture)
            g_stab.append(civ.stability)

        columns = {
            "turn": turns, "civ_id": civ_ids,
            "agent_population": a_pop, "agent_military": a_mil, "agent_economy": a_econ,
            "agent_culture": a_cult, "agent_stability": a_stab,
            "agg_population": g_pop, "agg_military": g_mil, "agg_economy": g_econ,
            "agg_culture": g_cult, "agg_stability": g_stab,
        }
        self._logged.append(columns)
        self._writer.write_batch(_shadow_batch(columns))

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()

    # Exact checkpoints (chronicler.run_checkpoint) carry the logged columns,
    # not the open file. A restored logger writes nothing until ``retarget``.
    def __getstate__(self) -> dict:
        return {"path": str(self._path), "logged": self._logged}

    def __setstate__(self, state: dict) -> None:
        self._path = Path(state["path"])
        self._writer = None
        self._logged = state["logged"]

    def retarget(self, output_path: Path) -> None:
        """Rewrite every logged turn to ``output_path`` and log there from now
        on: the file an uninterrupted run holds at this turn."""
        self._path = output_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._writer = None
        if self._logged:
            sink = pa.OSFile(str(self._path), "wb")
            self._writer = ipc.new_file(sink, SHADOW_SCHEMA)
            for columns in self._logged:
                self._writer.write_batch(_shadow_batch(columns))


def _shadow_batch(columns: dict[str, list[int]]) -> pa.RecordBatch:
    return pa.record_batch({
        name: pa.array(columns[name], type=SHADOW_SCHEMA.field(name).type)
        for name in SHADOW_SCHEMA.names
    }, schema=SHADOW_SCHEMA)
