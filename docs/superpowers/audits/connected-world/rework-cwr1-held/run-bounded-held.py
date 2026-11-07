"""One preregistered CWR1 bounded held screen; generic runner owns its start ledger, lead owns registry."""
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
ap.add_argument('--pilot',type=Path,required=True)
ap.add_argument('--expected-protocol-sha',required=True)
a=ap.parse_args()
repo,out=a.checkout.resolve(),a.out.resolve()
if out.exists():
 raise SystemExit(f'refusing existing held directory: {out}; use the unchanged generic --resume for an interrupted run')
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
sp,notes=sr.check_seeds(cwr.SCREEN,sr.load_registry(),reuse='refuse')
assert not problems and not sp, {'screen':problems,'seeds':sp}
assert cwr.HORIZON==120 and len(cwr.ARMS)==12
assert len(sr.jobs_for(cwr.SCREEN,'held','all',list(cwr.ARMS)))==144
assert not sr.check_preregistration(cwr.SCREEN,held=True)
assert hashlib.sha256(cwr.PREREG.read_bytes()).hexdigest()==a.expected_protocol_sha
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
identity=[*sr.source_identity(cwr.SCREEN),sr.preregistration_line(cwr.SCREEN)]
native=next(line for line in identity if line.startswith('native '))
assert native.rsplit(' ',1)[-1]==a.expected_native_sha,native
assert 'dirty-code 0 tracked code files' in identity
pilot_rows,pilot_problems=sr.load_pilot(a.pilot,cwr.SCREEN,identity,sr.Runtime())
assert not pilot_problems,pilot_problems
assert not sr.check_metrics(pilot_rows,'pilot',cwr.SCREEN)
projection=sr.projected_held_core_hours(pilot_rows,cwr.SCREEN)
assert projection is not None and projection*sr.CEILING_MARGIN<=2.0
assert not sr.ledger_conflicts(sr.LEDGER,cwr.SCREEN,'held')
out.mkdir(parents=True)
commands=[]
base=[sys.executable,str(repo/'scripts/cw_rework_screen.py')]
run=[*base,'run',str(out),'--screen','CWR1','--cohort','held','--jobs','1','--pilot',str(a.pilot),'--keep-first']
check=[*base,'check','--screen','CWR1','--cohort','held','--metrics',str(out/'metrics.jsonl')]
report=[*base,'report',str(out/'metrics.jsonl'),'--screen','CWR1']
commands.extend([run,check,report])
start={'status':'STARTING_GENERIC_RUNNER','source':rev,'identity':sr.identity_digest(identity),'source_identity':identity,
 'native_input_count':len(native_receipt['native_inputs']),'native_input_sha256':native_receipt['native_input_sha256'],
 'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'commands':commands,
 'thread_environment':{key:os.environ[key] for key in ('RAYON_NUM_THREADS','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
 'registry_notes':notes,'cohort':'held','preregistered_projection_core_hours':projection,'fixed_margin':sr.CEILING_MARGIN,'protocol_sha256':a.expected_protocol_sha,'pilot_path':str(a.pilot),'pilot_metrics_sha256':hashlib.sha256(a.pilot.read_bytes()).hexdigest(),'held_cohort_start_delegated_to_generic_runner':True}
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
with (out/'report.md').open('w') as log, (out/'report.stderr.log').open('w') as err:
 report_result=subprocess.run(report,stdout=log,stderr=err)
rows=sr.read_rows(out/'metrics.jsonl',cwr.SCREEN) if (out/'metrics.jsonl').exists() else []
metric_problems=sr.check_metrics(rows,'held',cwr.SCREEN)
expected={(arm,sr.TAGS[stratum],seed) for arm in cwr.ARMS for stratum,seeds in cwr.SCREEN.held.items() for seed in seeds}
if {(r['arm'],r['stratum'],r['seed']) for r in rows}!=expected or len(rows)!=144:
 metric_problems.append('held screen does not contain the exact144 declared cases')
if [*sr.source_identity(cwr.SCREEN),sr.preregistration_line(cwr.SCREEN)]!=identity:
 metric_problems.append('source/native/protocol identity changed during held screen')
source_lines=sr.identity_of((out/'source.txt').read_text()) if (out/'source.txt').exists() else []
if source_lines!=identity:
 metric_problems.append('generic runner source identity differs')
if {r['identity'] for r in rows}!={sr.identity_digest(identity)}:
 metric_problems.append('metric row identity differs from source receipt')
used_hours=sum(sr.run_seconds(r) for r in rows)/3600
ceiling=sr.compute_ceiling(sr.preregistration_text(cwr.SCREEN))
passed=(result.returncode==check_result.returncode==report_result.returncode==0 and not metric_problems)
budget_pass=used_hours<=ceiling and result.returncode!=sr.RC_CEILING
budget_stopped=result.returncode==sr.RC_CEILING
receipt={**start,'status':'PASS' if passed and budget_pass else 'BUDGET_STOP' if budget_stopped or used_hours>ceiling else 'FAIL',
 'rows':len(rows),'failures':[{'arm':r['arm'],'stratum':r['stratum'],'seed':r['seed'],'rc':r['rc'],'error':r.get('error')} for r in rows if r['rc']],
 'run_returncode':result.returncode,'check_returncode':check_result.returncode,'report_returncode':report_result.returncode,
 'metric_problems':metric_problems,'simulation_seconds':sum(r.get('wall_s',0) for r in rows),
 'extraction_seconds':sum(r.get('extract_s',0) for r in rows),'actual_run_core_hours':used_hours,'preregistered_projection_core_hours':projection,
 'fixed_margin':sr.CEILING_MARGIN,'preregistered_projection_with_margin_core_hours':projection*sr.CEILING_MARGIN,
 'declared_cap_core_hours':ceiling,'budget_pass':budget_pass,'resource_measurement':measurement,'total_observed_wall_seconds':time.perf_counter()-t0,
 'metrics_sha256':hashlib.sha256((out/'metrics.jsonl').read_bytes()).hexdigest() if (out/'metrics.jsonl').exists() else None,
 'report_sha256':hashlib.sha256((out/'report.md').read_bytes()).hexdigest() if (out/'report.md').exists() else None,
 'held_execution_started':(out/'held-run.json').exists(),'generic_held_run_record':str(out/'held-run.json'),'held_seeds_spent_status':'cohort potentially spent once generic start record exists; lead must mark-run even if incomplete'}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ('status','source','rows','simulation_seconds','extraction_seconds','actual_run_core_hours','preregistered_projection_with_margin_core_hours','declared_cap_core_hours','budget_pass','held_execution_started')}),flush=True)
raise SystemExit(0 if passed and budget_pass else 4 if budget_stopped or used_hours>ceiling else 3)
