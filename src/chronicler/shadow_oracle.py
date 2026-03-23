"""Shadow oracle: KS + Anderson-Darling comparison of agent vs aggregate distributions."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pyarrow.ipc as ipc
from scipy import stats
from scipy.stats import ks_2samp, anderson_ksamp


@dataclass
class OracleResult:
    metric: str
    turn: int
    ks_stat: float
    ks_p: float
    ad_p: float
    alpha: float

    @property
    def passed(self) -> bool:
        return self.ks_p > self.alpha and self.ad_p > self.alpha


@dataclass
class CorrelationResult:
    metric1: str
    metric2: str
    turn: int
    delta: float

    @property
    def passed(self) -> bool:
        return self.delta < 0.15


@dataclass
class OracleReport:
    results: list[OracleResult | CorrelationResult]

    @property
    def ks_pass_count(self) -> int:
        return sum(1 for r in self.results if isinstance(r, OracleResult) and r.passed)

    @property
    def ks_total(self) -> int:
        return sum(1 for r in self.results if isinstance(r, OracleResult))

    @property
    def correlation_passed(self) -> bool:
        return all(r.passed for r in self.results if isinstance(r, CorrelationResult))

    @property
    def passed(self) -> bool:
        return self.ks_pass_count >= 12 and self.correlation_passed


def load_shadow_data(paths: list[Path]) -> dict:
    columns: dict[str, list] = {}
    for path in paths:
        reader = ipc.open_file(str(path))
        for i in range(reader.num_record_batches):
            batch = reader.get_batch(i)
            for col_name in batch.schema.names:
                columns.setdefault(col_name, []).extend(batch.column(col_name).to_pylist())
    return columns


def extract_at_turn(data: dict, column: str, turn: int) -> np.ndarray:
    turns = np.array(data["turn"])
    values = np.array(data[column])
    mask = turns == turn
    return values[mask]


def _anderson_pvalue(samples: list[np.ndarray]) -> tuple[float, float]:
    """Run Anderson-Darling with the modern SciPy API when available."""
    try:
        result = anderson_ksamp(
            samples,
            variant="midrank",
            method=stats.PermutationMethod(n_resamples=999, rng=0),
        )
        return float(result.statistic), float(result.pvalue)
    except TypeError:
        result = anderson_ksamp(samples)
        pvalue = getattr(result, "pvalue", result.significance_level)
        return float(result.statistic), float(pvalue)


def compare_distributions(data: dict) -> OracleReport:
    """Compare agent vs aggregate distributions from pre-loaded columnar data.

    data: dict with keys 'turn', 'agent_{metric}', 'agg_{metric}' for each of
    population, military, economy, culture, stability.
    """
    checkpoints = [100, 250, 500]
    metrics = ["population", "military", "economy", "culture", "stability"]
    bonferroni_alpha = 0.05 / (len(metrics) * len(checkpoints))

    results: list[OracleResult | CorrelationResult] = []

    for metric in metrics:
        for turn in checkpoints:
            agent_vals = extract_at_turn(data, f"agent_{metric}", turn)
            agg_vals = extract_at_turn(data, f"agg_{metric}", turn)
            if len(agent_vals) < 2 or len(agg_vals) < 2:
                continue
            ks_stat, ks_p = ks_2samp(agent_vals, agg_vals)
            ad_stat, ad_p = _anderson_pvalue([agent_vals, agg_vals])
            results.append(OracleResult(metric, turn, ks_stat, ks_p, ad_p, bonferroni_alpha))

    correlation_checks = [("military", "economy"), ("culture", "stability")]
    for m1, m2 in correlation_checks:
        for turn in checkpoints:
            agent_m1 = extract_at_turn(data, f"agent_{m1}", turn)
            agent_m2 = extract_at_turn(data, f"agent_{m2}", turn)
            agg_m1 = extract_at_turn(data, f"agg_{m1}", turn)
            agg_m2 = extract_at_turn(data, f"agg_{m2}", turn)
            if len(agent_m1) < 3 or len(agg_m1) < 3:
                continue
            corr_delta = abs(
                np.corrcoef(agent_m1, agent_m2)[0, 1]
                - np.corrcoef(agg_m1, agg_m2)[0, 1]
            )
            results.append(CorrelationResult(m1, m2, turn, corr_delta))

    return OracleReport(results)


def shadow_oracle_report(shadow_ipc_paths: list[Path]) -> OracleReport:
    """Compare agent vs aggregate distributions from Arrow IPC shadow logs."""
    all_data = load_shadow_data(shadow_ipc_paths)
    return compare_distributions(all_data)
