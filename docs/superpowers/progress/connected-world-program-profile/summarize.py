from pathlib import Path
import json
import sys
root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
profiles={p.parent.name:json.loads(p.read_text()) for p in root.glob('*/profile.json')}
worlds=['template_s5','template_s23','proc32_s19','proc32_s31','scaled22k_s42','scaled52k_s7','proc48_s42']
rows=[]
for world in worlds:
 pair=[profiles.get(f'{world}-{arm}') for arm in ('off','full')]
 if any(r is None for r in pair):continue
 off,full=pair; checkpoint={r['turn']:r for r in off['checkpoints']}
 assert off['source_snapshot']==full['source_snapshot']
 assert off['identity']['native_sha256']==full['identity']['native_sha256']
 row={'world':world,'turns':off['case']['turns'],'cpu_ratio':full['run_cpu_seconds']/off['run_cpu_seconds'],
      'wall_ratio':full['run_wall_seconds']/off['run_wall_seconds'],'bundle_ratio':full['bundle_bytes']/off['bundle_bytes'],
      'state_ratio':full['state_bytes']/off['state_bytes'],
      'max_checkpoint_ratio':max(r['bytes']/checkpoint[r['turn']]['bytes'] for r in full['checkpoints']),
      'extra_rss_mib':(full['run_peak_rss_kib']-off['run_peak_rss_kib'])/1024,
      'extraction_problems':full.get('extraction_problems',[]),'source':off['source_snapshot'],'off':{},'full':{}}
 for arm,r in zip(('off','full'),pair):
  row[arm]={key:r[key] for key in ['run_wall_seconds','run_cpu_seconds','run_peak_rss_kib','native_initial_agents',
   'native_peak_agents','bundle_bytes','state_bytes','simulation_output_bytes','sidecars','checkpoints','measurement_bytes']}
 row['flags']=[name for name,yes in [('cpu_over_25_percent',row['cpu_ratio']>1.25),('bundle_doubled',row['bundle_ratio']>=2),
    ('checkpoint_doubled',row['max_checkpoint_ratio']>=2),('rss_over_500_mib',row['extra_rss_mib']>500)] if yes]
 rows.append(row)
result={'status':'complete' if len(profiles)==14 else 'partial','completed':len(profiles),'expected':14,
 'missing':[f'{world}-{arm}' for world in worlds for arm in ('off','full') if f'{world}-{arm}' not in profiles],
 'qualification':False,'note':'single shared-host measurements; population/behavior and records differ; no default promotion',
 'lead_decision':'Flagged overhead accepted as opt-in experimental cost, conditional on no OOM, closure or source-guard failure',
 'pairs':rows}
(root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
for r in rows:print(r['world'],'CPU',round(r['cpu_ratio'],2),'bundle',round(r['bundle_ratio'],2),'checkpoint',round(r['max_checkpoint_ratio'],2),'extraRSSMiB',round(r['extra_rss_mib'],1),'errors',len(r['extraction_problems']))
print('completed',len(profiles),'of14')
