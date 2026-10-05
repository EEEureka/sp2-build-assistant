"""Actual camera-state setup through compile-only acceptance hooks.

Not evidence that the game's player UI can set FOV/optical-axis roll. The public
sp2build capture runs against that actual baseline and must restore it through
two native frames; the enclosing test fixture then restores the original view.
"""
import itertools,json,math,sys
from pathlib import Path
from precision_acceptance import Run

r=Run(sys.argv[1]);config=Path('D:/apps/steam/steamapps/common/SimplePlanes 2/BepInEx/config')
profile={'fieldOfViewDegrees':float(sys.argv[2]) if len(sys.argv)>2 else 37.5,'rollDegrees':float(sys.argv[3]) if len(sys.argv)>3 else 17.4}
setup=config/'sp2build.acceptance-camera.json';fault=config/'sp2build.acceptance-fault.json'
assert not setup.exists() and not fault.exists(),'Do not replace pending acceptance requests'
def call(n,c,a=None,images=False):
    x=r.call(n,c,a,images=images);assert x['success'],x;return x['data']
status=call('status','designer.status');assert status['registryVersion']=='0.5.0-dev16'
b=call('baseline','craft.snapshot',{'includeXml':True});assert b['name'].startswith('SP2Build 050 Precision Lab')
i=b['identity'];guard={'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
history=call('history-before','craft.history');selection=call('selection-before','designer.selection')
limits=[(min(p['position'][k] for p in b['parts']),max(p['position'][k] for p in b['parts'])) for k in range(3)]
points=[list(p) for p in itertools.product(*[[(lo+hi)/2+v*max(.5,hi-lo) for v in (-.25,0,.25)] for lo,hi in limits])]
def mv(m,v):return [sum(a*b for a,b in zip(row,v)) for row in m]
def pixel(c,p):
    v=mv(c['projectionRows'],mv(c['worldToCameraRows'],p+[1]));assert abs(v[3])>1e-8
    return [(v[0]/v[3]+1)*1280,(v[1]/v[3]+1)*800]
def angle(a,b):
    cosine=abs(sum(x*y for x,y in zip(a,b)))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return math.degrees(2*math.acos(min(1,cosine)))
def rolled(q,deg):
    x,y,z,w=q;s=math.sin(math.radians(deg)/2);c=math.cos(math.radians(deg)/2)
    return [x*c+y*s,y*c-x*s,z*c+w*s,w*c-z*s]
def comparison(a,b):
    return {'positionErrorMetres':math.dist(a['positionWorld'],b['positionWorld']),
        'rotationErrorDegrees':angle(a['rotationQuaternion'],b['rotationQuaternion']),
        'maxControlPointPixelError':max(math.dist(pixel(a,p),pixel(b,p)) for p in points),
        'exactFields':all(a[k]==b[k] for k in ('projection','rect','targetTextureInstanceId','enabled','cullingMask','clearFlags','parentInstanceId','cameraInstanceId')),
        'scalarFields':all(abs(a[k]-b[k])<=1e-6 for k in ('fieldOfViewDegrees','orthographicSize','aspect','nearClipMetres','farClipMetres'))}
def valid(row):return row['positionErrorMetres']<=.0001 and row['rotationErrorDegrees']<=.001 and row['maxControlPointPixelError']<=.1 and row['exactFields'] and row['scalarFields']
def capture(n,views):return call(n,'designer.capture',{**guard,'views':views,'resolution':{'width':1280,'height':800}},images=True)
def manifest(data):return json.loads(Path(data['manifestPath']).read_text(encoding='utf-8-sig'))
original=manifest(capture('original',['current']))['cameraBefore']
views=[{'view':v,'projection':'perspective' if v=='isometric' else 'orthographic'} for v in ('front','right','top','isometric')]
observations=[]
try:
    for j in range(10):
        setup.write_text(json.dumps(profile),encoding='utf-8')
        m=manifest(capture(f'four-{j:02}',views));a=m['cameraBefore']
        r.check(f'fixture-{j:02} actually active',abs(a['fieldOfViewDegrees']-profile['fieldOfViewDegrees'])<=1e-6 and angle(a['rotationQuaternion'],rolled(original['rotationQuaternion'],profile['rollDegrees']))<=.001,{'requested':profile,'actual':a})
        frames=[m['cameraAfter']]+[f['cameraState'] for f in m['restorationDiagnostics']['followingFrames']]
        rows=[comparison(a,f) for f in frames]
        r.check(f'fixture-{j:02} recovered through two frames',len(rows)==3 and all(valid(x) for x in rows),rows)
        observations.append({'cycle':j,'requested':profile,'checks':rows})
        assert not setup.exists(),'Fixture was not consumed'
    setup.write_text(json.dumps(profile),encoding='utf-8')
    fault.write_text(json.dumps({'stage':'capture_render_1'}),encoding='utf-8')
    x=r.call('injected-render-failure','designer.capture',{**guard,'views':views})
    r.check('real render failure reached',not x['success'] and x.get('error',{}).get('code')=='acceptance_injected_failure',x.get('error'))
    assert not x['success'] and x['error']['code']=='acceptance_injected_failure',x
    d=x['error']['details'];rows=[comparison(d['cameraBefore'],f) for f in [d['cameraAfter']]+[z['cameraState'] for z in d['followingFrames']]]
    r.check('nondefault baseline restored after render failure',len(rows)==3 and all(valid(z) for z in rows),rows)
finally:
    # Only these exact named test files; never delete arbitrary configuration.
    for p in (setup,fault):
        if p.exists():p.unlink()
    end=manifest(capture('original-after',['current']));row=comparison(original,end['cameraBefore'])
    r.check('enclosing fixture restores original player camera',valid(row),row)
    r.check('complete aircraft unchanged',call('after','craft.snapshot',{'includeXml':True})['xml']==b['xml'])
    r.check('native and plugin history unchanged',call('history-after','craft.history')==history)
    r.check('selection unchanged',call('selection-after','designer.selection')==selection)
(r.root/'independent-camera-audit.json').write_text(json.dumps({'controlPoints':points,'viewport':[2560,1600],'observations':observations,'checks':r.checks,'setupMeaning':__doc__},indent=2))
