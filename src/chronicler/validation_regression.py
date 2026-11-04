"""The regression summary: the balance oracle over agent satisfaction,
migration, rebellion and occupation rates, inequality, terminal population
and civilization survival, with its strict and calibrated floors.

Split out of ``validation_io`` verbatim; ``validation_io`` re-exports every
name here (docs/integration/validation-split.md).
"""
from __future__ import annotations

from collections import defaultdict

from .validation_common import EVENT_NAME_TO_CODE, _mean


# Full-gate balance uses strict historical thresholds plus explicitly reported
# calibrated tolerances for stochastic 500-turn batches.  The tolerance path is
# meant to distinguish near-threshold control-compatible drift from oracle errors
# without hiding the raw metric or whether the strict floor was missed.
REGRESSION_SATISFACTION_MEAN_MIN = 0.45
REGRESSION_SATISFACTION_MEAN_CALIBRATED_MIN = 0.40
REGRESSION_SATISFACTION_MEAN_MAX = 0.65
# Late-run satisfaction (``latest_satisfaction_mean``) pools the sampled turns
# of the last 60 turns before a run's last living sample, not that one sample.
# Seasons (a 12-turn year) and the climate cycle are functions of the turn, so
# every world's final sample falls on the same calendar point (autumn of a
# drought for both standard profiles); with the 10-turn sidecar cadence, 60
# turns visit every even turn of the year once, the run mean's seasonal mix.
# See docs/integration/wave3-defaults.md.
REGRESSION_LATEST_SATISFACTION_WINDOW_TURNS = 60
REGRESSION_MIGRATION_RATE_MIN = 0.05
REGRESSION_MIGRATION_RATE_CALIBRATED_MIN = 0.045
REGRESSION_MIGRATION_RATE_MAX = 0.15
REGRESSION_REBELLION_RATE_MIN = 0.02
REGRESSION_REBELLION_RATE_MAX = 0.08
REGRESSION_OCCUPATION_SHARE_MAX = 0.70
REGRESSION_OCCUPATION_VIOLATION_FRACTION_MAX = 0.01
REGRESSION_LATEST_OCCUPATION_VIOLATION_AGENT_FRACTION_MAX = 0.05
REGRESSION_OCCUPATION_EVIDENCE_RUN_MIN = 0.80


def _rounded_delta(value: float | None, target: float) -> float | None:
    return round(value - target, 6) if value is not None else None


def _floor_diagnostic(
    value: float | None,
    *,
    strict_min: float,
    calibrated_min: float,
    max_value: float,
    strict_ok: bool,
    calibrated_ok: bool,
) -> dict:
    return {
        "value": round(value, 6) if value is not None else None,
        "strict_min": strict_min,
        "calibrated_min": calibrated_min,
        "max": max_value,
        "strict_ok": strict_ok,
        "calibrated_ok": calibrated_ok,
        "strict_min_delta": _rounded_delta(value, strict_min),
        "calibrated_min_delta": _rounded_delta(value, calibrated_min),
        "max_delta": round(max_value - value, 6) if value is not None else None,
    }


def _agent_count_by_turn(validation_summary: dict | None) -> dict[int, int]:
    if not isinstance(validation_summary, dict):
        return {}
    counts: dict[int, int] = {}
    aggregates = validation_summary.get("agent_aggregates_by_turn", {})
    if not isinstance(aggregates, dict):
        return counts
    for turn_str, civ_aggs in aggregates.items():
        turn = _aggregate_turn_key(turn_str)
        if turn is None:
            continue
        if not isinstance(civ_aggs, dict) or any(
            not isinstance(civ_data, dict) or _population_count(civ_data.get("agent_count")) is None
            for civ_data in civ_aggs.values()
        ):
            continue
        counts[turn] = sum(civ_data["agent_count"] for civ_data in civ_aggs.values())
    return counts


def _final_ginis_from_validation_summary(validation_summary: dict | None) -> list[float]:
    if not isinstance(validation_summary, dict):
        return []
    agent_aggregates = validation_summary.get("agent_aggregates_by_turn", {})
    if not isinstance(agent_aggregates, dict):
        return []
    for turn in _aggregate_turns_descending(agent_aggregates):
        turn_aggregates = agent_aggregates.get(str(turn), {})
        if not isinstance(turn_aggregates, dict):
            continue
        ginis = [
            float(civ_data["gini"])
            for civ_data in turn_aggregates.values()
            if isinstance(civ_data, dict)
            and (_population_count(civ_data.get("agent_count")) or 0) > 0
            and civ_data.get("gini") is not None
        ]
        if ginis:
            return ginis
    return []


def _population_count(value: object) -> int | None:
    """Accept explicit, nonnegative integer counts, never floors or coercions."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _aggregate_turn_key(value: object) -> int | None:
    """Accept only canonical nonnegative JSON turn keys, without coercion."""
    if not isinstance(value, str):
        return None
    try:
        turn = int(value)
    except ValueError:
        return None
    return turn if turn >= 0 and str(turn) == value else None


def _aggregate_turns_descending(aggregates: dict) -> list[int]:
    turns = (_aggregate_turn_key(key) for key in aggregates)
    return sorted((turn for turn in turns if turn is not None), reverse=True)


def _final_living_population(run: dict) -> dict:
    """Read terminal population without mistaking territory or old samples for life.

    Hybrid region populations require an explicit matching world-state turn
    before they can establish terminal native-pool population. Other
    modes (including shadow and demographics-only) do not have that contract,
    so they require an explicit terminal native aggregate. An empty terminal
    aggregate is evidence of zero agents, not permission to rewind the sample.
    """
    bundle = run.get("bundle") or {}
    world = bundle.get("world_state", {})
    metadata = bundle.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    terminal_turn = _population_count(metadata.get("total_turns"))
    evidence = {
        "seed": run.get("seed", metadata.get("seed")),
        "population": None,
        "source": None,
        "turn": terminal_turn,
        "agent_mode": world.get("agent_mode") if isinstance(world, dict) else None,
        "reason": None,
    }
    if terminal_turn is None:
        evidence["reason"] = "missing_or_invalid_terminal_turn"
        return evidence
    if not isinstance(world, dict):
        evidence["reason"] = "invalid_world_state"
        return evidence
    if "turn" in world and _population_count(world["turn"]) != terminal_turn:
        evidence["reason"] = "world_state_turn_does_not_match_terminal_turn"
        return evidence

    if (
        world.get("agent_mode") == "hybrid"
        and _population_count(world.get("turn")) == terminal_turn
        and "regions" in world
    ):
        regions = world["regions"]
        if not isinstance(regions, list) or any(
            not isinstance(region, dict) or _population_count(region.get("population")) is None
            for region in regions
        ):
            evidence["reason"] = "invalid_final_region_population"
            return evidence
        evidence["population"] = sum(region["population"] for region in regions)
        evidence["source"] = "world_state.regions"
        return evidence

    summary = run.get("validation_summary")
    if summary is not None and not isinstance(summary, dict):
        evidence["reason"] = "invalid_validation_summary"
        return evidence
    aggregates = (summary or {}).get("agent_aggregates_by_turn", {})
    if not isinstance(aggregates, dict):
        evidence["reason"] = "invalid_terminal_agent_aggregate"
        return evidence
    if str(terminal_turn) not in aggregates:
        evidence["reason"] = "missing_terminal_agent_aggregate"
        return evidence
    terminal = aggregates[str(terminal_turn)]
    if not isinstance(terminal, dict):
        evidence["reason"] = "invalid_terminal_agent_aggregate"
        return evidence
    if any(
        not isinstance(civ_data, dict) or _population_count(civ_data.get("agent_count")) is None
        for civ_data in terminal.values()
    ):
        evidence["reason"] = "invalid_terminal_agent_count"
        return evidence
    evidence["population"] = sum(civ_data["agent_count"] for civ_data in terminal.values())
    evidence["source"] = "terminal_agent_aggregate"
    return evidence


def _late_satisfaction_window(agent_aggregates: dict, last_turn: int) -> tuple[float, float, int]:
    """Agent-weighted satisfaction sums over the late-run window ending at ``last_turn``.

    Returns ``(sum of mean x count, sum of (std^2 + mean^2) x count, count)``
    over every sampled turn in ``(last_turn - REGRESSION_LATEST_SATISFACTION_WINDOW_TURNS,
    last_turn]`` and every civ with living agents.
    """
    weighted = second_moment = 0.0
    weight = 0
    first = last_turn - REGRESSION_LATEST_SATISFACTION_WINDOW_TURNS
    for turn in _aggregate_turns_descending(agent_aggregates):
        if turn > last_turn:
            continue
        if turn <= first:
            break
        aggregates = agent_aggregates.get(str(turn), {})
        if not isinstance(aggregates, dict):
            continue
        for civ_data in aggregates.values():
            count = _population_count(civ_data.get("agent_count")) if isinstance(civ_data, dict) else None
            if count is None or count <= 0:
                continue
            mean = float(civ_data.get("satisfaction_mean", 0.0))
            std = float(civ_data.get("satisfaction_std", 0.0))
            weighted += mean * count
            second_moment += (std ** 2 + mean ** 2) * count
            weight += count
    return weighted, second_moment, weight


def run_regression_summary(seed_runs: list[dict]) -> dict:
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}
    has_agent_event_inputs = any(run.get("events") for run in seed_runs)
    has_aggregate_inputs = any(
        isinstance(run.get("validation_summary"), dict)
        and run["validation_summary"].get("agent_aggregates_by_turn")
        for run in seed_runs
    )
    if not has_agent_event_inputs and not has_aggregate_inputs:
        return {"status": "SKIP", "reason": "incomplete_agent_event_inputs"}

    satisfaction_weighted_sum = 0.0
    satisfaction_second_moment_sum = 0.0
    satisfaction_weight_total = 0
    latest_satisfaction_weighted_sum = 0.0
    latest_satisfaction_second_moment_sum = 0.0
    latest_satisfaction_weight_total = 0
    final_sample_satisfaction_weighted_sum = 0.0
    final_sample_satisfaction_weight_total = 0
    controlled_occupation_shares: list[float] = []
    fallback_occupation_shares: list[float] = []
    latest_controlled_occupation_shares: list[float] = []
    latest_fallback_occupation_shares: list[float] = []
    latest_occupation_violation_agent_count = 0.0
    latest_occupation_agent_total = 0.0
    current_occupation_schema_runs = 0
    controlled_occupation_evidence_runs = 0
    latest_current_occupation_schema_runs = 0
    latest_controlled_occupation_evidence_runs = 0
    latest_incomplete_controlled_occupation_runs = 0
    final_ginis: list[float] = []
    final_civ_survivals: list[int] = []
    living_population_evidence = [_final_living_population(run) for run in seed_runs]
    full_initial_survival_flags: list[bool] = []
    negative_treasury_runs = 0
    total_agent_turns = 0.0
    migration_events = 0
    rebellion_events = 0

    for run in seed_runs:
        validation_summary = run.get("validation_summary")
        validation_summary = validation_summary if isinstance(validation_summary, dict) else {}
        agent_aggregates = validation_summary.get("agent_aggregates_by_turn", {})
        if not isinstance(agent_aggregates, dict):
            agent_aggregates = {}
        run_final_ginis = _final_ginis_from_validation_summary(validation_summary)
        run_has_current_occupation_schema = False
        run_has_controlled_occupation_evidence = False
        run_latest_has_current_occupation_schema = False
        run_latest_has_controlled_occupation_evidence = False
        run_latest_has_incomplete_controlled_occupation = False
        if agent_aggregates:
            for turn_key, turn_aggregates in agent_aggregates.items():
                if _aggregate_turn_key(turn_key) is None or not isinstance(turn_aggregates, dict):
                    continue
                for civ_data in turn_aggregates.values():
                    count = _population_count(civ_data.get("agent_count")) if isinstance(civ_data, dict) else None
                    if count is None or count <= 0:
                        continue
                    satisfaction_mean = float(civ_data.get("satisfaction_mean", 0.0))
                    satisfaction_std = float(civ_data.get("satisfaction_std", 0.0))
                    satisfaction_weighted_sum += satisfaction_mean * count
                    satisfaction_second_moment_sum += (
                        satisfaction_std ** 2 + satisfaction_mean ** 2
                    ) * count
                    satisfaction_weight_total += count
                    controlled_count = int(civ_data.get("controlled_agent_count", 0))
                    controlled_counts = civ_data.get("controlled_occupation_counts", {})
                    all_occupation_counts = civ_data.get("occupation_counts", {})
                    has_controlled_schema = (
                        "controlled_agent_count" in civ_data
                        or "controlled_occupation_counts" in civ_data
                    )
                    if has_controlled_schema:
                        run_has_current_occupation_schema = True
                    if controlled_count >= 5 and controlled_counts:
                        counted_controlled = sum(int(occ_count) for occ_count in controlled_counts.values())
                    else:
                        counted_controlled = 0
                    if (
                        controlled_count >= 5
                        and controlled_counts
                        and counted_controlled == controlled_count
                    ):
                        run_has_controlled_occupation_evidence = True
                        for occ_count in controlled_counts.values():
                            controlled_occupation_shares.append(float(occ_count) / controlled_count)
                    elif not has_controlled_schema and count >= 5 and all_occupation_counts:
                        # Legacy summaries did not distinguish controlled from
                        # displaced agents.  Use all-agent occupation evidence only
                        # for that schema, not for current sidecars that explicitly
                        # report zero controlled population.
                        for occ_count in all_occupation_counts.values():
                            fallback_occupation_shares.append(float(occ_count) / count)

            for turn in _aggregate_turns_descending(agent_aggregates):
                latest_aggregates = agent_aggregates.get(str(turn), {})
                if not isinstance(latest_aggregates, dict) or not latest_aggregates:
                    continue
                turn_satisfaction_weighted_sum = 0.0
                turn_satisfaction_second_moment_sum = 0.0
                turn_satisfaction_weight_total = 0
                turn_latest_controlled_occupation_shares: list[float] = []
                turn_latest_fallback_occupation_shares: list[float] = []
                turn_latest_occupation_violation_agent_count = 0.0
                turn_latest_occupation_agent_total = 0.0
                turn_latest_has_current_occupation_schema = False
                turn_latest_has_controlled_occupation_evidence = False
                turn_latest_has_incomplete_controlled_occupation = False
                for civ_data in latest_aggregates.values():
                    count = _population_count(civ_data.get("agent_count")) if isinstance(civ_data, dict) else None
                    if count is None or count <= 0:
                        continue
                    satisfaction_mean = float(civ_data.get("satisfaction_mean", 0.0))
                    satisfaction_std = float(civ_data.get("satisfaction_std", 0.0))
                    turn_satisfaction_weighted_sum += satisfaction_mean * count
                    turn_satisfaction_second_moment_sum += (
                        satisfaction_std ** 2 + satisfaction_mean ** 2
                    ) * count
                    turn_satisfaction_weight_total += count

                    controlled_count = int(civ_data.get("controlled_agent_count", 0))
                    controlled_counts = civ_data.get("controlled_occupation_counts", {})
                    all_occupation_counts = civ_data.get("occupation_counts", {})
                    has_controlled_schema = (
                        "controlled_agent_count" in civ_data
                        or "controlled_occupation_counts" in civ_data
                    )
                    if has_controlled_schema:
                        turn_latest_has_current_occupation_schema = True
                    if controlled_count >= 5 and controlled_counts:
                        counted_controlled = sum(int(occ_count) for occ_count in controlled_counts.values())
                    else:
                        counted_controlled = 0
                    if has_controlled_schema and controlled_count >= 5:
                        if controlled_counts and counted_controlled == controlled_count:
                            turn_latest_has_controlled_occupation_evidence = True
                            turn_latest_occupation_agent_total += controlled_count
                            for occ_count in controlled_counts.values():
                                occ_count = int(occ_count)
                                share = float(occ_count) / controlled_count
                                turn_latest_controlled_occupation_shares.append(share)
                                if share <= 0.0 or share > REGRESSION_OCCUPATION_SHARE_MAX:
                                    turn_latest_occupation_violation_agent_count += occ_count
                        else:
                            turn_latest_has_incomplete_controlled_occupation = True
                    elif not has_controlled_schema and count >= 5 and all_occupation_counts:
                        turn_latest_occupation_agent_total += count
                        for occ_count in all_occupation_counts.values():
                            occ_count = int(occ_count)
                            share = float(occ_count) / count
                            turn_latest_fallback_occupation_shares.append(share)
                            if share <= 0.0 or share > REGRESSION_OCCUPATION_SHARE_MAX:
                                turn_latest_occupation_violation_agent_count += occ_count
                if turn_satisfaction_weight_total:
                    final_sample_satisfaction_weighted_sum += turn_satisfaction_weighted_sum
                    final_sample_satisfaction_weight_total += turn_satisfaction_weight_total
                    window_sums = _late_satisfaction_window(agent_aggregates, turn)
                    latest_satisfaction_weighted_sum += window_sums[0]
                    latest_satisfaction_second_moment_sum += window_sums[1]
                    latest_satisfaction_weight_total += window_sums[2]
                    if turn_latest_has_current_occupation_schema:
                        run_latest_has_current_occupation_schema = True
                    if turn_latest_has_controlled_occupation_evidence:
                        run_latest_has_controlled_occupation_evidence = True
                    if turn_latest_has_incomplete_controlled_occupation:
                        run_latest_has_incomplete_controlled_occupation = True
                    latest_controlled_occupation_shares.extend(turn_latest_controlled_occupation_shares)
                    latest_fallback_occupation_shares.extend(turn_latest_fallback_occupation_shares)
                    latest_occupation_violation_agent_count += turn_latest_occupation_violation_agent_count
                    latest_occupation_agent_total += turn_latest_occupation_agent_total
                    break

            sampled_counts = _agent_count_by_turn(validation_summary)
            if run_has_current_occupation_schema:
                current_occupation_schema_runs += 1
            if run_has_controlled_occupation_evidence:
                controlled_occupation_evidence_runs += 1
            if run_latest_has_current_occupation_schema:
                latest_current_occupation_schema_runs += 1
            if run_latest_has_controlled_occupation_evidence:
                latest_controlled_occupation_evidence_runs += 1
            if run_latest_has_incomplete_controlled_occupation:
                latest_incomplete_controlled_occupation_runs += 1
            if sampled_counts:
                avg_agents = _mean(list(sampled_counts.values()))
                metadata = run["bundle"].get("metadata")
                total_turns = (
                    _population_count(metadata.get("total_turns"))
                    if isinstance(metadata, dict) else None
                ) or 0
                total_agent_turns += avg_agents * total_turns

        history = run["bundle"].get("history", [])
        final_snapshot = history[-1] if history else {}
        first_snapshot = history[0] if history else {}
        civ_stats = final_snapshot.get("civ_stats", {})
        initial_civ_stats = first_snapshot.get("civ_stats", {})
        alive_civs = 0
        final_survivors: set[str] = set()
        initial_survivors: set[str] = {
            civ_name for civ_name, civ_data in initial_civ_stats.items()
            if civ_data.get("regions")
        }
        for civ_data in civ_stats.values():
            if civ_data.get("regions"):
                alive_civs += 1
        for civ_name, civ_data in civ_stats.items():
            if civ_data.get("regions"):
                final_survivors.add(civ_name)
        final_civ_survivals.append(alive_civs)
        if initial_survivors:
            full_initial_survival_flags.append(initial_survivors.issubset(final_survivors))
        if validation_summary and "agent_aggregates_by_turn" in validation_summary:
            final_ginis.extend(run_final_ginis)
        else:
            for civ_data in civ_stats.values():
                if civ_data.get("regions"):
                    final_ginis.append(float(civ_data.get("gini", 0.0)))

        treasury_streaks: dict[str, int] = defaultdict(int)
        max_treasury_streaks: dict[str, int] = defaultdict(int)
        for snapshot in run["bundle"].get("history", []):
            for civ_name, civ_data in snapshot.get("civ_stats", {}).items():
                if float(civ_data.get("treasury", 0.0)) < 0 and civ_data.get("regions"):
                    treasury_streaks[civ_name] += 1
                    max_treasury_streaks[civ_name] = max(
                        max_treasury_streaks[civ_name],
                        treasury_streaks[civ_name],
                    )
                else:
                    treasury_streaks[civ_name] = 0
        bad_survivors = sum(
            1
            for civ_name, streak in max_treasury_streaks.items()
            if civ_name in final_survivors and streak > 50
        )
        if final_survivors and (bad_survivors / len(final_survivors)) > 0.30:
            negative_treasury_runs += 1

        migration_events += sum(1 for event in run["events"] if event["event_type"] == EVENT_NAME_TO_CODE["migration"])
        rebellion_events += sum(1 for event in run["events"] if event["event_type"] == EVENT_NAME_TO_CODE["rebellion"])

    migration_rate = migration_events / total_agent_turns if total_agent_turns else 0.0
    rebellion_rate = rebellion_events / total_agent_turns if total_agent_turns else 0.0
    satisfaction_mean = (
        satisfaction_weighted_sum / satisfaction_weight_total
        if satisfaction_weight_total else None
    )
    satisfaction_std = None
    if satisfaction_weight_total and satisfaction_mean is not None:
        variance = satisfaction_second_moment_sum / satisfaction_weight_total - satisfaction_mean ** 2
        satisfaction_std = max(variance, 0.0) ** 0.5
    latest_satisfaction_mean = (
        latest_satisfaction_weighted_sum / latest_satisfaction_weight_total
        if latest_satisfaction_weight_total else None
    )
    final_sample_satisfaction_mean = (
        final_sample_satisfaction_weighted_sum / final_sample_satisfaction_weight_total
        if final_sample_satisfaction_weight_total else None
    )
    latest_satisfaction_std = None
    if latest_satisfaction_weight_total and latest_satisfaction_mean is not None:
        latest_variance = (
            latest_satisfaction_second_moment_sum / latest_satisfaction_weight_total
            - latest_satisfaction_mean ** 2
        )
        latest_satisfaction_std = max(latest_variance, 0.0) ** 0.5
    occupation_shares = controlled_occupation_shares or fallback_occupation_shares
    occupation_source = (
        "controlled" if controlled_occupation_shares
        else "legacy_fallback" if fallback_occupation_shares
        else "none"
    )
    occupation_violation_fraction = (
        sum(
            1
            for share in occupation_shares
            if share <= 0.0 or share > REGRESSION_OCCUPATION_SHARE_MAX
        ) / len(occupation_shares)
        if occupation_shares else 1.0
    )
    latest_occupation_shares = (
        latest_controlled_occupation_shares or latest_fallback_occupation_shares
    )
    latest_occupation_source = (
        "controlled" if latest_controlled_occupation_shares
        else "legacy_fallback" if latest_fallback_occupation_shares
        else "none"
    )
    latest_occupation_violation_fraction = (
        latest_occupation_violation_agent_count / latest_occupation_agent_total
        if latest_occupation_agent_total else 1.0
    )
    occupation_evidence_run_fraction = (
        controlled_occupation_evidence_runs / current_occupation_schema_runs
        if current_occupation_schema_runs else None
    )
    latest_occupation_evidence_run_fraction = (
        latest_controlled_occupation_evidence_runs / latest_current_occupation_schema_runs
        if latest_current_occupation_schema_runs else None
    )
    latest_occupation_incomplete_run_fraction = (
        latest_incomplete_controlled_occupation_runs / latest_current_occupation_schema_runs
        if latest_current_occupation_schema_runs else None
    )
    occupation_evidence_ok = (
        occupation_evidence_run_fraction is None
        or occupation_evidence_run_fraction >= REGRESSION_OCCUPATION_EVIDENCE_RUN_MIN
    )
    latest_occupation_evidence_ok = (
        latest_occupation_evidence_run_fraction is None
        or latest_occupation_evidence_run_fraction >= REGRESSION_OCCUPATION_EVIDENCE_RUN_MIN
    )
    latest_occupation_complete_ok = (
        latest_occupation_incomplete_run_fraction is None
        or latest_occupation_incomplete_run_fraction == 0.0
    )
    latest_occupation_ok = (
        bool(latest_occupation_shares)
        and latest_occupation_violation_fraction
        <= REGRESSION_LATEST_OCCUPATION_VIOLATION_AGENT_FRACTION_MAX
        and latest_occupation_evidence_ok
        and latest_occupation_complete_ok
    )
    occupation_ok = (
        bool(occupation_shares)
        and occupation_violation_fraction <= REGRESSION_OCCUPATION_VIOLATION_FRACTION_MAX
        and occupation_evidence_ok
        and latest_occupation_ok
    )
    satisfaction_mean_ok = (
        REGRESSION_SATISFACTION_MEAN_MIN
        <= satisfaction_mean
        <= REGRESSION_SATISFACTION_MEAN_MAX
        if satisfaction_mean is not None else False
    )
    latest_satisfaction_mean_ok = (
        REGRESSION_SATISFACTION_MEAN_MIN
        <= latest_satisfaction_mean
        <= REGRESSION_SATISFACTION_MEAN_MAX
        if latest_satisfaction_mean is not None else False
    )
    satisfaction_mean_calibrated_ok = (
        REGRESSION_SATISFACTION_MEAN_CALIBRATED_MIN
        <= satisfaction_mean
        <= REGRESSION_SATISFACTION_MEAN_MAX
        if satisfaction_mean is not None else False
    )
    latest_satisfaction_mean_calibrated_ok = (
        REGRESSION_SATISFACTION_MEAN_CALIBRATED_MIN
        <= latest_satisfaction_mean
        <= REGRESSION_SATISFACTION_MEAN_MAX
        if latest_satisfaction_mean is not None else False
    )
    satisfaction_std_ok = 0.10 <= satisfaction_std <= 0.25 if satisfaction_std is not None else False
    gini_ok = (
        sum(1 for g in final_ginis if 0.30 <= g <= 0.70) / len(final_ginis) >= 0.20
        if final_ginis else False
    )
    zero_survival_fraction = (
        sum(1 for count in final_civ_survivals if count == 0) / len(final_civ_survivals)
        if final_civ_survivals else 1.0
    )
    exact_four_region_fraction = (
        sum(1 for count in final_civ_survivals if count == 4) / len(final_civ_survivals)
        if final_civ_survivals else 1.0
    )
    full_survival_fraction = (
        sum(1 for survived in full_initial_survival_flags if survived) / len(full_initial_survival_flags)
        if full_initial_survival_flags else exact_four_region_fraction
    )
    civ_survival_ok = zero_survival_fraction == 0.0 and full_survival_fraction <= 0.20
    treasury_ok = negative_treasury_runs <= max(1, int(len(seed_runs) * 0.30))
    measured_populations = [
        evidence["population"] for evidence in living_population_evidence
        if evidence["population"] is not None
    ]
    extinct_world_count = sum(population == 0 for population in measured_populations)
    population_unknown_count = len(seed_runs) - len(measured_populations)
    # Preserve the existing no-total-extinction intent without a new tunable
    # survival-size floor. Unknown terminal evidence must not earn a pass.
    living_population_ok = extinct_world_count == 0 and population_unknown_count == 0

    rebellion_rate_ok = (
        REGRESSION_REBELLION_RATE_MIN <= rebellion_rate <= REGRESSION_REBELLION_RATE_MAX
        if total_agent_turns else False
    )
    migration_rate_ok = (
        REGRESSION_MIGRATION_RATE_MIN <= migration_rate <= REGRESSION_MIGRATION_RATE_MAX
        if total_agent_turns else False
    )
    migration_rate_calibrated_ok = (
        REGRESSION_MIGRATION_RATE_CALIBRATED_MIN <= migration_rate <= REGRESSION_MIGRATION_RATE_MAX
        if total_agent_turns else False
    )
    strict_overall_ok = (
        satisfaction_mean_ok
        and latest_satisfaction_mean_ok
        and satisfaction_std_ok
        and rebellion_rate_ok
        and migration_rate_ok
        and gini_ok
        and occupation_ok
        and civ_survival_ok
        and living_population_ok
        and treasury_ok
    )
    calibrated_floor_ok = (
        satisfaction_mean_calibrated_ok
        and latest_satisfaction_mean_calibrated_ok
        and satisfaction_std_ok
        and rebellion_rate_ok
        and migration_rate_calibrated_ok
        and gini_ok
        and occupation_ok
        and civ_survival_ok
        and living_population_ok
        and treasury_ok
    )
    strict_checks = [
        ("satisfaction_mean", satisfaction_mean_ok),
        ("latest_satisfaction_mean", latest_satisfaction_mean_ok),
        ("satisfaction_std", satisfaction_std_ok),
        ("rebellion_rate_per_agent_turn", rebellion_rate_ok),
        ("migration_rate_per_agent_turn", migration_rate_ok),
        ("gini_in_range_fraction", gini_ok),
        ("occupation", occupation_ok),
        ("civ_survival", civ_survival_ok),
        ("living_population", living_population_ok),
        ("treasury", treasury_ok),
    ]
    calibrated_checks = [
        ("satisfaction_mean", satisfaction_mean_calibrated_ok),
        ("latest_satisfaction_mean", latest_satisfaction_mean_calibrated_ok),
        ("satisfaction_std", satisfaction_std_ok),
        ("rebellion_rate_per_agent_turn", rebellion_rate_ok),
        ("migration_rate_per_agent_turn", migration_rate_calibrated_ok),
        ("gini_in_range_fraction", gini_ok),
        ("occupation", occupation_ok),
        ("civ_survival", civ_survival_ok),
        ("living_population", living_population_ok),
        ("treasury", treasury_ok),
    ]
    strict_regression_failed_checks = [name for name, ok in strict_checks if not ok]
    calibrated_floor_failed_checks = [name for name, ok in calibrated_checks if not ok]
    regression_floor_diagnostics = {
        "satisfaction_mean": _floor_diagnostic(
            satisfaction_mean,
            strict_min=REGRESSION_SATISFACTION_MEAN_MIN,
            calibrated_min=REGRESSION_SATISFACTION_MEAN_CALIBRATED_MIN,
            max_value=REGRESSION_SATISFACTION_MEAN_MAX,
            strict_ok=satisfaction_mean_ok,
            calibrated_ok=satisfaction_mean_calibrated_ok,
        ),
        "latest_satisfaction_mean": _floor_diagnostic(
            latest_satisfaction_mean,
            strict_min=REGRESSION_SATISFACTION_MEAN_MIN,
            calibrated_min=REGRESSION_SATISFACTION_MEAN_CALIBRATED_MIN,
            max_value=REGRESSION_SATISFACTION_MEAN_MAX,
            strict_ok=latest_satisfaction_mean_ok,
            calibrated_ok=latest_satisfaction_mean_calibrated_ok,
        ),
        "migration_rate_per_agent_turn": _floor_diagnostic(
            migration_rate,
            strict_min=REGRESSION_MIGRATION_RATE_MIN,
            calibrated_min=REGRESSION_MIGRATION_RATE_CALIBRATED_MIN,
            max_value=REGRESSION_MIGRATION_RATE_MAX,
            strict_ok=migration_rate_ok,
            calibrated_ok=migration_rate_calibrated_ok,
        ),
    }
    calibrated_floor_relaxed_checks = [
        name
        for name, diagnostic in regression_floor_diagnostics.items()
        if not diagnostic["strict_ok"] and diagnostic["calibrated_ok"]
    ]
    overall_ok = strict_overall_ok or calibrated_floor_ok
    regression_adjudication = (
        "strict"
        if strict_overall_ok else "calibrated_floor"
        if calibrated_floor_ok else "fail"
    )

    return {
        "status": "PASS" if overall_ok else "FAIL",
        "regression_adjudication": regression_adjudication,
        "strict_regression_ok": strict_overall_ok,
        "calibrated_floor_ok": calibrated_floor_ok,
        "strict_regression_failed_checks": strict_regression_failed_checks,
        "calibrated_floor_failed_checks": calibrated_floor_failed_checks,
        "calibrated_floor_relaxed_checks": calibrated_floor_relaxed_checks,
        "regression_floor_diagnostics": regression_floor_diagnostics,
        "satisfaction_mean": round(satisfaction_mean, 4) if satisfaction_mean is not None else None,
        "satisfaction_std": round(satisfaction_std, 4) if satisfaction_std is not None else None,
        "latest_satisfaction_mean": (
            round(latest_satisfaction_mean, 4)
            if latest_satisfaction_mean is not None else None
        ),
        "latest_satisfaction_std": (
            round(latest_satisfaction_std, 4)
            if latest_satisfaction_std is not None else None
        ),
        "latest_satisfaction_window_turns": REGRESSION_LATEST_SATISFACTION_WINDOW_TURNS,
        "final_sample_satisfaction_mean": (
            round(final_sample_satisfaction_mean, 4)
            if final_sample_satisfaction_mean is not None else None
        ),
        "latest_satisfaction_mean_ok": latest_satisfaction_mean_ok,
        "latest_satisfaction_mean_calibrated_ok": latest_satisfaction_mean_calibrated_ok,
        "satisfaction_mean_ok": satisfaction_mean_ok,
        "satisfaction_mean_calibrated_ok": satisfaction_mean_calibrated_ok,
        "migration_rate_per_agent_turn": round(migration_rate, 6),
        "migration_rate_ok": migration_rate_ok,
        "migration_rate_calibrated_ok": migration_rate_calibrated_ok,
        "rebellion_rate_per_agent_turn": round(rebellion_rate, 6),
        "gini_in_range_fraction": round(sum(1 for g in final_ginis if 0.30 <= g <= 0.70) / len(final_ginis), 4) if final_ginis else None,
        "occupation_ok": occupation_ok,
        "occupation_source": occupation_source,
        "occupation_violation_fraction": round(occupation_violation_fraction, 4),
        "occupation_evidence_run_fraction": (
            round(occupation_evidence_run_fraction, 4)
            if occupation_evidence_run_fraction is not None else None
        ),
        "latest_occupation_source": latest_occupation_source,
        "latest_occupation_violation_fraction": round(latest_occupation_violation_fraction, 4),
        "latest_occupation_evidence_run_fraction": (
            round(latest_occupation_evidence_run_fraction, 4)
            if latest_occupation_evidence_run_fraction is not None else None
        ),
        "latest_occupation_incomplete_run_fraction": (
            round(latest_occupation_incomplete_run_fraction, 4)
            if latest_occupation_incomplete_run_fraction is not None else None
        ),
        "latest_occupation_ok": latest_occupation_ok,
        "reason": (
            "terminal_population_extinction" if extinct_world_count else
            "missing_or_invalid_terminal_population_evidence" if population_unknown_count else None
        ),
        "living_population_ok": living_population_ok,
        "final_living_population_by_seed": living_population_evidence,
        "final_living_population_counts": [evidence["population"] for evidence in living_population_evidence],
        "extinct_world_count": extinct_world_count,
        "extinct_world_fraction": (
            round(extinct_world_count / len(measured_populations), 4)
            if measured_populations else None
        ),
        "population_unknown_run_count": population_unknown_count,
        "population_evidence_run_fraction": round(len(measured_populations) / len(seed_runs), 4),
        "civ_survival_counts": final_civ_survivals,
        "civ_zero_survival_fraction": round(zero_survival_fraction, 4) if final_civ_survivals else None,
        "civ_full_survival_fraction": round(full_survival_fraction, 4) if full_initial_survival_flags or final_civ_survivals else None,
        "civ_exact_four_region_fraction": round(exact_four_region_fraction, 4) if final_civ_survivals else None,
        "treasury_bad_seed_count": negative_treasury_runs,
    }
