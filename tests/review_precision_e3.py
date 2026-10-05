"""Independent recorded-state, mesh, mount and projection audit for E3 fits."""
import json,math,sys,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
gold=Path(sys.argv[1]);fit=Path(sys.argv[2]);checks=[]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def data(p):return read(p)['data']
def check(n,b,d=None):checks.append({'check':n,'status':'pass' if b else 'fail','details':d})
def canonical(n):return (n.tag,tuple(sorted(n.attrib.items())),n.text or '',tuple(canonical(c) for c in n))
def parts(s):return {int(p.get('id')):p for p in ET.fromstring(s['xml']).findall('./Assembly/Parts/Part')}
def meshes(root,name):return read(next((root/name).rglob('meshes.json')))['meshes']
g=data(gold/'gold.json');gx=parts(g);gm=meshes(gold,'native-mesh');gc=data(gold/'native-views.json');gp={p['id']:p for p in g['parts']}
for trial in range(1,4):
 label='trial-'+str(trial);s=data(fit/(label+'-final.json'));px=parts(s);by={p['id']:p for p in s['parts']}
 for pid in (1,2,3,4):check(label+' frozen complete part '+str(pid),canonical(gx[pid])==canonical(px[pid]))
 for pid in gp:
  for tag in ('Animator.State','InputController.State','PartTargeting.State'):
   check(label+' preserved '+str(pid)+' '+tag,[canonical(x) for x in gx[pid].findall(tag)]==[canonical(x) for x in px[pid].findall(tag)])
 for tag in ('Theme','Variables','DisconnectedParts'):
  check(label+' global '+tag,[canonical(n) for n in ET.fromstring(g['xml']).findall('.//'+tag)]==[canonical(n) for n in ET.fromstring(s['xml']).findall('.//'+tag)])
 check(label+' exact connection graph',g['connections']==s['connections'])
 for pid in range(4,9):
  a=gp[pid];b=by[pid];angle=math.degrees(4*math.asin(min(1,min(math.dist(a['rotationQuaternion'],b['rotationQuaternion']),math.dist(a['rotationQuaternion'],[-v for v in b['rotationQuaternion']]))/2)))
  check(label+' part pose '+str(pid),math.dist(a['position'],b['position'])<=.0001 and angle<=.01,{'positionMetres':math.dist(a['position'],b['position']),'angleDegrees':angle})
 am=meshes(fit,label+'-final-mesh');top=len(gm)==len(am) and all(a['partId']==b['partId'] and a['indices']==b['indices'] and len(a['vertices'])==len(b['vertices']) for a,b in zip(gm,am))
 err=max((math.dist(p,q) for a,b in zip(gm,am) for p,q in zip(a['vertices'],b['vertices'])),default=0) if top else None
 check(label+' full native meshes',top and err<=.0001,{'sameTopology':top,'maxVertexErrorMetres':err})
 for pid in range(5,9):
  a=data(gold/f'gold-ap-{pid}.json')['points'];b=data(fit/f'{label}-ap-{pid}.json')['points']
  check(label+' mount roles/types '+str(pid),[{k:p[k] for k in ('id','role','seekTypes','receiveTypes','connectedPartIds')} for p in a]==[{k:p[k] for k in ('id','role','seekTypes','receiveTypes','connectedPartIds')} for p in b])
  e=max((math.dist(p[k],q[k]) for p,q in zip(a,b) for k in ('worldPosition','normal','jointAxisWorld')),default=0)
  check(label+' mount positions and axes '+str(pid),e<=.0001,e)
 tire=lambda d:next(x['bounds']['center'] for x in d['geometry']['renderers'] if x['name'].startswith('Tire'))
 e=math.dist(tire(data(gold/'gold-geometry-6.json')),tire(data(fit/f'{label}-final-measure-wheel.json')));check(label+' actual tire center',e<=.0001,e)
 ac=data(fit/f'{label}-final-views.json')
 for a,b in zip(gc['views'],ac['views']):
  def project(cam,point):
   c=np.array(cam['projectionRows'])@np.array(cam['worldToCameraRows'])@np.array([*point,1]);return(c[:2]/c[3]+1)*np.array([800,500])
  e=max(float(np.linalg.norm(project(a['camera'],p['position'])-project(b['camera'],p['position']))) for p in gp.values())
  check(label+' actual fixed camera '+a['name'],e<=.1,e)
for kind in ('final','start','worse'):
 sheet=Image.new('RGB',(1800,1600),'white');draw=ImageDraw.Draw(sheet)
 for row,label in enumerate(['gold','trial-1','trial-2','trial-3']):
  c=gc if label=='gold' else data(fit/(label+'-'+kind+'-views.json'))
  for col,v in enumerate(c['views']):
   im=Image.open(Path(c['outputDirectory'])/v['file']).convert('RGB');im.thumbnail((600,375));sheet.paste(im,(col*600,row*400+25));draw.text((col*600+6,row*400+6),label+' '+kind+' '+v['name'],fill='black')
 sheet.save(fit/('native-'+kind+'-contact.png'))
(fit/'independent-review.json').write_text(json.dumps({'checks':checks,'meaning':'Recorded native UI reference versus three public-target fits; contact sheets require opening. Two-state animation and mirrored mechanisms are separately required.'},indent=2))
print(json.dumps({'passed':sum(c['status']=='pass' for c in checks),'failed':[c for c in checks if c['status']=='fail']}))
