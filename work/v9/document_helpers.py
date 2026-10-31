def mr(t,plain=False):
    r=OxmlElement('m:r')
    if plain:
        pr=OxmlElement('m:rPr');sty=OxmlElement('m:sty');sty.set(qn('m:val'),'p');pr.append(sty);r.append(pr)
    x=OxmlElement('m:t');x.text=t;x.set(qn('xml:space'),'preserve');r.append(x);return r
def elem(tag,vals):
    x=OxmlElement('m:'+tag)
    for v in vals:x.append(v)
    return x
SYMS={'alpha':'α','beta':'β','gamma':'γ','delta':'δ','epsilon':'ε','varepsilon':'ε','theta':'θ','lambda':'λ','Lambda':'Λ','mu':'μ','pi':'π','rho':'ρ','sigma':'σ','tau':'τ','omega':'ω','kappa':'κ','Delta':'Δ','Omega':'Ω','Pi':'Π','Phi':'Φ','Sigma':'Σ','ell':'ℓ','in':'∈','notin':'∉','subseteq':'⊆','leq':'≤','le':'≤','geq':'≥','ge':'≥','ne':'≠','neq':'≠','infty':'∞','forall':'∀','exists':'∃','to':'→','leftarrow':'←','Rightarrow':'⇒','times':'×','cdot':'·','pm':'±','mid':'|','vert':'|','lvert':'|','rvert':'|','lVert':'‖','rVert':'‖','sum':'∑','int':'∫','prod':'∏','cup':'∪','cap':'∩','emptyset':'∅','partial':'∂','nabla':'∇','Pr':'Pr','log':'log','exp':'exp','min':'min','max':'max','inf':'inf','sup':'sup','argmin':'arg min','sqrt':'√'}
class MathParser:
    def __init__(self,s):self.s=s;self.i=0
    def group(self):
        while self.i<len(self.s) and self.s[self.i].isspace():self.i+=1
        if self.i<len(self.s) and self.s[self.i]=='{':
            self.i+=1;return self.parse('}')
        return self.atom()
    def rawgroup(self):
        while self.i<len(self.s) and self.s[self.i].isspace():self.i+=1
        if self.i>=len(self.s) or self.s[self.i]!='{':return ''
        self.i+=1;start=self.i;depth=1
        while self.i<len(self.s):
            ch=self.s[self.i];self.i+=1
            if ch=='{':depth+=1
            if ch=='}':
                depth-=1
                if depth==0:return self.s[start:self.i-1]
        return self.s[start:]
    def atom(self):
        if self.i>=len(self.s):return []
        ch=self.s[self.i];self.i+=1
        if ch=='{':return self.parse('}')
        if ch!='\\':return [mr(' ' if ch=='~' else ch)]
        if self.i<len(self.s) and not self.s[self.i].isalpha():
            c=self.s[self.i];self.i+=1;return [mr(' ' if c in ',;: !' else c)]
        m=re.match(r'[A-Za-z]+',self.s[self.i:]);cmd=m.group() if m else '';self.i+=len(cmd)
        if cmd in ['left','right','displaystyle','limits','nolimits']:return []
        if cmd in ['quad','qquad']:return [mr('   ' if cmd=='quad' else '      ')]
        if cmd in ['frac','dfrac','tfrac']:
            a=self.group();b=self.group();return [elem('f',[elem('num',a),elem('den',b)])]
        if cmd=='sqrt':
            a=self.group();rad=OxmlElement('m:rad');pr=OxmlElement('m:radPr');hide=OxmlElement('m:degHide');hide.set(qn('m:val'),'1');pr.append(hide);rad.append(pr);rad.append(OxmlElement('m:deg'));rad.append(elem('e',a));return [rad]
        if cmd in ['mathrm','text','operatorname','mathbf','mathsf','mathtt']:
            return [mr(self.rawgroup().replace('\\ ',' '),True)]
        if cmd in ['mathcal','mathbb','mathop']:
            return self.group()
        if cmd in ['widehat','hat','bar','overline','tilde']:
            a=self.group();acc=OxmlElement('m:acc');pr=OxmlElement('m:accPr');chr=OxmlElement('m:chr');chr.set(qn('m:val'),{'widehat':'̂','hat':'̂','bar':'̅','overline':'̅','tilde':'̃'}[cmd]);pr.append(chr);acc.append(pr);acc.append(elem('e',a));return [acc]
        if cmd in SYMS:return [mr(SYMS[cmd],cmd in ['Pr','log','exp','min','max','inf','sup','argmin'])]
        unknown.add(cmd);return [mr(cmd)]
    def parse(self,stop=None):
        out=[]
        while self.i<len(self.s):
            if stop and self.s[self.i]==stop:self.i+=1;break
            if self.s[self.i] in '\n\r':self.i+=1;continue
            a=self.atom()
            if not a:continue
            subs=sups=None
            while self.i<len(self.s) and self.s[self.i] in '_^':
                k=self.s[self.i];self.i+=1;b=self.group()
                if k=='_':subs=b
                else:sups=b
            if subs is not None or sups is not None:
                if subs is not None and sups is not None:a=[elem('sSubSup',[elem('e',a),elem('sub',subs),elem('sup',sups)])]
                elif subs is not None:a=[elem('sSub',[elem('e',a),elem('sub',subs)])]
                else:a=[elem('sSup',[elem('e',a),elem('sup',sups)])]
            out.extend(a)
        return out
def math_run(para,s):
    om=OxmlElement('m:oMath')
    for x in MathParser(s).parse():om.append(x)
    para._p.append(om)
def hyperlink(para,url,label='Primary source'):
    rid=para.part.relate_to(url,RT.HYPERLINK,is_external=True);h=OxmlElement('w:hyperlink');h.set(qn('r:id'),rid)
    r=OxmlElement('w:r');pr=OxmlElement('w:rPr');color=OxmlElement('w:color');color.set(qn('w:val'),'1D4F70');pr.append(color);r.append(pr)
    t=OxmlElement('w:t');t.text=label;r.append(t);h.append(r);para._p.append(h)
def clean(t):
    t=t.replace('–','-').replace('—',' - ').replace('\u00a0',' ')
    t=re.sub(r'(?<=[,;])(?=[A-Za-z0-9])',' ',t)
    for mon in ['October','July']:
        t=re.sub(r'(\d)('+mon+r')',r'\1 \2',t);t=re.sub(r'('+mon+r')(\d)',r'\1 \2',t)
    t=t.replace('lastedited','last edited').replace('inspected24','inspected 24')
    t=re.sub(r'\bDOI(?=\d)','DOI ',t)
    t=re.sub(r'\b(Science|D|Paper)(\d)',r'\1 \2',t)
    t=re.sub(r'([0-9])(?=(seconds|percent|vehicles|words)\b)',r'\1 ',t)
    return t
INLINE_VAR=re.compile(r'(?<![A-Za-z0-9/])(?:[A-Za-z]|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|rho|sigma|tau|omega|kappa|Delta)_(?:\([A-Za-z0-9<>=,+ -]+\)|[A-Za-z0-9]+|\*)(?:\^(?:\([A-Za-z0-9+ -]+\)|[A-Za-z0-9]+))?')
def inline_text(a,t):
    start=0
    for m in INLINE_VAR.finditer(t):
        if m.start()>start:a.add_run(t[start:m.start()])
        var=m.group()
        var=re.sub(r'^(alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|rho|sigma|tau|omega|kappa|Delta)',lambda z:'\\'+z[1],var)
        var=re.sub(r'_\(([^)]+)\)',r'_{\1}',var)
        var=re.sub(r'_([A-Za-z0-9]+)',r'_{\1}',var)
        var=re.sub(r'\^\(([^)]+)\)',r'^{\1}',var)
        var=re.sub(r'\^([A-Za-z0-9]+)',r'^{\1}',var)
        math_run(a,var);start=m.end()
    if start<len(t):a.add_run(t[start:])
def p(t,style=None):
    t=clean(t);plain.append(t);a=doc.add_paragraph(style=style)
    pieces=re.split(r'(https?://[^\s]+|\*\*.*?\*\*|\$[^$]+\$)',t)
    for x in pieces:
        if x.startswith('http'):
            url=x.rstrip('.,;');hyperlink(a,url)
        elif x.startswith('**') and x.endswith('**'):a.add_run(x[2:-2]).bold=True
        elif x.startswith('$') and x.endswith('$'):math_run(a,x[1:-1])
        else:inline_text(a,x)
    if t.startswith(('Proposition ','Theorem ','Lemma ','Algorithm ')):
        # Emphasize the proposition label without making the whole argument bold.
        if a.runs:a.runs[0].bold=False
    return a
def h(t,level=1):
    global hcount
    t=clean(t);t=re.sub(r'[^A-Za-z0-9 ]',' ',t);t=re.sub(r' +',' ',t).strip()
    if level==1:hcount+=1;t=str(hcount)+' '+t
    contents.append((level,t));plain.append(t);a=doc.add_heading(t,level);return a
def equation(t):
    global eqcount
    if '\\qquad' in t and len(t)>150:
        for part in t.split('\\qquad'):equation(part.strip().rstrip(','))
        return
    eqcount+=1;plain.append('Equation '+str(eqcount)+' '+t)
    a=doc.add_paragraph();a.alignment=WD_ALIGN_PARAGRAPH.CENTER
    a.paragraph_format.space_before=Pt(5);a.paragraph_format.space_after=Pt(7);a.paragraph_format.keep_with_next=True
    math_run(a,t.strip());a.add_run('   ('+str(eqcount)+')').font.size=Pt(9)
def fig(file,caption,w=6.85):
    doc.add_picture(str(W/file),width=Inches(w))
    doc.paragraphs[-1].paragraph_format.keep_with_next=True
    if file=='recovery_bound.png':doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER
    p(caption)
def table(headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers));t.autofit=False;t.alignment=WD_TABLE_ALIGNMENT.CENTER
    for i,w in enumerate(widths):t.columns[i].width=Inches(w)
    for i,v in enumerate(headers):t.rows[0].cells[i].text=v
    for row in rows:
        cells=t.add_row().cells
        for i,v in enumerate(row):cells[i].text=str(v)
    for k,row in enumerate(t.rows):
        pr=row._tr.get_or_add_trPr();pr.append(OxmlElement('w:cantSplit'))
        if k==0:pr.append(OxmlElement('w:tblHeader'))
        for i,c in enumerate(row.cells):
            c.width=Inches(widths[i]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cp=c._tc.get_or_add_tcPr();m=OxmlElement('w:tcMar')
            for side in ['top','bottom','left','right']:
                z=OxmlElement('w:'+side);z.set(qn('w:w'),'85');z.set(qn('w:type'),'dxa');m.append(z)
            cp.append(m);b=OxmlElement('w:tcBorders')
            for side in ['top','bottom','left','right']:
                z=OxmlElement('w:'+side);z.set(qn('w:val'),'single');z.set(qn('w:sz'),'4');z.set(qn('w:color'),'D9D9D9');b.append(z)
            cp.append(b);s=OxmlElement('w:shd');s.set(qn('w:fill'),'DFE5EB' if k==0 else 'FFFFFF');cp.append(s)
            for a in c.paragraphs:
                a.paragraph_format.space_after=Pt(2);a.paragraph_format.line_spacing=1
                if k==0:a.paragraph_format.keep_with_next=True
                for r in a.runs:r.font.size=Pt(10);r.bold=k==0
    p('')
    return t
def parse(txt,mode=None):
    blocks=re.split(r'\n\s*\n',txt.strip())
    for b in blocks:
        b=b.strip()
        if not b:continue
        if b.startswith('$$') and b.endswith('$$'):equation(b[2:-2]);continue
        if b.startswith('#'):
            m=re.match(r'^(#+)\s+(.*)',b,re.S);level=len(m[1]);title=m[2]
            if mode=='front':
                if title.startswith('AmbuGo joint'):p(title,'Title')
                elif title.startswith('A methods'):p(title,'Subtitle')
                else:h(title,2)
            elif mode=='algorithm':h(title,1 if level==1 else 2)
            else:h(title,min(level,3))
            continue
        if mode=='urban':
            m=re.match(r'^\d+\s+([^\n]+)$',b)
            if m:h(m[1],2);continue
        if b.startswith('```'):
            for ln in b.splitlines()[1:-1]:
                a=p(ln)
                for r in a.runs:r.font.name='Consolas';r.font.size=Pt(9)
            continue
        p(re.sub(r'\n(?![-*] )',' ',b))

