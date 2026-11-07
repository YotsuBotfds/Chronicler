"""Source-bound development schema check on shared timing worlds; never budget authority."""
from __future__ import annotations
import argparse
from dataclasses import replace
from functools import partial
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument('--checkout', type=Path, required=True)
ap.add_argument('--expected-source', required=True)
ap.add_argument('--expected-native-sha', required=True)
ap.add_argument('--out', type=Path, required=True)
a = ap.parse_args()
repo, out = a.checkout.resolve(), a.out.resolve()
if out.exists():
    raise SystemExit(f'refusing existing output: {out}')
for key in ('RAYON_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    if os.environ.get(key) != '1':
        raise SystemExit(f'{key}=1 required')
rev = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
if rev != a.expected_source:
    raise SystemExit(f'source differs: {rev}')
if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
    raise SystemExit('tracked source checkout dirty')
os.chdir(repo)
sys.path[:0] = [str(repo / 'src'), str(repo / 'scripts')]
import cw_rework_screen as cwr
sr = cwr.SR
problems = sr.check_screen(cwr.SCREEN)
seed_problems, seed_notes = sr.check_seeds(cwr.SCREEN, sr.load_registry(), reuse='ignore')
if problems or seed_problems:
    raise SystemExit({'screen': problems, 'seeds': seed_problems})
identity = sr.source_identity(cwr.SCREEN)
native = next(line for line in identity if line.startswith('native '))
if native.rsplit(' ', 1)[-1] != a.expected_native_sha:
    raise SystemExit(f'extension differs: {native}')
if 'dirty-code 0 tracked code files' not in identity:
    raise SystemExit('source has dirty code')
digest = sr.identity_digest(identity)
turns = 8
screen = replace(cwr.SCREEN, extract=partial(cwr.extract, expected_turns=turns))
out.mkdir(parents=True)
source = '\n'.join(identity) + '\nrun: development schema only; NOT official timing pilot or held evidence; horizon8\n'
(out / 'source.txt').write_text(source)
harness = Path(__file__).resolve()
(out / 'harness.json').write_text(json.dumps({
    'path': str(harness), 'sha256': hashlib.sha256(harness.read_bytes()).hexdigest(),
    'argv': sys.argv, 'seed_notes': seed_notes,
    'purpose': 'all12 t5 control schema cases plus AD p19; eight turns; no held world; cannot authorize held budget',
}, indent=2) + '\n')

def simulate(cmd):
    directory = Path(cmd[cmd.index('--output') + 1]).parent
    (directory / 'command.json').write_text(json.dumps(cmd, indent=2) + '\n')
    result = sr.simulate(cmd)
    (directory / 'stdout.txt').write_text(result.stdout or '')
    (directory / 'stderr.txt').write_text(result.stderr or '')
    return result

runtime = sr.Runtime(simulate=simulate)
sr.load_bundle_file = cwr.load_bundle_file
jobs = [(arm, 't', 5) for arm in cwr.ARMS] + [('AD', 'p', 19)]
t0 = time.perf_counter()
rows = []
with (out / 'metrics.jsonl').open('w') as fh:
    for arm, tag, seed in jobs:
        row = sr.run_one(screen, runtime, out, 'dev_schema', arm, tag, seed, True, digest, turns)
        rows.append(row)
        fh.write(json.dumps(row, sort_keys=True) + '\n')
        fh.flush()
        print(json.dumps({k: row.get(k) for k in ('arm', 'stratum', 'seed', 'rc', 'wall_s', 'extract_s', 'error')}), flush=True)
        if row['rc']:
            break
if subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() != rev:
    raise SystemExit('source moved during schema check')
if sr.source_identity(cwr.SCREEN) != identity:
    raise SystemExit('source/native identity changed during schema check')
usage, child = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
passed = len(rows) == len(jobs) and all(row['rc'] == 0 for row in rows)
receipt = {'status': 'PASS' if passed else 'FAIL', 'source': rev, 'identity': digest,
    'native': native, 'horizon': turns, 'expected_rows': len(jobs), 'rows': len(rows),
    'failed': [f"{r['arm']}-{r['stratum']}{r['seed']}" for r in rows if r['rc']],
    'wall_seconds': time.perf_counter() - t0,
    'cpu_user_seconds': usage.ru_utime + child.ru_utime,
    'cpu_system_seconds': usage.ru_stime + child.ru_stime,
    'self_peak_rss_kib': usage.ru_maxrss, 'child_peak_rss_kib': child.ru_maxrss,
    'official_budget_authority': False, 'held_seeds_spent': 0}
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt), flush=True)
raise SystemExit(0 if passed else 1)
