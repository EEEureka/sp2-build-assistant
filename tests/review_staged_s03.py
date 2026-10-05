"""Review captured S03 evidence, without any game writes or new captures."""
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from jsonschema import Draft202012Validator

root = Path(__file__).parents[1]
stage = Path('D:/codeSpace/sp2_craft_edit/staged-build/S03')
source = stage / 'final-rev24'
load = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
checks = []

def check(name, value):
    checks.append({'name': name, 'pass': bool(value)})

def near(a, b, tol=1e-5):
    return len(a) == len(b) and all(abs(x-y) < tol for x,y in zip(a,b))

spec = importlib.util.spec_from_file_location('s03_contracts',root/'cli/contracts.py')
contracts = importlib.util.module_from_spec(spec); spec.loader.exec_module(contracts)
snapshot = load(source/'snapshot.json')['data']; identity = snapshot['identity']
for path in sorted(source.glob('*.json')):
    j = load(path)
    if 'success' not in j: continue
    check(path.name+' final identity',j['success'] and j['data'].get('identity')==identity)
    command = next((cmd for prefix,cmd in [('geometry-','parts.geometry'),('shape-','shape.get'),('part-','parts.get'),('ray-output-','designer.raycast')] if path.name.startswith(prefix)),None)
    command = command or {'snapshot.json':'craft.snapshot','centers-contributors.json':'craft.centers','centers-summary.json':'craft.centers','connections-structured.json':'connections.list','designer-status.json':'designer.status','history.json':'craft.history','parts-list.json':'parts.list','symmetry.json':'symmetry.get'}.get(path.name)
    if command:
        check(path.name+' output schema',not list(Draft202012Validator(contracts.output_schema(command)).iter_errors(j)))
parts = {p['id']:p for p in snapshot['parts']}
connections = load(source/'connections-structured.json')['data']['connections']
seen = {3}
while True:
    added = {n for c in connections if c['partA'] in seen or c['partB'] in seen for n in (c['partA'],c['partB'])}-seen
    if not added: break
    seen.update(added)
check('8 parts fully connected by 7 edges',len(parts)==8 and seen==set(parts) and len(connections)==7)
x0 = parts[3]['position'][0]
check('Main control and trunk share symmetry X',abs(x0-parts[1]['position'][0])<1e-6)
check('Correct final reflected origins',near(parts[8]['position'],[2*x0-parts[7]['position'][0],*parts[7]['position'][1:]]))
geometries = {i:load(source/f'geometry-{i}.json')['data']['geometry'] for i in parts}
b7 = geometries[7]['renderers'][0]['bounds']; b8 = geometries[8]['renderers'][0]['bounds']
check('Wing mesh reflected min',near(b8['min'],[2*x0-b7['max'][0],*b7['min'][1:]],1e-4))
check('Wing mesh reflected max',near(b8['max'],[2*x0-b7['min'][0],*b7['max'][1:]],1e-4))
check('Measured width 12.8334 m',abs(b7['max'][0]-b8['min'][0]-12.8334)<1e-4)
s7 = load(source/'shape-7.json')['data']['shape']['configuration']; s8 = load(source/'shape-8.json')['data']['shape']['configuration']
check('Sections identical, flipped opposites',s7['sections']==s8['sections'] and not s7['flipped'] and s8['flipped'])
group = load(source/'symmetry.json')['data']['groups']
check('Exactly two enabled main wing peers',len(group)==1 and {p['id'] for p in group[0]['parts']}=={7,8} and all(p['enabled'] for p in group[0]['parts']))
c = load(source/'centers-contributors.json')['data']
rows = c['contributors']['items']; mass = [r for r in rows if r['metric']=='mass']; lift = [r for r in rows if r['metric']=='lift']
total = sum(r['massKg'] for r in mass)
weighted = [sum(r['massKg']*r['positionWorldMeters'][i] for r in mass)/total for i in range(3)]
check('CoM agrees with native mass contributors',abs(total-c['centers']['com']['massKg'])<1e-8 and near(weighted,c['centers']['com']['positionWorldMeters'],1e-6))
check('CoM and CoL lie on lateral symmetry plane',abs(c['centers']['com']['positionWorldMeters'][0]-x0)<1e-5 and abs(c['centers']['col']['positionWorldMeters'][0]-x0)<1e-5)
check('Two equal lift weights and no thrust',len(lift)==2 and {r['part']['id'] for r in lift}=={7,8} and abs(lift[0]['nativeWeight']-lift[1]['nativeWeight'])<1e-5 and c['centers']['cot']['status']=='unavailable')
local = {i:load(source/f'part-{i}.json')['data']['part']['state']['attributes']['centerOfMass'].split(',') for i in [7,8]}
check('Observed native flipped-wing local CoM Y zero',abs(float(local[7][1])-.1585702)<1e-6 and float(local[8][1])==0)
aircraft = ET.fromstring(snapshot['xml'])
if aircraft.tag!='Aircraft': aircraft = aircraft.find('.//Aircraft')
check('Native XML save-time width is stale',abs(float(aircraft.attrib['size'].split(',')[0])-7.066614)<1e-5)
bad = load(stage/'bad-mirror/snapshot-rev15.json')['data']; badparts = {p['id']:p for p in bad['parts']}
oldconfig = load(stage/'symmetry-get-raw.json')['data']['configuration']
check('First wrong mirror used old x=0, not current body plane',oldconfig['mirrorPlaneDistance']==0 and abs(badparts[8]['position'][0]+badparts[7]['position'][0])<1e-6 and abs(x0)>1)
failure = load(stage/'bad-mirror/batch-e-failed.response.json'); rb = failure['rollbackResult']
check('Observed mid-batch failure restored identical state',not failure['success'] and failure['error']['code']=='symmetry_not_found' and rb['restored'] and rb['fingerprintIdentical'] and rb['beforeFingerprint']==rb['currentFingerprint'] and not rb['revisionChanged'])
for name,peers in [('t1-sync-on',[8]),('t1b-restore',[8]),('t2b-single-side',[]),('t2c-restore-single',[])]:
    result = load(stage/f'batches/{name}.response.json')
    check(name+' recorded propagation result',result['success'] and result['data']['actualChanges'][0]['synchronizedPartIds']==peers)
for name,enabled in [('t2-disable',False),('t3-reenable',True)]:
    result = load(stage/f'batches/{name}.response.json'); change = result['data']['actualChanges'][0]
    check(name+' recorded enable result',result['success'] and change['enabled']==enabled and set(change['partIds'])=={7,8})
restore = load(stage/'batches/t1b-restore.response.json')['data']['identity']['fingerprint']
check('Final reenable restores same entire craft fingerprint',restore==identity['fingerprint'])
ray2 = load(source/'ray-output-L2.json')['data']['hits'][0]; ray3 = load(source/'ray-output-L3.json')['data']['hits'][0]
check('Both outer ray hits mirror in X',ray2['partId']==8 and ray3['partId']==7 and near(ray2['point'],[2*x0-ray3['point'][0],*ray3['point'][1:]],1e-4))
report = {'stage':'S03','identity':identity,'passed':sum(c['pass'] for c in checks),'total':len(checks),'checks':checks,
          'boundaries':'Evidence from old DLL 0.4.0; does not accept 0.4.4 stale-cache fix. Intermediate sync results are mutation responses, not independently archived shape readbacks. Native CoM bug remains. No stability/flight test.'}
out = root/'tests/artifacts/staged-build/S03-review/independent-review.json'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[c for c in checks if not c['pass']]}))
raise SystemExit(any(not c['pass'] for c in checks))
