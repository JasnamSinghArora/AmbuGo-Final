#!/usr/bin/env python3
"""Build the complete portable AmbuGo first-draft replication package.

Run ONLY after every simulation/secondary batch has completed and the final
source/configuration is frozen. This program never modifies runtime source.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,platform,shutil,sys,tempfile,zipfile
from pathlib import Path
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
OUTPUT=PROJECT/'outputs'
PREFIX='AmbuGo_First_Draft_Reproducibility_v9'
FINAL=OUTPUT/(PREFIX+'.zip')
FIXTURE_FILES=['nodes.csv','edges.csv','vehicle_classes.csv','od_probabilities.csv']
EVALUATION_PHASES={'main':1728,'sensitivity':72,'ablation':48,'adaptive_base':72,'exact_counts':72}
REQUIREMENTS='''# Versions used for the synthetic traffic and statistical study.
# Install with: python3 -m pip install --target work/v9/vendor -r requirements.txt
# Python 3.12 and platform-compatible wheels are recommended.
eclipse-sumo==1.28.0
libsumo==1.28.0
traci==1.28.0
sumolib==1.28.0
sumo-data==1.28.0
numpy==2.5.4
scipy==1.18.1
matplotlib==3.11.2
pandas==2.2.3
'''
REQUIRED_TOP=[
 'sumo_study.py','sumo_study_initial.py','run_sumo_batch.py','run_sumo_robustness.py',
 'analysis.py','analyze_sumo.py','analyze_corrected.py','reproduce_v8.py',
 'audit_v8_statistics.py','v8_regression_checks.py','meso.py','meso_checks.py',
 'make_base_figures.py','select_policy.py','select_progress_policy.py',
 'selected_policy.json','selected_policy_initial.json','sumo_frozen_source.json',
 'corrected_summary.json','meso_verification.json','v8_reproduction_results.json',
 'v8_statistics_audit.json','v8_regression_findings.json','sumo_analysis.json',
 'README_reproducibility.txt','verify_zip.py','build_package.py','replay_training.py',
 'paper_core.txt','paper_meso_results.txt','base_figures_notes.txt'
]


def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()


def checked_json(path):
 if not path.is_file():raise FileNotFoundError(path)
 return json.loads(path.read_text())


def check_completeness():
 frozen=checked_json(HERE/'sumo_frozen_source.json');actual=sha(HERE/'sumo_study.py')
 if actual!=frozen['sha256']:raise RuntimeError('Frozen microscopic source hash mismatch')
 if sha(HERE/'sumo_study_initial.py')!=frozen['initial_sha256']:raise RuntimeError('Initial microscopic source hash mismatch')
 known={actual,frozen['initial_sha256']};counts={};records={}
 for phase,expected in EVALUATION_PHASES.items():
  folder=HERE/('sumo_'+phase)
  if (folder/'failure.json').exists():raise RuntimeError('Unresolved failure record in '+str(folder))
  proto=checked_json(folder/'protocol.json');rows=checked_json(folder/'records.json');summ=checked_json(folder/'run_summary.json')
  if len(rows)!=expected or proto['expected_runs']!=expected or summ['actual_runs']!=expected:
   raise RuntimeError(f'Incomplete {phase}: expected {expected}, got {len(rows)}')
  if proto['model_sha256']!=actual:raise RuntimeError('Phase uses a different frozen source: '+phase)
  keys={(r['seed'],r['load'],r['missions'],r['label']) for r in rows}
  if len(keys)!=expected:raise RuntimeError('Duplicate policy-run keys in '+phase)
  for r in rows:
   trace=folder/'runs'/Path(r['trace_file']).name
   for required in [trace,trace.with_suffix('.json'),trace.with_name(trace.stem+'_ordinary_events.csv')]:
    if not required.is_file():raise FileNotFoundError(required)
  counts[phase]=len(rows);records[phase]=rows
 for phase in ['train','train_progress']:
  folder=HERE/('sumo_'+phase);proto=checked_json(folder/'protocol.json');rows=checked_json(folder/'records.json');summ=checked_json(folder/'run_summary.json')
  if len(rows)!=proto['expected_runs'] or summ['actual_runs']!=len(rows):raise RuntimeError('Incomplete development phase '+phase)
  if proto['model_sha256'] not in known:raise RuntimeError('Unknown development source hash')
  counts[phase]=len(rows)
 for name in REQUIRED_TOP:
  if not (HERE/name).is_file():raise FileNotFoundError(HERE/name)
 for name in FIXTURE_FILES:
  if not (OUTPUT/'AmbuGo_v7_Synthetic_Data'/name).is_file():raise FileNotFoundError(name)
 old=HERE/'teammate_v8/ambugo_v8/results/eval_runs.csv';new=HERE/'v8_corrected/results/eval_runs.csv'
 for p in [old,new]:
  with p.open() as f:rows=list(csv.DictReader(f))
  if len(rows)!=14400:raise RuntimeError('Mesoscopic CSV does not contain14400rows: '+str(p))
  if len({(r['X'],r['rho'],r['rep'],r['policy']) for r in rows})!=14400:raise RuntimeError('Duplicate mesoscopic run keys')
 if sum(counts[k] for k in EVALUATION_PHASES)!=1992:raise RuntimeError('Unexpected secondary/main total')
 return frozen,counts,records


def copy_file(src,stage,relative):
 src=Path(src);dest=stage/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)


def copy_filtered_tree(src,stage,relative):
 for p in sorted(Path(src).rglob('*')):
  if not p.is_file():continue
  rel=p.relative_to(src)
  if any(part in {'__pycache__','vendor','.DS_Store','.git'} for part in rel.parts):continue
  if p.suffix in {'.pyc','.pyo','.so','.dylib'}:continue
  copy_file(p,stage,Path(relative)/rel)


def write_index(stage,records):
 index=[]
 for phase,rows in records.items():
  for r in rows:
   old=r['trace_file'];relative='work/v9/sumo_'+phase+'/runs/'+Path(old).name
   index.append(dict(recorded_path=old,package_relative_path=relative,role='microscopic population trace',phase=phase,seed=r['seed'],load=r['load'],missions=r['missions'],policy=r['label']))
 for p in sorted((HERE/'scenarios').glob('*.json')):
  s=checked_json(p);old=s.get('route_file')
  if old:
   index.append(dict(recorded_path=old,package_relative_path='work/v9/archived_scenarios/'+Path(old).name,regenerated_active_path='work/v9/scenarios/'+Path(old).name,role='archived route input; regenerate active cache on extraction'))
 (stage/'PORTABLE_PATH_INDEX.json').write_text(json.dumps(dict(explanation='Recorded absolute paths are retained as provenance. Resolve by package_relative_path; the active scenario cache is intentionally absent.',entries=index),indent=2))
 return len(index)


def build(args):
 # Completion checks happen before staging. No partial experiment is packaged.
 frozen,counts,records=check_completeness();OUTPUT.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='ambugo_package_stage_',dir=HERE) as tmp:
  stage=Path(tmp)/PREFIX;stage.mkdir()
  # Authoring/analysis sources and completed scalar evidence at the study root.
  for p in sorted(HERE.iterdir()):
   if not p.is_file() or p.suffix not in {'.py','.json','.csv','.txt','.md'}:continue
   if p.name.startswith('pilot') or p.name in {'v8_source.txt','portable_package_plan.txt'}:continue
   copy_file(p,stage,Path('work/v9')/p.name)
  for n in FIXTURE_FILES:copy_file(OUTPUT/'AmbuGo_v7_Synthetic_Data'/n,stage,Path('outputs/AmbuGo_v7_Synthetic_Data')/n)
  # Immutable supplied evidence and the separate mechanically corrected source.
  copy_filtered_tree(HERE/'teammate_v8/ambugo_v8',stage,'work/v9/teammate_v8/ambugo_v8')
  copy_filtered_tree(HERE/'v8_corrected',stage,'work/v9/v8_corrected')
  # Avoid redundant generated publication-report copies inside the corrected
  # branch if any appear later, but retain all numerical evidence and source.
  for phase in EVALUATION_PHASES:
   folder=HERE/('sumo_'+phase)
   for p in sorted(folder.iterdir()):
    if p.is_file() and p.suffix in {'.json','.jsonl','.csv','.txt'}:
     copy_file(p,stage,Path('work/v9')/folder.name/p.name)
   for p in sorted((folder/'runs').iterdir()):
    if p.is_file() and p.suffix in {'.json','.npz','.csv','.log'}:
     copy_file(p,stage,Path('work/v9')/folder.name/'runs'/p.name)
  # Development records/protocols are retained; individual development traces
  # are not needed to reproduce the selected-parameter calculation.
  for phase in ['train','train_progress']:
   folder=HERE/('sumo_'+phase)
   for n in ['protocol.json','records.json','run_summary.json']:
    copy_file(folder/n,stage,Path('work/v9')/folder.name/n)
  for folder in ['figures','sumo_network']:
   copy_filtered_tree(HERE/folder,stage,Path('work/v9')/folder)
  # Cached JSON embeds absolute route paths. Preserve it as archived evidence
  # while forcing future traffic reruns to generate a local active cache.
  for p in sorted((HERE/'scenarios').iterdir()):
   if p.is_file() and (p.suffix in {'.json','.xml'}):copy_file(p,stage,Path('work/v9/archived_scenarios')/p.name)
  copy_file(HERE/'README_reproducibility.txt',stage,'README_reproducibility.txt')
  copy_file(HERE/'verify_zip.py',stage,'verify_zip.py')
  (stage/'requirements.txt').write_text(REQUIREMENTS)
  (stage/'requirements-document.txt').write_text('# Optional editable manuscript regeneration\npython-docx==1.2.0\nlxml==6.1.1\n')
  staged_papers=[]
  paper_paths=[Path(x).resolve() for x in args.paper]
  if not paper_paths:
   paper_paths=sorted(list(OUTPUT.glob('*v9*.pdf'))+list(OUTPUT.glob('*v9*.docx')))
  for p in paper_paths:
   if not p.is_file():raise FileNotFoundError(p)
   copy_file(p,stage,Path('manuscript')/p.name);staged_papers.append(p.name)
  index_entries=write_index(stage,records)
  if (stage/'work/v9/scenarios').exists():raise RuntimeError('Active scenario cache must not be packaged')
  if any('vendor' in p.relative_to(stage).parts for p in stage.rglob('*')):raise RuntimeError('Vendor inclusion is forbidden')
  if sha(stage/'work/v9/sumo_study.py')!=frozen['sha256']:raise RuntimeError('Staging changed frozen source')
  files=[]
  for p in sorted(stage.rglob('*')):
   if p.is_file():files.append(dict(path=p.relative_to(stage).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
  manifest=dict(package=PREFIX,created_utc=datetime.now(timezone.utc).isoformat(),provenance='Synthetic computational research; no measured city calibration',frozen_model_sha256=frozen['sha256'],initial_model_sha256=frozen['initial_sha256'],policy_runs=counts,total_microscopic_evaluation_and_secondary_runs=1992,corrected_mesoscopic_policy_runs=14400,manuscripts=staged_papers,portable_path_index_entries=index_entries,python_version=platform.python_version(),build_platform=dict(system=platform.system(),machine=platform.machine()),vendor_binaries_included=False,active_scenario_cache_included=False,files=files)
  (stage/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
  temp_zip=FINAL.with_suffix('.tmp.zip')
  with zipfile.ZipFile(temp_zip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9,allowZip64=True) as z:
   for p in sorted(stage.rglob('*')):
    if p.is_file():z.write(p,PREFIX+'/'+p.relative_to(stage).as_posix())
  # Verify the staged manifest against archive bytes before publishing the ZIP.
  import importlib.util
  spec=importlib.util.spec_from_file_location('ambugo_zip_verifier',HERE/'verify_zip.py');verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
  _,_,verified=verifier.verify_archive(temp_zip)
  temp_zip.replace(FINAL)
  summary=dict(path=str(FINAL),sha256=sha(FINAL),zip_bytes=FINAL.stat().st_size,uncompressed_bytes=sum(v['bytes'] for v in files),file_count=len(files),microscopic_policy_runs=counts,verification=verified,staged_manuscripts=staged_papers)
  (OUTPUT/(PREFIX+'_build.json')).write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))


def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--simulations-final',action='store_true',help='Required acknowledgement that all named study batches are finished');ap.add_argument('--paper',action='append',default=[],help='Optional final manuscript PDF/DOCX to stage; repeat for each')
 args=ap.parse_args()
 if not args.simulations_final:ap.error('Wait for all runs to finish, then pass --simulations-final')
 build(args)

if __name__=='__main__':main()
