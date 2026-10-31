from pathlib import Path
import sys,csv,json
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'vendor'))
import numpy as np
from analysis import bootstrap_mean_ci,clopper_pearson

def load(path):
 rows=list(csv.DictReader(path.open()))
 return {(float(r['X']),float(r['rho']),int(r['rep']),r['policy']):r for r in rows}

def main():
 old=load(HERE/'teammate_v8/ambugo_v8/results/eval_runs.csv');new=load(HERE/'v8_corrected/results/eval_runs.csv')
 cells=[];changes=[];contrasts=[]
 for X in [.6,.7,.8,.85,.9,.95]:
  for rho in [0.,.5]:
   for p in ['P0','P1','P2','P3','P3C','P4']:
    rr=[new[X,rho,i,p] for i in range(200)]
    if any(r['amb_tt']=='' for r in rr):raise RuntimeError(('Censored ambulance requires explicit analysis',X,rho,p))
    tt=np.array([float(r['amb_tt']) for r in rr]);base=np.array([float(new[X,rho,i,'P0']['amb_tt']) for i in range(200)])
    dj=np.array([float(r['d_delay_vh']) if p!='P0' else 0. for r in rr])
    c=dict(X=X,rho=rho,policy=p,n=200,ambulance_mean=float(tt.mean()),ambulance_median=float(np.median(tt)),ambulance_p90=float(np.quantile(tt,.9)),ambulance_cvar90=float(np.mean(np.sort(tt)[-20:])),ambulance_difference=bootstrap_mean_ci(tt-base),delta_residence_vh=bootstrap_mean_ci(dj),late_300s=clopper_pearson(int(sum(tt>300)),200),wait_completed_episodes_mean=float(np.mean([float(r['n_wait_over']) for r in rr])),unfinished_mean=float(np.mean([float(r['unfinished']) for r in rr])))
    cells.append(c)
    od=np.array([float(old[X,rho,i,p]['amb_tt']) for i in range(200)]);oj=np.array([float(old[X,rho,i,p]['d_delay_vh']) if p!='P0' else 0. for i in range(200)])
    changes.append(dict(X=X,rho=rho,policy=p,ambulance_model_change=bootstrap_mean_ci(tt-od),paired_effect_model_change=bootstrap_mean_ci(dj-oj)))
   for a,b in [('P2','P1'),('P3','P2'),('P3C','P3'),('P4','P3C')]:
    ta=np.array([float(new[X,rho,i,a]['amb_tt']) for i in range(200)]);tb=np.array([float(new[X,rho,i,b]['amb_tt']) for i in range(200)])
    da=np.array([float(new[X,rho,i,a]['d_delay_vh']) for i in range(200)]);db=np.array([float(new[X,rho,i,b]['d_delay_vh']) for i in range(200)])
    contrasts.append(dict(X=X,rho=rho,contrast=a+'-'+b,ambulance=bootstrap_mean_ci(ta-tb),residence_vh=bootstrap_mean_ci(da-db)))
 out=dict(n_runs=len(new),n_cells=len(cells),independent_seeds_per_cell=200,analysis='Matched mechanical sensitivity with original tuning fixed; not a new preregistered confirmatory experiment',cells=cells,mechanical_changes=changes,contrasts=contrasts)
 (HERE/'corrected_summary.json').write_text(json.dumps(out,indent=2))
 flat=[]
 for c in cells:
  flat.append(dict(X=c['X'],rho=c['rho'],policy=c['policy'],n=200,ambulance_mean=c['ambulance_mean'],ambulance_difference=c['ambulance_difference']['mean'],ambulance_difference_lo=c['ambulance_difference']['ci_low'],ambulance_difference_hi=c['ambulance_difference']['ci_high'],delta_residence_vh=c['delta_residence_vh']['mean'],residence_lo=c['delta_residence_vh']['ci_low'],residence_hi=c['delta_residence_vh']['ci_high'],late_count=c['late_300s']['events'],wait_completed_episodes_mean=c['wait_completed_episodes_mean']))
 with (HERE/'corrected_summary.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
 for c in cells:
  if c['rho']==0 and c['policy'] in ['P0','P2','P4']:print(c['X'],c['policy'],'T',round(c['ambulance_mean'],2),'dJ',round(c['delta_residence_vh']['mean'],3),'CI',round(c['delta_residence_vh']['ci_low'],3),round(c['delta_residence_vh']['ci_high'],3),flush=True)
if __name__=='__main__':main()
