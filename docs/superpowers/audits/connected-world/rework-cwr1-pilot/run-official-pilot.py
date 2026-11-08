"""One official CWR1 timing/schema pilot; never starts a held run or edits registry."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import resource
from pathlib import Path
import subprocess
import sys
import time

ap=argparse.ArgumentParser()
ap.add_argument('--checkout',type=Path,required=True)
ap.add_argument('--expected-source',required=True)
ap.add_argument('--expected-native-sha',required=True)
ap.add_argument('--native-receipt',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args()
repo,out=a.checkout.resolve(),a.out.resolve()
if out.exists():
 raise SystemExit(f'refusing existing pilot directory: {out}')
for key in ('RAYON_NUM_THREADS','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
 if os.environ.get(key)!='1':raise SystemExit(f'{key}=1 required')
os.chdir(repo)
rev=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert rev==a.expected_source,rev
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],text=True).strip()
sys.path[:0]=[str(repo/'src'),str(repo/'scripts')]
import cw_rework_screen as cwr
sr=cwr.SR
problems=sr.check_screen(cwr.SCREEN)
sp,notes=sr.check_seeds(cwr.SCREEN,sr.load_registry(),reuse='ignore')
assert not problems and not sp, {'screen':problems,'seeds':sp}
assert cwr.HORIZON==120 and len(cwr.ARMS)==12
assert len(sr.jobs_for(cwr.SCREEN,'pilot','all',list(cwr.ARMS)))==24
assert sr.compute_ceiling(sr.preregistration_text(cwr.SCREEN))==2.0
native_receipt=json.loads(a.native_receipt.read_text())
assert native_receipt['native_sha256']==a.expected_native_sha
recorded_paths=[r['path'] for r in native_receipt['native_inputs']]
expected_paths={str(p.relative_to(repo)) for p in (repo/'chronicler-agents'/'src').rglob('*.rs')}
expected_paths.update('chronicler-agents/'+p for p in ('Cargo.toml','Cargo.lock','build.rs'))
assert native_receipt['native_input_count']==len(recorded_paths)==57
assert len(set(recorded_paths))==len(recorded_paths)
assert set(recorded_paths)==expected_paths,'native source inventory differs'
assert hashlib.sha256((repo/'chronicler-agents'/'pyproject.toml').read_bytes()).hexdigest()==native_receipt['pyproject_sha256']
for r in native_receipt['native_inputs']:
 assert hashlib.sha256((repo/r['path']).read_bytes()).hexdigest()==r['sha256'],r['path']
identity=sr.source_identity(cwr.SCREEN)
native=next(line for line in identity if line.startswith('native '))
assert native.rsplit(' ',1)[-1]==a.expected_native_sha,native
assert 'dirty-code 0 tracked code files' in identity
out.mkdir(parents=True)
commands=[]
base=[sys.executable,str(repo/'scripts/cw_rework_screen.py')]
run=[*base,'run',str(out),'--screen','CWR1','--cohort','pilot','--jobs','1','--keep-first']
check=[*base,'check','--screen','CWR1','--cohort','pilot','--metrics',str(out/'metrics.jsonl')]
report=[*base,'report',str(out/'metrics.jsonl'),'--screen','CWR1']
commands.extend([run,check,report])
start={'status':'STARTED','source':rev,'identity':sr.identity_digest(identity),'source_identity':identity,
 'native_input_count':len(native_receipt['native_inputs']),'native_input_sha256':native_receipt['native_input_sha256'],
 'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'commands':commands,
 'thread_environment':{key:os.environ[key] for key in ('RAYON_NUM_THREADS','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
 'registry_notes':notes,'official_budget_authority':True,'held_seeds_spent':0}
(out/'launch.json').write_text(json.dumps(start,indent=2)+'\n')
t0=time.perf_counter()
usage_before=resource.getrusage(resource.RUSAGE_CHILDREN)
with (out/'run.log').open('w') as log:
 result=subprocess.run(run,stdout=log,stderr=subprocess.STDOUT)
runner_wall=time.perf_counter()-t0
usage_after=resource.getrusage(resource.RUSAGE_CHILDREN)
measurement={'runner_wall_seconds':runner_wall,
 'descendant_user_cpu_seconds':usage_after.ru_utime-usage_before.ru_utime,
 'descendant_system_cpu_seconds':usage_after.ru_stime-usage_before.ru_stime,
 'child_max_single_process_rss_kib_before':usage_before.ru_maxrss,
 'child_max_single_process_rss_kib_after':usage_after.ru_maxrss,
 'rss_scope':'Linux RUSAGE_CHILDREN lifetime maximum of a single waited-for child/descendant, including prior identity probe; not simultaneous process-tree memory and not a subtractable maximum',
 'cpu_scope':'RUSAGE_CHILDREN deltas immediately around the fresh generic screen-runner subprocess; includes its waited-for simulation descendants and extraction, excludes later check/report'}
(out/'resource-measurement.json').write_text(json.dumps(measurement,indent=2)+'\n')
with (out/'check.log').open('w') as log:
 check_result=subprocess.run(check,stdout=log,stderr=subprocess.STDOUT)
with (out/'report.log').open('w') as log:
 report_result=subprocess.run(report,stdout=log,stderr=subprocess.STDOUT)
rows=sr.read_rows(out/'metrics.jsonl',cwr.SCREEN) if (out/'metrics.jsonl').exists() else []
metric_problems=sr.check_metrics(rows,'pilot',cwr.SCREEN)
expected={(arm,tag,seed) for arm in cwr.ARMS for tag,seed in [('t',5),('p',19)]}
if {(r['arm'],r['stratum'],r['seed']) for r in rows}!=expected or len(rows)!=24:
 metric_problems.append('official pilot does not contain the exact24 declared cases')
if sr.source_identity(cwr.SCREEN)!=identity:
 metric_problems.append('source/native identity changed during pilot')
source_lines=sr.identity_of((out/'source.txt').read_text()) if (out/'source.txt').exists() else []
if source_lines!=identity:
 metric_problems.append('generic runner source identity differs')
if {r['identity'] for r in rows}!={sr.identity_digest(identity)}:
 metric_problems.append('metric row identity differs from source receipt')
hours=sr.projected_held_core_hours(rows,cwr.SCREEN)
ceiling=sr.compute_ceiling(sr.preregistration_text(cwr.SCREEN))
passed=(result.returncode==check_result.returncode==report_result.returncode==0 and not metric_problems)
budget_pass=hours is not None and hours*sr.CEILING_MARGIN<=ceiling
receipt={**start,'status':'PASS' if passed and budget_pass else 'SCHEMA_FAIL' if not passed else 'BUDGET_FAIL',
 'rows':len(rows),'failures':[{'arm':r['arm'],'stratum':r['stratum'],'seed':r['seed'],'rc':r['rc'],'error':r.get('error')} for r in rows if r['rc']],
 'run_returncode':result.returncode,'check_returncode':check_result.returncode,'report_returncode':report_result.returncode,
 'metric_problems':metric_problems,'simulation_seconds':sum(r.get('wall_s',0) for r in rows),
 'extraction_seconds':sum(r.get('extract_s',0) for r in rows),'projection_core_hours':hours,
 'fixed_margin':sr.CEILING_MARGIN,'projection_with_margin_core_hours':hours*sr.CEILING_MARGIN if hours is not None else None,
 'declared_cap_core_hours':ceiling,'budget_pass':budget_pass,'resource_measurement':measurement,'total_observed_wall_seconds':time.perf_counter()-t0,
 'metrics_sha256':hashlib.sha256((out/'metrics.jsonl').read_bytes()).hexdigest() if (out/'metrics.jsonl').exists() else None,
 'report_sha256':hashlib.sha256((out/'report.md').read_bytes()).hexdigest() if (out/'report.md').exists() else None,
 'held_execution_started':False}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ('status','source','rows','simulation_seconds','extraction_seconds','projection_core_hours','projection_with_margin_core_hours','declared_cap_core_hours','budget_pass','held_seeds_spent')}),flush=True)
raise SystemExit(0 if passed and budget_pass else 3 if not passed else 4)
