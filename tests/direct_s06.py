from direct_build import Session, raw, states
import json

s=Session('S06-retest')
status=s.read('designer.status'); start=s.read('craft.snapshot')
s.check('0.4.8 ready with 16 saved parts',status['designerReady'] and status['pluginVersion']=='0.4.8' and len(start['parts'])==16)
parts={p['id']:p for p in start['parts']}
s.check('Expected wing and control identities',all(parts[i]['type']=='JWing-1' for i in (7,8)) and all(parts[i]['type']=='ControlSurface-Flap-1' for i in (15,16)))
checkpoint=s.guard('craft.checkpoint.create',name='Direct S06 input verification baseline')
(s.path/'baseline-checkpoint.json').write_text(json.dumps(checkpoint,indent=2),encoding='utf-8')
schema=s.read('catalog.schema',flags=('--id','tpl-923fb3378019afb3'))
s.check('Catalog advertises exact seven controller fields',set(a['name'] for a in schema['templates'][0]['parts'][0]['toolEditableExtensions'][0]['attributes'])=={'input','activationGroup','invert','min','max','zeroOnDeactivate','invertType'})
op=raw(15,input='Aileron',invert=False,min=-1,max=1,activationGroup='0',zeroOnDeactivate=False,invertType='Axis');op['symmetric']=True
s.apply(op,label='bind-ailerons')
for i in (15,16):
    p=s.read('parts.get',flags=('--id',i))['part']
    s.check(f'{i} native Aileron mapped without double inversion',all(states(p)['InputController.State'][k]==v for k,v in {'input':'Aileron','invert':'false','min':'-1','max':'1','activationGroup':'0'}.items()))
formal=s.read('craft.snapshot'); formal_cp=s.guard('craft.checkpoint.create',name='S06 formal Aileron binding')
s.apply(raw(15,input='clamp(Aileron,-1,1)',activationGroup='Brake > 0',invert=True,min=1,max=-1,zeroOnDeactivate=True,invertType='Output'),label='valid-expression-and-mapping')
tested=states(s.read('parts.get',flags=('--id',15))['part'])['InputController.State']
s.check('All seven configured fields read back',all(tested[k]==v for k,v in {'input':'clamp(Aileron,-1,1)','activationGroup':'Brake > 0','invert':'true','min':'1','max':'-1','zeroOnDeactivate':'true','invertType':'Output'}.items()))
for label,attributes,code in [('bad-expression',{'input':'clamp('},'invalid_expression'),('bad-activator',{'activationGroup':'Brake >'},'invalid_expression'),('bad-group',{'activationGroup':'9'},'out_of_range'),('bad-boolean',{'invert':1},'invalid_boolean'),('bad-number',{'max':'NaN'},'invalid_number')]:
    before=s.read('craft.snapshot')
    result=s.apply({'kind':'part.update','partId':15,'changes':[{'path':'','attribute':'name','value':'TEMP rollback probe'}]},raw(15,**attributes),require=False,label=label)
    s.check(label+' rejects with expected code',not result['success'] and result['error']['code']==code)
    after=s.read('craft.snapshot')
    s.check(label+' recovers earlier valid mutation',result['rollbackResult']['restored'] and before['identity']['fingerprint']==after['identity']['fingerprint'])
s.guard('craft.rollback',checkpointId=formal_cp['id'])
final=s.read('craft.snapshot');s.check('Restored formal binding fingerprint',final['identity']['fingerprint']==formal['identity']['fingerprint'])
for i in (15,16):
    p=s.read('parts.get',flags=('--id',i))['part'];geom=s.read('parts.geometry',flags=('--id',i))
    s.check(f'{i} formal binding and mesh retained',states(p)['InputController.State']['input']=='Aileron' and len(geom['geometry']['renderers'])>0 and len(geom['geometry']['editorColliders'])>0)
conn=s.read('connections.list',flags=('--view','structured'));sym=s.read('symmetry.get')
s.check('Topology and symmetry groups retained',len(conn['connections'])==15 and any(g['id']==4 and {p['id'] for p in g['parts']}=={15,16} and all(p['enabled'] for p in g['parts']) for g in sym['groups']))
s.capture()
print('S06 checks',len(s.checks),'passed; image inspection still required')
