"""Independent reference measurements, not bridge math or serialized shape values."""
import json,sys
from pathlib import Path

def cuts(meshes,pid,z):
    segments=[]
    for m in meshes:
        if m['partId']!=pid:continue
        for i in range(0,len(m['indices']),3):
            tri=[m['vertices'][k] for k in m['indices'][i:i+3]];hits=[]
            for a,b in zip(tri,tri[1:]+tri[:1]):
                da,db=a[2]-z,b[2]-z
                if da*db<0:
                    t=da/(da-db);hits.append([a[k]+t*(b[k]-a[k]) for k in range(3)])
                elif abs(da)<1e-12:hits.append(a)
            unique={tuple(round(c,10) for c in p):p for p in hits}
            if len(unique)==2:segments.append(list(unique.values()))
    return segments

def bounds(points):
    assert points
    return {'min':[min(p[k] for p in points) for k in range(3)],'max':[max(p[k] for p in points) for k in range(3)]}

def mesh_bounds(meshes,pid):return bounds([p for m in meshes if m['partId']==pid for p in m['vertices']])

def profile(meshes,pid,z):
    b=bounds([p for s in cuts(meshes,pid,z) for p in s])
    return {'z':z,'width':b['max'][0]-b['min'][0],'height':b['max'][1]-b['min'][1]}

def make_public(gold):
    meshes=json.loads(next((gold/'gold-mesh').rglob('meshes.json')).read_text())['meshes']
    b=mesh_bounds(meshes,6);start=b['min'][2];end=b['max'][2]
    shift=[(b['min'][k]+b['max'][k])/2-[0,5,1.65][k] for k in range(3)]
    return {'provenance':'Measured reference mesh; no XML, shape fields or full target parameter set provided to fitter.',
        'nose':{'partId':6,'sections':[profile(meshes,6,start+(end-start)*t) for t in (.01,.5,.99)],'backZ':start,'frontZ':end},
        'fixtureTranslation':shift,
        'windows':[{'partId':i,'zMin':mesh_bounds(meshes,i)['min'][2],'zMax':mesh_bounds(meshes,i)['max'][2]} for i in range(7,11)],
        'frozenPartIds':[1,2,3,4], 'editablePartIds':[5,6,7,8,9,10],
        'tolerances':{'sampledContourMetres':.001,'silhouetteP95Pixels':2,'silhouetteMaxPixels':4},
        'viewRegion':{'zMin':.226+shift[2],'zMax':2.274+shift[2],'metresPerPixel':.001,'width':2048,'height':2048}}

if __name__=='__main__':
    gold=Path(sys.argv[1]);p=make_public(gold)
    (gold/'public-target.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
    print(json.dumps(p,indent=2))
