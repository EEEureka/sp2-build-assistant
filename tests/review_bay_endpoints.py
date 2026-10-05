"""Independent rigid-pivot calculation on exported endpoint mesh vertices."""
import json,math,xml.etree.ElementTree as ET
from PIL import Image,ImageDraw
from precision_acceptance import ROOT
def qmul(a,b):
 x,y,z,w=a;X,Y,Z,W=b
 return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def inv(q):return [-q[0],-q[1],-q[2],q[3]]
def rot(q,v):
 n=math.sqrt(sum(x*x for x in q));q=[x/n for x in q]
 return qmul(qmul(q,[*v,0]),inv(q))[:3]
def read(run,file):return json.loads((ROOT/run/file).read_text(encoding='utf-8-sig'))
def mesh(run):return json.loads(next((ROOT/run/'mesh').rglob('meshes.json')).read_text(encoding='utf-8-sig'))['meshes']
def nums(s):return list(map(float,s.split(',')))
report=[];canvas=Image.new('RGB',(1440,1260),'white');draw=ImageDraw.Draw(canvas)
for case_idx,case in enumerate(('original','manual')):
 closed='dev9-bay-endpoint-'+case+'-closed';opened='dev9-bay-endpoint-'+case+'-open'
 cs,os=read(closed,'snapshot.json')['data'],read(opened,'snapshot.json')['data']
 part=ET.fromstring(cs['xml']).find("./Assembly/Parts/Part[@id='10']")
 assert nums(part.attrib['rotation'])==[0,0,0], 'Fixture requires zero part rotation'
 world=nums(part.attrib['position']);bay=part.find('GearBay.State');anim=part.find('Animator.State')
 end=sorted(anim.findall('Keyframe'),key=lambda k:float(k.attrib['percent']))[-1]
 ends={p.attrib['element']:nums(p.attrib['rotation']) for p in end.findall('Pose')}
 cm,om=mesh(closed),mesh(opened);matching=[]
 for c,o in zip(cm,om):
  assert c['partId']==o['partId'] and c['indices']==o['indices']
  movement=max(math.dist(a,b) for a,b in zip(c['vertices'],o['vertices']))
  row={'partId':c['partId'],'maxMovementMetres':movement}
  if c['partId']==10:
   errors=[]
   for idx,suffix in enumerate(('', '2')):
    center=[a+b for a,b in zip(world,nums(bay.attrib['hingePos'+suffix]))]
    axis=nums(bay.attrib['hingeRot'+suffix]);r=qmul(qmul(axis,ends['door'+str(idx+1)]),inv(axis))
    predicted=[[p+q for p,q in zip(center,rot(r,[v-p for v,p in zip(vtx,center)]))] for vtx in c['vertices']]
    errors.append(max(math.dist(a,b) for a,b in zip(predicted,o['vertices'])))
   row.update({'pivotErrorMetres':errors,'matchingAxis':errors.index(min(errors))+1,'pass':min(errors)<=.0001 and movement>.1})
   matching.append(row['matchingAxis'])
  else:row['pass']=movement<=.0001
  report.append({'case':case,**row})
 assert len(set(matching))==2, 'Both independent hinge axes must be exercised'
 for j,name in enumerate((closed,opened)):
  views=read(name,'views.json')['data']
  for i,v in enumerate(views['views']):
   image=Image.open(str(__import__('pathlib').Path(views['outputDirectory'])/v['file'])).convert('RGB');image.thumbnail((480,290))
   y=(case_idx*2+j)*315;canvas.paste(image,(i*480,y+25));draw.text((i*480+5,y+5),case+' '+('closed' if j==0 else 'open')+' '+v['name'],fill='black')
out=ROOT/'dev9-bay-endpoint-audit';out.mkdir(exist_ok=True)
(out/'independent.json').write_text(json.dumps({'checks':report,'pass':all(x['pass'] for x in report),'method':'Rotate every closed mesh vertex by H * keyframeRotation * inverse(H) about its observed world hinge; do not call bridge measurement code. Host must remain fixed.'},indent=2))
canvas.save(out/'endpoint-contact.png');print(json.dumps(report))
