"""The switch compatibility matrix, generated from ``chronicler.feature_catalog``.

    PYTHONPATH=src python scripts/feature_matrix.py [--json OUT.json] [--markdown OUT.md]

Catalog only (no runs; adapted from audit E's prototype). Every selection is
evaluated per agent mode and per **world**: a template world and a procedural one,
which differ in the catalog's world-dependent settings (``WORLD_SETTINGS``, today
``procedural_world``; every other setting takes its default). For every boolean
switch: its minimal accepted selection (prerequisites switched on, required
choices set), the agent modes and the worlds it allows. Then:

* **pairs**: every two switches with their minimal selections joined, evaluated in
  each world under the most detailed agent mode both allow. A pair is valid when it
  is accepted in every world both switches allow; a refusal in a world one of them
  does not allow is *world-dependent* (reported, not a problem); a refusal is
  *expected* only for an exclusive pair or a pair without a common agent mode or
  world;
* **prerequisite drops**: each minimal selection with one prerequisite switch (and
  its choices) removed, in a mode and world the switch allows; the catalog must
  refuse every one;
* **all enabled**, per agent mode and world: the largest selection the catalog
  accepts (every switch the mode and world allow, required choices set, then the
  first switch in catalog order with an unmet requirement dropped until none is,
  as the viewer's ``normalizeSelection`` does), its flags and the catalog's verdict.

The run's own checks stay authoritative: ``tests/test_feature_matrix.py`` also
sends every all-enabled selection (template and procedural worlds) and every drop
through ``main._configure_run``. Exit code 1 when a drop is accepted, a pair is
refused unexpectedly, an all-enabled selection is refused or an exclusion is
one-sided.
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

WORLDS: tuple[str, ...] = ("template", "procedural")
#: Settings that depend on the world a run starts, and their value in each world.
WORLD_SETTINGS: dict[str, dict[str, bool]] = {"procedural_world": {"template": False, "procedural": True}}


def _entries() -> dict[str, dict]:
    return fc._by_key()


def bool_switches() -> list[str]:
    return [e["key"] for e in fc.feature_entries() if e["kind"] == "bool"]


def world_settings() -> dict[str, dict[str, bool]]:
    """The world-dependent settings this catalog declares."""
    return {name: values for name, values in WORLD_SETTINGS.items() if name in fc.SETTINGS}


def surface(mode: str, world: str) -> dict:
    """The live surface of an agent mode in a world: default settings, the world's
    world-dependent ones."""
    out = fc.live_surface(argparse.Namespace(agents=mode))
    out["settings"] = {**out["settings"], **{name: values[world] for name, values in world_settings().items()}}
    return out


def surfaces() -> dict[str, dict[str, dict]]:
    return {mode: {world: surface(mode, world) for world in WORLDS} for mode in fc.AGENT_MODES}


def exclusions(key: str) -> set[str]:
    return {c["not"]["feature"] for c in _entries()[key]["requires"] if "not" in c and "feature" in c["not"]}


def closure(key: str) -> tuple[dict, list[str], list[str]]:
    """The smallest selection the catalog accepts with ``key`` on, and the agent modes
    and worlds it allows (an ``any`` condition takes its first alternative; exclusions
    add nothing; a world-dependent setting narrows the worlds)."""
    entries = _entries()
    selection: dict = {key: True}
    modes, worlds = list(fc.AGENT_MODES), list(WORLDS)
    stack = [key]
    settings = world_settings()

    def walk(condition):
        nonlocal modes, worlds
        if "agents" in condition:
            modes = [m for m in modes if m in condition["agents"]]
        elif "feature" in condition:
            if condition["feature"] not in selection:
                selection[condition["feature"]] = True
                stack.append(condition["feature"])
        elif "choice" in condition:
            if entries[condition["choice"]]["choices"][0] not in condition["values"]:
                selection[condition["choice"]] = condition["values"][0]
        elif "setting" in condition:
            if condition["setting"] in settings:
                worlds = [w for w in worlds if settings[condition["setting"]][w]]
        elif "any" in condition:
            walk(condition["any"][0])

    while stack:
        for condition in entries[stack.pop()]["requires"]:
            walk(condition)
    return selection, modes, worlds


def _detailed(modes) -> str | None:
    """The most detailed agent mode of a list (the CLI orders them by detail)."""
    return max(modes, key=fc.AGENT_MODES.index) if modes else None


def _without(selection: dict, dropped: str) -> dict:
    entries = _entries()
    return {k: v for k, v in selection.items() if k != dropped and entries[k]["parent"] != dropped}


def all_enabled(mode: str, world: str = "template") -> dict:
    """The largest selection the catalog accepts under ``mode`` in ``world``: every
    switch whose minimal selection allows both, required choices set, then (as the
    viewer's normalizeSelection does) the first switch in catalog order with an unmet
    requirement dropped until none is left."""
    surf = surface(mode, world)
    entries = _entries()
    selection: dict = {}
    for key in bool_switches():
        sel, modes, worlds = closure(key)
        if mode in modes and world in worlds:
            for k, v in sel.items():
                if entries[k]["kind"] == "choice":
                    selection.setdefault(k, v)
                else:
                    selection[k] = True
    while True:
        unmet = fc.unmet_requirements(selection, surf)       # catalog order: "'key' (--flag) reason"
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
        sel, modes, worlds = closure(key)
        features[key] = {"closure": sel, "modes": modes, "worlds": worlds,
                         "valid": {m: {w: fc.validate_features(sel, surf[m][w]) for w in WORLDS}
                                   for m in fc.AGENT_MODES}}
        mode, world = _detailed(modes), (worlds[0] if worlds else None)
        for other in sel:
            if other != key and entries[other]["kind"] == "bool":
                refusal = (fc.validate_features(_without(sel, other), surf[mode][world]) if mode and world
                           else "no agent mode or world")
                drops.append({"feature": key, "dropped": other, "mode": mode, "world": world, "refusal": refusal})
    pairs = []
    for a, b in itertools.combinations(bools, 2):
        sel = {**features[a]["closure"], **features[b]["closure"]}
        modes = [m for m in features[a]["modes"] if m in features[b]["modes"]]
        worlds = [w for w in features[a]["worlds"] if w in features[b]["worlds"]]
        mode = _detailed(modes)
        by_world = {w: (fc.validate_features(sel, surf[mode][w]) if mode else "the two switches share no agent mode")
                    for w in WORLDS}
        refusal = next((by_world[w] for w in worlds if by_world[w] is not None), None) if worlds else \
            "the two switches share no world"
        world_dependent = {w: r for w, r in by_world.items() if r is not None and w not in worlds}
        expected = b in exclusions(a) or a in exclusions(b) or mode is None or not worlds
        pairs.append({"pair": [a, b], "mode": mode, "worlds": worlds, "by_world": by_world, "refusal": refusal,
                      "world_dependent": world_dependent, "expected_refusal": expected})
    enabled = {}
    for mode in fc.AGENT_MODES:
        enabled[mode] = {}
        for world in WORLDS:
            sel = all_enabled(mode, world)
            enabled[mode][world] = {"switches": [k for k in bools if sel.get(k) is True],
                                    "flags": fc.feature_cli_arguments(sel), "selection": sel,
                                    "refusal": fc.validate_features(sel, surf[mode][world])}
    return {
        "catalog_schema_version": fc.CATALOG_SCHEMA_VERSION,
        "groups": list(dict.fromkeys(e["group"] for e in fc.feature_entries())),
        "worlds": list(WORLDS),
        "world_settings": world_settings(),
        "switches": len(bools),
        "features": features,
        "pairs_total": len(pairs),
        "pairs_valid": [p["pair"] for p in pairs if p["refusal"] is None],
        "pairs_world_dependent": [p for p in pairs if p["refusal"] is None and p["world_dependent"]],
        "pairs_refused": [p for p in pairs if p["refusal"] is not None],
        "pairs_refused_unexpectedly": [p for p in pairs if p["refusal"] is not None and not p["expected_refusal"]],
        "pairs_accepted_despite_exclusion": [p for p in pairs if p["refusal"] is None and p["expected_refusal"]],
        "drops": drops,
        "drops_not_refused": [d for d in drops if d["refusal"] is None],
        "all_enabled": enabled,
        "exclusion_problems": fc.exclusion_problems(),
    }


def problems(m: dict) -> list[str]:
    out = [f"drop of {d['dropped']} from {d['feature']} accepted" for d in m["drops_not_refused"]]
    out += [f"pair {'+'.join(p['pair'])} refused under {p['mode']}: {p['refusal']}"
            for p in m["pairs_refused_unexpectedly"]]
    out += [f"pair {'+'.join(p['pair'])} accepted although they exclude each other"
            for p in m["pairs_accepted_despite_exclusion"] if p["mode"] is not None and p["worlds"]]
    out += [f"all enabled under {mode} in a {world} world: {e['refusal']}"
            for mode, by in m["all_enabled"].items() for world, e in by.items() if e["refusal"]]
    out += m["exclusion_problems"]
    return out


def markdown(m: dict) -> str:
    lines = [f"# Switch compatibility matrix (catalog schema {m['catalog_schema_version']})", "",
             f"{m['switches']} switches in groups {', '.join(m['groups'])}; worlds {', '.join(m['worlds'])} "
             f"(world-dependent settings: {', '.join(m['world_settings']) or 'none'}); {m['pairs_total']} pairs, "
             f"{len(m['pairs_valid'])} valid ({len(m['pairs_world_dependent'])} only in some worlds), "
             f"{len(m['pairs_refused'])} refused ({len(m['pairs_refused_unexpectedly'])} unexpectedly); "
             f"{len(m['drops'])} prerequisite drops, {len(m['drops_not_refused'])} accepted.", "",
             "| Switch | Agent modes | Worlds | Minimal selection |", "| --- | --- | --- | --- |"]
    for key, f in m["features"].items():
        others = ", ".join(f"{k}={v}" if v is not True else k for k, v in f["closure"].items() if k != key)
        lines.append(f"| {key} | {', '.join(f['modes']) or 'none'} | {', '.join(f['worlds']) or 'none'} | "
                     f"{others or '-'} |")
    lines += ["", "## Refused pairs", ""]
    lines += [f"- {'+'.join(p['pair'])} ({p['mode']}): {p['refusal']}"
              + ("" if p["expected_refusal"] else " **unexpected**") for p in m["pairs_refused"]] or ["- none"]
    lines += ["", "## World-dependent pairs (valid in the worlds both switches allow)", ""]
    lines += [f"- {'+'.join(p['pair'])}: valid in {', '.join(p['worlds'])}; refused in "
              + "; ".join(f"{w} ({r})" for w, r in p["world_dependent"].items())
              for p in m["pairs_world_dependent"]] or ["- none"]
    lines += ["", "## Prerequisite drops (each must be refused)", ""]
    lines += [f"- {d['feature']} without {d['dropped']} ({d['mode']}, {d['world']}): {d['refusal'] or '**accepted**'}"
              for d in m["drops"]]
    lines += ["", "## All enabled, per agent mode and world", ""]
    for mode, by in m["all_enabled"].items():
        for world, e in by.items():
            lines.append(f"- {mode}, {world}: {'accepted' if e['refusal'] is None else e['refusal']}; "
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
          f"({len(m['pairs_refused_unexpectedly'])} unexpectedly), {len(m['pairs_world_dependent'])} world-dependent; "
          f"{len(m['drops'])} prerequisite drops, {len(m['drops_not_refused'])} accepted")
    for mode, by in m["all_enabled"].items():
        for world, e in by.items():
            print(f"  all enabled under {mode} in a {world} world: {len(e['switches'])} switches, "
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
