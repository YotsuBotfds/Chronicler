"""Receipt contracts use inert bytes; actual compiled-class checks remain in CI."""
import hashlib
from pathlib import Path
import runpy
import zipfile

import pytest


SOURCE = "a" * 40


@pytest.fixture(scope="module")
def record_wheel():
    source = Path(__file__).resolve().parents[1] / "scripts/native_wheel_receipt.py"
    return runpy.run_path(str(source))["wheel_receipt"]


def _files(tmp_path, payload=b"inert native fixture", *, member=None):
    native = tmp_path / "runtime.cpython-313-x86_64-linux-gnu.so"
    native.write_bytes(b"inert native fixture")
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    wheel = wheel_dir / "runtime-1.0-cp313-linux.whl"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member or f"runtime/{native.name}", payload)
    return wheel_dir, wheel, native


def test_receipt_links_complete_wheel_and_installed_member_without_import(record_wheel, tmp_path):
    directory, wheel, native = _files(tmp_path)
    result = record_wheel(directory, native, SOURCE)
    assert result["source_commit"] == SOURCE
    assert result["wheel"] == {
        "filename": wheel.name, "bytes": wheel.stat().st_size,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "native_member": f"runtime/{native.name}",
    }
    expected = hashlib.sha256(native.read_bytes()).hexdigest()
    assert result["installed_native"]["sha256"] == result["installed_native"]["wheel_member_sha256"] == expected
    assert result["installed_native"]["bytes"] == native.stat().st_size
    assert "no reproducibility" in result["scope"]


@pytest.mark.parametrize("payload", [b"different", b"INERT NATIVE FIXTURE"])
def test_wrong_installed_bytes_never_receive_a_receipt(record_wheel, tmp_path, payload):
    directory, _wheel, native = _files(tmp_path, payload)
    with pytest.raises(ValueError, match="differs from installed"):
        record_wheel(directory, native, SOURCE)


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_wheels_refuse_instead_of_selecting_one(record_wheel, tmp_path, count):
    directory, wheel, native = _files(tmp_path)
    if count == 0:
        wheel.unlink()
    else:
        (directory / "stale.whl").write_bytes(wheel.read_bytes())
    with pytest.raises(ValueError, match="exactly one freshly built"):
        record_wheel(directory, native, SOURCE)


def test_missing_or_ambiguous_native_members_refuse(record_wheel, tmp_path):
    directory, wheel, native = _files(tmp_path, member="unrelated.py")
    with pytest.raises(ValueError, match="exactly one matching native"):
        record_wheel(directory, native, SOURCE)
    with zipfile.ZipFile(wheel, "w") as archive:
        for prefix in ("one", "two"):
            archive.writestr(f"{prefix}/{native.name}", native.read_bytes())
    with pytest.raises(ValueError, match="exactly one matching native"):
        record_wheel(directory, native, SOURCE)


@pytest.mark.parametrize("source", [None, True, "main", "a" * 39, "A" * 40, "a" * 41])
def test_nonexact_source_refuses_before_filesystem_reads(record_wheel, source):
    class ForbiddenPath:
        def glob(self, _pattern):
            pytest.fail("invalid source reached filesystem")
    with pytest.raises(ValueError, match="exact source commit"):
        record_wheel(ForbiddenPath(), ForbiddenPath(), source)


def test_workflow_keeps_full_test_command_and_publishes_wheel_separately():
    import ast
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/tests.yml").read_text())
    steps = workflow["jobs"]["python-native-tests"]["steps"]
    preflight = next(step["run"] for step in steps if step["name"] == "Run Python tests with real native extension preloaded")
    code = preflight.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    ast.parse(code)
    assert code.index("for name in (\"AgentSimulator\"") < code.index("record_wheel(") < code.index("pytest.main(")
    assert 'pytest.main(["-q", "--junitxml=ci-evidence/native.xml"])' in code
    result_step = next(step for step in steps if step["name"] == "Retain native Python test results")
    wheel_step = next(step for step in steps if step["name"] == "Retain the identified native wheel")
    assert result_step["with"]["path"] == "ci-evidence/"
    assert wheel_step["if"] == "always()"
    assert wheel_step["with"]["retention-days"] == 14
    assert set(wheel_step["with"]["path"].splitlines()) == {
        "ci-native-wheel/manifest.json", "chronicler-agents/target/wheels/*.whl",
    }
