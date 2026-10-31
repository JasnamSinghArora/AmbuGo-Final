"""Seed-block inference for completed held-out microscopic experiments."""
from pathlib import Path
import json,csv,hashlib,sys
import numpy as np
from scipy.stats import beta
H=Path(__file__).resolve().parent
F={'time_s':'ambulance_mean_s','restricted_600_s':'ambulance_restricted_600s_mean','A_vh':'positive_spatial_vehicle_s','Dplus_vh':'positive_individual_residence_vehicle_s','deltaJ_vh':'delta_residence_vehicle_s','tail300':'mission_300s_fraction','tail600':'mission_600s_fraction','requests':'priority_request_ticks','admissions':'priority_phase_admissions','terminalL1':'terminal_spatial_L1','unfinished':'unfinished_ordinary','external_end':'source_waiting_end','fallbacks':'progress_guard_fallbacks'}
SCALE={k:3600 if k.endswith('_vh') else 1 for k in F}
def boot(x,key):
 x=np.asarray(x,dtype=float);rng=np.random.default_rng(int(hashlib.sha256(key.encode()).hexdigest()[:16],16));idx=rng.integers(0,len(x),size=(10000,len(x)))
 bs=x[idx].mean(axis=1)
 return dict(mean=float(x.mean()),lo=float(np.quantile(bs,.025)),hi=float(np.quantile(bs,.975)),n=len(x),sd=float(x.std(ddof=1)))
def vec(rows,metric):return np.array([r[F[metric]] for r in rows],float)/SCALE[metric]
def run():
 records=json.loads((H/'sumo_main/records.json').read_text());prot=json.loads((H/'sumo_main/protocol.json').read_text())
 assert len(records)==prot['expected_runs']==1728
 assert hashlib.sha256((H/'sumo_study.py').read_bytes()).hexdigest()==prot['model_sha256']
 ids={(r['seed'],r['load'],r['missions'],r['policy']):r for r in records};assert len(ids)==len(records)
 seeds=prot['seeds'];conds=[(x,m) for x in prot['loads'] for m in prot['missions_per_hour']]
 for s in seeds:
  for x,m in conds:
   z=[ids[s,x,m,p] for p in ['P0','P1','P2','P3']]
   assert len({r['schedule_sha256'] for r in z})==1
   assert len({tuple((a['id'],a['dispatch'],a['origin']) for a in r['mission_rows']) for r in z})==1
   assert len({r['n_ordinary'] for r in z})==1
   for r in z:
    assert r['config']['horizon']-max(a['dispatch'] for a in r['mission_rows'])>=600
    assert abs(r['delta_residence_vehicle_s']-(r['positive_individual_residence_vehicle_s']-r['negative_individual_residence_vehicle_s']))<1e-8
 cells=[];contrasts=[];aggregate={};aggregate_contrasts=[]
 for x,m in conds:
  by={p:[ids[s,x,m,p] for s in seeds] for p in ['P0','P1','P2','P3']}
  for p,rr in by.items():
   event=sum(r['any_mission_over_600s'] for r in rr)
   cells.append(dict(load=x,missions=m,policy=p,metrics={f:boot(vec(rr,f),f'{x}-{m}-{p}-{f}') for f in F},missions_total=m*len(seeds),missions_completed=sum(r['missions_completed'] for r in rr),over600_episodes=event,over600_episode_CP95=[0 if event==0 else float(beta.ppf(.025,event,len(seeds)-event+1)),1 if event==len(seeds) else float(beta.ppf(.975,event+1,len(seeds)-event))]))
  for p,q in [('P1','P0'),('P2','P0'),('P3','P0'),('P2','P1'),('P3','P2')]:
   contrasts.append(dict(load=x,missions=m,comparison=p+'-'+q,metrics={f:boot(vec(by[p],f)-vec(by[q],f),f'{x}-{m}-{p}-{q}-{f}') for f in F}))
 for p in ['P0','P1','P2','P3']:
  aggregate[p]={f:boot([np.mean([ids[s,x,m,p][F[f]]/SCALE[f] for x,m in conds]) for s in seeds],f'agg-{p}-{f}') for f in F}
 for p,q in [('P1','P0'),('P2','P0'),('P3','P0'),('P2','P1'),('P3','P2')]:
  vals={f:np.array([np.mean([(ids[s,x,m,p][F[f]]-ids[s,x,m,q][F[f]])/SCALE[f] for x,m in conds]) for s in seeds]) for f in F}
  aggregate_contrasts.append(dict(comparison=p+'-'+q,metrics={f:boot(vals[f],f'agg-{p}-{q}-{f}') for f in F}))
 runtimes=np.array([r['wall_time_s'] for r in records]);decisions=np.array([r['active_decision_ticks'] for r in records]);ct=np.array([r['controller_wall_time_s'] for r in records]);valid=decisions>0
 verification={k:sum(r[k] for r in records) for k in ['colliding_vehicle_events','starting_teleport_events','signal_timing_violations']}
 verification.update(partition_max=max(r['partition_identity_max_error'] for r in records),residence_max=max(r['residence_identity_error'] for r in records),source_waiting_max=max(r['source_waiting_end'] for r in records),unfinished_range=[min(r['unfinished_ordinary'] for r in records),max(r['unfinished_ordinary'] for r in records)],max_simultaneous_ambulances=max(r['max_simultaneous_ambulances'] for r in records),all_missions_completed=all(r['missions_completed']==r['missions'] for r in records),max_ambulance_s=max(r['ambulance_max_s'] for r in records),runtime_median_s=float(np.median(runtimes)),runtime_p95_s=float(np.quantile(runtimes,.95)),controller_total_per_control_tick_ms=float(1000*ct.sum()/sum(r['config']['horizon'] for r in records)),episode_mean_controller_ms_p95=float(np.quantile([1000*r['controller_wall_time_s']/r['config']['horizon'] for r in records],.95)),max_service_age=max(r['max_service_age_s'] for r in records),completed_signal_intervals=sum(r['completed_signal_intervals'] for r in records),n_mission_trips=sum(r['missions'] for r in records),scenario_pairs_verified=len(seeds)*len(conds),fallback_total=sum(r['progress_guard_fallbacks'] for r in records if r['policy']=='P3'),p3_missions=sum(r['missions'] for r in records if r['policy']=='P3'))
 out=dict(protocol=prot,cells=cells,contrasts=contrasts,aggregate=aggregate,aggregate_contrasts=aggregate_contrasts,verification=verification)
 sensitivity=[]
 for phase in ['sensitivity','ablation','adaptive_base','exact_counts']:
  file=H/('sumo_'+phase)/'records.json'
  if not file.exists():continue
  rr=json.loads(file.read_text());p2=json.loads((file.parent/'protocol.json').read_text());assert len(rr)==p2['expected_runs'];d={(r['seed'],r['load'],r['missions'],r['policy']):r for r in rr}
  assert len(d)==len(rr)
  for r in rr:assert r['schedule_sha256']==ids[r['seed'],r['load'],r['missions'],r['policy']]['schedule_sha256']
  for x in sorted({r['load'] for r in rr}):
   sk=sorted({r['seed'] for r in rr});metrics={}
   for f in F:
    if phase!='ablation':
     # Difference in P3-P2 treatment contrasts between .25 and .5 physical steps.
     a=[((d[s,x,4,'P3'][F[f]]-d[s,x,4,'P2'][F[f]])-(ids[s,x,4,'P3'][F[f]]-ids[s,x,4,'P2'][F[f]]))/SCALE[f] for s in sk]
    else:
     # No-progress P3 minus guarded P3, baseline stays identical.
     a=[(d[s,x,4,'P3'][F[f]]-ids[s,x,4,'P3'][F[f]])/SCALE[f] for s in sk]
    metrics[f]=boot(a,f'{phase}-{x}-{f}')
   sensitivity.append(dict(phase=phase,load=x,metrics=metrics,raw_contrast={f:boot([(d[s,x,4,'P3'][F[f]]-d[s,x,4,'P2'][F[f]])/SCALE[f] for s in sk],f'raw-{phase}-{x}-{f}') for f in F} if phase!='ablation' else None))
 out['sensitivities']=sensitivity
 (H/'sumo_analysis.json').write_text(json.dumps(out,indent=2))
 with (H/'sumo_cell_summary.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['load','missions','policy']+[v for k in F for v in [k,k+'_lo',k+'_hi']])
  for c in cells:w.writerow([c['load'],c['missions'],c['policy']]+[c['metrics'][k][v] for k in F for v in ['mean','lo','hi']])
 for z in aggregate_contrasts:print(z['comparison'],{k:[round(z['metrics'][k][v],3) for v in ['mean','lo','hi']] for k in ['time_s','A_vh','Dplus_vh','deltaJ_vh']})
 print(json.dumps(verification,indent=2))
if __name__=='__main__':run()
