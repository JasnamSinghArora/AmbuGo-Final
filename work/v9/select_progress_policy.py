from pathlib import Path
import json,time,hashlib
import numpy as np
H=Path(__file__).resolve().parent
r=json.loads((H/'sumo_train_progress/records.json').read_text())
g={}
for x in r:g.setdefault(x['label'],{})[(x['seed'],x['load'],x['missions'])]=x
keys=sorted(g['P2']);rows=[]
for label,z in sorted(g.items()):
 if not label.startswith('P3'):continue
 a=np.array([z[k]['ambulance_mean_s']-g['P2'][k]['ambulance_mean_s'] for k in keys]);b=np.array([z[k]['positive_spatial_vehicle_s'] for k in keys]);dj=np.array([z[k]['delta_residence_vehicle_s'] for k in keys]);cfg=z[keys[0]]['config']
 rows.append(dict(label=label,delta_ambulance_s=float(a.mean()),mean_positive_exposure_vehicle_s=float(b.mean()),delta_positive_exposure_vs_P2_vehicle_s=float(np.mean([z[k]['positive_spatial_vehicle_s']-g['P2'][k]['positive_spatial_vehicle_s'] for k in keys])),mean_signed_residence_vehicle_s=float(dj.mean()),eligible=bool(a.mean()<=20),configuration={k:cfg[k] for k in ['harm_budget','epsilon','action_mode','progress_guard_s']}))
valid=[x for x in rows if x['eligible']]
selected=min(valid,key=lambda x:(x['mean_positive_exposure_vehicle_s'],x['delta_ambulance_s'],x['label'])) if valid else min(rows,key=lambda x:(x['delta_ambulance_s'],x['label']))
out=dict(rule='Among progress-guard candidates with training episode-mean ambulance time no more than 20 s above P2, choose minimum mean positive 68-group spatial occupancy exposure; if none qualify choose least time increase and declare failure of training constraint.',training_scenarios=len(keys),selected_configuration=selected['configuration'],selected_label=selected['label'],training_constraint_satisfied=bool(valid),locked_before_main_unix=time.time(),model_sha256=hashlib.sha256((H/'sumo_study.py').read_bytes()).hexdigest(),rows=rows)
prior=H/'selected_policy.json'
if prior.exists() and not (H/'selected_policy_initial.json').exists():(H/'selected_policy_initial.json').write_bytes(prior.read_bytes())
prior.write_text(json.dumps(out,indent=2))
for x in rows:print(x['label'],round(x['delta_ambulance_s'],2),round(x['mean_positive_exposure_vehicle_s']/3600,3),round(x['delta_positive_exposure_vs_P2_vehicle_s']/3600,3),x['eligible'])
print('SELECTED',selected)
