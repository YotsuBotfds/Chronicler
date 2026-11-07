"""Capture, replay and calibrate the watershed account on development worlds.

In ``record_only`` the account changes nothing, so the index the simulation
uses, and everything the account reads, is the same whatever its constants.
``capture`` runs procedural development worlds once with ``--watershed`` and
saves, per turn, the account's inputs (``watershed.region_inputs``) and the
index observed after each tick, with the opening index and cover. A replay
runs the account on those inputs under other constants: ``simulate`` is a
fast transcription of ``watershed.account_step`` (storage, derived index and
flood excess only), checked against it by ``check``; the opening storage is
recomputed under the replayed constants.

Metrics (turns 0-74, the first climate cycle, are a spin-up from the
world-generation index and are left out of all but the drifts):

* level: mean (derived - observed) index, all regions, headwater regions and
  regions with upstream inflow;
* amplitude: the derived index's climate-phase amplitude over the observed's;
* correlation: the median per-region correlation of the two series;
* droughts: the share of region-turns in a drought (storage below the
  drought fraction for the drought length) against the same rule applied to
  the observed index's fill;
* drift: the relative change of the world's storage between whole climate
  cycles (cycle 2, turns 75-149, to cycle 5, turns 300-374: ``drift_long``;
  cycle 4 to cycle 5, turns 225-374: ``drift_late``), beside the observed
  index's own drift over the same cycles;
* floods: flood events (onset above the channel, open until arrivals fall
  to the recession threshold) per world and their lengths.

``score`` is the mean over worlds of each world's weighted absolute errors
(stationarity, level by group, amplitude, drought share), so errors in two
worlds cannot cancel. ``fit`` minimises it over a declared parameterization
(``PARAMETERIZATIONS``) by bounded Powell search from declared starting
values; ``cv`` holds out two seeds at a time, fits on the other six (32x10)
and scores the held seeds at 32x10 and 64x16.

Development worlds only (``DEVELOPMENT_PROCEDURAL``); it refuses any other
seed. Nothing here changes the simulation.

    python scripts/watershed_replay.py capture OUT [--seeds 7,11,...] [--turns 400] [--regions 32 --civs 10]
    python scripts/watershed_replay.py check OUT                       # simulate == account_step
    python scripts/watershed_replay.py replay OUT [--params JSON] [--b1]
    python scripts/watershed_replay.py fit OUT --form reduced [--json RESULT]
    python scripts/watershed_replay.py cv OUT32 OUT64 --form reduced [--pairs all|disjoint] [--json RESULT]
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

DEVELOPMENT_PROCEDURAL = (7, 11, 13, 17, 21, 31, 302, 303)
PHASES = ("temperate", "warming", "drought", "cooling")
CYCLE = 75


def _check_seeds(seeds):
    bad = [s for s in seeds if s not in DEVELOPMENT_PROCEDURAL]
    if bad:
        raise SystemExit(f"refused: {bad} are not procedural development worlds {DEVELOPMENT_PROCEDURAL}")


def capture(out: Path, seeds: list[int], turns: int, agents: str, regions: int = 32, civs: int = 10) -> None:
    from chronicler import watershed as ws
    from chronicler.main import _build_parser, execute_run
    _check_seeds(seeds)
    out.mkdir(parents=True, exist_ok=True)
    for seed in seeds:
        rec: dict = {"seed": seed, "regions": regions, "civs": civs, "agents": agents, "turns": []}
        originals = (ws.region_inputs, ws.after_ecology, ws.open_account)

        def region_inputs(world, state, _orig=originals[0]):
            turn, key, trend, inputs = _orig(world, state)
            rec["turns"].append({"turn": turn, "phase": key, "trend": trend, "inputs": [list(i) for i in inputs]})
            return turn, key, trend, inputs

        def after_ecology(world, acc, _orig=originals[1]):
            events = _orig(world, acc)
            rec["turns"][-1]["observed"] = [float(r.ecology.water) for r in world.regions]
            return events

        def open_account(world, graph, mode="record_only", _orig=originals[2]):
            state = _orig(world, graph, mode)
            # The opening cover and index cap, so a replay recomputes the opening storage under
            # its own constants (the capture's opening storage used the constants in force).
            rec.update(graph=graph.model_dump(), opening_storage=list(state.storage),
                       opening_index=list(state.last_index),
                       opening_cover=[ws._cover(r) for r in world.regions],
                       opening_cap=[ws.index_cap(r) for r in world.regions])
            return state

        ws.region_inputs, ws.after_ecology, ws.open_account = region_inputs, after_ecology, open_account
        try:
            folder = out / f"p{seed}"
            args = _build_parser().parse_args([
                "--seed", str(seed), "--turns", str(turns), "--regions", str(regions), "--civs", str(civs),
                "--worldgen", "procedural", "--agents", agents, "--simulate-only", "--watershed",
                "--output", str(folder / "chronicle.md"), "--state", str(folder / "state.json")])
            execute_run(args)
        finally:
            ws.region_inputs, ws.after_ecology, ws.open_account = originals
        from chronicler.bundle_codec import load_bundle
        events = load_bundle(folder / "chronicle_bundle.json")["events_timeline"]
        rec["river_floods"] = sum(1 for e in events if e.get("event_type") == "flood"
                                  and "river floods" in e.get("description", ""))
        rec["coastal_floods"] = sum(1 for e in events if e.get("event_type") == "flood"
                                    and "Flooding devastates" in e.get("description", ""))
        (out / f"capture_p{seed}.json").write_text(json.dumps(rec), encoding="utf-8")
        print(f"captured procedural {seed}: {len(rec['turns'])} turns", flush=True)



def load(folder: Path) -> list[dict]:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("capture_p*.json"))]
    _check_seeds([r["seed"] for r in records])
    return records


# --- Fast replay ----------------------------------------------------------------------

class World:
    """A capture as arrays (inputs are fixed; only the constants vary)."""

    def __init__(self, rec: dict):
        import numpy as np
        self.seed, self.size = rec["seed"], (rec.get("regions"), rec.get("civs"))
        graph = rec["graph"]
        self.down, self.order = list(graph["down"]), list(graph["order"])
        self.n = n = len(self.down)
        turns = rec["turns"]
        self.T = len(turns)
        self.turn = [t["turn"] for t in turns]
        self.phase = [t["phase"] for t in turns]
        self.trend = np.array([t["trend"] for t in turns])
        col = lambda k: np.array([[row[k] for row in t["inputs"]] for t in turns], dtype=float)
        self.terrain = [[row[0] for row in t["inputs"]] for t in turns]
        self.moisture, self.cover, self.water, self.exposure, self.shock = col(1), col(2), col(3), col(4), col(5)
        self.irrigated = col(6) > 0.5
        self.river = col(7) > 0.5
        self.cap = col(8)
        self.observed = np.array([t["observed"] for t in turns], dtype=float)
        self.opening_index = np.array(rec["opening_index"], dtype=float)
        self.opening_cover = np.array(rec.get("opening_cover") or [row[2] for row in turns[0]["inputs"]], dtype=float)
        self.opening_cap = np.array(rec.get("opening_cap") or [row[8] for row in turns[0]["inputs"]], dtype=float)
        self.last = np.vstack([self.opening_index[None, :], self.observed[:-1]])
        self.upstream = [any(d == r for d in self.down) for r in range(n)]
        self.tundra = np.array([[tt == "tundra" for tt in row] for row in self.terrain])
        self.river_floods, self.coastal_floods = rec.get("river_floods"), rec.get("coastal_floods")


def simulate(world: World, params) -> dict:
    """``watershed.account_step`` over the capture (storage, derived index and
    flood excess), from the opening storage under ``params``."""
    import numpy as np
    floor = params.index_floor
    phase_p = np.array([params.phase_precipitation[k] for k in world.phase])[:, None]
    phase_e = np.array([params.phase_evaporation[k] for k in world.phase])[:, None]
    et = world.exposure * world.trend[:, None]
    cap = params.storage_base * (1.0 + params.forest_retention * world.cover)
    span = np.maximum(world.cap - floor, 1e-9)
    p = (params.precipitation_base * (0.2 + world.moisture) * np.maximum(0.0, 1.0 - (1.0 - phase_p) * et)
         * np.maximum(0.0, 1.0 - params.shock_precipitation * world.shock))
    warming = np.array([k == "warming" for k in world.phase])[:, None]
    p = p + params.tundra_melt * (warming & world.tundra)
    tev = np.array([[params.terrain_evaporation.get(tt, 1.0) for tt in row] for row in world.terrain])
    e_pot = params.evaporation_base * (1.0 + (phase_e - 1.0) * et) * tev * (1.0 + params.transpiration * world.cover)
    x = (world.water - world.last) / span * cap
    x_in, want = np.maximum(x, 0.0), np.maximum(-x, 0.0)
    demand = np.where(world.irrigated, params.irrigation_demand, 0.0)
    if params.channel_ratio is not None:
        # Normal inflow: normal precipitation plus the seasonal melt (tundra, warming).
        basin = params.precipitation_base * (0.2 + world.moisture) + params.tundra_melt * (warming & world.tundra)
        for r in world.order:
            if world.down[r] >= 0:
                basin[:, world.down[r]] += basin[:, r]
        channel = params.channel_ratio * basin
    else:
        channel = params.channel_capacity * np.where(world.river, params.river_channel_factor, 1.0)
    P, C, XI, XW, EP, D = (a.tolist() for a in (p, cap, x_in, want, e_pot, demand))
    open_cap = params.storage_base * (1.0 + params.forest_retention * world.opening_cover)
    open_span = np.maximum(world.opening_cap - floor, 1e-9)
    s = (open_cap * np.clip((world.opening_index - floor) / open_span, 0.0, 1.0)).tolist()
    n, down, order, keep = world.n, world.down, world.order, 1.0 - params.baseflow
    storage = np.empty((world.T, n))
    withdrawal = np.empty((world.T, n))
    inflow = np.empty((world.T, n))
    for k in range(world.T):
        pk, ck, xik, xwk, epk, dk = P[k], C[k], XI[k], XW[k], EP[k], D[k]
        inc = [0.0] * n
        s2row = [0.0] * n
        wrow = [0.0] * n
        for r in order:
            sr = s[r]
            xo = xwk[r] if xwk[r] < sr else sr
            a = sr + pk[r] + xik[r] - xo + inc[r]
            e = epk[r] if epk[r] < a else a
            t = a - e
            w = (dk[r] if dk[r] < t else t) if dk[r] > 0.0 else 0.0
            b = t - w
            s2 = keep * (b if b < ck[r] else ck[r])
            q = b - s2
            d = down[r]
            if d >= 0:
                inc[d] += q
            s2row[r], wrow[r] = s2, w
        s = s2row
        storage[k], withdrawal[k], inflow[k] = s2row, wrow, inc
    fill = np.minimum(1.0, storage / cap + params.irrigation_wetting * withdrawal / cap)
    derived = floor + (world.cap - floor) * np.maximum(0.0, fill)
    excess = np.maximum(0.0, p + inflow - channel)
    return {"storage": storage, "capacity": cap, "derived": derived, "excess": excess,
            "arrivals": p + inflow, "channel": channel, "precipitation": p}


def check(folder: Path, turns: int = 120) -> float:
    """Max abs difference of ``simulate`` against ``watershed.account_step``."""
    from chronicler import watershed as ws
    from chronicler.watershed_state import WatershedGraph
    worst = 0.0
    for rec in load(folder):
        world, params = World(rec), ws.PARAMETERS
        sim = simulate(world, params)
        graph = WatershedGraph(**rec["graph"])
        n = world.n
        storage = [float(v) for v in (params.storage_base * (1.0 + params.forest_retention * world.opening_cover)
                                      * ((world.opening_index - params.index_floor)
                                         / (world.opening_cap - params.index_floor)).clip(0, 1))]
        last = list(rec["opening_index"])
        for k, t in enumerate(rec["turns"][:turns]):
            plan = ws.account_step(graph, storage, last, t["turn"], t["phase"], t["trend"],
                                   [ws.RegionInput(*row) for row in t["inputs"]], params)
            c = plan.columns
            for name, key in (("storage", "storage"), ("derived", "index_derived"), ("excess", "flood_excess")):
                worst = max(worst, max(abs(sim[name][k][r] - c[key][r]) for r in range(n)))
            storage, last = list(c["storage"]), list(t["observed"])
    return worst


def _runs(flags) -> "object":
    """Per region, the length of the run of True ending at each turn."""
    import numpy as np
    out = np.zeros(flags.shape, dtype=int)
    run = np.zeros(flags.shape[1], dtype=int)
    for k in range(flags.shape[0]):
        run = np.where(flags[k], run + 1, 0)
        out[k] = run
    return out


def flood_events(arrivals, channel, recession: float):
    """Flood events with hysteresis (as ``watershed.after_ecology``): a list of
    (region, start, turns) and the count of region-turns inside an event."""
    T, n = arrivals.shape
    events, open_at = [], {}
    for k in range(T):
        for r in range(n):
            if r in open_at:
                if arrivals[k, r] > recession * channel[k, r]:
                    open_at[r][2] += 1
                else:
                    events.append(tuple(open_at.pop(r)))
            elif k > 0 and arrivals[k, r] > channel[k, r] and arrivals[k - 1, r] <= channel[k - 1, r]:
                open_at[r] = [r, k, 1]       # crosses the channel from below; never on the opening turn
    events.extend(tuple(v) for v in open_at.values())
    return events


def world_metrics(world: World, sim: dict, params, start: int = CYCLE) -> dict:
    import numpy as np
    d, o = sim["derived"][start:], world.observed[start:]
    up = np.array(world.upstream)
    out = {"seed": world.seed, "size": f"{world.size[0]}x{world.size[1]}", "turns": world.T}
    for name, mask in (("all", np.ones(world.n, bool)), ("headwater", ~up), ("upstream", up)):
        out[f"level_{name}"] = float((d[:, mask] - o[:, mask]).mean()) if mask.any() else 0.0
    phases = world.phase[start:]
    means = {ph: (float(d[[i for i, p in enumerate(phases) if p == ph]].mean()),
                  float(o[[i for i, p in enumerate(phases) if p == ph]].mean())) for ph in PHASES}
    amp_d = max(v[0] for v in means.values()) - min(v[0] for v in means.values())
    amp_o = max(v[1] for v in means.values()) - min(v[1] for v in means.values())
    out["amplitude_ratio"] = amp_d / amp_o if amp_o else 1.0
    corrs = []
    for r in range(world.n):
        if d[:, r].std() > 0 and o[:, r].std() > 0:
            corrs.append(float(np.corrcoef(d[:, r], o[:, r])[0, 1]))
    out["median_corr"] = float(np.median(corrs)) if corrs else None
    frac_d = sim["storage"] / sim["capacity"]
    span = np.maximum(world.cap - params.index_floor, 1e-9)
    frac_o = (world.observed - params.index_floor) / span
    out["drought_share"] = float((_runs(frac_d < params.drought_fraction)[start:] >= params.drought_turns).mean())
    out["drought_share_observed"] = float((_runs(frac_o < params.drought_fraction)[start:] >= params.drought_turns).mean())
    total = sim["storage"].sum(axis=1)
    obs_total = world.observed.sum(axis=1)

    def cycle(series, c):
        a, b = c * CYCLE, (c + 1) * CYCLE
        return float(series[a:b].mean()) if b <= len(series) else None

    def drift(series, c0, c1):
        a, b = cycle(series, c0), cycle(series, c1)
        return (b - a) / a if a and b is not None else None

    out["drift_long"], out["drift_long_observed"] = drift(total, 1, 4), drift(obs_total, 1, 4)
    out["drift_late"], out["drift_late_observed"] = drift(total, 3, 4), drift(obs_total, 3, 4)
    out["drift_early"], out["drift_early_observed"] = drift(total, 1, 2), drift(obs_total, 1, 2)
    out["storage_open_end"] = [round(float(sim["storage"][0].sum()), 2), round(float(total[-1]), 2)]
    events = [e for e in flood_events(sim["arrivals"], sim["channel"], params.flood_recession) if e[1] >= 1]
    lengths = sorted(e[2] for e in events)
    out["flood_events"] = len(events)
    out["flood_regions"] = len({e[0] for e in events})
    out["flood_event_turns_max"] = lengths[-1] if lengths else 0
    out["flood_event_turns_median"] = lengths[len(lengths) // 2] if lengths else 0
    excess = sim["excess"][1:] > 0
    out["flood_region_turns"] = int(excess.sum())
    runs = _runs(excess)
    out["flood_run_max"] = int(runs.max()) if runs.size else 0
    out["coastal_floods"], out["river_floods_old"] = world.coastal_floods, world.river_floods
    return out


#: Weights of each world's absolute errors in ``score``.
WEIGHTS = {"drift_long": 4.0, "level_all": 4.0, "level_headwater": 1.0, "level_upstream": 1.0,
           "amplitude": 1.0, "drought": 2.0}


def world_score(m: dict) -> float:
    drift = m["drift_long"] if m["drift_long"] is not None else m["drift_early"]
    return (WEIGHTS["drift_long"] * abs(drift) + WEIGHTS["level_all"] * abs(m["level_all"])
            + WEIGHTS["level_headwater"] * abs(m["level_headwater"])
            + WEIGHTS["level_upstream"] * abs(m["level_upstream"])
            + WEIGHTS["amplitude"] * abs(m["amplitude_ratio"] - 1.0)
            + WEIGHTS["drought"] * abs(m["drought_share"] - m["drought_share_observed"]))


def evaluate(worlds: list[World], params) -> tuple[float, list[dict]]:
    metrics = [world_metrics(w, simulate(w, params), params) for w in worlds]
    for m in metrics:
        m["score"] = world_score(m)
    return math.fsum(m["score"] for m in metrics) / len(metrics), metrics


# --- Parameterizations and fit ------------------------------------------------------------

#: Each parameterization: the free constants with their declared physical ranges and
#: starting values, and the constants it fixes (others keep ``Parameters`` defaults).
#: Phase factors f scale precipitation (or evaporation) by 1 - (1 - f) x exposure x trend.
PARAMETERIZATIONS: dict[str, dict] = {
    # All twelve climate and forest constants free (the first B2 fit's set).
    "full": {"free": {
        "precipitation_base": ((0.04, 0.3), 0.1), "evaporation_base": ((0.005, 0.12), 0.03),
        "baseflow": ((0.002, 0.08), 0.05),
        "phase_precipitation.warming": ((0.5, 1.5), 1.0), "phase_precipitation.drought": ((-1.5, 1.0), 0.3),
        "phase_precipitation.cooling": ((-1.5, 1.0), 0.6),
        "phase_evaporation.warming": ((1.0, 2.0), 1.3), "phase_evaporation.drought": ((1.0, 4.0), 1.6),
        "phase_evaporation.cooling": ((0.5, 1.5), 0.7),
        "shock_precipitation": ((0.0, 3.0), 1.0), "transpiration": ((0.0, 1.0), 0.3),
        "forest_retention": ((0.0, 1.0), 0.5)},
        "fixed": {}},
    # Six free: the water balance (precipitation, evaporation, baseflow) and the two phases in
    # which the old index loses water (drought, cooling). Fixed, with their reasons:
    # warming factors 1.0 (the old index has no warming-phase water term besides tundra melt,
    # which the account keeps); cooling evaporation 1.0 (collinear with cooling precipitation:
    # only their net is identified); harvest shock 1.0 (its declared meaning: a bad year of
    # depth h is a precipitation deficit of h); forest retention 0.5 and transpiration 0.3 (the
    # B1 declared forest linkage: the old index has no forest storage, so it cannot identify them).
    "reduced": {"free": {
        "precipitation_base": ((0.04, 0.3), 0.1), "evaporation_base": ((0.005, 0.12), 0.03),
        "baseflow": ((0.002, 0.08), 0.05),
        "phase_precipitation.drought": ((-1.0, 1.0), 0.3), "phase_precipitation.cooling": ((-1.0, 1.0), 0.6),
        "phase_evaporation.drought": ((1.0, 4.0), 1.6)},
        "fixed": {"phase_precipitation.warming": 1.0, "phase_evaporation.warming": 1.0,
                  "phase_evaporation.cooling": 1.0, "shock_precipitation": 1.0,
                  "forest_retention": 0.5, "transpiration": 0.3}},
    # Three free: "minimal" with evaporation fixed at its B1 value 0.03. Precipitation and
    # evaporation set the water balance together (the "minimal" folds keep their ratio at
    # 6.3-6.8 while both move by a third), so only their ratio is identified; one is fixed.
    "core": {"free": {
        "precipitation_base": ((0.04, 0.4), 0.15), "baseflow": ((0.002, 0.08), 0.05),
        "phase_precipitation.cooling": ((-1.0, 1.0), 0.6)},
        "fixed": {"evaporation_base": 0.03, "phase_precipitation.warming": 1.0, "phase_evaporation.warming": 1.0,
                  "phase_precipitation.drought": -1.0, "phase_evaporation.drought": 4.0,
                  "phase_evaporation.cooling": 1.0, "shock_precipitation": 1.0,
                  "forest_retention": 0.5, "transpiration": 0.3}},
    # Four free. The reduced fit drives the drought phase to its physical limits, so they are
    # fixed there: drought precipitation -1.0 (every drop of rain is lost at the largest
    # exposure x trend share, 0.5) and drought evaporation 4.0 (potential evaporation x2.5 there,
    # the declared limit). The rest as in "reduced".
    "minimal": {"free": {
        "precipitation_base": ((0.04, 0.3), 0.1), "evaporation_base": ((0.005, 0.12), 0.03),
        "baseflow": ((0.002, 0.08), 0.05), "phase_precipitation.cooling": ((-1.0, 1.0), 0.6)},
        "fixed": {"phase_precipitation.warming": 1.0, "phase_evaporation.warming": 1.0,
                  "phase_precipitation.drought": -1.0, "phase_evaporation.drought": 4.0,
                  "phase_evaporation.cooling": 1.0, "shock_precipitation": 1.0,
                  "forest_retention": 0.5, "transpiration": 0.3}},
}


def _with(params, name: str, value: float):
    from dataclasses import replace
    if "." in name:
        table, key = name.split(".")
        return replace(params, **{table: {**getattr(params, table), key: value}})
    return replace(params, **{name: value})


def build(form: str, values: list[float] | None = None, base=None):
    """``Parameters`` of a parameterization (its starting values unless given)."""
    from chronicler import watershed as ws
    spec = PARAMETERIZATIONS[form]
    params = base or ws.PARAMETERS
    for name, value in spec["fixed"].items():
        params = _with(params, name, value)
    names = list(spec["free"])
    values = values if values is not None else [spec["free"][k][1] for k in names]
    for name, value in zip(names, values):
        params = _with(params, name, float(value))
    return params


#: Starting points of the search, as fractions of each free constant's range (the declared
#: starting value first): a local search from one point stopped in different optima per fold.
STARTS = (None, 0.25, 0.75)


def fit(worlds: list[World], form: str, maxfev: int = 1500) -> dict:
    """Bounded Powell search of ``score`` from each of ``STARTS`` (deterministic); the best wins."""
    import numpy as np
    from scipy.optimize import minimize
    spec = PARAMETERIZATIONS[form]
    names = list(spec["free"])
    bounds = [spec["free"][k][0] for k in names]
    lo, hi = np.array([b[0] for b in bounds]), np.array([b[1] for b in bounds])
    calls = {"n": 0}

    def objective(x):
        calls["n"] += 1
        return evaluate(worlds, build(form, list(np.clip(x, lo, hi))))[0]

    best = None
    for start in STARTS:
        x0 = np.array([spec["free"][k][1] for k in names]) if start is None else lo + start * (hi - lo)
        result = minimize(objective, x0, method="Powell", bounds=bounds,
                          options={"maxfev": maxfev, "xtol": 1e-3, "ftol": 1e-5})
        if best is None or result.fun < best.fun - 1e-9:
            best = result
    result = best
    x = [round(float(v), 4) for v in np.clip(result.x, lo, hi)]
    params = build(form, x)
    train, metrics = evaluate(worlds, params)
    at_bound = [k for k, v, (lo, hi) in zip(names, x, bounds) if abs(v - lo) < 1e-3 * (hi - lo) or abs(v - hi) < 1e-3 * (hi - lo)]
    return {"form": form, "values": dict(zip(names, x)), "train_score": train, "at_bound": at_bound,
            "evaluations": calls["n"], "metrics": metrics, "params": params}


def _pairs(seeds, mode: str):
    if mode == "all":
        return list(itertools.combinations(seeds, 2))
    return [tuple(seeds[i:i + 2]) for i in range(0, len(seeds), 2)]


def cv(folder32: Path, folder64: Path, form: str, pairs: str = "disjoint", maxfev: int = 1500) -> dict:
    w32 = {w.seed: w for w in (World(r) for r in load(folder32))}
    w64 = {w.seed: w for w in (World(r) for r in load(folder64))}
    seeds = sorted(w32)
    folds = []
    for held in _pairs(seeds, pairs):
        train = [w32[s] for s in seeds if s not in held]
        result = fit(train, form, maxfev)
        test32, m32 = evaluate([w32[s] for s in held], result["params"])
        test64, m64 = evaluate([w64[s] for s in held if s in w64], result["params"])
        folds.append({"held": list(held), "values": result["values"], "at_bound": result["at_bound"],
                      "train_score": result["train_score"], "test_score_32": test32, "test_score_64": test64,
                      "test_32": m32, "test_64": m64})
        print(f"fold {held}: train {result['train_score']:.3f} test32 {test32:.3f} test64 {test64:.3f} "
              f"bound {result['at_bound']} {json.dumps(result['values'])}", flush=True)
    return {"form": form, "pairs": pairs, "folds": folds}


def _summary(metrics: list[dict]) -> dict:
    keys = ("score", "level_all", "level_headwater", "level_upstream", "amplitude_ratio", "median_corr",
            "drought_share", "drought_share_observed", "drift_long", "drift_long_observed", "drift_late",
            "drift_late_observed", "flood_events", "flood_event_turns_max", "flood_region_turns", "coastal_floods")
    out = {}
    for k in keys:
        vals = [m[k] for m in metrics if m.get(k) is not None]
        out[k] = math.fsum(vals) / len(vals) if vals else None
    out["max_abs_drift_long"] = max(abs(m["drift_long"]) for m in metrics if m["drift_long"] is not None)
    out["max_abs_level_upstream"] = max(abs(m["level_upstream"]) for m in metrics)
    return out


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if k != "params"}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, 4)
    return obj


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("out", type=Path)
    cap.add_argument("--seeds", default=",".join(map(str, DEVELOPMENT_PROCEDURAL)))
    cap.add_argument("--turns", type=int, default=400)
    cap.add_argument("--agents", default="hybrid")
    cap.add_argument("--regions", type=int, default=32)
    cap.add_argument("--civs", type=int, default=10)
    chk = sub.add_parser("check")
    chk.add_argument("out", type=Path)
    rep = sub.add_parser("replay")
    rep.add_argument("out", type=Path)
    rep.add_argument("--params", help="JSON object of Parameters fields to override")
    rep.add_argument("--b1", action="store_true", help="the B1 constants instead of those in force")
    fi = sub.add_parser("fit")
    fi.add_argument("out", type=Path)
    fi.add_argument("--form", choices=sorted(PARAMETERIZATIONS), default="reduced")
    fi.add_argument("--maxfev", type=int, default=1500)
    fi.add_argument("--json", type=Path)
    cvp = sub.add_parser("cv")
    cvp.add_argument("out32", type=Path)
    cvp.add_argument("out64", type=Path)
    cvp.add_argument("--form", choices=sorted(PARAMETERIZATIONS), default="reduced")
    cvp.add_argument("--pairs", choices=("all", "disjoint"), default="disjoint")
    cvp.add_argument("--maxfev", type=int, default=1500)
    cvp.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "capture":
        capture(args.out, [int(s) for s in args.seeds.split(",")], args.turns, args.agents, args.regions, args.civs)
        return 0
    if args.cmd == "check":
        print(f"max abs difference simulate vs account_step: {check(args.out):.3e}")
        return 0
    if args.cmd == "fit":
        result = fit([World(r) for r in load(args.out)], args.form, args.maxfev)
        result["summary"] = _summary(result["metrics"])
        out = _clean(result)
        if args.json:
            args.json.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({k: out[k] for k in ("form", "values", "train_score", "at_bound", "evaluations", "summary")},
                         indent=1))
        return 0
    if args.cmd == "cv":
        result = _clean(cv(args.out32, args.out64, args.form, args.pairs, args.maxfev))
        if args.json:
            args.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        return 0
    from dataclasses import replace
    from chronicler import watershed as ws
    params = ws.B1_PARAMETERS if args.b1 else ws.PARAMETERS
    if args.params:
        params = replace(params, **json.loads(args.params))
    score, metrics = evaluate([World(r) for r in load(args.out)], params)
    print(json.dumps(_clean({"score": score, "summary": _summary(metrics), "worlds": metrics,
                             "params": None, "constants": params.as_dict()}), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
