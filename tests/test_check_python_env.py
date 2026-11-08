"""Environment check logic with fake finders: no native import, no child process."""
import hashlib
import importlib.util
from importlib.machinery import EXTENSION_SUFFIXES, ExtensionFileLoader, ModuleSpec, SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_python_env.py"
CLASSES = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("check_python_env_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finder(specs):
    """A find_spec that records names and raises any exception it is given."""
    def find_spec(name):
        find_spec.calls.append(name)
        found = specs.get(name)
        if isinstance(found, Exception):
            raise found
        return found
    find_spec.calls = []
    return find_spec


def no_import(name):
    raise AssertionError(f"the check imported {name}")


def chronicler_spec(origin=ROOT / "src/chronicler/__init__.py"):
    return ModuleSpec("chronicler", None, origin=str(origin), is_package=True)


@pytest.fixture
def scripts_dir(tmp_path):
    directory = tmp_path / "bin"
    directory.mkdir()
    (directory / "chronicler").write_text("#!console script\n")
    return directory


@pytest.fixture
def native_package(tmp_path):
    package = tmp_path / "site" / "chronicler_agents"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise AssertionError('never executed')\n")
    compiled = package / f"chronicler_agents{EXTENSION_SUFFIXES[0]}"
    compiled.write_bytes(b"inert bytes standing in for a compiled extension")
    spec = ModuleSpec("chronicler_agents", None, origin=str(package / "__init__.py"), is_package=True)
    spec.submodule_search_locations = [str(package)]
    return spec, compiled


def compiled_modules(path, *, loader=None, package_classes=None, module_classes=None):
    classes = {name: type(name, (), {}) for name in CLASSES}
    loader = ExtensionFileLoader("chronicler_agents.chronicler_agents", str(path)) if loader is None else loader
    module = SimpleNamespace(__file__=str(path), __spec__=SimpleNamespace(loader=loader),
                             **(classes if module_classes is None else module_classes))
    package = SimpleNamespace(**(classes if package_classes is None else package_classes))
    return {"chronicler_agents": package, "chronicler_agents.chronicler_agents": module}


def test_no_native_passes_with_only_top_level_lookups(tool, scripts_dir):
    find_spec = finder({"chronicler": chronicler_spec()})
    report = tool.evaluate("no-native", find_spec=find_spec, import_module=no_import,
                           version=lambda name: None, scripts_dir=scripts_dir)
    assert report["passed"] is True
    assert report["checks"] == {"chronicler resolves to this checkout's src": True,
                                "chronicler console script is installed": True,
                                "chronicler_agents is absent": True}
    assert sorted(find_spec.calls) == ["chronicler", "chronicler_agents"]
    assert report["native"] == {"importable": False, "lookup_error": None}
    assert "Result: PASS (expected no-native)" in tool.render(report)


def test_no_native_reports_a_stale_extension_by_path_and_hash_without_importing(tool, scripts_dir, native_package):
    spec, compiled = native_package
    find_spec = finder({"chronicler": chronicler_spec(), "chronicler_agents": spec})
    report = tool.evaluate("no-native", find_spec=find_spec, import_module=no_import,
                           version=lambda name: "0.1.0", scripts_dir=scripts_dir)
    assert report["passed"] is False
    assert report["checks"]["chronicler_agents is absent"] is False
    native = report["native"]
    assert native["origin"] == spec.origin and native["distribution_version"] == "0.1.0"
    assert native["compiled_files"] == [{"path": str(compiled), "bytes": compiled.stat().st_size,
                                         "sha256": hashlib.sha256(compiled.read_bytes()).hexdigest()}]
    assert "submodule" not in native and "classes" not in native
    assert all("." not in name for name in find_spec.calls)
    text = tool.render(report)
    assert "[FAIL] chronicler_agents is absent" in text and "uv sync --frozen" in text


def test_report_only_mode_describes_native_state_without_importing_or_checking_it(tool, scripts_dir, native_package):
    spec, compiled = native_package
    find_spec = finder({"chronicler": chronicler_spec(), "chronicler_agents": spec})
    report = tool.evaluate(None, find_spec=find_spec, import_module=no_import,
                           version=lambda name: None, scripts_dir=scripts_dir)
    assert report["passed"] is True
    assert set(report["checks"]) == {"chronicler resolves to this checkout's src",
                                     "chronicler console script is installed"}
    assert report["native"]["compiled_files"][0]["path"] == str(compiled)


def test_a_finder_that_holds_the_native_package_reads_as_absent(tool, scripts_dir):
    held = ModuleNotFoundError("Native runtime is held in this test lane", name="chronicler_agents")
    find_spec = finder({"chronicler": chronicler_spec(), "chronicler_agents": held})
    report = tool.evaluate("no-native", find_spec=find_spec, import_module=no_import,
                           version=lambda name: None, scripts_dir=scripts_dir)
    assert report["passed"] is True
    assert report["native"]["lookup_error"].startswith("ModuleNotFoundError: Native runtime is held")


def test_single_file_extension_module_is_its_own_compiled_file(tool, tmp_path):
    path = tmp_path / f"chronicler_agents{EXTENSION_SUFFIXES[0]}"
    path.write_bytes(b"inert")
    assert tool.compiled_files(ModuleSpec("chronicler_agents", None, origin=str(path))) == [path]


def test_native_passes_for_the_compiled_submodule_and_its_real_classes(tool, scripts_dir, native_package):
    spec, compiled = native_package
    modules = compiled_modules(compiled)
    report = tool.evaluate("native", find_spec=finder({"chronicler": chronicler_spec(), "chronicler_agents": spec}),
                           import_module=modules.__getitem__, version=lambda name: "0.1.0", scripts_dir=scripts_dir)
    assert report["passed"] is True
    assert report["native"]["submodule"] == {"path": str(compiled), "bytes": compiled.stat().st_size,
                                             "sha256": hashlib.sha256(compiled.read_bytes()).hexdigest(),
                                             "compiled": True}
    assert report["native"]["classes"] == dict.fromkeys(CLASSES, True)


@pytest.mark.parametrize("change", ["absent", "import_error", "source_loader", "suffix", "function", "shadowed"])
def test_native_refuses_absence_stubs_and_shadowed_classes(tool, scripts_dir, native_package, tmp_path, change):
    spec, compiled = native_package
    specs = {"chronicler": chronicler_spec(), "chronicler_agents": spec}
    modules = compiled_modules(compiled)
    if change == "absent":
        del specs["chronicler_agents"]
    elif change == "import_error":
        modules = {}
    elif change == "source_loader":
        stub = tmp_path / "chronicler_agents.py"
        stub.write_text("")
        modules = compiled_modules(stub, loader=SourceFileLoader("chronicler_agents.chronicler_agents", str(stub)))
    elif change == "suffix":
        modules = compiled_modules(tmp_path / "chronicler_agents.txt")
    elif change == "function":
        classes = {name: (lambda: None) for name in CLASSES}
        modules = compiled_modules(compiled, package_classes=classes, module_classes=classes)
    else:
        modules = compiled_modules(compiled, package_classes={name: type(name, (), {}) for name in CLASSES})

    def import_module(name):
        if name not in modules:
            raise ImportError(f"No module named {name!r}")
        return modules[name]

    report = tool.evaluate("native", find_spec=finder(specs), import_module=import_module,
                           version=lambda name: None, scripts_dir=scripts_dir)
    importable = report["checks"]["chronicler_agents is importable"]
    compiled = report["checks"]["chronicler_agents.chronicler_agents is a compiled extension"]
    classes = report["checks"][", ".join(CLASSES) + " are the compiled classes"]
    expected = {"absent": (False, False, False), "import_error": (False, False, False),
                "source_loader": (True, False, True), "suffix": (True, False, True),
                "function": (True, True, False), "shadowed": (True, True, False)}[change]
    assert (importable, compiled, classes) == expected
    assert report["passed"] is False
    assert report["checks"]["chronicler resolves to this checkout's src"] is True
    assert ("maturin develop" in tool.render(report)) is (not compiled)


def test_chronicler_from_another_checkout_or_without_its_console_script_fails(tool, tmp_path):
    other = tmp_path / "other/src/chronicler/__init__.py"
    other.parent.mkdir(parents=True)
    other.write_text("")
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    report = tool.evaluate("no-native", find_spec=finder({"chronicler": chronicler_spec(other)}),
                           import_module=no_import, version=lambda name: None, scripts_dir=empty)
    assert report["passed"] is False
    assert report["checks"]["chronicler resolves to this checkout's src"] is False
    assert report["checks"]["chronicler console script is installed"] is False
    assert report["checks"]["chronicler_agents is absent"] is True
    assert "PYTHONPATH=src" in tool.render(report)


def test_main_exit_status_follows_the_report(tool, monkeypatch, capsys):
    with pytest.raises(ValueError):
        tool.evaluate("maybe")
    seen = []
    for passed, status in ((True, 0), (False, 1)):
        report = {"passed": passed, "checks": {}}
        monkeypatch.setattr(tool, "evaluate", lambda expect, report=report: seen.append(expect) or report)
        assert tool.main(["--expect", "no-native", "--json"]) == status
    assert seen == ["no-native", "no-native"]
    assert '"passed": false' in capsys.readouterr().out
    with pytest.raises(SystemExit):
        tool.main(["--expect", "maybe"])


def test_setup_scripts_build_into_the_target_venv_and_check_it():
    unix = (ROOT / "setup.sh").read_text()
    windows = (ROOT / "setup.bat").read_text()
    cloud = (ROOT / "scripts/cloud_setup.sh").read_text()
    assert "uv sync --frozen" in unix and "uv sync --frozen" in windows and "uv sync" in cloud
    # The build target is .venv by default and the native venv with --native-venv.
    assert "if [ \"$SEPARATE_NATIVE\" -eq 1 ]; then TARGET_VENV=$NATIVE_VENV; else TARGET_VENV=$VENV; fi" in unix
    assert 'if %SEPARATE_NATIVE%==1 set "TARGET_VENV=%NATIVE_VENV%"' in windows
    assert unix.index('source "$(venv_activate "$TARGET_VENV")"') < unix.index("python -m maturin develop")
    assert windows.index('call "%TARGET_VENV%\\Scripts\\activate.bat"') < windows.index("python -m maturin develop")
    for script in (unix, windows, cloud):
        assert "scripts/check_python_env.py --expect no-native" in script.replace("\\", "/")
    assert '"$NATIVE_PY" scripts/check_python_env.py --expect native' in unix
    assert '"%TARGET_VENV%\\Scripts\\python.exe" scripts\\check_python_env.py --expect native' in windows
    # Cloud setup warns and continues: its checks run through step().
    assert 'step "check .venv (no native)" .venv/bin/python scripts/check_python_env.py --expect no-native' in cloud


CPUINFO = """processor\t: 0
model name\t: AMD Ryzen 9 9950X 16-Core Processor
physical id\t: 0
core id\t: 0
flags\t\t: fpu sse2 avx2 avx512f

processor\t: 1
model name\t: AMD Ryzen 9 9950X 16-Core Processor
physical id\t: 0
core id\t: 0
flags\t\t: fpu sse2 avx2 avx512f

processor\t: 2
physical id\t: 0
core id\t: 1

processor\t: 3
physical id\t: 0
core id\t: 1
"""


def test_cpu_info_counts_physical_cores_and_vector_flags(tool):
    info = tool.cpu_info(CPUINFO)
    assert info == {"model": "AMD Ryzen 9 9950X 16-Core Processor", "physical_cores": 2,
                    "avx2": True, "avx512f": True}
    zen2 = tool.cpu_info(CPUINFO.replace(" avx512f", ""))
    assert zen2["avx2"] is True and zen2["avx512f"] is False
    assert tool.cpu_info(None)["physical_cores"] is None and tool.cpu_info("")["avx2"] is None


def no_child_process(*args, **kwargs):
    raise AssertionError("the machine report started a child process")


def test_machine_report_without_tools_starts_no_child_process(tool, monkeypatch):
    files = {"/proc/cpuinfo": CPUINFO, "/etc/os-release": 'NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 24.04.1 LTS"\n',
             "/proc/sys/kernel/osrelease": "6.8.0-48-generic\n",
             "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor": "performance\n"}
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    monkeypatch.delenv("RAYON_NUM_THREADS", raising=False)
    sizes = {"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": 1024}
    machine = tool.machine_report(read=lambda path: files.get(path.as_posix()), which=lambda name: None,
                                  run=no_child_process, sysconf=sizes.__getitem__, budget=lambda: 31)
    assert machine["cpu"]["physical_cores"] == 2 and machine["cpu"]["avx512f"] is True
    assert machine["batch_cpu_budget"] == 31 and machine["memory_bytes"] == 4096 * 1024
    assert machine["os"]["distribution"] == "Ubuntu 24.04.1 LTS" and machine["os"]["wsl"] is False
    assert machine["os"]["cpu_governor"] == "performance"
    assert machine["tools"] == {name: "absent" for name in tool.TOOLS}
    assert machine["git"] == {"head": None, "dirty": None}
    assert machine["environment"]["PYTHONHASHSEED"] == "0" and machine["environment"]["RAYON_NUM_THREADS"] is None
    wsl = tool.machine_report(read=lambda path: "5.15.153.1-microsoft-standard-WSL2" if "osrelease" in path.name else None,
                              which=lambda name: None, run=no_child_process, sysconf=None, budget=lambda: 1)
    assert wsl["os"]["wsl"] is True and wsl["memory_bytes"] is None


def test_tool_version_reports_the_first_line_or_the_failure(tool):
    def run(command, **kwargs):
        assert command == ["/usr/bin/rustc", "--version"] and kwargs["timeout"] == 5
        return SimpleNamespace(stdout="rustc 1.85.0 (4d91de4e4 2025-02-17)\nmore\n", stderr="", returncode=0)
    assert tool.tool_version("rustc", which=lambda name: f"/usr/bin/{name}", run=run) == "rustc 1.85.0 (4d91de4e4 2025-02-17)"
    def fails(command, **kwargs):
        raise tool.subprocess.TimeoutExpired(command, 5)
    assert tool.tool_version("node", which=lambda name: "/usr/bin/node", run=fails) == "error: TimeoutExpired"
    assert tool.tool_version("uv", which=lambda name: None, run=no_child_process) == "absent"


def test_machine_section_is_rendered_and_never_changes_the_result(tool, monkeypatch, capsys):
    machine = tool.machine_report(read=lambda path: CPUINFO if path.name == "cpuinfo" else None,
                                  which=lambda name: None, run=no_child_process, sysconf=None, budget=lambda: 31)
    report = {"passed": True, "checks": {}}
    monkeypatch.setattr(tool, "evaluate", lambda expect: dict(report))
    monkeypatch.setattr(tool, "machine_report", lambda: machine)
    assert tool.main(["--machine", "--json"]) == 0
    assert '"batch_cpu_budget": 31' in capsys.readouterr().out
    lines = tool.render_machine(machine)
    assert lines[0].startswith("Machine:       AMD Ryzen 9 9950X") and "AVX-512 yes" in lines[0]
    assert any(line.startswith("Batch budget:  31 workers") for line in lines)
