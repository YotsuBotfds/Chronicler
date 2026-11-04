"""The civilization-trajectory oracles: the era oracle (M53 oracle 3: era
inflections, and no silent collapses) and the arc oracle (oracle 6: each
civilization's arc family), with the series helpers they share.

Split out of ``validation_io`` verbatim; ``validation_io`` re-exports every
name here (docs/integration/validation-split.md). The crisis event types the
era oracle counts stay in ``validation_io`` with the loader that reads them.
"""
from __future__ import annotations

from collections import Counter

from .validation_common import _mean, required_seed_count


# Era oracle (M53 oracle 3). Recalibrated 2026-10 for living worlds
# (docs/integration/wave3-defaults.md). A silent collapse is a population
# collapse of one civ that neither its own era signals nor its recorded crises
# mark. Seed fractions and the 30% drop are the M53 spec's; the smoothing
# window is the inflection detector's own, and the 5-turn slack is unchanged.
ERA_INFLECTION_SEED_FRACTION_MIN = 0.80
ERA_SILENT_COLLAPSE_SEED_FRACTION_MAX = 0.10
ERA_COLLAPSE_DROP_FRACTION = 0.30
ERA_COLLAPSE_SMOOTHING_WINDOW = 5
ERA_SIGNAL_SLACK_TURNS = 5


def _collapse_nearby_points(points: list[int], radius: int = 5) -> list[int]:
    if not points:
        return []
    points = sorted(points)
    collapsed = [points[0]]
    for point in points[1:]:
        if point - collapsed[-1] > radius:
            collapsed.append(point)
    return collapsed


def _trajectory_metric_series(trajectory: dict) -> dict[str, list[float]]:
    return {
        "population": [float(v) for v in trajectory.get("population", [])],
        "treasury": [float(v) for v in trajectory.get("treasury", [])],
        "stability": [float(v) for v in trajectory.get("stability", [])],
        "territory": [float(v) for v in trajectory.get("territory", [])],
        "prestige": [float(v) for v in trajectory.get("prestige", [])],
    }


def _trajectory_composite_series(
    trajectory: dict,
    metrics: tuple[str, ...] | None = None,
) -> list[float]:
    series_map = _trajectory_metric_series(trajectory)
    available: list[list[float]] = []
    selected_metrics = metrics or tuple(series_map.keys())
    for metric_name in selected_metrics:
        values = series_map.get(metric_name, [])
        if not values:
            continue
        baseline = abs(values[0]) if values[0] != 0 else max(abs(v) for v in values) or 1.0
        available.append([value / baseline for value in values])
    if not available:
        return trajectory.get("population", [])
    length = min(len(series) for series in available)
    return [
        sum(series[idx] for series in available) / len(available)
        for idx in range(length)
    ]


def _smoothed_series(series: list[float], window: int) -> list[float]:
    smoothed: list[float] = []
    for i in range(len(series)):
        start = max(0, i - window + 1)
        chunk = series[start : i + 1]
        smoothed.append(sum(chunk) / len(chunk))
    return smoothed


def _significant_slope_pattern(
    smoothed: list[float],
    *,
    epsilon_scale: float = 0.8,
    min_run_fraction: float = 0.02,
    min_delta_fraction: float = 0.03,
) -> tuple[int, ...]:
    if len(smoothed) < 2:
        return ()

    deriv = [smoothed[i + 1] - smoothed[i] for i in range(len(smoothed) - 1)]
    avg_abs_slope = _mean([abs(delta) for delta in deriv])
    series_range = max(smoothed) - min(smoothed)
    epsilon = max(avg_abs_slope * epsilon_scale, series_range * 0.001, 1e-6)

    raw_segments: list[tuple[int, int, int, float]] = []
    current_sign = 0
    segment_start = 0
    for idx, delta in enumerate(deriv):
        sign = 1 if delta > epsilon else -1 if delta < -epsilon else 0
        if sign == 0:
            continue
        if current_sign == 0:
            current_sign = sign
            segment_start = idx
            continue
        if sign != current_sign:
            raw_segments.append(
                (
                    current_sign,
                    segment_start,
                    idx,
                    smoothed[idx] - smoothed[segment_start],
                )
            )
            current_sign = sign
            segment_start = idx

    if current_sign != 0:
        raw_segments.append(
            (
                current_sign,
                segment_start,
                len(smoothed) - 1,
                smoothed[-1] - smoothed[segment_start],
            )
        )

    min_run = max(3, int(len(smoothed) * min_run_fraction))
    min_delta = max(series_range * min_delta_fraction, epsilon * min_run)
    pattern: list[int] = []
    for sign, start, end, delta in raw_segments:
        duration = max(1, end - start)
        if duration < min_run or abs(delta) < min_delta:
            continue
        if not pattern or pattern[-1] != sign:
            pattern.append(sign)
    return tuple(pattern)


def detect_inflection_points(
    series: list[float],
    smoothing_window: int = 5,
) -> list[int]:
    """Oracle 3: Detect era inflection points in a time series.

    Uses smoothed-derivative magnitude detection with auto-calibrated
    threshold based on the derivative's own standard deviation. An inflection
    point is a turn where the local slope of the smoothed series exceeds
    3.0 × std of the derivative, indicating a structural shift
    (collapse, rapid growth, recovery) rather than noise.

    Nearby candidate points within ``smoothing_window`` turns are collapsed
    to the single highest-magnitude point to avoid duplicate reporting of
    the same transition.

    Parameters
    ----------
    series:
        List of numeric values (e.g. population per turn).
    smoothing_window:
        Rolling mean window size for smoothing (default 5).

    Returns
    -------
    List of turn indices where inflection points occur (large-magnitude
    slope changes in the smoothed series). Returns an empty list for
    series that are noisy but structurally stable.
    """
    n = len(series)
    if n < smoothing_window + 1:
        return []

    # Step 1: Rolling mean smoothing
    smoothed: list[float] = []
    for i in range(n):
        start = max(0, i - smoothing_window + 1)
        window = series[start : i + 1]
        smoothed.append(sum(window) / len(window))

    # Step 2: First derivative (diff of smoothed values)
    deriv: list[float] = [smoothed[i + 1] - smoothed[i] for i in range(n - 1)]

    # Step 3: Auto-calibrated threshold — 3.0 × std of first derivative.
    # Using derivative std (not series std) keeps the threshold proportional
    # to typical turn-to-turn slope variation, making detection sensitive to
    # structural shifts but blind to slow drift or noise.
    mean_d = sum(deriv) / len(deriv)
    var_d = sum((d - mean_d) ** 2 for d in deriv) / len(deriv)
    std_d = var_d ** 0.5
    threshold = 3.0 * std_d

    if threshold == 0.0:
        # Flat series — no inflection points possible
        return []

    # Step 4: Find points where |derivative| exceeds threshold.
    # Skip the first (smoothing_window - 1) steps to avoid warm-up artifacts
    # from the rolling mean operating on an incomplete window at series start.
    # These represent large structural shifts in the series.
    candidates: list[tuple[int, float]] = []  # (turn_index, abs_magnitude)
    warmup = smoothing_window - 1
    for i, d in enumerate(deriv):
        if i < warmup:
            continue
        if abs(d) > threshold:
            # Turn index in original series: derivative at i spans [i, i+1]
            candidates.append((i + 1, abs(d)))

    if not candidates:
        return []

    # Step 5: Collapse nearby candidates within smoothing_window into single peak
    # Sort by index (already in order), merge clusters.
    inflection_points: list[int] = []
    cluster_start = candidates[0][0]
    cluster_best_idx = candidates[0][0]
    cluster_best_mag = candidates[0][1]

    for turn_idx, mag in candidates[1:]:
        if turn_idx - cluster_start <= smoothing_window:
            # Same cluster — keep best magnitude
            if mag > cluster_best_mag:
                cluster_best_mag = mag
                cluster_best_idx = turn_idx
        else:
            inflection_points.append(cluster_best_idx)
            cluster_start = turn_idx
            cluster_best_idx = turn_idx
            cluster_best_mag = mag

    inflection_points.append(cluster_best_idx)
    return inflection_points


def _legacy_classify_civ_arc(trajectory: dict) -> str:
    """Oracle 6: Classify a civilization's trajectory into one of six emotional arc families.

    Based on Kurt Vonnegut's story shapes. Uses a thirds-based analysis of a
    smoothed population series to determine the dominant arc pattern.

    Parameters
    ----------
    trajectory:
        Dict with at least a "population" key containing a list of numeric values.

    Returns
    -------
    One of: "rags_to_riches", "riches_to_rags", "icarus", "oedipus",
    "cinderella", "man_in_a_hole", "stable".
    """
    pop = _trajectory_composite_series(trajectory)
    n = len(pop)
    if n == 0:
        return "stable"

    # Step 1: Smooth the population series with rolling mean
    window = max(10, n // 10)
    smoothed: list[float] = []
    for i in range(n):
        start = max(0, i - window + 1)
        chunk = pop[start: i + 1]
        smoothed.append(sum(chunk) / len(chunk))

    # Step 2: Split into thirds and compute mean for each third
    third = max(1, n // 3)
    first_mean = sum(smoothed[:third]) / third
    # Middle third: avoid overlap at boundaries for small series
    mid_start = third
    mid_end = 2 * third
    mid_chunk = smoothed[mid_start:mid_end] if mid_end > mid_start else [smoothed[mid_start]]
    middle_mean = sum(mid_chunk) / len(mid_chunk)
    last_chunk = smoothed[2 * third:] if smoothed[2 * third:] else [smoothed[-1]]
    last_mean = sum(last_chunk) / len(last_chunk)

    # Step 3: Stable check — all thirds within 20% of each other
    overall_mean = (first_mean + middle_mean + last_mean) / 3.0
    if overall_mean != 0.0:
        max_dev = max(
            abs(first_mean - overall_mean),
            abs(middle_mean - overall_mean),
            abs(last_mean - overall_mean),
        )
        if max_dev / abs(overall_mean) <= 0.20:
            return "stable"
    else:
        # All values are zero — treat as stable
        return "stable"

    # Step 4: Classify by pattern of thirds
    # rags_to_riches: monotone up
    if first_mean < middle_mean < last_mean:
        return "rags_to_riches"

    # riches_to_rags: monotone down
    if first_mean > middle_mean > last_mean:
        return "riches_to_rags"

    # icarus: up then down (middle is the peak)
    if middle_mean > first_mean and middle_mean > last_mean:
        return "icarus"

    # For the down-then-up family, distinguish by final level vs start
    if first_mean > middle_mean and last_mean > middle_mean:
        # cinderella: recovers to at least starting level
        if last_mean >= first_mean:
            return "cinderella"
        # man_in_a_hole: partial recovery but doesn't reach start
        # oedipus: down-up-down — requires last < first, use oedipus when
        # last < first (same condition as man_in_a_hole without further info)
        # Per spec: oedipus = middle < first AND middle < last AND last < first
        # man_in_a_hole = first > middle AND last > middle AND last < first
        # Both conditions are identical from thirds analysis — use oedipus as
        # the canonical name here for partial recovery with final < start.
        # Spec says oedipus: last < first; man_in_a_hole: last < first too.
        # Differentiate: oedipus ends lower (last < middle average baseline),
        # man_in_a_hole ends in middle recovery range.
        # Simple heuristic: if last is closer to first or above midpoint,
        # it's man_in_a_hole; if last is near the trough, it's oedipus.
        # Use midpoint of (first, middle) as divider:
        midpoint = (first_mean + middle_mean) / 2.0
        if last_mean >= midpoint:
            return "man_in_a_hole"
        else:
            return "oedipus"

    # Fallback
    return "stable"


def _classify_series_by_thirds(series: list[float]) -> str:
    """Classify a smoothed series by coarse first/middle/last thirds.

    This is intentionally blunt. It exists as a fallback when the fine-grained
    derivative pattern overreacts to a short early surge even though the
    trajectory spends most of its lifespan in sustained decline.
    """
    n = len(series)
    if n == 0:
        return "stable"

    smoothed = _smoothed_series(series, max(10, n // 10))
    third = max(1, n // 3)
    first_mean = sum(smoothed[:third]) / third
    mid_start = third
    mid_end = 2 * third
    mid_chunk = smoothed[mid_start:mid_end] if mid_end > mid_start else [smoothed[mid_start]]
    middle_mean = sum(mid_chunk) / len(mid_chunk)
    last_chunk = smoothed[2 * third:] if smoothed[2 * third:] else [smoothed[-1]]
    last_mean = sum(last_chunk) / len(last_chunk)

    overall_mean = (first_mean + middle_mean + last_mean) / 3.0
    if overall_mean == 0.0:
        return "stable"
    max_dev = max(
        abs(first_mean - overall_mean),
        abs(middle_mean - overall_mean),
        abs(last_mean - overall_mean),
    )
    if max_dev / abs(overall_mean) <= 0.20:
        return "stable"

    if first_mean < middle_mean < last_mean:
        return "rags_to_riches"
    if first_mean > middle_mean > last_mean:
        return "riches_to_rags"
    if middle_mean > first_mean and middle_mean > last_mean:
        return "icarus"
    if first_mean > middle_mean and last_mean > middle_mean:
        if last_mean >= first_mean:
            return "cinderella"
        midpoint = (first_mean + middle_mean) / 2.0
        if last_mean >= midpoint:
            return "man_in_a_hole"
        return "oedipus"
    return "stable"


def _has_material_rags_growth(trajectory: dict) -> bool:
    """Return true when a rags arc reflects durable population/territory growth.

    Composite prestige can rise for one-person or extinct successor civs; those
    should not dominate the rags-to-riches family without material growth.
    """
    population = [float(x or 0.0) for x in trajectory.get("population", [])]
    territory = [float(x or 0.0) for x in trajectory.get("territory", [])]
    if population:
        start_pop = max(population[0], 0.0)
        final_pop = max(population[-1], 0.0)
        peak_pop = max(population)
        if final_pop >= max(5.0, start_pop * 1.25) and final_pop >= peak_pop * 0.75:
            return True
    if territory:
        start_territory = max(territory[0], 0.0)
        final_territory = max(territory[-1], 0.0)
        peak_territory = max(territory)
        if final_territory >= start_territory + 1.0 and final_territory >= peak_territory * 0.75:
            return True
    return False


def _classify_material_arc_when_prestige_masks_growth(trajectory: dict) -> str:
    """Classify population/territory shape when prestige masks material decline.

    A monotone prestige score can make a collapsed successor look like a
    rags-to-riches arc.  Rather than dumping those non-flat material histories
    into ``stable``, classify the material-only series and use any non-stable
    shape it exposes.
    """
    material_series = _trajectory_composite_series(
        trajectory,
        metrics=("population", "territory"),
    )
    if not material_series:
        return "stable"

    n = len(material_series)
    smoothed = _smoothed_series(material_series, max(10, n // 10))
    mean_value = _mean(smoothed)
    series_range = max(smoothed) - min(smoothed)
    if mean_value == 0.0:
        return "stable" if series_range == 0.0 else _classify_series_by_thirds(smoothed)
    if series_range / abs(mean_value) <= 0.20:
        return "stable"

    pattern = _significant_slope_pattern(smoothed)
    if pattern == (1,):
        return "rags_to_riches" if _has_material_rags_growth(trajectory) else "stable"
    if pattern == (-1,):
        return "riches_to_rags"
    if pattern and pattern[0] == 1 and pattern[-1] == -1:
        return "icarus"
    if pattern and pattern[0] == -1 and pattern[-1] == 1:
        return "man_in_a_hole"
    if pattern and pattern[0] == 1 and pattern[-1] == 1 and len(pattern) >= 3:
        return "cinderella"
    if pattern and pattern[0] == -1 and pattern[-1] == -1 and len(pattern) >= 3:
        return "oedipus"
    material_thirds = _classify_series_by_thirds(smoothed)
    return material_thirds if material_thirds != "rags_to_riches" or _has_material_rags_growth(trajectory) else "stable"


def _classify_rags_candidate(trajectory: dict) -> str:
    material_arc = _classify_material_arc_when_prestige_masks_growth(trajectory)
    if material_arc not in ("stable", "rags_to_riches"):
        return material_arc
    if _has_material_rags_growth(trajectory):
        return "rags_to_riches"
    return "stable"


def classify_civ_arc(trajectory: dict) -> str:
    """Oracle 6: Classify a civ trajectory into one of six emotional arc families."""
    series = _trajectory_composite_series(
        trajectory,
        metrics=("population", "territory", "prestige"),
    )
    n = len(series)
    if n == 0:
        return "stable"

    window = max(10, n // 10)
    smoothed = _smoothed_series(series, window)
    mean_value = _mean(smoothed)
    series_range = max(smoothed) - min(smoothed)
    if mean_value == 0.0:
        if series_range == 0.0:
            return "stable"
    elif series_range / abs(mean_value) <= 0.20:
        return "stable"

    pattern = _significant_slope_pattern(smoothed)
    if pattern == (1,):
        return _classify_rags_candidate(trajectory)
    if pattern == (-1,):
        return "riches_to_rags"
    if pattern and pattern[0] == 1 and pattern[-1] == 1 and len(pattern) >= 3:
        return "cinderella"
    if pattern and pattern[0] == -1 and pattern[-1] == -1 and len(pattern) >= 3:
        return "oedipus"
    if pattern and pattern[0] == 1 and pattern[-1] == -1:
        # A short early surge can produce a local up-then-down derivative even
        # when the civ spends most of its life in terminal decline. For extinct
        # civs, let the broader thirds summary win when it clearly reads as a
        # riches-to-rags trajectory instead of a simple Icarus arc.
        final_population = float(trajectory.get("population", [0])[-1] or 0.0)
        if final_population <= 0.0 and _classify_series_by_thirds(series) == "riches_to_rags":
            return "riches_to_rags"
        # On long-horizon runs, a civ can peak modestly, die out, and then sit
        # extinct for hundreds of turns. The derivative pattern still reads
        # up-then-down, but this behaves more like a terminal decline than an
        # archetypal Icarus boom-and-bust.
        if final_population <= 0.0 and n >= 400:
            pop_series = [float(x or 0.0) for x in trajectory.get("population", [])]
            if pop_series:
                start_population = max(pop_series[0], 1.0)
                peak_population = max(pop_series)
                if (peak_population / start_population) < 2.5:
                    return "riches_to_rags"
        return "icarus"
    if pattern and pattern[0] == -1 and pattern[-1] == 1:
        return "man_in_a_hole"

    start_value = smoothed[0]
    end_value = smoothed[-1]
    if end_value > start_value * 1.10:
        return _classify_rags_candidate(trajectory)
    if end_value < start_value * 0.90:
        return "riches_to_rags"
    return "stable"


def detect_collapse_episodes(
    series: list[float],
    *,
    drop_fraction: float = ERA_COLLAPSE_DROP_FRACTION,
    smoothing_window: int = ERA_COLLAPSE_SMOOTHING_WINDOW,
) -> list[tuple[int, int, float, float]]:
    """Population collapses: falls of ``drop_fraction`` or more from a peak.

    The series is smoothed with the inflection detector's trailing rolling
    mean, so one-turn swings of small populations are not collapses. A running
    peak is tracked; a collapse opens when the smoothed value falls to
    ``(1 - drop_fraction) x peak`` and follows the trough until the series
    regains the peak or rebounds from the trough by the same ratio (to
    ``trough / (1 - drop_fraction)``). The next peak is tracked from there, so
    every collapse of a run is found, not only the one below the global peak.

    Returns ``(peak_index, trough_index, peak_value, trough_value)`` per
    collapse, in smoothed units.
    """
    if len(series) < 2:
        return []
    keep = 1.0 - drop_fraction
    smoothed = _smoothed_series([float(value) for value in series], max(1, smoothing_window))
    episodes: list[tuple[int, int, float, float]] = []
    peak_value, peak_index = smoothed[0], 0
    trough_value = trough_index = None
    for index in range(1, len(smoothed)):
        value = smoothed[index]
        if trough_index is None:
            if value >= peak_value:  # the last turn at the peak: where the fall begins
                peak_value, peak_index = value, index
            elif peak_value > 0 and value <= keep * peak_value:
                trough_value, trough_index = value, index
            continue
        if value < trough_value:
            trough_value, trough_index = value, index
        elif value >= peak_value or (value > trough_value and value * keep >= trough_value):
            episodes.append((peak_index, trough_index, peak_value, trough_value))
            trough_value = trough_index = None
            peak_value, peak_index = value, index
    if trough_index is not None:
        episodes.append((peak_index, trough_index, peak_value, trough_value))
    return episodes


def run_era_oracle(seed_runs: list[dict]) -> dict:
    """Oracle 3: era inflections, and no silent collapses.

    A seed needs at least two (collapsed) inflection points across its civs'
    era signals. A *silent collapse* is a population collapse of one civ
    (``detect_collapse_episodes``) that nothing marks between five turns
    before its peak and five after its trough: no inflection point in that
    civ's own era signals (population, treasury, stability, territory,
    prestige) and no recorded crisis naming it (``ERA_CRISIS_EVENT_TYPES``).
    The oracle passes when at least 80% of seeds have inflections and at most
    10% of seeds have a silent collapse.

    Recalibrated 2026-10 (docs/integration/wave3-defaults.md). The old check
    took each civ's global peak and the lowest point after it and accepted an
    inflection of *any* civ's signal anywhere in that window, which could span
    centuries; three quarters of those inflections were treasury jumps. It
    therefore depended on other civs' finances, missed every collapse but one
    per civ, and could not tell a collapse that the chronicle records from
    one it does not.
    """
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    analyzed_seeds = 0
    seeds_with_inflections = 0
    silent_collapse_seeds = 0
    collapse_episode_count = 0
    era_signal_marked = 0
    crisis_only_marked = 0
    per_seed: list[dict] = []
    silent_episodes: list[dict] = []

    for run in seed_runs:
        trajectories = run.get("civ_trajectories", [])
        if not trajectories:
            continue
        analyzed_seeds += 1
        crisis_turns = run.get("civ_crisis_event_turns") or {}
        inflection_turns: list[int] = []
        signal_hits: Counter[str] = Counter()
        seed_collapses = 0
        seed_silent: list[dict] = []
        for trajectory in trajectories:
            series_map = _trajectory_metric_series(trajectory)
            length = max((len(values) for values in series_map.values()), default=0)
            turns = list(trajectory.get("turn") or range(length))
            own_turns: set[int] = set()
            for signal_name, series in series_map.items():
                if len(series) < 10:
                    continue
                points = detect_inflection_points(series)
                signal_hits[signal_name] += len(points)
                own_turns.update(turns[point] for point in points if point < len(turns))
            inflection_turns.extend(own_turns)
            pop_series = series_map["population"]
            if len(pop_series) < 10:
                continue
            civ_name = trajectory.get("civ_name")
            civ_crises = crisis_turns.get(civ_name, []) if isinstance(civ_name, str) else []
            for peak, trough, peak_value, trough_value in detect_collapse_episodes(pop_series):
                if trough >= len(turns):
                    continue
                low = turns[peak] - ERA_SIGNAL_SLACK_TURNS
                high = turns[trough] + ERA_SIGNAL_SLACK_TURNS
                seed_collapses += 1
                if any(low <= turn <= high for turn in own_turns):
                    era_signal_marked += 1
                elif any(low <= turn <= high for turn in civ_crises):
                    crisis_only_marked += 1
                else:
                    seed_silent.append({
                        "seed": run.get("seed"),
                        "civ": civ_name,
                        "peak_turn": turns[peak],
                        "trough_turn": turns[trough],
                        "peak_population": round(peak_value, 1),
                        "trough_population": round(trough_value, 1),
                    })
        collapsed = _collapse_nearby_points(inflection_turns, radius=5)
        collapse_episode_count += seed_collapses
        if len(collapsed) >= 2:
            seeds_with_inflections += 1
        if seed_silent:
            silent_collapse_seeds += 1
            silent_episodes.extend(seed_silent)
        per_seed.append({
            "seed": run.get("seed"),
            "inflection_count": len(collapsed),
            "inflection_turns": collapsed,
            "silent_collapse": bool(seed_silent),
            "collapse_count": seed_collapses,
            "silent_collapse_count": len(seed_silent),
            "signal_hits": dict(signal_hits),
        })

    if analyzed_seeds == 0:
        return {"status": "SKIP", "reason": "no_history_series"}

    required = required_seed_count(analyzed_seeds, ERA_INFLECTION_SEED_FRACTION_MIN)
    max_silent = analyzed_seeds * ERA_SILENT_COLLAPSE_SEED_FRACTION_MAX
    return {
        "status": "PASS" if seeds_with_inflections >= required and silent_collapse_seeds <= max_silent else "FAIL",
        "analyzed_seeds": analyzed_seeds,
        "required_seed_count": required,
        "seeds_with_inflections": seeds_with_inflections,
        "silent_collapse_seeds": silent_collapse_seeds,
        "collapse_episode_count": collapse_episode_count,
        "collapses_marked_by_era_signal": era_signal_marked,
        "collapses_marked_by_crisis_only": crisis_only_marked,
        "silent_collapse_episodes": silent_episodes,
        "per_seed": per_seed,
    }


def run_arc_oracle(seed_runs: list[dict]) -> dict:
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    arc_counts: dict[str, int] = {}
    arc_families: set[str] = set()
    per_seed: list[dict] = []
    seeds_with_three_types = 0

    for run in seed_runs:
        seed_arcs: list[str] = []
        for trajectory in run.get("civ_trajectories", []):
            population = trajectory.get("population", [])
            if len(population) < 10:
                continue
            arc = classify_civ_arc(trajectory)
            seed_arcs.append(arc)
            arc_counts[arc] = arc_counts.get(arc, 0) + 1
            if arc != "stable":
                arc_families.add(arc)
        distinct_types = len(set(seed_arcs))
        if distinct_types >= 3:
            seeds_with_three_types += 1
        per_seed.append({
            "seed": run.get("seed"),
            "arc_types": seed_arcs,
            "distinct_type_count": distinct_types,
        })

    total_civs = sum(arc_counts.values())
    if total_civs == 0:
        return {"status": "SKIP", "reason": "no_civ_trajectories"}

    dominance_violations = {
        arc: count / total_civs
        for arc, count in arc_counts.items()
        if count / total_civs > 0.40
    }
    families_ok = len(arc_families) >= 5
    dominance_ok = not dominance_violations
    diversity_ok = seeds_with_three_types >= required_seed_count(len(per_seed), 0.50)

    return {
        "status": "PASS" if families_ok and dominance_ok and diversity_ok else "FAIL",
        "families_found": sorted(arc_families),
        "family_count": len(arc_families),
        "arc_counts": dict(sorted(arc_counts.items())),
        "dominance_violations": dominance_violations,
        "seeds_with_three_types": seeds_with_three_types,
        "per_seed": per_seed,
    }
