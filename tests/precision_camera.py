"""Live native capture plus independent projection restoration audit.

Uses plain double-precision matrix arithmetic, not bridge CameraState.Compare.
Pixel error is conservatively measured in a 2560x1600 viewport (native aspect
1.6); record the actual viewport separately if a different display is used.
"""
import itertools,json,math,sys
from pathlib import Path
from precision_acceptance import Run
r=Run(sys.argv[1])
before=r.call('baseline','craft.snapshot',{'includeXml':True})['data']
assert before['name'].startswith('SP2Build 050 Precision Lab')
identity=before['identity'];guard={'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
history=r.call('history-before','craft.history')['data']
selection=r.call('selection-before','designer.selection')['data']
# Derive control points from this aircraft, rather than reusing F2 coordinates
# for the much larger C17. These are independent world-space test points, not
# results from the bridge's camera comparison implementation.
positions=[p['position'] for p in before['parts']]
limits=[(min(p[k] for p in positions),max(p[k] for p in positions)) for k in range(3)]
axes=[[(a+b)/2+f*max(.5,b-a) for f in (-.25,0,.25)] for a,b in limits]
points=[list(p) for p in itertools.product(*axes)]

def mv(m,v):return [sum(x*y for x,y in zip(row,v)) for row in m]
def pixel(c,p):
    clip=mv(c['projectionRows'],mv(c['worldToCameraRows'],p+[1]))
    assert abs(clip[3])>1e-8
    return [(clip[0]/clip[3]+1)*1280,(clip[1]/clip[3]+1)*800]
def angle(a,b):
    dot=abs(sum(x*y for x,y in zip(a,b)))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return math.degrees(2*math.acos(min(1,dot)))
def audit(label,result):
    assert result['success'],result
    m=json.loads(Path(result['data']['manifestPath']).read_text(encoding='utf-8-sig'))
    a=m['cameraBefore'];frames=[m['cameraAfter']]+[f['cameraState'] for f in m['restorationDiagnostics']['followingFrames']]
    assert len(frames)==3
    rows=[]
    for b in frames:
        rows.append({'positionErrorMetres':math.dist(a['positionWorld'],b['positionWorld']),
          'rotationErrorDegrees':angle(a['rotationQuaternion'],b['rotationQuaternion']),
          'maxControlPointPixelError':max(math.dist(pixel(a,p),pixel(b,p)) for p in points),
          'exactFields':all(a[k]==b[k] for k in ['projection','rect','targetTextureInstanceId','cullingMask','clearFlags','enabled','parentInstanceId','cameraInstanceId']),
          'scalarFields':all(abs(a[k]-b[k])<=1e-6 for k in ['fieldOfViewDegrees','orthographicSize','aspect','nearClipMetres','farClipMetres'])})
    r.check(label+' independent camera recovery',all(x['positionErrorMetres']<=.0001 and x['rotationErrorDegrees']<=.001 and x['maxControlPointPixelError']<=.1 and x['exactFields'] and x['scalarFields'] for x in rows),rows)
    r.check(label+' scene one',result['data']['sceneIntegrity']['aircraftInstanceCount']==1)
    return m
views=[{'view':v,'projection':'orthographic'} for v in ('front','right','top')]+[{'view':'isometric','projection':'perspective'}]
for i in range(int(sys.argv[2]) if len(sys.argv)>2 else 10):
    x=r.call('four-%02d'%i,'designer.capture',{**guard,'views':views,'resolution':{'width':1280,'height':800}},images=True)
    m=audit('four-%02d'%i,x)
    r.check('four-%02d projection modes'%i,[v['camera']['projection'] for v in m['views']]==['orthographic']*3+['perspective'])
extra=[{'view':v,'projection':'orthographic'} for v in ('back','left','bottom')]+[{'view':'current'},
 {'view':'custom','azimuthDegrees':31.7,'elevationDegrees':22.3,'rollDegrees':17.4,'projection':'perspective','fieldOfViewDegrees':37.5}]
x=r.call('other-views','designer.capture',{**guard,'views':extra,'resolution':{'width':900,'height':1200}},images=True)
if x['success']:audit('other-views',x)
else:r.check('other-views',False,x)
for label,patch in [('old-revision',{'expectedRevision':identity['revision']+100}),('bad-direction',{'views':[{'view':'custom','direction':[0,0,0]}]}),('budget',{'views':['front']*8,'resolution':{'width':2048,'height':2048}})]:
    x=r.call(label,'designer.capture',{**guard,'views':['front'],'resolution':{'width':800,'height':600},**patch})
    r.check(label+' rejected',not x['success'],x.get('error'))
x=r.call('after-errors','designer.capture',{**guard,'views':['current'],'resolution':{'width':1280,'height':800}},images=True);audit('after-errors',x)
after=r.call('after','craft.snapshot',{'includeXml':True})['data']
r.check('complete XML unchanged',before['xml']==after['xml'])
r.check('history unchanged',history==r.call('history-after','craft.history')['data'])
r.check('selection unchanged',selection==r.call('selection-after','designer.selection')['data'])
(r.root/'projection-audit.json').write_text(json.dumps({'controlPoints':points,'viewport':[2560,1600],'checks':r.checks},indent=2),encoding='utf-8')
