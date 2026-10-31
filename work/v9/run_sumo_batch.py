"""Locked paired experiment runner; all output values come from actual SUMO runs."""
from pathlib import Path
import sys,json,hashlib,time,argparse,csv
from concurrent.futures import ProcessPoolExecutor,as_completed
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'vendor'))
import numpy as np
import sumo_study as ss

def configs_train():
 return [dict(policy='P0',label='P0'),dict(policy='P2',label='P2')]+[dict(policy='P3',label=f'P3_b{b}_e{e}_{mode}',harm_budget=b,epsilon=e,action_mode=mode) for b in [600,2400,10000] for e in [0,10] for mode in ['multi','strong']]

def worker(job):
 seed,load,missions,configurations,common,out=job
 output=Path(out);output.mkdir(parents=True,exist_ok=True)
 records=[];base=None;base_individual=None;base_hash=None
 for cfg in configurations:
  cfg=dict(cfg);policy=cfg.pop('policy');label=cfg.pop('label')
  r=ss.run_case(seed,load,missions,policy,output=output,**(common|cfg))
  counts=r.pop('history').astype(np.int32)
  event_file=Path(r['trace_file']).with_name(Path(r['trace_file']).stem+'_ordinary_events.csv')
  with event_file.open() as f:events=list(csv.DictReader(f))
  individual={x['id']:float(x['restricted_residence']) for x in events}
  if policy=='P0':base=counts;base_individual=individual;base_hash=r['schedule_sha256']
  if base is None:raise ValueError('First policy must be P0')
  assert r['schedule_sha256']==base_hash and individual.keys()==base_individual.keys()
  idelta=np.array([individual[k]-base_individual[k] for k in individual])
  r['positive_individual_residence_vehicle_s']=float(np.maximum(idelta,0).sum())
  r['negative_individual_residence_vehicle_s']=float(np.maximum(-idelta,0).sum())
  r['ordinary_positive_residence_count']=int((idelta>0).sum())
  r['ordinary_over_60s_residence_count']=int((idelta>60).sum())
  delta=counts-base;step=r['config']['step'];pos=np.maximum(delta,0).sum()*step;neg=np.maximum(-delta,0).sum()*step
  r['label']=label;r['positive_spatial_vehicle_s']=float(pos);r['negative_spatial_vehicle_s']=float(neg);r['delta_residence_vehicle_s']=float(delta.sum()*step)
  assert abs(r['delta_residence_vehicle_s']-(pos-neg))<1e-8
  assert abs(r['delta_residence_vehicle_s']-float(idelta.sum()))<1e-8
  r['terminal_spatial_L1']=int(np.abs(delta[-1]).sum());r['terminal_delta_N']=int(delta[-1].sum())
  r['cumulative_delta_J_last_600s']=float(delta[-int(600/step):].sum()*step)
  # Finite-horizon endpoint and a prespecified fixed600s mission outcome.
  r['ambulance_restricted_600s_mean']=float(np.mean([min(x['travel_s'],600) for x in r['mission_rows']]))
  r['any_mission_over_600s']=int(any(x['censored'] or x['travel_s']>600 for x in r['mission_rows']))
  r['mission_300s_fraction']=float(np.mean([x['censored'] or x['travel_s']>300 for x in r['mission_rows']]))
  r['mission_600s_fraction']=float(np.mean([x['censored'] or x['travel_s']>600 for x in r['mission_rows']]))
  r.pop('whole_episode_population',None);r.pop('partition',None);r.pop('plan_examples',None)
  records.append(r)
 return records

def main():
 ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['train','train_progress','main','sensitivity','ablation']);ap.add_argument('--workers',type=int,default=4);a=ap.parse_args()
 common=dict(step=.5,warmup=1800,horizon=7200,mission_end=5400,save_trace=True)
 if a.phase=='train':
  seeds=list(range(5001,5007));loads=[.7,.9];rates=[4];configs=configs_train()
 elif a.phase=='train_progress':
  seeds=list(range(5001,5007));loads=[.7,.9];rates=[4]
  configs=[dict(policy='P0',label='P0'),dict(policy='P2',label='P2')]+[dict(policy='P3',label=f'P3_b{b}_g{g}',harm_budget=b,epsilon=0,action_mode='strong',progress_guard_s=g) for b in [600,2400,10000] for g in [5,10,20]]
 elif a.phase=='main':
  pick=json.loads((HERE/'selected_policy.json').read_text())['selected_configuration']
  seeds=list(range(48));loads=[.6,.8,.95];rates=[1,4,10]
  configs=[dict(policy=p,label=p) for p in ['P0','P1','P2']]+[dict(policy='P3',label='P3',**pick)]
 elif a.phase=='sensitivity':
  pick=json.loads((HERE/'selected_policy.json').read_text())['selected_configuration']
  seeds=list(range(12));loads=[.6,.95];rates=[4]
  configs=[dict(policy='P0',label='P0'),dict(policy='P2',label='P2'),dict(policy='P3',label='P3',**pick)]
  common['step']=.25
 else:
  pick=json.loads((HERE/'selected_policy.json').read_text())['selected_configuration'];pick['progress_guard_s']=None
  seeds=list(range(12));loads=[.6,.95];rates=[4]
  configs=[dict(policy='P0',label='P0'),dict(policy='P3',label='P3_no_progress',**pick)]
 out=HERE/('sumo_'+a.phase);out.mkdir(exist_ok=True)
 sourcehash=hashlib.sha256((HERE/'sumo_study.py').read_bytes()).hexdigest()
 protocol=dict(phase=a.phase,seeds=seeds,loads=loads,missions_per_hour=rates,configurations=configs,common=common,model_sha256=sourcehash,runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),locked_at_unix=time.time(),expected_runs=len(seeds)*len(loads)*len(rates)*len(configs),inference_unit='scenario seed; missions clustered within each episode',primary_comparison='P3 minus P2; ambulance mean and positive spatial occupancy exposure',scope='synthetic microscopic simulation; no field calibration')
 (out/'protocol.json').write_text(json.dumps(protocol,indent=2))
 jobs=[(s,x,m,configs,common,str(out/'runs')) for s in seeds for x in loads for m in rates]
 started=time.perf_counter();allrows=[]
 with (out/'records.jsonl').open('w') as f,ProcessPoolExecutor(max_workers=a.workers) as pool:
  fs={pool.submit(worker,j):j[:3] for j in jobs}
  for i,future in enumerate(as_completed(fs),1):
   try:rr=future.result()
   except Exception as e:
    (out/'failure.json').write_text(json.dumps(dict(job=fs[future],error=repr(e)),indent=2));raise
   allrows+=rr
   for r in rr:f.write(json.dumps(r)+'\n')
   f.flush()
   if i%4==0 or i==len(jobs):print(a.phase,i,'/',len(jobs),'scenarios;',len(allrows),'runs;',round(time.perf_counter()-started,1),'s',flush=True)
 allrows.sort(key=lambda r:(r['seed'],r['load'],r['missions'],r['label']))
 (out/'records.json').write_text(json.dumps(allrows,indent=2))
 summary=dict(actual_runs=len(allrows),seconds=time.perf_counter()-started,model_sha256=sourcehash,collisions=sum(r['colliding_vehicle_events'] for r in allrows),teleports=sum(r['starting_teleport_events'] for r in allrows),census_max=max(r['partition_identity_max_error'] for r in allrows),residence_max=max(r['residence_identity_error'] for r in allrows))
 (out/'run_summary.json').write_text(json.dumps(summary,indent=2));print(summary,flush=True)
if __name__=='__main__':main()
