# M28: Oracle Gate — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-time 200-seed validation that hybrid mode produces statistically compatible distributions to aggregate mode.

**Architecture:** Standalone `scripts/run_oracle_gate.py` orchestrates parallel subprocess runs of the simulation in both aggregate and hybrid modes, then compares distributions using a `compare_distributions()` function extracted from `shadow_oracle.py`. A thin adapter reshapes bundle JSON into the columnar format the comparison expects.

**Tech Stack:** Python 3.12, scipy (ks_2samp, anderson_ksamp), numpy, subprocess, multiprocessing, json

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/chronicler/main.py` | Modify | Add `--agents` CLI flag, wire `AgentBridge` creation in `execute_run()` |
| `src/chronicler/shadow_oracle.py` | Modify | Extract `compare_distributions()` from `shadow_oracle_report()` |
| `scripts/run_oracle_gate.py` | Create | Batch orchestration, adapter, terminal report, JSON output |
| `tests/test_shadow_oracle.py` | Modify | Add tests for `compare_distributions()` |
| `tests/test_oracle_gate.py` | Create | Adapter + report formatting tests |

---

## Chunk 1: Prerequisites + Oracle Refactor

### Task 1: Add `--agents` CLI Flag

M27 wired the simulation internals (`world.agent_mode` checks in `run_turn`, `politics.py`) but no CLI flag exists to activate hybrid mode. The oracle gate script needs to invoke `python -m chronicler --simulate-only --seed N --agents hybrid`.

**Files:**
- Modify: `src/chronicler/main.py:555-608` (parser), `src/chronicler/main.py:184-216` (execute_run loop)
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing test for `--agents` flag**

```python
# tests/test_main.py — add to existing test class

def test_agents_flag_parsed():
    """--agents flag is parsed and stored on args."""
    from chronicler.main import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--simulate-only", "--agents", "hybrid"])
    assert args.agents == "hybrid"

def test_agents_flag_default_off():
    """--agents defaults to 'off'."""
    from chronicler.main import _build_parser
    parser = _build_parser()
    args = parser.parse_args([])
    assert args.agents == "off"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_main.py::test_agents_flag_parsed tests/test_main.py::test_agents_flag_default_off -v`
Expected: FAIL — unrecognized argument `--agents`

- [ ] **Step 3: Add `--agents` argument to parser**

In `_build_parser()` in `src/chronicler/main.py`, after the `--simulate-only` argument (line ~589):

```python
    parser.add_argument("--agents", type=str, default="off",
                        choices=["off", "demographics-only", "shadow", "hybrid"],
                        help="Agent mode: off (aggregate), demographics-only, shadow (compare), hybrid (agent-driven)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_main.py::test_agents_flag_parsed tests/test_main.py::test_agents_flag_default_off -v`
Expected: PASS

- [ ] **Step 5: Write failing test for hybrid mode wiring**

```python
def test_agents_hybrid_sets_agent_mode(tmp_path):
    """--agents=hybrid sets world.agent_mode and creates AgentBridge."""
    import subprocess, json
    result = subprocess.run(
        ["python", "-m", "chronicler", "--simulate-only", "--seed", "42",
         "--turns", "5", "--agents", "hybrid",
         "--output", str(tmp_path / "chronicle.md"),
         "--state", str(tmp_path / "state.json")],
        capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    bundle_path = tmp_path / "chronicle_bundle.json"
    assert bundle_path.exists()
    with open(bundle_path) as f:
        bundle = json.load(f)
    # Hybrid mode should produce a bundle with history
    assert len(bundle["history"]) == 5
```

- [ ] **Step 6: Wire `--agents` in `execute_run()`**

In `src/chronicler/main.py`, in the `execute_run()` function, after world setup (after line ~162 where tuning overrides are applied):

```python
    # M28: Agent mode wiring
    agent_mode = getattr(args, "agents", "off")
    agent_bridge = None
    if agent_mode in ("shadow", "hybrid"):
        world.agent_mode = agent_mode
        from chronicler.agent_bridge import AgentBridge
        agent_bridge = AgentBridge(world, mode=agent_mode)
```

Then in the turn loop (line ~211), pass `agent_bridge`:

```python
        chronicle_text = run_turn(
            world,
            action_selector=action_selector,
            narrator=_noop_narrator or engine.narrator,
            seed=seed + turn_num,
            agent_bridge=agent_bridge,
        )
```

And after the turn loop, close the bridge:

```python
    if agent_bridge is not None:
        agent_bridge.close()
```

- [ ] **Step 7: Run the integration test**

Run: `python -m pytest tests/test_main.py::test_agents_hybrid_sets_agent_mode -v`
Expected: PASS

- [ ] **Step 8: Verify aggregate mode is unaffected**

Run: `python -m pytest tests/test_main.py -v`
Expected: All existing tests still pass.

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat(m28): add --agents CLI flag with hybrid mode wiring"
```

---

### Task 2: Extract `compare_distributions()` from `shadow_oracle.py`

Per spec: extract the comparison loop into a reusable function that accepts a pre-loaded dict, so both the shadow IPC path and the oracle gate can share the same logic.

**Files:**
- Modify: `src/chronicler/shadow_oracle.py`
- Modify: `tests/test_shadow_oracle.py`

- [ ] **Step 1: Write failing test for `compare_distributions()`**

```python
# tests/test_shadow_oracle.py — add new test class

from chronicler.shadow_oracle import compare_distributions

class TestCompareDistributions:
    def test_matching_data_passes(self):
        """compare_distributions with matching synthetic data passes."""
        rng = np.random.default_rng(42)
        data = {"turn": [], "agent_population": [], "agg_population": [],
                "agent_military": [], "agg_military": [],
                "agent_economy": [], "agg_economy": [],
                "agent_culture": [], "agg_culture": [],
                "agent_stability": [], "agg_stability": []}
        for turn in [100, 250, 500]:
            for _ in range(200):
                data["turn"].append(turn)
                for metric in ["population", "military", "economy", "culture", "stability"]:
                    val = int(rng.normal(50, 5))
                    data[f"agent_{metric}"].append(max(0, val))
                    data[f"agg_{metric}"].append(max(0, int(rng.normal(50, 5))))
        report = compare_distributions(data)
        assert report.ks_pass_count >= 12
        assert report.correlation_passed

    def test_divergent_data_detects(self):
        """compare_distributions with divergent population detects failure."""
        rng = np.random.default_rng(42)
        data = {"turn": [], "agent_population": [], "agg_population": [],
                "agent_military": [], "agg_military": [],
                "agent_economy": [], "agg_economy": [],
                "agent_culture": [], "agg_culture": [],
                "agent_stability": [], "agg_stability": []}
        for turn in [100, 250, 500]:
            for _ in range(200):
                data["turn"].append(turn)
                data["agent_population"].append(max(0, int(rng.normal(80, 5))))
                data["agg_population"].append(max(0, int(rng.normal(50, 5))))
                for metric in ["military", "economy", "culture", "stability"]:
                    val = int(rng.normal(50, 5))
                    data[f"agent_{metric}"].append(max(0, val))
                    data[f"agg_{metric}"].append(max(0, int(rng.normal(50, 5))))
        report = compare_distributions(data)
        pop_results = [r for r in report.results
                       if hasattr(r, "metric") and r.metric == "population"]
        assert any(not r.passed for r in pop_results)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_shadow_oracle.py::TestCompareDistributions -v`
Expected: FAIL — cannot import `compare_distributions`

- [ ] **Step 3: Extract `compare_distributions()` from `shadow_oracle_report()`**

In `src/chronicler/shadow_oracle.py`, replace the existing `shadow_oracle_report()` function (lines 75-108) with these two functions. `compare_distributions()` goes first, then the slimmed-down `shadow_oracle_report()` wrapper:

```python
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
            ad_stat, _, ad_p = anderson_ksamp([agent_vals, agg_vals])
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
```

- [ ] **Step 4: Run ALL shadow oracle tests**

Run: `python -m pytest tests/test_shadow_oracle.py -v`
Expected: ALL pass — both new `TestCompareDistributions` tests and existing `TestOracleReport` tests (which now call `shadow_oracle_report()` → `compare_distributions()`).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/shadow_oracle.py tests/test_shadow_oracle.py
git commit -m "refactor(m28): extract compare_distributions() from shadow_oracle_report()"
```

---

## Chunk 2: Oracle Gate Script

### Task 3: Data Adapter

The adapter loads bundles from aggregate and hybrid batch directories, extracts civ stats at checkpoint turns, and produces the columnar dict that `compare_distributions()` expects.

**Files:**
- Create: `tests/test_oracle_gate.py`
- Create: `scripts/run_oracle_gate.py` (adapter function only in this task)

- [ ] **Step 1: Write failing test for adapter**

```python
# tests/test_oracle_gate.py

import json
import tempfile
from pathlib import Path
import pytest


def _make_bundle(seed_dir: Path, history: list[dict]) -> None:
    """Write a minimal chronicle_bundle.json."""
    seed_dir.mkdir(parents=True, exist_ok=True)
    bundle = {"history": history, "metadata": {"seed": 0}}
    with open(seed_dir / "chronicle_bundle.json", "w") as f:
        json.dump(bundle, f)


def _make_snapshot(turn: int, civs: dict[str, dict]) -> dict:
    """Create a TurnSnapshot-like dict."""
    return {"turn": turn, "civ_stats": civs}


class TestAdapter:
    def test_basic_extraction(self, tmp_path):
        """Adapter extracts matching civ stats at checkpoints."""
        from scripts.run_oracle_gate import load_comparison_data

        agg_dir = tmp_path / "aggregate"
        hyb_dir = tmp_path / "hybrid"

        civ_stats = {"Aram": {"population": 50, "military": 30, "economy": 25,
                              "culture": 20, "stability": 40}}
        history = [_make_snapshot(t, civ_stats) for t in range(501)]

        _make_bundle(agg_dir / "seed_0", history)
        _make_bundle(hyb_dir / "seed_0", history)

        data = load_comparison_data(agg_dir, hyb_dir, checkpoints=[100, 250, 500])
        assert len(data["turn"]) == 3  # 3 checkpoints x 1 civ x 1 seed
        assert data["agent_population"] == [50, 50, 50]
        assert data["agg_population"] == [50, 50, 50]

    def test_multiple_seeds_and_civs(self, tmp_path):
        """Adapter handles multiple seeds and multiple civs."""
        from scripts.run_oracle_gate import load_comparison_data

        agg_dir = tmp_path / "aggregate"
        hyb_dir = tmp_path / "hybrid"

        for seed in range(3):
            civs = {
                "Aram": {"population": 50 + seed, "military": 30, "economy": 25,
                         "culture": 20, "stability": 40},
                "Bora": {"population": 60 + seed, "military": 35, "economy": 28,
                         "culture": 22, "stability": 45},
            }
            history = [_make_snapshot(t, civs) for t in range(501)]
            _make_bundle(agg_dir / f"seed_{seed}", history)
            _make_bundle(hyb_dir / f"seed_{seed}", history)

        data = load_comparison_data(agg_dir, hyb_dir, checkpoints=[100, 250, 500])
        # 3 checkpoints x 2 civs x 3 seeds = 18
        assert len(data["turn"]) == 18

    def test_mismatched_civs_excluded(self, tmp_path):
        """Civs in one run but not the other are excluded."""
        from scripts.run_oracle_gate import load_comparison_data

        agg_dir = tmp_path / "aggregate"
        hyb_dir = tmp_path / "hybrid"

        agg_civs = {"Aram": {"population": 50, "military": 30, "economy": 25,
                             "culture": 20, "stability": 40}}
        hyb_civs = {
            "Aram": {"population": 55, "military": 32, "economy": 27,
                     "culture": 21, "stability": 42},
            "NewCiv": {"population": 10, "military": 5, "economy": 3,
                       "culture": 2, "stability": 15},
        }

        _make_bundle(agg_dir / "seed_0",
                     [_make_snapshot(t, agg_civs) for t in range(501)])
        _make_bundle(hyb_dir / "seed_0",
                     [_make_snapshot(t, hyb_civs) for t in range(501)])

        data = load_comparison_data(agg_dir, hyb_dir, checkpoints=[100, 250, 500])
        # Only Aram matches — 3 checkpoints x 1 civ x 1 seed
        assert len(data["turn"]) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_oracle_gate.py::TestAdapter -v`
Expected: FAIL — cannot import `load_comparison_data`

- [ ] **Step 3: Implement adapter in `scripts/run_oracle_gate.py`**

```python
#!/usr/bin/env python3
"""M28 Oracle Gate — 200-seed validation of hybrid vs aggregate mode."""
from __future__ import annotations

import json
from pathlib import Path

METRICS = ["population", "military", "economy", "culture", "stability"]


def load_comparison_data(
    agg_dir: Path,
    hyb_dir: Path,
    checkpoints: list[int] | None = None,
) -> dict[str, list]:
    """Load aggregate and hybrid bundles, extract civ stats at checkpoints.

    Returns columnar dict matching shadow_oracle's expected format:
    keys: turn, agent_{metric}, agg_{metric} for each metric.
    """
    if checkpoints is None:
        checkpoints = [100, 250, 500]

    columns: dict[str, list] = {"turn": []}
    for m in METRICS:
        columns[f"agent_{m}"] = []
        columns[f"agg_{m}"] = []

    agg_seeds = _find_seed_dirs(agg_dir)
    hyb_seeds = _find_seed_dirs(hyb_dir)
    common_seeds = sorted(set(agg_seeds) & set(hyb_seeds))

    for seed_name in common_seeds:
        agg_bundle = _load_bundle(agg_dir / seed_name)
        hyb_bundle = _load_bundle(hyb_dir / seed_name)
        if agg_bundle is None or hyb_bundle is None:
            continue

        agg_snaps = {s["turn"]: s for s in agg_bundle["history"]}
        hyb_snaps = {s["turn"]: s for s in hyb_bundle["history"]}

        for turn in checkpoints:
            agg_snap = agg_snaps.get(turn)
            hyb_snap = hyb_snaps.get(turn)
            if agg_snap is None or hyb_snap is None:
                continue

            common_civs = set(agg_snap["civ_stats"]) & set(hyb_snap["civ_stats"])
            for civ_name in sorted(common_civs):
                agg_stats = agg_snap["civ_stats"][civ_name]
                hyb_stats = hyb_snap["civ_stats"][civ_name]
                columns["turn"].append(turn)
                for m in METRICS:
                    columns[f"agent_{m}"].append(hyb_stats[m])
                    columns[f"agg_{m}"].append(agg_stats[m])

    return columns


def _find_seed_dirs(batch_dir: Path) -> list[str]:
    """Find seed_N directories in a batch directory."""
    if not batch_dir.exists():
        return []
    return [d.name for d in sorted(batch_dir.iterdir())
            if d.is_dir() and d.name.startswith("seed_")]


def _load_bundle(seed_dir: Path) -> dict | None:
    """Load chronicle_bundle.json from a seed directory."""
    bundle_path = seed_dir / "chronicle_bundle.json"
    if not bundle_path.exists():
        return None
    with open(bundle_path) as f:
        return json.load(f)
```

- [ ] **Step 4: Run adapter tests**

Run: `python -m pytest tests/test_oracle_gate.py::TestAdapter -v`
Expected: ALL pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_oracle_gate.py tests/test_oracle_gate.py
git commit -m "feat(m28): add oracle gate adapter — bundle JSON to comparison data"
```

---

### Task 4: Report Formatting

Terminal summary and JSON report generation.

**Files:**
- Modify: `scripts/run_oracle_gate.py`
- Modify: `tests/test_oracle_gate.py`

- [ ] **Step 1: Write failing test for terminal report**

```python
# tests/test_oracle_gate.py — add new test class

from chronicler.shadow_oracle import OracleResult, CorrelationResult, OracleReport


class TestReportFormatting:
    def _make_report(self) -> OracleReport:
        """Create a synthetic OracleReport for formatting tests."""
        results = []
        for metric in ["population", "military", "economy", "culture", "stability"]:
            for turn in [100, 250, 500]:
                passed = not (metric == "military" and turn == 500)
                results.append(OracleResult(
                    metric=metric, turn=turn,
                    ks_stat=0.04 if passed else 0.25,
                    ks_p=0.5 if passed else 0.001,
                    ad_p=0.6 if passed else 0.0005,
                    alpha=0.003,
                ))
        for m1, m2 in [("military", "economy"), ("culture", "stability")]:
            for turn in [100, 250, 500]:
                results.append(CorrelationResult(m1, m2, turn, delta=0.05))
        return OracleReport(results)

    def test_terminal_summary_contains_result(self):
        from scripts.run_oracle_gate import format_terminal_report
        report = self._make_report()
        text = format_terminal_report(report, seeds=200, turns=500,
                                      agg_dir="agg/", hyb_dir="hyb/",
                                      report_path="report.json")
        assert "14/15" in text
        assert "PASS" in text
        assert "FAIL" in text  # military at turn 500

    def test_terminal_summary_shows_ks_pvalue(self):
        from scripts.run_oracle_gate import format_terminal_report
        report = self._make_report()
        text = format_terminal_report(report, seeds=200, turns=500,
                                      agg_dir="agg/", hyb_dir="hyb/",
                                      report_path="report.json")
        assert "0.001" in text  # the failing KS p-value
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_oracle_gate.py::TestReportFormatting -v`
Expected: FAIL — cannot import `format_terminal_report`

- [ ] **Step 3: Implement `format_terminal_report()`**

Add to `scripts/run_oracle_gate.py`:

```python
from chronicler.shadow_oracle import OracleResult, CorrelationResult, OracleReport


def format_terminal_report(
    report: OracleReport,
    seeds: int,
    turns: int,
    agg_dir: str,
    hyb_dir: str,
    report_path: str,
) -> str:
    """Format oracle report as terminal-friendly text."""
    checkpoints = [100, 250, 500]
    lines = [
        "=== Oracle Gate Report ===",
        f"Seeds: {seeds}  Turns: {turns}  Checkpoints: {', '.join(str(c) for c in checkpoints)}",
        "",
        "--- Distribution Tests (KS + Anderson-Darling) ---",
    ]

    # Header
    cp_headers = "".join(f"Turn {c:<12}" for c in checkpoints)
    lines.append(f"{'':17}{cp_headers}")

    # Build lookup: (metric, turn) -> OracleResult
    dist_lookup: dict[tuple[str, int], OracleResult] = {}
    for r in report.results:
        if isinstance(r, OracleResult):
            dist_lookup[(r.metric, r.turn)] = r

    for metric in METRICS:
        cells = []
        for turn in checkpoints:
            r = dist_lookup.get((metric, turn))
            if r is None:
                cells.append(f"{'N/A':16}")
            elif r.passed:
                cells.append(f"PASS ({r.ks_p:.3f})   ")
            else:
                cells.append(f"FAIL ({r.ks_p:.3f})   ")
        lines.append(f"{metric:17}{''.join(cells)}")

    lines.append("")
    lines.append(f"Distribution: {report.ks_pass_count}/{report.ks_total} passed "
                 f"(threshold: 12/{report.ks_total})")

    # Correlation
    lines.append("")
    lines.append("--- Correlation Structure ---")
    lines.append(f"{'':17}{cp_headers}")

    corr_lookup: dict[tuple[str, str, int], CorrelationResult] = {}
    for r in report.results:
        if isinstance(r, CorrelationResult):
            corr_lookup[(r.metric1, r.metric2, r.turn)] = r

    for m1, m2 in [("military", "economy"), ("culture", "stability")]:
        cells = []
        for turn in checkpoints:
            r = corr_lookup.get((m1, m2, turn))
            if r is None:
                cells.append(f"{'N/A':16}")
            else:
                cells.append(f"{r.delta:<16.2f}")
        label = f"{m1[:3]}/{m2[:4]}"
        lines.append(f"{label:17}{''.join(cells)}")

    lines.append("")
    corr_status = "ALL PASSED" if report.correlation_passed else "FAILED"
    lines.append(f"Correlation: {corr_status} (threshold: delta < 0.15)")

    # Summary
    lines.append("")
    lines.append("--- Summary ---")
    overall = "PASS" if report.passed else "FAIL"
    lines.append(f"RESULT: {overall} ({report.ks_pass_count}/{report.ks_total} distribution, "
                 f"correlation {'OK' if report.correlation_passed else 'FAILED'})")
    lines.append("")
    lines.append(f"Aggregate dir: {agg_dir}")
    lines.append(f"Hybrid dir:    {hyb_dir}")
    lines.append(f"Report:        {report_path}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run formatting tests**

Run: `python -m pytest tests/test_oracle_gate.py::TestReportFormatting -v`
Expected: ALL pass.

- [ ] **Step 5: Write failing test for JSON report**

```python
# tests/test_oracle_gate.py — add to TestReportFormatting

    def test_build_json_report(self):
        from scripts.run_oracle_gate import build_json_report
        report = self._make_report()
        data = {"turn": [100] * 200}  # dummy comparison data for raw correlations
        for m in ["population", "military", "economy", "culture", "stability"]:
            data[f"agent_{m}"] = list(range(200))
            data[f"agg_{m}"] = list(range(200))
        result = build_json_report(report, data, seeds=200, turns=500,
                                   agg_dir="agg/", hyb_dir="hyb/")
        assert result["summary"]["distribution_passed"] == 14
        assert result["summary"]["overall"] == "PASS"
        assert len(result["distribution_tests"]) == 15
        assert len(result["correlation_tests"]) == 6
        # Correlation tests include raw values
        assert "agent_corr" in result["correlation_tests"][0]
        assert "agg_corr" in result["correlation_tests"][0]
```

- [ ] **Step 6: Implement `build_json_report()`**

Add to `scripts/run_oracle_gate.py`:

```python
import numpy as np
from datetime import datetime, timezone


def build_json_report(
    report: OracleReport,
    comparison_data: dict,
    seeds: int,
    turns: int,
    agg_dir: str,
    hyb_dir: str,
) -> dict:
    """Build JSON-serializable oracle report."""
    checkpoints = [100, 250, 500]

    dist_tests = []
    for r in report.results:
        if isinstance(r, OracleResult):
            dist_tests.append({
                "metric": r.metric,
                "turn": r.turn,
                "ks_stat": round(r.ks_stat, 6),
                "ks_p": round(r.ks_p, 6),
                "ad_p": round(r.ad_p, 6),
                "alpha": round(r.alpha, 6),
                "passed": r.passed,
            })

    # Compute raw correlations for JSON (not stored in CorrelationResult)
    turns_arr = np.array(comparison_data["turn"])
    corr_tests = []
    for r in report.results:
        if isinstance(r, CorrelationResult):
            mask = turns_arr == r.turn
            agent_m1 = np.array(comparison_data[f"agent_{r.metric1}"])[mask]
            agent_m2 = np.array(comparison_data[f"agent_{r.metric2}"])[mask]
            agg_m1 = np.array(comparison_data[f"agg_{r.metric1}"])[mask]
            agg_m2 = np.array(comparison_data[f"agg_{r.metric2}"])[mask]
            agent_corr = float(np.corrcoef(agent_m1, agent_m2)[0, 1]) if len(agent_m1) >= 3 else 0.0
            agg_corr = float(np.corrcoef(agg_m1, agg_m2)[0, 1]) if len(agg_m1) >= 3 else 0.0
            corr_tests.append({
                "metric1": r.metric1,
                "metric2": r.metric2,
                "turn": r.turn,
                "agent_corr": round(agent_corr, 6),
                "agg_corr": round(agg_corr, 6),
                "delta": round(r.delta, 6),
                "passed": r.passed,
            })

    return {
        "metadata": {
            "seeds": seeds,
            "turns": turns,
            "checkpoints": checkpoints,
            "aggregate_dir": str(agg_dir),
            "hybrid_dir": str(hyb_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "distribution_tests": dist_tests,
        "correlation_tests": corr_tests,
        "summary": {
            "distribution_passed": report.ks_pass_count,
            "distribution_total": report.ks_total,
            "distribution_threshold": 12,
            "correlation_all_passed": report.correlation_passed,
            "overall": "PASS" if report.passed else "FAIL",
        },
    }
```

- [ ] **Step 7: Run all report tests**

Run: `python -m pytest tests/test_oracle_gate.py::TestReportFormatting -v`
Expected: ALL pass.

- [ ] **Step 8: Commit**

```bash
git add scripts/run_oracle_gate.py tests/test_oracle_gate.py
git commit -m "feat(m28): add terminal report and JSON report formatting"
```

---

### Task 5: Batch Orchestration + Main Entry Point

Wire the `__main__` block: parse CLI args, run aggregate/hybrid batches via subprocess, load comparison data, run comparison, print report, write JSON.

**Files:**
- Modify: `scripts/run_oracle_gate.py`

- [ ] **Step 1: Write failing test for batch runner**

```python
# tests/test_oracle_gate.py — add new test class

class TestBatchRunner:
    def test_run_single_seed_e2e(self, tmp_path):
        """End-to-end plumbing test: 1 seed, 10 turns.

        With 10 turns, no checkpoint turns (100/250/500) have data, so the
        comparison is vacuously empty. This validates the subprocess wiring,
        directory structure, and report generation — not statistical correctness.
        """
        import subprocess
        result = subprocess.run(
            ["python", "scripts/run_oracle_gate.py",
             "--seeds", "1", "--turns", "10", "--parallel", "1",
             "--output-dir", str(tmp_path / "gate")],
            capture_output=True, text=True, timeout=300,
        )
        assert result.returncode == 0, result.stderr
        report_path = tmp_path / "gate" / "oracle_report.json"
        assert report_path.exists()
        with open(report_path) as f:
            report = json.load(f)
        assert report["metadata"]["seeds"] == 1
```

- [ ] **Step 2: Implement batch orchestration**

Add to `scripts/run_oracle_gate.py`:

```python
import argparse
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed


def _run_seed(seed: int, turns: int, agents: str, output_dir: Path) -> tuple[int, bool]:
    """Run a single seed via subprocess. Returns (seed, success)."""
    seed_dir = output_dir / f"seed_{seed}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "chronicler",
        "--simulate-only",
        "--seed", str(seed),
        "--turns", str(turns),
        "--agents", agents,
        "--output", str(seed_dir / "chronicle.md"),
        "--state", str(seed_dir / "state.json"),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return (seed, proc.returncode == 0)
    except subprocess.TimeoutExpired:
        return (seed, False)


def run_batch(seeds: int, turns: int, agents: str, output_dir: Path,
              parallel: int) -> tuple[int, int]:
    """Run batch of seeds. Returns (completed, failed)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = 0
    failed = 0

    with ProcessPoolExecutor(max_workers=parallel) as executor:
        futures = {
            executor.submit(_run_seed, seed, turns, agents, output_dir): seed
            for seed in range(seeds)
        }
        for future in as_completed(futures):
            seed, success = future.result()
            if success:
                completed += 1
            else:
                failed += 1
                print(f"  WARNING: seed {seed} failed", file=sys.stderr)
            total = completed + failed
            if total % 20 == 0 or total == seeds:
                print(f"  Progress: {total}/{seeds} ({completed} ok, {failed} failed)")

    return completed, failed


def main():
    parser = argparse.ArgumentParser(description="M28 Oracle Gate — hybrid vs aggregate validation")
    parser.add_argument("--aggregate-dir", type=Path, default=None,
                        help="Pre-existing aggregate batch directory (skip aggregate run)")
    parser.add_argument("--output-dir", type=Path, default=Path("output/oracle_gate"),
                        help="Output directory (default: output/oracle_gate)")
    parser.add_argument("--parallel", type=int, default=28,
                        help="Parallel workers (default: 28)")
    parser.add_argument("--seeds", type=int, default=200,
                        help="Number of seeds (default: 200)")
    parser.add_argument("--turns", type=int, default=500,
                        help="Turns per seed (default: 500)")
    args = parser.parse_args()

    from chronicler.shadow_oracle import compare_distributions

    agg_dir = args.aggregate_dir or (args.output_dir / "aggregate")
    hyb_dir = args.output_dir / "hybrid"

    start = time.time()

    # Phase 1: Aggregate batch
    if args.aggregate_dir:
        print(f"Using pre-existing aggregate baseline: {args.aggregate_dir}")
    else:
        print(f"Running aggregate batch: {args.seeds} seeds x {args.turns} turns")
        agg_ok, agg_fail = run_batch(args.seeds, args.turns, "off", agg_dir, args.parallel)
        print(f"Aggregate batch complete: {agg_ok} ok, {agg_fail} failed")
        if agg_ok < int(args.seeds * 0.8):
            print(f"WARNING: Only {agg_ok}/{args.seeds} aggregate seeds completed (<80%). "
                  "Results may not be statistically representative.")

    # Phase 2: Hybrid batch
    print(f"Running hybrid batch: {args.seeds} seeds x {args.turns} turns")
    hyb_ok, hyb_fail = run_batch(args.seeds, args.turns, "hybrid", hyb_dir, args.parallel)
    print(f"Hybrid batch complete: {hyb_ok} ok, {hyb_fail} failed")
    if hyb_ok < int(args.seeds * 0.8):
        print(f"WARNING: Only {hyb_ok}/{args.seeds} hybrid seeds completed (<80%). "
              "Results may not be statistically representative.")

    elapsed = time.time() - start
    print(f"\nBatch execution: {elapsed:.0f}s")

    # Phase 3: Compare
    print("Loading comparison data...")
    comparison_data = load_comparison_data(agg_dir, hyb_dir)
    n_rows = len(comparison_data["turn"])
    print(f"Loaded {n_rows} data points from {hyb_ok} seed pairs")

    report = compare_distributions(comparison_data)

    # Report
    report_path = args.output_dir / "oracle_report.json"
    json_report = build_json_report(
        report, comparison_data,
        seeds=args.seeds, turns=args.turns,
        agg_dir=str(agg_dir), hyb_dir=str(hyb_dir),
    )
    with open(report_path, "w") as f:
        json.dump(json_report, f, indent=2)

    terminal_text = format_terminal_report(
        report, seeds=args.seeds, turns=args.turns,
        agg_dir=str(agg_dir), hyb_dir=str(hyb_dir),
        report_path=str(report_path),
    )
    print(f"\n{terminal_text}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run e2e test**

Run: `python -m pytest tests/test_oracle_gate.py::TestBatchRunner::test_run_single_seed_e2e -v --timeout=300`
Expected: PASS (may take ~30s for a single 10-turn seed pair).

Note: This test requires the Rust `chronicler-agents` crate to be built. If it fails because the crate isn't compiled, run `cd chronicler-agents && maturin develop --release` first.

- [ ] **Step 4: Run all oracle gate tests**

Run: `python -m pytest tests/test_oracle_gate.py -v --timeout=300`
Expected: ALL pass.

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `python -m pytest tests/ -v --timeout=300`
Expected: ALL pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_oracle_gate.py tests/test_oracle_gate.py
git commit -m "feat(m28): add batch orchestration and main entry point"
```
