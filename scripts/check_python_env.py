"""Report a Python environment's Chronicler source and native state; check it.

Run it with the interpreter of the environment to check:

    .venv/bin/python scripts/check_python_env.py --expect no-native
    ~/.venvs/chronicler-native/bin/python scripts/check_python_env.py --expect native

It reports the interpreter and virtual environment; whether ``chronicler``
resolves to this checkout's ``src/`` and has its console script; and whether
``chronicler_agents`` is importable, from which path, and the SHA-256 of its
compiled extension file. Without ``--expect`` it only reports the native state.

``--expect no-native`` (and the report-only mode) never imports
``chronicler_agents``: it makes the same top-level
``importlib.util.find_spec("chronicler_agents")`` lookup as CI's "Assert native
extension is absent" step, then reads files. ``--expect native`` imports it and
requires the compiled submodule ``chronicler_agents.chronicler_agents`` (loaded
by an ``ExtensionFileLoader`` from a file with an extension-module suffix) and
real ``AgentSimulator``, ``EcologySimulator`` and ``PoliticsSimulator`` classes,
the checks of README.md's native lane and ``scripts/native_ci_shards.py``.

Exit status 0 when every check passes, 1 otherwise. A pass describes this one
environment; it is not native, POSIX-persistence or scientific qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.machinery
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import sysconfig

ROOT = Path(__file__).resolve().parents[1]
NATIVE = "chronicler_agents"
SUBMODULE = "chronicler_agents.chronicler_agents"
CLASSES = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
EXPECTATIONS = ("native", "no-native")


def file_identity(path: Path) -> dict:
    with open(path, "rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}


def lookup(name: str, find_spec):
    """Top-level find_spec, which locates ``name`` without executing it."""
    try:
        return find_spec(name), None
    except (ImportError, ValueError) as error:  # e.g. a finder that holds the module
        return None, f"{type(error).__name__}: {error}"


def installed_version(name: str):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def same_file(left, right: Path) -> bool:
    try:
        return left is not None and os.path.samefile(left, right)
    except OSError:
        return False


def chronicler_state(find_spec, scripts_dir: Path) -> dict:
    expected = ROOT / "src" / "chronicler" / "__init__.py"
    spec, error = lookup("chronicler", find_spec)
    origin = getattr(spec, "origin", None)
    cli = next((scripts_dir / name for name in ("chronicler", "chronicler.exe")
                if (scripts_dir / name).is_file()), None)
    return {"origin": origin, "expected": str(expected), "this_checkout": same_file(origin, expected),
            "lookup_error": error, "cli": None if cli is None else str(cli)}


def compiled_files(spec) -> list[Path]:
    """Extension-module files for ``chronicler_agents``, found without importing it."""
    suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
    origin = getattr(spec, "origin", None)
    if isinstance(origin, str) and origin.endswith(suffixes):
        return [Path(origin)]
    return [Path(location) / f"{NATIVE}{suffix}"
            for location in (getattr(spec, "submodule_search_locations", None) or ())
            for suffix in suffixes if (Path(location) / f"{NATIVE}{suffix}").is_file()]


def native_state(expect, find_spec, import_module, version) -> dict:
    spec, error = lookup(NATIVE, find_spec)
    state = {"importable": spec is not None, "lookup_error": error}
    if spec is None:
        return state
    state.update(origin=getattr(spec, "origin", None),
                 locations=[str(item) for item in (getattr(spec, "submodule_search_locations", None) or ())],
                 distribution_version=version("chronicler-agents"),
                 compiled_files=[file_identity(path) for path in compiled_files(spec)])
    if expect != "native":
        return state  # Never import the native package unless it is expected.
    try:
        package = import_module(NATIVE)
        module = import_module(SUBMODULE)
    except Exception as exc:  # The extension's own initialisation can raise anything.
        state["import_error"] = f"{type(exc).__name__}: {exc}"
        return state
    module_spec = getattr(module, "__spec__", None)
    path = getattr(module, "__file__", None)
    compiled = (module_spec is not None
                and isinstance(module_spec.loader, importlib.machinery.ExtensionFileLoader)
                and isinstance(path, str) and path.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)))
    state["submodule"] = dict(file_identity(Path(path)) if compiled else {"path": path}, compiled=compiled)
    state["classes"] = {name: isinstance(getattr(package, name, None), type)
                        and getattr(package, name, None) is getattr(module, name, None) for name in CLASSES}
    return state


def evaluate(expect, *, find_spec=importlib.util.find_spec, import_module=importlib.import_module,
             version=installed_version, scripts_dir=None) -> dict:
    if expect not in (None, *EXPECTATIONS):
        raise ValueError(f"unknown expectation: {expect!r}")
    scripts_dir = Path(sysconfig.get_path("scripts")) if scripts_dir is None else Path(scripts_dir)
    report = {
        "checkout": str(ROOT),
        "interpreter": {"executable": sys.executable, "version": platform.python_version(),
                        "implementation": platform.python_implementation(),
                        "platform": f"{sys.platform} {platform.machine()}"},
        "environment": {"prefix": sys.prefix, "virtual_env": sys.prefix != sys.base_prefix,
                        "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV"),
                        "PYTHONPATH": os.environ.get("PYTHONPATH")},
        "expect": expect,
        "chronicler": chronicler_state(find_spec, scripts_dir),
        "native": native_state(expect, find_spec, import_module, version),
    }
    chronicler, native = report["chronicler"], report["native"]
    checks = {"chronicler resolves to this checkout's src": chronicler["this_checkout"],
              "chronicler console script is installed": chronicler["cli"] is not None}
    if expect == "no-native":
        checks["chronicler_agents is absent"] = not native["importable"]
    elif expect == "native":
        checks["chronicler_agents is importable"] = native["importable"] and "import_error" not in native
        checks[f"{SUBMODULE} is a compiled extension"] = bool(native.get("submodule", {}).get("compiled"))
        checks[", ".join(CLASSES) + " are the compiled classes"] = bool(native.get("classes")) and all(native["classes"].values())
    report["checks"] = checks
    report["passed"] = all(checks.values())
    return report


def hints(report) -> list[str]:
    checks = report["checks"]
    found = []
    if not report["chronicler"]["this_checkout"]:
        found.append("chronicler is not this checkout's src: run setup.sh (or `uv sync --frozen`) "
                     "from this checkout, or set PYTHONPATH=src when running from a worktree.")
    if checks.get("chronicler_agents is absent") is False:
        found.append("Remove chronicler_agents from this no-native environment: `uv sync --frozen` "
                     "(an exact sync uninstalls it), `python -m pip uninstall chronicler-agents`, or "
                     "recreate the venv. Build native extensions only into the separate native venv.")
    if report["expect"] == "native" and not report["passed"] and not checks.get(f"{SUBMODULE} is a compiled extension"):
        found.append("Build a fresh extension into this venv: VIRTUAL_ENV=<this venv> <this python> -m maturin "
                     "develop --release --locked --manifest-path chronicler-agents/Cargo.toml")
    return found


def render(report) -> str:
    chronicler, native, env = report["chronicler"], report["native"], report["environment"]
    interp = report["interpreter"]
    lines = [f"Checkout:      {report['checkout']}",
             f"Interpreter:   {interp['executable']} ({interp['implementation']} {interp['version']}, {interp['platform']})",
             f"Environment:   {env['prefix']} ({'virtual environment' if env['virtual_env'] else 'NOT a virtual environment'})"]
    if env["VIRTUAL_ENV"] and not same_file(env["VIRTUAL_ENV"], Path(env["prefix"])):
        lines.append(f"VIRTUAL_ENV:   {env['VIRTUAL_ENV']} (a different environment)")
    if env["PYTHONPATH"]:
        lines.append(f"PYTHONPATH:    {env['PYTHONPATH']} (included in the lookups below)")
    lines.append(f"chronicler:    {chronicler['origin'] or 'not importable'}"
                 f" ({'this checkout' if chronicler['this_checkout'] else 'NOT this checkout'})")
    lines.append(f"CLI:           {chronicler['cli'] or 'missing'}")
    if not native["importable"]:
        lines.append("chronicler_agents: absent" + (f" ({native['lookup_error']})" if native["lookup_error"] else ""))
    else:
        lines.append(f"chronicler_agents: importable from {native['origin'] or native['locations']}"
                     f" (distribution {native['distribution_version'] or 'not recorded'})")
        for item in native["compiled_files"]:
            lines.append(f"  compiled file: {item['path']} ({item['bytes']} bytes, sha256 {item['sha256']})")
        if not native["compiled_files"]:
            lines.append("  compiled file: none found")
        if "import_error" in native:
            lines.append(f"  import failed: {native['import_error']}")
        if "submodule" in native:
            lines.append(f"  {SUBMODULE}: {native['submodule']['path']}"
                         f" ({'compiled extension' if native['submodule']['compiled'] else 'NOT a compiled extension'})")
            lines.append("  classes: " + ", ".join(f"{name} {'ok' if ok else 'NOT compiled'}"
                                                   for name, ok in native["classes"].items()))
        elif report["expect"] != "native":
            lines.append("  (not imported; --expect native imports it and checks the compiled classes)")
    for name, ok in report["checks"].items():
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}")
    lines.extend(f"hint: {hint}" for hint in hints(report))
    expected = f"expected {report['expect']}" if report["expect"] else "native state reported, not checked"
    lines.append(f"Result: {'PASS' if report['passed'] else 'FAIL'} ({expected})")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--expect", choices=EXPECTATIONS, help="fail unless the native extension state matches")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    report = evaluate(args.expect)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
