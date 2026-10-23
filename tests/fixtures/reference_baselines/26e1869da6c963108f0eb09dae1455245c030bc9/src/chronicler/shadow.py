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

        batch = pa.record_batch({
            "turn": pa.array(turns, type=pa.uint32()),
            "civ_id": pa.array(civ_ids, type=pa.uint16()),
            "agent_population": pa.array(a_pop, type=pa.uint32()),
            "agent_military": pa.array(a_mil, type=pa.uint32()),
            "agent_economy": pa.array(a_econ, type=pa.uint32()),
            "agent_culture": pa.array(a_cult, type=pa.uint32()),
            "agent_stability": pa.array(a_stab, type=pa.uint32()),
            "agg_population": pa.array(g_pop, type=pa.uint32()),
            "agg_military": pa.array(g_mil, type=pa.uint32()),
            "agg_economy": pa.array(g_econ, type=pa.uint32()),
            "agg_culture": pa.array(g_cult, type=pa.uint32()),
            "agg_stability": pa.array(g_stab, type=pa.uint32()),
        }, schema=SHADOW_SCHEMA)
        self._writer.write_batch(batch)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
