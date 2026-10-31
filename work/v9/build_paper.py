from pathlib import Path
import re,json,math
from copy import deepcopy
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
ROOT=Path(__file__).resolve().parents[2];W=Path(__file__).resolve().parent;OUT=ROOT/'outputs'
doc=Document();sec=doc.sections[0]
sec.page_width=Inches(8.5);sec.page_height=Inches(11);sec.left_margin=sec.right_margin=Inches(.8);sec.top_margin=sec.bottom_margin=Inches(.7);sec.footer_distance=Inches(.3)
for nm in ['Normal','Body Text','Title','Subtitle','Heading 1','Heading 2','Heading 3']:
 st=doc.styles[nm];st.font.name='Calibri';st.font.color.rgb=RGBColor(0,0,0);st.paragraph_format.widow_control=True
normal=doc.styles['Normal'];normal.font.size=Pt(11);normal.paragraph_format.space_after=Pt(6);normal.paragraph_format.line_spacing=1.04
for nm,size in [('Title',23),('Subtitle',12),('Heading 1',16),('Heading 2',12),('Heading 3',11)]:
 st=doc.styles[nm];st.font.size=Pt(size);st.font.bold=nm!='Subtitle';st.paragraph_format.space_before=Pt(12 if 'Heading' in nm else 0);st.paragraph_format.space_after=Pt(6);st.paragraph_format.keep_with_next=True
for st in doc.styles:
 if st.type==1 and st.element.pPr is not None:
  for e in list(st.element.pPr.findall(qn('w:pBdr'))):st.element.pPr.remove(e)
fp=sec.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.RIGHT
fp.add_run('AmbuGo  |  First empirical draft  |  ').font.size=Pt(8)
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');fp._p.append(fld)
plain=[];eqcount=0;hcount=0;unknown=set();contents=[]
exec((W/'document_helpers.py').read_text(),globals())
INLINE_VAR=re.compile(r'(?<![A-Za-z0-9/])(?:[A-Za-z]|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|rho|sigma|tau|omega|kappa|Delta)_(?:\([A-Za-z0-9<>=,+ -]+\)|[A-Za-z0-9]+|\*)(?:\^(?:\([A-Za-z0-9+ -]+\)|[A-Za-z0-9]+|[+-]))?')
SYMS.update({'ell':'ℓ','mapsto':'↦','equiv':'≡','leqslant':'≤','geqslant':'≥','colon':':','cdots':'⋯'})
_oldclean=clean
def clean(t):
 t=_oldclean(t)
 t=re.sub(r'(\d), (?=\d{3}\b)',r'\1,',t)
 t=re.sub(r'\[R\d+(?:,\s*R\d+)*\]',lambda m:re.sub(r'R(?=\d)','',m[0]),t)
 # The two independent microscopic and mesoscopic naming families are kept distinct.
 for old,new in [('P0','S0'),('P1','SEQ'),('P2','JFAST'),('P3','JSEL')]:
  if MODE=='micro':t=re.sub(r'\b'+old+r'\b',new,t)
 for a,b in {'n̂_e':r'$\widehat n_e$','q̂_e':r'$\widehat q_e$','d̂_e':r'$\widehat d_e$','Ĉ_e':r'$\widehat C_e$','T̂_min':r'$\widehat T_{\min}$','λ̄_e':r'$\bar\lambda_e$','p̄':r'$\bar p$'}.items():t=t.replace(a,b)
 t=re.sub(r'([A-Za-zλ])([̂̄])_([A-Za-z]+)',lambda m:'$'+('\\widehat ' if m[2]=='̂' else '\\bar ')+('\\lambda' if m[1]=='λ' else m[1])+'_{'+m[3]+'}$',t)
 t=t.replace('J_H^pi',r'$J_H^{\pi}$')
 t=re.sub(r'\b([A-Za-z])_([A-Za-z0-9]+)\^pi\b',lambda m:'$'+m[1]+'_{'+m[2]+'}^{\\pi}$',t)
 t=t.replace('T̄^π',r'$\bar T^{\pi}$').replace('θ_T',r'$\theta_T$').replace('θ_A',r'$\theta_A$')
 t=t.replace('H_ind','D_H^+')
 t=t.replace('identity d=[d]_+-[-d]_+',r'identity $d=[d]_+-[-d]_+$').replace('Apply x=[x]_+-[-x]_+',r'Apply $x=[x]_+-[-x]_+$').replace('Delta J_H',r'$\Delta J_H$')
 return t
MODE='plain'
def section(text,title):
 m=re.search(r'^# '+re.escape(title)+r'\n(.*?)(?=^# |\Z)',text,re.M|re.S)
 if not m:raise KeyError(title)
 return m[1].strip()
def body(text):parse(text)
def figure(filename,caption,width=6.65):
 a=doc.add_paragraph();a.alignment=WD_ALIGN_PARAGRAPH.CENTER;a.paragraph_format.keep_with_next=True
 a.add_run().add_picture(str(W/'figures'/filename),width=Inches(width))
 cap=p(caption);cap.paragraph_format.space_after=Pt(9)
 for r in cap.runs:r.font.size=Pt(9.5)
 # Editable-image alt text.
 for el in a._p.iter(qn('wp:docPr')):el.set('descr',caption)
def equation(t):
 global eqcount
 if '\\qquad' in t and len(t)>145:
  for part in t.split('\\qquad'):equation(part.strip().rstrip(','))
  return
 eqcount+=1;plain.append('Equation '+str(eqcount)+' '+t)
 a=doc.add_paragraph();a.alignment=WD_ALIGN_PARAGRAPH.CENTER;a.paragraph_format.space_before=Pt(4);a.paragraph_format.space_after=Pt(6);a.paragraph_format.keep_with_next=False
 math_run(a,t.strip());a.add_run('   ('+str(eqcount)+')').font.size=Pt(9)
def ciform(v,d=2):return f"{v['mean']:.{d}f} [{v['lo']:.{d}f}, {v['hi']:.{d}f}]"
core=(W/'paper_core.txt').read_text();analysis_file=W/'sumo_analysis.json';analysis=json.loads(analysis_file.read_text()) if analysis_file.exists() else None
p('AmbuGo joint ambulance routing and selective signal priority','Title')
p('A reproducible study of synthetic urban traffic','Subtitle')
p('First empirical manuscript draft  •  25 October 2026')
h('Abstract',2)
if (W/'paper_abstract.txt').exists():body((W/'paper_abstract.txt').read_text())
else:p('Results section under assembly. This layout proof is not a completed manuscript.')
p('Keywords: emergency vehicle routing; traffic signal priority; congestion recovery; microscopic simulation; finite horizon accounting; paired experiments.')
h('Introduction');body(section(core,'Introduction'))
body((W/'paper_related.txt').read_text())
h('Decision problem and mathematical foundations')
table(['Symbol','Units','Meaning'],[['T','seconds','Ambulance travel from desired dispatch'],['J','vehicle-seconds','Restricted ordinary residence over the observation window'],['A','vehicle-seconds','Positive spatial occupancy exposure relative to S0'],['D+','vehicle-seconds','Positive individual residence change relative to S0'],['X','dimensionless','Nominal design loading index; not measured saturation'],['B','vehicle-seconds','Admission threshold for the local burden score'],['ε','seconds','Finite-candidate predicted-time tolerance'],['γ','seconds','Observed free-flow progress deficit that triggers escalation'],['W and H','seconds','Initialization cutoff and common experiment endpoint']],[.75,1.3,4.85])
theory=(W/'paper_theory.txt').read_text();theory=theory[theory.index('## Causal control and the joint objective'):]
theory=re.sub(r'(?<![A-Za-z])a_i', 'd_i', theory)
theory=re.sub(r'(?<![A-Za-z])t_0', 'W', theory)
theory=theory.replace('Proposition 3.', 'Proposition 4.')
causal=theory[:theory.index('## Finite horizon residence')]
body(causal)
body((W/'paper_objective.txt').read_text())
body(theory[theory.index('## Finite horizon residence'):theory.index('## A conditional theory')])
body((W/'paper_theory_individual.txt').read_text().replace('a_i','d_i').replace('Proposition.','Proposition 3.'))
body(theory[theory.index('## A conditional theory'):])
figure('analytic_pulse.png','Figure 1. Exact isolated-queue calculation for a service blackout. This is an analytical illustration under constant arrival and service assumptions, not a fitted network law.',5.7)
h('Mesoscopic model and mechanical reanalysis');body(section(core,'Mesoscopic experiment and mechanical reanalysis'))
figure('network.png','Figure 2. The synthetic district shared by the two modeling layers. Geometry and traffic parameters are generated research inputs, not a reconstructed or calibrated city.',5.15)
MODE='micro';body((W/'sumo_methods.txt').read_text().split('## Development selection and frozen')[0])
if (W/'figures/method.png').exists():figure('method.png','Figure 3. Causal route and priority decisions, physical execution and separate paired evaluation. The baseline evaluation ledger supplies no control information.',6.7)
MODE='plain';h('Experimental design and statistical analysis');body(section(core,'Experimental design and statistical analysis'))
p('The main microscopic grid contains 48 scenario seeds, three nominal loads (0.60, 0.80 and 0.95), three mission doses (1, 4 and 10 in the one-hour mission window) and four policies, for 1,728 runs. Secondary experiments use seeds 0–11, nominal loads 0.60 and 0.95 and four missions: 72 runs at a 0.25 s physical step; 48 runs for the no-progress-switch ablation and its baseline; 72 runs with a longest-count base controller; and 72 runs with noiseless counts sampled each second, zero receipt delay and retained Markov dropout. The latter retains the same count-to-queue proxy; missing observations remain held, and faster sampling shortens dropout duration in seconds. It is not a true-queue or future-information oracle. Secondary treatment contrasts are compared with the matching primary episodes. They are sensitivity analyses of the chosen policy, not an additional parameter-selection round.')
table(['Layer','Independent seeds per cell','Conditions','Completed design'],[['Corrected mesoscopic','200','6 loads × 2 yielding settings × 6 policies','14,400 runs'],['Initial development','6','2 loads × 14 configurations','168 runs'],['Progress development','6','2 loads × 11 configurations','132 runs'],['Main microscopic','48','3 loads × 3 mission doses × 4 policies','1,728 runs'],['Secondary microscopic','12','2 loads × dose 4; four checks','264 runs']],[1.5,1.25,2.55,1.6])
body((W/'paper_meso_results.txt').read_text())
figure('meso_results.png','Figure 4. Corrected mesoscopic ambulance means and signed ordinary residence differences relative to M0, without abstract yielding. Error bars show 95 percent paired bootstrap intervals for ordinary effects; 200 seeds per cell.',6.7)
figure('mechanical_change.png','Figure 5. Effect of correcting ambulance admission, storage and service. Ordinary cost changes are differences of baseline-paired effects, (corrected M2 − corrected M0) − (original M2 − original M0), not raw changes in M2 residence.',6.6)
h('Microscopic results')
if (W/'paper_sumo_results.txt').exists():body((W/'paper_sumo_results.txt').read_text())
else:p('Held-out results are pending in this layout proof.')
if analysis:body((W/'paper_tail_results.txt').read_text())
if analysis:
 table(['Controller','Mean ambulance s','Positive spatial vh','Individual increase vh','Signed residence vh'],[[pname,f"{analysis['aggregate'][pkey]['time_s']['mean']:.2f}",f"{analysis['aggregate'][pkey]['A_vh']['mean']:.2f}",f"{analysis['aggregate'][pkey]['Dplus_vh']['mean']:.2f}",f"{analysis['aggregate'][pkey]['deltaJ_vh']['mean']:.2f}"] for pkey,pname in [('P0','S0'),('P1','SEQ'),('P2','JFAST'),('P3','JSEL')]],[1.0,1.4,1.5,1.5,1.5])
 p('Balanced microscopic means, giving equal weight to each of the nine load–dose conditions. Aftereffect measures use S0 as the paired reference. Vehicle-hours aggregate across ordinary vehicles, whereas ambulance duration is an episode mean restricted at the common horizon.')
 for file,caption in [('sumo_time.png','Figure 6. Mean restricted ambulance duration by controller, nominal loading and mission dose. Error bars show seed-level 95 percent bootstrap intervals.'),('sumo_effects.png','Figure 7. Paired JSEL minus JFAST effects across the main condition grid. The 20 s time tolerance is an experimental target, not a clinical standard. Aftereffects use the same S0 baseline.'),('sumo_burden.png','Figure 8. Signed residence, positive individual residence and positive spatial exposure are different outcomes. Each is computed on a fixed paired cohort and horizon.'),('sumo_sensitivity.png','Figure 9. Sensitivity of the selected policy and its treatment contrasts. Intervals resample the 12 shared scenario seeds within each load.')]:
  if (W/'figures'/file).exists():figure(file,caption,6.7)
h('Discussion');body(section(core,'Discussion'))
if (W/'paper_conclusion_results.txt').exists():body((W/'paper_conclusion_results.txt').read_text())
h('Limitations and field calibration');body(section(core,'Limitations and the field calibration stage'))
h('Conclusions')
if (W/'paper_conclusion.txt').exists():body((W/'paper_conclusion.txt').read_text())
else:p('Conclusion pending completed held-out analysis.')
h('References')
for r in json.loads((W/'references.json').read_text()):
 a=p(f"[{r['id'][1:]}] {r['authors']} ({r['year']}). {r['title']}. {r['publication']}.")
 hyperlink(a,r['url'],'Source')
doc.add_page_break();h('Supplementary methods');append=(W/'paper_appendix.txt').read_text();body(append[append.index('## Identification'):])
h('Complete controller procedure',2)
MODE='micro';algo=(W/'paper_algo.txt').read_text();chunks=algo.split('\n\n')
for b in chunks[1:]:
 if b.startswith(('At integer','Procedure SCORE')):
  for line in b.splitlines():
   indent=len(line)-len(line.lstrip());a=doc.add_paragraph();a.paragraph_format.left_indent=Inches(min(.7,indent*.018));a.paragraph_format.space_after=Pt(0);a.paragraph_format.line_spacing=1
   line=_oldclean(line.strip())
   for old,new in [('P0','S0'),('P1','SEQ'),('P2','JFAST'),('P3','JSEL')]:line=re.sub(r'\b'+old+r'\b',new,line)
   a.add_run(line).font.name='Consolas'
   for r in a.runs:r.font.size=Pt(9)
 else:body(b)
MODE='plain'
h('Input and control parameter register',2)
table(['Parameter','Value','Interpretation'],[['District','16 signals; 8 boundaries; 59 directed links','Shared synthetic geometry'],['Regular lane width','3.2 m','Microscopic compiler setting'],['Road speed','8.33 or 11.11 m/s','Declared free-flow limit'],['Nominal load','0.60; 0.80; 0.95','Ex ante PCU planning index'],['Mission dose','1; 4; 10 per scheduled hour','Jittered spacing; overlaps allowed'],['Physical and decision steps','0.5 s and 1 s','Physical sensitivity at 0.25 s'],['Initialization and horizon','1,800 s and 7,200 s','Demand continues to horizon'],['Mission window','1,800–5,400 s','All trips retained through horizon'],['Minimum green; clearances','8 s; 3 s amber; 2 s all-red','Protected single approach'],['Pedestrian opportunity','25 s all-red reservation','No physical pedestrian simulation'],['Service-age trigger','150 s','Service opportunity, not traveler deadline'],['Sensor period and delay','5 s and 2 s','Last observation held during dropout'],['Dropout transition','0.015 missing; 0.25 recovery','Per sampling opportunity'],['Route continuations','At most 4; free-flow factor 1.5','Incumbent retained if legal'],['Selected action library','None or trigger 30 s / hold 60 s','Finite joint route/action domain'],['Selected burden cap','10,000 vehicle-seconds','Local score threshold, not city cost bound'],['Selected predicted-time tolerance','0 s','Smallest computed ETA at the snapshot'],['Progress switch threshold','20 s','Executed free-flow progress proxy'],['Route hysteresis','10 s','Selective mode retains global forecast cap'],['Downstream headroom','Observed count <85% storage','Declared aggregate receiving proxy'],['Minimum predicted benefit','5 s','Admission gate in selective mode']],[1.65,2.15,3.1])
if analysis:
 h('Full microscopic condition results',2)
 p('All entries are means; cells contain 48 episode seeds. The accompanying CSV contains confidence intervals and every retained scalar outcome. A and D+ are relative to the same S0 episode; ΔJ is signed restricted residence. No table value is a field observation.')
 rows=[]
 names={'P0':'S0','P1':'SEQ','P2':'JFAST','P3':'JSEL'}
 for z in analysis['cells']:
  m=z['metrics'];rows.append([f"{z['load']:.2f}",str(z['missions']),names[z['policy']],f"{m['time_s']['mean']:.2f}",f"{m['A_vh']['mean']:.2f}",f"{m['Dplus_vh']['mean']:.2f}",f"{m['deltaJ_vh']['mean']:.2f}"])
 table(['Load','Missions','Policy','Time s','A vh','D+ vh','ΔJ vh'],rows,[.65,.8,.85,1.05,1.15,1.15,1.25])
 h('Paired selective versus aggressive contrasts',2)
 rows=[]
 for z in analysis['contrasts']:
  if z['comparison']!='P3-P2':continue
  m=z['metrics'];rows.append([f"{z['load']:.2f} / {z['missions']}",ciform(m['time_s'],1),ciform(m['A_vh'],1),ciform(m['Dplus_vh'],1),ciform(m['deltaJ_vh'],1)])
 table(['Load / dose','Time s [95% CI]','A vh [95% CI]','D+ vh [95% CI]','ΔJ vh [95% CI]'],rows,[.8,1.5,1.5,1.5,1.6])
 h('Verification and provenance register',2)
 for file in ['v8_corrected/mechanical_provenance.json','sumo_main/protocol.json']:
  z=json.loads((W/file).read_text());p(file+': '+str(z.get('model_sha256',z.get('corrected_sim_sha256','See machine-readable file'))))
 p('Microscopic model SHA256: 471a22911a2de9773fcd839872b3ba1ec5e00412c0ecc79142503e72f41cecf2. The archive manifest records the checksum of each delivered source and result file. Raw source hashes are identifiers, not validation evidence.')
doc.core_properties.title='AmbuGo joint ambulance routing and selective signal priority';doc.core_properties.author='';doc.core_properties.subject='Synthetic empirical research manuscript';doc.core_properties.keywords='ambulance routing, traffic priority, SUMO, congestion aftereffects'
OUT.mkdir(exist_ok=True);target=OUT/'AmbuGo_First_Empirical_Draft_v9.docx';doc.save(target)
(W/'manuscript_text.txt').write_text('\n\n'.join(plain));(W/'document_build_diagnostics.json').write_text(json.dumps(dict(equations=eqcount,unknown_math_commands=sorted(unknown),headings=contents,paragraphs=len(doc.paragraphs),tables=len(doc.tables)),indent=2))
print(target);print('equations',eqcount,'unknown',sorted(unknown),'words',len(' '.join(plain).split()))
