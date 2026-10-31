"""Check story event claims directly against the included raw replay and control log."""
from pathlib import Path
import json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def validate_story(output_dir):
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    load=lambda p:json.loads(Path(p).read_text())
    story=load(ROOT/'data/story.json');mapping=load(ROOT/'data/time_mapping.json');source=story['source'];a=np.load(ROOT/source['replay_path']);m=load(ROOT/source['metadata_path']);control=load(ROOT/source['controller_log_path'])
    segments=story['segments'];V=[x['video_start_s'] for x in segments]+[segments[-1]['video_end_s']];T=[x['simulation_start_s']for x in segments]+[segments[-1]['simulation_end_s']];errors=[];checks={}
    def ck(key,value):
     checks[key]=bool(value)
     if not value:errors.append(key)
    ck('same_graph_story_clock',V==mapping['video_time_s'] and T==mapping['simulation_time_s'])
    ck('continuous_clock',V[0]==0 and V[-1]==20 and np.all(np.diff(V)>0) and np.all(np.diff(T)>0) and all(x['simulation_end_s']==y['simulation_start_s']for x,y in zip(segments,segments[1:])))
    ck('same_source_case',story['source_case']==source['case']=='B1000' and story['focus_ambulance']==source['focus_ambulance']=='a002')
    ck('source_unchanged',hashlib.sha256((ROOT/source['replay_path']).read_bytes()).hexdigest()==source['replay_sha256'])
    for e in story['events']:ck('clock_event_'+e['id'],abs(e['video_time_s']-np.interp(e['simulation_time_s'],T,V))<1e-9)
    evs={x['t']:x for x in control['events']if x['ambulance']=='a002'}
    ck('genuine_refusal',all(evs[t]['reason']=='burden_budget_exceeded'for t in range(785,792)))
    ck('genuine_admission',evs[792]['reason']=='selective_gate_passed')
    pcl=next(j for j in m['junction_ids']if '1424395831'in j);ji=m['junction_ids'].index(pcl);target=m['edge_ids'].index('335061218')
    ix=lambda t:int(np.searchsorted(a['t'],t))
    ck('green_is_not_admission',a['signal_mode'][ix(792.5),ji]!=0 and a['signal_mode'][ix(796.5),ji]==0 and a['signal_edge'][ix(796.5),ji]==target)
    ck('final_ordinary_amber',a['signal_mode'][ix(1107.5),ji]==1 and a['signal_edge'][ix(1107.5),ji]==m['edge_ids'].index('172380615#1'))
    ck('final_all_red',a['signal_mode'][ix(1110.5),ji]==2)
    ck('no_requests_after_arrival',not np.any(a['signal_request'][ix(1083.5):]>=0))
    ordinary_ids={i for i,x in enumerate(m['vehicles'])if x['type']!='ambulance'}
    def ordinary_stopped(e,t):
     i=ix(t);lo,hi=a['offsets'][i:i+2];ei=m['edge_ids'].index(e)
     return sum(int(v)in ordinary_ids and s<.1 and ed==ei for v,s,ed in zip(a['vehicle'][lo:hi],a['speed'][lo:hi],a['edge'][lo:hi]))
    for name,edge,green,clear in [('northwest','172380615#1',1095.5,1100),('southwest','172382686#4',1112.5,1120)]:
     ei=m['edge_ids'].index(edge);k=ix(green);previous=k-1
     ck(name+'_green',a['signal_mode'][k,ji]==0 and a['signal_edge'][k,ji]==ei and not(a['signal_mode'][previous,ji]==0 and a['signal_edge'][previous,ji]==ei))
     ck(name+'_observed_queue_release',ordinary_stopped(edge,green-.5)==3 and ordinary_stopped(edge,clear)==0)
    ck('queues_did_not_clear_to_cause_admission',np.array_equal(a['ordinary_edge_counts'][ix(785),[m['edge_ids'].index(e)for e in ['335061218','172380615#1','172382686#4','172660580#0']]],a['ordinary_edge_counts'][ix(792),[m['edge_ids'].index(e)for e in ['335061218','172380615#1','172382686#4','172660580#0']]]))
    out=dict(all_checks_pass=not errors,errors=errors,checks=checks,request_refusal_first_video_s=float(np.interp(785,T,V)),admission_video_s=float(np.interp(792,T,V)),green_video_s=float(np.interp(796.5,T,V)),scope='Read-only audit of existing B1000/a002 20-second storyboard and shared graph clock. The Google basemap does not supply trajectories or control data.',files_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [ROOT/'data/story.json',ROOT/'data/time_mapping.json']},interpretive_notes=['No refusal marker before video4.25s: earlier red is an approach/normal signal state, not a logged admission refusal.','Admission at video5.5s remains distinct from physicalgreen at video7.0s.','Final ordinary queue discharge is real local service, not proof of complete network recovery.','Provider attribution must remain visible throughout Google-map footage.'])
    (output_dir/'story_audit.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:out[k]for k in ['all_checks_pass','errors','request_refusal_first_video_s','admission_video_s','green_video_s']},indent=2))

    if errors:raise AssertionError(f'Story audit failed: {errors}')
    return out
