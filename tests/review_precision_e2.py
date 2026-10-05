"""Independent E2 review from recorded native meshes/XML/poses, no live calls."""
import json,math,sys,xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np
gold=Path(sys.argv[1]);fit=Path(sys.argv[2]);checks=[]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def data(p):return read(p)['data']
def check(name,ok,detail=None):checks.append({'check':name,'status':'pass' if ok else 'fail','details':detail})
def qm(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def rotate(q,v):return qm(qm(q,[*v,0]),[-q[0],-q[1],-q[2],q[3]])[:3]
def qa(a,b):
    a=np.array(a)/np.linalg.norm(a);b=np.array(b)/np.linalg.norm(b)
    return math.degrees(4*math.asin(min(1,min(np.linalg.norm(a-b),np.linalg.norm(a+b))/2)))
def parts(s):return {p['id']:p for p in s['parts']}
def xmlparts(s):return {int(p.attrib['id']):p for p in ET.fromstring(s['xml']).findall('./Assembly/Parts/Part')}
def canonical(n):return (n.tag,tuple(sorted(n.attrib.items())),n.text or '',tuple(canonical(c) for c in n))
def mesh(root,name):return read(next((root/name).rglob('meshes.json')))['meshes']
def compare_meshes(a,b):
    compatible=len(a)==len(b) and all(x['partId']==y['partId'] and x['indices']==y['indices'] and len(x['vertices'])==len(y['vertices']) for x,y in zip(a,b))
    return {'matchingTopology':compatible,'maxVertexErrorMetres':max((math.dist(p,q) for x,y in zip(a,b) for p,q in zip(x['vertices'],y['vertices'])),default=0) if compatible else None}
g=data(gold/'gold.json');gp=parts(g);gx=xmlparts(g);gm=mesh(gold,'gold-mesh');t=read(gold/'public-target.json')
before=data(gold/'before-rigid-target.json');bp=parts(before);motion=t['requestedLocalMotion'];localq=motion['rotationQuaternion'];fq=motion['frame']['rotationQuaternion']
q=qm(qm(fq,localq),[-fq[0],-fq[1],-fq[2],fq[3]])
pivot=[p+x for p,x in zip(motion['frame']['position'],rotate(fq,motion['pivot']))];delta=rotate(fq,motion['translation'])
for pid in t['group']:
    expected=[p+d+x for p,d,x in zip(pivot,delta,rotate(q,[v-p for v,p in zip(bp[pid]['position'],pivot)]))]
    check('independent 5mm external .2deg target '+str(pid),math.dist(expected,gp[pid]['position'])<=.0001 and qa(qm(q,bp[pid]['rotationQuaternion']),gp[pid]['rotationQuaternion'])<=.01,{'positionErrorMetres':math.dist(expected,gp[pid]['position'])})
a=next(p for p in data(gold/'gold-ap-8.json')['points'] if p['id']==1)['worldPosition'];b=next(p for p in data(gold/'gold-ap-9.json')['points'] if p['id']==0)['worldPosition']
check('legal connection intentionally retains nonzero AP offset',math.dist(a,b)>.01,{'metres':math.dist(a,b)})
for trial in range(1,4):
    label='trial-'+str(trial);s=data(fit/(label+'-final.json'));p=parts(s);x=xmlparts(s)
    for pid in (1,2,3,4,5,6):check(label+' frozen full Part '+str(pid),canonical(gx[pid])==canonical(x[pid]))
    for pid in t['group']:
        check(label+' pose '+str(pid),math.dist(p[pid]['position'],gp[pid]['position'])<=.0001 and qa(p[pid]['rotationQuaternion'],gp[pid]['rotationQuaternion'])<=.01)
        check(label+' scale '+str(pid),p[pid]['scale']==gp[pid]['scale'])
    for i,a in enumerate(t['group']):
        for b in t['group'][i+1:]:check(label+' rigid distance '+str(a)+'/'+str(b),abs(math.dist(p[a]['position'],p[b]['position'])-math.dist(gp[a]['position'],gp[b]['position']))<=.0001)
    for pid in gp:
        for tag in ('Animator.State','InputController.State','PartTargeting.State'):
            check(label+' preserved '+str(pid)+' '+tag,[canonical(n) for n in gx[pid].findall(tag)]==[canonical(n) for n in x[pid].findall(tag)])
    for tag in ('Theme','Variables'):
        check(label+' global craft '+tag,[canonical(n) for n in ET.fromstring(g['xml']).findall('.//'+tag)]==[canonical(n) for n in ET.fromstring(s['xml']).findall('.//'+tag)])
    check(label+' same connection graph',s['connections']==g['connections'])
    md=compare_meshes(gm,mesh(fit,label+'-final-mesh'));check(label+' actual native geometry',md['matchingTopology'] and md['maxVertexErrorMetres']<=.0001,md)
    for pid in (10,11):
        a=data(gold/('gold-projector-'+str(pid)+'.json'))['projectorPose'];b=data(fit/(label+'-projector-'+str(pid)+'.json'))['projectorPose']
        check(label+' projector follows group '+str(pid),math.dist(a['position'],b['position'])<=.0001 and qa(a['rotationQuaternion'],b['rotationQuaternion'])<=.01)
    pngstats=[]
    for kind in ('joint','detail'):
        gd=data(gold/('gold-'+kind+'.json'));ad=data(fit/(label+'-final-'+kind+'.json'))
        gmfest=read(Path(gd['manifestPath']));amfest=read(Path(ad['manifestPath']))
        # Compare actual native cameras, not double-precision request basis
        # normalization (which may differ at 1e-17 on replay).
        camera_errors=[]
        for gv,av in zip(gmfest['views'],amfest['views']):
            gc=gv['camera'];ac=av['camera'];control=[gp[pid]['position'] for pid in t['group']]
            def pixel(c,p):
                clip=np.array(c['projectionRows'])@np.array(c['worldToCameraRows'])@np.array([*p,1])
                return (clip[:2]/clip[3]+1)*np.array([800,500])
            camera_errors.append({'positionMetres':math.dist(gc['positionWorld'],ac['positionWorld']),
                'rotationDegrees':qa(gc['rotationQuaternion'],ac['rotationQuaternion']),
                'projectionPixelError':max(float(np.linalg.norm(pixel(gc,p)-pixel(ac,p))) for p in control),
                'unusedOrthographicSize':None if gc['projection']=='orthographic' else [gc['orthographicSize'],ac['orthographicSize']],
                'scalarsMatch':gc['projection']==ac['projection'] and all(abs(gc[k]-ac[k])<=1e-6 for k in (('orthographicSize',) if gc['projection']=='orthographic' else ('fieldOfViewDegrees',))+('aspect','nearClipMetres','farClipMetres'))})
            gi=np.asarray(Image.open(Path(gd['manifestPath']).parent/gv['file']).convert('RGB'),dtype=int)
            ai=np.asarray(Image.open(Path(ad['manifestPath']).parent/av['file']).convert('RGB'),dtype=int)
            diff=np.max(np.abs(gi-ai),axis=2);pngstats.append({'kind':kind,'view':gv['name'],'maxChannelDifference':int(diff.max()),'pixelsOver2':int((diff>2).sum())})
        check(label+' fixed actual native camera '+kind,gd['repeatableResolution']==ad['repeatableResolution'] and all(x['positionMetres']<=.0001 and x['rotationDegrees']<=.001 and x['projectionPixelError']<=.1 and x['scalarsMatch'] for x in camera_errors),camera_errors)
    (fit/(label+'-native-image-diff.json')).write_text(json.dumps(pngstats,indent=2))
sheet=Image.new('RGB',(1800,4*400),'white');draw=ImageDraw.Draw(sheet)
for row,label in enumerate(('gold','trial-1','trial-2','trial-3')):
    for col,(kind,view) in enumerate((('joint','isometric'),('joint','top'),('detail','left'))):
        root=gold if label=='gold' else fit;fn='gold-'+kind if label=='gold' else label+'-final-'+kind
        d=data(root/(fn+'.json'));im=Image.open(Path(d['manifestPath']).parent/(view+'.png')).convert('RGB');im.thumbnail((600,750))
        sheet.paste(im,(col*600,row*400+25));draw.text((col*600+8,row*400+7),label+' '+view,fill='black')
sheet.save(fit/'native-final-contact.png')
(fit/'independent-review-v3.json').write_text(json.dumps({'checks':checks,'meaning':'Developer controlled native fixture; image metrics and objective tests do not replace visual inspection/user aesthetic approval. V1 raw request basis and V2 inactive perspective ortho-size comparisons retained. V3 evaluates actual projection matrices/control points and active projection parameters, retaining inactive values in diagnostics. This does not relax the separate before/after player camera restoration checks.'},indent=2))
print(json.dumps({'passed':sum(x['status']=='pass' for x in checks),'failed':[x for x in checks if x['status']=='fail']}))
