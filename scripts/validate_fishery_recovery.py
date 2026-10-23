"""Fixed 40-turn Phase 2 -> Phase 9 coastal harvest/rest validation.

Uses actual economy/ecology functions with prescribed snapshots, without an
agent or demographic tick. Independent source workers avoid import contamination.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

BASELINE = "edf72991cad58d6670b1f382c33d50d903a6054a"
SCHEMA_ADDITIONS = ("fishery_stocks", "fishery_yield_ratios", "fishery_catch_budgets")
TOLERANCE = 1e-9


def canonical_hash(world) -> str:
    state = world.model_dump(mode="json")
    # Joint integration adds dormant aid metadata to this fishery-only fixture.
    # Assert its exact defaults before projecting shared baseline values.
    for field, default in (("mutual_aid_enabled", False), ("mutual_aid_state", {}),
                           ("mutual_aid_last_dispatch_turn", None), ("mutual_aid_last_transfers", [])):
        if field in state:
            assert state.pop(field) == default, (field, "aid unexpectedly active")
    state.pop("fishery_experiment", None)
    for region in state["regions"]:
        for field in SCHEMA_ADDITIONS:
            region.pop(field, None)
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def run_fixture(source: Path, enabled: bool, resume_at: int | None = None) -> dict:
    sys.path.insert(0, str(source.resolve()))
    import pyarrow as pa
    from chronicler.ecology import check_food_yield, compute_resource_yields, tick_ecology
    from chronicler.economy import compute_economy
    from chronicler.models import (
        Civilization, ClimatePhase, Leader, Region, RegionStockpile, TechEra, WorldState,
    )
    from chronicler.resources import get_season_id
    from chronicler.tuning import K_FAMINE_POP_LOSS

    region = Region(name="Coastal fishery", terrain="coast", resources="maritime",
                    controller="Coastal polity", carrying_capacity=3000, population=1000,
                    resource_types=[3, 255, 255], resource_base_yields=[1, 0, 0],
                    resource_effective_yields=[1, 0, 0],
                    stockpile=RegionStockpile(goods={"fish": 2000.0}))
    civ = Civilization(name="Coastal polity", population=1000, military=30, economy=40,
                       culture=30, stability=50, tech_era=TechEra.IRON, treasury=50,
                       leader=Leader(name="Coastal keeper", trait="cautious", reign_start=0),
                       regions=[region.name])
    world = WorldState(name="Fixed coastal pair", seed=42, regions=[region], civilizations=[civ],
                       tuning_overrides={K_FAMINE_POP_LOSS: 0.0})
    if enabled:
        world.fishery_experiment.enabled = True
    trace = []
    goods_residuals = []
    biomass_residuals = []
    combined_residuals = []
    totals = {key: 0.0 for key in ("production", "consumption", "storage_loss", "cap_overflow",
                                  "clamp_floor_loss", "transit_loss", "in_transit_delta",
                                  "biological_replenishment", "harvest", "discarded_catch")}
    persistence_verified = False
    initial_goods = 2000.0
    # Config defaults are fixed; available only on the experiment branch.
    biomass_capacity = 1600.0 if enabled else None
    initial_biomass = biomass_capacity

    for turn in range(40):
        if turn == resume_at:
            with tempfile.TemporaryDirectory(prefix="fishery-resume-") as folder:
                state_path = Path(folder) / "state.json"
                before = world.model_dump(mode="json")
                world.save(state_path)
                world = WorldState.load(state_path)
                if world.model_dump(mode="json") != before:
                    raise AssertionError("persisted Python state changed at harvest/rest boundary")
                persistence_verified = True
        world.turn = turn
        region = world.regions[0]
        farmers = 800 if turn < 20 else 0
        snapshot = pa.record_batch({
            "region": pa.array([0] * 1000, type=pa.int32()),
            "occupation": pa.array([0] * farmers + [3] * (1000 - farmers), type=pa.int32()),
            "wealth": pa.array([0.0] * 1000, type=pa.float32()),
            "civ_affinity": pa.array([0] * 1000, type=pa.int32()),
        })
        # Fixture-only live-workforce provider, never serialized as native state.
        world._agent_bridge = SimpleNamespace(get_snapshot=lambda: snapshot)
        goods_before = sum(region.stockpile.goods.values())
        previous_budget = (region.fishery_catch_budgets[0] or 0.0) if enabled else None
        ratio = region.fishery_yield_ratios[0] if enabled else 1.0
        expected_production = region.resource_effective_yields[0] * ratio * farmers
        if enabled:
            expected_production = min(expected_production, previous_budget)

        # Phase 2 uses the previous Phase 9 catch credit, with real goods accounting.
        result = compute_economy(world, snapshot, world.region_map,
                                 agent_mode=True, active_trade_routes=[])
        ledger = result.conservation
        production = ledger["production"]
        if not math.isclose(production, expected_production, abs_tol=TOLERANCE, rel_tol=0):
            raise AssertionError("actual goods production disagrees with lagged catch credit")
        if enabled and production > previous_budget + TOLERANCE:
            raise AssertionError("food production exceeds the biomass debit")
        goods_after = sum(region.stockpile.goods.values())
        goods_residual = goods_before + production - goods_after - sum(
            ledger[key] for key in ("consumption", "storage_loss", "cap_overflow", "clamp_floor_loss",
                                   "transit_loss", "in_transit_delta")
        )
        goods_residuals.append(goods_residual)
        for key in ledger:
            if key in totals:
                totals[key] += ledger[key]
        discarded_catch = max(0.0, previous_budget - production) if enabled else None
        if enabled:
            totals["discarded_catch"] += discarded_catch

        # Phase 9. Potential observation has no mineral/resource mutation in this fixture.
        potential = compute_resource_yields(region, get_season_id(turn), ClimatePhase.TEMPERATE,
                                             region.population // 5, world)[0]
        stock_before = region.fishery_stocks[0] if enabled else None
        events = tick_ecology(world, ClimatePhase.TEMPERATE)
        world.events_timeline.extend(events)
        actual_yield = region.resource_current_yields[0] if enabled else potential
        yield_famine = check_food_yield(region, [actual_yield, 0, 0], ClimatePhase.TEMPERATE)
        stock_after = region.fishery_stocks[0] if enabled else None
        recovery = world.fishery_experiment.recovery_rate * (1 - stock_before) if enabled else None
        catch = region.fishery_catch_budgets[0] if enabled else None
        biomass_residual = None
        combined_residual = None
        if enabled:
            if not all(math.isfinite(value) for value in (stock_before, stock_after, recovery, catch)):
                raise AssertionError("nonfinite fishery stock, recovery or catch")
            if not 0 <= stock_after <= 1 or recovery < 0 or catch < 0:
                raise AssertionError("fishery state outside physical bounds")
            biomass_residual = (stock_before + recovery - stock_after) * biomass_capacity - catch
            biomass_residuals.append(biomass_residual)
            totals["biological_replenishment"] += recovery * biomass_capacity
            totals["harvest"] += catch
            # Pending current catch is outside goods inventory until next Phase 2.
            combined_residual = (initial_biomass + initial_goods + totals["biological_replenishment"]
                                 - stock_after * biomass_capacity - goods_after - catch
                                 - sum(totals[key] for key in ("consumption", "storage_loss", "cap_overflow",
                                                            "clamp_floor_loss", "transit_loss", "in_transit_delta",
                                                            "discarded_catch")))
            combined_residuals.append(combined_residual)
        if region.population != 1000 or world.civilizations[0].population != 1000:
            raise AssertionError("fixture population changed")
        if not all(math.isfinite(value) for value in (goods_after, production, result.food_sufficiency[region.name])):
            raise AssertionError("nonfinite goods result")
        if farmers == 0 and enabled and catch != 0:
            raise AssertionError("rest generated a harvest")
        world.turn = turn + 1
        trace.append({
            "turn": turn, "stage": "harvest" if farmers else "rest", "farmers": farmers,
            "stock_before": stock_before, "stock_after": stock_after, "recovery_fraction": recovery,
            "catch_worker_units": catch, "previous_catch_credit": previous_budget,
            "actual_food_production": production, "discarded_previous_catch": discarded_catch,
            "potential_yield": potential, "actual_yield": actual_yield,
            "yield_famine_predicate": yield_famine,
            "famine_events": sum(event.event_type == "famine" for event in events),
            "stockpile_food_sufficiency": result.food_sufficiency[region.name],
            "food_stock_before_phase2": goods_before, "food_stock_after_phase2": goods_after,
            "goods_ledger": ledger, "cargo": 0.0, "pending_deliveries": 0.0,
            "pending_catch_credit": catch, "goods_balance_residual": goods_residual,
            "biomass_balance_residual": biomass_residual, "combined_balance_residual": combined_residual,
            "canonical_state_sha256": canonical_hash(world),
        })

    maximum = lambda values: max(map(abs, values), default=0.0)
    checks = {"goods_balance": maximum(goods_residuals) < TOLERANCE,
              "finite_stock_and_recovery": True,
              "biomass_balance": maximum(biomass_residuals) < TOLERANCE if enabled else None,
              "combined_biomass_goods_balance": maximum(combined_residuals) < TOLERANCE if enabled else None,
              "production_bounded_by_previous_catch": True if enabled else None,
              "no_harvest_while_resting": True if enabled else None}
    if not all(value for value in checks.values() if value is not None):
        raise AssertionError(f"ledger checks failed: {checks}")
    summary = {
        "stock_at_end_of_harvest": trace[19]["stock_after"], "stock_at_end_of_rest": trace[39]["stock_after"],
        "total_food_production": totals["production"], "total_harvest_debit": totals["harvest"] if enabled else None,
        "total_replenishment": totals["biological_replenishment"] if enabled else None,
        "total_discarded_catch": totals["discarded_catch"] if enabled else None,
        "yield_famine_turns": [row["turn"] for row in trace if row["yield_famine_predicate"]],
        "famine_event_turns": [row["turn"] for row in trace if row["famine_events"]],
        "stockpile_shortage_turns": [row["turn"] for row in trace if row["stockpile_food_sufficiency"] < 1],
        "stockpile_shortage_without_yield_famine_turns": [row["turn"] for row in trace
            if row["stockpile_food_sufficiency"] < 1 and not row["yield_famine_predicate"]],
        "max_goods_balance_residual": maximum(goods_residuals),
        "max_biomass_balance_residual": maximum(biomass_residuals) if enabled else None,
        "max_combined_balance_residual": maximum(combined_residuals) if enabled else None,
        "final_pending_catch": trace[-1]["pending_catch_credit"],
        "final_goods": goods_after,
    }
    return {"summary": summary, "checks": checks, "trace": trace,
            "persistence": {"resumed_at": resume_at, "roundtrip_verified": persistence_verified}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--enabled", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--resume-at", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(run_fixture(args.source, args.enabled, args.resume_at), allow_nan=False))
        return
    if args.baseline_src is None:
        parser.error("--baseline-src is required")
    baseline_root = args.baseline_src.resolve().parent
    head = subprocess.check_output(["git", "-C", str(baseline_root), "rev-parse", "HEAD"], text=True).strip()
    if head != BASELINE or subprocess.check_output(
            ["git", "-C", str(baseline_root), "status", "--porcelain"], text=True).strip():
        parser.error(f"baseline must be a clean untouched checkout of {BASELINE}")
    source = Path(__file__).resolve().parents[1] / "src"

    def launch(src, enabled=False, resume_at=None):
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--source", str(src)]
        if enabled:
            command.append("--enabled")
        if resume_at is not None:
            command.extend(["--resume-at", str(resume_at)])
        return json.loads(subprocess.check_output(command, text=True))

    control, off, on, resumed = launch(args.baseline_src), launch(source), launch(source, True), launch(source, True, 20)
    checks = {"off_equals_untouched_edf7299_each_turn": control == off,
              "enabled_resume_equals_uninterrupted_each_turn": on["trace"] == resumed["trace"],
              "resumed_state_roundtrip_verified": resumed["persistence"]["roundtrip_verified"],
              "harvest_depletes_stock": on["summary"]["stock_at_end_of_harvest"] < 1,
              "rest_restores_stock": on["summary"]["stock_at_end_of_rest"] > on["summary"]["stock_at_end_of_harvest"]}
    report = {"baseline_commit": BASELINE, "source_head": subprocess.check_output(
                  ["git", "-C", str(source.parent), "rev-parse", "HEAD"], text=True).strip(),
              "fixture": {"seed": 42, "turns": 40, "harvest_turns": [0, 19], "rest_turns": [20, 39],
                          "population": 1000, "farmers_harvest": 800, "farmers_rest": 0,
                          "initial_food_stock": 2000, "base_yield": 1.0, "climate": "temperate",
                          "famine_population_loss": 0, "trade_routes": [], "merchants": 0,
                          "fishery_parameters": {"reserve_turns": 8, "recovery_rate": .04,
                                                 "harvest_fraction": .25, "reference_workers": 200}},
              "scope": "Controlled Python Phase 2 -> Phase 9; prescribed workforce; no native agent/demographic tick. Cargo and delivery buffers are zero by construction. No full hybrid continuation or cross-b665e198 comparison.",
              "checks": checks, "control": control, "off": off, "on": on,
              "resumed": {"summary": resumed["summary"], "persistence": resumed["persistence"]}}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"checks": checks, "off_summary": off["summary"], "on_summary": on["summary"]}, indent=2))
    if not all(checks.values()):
        raise SystemExit("40-turn paired validation failed")


if __name__ == "__main__":
    main()
