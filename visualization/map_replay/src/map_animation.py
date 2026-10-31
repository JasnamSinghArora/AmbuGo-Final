"""Portable final 20-second map renderer. Six fixed Google Maps captures share
one Web Mercator camera with all recorded vehicles, routes and signals. The
camera moves; the replay itself is unchanged. Native map attribution is retained.
"""
from pathlib import Path
import sys,json,math,argparse,subprocess,hashlib,os
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageFilter
ROOT=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent;OUT=ROOT/'generated'
import map_support as old
W,H=1920,1080;TOP=62;MH=958;BOTTOM=1020;BLUE=old.BLUE;RED=old.RED;GREEN=old.GREEN;GREY=old.GREY;AMBER=old.AMBER;INK=old.INK
circle=old.circle;txt=old.txt;check=old.check

def ease(x):
 x=np.clip(x,0,1);return x*x*x*(10+x*(-15+6*x))
def blendcam(a,b,x):
 u=ease(x);out=np.array(a)*(1-u)+np.array(b)*u;out[2]=math.exp(math.log(a[2])*(1-u)+math.log(b[2])*u);return out
class Movie(old.Movie):
 def __init__(self,output_dir=None):
  self.output_dir=Path(output_dir or OUT);self.output_dir.mkdir(parents=True,exist_ok=True)
  super().__init__();self.story=json.loads((ROOT/'data/story.json').read_text());self.connections=json.loads((ROOT/'data/connectors.json').read_text());self.route_cache={}
  self.J=np.array([*old.src.llxy(76.7129,30.71042),275.]);self.HC=np.array([*old.src.llxy(76.73105,30.69545),420.]);self.WIDE=np.array([*old.src.llxy(76.7226866,30.7041958),3200.]);self.patches=[]
  inputs=[('far',ROOT/'assets/maps/far.png',76.7226514,30.7042347,14),('wide',ROOT/'assets/maps/wide.png',76.7226514,30.7042347,15),('middle',ROOT/'assets/maps/middle.png',76.7245,30.7065,16),('junction_mid',ROOT/'assets/maps/junction_mid.png',76.7129,30.71042,17),('hospital',ROOT/'assets/maps/hospital.png',76.73105,30.6951,17),('junction',ROOT/'assets/maps/junction.png',76.7129,30.71042,18)]
  manifest=[]
  for name,path,lon,lat,z in inputs:
   im=Image.open(path).convert('RGBA');mask=Image.new('L',im.size,0);d=ImageDraw.Draw(mask);d.rectangle((82,74,1268,672),fill=255);d.rectangle((72,610,188,720),fill=0);d.rectangle((1103,669,1280,720),fill=0);d.rectangle((1212,565,1280,720),fill=0);im.putalpha(255)
   p={'name':name,'image':im,'center':old.src.llxy(lon,lat),'res':156543.03392804097/2**z,'z':z};self.patches.append(p)
   manifest.append({'name':name,'source_url':f'https://www.google.com/maps/@{lat},{lon},{z}z','lon':lon,'lat':lat,'zoom':z,'capture_size':[1280,720],'capture_center_pixel':[640,360],'mercator_metres_per_pixel':p['res'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
  (self.output_dir/'capture_manifest.json').write_text(json.dumps(manifest,indent=2))
  original=Image.open(ROOT/'assets/maps/junction.png').convert('RGB');self.logo=original.crop((620,677,735,701)).resize((173,36),Image.Resampling.LANCZOS);self.credit=original.crop((754,703,878,720)).resize((186,26),Image.Resampling.LANCZOS)
  self.background_cache={};self.prepare_cameras()
 def time(self,vt):
  v=[0,3,5.5,9.5,14,16.5,20];s=[761.5,778,792,804,1048,1083.5,1125];i=min(5,max(0,np.searchsorted(v,vt,side='right')-1));return float(np.interp(vt,v,s)),i
 def screen(self,xy,cam):return (np.asarray(xy)-cam[:2])*[W/(2*cam[2]),-W/(2*cam[2])]+[W/2,MH/2+TOP]
 def prepare_cameras(self):
  self.cameras=[];audit=[]
  for i in range(601):
   vt=i/30;t,phase=self.time(vt);p=self.r.amb(t)[2]
   if vt<1.25:cam=self.WIDE.copy()
   elif vt<3:
    cam=blendcam(self.WIDE,self.J,(vt-1.25)/1.75);u=ease((vt-1.25)/1.05);cam[:2]=self.WIDE[:2]*(1-u)+self.J[:2]*u
   elif vt<=9.5:cam=self.J.copy()
   elif vt<14:
    u=(vt-9.5)/4.5
    # Continuous ambulance tracking with gentle hand-off from the fixed junction,
    # then to the fixed destination. Zoom opens during the accelerated corridor.
    zoom=275+(1350-275)*math.sin(math.pi*u)**1.25+(420-275)*u
    follow=np.array([*p,zoom]);a=ease((vt-9.5)/.9);cam=self.J*(1-a)+follow*a
    b=ease((vt-13.1)/.9);cam=cam*(1-b)+self.HC*b
   elif vt<=16.5:cam=self.HC.copy()
   elif vt<17.35:cam=blendcam(self.HC,self.WIDE,(vt-16.5)/.85)
   elif vt<18.5:cam=blendcam(self.WIDE,self.J,(vt-17.35)/1.15)
   else:cam=self.J.copy()
   if vt<16.5 and np.isfinite(p).all():
    required=max(abs(p[0]-cam[0])+65,(abs(p[1]-cam[1])+65)*W/MH)
    # A soft maximum ensures the tracked vehicle stays inside the view without
    # an abrupt camera correction at the screen boundary.
    cam[2]=max(cam[2],required)+20*math.log1p(math.exp(-abs(cam[2]-required)/20))
   self.cameras.append(cam)
  self.cameras=np.array(self.cameras)
  # Symmetric short camera smoothing removes position-sample tremor, while the
  # replayed vehicles retain their original positions and timing.
  for j in range(3):
   padded=np.pad(self.cameras[:,j],(6,6),mode='edge');self.cameras[:,j]=np.convolve(padded,np.array([1,2,3,4,5,6,7,6,5,4,3,2,1])/49,mode='valid')
  for i,cam in enumerate(self.cameras):
   vt=i/30;t,phase=self.time(vt);p=self.r.amb(t)[2]
   if vt<16.5 and np.isfinite(p).all():
    ps=self.screen(p,cam);audit.append({'video_s':vt,'simulation_s':t,'ambulance_pixel':ps.tolist(),'inside':bool(70<ps[0]<1850 and TOP+60<ps[1]<BOTTOM-60)})
  (self.output_dir/'camera_audit.json').write_text(json.dumps({'continuous_camera':True,'same_camera_for_map_and_overlays':True,'vehicle_positions_unchanged':True,'visible_frames':sum(a['inside'] for a in audit),'checked_frames':len(audit),'failures':[a for a in audit if not a['inside']],'camera_samples':self.cameras.tolist()},indent=2))
 def camera(self,vt):
  f=min(600,max(0,vt*30));i=int(f);return self.cameras[i] if i==600 else self.cameras[i]*(1-(f-i))+self.cameras[i+1]*(f-i)
 def background(self,cam):
  key=tuple(np.round(cam,2))
  if key in self.background_cache:return self.background_cache[key].copy()
  out=Image.new('RGBA',(W,MH),(245,245,243,255));worldres=2*cam[2]/W
  for p in self.patches:
   r=p['res'];a=worldres/r;left=cam[0]-cam[2];top=cam[1]+cam[2]*MH/W;x=(left-p['center'][0])/r+640;y=(p['center'][1]-top)/r+360
   x2=x+W*a;y2=y+MH*a
   margin=min(x-82,1268-x2,y-74,672-y2)
   for rx1,ry1,rx2,ry2 in [(72,610,188,720),(1103,669,1280,720),(1212,565,1280,720)]:
    margin=min(margin,max(rx1-x2,x-rx2,ry1-y2,y-ry2))
   opacity=1 if p['z']==14 else float(ease(margin/18))
   if opacity<.001:continue
   patch=p['image'].transform((W,MH),Image.Transform.AFFINE,(a,0,x,0,a,y),Image.Resampling.BICUBIC)
   # Blend the WHOLE frame only when this source fully covers it. This avoids
   # mixed label sizes, partial detail patches and visible geographic seams.
   patch.putalpha(round(255*opacity));out=Image.alpha_composite(out,patch)
  result=Image.new('RGB',(W,H),'white');result.paste(out.convert('RGB'),(0,TOP))
  if len(self.background_cache)>5:self.background_cache.pop(next(iter(self.background_cache)))
  self.background_cache[key]=result.copy();return result
 def route_points(self,ids):
  key=tuple(ids)
  if key in self.route_cache:return self.route_cache[key]
  pts=[]
  for j,e in enumerate(ids):
   pts.extend(self.edges[e])
   if j+1<len(ids):
    nxt=ids[j+1];opts=self.connections.get(e+'|'+nxt,[])
    if opts:
     chosen=opts[0];seen=set()
     for _ in range(6):
      if chosen['via'] in seen:break
      seen.add(chosen['via']);pts.extend(old.src.llxy(*np.array(chosen['shape_lonlat']).T));viaedge=chosen['via'].rsplit('_',1)[0];more=self.connections.get(viaedge+'|'+nxt,[])
      if not more:break
      chosen=more[0]
  arr=np.array(pts);self.route_cache[key]=arr;return arr
 def route(self,d,ids,cam,col=BLUE,width=9,arrows=False):
  if not ids:return
  pts=self.screen(self.route_points(ids),cam);ps=[tuple(p) for p in pts];d.line(ps,fill=(255,255,255,230),width=width+5,joint='curve');d.line(ps,fill=col,width=width,joint='curve')
  if arrows:
   delta=np.diff(pts,axis=0);length=np.linalg.norm(delta,axis=1);cum=np.r_[0,np.cumsum(length)]
   for s in np.arange(100,cum[-1],185):
    j=min(len(delta)-1,np.searchsorted(cum,s)-1)
    if length[j]<.01:continue
    u=delta[j]/length[j];n=np.array([-u[1],u[0]]);p=pts[j]+u*(s-cum[j]);d.line([tuple(p-u*5+n*4),tuple(p),tuple(p-u*5-n*4)],fill='white',width=2)
 def car(self,d,p,a,L,B,amb=False,stopped=False,vt=0):
  rad=math.radians(a);u=np.array([math.sin(rad),-math.cos(rad)]);n=np.array([u[1],-u[0]]);p=p-u*L/2
  def poly(vals,c,outline=None,w=1):d.polygon([tuple(p+u*x+n*y) for x,y in vals],fill=c,outline=outline,width=w)
  if amb:circle(d,p,44,(255,255,255,225),BLUE,3)
  for x in [-L*.3,L*.3]:
   for y in [-B*.52,B*.52]:poly([(x-3,y-2),(x+3,y-2),(x+3,y+2),(x-3,y+2)],(35,40,48))
  poly([(-L/2,-B/2),(-L/2,B/2),(L*.37,B/2),(L/2,B*.32),(L/2,-B*.32),(L*.37,-B/2)],'white' if amb else (62,74,87),INK,2 if amb else 1)
  poly([(L*.16,-B*.39),(L*.16,B*.39),(L*.34,B*.32),(L*.34,-B*.32)],(155,202,229) if amb else (181,198,211))
  if amb:
   cp=p-u*7;d.line([tuple(cp-u*9),tuple(cp+u*9)],fill=RED,width=6);d.line([tuple(cp-n*9),tuple(cp+n*9)],fill=RED,width=6)
   for k,c in [(-1,RED),(1,BLUE)]:circle(d,p+u*4+n*(B/2+3)*k,4,c if int(vt*4)%2==(k==1) else 'white')
  elif stopped:
   for k in [-1,1]:circle(d,p-u*L*.44+n*B*.30*k,2.3,RED)
 def cars(self,d,t,cam,vt):
  ids,xy,angles,speeds=self.r.positions(t);ps=self.screen(xy,cam);scale=W/(2*cam[2]);focus=None
  for k,p,a,v in zip(ids,ps,angles,speeds):
   if not(-35<p[0]<W+35 and TOP-30<p[1]<BOTTOM+30):continue
   if k==self.r.ami[2]:focus=(p,a);continue
   le,wi=self.r.vehicle_dimensions[k];self.car(d,p,a,np.clip(le*scale*1.164,12,31),np.clip(wi*scale*1.164,6,12),stopped=v<.1,vt=vt)
  if focus:self.car(d,*focus,64,30,amb=True,vt=vt)
 def lights(self,d,t,cam,vt):
  a=self.r.a;i=self.r.at(t);focus_phase=cam[2]<650 and (2.9<vt<9.9 or vt>18.4)
  for jid,j in self.signals.items():
   ji=self.r.meta['junction_ids'].index(jid);mode=int(a['signal_mode'][i,ji]);served=int(a['signal_edge'][i,ji])
   for eid in j['incoming']:
    pts=self.screen(self.edges[eid],cam);p=pts[-1]
    if not(30<p[0]<W-30 and TOP+30<p[1]<BOTTOM-30):continue
    c=GREEN if mode==0 and served==self.ei[eid] else AMBER if mode==1 and served==self.ei[eid] else RED
    u=pts[-1]-pts[-2];u/=max(np.linalg.norm(u),.001);n=np.array([-u[1],u[0]])
    if not(focus_phase and jid==self.jid):circle(d,p,5,c,'white',2);continue
    d.line([tuple(p-n*18),tuple(p+n*18)],fill=c,width=6)
    target=(eid==self.target if vt<16.5 else served==self.ei[eid]);q=p-u*85-n*(135 if target else 70);size=1 if target else .48
    d.line([tuple(p),tuple(q)],fill='white',width=4);d.line([tuple(p),tuple(q)],fill=(90,98,108),width=1)
    x,y=q;d.rounded_rectangle((x-23*size,y-56*size,x+23*size,y+56*size),6,fill=(38,44,52),outline='white',width=2)
    for k,col in enumerate([RED,AMBER,GREEN]):circle(d,(x,y+(k-1)*35*size),13*size,col if col==c else (78,85,92))
    if target and eid==self.target and 785<=t<802.5:
     r=q+np.array([87,78]);ap=self.screen(self.r.amb(t)[2],cam);vec=r-ap;dist=np.linalg.norm(vec)
     for f in np.arange(50/max(dist,1),1-26/max(dist,1),15/max(dist,1)):circle(d,ap+vec*f,2.5,BLUE if t>=792 else RED)
     circle(d,r,24,'white',BLUE if t>=792 else RED,3)
     if t>=792:check(d,r,BLUE,12)
     else:
      x,y=r;d.line([(x-9,y-9),(x+9,y+9)],fill=RED,width=5);d.line([(x-9,y+9),(x+9,y-9)],fill=RED,width=5)
    if c==GREEN:
     p2=p+u*27;d.polygon([tuple(p2+u*13),tuple(p2-u*7+n*9),tuple(p2-u*7-n*9)],fill=GREEN,outline='white',width=2)
 def hospital(self,d,cam,done=False):
  p=self.screen(self.hp,cam)
  if not(55<p[0]<W-120 and TOP+60<p[1]<BOTTOM-60):return
  x,y=p;d.rounded_rectangle((x-28,y-28,x+28,y+28),6,fill='white',outline=BLUE,width=3);txt(d,p,'H',36,BLUE,True,'mm')
  if done:circle(d,p+[33,24],20,'white',GREEN,2);check(d,p+[33,24],GREEN,10)
 def frame(self,vt):
  t,phase=self.time(vt);cam=self.camera(vt);im=self.background(cam);layer=Image.new('RGBA',(W,H));d=ImageDraw.Draw(layer);rid=int(self.r.a['ambulance_route'][self.r.at(t),2]);route=self.r.meta['routes'][rid] if rid>=0 else []
  if vt<2:
   for c in self.old['first_decision']['unique_routes']:self.route(d,c['route'],cam,(125,135,147,255),7)
  if phase==4:self.route(d,self.final['incumbent_route'],cam,(130,140,152,255),9)
  if phase<5:self.route(d,route,cam,BLUE,9,True)
  elif vt<18:self.route(d,self.final['chosen_route'],cam,(96,145,202,150),6)
  self.lights(d,t,cam,vt);self.cars(d,t,cam,vt);self.hospital(d,cam,phase==5)
  # Graphical layers never enter the permanent Google attribution strip.
  layer.paste((0,0,0,0),(0,0,W,TOP));layer.paste((0,0,0,0),(0,BOTTOM,W,H));im=Image.alpha_composite(im.convert('RGBA'),layer).convert('RGB');d=ImageDraw.Draw(im)
  if t<785:title='Route choice' if vt<1.5 else 'Approaching the signal'
  elif t<792:title='Priority withheld'
  elif t<796.5:title='Request accepted'
  elif t<802.5:title='Ambulance green'
  elif vt<14:title='To hospital'
  elif t<1055:title='Hospital approach'
  elif t<1083.5:title='Route updated'
  else:title='Traffic continues'
  txt(d,(30,13),title,28,INK,True);txt(d,(W-26,19),'MOHALI · SIMULATED TRAFFIC',16,(100,109,119),anchor='ra');d.line((0,TOP-1,W,TOP-1),fill=(220,224,229),width=1)
  if vt<2.2:
   alpha=1-ease((vt-1.6)/.6);bar=Image.new('RGBA',(W,58));bd=ImageDraw.Draw(bar);bd.rectangle((0,0,W,58),fill=(255,255,255,236));txt(bd,(25,29),'ETA',22,INK,True,'lm')
   for j,c in enumerate(self.old['first_decision']['unique_routes']):
    sec=round(c['forecast_with_priority_s']);x=165+j*310;txt(bd,(x,29),f"{chr(65+j)}  {sec//60}:{sec%60:02}",25,BLUE if c['chosen'] else GREY,c['chosen'],'lm')
    if c['chosen']:check(bd,(x+155,29),BLUE,10)
   bar.putalpha(bar.getchannel('A').point(lambda a:int(a*alpha)));im.paste(bar,(0,BOTTOM-58),bar)
  if 14.5<vt<16.2:
   old.badge(d,(145,TOP+43),'ETA 25 s',BLUE);old.badge(d,(390,TOP+43),'ETA 35 s',GREY);check(d,(256,TOP+43),BLUE,10)
  # The original logo and complete copyright wording stay adjacent to the map,
  # at fixed readable size throughout camera motion. No fixed scale bar.
  im.paste(self.logo,(24,1031));im.paste(self.credit,(220,1036));d=ImageDraw.Draw(im);elapsed=int(t-760);txt(d,(W-28,1047),f'{elapsed//60:02}:{elapsed%60:02} since dispatch',18,(90,98,108),anchor='rm')
  return im

def render(output_dir=None,preview=False):
 out=Path(output_dir or OUT);out.mkdir(parents=True,exist_ok=True);m=Movie(out)
 if preview:
  for v in [.7,1.8,2.5,3.2,4.7,6,7.6,9.3,10.5,11.8,13.2,14.8,16.3,17.1,17.8,18.7,19.5]:m.frame(v).save(out/f'map_preview_{v:04.1f}.jpg',quality=95)
  print('Map previews ready:',out);return out
 import imageio_ffmpeg
 ff=os.environ.get('AMBUGO_FFMPEG') or imageio_ffmpeg.get_ffmpeg_exe();path=out/'01_Google_Maps_Journey.mp4'
 with (out/'map_encode.log').open('w') as err:
  proc=subprocess.Popen([str(ff),'-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-','-an','-c:v','libx264','-preset','fast','-threads','3','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],stdin=subprocess.PIPE,stderr=err)
  try:
   for i in range(600):
    proc.stdin.write(m.frame(i/30).tobytes())
    if i%100==0:print(f'Map {i}/600',flush=True)
   proc.stdin.close()
   if proc.wait()!=0:raise RuntimeError('Encoding failed; inspect map_encode.log')
  except BaseException:
   proc.kill();proc.wait();raise
 m.frame(.7).save(out/'01_Poster.jpg',quality=95)
 print(path);return path

def main():
 ap=argparse.ArgumentParser(description='Reproduce the final 20-second Google Maps animation from the frozen replay.')
 ap.add_argument('--preview-only','--preview',action='store_true');ap.add_argument('--output',type=Path,default=OUT)
 a=ap.parse_args();render(a.output,a.preview_only)
if __name__=='__main__':main()
