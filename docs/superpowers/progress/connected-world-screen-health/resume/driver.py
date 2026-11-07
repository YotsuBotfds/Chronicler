"""Bounded health exact resume from actual PA-p19 pilot lifecycle states."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

repo = Path('/workspace/cw-health')
sys.path.insert(0, str(repo / 'scripts'))
import checkpoint_identity as CI
import cw_health_screen as HS
from chronicler.bundle_codec import load_bundle

bundle_path = Path('/workspace/evidence/health/pilot-v2/runs/PA-p19/chronicle_bundle.json')
bundle = load_bundle(bundle_path)
metrics, problems = HS.extract(bundle, HS.SCREEN.arms['PA'][0])
assert not problems, problems
assert len(bundle['history']) == 200 and bundle['world_state']['seed'] == 19
assert len(bundle['world_state']['regions']) == 32

found = {}
states = {}
for snap in bundle['history']:
    turn = snap['turn']
    ph = snap['livelihoods']['public_health']
    care = snap['livelihoods']['epidemic_care']
    source = turn - 1
    yes = {
        'supplied_paid_care_with_prepaid_carry': (
            any(row['food_milli'] > 0 for row in ph['supplies'])
            and any(row['wages_paid_milli'] > 0 for row in care['frame'])
            and any(row['care_carry_after'] > 0 for row in ph['funding'])),
        'paid_staffed_guard': any(row['staffed'] for row in ph['guards']),
        'guard_prepaid_carry_reused': any(row['guard_carry_before'] > 0 and row['guard_paid_milli'] > 0
                                         for row in ph['funding']),
        'delayed_outbreak_report_pending': any(row['delivery'] > source for row in ph['reports']),
    }
    for name, active in yes.items():
        if active and name not in found:
            found[name] = turn
    if any(yes.values()):
        states[turn] = {'source_turn': source, 'active': [name for name, active in yes.items() if active],
                        'food_milli': sum(row['food_milli'] for row in ph['supplies']),
                        'care_paid_milli': sum(row['wages_paid_milli'] for row in care['frame']),
                        'staffed_guards': sum(row['staffed'] for row in ph['guards']),
                        'funding': ph['funding']}
points = set(found.values())
if found.get('supplied_paid_care_with_prepaid_carry', 0) > 1:
    points.add(found['supplied_paid_care_with_prepaid_carry'] - 1)
points = sorted(k for k in points if 0 < k < 200)
assert points and len(points) <= 5

output = Path('/workspace/evidence/health/active-resume-v1')
assert not output.exists(), 'preserve previous evidence'
output.mkdir(parents=True)
identity = HS.SR.source_identity(HS.SCREEN)
plan = {'source_identity': identity,
        'bundle': str(bundle_path), 'bundle_sha256': hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'categories': found, 'ks': points,
        'missing': [name for name in yes if name not in found],
        'checkpoint_states': {k: states.get(k, {'before_first_material_service': True}) for k in points}}
(output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
cli = list(HS.BASE)
i = cli.index('--turns')
del cli[i:i+2]
cli.remove('--simulate-only')
cli += list(HS.SCREEN.arms['PA'][0]) + ['--seed', '19', *HS.SR.PROCEDURAL]
CI.CASES['health_pa_p19_active'] = (cli, 200, 0, 'spread')
report = CI.run_case(output, 'health_pa_p19_active', ks=points, jobs=1, extra=[], keep=False, resume_hash_seed='0')
report.update(active_plan=plan)
(output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
raise SystemExit(0 if report.get('pass') else 1)
