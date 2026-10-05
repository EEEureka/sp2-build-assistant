"""Compare ordered add/resize/connect/delete boundaries against separate calls."""
import json,math,sys,uuid
from precision_acceptance import Run
from review_restore_state import audit

r=Run(sys.argv[1])
def call(n,c,a=None,**kw):
    x=r.call(n,c,a,**kw);assert x['success'],x;return x['data']
def guard():
    i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def snap(n):return call(n,'craft.snapshot',{'includeXml':True})
def write(n,ops):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def reset(n):call(n,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
def mesh(n,ids):
    call(n,'geometry.section',{**guard(),'partIds':ids,'plane':{'origin':[0,2.25,0],'normal':[0,1,0]},'export':True,'exportMeshes':True},images=True)
    return json.loads(next((r.root/n).rglob('meshes.json')).read_text(encoding='utf-8-sig'))['meshes']
def add(name,pos):return {'kind':'part.add','templateId':'tpl-f748657136c8ca1a','temporaryId':name,'position':pos}
def name(pid,value):return {'kind':'part.update','partId':pid,'symmetric':False,'changes':[{'path':'Part','attribute':'name','value':value}]}
def shape(pid,length,width,height,auto):return {'kind':'shape.update','partId':pid,'symmetric':False,'patch':{'autoResize':auto,'length':length,'sections':[{'index':i,'width':width,'height':height,'syncAdjacent':False} for i in (0,1)]}}
base=snap('baseline');assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
cp=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'edit-plan boundaries'})['id']
try:
    for auto in (True,False):
        tag='auto' if auto else 'explicit'
        ops=[add('host',[4,2.25,0]),shape('host',1.5,1.4,1.2,False),name('host','first name'),name('host','final host'),
             add('tip',[7,2.25,0]),shape('tip',.7,.6,.8,auto),
             {'kind':'connection.connect','partA':'tip','attachPointA':1,'partB':'host','attachPointB':0,'symmetric':False},
             name('tip','connected tip'),name('host','connected host'),
             add('discard',[9,2.25,0]),{'kind':'part.delete','partId':'discard','symmetric':False},add('replacement',[10,2.25,0]),name('replacement','new identity')]
        reset(tag+'-batch-reset');out=write(tag+'-batch',ops);b=snap(tag+'-batch-state');ids=sorted(set(p['id'] for p in b['parts'])-set(p['id'] for p in base['parts']))
        mb=mesh(tag+'-batch-mesh',ids)
        bs=call(tag+'-batch-tip','shape.get',{'id':out['temporaryIds']['tip']})['shape']
        bp={pid:call(tag+'-batch-points-'+str(pid),'connections.points',{'part':pid})['points'] for pid in ids}
        # A temporary binding belongs to one batch. Resolve each prior result
        # when building the independent serial sequence; never reuse deleted IDs.
        reset(tag+'-serial-reset');refs={}
        for i,op in enumerate(ops):
            item=dict(op)
            for key in ('partId','partA','partB'):
                if isinstance(item.get(key),str):item[key]=refs[item[key]]
            result=write(tag+'-serial-'+str(i),[item]);refs.update(result['temporaryIds'])
        s=snap(tag+'-serial-state');ms=mesh(tag+'-serial-mesh',ids)
        ss=call(tag+'-serial-tip','shape.get',{'id':refs['tip']})['shape']
        proof=audit(b['xml'],s['xml']);r.check(tag+' complete state same',proof['equivalent'],proof)
        r.check(tag+' effective shape same',bs==ss,{'batch':bs,'serial':ss})
        r.check(tag+' native autoResize consumed or disabled',ss['configuration']['autoResize'] is False,ss)
        r.check(tag+' intended size behavior',abs(ss['configuration']['length']-(1.5 if auto else .7))<=1e-5,ss)
        topology=len(mb)==len(ms) and all(x['partId']==y['partId'] and x['indices']==y['indices'] and len(x['vertices'])==len(y['vertices']) for x,y in zip(mb,ms))
        error=max((math.dist(x,y) for m,n in zip(mb,ms) for x,y in zip(m['vertices'],n['vertices'])),default=0) if topology else float('inf')
        r.check(tag+' all native geometry same',topology and error<=.0001,{'topology':topology,'maxMetres':error})
        for pid in ids:
            points=call(tag+'-serial-points-'+str(pid),'connections.points',{'part':pid})['points'];r.check(tag+' actual mounts same '+str(pid),bp[pid]==points)
        r.check(tag+' reuse explicitly reported',any(x['partId']==out['temporaryIds']['replacement'] for x in out['reusedPartIds']),out['reusedPartIds'])
finally:
    reset('restore-original');proof=audit(base['xml'],snap('final')['xml']);r.check('complete original restore',proof['equivalent'],proof)
    state=call('final-status','designer.status');r.check('healthy one aircraft',state['sceneIntegrity']['status']=='healthy' and state['sceneIntegrity']['aircraftInstanceCount']==1)
print(json.dumps({'passed':sum(c['status']=='pass' for c in r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
