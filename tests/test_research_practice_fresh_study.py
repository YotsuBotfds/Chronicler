"""Closed dormant workflow/source metadata only; no runtime or World imports."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs/experiments/research-practice-fresh-study-cbf-workflow.yml"
REGISTRATION = ROOT / "docs/experiments/research-practice-fresh-study-cbf-registration-2026-10-29.md"
ACTIVE_PATH = ".github/workflows/research-practice-fresh-study-cbf.yml"
BRANCH = "lead/cloud-fresh-practice-study-cbf-20261029"
GUARD = "$" + "{{ github.event_name == 'push' && github.ref == 'refs/heads/" + BRANCH + "' && github.run_attempt == 1 }}"
PREPARED_GUARD = GUARD.replace("{{ ", "{{ false && ", 1)
BODY_SHA256 = "041990fb76a15448f762956d9a10ffbb4b10576408122d65b823c0af0c5f2a3d"
REGISTRATION_SHA256 = "80360b2e5b93e67d489b4f68c106d5043eed436f53330cbf004a08f565f20fb4"
RUNTIME_SHA256 = {
    "scripts/research_practice_recorder.py": "c351b11eee75950b4d39ca46954fe2364664a62a529c71ada1b82d9804ba8c1c",
    "scripts/research_practice_adapter.py": "5b428eaf71fdbdbfc33ca913d52a39c7f954c9bdb41ae1f281a0b96a3c5d76db",
    "scripts/research_practice_contract.py": "00138cd4c558b1b1a3fc5b78eb80b80c5c8bfe17b27a30d2c3d4d95840cc6b91",
    "scripts/run_research_practice_continuation.py": "88134437e33e9287836b3922d7aa2873d9ac1a0658bbe6bd1598682e528cc7e8",
    "scripts/read_research_practice_continuation.py": "ec483f7a07ef254c4cc99072e95214df9af4eb7a6ce2f048de87e032cbf8e33e",
    "scripts/research_practice_trace_reader.py": "0f69431256c224e72603de68a8837acd87cea21b1c0ad74a68c0c3576009ebd0",
    "scripts/research_practice_resources.py": "44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2",
    "scripts/research_practice_runtime_policy.py": "f98495d350086258cd06dddf5644c0bc05eae4c7c35065866ec8a583a531331c",
    "scripts/fetch_research_practice_wheel.py": "2c21e6f6697c23b8c9f66626a2cf8ec28966e4d7a159239088c573a40ada2051",
    "docs/experiments/natural-practice-observer-registration-2026-10-29.md": "cc0199a6be414a9c86cafead857ffb7af51f2973d4aba8f62bc0a3e7a4bc34b2",
    "scripts/run_research_practice_cp60_proof.py": "e20e880645a49ce3435018a0aea739282a85a83d0d735946ef844de7f0acc975"
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parsed(raw):
    value = yaml.safe_load(raw)
    if True in value:
        assert "on" not in value
        value["on"] = value.pop(True)
    return value


def workflow_contract(value):
    value = deepcopy(value)
    assert value["on"] == {"push": {"branches": [BRANCH], "paths": [ACTIVE_PATH]}}
    job = value["jobs"]["natural-study"]
    assert (value["name"], job["if"]) in (
        ("Prepared fresh natural practice study CBF", PREPARED_GUARD),
        ("Fresh natural practice study CBF", GUARD))
    value.pop("name")
    job.pop("if")
    assert digest(value) == BODY_SHA256


def active_copy():
    value = parsed(TEMPLATE.read_bytes())
    value["name"] = "Fresh natural practice study CBF"
    value["jobs"]["natural-study"]["if"] = GUARD
    return value


def registration():
    return json.loads(REGISTRATION.read_text().split("```json\n")[1].split("\n```")[0])


def test_dormant_template_and_exact_future_active_copy():
    value = parsed(TEMPLATE.read_bytes())
    assert value["name"] == "Prepared fresh natural practice study CBF"
    assert value["jobs"]["natural-study"]["if"] == PREPARED_GUARD
    workflow_contract(value)
    workflow_contract(active_copy())
    if (ROOT / ACTIVE_PATH).exists():
        actual = parsed((ROOT / ACTIVE_PATH).read_bytes())
        workflow_contract(actual)
        assert actual == active_copy()


@pytest.mark.parametrize("fault", ["branch", "path", "dispatch", "guard", "producer", "python", "caps", "mode", "subset", "policy", "retention", "raw_omission"])
def test_offpolicy_workflow_or_copy_is_rejected(fault):
    value = active_copy()
    job = value["jobs"]["natural-study"]
    steps = job["steps"]
    if fault == "branch": value["on"]["push"]["branches"] = ["main"]
    elif fault == "path": value["on"]["push"]["paths"] = ["**"]
    elif fault == "dispatch": value["on"]["workflow_dispatch"] = {}
    elif fault == "guard": job["if"] = "$" + "{{ true }}"
    elif fault == "producer": steps[1]["with"]["ref"] = "main"
    elif fault == "python": steps[2]["with"]["python-version"] = "3.13"
    elif fault == "caps": value["env"]["PYTHON_CPU_COUNT"] = "2"
    elif fault == "mode":
        step = next(s for s in steps if "run_research_practice_cp60_proof.py freeze" in s.get("run", ""))
        step["run"] = step["run"].replace(".py freeze", ".py run")
    elif fault == "subset":
        step = next(s for s in steps if s.get("id") == "study")
        step["run"] += " --seed 2001"
    elif fault == "policy":
        step = next(s for s in steps if s.get("id") == "study")
        step["run"] = step["run"].replace("cloud-cbf-3ee", "local-fb20")
    elif fault == "retention": steps[-1]["with"]["retention-days"] = 1
    else: steps.pop()
    with pytest.raises(AssertionError):
        workflow_contract(value)


def test_fixed_cost_all_rows_and_fresh_facts_unmeasured():
    value = registration()
    assert digest(value) == REGISTRATION_SHA256
    assert value["seeds"] == list(range(2000, 2008))
    assert value["roles"] == ["parent", "active", "pause_new_trials"]
    rows = [(seed, role, value["role_ticks"][role]) for seed in value["seeds"] for role in value["roles"]]
    assert len(rows) == value["executions"] == 24
    assert sum(ticks for _, _, ticks in rows) == value["physics_ticks"] == 3360
    assert all(sum(t for s, _, t in rows if s == seed) == 420 for seed in value["seeds"])
    assert value["expected_frames"] * 16 == value["selected_slots"] == 53760
    assert value["payment_witness_limit_per_role"] == 32
    assert all(v is None for k, v in value["fresh_observed_facts"].items() if k != "efficacy_qualified")
    assert value["fresh_observed_facts"]["efficacy_qualified"] is False


@pytest.mark.parametrize("path,sha256", sorted(RUNTIME_SHA256.items()))
def test_control_runtime_unchanged(path, sha256):
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha256


def test_metadata_only_freeze_is_compatible_and_has_no_proof_window():
    source = ast.parse((ROOT / "scripts/run_research_practice_cp60_proof.py").read_bytes())
    freeze = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "metadata_freeze")
    names = {n.id for n in ast.walk(freeze) if isinstance(n, ast.Name)}
    assert not names & {"SEED", "FORK", "END", "ProofOwner", "worker", "run", "WorldState"}
    calls = [ast.unparse(n.func) for n in ast.walk(freeze) if isinstance(n, ast.Call)]
    assert calls.count("cls.checkpoint_schema") == 1  # one source call in fixed3-class loop
    assert "R.identity" in calls and calls.count("C.write") == 2
    text = ast.unparse(freeze)
    assert 'proof-metadata-observation.json' in text
    assert 'R.identity(source, C.P.DEFAULT_POLICY, options.wheel_receipt)' in text
    assert 'C.write(path, frozen)' in text
    runner = ast.parse((ROOT / "scripts/run_research_practice_continuation.py").read_bytes())
    verify = next(n for n in runner.body if isinstance(n, ast.FunctionDef) and n.name == "verify_freeze")
    assert "identity(source, policy_name, wheel_receipt)" in ast.unparse(verify)


def test_stage_order_exact_commands_and_negative_publication():
    value = parsed(TEMPLATE.read_bytes())
    steps = value["jobs"]["natural-study"]["steps"]
    runs = [s.get("run", "") for s in steps]
    pure = next(i for i, text in enumerate(runs) if "-m pytest" in text)
    wheel = next(i for i, text in enumerate(runs) if "fetch_research_practice_wheel.py" in text)
    install = next(i for i, text in enumerate(runs) if "uv pip install" in text)
    freeze = next(i for i, text in enumerate(runs) if "run_research_practice_cp60_proof.py freeze" in text)
    study = next(i for i, s in enumerate(steps) if s.get("id") == "study")
    read = next(i for i, text in enumerate(runs) if "read_research_practice_continuation.py" in text)
    assert pure < wheel < install < freeze < study < read < len(steps)-2
    assert "timeout --signal=KILL 110s" in runs[pure]
    assert "test_research_practice_fresh_study.py" in runs[pure]
    assert all(flag not in runs[study] for flag in ("--seed", "--role", "--turns"))
    assert "--runtime-policy cloud-cbf-3ee" in runs[study] and "--runtime-policy cloud-cbf-3ee" in runs[read]
    assert all("maturin" not in text and "cargo " not in text for text in runs)
    assert all(s["if"] == "always()" for s in steps[-2:])
    assert steps[-2:][0]["with"]["name"].startswith("fresh-practice-study-readout-")
    assert steps[-1]["with"]["name"].startswith("fresh-practice-study-raw-")
    for suffix in ("/practice-study-evidence/", "/practice-study-readout/", "/proof-metadata-observation.json"):
        assert suffix in steps[-1]["with"]["path"]


def test_bounded_offline_selector_lists_the_contract_once():
    tree = ast.parse((ROOT / "scripts/run_python_oracle_checks.py").read_bytes())
    chunks = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "CHUNKS" for t in n.targets))
    paths = [path for selection in chunks.values() for path in selection]
    assert len(paths) == len(set(paths))
    assert paths.count("tests/test_research_practice_fresh_study.py") == 1
    assert "tests/test_research_practice_fresh_study.py" in chunks["practice-growth-observer"]
    assert "CHUNK_LIMIT_SECONDS = 110" in (ROOT / "scripts/run_python_oracle_checks.py").read_text()
