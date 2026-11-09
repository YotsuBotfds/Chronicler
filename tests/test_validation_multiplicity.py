"""chronicler.validation_multiplicity: Holm adjustment of the needs-pairing family
(report only), and the best_of guard: no gate path uses the selection-biased
method 1 scorer.

Reads files only (no child process, network or native import).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from chronicler import validate, validation_gate, validation_io
from chronicler.validation_multiplicity import (
    NEEDS_FAMILY, holm_adjust, main, needs_pairing_family, report_needs_family,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDENS = ROOT / "tests" / "fixtures" / "validation_parity" / "goldens.json"


def test_holm_adjust_known_values():
    # Sorted 0.01, 0.02, 0.03, 0.04, 0.05 -> 5p, 4p, 3p, 2p, 1p = .05, .08, .09, .08, .05,
    # then the running max: .05, .08, .09, .09, .09.
    assert holm_adjust([0.01, 0.04, 0.03, 0.02, 0.05]) == pytest.approx([0.05, 0.09, 0.09, 0.08, 0.09])
    assert holm_adjust([0.5, 0.001]) == pytest.approx([0.5, 0.002])
    assert holm_adjust([]) == []
    assert holm_adjust([0.3]) == [0.3]


def test_holm_adjust_is_monotone_capped_and_not_below_raw():
    raw = [0.2, 0.001, 0.9, 0.04, 0.04, 0.6, 0.011]
    adjusted = holm_adjust(raw)
    assert all(a >= p for a, p in zip(adjusted, raw))
    assert max(adjusted) <= 1.0 and holm_adjust([0.4, 0.5, 0.6]) == [1.0, 1.0, 1.0]
    ranked = sorted(range(len(raw)), key=lambda i: (raw[i], i))
    assert [adjusted[i] for i in ranked] == sorted(adjusted)
    # Equal raw values get equal adjusted values.
    assert adjusted[3] == adjusted[4]


@pytest.mark.parametrize("bad", ([-0.1], [1.5], [float("nan")]))
def test_holm_adjust_rejects_values_outside_unit_interval(bad):
    with pytest.raises(ValueError):
        holm_adjust(bad)


def test_family_is_the_five_decisive_pairings():
    assert NEEDS_FAMILY == ("autonomy", "social", "purpose", "material", "safety")
    assert NEEDS_FAMILY == tuple(need for need, _event in validation_io.NEEDS_PAIRINGS)
    assert "spiritual" not in NEEDS_FAMILY


def test_needs_pairing_family_counts_seeds_and_adjusts():
    per_seed = [{"by_pairing": {"material": [12, 8, 2], "social": [3, 1, 2]}} for _ in range(6)]
    per_seed.append({"by_pairing": {"material": [4, 2, 2]}})       # a tie does not count
    per_seed.append({"by_pairing": {}})
    family = needs_pairing_family({"status": "PASS", "per_seed": per_seed})
    assert list(family) == list(NEEDS_FAMILY)
    material = family["material"]
    assert (material["seeds_concordant"], material["seeds_discordant"]) == (6, 0)
    assert material["sign_test_p"] == pytest.approx(1 / 64)
    assert family["social"]["sign_test_p"] == 1.0 and family["social"]["seeds_discordant"] == 6
    assert family["autonomy"]["sign_test_p"] == 1.0
    assert material["holm_p"] == pytest.approx(5 / 64)
    assert all(family[n]["holm_p"] >= family[n]["sign_test_p"] for n in NEEDS_FAMILY)
    assert needs_pairing_family({"status": "SKIP", "reason": "no_bundles"}) is None


def test_reporting_leaves_the_oracle_result_unchanged():
    goldens = json.loads(GOLDENS.read_text(encoding="utf-8"))["run_oracles"]
    report = goldens["rich_all"]
    before = json.dumps(report, sort_keys=True)
    table = report_needs_family(report)
    assert json.dumps(report, sort_keys=True) == before
    assert table["status"] == report["results"]["needs"]["status"]
    assert table["method_version"] == report["results"]["needs"]["method_version"]
    assert set(table["pairings"]) == set(NEEDS_FAMILY)
    assert "holm_p" not in json.dumps(goldens)
    skipped = report_needs_family(goldens["determinism_all"])
    assert skipped["pairings"] is None
    assert report_needs_family({"results": {}})["status"] is None


def test_cli_prints_the_family(tmp_path, capsys):
    report = json.loads(GOLDENS.read_text(encoding="utf-8"))["run_oracles"]["rich_all"]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert main([str(path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["family"] == list(NEEDS_FAMILY) and set(printed["pairings"]) == set(NEEDS_FAMILY)


# --- best_of: re-scoring only, never a gate ---------------------------------

def test_best_of_is_documented_as_selection_biased():
    doc = validation_io.run_needs_oracle_best_of.__doc__
    assert "Selection-biased: re-scoring only; never a gate." in doc


@pytest.mark.parametrize("path", ("src/chronicler/validation_gate.py", "scripts/m53b_run_validation.py"))
def test_gate_sources_do_not_mention_best_of(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "best_of" not in text
    names = {node.id for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Attribute)}
    assert not any("best_of" in name for name in names)


def test_gate_registries_do_not_dispatch_best_of():
    assert validation_io.run_needs_oracle_best_of not in validate.ORACLE_RUNNERS.values()
    assert validate.ORACLE_RUNNERS["needs"] is not validation_io.run_needs_oracle_best_of
    assert not any("best_of" in name for name in vars(validation_gate))
