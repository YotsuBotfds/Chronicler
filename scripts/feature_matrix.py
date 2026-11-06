"""The switch compatibility matrix, generated from ``chronicler.feature_catalog``.

    PYTHONPATH=src python scripts/feature_matrix.py [--json OUT.json] [--markdown OUT.md]

Catalog only (no runs; adapted from audit E's prototype). For every boolean
switch: its minimal accepted selection (prerequisites switched on, required
choices set) and the agent modes it allows. Then:

* **pairs**: every two switches with their minimal selections joined, valid or
  refused (with the catalog's reason) under the most detailed agent mode both
  allow; a pair is *expected* to be refused only when the two exclude each
  other or share no agent mode;
* **prerequisite drops**: each minimal selection with one prerequisite switch
  (and its choices) removed; the catalog must refuse every one;
* **all enabled**, per agent mode: the largest selection the catalog accepts
  (every switch the mode allows, required choices set, then the first switch in
  catalog order with an unmet requirement dropped until none is, as the
  viewer's ``normalizeSelection`` does), its flags and the catalog's verdict.

The run's own checks stay authoritative: ``tests/test_feature_matrix.py`` also
sends every all-enabled selection through ``main._configure_run``. Exit code 1
when a drop is accepted, a pair is refused unexpectedly, an all-enabled
selection is refused or an exclusion is one-sided.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from chronicler import feature_catalog as fc  # noqa: E402


def _entries() -> dict[str, dict]:
    return fc._by_key()


def bool_switches() -> list[str]:
    return [e["key"] for e in fc.feature_entries() if e["kind"] == "bool"]


def surfaces() -> dict[str, dict]:
    """The live surface of each agent mode with the default settings."""
    return {mode: fc.live_surface(argparse.Namespace(agents=mode)) for mode in fc.AGENT_MODES}


def exclusions(key: str) -> set[str]:
    return {c["not"]["feature"] for c in _entries()[key]["requires"] if "not" in c and "feature" in c["not"]}


def closure(key: str) -> tuple[dict, list[str]]:
    """The smallest selection the catalog accepts with ``key`` on, and the agent modes
    it allows (an ``any`` condition takes its first alternative; exclusions add
    nothing)."""
    entries = _entries()
    selection: dict = {key: True}
    modes = list(fc.AGENT_MODES)
    stack = [key]

    def walk(condition):
        nonlocal modes
        if "agents" in condition:
            modes = [m for m in modes if m in condition["agents"]]
        elif "feature" in condition:
            if condition["feature"] not in selection:
                selection[condition["feature"]] = True
                stack.append(condition["feature"])
        elif "choice" in condition:
            if entries[condition["choice"]]["choices"][0] not in condition["values"]:
                selection[condition["choice"]] = condition["values"][0]
        elif "any" in condition:
            walk(condition["any"][0])

    while stack:
        for condition in entries[stack.pop()]["requires"]:
            walk(condition)
    return selection, modes


def _detailed(modes) -> str | None:
    """The most detailed agent mode of a list (the CLI orders them by detail)."""
    return max(modes, key=fc.AGENT_MODES.index) if modes else None


def _without(selection: dict, dropped: str) -> dict:
    entries = _entries()
    return {k: v for k, v in selection.items() if k != dropped and entries[k]["parent"] != dropped}


def all_enabled(mode: str) -> dict:
    """The largest selection the catalog accepts under ``mode``: every switch whose
    minimal selection allows the mode, required choices set, then (as the viewer's
    normalizeSelection does) the first switch in catalog order with an unmet
    requirement dropped until none is left."""
    surface = surfaces()[mode]
    entries = _entries()
    selection: dict = {}
    for key in bool_switches():
        sel, modes = closure(key)
        if mode in modes:
            for k, v in sel.items():
                if entries[k]["kind"] == "choice":
                    selection.setdefault(k, v)
                else:
                    selection[k] = True
    while True:
        unmet = fc.unmet_requirements(selection, surface)       # catalog order: "'key' (--flag) reason"
        if not unmet:
            return selection
        key = unmet[0].split("'")[1]
        del selection[key]
        for child in [k for k in selection if entries[k]["parent"] == key]:
            del selection[child]


def matrix() -> dict:
    entries = _entries()
    surf = surfaces()
    bools = bool_switches()
    features, drops = {}, []
    for key in bools:
        sel, modes = closure(key)
        features[key] = {"closure": sel, "modes": modes,
                         "valid_by_mode": {m: fc.validate_features(sel, surf[m]) for m in fc.AGENT_MODES}}
        mode = _detailed(modes)
        for other in sel:
            if other != key and entries[other]["kind"] == "bool":
                refusal = fc.validate_features(_without(sel, other), surf[mode]) if mode else "no agent mode"
                drops.append({"feature": key, "dropped": other, "mode": mode, "refusal": refusal})
    pairs = []
    for a, b in itertools.combinations(bools, 2):
        sel = {**features[a]["closure"], **features[b]["closure"]}
        modes = [m for m in features[a]["modes"] if m in features[b]["modes"]]
        mode = _detailed(modes)
        refusal = fc.validate_features(sel, surf[mode]) if mode else "the two switches share no agent mode"
        expected = (b in exclusions(a) or a in exclusions(b) or mode is None)
        pairs.append({"pair": [a, b], "mode": mode, "refusal": refusal, "expected_refusal": expected})
    enabled = {}
    for mode in fc.AGENT_MODES:
        sel = all_enabled(mode)
        enabled[mode] = {"switches": [k for k in bools if sel.get(k) is True],
                         "flags": fc.feature_cli_arguments(sel), "selection": sel,
                         "refusal": fc.validate_features(sel, surf[mode])}
    out = {
        "catalog_schema_version": fc.CATALOG_SCHEMA_VERSION,
        "groups": list(dict.fromkeys(e["group"] for e in fc.feature_entries())),
        "switches": len(bools),
        "features": features,
        "pairs_total": len(pairs),
        "pairs_valid": [p["pair"] for p in pairs if p["refusal"] is None],
        "pairs_refused": [p for p in pairs if p["refusal"] is not None],
        "pairs_refused_unexpectedly": [p for p in pairs if p["refusal"] is not None and not p["expected_refusal"]],
        "pairs_accepted_despite_exclusion": [p for p in pairs if p["refusal"] is None and p["expected_refusal"]],
        "drops": drops,
        "drops_not_refused": [d for d in drops if d["refusal"] is None],
        "all_enabled": enabled,
        "exclusion_problems": fc.exclusion_problems(),
    }
    return out


def problems(m: dict) -> list[str]:
    out = [f"drop of {d['dropped']} from {d['feature']} accepted" for d in m["drops_not_refused"]]
    out += [f"pair {'+'.join(p['pair'])} refused under {p['mode']}: {p['refusal']}"
            for p in m["pairs_refused_unexpectedly"]]
    out += [f"pair {'+'.join(p['pair'])} accepted although they exclude each other"
            for p in m["pairs_accepted_despite_exclusion"] if p["mode"] is not None]
    out += [f"all enabled under {mode}: {e['refusal']}" for mode, e in m["all_enabled"].items() if e["refusal"]]
    out += m["exclusion_problems"]
    return out


def markdown(m: dict) -> str:
    lines = [f"# Switch compatibility matrix (catalog schema {m['catalog_schema_version']})", "",
             f"{m['switches']} switches in groups {', '.join(m['groups'])}; {m['pairs_total']} pairs, "
             f"{len(m['pairs_valid'])} valid, {len(m['pairs_refused'])} refused "
             f"({len(m['pairs_refused_unexpectedly'])} unexpectedly); {len(m['drops'])} prerequisite drops, "
             f"{len(m['drops_not_refused'])} accepted.", "",
             "| Switch | Agent modes | Minimal selection |", "| --- | --- | --- |"]
    for key, f in m["features"].items():
        others = ", ".join(f"{k}={v}" if v is not True else k for k, v in f["closure"].items() if k != key)
        lines.append(f"| {key} | {', '.join(f['modes']) or 'none'} | {others or '-'} |")
    lines += ["", "## Refused pairs", ""]
    lines += [f"- {'+'.join(p['pair'])} ({p['mode']}): {p['refusal']}"
              + ("" if p["expected_refusal"] else " **unexpected**") for p in m["pairs_refused"]] or ["- none"]
    lines += ["", "## Prerequisite drops (each must be refused)", ""]
    lines += [f"- {d['feature']} without {d['dropped']} ({d['mode']}): {d['refusal'] or '**accepted**'}"
              for d in m["drops"]]
    lines += ["", "## All enabled, per agent mode", ""]
    for mode, e in m["all_enabled"].items():
        lines.append(f"- {mode}: {'accepted' if e['refusal'] is None else e['refusal']}; "
                     f"{' '.join(e['flags']) or '(nothing)'}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", default=None)
    ap.add_argument("--markdown", default=None)
    a = ap.parse_args(argv)
    m = matrix()
    found = problems(m)
    print(f"{m['switches']} switches; {m['pairs_total']} pairs, {len(m['pairs_refused'])} refused "
          f"({len(m['pairs_refused_unexpectedly'])} unexpectedly); {len(m['drops'])} prerequisite drops, "
          f"{len(m['drops_not_refused'])} accepted")
    for mode, e in m["all_enabled"].items():
        print(f"  all enabled under {mode}: {len(e['switches'])} switches, "
              f"{'accepted' if e['refusal'] is None else e['refusal']}")
    for p in found:
        print("PROBLEM", p)
    if a.json:
        Path(a.json).write_text(json.dumps(m, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if a.markdown:
        Path(a.markdown).write_text(markdown(m), encoding="utf-8")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
