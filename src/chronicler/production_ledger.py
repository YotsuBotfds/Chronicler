"""Realized production and extraction ledger (2026-10).

docs/integration/production-ledger.md. One row per region and occupied
resource slot per turn, from just before the Phase 9 ecology tick to just
after it: what the slot produced this turn (the economy's ``slot_output``),
its stock before and after (a mineral reserve, a fish stock), what was taken
from that stock and what grew back, what the earlier proxy rule would have
charged, and the slot's degradation (the overextraction track and the land
it grows on).

The ledger only reads. It is built when the validation sidecar is written
(``validation_resource_ledger.arrow`` beside the other validation files; the
bundle is untouched) or when ``CHRONICLER_CHECK_RESOURCES=1`` asks for its
checks; otherwise nothing is built. Its checks:

* minerals: the reserve lost equals the reported draw, a reserve never
  grows, and where the economy reported output the draw is that output over
  the deposit's target crew at the depletion rate (no output, no draw);
* fish stocks: stock plus outstanding allowance changes by exactly the
  regrowth less the fish that left the water (landed, plus any allowance
  charged without being landed: none under the landed-catch rule);
* goods: the slots' output, the foraged grain and the wares made add up to
  the economy's production, which is what entered the stocks;
* the overextraction streak and the mines' soil charge read the take the
  rules say (realized output where reported, the proxy otherwise).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chronicler.economy import EconomyResult
    from chronicler.models import WorldState

RESOURCE_CHECK_ENV = "CHRONICLER_CHECK_RESOURCES"
LEDGER_FILENAME = "validation_resource_ledger.arrow"

STOCK_NONE = 0
STOCK_RESERVE = 1
STOCK_FISH = 2

#: Column name -> pyarrow type name, in file order.
LEDGER_COLUMNS: dict[str, str] = {
    "turn": "uint32",
    "region": "uint16",
    "slot": "uint8",
    "resource_type": "uint8",
    "realized": "bool_",
    "output": "float32",
    "stock_kind": "uint8",
    "stock_before": "float64",
    "depletion": "float64",
    "recovery": "float64",
    "stock_after": "float64",
    "proxy_depletion": "float64",
    "lost": "float64",
    "reserved_before": "float64",
    "reserved_after": "float64",
    "effective_before": "float32",
    "effective_after": "float32",
    "take": "float32",
    "proxy_take": "float32",
    "sustainable": "float32",
    "streak": "int32",
    "soil_before": "float32",
    "soil_after": "float32",
    "forest_before": "float32",
    "forest_after": "float32",
    "mine_soil": "float32",
    "proxy_mine_soil": "float32",
}

_RESERVE_TOL = 1e-6
_FISH_TOL = 1e-9
_TAKE_TOL = 1e-4


def resource_check_enabled() -> bool:
    return os.environ.get(RESOURCE_CHECK_ENV, "") not in ("", "0")


def _depletable_types():
    from chronicler.models import ResourceType
    return frozenset({ResourceType.GRAIN, ResourceType.BOTANICALS, ResourceType.FISH,
                      ResourceType.ORE, ResourceType.PRECIOUS})


def _flat_mine_soil(world: "WorldState", region) -> float:
    """The flat per-mine soil charge (``ecology._tick_soil``) of a controlled
    region with an active mine; 0 otherwise."""
    from chronicler.models import InfrastructureType
    from chronicler.tuning import (
        K_MECHANIZATION_MINE_MULT, K_METALLURGY_MINE_REDUCTION, K_MINE_SOIL_DEGRADATION, get_override,
    )
    if region.controller is None:
        return 0.0
    if not any(i.type == InfrastructureType.MINES and i.active for i in region.infrastructure):
        return 0.0
    civ = next((c for c in world.civilizations if c.name == region.controller), None)
    if civ is None:
        return 0.0
    rate = get_override(world, K_MINE_SOIL_DEGRADATION, 0.03)
    if civ.active_focus == "metallurgy":
        rate *= get_override(world, K_METALLURGY_MINE_REDUCTION, 0.5)
    elif civ.active_focus == "mechanization":
        rate *= get_override(world, K_MECHANIZATION_MINE_MULT, 2.0)
    return rate


class ResourceLedgerTurn:
    """One turn's ledger: :meth:`start` before the Phase 9 ecology tick (after
    the economy), :meth:`observe_native` with the native ecology batch,
    :meth:`finish` after the tick. Reads only."""

    def __init__(self, world: "WorldState", economy_result: "EconomyResult | None",
                 *, check: bool, record: bool) -> None:
        self.turn = world.turn
        self.check = check
        self.record = record
        self.economy = economy_result
        outputs = economy_result.slot_output if economy_result is not None else {}
        self.outputs = outputs
        self.native: dict[str, list] | None = None
        fishery = world.fishery_experiment
        self.fishery_on = bool(fishery.enabled)
        from chronicler.experimental.fisheries import charges_landed_catch
        self.landed_rule = self.fishery_on and bool(outputs) and charges_landed_catch(world)
        self.before = []
        for region in world.regions:
            self.before.append({
                "population": region.population,
                "reserves": list(region.resource_reserves),
                "fish": list(region.fishery_stocks),
                "budgets": list(region.fishery_catch_budgets),
                "effective": list(region.resource_effective_yields),
                "streaks": [region.overextraction_streaks.get(s, 0) for s in range(3)],
                "soil": region.ecology.soil,
                "forest": region.ecology.forest_cover,
                "types": list(region.resource_types),
                "flat_mine_soil": _flat_mine_soil(world, region),
                "controlled": region.controller is not None,
            })

    def observe_native(self, region_batch) -> None:
        """Keep the native tick's ledger columns (absent from extensions built
        before 2026-10: the ledger then reads the state alone)."""
        from chronicler.columnar import pylist, schema_names
        names = set(schema_names(region_batch))
        if "extraction_realized" not in names:
            return
        cols = ["extraction_realized", "extraction_target_crew", "mine_soil", "proxy_mine_soil",
                "mine_crew_ratio"]
        cols += [f"{p}_{s}" for p in ("mineral_drawn", "proxy_mineral_draw", "overextraction_take")
                 for s in range(3)]
        self.native = {c: pylist(region_batch.column(c)) for c in cols}

    # ------------------------------------------------------------------
    def finish(self, world: "WorldState") -> dict[str, list]:
        """The turn's rows (column lists) after the tick; raises
        ``AssertionError`` on a broken balance when checking."""
        from chronicler.ecology import harvest_normal_index
        from chronicler.models import EMPTY_SLOT, MINERAL_TYPES, ResourceType
        from chronicler.tuning import (
            K_DEPLETION_RATE, K_OVEREXTRACTION_STREAK_LIMIT, K_WORKERS_PER_YIELD_UNIT, get_override,
        )
        rows: dict[str, list] = {name: [] for name in LEDGER_COLUMNS}
        problems: list[str] = []
        native = self.native
        depletable = _depletable_types()
        config = world.fishery_experiment
        fish_normal = harvest_normal_index(int(ResourceType.FISH))
        workers_per_unit = get_override(world, K_WORKERS_PER_YIELD_UNIT, 200)
        depletion_rate = get_override(world, K_DEPLETION_RATE, 0.009)
        streak_limit = int(get_override(world, K_OVEREXTRACTION_STREAK_LIMIT, 35))

        for rid, region in enumerate(world.regions):
            b = self.before[rid]
            out = self.outputs.get(region.name)
            realized = out is not None
            if native is not None and bool(native["extraction_realized"][rid]) != realized:
                problems.append(f"region {rid}: native tick realized={native['extraction_realized'][rid]} "
                                f"but the economy reported output={realized}")
            mine_row_written = False
            for slot in range(3):
                rtype = region.resource_types[slot]
                if rtype == EMPTY_SLOT or b["types"][slot] != rtype:
                    continue
                output = float(out[slot]) if realized else 0.0
                kind = STOCK_NONE
                stock_before = depletion = recovery = stock_after = proxy = lost = 0.0
                reserved_before = reserved_after = 0.0
                if rtype in MINERAL_TYPES:
                    kind = STOCK_RESERVE
                    stock_before = float(b["reserves"][slot])
                    stock_after = float(region.resource_reserves[slot])
                    depletion = stock_before - stock_after
                    proxy = depletion
                    if native is not None:
                        drawn = native[f"mineral_drawn_{slot}"][rid]
                        proxy = native[f"proxy_mineral_draw_{slot}"][rid]
                        if abs(drawn - depletion) > _RESERVE_TOL:
                            problems.append(f"region {rid} slot {slot}: reserve fell by {depletion:.8f}, "
                                            f"the tick drew {drawn:.8f}")
                        if realized and stock_before > 0.01:
                            crew = native["extraction_target_crew"][rid]
                            expect = (stock_before - max(0.0, stock_before - max(output, 0.0) / crew * depletion_rate)
                                      if crew > 0 else 0.0)
                            if abs(expect - depletion) > _RESERVE_TOL:
                                problems.append(f"region {rid} slot {slot}: output {output:.6f} over crew "
                                                f"{crew} draws {expect:.8f}, the reserve fell {depletion:.8f}")
                    if depletion < -_RESERVE_TOL or stock_after < 0.0:
                        problems.append(f"region {rid} slot {slot}: reserve {stock_before} -> {stock_after}")
                elif rtype == ResourceType.FISH and self.fishery_on:
                    kind = STOCK_FISH
                    capacity = region.resource_base_yields[slot] * config.reserve_turns
                    units = capacity * config.reference_workers
                    s0 = float(b["fish"][slot])
                    budget0 = b["budgets"][slot] or 0.0
                    reserved_before = budget0 / units if units > 0 else 0.0
                    budget1 = region.fishery_catch_budgets[slot] or 0.0
                    reserved_after = budget1 / units if units > 0 else 0.0
                    s1 = float(region.fishery_stocks[slot])
                    landed = (max(output, 0.0) * fish_normal / units
                              if realized and units > 0 else reserved_before)
                    landed = min(landed, reserved_before)
                    returned = 0.0
                    if self.landed_rule and realized:
                        from chronicler.experimental.fisheries import unlanded_stock
                        returned = unlanded_stock(b["budgets"][slot], region.resource_base_yields[slot],
                                                  output, config)
                    s_mid = min(1.0, s0 + returned)
                    recovery = config.recovery_rate * (1.0 - s_mid)
                    lost = max(0.0, reserved_before - landed - returned)
                    stock_before = s0 + reserved_before
                    stock_after = s1 + reserved_after
                    depletion = landed + lost
                    proxy = reserved_before
                    gap = stock_after - (stock_before - depletion + recovery)
                    if abs(gap) > _FISH_TOL and s0 + returned <= 1.0:
                        problems.append(f"region {rid} slot {slot}: fish stock + allowance "
                                        f"{stock_before:.10f} -> {stock_after:.10f}, landed {landed:.10f}, "
                                        f"lost {lost:.10f}, regrowth {recovery:.10f} (gap {gap:.3g})")
                # Overextraction track.
                eff0 = float(b["effective"][slot])
                eff1 = float(region.resource_effective_yields[slot])
                take = proxy_take = sustainable = 0.0
                streak = int(region.overextraction_streaks.get(slot, 0))
                if rtype in depletable:
                    proxy_take = float(b["population"] // 5 if b["population"] > 0 else 0)
                    take = proxy_take
                    if native is not None:
                        take = native[f"overextraction_take_{slot}"][rid]
                    sustainable = eff0 * workers_per_unit
                    if self.check and native is not None and b["controlled"]:
                        _check_take(problems, rid, slot, region, take, proxy_take, output, realized,
                                    world)
                    if self.check and b["controlled"] and sustainable > 0:
                        _check_streak(problems, rid, slot, take, sustainable, b["streaks"][slot],
                                      streak, eff0, eff1, streak_limit)
                mine_soil = proxy_mine_soil = 0.0
                if rtype in MINERAL_TYPES and not mine_row_written:
                    mine_row_written = True
                    if native is not None:
                        mine_soil = native["mine_soil"][rid]
                        proxy_mine_soil = native["proxy_mine_soil"][rid]
                        if self.check:
                            _check_mine_soil(problems, rid, world, native, mine_soil, proxy_mine_soil)
                    else:
                        mine_soil = proxy_mine_soil = b["flat_mine_soil"]
                row = (self.turn, rid, slot, int(rtype), realized, output, kind, stock_before, depletion,
                       recovery, stock_after, proxy, lost, reserved_before, reserved_after, eff0, eff1,
                       take, proxy_take, sustainable, streak, b["soil"], region.ecology.soil,
                       b["forest"], region.ecology.forest_cover, mine_soil, proxy_mine_soil)
                for name, value in zip(LEDGER_COLUMNS, row):
                    rows[name].append(value)

        if self.check:
            _check_goods(problems, self.economy)
            if problems:
                raise AssertionError(
                    f"resource ledger does not balance at turn {self.turn}: "
                    + "; ".join(problems[:8]) + (f" (+{len(problems) - 8} more)" if len(problems) > 8 else "")
                )
        return rows


def _check_take(problems, rid, slot, region, take, proxy_take, output, realized, world) -> None:
    from chronicler.agent_bridge import extraction_rules
    if realized and extraction_rules(world)[0]:
        base = region.resource_base_yields[slot]
        expect = max(output, 0.0) / base if base > 0 else 0.0
        if abs(take - expect) > _TAKE_TOL * max(1.0, expect):
            problems.append(f"region {rid} slot {slot}: overextraction take {take} against output "
                            f"{output} / base {base} = {expect}")
    elif take != proxy_take:
        problems.append(f"region {rid} slot {slot}: overextraction take {take} without realized "
                        f"output, proxy population / 5 = {proxy_take}")


def _check_streak(problems, rid, slot, take, sustainable, before, after, eff0, eff1, limit) -> None:
    if abs(take - sustainable) <= _TAKE_TOL * sustainable:
        return  # single/double precision may differ at the boundary
    # The native tick holds effective yields in single precision.
    unchanged = abs(eff1 - eff0) <= 1e-6 * max(1.0, abs(eff0))
    if take > sustainable:
        ok = (after == before + 1 and unchanged) or (after == 0 and before + 1 >= limit and not unchanged
                                                     and eff1 < eff0)
    else:
        ok = after == 0 and unchanged
    if not ok:
        problems.append(f"region {rid} slot {slot}: take {take} vs sustainable {sustainable}: "
                        f"streak {before} -> {after}, effective yield {eff0} -> {eff1}")


def _check_mine_soil(problems, rid, world, native, mine_soil, proxy_mine_soil) -> None:
    from chronicler.agent_bridge import extraction_rules
    if native["extraction_realized"][rid] and extraction_rules(world)[1]:
        expect = proxy_mine_soil * native["mine_crew_ratio"][rid]
    else:
        expect = proxy_mine_soil
    if abs(mine_soil - expect) > 1e-6:
        problems.append(f"region {rid}: mines took {mine_soil} of soil, the rule says {expect}")


def _check_goods(problems, economy) -> None:
    """The slots' output, foraged grain and wares made are the economy's
    production (everything that entered the stocks this turn)."""
    if economy is None or not economy.slot_output:
        return
    total = 0.0
    for name, outs in economy.slot_output.items():
        total += sum(outs) + economy.forage_output.get(name, 0.0) + economy.craft_output.get(name, 0.0)
    production = float(economy.conservation.get("production", 0.0))
    if abs(total - production) > 1e-5 * max(1.0, abs(production)):
        problems.append(f"slot output + forage + wares {total:.6f} != economy production {production:.6f}")


# ----------------------------------------------------------------------
# Turn hooks (simulation.run_turn_result)
# ----------------------------------------------------------------------

def start_turn_ledger(world: "WorldState", economy_result, agent_bridge=None) -> ResourceLedgerTurn | None:
    """A ledger for this turn's Phase 9 when the sidecar records it or the
    resource check is on; None (nothing built) otherwise."""
    sidecar = getattr(agent_bridge, "_sidecar", None) if agent_bridge is not None else None
    check = resource_check_enabled()
    if sidecar is None and not check:
        return None
    return ResourceLedgerTurn(world, economy_result, check=check, record=sidecar is not None)


def finish_turn_ledger(world: "WorldState", ledger: ResourceLedgerTurn | None, agent_bridge=None) -> None:
    if ledger is None:
        return
    rows = ledger.finish(world)
    sidecar = getattr(agent_bridge, "_sidecar", None) if agent_bridge is not None else None
    if ledger.record and sidecar is not None:
        sidecar.add_resource_ledger_rows(rows)


# ----------------------------------------------------------------------
# File and summary
# ----------------------------------------------------------------------

def write_ledger(path, columns: dict[str, list], *, artifact_budget=None) -> None:
    """Write the ledger's column lists as an Arrow IPC file (zstd when the
    build has it)."""
    import pyarrow as pa
    import pyarrow.ipc as ipc
    arrays = [pa.array(columns.get(name, []), type=getattr(pa, kind)()) for name, kind in LEDGER_COLUMNS.items()]
    batch = pa.record_batch(arrays, names=list(LEDGER_COLUMNS))
    options = ipc.IpcWriteOptions(compression="zstd") if pa.Codec.is_available("zstd") else None
    if artifact_budget is None:
        with pa.OSFile(str(path), "wb") as handle:
            writer = ipc.new_file(handle, batch.schema, options=options)
            writer.write_batch(batch)
            writer.close()
    else:
        artifact_budget.require_healthy()
        with pa.BufferOutputStream() as handle:
            writer = ipc.new_file(handle, batch.schema, options=options)
            writer.write_batch(batch)
            writer.close()
            content = handle.getvalue().to_pybytes()
        artifact_budget.write_bytes(path, content)


def read_ledger(path) -> dict[str, list]:
    import pyarrow as pa
    import pyarrow.ipc as ipc
    with pa.memory_map(str(path), "r") as source:
        table = ipc.open_file(source).read_all()
    return {name: table.column(name).to_pylist() for name in table.column_names}


COLLAPSE_STOCK = 0.25
RECOVERED_STOCK = 0.6
EXHAUSTED_RESERVE = 0.01


def summarize_ledger(columns: dict[str, list]) -> dict[str, Any]:
    """Per-world summary of one ledger: realized against proxy depletion,
    exhausted mineral slots, fishery collapses and their recovery times, the
    mines' soil charge and the overextraction pressure.

    Fish stocks are read in the water (stock less outstanding allowance), the
    state ``fishery_collapse`` events read.
    """
    n = len(columns.get("turn", []))
    turns = columns["turn"] if n else []
    summary: dict[str, Any] = {"rows": n, "turns": (max(turns) - min(turns) + 1) if n else 0}
    if not n:
        return summary
    col = columns
    mineral = {"realized": 0.0, "proxy": 0.0, "realized_turns": 0, "slot_turns": 0, "output": 0.0}
    fish = {"landed": 0.0, "lost": 0.0, "proxy": 0.0, "regrowth": 0.0, "output": 0.0}
    mine_soil = {"charged": 0.0, "proxy": 0.0}
    outputs: dict[int, float] = {}
    pressure_max = 0.0
    pressure_over = 0
    last_reserve: dict[tuple[int, int], tuple[int, float]] = {}
    fish_series: dict[tuple[int, int], list[tuple[int, float]]] = {}
    penalized = 0
    for i in range(n):
        kind = col["stock_kind"][i]
        key = (col["region"][i], col["slot"][i])
        outputs[col["resource_type"][i]] = outputs.get(col["resource_type"][i], 0.0) + col["output"][i]
        if kind == STOCK_RESERVE:
            mineral["realized"] += col["depletion"][i]
            mineral["proxy"] += col["proxy_depletion"][i]
            mineral["slot_turns"] += 1
            mineral["realized_turns"] += 1 if col["realized"][i] else 0
            mineral["output"] += col["output"][i]
            last_reserve[key] = (col["turn"][i], col["stock_after"][i])
        elif kind == STOCK_FISH:
            fish["landed"] += col["depletion"][i] - col["lost"][i]
            fish["lost"] += col["lost"][i]
            fish["proxy"] += col["proxy_depletion"][i]
            fish["regrowth"] += col["recovery"][i]
            fish["output"] += col["output"][i]
            in_water = col["stock_after"][i] - col["reserved_after"][i]
            fish_series.setdefault(key, []).append((col["turn"][i], in_water))
        mine_soil["charged"] += col["mine_soil"][i]
        mine_soil["proxy"] += col["proxy_mine_soil"][i]
        if col["sustainable"][i] > 0:
            p = col["take"][i] / col["sustainable"][i]
            pressure_max = max(pressure_max, p)
            pressure_over += 1 if p > 1.0 else 0
        if col["effective_after"][i] < col["effective_before"][i]:
            penalized += 1
    exhausted = sum(1 for _, (_, r) in last_reserve.items() if r < EXHAUSTED_RESERVE)
    collapses = 0
    recoveries: list[int] = []
    unrecovered = 0
    for series in fish_series.values():
        series.sort()
        collapsed_at = None
        for turn, stock in series:
            if collapsed_at is None and stock < COLLAPSE_STOCK:
                collapsed_at = turn
                collapses += 1
            elif collapsed_at is not None and stock >= RECOVERED_STOCK:
                recoveries.append(turn - collapsed_at)
                collapsed_at = None
        if collapsed_at is not None:
            unrecovered += 1
    summary.update({
        "mineral_slots": len(last_reserve),
        "mineral_exhausted": exhausted,
        "mineral_reserve_final_mean": (sum(r for _, r in last_reserve.values()) / len(last_reserve)
                                       if last_reserve else None),
        "mineral_depletion_realized": mineral["realized"],
        "mineral_depletion_proxy": mineral["proxy"],
        "mineral_output": mineral["output"],
        "mineral_realized_share": (mineral["realized_turns"] / mineral["slot_turns"]
                                   if mineral["slot_turns"] else None),
        "fish_slots": len(fish_series),
        "fish_landed": fish["landed"],
        "fish_lost": fish["lost"],
        "fish_charged_proxy": fish["proxy"],
        "fish_regrowth": fish["regrowth"],
        "fish_final_mean": (sum(s[-1][1] for s in fish_series.values()) / len(fish_series)
                            if fish_series else None),
        "fish_collapses": collapses,
        "fish_recoveries": len(recoveries),
        "fish_recovery_turns_mean": (sum(recoveries) / len(recoveries)) if recoveries else None,
        "fish_unrecovered": unrecovered,
        "mine_soil_charged": mine_soil["charged"],
        "mine_soil_proxy": mine_soil["proxy"],
        "overextraction_pressure_max": pressure_max,
        "overextraction_slot_turns_over": pressure_over,
        "yield_penalties": penalized,
        "output_by_resource": {int(k): v for k, v in sorted(outputs.items())},
    })
    return summary

