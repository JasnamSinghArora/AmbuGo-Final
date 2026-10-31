"""Recompute a stratified subset of supplied v8 raw runs without modifying them."""
from pathlib import Path
import sys,json,csv,time,math
from concurrent.futures import ProcessPoolExecutor
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'vendor'))
sys.path.insert(0,str(HERE/'teammate_v8/ambugo_v8/scripts'))
import run_experiments as re

def job(a):
    x,rho,seed=a
    return re.run_cell(dict(X=x,rho=rho,rep=seed,pols=re.tuned_policies()))

if __name__=='__main__':
    started=time.perf_counter()
    original=list(csv.DictReader((HERE/'teammate_v8/ambugo_v8/results/eval_runs.csv').open()))
    ref={(float(r['X']),float(r['rho']),int(r['rep']),r['policy']):r for r in original}
    jobs=[(x,r,s) for x in [.6,.7,.8,.85,.9,.95] for r in [0.,.5] for s in [0,37,199]]
    records=[];mismatches=[]
    with ProcessPoolExecutor(max_workers=3) as pool:
        for rows in pool.map(job,jobs):
            for row in rows:
                key=(row['X'],row['rho'],row['rep'],row['policy']);old=ref[key]
                for name in ['amb_tt','delay_vh','delay_ph','max_wait','n_wait_over','max_ped_wait','unfinished','d_delay_vh','d_delay_ph','d_unfinished']:
                    if name not in row:continue
                    actual=row[name];expected=old.get(name,'')
                    if actual is None and expected=='':continue
                    if expected=='' or not math.isclose(float(actual),float(expected),rel_tol=1e-12,abs_tol=1e-9):
                        mismatches.append(dict(key=key,metric=name,actual=actual,expected=expected))
                records.append({k:v for k,v in row.items() if k!='_dN'})
            print('reproduced',len(records),flush=True)
    out=dict(supplied_rows=len(original),recomputed_rows=len(records),scenario_seeds=[0,37,199],loads=[.6,.7,.8,.85,.9,.95],yielding=[0.,.5],mismatches=mismatches,seconds=time.perf_counter()-started,scope='Numerical reproduction of the supplied implementation; not physical validation',records=records)
    (HERE/'v8_reproduction_results.json').write_text(json.dumps(out,indent=2))
    print(json.dumps({k:v for k,v in out.items() if k!='records'},indent=2))
