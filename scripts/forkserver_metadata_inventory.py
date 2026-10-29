"""Bounded, read-only source inventory for the inactive metadata proof design.

This parses Python source; it never imports Chronicler or its dependencies and
does not certify the actual runtime import graph, class contents or fork safety.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re


MAX_FILES = 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_MODULES = 64
_MODULE = re.compile(r"chronicler(?:\.[A-Za-z_]\w*)*\Z", re.ASCII)


def _read_source(path: Path, package: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(package):
        raise ValueError("source must be a regular non-symlink package file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("source file exceeds byte limit")
    return raw


def _module_path(package: Path, name: str) -> Path:
    if type(name) is not str or _MODULE.fullmatch(name) is None:
        raise ValueError("invalid Chronicler module name")
    suffix = name.split(".")[1:]
    base = package.joinpath(*suffix)
    path = base.with_suffix(".py") if suffix else package / "__init__.py"
    if not path.is_file():
        path = base / "__init__.py"
    return path


def _runtime_imports(tree: ast.Module) -> set[str]:
    """Direct source edges only; dynamic execution remains a runtime obligation."""
    def eager_import(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return False
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return True
        return any(eager_import(child) for child in ast.iter_child_nodes(node))

    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names if _MODULE.fullmatch(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise ValueError("relative imports require explicit source review")
            if node.module == "chronicler":
                raise ValueError("package-attribute imports require explicit source review")
            if node.module and _MODULE.fullmatch(node.module):
                names.add(node.module)
        elif isinstance(node, ast.ClassDef):
            if eager_import(node):
                raise ValueError("class-body imports require explicit source review")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        elif isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            if node.orelse:
                raise ValueError("TYPE_CHECKING else branch requires explicit source review")
        elif any(isinstance(child, (ast.Import, ast.ImportFrom)) for child in ast.walk(node)):
            raise ValueError("conditional imports require explicit source review")
    return names


def inventory(root: Path) -> dict:
    """Inventory a source tree without evaluating its code or claiming Git state."""
    root = Path(root).resolve()
    package = root / "src" / "chronicler"
    if package.is_symlink() or not package.is_dir():
        raise ValueError("expected a regular src/chronicler package directory")
    package = package.resolve()
    files = []
    for path in package.rglob("*.py"):
        if len(files) >= MAX_FILES:
            raise ValueError("package file limit exceeded")
        files.append(path)
    files.sort(key=lambda path: path.relative_to(package).as_posix())
    digest = hashlib.sha256()
    hashes = {}
    total_bytes = 0
    for path in files:
        raw = _read_source(path, package)
        total_bytes += len(raw)
        if total_bytes > MAX_PACKAGE_BYTES:
            raise ValueError("package byte limit exceeded")
        relative = path.relative_to(package).as_posix()
        sha = hashlib.sha256(raw).hexdigest()
        hashes[relative] = sha
        # Same path/NUL/content-hash/newline recipe as batch_manifest.package_digest.
        digest.update(relative.encode("utf-8") + b"\0" + sha.encode("ascii") + b"\n")

    pending = ["chronicler.models", "chronicler"]
    modules = {}
    while pending:
        name = pending.pop()
        if name in modules:
            continue
        if len(modules) >= MAX_MODULES:
            raise ValueError("static module limit exceeded")
        path = _module_path(package, name)
        raw = _read_source(path, package)
        relative = path.relative_to(package).as_posix()
        sha = hashlib.sha256(raw).hexdigest()
        if hashes.get(relative) != sha:
            raise ValueError("source changed during inventory")
        tree = ast.parse(raw, filename=relative)
        imports = _runtime_imports(tree)
        parts = name.split(".")
        parents = {".".join(parts[:index]) for index in range(1, len(parts))}
        modules[name] = {
            "path": "src/chronicler/" + relative,
            "sha256": sha,
            "direct_source_imports": sorted(imports),
            "declared_classes": [node.name for node in tree.body if isinstance(node, ast.ClassDef)],
        }
        pending.extend(sorted(imports | parents))

    return {
        "kind": "chronicler-static-model-preload-inventory",
        "schema_version": 1,
        "qualification": "none; static source only",
        "package_digest": digest.hexdigest(),
        "package_files": len(files),
        "package_bytes": total_bytes,
        "modules": {name: modules[name] for name in sorted(modules)},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(inventory(args.source_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
