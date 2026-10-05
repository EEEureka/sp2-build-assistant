"""Independent review of recorded 0.4.10 turboprop build evidence."""
import json,math
from pathlib import Path
ROOT=Path(__file__).parent/'artifacts/staged-build/direct-0.4.10/final-verification'
checks=[]
def read(suffix):return json.loads(next(ROOT.glob('*-'+suffix+'.json')).read_text())['data']
def check(name,value):
    checks.append({'name':name,'pass':bool(value)})
    if not value:raise AssertionError(name)
snap=read('craft.snapshot');parts={p['id']:p for p in snap['parts']};centers=read('craft.centers')
connections=read('connections.list')['connections'];groups=read('symmetry.get')['groups']
geom={i:read('geometry-'+str(i))['geometry']['renderers'] for i in [1,7,8,19,20,25,26,27,28,29,30,31,33,35,36,38,40,42,43]}
details={i:read('part-'+str(i))['part'] for i in [33,35,36,40,42,43]}
fingerprints={json.loads(f.read_text()).get('data',{}).get('identity',{}).get('fingerprint') for f in ROOT.glob('[0-9]*.json') if not f.name.endswith('-input.json')}
check('all recorded final queries share one fingerprint',fingerprints=={snap['identity']['fingerprint']})
check('42 parts and 41 native connections',len(parts)==42 and len(connections)==41)
seen={3}
while True:
    before=len(seen)
    for c in connections:
        if c['partA'] in seen or c['partB'] in seen:seen.update((c['partA'],c['partB']))
    if len(seen)==before:break
check('all connected to flight computer',seen==set(parts))
check('16 active pairs',len(groups)==16 and all(len(g['parts'])==2 and all(p['enabled'] for p in g['parts']) for g in groups))
for a,b in [(31,38),(32,39),(33,40),(35,42),(36,43),(34,44),(37,41)]:
    pa,pb=parts[a]['position'],parts[b]['position']
    check('engine mirrored position '+str(a),max(abs(pa[0]+pb[0]),abs(pa[1]-pb[1]),abs(pa[2]-pb[2]))<1e-5)
for turbine,gear,prop in [(33,35,36),(40,42,43)]:
    check('turbine throttle '+str(turbine),details[turbine]['inputControllers'][0]['input']=='Throttle')
    check('propeller auto pitch '+str(prop),next(n for n in details[prop]['state']['children'] if n['element']=='PropellerAssembly.State')['attributes']['pitchControlType']=='Auto')
    check('manual/reverse controls explicitly neutral '+str(prop),all(i['input']=='Disabled' and i['min']==0 and i['max']==0 for i in details[prop]['inputControllers']))
    for a,b,ia,ib in [(turbine,gear,0,0),(gear,prop,1,0)]:
        x=next(p for p in details[a]['attachPoints'] if p['id']==ia);y=next(p for p in details[b]['attachPoints'] if p['id']==ib)
        check('native mechanical connection '+str(a)+'-'+str(b),b in x['connectedPartIds'] and a in y['connectedPartIds'])
        # FB-042: old DLL reads definition coordinates after native undo. The independently
        # queried live handle collider locations remain on the gearbox/propeller axis.
        ga=read('geometry-'+str(a))['geometry']['colliders'];gb=read('geometry-'+str(b))['geometry']['colliders']
        handles_a=[r['bounds']['center'] for r in ga if r['name']=='AttachPoint']
        handles_b=[r['bounds']['center'] for r in gb if r['name']=='AttachPoint']
        check('native handle colocation '+str(a)+'-'+str(b),min(math.dist(pa,pb) for pa in handles_a for pb in handles_b)<.003)
floor=[next(r for r in geom[i] if r['name'].startswith('Tire'))['bounds']['min'][1] for i in (26,28,30)]
check('three tire bottoms share designer level plane',max(floor)-min(floor)<1e-5)
clearances=[]
for prop in (36,43):
    center=parts[prop]['position']; blades=geom[prop][1:]
    check('four blade renderers '+str(prop),len(blades)==4)
    radius=max(math.hypot(x-center[0],y-center[1]) for b in blades for x in (b['bounds']['min'][0],b['bounds']['max'][0]) for y in (b['bounds']['min'][1],b['bounds']['max'][1]))
    zmin=min(b['bounds']['min'][2] for b in blades)
    wingfront=max(r['bounds']['max'][2] for i in (7,8,19,20) for r in geom[i])
    gearfront=max(r['bounds']['max'][2] for i in (25,26,27,28) for r in geom[i])
    fuselagewidth=geom[1][0]['bounds']['max'][0]
    c={'partId':prop,'nominalDiameterMetres':2.54,'stationaryMeshSpinRadiusUpperBound':radius,
       'spinEnvelopeGroundGapMetres':center[1]-radius-max(floor),
       'spinEnvelopeFuselageGapMetres':abs(center[0])-radius-fuselagewidth,
       'bladeAxialGapAheadWingAndSlatBoundsMetres':zmin-wingfront,
       'bladeAxialGapAheadMainGearBoundsMetres':zmin-gearfront}
    for k,v in c.items():
        if 'Gap' in k:check(str(prop)+' '+k,v>.25)
    clearances.append(c)
check('center scope includes all parts',centers['scope']['connectedPartCount']==42 and centers['scope']['disconnectedPartCount']==0)
check('two propeller center contributors',centers['centers']['cot']['contributorCount']==2)
check('single actual scene aircraft',read('designer.status')['sceneIntegrity']['status']=='healthy' and read('designer.status')['sceneIntegrity']['aircraftInstanceCount']==1)
report={'identity':snap['identity'],'passed':len(checks),'checks':checks,'clearances':clearances,
        'clearanceScope':'Conservative AABB bound of current blade meshes revolved around their common +Z axis, at current designer pitch. Ground uses level plane through rendered tyre bottoms. This is not full pitch/feather travel, strut compression, takeoff attitude, stress or flight validation.',
        'massKg':centers['centers']['com']['massKg'],'relations':centers['relations'],
        'nativeScreenshotFeature':'0.4.11 implemented separately; not loaded or accepted in this run.'}
(ROOT/'review.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('checks','relations')},indent=2))
