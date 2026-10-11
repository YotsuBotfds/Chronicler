"""Explicit two-turn synthetic capture driver; default invocation executes nothing.

Opt in with --enabled --fixture existing-two-turn plus explicit --origin,
--revision, --tree and --source-label. Output goes only to stdout.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from chronicler import governance_capture as capture
from chronicler import governance_kernel_harness as h
from chronicler import governance_measurements as gm


def existing_fixture():
    """Construct the accepted example's initial values, without running it.

    Only its read-only policy factory is reused. Fixture imports occur solely
    after explicit opt-in; the example experiment and old wrapper are not used.
    """
    import importlib.util
    from chronicler import institutions as i
    from chronicler import elite_metrics as e
    from chronicler import governance_capital as c
    from chronicler import ruler_ambitions as a

    spec = importlib.util.spec_from_file_location(
        "explicit_capture_fixture_policy", REPO_ROOT / "examples" / "governance_four_kernel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policy = module.synthetic_policy()
    opening = h.HarnessCarry(0, -1, (0,), (h.CivCarry(0, i.InstitutionSnapshot(0, ()),
        e.EliteRatchetState(-1, 0.), c.GovernanceState(0, .5, .3), None),))
    obs = h.CivObservation(civ_id=0, factions=i.FactionWeights(.6, .1, .2, .1), treasury=100.,
        base_governing_cost=0., region_count=4, trade_route_count=3, proposals=(), mock_suppressions=(),
        ambition_snapshot=a.AmbitionSnapshot('0', 'synthetic-reign-1', 0, 0, .5, .3,
            owned_regions=('Home',), conquerable_regions=('Border',), military_eligible=True),
        legitimacy=c.LegitimacyInputs(), events=(), accession=c.SuccessionKind.PEACEFUL,
        ambition_draws=(a.SelectionDraw(0., 0., 0.),)*2, accession_event_cursor=0)
    next_obs = replace(obs,
        ambition_snapshot=replace(obs.ambition_snapshot, turn=1, owned_regions=('Home', 'Border')),
        accession=None, ambition_draws=(), accession_event_cursor=None,
        proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),),
        mock_suppressions=(h.MockSuppression('synthetic-suppression-1', True),))
    frames = tuple(h.SyntheticFrame(n, n, 'explicit_synthetic_fixture', (item,), (), ())
                   for n, item in enumerate((obs, next_obs)))
    return opening, frames, policy


def capture_fixture(*, origin: gm.MeasurementOrigin, source_identity: gm.SourceIdentity):
    opening, frames, policy = existing_fixture()
    first = capture.capture_frame(enabled=True, opening=opening, frame=frames[0],
        policy=policy, origin=origin, source_identity=source_identity)
    # Match the existing example's exact restart boundary, without spending twice.
    restored = h.carry_from_json(h.carry_to_json(first.result.carry))
    second = capture.capture_frame(enabled=True, opening=restored, frame=frames[1],
        policy=policy, origin=origin, source_identity=source_identity)
    return first, second


def capture_json(captures) -> str:
    """Canonical output uses each owner's encoder; Fractions never become floats."""
    rows = [dict(status=item.status,
                 synthetic_frame=dict(source_turn=item.frame.source_turn,
                    ownership_epoch=item.frame.ownership_epoch, origin=item.frame.origin),
                 opening=json.loads(h.carry_to_json(item.opening)),
                 result_carry=json.loads(h.carry_to_json(item.result.carry)),
                 measurement=json.loads(gm.measurement_json(item.measurement)))
            for item in captures]
    return json.dumps(dict(contract=capture.CAPTURE_CONTRACT, enabled=True, captures=rows),
                      sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--fixture", choices=("existing-two-turn",))
    parser.add_argument("--origin", choices=tuple(item.value for item in gm.MeasurementOrigin))
    parser.add_argument("--revision")
    parser.add_argument("--tree")
    parser.add_argument("--source-label")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    # Dispatch before optional choice/provenance validation. Only the exact
    # activation/help flags are interpreted here; optional values remain opaque.
    dispatch = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    dispatch.add_argument("--enabled", action="store_true")
    dispatch.add_argument("-h", "--help", action="store_true")
    activation, _ = dispatch.parse_known_args(raw)
    if activation.help:
        build_parser().parse_args(["--help"])
    if not activation.enabled:
        sys.stdout.write(json.dumps(dict(contract=capture.CAPTURE_CONTRACT, enabled=False,
            status="disabled_no_measurement", captures=[],
            unavailable=[dict(key=item.key, reason=item.reason)
                         for item in gm.m67_measurement_obligation_catalogue()]),
            sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    parser = build_parser()
    args = parser.parse_args(raw)
    if not all((args.fixture, args.origin, args.revision, args.tree, args.source_label)):
        parser.error("enabled capture requires fixture, origin, revision, tree and source-label")
    try:
        identity = gm.SourceIdentity(args.revision, args.tree, args.source_label)
        captures = capture_fixture(origin=gm.MeasurementOrigin(args.origin), source_identity=identity)
    except ValueError as error:
        parser.error(str(error))
    text = capture_json(captures) if args.json else (
        f"CAPTURE {capture.CAPTURE_CONTRACT}; caller-declared source identity\n" +
        "".join(gm.render_report(item.measurement) for item in captures))
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
