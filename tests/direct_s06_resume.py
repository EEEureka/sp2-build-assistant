from direct_build import Session, raw, states, ROOT
import json

s=Session('S06-retest')
formal_cps=[]
for path in s.path.glob('*-craft.checkpoint.create.json'):
    d=json.loads(path.read_text())['data']
    if d.get('name')=='S06 formal Aileron binding': formal_cps.append(d)
assert len(formal_cps)==1, formal_cps
formal_cp=formal_cps[0]
p=s.read('parts.get',flags=('--id',15))['part']; tested=states(p)['InputController.State']
s.check('Six explicit fields read back',all(tested[k]==v for k,v in {'input':'clamp(Aileron,-1,1)','activationGroup':'Brake > 0','invert':'true','min':'1','max':'-1','invertType':'Output'}.items()))
s.check('True default omitted from XML: effective-value readout needed','zeroOnDeactivate' not in tested)
for label,attributes,code in [('bad-expression',{'input':'clamp('},'invalid_expression'),('bad-activator',{'activationGroup':'Brake >'},'invalid_expression'),('bad-group',{'activationGroup':'9'},'out_of_range'),('bad-boolean',{'invert':1},'invalid_boolean'),('bad-number',{'max':'NaN'},'invalid_number')]:
    before=s.read('craft.snapshot')
    result=s.apply({'kind':'part.update','partId':15,'changes':[{'path':'','attribute':'name','value':'TEMP rollback probe'}]},raw(15,**attributes),require=False,label=label)
    s.check(label+' rejects with expected code',not result['success'] and result['error']['code']==code)
    after=s.read('craft.snapshot')
    s.check(label+' recovers earlier valid mutation',result['rollbackResult']['restored'] and before['identity']['fingerprint']==after['identity']['fingerprint'])
s.guard('craft.rollback',checkpointId=formal_cp['id'])
final=s.read('craft.snapshot');s.check('Restored formal binding fingerprint',final['identity']['fingerprint']==formal_cp['fingerprint'])
for i in (15,16):
    p=s.read('parts.get',flags=('--id',i))['part'];geom=s.read('parts.geometry',flags=('--id',i))
    s.check(f'{i} formal binding and mesh retained',states(p)['InputController.State']['input']=='Aileron' and len(geom['geometry']['renderers'])>0 and len(geom['geometry']['editorColliders'])>0)
conn=s.read('connections.list',flags=('--view','structured'));sym=s.read('symmetry.get')
s.check('Topology and symmetry groups retained',len(conn['connections'])==15 and any(g['id']==4 and {p['id'] for p in g['parts']}=={15,16} and all(p['enabled'] for p in g['parts']) for g in sym['groups']))
s.capture()
print('S06 checks',len(s.checks),'passed; image inspection still required')
