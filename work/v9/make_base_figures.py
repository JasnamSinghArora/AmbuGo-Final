#!/usr/bin/env python3
"""Static research figures from completed AmbuGo outputs, with no traffic runs."""
from pathlib import Path
import csv,json,math,os,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'vendor'))
os.environ['MPLCONFIGDIR']=str(HERE/'mpl_cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch

OUT=HERE/'figures';OUT.mkdir(exist_ok=True)
DATA=json.loads((HERE/'corrected_summary.json').read_text())
VER=json.loads((HERE/'meso_verification.json').read_text())
GEOM=HERE.parents[1]/'outputs/AmbuGo_v7_Synthetic_Data'
COLORS={'P0':'#292d32','P1':'#b86b19','P2':'#176b9a','P4':'#735295'}
LABELS={'P0':'M0  no priority','P1':'M1  no phase skip','P2':'M2  phase skip','P4':'MR  queue and route rules'}
STYLES={'P0':('-', 'o'),'P1':('-', 's'),'P2':('-', 'D'),'P4':('--', '^')}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':9,'axes.titlesize':10,'axes.titleweight':'semibold','axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#59616a','axes.linewidth':.65,'xtick.labelsize':8.3,'ytick.labelsize':8.3,'xtick.major.width':.6,'ytick.major.width':.6,'xtick.major.size':3,'ytick.major.size':3,'legend.fontsize':8.2,'legend.frameon':False,'figure.facecolor':'white','axes.facecolor':'white','savefig.facecolor':'white','savefig.dpi':320,'mathtext.fontset':'dejavusans','lines.linewidth':1.5,'lines.markersize':4.1})

def cells(policy,rho=0.):
 return sorted([x for x in DATA['cells'] if x['policy']==policy and x['rho']==rho],key=lambda d:d['X'])
def changes(policy,rho=0.):
 return sorted([x for x in DATA['mechanical_changes'] if x['policy']==policy and x['rho']==rho],key=lambda d:d['X'])
def clean(ax):
 ax.grid(axis='y',color='#dfe3e7',linewidth=.55,zorder=0)
 ax.set_axisbelow(True)
def errorbar(ax,x,stats,color,marker='o',label=None,linestyle='-'):
 means=np.array([v['mean'] for v in stats]);lo=np.array([v['ci_low'] for v in stats]);hi=np.array([v['ci_high'] for v in stats])
 ax.errorbar(x,means,yerr=np.vstack([means-lo,hi-means]),color=color,marker=marker,linestyle=linestyle,linewidth=1.2,elinewidth=.8,capsize=2.,capthick=.8,label=label,zorder=4)
def export(fig,name):
 fig.savefig(OUT/(name+'.png'),dpi=320,bbox_inches='tight',pad_inches=.055)
 plt.close(fig)

def network():
 nd=list(csv.DictReader((GEOM/'nodes.csv').open()));ed=list(csv.DictReader((GEOM/'edges.csv').open()));xy={r['node_id']:(float(r['x_m']),float(r['y_m'])) for r in nd}
 fig,ax=plt.subplots(figsize=(6.5,4.75));fig.subplots_adjust(left=.02,right=.98,bottom=.12,top=.88)
 drawn=set()
 for e in ed:
  u,v=e['from_node'],e['to_node'];pair=tuple(sorted([u,v]))
  if pair not in drawn:
   x,y=xy[u];xx,yy=xy[v];ax.plot([x,xx],[y,yy],color='#b6bdc4',lw=1.4 if int(e['lanes'])==2 else .8,zorder=1);drawn.add(pair)
  # A short arrow in the center of each directed link shows the asymmetric edge.
  a=np.array(xy[u]);b=np.array(xy[v]);d=b-a;L=np.linalg.norm(d);n=np.array([-d[1],d[0]])/L
  center=(a+b)/2+n*8;start=center-d/L*19;end=center+d/L*19
  ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=6.5,lw=.6,color='#73818d',zorder=2))
 for r in nd:
  ident=r['node_id'];x,y=xy[ident];signal=r['kind']=='signalized_junction'
  ax.scatter([x],[y],s=36 if signal else 34,marker='o' if signal else 's',facecolor='#176b9a' if signal else '#b86b19',edgecolor='white',lw=.65,zorder=3)
  if ident=='BE1':
   ax.scatter([x],[y],s=85,marker='*',facecolor='#ad3b3b',edgecolor='white',lw=.6,zorder=4)
   ax.annotate('BE1  hospital',xy=(x,y),xytext=(8,-2),textcoords='offset points',fontsize=8.5,ha='left',va='center',color='#8c2929')
  else:
   dy=-9 if signal else -10
   ax.annotate(ident,xy=(x,y),xytext=(0,dy),textcoords='offset points',fontsize=8,ha='center',va='bottom',bbox=dict(facecolor='white',edgecolor='none',pad=.3,alpha=.9),zorder=5)
 ax.set_aspect('equal');ax.set_xlim(-390,1710);ax.set_ylim(1520,-400);ax.axis('off')
 ax.annotate('N',xy=(-250,-320),xytext=(-250,-100),arrowprops=dict(arrowstyle='-|>',lw=1,color='#303b45'),ha='center',va='center',fontsize=9,color='#303b45')
 sx,sy=-240,1410;ax.plot([sx,sx+500],[sy,sy],color='#303b45',lw=1.6);ax.plot([sx,sx],[sy-15,sy+15],color='#303b45',lw=1);ax.plot([sx+500,sx+500],[sy-15,sy+15],color='#303b45',lw=1);ax.text(sx+250,sy+67,'500 m',ha='center',va='center',fontsize=8.5)
 fig.suptitle('Synthetic signalized district',x=.5,y=.99,fontsize=11,fontweight='semibold')
 fig.text(.5,.94,'16 signalized junctions   |   8 boundary nodes   |   59 directed links',ha='center',fontsize=9,color='#4d5660')
 handles=[Line2D([],[],marker='o',color='none',markerfacecolor='#176b9a',markeredgecolor='white',markersize=6,label='Signalized junction'),Line2D([],[],marker='s',color='none',markerfacecolor='#b86b19',markeredgecolor='white',markersize=6,label='Boundary node'),Line2D([],[],marker='*',color='none',markerfacecolor='#ad3b3b',markersize=9,label='Hospital destination')]
 fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.006),ncol=3,columnspacing=1.3,handletextpad=.5,fontsize=8.3)
 export(fig,'network')

def meso_results():
 fig,axs=plt.subplots(1,2,figsize=(6.5,4.0));fig.subplots_adjust(left=.1,right=.985,bottom=.27,top=.80,wspace=.31)
 xx=np.array([x['X'] for x in cells('P0')])
 for i,p in enumerate(['P0','P1','P2','P4']):
  rr=cells(p);style,marker=STYLES[p]
  axs[0].plot(xx,[x['ambulance_mean'] for x in rr],linestyle=style,marker=marker,color=COLORS[p],label=LABELS[p],zorder=4)
  if p!='P0':
   # Tiny horizontal dodge makes overlapping uncertainty bars readable. Tick
   # positions retain the nominal design X; no numerical endpoint is modified.
   offset={'P1':-.0025,'P2':0.,'P4':.0025}[p]
   errorbar(axs[1],xx+offset,[x['delta_residence_vh'] for x in rr],COLORS[p],marker,linestyle=style)
 for ax in axs:
  clean(ax);ax.set_xlim(.575,.975);ax.set_xticks(xx);ax.set_xticklabels([f'{x:.2f}' for x in xx]);ax.set_xlabel('Nominal critical degree of saturation $X$')
 axs[0].set_ylabel('Mean ambulance travel time (s)');axs[0].set_title('(a) Ambulance outcome',loc='left',pad=8);axs[0].set_ylim(170,525)
 axs[1].set_ylabel('Extra ordinary residence (vehicle-h)');axs[1].set_title('(b) Paired ordinary-traffic effect',loc='left',pad=8);axs[1].axhline(0,color='#3e4852',lw=.8,zorder=2)
 fig.suptitle('Mechanically corrected mesoscopic experiment',y=.985,fontsize=11,fontweight='semibold')
 fig.text(.5,.91,'No yielding ($\\rho=0$); 200 paired scenarios per nominal load',ha='center',fontsize=9,color='#4d5660')
 handles,labels=axs[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.004),ncol=2,columnspacing=1.5,handlelength=2.8,fontsize=8.3)
 export(fig,'meso_results')

def mechanical_change():
 fig,axs=plt.subplots(1,2,figsize=(6.5,3.9));fig.subplots_adjust(left=.1,right=.985,bottom=.27,top=.79,wspace=.35)
 xx=np.array([x['X'] for x in changes('P0')])
 for p,delta,marker,style in [('P0',-.0016,'o','--'),('P2',.0016,'D','-')]:
  rr=changes(p);errorbar(axs[0],xx+delta,[x['ambulance_model_change'] for x in rr],COLORS[p],marker,label=LABELS[p],linestyle=style)
 rr=changes('P2');errorbar(axs[1],xx,[x['paired_effect_model_change'] for x in rr],COLORS['P2'],'D')
 for ax in axs:
  clean(ax);ax.axhline(0,color='#3e4852',lw=.8,zorder=2);ax.set_xlim(.575,.975);ax.set_xticks(xx);ax.set_xticklabels([f'{x:.2f}' for x in xx]);ax.set_xlabel('Nominal critical degree of saturation $X$')
 axs[0].set_ylabel('Corrected minus original travel (s)');axs[0].set_title('(a) Ambulance travel change',loc='left',pad=8)
 axs[1].set_ylabel('Change in paired effect (vehicle-h)');axs[1].set_title('(b) M2 ordinary-cost change',loc='left',pad=8)
 fig.suptitle('Sensitivity to ambulance admission and capacity mechanics',y=.985,fontsize=10.7,fontweight='semibold')
 fig.text(.5,.91,'Paired corrected minus original effects; no yielding ($\\rho=0$)',ha='center',fontsize=9,color='#4d5660')
 handles,labels=axs[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.06),ncol=2,columnspacing=1.7,handlelength=2.6,fontsize=8.2)
 fig.text(.5,.015,'(b) compares (M2 $-$ M0) in each model; intervals are 95% paired bootstrap CIs.',ha='center',fontsize=8,color='#4d5660')
 export(fig,'mechanical_change')

def analytic_pulse():
 fig,axs=plt.subplots(1,2,figsize=(6.5,3.6));fig.subplots_adjust(left=.105,right=.985,bottom=.22,top=.78,wspace=.35)
 xx=np.linspace(.2,.95,250);yy=25*xx/(1-xx)
 axs[0].plot(xx,yy,color='#176b9a',label='Exact fluid expression')
 rr=VER['fluid_pulse'];axs[0].scatter([v['X'] for v in rr],[v['numerical_area_vehicle_s'] for v in rr],color='#b86b19',marker='o',s=19,zorder=4,label='ODE integration')
 axs[0].set_xlabel('Load $X=\\lambda/c$');axs[0].set_ylabel('Additional residence (vehicle-s)');axs[0].set_title('(a) Isolated fluid pulse',loc='left',pad=8);axs[0].set_xlim(.2,.96);axs[0].set_ylim(0,500);axs[0].legend(loc='upper left',fontsize=7.9)
 axs[0].text(.04,.59,r'$A=\\frac{c\\Delta^2X}{2(1-X)}$'.replace('\\\\','\\'),transform=axs[0].transAxes,fontsize=11,color='#303b45')
 colors=['#176b9a','#b86b19','#42816e','#735295'];markers=['o','s','D','^']
 for x,col,marker in zip([.5,.7,.85,.9],colors,markers):
  q=sorted([v for v in VER['packet_refinement'] if v['X']==x],key=lambda d:d['packet_mass'])
  axs[1].loglog([v['packet_mass'] for v in q],[abs(v['error_vehicle_s'])/v['fluid_area_vehicle_s']*100 for v in q],marker=marker,color=col,label=f'$X={x:.2f}$',linewidth=1.3)
 axs[1].set_xlabel('Numerical packet mass (vehicle-equivalents)');axs[1].set_ylabel('Absolute relative area error (%)');axs[1].set_title('(b) Packet refinement',loc='left',pad=8);axs[1].set_xlim(.004,.32);axs[1].set_ylim(.15,20);axs[1].set_xticks([.005,.025,.1,.25]);axs[1].set_xticklabels(['0.005','0.025','0.10','0.25']);axs[1].set_yticks([.2,1,5,20]);axs[1].set_yticklabels(['0.2','1','5','20']);axs[1].legend(loc='upper left',fontsize=7.7,ncol=1)
 for ax in axs:clean(ax)
 fig.suptitle('Independent analytic and numerical verification',y=.985,fontsize=11,fontweight='semibold')
 fig.text(.5,.91,'Initially empty queue; $c=0.5$ vehicle/s; 10 s service blackout',ha='center',fontsize=9,color='#4d5660')
 fig.text(.5,.035,'Constant arrivals and restored constant service; this is not a network cost law.',ha='center',fontsize=8.2,color='#4d5660')
 export(fig,'analytic_pulse')

def notes():
 txt=['Static figure source and numeric readouts','25 October 2026','',
 'All outcomes below are from completed corrected_summary.json. Original values are reconstructed only as corrected mean minus its reported matched mechanical-change mean. Confidence intervals are reported paired scenario-level percentile bootstrap intervals (10000 resamples, n=200 per cell); no unavailable absolute-mean confidence interval was fabricated. The mechanical comparison retains original tuning and is a sensitivity analysis, not a newly preregistered confirmatory experiment.','',
 'Figure network. Actual v7 synthetic geometry: 16 signalized junctions, 8 boundary nodes, 59 directed links. Arrows indicate link direction. Hospital destination BE1 is a model boundary. Road coordinates and layout are synthetic, not a real urban map.','',
 'Figure meso_results. Mechanically corrected mesoscopic outcomes without driver yielding (rho=0), across six nominal critical-load targets. Panel a shows mean ambulance travel for M0, M1, M2 and MR. Panel b shows signed extra restricted-horizon ordinary residence versus the corresponding corrected M0, with 95% paired bootstrap intervals. Intervals containing zero do not establish equivalence or no cost. The mesoscopic labels M0, M1, M2 and MR correspond to executable data keys P0, P1, P2 and P4, respectively; these are distinct from the microscopic controller labels.','']
 for p in ['P0','P1','P2','P4']:
  txt.append(LABELS[p]+' (executable key '+p+')')
  for d in cells(p):
   s=d['delta_residence_vh'];a=d['ambulance_difference'];txt.append(f"X={d['X']:.2f}; ambulance mean={d['ambulance_mean']:.6f} s; paired ambulance effect={a['mean']:.6f} [{a['ci_low']:.6f},{a['ci_high']:.6f}] s; ordinary extra residence={s['mean']:.9f} [{s['ci_low']:.9f},{s['ci_high']:.9f}] vehicle-h")
 txt+=['','Figure mechanical_change. Paired sensitivity to replacing ambulance source insertion, discharge and storage exceptions with shared-capacity, strict-storage mechanics. Panel a reports corrected minus original ambulance travel for M0 and M2. Panel b reports the difference of ordinary residence effects, (corrected M2-corrected M0)-(original M2-original M0), not the raw change of the M2 trajectory alone. Both panels use rho=0 and 95% paired bootstrap intervals.','']
 for p in ['P0','P2']:
  for d in changes(p):
   c=next(v for v in cells(p) if v['X']==d['X']);a=d['ambulance_model_change'];b=d['paired_effect_model_change'];origT=c['ambulance_mean']-a['mean'];origcost=c['delta_residence_vh']['mean']-b['mean']
   txt.append(f"{LABELS[p].split()[0]} (executable key {p}), X={d['X']:.2f}; original ambulance mean={origT:.6f} s; corrected ambulance mean={c['ambulance_mean']:.6f} s; change={a['mean']:.6f} [{a['ci_low']:.6f},{a['ci_high']:.6f}] s; original paired ordinary effect={origcost:.9f}; corrected effect={c['delta_residence_vh']['mean']:.9f}; paired-effect change={b['mean']:.9f} [{b['ci_low']:.9f},{b['ci_high']:.9f}] vehicle-h")
 txt+=['','Figure analytic_pulse. Independent verification of a single initially empty queue with constant arrival lambda<c, complete service blackout Delta, and constant restored service c. The exact excess residence is c*Delta^2*X/[2*(1-X)], X=lambda/c. Panel a contrasts that analytic curve with independently integrated numerical points; panel b shows actual deterministic fine-packet convergence. Packet mass is a numerical discretization in vehicle-equivalents, not fractional real vehicles. These results establish this toy calculation only; they do not validate a universal urban traffic law.','']
 for d in VER['fluid_pulse']:txt.append(f"Fluid X={d['X']:.2f}; exact area={d['area_vehicle_s']:.12f}; ODE area={d['numerical_area_vehicle_s']:.12f}; discrepancy={d['error_vehicle_s']:.4g} vehicle-s")
 for d in VER['packet_refinement']:txt.append(f"Packet X={d['X']:.2f}; mass={d['packet_mass']}; absolute relative area error={abs(d['error_vehicle_s'])/d['fluid_area_vehicle_s']*100:.9f}%")
 (HERE/'base_figures_notes.txt').write_text('\n'.join(txt)+'\n')

if __name__=='__main__':
 network();meso_results();mechanical_change();analytic_pulse();notes()
 print(json.dumps({x.name:x.stat().st_size for x in OUT.glob('*.png') if x.stem in ['network','meso_results','mechanical_change','analytic_pulse']},indent=2))
