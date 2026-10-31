#!/usr/bin/env python3
"""AmbuGo v9 synthetic SUMO experiment. No field calibration is claimed.

API: buildnetwork(root=...), make_scenario(seed, load, missions, ...),
run_case(seed,load,missions,policy,...). Python imports use local vendor only.
"""
from __future__ import annotations
import argparse, bisect, csv, hashlib, heapq, json, math, os, random, subprocess, sys, time
from pathlib import Path
from collections import defaultdict
import xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
VENDOR=HERE/'vendor'
if str(VENDOR) not in sys.path: sys.path.insert(0,str(VENDOR))
import numpy as np
try:
    import libsumo as traci
    BACKEND='libsumo'
except ImportError:
    import traci
    BACKEND='traci'
import traci.constants as tc
FIXTURE=HERE.parents[1]/'outputs/AmbuGo_v7_Synthetic_Data'
NETDIR=HERE/'sumo_network'
SUMO=str(VENDOR/'sumo/bin/sumo')
NETCONVERT=str(VENDOR/'sumo/bin/netconvert')
CLASS_PCU={'car':1.,'motorcycle':.5,'autorickshaw':1.,'bus':3.,'goods':2.5}
DEFAULTS=dict(step=1.,warmup=1800,horizon=7200,mission_end=5400,epsilon=10.,harm_budget=120.,headroom=.85,trigger=30.,hold=60.,sensor_period=5,sensor_delay=2,sensor_noise=True,base='fixed',action_mode='multi',progress_guard_s=None,save_trace=True)
POLICIES={
 'P0':'No signal priority; traffic-aware routing',
 'P1':'Sequential traffic-aware routing then unconditional preemption',
 'P2':'Joint time-oriented routing and unconditional preemption',
 'P3':'Joint near-fastest routing and burden-selective preemption'}

def stable_rng(seed,*parts):
    z=hashlib.sha256(('|'.join(map(str,(20261025,seed)+parts))).encode()).digest()
    return random.Random(int.from_bytes(z[:16],'big'))

def rows(name):
    return list(csv.DictReader((FIXTURE/(name+'.csv')).open()))

def paths(start,dest,edges,adj,k=4,ratio=1.35,forbid_first=None):
    """Deterministic k shortest loopless node paths, excluding immediate U-turn."""
    h=[(0.,start,(),(start,))];ans=[];bound=None
    while h and len(ans)<k:
        c,u,p,seen=heapq.heappop(h)
        if bound is not None and c>bound+1e-9: break
        if u==dest:
            if bound is None:bound=c*ratio
            ans.append(list(p));continue
        for eid in adj.get(u,[]):
            e=edges[eid];v=e['to']
            if v in seen or (not p and v==forbid_first):continue
            heapq.heappush(h,(c+e['ff'],v,p+(eid,),seen+(v,)))
    return ans

def public_model():
    nd=rows('nodes');ed=rows('edges');classes=rows('vehicle_classes')
    nodes={r['node_id']:dict(id=r['node_id'],x=float(r['x_m']),y=float(r['y_m']),signal=r['kind']=='signalized_junction') for r in nd}
    edges={r['edge_id']:dict(id=r['edge_id'],fr=r['from_node'],to=r['to_node'],L=float(r['length_m']),lanes=int(r['lanes']),v=float(r['speed_limit_mps']),ff=float(r['length_m'])/float(r['speed_limit_mps']),s=float(r['capacity_veh_per_s_per_lane'])*int(r['lanes']),K=float(r['usable_storage_veh'])) for r in ed}
    adj=defaultdict(list);inc=defaultdict(list)
    for e in edges.values():adj[e['fr']].append(e['id']);inc[e['to']].append(e['id'])
    for a in (adj,inc):
        for key in a:a[key].sort()
    bounds=sorted(n for n,v in nodes.items() if not v['signal']);juncs=sorted(n for n,v in nodes.items() if v['signal'])
    od=defaultdict(list)
    for r in rows('od_probabilities'):od[r['origin_id']].append((r['destination_id'],float(r['probability'])))
    routepool={};expected=defaultdict(float);meanpcu=sum(float(r['probability'])*CLASS_PCU[r['class_id']] for r in classes)
    for o in bounds:
        for d,p in od[o]:
            pp=paths(o,d,edges,adj)
            if not pp:raise ValueError(('No route',o,d))
            costs=[sum(edges[e]['ff'] for e in z) for z in pp];a=min(costs);ww=[math.exp(-.05*(c-a)) for c in costs];ww=[w/sum(ww) for w in ww]
            routepool[(o,d)]=(pp,ww)
            for route,w in zip(pp,ww):
                for eid in route:expected[eid]+=.1*p*w*meanpcu
    return dict(nodes=nodes,edges=edges,adj=dict(adj),inc=dict(inc),bounds=bounds,juncs=juncs,od=dict(od),routepool=routepool,classes=classes,expected=dict(expected),meanpcu=meanpcu)

_MODEL=None

def get_model():
    global _MODEL
    if _MODEL is None:_MODEL=public_model()
    return _MODEL

def green_split(total,weights,gmin=8.):
    n=len(weights);total=max(total,gmin*n);alloc=[gmin]*n;left=total-gmin*n
    ss=sum(weights)
    for i,w in enumerate(weights):alloc[i]+=left*(w/ss if ss else 1/n)
    # Explicit minimum is retained; no nominal maximum-green claim is made.
    return alloc

def signal_design(load,model=None):
    """Bisection on an EX ANTE PCU capacity surrogate; not measured SUMO X."""
    m=model or get_model()
    def design(scale):
        plans={};xs=[]
        for j in m['juncs']:
            arms=m['inc'][j];ys=[scale*m['expected'].get(e,0)/m['edges'][e]['s'] for e in arms];Y=sum(ys);lost=25+7*len(arms)
            C=min(150.,max(60.,(1.5*lost+5)/max(1-Y,.05),25+13*len(arms)))
            gs=green_split(C-25-5*len(arms),ys)
            C=sum(gs)+25+5*len(arms)
            armX={e:scale*m['expected'].get(e,0)/(m['edges'][e]['s']*g/C) for e,g in zip(arms,gs)}
            plans[j]=dict(arms=arms,greens=[round(g) for g in gs],cycle=round(sum(round(g) for g in gs)+25+5*len(arms)),X=armX)
            xs+=list(armX.values())
        return max(xs),plans
    lo,hi=.001,20.
    for _ in range(60):
        mid=(lo+hi)/2
        if design(mid)[0]<load:lo=mid
        else:hi=mid
    scale=(lo+hi)/2;achieved,plans=design(scale)
    return dict(scale=scale,nominal_critical_X=achieved,plans=plans,expected_veh_per_s={e:scale*v/m['meanpcu'] for e,v in m['expected'].items()})

def buildnetwork(root=None):
    root=Path(root or NETDIR);root.mkdir(parents=True,exist_ok=True);netfile=root/'district.net.xml'
    if netfile.exists():return netfile
    m=get_model();ns=ET.Element('nodes')
    for n in m['nodes'].values():ET.SubElement(ns,'node',id=n['id'],x=str(n['x']),y=str(n['y']),type='traffic_light' if n['signal'] else 'dead_end')
    es=ET.Element('edges')
    for e in m['edges'].values():ET.SubElement(es,'edge',id=e['id'],**{'from':e['fr'],'to':e['to'],'numLanes':str(e['lanes']),'speed':str(e['v']),'width':'3.2','length':str(e['L']),'spreadType':'center','priority':'2'})
    ET.ElementTree(ns).write(root/'district.nod.xml',encoding='utf-8',xml_declaration=True);ET.ElementTree(es).write(root/'district.edg.xml',encoding='utf-8',xml_declaration=True)
    cmd=[NETCONVERT,'--node-files',str(root/'district.nod.xml'),'--edge-files',str(root/'district.edg.xml'),'--output-file',str(netfile),'--no-turnarounds','true','--no-turnarounds.except-deadend','false','--junctions.corner-detail','5','--tls.default-type','static','--no-warnings','true']
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stderr+p.stdout)
    (root/'netconvert.log').write_text(p.stdout+p.stderr)
    return netfile

def choices(rng,vals,weights):return rng.choices(vals,weights,k=1)[0]

def make_scenario(seed,load,missions,*,warmup=1800,horizon=7200,mission_end=5400,root=None):
    """Ordinary schedules and routes do not depend on the control policy."""
    m=get_model();des=signal_design(load,m);root=Path(root or HERE/'scenarios');root.mkdir(parents=True,exist_ok=True)
    key=f'v2_s{seed}_x{load:.3f}_m{missions}_w{warmup}_h{horizon}_e{mission_end}';f=root/(key+'.rou.xml');jf=root/(key+'.json')
    if f.exists() and jf.exists():return json.loads(jf.read_text())
    r=stable_rng(seed,'shared_demand_shock');sigma=.18;rho=.75
    z=r.gauss(0,sigma/math.sqrt(1-rho*rho));stationvar=sigma*sigma/(1-rho*rho);shock=[]
    for minute in range(math.ceil(horizon/60)):
        if minute:z=rho*z+r.gauss(0,sigma)
        shock.append(math.exp(z-.5*stationvar))
    ordinary=[];cid=[c['class_id'] for c in m['classes']];cw=[float(c['probability']) for c in m['classes']]
    for oi,o in enumerate(m['bounds']):
        a=stable_rng(seed,'departures',o);b=stable_rng(seed,'attributes',o);ods=m['od'][o]
        for minute,factor in enumerate(shock):
            lam=.1*des['scale']*factor;start=minute*60.;t=start
            while True:
                t+=a.expovariate(lam)
                if t>=min(start+60,horizon):break
                d=choices(b,[x[0] for x in ods],[x[1] for x in ods]);pp,ww=m['routepool'][(o,d)];route=choices(b,pp,ww);cl=choices(b,cid,cw)
                ordinary.append(dict(depart=math.ceil(t),origin=o,destination=d,cls=cl,route=route))
    ordinary.sort(key=lambda x:(x['depart'],x['origin']))
    for i,v in enumerate(ordinary):v['id']=f'v{i:06d}'
    ambulances=[];mr=stable_rng(seed,'missions');origins=['BW1','BW2','BN1','BN2','BS1','BS2']
    for k in range(missions):
        width=(mission_end-warmup)/max(missions,1);t=warmup+(k+.15+.7*mr.random())*width;o=mr.choice(origins);route=m['routepool'][(o,'BE1')][0][0]
        ambulances.append(dict(id=f'a{k:03d}',depart=math.ceil(t),origin=o,destination='BE1',cls='ambulance',route=route))
    rootxml=ET.Element('routes')
    for c in m['classes']:
        ET.SubElement(rootxml,'vType',id=c['class_id'],vClass={'car':'passenger','motorcycle':'motorcycle','autorickshaw':'passenger','bus':'bus','goods':'truck'}[c['class_id']],length=c['length_m'],width=c['width_m'],minGap=c['min_gap_m'],tau=c['desired_headway_s'],accel=c['accel_mps2'],decel=c['decel_mps2'],sigma='0',speedFactor='1',speedDev='0',lcStrategic='1',lcCooperative='1')
    ET.SubElement(rootxml,'vType',id='ambulance',vClass='passenger',length='5',width='2',minGap='2',tau='1.3',accel='2',decel='4.5',sigma='0',speedFactor='1',speedDev='0',color='red')
    for v in sorted(ordinary+ambulances,key=lambda v:(v['depart'],v['id'])):
        ve=ET.SubElement(rootxml,'vehicle',id=v['id'],type=v['cls'],depart=str(v['depart']),departLane='best',departSpeed='max');ET.SubElement(ve,'route',edges=' '.join(v['route']))
    ET.ElementTree(rootxml).write(f,encoding='utf-8',xml_declaration=True)
    s=dict(key=key,seed=seed,load=load,missions=missions,warmup=warmup,horizon=horizon,mission_end=mission_end,route_file=str(f),ordinary=ordinary,ambulances=ambulances,design=des,provenance='synthetic_not_measured',schedule_sha256=hashlib.sha256(f.read_bytes()).hexdigest())
    jf.write_text(json.dumps(s,separators=(',',':')));return s

class Signal:
    """Safe single-approach protected controller, including clearance stages."""
    def __init__(self,j,plan,linkarms,offset=0):
        self.j=j;self.arms=plan['arms'];self.gs=plan['greens'];self.C=plan['cycle'];self.linkarms=linkarms;self.nlinks=len(linkarms)
        self.stage=0;self.mode='green';self.elapsed=0;self.target=None;self.lastserved={e:-offset for e in self.arms};self.lastped=-offset;self.request=None
        self.baseindex=0;self.extensions=0;self.accepted=0;self.guard_overrides=0;self.ped_opportunities=0;self.transitions=0;self.max_service_age=0;self._state=None;self._tag=None;self._phase_start=0;self.phase_spans=[];self.phase_violations=0
        # Stagger initial phases deterministically; no partially elapsed green is necessary.
        self.stage=offset%len(self.arms);self.baseindex=self.stage
    @property
    def edge(self):return self.arms[self.stage] if self.mode in ('green','amber') else None
    def state(self):
        char='G' if self.mode=='green' else ('y' if self.mode=='amber' else 'r')
        return ''.join(char if (self.mode in ('green','amber') and e==self.arms[self.stage]) else 'r' for e in self.linkarms)
    def switch_delay(self,e):
        if self.mode=='green':return 0. if self.edge==e else max(0,8-self.elapsed)+5.
        if self.mode=='amber':return max(0,3-self.elapsed)+2.
        if self.mode=='allred':return max(0,2-self.elapsed)
        return max(0,25-self.elapsed)
    def nominal_wait(self,e,at=0):
        # Forecast cyclic continuation from current actual stage, no future observations.
        if e not in self.arms:return 0.
        if self.mode=='green' and self.edge==e and at<=max(0,self.gs[self.stage]-self.elapsed):return 0.
        i=self.stage;remaining=0.
        if self.mode=='green':remaining=max(0,self.gs[i]-self.elapsed)+5
        elif self.mode=='amber':remaining=max(0,3-self.elapsed)+2
        elif self.mode=='allred':remaining=max(0,2-self.elapsed)
        elif self.mode=='ped':remaining=max(0,25-self.elapsed);i=-1
        for _ in range((math.ceil(max(0,at)/max(self.C,1))+2)*(len(self.arms)+1)):
            i+=1
            if i==len(self.arms):remaining+=25;i=0
            if self.arms[i]==e:
                if at<=remaining:return remaining-at
                if at<=remaining+self.gs[i]:return 0.
            remaining+=self.gs[i]+5
        return self.C/2
    def update(self,t,request,observed,base='fixed'):
        self.request=request
        ages={e:t-self.lastserved[e] for e in self.arms if observed.get(e,0)>0}
        pedage=t-self.lastped
        self.max_service_age=max(self.max_service_age,max(ages.values(),default=0),pedage)
        urgent=max(ages,key=ages.get) if ages else None
        guard=(urgent if urgent is not None and ages[urgent]>=150 else None)
        if pedage>=150 and (guard is None or pedage>=ages[guard]):guard='PED'
        if self.mode=='green':
            self.lastserved[self.edge]=t
            duration=self.gs[self.stage]
            if request and request['edge']==self.edge:
                duration=max(duration,min(request['hold'],90))
            truncate=request is not None and request['edge']!=self.edge and self.elapsed>=8
            if guard is not None and guard!=self.edge and self.elapsed>=8:
                self.target=guard;self.guard_overrides+=bool(request);truncate=True
            elif truncate:self.target=request['edge']
            if self.elapsed>=duration or truncate:
                self.mode='amber';self.elapsed=0;self.transitions+=1
        elif self.mode=='amber' and self.elapsed>=3:
            self.mode='allred';self.elapsed=0
        elif self.mode=='allred' and self.elapsed>=2:
            nexttarget=self.target;self.target=None
            if guard is not None:
                if nexttarget not in (None,guard):self.guard_overrides+=1
                nexttarget=guard
            elif request:nexttarget=request['edge']
            if nexttarget is None and base=='longest_queue':
                nexttarget=max(self.arms,key=lambda e:(observed.get(e,0),t-self.lastserved[e],e))
                if t-self.lastped>=100:nexttarget='PED'
            if nexttarget is None:
                self.baseindex=(self.baseindex+1)%(len(self.arms)+1)
                nexttarget='PED' if self.baseindex==len(self.arms) else self.arms[self.baseindex]
            if nexttarget=='PED':self.mode='ped';self.elapsed=0;self.lastped=t;self.ped_opportunities+=1;self.baseindex=len(self.arms)
            else:
                self.stage=self.arms.index(nexttarget);self.mode='green';self.elapsed=0;self.lastserved[nexttarget]=t;self.baseindex=self.stage
                if request and request['edge']==nexttarget:self.accepted+=1
        elif self.mode=='ped':
            self.lastped=t
            if self.elapsed>=25:
                if guard and guard!='PED':target=guard
                elif request:target=request['edge']
                else:
                    self.baseindex=0;target=self.arms[0]
                self.stage=self.arms.index(target);self.mode='green';self.elapsed=0;self.lastserved[target]=t;self.baseindex=self.stage
        self.elapsed+=1
        tag=(self.mode,self.stage if self.mode in ('green','amber') else None)
        if tag!=self._tag:
            if self._tag is not None:
                oldmode,oldstage=self._tag;duration=t-self._phase_start
                minimum={'green':8,'amber':3,'allred':2,'ped':25}[oldmode]
                maximum=max(90,self.gs[oldstage]) if oldmode=='green' else minimum
                self.phase_violations+=int(duration<minimum or duration>maximum)
                self.phase_spans.append((oldmode,duration))
            self._tag=tag;self._phase_start=t
        s=self.state()
        if s!=self._state:traci.trafficlight.setRedYellowGreenState(self.j,s);self._state=s

class Controller:
    def __init__(self,m,scenario,signals,policy,config):
        self.m=m;self.s=scenario;self.signals=signals;self.policy=policy;self.c=config
        self.obs={e:0 for e in m['edges']};self.age={e:0 for e in m['edges']};self.dropout={e:False for e in m['edges']};self.pending=defaultdict(list)
        self.lastedge={};self.progress={};self.fallback_ids=set();self.fallback_log=[];self.amaction={};self.pathcache={};self.leases={};self.finished_leases=set();self.expired_leases=0;self.route_changes=0;self.route_evaluations=0;self.requests=0;self.rejected_harm=0;self.rejected_headroom=0;self.rejected_benefit=0;self.sensor_available=0;self.sensor_total=0;self.actions=defaultdict(int);self.design=scenario['design'];self.lastplanlog=[]
    def observe(self,t,counts):
        for eid,n in self.pending.pop(t,[]):self.obs[eid]=n;self.age[eid]=t
        if t%self.c['sensor_period']:return
        for eid in self.obs:
            rr=stable_rng(self.s['seed'],'sensor',t,eid)
            self.dropout[eid]=rr.random()<(.75 if self.dropout[eid] else .015)
            self.sensor_total+=1
            if self.dropout[eid]:continue
            self.sensor_available+=1
            noise=rr.choice([-2,-1,0,0,0,1,2]) if self.c['sensor_noise'] else 0
            measured=max(0,counts.get(eid,0)+noise)
            if self.c['sensor_delay']==0:self.obs[eid]=measured;self.age[eid]=t
            else:self.pending[t+self.c['sensor_delay']].append((eid,measured))
    def q(self,e):
        ee=self.m['edges'][e];flow=self.design['expected_veh_per_s'].get(e,0)
        return max(0,self.obs.get(e,0)-flow*ee['ff'])
    def pulse(self,e,out,a,arrival,policy=None):
        policy=policy or self.policy
        ee=self.m['edges'][e];j=ee['to']
        if j not in self.signals:return 0.,0.,True,0.
        si=self.signals[j];wait=si.nominal_wait(e,arrival);qclear=self.q(e)/max(ee['s']/self.m['meanpcu'],.1)
        if a[1]==0:return wait,0.,False,0.
        headroom=(out is None or self.obs.get(out,0)<self.c['headroom']*self.m['edges'][out]['K'])
        switch=si.switch_delay(e)
        # A requested green starts only after the current legal clearance.
        # Feasibility accounts for the request look-ahead, queue estimate and a
        # two-second microscopic start-up allowance, relative to green start.
        estimated_cross=max(0,a[0]+qclear-switch)+qclear+2.
        possible=estimated_cross<=a[1]
        priority_wait=max(0,switch-max(0,arrival))
        benefit=max(0,wait-priority_wait) if possible and headroom else 0.
        lost=min(a[1],max(5.,a[0]+qclear))
        burden=0.
        for other in si.arms:
            if other==e:continue
            lam=self.design['expected_veh_per_s'].get(other,0);X=self.design['plans'][j]['X'].get(other,0)
            burden+=self.q(other)*lost+lam*lost*lost/(2*max(1-X,.05))
        admitted=benefit>=5 and burden<=self.c['harm_budget'] and headroom if policy=='P3' else headroom
        return max(0,wait-(benefit if admitted else 0)),burden if admitted else 0.,admitted,benefit
    def candidates(self,e):
        if e not in self.pathcache:
            ee=self.m['edges'][e]
            pp=paths(ee['to'],'BE1',self.m['edges'],self.m['adj'],k=4,ratio=1.5,forbid_first=ee['fr'])
            self.pathcache[e]=[[e]+p for p in pp] or [[e]]
        return self.pathcache[e]
    def estimate(self,path,a,remaining,policy=None):
        policy=policy or self.policy
        T=0.;A=0.;approvals=0
        for i,e in enumerate(path):
            ee=self.m['edges'][e];ff=remaining/ee['v'] if i==0 else ee['ff'];T+=ff
            q=self.q(e)/max(ee['s']/self.m['meanpcu'],.1);T+=q
            if policy in ('P0','P1'):
                j=ee['to'];wait=self.signals[j].nominal_wait(e,T) if j in self.signals else 0.;harm=0.;allow=False
            else:wait,harm,allow,b=self.pulse(e,path[i+1] if i+1<len(path) else None,a,T,policy=policy)
            T+=wait;A+=harm;approvals+=int(allow)
        return T,A,approvals
    def plan(self,aid,e,remaining,t,policy=None):
        policy=policy or self.policy
        pp=list(self.candidates(e))
        current=list(traci.vehicle.getRoute(aid));ix=traci.vehicle.getRouteIndex(aid);cur=current[max(ix,0):]
        # Include the legal incumbent continuation in the same finite domain.
        if cur and cur[0]==e and cur not in pp:pp=pp[:3]+[cur]
        p3actions=[(0.,0.),(30.,60.)] if self.c['action_mode']=='strong' else [(0.,0.),(10.,20.),(20.,40.),(30.,60.)]
        actions=[(0.,0.)] if policy=='P0' else ([(self.c['trigger'],self.c['hold'])] if policy in ('P1','P2') else p3actions)
        vals=[]
        for path in pp:
            for a in actions:
                T,A,n=self.estimate(path,a,remaining,policy=policy);vals.append((T,A,tuple(path),a,n))
        mint=min(v[0] for v in vals)
        if policy=='P3':best=min((v for v in vals if v[0]<=mint+self.c['epsilon']),key=lambda v:(v[1],v[0],v[2],v[3]))
        else:best=min(vals,key=lambda v:(v[0],v[1],v[2]))
        if cur and cur[0]==e:
            curvals=[(self.estimate(cur,a,remaining,policy=policy)[0],a) for a in actions]
            incumbent=min(v[0] for v in curvals)
            if list(best[2])!=cur and incumbent-best[0]<=10:
                vv=[v for v in vals if list(v[2])==cur and (policy!='P3' or v[0]<=mint+self.c['epsilon'])]
                if vv:
                    cmin=min(v[0] for v in vv)
                    best=min((v for v in vv if v[0]<=cmin+(self.c['epsilon'] if policy=='P3' else 0)),key=lambda v:(v[1],v[0],v[3]))
                # For P3, hysteresis cannot override the global predicted-time cap.
        if policy=='P3' and best[0]>mint+self.c['epsilon']+1e-8:raise RuntimeError('Predicted global time-band violation')
        if list(best[2])!=cur:
            traci.vehicle.setRoute(aid,list(best[2]));self.route_changes+=1
        self.amaction[aid]=best[3];self.actions[str(best[3])]+=1;self.route_evaluations+=len(vals)
        if len(self.lastplanlog)<100:self.lastplanlog.append(dict(t=t,ambulance=aid,mode=policy,edge=e,T=best[0],global_min_T=mint,A=best[1],action=best[3],route=list(best[2]),candidate_count=len(vals)))
    def progress_mode(self,aid,e,position,t,dispatch):
        """Causal irreversible per-ambulance escalation using executed progress only."""
        state=self.progress.setdefault(aid,dict(last_regular=e,completed_freeflow=0.))
        if state['last_regular']!=e:
            state['completed_freeflow']+=self.m['edges'][state['last_regular']]['ff']
            state['last_regular']=e
        travelled_ff=state['completed_freeflow']+max(0.,position)/self.m['edges'][e]['v']
        delay=max(0.,t-dispatch-travelled_ff)
        threshold=self.c.get('progress_guard_s')
        just_triggered=False
        if self.policy=='P3' and threshold is not None and aid not in self.fallback_ids and delay>threshold:
            self.fallback_ids.add(aid);just_triggered=True
            self.fallback_log.append(dict(ambulance=aid,t=t,dispatch=dispatch,delay_s=delay,executed_freeflow_progress_s=travelled_ff,threshold_s=threshold))
            for key in list(self.leases):
                if key[0]==aid:self.leases.pop(key,None)
        mode='P2' if aid in self.fallback_ids else self.policy
        return mode,just_triggered
    def requests_at(self,t,active):
        req={}
        for a in sorted(active,key=lambda x:(x['depart'],x['id'])):
            aid=a['id'];e=traci.vehicle.getRoadID(aid)
            if not e or e.startswith(':') or e not in self.m['edges']:continue
            ee=self.m['edges'][e];position=traci.vehicle.getLanePosition(aid);remaining=max(0,ee['L']-position)
            mode,just_fallback=self.progress_mode(aid,e,position,t,a['depart'])
            if self.lastedge.get(aid)!=e or just_fallback:
                old=self.lastedge.get(aid)
                if old is not None:self.leases.pop((aid,old),None)
                self.plan(aid,e,remaining,t,policy=mode);self.lastedge[aid]=e
            if mode=='P0':continue
            act=self.amaction.get(aid,(self.c['trigger'],self.c['hold']));H,hold=act
            if hold==0:continue
            j=ee['to']
            if j not in self.signals:continue
            # Route may contain an internal edge while crossing; normal route lists do not.
            route=list(traci.vehicle.getRoute(aid));ri=traci.vehicle.getRouteIndex(aid);out=route[ri+1] if ri+1<len(route) else None
            eta=remaining/ee['v'];qclear=self.q(e)/max(ee['s']/self.m['meanpcu'],.1)
            active_lease=mode=='P3' and (aid,e) in self.leases
            if eta>H+qclear and not active_lease:continue
            wait,harm,allow,benefit=self.pulse(e,out,act,eta+qclear,policy=mode)
            if mode=='P3':
                leasekey=(aid,e)
                if leasekey in self.finished_leases:continue
                lease=self.leases.get(leasekey)
                headroom_ok=not out or self.obs.get(out,0)<self.c['headroom']*self.m['edges'][out]['K']
                if lease is not None:
                    sig=self.signals[j]
                    if lease['expiry'] is None and sig.mode=='green' and sig.edge==e:
                        lease['expiry']=t+max(0,hold-sig.elapsed)
                    if (lease['expiry'] is not None and t>=lease['expiry']) or t-lease['requested']>=120 or not headroom_ok:
                        self.finished_leases.add(leasekey);self.leases.pop(leasekey,None);self.expired_leases+=1
                        continue
                    # Admission commits a bounded pulse. It is not withdrawn merely
                    # because its own successful intervention turns the approach green.
                    allow=True;benefit=lease['benefit'];harm=lease['harm']
                elif allow:
                    self.leases[leasekey]=dict(requested=t,expiry=None,benefit=benefit,harm=harm)
                else:
                    if not headroom_ok:self.rejected_headroom+=1
                    elif benefit<5:self.rejected_benefit+=1
                    else:self.rejected_harm+=1
                    continue
            if mode in ('P1','P2'):
                # Aggressive comparison still cannot force receiving-space insertion in SUMO.
                allow=True
            if j not in req:
                req[j]=dict(edge=e,hold=hold,ambulance=aid,dispatch=a['depart'],predicted_benefit=benefit,predicted_burden=harm);self.requests+=1
        return req

def run_case(seed,load,missions,policy,*,output=None,**overrides):
    if policy not in POLICIES:raise ValueError(policy)
    c=dict(DEFAULTS);c.update(overrides);m=get_model();net=buildnetwork()
    scenario=make_scenario(seed,load,missions,warmup=c['warmup'],horizon=c['horizon'],mission_end=c['mission_end'])
    root=ET.parse(net).getroot();links=defaultdict(dict)
    for co in root.findall('connection'):
        if 'tl' in co.attrib:links[co.attrib['tl']][int(co.attrib['linkIndex'])]=co.attrib['from']
    signals={j:Signal(j,scenario['design']['plans'][j],[links[j][k] for k in range(max(links[j])+1)],stable_rng(0,'offset',j).randrange(len(scenario['design']['plans'][j]['arms']))) for j in m['juncs']}
    controller=Controller(m,{'seed':scenario['seed'],'design':scenario['design']},signals,policy,c)
    logdir=Path(output) if output else HERE/'run_logs';logdir.mkdir(parents=True,exist_ok=True)
    tag=f'{scenario["key"]}_{policy}_{c["base"]}_b{c["harm_budget"]}_eps{c["epsilon"]}_dt{c["step"]}_noise{int(c["sensor_noise"])}_delay{c["sensor_delay"]}_actions{c["action_mode"]}_pg{c["progress_guard_s"]}'
    cmd=[SUMO,'--net-file',str(net),'--route-files',scenario['route_file'],'--begin','0','--end',str(c['horizon']),'--step-length',str(c['step']),'--no-step-log','true','--duration-log.disable','true','--no-warnings','true','--time-to-teleport','-1','--collision.action','warn','--seed',str(seed),'--ignore-junction-blocker','-1','--error-log',str(logdir/(tag+'.log'))]
    tstart=time.perf_counter();traci.start(cmd)
    eids=sorted(m['edges']);orig=m['bounds'];partition=eids+['INTERNAL']+['SOURCE_'+o for o in orig];idx={e:i for i,e in enumerate(eids)}
    for eid in eids:traci.edge.subscribe(eid,[tc.LAST_STEP_VEHICLE_NUMBER])
    desired=defaultdict(list);v_to_origin={}
    for v in scenario['ordinary']:desired[v['origin']].append(v['depart']);v_to_origin[v['id']]=v['origin']
    departed=defaultdict(int);completed=0;ordinary_arrivals={};ordinary_insertions={};amap={a['id']:a for a in scenario['ambulances']};aliveamb=set();arrivals={};insertions={};activecounts=[]
    history=np.zeros((int(round((c['horizon']-c['warmup'])/c['step'])),len(partition)),dtype=np.int16)
    mission_completed=0;collisions=0;teleports=0;all_history_j=[];J=0.;vehicle_seconds_identity_error=0;max_ordinary_in_system=0
    if c['step'] not in (1.,.5,.25):raise ValueError('Supported steps are 1,0.5,0.25')
    step_sub=int(round(1/c['step']));controller_time=0.;decisions=0
    try:
        for tick in range(c['horizon']):
            # Apply causal controller command at integer decision boundary, then advance physical simulator.
            counts={}
            if tick>0:
                sr=traci.edge.getAllSubscriptionResults()
                counts={eid:int(sr.get(eid,{}).get(tc.LAST_STEP_VEHICLE_NUMBER,0)) for eid in eids}
            controller.observe(tick,counts)
            ts=time.perf_counter();req=controller.requests_at(tick,[amap[x] for x in aliveamb]);decisions+=bool(aliveamb)
            for j,sig in signals.items():sig.update(tick,req.get(j),controller.obs,base=c['base'])
            controller_time+=time.perf_counter()-ts
            for sub in range(step_sub):
                now=traci.simulation.getTime()
                # Left-endpoint census represents [now, now+step). Desired releases
                # are integer-grid times. Completion clocks use actual SUMO time.
                sr=traci.edge.getAllSubscriptionResults()
                regular=np.array([int(sr.get(e,{}).get(tc.LAST_STEP_VEHICLE_NUMBER,0)) for e in eids],dtype=np.int32)
                for aid in aliveamb:
                    road=traci.vehicle.getRoadID(aid)
                    if road in idx:regular[idx[road]]-=1
                source=np.array([bisect.bisect_right(desired[o],now)-departed[o] for o in orig],dtype=np.int32)
                live=len(traci.vehicle.getIDList())-len(aliveamb)
                internal=live-int(regular.sum())
                state=np.concatenate([regular,[internal],source])
                released=sum(bisect.bisect_right(desired[o],now) for o in orig);N=released-completed
                err=abs(N-int(state.sum()));vehicle_seconds_identity_error=max(vehicle_seconds_identity_error,err)
                if (state<0).any():raise RuntimeError(('Negative partition',now,state.tolist()))
                if err:raise RuntimeError(('Conservation partition error',now,N,state.sum()))
                if sub==0:all_history_j.append(N)
                if now>=c['warmup']:
                    history[int(round((now-c['warmup'])/c['step']))]=state
                    J+=N*c['step'];max_ordinary_in_system=max(max_ordinary_in_system,N);activecounts.append(len(aliveamb))
                traci.simulationStep()
                actual=traci.simulation.getTime()
                for v in traci.simulation.getDepartedIDList():
                    if v in amap:aliveamb.add(v);insertions[v]=actual
                    else:departed[v_to_origin[v]]+=1;ordinary_insertions[v]=actual
                for v in traci.simulation.getArrivedIDList():
                    if v in amap:arrivals[v]=actual;aliveamb.discard(v);mission_completed+=1
                    else:completed+=1;ordinary_arrivals[v]=actual
                collisions+=traci.simulation.getCollidingVehiclesNumber();teleports+=traci.simulation.getStartingTeleportNumber()
        endsource={o:bisect.bisect_right(desired[o],c['horizon'])-departed[o] for o in orig}
        endunfinished=sum(bisect.bisect_right(desired[o],c['horizon']) for o in orig)-completed
    finally:
        traci.close()
    elapsed=time.perf_counter()-tstart
    direct_J=sum(max(0.,min(ordinary_arrivals.get(v['id'],c['horizon']),c['horizon'])-max(v['depart'],c['warmup'])) for v in scenario['ordinary'])
    residence_error=abs(J-direct_J)
    if residence_error>1e-6:raise RuntimeError(('Residence identity error',J,direct_J))
    mission_rows=[]
    for a in scenario['ambulances']:
        arrival=arrivals.get(a['id']);travel=(arrival-a['depart']) if arrival is not None else (c['horizon']-a['depart'])
        mission_rows.append(dict(id=a['id'],dispatch=a['depart'],origin=a['origin'],arrival=arrival,insertion=insertions.get(a['id']),travel_s=travel,censored=arrival is None))
    result=dict(seed=seed,load=load,missions=missions,policy=policy,config=c,backend=BACKEND,sumo_version=traci.__version__ if hasattr(traci,'__version__') else '1.28.0',scenario_key=scenario['key'],schedule_sha256=scenario['schedule_sha256'],n_ordinary=len(scenario['ordinary']),nominal_critical_X=scenario['design']['nominal_critical_X'],design_scale=scenario['design']['scale'],ordinary_J_vehicle_s=J,ordinary_completed=completed,unfinished_ordinary=endunfinished,source_waiting_end=sum(endsource.values()),missions_completed=mission_completed,mission_rows=mission_rows,ambulance_mean_s=float(np.mean([r['travel_s'] for r in mission_rows])) if mission_rows else None,ambulance_max_s=max((r['travel_s'] for r in mission_rows),default=None),route_changes=controller.route_changes,progress_guard_fallbacks=len(controller.fallback_log),progress_guard_log=controller.fallback_log,expired_priority_leases=controller.expired_leases,route_candidate_evaluations=controller.route_evaluations,priority_request_ticks=controller.requests,rejected_harm_ticks=controller.rejected_harm,rejected_headroom_ticks=controller.rejected_headroom,rejected_benefit_ticks=controller.rejected_benefit,priority_phase_admissions=sum(s.accepted for s in signals.values()),guard_overrides=sum(s.guard_overrides for s in signals.values()),signal_timing_violations=sum(s.phase_violations for s in signals.values()),completed_signal_intervals=sum(len(s.phase_spans) for s in signals.values()),max_service_age_s=max(s.max_service_age for s in signals.values()),pedestrian_service_opportunities=sum(s.ped_opportunities for s in signals.values()),sensor_availability=controller.sensor_available/max(1,controller.sensor_total),max_simultaneous_ambulances=max(activecounts,default=0),colliding_vehicle_events=collisions,starting_teleport_events=teleports,partition_identity_max_error=vehicle_seconds_identity_error,residence_identity_error=round(residence_error,9),ordinary_individual_J_vehicle_s=direct_J,max_ordinary_in_system=max_ordinary_in_system,wall_time_s=elapsed,controller_wall_time_s=controller_time,active_decision_ticks=decisions,selected_action_counts=dict(controller.actions),plan_examples=controller.lastplanlog,partition=partition,history=history,whole_episode_population=all_history_j)
    if c['save_trace']:
        np.savez_compressed(logdir/(tag+'.npz'),counts=history,partition=np.array(partition),step=c['step'],start=c['warmup'],population=np.array(all_history_j,dtype=np.int32));result['trace_file']=str(logdir/(tag+'.npz'))
    with (logdir/(tag+'_ordinary_events.csv')).open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['id','desired','insertion_observed','completion_observed','restricted_residence'])
        for v in scenario['ordinary']:
            w.writerow([v['id'],v['depart'],ordinary_insertions.get(v['id'],''),ordinary_arrivals.get(v['id'],''),max(0.,min(ordinary_arrivals.get(v['id'],c['horizon']),c['horizon'])-max(v['depart'],c['warmup']))])
    (logdir/(tag+'.json')).write_text(json.dumps({k:v for k,v in result.items() if k!='history'},indent=2))
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=5000);ap.add_argument('--load',type=float,default=.8);ap.add_argument('--missions',type=int,default=1);ap.add_argument('--policy',choices=list(POLICIES),default='P0');ap.add_argument('--warmup',type=int,default=900);ap.add_argument('--horizon',type=int,default=3600);ap.add_argument('--mission-end',type=int,default=2700);ap.add_argument('--harm-budget',type=float,default=120);ap.add_argument('--epsilon',type=float,default=10);ap.add_argument('--base',choices=['fixed','longest_queue'],default='fixed');ap.add_argument('--action-mode',choices=['multi','strong'],default='multi');ap.add_argument('--progress-guard-s',type=float,default=None);ap.add_argument('--step',type=float,default=1.);ap.add_argument('--output',default=str(HERE/'pilot'));args=ap.parse_args()
    r=run_case(args.seed,args.load,args.missions,args.policy,warmup=args.warmup,horizon=args.horizon,mission_end=args.mission_end,harm_budget=args.harm_budget,epsilon=args.epsilon,base=args.base,action_mode=args.action_mode,progress_guard_s=args.progress_guard_s,step=args.step,output=args.output)
    print(json.dumps({k:v for k,v in r.items() if k not in ('history','plan_examples','mission_rows','partition','whole_episode_population')},indent=2))
if __name__=='__main__':main()
