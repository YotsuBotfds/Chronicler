"""Synthetic artifact contracts, not generated worlds or scientific outcomes."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import random
import struct
import zlib

import pytest

from test_research_natural_continuation import modules

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def synthetic(modules, tmp_path, monkeypatch):
    # Reuse the script loader fixture without importing any native runtime.
    c, runner, reader = modules
    import numpy as np
    from chronicler.main import _build_parser
    from chronicler.batch_manifest import simulation_config
    root = tmp_path / "synthetic-artifacts"
    root.mkdir()
    schema = {"AgentSimulator": dict(version=1, fingerprint="synthetic-agent", schema_sha256="synthetic-schema"),
        "EcologySimulator": dict(version=1, fingerprint="synthetic-ecology", schema_sha256="unused"),
        "PoliticsSimulator": dict(version=1, fingerprint="synthetic-politics", schema_sha256="unused")}
    observed_runtime = dict(source=dict(package_digest="synthetic-package", git_sha=c.SOURCE),
        native=dict(status="found", sha256=c.NATIVE, bytes=3), available_compiled_classes=schema,
        environment=dict(python="3.13.5", implementation="CPython", machine="synthetic", affinity_cpu_count=1,
                         thread_env={"PYTHONHASHSEED": "0"}, packages={}))
    frozen = dict(runtime=observed_runtime, controls={name: c.sha(ROOT / name) for name in c.CONTROL_FILES})
    registration = dict(path=str((ROOT / c.REGISTRATION).resolve()), sha256=frozen["controls"][c.REGISTRATION])
    identity = dict(source=observed_runtime["source"], native={**observed_runtime["native"],
        "state_layouts": {"agent": "v1:synthetic-agent", "ecology": "v1:synthetic-ecology", "politics": "v1:synthetic-politics"}},
        environment={**observed_runtime["environment"], "hash_seed": "0"})
    python = random.Random(2000).getstate()
    numpy = np.random.RandomState(2000).get_state()
    rng = dict(python=[python[0], list(python[1]), python[2]], numpy=[numpy[0], numpy[1].tolist(), *numpy[2:]])
    plan = dict(schema_version=1, rule="finite-retained-v1", enabled=True, enabled_turn=0, policy_changed_turn=0,
        next_open_turn=0, origin_cursor=-1, cycles=[], blocked_reason="", blocked_turn=None,
        host_seal="0" * 64, academy_births=[])
    science = dict(seat_ids=[], claims=[], trials=[], proposals=[], receipts=[], trial_spent=0, effort_spent=0,
        research_agendas=plan, **c.CONTROLS)
    def header(turn, config, role):
        flags = dict(scholarship=True, techniques=True, scientific_claims=True, health_care=False,
            harvest_forecasts=False, ritual_gatherings=False, transaction_receipts=False,
            scientific_research_agendas=role != "pause_new_trials")
        return dict(format="chronicler-run-checkpoint", version=1, turn=turn, seed=2000, exact=role == "parent",
                    identity=identity, flags=flags, run_config=config, lineage=config["lineage"])
    def checkpoint(path, value):
        value = deepcopy(value)
        body, sections = b"", []
        for name, raw in (("python", b"synthetic opaque bytes; deliberately never unpickled"),
                          ("native.agent.0", b"synthetic opaque native bytes; deliberately never loaded")):
            packed = zlib.compress(raw)
            sections.append(dict(name=name, offset=len(body), length=len(packed), raw_length=len(raw),
                                 sha256=c.hashlib.sha256(packed).hexdigest()))
            body += packed
        value["sections"] = sections
        raw_header = c.encoded(value)
        path.write_bytes(c.MAGIC + struct.pack("<I", len(raw_header)) + raw_header + body)
        return c.checkpoint_sections(path)
    seed_root = root / "seed-2000"
    for role in c.ROLES:
        (seed_root / role).mkdir(parents=True)
    parent_folder = seed_root / "parent"
    parent_receipt = dict(schema_version=1, experiment=c.EXPERIMENT, cohort="development", feature="scientific_claims",
        arm="parent", intervention_fork=False, applied_before_turn=0, seed=2000,
        controls_before=dict(c.CONTROLS, publication_rule="current-context-v1"), controls_after=dict(c.CONTROLS),
        parent_checkpoint=None, registration=registration, source=observed_runtime["source"], native=observed_runtime["native"],
        previous_experiment=None, research_policy=dict(before={"mode": plan["rule"], **plan},
            after={"mode": plan["rule"], **plan}, requested_enabled=None))
    simulation = simulation_config(_build_parser().parse_args(runner.simulation_args(parent_folder, 2000, "parent")))
    parent_config = dict(simulation_args=simulation, expansion_experiment=parent_receipt, resume_info=None, lineage=[])
    parent_path = parent_folder / "checkpoint_turn_60.ckpt"
    parent_header, parent_sections = checkpoint(parent_path, header(60, parent_config, "parent"))
    c.write(parent_folder / "boundary-rng.json", dict(seed=2000, turn=60, checkpoint_sha256=c.sha(parent_path),
        checkpoint_sections=parent_sections, state=rng, state_sha256=c.digest(rng), producer_runtime=observed_runtime,
        controls_sha256=c.digest(frozen["controls"])))
    c.write(parent_folder / "initial-rng.json", dict(seed=2000, state=rng))
    def history(role):
        return [dict(turn=turn, scientific_claims=dict(source_turn=turn - 1, allocations=[],
            research_agendas=dict(rule="finite-retained-v1", enabled=role != "pause_new_trials" or turn <= 60)))
            for turn in range(1, 181)]
    parent_world = dict(seed=2000, turn=60, agent_mode="hybrid", regions=[{} for _ in range(8)],
                        civilizations=[{} for _ in range(4)], scientific_claims=deepcopy(science), events_timeline=[])
    restore = dict(checkpoint_sha256=c.sha(parent_path), header=parent_header, run_config=parent_config,
        world=parent_world, history=history("parent")[:60], native_sections={"native.agent.0": {
            **parent_sections["native.agent.0"], "class_name": "AgentSimulator", **schema["AgentSimulator"]}})
    for role in c.ROLES:
        folder = seed_root / role
        current_science = deepcopy(science)
        receipt, config, resume = deepcopy(parent_receipt), deepcopy(parent_config), None
        if role != "parent":
            expected_parent = dict(path=str(parent_path.resolve()), sha256=c.sha(parent_path), turn=60, seed=2000,
                identity=parent_header["identity"], flags=parent_header["flags"], exact=True)
            receipt.update(arm=role, intervention_fork=True, applied_before_turn=60,
                controls_before=dict(c.CONTROLS), parent_checkpoint=expected_parent, previous_experiment=deepcopy(parent_receipt))
            receipt["research_policy"]["requested_enabled"] = role == "active"
            if role == "pause_new_trials":
                current_science["research_agendas"].update(enabled=False, policy_changed_turn=60)
                receipt["research_policy"]["after"].update(enabled=False, policy_changed_turn=60)
            resume = dict(kind="experiment-fork", exact=False, turn=60)
            config.update(expansion_experiment=receipt, resume_info=resume, lineage=[
                dict(resumed_at=60, kind="checkpoint", exact=True),
                dict(resumed_at=60, kind="experiment-fork", exact=False, experiment=receipt)])
            config["simulation_args"]["scientific_research_agendas"] = role == "active"
            c.write(folder / "restore.json", restore)
            c.write(folder / "restored-rng.json", dict(sidecar_sha256=c.sha(parent_folder / "boundary-rng.json"), state_sha256=c.digest(rng)))
        world = {**deepcopy(parent_world), "turn": 180, "scientific_claims": current_science}
        rows = history(role)
        metadata = dict(seed=2000, total_turns=180, generated_at="2026-10-29T00:00:00+00:00", expansion_experiment=receipt)
        if resume:
            metadata["resume"] = resume
        bundle = dict(world_state=world, history=rows, events_timeline=[], metadata=metadata)
        c.write(folder / "state.json", world)
        c.write(folder / "chronicle_bundle.json", bundle)
        h, sections = checkpoint(folder / "checkpoint_turn_180.ckpt", header(180, config, role))
        native_record = {"native.agent.0": {**sections["native.agent.0"], "class_name": "AgentSimulator", **schema["AgentSimulator"]}}
        (folder / "native.agent.0-final.bin").write_bytes(b"synthetic opaque native bytes; deliberately never loaded")
        c.write(folder / "worker-identity.json", dict(identities_stable=True, before=frozen, after=frozen))
        c.write(folder / "cleanup.json", dict(complete=True))
        c.write(folder / "request.json", runner.request(2000, role, registration, parent_path if role != "parent" else None))
        summary = dict(seed=2000, role=role, execution_complete=True, final_turn=180,
            actual_physics_ticks=180 if role == "parent" else 120, header=h, run_config=config,
            native_sections=native_record, raw_world_sha256=c.digest(world), raw_history_sha256=c.digest(rows),
            final_rng=rng, final_rng_sha256=c.digest(rng), experiment_receipt=receipt,
            pause=c.pause_archive(science, current_science) if role == "pause_new_trials" else None,
            exposure=c.exposure(current_science, rows))
        c.write(folder / "worker-summary.json", summary)
    from chronicler.bundle_codec import decode_bundle
    return c, reader, root, frozen, decode_bundle


def test_synthetic_complete_roles_reconcile_native_checkpoint_rng_and_null_exposure(synthetic):
    c, reader, root, frozen, decode = synthetic
    roles = {role: reader.inspect_role(root, 2000, role, frozen, decode) for role in c.ROLES}
    assert all(row["exposure"]["new_trials"] == 0 for row in roles.values())
    compared = reader.active_identity(roles["parent"], roles["active"], c.same)
    assert compared["file_set_equal"] and all(compared["files"].values())
    assert compared["normalized_bundle_differences"] == []
    assert roles["pause_new_trials"]["summary"]["pause"]["no_new_trial_funding"] is True


@pytest.mark.parametrize("field", ["publication", "rng", "native", "request"])
def test_readout_refuses_unregistered_control_or_broken_raw_link(synthetic, field):
    c, reader, root, frozen, decode = synthetic
    folder = root / "seed-2000/active"
    if field == "publication":
        bundle = c.read(folder / "chronicle_bundle.json")
        bundle["metadata"]["expansion_experiment"]["controls_after"]["publication_rule"] = "current-context-v1"
        (folder / "chronicle_bundle.json").write_bytes(c.encoded(bundle))
    elif field == "rng":
        restored = c.read(folder / "restored-rng.json")
        restored["state_sha256"] = "not-the-boundary"
        (folder / "restored-rng.json").write_bytes(c.encoded(restored))
    elif field == "native":
        (folder / "native.agent.0-final.bin").write_bytes(b"different native bytes")
    else:
        request = c.read(folder / "request.json")
        request["controls"]["research_enabled"] = False
        (folder / "request.json").write_bytes(c.encoded(request))
    with pytest.raises(c.ContractError):
        reader.inspect_role(root, 2000, "active", frozen, decode)
