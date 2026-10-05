"""Recorded live acceptance of lifecycle and effective controller fixes (global CLI)."""
import json
from pathlib import Path
import direct_build as d
d.ROOT=Path(__file__).parent/'artifacts/staged-build/direct-0.4.10'
s=d.Session('acceptance')
baseline=s.read('craft.snapshot',{'includeXml':True})
checkpoint=s.guard('craft.checkpoint.create',name='0.4.10 lifecycle acceptance baseline')
(s.path/'baseline-checkpoint.json').write_text(json.dumps(checkpoint,indent=2),encoding='utf-8')
def scene(label):
    v=s.read('designer.status')['sceneIntegrity']
    s.check(label,v['status']=='healthy' and v['aircraftInstanceCount']==1 and v['activeAircraftInstanceCount']==1)
def restore_data(label):
    v=s.read('craft.snapshot',{'includeXml':True})
    # Native Euler serialization may vary; compare stable role/count and all world positions.
    a={p['id']:p for p in baseline['parts']}; b={p['id']:p for p in v['parts']}
    s.check(label,set(a)==set(b) and all(a[k]['name']==b[k]['name'] and a[k]['type']==b[k]['type'] and max(abs(x-y) for x,y in zip(a[k]['position'],b[k]['position']))<1e-4 for k in a))
    s.check(label+' controller restored',s.read('parts.get',{'id':15})['part']['inputControllers'][0]['zeroOnDeactivate'] is False)
def rename(name): return {'kind':'part.update','partId':15,'changes':[{'path':'','attribute':'name','value':name}]}
scene('startup one instance')
for i,expected in [(15,['Aileron']),(21,['Disabled','BuildBrakeCommand']),(26,['Disabled','Brake']),(30,['Yaw','Brake']),(1,[])]:
    v=s.read('parts.get',{'id':i})['part']['inputControllers']
    s.check('effective inputs '+str(i),[x['input'] for x in v]==expected)
    s.check('indexed paths '+str(i),[x['path'] for x in v]==['InputController.State[%d]'%j for j in range(len(v))])
catalog=s.read('catalog.schema',{'id':'tpl-0107631356a369e6'})
s.check('unused small turboprop template effective inputs',any(p.get('inputControllers') for p in catalog['templates'][0]['parts']))
r=s.apply(rename('Lifecycle first'),rename('Lifecycle second'),d.raw(15,zeroOnDeactivate=True),label='multiple-replacements-one-batch')
s.check('batch scene verification',r['data']['validation']['sceneIntegrityVerified'])
scene('multi replacement only one instance')
v=s.read('parts.get',{'id':15})['part']['inputControllers'][0]
s.check('omitted true default readable',v['zeroOnDeactivate'] is True and 'zeroOnDeactivate' not in v['serializedAttributes'])
s.check('shape read same effective default',s.read('shape.get',{'id':15})['shape']['inputControllers'][0]==v)
s.guard('craft.undo'); scene('undo only one instance'); restore_data('undo baseline')
r=s.apply(rename('Recovery first'),rename('Recovery second'),{'kind':'variable.add','variable':'LifecycleInvalid','function':'NoSuchLifecycleFunction('},require=False,label='partial-execution-failure')
s.check('execution failure',not r['success'])
s.check('whole batch recovery',r.get('rollbackResult',{}).get('restored') is True)
scene('failure recovery only one instance'); restore_data('failure baseline')
s.apply(rename('Rollback first'),rename('Rollback second'),d.raw(15,zeroOnDeactivate=True),label='multiple-replacements-before-rollback')
scene('second multi replacement only one instance')
s.guard('craft.rollback',checkpointId=checkpoint['id'])
scene('checkpoint rollback only one instance'); restore_data('rollback baseline')
s.read('craft.history')
print('ACCEPTANCE COMPLETE',s.path,flush=True)
