"""Shared drawing primitives and minimal replay initialization for the map film."""
from pathlib import Path
import os,json
import numpy as np
from PIL import ImageFont
import replay as src
ROOT=Path(__file__).resolve().parents[1]
BLUE=(27,104,220);GREY=(107,116,128);RED=(216,38,43);GREEN=(18,148,73);AMBER=(238,159,21);INK=(35,43,52)
fonts={}

def font(n,b=False):
    if (n,b) not in fonts:
        override=os.environ.get('AMBUGO_FONT_BOLD' if b else 'AMBUGO_FONT_REGULAR')
        if override:
            path=Path(override).expanduser()
            if not path.is_file():raise FileNotFoundError(f'Font override does not exist: {path}')
        else:
            from matplotlib import font_manager
            prop=font_manager.FontProperties(family='Arial',weight='bold' if b else 'normal')
            try:path=font_manager.findfont(prop,fallback_to_default=False)
            except ValueError:
                path=font_manager.findfont(font_manager.FontProperties(family='DejaVu Sans',weight='bold' if b else 'normal'))
        fonts[n,b]=ImageFont.truetype(str(path),n)
    return fonts[n,b]

def txt(d,p,s,n=25,c=INK,b=False,anchor=None):d.text(tuple(p),s,font=font(n,b),fill=c,anchor=anchor)

def circle(d,p,r,fill,outline=None,w=1):d.ellipse((p[0]-r,p[1]-r,p[0]+r,p[1]+r),fill=fill,outline=outline,width=w)

def check(d,p,color=GREEN,size=13):
 x,y=p;d.line([(x-size,y),(x-3,y+size*.65),(x+size,y-size)],fill=color,width=5,joint='curve')

def badge(d,p,s,color=BLUE):
 x,y=p;bb=d.textbbox((0,0),s,font=font(27,True));tw=bb[2];d.rounded_rectangle((x-tw/2-15,y-23,x+tw/2+15,y+23),12,fill='white',outline=color,width=2);txt(d,(x,y),s,27,color,True,'mm')

class Movie:
    def __init__(self):
        self.r=src.Replay('P3')
        self.net=json.loads((ROOT/'data/network_geo.json').read_text())
        self.edges={e['id']:src.llxy(*np.array(e['lonlat']).T) for e in self.net['edges']}
        self.signals={s['id']:s for s in self.net['signals']}
        self.old=json.loads((ROOT/'data/decisions.json').read_text())
        self.final=self.old['route_updates'][-1]
        self.hp=src.llxy(76.73095468333334,30.69473045)
        self.jid=next(j for j in self.r.meta['junction_ids'] if '1424395831' in j)
        self.ji=self.r.meta['junction_ids'].index(self.jid)
        self.target='335061218'
        self.ei={e:i for i,e in enumerate(self.r.meta['edge_ids'])}
