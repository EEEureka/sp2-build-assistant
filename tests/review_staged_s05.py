"""Review S05 actual saved evidence, keeping rev14 and rev15 separate."""
import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from jsonschema import Draft202012Validator

root=Path(__file__).parents[1]
source=Path('D:/codeSpace/sp2_craft_edit/staged-build/S05')
load=lambda n:json.loads((source/n).read_text(encoding='utf-8-sig'))
checks=[]
def check(name,value):checks.append({'name':name,'pass':bool(value)})
def near(a,b,tol=1e-5):return len(a)==len(b) and all(abs(x-y)<tol for x,y in zip(a,b))
spec=importlib.util.spec_from_file_location('s05_contracts',root/'cli/contracts.py')
contracts=importlib.util.module_from_spec(spec);spec.loader.exec_module(contracts)
final=load('snapshot-after-lower.json')['data'];identity=final['identity']
parts={p['id']:p for p in final['parts']}
start={p['id']:p for p in load('parts-list-start.json')['data']['listing']['items']}
check('Expected only two permanent new parts',set(parts)-set(start)=={13,14} and len(parts)==14)
for i,old in start.items():
    check(f'Original part {i} pose/type/material/group preserved',all(parts[i][k]==old[k] for k in ['type','name','position','rotationEulerDegrees','scale','materialIds','symmetryId']))
for name,command in [('parts-list-final.json','parts.list'),('connections-final.json','connections.list'),('symmetry-after-lower.json','symmetry.get'),
                     ('part-13-after-lower.json','parts.get'),('part-14-after-lower.json','parts.get'),
                     ('geometry-13-after-lower.json','parts.geometry'),('geometry-14-after-lower.json','parts.geometry'),
                     ('assembly-13-final.json','parts.assembly'),('centers-final15.json','craft.centers')]:
    j=load(name)
    check(name+' final identity',j['success'] and j['data']['identity']==identity)
    check(name+' schema',not list(Draft202012Validator(contracts.output_schema(command)).iter_errors(j)))
connections=load('connections-final.json')['data']['connections'];seen={3}
while True:
    added={n for c in connections if c['partA'] in seen or c['partB'] in seen for n in [c['partA'],c['partB']]}-seen
    if not added:break
    seen.update(added)
check('14 parts connected by 13 edges',len(connections)==13 and seen==set(parts))
def link(a,b,ap,bp):
    return any((c['partA'],c['partB'],c['attachPointsA'],c['attachPointsB']) in [(a,b,[ap],[bp]),(b,a,[bp],[ap])] for c in connections)
check('Wing root to tail host, rudder to wing surface',link(13,5,0,2) and link(14,13,0,1))
check('Bounded vertical-tail assembly',set(load('assembly-13-final.json')['data']['assembly']['memberPartIds'])=={13,14})
check('Original symmetry groups unchanged',load('symmetry-after-lower.json')['data']['groups']==load('symmetry-start.json')['data']['groups'])
check('Vertical wing centered, upright and lowered',abs(parts[13]['position'][0])<1e-5 and near(parts[13]['rotationEulerDegrees'],[0,0,90]) and abs(parts[13]['position'][1]-2.858)<1e-5)
oldrudder=load('part-14-after-connect.json')['data']['part'];rudder=load('part-14-after-lower.json')['data']['part']
check('Native rudder follows wing movement',near(rudder['position'],[oldrudder['position'][0],oldrudder['position'][1]-.217,oldrudder['position'][2]]))
xml=ET.fromstring(final['xml']);p13=xml.find('.//Part[@id="13"]');p14=xml.find('.//Part[@id="14"]')
wing=p13.find('JWing.State');control=p14.find('ControlSurfacePart.State');inputs=p14.find('InputController.State')
check('Vertical fin symmetric airfoil, 1.8m span',all(s.get('airfoil')=='Symmetric' for s in wing.findall('Slice')) and float(wing.findall('Slice')[-1].get('position'))==1.8)
check('Rudder restored native shape settings',control.get('style')=='StandardFlap' and control.get('range')=='0.15,1.7' and control.get('maxDeflection')=='25')
check('Rudder Yaw controller verified from final XML',all(inputs.get(k)==v for k,v in {'input':'Yaw','invert':'false','min':'-1','max':'1','activationGroup':'0','zeroOnDeactivate':'false'}.items()))
geom=load('geometry-13-after-lower.json')['data']['geometry']['renderers'][0]['bounds']
check('Vertical mesh dimensions',near(geom['size'],[.192,1.8,1.66],1e-4) and abs(geom['min'][1]-2.858)<1e-5)
for path in sorted(source.glob('ray-check-skin-*.json')):
    j=load(path.name)
    if not j.get('success'):continue
    check(path.name+' local skin above wing root',j['data']['identity']==identity and any(h['partId']==5 and h['point'][1]>geom['min'][1] for h in j['data']['hits']))
ray=load('ray-inside-2.95_-4.6.json')['data']
check('Independent horizontal ray intersects wing and body at root',ray['identity']==identity and {5,13}.issubset({h['partId'] for h in ray['hits']}))
centers=load('centers-final15.json')['data'];mass=[r for r in centers['contributors']['items'] if r['metric']=='mass'];lift=[r for r in centers['contributors']['items'] if r['metric']=='lift']
total=sum(r['massKg'] for r in mass)
check('Mass reconstructed from all fourteen parts',len(mass)==14 and abs(total-centers['centers']['com']['massKg'])<1e-6)
check('Vertical fin included with near-zero world-up projection',len(lift)==5 and any(r['part']['id']==13 and r['included'] and r['nativeWeight']<1e-6 for r in lift))
check('No propulsion sources yet',centers['centers']['cot']['reasonCodes']==['no_sources'])
check('Final checkpoint fingerprint',load('checkpoint-end.json')['data']['fingerprint']==identity['fingerprint'])
capture=load('capture-tail2-envelope.json')['data']
check('Final tail capture shares revision and is complete',capture['identity']==identity and capture['complete'] and not capture['staleAtDelivery'])
check('Final capture image exists',all(Path(p).is_file() for p in capture['recommendedImages']))
report={'identity':identity,'passed':sum(c['pass'] for c in checks),'total':len(checks),'checks':checks,'boundary':'Static designer configuration, final XML, mesh/ray evidence. Rev14 gap and rev15 corrected joint images opened separately; no flight or stability assessment.'}
out=root/'tests/artifacts/staged-build/S05-review/independent-review.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[c for c in checks if not c['pass']]}))
raise SystemExit(any(not c['pass'] for c in checks))
