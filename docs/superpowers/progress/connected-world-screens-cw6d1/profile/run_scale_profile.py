import argparse,json,os,resource,subprocess,sys,time
from pathlib import Path
checkout=Path(__file__).resolve().parents[5]
parser=argparse.ArgumentParser(description='D1 bounded declared-scale profile, not qualification')
parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args()
root=args.output_dir.resolve()
root.mkdir(exist_ok=True)
base=['--agents','hybrid','--simulate-only','--food-allocation','--household-retail','--household-retail-boundary','all','--grain-reserves']
features=['--reform-services','--guild-leagues']
child=r'''
import json,sys,time,resource
from pathlib import Path
import chronicler.main as cm
from chronicler.run_checkpoint import read_checkpoint
original=cm._write_exact_checkpoint
measures=[]
def measure(*a,**k):
 t=time.perf_counter();p=original(*a,**k);written=time.perf_counter()-t
 t=time.perf_counter();loaded=read_checkpoint(p);read=time.perf_counter()-t
 measures.append(dict(turn=loaded.state.world.turn,bytes=Path(p).stat().st_size,write_seconds=written,read_seconds=read))
 return p
cm._write_exact_checkpoint=measure
args=sys.argv[2:]
if sys.argv[1]!='0':
 from chronicler.utils import sync_civ_population
 old=cm.generate_world
 target=int(sys.argv[1])
 def scaled(*a,**k):
  w=old(*a,**k);m=target/max(1,sum(r.population for r in w.regions))
  for r in w.regions:r.carrying_capacity=max(1,round(r.carrying_capacity*m));r.population=round(r.population*m)
  for c in w.civilizations:sync_civ_population(c,w)
  return w
 cm.generate_world=scaled
sys.argv=['chronicler',*args];cm.main()
output=Path(args[args.index('--output')+1]).parent
(output/'checkpoint-metrics.json').write_text(json.dumps(measures))
(output/'process.json').write_text(json.dumps(dict(peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)))
'''
cases=[]
for seed in (5,23):cases.append((f't{seed}',0,['--seed',str(seed),'--turns','200','--checkpoint-turns','50,100,150,199']))
for seed in (19,31):cases.append((f'p{seed}',0,['--seed',str(seed),'--turns','200','--worldgen','procedural','--regions','32','--civs','10','--checkpoint-turns','50,100,150,199']))
cases.extend([('scaled22k',18800,['--seed','42','--regions','12','--civs','4','--turns','30','--validation-sidecar','--checkpoint-turns','29']),('scaled52k',43700,['--seed','7','--regions','12','--civs','4','--turns','20','--checkpoint-turns','19']),('proc48',0,['--seed','42','--regions','48','--civs','10','--turns','150','--validation-sidecar','--checkpoint-turns','149'])])
env={**os.environ,'PYTHONPATH':str(checkout/'src'),'PYTHONHASHSEED':'0','RAYON_NUM_THREADS':'1','CHRONICLER_QUIET':'1'}
rows=[]
for name,target,args in cases:
 for arm,extra in [('off',[]),('on',features)]:
  d=root/(name+'-'+arm);d.mkdir(exist_ok=False)
  before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
  with (d/'run.log').open('w') as f:
   r=subprocess.run([sys.executable,'-c',child,str(target),*base,*args,*extra,'--output',str(d/'chronicle.md'),'--state',str(d/'state.json')],env=env,cwd=checkout,stdout=f,stderr=subprocess.STDOUT)
  after=resource.getrusage(resource.RUSAGE_CHILDREN)
  row=dict(case=name,arm=arm,target=target,rc=r.returncode,wall_seconds=time.perf_counter()-start,cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,peak_rss_kib=json.loads((d/'process.json').read_text())['peak_rss_kib'] if (d/'process.json').exists() else None,output_bytes=sum(p.stat().st_size for p in d.rglob('*') if p.is_file()),bundle_bytes=(d/'chronicle_bundle.json').stat().st_size if (d/'chronicle_bundle.json').exists() else None,state_bytes=(d/'state.json').stat().st_size if (d/'state.json').exists() else None,checkpoints=json.loads((d/'checkpoint-metrics.json').read_text()) if (d/'checkpoint-metrics.json').exists() else [])
  row['files']={str(p.relative_to(d)):p.stat().st_size for p in d.rglob('*') if p.is_file()};rows.append(row);(root/'metrics.json').write_text(json.dumps(rows,indent=2));print(name,arm,row['rc'],round(row['wall_seconds'],2),flush=True)
  if r.returncode:sys.exit(r.returncode)
