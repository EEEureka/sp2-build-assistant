from direct_build import Session,raw,states
import json
s=Session('S08')
start=s.read('craft.snapshot');s.check('Eighteen parts at S08 baseline',len(start['parts'])==18)
s.guard('craft.checkpoint.create',name='S08 before leading-edge slats')
catalog=s.read('catalog.schema',flags=('--id','tpl-fe1d383efbcc425c'));s.check('Unused Slat template has input extension',bool(catalog['templates'][0]['parts'][0]['toolEditableExtensions']))
ops=[]
for wing,name in [(7,'slatR'),(8,'slatL')]:
    ops += [{'kind':'wing.control.add','wingPartId':wing,'style':'Slat','temporaryId':name,'patch':{'spanRange':[.4,5.4],'chordFraction':[.12,.12],'maxDeflectionDegrees':20}},raw(name,input='Flaps',min=0,max=1,invert=False,activationGroup='0')]
ops += [{'kind':'symmetry.link','partIds':['slatR','slatL']}]
result=s.apply(*ops,label='add-slats-and-bind-input')['data'];ids=result['temporaryIds'];(s.path/'roles.json').write_text(json.dumps(ids),encoding='utf-8')
for name,wing in [('slatR',7),('slatL',8)]:
    i=ids[name];part=s.read('parts.get',flags=('--id',i))['part'];shape=s.read('shape.get',flags=('--id',i))['shape'];geom=s.read('parts.geometry',flags=('--id',i))['geometry']
    s.check(name+' configured as leading-edge slat',part['type']=='ControlSurface-Slat-1' and states(part)['InputController.State']['input']=='Flaps' and shape['wingPartId']==wing and abs(shape['chordFraction'][0]-.12)<1e-5 and len(geom['editorColliders'])>0)
    wing_shape=s.read('shape.get',flags=('--id',wing))['shape']
    s.check(name+' coexists with trailing-edge surfaces',len(wing_shape['controlSurfaces'])==3)
before=s.read('craft.snapshot')
failed=s.apply({'kind':'shape.update','partId':ids['slatR'],'patch':{'chordFraction':[.41,.12]}},require=False,label='oversized-slat-rejected')
s.check('Slat size refused and state recovered',not failed['success'] and failed['rollbackResult']['restored'])
after=s.read('craft.snapshot');s.check('Invalid size leaves exact fingerprint',after['identity']['fingerprint']==before['identity']['fingerprint'])
s.capture([{'name':'right','selector':{'kind':'parts','partIds':[7,15,17,ids['slatR']]}},{'name':'left','selector':{'kind':'parts','partIds':[8,16,18,ids['slatL']]}}],details='perGroup')
print('S08 BUILT',ids)
