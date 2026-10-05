"""Independent double-precision quaternion/point oracle, installed CLI only."""
import json
import math
import uuid
from precision_acceptance import Run

def add(a,b):return [x+y for x,y in zip(a,b)]
def sub(a,b):return [x-y for x,y in zip(a,b)]
def mul(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def inverse(q):return [-q[0],-q[1],-q[2],q[3]]
def rotate(q,v):return mul(mul(q,[*v,0]),inverse(q))[:3]
def axis(v,angle):
    length=math.sqrt(sum(x*x for x in v));rad=math.radians(angle)/2
    return [*(x/length*math.sin(rad) for x in v),math.cos(rad)]
def distance(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
def angle(a,b):
    a=[x/math.sqrt(sum(y*y for y in a)) for x in a];b=[x/math.sqrt(sum(y*y for y in b)) for x in b]
    return math.degrees(4*math.asin(min(1,min(distance(a,b),distance(a,[-x for x in b]))/2)))

r=Run('dev5-transforms')
baseline=r.call('baseline','craft.snapshot',{'includeXml':True})['data']
assert baseline['name'].startswith('SP2Build 050 Precision Lab')
origin_id=r.call('craft-frame','symmetry.get')['data']['configuration']['originPartId']
for name,frame in [('world',{'kind':'world'}),('part',{'kind':'part','partId':76}),('craft',{'kind':'craft'}),('custom',{'kind':'custom','position':[2,-3,4],'rotationQuaternion':axis([1,2,3],33.3)})]:
    for mode in ('delta','absolute'):
        label=name+'-'+mode
        before=r.call(label+'-before','craft.snapshot',{'includeXml':True})['data'];byid={p['id']:p for p in before['parts']};ident=before['identity']
        if name=='world':fp=[0,0,0];fq=[0,0,0,1]
        elif name=='custom':fp=frame['position'];fq=frame['rotationQuaternion']
        else:
            pid=frame.get('partId',origin_id);fp=byid[pid]['position'];fq=byid[pid]['rotationQuaternion']
        ids=[76,218];anchor=byid[76];q=axis([1,2,-1],179.997);translation=[.012,-.007,.002];pivot=[.1,.2,-.3]
        op={'kind':'transform.apply','partIds':ids,'frame':frame,'mode':mode,'rotationQuaternion':q,'symmetric':False}
        if mode=='delta':
            op.update(translation=translation,pivot=pivot);wq=mul(mul(fq,q),inverse(fq));wp=add(fp,rotate(fq,pivot));wt=rotate(fq,translation)
        else:
            target=add(rotate(inverse(fq),sub(anchor['position'],fp)),[.02,0,0]);op['position']=target
            wp=anchor['position'];wt=sub(add(fp,rotate(fq,target)),wp);wq=mul(mul(fq,q),inverse(anchor['rotationQuaternion']))
        request={'craftSessionId':ident['craftSessionId'],'expectedRevision':ident['revision'],'requestId':uuid.uuid4().hex,'operations':[op]}
        result=r.call(label+'-apply','batch.apply',request)
        r.check(label+' commit',result['success'],result.get('error'))
        if not result['success']:
            if not result.get('rollbackResult',{}).get('restored'):raise RuntimeError('Stop unconfirmed recovery')
            continue
        after=r.call(label+'-after','craft.snapshot',{'includeXml':True})['data'];post={p['id']:p for p in after['parts']}
        for pid in ids:
            expectedp=add(add(wp,rotate(wq,sub(byid[pid]['position'],wp))),wt);expectedq=mul(wq,byid[pid]['rotationQuaternion'])
            dp=distance(post[pid]['position'],expectedp);dq=angle(post[pid]['rotationQuaternion'],expectedq)
            r.check(label+f' independent pose {pid}',dp<=.0001 and dq<=.01,{'positionErrorMetres':dp,'rotationErrorDegrees':dq})
            r.check(label+f' scale preserved {pid}',byid[pid]['scale']==post[pid]['scale'])
        replay=r.call(label+'-replay','batch.apply',request)
        r.check(label+' request idempotent',replay['success'] and replay['data']['identity']==result['data']['identity'])
        ident=after['identity']
        rollback=r.call(label+'-rollback','craft.rollback',{'craftSessionId':ident['craftSessionId'],'expectedRevision':ident['revision'],'requestId':uuid.uuid4().hex,'checkpointId':result['data']['beforeCheckpointId']})
        assert rollback['success'],rollback
r.call('final','designer.status')
