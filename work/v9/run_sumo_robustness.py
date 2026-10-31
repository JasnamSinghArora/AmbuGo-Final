"""Secondary robustness to base control and observation quality; fixed before review."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import json,hashlib,time,argparse
from run_sumo_batch import worker
H=Path(__file__).resolve().parent

def main():
 ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['adaptive_base','exact_counts']);ap.add_argument('--workers',type=int,default=8);a=ap.parse_args()
 pick=json.loads((H/'selected_policy.json').read_text())['selected_configuration']
 common=dict(step=.5,warmup=1800,horizon=7200,mission_end=5400,save_trace=True)
 if a.phase=='adaptive_base':common['base']='longest_queue'
 else:common.update(sensor_period=1,sensor_delay=0,sensor_noise=False)
 configs=[dict(policy='P0',label='P0'),dict(policy='P2',label='P2'),dict(policy='P3',label='P3',**pick)]
 seeds=list(range(12));loads=[.6,.95];out=H/('sumo_'+a.phase);out.mkdir(exist_ok=True)
 proto=dict(phase=a.phase,seeds=seeds,loads=loads,missions_per_hour=[4],configurations=configs,common=common,expected_runs=72,model_sha256=hashlib.sha256((H/'sumo_study.py').read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),locked_at_unix=time.time(),scope='Secondary robustness; exact_counts means noiseless current aggregate counts, not exact queues or future traffic.')
 (out/'protocol.json').write_text(json.dumps(proto,indent=2));start=time.perf_counter();rows=[]
 jobs=[(s,x,4,configs,common,str(out/'runs')) for s in seeds for x in loads]
 with ProcessPoolExecutor(max_workers=a.workers) as pool,(out/'records.jsonl').open('w') as f:
  fs={pool.submit(worker,j):j[:3] for j in jobs}
  for i,fu in enumerate(as_completed(fs),1):
   try:rr=fu.result()
   except Exception as e:(out/'failure.json').write_text(json.dumps(dict(job=fs[fu],error=repr(e))));raise
   rows+=rr
   for r in rr:f.write(json.dumps(r)+'\n')
   f.flush()
   if i%4==0:print(a.phase,i,'/24 scenarios',round(time.perf_counter()-start,1),'s',flush=True)
 rows.sort(key=lambda r:(r['seed'],r['load'],r['policy']));(out/'records.json').write_text(json.dumps(rows,indent=2))
 (out/'run_summary.json').write_text(json.dumps(dict(actual_runs=len(rows),seconds=time.perf_counter()-start,collisions=sum(r['colliding_vehicle_events'] for r in rows),teleports=sum(r['starting_teleport_events'] for r in rows),signal_timing_violations=sum(r['signal_timing_violations'] for r in rows),census_max=max(r['partition_identity_max_error'] for r in rows),residence_max=max(r['residence_identity_error'] for r in rows)),indent=2))
if __name__=='__main__':main()
