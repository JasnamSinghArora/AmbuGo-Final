"""Regression tests for the narrowly corrected v8 mechanical sensitivity."""
import sys,json,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('toy_helpers',ROOT/'tests/run_tests.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
from ambugo.sim import Simulator
from ambugo.policies import NoPriority,make_policy
from ambugo.design import Design
from ambugo.network import Network
from ambugo.scenario import make_scenario

class Probe(Simulator):
    def __init__(self,*a,**k):self.peaks=[];self.discharge=[];self.ambulance_first_entry=None;super().__init__(*a,**k)
    def enter(self,vid,e,t,offset_m=0.):
        if vid==self.amb and self.amb_in and self.pos[vid]>0:
            prev=self.amb_route[self.pos[vid]-1]
            self.discharge.append(dict(t=t,capacity=self.cap(prev,t),credit_remaining=self.credit[prev]))
        super().enter(vid,e,t,offset_m)
        if vid==self.amb and self.pos[vid]==0:self.ambulance_first_entry=dict(t=t,ready=self.ready[vid],offset=offset_m)
        if not self.net.edges[e]['is_exit']:self.peaks.append((t,e,self.occ[e],self.net.edges[e]['storage']))

def scenario(td,vehicles,dispatch=10,horizon=240):
 return dict(rep=0,vehicles=vehicles,shocks=[],incidents=[],horizon=horizon,amb=dict(origin='B_in',dest='B_out',dispatch=dispatch,insert_pos_m=20.,pcu=1.5,occ=3))

def main():
 checks=[]
 def check(name,ok,**evidence):
  checks.append(dict(name=name,passed=bool(ok),**evidence))
  assert ok,(name,evidence)
 td=helper.ToyDesign(s=.5,g=30,g_dummy=30);A=td.net.eid['A'];O=td.net.eid['OUT'];td.net.edges[A]['storage']=2.
 vs=[dict(t=t,o='B_in',d='B_out',route=(A,O),cls='car',pcu=1.,occ=1) for t in (0.,1.)]
 sim=Probe(td,scenario(td,vs),NoPriority(),audit=True);r=sim.run()
 check('strict_storage_even_with_ambulance',all(occ<=cap+1e-9 for t,e,occ,cap in sim.peaks),max_excess=max(occ-cap for t,e,occ,cap in sim.peaks))
 check('ambulance_pays_source_wait',r['amb_source_wait'] is not None and r['amb_source_wait']>0,source_wait_s=r['amb_source_wait'],insertion=r['amb_insertion'])
 check('ordinary_accounting_excludes_queued_ambulance',not r['violations'],violations=r['violations'])
 td=helper.ToyDesign(s=0.,g=30,g_dummy=30);sim=Probe(td,scenario(td,[],dispatch=0),NoPriority(),audit=True);r=sim.run()
 check('zero_capacity_prevents_ambulance_admission_and_discharge',not sim.discharge and r['amb_insertion'] is None and r['amb_arrival'] is None,discharges=sim.discharge,arrival=r['amb_arrival'])
 check('queued_ambulance_zero_capacity_conservation',not r['violations'],violations=r['violations'])
 td=helper.ToyDesign(s=.5,g=30,g_dummy=30);sim=Probe(td,scenario(td,[],dispatch=0),NoPriority(),audit=True);r=sim.run()
 check('ambulance_uses_source_pcu_capacity',r['amb_insertion']==2,insertion=r['amb_insertion'])
 check('ambulance_enters_at_position_zero',sim.ambulance_first_entry['offset']==0 and sim.ambulance_first_entry['ready']==r['amb_insertion']+td.net.edges[td.net.eid['A']]['tt'],first_entry=sim.ambulance_first_entry)
 check('positive_capacity_allows_ambulance_eventually',r['amb_arrival'] is not None and len(sim.discharge)==1,discharge=sim.discharge,arrival=r['amb_arrival'])
 check('stopline_credit_is_debited',all(x['credit_remaining']<1.5 for x in sim.discharge),discharge=sim.discharge)
 check('credit_and_storage_audit_positive_case',not r['violations'],violations=r['violations'])
 td=helper.ToyDesign(s=.5,g=30,g_dummy=30);sc=scenario(td,[],dispatch=0);sc['incidents']=[dict(edge=td.net.eid['A'],start=20,end=240,cap_mult=0.,speed_mult=1.)]
 sim=Probe(td,sc,NoPriority(),audit=True);r=sim.run()
 check('zero_capacity_after_admission_prevents_stopline_discharge',r['amb_insertion']==2 and not sim.discharge and r['amb_arrival'] is None,insertion=r['amb_insertion'],discharges=sim.discharge,arrival=r['amb_arrival'])
 check('zero_capacity_after_admission_conservation',not r['violations'],violations=r['violations'])
 net=Network.from_v7_geometry();d=Design(net,target_x=.95)
 runs=[]
 for rep in [0,1]:
  sc=make_scenario(d,rep,horizon=1800,dispatch_window=(600,700),incident_prob=1.)
  for policy in ['P0','P2','P4']:
   sim=Simulator(d,sc,make_policy(policy),rho_yield=.5,audit=True);r=sim.run()
   check(f'full_network_stress_{rep}_{policy}',not r['violations'],amb_tt=r['amb_tt'],amb_source_wait=r['amb_source_wait'],violations=r['violations'])
   runs.append(dict(rep=rep,policy=policy,amb_tt=r['amb_tt'],source_wait=r['amb_source_wait']))
 out=dict(scope='minimal corrected v8 mechanics, not recalibration or full microsimulation validation',checks_passed=len(checks),checks=checks,runs=runs)
 (ROOT/'results/mechanical_verification.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
