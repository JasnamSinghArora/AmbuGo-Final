#!/usr/bin/env python3
"""Replay either development stage in an isolated source copy.

The frozen evaluation source, selected configuration and archived records in the
main extraction are never overwritten. Dependencies must already be installed
in work/v9/vendor. The replay reuses that local runtime by a directory link.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys
HERE=Path(__file__).resolve().parent;PROJECT=HERE.parents[1]


def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('stage',choices=['initial','progress']);ap.add_argument('--workers',type=int,default=4);ap.add_argument('--output');ap.add_argument('--copy-vendor',action='store_true',help='Copy installed dependencies if directory links are unavailable');a=ap.parse_args()
 dest=Path(a.output).resolve() if a.output else PROJECT/'replays'/('training_'+a.stage)
 if dest.exists() and any(dest.iterdir()):raise ValueError('Replay destination must be new or empty')
 vendor=HERE/'vendor'
 if not vendor.is_dir():raise FileNotFoundError('Install requirements into work/v9/vendor first')
 target=dest/'work/v9';target.mkdir(parents=True,exist_ok=True)
 phase='train' if a.stage=='initial' else 'train_progress'
 model=HERE/('sumo_study_initial.py' if a.stage=='initial' else 'sumo_study.py')
 frozen=json.loads((HERE/'sumo_frozen_source.json').read_text());expected=frozen['initial_sha256'] if a.stage=='initial' else frozen['sha256']
 h=hashlib.sha256(model.read_bytes()).hexdigest()
 if h!=expected:raise RuntimeError('Requested archived model hash mismatch')
 shutil.copy2(model,target/'sumo_study.py')
 for n in ['run_sumo_batch.py','select_policy.py','select_progress_policy.py']:
  shutil.copy2(HERE/n,target/n)
 fixture=dest/'outputs/AmbuGo_v7_Synthetic_Data';fixture.mkdir(parents=True,exist_ok=True)
 for n in ['nodes.csv','edges.csv','vehicle_classes.csv','od_probabilities.csv']:
  shutil.copy2(PROJECT/'outputs/AmbuGo_v7_Synthetic_Data'/n,fixture/n)
 if a.copy_vendor:shutil.copytree(vendor,target/'vendor')
 else:
  try:(target/'vendor').symlink_to(vendor.resolve(),target_is_directory=True)
  except OSError as e:raise RuntimeError('Directory link unavailable; rerun in a new destination with --copy-vendor') from e
 env=os.environ.copy();env['PYTHONPATH']=str(target/'vendor')+os.pathsep+env.get('PYTHONPATH','')
 subprocess.run([sys.executable,str(target/'run_sumo_batch.py'),phase,'--workers',str(a.workers)],cwd=dest,env=env,check=True)
 selector='select_policy.py' if a.stage=='initial' else 'select_progress_policy.py'
 subprocess.run([sys.executable,str(target/selector)],cwd=dest,env=env,check=True)
 print(json.dumps(dict(replay_project=str(dest),stage=a.stage,model_sha256=h,selected_configuration_file=str(target/'selected_policy.json'),scope='Independent replay folder; original extraction was not overwritten'),indent=2))
if __name__=='__main__':main()
