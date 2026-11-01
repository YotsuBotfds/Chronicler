"""Strict test-only inverse witnesses for three reviewed Kimi main changes.

Historical targets remain immutable: ff57's canonical default witness retains
its extracted admission helper; care parent 2e742 predates all three unrelated
runner/output repairs. Each inverse includes lexical context on both sides. No
helper/body/predicate/location is admitted by name alone, and the caller still
hashes the complete projected module. These source checks do not qualify native
care bodies, simulation identity, RNG, checkpoint behavior or scientific efficacy.
"""

_RUNNER_REPAIRS = (
    (
        'artifact-budget helper location and body',
        r'''    return {"campaign": snapshot_summary(world)}


def _require_artifact_budget_admission(args, world, checkpoint_resume, artifact_budget) -> None:
    """Reject run shapes outside the explicit artifact-budget contract."""
    artifact_budget.require_healthy()
    if (world is not None or checkpoint_resume is not None
            or getattr(args, "resume", None)):
        raise ValueError("artifact_budget supports only fresh unsupplied Worlds")
    if (getattr(args, "checkpoint_every", None) is not None
            or getattr(args, "checkpoint_turns", None)):
        raise ValueError("artifact_budget exact checkpoints are unqualified")
    if (getattr(args, "agents", "off") != "hybrid"
            or getattr(args, "live", False)
            or getattr(args, "interactive", False)
            or getattr(args, "ablation_output", False)):
        raise ValueError("artifact_budget requires an ordinary noninteractive hybrid run")


def execute_run(
    args: argparse.Namespace,
    sim_client: LLMClient | None = None,
''',
        r'''    return {"campaign": snapshot_summary(world)}


def execute_run(
    args: argparse.Namespace,
    sim_client: LLMClient | None = None,
''',
    ),
    (
        'artifact-budget call at execute_run entry',
        r'''        implement owner/log admission or qualify an enabled study.
    """
    if artifact_budget is not None:
        _require_artifact_budget_admission(args, world, checkpoint_resume, artifact_budget)

    # Fallback clients
    _sim = sim_client or _DummyClient()
''',
        r'''        implement owner/log admission or qualify an enabled study.
    """
    if artifact_budget is not None:
        artifact_budget.require_healthy()
        if (world is not None or checkpoint_resume is not None
                or getattr(args, "resume", None)):
            raise ValueError("artifact_budget supports only fresh unsupplied Worlds")
        if (getattr(args, "checkpoint_every", None) is not None
                or getattr(args, "checkpoint_turns", None)):
            raise ValueError("artifact_budget exact checkpoints are unqualified")
        if (getattr(args, "agents", "off") != "hybrid"
                or getattr(args, "live", False)
                or getattr(args, "interactive", False)
                or getattr(args, "ablation_output", False)):
            raise ValueError("artifact_budget requires an ordinary noninteractive hybrid run")

    # Fallback clients
    _sim = sim_client or _DummyClient()
''',
    ),
    (
        'live callback interrupt deferral at captured-turn boundary',
        r'''            provenance=engine.take_turn_provenance(),
        ))

        # on_turn callback — fires after each turn's data is captured. Live
        # pacing sleeps here, so defer a first Ctrl-C as during the turn itself;
        # after an earlier request the default handler keeps a second immediate.
        if on_turn is not None:
            turn_events = history_index(world).events_for_turn(world, world.turn - 1)
            turn_named = world.named_events[named_events_before:]
            if _interrupt_requested:
                on_turn(snapshot, chronicle_text, turn_events, turn_named)
            else:
                with _SigintDeferral() as deferral:
                    on_turn(snapshot, chronicle_text, turn_events, turn_named)
                _interrupt_requested = deferral.requested

        # Update memory streams with this turn's events
        turn_events = history_index(world).events_for_turn(world, world.turn - 1)
''',
        r'''            provenance=engine.take_turn_provenance(),
        ))

        # on_turn callback — fires after each turn's data is captured
        if on_turn is not None:
            turn_events = history_index(world).events_for_turn(world, world.turn - 1)
            turn_named = world.named_events[named_events_before:]
            on_turn(snapshot, chronicle_text, turn_events, turn_named)

        # Update memory streams with this turn's events
        turn_events = history_index(world).events_for_turn(world, world.turn - 1)
''',
    ),
)

_ARTIFACT_REPAIRS = (
    (
        'atomic writer helper locations and bodies',
        r'''    save_sidecar(world, path, atomic=True)
    from chronicler.languages import save_sidecar as save_languages
    save_languages(world, path, atomic=True)


def _write_chronicle_output(output_path: Path, output_text: str, *, artifact_budget=None) -> None:
    """Write the final chronicle by atomically replacing any previous one."""
    atomic_write_text(output_path, output_text, artifact_budget=artifact_budget)


def _write_analysis_report(analyze_dir: Path, report: dict[str, Any]) -> Path:
    """Write the CLI analytics report by atomically replacing any previous one."""
    import json

    report_path = analyze_dir / "batch_report.json"
    atomic_write_text(report_path, json.dumps(report, indent=2))
    return report_path


def _resolve_checkpoint_every(args: argparse.Namespace) -> int | None:
''',
        r'''    save_sidecar(world, path, atomic=True)
    from chronicler.languages import save_sidecar as save_languages
    save_languages(world, path, atomic=True)


def _resolve_checkpoint_every(args: argparse.Namespace) -> int | None:
''',
    ),
    (
        'final chronicle write at ordinary-output boundary',
        r'''            output_text = provenance_header + "\n\n" + output_text

        # Write output
        _write_chronicle_output(output_path, output_text, artifact_budget=artifact_budget)
        print(f"\nChronicle written to {output_path} ({len(output_text)} characters)")

        # Save final state
''',
        r'''            output_text = provenance_header + "\n\n" + output_text

        # Write output
        if artifact_budget is None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output_text, encoding="utf-8")
        else:
            artifact_budget.ensure_directory(output_path.parent)
            artifact_budget.write_text(output_path, output_text, encoding="utf-8")
        print(f"\nChronicle written to {output_path} ({len(output_text)} characters)")

        # Save final state
''',
    ),
    (
        'analytics report write at CLI analyze dispatch',
        r'''        if getattr(args, "checkpoints", None):
            checkpoints = [int(x.strip()) for x in args.checkpoints.split(",")]
        report = generate_report(analyze_dir, checkpoints=checkpoints)
        report_path = _write_analysis_report(analyze_dir, report)
        if getattr(args, "compare", None):
            with open(args.compare) as f:
                baseline = _json.load(f)
''',
        r'''        if getattr(args, "checkpoints", None):
            checkpoints = [int(x.strip()) for x in args.checkpoints.split(",")]
        report = generate_report(analyze_dir, checkpoints=checkpoints)
        report_path = analyze_dir / "batch_report.json"
        with open(report_path, "w") as f:
            _json.dump(report, f, indent=2)
        if getattr(args, "compare", None):
            with open(args.compare) as f:
                baseline = _json.load(f)
''',
    ),
)


def _inverse_exact(source, repairs):
    for label, current, historical in repairs:
        assert source.count(current) == 1, f"reviewed main witness changed: {label}"
        source = source.replace(current, historical, 1)
    return source


def before_reviewed_runner_repairs(source):
    """Invert exact ff57 budget extraction and 803 live interrupt repair sites."""
    return _inverse_exact(source, _RUNNER_REPAIRS)


def before_reviewed_live_callback_repair(source):
    """Retain ff57's exact extracted helper and invert only 803's callback site."""
    for label, current, _ in _RUNNER_REPAIRS[:2]:
        assert source.count(current) == 1, f"reviewed main witness changed: {label}"
    return _inverse_exact(source, _RUNNER_REPAIRS[2:])


def before_reviewed_artifact_repairs(source):
    """Additionally invert exact 0a49 atomic writer sites to care's 2e742 parent."""
    return _inverse_exact(before_reviewed_runner_repairs(source), _ARTIFACT_REPAIRS)
