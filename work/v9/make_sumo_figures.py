#!/usr/bin/env python3
"""Publication figures from root-owned completed analysis; no simulations/inference."""
from pathlib import Path
import argparse, hashlib, json, os, sys
H=Path(__file__).resolve().parent
sys.path.insert(0,str(H/'vendor'))
os.environ.setdefault('MPLCONFIGDIR',str(H/'mpl_cache'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

OUT=H/'figures'
LABEL={'P0':'S0','P1':'SEQ','P2':'JFAST','P3':'JSEL'}
COLOR={'P0':'#292d32','P1':'#b86b19','P2':'#176b9a','P3':'#42816e'}
MARK={'P0':'o','P1':'s','P2':'D','P3':'^'}
STYLE={'P0':'-','P1':':','P2':'-','P3':'--'}
GREY='#59616a';GRID='#e1e5e8';PURPLE='#735295'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.labelsize':10,'axes.titlesize':10.5,'axes.titleweight':'semibold','axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':GREY,'axes.linewidth':.7,'xtick.labelsize':10,'ytick.labelsize':10,'xtick.major.size':3,'ytick.major.size':3,'legend.fontsize':10,'legend.frameon':False,'figure.facecolor':'white','axes.facecolor':'white','savefig.facecolor':'white','savefig.dpi':320,'mathtext.fontset':'dejavusans','lines.linewidth':1.4,'lines.markersize':4.3,'svg.fonttype':'none'})

def intervals(stats):
    y=np.array([s['mean'] for s in stats]);lo=np.array([s['lo'] for s in stats]);hi=np.array([s['hi'] for s in stats])
    if not np.all(np.isfinite(np.r_[y,lo,hi])):raise ValueError('Nonfinite analysis interval')
    if not np.all((lo<=y+1e-9)&(y<=hi+1e-9)):raise ValueError('Mean is outside supplied interval; inspect analysis rather than fabricate a plotting interval')
    return y,np.array([y-lo,hi-y])

def clean(ax,axis='y'):
    ax.grid(axis=axis,color=GRID,lw=.6,zorder=0);ax.set_axisbelow(True)

def policy_handles():
    return [Line2D([],[],color=COLOR[p],marker=MARK[p],linestyle=STYLE[p],label=LABEL[p],lw=1.4,markersize=4.5) for p in LABEL]

def line_ci(ax,x,stats,p,offset=0):
    means,error=intervals(stats)
    ax.errorbar(np.asarray(x)+offset,means,yerr=error,color=COLOR[p],marker=MARK[p],linestyle=STYLE[p],lw=1.35,elinewidth=.9,capsize=2.1,capthick=.8,zorder=4,label=LABEL[p])

def export(fig,name):
    OUT.mkdir(exist_ok=True)
    # Fixed physical size preserves the 10-point typography at the stated paper width.
    fig.savefig(OUT/(name+'.png'),dpi=320)
    fig.savefig(OUT/(name+'.svg'))
    plt.close(fig)

def header(fig,title,subtitle):
    fig.suptitle(title,x=.5,y=.985,fontsize=12,fontweight='semibold')
    fig.text(.5,.91,subtitle,ha='center',va='center',fontsize=10,color=GREY)

def make_time(d):
    loads=d['protocol']['loads'];rates=d['protocol']['missions_per_hour'];n=len(d['protocol']['seeds'])
    lookup={(z['load'],z['missions'],z['policy']):z for z in d['cells']}
    fig,axs=plt.subplots(1,3,figsize=(6.7,4.15),sharey=True)
    fig.subplots_adjust(left=.105,right=.985,bottom=.235,top=.79,wspace=.22)
    ymax=max(z['metrics']['time_s']['hi'] for z in d['cells'])*1.08
    offsets={'P0':-.005,'P1':-.0017,'P2':.0017,'P3':.005}
    for i,(ax,m) in enumerate(zip(axs,rates)):
        for p in LABEL:line_ci(ax,loads,[lookup[x,m,p]['metrics']['time_s'] for x in loads],p,offsets[p])
        clean(ax);ax.set_xlim(min(loads)-.035,max(loads)+.035);ax.set_xticks(loads);ax.set_xticklabels([f'{x:.2f}' for x in loads]);ax.set_ylim(0,ymax)
        ax.set_title(f'({chr(97+i)}) {m} mission'+('' if m==1 else 's')+'/h',loc='left',pad=8)
        ax.set_xlabel('Nominal load $X$')
    axs[0].set_ylabel('Mean restricted duration (s)')
    header(fig,'Restricted ambulance duration across load and dose',f'SYNTHETIC · {n} paired seeds per condition · 95% seed-bootstrap intervals')
    fig.legend(handles=policy_handles(),loc='lower center',bbox_to_anchor=(.5,.02),ncol=4,columnspacing=1.15,handlelength=2.2,handletextpad=.55)
    export(fig,'sumo_time')

def forest_points(ax,rows,metric,y,color=COLOR['P3'],markers=None):
    means,errs=intervals([r['metrics'][metric] for r in rows])
    for i,yy in enumerate(y):
        ax.errorbar(means[i],yy,xerr=errs[:,i:i+1],color=color if isinstance(color,str) else color[i],fmt=markers[i] if markers else 'o',ms=4.7,elinewidth=1.05,capsize=2.2,capthick=.8,zorder=4)
    return means,errs

def forest_limits(ax,rows,metric,include=None):
    ss=[r['metrics'][metric] for r in rows];low=min([0]+[s['lo'] for s in ss]);high=max([0]+[s['hi'] for s in ss])
    if include is not None:low=min(low,include);high=max(high,include)
    span=max(high-low,1e-3);ax.set_xlim(low-.10*span,high+.12*span);ax.xaxis.set_major_locator(MaxNLocator(nbins=3,min_n_ticks=2))
    ax.axvline(0,color=GREY,lw=.8,zorder=2);clean(ax,'x')

def make_effects(d):
    n=len(d['protocol']['seeds']);lookup={(z['load'],z['missions']):z for z in d['contrasts'] if z['comparison']=='P3-P2'}
    cond=[(x,m) for m in d['protocol']['missions_per_hour'] for x in d['protocol']['loads']]
    rows=[lookup[c] for c in cond];y=np.arange(len(rows))[::-1]
    labels=[f'{x:.2f} · {m}/h' for x,m in cond];marks=[{1:'o',4:'s',10:'^'}[m] for x,m in cond]
    fig,axs=plt.subplots(1,3,figsize=(6.7,5.0),sharey=True)
    fig.subplots_adjust(left=.19,right=.985,bottom=.20,top=.79,wspace=.48)
    keys=['time_s','A_vh','Dplus_vh'];titles=['(a) Ambulance','(b) Spatial $A$','(c) Individual $D^{+}$'];xlabels=['Duration difference\n(s)','Exposure difference\n(vehicle-h)','Burden difference\n(vehicle-h)']
    for ax,key,title,xlab in zip(axs,keys,titles,xlabels):
        for start in [2.5,8.5]:ax.axhspan(start-3,start,color='#f4f6f7',zorder=0)
        forest_points(ax,rows,key,y,markers=marks);forest_limits(ax,rows,key,20 if key=='time_s' else None)
        ax.set_ylim(-.6,len(y)-.4);ax.set_title(title,loc='left',pad=8);ax.set_xlabel(xlab)
        ax.set_yticks(y);ax.set_yticklabels(labels)
        if key=='time_s':ax.axvline(20,color=COLOR['P1'],linestyle='--',lw=1,zorder=2)
    axs[0].set_ylabel('Nominal $X$ · missions/h')
    header(fig,'Paired JSEL minus JFAST effects',f'SYNTHETIC · {n} paired seeds per condition · 95% seed-bootstrap intervals')
    axs[0].text(20,len(rows)-.65,'20 s',ha='center',va='center',fontsize=10,color=COLOR['P1'],bbox=dict(facecolor='white',edgecolor='none',pad=.3,alpha=.95))
    fig.text(.5,.018,'Right of zero: JSEL has the larger outcome. Intervals are marginal.',ha='center',fontsize=10,color=GREY)
    export(fig,'sumo_effects')

def make_burden(d):
    loads=d['protocol']['loads'];m=4;n=len(d['protocol']['seeds']);lookup={(z['load'],z['missions'],z['policy']):z for z in d['cells']}
    fig,axs=plt.subplots(1,3,figsize=(6.7,4.35));fig.subplots_adjust(left=.105,right=.985,bottom=.25,top=.79,wspace=.56)
    offsets={'P0':-.005,'P1':-.0017,'P2':.0017,'P3':.005}
    keys=['A_vh','Dplus_vh','deltaJ_vh'];titles=['(a) Spatial $A$','(b) Individual $D^{+}$',r'(c) Signed $\Delta J$']
    for ax,key,title in zip(axs,keys,titles):
        ss=[lookup[x,m,p]['metrics'][key] for p in LABEL for x in loads]
        low=min(0,min(v['lo'] for v in ss));high=max(v['hi'] for v in ss);span=max(high-low,1e-3)
        ax.set_ylim(low-.07*span,high+.12*span)
        for p in LABEL:line_ci(ax,loads,[lookup[x,m,p]['metrics'][key] for x in loads],p,offsets[p])
        ax.axhline(0,color=GREY,lw=.8,zorder=2);clean(ax)
        ax.set_xlim(min(loads)-.035,max(loads)+.035);ax.set_xticks(loads);ax.set_xticklabels([f'{x:.2f}' for x in loads]);ax.set_xlabel('Nominal load $X$');ax.set_ylabel('Vehicle-hours');ax.yaxis.set_major_locator(MaxNLocator(nbins=4,min_n_ticks=3));ax.set_title(title,loc='left',pad=8)
    header(fig,'Ordinary-traffic burdens relative to S0',f'SYNTHETIC · four missions/h · {n} paired seeds · separate vertical scales')
    fig.legend(handles=policy_handles(),loc='lower center',bbox_to_anchor=(.5,.035),ncol=4,columnspacing=1.15,handlelength=2.2,handletextpad=.55)
    export(fig,'sumo_burden')

def make_sensitivity(d):
    allrows=d.get('sensitivities',[]);phases=['sensitivity','adaptive_base','exact_counts','ablation'];phase_names={'sensitivity':'Step .25','adaptive_base':'Longest count','exact_counts':'Frequent exact','ablation':'No guard'}
    missing=[p for p in phases if not any(r['phase']==p for r in allrows)]
    if missing:raise RuntimeError('Analysis is missing completed secondary phases: '+','.join(missing))
    rows=[r for phase in phases for r in sorted([z for z in allrows if z['phase']==phase],key=lambda z:z['load'])]
    if len(rows)!=8:raise RuntimeError('Expected four completed secondary phases at two loads each')
    yy=np.arange(len(rows))[::-1];labels=[phase_names[r['phase']]+f' | {r["load"]:.2f}' for r in rows]
    colors=[PURPLE if r['phase']=='ablation' else COLOR['P3'] for r in rows];marks=['D' if r['phase']=='ablation' else 'o' for r in rows]
    ns=sorted({r['metrics']['time_s']['n'] for r in rows});ntext='/'.join(map(str,ns))
    fig,axs=plt.subplots(1,3,figsize=(6.7,5.7),sharey=True);fig.subplots_adjust(left=.285,right=.985,bottom=.29,top=.79,wspace=.49)
    keys=['time_s','A_vh','Dplus_vh'];titles=['(a) Time','(b) Spatial $A$','(c) $D^{+}$'];xlabs=['Plotted difference\n(s)','Plotted difference\n(vehicle-h)','Plotted difference\n(vehicle-h)']
    for ax,key,title,xlab in zip(axs,keys,titles,xlabs):
        ax.axhspan(-.5,1.5,color='#f3eef8',zorder=0);ax.axhline(1.5,color='#c1b5cd',lw=.7,zorder=1)
        forest_points(ax,rows,key,yy,color=colors,markers=marks);forest_limits(ax,rows,key)
        ax.set_ylim(-.6,len(rows)-.4);ax.set_yticks(yy);ax.set_yticklabels(labels);ax.set_xlabel(xlab);ax.set_title(title,loc='left',pad=8)
    header(fig,'Sensitivity and progress-guard ablation',f'SYNTHETIC · four missions/h · {ntext} paired seeds per row · 95% intervals')
    handles=[Line2D([],[],color=COLOR['P3'],marker='o',lw=1,label='Secondary − main (JSEL − JFAST)'),Line2D([],[],color=PURPLE,marker='D',lw=1,label='No guard − guarded JSEL')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.035),ncol=1,fontsize=10,handlelength=2.1,labelspacing=.65)
    export(fig,'sumo_sensitivity')

def captions(d):
    n=len(d['protocol']['seeds']);sn=sorted({r['metrics']['time_s']['n'] for r in d['sensitivities']})
    paragraphs=[
      'Figure sumo_time. Synthetic microscopic restricted ambulance duration under S0 (P0, traffic-aware routing without signal priority), SEQ (P1, routing without anticipated priority followed by aggressive requests), JFAST (P2, joint time-oriented routing and aggressive priority), and JSEL (P3, joint selective routing with the frozen causal progress guard). Panels show one, four and ten scheduled missions in the one-hour mission window, across nominal load targets X=0.60,0.80,0.95. Each point is the mean of episode-mean durations from desired dispatch to recorded completion or the common horizon H, whichever occurs first, with a 95% percentile bootstrap interval over '+str(n)+' scenario seeds. Missions within a seed are clustered. Bars around absolute policy means are not confidence intervals for their paired differences; the paired contrasts are shown separately. Small horizontal displacements distinguish overlapping intervals without changing the nominal load values. Nominal X is an ex ante capacity index, not measured SUMO saturation. Nonarrivals remain included at their horizon-restricted duration rather than being omitted. Episode means do not bound individual delays; censoring and severe mission-level tails are reported separately. No observed city is represented.',
      'Figure sumo_effects. Paired effects JSEL−JFAST on episode-mean restricted ambulance duration, positive spatial exposure A, and positive individual restricted-residence burden D⁺ in all nine load-by-dose conditions. Points and intervals use scenario-paired differences before seed-level bootstrap resampling (n='+str(n)+',10000 resamples). The dashed20 s line is the predeclared ambulance design target, not a guaranteed trip-time bound. The zero line is the no-difference reference; positive values mean a larger outcome under JSEL. Intervals are marginal95% intervals rather than simultaneous or multiplicity-adjusted statements, and intervals crossing zero do not establish equivalence. Both A and D⁺ are first computed relative to each matched S0 episode before subtracting the JFAST value.',
      'Figure sumo_burden. Ordinary-traffic outcomes relative to the scenario-matched S0 trajectory, for the four-mission/h condition. All four microscopic controllers are shown across the three nominal loads, with marginal95% seed-bootstrap intervals (n='+str(n)+'). A is positive spatial accumulation exposure: physical-step integration of the sum of positive occupancy differences on59 regular links, one internal-junction group and eight desired-but-uninserted source queues. D⁺ is the sum across identical ordinary IDs of positive differences in restricted individual residence through the common horizon. ΔJ is signed total restricted residence change, retaining both benefits and harms. Quantities are converted from vehicle-seconds to vehicle-hours and are totals per simulated episode, not automatically per mission. A and D⁺ can be positive when ΔJ is small, and A includes moving-traffic displacement. S0 is identically zero by definition. The panels have separate vertical scales; comparing their apparent heights does not compare equal numerical magnitudes. The complete nine-condition paired comparison is reported in sumo_effects.',
      'Figure sumo_sensitivity. Four prespecified secondary analyses at nominal X=0.60 and0.95 with four missions/h. For the0.25 s physical-step, longest-observed-count base-controller, and frequent noiseless-available-count analyses (green circles), each point is the paired change in the JSEL−JFAST treatment contrast relative to the corresponding main0.5 s/noisy-count/cyclic-base episode. For the progress-guard ablation (purple diamonds and shaded rows), the point instead compares unguarded JSEL directly with guarded JSEL on the same scenario; it is not another difference of JSEL−JFAST contrasts. The frequent-count variant samples each second without count noise or receipt delay; the Markov dropout process remains active. It is not an oracle: missing records leave stale counts, exact queues are unknown, and future traffic is unavailable. Sampling frequency also changes the duration in seconds of this per-sample dropout process, so this is a joint observation-model sensitivity. Each row uses '+('/'.join(map(str,sn)))+' paired scenario seeds and10000 bootstrap resamples. Intervals are marginal95% percentile intervals. The bootstrap operates on the paired difference at the seed level, not on independently sampled policy means. A and D⁺ retain the same S0-relative definitions as the main analysis. The broad high-load timestep interval does not establish numerical equivalence, and an interval containing zero is not an equivalence test. These are finite-sample model and controller sensitivities, not validation against field measurements.'
    ]
    # Human-facing spacing in captions is explicit, independent of document builders.
    fixes={'n='+str(n)+',10000':'n='+str(n)+', 10000','dashed20':'dashed 20','marginal95':'marginal 95','on59':'on 59','and0.95':'and 0.95','the0.25':'the 0.25','main0.5':'main 0.5','and10000':'and 10000'}
    text='\n\n'.join(paragraphs)+'\n'
    for a,b in fixes.items():text=text.replace(a,b)
    (H/'figscaptions.txt').write_text(text)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--analysis',type=Path,default=H/'sumo_analysis.json');args=ap.parse_args()
    if not args.analysis.exists():raise SystemExit('Waiting for root-owned completed analysis: '+str(args.analysis))
    d=json.loads(args.analysis.read_text())
    make_time(d);make_effects(d);make_burden(d);make_sensitivity(d);captions(d)
    manifest=dict(analysis_file=str(args.analysis),analysis_sha256=hashlib.sha256(args.analysis.read_bytes()).hexdigest(),figure_width_inches=6.7,main_seed_count=len(d['protocol']['seeds']),files={name:(OUT/(name+'.png')).stat().st_size for name in ['sumo_time','sumo_effects','sumo_burden','sumo_sensitivity']})
    (OUT/'sumo_figures_manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
