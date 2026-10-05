"""Independent E3 endpoint audit; no bridge measurement code is used."""
import json,math,sys,xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image,ImageDraw
root=Path(sys.argv[1]);names=sys.argv[2:5];out=root/sys.argv[5];out.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def data(n,f):return read(root/n/f)['data']
def mesh(n):return read(next((root/n/'mesh').rglob('meshes.json')))['meshes']
def mul(a,b):
 x,y,z,w=a;X,Y,Z,W=b
 return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def norm(q):return [x/math.sqrt(sum(v*v for v in q)) for x in q]
def inv(q):return [-q[0],-q[1],-q[2],q[3]]
def rot(q,v):
 q=norm(q);return mul(mul(q,[*v,0]),inv(q))[:3]
def add(a,b):return [x+y for x,y in zip(a,b)]
def sub(a,b):return [x-y for x,y in zip(a,b)]
def nums(s):return list(map(float,s.split(',')))
def canon(n):return (n.tag,tuple(sorted(n.attrib.items())),tuple(canon(c) for c in n))
checks=[]
def check(n,b,d=None):checks.append({'check':n,'status':'pass' if b else 'fail','details':d})
snaps=[data(n,'snapshot.json') for n in names];meshes=[mesh(n) for n in names]
parts=[{p['id']:p for p in s['parts']} for s in snaps]
xmls=[{int(p.get('id')):p for p in ET.fromstring(s['xml']).findall('./Assembly/Parts/Part')} for s in snaps]
for n,s,x in zip(names,snaps,xmls):
 check(n+' capture preserves serialized state',s['xml']==data(n,'after.json')['xml'])
 check(n+' graph unchanged',s['connections']==snaps[0]['connections'])
 for pid in x:
  for tag in ('Animator.State','InputController.State','PartTargeting.State'):
   check(n+' configuration '+str(pid)+' '+tag,[canon(c) for c in x[pid].findall(tag)]==[canon(c) for c in xmls[0][pid].findall(tag)])
for stage in (1,2):
 for i,(a,b) in enumerate(zip(meshes[0],meshes[stage])):
  same=a['partId']==b['partId'] and a['indices']==b['indices'] and len(a['vertices'])==len(b['vertices'])
  check('endpoint topology '+str((stage,i)),same)
  if a['partId'] in (4,8):
   e=max(math.dist(p,q) for p,q in zip(a['vertices'],b['vertices']));check('frozen mesh '+str((stage,i)),e<=.0001,e)
# Wheel frame from the serialized native animation, independently transformed
# through the gear part quaternion and its style size.
gear=xmls[0][5];anim=gear.find('Animator.State');size=float(gear.find('GearLeg.State').get('size'))
gp=parts[0][5];gq=norm(gp['rotationQuaternion']);wheelposes={float(k.get('percent')):k.find("Pose[@element='Wheel']") for k in anim.findall('Keyframe')}
for stage,t in ((0,1.),(1,0.)):
 p=wheelposes[t];expected=add(gp['position'],rot(gq,[v*size for v in nums(p.get('position'))]));actual=parts[stage][6]
 check('native wheel keyframe position '+str(t),math.dist(expected,actual['position'])<=.0001,{'expected':expected,'actual':actual['position']})
 q=norm(mul(gq,nums(p.get('rotation'))));a=norm(actual['rotationQuaternion']);angle=math.degrees(4*math.asin(min(1,min(math.dist(q,a),math.dist(q,[-v for v in a]))/2)))
 check('native wheel keyframe rotation '+str(t),angle<=.01,angle)
# Every wheel vertex must undergo the same observed endpoint rigid transform.
down,up=parts[0][6],parts[1][6];dq=mul(norm(up['rotationQuaternion']),inv(norm(down['rotationQuaternion'])))
errs=[math.dist(add(up['position'],rot(dq,sub(p,down['position']))),q) for a,b in zip(meshes[0],meshes[1]) if a['partId']==6 for p,q in zip(a['vertices'],b['vertices'])]
check('wheel meshes follow native endpoint pose',max(errs)<=.0001,max(errs))
# Doors: closed -> open using each hinge's actual rotated part frame.
bay=xmls[2][7].find('GearBay.State');bp=parts[2][7];bq=norm(bp['rotationQuaternion']);anim=xmls[2][7].find('Animator.State');end=max(anim.findall('Keyframe'),key=lambda k:float(k.get('percent')));matched=[]
for i,(closed,opened) in enumerate(zip(meshes[2],meshes[1])):
 if closed['partId']!=7:continue
 errors=[]
 for axis,suffix in enumerate(('', '2'),1):
  pivot=add(bp['position'],rot(bq,nums(bay.get('hingePos'+suffix))));hq=mul(bq,nums(bay.get('hingeRot'+suffix)));pose=end.find("Pose[@element='door"+str(axis)+"']");dq=mul(mul(hq,nums(pose.get('rotation'))),inv(hq))
  errors.append(max(math.dist(add(pivot,rot(dq,sub(p,pivot))),q) for p,q in zip(closed['vertices'],opened['vertices'])))
 matched.append(errors.index(min(errors)));check('native door hinge mesh '+str(i),min(errors)<=.0001,errors)
check('both hinge axes verified',set(matched)=={0,1})
# Fixture has axis-aligned rectangular bay before the rounded corner strips.
v=[p for m in meshes[2] if m['partId'] in (5,6) for p in m['vertices']];door=[p for m in meshes[2] if m['partId']==7 for p in m['vertices']]
bounds=lambda v:{'min':[min(p[a] for p in v) for a in range(3)],'max':[max(p[a] for p in v) for a in range(3)]}
vb,db=bounds(v),bounds(door)
check('retracted gear above closed door',vb['min'][1]-db['max'][1]>.001,{'gapMetres':vb['min'][1]-db['max'][1],'gearBounds':vb,'doorBounds':db})
check('retracted gear inside bay lateral envelope',vb['min'][0]>=2.95 and vb['max'][0]<=5.05 and vb['min'][2]>=-1.4 and vb['max'][2]<=1.4,vb)
sheet=Image.new('RGB',(1800,1200),'white');draw=ImageDraw.Draw(sheet)
for row,n in enumerate(names):
 d=data(n,'views.json')
 for col,v in enumerate(d['views']):
  im=Image.open(Path(d['outputDirectory'])/v['file']).convert('RGB');im.thumbnail((600,375));sheet.paste(im,(col*600,row*400+25));draw.text((col*600+5,row*400+5),n+' '+v['name'],fill='black')
sheet.save(out/'native-endpoints.png');(out/'checks.json').write_text(json.dumps(checks,indent=2))
print(json.dumps({'passed':sum(c['status']=='pass' for c in checks),'failed':[c for c in checks if c['status']=='fail']}))
