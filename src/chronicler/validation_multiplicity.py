"""Multiple-comparison adjustment for the needs oracle (report only).

The needs oracle (``validation_io.run_needs_oracle``) tests one hypothesis per
decisive pairing (``validation_io.NEEDS_PAIRINGS``: autonomy -> rebellion,
social, material and safety -> migration, purpose -> occupation switch) and
reports no correction for testing five. This module reports Holm-adjusted
p-values for that family beside the unadjusted ones. It never changes a
status: PASS stays the oracle's (``validation_gate``). Using the adjusted
values to decide would be a correction with its own
``NEEDS_ORACLE_METHOD_VERSION`` bump and rebaseline.

It reads a finished result or report and changes no oracle output, so the
validation reports and their pinned goldens stay byte-identical.

Usage::

    python -m chronicler.validation_multiplicity validate_report_full.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from .validation_io import NEEDS_PAIRINGS, _sign_test_p

NEEDS_FAMILY = tuple(need for need, _event in NEEDS_PAIRINGS)


def holm_adjust(pvalues: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values, in the input order.

    Sort ascending; the i-th smallest (0-based, of ``m``) becomes
    ``max over j <= i of min(1, (m - j) * p_(j))``: monotone in the sorted
    order and capped at 1. Ties keep their input order. Controls the
    family-wise error rate under any dependence between the tests.
    """
    values = [float(p) for p in pvalues]
    for p in values:
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"p-values must be in [0, 1]: {p!r}")
    m = len(values)
    order = sorted(range(m), key=lambda i: (values[i], i))
    adjusted = [0.0] * m
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * values[index]))
        adjusted[index] = running
    return adjusted


def needs_pairing_family(needs: Mapping) -> dict[str, dict] | None:
    """The needs oracle's pairing family of one result (one method version, its
    snapshots pooled), with a Holm-adjusted p-value per pairing; None when the
    result has no per-seed pairing counts (SKIP, error).

    Family: the five decisive pairings of ``NEEDS_PAIRINGS`` (the informational
    spiritual pairing is outside it, since it never decides). Each pairing's
    p-value is the exact one-sided sign test (``validation_io._sign_test_p``)
    over seeds: a seed is concordant when that pairing's matched pairs in it
    have more concordant than discordant pairs (``per_seed[*]["by_pairing"]``,
    ``[pairs, concordant, discordant]``), discordant when fewer, and does not
    count on a tie or without pairs. Seeds are the test's units, as they are
    the clusters of the oracle's pooled bound, because a seed's pairs share
    agents and overlapping windows. ``holm_p`` adjusts the five ``sign_test_p``
    values with ``holm_adjust``. The ablation methods (7, 8) carry method 6's
    observational ``per_seed``; the family is that component's.
    """
    per_seed = needs.get("per_seed")
    if not isinstance(per_seed, list) or not per_seed:
        return None
    rows = {}
    for need in NEEDS_FAMILY:
        concordant = discordant = 0
        for record in per_seed:
            counts = (record.get("by_pairing") or {}).get(need)
            if not counts:
                continue
            _pairs, c, d = counts
            concordant += c > d
            discordant += c < d
        rows[need] = {"seeds_concordant": concordant, "seeds_discordant": discordant,
                      "sign_test_p": _sign_test_p(concordant, discordant)}
    for need, holm in zip(NEEDS_FAMILY, holm_adjust([rows[n]["sign_test_p"] for n in NEEDS_FAMILY])):
        rows[need]["holm_p"] = holm
    return rows


def report_needs_family(report: Mapping) -> dict:
    """The family table of a validation report (``chronicler.validate`` output):
    ``{"status", "method_version", "family", "pairings"}``, ``pairings`` None when
    the report's needs oracle has no per-seed pairing counts."""
    needs = (report.get("results") or {}).get("needs")
    if not isinstance(needs, Mapping):
        return {"status": None, "method_version": None, "family": list(NEEDS_FAMILY), "pairings": None}
    return {"status": needs.get("status"), "method_version": needs.get("method_version"),
            "family": list(NEEDS_FAMILY), "pairings": needs_pairing_family(needs)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Holm-adjusted needs-pairing p-values of a validation report "
                                                 "(report only; never changes a status)")
    parser.add_argument("report", type=Path, help="a chronicler.validate JSON report")
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    print(json.dumps(report_needs_family(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
