"""Focused counterexamples against the unmodified teammate v8 simulator."""
import sys,json,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parent/'teammate_v8'/'ambugo_v8'
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('v8_test_helpers',ROOT/'tests/run_tests.py');tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
from ambugo.sim import Simulator
from ambugo.policies import NoPriority

class Probe(Simulator):
    def __init__(self,*a,**k):self.storage_peaks=[];self.ambulance_discharges=[];super().__init__(*a,**k)
    def enter(self,vid,e,t,offset_m=0.):
        if vid==self.amb and self.amb_in and self.pos[vid]>0:
            prev=self.amb_route[self.pos[vid]-1]
            self.ambulance_discharges.append(dict(t=t,edge=self.net.edges[prev]['id'],capacity=self.cap(prev,t),credit_after_discharge=self.credit[prev],ambulance_pcu=self.pcu[vid]))
        super().enter(vid,e,t,offset_m)
        if not self.net.edges[e]['is_exit']:
            self.storage_peaks.append(dict(t=t,edge=self.net.edges[e]['id'],occupancy_pcu=self.occ[e],storage_pcu=self.net.edges[e]['storage']))

def scenario(td,vehicles,dispatch=10,horizon=150):
    A=td.net.eid['A'];OUT=td.net.eid['OUT']
    return dict(rep=0,vehicles=vehicles,shocks=[],incidents=[],horizon=horizon,amb=dict(origin='B_in',dest='B_out',dispatch=dispatch,insert_pos_m=20.,pcu=1.5,occ=3))

def main():
    findings=[]
    td=tests.ToyDesign(s=.5,g=30,g_dummy=30);A=td.net.eid['A'];O=td.net.eid['OUT'];td.net.edges[A]['storage']=2.
    vs=[dict(t=t,o='B_in',d='B_out',route=(A,O),cls='car',pcu=1.,occ=1) for t in (0.,1.)]
    sim=Probe(td,scenario(td,vs),NoPriority(),audit=True);r=sim.run();over=[p for p in sim.storage_peaks if p['occupancy_pcu']>p['storage_pcu']+1e-9]
    findings.append(dict(name='ambulance_exceeds_full_link_storage',counterexample_observed=bool(over),excess_events=over,audit_violations=r['violations']))
    td=tests.ToyDesign(s=0.,g=30,g_dummy=30);sim=Probe(td,scenario(td,[],dispatch=0),NoPriority(),audit=True);r=sim.run()
    findings.append(dict(name='ambulance_crosses_zero_discharge_capacity',counterexample_observed=bool(sim.ambulance_discharges),discharges=sim.ambulance_discharges,ambulance_arrival=r['amb_arrival'],audit_violations=r['violations']))
    td=tests.ToyDesign(s=.5,g=30,g_dummy=30);sim=Probe(td,scenario(td,[],dispatch=0),NoPriority(),audit=True);r=sim.run()
    findings.append(dict(name='ambulance_discharged_without_pcu_credit_consumption',counterexample_observed=any(x['credit_after_discharge']>0 for x in sim.ambulance_discharges),discharges=sim.ambulance_discharges,audit_violations=r['violations']))
    td=tests.ToyDesign(s=.5,g=30,g_dummy=30);A=td.net.eid['A'];O=td.net.eid['OUT']
    vs=[dict(t=0.,o='B_in',d='B_out',route=(A,O),cls='car',pcu=1.,occ=1)]
    sc=scenario(td,vs,dispatch=10**9,horizon=400);sc['incidents']=[dict(edge=A,start=20,end=500,cap_mult=0.,speed_mult=1.)]
    sim=Probe(td,sc,NoPriority(),audit=True);r=sim.run();unfinished_wait=399-sim.ready[0]
    findings.append(dict(name='unfinished_over_cap_wait_omitted_from_wait_metrics',counterexample_observed=unfinished_wait>180 and r['n_wait_over']==0,unfinished_vehicle_wait_at_last_tick_s=unfinished_wait,reported_max_wait_s=r['max_wait'],reported_n_wait_over=r['n_wait_over'],audit_violations=r['violations']))
    out=dict(source='unmodified teammate v8',findings=findings)
    p=Path(__file__).resolve().parent/'v8_regression_findings.json';p.write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
