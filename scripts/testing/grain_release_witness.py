"""Exact test-only inverse of the optional local full-meal release policy.

Keeps the existing public-shipment/default historical source pins immutable.
Literal contexts enforce the declared insertion sites; the parent full-file
hash rejects unrelated edits. Runtime/default neutrality is checked separately.
"""
from __future__ import annotations

import hashlib

_LAYERS = {
    'src/chronicler/grain_reserves.py': {
        "sha256": '8a754a43e6dcd7122fbcf76197e09ac596374beff9d25521a17f19d24894e717',
        "patches": [
            {"old": '''    sufficiency and post-trade food supply), then spoil. Returns events."""
    if not grain_reserves_active(world):
        return []
    from chronicler.harvest_forecasts_state import harvest_forecasts_on
    if harvest_forecasts_on(world):
        from chronicler.harvest_forecasts import clear_stale_preparedness
''',
             "new": '''    sufficiency and post-trade food supply), then spoil. Returns events."""
    if not grain_reserves_active(world):
        return []
    from chronicler.tuning import K_GRAIN_RESERVES_FULL_MEAL_RELEASE, get_override
    full_meal_release = get_override(world, K_GRAIN_RESERVES_FULL_MEAL_RELEASE, 0.0)
    if type(full_meal_release) not in (int, float) or full_meal_release not in (0.0, 1.0):
        raise ValueError("grain_reserves.full_meal_release must be 0 or 1")
    from chronicler.harvest_forecasts_state import harvest_forecasts_on
    if harvest_forecasts_on(world):
        from chronicler.harvest_forecasts import clear_stale_preparedness
'''},
            {"old": '''            # Well stocked, it covers the whole shortfall; low, it keeps the
            # people above the famine line and saves the rest for worse.
            full = granary.target <= EPS or granary.grain >= RESERVE_FOR_FAMINE * granary.target
            level = RELEASE_TO if full else FAMINE_SEVERE_SUFFICIENCY
            if sufficiency >= level - 1e-6:
                granary.releasing = granary.announced = granary.emptied = False
                continue
''',
             "new": '''            # Well stocked, it covers the whole shortfall; low, it keeps the
            # people above the famine line and saves the rest for worse.
            full = granary.target <= EPS or granary.grain >= RESERVE_FOR_FAMINE * granary.target
            # The opt-in alternative spends only this region's existing stock
            # for present relief; it may leave less for a later severe shortage.
            level = RELEASE_TO if full or full_meal_release else FAMINE_SEVERE_SUFFICIENCY
            if sufficiency >= level - 1e-6:
                granary.releasing = granary.announced = granary.emptied = False
                continue
'''},
        ],
    },
    'src/chronicler/tuning.py': {
        "sha256": 'ed3682456d480538e130ec5481c51d08253a74ff48ce31b494b83204033cbd9e',
        "patches": [
            {"old": '''# Optional public-granary allocation policy (0: reserve fill first; 1: food
# shortfall first within each existing domestic/foreign procurement pass).
K_GRAIN_RESERVES_SHORTFALL_PRIORITY = "grain_reserves.shortfall_priority"
# Bulk trade (2026-10): loads one merchant carries per trip overland, by river
# and by sea, and whether trips are planned in bulk, filled against the tick's
# committed deliveries (0: one-load planning, loading the capacity or the
''',
             "new": '''# Optional public-granary allocation policy (0: reserve fill first; 1: food
# shortfall first within each existing domestic/foreign procurement pass).
K_GRAIN_RESERVES_SHORTFALL_PRIORITY = "grain_reserves.shortfall_priority"
# Optional local release policy: 0 retains low-stock famine-line rationing;
# 1 aims for a full meal from existing local grain, with no shared reserve.
K_GRAIN_RESERVES_FULL_MEAL_RELEASE = "grain_reserves.full_meal_release"
# Bulk trade (2026-10): loads one merchant carries per trip overland, by river
# and by sea, and whether trips are planned in bulk, filled against the tick's
# committed deliveries (0: one-load planning, loading the capacity or the
'''},
            {"old": '''    K_CLIMATE_TREND_SHARE,
    K_OVEREXTRACTION_REALIZED, K_MINE_SOIL_REALIZED, K_FISHERY_CHARGES_LANDED_CATCH,
    K_YIELD_PENALTY_REACHES_GOODS,
    K_GRAIN_RESERVES_SHORTFALL_PRIORITY,
    K_LAND_CARGO_CAP, K_RIVER_CARGO_CAP, K_SEA_CARGO_CAP, K_CARGO_FILL,
    K_GUILD_NEWS,
    K_COMMUNITY_FULL_ANCHOR,
''',
             "new": '''    K_CLIMATE_TREND_SHARE,
    K_OVEREXTRACTION_REALIZED, K_MINE_SOIL_REALIZED, K_FISHERY_CHARGES_LANDED_CATCH,
    K_YIELD_PENALTY_REACHES_GOODS,
    K_GRAIN_RESERVES_SHORTFALL_PRIORITY, K_GRAIN_RESERVES_FULL_MEAL_RELEASE,
    K_LAND_CARGO_CAP, K_RIVER_CARGO_CAP, K_SEA_CARGO_CAP, K_CARGO_FILL,
    K_GUILD_NEWS,
    K_COMMUNITY_FULL_ANCHOR,
'''},
        ],
    },
}


def before_grain_release(source: str, path: str) -> str:
    from scripts.testing.livelihoods_sprint_witness import before_livelihoods_sprint
    source = before_livelihoods_sprint(source, path)
    from scripts.testing.food_accounting_witness import before_food_accounting
    row = _LAYERS.get(path)
    if row is None:
        return source
    source = before_food_accounting(source, path, allow_parent=True)
    for patch in reversed(row["patches"]):
        assert source.count(patch["new"]) == 1, f"grain release witness changed: {path}"
        source = source.replace(patch["new"], patch["old"], 1)
    assert hashlib.sha256(source.encode()).hexdigest() == row["sha256"], path
    return source
