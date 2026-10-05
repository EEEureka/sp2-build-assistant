"""Live material bounds, inheritance, omission and atomic rejection.

These checks supplement native UI comparison; they do not certify visual night
emission or the full matrix. Only a recorded same-session F2 fixture is used.
"""
import copy,json,sys,uuid,xml.etree.ElementTree as ET
from precision_acceptance import Run,ROOT

r=Run(sys.argv[1]);prep=ROOT/sys.argv[2]
fixture=json.loads((prep/'fixture.json').read_text(encoding='utf-8-sig'))
ids=fixture['partIds'];mid=fixture['materialId']

def call(n,c,a=None):
    result=r.call(n,c,a);assert result['success'],result;return result['data']

def snap(n):
    s=call(n,'craft.snapshot',{'includeXml':True})
    assert s['name']=='SP2Build 050 Precision Lab F2' and not s['identity']['stateUncertain']
    return s

def guard():
    i=call('guard-'+str(len(r.calls)),'designer.status')['identity']
    return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}

def op(patch):return {'kind':'appearance.set','mode':'shared','materialId':mid,'patch':patch}
def apply(n,patch):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[op(patch)]})
def restore(n,cp):call(n,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
def appearance(n):return call(n,'appearance.get',{'partIds':ids})
def material(a):return next(m for m in a['palette'] if m['id']==mid)
def outside(xml):
    root=ET.fromstring(xml)
    theme=root.find('Theme')
    assert theme is not None
    # Native XML uses ordered materials (including hidden reserved entries),
    # not public material IDs. This fixture has one deliberately unique name.
    matches=[m for m in theme.findall('Material') if m.get('name')=='UI Parity']
    assert len(matches)==1
    for parent in theme.iter():
        if matches[0] in list(parent):parent.remove(matches[0]);break
    return ET.tostring(root,encoding='unicode')

original=snap('original');assert original['partCount']==3
try:
    restore('fixture',fixture['checkpointId'])
    baseline=snap('fixture-baseline');look=appearance('initial-appearance')
    texture=call('textures','resources.list',{'category':'textures','limit':1000})
    assert texture['offset']==0 and texture['total']==len(texture['items'])
    flat=next(t for t in texture['items'] if t['available'] and t['paintStyle']=='SinglePlaneTextureColorMask')
    apply('flat-setup',{'style':'SinglePlaneTextureColorMask','textureId':flat['id']})
    state=appearance('flat-state');base_material=material(state)
    # Native numeric extrema plus per-colour override/inheritance.
    for label,patch in [
        ('lower',{'metallic':0,'smoothness':0,'emissionDay':0,'emissionNight':0,'textureBlend':0,
                  'textureOffset':[-10000,-10000,-10000],'textureRotation':[-360,-360,-360],
                  'textureScale':[.0001,.0001,.0001],
                  'colors':[{'index':0,'rgba':[0,0,0,0],'metallic':0,'smoothness':0,'emissionDay':0,'emissionNight':0}]}),
        ('upper',{'metallic':1,'smoothness':1,'emissionDay':5,'emissionNight':5,'textureBlend':1,
                  'textureOffset':[10000,10000,10000],'textureRotation':[360,360,360],
                  'textureScale':[10000,10000,10000],
                  'colors':[{'index':0,'rgba':[1,1,1,1],'metallic':1,'smoothness':1,'emissionDay':5,'emissionNight':5}]}),
        ('inherit',{'colors':[{'index':0,'metallic':None,'smoothness':None,'emissionDay':None,'emissionNight':None}]}),
    ]:
        prior=material(appearance(label+'-before'))
        out=apply(label,patch);effective=material(appearance(label+'-after'))
        expected=copy.deepcopy(prior)
        for k,v in patch.items():
            if k=='colors':
                for c in v:expected[k][c['index']].update(c)
            else:expected[k]=v
        def close(a,b):
            if isinstance(a,dict):return a.keys()==b.keys() and all(close(a[k],b[k]) for k in a)
            if isinstance(a,list):return len(a)==len(b) and all(close(x,y) for x,y in zip(a,b))
            if isinstance(a,(float,int)) and not isinstance(a,bool):return abs(a-b)<=1e-6
            return a==b
        r.check(label+' full effective material and omitted fields',close(effective,expected),{'expected':expected,'effective':effective})
        r.check(label+' exact affected users',sorted(out['actualChanges'][0]['affectedPartIds'])==sorted(ids))
        r.check(label+' all nonmaterial XML unchanged',outside(snap(label+'-snapshot')['xml'])==outside(baseline['xml']))
    negative=[('metal-low',{'metallic':-.01}),('metal-high',{'metallic':1.01}),
        ('smooth-low',{'smoothness':-.01}),('smooth-high',{'smoothness':1.01}),
        ('day-low',{'emissionDay':-.01}),('day-high',{'emissionDay':5.01}),
        ('night-low',{'emissionNight':-.01}),('night-high',{'emissionNight':5.01}),
        ('blend-low',{'textureBlend':-.01}),('blend-high',{'textureBlend':1.01}),
        ('zero-scale',{'textureScale':[0,1,1]}),('offset-high',{'textureOffset':[10001,0,0]}),
        ('rotation-high',{'textureRotation':[361,0,0]}),('unknown-wrap',{'textureWrapMode':['missing','Repeat','Repeat']}),
        ('unknown-texture',{'textureId':'__missing__'}),('unknown-preset',{'texturePresetId':'__missing__'}),
        ('rgba-range',{'colors':[{'index':0,'rgba':[1.01,0,0,1]}]}),
        ('duplicate-color',{'colors':[{'index':0,'rgba':[1,0,0,1]},{'index':0,'rgba':[0,1,0,1]}]}),
        ('solid-conflict',{'style':'SolidColor','textureBlend':.5}),
        ('solid-override',{'style':'SolidColor','colors':[{'index':0,'metallic':.2}]}),
        ('null-material-day',{'emissionDay':None}),('wrong-number',{'metallic':{}})]
    before=snap('before-negative');history=call('history-before','craft.history')
    for label,patch in negative:
        result=r.call('reject-'+label,'batch.preview',{**guard(),'operations':[op(patch)]})
        r.check(label+' explicit rejection',not result['success'] and result.get('error',{}).get('code') in
                ('invalid_property_value','property_out_of_range','invalid_input','invalid_resource_id'),result.get('error'))
    after=snap('after-negative')
    r.check('all rejected previews preserve XML and identity',before==after)
    r.check('all rejected previews preserve native history',history==call('history-after','craft.history'))
    # The actual write route must also reject before touching unrelated data.
    result=r.call('reject-actual-write','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,
        'operations':[op({'metallic':.4}),op({'emissionDay':5.01})]})
    r.check('later invalid write fails',not result['success'],result.get('error'))
    r.check('actual write full state restored',snap('after-failed-write')['xml']==before['xml'])
    r.check('global theme unchanged',appearance('global-after')['globalCustomThemeFingerprint']==look['globalCustomThemeFingerprint'])
finally:
    restore('restore-original',fixture['originalCheckpointId'])
    final=snap('final');r.check('complete original restored',final['xml']==original['xml'])
    status=call('final-status','designer.status')
    r.check('healthy single aircraft',status['sceneIntegrity']['status']=='healthy' and status['sceneIntegrity']['aircraftInstanceCount']==1)
print(json.dumps({'checks':len(r.checks),'failed':[c for c in r.checks if c['status']=='fail']}))
sys.exit(any(c['status']=='fail' for c in r.checks))
