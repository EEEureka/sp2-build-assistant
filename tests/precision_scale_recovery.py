"""Explicit default scales must survive native replacement and rollback exactly."""
import sys, uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
def snapshot(label):
    x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
    assert x['data']['name']=='SP2Build 050 Precision Lab F2'
    return x['data']
def guard():
    i=snapshot('guard-'+str(len(r.calls)))['identity']
    return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision'],'requestId':uuid.uuid4().hex}
def apply(label,ops):
    x=r.call(label,'batch.apply',{**guard(),'operations':ops});assert x['success'],x
    return x['data']
def rollback(label,cp):
    x=r.call(label,'craft.rollback',{**guard(),'checkpointId':cp});assert x['success'],x
    return x['data']
base=snapshot('baseline')
assert len(base['parts'])==3
root=r.call('checkpoint','craft.checkpoint.create',{**guard(),'name':'Scale regression original'})['data']['id']
x=apply('fixtures',[{'kind':'part.add','templateId':t,'temporaryId':k,'position':[0,y,0]} for t,k,y in [('tpl-c2ea68c52a8d3473','piston',4.5),('tpl-33195a9c4cfc6ff1','hinge',1)]])
ids=x['temporaryIds']
for case,scale in enumerate(([1,1,1],[1.000002,1.000003,1.000004])):
    # Native setters materialize the explicit unit scale, reproducing the bug.
    if case==0:
        apply('default-setters',[{'kind':'properties.set','partId':ids[k],'symmetric':False,'patch':{f'{family}[0].size':1}} for k,family in [('piston','Piston'),('hinge','JointRotator')]])
    else:
        apply('near-unit-scales',[{'kind':'part.update','partId':ids[k],'symmetric':False,'changes':[{'path':'Part','attribute':'scale','value':','.join(map(str,scale))}]} for k in ids])
    before=snapshot(f'case-{case}-before')
    cp=r.call(f'case-{case}-checkpoint','craft.checkpoint.create',{**guard(),'name':'Explicit scale'})['data']['id']
    apply(f'case-{case}-rename',[{'kind':'part.update','partId':ids['piston'],'changes':[{'path':'Part','attribute':'name','value':'temporary scale recovery'}]}])
    rollback(f'case-{case}-rollback',cp)
    after=snapshot(f'case-{case}-after')
    r.check(f'case {case} exact XML after rollback',before['xml']==after['xml'])
    r.check(f'case {case} exact fingerprint after rollback',before['identity']['fingerprint']==after['identity']['fingerprint'])
    for key,pid in ids.items():
        fields=r.call(f'case-{case}-properties-{key}','properties.get',{'id':pid,'limit':1000})['data']['parts'][0]['fields']
        size=next(f['value'] for f in fields if f['propertyId'] in ('Piston[0].size','JointRotator[0].size'))
        r.check(f'case {case} {key} size reflects actual scale',abs(size-scale[1])<0.0000001,{'effectiveSize':size,'scaleY':scale[1]})
rollback('remove-fixtures',root)
end=snapshot('restored')
r.check('original three-part XML restored',end['xml']==base['xml'])
r.call('final-status','designer.status')
