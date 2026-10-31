#!/usr/bin/env python3
"""Read-only control logging on a deterministic repeat of the existing episode."""
from pathlib import Path
import os,sys,json,copy,hashlib
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ORIGINAL=ROOT/'work/punjab/sim'
BUDGET=float(os.environ.get('AMBUGO_EXPLAIN_BUDGET','10000'))
REPEAT=HERE/('instrumented_repeat' if BUDGET==10000 else f'budget_{int(BUDGET)}')
os.environ['PUNJAB_OUTPUT_DIR']=str(REPEAT)
sys.path.insert(0,str(ORIGINAL))
import run_punjab as rp
import numpy as np
traci=rp.traci
Base=rp.RealMapController
instances=[]

class ExplainedController(Base):
    def __init__(self,*a,**kw):
        a[4]['harm_budget']=BUDGET
        super().__init__(*a,**kw);self.explain_decisions=[];self.explain_events=[];self.explain_progress=[];self._context=None;self._aid=None;self._estimates=[];self._pulses=[];instances.append(self)
    def progress_mode(self,aid,*a,**kw):
        self._aid=aid
        result=super().progress_mode(aid,*a,**kw)
        e,position,t,dispatch=a;state=self.progress[aid]
        executed=state['completed_freeflow']+max(0.,position)/self.m['edges'][e]['v']
        self.explain_progress.append(dict(t=t,ambulance=aid,edge=e,position_m=position,executed_freeflow_progress_s=executed,elapsed_since_dispatch_s=t-dispatch,progress_delay_proxy_s=max(0.,t-dispatch-executed),threshold_s=self.c.get('progress_guard_s'),effective_mode=result[0],just_escalated=bool(result[1])))
        return result
    def estimate(self,path,a,remaining,policy=None):
        result=super().estimate(path,a,remaining,policy)
        if self._context and self._context['kind']=='plan':
            self._estimates.append(dict(route=list(path),action=list(a),eta_s=float(result[0]),burden_veh_s=float(result[1]),legacy_allow_counter=int(result[2])))
        return result
    def pulse(self,e,out,a,arrival,policy=None):
        result=super().pulse(e,out,a,arrival,policy)
        if not self._context:return result
        j=self.m['edges'][e]['to']
        if j not in self.signals:return result
        sig=self.signals[j];ee=self.m['edges'][e];q=self.q(e);clear=q/max(ee['s']/self.m['meanpcu'],.1)
        wait=sig.nominal_wait(e,arrival);switch=sig.switch_delay(e);headroom=(out is None or self.obs.get(out,0)<self.c['headroom']*self.m['edges'][out]['K'])
        estimated_cross=max(0,a[0]+clear-switch)+clear+2;possible=estimated_cross<=a[1]
        lost=min(a[1],max(5.,a[0]+clear));raw=0.;conflict=[]
        for other in sig.arms:
            if other==e:continue
            lam=self.design['expected_veh_per_s'].get(other,0);X=self.design['plans'][j]['X'].get(other,0)
            cost=self.q(other)*lost+lam*lost*lost/(2*max(1-X,.05));raw+=cost
            conflict.append(dict(edge=other,queue_proxy=self.q(other),arrival_rate=lam,nominal_design_X=X,burden_proxy_veh_s=cost))
        p=dict(t=self._context['t'],ambulance=self._aid,junction=j,approach=e,outgoing=out,mode=policy or self.policy,action=list(a),estimated_arrival_s=float(arrival),queue_proxy=q,queue_clearance_s=clear,nominal_signal_wait_s=wait,switch_delay_s=switch,pulse_feasible=possible,headroom=headroom,predicted_benefit_s=float(result[3]),raw_burden_proxy_veh_s=raw,admitted_burden_proxy_veh_s=float(result[1]),local_gate_passed=bool(result[2]),conflicting_approaches=conflict,observed_count=self.obs.get(e,0),own_phase_before=('green' if sig.mode=='green' and sig.edge==e else 'amber' if sig.mode=='amber' and sig.edge==e else 'red'),signal_mode_before=sig.mode,green_edge_before=sig.edge,lease_before=copy.deepcopy(self.leases.get((self._aid,e))),finished_before=(self._aid,e) in self.finished_leases,thresholds=dict(minimum_benefit_s=5,burden_budget_veh_s=self.c['harm_budget'],receiving_fraction=self.c['headroom']))
        if self._context['kind']=='request':self._pulses.append(p)
        return result
    def plan(self,aid,e,remaining,t,policy=None):
        oldcontext=self._context;oldestimates=self._estimates;self._context=dict(kind='plan',t=t,aid=aid);self._aid=aid;self._estimates=[]
        pp=list(self.candidates(e));route=list(traci.vehicle.getRoute(aid));ix=traci.vehicle.getRouteIndex(aid);cur=route[max(ix,0):]
        if cur and cur[0]==e and cur not in pp:pp=pp[:3]+[cur]
        mode=policy or self.policy
        acts=[(0.,0.)] if mode=='P0' else ([(self.c['trigger'],self.c['hold'])] if mode in ('P1','P2') else ([(0.,0.),(30.,60.)] if self.c['action_mode']=='strong' else [(0.,0.),(10.,20.),(20.,40.),(30.,60.)]))
        keys=[(tuple(p),tuple(a)) for p in pp for a in acts]
        super().plan(aid,e,remaining,t,policy)
        evaluated=self._estimates;lookup={(tuple(x['route']),tuple(x['action'])):x for x in evaluated}
        candidates=[dict(lookup[k]) for k in keys];mint=min(x['eta_s'] for x in candidates)
        actual=list(traci.vehicle.getRoute(aid));rix=traci.vehicle.getRouteIndex(aid);actual=actual[max(rix,0):];action=list(self.amaction[aid]);chosen=None
        for k,x in enumerate(candidates):
            x['candidate_id']=k;x['eligible']=bool(mode!='P3' or x['eta_s']<=mint+self.c['epsilon']+1e-9);x['chosen']=x['route']==actual and x['action']==action
            if x['chosen']:chosen=k
        assert chosen is not None
        self.explain_decisions.append(dict(t=t,ambulance=aid,current_edge=e,mode=mode,remaining_current_edge_m=remaining,incumbent_route=cur,candidates=candidates,chosen=chosen,minimum_predicted_eta_s=mint,time_band_s=self.c['epsilon'] if mode=='P3' else None,selection_rule='Minimum predicted ETA within finite candidates; in selective mode choose minimum heuristic burden within the predicted-time band, with constrained incumbent hysteresis.',burden_label='Unvalidated local queue/service-loss proxy, not measured network aftereffects or individual delay.'))
        self._context=oldcontext;self._estimates=oldestimates
    def requests_at(self,t,active):
        self._context=dict(kind='request',t=t);self._pulses=[]
        result=super().requests_at(t,active)
        pulses={x['ambulance']:x for x in self._pulses}
        for vehicle in active:
            aid=vehicle['id'];e=traci.vehicle.getRoadID(aid)
            if e not in self.m['edges']:continue
            ee=self.m['edges'][e];j=ee['to']
            if j not in self.signals:continue
            sig=self.signals[j];mode='P2' if aid in self.fallback_ids else self.policy;act=self.amaction.get(aid,(self.c['trigger'],self.c['hold']));remaining=max(0,ee['L']-traci.vehicle.getLanePosition(aid));eta=remaining/ee['v'];clear=self.q(e)/max(ee['s']/self.m['meanpcu'],.1)
            p=copy.deepcopy(pulses.get(aid,dict(t=t,ambulance=aid,junction=j,approach=e,mode=mode,action=list(act),queue_proxy=self.q(e),own_phase_before=('green' if sig.mode=='green' and sig.edge==e else 'amber' if sig.mode=='amber' and sig.edge==e else 'red'),predicted_benefit_s=None,raw_burden_proxy_veh_s=None,headroom=None)))
            requested=bool(j in result and result[j]['ambulance']==aid);p.update(request_active=requested,inside_request_horizon=eta<=act[0]+clear,free_flow_eta_to_stopline_s=eta,controller_policy='P3_with_progress_escalation',physical_green_guaranteed=False)
            if requested:
                p['reason']='progress_escalation_priority' if mode=='P2' else ('committed_selective_lease' if p.get('lease_before') else 'selective_gate_passed')
            elif act[1]==0:p['reason']='planner_selected_no_priority'
            elif aid not in pulses:p['reason']='outside_request_horizon'
            elif mode=='P3':
                if p.get('finished_before'):p['reason']='priority_lease_already_finished'
                elif p.get('lease_before') and (aid,e) in self.finished_leases:
                    p['reason']='lease_lost_receiving_space' if not p['headroom'] else 'bounded_priority_lease_expired'
                elif not p['headroom']:p['reason']='insufficient_receiving_space'
                elif p['predicted_benefit_s']<5:
                    p['reason']='pulse_not_predicted_to_clear_queue' if not p['pulse_feasible'] else 'predicted_benefit_below_5_seconds'
                elif p['raw_burden_proxy_veh_s']>self.c['harm_budget']:p['reason']='burden_budget_exceeded'
                elif j in result:p['reason']='older_mission_has_junction_request'
                else:p['reason']='no_request_other'
            else:p['reason']='older_mission_has_junction_request' if j in result else 'no_request_other'
            p['reason_is_actual_control_path']=True
            self.explain_events.append(p)
        self._context=None
        return result

def main():
    config=json.loads((ORIGINAL/'config.json').read_text());before={f:hashlib.sha256((ORIGINAL/f).read_bytes()).hexdigest() for f in ['run_punjab.py','P3.json','P3.npz','mohali_urban.net.xml']}
    rp.RealMapController=ExplainedController
    rp.run('P3',ORIGINAL/'mohali_urban.net.xml',config)
    new=json.loads((REPEAT/'P3.json').read_text());old=json.loads((ORIGINAL/'P3.json').read_text())
    fields=['missions','plans','progress_guard_log','route_changes','priority_phase_admissions','signal_timing_violations','collision_events','teleport_events','schedule_sha256','ordinary_completed','ordinary_scheduled','net_sha256']
    checks={k:new[k]==old[k] for k in fields}
    aa=np.load(REPEAT/'P3.npz');bb=np.load(ORIGINAL/'P3.npz');arraychecks={k:bool(np.array_equal(aa[k],bb[k],equal_nan=True)) for k in aa.files}
    original_unchanged={f:hashlib.sha256((ORIGINAL/f).read_bytes()).hexdigest()==v for f,v in before.items()}
    no_budget=lambda d:{k:v for k,v in d.items() if k!='harm_budget'}
    fixed_conditions=dict(same_schedule=new['schedule_sha256']==old['schedule_sha256'],same_geometry=new['net_sha256']==old['net_sha256'],same_other_controller_settings=no_budget(new['configuration'])==no_budget(old['configuration']),same_mission_design=new['scenario_config']==old['scenario_config'])
    pre=np.flatnonzero(aa['t']<600);cut=int(aa['offsets'][pre[-1]+1]);cut_old=int(bb['offsets'][pre[-1]+1]);fixed_conditions['same_pre_dispatch_traffic']=cut==cut_old and all(np.array_equal(aa[k][:cut],bb[k][:cut],equal_nan=True) for k in ['vehicle','x','y','lon','lat','speed','angle','edge'])
    assert all(fixed_conditions.values()) and all(original_unchanged.values())
    if BUDGET==10000:assert all(checks.values()) and all(arraychecks.values())
    controller=instances[-1];log=dict(budget_veh_s=BUDGET,provenance=('Read-only instrumentation of deterministic repeated corrected Mohali P3 episode; all stored numeric trajectory arrays and original controller outputs reproduced exactly.' if BUDGET==10000 else 'Explicit controlled budget-sensitivity illustration. Only burden budget changes from the default episode; not a new efficacy validation.'),decisions=controller.explain_decisions,events=controller.explain_events,progress=controller.explain_progress,repeat_verification=dict(fields=checks,arrays=arraychecks,original_files_unchanged=original_unchanged,fixed_conditions=fixed_conditions),source_net_sha256=new['net_sha256'],source_controller_sha256=new['frozen_controller_sha256'],legacy_allow_counter_note='The inherited estimate counter includes non-signal edges. It is not a count of priority grants and is not used to select a route.')
    (REPEAT/'control_explanations.json').write_text(json.dumps(log,indent=2))
    if BUDGET==10000:(HERE/'control_explanations_raw.json').write_text(json.dumps(log,indent=2))
    print('VALIDATED BUDGET',BUDGET,len(log['decisions']),'decisions',len(log['events']),'events',flush=True)
if __name__=='__main__':main()
