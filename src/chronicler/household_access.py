"""Household food access and welfare metrics (DEP-7, ``--household-access``, default off).

Observation only: this package reads the frames other packages already
settled and changes nothing it observes (no native call, no money, no RNG).
It needs ``--food-allocation`` (L2) in hybrid mode. Its ``after_agent_tick``
hook runs after L2's and household retail's (L6b) hooks of the same tick
(declaration order), and reads:

* L2's frame of the turn (``food_allocation`` state ``totals`` and scarce
  ``regions``): every non-retail region's people, rations and shortfall, the
  poorer/richer-half and child split and the people below the floor;
* household retail's settled provisioning rows of the turn
  (``household_retail.provisioning_rows``): each pilot region's persons,
  rations and the people priced out of their fair share with their deficit.

Definitions (rations: 1.0 is a full ration; ``provisioning.rs``):

* ``calories_met_share = allocated / alive`` (retail: ``rations / persons``);
* ``shortfall_depth = shortfall / alive``, with ``shortfall = sum(1 - ration)``
  (retail: ``persons - rations``, the same sum since each ration is at most 1);
* ``below_floor_share``: people below the L2 subsistence floor per person, over
  L2 regions only (retail rows carry no floor count);
* ``poorer_richer_ratio``: the poorer half's mean shortfall over the richer
  half's (L2 only; None when the richer half has no shortfall);
* ``child_shortfall_share``: children's share of the shortfall (L2 only);
* ``priced_out_persons`` and ``priced_out_deficit`` (retail regions), and the
  cumulative ``priced_out_person_turns``.

World aggregates use L2's totals (all non-retail regions) plus the retail rows.
A metric that was not observed is None, never 0: without an L2 frame for the
turn the world aggregates are None; a metric without people is None. Region
rows list the regions observed in detail (L2's scarce regions and the settled
retail regions); L2's other regions fed everyone a full ration and appear only
in the world aggregates.

Welfare primaries for screens, from the cumulative counters:
``P1 = 1000 x poorer-half shortfall / poorer-half person-turns`` (L2) and
``P2 = 1000 x priced-out person-turns / observed person-turns``. A joint
food-and-care welfare number waits for the owner's weights (open question).
Values are rounded to 6 digits, as L2 rounds its own.
"""
from __future__ import annotations

from typing import Any, Iterable

from chronicler.household_access_state import COUNTERS, HouseholdAccessState

STAGE = "DEP-7"
#: L2 frame keys this package reads (``food_allocation.after_agent_tick`` totals).
_L2_KEYS: tuple[str, ...] = (
    "alive", "allocated", "shortfall", "below_floor", "people_poorer_half", "shortfall_poorer_half",
    "people_richer_half", "shortfall_richer_half", "children", "shortfall_children")
#: Retail provisioning columns this package reads (``provisioning.rs`` RETAIL_REGION_COLUMNS).
_RETAIL_KEYS: tuple[str, ...] = ("persons", "rations", "priced_out_persons", "priced_out_deficit")


def _state(world) -> HouseholdAccessState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "household_access", None) if container is not None else None


def set_household_access_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    state = _state(world)
    if state is None:
        world.livelihoods.household_access = state = HouseholdAccessState()
    state.enabled = bool(value)
    if not value:
        state.frame, state.frame_turn = None, None


def household_access_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _ratio(num: float, den: float) -> float | None:
    return _round(num / den) if den > 0 else None


def _l2_metrics(row: dict) -> dict:
    alive = float(row["alive"])
    poorer = _ratio(float(row["shortfall_poorer_half"]), float(row["people_poorer_half"]))
    richer = _ratio(float(row["shortfall_richer_half"]), float(row["people_richer_half"]))
    return {
        "calories_met_share": _ratio(float(row["allocated"]), alive),
        "shortfall_depth": _ratio(float(row["shortfall"]), alive),
        "below_floor_share": _ratio(float(row["below_floor"]), alive),
        "poorer_half_shortfall_depth": poorer,
        "richer_half_shortfall_depth": richer,
        "poorer_richer_ratio": (_ratio(poorer, richer) if poorer is not None and richer is not None else None),
        "child_shortfall_share": _ratio(float(row["shortfall_children"]), float(row["shortfall"])),
    }


def _retail_row(region: int, row: dict) -> dict:
    persons = float(row["persons"])
    rations = float(row["rations"])
    shortfall = max(0.0, persons - rations)
    return {
        "region": int(region), "source": "retail", "alive": int(persons),
        "calories_met_share": _ratio(rations, persons), "shortfall_depth": _ratio(shortfall, persons),
        "below_floor_share": None, "poorer_half_shortfall_depth": None, "richer_half_shortfall_depth": None,
        "poorer_richer_ratio": None, "child_shortfall_share": None,
        "priced_out_persons": int(row["priced_out_persons"]),
        "priced_out_deficit": _round(row["priced_out_deficit"]),
    }


def compute_frame(l2_totals: dict | None, l2_regions: Iterable[dict], retail: dict[int, dict] | None) -> dict | None:
    """The turn's frame from L2's totals and scarce rows (None: no L2 frame
    this turn) and retail's settled rows ``{region: provisioning row}``; None
    when neither was observed. Pure: copies nothing back."""
    retail = retail or {}
    if l2_totals is None and not retail:
        return None
    rows = []
    if l2_totals is not None:
        for row in l2_regions:
            rows.append({"region": int(row["region"]), "source": "allocation", "alive": int(row["alive"]),
                         **_l2_metrics(row), "priced_out_persons": None, "priced_out_deficit": None})
    rows.extend(_retail_row(rid, retail[rid]) for rid in sorted(retail))
    rows.sort(key=lambda r: r["region"])
    world = None
    if l2_totals is not None:
        l2 = {key: float(l2_totals.get(key, 0.0)) for key in _L2_KEYS}
        persons = sum(float(r["persons"]) for r in retail.values())
        rations = sum(float(r["rations"]) for r in retail.values())
        alive = l2["alive"] + persons
        priced = sum(float(r["priced_out_persons"]) for r in retail.values()) if retail else None
        deficit = sum(float(r["priced_out_deficit"]) for r in retail.values()) if retail else None
        world = {
            "alive": int(alive), "allocation_alive": int(l2["alive"]), "retail_alive": int(persons),
            "retail_regions": len(retail),
            **_l2_metrics(l2),
            # Over L2 plus retail people (the two metrics both frames carry).
            "calories_met_share": _ratio(l2["allocated"] + rations, alive),
            "shortfall_depth": _ratio(l2["shortfall"] + max(0.0, persons - rations), alive),
            "priced_out_persons": None if priced is None else int(priced),
            "priced_out_share": _ratio(priced, persons) if priced is not None else None,
            "priced_out_deficit": _round(deficit),
        }
    return {"world": world, "regions": rows}


def _bump(state: HouseholdAccessState, key: str, amount: float = 1) -> None:
    state.counters[key] = round(state.counters.get(key, 0) + amount, 6)


def after_agent_tick(world, agent_bridge) -> list:
    """Read this tick's L2 frame and retail rows once; change nothing else."""
    state = _state(world)
    turn = int(world.turn)
    alloc = getattr(getattr(world, "livelihoods", None), "food_allocation", None)
    observed = alloc is not None and alloc.frame_turn == turn
    retail = None
    if getattr(world.livelihoods, "household_retail", None) is not None:
        from chronicler.household_retail import provisioning_rows
        retail = provisioning_rows(world)
    frame = compute_frame(dict(alloc.totals) if observed else None,
                          list(alloc.regions) if observed else (), retail)
    if frame is None or frame["world"] is None:
        _bump(state, "turns_unobserved")
    else:
        _bump(state, "turns_observed")
    if frame is None:
        return []
    if observed:
        totals = alloc.totals
        _bump(state, "allocation_person_turns", float(totals.get("alive", 0.0)))
        _bump(state, "people_poorer_half", float(totals.get("people_poorer_half", 0.0)))
        _bump(state, "shortfall_poorer_half", float(totals.get("shortfall_poorer_half", 0.0)))
        _bump(state, "person_turns", float(totals.get("alive", 0.0)))
        _bump(state, "shortfall", float(totals.get("shortfall", 0.0)))
    for row in (retail or {}).values():
        persons, rations = float(row["persons"]), float(row["rations"])
        _bump(state, "retail_person_turns", persons)
        _bump(state, "person_turns", persons)
        _bump(state, "shortfall", max(0.0, persons - rations))
        _bump(state, "priced_out_person_turns", float(row["priced_out_persons"]))
        _bump(state, "priced_out_deficit", float(row["priced_out_deficit"]))
    state.frame_turn = turn
    state.frame = frame
    return []


def primaries(counters: dict) -> dict:
    """The screens' welfare primaries from cumulative counters (None: no denominator)."""
    return {
        "P1_poorer_half_shortfall_per_1000": _ratio(1000.0 * counters.get("shortfall_poorer_half", 0.0),
                                                    counters.get("people_poorer_half", 0.0)),
        "P2_priced_out_per_1000": _ratio(1000.0 * counters.get("priced_out_person_turns", 0.0),
                                         counters.get("person_turns", 0.0)),
    }


def snapshot_summary(world) -> dict:
    """The completed turn's copied frame (never live state); None: not observed."""
    state = _state(world)
    source = world.turn - 1
    observed = state.frame_turn == source and state.frame is not None
    counters = {k: state.counters[k] for k in COUNTERS if k in state.counters}
    return {
        "schema_version": 1, "stage": STAGE, "source_turn": source,
        "world": dict(state.frame["world"]) if observed and state.frame["world"] is not None else None,
        "regions": [dict(r) for r in state.frame["regions"]] if observed else None,
        "counters": counters,
        "primaries": primaries(counters),
    }


def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1)))]


def _spread(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"min": min(values), "p50": _pct(values, 0.5), "p90": _pct(values, 0.9), "max": max(values)}


def extract_household_access_metrics(bundles: Iterable[dict]) -> dict:
    """Aggregate over bundles whose history rows carry
    ``livelihoods.household_access``; ``{}`` when none does (the report then
    has no section). Per-turn metrics pool the observed turns of every run;
    the primaries are each run's final cumulative values."""
    runs = 0
    met, depth, below, priced_out = [], [], [], []
    p1, p2 = [], []
    for bundle in bundles:
        last: dict[str, Any] | None = None
        for snap in bundle.get("history") or []:
            part = (snap.get("livelihoods") or {}).get("household_access")
            if not part:
                continue
            last = part
            world = part.get("world")
            if world is None:
                continue
            for values, key in ((met, "calories_met_share"), (depth, "shortfall_depth"),
                                (below, "below_floor_share"), (priced_out, "priced_out_share")):
                if world.get(key) is not None:
                    values.append(world[key])
        if last is None:
            continue
        runs += 1
        prim = last.get("primaries") or {}
        if prim.get("P1_poorer_half_shortfall_per_1000") is not None:
            p1.append(prim["P1_poorer_half_shortfall_per_1000"])
        if prim.get("P2_priced_out_per_1000") is not None:
            p2.append(prim["P2_priced_out_per_1000"])
    if not runs:
        return {}
    return {
        "runs": runs,
        "calories_met_share": _spread(met),
        "shortfall_depth": _spread(depth),
        "below_floor_share": _spread(below),
        "priced_out_share": _spread(priced_out),
        "P1_poorer_half_shortfall_per_1000": _spread(p1),
        "P2_priced_out_per_1000": _spread(p2),
    }
