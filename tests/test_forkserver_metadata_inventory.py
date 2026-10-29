"""Read-only source planning tests; no models, numeric runtime or fork imports."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / "scripts" / "forkserver_metadata_inventory.py"
SPEC = importlib.util.spec_from_file_location("forkserver_metadata_inventory", PATH)
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def _source(tmp_path, files):
    package = tmp_path / "src" / "chronicler"
    for name, text in files.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return package


def test_static_inventory_includes_transitive_research_and_parent_package_without_imports(tmp_path):
    package = _source(tmp_path, {
        "__init__.py": "raise AssertionError('must not import package')\n",
        "models.py": "from chronicler.experimental.data import State\nclass WorldState: pass\n",
        "experimental/__init__.py": "raise AssertionError('must not import parent')\n",
        "experimental/data.py": "from chronicler.research import LazyResearchModel\nclass State(LazyResearchModel): pass\n",
        "research.py": "class LazyResearchModel: pass\n",
        "unimported.py": "raise AssertionError('not in model closure')\n",
    })
    before = {path: path.read_bytes() for path in package.rglob("*.py")}
    result = inventory.inventory(tmp_path)
    assert set(result["modules"]) == {
        "chronicler", "chronicler.models", "chronicler.experimental", "chronicler.experimental.data", "chronicler.research",
    }
    assert result["modules"]["chronicler.research"]["declared_classes"] == ["LazyResearchModel"]
    assert result["package_files"] == 6
    expected = hashlib.sha256()
    for path in sorted(before, key=lambda path: path.relative_to(package).as_posix()):
        expected.update(path.relative_to(package).as_posix().encode() + b"\0"
                        + hashlib.sha256(before[path]).hexdigest().encode() + b"\n")
    assert result["package_digest"] == expected.hexdigest()
    assert result["qualification"] == "none; static source only"
    assert {path: path.read_bytes() for path in package.rglob("*.py")} == before


def test_type_checking_and_function_local_edges_are_not_claimed_as_runtime_imports(tmp_path):
    _source(tmp_path, {"__init__.py": "", "models.py": """
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from chronicler.missing import Data
def deferred():
    import chronicler.also_missing
class Data:
    def deferred_method(self):
        import chronicler.still_missing
"""})
    assert set(inventory.inventory(tmp_path)["modules"]) == {"chronicler", "chronicler.models"}


@pytest.mark.parametrize("text", [
    "if enabled:\n    import chronicler.branch\n",
    "try:\n    import chronicler.branch\nexcept ImportError: pass\n",
    "from .data import State\n",
    "from chronicler import data\n",
    "class Data:\n    import chronicler.branch\n",
    "class Data:\n    if enabled:\n        from chronicler.branch import State\n",
    "class Data:\n    class Nested:\n        import chronicler.branch\n",
    "if TYPE_CHECKING:\n    pass\nelse:\n    import chronicler.branch\n",
])
def test_unsupported_import_constructs_require_source_review(tmp_path, text):
    _source(tmp_path, {"__init__.py": "", "models.py": text})
    with pytest.raises(ValueError, match="source review"):
        inventory.inventory(tmp_path)


@pytest.mark.parametrize("name", ["../models", "chronicler...models", "other.models", False])
def test_module_names_cannot_escape_the_package(tmp_path, name):
    with pytest.raises(ValueError, match="module name"):
        inventory._module_path(tmp_path, name)


def test_missing_transitive_module_and_symlinked_source_are_not_inventory_success(tmp_path):
    package = _source(tmp_path, {"__init__.py": "", "models.py": "from chronicler.missing import State\n"})
    with pytest.raises(ValueError, match="regular"):
        inventory.inventory(tmp_path)
    (package / "models.py").unlink()
    target = tmp_path / "outside.py"
    target.write_text("class State: pass\n")
    (package / "models.py").symlink_to(target)
    with pytest.raises(ValueError, match="regular"):
        inventory.inventory(tmp_path)


@pytest.mark.parametrize("limit", ["MAX_FILES", "MAX_SOURCE_BYTES", "MAX_PACKAGE_BYTES", "MAX_MODULES"])
def test_all_source_inventory_bounds_fail_closed(tmp_path, monkeypatch, limit):
    _source(tmp_path, {"__init__.py": "# package\n", "models.py": "class WorldState: pass\n"})
    monkeypatch.setattr(inventory, limit, 1)
    with pytest.raises(ValueError, match="limit"):
        inventory.inventory(tmp_path)


def test_changed_source_between_package_hashing_and_ast_read_is_refused(tmp_path, monkeypatch):
    package = _source(tmp_path, {"__init__.py": "", "models.py": "class WorldState: pass\n"})
    original = inventory._read_source
    calls = 0

    def changing(path, root):
        nonlocal calls
        calls += 1
        if calls == 3:
            (package / "models.py").write_text("class Changed: pass\n")
        return original(path, root)

    monkeypatch.setattr(inventory, "_read_source", changing)
    with pytest.raises(ValueError, match="changed"):
        inventory.inventory(tmp_path)
