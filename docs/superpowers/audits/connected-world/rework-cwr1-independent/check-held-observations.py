#!/usr/bin/env python3
"""Independent fixed-harm rendering, activation/coverage and receipt crosschecks.

Reads the completed frozen CWR1 artifacts only. No simulation or production
module import, new outcome selection, registry write or producer write.
"""
import argparse
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path
import resource
import statistics
import time

ARMS = ('RD','AD','RL','AL','MX','IX','WX','TX','RPC','APC','RNR','ANR')
PARENTS = {'AD':'RD','RL':'RD','AL':'RL','MX':'AD','IX':'AD','WX':'AD','TX':'AD','RPC':'RD','APC':'RPC','RNR':'RD','ANR':'RNR'}
SEEDS = {'t':tuple(range(4101,4107)), 'p':tuple(range(4201,4207))}
HARMS = {'population':'Population at the end (sum over civilizations)', 'treasury':'Treasury at the end (sum over civilizations)',
 'food_shortfall':'Food shortfall after relief over the run (food)', 'priced_out_persons':'Priced-out person-turns',
 'priced_out_children':'Priced-out child-turns', 'deaths_famine':'Deaths by famine (the famine authority)',
 'deaths_epidemic':'Deaths by epidemic (the epidemic authority)', 'deaths_war':'Deaths by war (the casualty authority)',
 'out_migration':'Agents migrating between regions over the run', 'wealth_gini':'Mean wealth Gini of living civilizations at the end',
 'forest_stand':'Timber stand share of capacity at the end'}
OBS = ('person_turns','food_shortfall_per_1000_pt','epidemic_deaths_per_1000_pt','a6_personal_rows','a6_would_rows','d3_input_rows',
 'a6_information_turns','combined_migration_input_rows','combined_native_choice_changes','a6_offer_declines','a6_would_decline_offers',
 'a6_work_observed','a6_work_unknown','trade_unknown_destination','trade_personal_return_refusal','care_covered_region_turns',
 'water_service_region_turns','care_paid_milli','food_consumed_milli','retail_access_deficit','retail_access_unknown_region_turns',
 'retail_free_rations_observed','retail_priority_household_turns','retail_free_to_priority_observed','merge_validated_turns','merge_truncated_turns')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def near(a,b):return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-10)
def description(values):
 if not values:return None
 mean=statistics.mean(values)
 flips=[math.fsum(sign*v for sign,v in zip(signs,values))/len(values) for signs in itertools.product((-1,1),repeat=len(values))]
 return {'n':len(values),'mean':mean,'min':min(values),'max':max(values),'positive':sum(v>0 for v in values),'negative':sum(v<0 for v in values),'zero':sum(v==0 for v in values),'sign_flip_extreme':sum(abs(v)>=abs(mean)-1e-12*max(1,abs(mean)) for v in flips),'sign_flip_assignments':len(flips),'sign_flip_min':min(flips),'sign_flip_max':max(flips)}
def cells(values):
 d=description(values)
 if d is None:return ['n/a','0 / 0 / 0','n/a']
 return [f"{d['mean']:+.4g} [{d['min']:+.4g}, {d['max']:+.4g}]",f"{d['positive']} / {d['negative']} / {d['zero']}",f"{d['sign_flip_extreme']}/{d['sign_flip_assignments']} as extreme; means [{d['sign_flip_min']:+.4g}, {d['sign_flip_max']:+.4g}]"]

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--directory',type=Path,required=True);ap.add_argument('--arithmetic',type=Path,required=True);ap.add_argument('--protocol',type=Path,required=True);ap.add_argument('--receipt',type=Path,required=True)
 a=ap.parse_args()
 if a.receipt.exists():ap.error('receipt exists; choose a new destination')
 start=time.perf_counter();before=resource.getrusage(resource.RUSAGE_SELF)
 rows=[json.loads(s) for s in (a.directory/'metrics.jsonl').read_text().splitlines() if s]
 by={(r['arm'],r['stratum'],r['seed']):r for r in rows}
 expected={(arm,tag,s) for arm in ARMS for tag,seeds in SEEDS.items() for s in seeds}
 assert len(rows)==144 and set(by)==expected and all(r['rc']==0 for r in rows)
 arithmetic=json.loads(a.arithmetic.read_text());original=json.loads((a.directory/'receipt.json').read_text());resource_record=json.loads((a.directory/'resource-measurement.json').read_text());ledger=json.loads((a.directory/'held-run.json').read_text())
 assert arithmetic['status']==original['status']=='PASS' and original['run_returncode']==original['check_returncode']==original['report_returncode']==0
 assert original['identity']==arithmetic['identity']==ledger['identity'] and ledger['screen']=='CWR1' and ledger['cohort']=='held'
 assert sha(a.directory/'metrics.jsonl')==original['metrics_sha256']==arithmetic['metrics_sha256']=='6c56e3ffa725848c69aecf6f2edfcdf81adb18e5c5f038562e2c9d3c73ace9e0'
 assert sha(a.directory/'report.md')==original['report_sha256']==arithmetic['report_sha256']=='e5d64f1658265a64ed100d158d650d29eed1f0247d77ea980599c3a145eaf2c3'
 assert sha(a.protocol)==original['protocol_sha256']==ledger['preregistration'].split()[0]=='51b8a336969f48b4beb6f5b3e543062eda71822b98513b337ceb2d010e6efe7a'
 assert resource_record==original['resource_measurement']
 assert 'not simultaneous process-tree memory' in resource_record['rss_scope'] and 'excludes later check/report' in resource_record['cpu_scope']
 seconds=math.fsum(r['wall_s']+r['extract_s'] for r in rows)
 assert near(math.fsum(r['wall_s'] for r in rows),original['simulation_seconds']) and near(math.fsum(r['extract_s'] for r in rows),original['extraction_seconds'])
 assert near(seconds/3600,original['actual_run_core_hours']) and seconds/3600<=2
 table=(a.directory/'report.md').read_text().splitlines();rendered=[]
 for arm,parent in PARENTS.items():
  for harm,label in HARMS.items():
   for tag,seeds in SEEDS.items():
    worlds=[];values=[];formatted=[]
    for seed in seeds:
     left,right=by[arm,tag,seed]['harm'][harm],by[parent,tag,seed]['harm'][harm]
     value=None if left['value'] is None or right['value'] is None else left['value']-right['value']
     worlds.append({'seed':seed,'left':left,'right':right,'difference':value})
     if value is None:
      state=(left if left['value'] is None else right)['state'].replace('_',' ')
      formatted.append(f'{seed}: {state}')
     else:values.append(value);formatted.append(f'{seed}: {value:+.4g}')
    found=[[c.strip() for c in line.split('|')[1:-1]] for line in table if line.startswith(f'| {arm} - {parent} | {label} | {tag} |')]
    assert len(found)==1,(arm,parent,harm,tag,'render row count')
    expect=['requires slice extractor','n/a','n/a','n/a'] if harm in ('deaths_famine','deaths_war') else ['; '.join(formatted),*cells(values)]
    assert found[0][3:7]==expect,(arm,parent,harm,tag,'render arithmetic')
    rendered.append({'arm':arm,'control':parent,'harm':harm,'stratum':tag,'worlds':worlds,'observed_pair_summary':description(values),'full_cohort_summary':description(values) if len(values)==6 else None,'missing_policy':'unknown remains explicit; producer rendered summary describes observed pairs only when some are unavailable'})
 inventory=[]
 for tag,seeds in SEEDS.items():
  for arm in ARMS:
   entries=[by[arm,tag,s] for s in seeds]
   inventory.append({'arm':arm,'stratum':tag,'worlds':[{'seed':r['seed'],'eligibility':r['activation'],'observations':{k:r['m'][k] for k in OBS},'harms':r['harm']} for r in entries],
    'retail_unknown_worlds':sum(r['m']['retail_access_deficit'] is None for r in entries),
    'retail_unknown_region_turns':sum(r['m']['retail_access_unknown_region_turns'] for r in entries),
    'merge_complete_turns':sum(r['m']['merge_validated_turns'] for r in entries),'merge_capped_turns':sum(r['m']['merge_truncated_turns'] for r in entries)})
 after=resource.getrusage(resource.RUSAGE_SELF)
 result={'status':'PASS','source':original['source'],'identity':original['identity'],'protocol_sha256':sha(a.protocol),'metrics_sha256':sha(a.directory/'metrics.jsonl'),'report_sha256':sha(a.directory/'report.md'),'arithmetic_receipt_sha256':sha(a.arithmetic),'producer_receipt_sha256':sha(a.directory/'receipt.json'),'held_start_record_sha256':sha(a.directory/'held-run.json'),'resource_record_sha256':sha(a.directory/'resource-measurement.json'),
 'rendered_fixed_harm_rows_checked':len(rendered),'harm_comparisons':rendered,'all_world_activation_and_observability':inventory,
 'unrecorded_famine_cause_world_arms':sum(r['harm']['deaths_famine']['value'] is None for r in rows),'unrecorded_war_cause_world_arms':sum(r['harm']['deaths_war']['value'] is None for r in rows),'unrecorded_forest_world_arms':sum(r['harm']['forest_stand']['value'] is None for r in rows),
 'simulation_plus_extraction_seconds':seconds,'counted_core_hours':seconds/3600,'declared_cap_core_hours':2,'producer_resource_observation':resource_record,'producer_descendant_cpu_seconds':resource_record['descendant_user_cpu_seconds']+resource_record['descendant_system_cpu_seconds'],
 'review_cpu_seconds':after.ru_utime-before.ru_utime+after.ru_stime-before.ru_stime,'review_wall_seconds':time.perf_counter()-start,'native_or_simulation_import':False,'producer_or_registry_writes':False,'checker_sha256':sha(Path(__file__)),
 'interpretation':'Only preregistered within-CWR recipes are compared. Historical CW6 differs in source/rules,D3 ownership,crowding recipes and seeds; old-to-new differences are not gains from one fix. Activation is observed, never an inclusion filter. Observed retail subtotals have endogenous coverage. Raw retained-first-world checks are a separate limited24case sample.'}
 a.receipt.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print(json.dumps({k:result[k] for k in ('status','rendered_fixed_harm_rows_checked','counted_core_hours','unrecorded_famine_cause_world_arms','unrecorded_war_cause_world_arms','unrecorded_forest_world_arms','review_cpu_seconds')}))
if __name__=='__main__':main()
