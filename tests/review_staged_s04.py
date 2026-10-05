"""Independent captured-evidence review of S04; not 0.4.6 acceptance."""
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator

root=Path(__file__).parents[1]
source=Path('D:/codeSpace/sp2_craft_edit/staged-build/S04')
load=lambda name:json.loads((source/name).read_text(encoding='utf-8-sig'))
checks=[]
def check(name,value):checks.append({'name':name,'pass':bool(value)})
def near(a,b,tol=1e-5):return len(a)==len(b) and all(abs(x-y)<tol for x,y in zip(a,b))
spec=importlib.util.spec_from_file_location('s04_contracts',root/'cli/contracts.py')
contracts=importlib.util.module_from_spec(spec);spec.loader.exec_module(contracts)
partsdata=load('parts-list-final.json')['data']; identity=partsdata['identity']; parts={p['id']:p for p in partsdata['listing']['items']}
for path in sorted(source.glob('*-final.json')):
    if '-elev-' in path.name:continue # rev23 intermediate, not final rev29
    j=load(path.name);check(path.name+' identity',j['success'] and j['data'].get('identity')==identity)
    command=next((cmd for prefix,cmd in [('assembly-','parts.assembly'),('geometry-','parts.geometry'),('shape-','shape.get'),('centers-','craft.centers'),('connections-','connections.list'),('symmetry-','symmetry.get'),('parts-list-','parts.list'),('capabilities-','capabilities')] if path.name.startswith(prefix)),None)
    if command:check(path.name+' schema',not list(Draft202012Validator(contracts.output_schema(command)).iter_errors(j)))
connections=load('connections-final.json')['data']['connections'];seen={3}
while True:
    added={n for c in connections if c['partA'] in seen or c['partB'] in seen for n in [c['partA'],c['partB']]}-seen
    if not added:break
    seen.update(added)
check('12 parts all connected by 11 edges',len(parts)==12 and seen==set(parts) and len(connections)==11)
for wing,control in [(9,10),(11,12)]:
    s=load(f'shape-{wing}-final.json')['data']['shape'];c=load(f'shape-{control}-final.json')['data']['shape']
    check(f'Wing {wing} owns only elevator {control}',[x['partId'] for x in s['controlSurfaces']]==[control] and c['wingPartId']==wing)
    check(f'Wing {wing} bounded assembly',set(load(f'assembly-{wing}-final.json')['data']['assembly']['memberPartIds'])=={wing,control})
    check(f'Wing {wing} stations/airfoils',near([x['spanPosition'] for x in s['configuration']['sections']],[0,.6,1.2,1.8]) and all(x['airfoil']=='NACA0012' for x in s['configuration']['sections']))
    check(f'Elevator {control} restored dimensions',c['style']=='StandardFlap' and c['configuration']['maxDeflectionDegrees']==25 and near(c['configuration']['spanRange'],[.1,1.7]) and near(c['chordFraction'],[.3,.3]))
    link=next(c for c in connections if {c['partA'],c['partB']}=={wing,control})
    check(f'Elevator {control} final surface connection',link['attachPointsA' if link['partA']==wing else 'attachPointsB']==[1])
x0=parts[3]['position'][0]
for a,b in [(9,11),(10,12)]:
    check(f'{a}/{b} mirrored positions',near(parts[b]['position'],[2*x0-parts[a]['position'][0],*parts[a]['position'][1:]]))
    def bounds(i):
        rows=load(f'geometry-{i}-final.json')['data']['geometry']['renderers']
        return ([min(r['bounds']['min'][j] for r in rows) for j in range(3)],[max(r['bounds']['max'][j] for r in rows) for j in range(3)])
    amin,amax=bounds(a);bmin,bmax=bounds(b)
    check(f'{a}/{b} mirrored mesh bounds',near(bmin,[2*x0-amax[0],*amin[1:]],1e-4) and near(bmax,[2*x0-amin[0],*amax[1:]],1e-4))
centers=load('centers-contributors-final.json')['data'];rows=centers['contributors']['items'];mass=[r for r in rows if r['metric']=='mass'];lift=[r for r in rows if r['metric']=='lift']
total=sum(r['massKg'] for r in mass)
check('Mass from all 12 sources',len(mass)==12 and abs(total-centers['centers']['com']['massKg'])<1e-6)
check('Four wing lift sources, no thrust',{r['part']['id'] for r in lift}=={7,8,9,11} and centers['centers']['cot']['status']=='unavailable')
check('Lateral CoM/CoL centered',abs(centers['centers']['com']['positionWorldMeters'][0]-x0)<1e-5 and abs(centers['centers']['col']['positionWorldMeters'][0]-x0)<1e-5)
old=load('part-11-preconnect.json')['data']['part']['attachPoints'];fixed=load('part-11-after-elev2.json')['data']['part']['attachPoints']
check('Defect: control consumed free structural root',old[0]['connectedPartIds']==[12] and not old[0]['surface'] and old[1]['surface'] and old[1]['connectedPartIds']==[])
check('Order workaround leaves proper native attachment',fixed[0]['connectedPartIds']==[5] and fixed[1]['connectedPartIds']==[12])
for name in ['batch-e2-connect-left-idx0.response.json','batch-e3-connect-left-idx1.response.json']:
    j=load(name);check(name+' expected rejection restored',not j['success'] and j['error']['code']=='invalid_connection' and j['rollbackResult']['restored'] and j['rollbackResult']['fingerprintIdentical'])
report={'identity':identity,'passed':sum(c['pass'] for c in checks),'total':len(checks),'checks':checks,'boundary':'S04 built under DLL 0.4.4, using an order workaround. New 0.4.6 attachment selection still requires restart and acceptance; no flight-direction or stability test.'}
out=root/'tests/artifacts/staged-build/S04-review/independent-review.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[c for c in checks if not c['pass']]}))
raise SystemExit(any(not c['pass'] for c in checks))
