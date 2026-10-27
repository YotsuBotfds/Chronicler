#!/usr/bin/env python3
"""Byte-identity runs for performance work.

``run OUT_DIR [--case NAME ...] [--source-root SRC] [--native-root DIR] [--cli-arg ARG ...]``
    Run the case matrix below as CLI subprocesses (``PYTHONHASHSEED=0``,
    ``RAYON_NUM_THREADS=1``), one at a time, each into ``OUT_DIR/<case>``.
    ``--source-root`` puts another checkout's ``src`` first on
    ``PYTHONPATH`` and ``--native-root`` a saved ``chronicler_agents``
    package, which is how a base tree is run. ``--cli-arg`` adds a CLI
    argument to every case (a feature switch such as ``--no-scholarship``).

``compare BASE_DIR NEW_DIR [--faith-ids]``
    Every file of every case byte for byte (``chronicle_bundle.json``
    decoded, without ``metadata.generated_at``), as
    ``scripts/cities_identity.py compare``; each bundle's raw bytes are
    also compared with only the ``generated_at`` value blanked.

    ``--faith-ids`` compares a run with permanent faith ids
    (docs/integration/permanent-faiths.md) against one without: the new
    run's faith table is dropped and every field that newly carries a
    permanent id is projected back to the native slot that faith held,
    using the new run's own table (``FaithProjection``); state files are
    then compared decoded and the raw-bytes check is skipped. Each case
    prints the fields it changed and how many values.

Scaled cases multiply region capacities and starting populations before
the first turn, as ``scripts/agent_scale_benchmark.py`` does.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]

# name -> (CLI arguments, starting-agent target or 0)
CASES: dict[str, tuple[list[str], int]] = {
    "off_s42": (["--seed", "42", "--turns", "300", "--agents", "off"], 0),
    "off_s7": (["--seed", "7", "--turns", "300", "--agents", "off"], 0),
    "hybrid_s42": (["--seed", "42", "--turns", "200", "--agents", "hybrid",
                    "--validation-sidecar"], 0),
    "hybrid_s7": (["--seed", "7", "--turns", "200", "--agents", "hybrid",
                   "--validation-sidecar"], 0),
    "hybrid_s1234": (["--seed", "1234", "--turns", "200", "--agents", "hybrid"], 0),
    "proc48_hybrid_s42": (["--seed", "42", "--turns", "150", "--regions", "48", "--civs", "10",
                           "--agents", "hybrid", "--validation-sidecar"], 0),
    "proc48_off_s7": (["--seed", "7", "--turns", "200", "--regions", "48", "--civs", "10",
                       "--agents", "off"], 0),
    "scaled22k_s42": (["--seed", "42", "--turns", "30", "--regions", "12", "--civs", "4",
                       "--agents", "hybrid", "--validation-sidecar"], 18800),
    "scaled52k_s7": (["--seed", "7", "--turns", "20", "--regions", "12", "--civs", "4",
                      "--agents", "hybrid"], 43700),
}

_SCALED_RUNNER = r"""
import sys
import chronicler.main as cm
from chronicler.utils import sync_civ_population
target = int(sys.argv[1])
original = cm.generate_world
def scaled(*a, **k):
    world = original(*a, **k)
    mult = target / max(1, sum(r.population for r in world.regions))
    for region in world.regions:
        region.carrying_capacity = max(1, round(region.carrying_capacity * mult))
        region.population = round(region.population * mult)
    for civ in world.civilizations:
        sync_civ_population(civ, world)
    return world
cm.generate_world = scaled
sys.argv = ["chronicler"] + sys.argv[2:]
cm.main()
"""


def _env(source_root: Path | None, native_root: Path | None) -> dict:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["RAYON_NUM_THREADS"] = "1"
    env["CHRONICLER_QUIET"] = "1"
    paths = []
    if native_root:
        paths.append(str(native_root.resolve()))
    if source_root:
        paths.append(str((source_root / "src").resolve()))
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths)
    else:
        env.pop("PYTHONPATH", None)
    return env


_WHICH = (
    "import hashlib, chronicler, chronicler_agents.chronicler_agents as m\n"
    "print('chronicler', chronicler.__file__)\n"
    "print('native', m.__file__, hashlib.sha256(open(m.__file__, 'rb').read()).hexdigest())\n"
)


def run(out: Path, cases: list[str], source_root: Path | None, native_root: Path | None,
        extra: list[str] | None = None) -> int:
    env = _env(source_root, native_root)
    # Record which source tree and native build the runs used.
    which = subprocess.run([sys.executable, "-c", _WHICH], env=env, cwd=str(out),
                           capture_output=True, text=True)
    (out / "which.txt").write_text(which.stdout + which.stderr)
    print(which.stdout.strip(), flush=True)
    status = 0
    for name in cases:
        cli, target = CASES[name]
        case_dir = out / name
        case_dir.mkdir(parents=True, exist_ok=True)
        cli = cli + list(extra or []) + ["--simulate-only", "--output", str(case_dir / "chronicle.md"),
                     "--state", str(case_dir / "state.json")]
        if target:
            cmd = [sys.executable, "-c", _SCALED_RUNNER, str(target), *cli]
        else:
            cmd = [sys.executable, "-m", "chronicler.main", *cli]
        t0 = time.monotonic()
        with open(out / f"{name}.log", "w") as log:
            proc = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                  cwd=str(out))
        print(f"{name}: exit {proc.returncode} in {time.monotonic() - t0:.0f} s", flush=True)
        status |= proc.returncode != 0
    return int(status)


_GENERATED_AT = re.compile(rb'"generated_at": ?"[^"]*"')


def _raw_bundle_problems(base: Path, new: Path) -> list[str]:
    """Raw bytes of every bundle, with only the wall-clock stamp blanked."""
    problems = []
    for a in sorted(base.rglob("chronicle_bundle.json")):
        b = new / a.relative_to(base)
        if not b.exists():
            continue
        if _GENERATED_AT.sub(b"", a.read_bytes()) != _GENERATED_AT.sub(b"", b.read_bytes()):
            problems.append(f"raw bytes differ: {a.relative_to(base)}")
    return problems


_TEMPLE_TEXT = re.compile(r"^Temple of faith (\d+) ")
_TEMPLE_ID = re.compile(r"temple:(\d+)")


class FaithProjection:
    """A run's permanent faith ids projected back to native slots.

    Built from the run's own ``faiths`` table (index = permanent id, ``slot``
    the slot it held), it rewrites, in a decoded file of that run, exactly
    the fields that carry a permanent id since docs/integration/permanent-faiths.md
    and drops the table: movements (``faith``, ``schism_from``,
    ``schism_to``, a schism's ``successor``), tolerations (``faith``, in the
    world state and the history's reform rows), conversion objectives
    (``conversion_faith_id``), seats (``faith``), ``Temple of faith <id>``
    descriptions, temple chronicler ids (``temple:<id>``) and ``faith``, and
    the faith words' ``ref``. ``counts`` holds the values changed per field.
    """

    def __init__(self, table: list[dict]):
        self.slot = {k: rec["slot"] for k, rec in enumerate(table)}
        self.released = sum(1 for rec in table if rec.get("released_turn") is not None)
        self.size = len(table)
        from collections import Counter
        self.counts: Counter = Counter()

    def _map(self, value, field: str):
        if isinstance(value, int) and not isinstance(value, bool) and value in self.slot \
                and self.slot[value] != value:
            self.counts[field] += 1
            return self.slot[value]
        return value

    def _put(self, obj, key: str, field: str) -> None:
        if isinstance(obj, dict) and key in obj:
            obj[key] = self._map(obj[key], field)

    def _text(self, desc, field: str):
        if not isinstance(desc, str):
            return desc
        m = _TEMPLE_TEXT.match(desc)
        if m is None:
            return desc
        new = self._map(int(m.group(1)), field)
        return desc if new == int(m.group(1)) else f"Temple of faith {new} " + desc[m.end():]

    def _ids(self, value, field: str):
        """Temple chronicler ids anywhere in a value (strings and dict keys)."""
        if isinstance(value, str):
            def sub(m):
                return f"temple:{self._map(int(m.group(1)), field)}"
            return _TEMPLE_ID.sub(sub, value)
        if isinstance(value, list):
            return [self._ids(v, field) for v in value]
        if isinstance(value, dict):
            out = {self._ids(k, field): self._ids(v, field) for k, v in value.items()}
            if out.get("kind") == "temple" and "faith" in out:
                out["faith"] = self._map(out["faith"], "historiography.faith")
            return out
        return value

    def _world(self, ws: dict, where: str) -> None:
        if ws.pop("faiths", None) is not None:
            self.counts[f"{where}.faiths (table dropped)"] += 1
        am = ws.get("agent_movements") or {}
        for m in am.get("movements") or []:
            self._put(m, "faith", "movements.faith")
            self._put(m, "schism_from", "movements.schism_from")
            self._put(m, "schism_to", "movements.schism_to")
            if m.get("end") == 4:  # agent_movements_state.SCHISM
                self._put(m, "successor", "movements.successor")
        for r in am.get("reforms") or []:
            if r.get("kind") == 2:  # TOLERATION
                self._put(r, "faith", "reforms.faith")
        for rec in ((ws.get("gp_agendas") or {}).get("records") or {}).values():
            self._put(rec.get("agenda"), "conversion_faith_id", "gp_agendas.conversion_faith_id")
        for civ in ws.get("civilizations") or []:
            for a in (civ.get("governance") or {}).get("ambitions") or []:
                self._put(a, "conversion_faith_id", "governance.conversion_faith_id")
        for seat in (ws.get("scholarship") or {}).get("seats") or []:
            self._put(seat, "faith", "scholarship.faith")
        for ev in ws.get("events_timeline") or []:
            ev["description"] = self._text(ev.get("description"), "events.temple_description")

    def _words(self, rows, columns) -> None:
        ki, ri = columns.index("kind"), columns.index("ref")
        for row in rows:
            if row[ki] == "faith":
                row[ri] = self._map(row[ri], "languages.words.ref")

    def __call__(self, name: str, data: dict) -> None:
        if name == "chronicle_bundle.json":
            self._world(data["world_state"], "world_state")
            for snap in data.get("history") or []:
                for row in (snap.get("agent_movements") or {}).get("reforms") or []:
                    self._put(row, "faith", "history.reforms.faith")
            for ev in data.get("events_timeline") or []:
                ev["description"] = self._text(ev.get("description"), "events.temple_description")
            if isinstance(data.get("historiography"), dict):
                data["historiography"] = self._ids(data["historiography"], "historiography.temple_id")
            langs = data.get("languages")
            if isinstance(langs, dict):
                self._words(langs.get("words") or [], list(langs.get("word_columns") or []))
                for f in langs.get("faiths") or []:
                    self._put(f, "faith", "languages.faiths")
        elif name.endswith(".historiography.json"):
            data.update(self._ids(data, "historiography.temple_id"))
        elif name.endswith(".languages.json"):
            st = data.get("state") if isinstance(data.get("state"), dict) else data
            for w in st.get("words") or []:
                if w.get("kind") == "faith":
                    self._put(w, "ref", "languages.words.ref")
            if isinstance(st.get("faiths"), dict):
                st["faiths"] = {str(self._map(int(k), "languages.faiths")): v
                                for k, v in st["faiths"].items()}
        elif name.startswith("state") and name.endswith(".json"):
            self._world(data, "state")


def _faith_projection(case_dir: Path) -> FaithProjection | None:
    """The projection of a case's run, from its state's faith table."""
    import json
    state = case_dir / "state.json"
    if not state.exists():
        return None
    table = json.loads(state.read_text(encoding="utf-8")).get("faiths") or []
    return FaithProjection(table)


def compare(base: Path, new: Path, faith_ids: bool = False) -> int:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from cities_identity import compare as compare_dirs

    total_checked = 0
    total_problems = 0
    cases = sorted(p.name for p in base.iterdir() if p.is_dir())
    for name in cases:
        projection = _faith_projection(new / name) if faith_ids else None
        checked, problems = compare_dirs(base / name, new / name, normalize=projection)
        if not faith_ids:
            problems += _raw_bundle_problems(base / name, new / name)
        total_checked += checked
        total_problems += len(problems)
        print(f"{name}: {checked} files, {len(problems)} differences")
        if projection is not None:
            print(f"  faith table: {projection.size} faiths, {projection.released} released; "
                  f"projected: {dict(sorted(projection.counts.items())) or 'nothing'}")
        for line in problems:
            print(f"  {line}")
    print(f"{len(cases)} cases, {total_checked} files compared, {total_problems} differences")
    return 0 if total_checked and not total_problems else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("out", type=Path)
    r.add_argument("--case", action="append", choices=sorted(CASES))
    r.add_argument("--source-root", type=Path)
    r.add_argument("--native-root", type=Path)
    r.add_argument("--cli-arg", action="append", default=[],
                   help="extra CLI argument for every case (repeatable)")
    c = sub.add_parser("compare")
    c.add_argument("base", type=Path)
    c.add_argument("new", type=Path)
    c.add_argument("--faith-ids", action="store_true",
                   help="project the new run's permanent faith ids back to slots (see above)")
    a = p.parse_args(argv)
    if a.cmd == "run":
        a.out.mkdir(parents=True, exist_ok=True)
        return run(a.out.resolve(), a.case or list(CASES), a.source_root, a.native_root, a.cli_arg)
    return compare(a.base, a.new, faith_ids=a.faith_ids)


if __name__ == "__main__":
    sys.exit(main())
