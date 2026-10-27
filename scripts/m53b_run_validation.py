#!/usr/bin/env python3
"""Run canonical M53b validation profiles.

Profiles:
- subset: 20 seeds x 200 turns, raw validation sidecars
- full: 200 seeds x 500 turns, validation sidecars + condensed summaries
- determinism-off: two duplicate-seed aggregate runs
- determinism-hybrid: two duplicate-seed hybrid runs

Worlds (``--worldgen``):
- template (default): the CLI's default world, 8 template regions and 4 civs
- procedural: heightmap/Voronoi geography with a fixed region and civ count
  per seed (``PROCEDURAL_WORLD``); its own seed and turn defaults
  (``PROCEDURAL_PROFILE_DEFAULTS``). See docs/integration/procedural-gates.md.

Every profile writes a new batch directory under ``--output-root`` (a used
one is refused before anything runs) with its ``batch_manifest.json``, which
``chronicler.validate`` checks; a baseline report of another cohort is
compared only with ``--exploratory-comparison``.
See docs/integration/validation-integrity.md.

Ablation oracles (``--ablation-oracles``, on by default in the full
profile, opt-in in the subset): the batch also writes an exact checkpoint
after each fork turn, and every seed is forked there with one native
decision term switched off (``chronicler.ablation_arms``: the need terms,
``needs``; the kin roots, ``kin_roots``) into ``ablation_<first seed>``
beside the batch. The needs oracle's ablation component (method 7) and the
cohort oracle's (method 4) read them: causal evidence, reported but not yet
required; ``--require-causal-oracles`` makes them decide. See
docs/integration/ablation-oracles.md.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chronicler.artifact_io import (
    ArtifactIOError,
    atomic_write_json,
    atomic_write_text,
    strict_json_dumps,
    strict_json_loads,
)
from chronicler.batch_manifest import (
    BUNDLE_FILENAME,
    MANIFEST_FILENAME,
    BatchDestinationError,
    check_batch_destination,
    finish_batch_manifest,
    new_batch_manifest,
    prepare_batch_dir,
    record_batch_run,
    write_batch_manifest,
)
from chronicler.ablation_arms import GATE_ARMS, checkpoint_turns, run_ablation_arms
from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown
from chronicler.validation_gate import (
    CAUSAL_ORACLES_FLAG,
    PROFILE_CHOICES,
    REQUIRED_ORACLES_BY_PROFILE,
    causal_oracles_required,
    ValidationGateInputError,
    adjudicate_validation_report,
    build_gate_decision_payload,
    format_gate_failure as _format_gate_failure,
    format_gate_markdown,
    format_gate_summary,
    load_validation_report,
)


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC) if not existing else f"{SRC}{os.pathsep}{existing}"
    env["PYTHONHASHSEED"] = "0"
    return env


PROFILE_DEFAULTS = {
    "subset": {"seeds": 20, "turns": 200},
    "full": {"seeds": 200, "turns": 500},
    "determinism-off": {"seeds": 2, "turns": 200},
    "determinism-hybrid": {"seeds": 2, "turns": 200},
}


WORLDGEN_CHOICES = ("template", "procedural")

# The procedural profile's world: every seed gets this many regions and civs
# (`--worldgen procedural --regions R --civs C`). A mid-sized map, the size
# range users pick once they leave the 12-region templates.
PROCEDURAL_WORLD = {"regions": 32, "civs": 10}

# A procedural seed costs about 3.2 template seeds of CPU, 2.6 of disk and 3-4
# of validation memory (more regions, civs and agents), so the full profile
# has half the seeds and 60% of the turns: about 45 minutes on three workers
# and a 2.5 GB validation peak (docs/integration/procedural-gates.md).
PROCEDURAL_PROFILE_DEFAULTS = {
    "subset": {"seeds": 20, "turns": 200},
    "full": {"seeds": 100, "turns": 300},
    "determinism-off": {"seeds": 2, "turns": 200},
    "determinism-hybrid": {"seeds": 2, "turns": 200},
}


def apply_profile_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """Fill omitted seeds/turns (and, for procedural worlds, regions/civs)
    from the selected validation profile and world generator."""
    worldgen = getattr(args, "worldgen", None) or "template"
    table = PROCEDURAL_PROFILE_DEFAULTS if worldgen == "procedural" else PROFILE_DEFAULTS
    defaults = table[args.profile]
    if args.seeds is None:
        args.seeds = defaults["seeds"]
    if args.turns is None:
        args.turns = defaults["turns"]
    if worldgen == "procedural":
        if getattr(args, "regions", None) is None:
            args.regions = PROCEDURAL_WORLD["regions"]
        if getattr(args, "civs", None) is None:
            args.civs = PROCEDURAL_WORLD["civs"]
    return args


def _world_args(args: argparse.Namespace) -> list[str]:
    """World generator arguments; the template world forwards none (CLI default)."""
    if (getattr(args, "worldgen", None) or "template") != "procedural":
        return []
    return ["--worldgen", "procedural", "--regions", str(args.regions), "--civs", str(args.civs)]


def _feature_flags(args: argparse.Namespace) -> list[str]:
    """Optional simulation feature switches forwarded to every run."""
    campaigns = getattr(args, "campaigns", None)
    if campaigns is None:
        return []
    return ["--campaigns" if campaigns else "--no-campaigns"]


def _batch_dir_for(output_root: Path, seed_start: int) -> Path:
    return output_root / f"batch_{seed_start}"


# Profiles that can fork ablation arms, and those that do by default. A
# subset forks once per seed, too few agents below the safety threshold to
# measure that pairing: there the arms cost more than they show.
ABLATION_PROFILES = ("subset", "full")
ABLATION_DEFAULT_PROFILES = ("full",)


def ablation_enabled(args: argparse.Namespace) -> bool:
    """Whether the profile runs the ablation arms: ``--ablation-oracles`` /
    ``--no-ablation-oracles``, else on in ``ABLATION_DEFAULT_PROFILES``."""
    requested = getattr(args, "ablation_oracles", None)
    if args.profile not in ABLATION_PROFILES:
        return False
    return args.profile in ABLATION_DEFAULT_PROFILES if requested is None else bool(requested)


def require_causal(args: argparse.Namespace) -> bool:
    """``--require-causal-oracles``, else ``CAUSAL_ORACLES_REQUIRED``."""
    requested = getattr(args, "require_causal_oracles", None)
    return causal_oracles_required(None, requested)


def _ablation_args(args: argparse.Namespace) -> list[str]:
    """The batch's fork checkpoints (``--checkpoint-turns``), when the arms run."""
    if not ablation_enabled(args):
        return []
    turns = checkpoint_turns(args.turns)
    return ["--checkpoint-turns", ",".join(str(t) for t in turns)] if turns else []


def _ablation_dir_for(batch_dir: Path) -> Path:
    """``ablation_<first seed>`` beside ``batch_<first seed>``."""
    name = batch_dir.name
    if name.startswith("batch_"):
        return batch_dir.parent / ("ablation_" + name[len("batch_"):])
    return batch_dir.parent / f"{name}_ablation"


def run_arms(args: argparse.Namespace, batch_dir: Path, cwd: Path, env: dict[str, str]) -> dict[str, Any] | None:
    """Fork every seed of ``batch_dir`` into its ablation arms (None when off)."""
    if not ablation_enabled(args):
        return None
    arms = [arm for arm in str(getattr(args, "ablation_arms", None) or ",".join(GATE_ARMS)).split(",") if arm]
    out = _ablation_dir_for(batch_dir)
    print(f"> ablation arms {','.join(arms)} into {out}")
    manifest = run_ablation_arms(
        batch_dir, out, arms=arms, total_turns=args.turns, parallel=max(1, int(args.parallel or 1)),
        env=env, cwd=cwd,
    )
    return {"dir": out, "arms": arms, "forks": manifest.get("fork_count"), "seconds": manifest.get("seconds"),
            "fork_turns": manifest.get("fork_turns")}


def _governance_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit Phase 8 governance switch; omitted keeps the CLI default."""
    governance = getattr(args, "governance", None)
    if governance is None:
        return []
    return ["--governance" if governance else "--no-governance"]


def _contact_ledger_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit contact-ledger switch; omitted keeps the CLI default."""
    ledger = getattr(args, "contact_ledger", None)
    if ledger is None:
        return []
    return ["--contact-ledger" if ledger else "--no-contact-ledger"]


def _epidemiology_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit epidemiology switch; omitted keeps the CLI default."""
    epidemiology = getattr(args, "epidemiology", None)
    if epidemiology is None:
        return []
    return ["--epidemiology" if epidemiology else "--no-epidemiology"]


def _finance_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit finance switch; omitted keeps the CLI default."""
    finance = getattr(args, "finance", None)
    if finance is None:
        return []
    return ["--finance" if finance else "--no-finance"]


def _diplomacy_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit diplomacy switch; omitted keeps the CLI default."""
    diplomacy = getattr(args, "diplomacy", None)
    if diplomacy is None:
        return []
    return ["--diplomacy" if diplomacy else "--no-diplomacy"]


def _techniques_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit techniques switch; omitted keeps the CLI default."""
    techniques = getattr(args, "techniques", None)
    if techniques is None:
        return []
    return ["--techniques" if techniques else "--no-techniques"]


def _maritime_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit maritime switch; omitted keeps the CLI default."""
    maritime = getattr(args, "maritime", None)
    if maritime is None:
        return []
    return ["--maritime" if maritime else "--no-maritime"]


def _gp_agendas_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit great-person agenda switch; omitted keeps the CLI default."""
    gp_agendas = getattr(args, "gp_agendas", None)
    if gp_agendas is None:
        return []
    return ["--gp-agendas" if gp_agendas else "--no-gp-agendas"]


def _nomads_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit nomads switch; omitted keeps the CLI default."""
    nomads = getattr(args, "nomads", None)
    if nomads is None:
        return []
    return ["--nomads" if nomads else "--no-nomads"]


def _cities_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit cities switch; omitted keeps the CLI default."""
    cities = getattr(args, "cities", None)
    if cities is None:
        return []
    return ["--cities" if cities else "--no-cities"]


def _agent_movements_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit agent-movements switch; omitted keeps the CLI default."""
    movements = getattr(args, "agent_movements", None)
    if movements is None:
        return []
    return ["--agent-movements" if movements else "--no-agent-movements"]


def _guilds_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit guilds switch; omitted keeps the CLI default."""
    guilds = getattr(args, "guilds", None)
    if guilds is None:
        return []
    return ["--guilds" if guilds else "--no-guilds"]


def _scholarship_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit seats-of-learning switch; omitted keeps the CLI default."""
    scholarship = getattr(args, "scholarship", None)
    if scholarship is None:
        return []
    return ["--scholarship" if scholarship else "--no-scholarship"]


def _grain_reserves_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit public-granaries switch; omitted keeps the CLI default."""
    grain_reserves = getattr(args, "grain_reserves", None)
    if grain_reserves is None:
        return []
    return ["--grain-reserves" if grain_reserves else "--no-grain-reserves"]


def _historiography_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit historiography switch; omitted keeps the CLI default."""
    historiography = getattr(args, "historiography", None)
    if historiography is None:
        return []
    return ["--historiography" if historiography else "--no-historiography"]


def _languages_args(args: argparse.Namespace) -> list[str]:
    """Forward an explicit languages switch; omitted keeps the CLI default."""
    languages = getattr(args, "languages", None)
    if languages is None:
        return []
    return ["--languages" if languages else "--no-languages"]


def _fishery_aid_args(args: argparse.Namespace, agents: str = "hybrid") -> list[str]:
    """Forward explicit fisheries / mutual-aid switches; omitted keeps the CLI default.

    Mutual aid is dormant under ``--agents off`` and the CLI rejects an explicit
    ``--mutual-aid`` there, so an aggregate run only receives ``--no-mutual-aid``.
    """
    out: list[str] = []
    fisheries = getattr(args, "fisheries", None)
    if fisheries is not None:
        out.append("--fisheries" if fisheries else "--no-fisheries")
    aid = getattr(args, "mutual_aid", None)
    if aid is not None and not (aid and agents == "off"):
        out.append("--mutual-aid" if aid else "--no-mutual-aid")
    return out


def run_subset(args: argparse.Namespace, cwd: Path, env: dict[str, str]) -> Path:
    output_root = args.output_root / "oracle_subset"
    cmd = [
        sys.executable,
        "-m",
        "chronicler.main",
        "--seed-range",
        f"{args.seed_start}-{args.seed_start + args.seeds - 1}",
        "--turns",
        str(args.turns),
        "--agents",
        "hybrid",
        "--simulate-only",
        "--validation-sidecar",
        "--parallel",
        str(args.parallel),
        "--output",
        str(output_root / "chronicle.md"),
        *_world_args(args),
        *_feature_flags(args),
        *_governance_args(args),
        *_contact_ledger_args(args),
        *_finance_args(args),
        *_fishery_aid_args(args),
        *_epidemiology_args(args),
        *_diplomacy_args(args),
        *_techniques_args(args),
        *_maritime_args(args),
        *_gp_agendas_args(args),
        *_nomads_args(args),
        *_cities_args(args),
        *_agent_movements_args(args),
        *_guilds_args(args),
        *_scholarship_args(args),
        *_grain_reserves_args(args),
        *_historiography_args(args),
        *_languages_args(args),
        *_ablation_args(args),
    ]
    _run(cmd, cwd, env)
    return _batch_dir_for(output_root, args.seed_start)


def run_full(args: argparse.Namespace, cwd: Path, env: dict[str, str]) -> Path:
    output_root = args.output_root / "full_gate"
    cmd = [
        sys.executable,
        "-m",
        "chronicler.main",
        "--seed-range",
        f"{args.seed_start}-{args.seed_start + args.seeds - 1}",
        "--turns",
        str(args.turns),
        "--agents",
        "hybrid",
        "--simulate-only",
        "--validation-sidecar",
        "--parallel",
        str(args.parallel),
        "--output",
        str(output_root / "chronicle.md"),
        *_world_args(args),
        *_feature_flags(args),
        *_governance_args(args),
        *_contact_ledger_args(args),
        *_finance_args(args),
        *_fishery_aid_args(args),
        *_epidemiology_args(args),
        *_diplomacy_args(args),
        *_techniques_args(args),
        *_maritime_args(args),
        *_gp_agendas_args(args),
        *_nomads_args(args),
        *_cities_args(args),
        *_agent_movements_args(args),
        *_guilds_args(args),
        *_scholarship_args(args),
        *_grain_reserves_args(args),
        *_historiography_args(args),
        *_languages_args(args),
        *_ablation_args(args),
    ]
    _run(cmd, cwd, env)
    return _batch_dir_for(output_root, args.seed_start)


def _determinism_manifest_args(args: argparse.Namespace, agents: str) -> argparse.Namespace:
    """The run arguments of a determinism pair, for its batch manifest."""
    run_args = argparse.Namespace(**vars(args))
    run_args.agents = agents
    run_args.simulate_only = True
    run_args.validation_sidecar = agents == "hybrid"
    if (getattr(args, "worldgen", None) or "template") != "procedural":
        run_args.worldgen = run_args.regions = run_args.civs = None
    run_args.parallel = None
    return run_args


def _bundle_total_turns(seed_dir: Path) -> int | None:
    try:
        metadata = json.loads((seed_dir / BUNDLE_FILENAME).read_text(encoding="utf-8")).get("metadata", {})
    except (OSError, ValueError):
        return None
    turns = metadata.get("total_turns") if isinstance(metadata, dict) else None
    return turns if isinstance(turns, int) and not isinstance(turns, bool) else None


def _profile_batch_dir(args: argparse.Namespace) -> Path:
    """The batch directory the selected profile writes."""
    if args.profile == "subset":
        return _batch_dir_for(args.output_root / "oracle_subset", args.seed_start)
    if args.profile == "full":
        return _batch_dir_for(args.output_root / "full_gate", args.seed_start)
    agents = "off" if args.profile == "determinism-off" else "hybrid"
    return args.output_root / f"determinism_{agents}" / "batch_42"


def run_determinism(args: argparse.Namespace, cwd: Path, env: dict[str, str], agents: str) -> Path:
    output_root = args.output_root / f"determinism_{agents}"
    batch_dir = output_root / "batch_42"
    prepare_batch_dir(batch_dir)
    run_dirs = ["seed_42_a", "seed_42_b"]
    manifest = new_batch_manifest(_determinism_manifest_args(args, agents), [42, 42], run_dirs=run_dirs)
    write_batch_manifest(batch_dir, manifest)
    for index, suffix in enumerate(("a", "b")):
        seed_dir = batch_dir / f"seed_42_{suffix}"
        seed_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            "-m",
            "chronicler.main",
            "--seed",
            "42",
            "--turns",
            str(args.turns),
            "--agents",
            agents,
            "--simulate-only",
            "--output",
            str(seed_dir / "chronicle.md"),
            "--state",
            str(seed_dir / "state.json"),
        ]
        if agents == "hybrid":
            cmd.insert(-4, "--validation-sidecar")
        cmd.extend(_world_args(args))
        cmd.extend(_feature_flags(args))
        cmd.extend(_governance_args(args))
        cmd.extend(_contact_ledger_args(args))
        cmd.extend(_finance_args(args))
        cmd.extend(_fishery_aid_args(args, agents))
        cmd.extend(_epidemiology_args(args))
        cmd.extend(_diplomacy_args(args))
        cmd.extend(_techniques_args(args))
        cmd.extend(_maritime_args(args))
        cmd.extend(_gp_agendas_args(args))
        cmd.extend(_nomads_args(args))
        cmd.extend(_cities_args(args))
        cmd.extend(_agent_movements_args(args))
        cmd.extend(_guilds_args(args))
        cmd.extend(_scholarship_args(args))
        cmd.extend(_grain_reserves_args(args))
        cmd.extend(_historiography_args(args))
        cmd.extend(_languages_args(args))
        _run(cmd, cwd, env)
        record_batch_run(batch_dir, manifest, index, _bundle_total_turns(seed_dir))
    finish_batch_manifest(batch_dir, manifest)
    return batch_dir


STDERR_TAIL_CHARS = 8000


def _stderr_tail(stderr: str | None) -> str | None:
    if not stderr:
        return None
    return stderr[-STDERR_TAIL_CHARS:]


def _validation_error_report(
    batch_dir: Path,
    *,
    reason: str,
    returncode: int | None = None,
    stderr: str | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "batch_dir": str(batch_dir),
        "oracles": ["all"],
        "results": {
            "validation_cli": {
                "status": "ERROR",
                "reason": reason,
            }
        },
        "status": "ERROR",
        "reason": reason,
    }
    tail = _stderr_tail(stderr)
    if returncode is not None or tail is not None:
        validation_subprocess: dict[str, Any] = {}
        if returncode is not None:
            validation_subprocess["returncode"] = returncode
        if tail is not None:
            validation_subprocess["stderr_tail"] = tail
        report["validation_subprocess"] = validation_subprocess
    return report


def _report_from_validation_process(proc: subprocess.CompletedProcess[str], batch_dir: Path) -> tuple[dict[str, Any], str]:
    try:
        report = strict_json_loads(proc.stdout, label="validation subprocess JSON")
        if not isinstance(report, dict):
            raise ValueError("validation report JSON must be an object")
    except (ArtifactIOError, ValueError) as exc:
        reason = f"validation subprocess produced invalid JSON: {exc}"
        report = _validation_error_report(
            batch_dir,
            reason=reason,
            returncode=proc.returncode,
            stderr=proc.stderr,
        )
        return report, strict_json_dumps(report)
    if proc.returncode != 0:
        validation_subprocess = report.setdefault("validation_subprocess", {})
        if not isinstance(validation_subprocess, dict):
            validation_subprocess = {}
            report["validation_subprocess"] = validation_subprocess
        validation_subprocess["returncode"] = proc.returncode
        tail = _stderr_tail(proc.stderr)
        if tail is not None:
            validation_subprocess["stderr_tail"] = tail
    return report, strict_json_dumps(report)


def _paths_collide(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _reject_baseline_output_collisions(baseline_report: Path, output_paths: list[tuple[str, Path]]) -> None:
    for label, output_path in output_paths:
        if _paths_collide(baseline_report, output_path):
            raise ValidationGateInputError(f"baseline-report must be different from {label}")


def _markdown_escape(text: str) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for char in ("\\", "`", "*", "_", "[", "]", "(", ")", "!"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def _comparison_error_summary(profile: str, reason: str) -> str:
    safe_reason = _markdown_escape(reason)
    return f"# Validation report comparison: {profile}\n\n**Status:** ERROR\n\n{safe_reason}\n"


def _comparison_error_result(
    profile: str,
    baseline_report: Path,
    current_report: Path,
    batch_dir: Path,
    *,
    reason: str,
    fail_on_regression: bool,
    require_strict_regression: bool = False,
) -> dict[str, Any]:
    comparison_path = batch_dir / f"compare_decision_{profile}.json"
    comparison_summary_path = batch_dir / f"compare_summary_{profile}.md"
    comparison = {
        "schema_version": 1,
        "profile": profile,
        "status": "ERROR",
        "reason": reason,
        "baseline_report_path": str(baseline_report),
        "current_report_path": str(current_report),
        "regression_detected": False,
        "regression_reasons": [],
        "require_strict_regression": require_strict_regression,
        "fail_on_regression": fail_on_regression,
        "exit_code": 1,
    }
    atomic_write_json(comparison_path, comparison)
    atomic_write_text(comparison_summary_path, _comparison_error_summary(profile, reason))
    print(f"Validation comparison error written to {comparison_path}")
    return {
        "comparison_path": comparison_path,
        "comparison_summary_path": comparison_summary_path,
        "comparison": comparison,
    }


def compare_batch_report(
    profile: str,
    baseline_report: Path,
    current_report: Path,
    batch_dir: Path,
    *,
    require_strict_regression: bool = False,
    fail_on_regression: bool = False,
    exploratory: bool = False,
) -> dict[str, Any]:
    try:
        baseline = load_validation_report(baseline_report)
        current = load_validation_report(current_report)
        comparison = compare_validation_reports(
            profile,
            baseline,
            current,
            require_strict_regression=require_strict_regression,
            fail_on_regression=fail_on_regression,
            exploratory=exploratory,
        )
    except ValidationGateInputError as exc:
        return _comparison_error_result(
            profile,
            baseline_report,
            current_report,
            batch_dir,
            reason=str(exc),
            fail_on_regression=fail_on_regression,
            require_strict_regression=require_strict_regression,
        )
    comparison["baseline_report_path"] = str(baseline_report)
    comparison["current_report_path"] = str(current_report)
    comparison_path = batch_dir / f"compare_decision_{profile}.json"
    comparison_summary_path = batch_dir / f"compare_summary_{profile}.md"
    atomic_write_json(comparison_path, comparison)
    atomic_write_text(comparison_summary_path, format_comparison_markdown(comparison))
    print(f"Validation comparison decision written to {comparison_path}")
    print(f"Validation comparison summary written to {comparison_summary_path}")
    label = "EXPLORATORY " if comparison.get("exploratory") else ""
    if comparison["regression_detected"]:
        print(f"Validation comparison: {label}REGRESSION " + ",".join(comparison["regression_reasons"]))
    else:
        print(f"Validation comparison: {label}NO REGRESSION (no newly failing required gates)")
    return {
        "comparison_path": comparison_path,
        "comparison_summary_path": comparison_summary_path,
        "comparison": comparison,
    }


def validate_batch(
    batch_dir: Path,
    report_name: str,
    cwd: Path,
    env: dict[str, str],
    profile: str,
    *,
    require_strict_regression: bool = False,
    baseline_report: Path | None = None,
    fail_on_regression: bool = False,
    exploratory_comparison: bool = False,
    ablation_dir: Path | None = None,
    require_causal_oracles: bool | None = None,
) -> dict[str, Any]:
    report_path = batch_dir / report_name
    decision_path = batch_dir / f"gate_decision_{profile}.json"
    summary_path = batch_dir / f"gate_summary_{profile}.md"
    if baseline_report is not None:
        _reject_baseline_output_collisions(
            baseline_report,
            [
                ("current-report", report_path),
                ("gate-decision", decision_path),
                ("gate-summary", summary_path),
                ("compare-decision", batch_dir / f"compare_decision_{profile}.json"),
                ("compare-summary", batch_dir / f"compare_summary_{profile}.md"),
            ],
        )
    cmd = [
        sys.executable,
        "-m",
        "chronicler.validate",
        "--batch-dir",
        str(batch_dir),
        "--oracles",
        "all",
        "--profile",
        profile,
    ]
    if ablation_dir is not None:
        cmd.extend(["--ablation-dir", str(ablation_dir)])
    if require_causal_oracles is not None:
        cmd.append(CAUSAL_ORACLES_FLAG if require_causal_oracles else "--no-" + CAUSAL_ORACLES_FLAG[2:])
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    report, report_text = _report_from_validation_process(proc, batch_dir)
    atomic_write_text(report_path, report_text)
    print(f"Validation report written to {report_path}")
    decision = adjudicate_validation_report(
        profile,
        report,
        require_strict_regression=require_strict_regression,
        require_causal_oracles=require_causal_oracles,
    )
    decision_payload = build_gate_decision_payload(decision, report, report_path=report_path)
    atomic_write_json(decision_path, decision_payload)
    atomic_write_text(summary_path, format_gate_markdown(decision, report, report_path=report_path))
    print(f"Validation gate decision written to {decision_path}")
    print(f"Validation gate summary written to {summary_path}")
    print(format_gate_summary(decision))
    comparison_result: dict[str, Any] = {}
    if baseline_report is not None:
        comparison_result = compare_batch_report(
            profile,
            baseline_report,
            report_path,
            batch_dir,
            require_strict_regression=require_strict_regression,
            fail_on_regression=fail_on_regression,
            exploratory=exploratory_comparison,
        )
    manifest_entry = report.get("batch_manifest")
    result = {
        "report_path": report_path,
        "decision_path": decision_path,
        "summary_path": summary_path,
        "decision": decision_payload,
        "batch_manifest_status": manifest_entry.get("status") if isinstance(manifest_entry, dict) else None,
    }
    result.update(comparison_result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run canonical M53b validation profiles")
    parser.add_argument(
        "--profile",
        required=True,
        choices=PROFILE_CHOICES,
    )
    parser.add_argument("--output-root", type=Path, default=Path("output/m53/canonical"))
    parser.add_argument("--seed-start", type=int, default=42)
    parser.add_argument("--seeds", type=int, default=None)
    parser.add_argument("--turns", type=int, default=None)
    parser.add_argument("--parallel", type=int, default=12,
                        help="batch worker processes (passed as --parallel N; 1 is one worker, 0 sequential)")
    parser.add_argument(
        "--worldgen",
        choices=WORLDGEN_CHOICES,
        default="template",
        help="World of every run: template (default, the CLI's 8-region template world) or "
             "procedural (heightmap/Voronoi geography, PROCEDURAL_WORLD regions and civs, "
             "PROCEDURAL_PROFILE_DEFAULTS seeds and turns).",
    )
    parser.add_argument("--regions", type=int, default=None,
                        help=f"Procedural worlds only: regions per world (default {PROCEDURAL_WORLD['regions']}).")
    parser.add_argument("--civs", type=int, default=None,
                        help=f"Procedural worlds only: civs per world (default {PROCEDURAL_WORLD['civs']}).")
    parser.add_argument(
        "--campaigns",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --campaigns/--no-campaigns (M60 war layer) to every simulation run.",
    )
    parser.add_argument(
        "--governance",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --governance/--no-governance to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--contact-ledger",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --contact-ledger/--no-contact-ledger to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--finance",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --finance/--no-finance to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--fisheries",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --fisheries/--no-fisheries to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--mutual-aid",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --mutual-aid/--no-mutual-aid to every agent-mode run (default: CLI default).",
    )
    parser.add_argument(
        "--epidemiology",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --epidemiology/--no-epidemiology to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--diplomacy",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --diplomacy/--no-diplomacy to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--techniques",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --techniques/--no-techniques to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--maritime",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --maritime/--no-maritime to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--gp-agendas",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --gp-agendas/--no-gp-agendas to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--nomads",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --nomads/--no-nomads to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--cities",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --cities/--no-cities to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--agent-movements",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --agent-movements/--no-agent-movements to every simulation run "
             "(default: CLI default).",
    )
    parser.add_argument(
        "--guilds",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --guilds/--no-guilds to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--scholarship",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --scholarship/--no-scholarship to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--grain-reserves",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --grain-reserves/--no-grain-reserves to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--historiography",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --historiography/--no-historiography to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--languages",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Forward --languages/--no-languages to every simulation run (default: CLI default).",
    )
    parser.add_argument(
        "--ablation-oracles",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Fork every seed into ablation arms (the need terms; the kin roots) for the needs and "
             "cohort oracles' ablation components (default: on in the full profile, off in the subset, "
             "which cannot measure the safety pairing; docs/integration/ablation-oracles.md).",
    )
    parser.add_argument(
        "--ablation-arms",
        default=None,
        help=f"Comma-separated arms to fork (default {','.join(GATE_ARMS)}; 'placebo' adds the "
             "calibration arm).",
    )
    parser.add_argument(
        CAUSAL_ORACLES_FLAG,
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Let the ablation components decide the needs and cohort oracles (default "
             "validation_gate.CAUSAL_ORACLES_REQUIRED, off: reported as causal evidence, not yet "
             "required). Needs the ablation arms.",
    )
    parser.add_argument(
        "--require-strict-regression",
        action="store_true",
        help="For full profile reports, fail calibrated-floor regression passes.",
    )
    parser.add_argument(
        "--baseline-report",
        type=Path,
        help="Optional prior validation report to compare against after the current gate runs.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="When --baseline-report is set, exit 2 for comparator-detected regressions.",
    )
    parser.add_argument(
        "--exploratory-comparison",
        action="store_true",
        help="When --baseline-report is set, compare even if the baseline measured a different cohort "
             "(seeds, turns, world, simulation configuration); the comparison is labelled exploratory.",
    )
    parsed = parser.parse_args()
    if parsed.worldgen != "procedural" and (parsed.regions is not None or parsed.civs is not None):
        parser.error("--regions and --civs require --worldgen procedural")
    args = apply_profile_defaults(parsed)
    if args.fail_on_regression and args.baseline_report is None:
        parser.error("--fail-on-regression requires --baseline-report")
    if args.exploratory_comparison and args.baseline_report is None:
        parser.error("--exploratory-comparison requires --baseline-report")
    if args.ablation_oracles and args.profile not in ABLATION_PROFILES:
        parser.error(f"--ablation-oracles applies to the {' and '.join(ABLATION_PROFILES)} profiles")
    if args.profile in ABLATION_PROFILES and require_causal(args) and not ablation_enabled(args):
        parser.error(f"{CAUSAL_ORACLES_FLAG} needs the ablation arms (--ablation-oracles)")
    try:
        check_batch_destination(_profile_batch_dir(args))
        if ablation_enabled(args):
            check_batch_destination(_ablation_dir_for(_profile_batch_dir(args)))
    except BatchDestinationError as exc:
        parser.error(str(exc))

    cwd = Path.cwd()
    env = _build_env()

    timings: dict[str, float] = {}
    arms_result = None
    if args.profile in ("subset", "full"):
        started = time.monotonic()
        batch_dir = run_subset(args, cwd, env) if args.profile == "subset" else run_full(args, cwd, env)
        timings["batch_seconds"] = round(time.monotonic() - started, 1)
        started = time.monotonic()
        arms_result = run_arms(args, batch_dir, cwd, env)
        if arms_result is not None:
            timings["ablation_seconds"] = round(time.monotonic() - started, 1)
        started = time.monotonic()
        validation_result = validate_batch(
            batch_dir,
            f"validate_report_{args.profile}.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
            baseline_report=args.baseline_report,
            fail_on_regression=args.fail_on_regression,
            exploratory_comparison=args.exploratory_comparison,
            ablation_dir=arms_result["dir"] if arms_result is not None else None,
            require_causal_oracles=args.require_causal_oracles,
        )
        timings["validation_seconds"] = round(time.monotonic() - started, 1)
    elif args.profile == "determinism-off":
        batch_dir = run_determinism(args, cwd, env, "off")
        validation_result = validate_batch(
            batch_dir,
            "validate_report_determinism_off.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
            baseline_report=args.baseline_report,
            fail_on_regression=args.fail_on_regression,
            exploratory_comparison=args.exploratory_comparison,
        )
    else:
        batch_dir = run_determinism(args, cwd, env, "hybrid")
        validation_result = validate_batch(
            batch_dir,
            "validate_report_determinism_hybrid.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
            baseline_report=args.baseline_report,
            fail_on_regression=args.fail_on_regression,
            exploratory_comparison=args.exploratory_comparison,
        )

    comparison = validation_result.get("comparison")
    summary = {
        "profile": args.profile,
        "batch_dir": str(batch_dir),
        "report_path": str(validation_result["report_path"]),
        "decision_path": str(validation_result["decision_path"]),
        "summary_path": str(validation_result["summary_path"]),
        "gate_status": "PASS" if validation_result["decision"]["ok"] else "FAIL",
        "gate_exit_code": validation_result["decision"]["exit_code"],
        "seed_start": args.seed_start,
        "seeds": args.seeds,
        "turns": args.turns,
        "parallel": args.parallel,
        "worldgen": args.worldgen,
        "regions": getattr(args, "regions", None),
        "civs": getattr(args, "civs", None),
        "campaigns": args.campaigns,
        "contact_ledger": args.contact_ledger,
        "finance": args.finance,
        "fisheries": args.fisheries,
        "mutual_aid": args.mutual_aid,
        "epidemiology": args.epidemiology,
        "diplomacy": args.diplomacy,
        "techniques": args.techniques,
        "maritime": args.maritime,
        "gp_agendas": args.gp_agendas,
        "nomads": args.nomads,
        "cities": args.cities,
        "agent_movements": args.agent_movements,
        "guilds": args.guilds,
        "scholarship": args.scholarship,
        "grain_reserves": args.grain_reserves,
        "historiography": args.historiography,
        "languages": args.languages,
        "ablation_oracles": arms_result is not None,
        "ablation_dir": str(arms_result["dir"]) if arms_result is not None else None,
        "ablation_arms": arms_result["arms"] if arms_result is not None else None,
        "ablation_fork_turns": arms_result["fork_turns"] if arms_result is not None else None,
        "ablation_forks": arms_result["forks"] if arms_result is not None else None,
        "causal_oracles_required": require_causal(args),
        **timings,
        "pythonhashseed": env["PYTHONHASHSEED"],
        "require_strict_regression": args.require_strict_regression,
        "baseline_report_path": str(args.baseline_report) if args.baseline_report is not None else None,
        "fail_on_regression": args.fail_on_regression,
        "comparison_path": str(validation_result["comparison_path"]) if comparison is not None else None,
        "comparison_summary_path": str(validation_result["comparison_summary_path"]) if comparison is not None else None,
        "batch_manifest_path": str(batch_dir / MANIFEST_FILENAME),
        "batch_manifest_status": validation_result.get("batch_manifest_status"),
        "exploratory_comparison": args.exploratory_comparison,
        "comparison_status": (
            "ERROR" if comparison and comparison.get("status") == "ERROR"
            else ("EXPLORATORY_" if comparison and comparison.get("exploratory") else "")
            + ("REGRESSION" if comparison["regression_detected"] else "NO_REGRESSION") if comparison else None
        ),
        "comparison_exit_code": comparison["exit_code"] if comparison is not None else None,
        "comparison_reasons": comparison["regression_reasons"] if comparison is not None else [],
        "comparison_error": comparison.get("reason") if comparison is not None and comparison.get("status") == "ERROR" else None,
    }
    atomic_write_json(batch_dir / "run_manifest.json", summary)
    print(strict_json_dumps(summary), end="")
    if not validation_result["decision"]["ok"]:
        print(_format_gate_failure(validation_result["decision"]), file=sys.stderr)
        raise SystemExit(validation_result["decision"]["exit_code"])
    if comparison is not None and comparison["exit_code"] != 0:
        raise SystemExit(comparison["exit_code"])


if __name__ == "__main__":
    main()
