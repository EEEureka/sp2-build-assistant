from direct_build import Session,raw,states
import json
s=Session('S07')
start=s.read('craft.snapshot');s.check('S07 starts from accepted sixteen-part craft',len(start['parts'])==16)
s.guard('craft.checkpoint.create',name='S07 before inboard Fowler flaps')
catalog=s.read('catalog.schema',flags=('--id','tpl-b940f15a25c2e308'))
s.check('Unused Fowler template publishes input field extension',bool(catalog['templates'][0]['parts'][0]['toolEditableExtensions']))
ops=[]
for wing,name in [(7,'flapR'),(8,'flapL')]:
    ops += [{'kind':'wing.control.add','wingPartId':wing,'style':'FowlerFlap','temporaryId':name,'patch':{'spanRange':[.35,2.55],'chordFraction':[.3,.3],'maxDeflectionDegrees':35}},raw(name,input='Flaps',min=0,max=1,invert=False,activationGroup='0')]
ops += [{'kind':'symmetry.link','partIds':['flapR','flapL']}]
result=s.apply(*ops,label='add-flaps-and-bind-input')['data']; ids=result['temporaryIds']
(s.path/'roles.json').write_text(json.dumps(ids),encoding='utf-8')
for name,wing in [('flapR',7),('flapL',8)]:
    i=ids[name];part=s.read('parts.get',flags=('--id',i))['part'];shape=s.read('shape.get',flags=('--id',i))['shape']
    s.check(name+' correct input, range, wing',states(part)['InputController.State']['input']=='Flaps' and shape['wingPartId']==wing and shape['configuration']['spanRange']==[.35,2.55] and abs(shape['chordFraction'][0]-.3)<1e-5)
before=s.read('craft.snapshot')
failed=s.apply({'kind':'shape.update','partId':ids['flapR'],'patch':{'spanRange':[.35,3.6]}},require=False,label='overlap-aileron-rejected')
s.check('Overlap explicitly refused',not failed['success'] and failed['error']['code']=='control_surface_overlap')
after=s.read('craft.snapshot');s.check('Overlap rollback exact',failed['rollbackResult']['restored'] and before['identity']['fingerprint']==after['identity']['fingerprint'])
s.apply({'kind':'shape.update','partId':ids['flapR'],'patch':{'maxDeflectionDegrees':30}},label='sync-flaps-30')
for i in ids.values():s.check(str(i)+' synchronized thirty degrees',s.read('shape.get',flags=('--id',i))['shape']['configuration']['maxDeflectionDegrees']==30)
s.apply({'kind':'shape.update','partId':ids['flapR'],'patch':{'maxDeflectionDegrees':35}},label='restore-flaps-35')
final=s.read('craft.snapshot');s.check('Flap round trip exact',final['identity']['fingerprint']==before['identity']['fingerprint'])
s.read('connections.list',flags=('--view','structured'));s.read('symmetry.get')
s.capture([{'name':'right','selector':{'kind':'parts','partIds':[7,15,ids['flapR']]}},{'name':'left','selector':{'kind':'parts','partIds':[8,16,ids['flapL']]}}],details='perGroup')
print('S07 BUILT',ids,'partCount',len(final['parts']))
