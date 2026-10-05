"""E2: three predeclared starts, current-state feedback and a public target.

Gold XML is not a solver input. Gold checkpoint is used only by trial setup and
cleanup; independent geometry and state review runs after the fitter finishes.
"""
import json,math,sys,uuid
from precision_acceptance import Run,ROOT
r=Run(sys.argv[1]);gold=ROOT/sys.argv[2]
t=json.loads((gold/'public-target.json').read_text());cp=json.loads((gold/'fixture.json').read_text())['checkpointId'];identity=None
starts=[{'translation':[.015,-.022,.008],'angle':.65,'length':-.09,'width':.06},
        {'translation':[-.024,-.013,-.012],'angle':-.5,'length':.12,'width':-.08},
        {'translation':[.009,-.032,.019],'angle':.9,'length':-.15,'width':.1}]
(r.root/'fixed-starts.json').write_text(json.dumps(starts,indent=2));iterations=[]
def qm(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def inv(q):return [-q[0],-q[1],-q[2],q[3]]
def norm(q):return [x/math.sqrt(sum(v*v for v in q)) for x in q]
def angle(a,b):
    a=norm(a);b=norm(b)
    return math.degrees(4*math.asin(min(1,min(math.dist(a,b),math.dist(a,[-v for v in b]))/2)))
def snap(label):
    global identity
    a=r.call(label,'craft.snapshot',{'includeXml':True});assert a['success'],a
    assert a['data']['name']=='SP2Build 050 Precision Lab F2' and a['data']['partCount']==11
    identity=a['data']['identity'];return a['data']
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def write(label,ops):
    global identity
    a=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert a['success'],a
    identity=a['data']['identity'];return a['data']
def restore(label,target=cp):
    global identity
    snap(label+'-guard')
    a=r.call(label,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':target});assert a['success'],a
    identity=a['data']['identity']
def prop(pid,k,v):return {'kind':'properties.set','partId':pid,'patch':{k:v},'symmetric':False}
fields={8:('JetEngineShroud[0].length','shroudLengthRatio'),10:('TextDecal[0].Width','textWidthMetres'),11:('TextureDecal[0].Width','stripeWidthMetres')}
def measure(label):
    s=snap(label+'-state');a=next(p for p in s['parts'] if p['id']==t['anchorPartId'])
    vals={}
    for pid,(key,target) in fields.items():
        x=r.call(label+'-field-'+str(pid),'properties.get',{'id':pid,'fields':[key]});assert x['success'],x
        f=x['data']['parts'][0]['fields'][0];assert f['valueAvailable'];vals[pid]=f['value']
    gap=r.call(label+'-gap','geometry.measure',{**guard(),'partIdsA':[9],'partIdsB':[4]});assert gap['success'] and gap['data']['complete'],gap
    err={'positionMetres':math.dist(a['position'],t['anchorTarget']['position']),'rotationDegrees':angle(a['rotationQuaternion'],t['anchorTarget']['rotationQuaternion']),
         'gapMetres':abs(gap['data']['measurement']['distanceMetres']-t['gapMetres']),'scalar':max(abs(vals[pid]-t[target]) for pid,(key,target) in fields.items())}
    return a,vals,err
def capture(label):
    for k in ('joint','detail'):
        m=json.loads((gold/('gold-'+k+'.json')).read_text())['data']
        a=r.call(label+'-'+k,'designer.capture',{**guard(),'views':m['repeatableViews'],'resolution':m['repeatableResolution']},images=True);assert a['success'],a
def mesh(label):
    a=r.call(label,'geometry.section',{**guard(),'partIds':list(range(4,12)),'plane':{'origin':[5.5,0,0],'normal':[1,0,0]},'export':True,'exportMeshes':True},images=True);assert a['success'],a
try:
    for trial,start in enumerate(starts,1):
        name='trial-'+str(trial);restore(name+'-reset')
        q=[0,math.sin(math.radians(start['angle'])/2),0,math.cos(math.radians(start['angle'])/2)]
        write(name+'-perturb',[{'kind':'transform.apply','partIds':t['group'],'anchorPartId':9,'mode':'delta','translation':start['translation'],'rotationQuaternion':q,'symmetric':False}]+
              [prop(pid,key,t[target]+(start['length'] if pid==8 else start['width'])) for pid,(key,target) in fields.items()])
        capture(name+'-start');steps=0;best=float('inf');bestcp=None
        for iteration in range(9):
            label=name+'-round-'+str(iteration);anchor,vals,err=measure(label)
            score=max(err[k]/t['tolerances'][k] for k in err)
            row={'trial':trial,'iteration':iteration,'errors':err,'candidateWrites':steps,'normalizedWorstError':score};iterations.append(row)
            if score<best:
                best=score
                bestcp=r.call(label+'-best','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':label})['data']['id']
            if score<=1:
                r.check(name+' meets all measured targets within budget',steps<=8,row)
                restore(name+'-best-restore',bestcp);snap(name+'-final');mesh(name+'-final-mesh');capture(name+'-final')
                for pid in (10,11):r.call(name+'-projector-'+str(pid),'decal.pose.get',{'id':pid})
                break
            assert steps<8,row
            gain=.8 if steps==0 else 1.0
            tq=t['anchorTarget']['rotationQuaternion'];cq=anchor['rotationQuaternion']
            if sum(x*y for x,y in zip(tq,cq))<0:tq=[-v for v in tq]
            targetq=norm([a+gain*(b-a) for a,b in zip(cq,tq)])
            pos=[a+gain*(b-a) for a,b in zip(anchor['position'],t['anchorTarget']['position'])]
            ops=([{'kind':'transform.apply','partIds':t['group'],'anchorPartId':9,'mode':'absolute','frame':{'kind':'world'},'position':pos,'rotationQuaternion':targetq,'symmetric':False}]+
                [prop(pid,key,vals[pid]+gain*(t[target]-vals[pid])) for pid,(key,target) in fields.items()])
            row['decision']={'basis':'Current anchor pose, gap and current effective dimensions versus public targets','gain':gain,'operations':ops}
            (r.root/'iterations.json').write_text(json.dumps(iterations,indent=2))
            write(label+'-candidate',ops);steps+=1
        (r.root/'iterations.json').write_text(json.dumps(iterations,indent=2))
finally:
    restore('cleanup-gold');snap('final-restored');r.call('final-status','designer.status')
