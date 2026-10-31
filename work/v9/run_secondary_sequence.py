from pathlib import Path
import subprocess,sys
h=Path(__file__).resolve().parent
for script,phase in [('run_sumo_batch.py','sensitivity'),('run_sumo_batch.py','ablation'),('run_sumo_robustness.py','adaptive_base'),('run_sumo_robustness.py','exact_counts')]:
 print('START',phase,flush=True)
 with (h/('sumo_'+phase+'.log')).open('w') as f:subprocess.run([sys.executable,str(h/script),phase,'--workers','4'],stdout=f,stderr=subprocess.STDOUT,check=True)
 print('DONE',phase,flush=True)
