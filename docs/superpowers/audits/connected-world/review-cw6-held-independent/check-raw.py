from pathlib import Path
import hashlib,json,math,sys
import pyarrow.ipc as ipc
from chronicler.bundle_codec import load_bundle
base=Path(sys.argv[1]); rows=[json.loads(s) for s in (base/'metrics.jsonl').read_text().splitlines() if s]
lookup={(r['arm'],r['stratum'],r['seed']):r for r in rows}
arm_modes={'FULL':('adapt','active','transfer',True),'A6R':('record_only','active','transfer',True),'D3R':('adapt','record_only','transfer',True),'D4C':('adapt','active','cost_only',True),'SUP':('adapt','active','transfer',False)}
def close(a,b): assert math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-7),(a,b)
readbacks=[]
requested=set(sys.argv[2:]) or {'p','t'}
for stratum,seed in [('p',881),('t',781)]:
 if stratum not in requested:continue
 for arm,(a6mode,d3mode,d4mode,supply) in arm_modes.items():
  key=arm,stratum,seed
  if key not in lookup:continue
  row=lookup[key];directory=base/'runs'/f'{arm}-{stratum}{seed}';path=directory/'chronicle_bundle.json'
  assert row['rc']==0 and not row['pk'] and (row['activation']['activated'] is True if arm!='FULL' else row['activation']['activated'] is None)
  if not path.exists():continue
  d=load_bundle(path);history=d['history'];assert d['metadata']['seed']==seed and d['metadata']['total_turns']==120 and d['world_state']['seed']==seed and len(history)==120
  assert [s['turn'] for s in history]==list(range(1,121)); nregions=len(d['world_state']['regions']);assert nregions==(32 if stratum=='p' else 8)
  person_turns=balance=deaths=service=total_migrations=0;max_native_closure=0; previous_close=None;meal_rows=supply_rows=requisition_rows=order_rows=0
  for source_turn,snap in enumerate(history):
   lv=snap['livelihoods'];w=lv['wealth_accounting'];frame=w['frame'];world=frame['world'];native=frame['native']
   assert w['source_turn']==frame['turn']==native['source_turn']==source_turn and frame['typed_complete'] is True and native['observed_complete'] is True
   assert all(c['closes'] is True for c in frame['closures']);assert abs(native['balance_closure'])<=1e-8;max_native_closure=max(max_native_closure,abs(native['balance_closure']))
   close(world['close']-world['open'],world['delta'])
   grouped={}; seen_native=set()
   for component in native['rows']:
    identity=component['region'],component['component'];assert identity not in seen_native;seen_native.add(identity);assert math.isfinite(component['amount']);grouped.setdefault(component['component'],[]).append(component['amount'])
   assert set(grouped)==set(native['totals'])
   for component,amounts in grouped.items():close(math.fsum(amounts),native['totals'][component])
   modeled=math.fsum(native['totals'].get(k,0.0) for k in ('income_applied','decay','ceiling_floor','birth_endowment','estate_out','inheritance_in'))
   close(modeled,native['modeled_net']);close(native['transfer_actual'],native['totals'].get('transfer_actual',0.0));close(world['delta']-modeled-native['transfer_actual'],native['balance_closure']);close(native['transfer_actual']-world['typed_net_milli']/1000,native['typed_receipt_difference'])
   if previous_close is not None:close(world['open'],previous_close);assert frame['continuity']['status']=='exact'
   previous_close=world['close'];balance+=world['delta'];deaths+=world['deaths'];pop=snap['regional_population'];assert pop['source_turn']==source_turn and len(pop['counts'])==nregions;person_turns+=sum(pop['counts'])
   for name,mode in [('adaptive_livelihoods',a6mode),('war_consequences',d3mode),('war_requisition',d4mode),('infrastructure_condition','repair'),('movement_branches','funded'),('reform_services','service'),('guild_leagues','mutual')]:
    package=lv[name];assert package['source_turn']==source_turn and package['mode']==mode,(key,name,source_turn)
   for name in ('residence_ledger','epidemic_care','public_health','harvest_cover'):
    assert lv[name]['source_turn']==source_turn,(name,source_turn)
   a6=lv['adaptive_livelihoods'];assert a6['rules']=='2' and a6['frame']['information_gate_installed'] is (a6mode!='record_only')
   if a6mode=='record_only':assert a6['frame']['rows_installed']==0
   assert lv['harvest_cover']['mode']==('loss' if supply else 'record_only')
   for asset in lv['infrastructure_condition']['assets']:
    if asset['status'] in ('serving','failed'):assert 0<=asset['service']<=1;service+=asset['service']
   seen_armies=set();rf=lv['war_requisition']['frame'];assert rf['turn']==source_turn and rf['events_dropped']==0
   for event in rf['events']:
    assert event['source_turn']==source_turn
    kind=event['kind']
    if kind=='consumption':
     meal_rows+=1;assert event['army'] not in seen_armies;seen_armies.add(event['army']);consumed,demand=event['consumed_rations'],event['demanded_rations'];assert 0<=consumed<=demand;close(event['adequacy'],consumed/demand if demand else 0)
    elif kind in ('initial','refill','forage'):
     supply_rows+=1;assert event['removed_milli']>=0
     if d4mode=='transfer':assert event['removed_milli']==500*event['credited_rations']
     else:assert event['credited_rations']==0
    elif kind in ('requisition','cargo_seizure') and event.get('goods')!='timber':
     requisition_rows+=1;credited=sum(r['rations'] for r in event['allocations']);assert event['removed_milli']==event['destroyed_milli']+500*credited
     if kind=='requisition':assert event['removed_milli']==event['commons_milli']+event['granary_milli']+event['owned_milli']
     if d4mode=='cost_only':assert credited==0
   if supply:
    orders=lv['timber_orders'];assert orders['source_turn']==source_turn
    for order in orders['orders']+orders['closed']:
     order_rows+=1;assert order['price_turn']<order['dispatched_turn'];assert order['cargo_open_milli']==order['cargo_milli']+order['delivered_milli']+order['lost_milli']+order['deposited_milli'];assert order['escrowed_milli']==order['credited_milli']+order['refunded_milli']+order['cash']
   else:assert 'timber_orders' not in lv
   total_migrations+=sum(m[2] for m in snap['migration'])
  metrics=row['m'];close(person_turns,metrics['person_turns']);close(balance,metrics['balance_change']);close(deaths,metrics['deaths']);close(service,metrics['service_asset_turns']);close(1000*balance/person_turns,metrics['balance_change_per_1000_pt']);close(1000*deaths/person_turns,metrics['deaths_per_1000_pt']);close(service/(nregions*120),metrics['service_per_region_turn']);assert total_migrations==metrics['all_migrations']
  sidecar=directory/'agent_events.arrow';table=ipc.open_file(sidecar).read_all();kinds=table['event_type'].to_pylist();drivers=table['migration_driver'].to_pylist();turns=table['turn'].to_pylist();assert min(turns)>=0 and max(turns)<=119
  migrations=sum(k=='migration' for k in kinds);unknown=sum(k=='migration' and v==255 for k,v in zip(kinds,drivers));observed_deaths=sum(k=='death' for k in kinds);record=metrics['event_sidecar'];assert migrations==total_migrations==record['migration'];assert unknown==metrics['unknown_migration_drivers']==record['unknown'];assert observed_deaths==deaths==record['deaths'];assert sidecar.stat().st_size==record['bytes'];assert hashlib.sha256(sidecar.read_bytes()).hexdigest()==record['sha256']
  readbacks.append({'arm':arm,'stratum':stratum,'seed':seed,'completed':120,'person_turns':person_turns,'balance_change':balance,'deaths':deaths,'service_asset_turns':service,'max_native_closure':max_native_closure,'meal_rows':meal_rows,'supply_rows':supply_rows,'requisition_rows':requisition_rows,'order_observation_rows':order_rows,'migrations':migrations,'unknown':unknown,'sidecar_sha256':record['sha256']})
  print(arm,stratum,seed,'raw120/date/control/wealth/physical/primary/sidecar PASS',flush=True)
  del d,history,table
out=base/('independent-raw-readback-'+''.join(sorted(requested))+'.json');out.write_text(json.dumps({'reviewer':'evidence','available_metric_rows':len(rows),'raw_readbacks':readbacks},indent=2)+'\n');print('readbacks',len(readbacks),flush=True)
