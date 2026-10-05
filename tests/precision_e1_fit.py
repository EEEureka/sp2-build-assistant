"""Three fixed E1 starts with a measured, bounded feedback loop.

The fitter reads public dimensions and the CURRENT state only. Test setup uses
the gold checkpoint between trials, but the solver never receives gold XML or
gold shape/property values. Final geometry/image review is a separate script.
"""
import json,math,sys,uuid
from precision_acceptance import Run,ROOT
from precision_e1_targets import mesh_bounds

r=Run(sys.argv[1]);gold=ROOT/sys.argv[2]
target=json.loads((gold/'public-target.json').read_text())
gold_cp=json.loads((gold/'fixture.json').read_text())['checkpointId']
starts=[{'back':[.012,-.01],'front':[.06,-.04],'glassHeight':.024,'glassZ':.009},
        {'back':[-.016,.012],'front':[-.05,.06],'glassHeight':-.018,'glassZ':-.012},
        {'back':[.008,.018],'front':[.04,.035],'glassHeight':.03,'glassZ':.015}]
(r.root/'fixed-starts.json').write_text(json.dumps(starts,indent=2))
history=[]

def snap(label):
    a=r.call(label,'craft.snapshot',{'includeXml':True});assert a['success'],a
    assert a['data']['name'] in ('SP2Build 050 Precision Lab F2','SP2Build 050 Precision Lab E1') and a['data']['partCount']==10
    return a['data']

def guard():
    i=snap('guard-'+str(len(r.calls)))['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}

def apply(label,ops):
    a=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert a['success'],a
    return a['data']

def restore(label):
    a=r.call(label,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':gold_cp});assert a['success'],a

def shape(label):return r.call(label,'shape.get',{'id':6})['data']['shape']['configuration']

def heights(label):
    values={}
    for w in target['windows']:
        a=r.call(label+'-'+str(w['partId']),'properties.get',{'id':w['partId'],'fields':['ProceduralWindow[0].height']});assert a['success'],a
        f=a['data']['parts'][0]['fields'][0];assert f['propertyId']=='ProceduralWindow[0].height' and f['valueAvailable']
        values[w['partId']]=f['value']
    return values

def measure(label):
    measured=[]
    for idx,section in enumerate(target['nose']['sections']):
        a=r.call(label+'-section-'+str(idx),'geometry.section',{**guard(),'partIds':[6],'frame':{'kind':'world'},'plane':{'origin':[0,5,section['z']],'normal':[0,0,1]}});assert a['success'],a
        d=a['data'];assert d['complete'] and not d['staleAtDelivery'] and not d['measurement']['truncated'],d
        ps=[p for s in d['measurement']['segments'] for p in (s['a'],s['b'])];assert ps
        measured.append({'width':max(p[0] for p in ps)-min(p[0] for p in ps),'height':max(p[1] for p in ps)-min(p[1] for p in ps)})
    a=r.call(label+'-mesh','geometry.section',{**guard(),'partIds':list(range(4,11)),'frame':{'kind':'world'},'plane':{'origin':[0,5,1.65],'normal':[0,0,1]},'export':True,'exportMeshes':True},images=True);assert a['success'],a
    assert a['data']['complete'] and not a['data']['staleAtDelivery']
    meshes=json.loads(next((r.root/(label+'-mesh')).rglob('meshes.json')).read_text())['meshes']
    windows={w['partId']:mesh_bounds(meshes,w['partId']) for w in target['windows']}
    errors=[abs(a[k]-b[k]) for a,b in zip(measured,target['nose']['sections']) for k in ('width','height')]
    errors += [abs(windows[w['partId']][side][2]-w[key]) for w in target['windows'] for side,key in [('min','zMin'),('max','zMax')]]
    return measured,windows,max(errors)

def capture(label):
    for suffix in ('plan-side','front'):
        ref=json.loads((gold/('gold-'+suffix+'.json')).read_text())['data']
        a=r.call(label+'-'+suffix,'designer.capture',{**guard(),'views':ref['repeatableViews'],'resolution':ref['repeatableResolution']},images=True);assert a['success'],a

try:
    for trial,start in enumerate(starts,1):
        name='trial-'+str(trial);restore(name+'-setup-gold')
        current=shape(name+'-setup-shape');h=heights(name+'-setup-height')
        ops=[{'kind':'shape.update','partId':6,'symmetric':False,'patch':{'sections':[{'index':j,'width':current['sections'][j]['width']+start[k][0],'height':current['sections'][j]['height']+start[k][1],'syncAdjacent':False} for j,k in enumerate(('back','front'))]}}]
        for idx,w in enumerate(target['windows']):
            pid=w['partId'];sign=1 if idx%2==0 else -1
            ops.extend([{'kind':'properties.set','partId':pid,'symmetric':False,'patch':{'ProceduralWindow[0].height':h[pid]+sign*start['glassHeight']}},
                {'kind':'transform.apply','partIds':[pid],'frame':{'kind':'world'},'mode':'delta','translation':[0,0,sign*start['glassZ']],'symmetric':False}])
        apply(name+'-perturb',ops);snap(name+'-start');capture(name+'-start-native')
        best=float('inf');bestcp=None;steps=0
        for iteration in range(13):
            label=name+'-round-'+str(iteration)
            sections,windows,error=measure(label)
            record={'trial':trial,'iteration':iteration,'maxMeasuredDimensionErrorMetres':error,'candidateWrites':steps};history.append(record)
            (r.root/'iterations.json').write_text(json.dumps(history,indent=2))
            if error<best:
                best=error;bestcp=r.call(label+'-best','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':label+' best'})['data']['id']
            if error<=.0001 and steps>=2:break
            if iteration==12:break
            if error>best+1e-5:
                r.call(label+'-reject-worse','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':bestcp})
                raise AssertionError('Feedback worsened; retained best and stopped')
            current=shape(label+'-shape');ops=[]
            # The current native straight segment linearly interpolates end
            # dimensions. Infer the two corrections from measured section errors.
            ts=[(p['z']-target['nose']['backZ'])/(target['nose']['frontZ']-target['nose']['backZ']) for p in target['nose']['sections']]
            gain=.8 if iteration==0 else 1.;patch=[{'index':i,'syncAdjacent':False} for i in (0,1)]
            for field in ('width','height'):
                e0=target['nose']['sections'][0][field]-sections[0][field];e1=target['nose']['sections'][-1][field]-sections[-1][field]
                slope=(e1-e0)/(ts[-1]-ts[0]);delta=[e0-ts[0]*slope,e0+(1-ts[0])*slope]
                for i in (0,1):patch[i][field]=current['sections'][i][field]+gain*delta[i]
            ops.append({'kind':'shape.update','partId':6,'symmetric':False,'patch':{'sections':patch}})
            hs=heights(label+'-height')
            for w in target['windows']:
                pid=w['partId'];b=windows[pid]
                dh=(w['zMax']-w['zMin'])-(b['max'][2]-b['min'][2]);dz=(w['zMax']+w['zMin']-b['max'][2]-b['min'][2])/2
                ops.extend([{'kind':'properties.set','partId':pid,'symmetric':False,'patch':{'ProceduralWindow[0].height':hs[pid]+gain*dh}},
                    {'kind':'transform.apply','partIds':[pid],'frame':{'kind':'world'},'mode':'delta','translation':[0,0,gain*dz],'symmetric':False}])
            record['decision']={'gain':gain,'basis':'Current measured section residuals and glass mesh z bounds; current writable values only','operations':ops}
            (r.root/'iterations.json').write_text(json.dumps(history,indent=2))
            apply(label+'-candidate',ops);steps+=1
        r.check(name+' measured target',error<=.0001 and 2<=steps<=12,{'errorMetres':error,'candidateBatches':steps,'setupBatches':1,'bestCheckpointId':bestcp})
        snap(name+'-final');capture(name+'-final-native')
        (r.root/(name+'-result.json')).write_text(json.dumps({'trial':trial,'lastRound':iteration,'candidateBatches':steps,'bestCheckpointId':bestcp,'measuredErrorMetres':error},indent=2))
finally:
    restore('restore-native-gold');snap('final-restored');r.call('final-status','designer.status')
