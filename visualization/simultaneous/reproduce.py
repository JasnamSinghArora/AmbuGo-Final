#!/usr/bin/env python3
"""Render simultaneous map-and-graph films from included recorded assets."""
from pathlib import Path
import argparse, json, os, subprocess, tempfile
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'ambugo-side-mpl'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parent
FF=os.environ.get('AMBUGO_FFMPEG', imageio_ffmpeg.get_ffmpeg_exe())
V=np.array([0,3,5.5,9.5,14,16.5,20])
T=np.array([761.5,778,792,804,1048,1083.5,1125])
BLUE='#316d97'; GREY='#969da2'; INK='#313639'

class Panel:
    def __init__(self, synchronized):
        self.sync=synchronized
        data=json.loads((ROOT/'data/progression_data.json').read_text())
        assert data['source_case']=='B1000' and data['focus_ambulance']=='a002'
        r=data['recorded']; self.t=np.array(r['t_s'])
        self.speed=np.array(r['ambulance_speed_kmh'],float)
        self.count=np.array(r['ordinary_stopped_network'])
        self.base=np.array(r['routing_only_ordinary_stopped_network'])
        self.mode=np.array(r['focus_mode'])
        self.status=np.array(r['ambulance_status'])
        self.x=self.t-760
        plt.rcParams.update({'font.family':'DejaVu Sans','font.size':16,
                            'text.color':INK,'axes.labelcolor':INK,
                            'xtick.color':INK,'ytick.color':INK})
        self.fig=plt.figure(figsize=(9.6,10.8),dpi=100,facecolor='white')
        f=self.fig
        f.text(.12,.95,'Recorded simulation',fontsize=24)
        self.clock=f.text(.12,.91,'',fontsize=18,color='#667075')
        self.state=f.text(.12,.865,'',fontsize=17,color=BLUE)
        f.text(.12,.80,'Ambulance speed',fontsize=21)
        self.readout=f.text(.94,.80,'',ha='right',fontsize=24,color=BLUE)
        self.a=f.add_axes([.12,.55,.82,.215])
        f.text(.12,.465,'Ordinary vehicles stopped',fontsize=21)
        self.b=f.add_axes([.12,.21,.82,.215])
        for ax in [self.a,self.b]:
            ax.set_xlim(0,365); ax.grid(axis='y',color='#e6e8e9')
            ax.spines[['top','right']].set_visible(False)
            ax.spines[['left','bottom']].set_color('#c3c9cc')
            ax.tick_params(labelsize=14)
        self.a.set_ylim(0,60);self.a.set_yticks([0,25,50])
        self.a.set_ylabel('km/h',fontsize=16)
        self.a.set_xticks([])
        self.b.set_ylim(0,40);self.b.set_yticks([0,10,20,30,40])
        self.b.set_xticks([0,60,120,180,240,300,360])
        self.b.set_xlabel('Simulation seconds since dispatch',fontsize=17,labelpad=12)
        self.ls,=self.a.plot([],[],color=BLUE,lw=3)
        self.ps,=self.a.plot([],[],'o',color=BLUE,ms=6)
        self.lb,=self.b.step([],[],where='post',color=GREY,lw=2.2,label='Routing only')
        self.lc,=self.b.step([],[],where='post',color=BLUE,lw=2.6,label='AmbuGo')
        self.pc,=self.b.plot([],[],'o',color=BLUE,ms=6)
        self.b.legend(handles=[self.lc,self.lb],frameon=False,loc='upper center',
                      bbox_to_anchor=(.5,1.02),ncol=2,fontsize=14)
        self.ca=self.a.axvline(0,color='#a0a7ab',lw=1)
        self.cb=self.b.axvline(0,color='#a0a7ab',lw=1)
        f.text(.12,.105,'Generated traffic · Budget 1,000 vehicle-seconds',fontsize=14,color='#667075')
        f.text(.12,.07,'Network counts include all three ambulance missions.',fontsize=14,color='#667075')
        f.text(.12,.035,'Stopped counts are not total delay. Playback is accelerated.',fontsize=14,color='#667075')
    def frame(self,ft,duration):
        tm=float(np.interp(ft,V,T)) if self.sync else T[0]+(T[-1]-T[0])*ft/duration
        tm=min(tm,T[-1]); k=int(np.searchsorted(self.t,tm,side='right'))-1
        keep=(self.t>=T[0])&(self.t<=tm)
        xx=self.x[keep]
        self.ls.set_data(xx,self.speed[keep]);self.lc.set_data(xx,self.count[keep])
        self.lb.set_data(xx,self.base[keep])
        self.ca.set_xdata([tm-760]*2);self.cb.set_xdata([tm-760]*2)
        seconds=int(tm-760)
        prefix='Shared clock' if self.sync else 'Independent replay'
        self.clock.set_text(f'{prefix}  {seconds//60:02d}:{seconds%60:02d} since dispatch')
        mode='Selective priority' if self.mode[k]==0 else 'Stronger priority'
        self.state.set_text(mode)
        if np.isfinite(self.speed[k]):
            self.readout.set_text(f'{self.speed[k]:.0f} km/h')
            self.ps.set_data([self.x[k]],[self.speed[k]])
        else:
            self.readout.set_text('Arrived' if self.status[k]==2 else 'Not inserted')
            self.ps.set_data([],[])
        self.pc.set_data([self.x[k]],[self.count[k]])
        self.fig.canvas.draw()
        return Image.fromarray(np.asarray(self.fig.canvas.buffer_rgba())[:,:,:3].copy())

def header(sync):
    im=Image.new('RGB',(2880,120),'white');d=ImageDraw.Draw(im)
    path=font_manager.findfont('DejaVu Sans')
    def font(n):return ImageFont.truetype(path,n)
    d.text((48,20),'AmbuGo · route planning and selective priority',font=font(34),fill=INK)
    d.text((48,69),'Same recorded episode; animation and graphs share one clock.' if sync else
           'Planning illustration · priority limit 10,000',font=font(25),fill='#667075')
    d.text((1950,20),'Synchronized results' if sync else 'Separate simulation',font=font(34),fill=INK)
    d.text((1950,69),'Recorded traffic · priority budget 1,000' if sync else
           'Independent clock; not measurements of this film.',font=font(25),fill='#667075')
    d.line((0,119,2880,119),fill='#dce1e4',width=2)
    return im

def render(sync,preview=False):
    name='02_Synchronized_Map_and_Graphs' if sync else '01_Teammate_Film_with_Graphs'
    duration=20 if sync else 162.5
    fps=30 if sync else 12
    panel=Panel(sync); head=header(sync)
    head.save(ROOT/(name+'_header.png'))
    if preview:
        panel.frame(duration*.65,duration).save(ROOT/(name+'_panel.png'))
        plt.close(panel.fig);return
    output=ROOT/(name+'.mp4')
    input_name='01_Google_Maps_Journey.mp4' if sync else 'AmbuGo_v9_Plan.mp4'
    # The map is uncropped at native 1920x1080. A 960px graph column and
    # a 120px header produce a 2880x1200 canvas without obscuring attribution.
    cmd=[FF,'-y','-hide_banner','-loglevel','warning','-i',str(ROOT/'inputs'/input_name),
         '-f','rawvideo','-pix_fmt','rgb24','-s','960x1080','-r',str(fps),'-i','-',
         '-loop','1','-i',str(ROOT/(name+'_header.png')),
         '-filter_complex',
         '[0:v]setsar=1,setpts=PTS-STARTPTS[map];'
         '[1:v]fps=30,setsar=1,setpts=PTS-STARTPTS[graph];'
         '[map][graph]hstack=inputs=2[body];'
         '[2:v]fps=30,setsar=1,setpts=PTS-STARTPTS[head];'
         '[head][body]vstack=inputs=2[out]',
         '-map','[out]','-t',str(duration),'-r','30','-an','-c:v','libx264',
         '-threads','3','-preset','fast','-crf','18','-pix_fmt','yuv420p',
         '-movflags','+faststart',str(output)]
    with (ROOT/(name+'.log')).open('w') as log:
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
        try:
            for i in range(round(duration*fps)):
                p.stdin.write(panel.frame(i/fps,duration).tobytes())
                if i%(fps*10)==0:print(name,round(i/fps), '/',duration,flush=True)
        finally:p.stdin.close()
        if p.wait():raise RuntimeError('FFmpeg failed; inspect the log.')
    plt.close(panel.fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--preview',action='store_true')
    p.add_argument('--version',choices=['both','teammate','synchronized'],default='both')
    a=p.parse_args()
    for sync in [False,True]:
        if a.version=='both' or a.version==('synchronized' if sync else 'teammate'):
            render(sync,a.preview)
