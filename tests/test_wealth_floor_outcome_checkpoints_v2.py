"""Dictionary-only K2 metadata contracts; no CP sections or World fixtures."""
import ast
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from scripts import wealth_floor_outcome_checkpoints_v2 as K

ROOT = Path(__file__).resolve().parents[1]


def config(world="template"):
    return dict(worldgen=world, profile="subset", turns=125, seed_count=2, seed_start=42,
        regions=32 if world == "procedural" else 8, civs=10 if world == "procedural" else 4,
        parallel=2, checkpoint_turns=[101])


def header(cfg=None, current=None):
    cfg = config() if cfg is None else cfg
    return dict(format="chronicler-run-checkpoint", version=1, exact=True,
        seed=42, turn=101, num_turns=cfg["turns"], start_turn=0, lineage=[],
        identity=dict(source=dict(git_sha=K.B.CANDIDATE_SOURCE, package_digest=K.PACKAGE),
            native=dict(sha256=K.P.REVIEWED_BUILD["candidate_native_sha256"],
                state_layouts=dict(agent="v1:dcf0c34097c88451")),
            environment=dict(python=K.B.PYTHON_VERSION, implementation="CPython",
                affinity_cpu_count=2, thread_env=dict(K.THREADS))),
        world=dict(regions=cfg["regions"], civilizations=cfg["civs"] if current is None else current),
        run_config=dict(agent_mode="hybrid", validation_sidecar=True, lineage=[], resume_info=None,
            simulation_args=dict(civs=cfg["civs"])),
        sections=[dict(name="python", offset=0, length=7), dict(name="native.agent.0", offset=7, length=8)])


def test_policy_uses_actual_historical_ffi_bytes_and_metadata_scope():
    raw = (ROOT / "tests/fixtures/wealth_floor/source503_ffi_constants.py.txt").read_bytes()
    assert len(raw) == 3824
    assert hashlib.sha256(raw).hexdigest() == K.SOURCE_FFI_CONSTANTS_SHA256 == "61adb0b461ca89f1fe54f47bcb9448f1d5506948b92b7cde9e12007a52878f58"
    assert K.SOURCE_FFI_CONSTANTS_FILE == "src/chronicler/ffi_constants.py"
    assignments = {t.id: n.value for n in ast.parse(raw).body if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)}
    assert ast.literal_eval(assignments["MAX_CIV_RECORDS"]) == K.MAX_CIV_RECORDS == 254
    assert K.CIVILIZATION_METADATA_VERSION == 2 and K.CIVILIZATION_METADATA_SCOPE == "METADATA_ELIGIBILITY_ONLY"
    assert K.B.CANDIDATE_SOURCE == "503070175e3e78d9014add158ead8f16ce940843"
    assert K.PACKAGE == "49d78e877f981c4af2440e9dadbde7dd211e2fff0d2f1be68e7a4e5c10310e0a"


@pytest.mark.parametrize("world,current", [
    ("template", 4), ("template", 5), ("template", 254),
    ("procedural", 10), ("procedural", 11), ("procedural", 254),
])
def test_supported_current_record_growth_keeps_initial_configuration_exact(world, current):
    cfg = config(world); h = header(cfg, current); before = deepcopy(h)
    assert K.validate_header(h, cfg, 42, 101) is True
    assert h == before and h["run_config"]["simulation_args"]["civs"] == cfg["civs"]
    assert h["world"]["civilizations"] == current


@pytest.mark.parametrize("value", [3, 0, -1, 255, 10**20, True, False, 4.0, "4", None, float("nan"), float("inf")])
def test_current_record_count_refuses_unsupported_domain_and_lookalikes(value):
    h = header(); h["world"]["civilizations"] = value
    with pytest.raises(K.P.ProofRefused, match="civilization metadata"):
        K.validate_header(h, config(), 42, 101)


@pytest.mark.parametrize("case", ["world_missing", "current_missing", "args_missing", "initial_missing",
    "args_none", "args_list", "initial_bool", "initial_float", "initial_string", "initial_none",
    "initial_wrong", "config_float", "config_bool", "config_missing"])
def test_exact_saved_initial_and_registered_type_cannot_be_bypassed(case):
    cfg = config(); h = header(current=5); run = h["run_config"]
    if case == "world_missing": h.pop("world")
    elif case == "current_missing": h["world"].pop("civilizations")
    elif case == "args_missing": run.pop("simulation_args")
    elif case == "initial_missing": run["simulation_args"].pop("civs")
    elif case == "args_none": run["simulation_args"] = None
    elif case == "args_list": run["simulation_args"] = []
    elif case == "initial_bool": run["simulation_args"]["civs"] = True
    elif case == "initial_float": run["simulation_args"]["civs"] = 4.0
    elif case == "initial_string": run["simulation_args"]["civs"] = "4"
    elif case == "initial_none": run["simulation_args"]["civs"] = None
    elif case == "initial_wrong": run["simulation_args"]["civs"] = 5
    elif case == "config_float": cfg["civs"] = 4.0
    elif case == "config_bool": cfg["civs"] = True
    elif case == "config_missing": cfg.pop("civs")
    with pytest.raises(K.P.ProofRefused, match="civilization metadata"):
        K.validate_header(h, cfg, 42, 101)


@pytest.mark.parametrize("case", ["format", "exact", "old_source", "wrong_package", "old_native", "python",
    "implementation", "affinity", "affinity_bool", "thread_cap", "missing_cap", "hash_seed", "world", "mode",
    "sidecar", "version_bool", "seed", "turn", "horizon", "start", "sections", "header_lineage", "run_lineage", "resume"])
def test_original_non_count_refusals_survive_with_a_valid_growing_count(case):
    h = header(current=5); identity = h["identity"]; env = identity["environment"]; run = h["run_config"]
    if case == "format": h["format"] = "other"
    elif case == "exact": h["exact"] = False
    elif case == "old_source": identity["source"]["git_sha"] = K.B.BASELINE_SOURCE
    elif case == "wrong_package": identity["source"]["package_digest"] = "0" * 64
    elif case == "old_native": identity["native"]["sha256"] = K.B.OLD_NATIVE
    elif case == "python": env["python"] = "3.13.5"
    elif case == "implementation": env["implementation"] = "other"
    elif case == "affinity": env["affinity_cpu_count"] = 4
    elif case == "affinity_bool": env["affinity_cpu_count"] = True
    elif case == "thread_cap": env["thread_env"]["VECLIB_MAXIMUM_THREADS"] = "2"
    elif case == "missing_cap": env["thread_env"].pop("RAYON_NUM_THREADS")
    elif case == "hash_seed": env["thread_env"]["PYTHONHASHSEED"] = "1"
    elif case == "world": h["world"]["regions"] = 32
    elif case == "mode": run["agent_mode"] = "off"
    elif case == "sidecar": run["validation_sidecar"] = False
    elif case == "version_bool": h["version"] = True
    elif case == "seed": h["seed"] = 43
    elif case == "turn": h["turn"] = 100
    elif case == "horizon": h["num_turns"] = 126
    elif case == "start": h["start_turn"] = 1
    elif case == "sections": h["sections"] = h["sections"][:1]
    elif case == "header_lineage": h["lineage"] = [{"turn": 1}]
    elif case == "run_lineage": run["lineage"] = [{"turn": 1}]
    elif case == "resume": run["resume_info"] = {"exact": True}
    with pytest.raises(K.P.ProofRefused): K.validate_header(h, config(), 42, 101)


def test_original_helpers_retirement_and_old_K_are_preserved_exactly():
    raw = (ROOT / "scripts/wealth_floor_outcome_checkpoints.py").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "34aa2afe4ec99422f88fd12ef7832c78d942810846550c4cf5fc9b1b743d7961"
    old = ast.parse(raw); new = ast.parse(Path(K.__file__).read_bytes())
    def functions(tree): return {n.name: ast.dump(n, include_attributes=False) for n in tree.body if isinstance(n, ast.FunctionDef)}
    a, b = functions(old), functions(new)
    assert a.keys() == b.keys()
    assert {name for name in a if a[name] != b[name]} == {"validate_header"}
    # No default CLI, loader invocation, native import or candidate-source import.
    imports = [n.module or "" for n in ast.walk(new) if isinstance(n, ast.ImportFrom)]
    imports += [x.name for n in ast.walk(new) if isinstance(n, ast.Import) for x in n.names]
    assert not any(name.startswith(("chronicler", "chronicler_agents", "pickle", "zlib")) for name in imports)
    assert not any(isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
        and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__" for n in new.body)
