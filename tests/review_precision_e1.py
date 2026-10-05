"""Independent E1 mesh, contour, native-image and frozen-state review.

No bridge measurement or target-fitting implementation is used as an oracle.
Surface checks are vertex samples against opposite native triangles, not a
continuous CAD surface guarantee. Pixel silhouettes are mesh projections; native
PNG color differences are reported separately for visual inspection.
"""
import json,math,sys,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from precision_e1_targets import cuts

gold=Path(sys.argv[1]);run=Path(sys.argv[2]);checks=[]
def check(name,ok,details=None):checks.append({'check':name,'status':'pass' if ok else 'fail','details':details})
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def loadmesh(path):return read(next(path.rglob('meshes.json')))['meshes']
gm=loadmesh(gold/'gold-mesh');gs=read(gold/'gold-state.json')['data']
dz=read(gold/'public-target.json').get('fixtureTranslation',[0,0,0])[2]

def triangles(meshes,pid):
    return np.concatenate([np.asarray(m['vertices'],float)[np.asarray(m['indices']).reshape(-1,3)] for m in meshes if m['partId']==pid])

def point_distances(points,triangles):
    a,b,c=triangles[:,0],triangles[:,1],triangles[:,2];ab=b-a;ac=c-a
    n=np.cross(ab,ac);nn=(n*n).sum(1);valid=nn>1e-22;a,b,c,ab,ac,n,nn=[x[valid] for x in (a,b,c,ab,ac,n,nn)]
    ans=[]
    d00=(ab*ab).sum(1);d01=(ab*ac).sum(1);d11=(ac*ac).sum(1);den=d00*d11-d01*d01
    for start in range(0,len(points),96):
        p=points[start:start+96,None,:];ap=p-a
        d20=(ap*ab).sum(2);d21=(ap*ac).sum(2)
        v=(d11*d20-d01*d21)/den;w=(d00*d21-d01*d20)/den
        signed=(ap*n).sum(2);inside=(v>=0)&(w>=0)&(v+w<=1)
        dist=np.where(inside,signed*signed/nn,np.inf)
        for x,y in ((a,b),(b,c),(c,a)):
            e=y-x;ee=(e*e).sum(1);t=np.clip(((p-x)*e).sum(2)/ee,0,1)
            d=((p-(x+t[:,:,None]*e))**2).sum(2);dist=np.minimum(dist,d)
        ans.extend(np.sqrt(dist.min(1)).tolist())
    return ans

def section_error(a,b):
    def sample(seg):
        return [np.array(x)+(np.array(y)-x)*t for x,y in seg for t in np.linspace(0,1,max(2,int(math.dist(x,y)/.001)+1))]
    def one(ps,ss):
        x=np.asarray([p[0] for p in ss]);e=np.asarray([p[1] for p in ss])-x;ee=(e*e).sum(1);out=[]
        for p in ps:
            t=np.clip(((p-x)*e).sum(1)/ee,0,1);out.append(float(np.sqrt(((p-x-t[:,None]*e)**2).sum(1).min())))
        return out
    return max(one(sample(a),b)+one(sample(b),a))

def mask(meshes,view,ids):
    cam=view['camera'];forward=np.array(cam['forwardWorld']);up=np.array(cam['upWorld']);right=np.cross(up,forward)
    # Unity camera right is cross(up,forward). PNG y is down.
    center=np.array(cam['targetWorld']);ppm=2048/(2*cam['orthographicSize'])
    out=Image.new('1',(2048,2048));draw=ImageDraw.Draw(out)
    for m in meshes:
        if m['partId'] not in ids:continue
        v=np.array(m['vertices'])-center;xy=np.column_stack((1024+v@right*ppm,1024-v@up*ppm))
        for tri in np.asarray(m['indices']).reshape(-1,3):draw.polygon([tuple(x) for x in xy[tri]],fill=1)
    return np.asarray(out,dtype=bool),ppm

def edge(mask):
    interior=mask.copy()
    for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):interior &= np.roll(mask,(dy,dx),(0,1))
    result=mask & ~interior;result[[0,-1],:]=False;result[:,[0,-1]]=False
    return result

def contour_dist(a,b):
    # Exact Euclidean distances up to the frozen 4px maximum. Anything farther
    # is marked infinity, never rounded down or silently discarded.
    coords=np.argwhere(a);out=np.full(len(coords),np.inf)
    for dy,dx in sorted(((y,x) for y in range(-4,5) for x in range(-4,5) if x*x+y*y<=16),key=lambda p:p[0]*p[0]+p[1]*p[1]):
        ys=coords[:,0]+dy;xs=coords[:,1]+dx;valid=(ys>=0)&(ys<2048)&(xs>=0)&(xs<2048)
        idx=np.where(valid)[0];hits=b[ys[valid],xs[valid]];idx=idx[hits]
        out[idx]=np.minimum(out[idx],math.hypot(dx,dy))
    return out

def fixed_parts(state):
    root=ET.fromstring(state['xml'])
    return {p.attrib['id']:ET.tostring(p,encoding='unicode') for p in root.findall('./Assembly/Parts/Part') if int(p.attrib['id']) in (1,2,3,4)}

gold_parts=ET.fromstring(gs['xml']).findall('./Assembly/Parts/Part')
for trial in (1,2,3):
    name='trial-'+str(trial);result=read(run/(name+'-result.json'));fm=loadmesh(run/(name+'-round-'+str(result['lastRound'])+'-mesh'))
    final=read(run/(name+'-final.json'))['data'];check(name+' frozen parts exact XML',fixed_parts(final)==fixed_parts(gs))
    root=ET.fromstring(final['xml']);by={int(p.attrib['id']):p for p in root.findall('./Assembly/Parts/Part')}
    expected={int(p.attrib['id']):p for p in gold_parts}
    for pid in range(4,11):
        a=triangles(gm,pid);b=triangles(fm,pid)
        distances=point_distances(np.unique(a.reshape(-1,3),axis=0),b)+point_distances(np.unique(b.reshape(-1,3),axis=0),a)
        check(name+' part '+str(pid)+' bidirectional native surface vertex samples',max(distances)<=.001,{'maxMetres':max(distances),'samples':len(distances)})
        for tag in ('PartTargeting.State','Animator.State','InputController.State'):
            check(name+' part '+str(pid)+' '+tag+' preserved',[ET.tostring(x) for x in by[pid].findall(tag)]==[ET.tostring(x) for x in expected[pid].findall(tag)])
    errors=[]
    for basez in (1.05001,1.2,1.65,2.,2.24999):
        z=basez+dz;errors.append({'z':z,'maxSampledMetres':section_error(cuts(gm,6,z),cuts(fm,6,z))})
    check(name+' five independent nose cross sections',all(x['maxSampledMetres']<=.001 for x in errors),errors)
    # Both near-seam contours must match the reference. This uses full contour
    # distance, rather than a single closest surface pair that could miss a gap.
    seams=[section_error(cuts(gm,pid,z+dz),cuts(fm,pid,z+dz)) for pid,z in [(5,1.04999),(6,1.05001)]]
    check(name+' cabin/nose seam contours',max(seams)<=.001,{'sampledMaxMetres':max(seams)})
    for suffix in ('plan-side','front'):
        ref=read(gold/('gold-'+suffix+'.json'))['data'];cur=read(run/(name+'-final-native-'+suffix+'.json'))['data']
        for v in ref['views']:
            label=v['name'];cv=next(x for x in cur['views'] if x['name']==label)
            for scope,ids in [('body',[4,5,6]),('glass',[7,8,9,10])]:
                a,ppm=mask(gm,v,ids);b,_=mask(fm,cv,ids);ae=edge(a);be=edge(b)
                ds=np.concatenate([contour_dist(ae,be),contour_dist(be,ae)])
                ok=len(ds)>0 and np.isfinite(ds).all();p95=float(np.percentile(ds,95)) if ok else None;maximum=float(ds.max()) if ok else None
                check(name+' '+label+' '+scope+' silhouette',ok and p95<=2 and maximum<=4 and abs(ppm-1000)<.01,{'p95Pixels':p95,'maxPixels':maximum,'outside4px':int((~np.isfinite(ds)).sum()),'metresPerPixel':1/ppm,'samples':len(ds),'excluded':'image border; off-ROI frozen rear; mesh silhouettes do not certify transparency'})
                overlay=np.zeros((2048,2048,3),dtype=np.uint8);overlay[ae]=[255,0,0];overlay[be]=[0,255,255];overlay[ae&be]=[255,255,255]
                Image.fromarray(overlay).save(run/(name+'-'+label+'-'+scope+'-contours.png'))
            # Native imagery retained separately, not interpreted as a geometry oracle.
            path=lambda parent:next(parent.rglob(label+'.png'))
            ga=np.asarray(Image.open(path(gold/('gold-'+suffix))).convert('RGB'),dtype=np.int16)
            fa=np.asarray(Image.open(path(run/(name+'-final-native-'+suffix))).convert('RGB'),dtype=np.int16)
            delta=np.abs(ga-fa);check(name+' '+label+' native pixel difference recorded',True,{'identical':bool((delta==0).all()),'maxChannelDifference':int(delta.max()),'pixelsDifferent':int(np.any(delta,axis=2).sum()),'meaning':'Not a visual pass; open native images to assess glass and helpers.'})
    check(name+' iteration/write budget',2<=result['candidateBatches']<=12 and result['candidateBatches']+1<=30,result)
check('gold restored complete XML',read(run/'final-restored.json')['data']['xml']==gs['xml'])
report={'method':__doc__,'checks':checks,'pass':all(x['status']=='pass' for x in checks),'limits':['Developer-authored measurement-driven fitter, not independent agent trial','Prepared CLI primitives subsequently edited through native UI','Pixel silhouette metrics are projected native meshes; native color images reviewed separately','No picking, mirror or arbitrary corner/offset fitting claim from this benchmark']}
(run/'independent-review.json').write_text(json.dumps(report,indent=2,allow_nan=False))
print(json.dumps({'pass':report['pass'],'checks':len(checks),'failures':[x for x in checks if x['status']!='pass']},indent=2))
