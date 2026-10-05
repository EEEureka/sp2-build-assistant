from direct_build import Session,states
import json
s=Session('S09-brakeflap')
start=s.read('craft.snapshot');s.check('Twenty parts at baseline',len(start['parts'])==20)
s.guard('craft.checkpoint.create',name='S09 native BrakeFlap testing; dedicated Spoiler unavailable')
ops=[]
for wing,name in [(7,'brakeR'),(8,'brakeL')]:
    ops.append({'kind':'wing.control.add','wingPartId':wing,'style':'BrakeFlap','temporaryId':name,'patch':{'spanRange':[2.7,3.35],'chordFraction':[.28,.28],'flapDeflectionDegrees':0,'brakeTopDegrees':60,'brakeBottomDegrees':60,'brakeDeflectionSpeed':2}})
    ops.append({'kind':'part.update','partId':name,'changes':[{'path':'InputController.State[0]','attribute':'input','value':'Disabled'},{'path':'InputController.State[1]','attribute':'input','value':'Brake'}]})
ops.append({'kind':'symmetry.link','partIds':['brakeR','brakeL']})
result=s.apply(*ops,label='native-brakeflaps-two-indexed-inputs')['data'];ids=result['temporaryIds'];(s.path/'roles.json').write_text(json.dumps(ids),encoding='utf-8')
for i in ids.values():
    part=s.read('parts.get',flags=('--id',i))['part'];shape=s.read('shape.get',flags=('--id',i))['shape'];geom=s.read('parts.geometry',flags=('--id',i))['geometry']
    inputs=[n['attributes']['input'] for n in part['state']['children'] if n['element']=='InputController.State']
    s.check(str(i)+' separate flap/brake input controllers',inputs==['Disabled','Brake'])
    s.check(str(i)+' split brake angles retained',all(shape['configuration'][k]==v for k,v in {'flapDeflectionDegrees':0,'brakeTopDegrees':60,'brakeBottomDegrees':60,'brakeDeflectionSpeed':2}.items()))
    s.check(str(i)+' meshes and pick colliders generated',len(geom['renderers'])>=2 and len(geom['editorColliders'])>=2)
snapshot=s.read('craft.snapshot');s.check('22-part formal craft',len(snapshot['parts'])==22)
s.capture([{'name':'right','selector':{'kind':'parts','partIds':[7,15,17,19,ids['brakeR']]}},{'name':'left','selector':{'kind':'parts','partIds':[8,16,18,20,ids['brakeL']]}}],details='perGroup')
print('S09 BrakeFlap alternative configured; dedicated Spoiler remains unavailable')
