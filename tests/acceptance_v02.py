"""Independent live acceptance cases. Record failures; restore, then test next case.
Uses the installed global CLI and only the currently open aircraft.
"""
import json
import os
import traceback
import uuid
import xml.etree.ElementTree as ET
import live_verify_v02 as c

REPORT = c.ARTIFACTS / 'acceptance.json'
results = []
baseline = None
checkpoint = None
entries = []
selection = None

def save():
    REPORT.write_text(json.dumps({'checkpoint':checkpoint,'baselinePartCount':baseline['partCount'] if baseline else None,'cases':results},ensure_ascii=False,indent=2),encoding='utf-8')

def finish():
    print('REPORT '+str(REPORT.resolve()),flush=True)
    # Continue through every case, but still return a failing suite exit code.
    raise SystemExit(1 if any(r['status']!='passed' or r.get('restored') is False for r in results) else 0)

def case(name, action, write=False):
    start = c.sequence + 1
    result = {'case':name,'firstArtifact':start}
    if write and c.outcome_unknown:
        result.update(status='blocked',reason='Previous write outcome unknown; independent reads can continue')
    else:
        try:
            action()
            result['status']='passed'
        except Exception as exc:
            result.update(status='failed',error=str(exc),trace=traceback.format_exc())
        finally:
            if write and not c.outcome_unknown:
                try:
                    restored=c.guarded('craft.rollback',checkpointId=checkpoint)['data']
                    c.check('case baseline restored',restored['validation']['restorationVerified'])
                    result['restored']=True
                except Exception as exc:
                    result['restored']=False
                    result['recoveryError']=str(exc)
                    # Each later case gets one explicit recovery attempt before any write.
    result['lastArtifact']=c.sequence
    results.append(result); save()
    print(json.dumps(result,ensure_ascii=False),flush=True)

def begin_write():
    state=c.read('designer.status')['identity']
    if state['stateUncertain']:
        c.guarded('craft.rollback',checkpointId=checkpoint)

def template(kind):
    return next(e['id'] for e in entries if e['source']=='builtin' and e['creatable'] and e['partTypes']==[kind])

def add(kind='JFuselage-1', name='tmp', pos=None):
    begin_write()
    return c.apply({'kind':'part.add','templateId':template(kind),'temporaryId':name,'position':pos or [20,15,0],'rotation':[0,0,0]})['temporaryIds'][name]

def shape(p): return c.read('shape.get',id=p)['shape']['configuration']
def update(p, patch, **extra): return c.apply({'kind':'shape.update','partId':p,'patch':patch,**extra})
def bad(*ops):
    ident=c.read('designer.status')['identity']
    result=c.call('batch.apply',{'craftSessionId':ident['craftSessionId'],'expectedRevision':ident['revision'],'requestId':uuid.uuid4().hex,'operations':list(ops)},require=False)
    c.check('invalid request rejected',not result['success'])
    if 'rollbackResult' in result: c.check('invalid edit recovered',result['rollbackResult']['restored'])
    return result

def read_core():
    for cmd,args in [('capabilities',{}),('parts.list',{'offset':0,'limit':1000}),('connections.list',{}),('spatial.query',{'partA':1,'partB':3}),('variables.list',{}),('outputs.list',{}),('funky.list',{}),('funky.describe',{'name':'clamp'}),('funky.validate',{'expression':'clamp(Throttle,0,1)'}),('craft.history',{}),('craft.checkpoint.list',{}),('craft.checkpoint.get',{'id':checkpoint})]:c.read(cmd,**args)

def read_catalog():
    c.read('catalog.categories');c.read('catalog.subcategories',category='Structure')
    c.read('catalog.search',query='Fuselage');c.read('catalog.get',id=template('JFuselage-2'));c.read('catalog.schema',type='JFuselage-2')
    cat=c.read('catalog.export');c.check('all catalog schemas succeed',not any('error' in x for x in cat['schemas']))

def read_shapes():
    for family in ('fuselage','wing','controlSurface'):c.read('shape.schema',family=family)
    representatives={}
    for p in baseline['parts']:representatives.setdefault(p['type'],p['id'])
    errors=[]
    for typ,id in representatives.items():
        try:c.read('parts.get',id=id);c.read('shape.get',id=id);c.read('parts.geometry',id=id)
        except Exception as e:errors.append({'type':typ,'id':id,'error':str(e)})
    c.check('representative reads '+str(errors),not errors)

def roles(typ):
    ids=[p['id'] for p in baseline['parts'] if p['type']==typ]
    p=ids[0] if ids else add(typ)
    points=c.read('connections.points',part=p)['points']
    c.check('one rotor, housing available',sum(x['role']=='rotor' for x in points)==1 and any(x['role']=='housing' for x in points))

def length_geometry():
    p=add();c.read('parts.geometry',id=p)
    c.check('outside old volume',not c.hits(p,20,20,2))
    update(p,{'length':6},symmetric=False)
    c.read('parts.geometry',id=p);c.check('expanded geometry pick',c.hits(p,20,20,2))
    c.check('selection preserved',c.read('designer.selection')['selectedPartId']==selection)
    update(p,{'length':1},symmetric=False);c.check('old volume removed',not c.hits(p,20,20,2))

def raw_geometry():
    p=add()
    c.apply({'kind':'part.update','partId':p,'changes':[{'path':'JFuselage.State','attribute':'offset','value':'0,0,6'}]})
    c.check('raw fuselage resize picks new region',c.hits(p,20,20,2))

def refresh_undo():
    p=add();update(p,{'length':6},symmetric=False)
    c.apply({'kind':'craft.refresh'});c.check('explicit refresh preserves geometry',c.hits(p,20,20,2))
    update(p,{'length':1},symmetric=False);c.guarded('craft.undo')
    c.check('undo restores collider geometry',c.hits(p,20,20,2))

def fuselage_complex(typ):
    p=add(typ);initial=shape(p)
    update(p,{'sections':[{'index':0,'width':1.4,'height':1.8,'cornerRadius':{'topLeft':.2,'bottomRight':.3},'cornerStretch':{'topLeft':False},'edgeCurvature':{'top':.2},'cutting':{'top':.64,'bottom':0,'left':None,'right':None},'smoothing':True}]},symmetric=False)
    q=shape(p)['sections'][0];c.check('complex fuselage readback',abs(q['width']-1.4)<.001 and q['cutting']['top']==.64)
    if typ=='JFuselage-2':
        c.check('curved three sections',len(initial['sections'])==3)
        bad({'kind':'shape.update','partId':p,'patch':{'sections':[{'index':1,'cutting':{'top':.2}}]}})
    if typ=='JFuselage-Cone-1':update(p,{'noseconeRoundness':.7},symmetric=False);c.check('cone roundness',abs(shape(p)['noseconeRoundness']-.7)<.001)

def adjacency():
    p=add(name='a');q=add(name='b',pos=[20,15,1])
    a=c.read('connections.points',part=p)['points'];b=c.read('connections.points',part=q)['points']
    # Native body endpoints are identified from their local Z positions.
    ap=max(a,key=lambda x:x['localPosition'][2]);bp=min(b,key=lambda x:x['localPosition'][2])
    c.apply({'kind':'connection.connect','partA':p,'partB':q,'attachPointA':ap['id'],'attachPointB':bp['id'],'symmetric':False})
    c.apply({'kind':'fuselage.match','partId':p,'sectionIndex':1})
    update(p,{'sections':[{'index':1,'width':1.3,'cutting':{'right':.2}}]},symmetric=False)
    qa=shape(p)['sections'][1];qb=shape(q)['sections'][0]
    c.check('adjacent section synchronized',abs(qa['width']-qb['width'])<.001 and qb['cutting']['right']==.2)
    c.apply({'kind':'connection.disconnect','partA':p,'partB':q,'symmetric':False})

def symmetry():
    p=add();r=c.apply({'kind':'symmetry.create','partId':p});q=r['actualChanges'][0]['createdPartIds'][0]
    update(p,{'sections':[{'index':0,'cutting':{'right':.2}}]})
    c.check('right mirrored to left',shape(q)['sections'][0]['cutting']['left']==.2)
    c.apply({'kind':'symmetry.enable','partId':p,'enabled':False})
    update(p,{'length':4});c.check('disabled group remains unchanged',shape(q)['length']!=4)
    c.apply({'kind':'symmetry.enable','partId':p,'enabled':True});update(p,{'length':3})
    c.check('reenabled group propagates',shape(q)['length']==3)
    c.apply({'kind':'symmetry.unlink','partId':p});c.apply({'kind':'symmetry.link','partIds':[p,q]})
    c.read('symmetry.get',part=p)
    c.apply({'kind':'part.update','partId':p,'symmetric':True,'changes':[{'path':'','attribute':'name','value':'Symmetry acceptance'}]})
    c.check('raw scalar synchronization',c.read('parts.get',id=q)['part']['name']=='Symmetry acceptance')
    c.apply({'kind':'part.delete','partId':p,'symmetric':True})

def wing_geometry():
    p=add('JWing-1');initial=shape(p)
    update(p,{'replaceSections':[{'spanPosition':0,'chord':2,'offset':0,'airfoil':'NACA2412'},{'spanPosition':1,'chord':None,'offset':None,'airfoil':None},{'spanPosition':3,'chord':1,'offset':-.2,'airfoil':'NACA0012'}],'wingtip':{'stretch':1.2}},symmetric=False)
    q=shape(p);c.check('wing multisection and tip',len(q['sections'])==3 and abs(q['wingtip']['stretch']-1.2)<.001)
    bad({'kind':'shape.update','partId':p,'patch':{'sections':[{'index':0,'airfoil':'NACA0000'}]}})
    c.read('parts.geometry',id=p)

def control(style):
    p=add('JWing-1');span=c.read('shape.get',id=p)['shape']['spanMetres']
    r=c.apply({'kind':'wing.control.add','wingPartId':p,'style':style,'temporaryId':'cs','patch':{'spanRange':[.2*span,.6*span],'chordFraction':[.2,.2]}})
    q=r['temporaryIds']['cs'];state=c.read('shape.get',id=q)['shape']
    c.check('native control connected',state['wingPartId']==p)
    update(q,{'spanRange':[.25*span,.65*span],'chordFraction':[.25,.3]},symmetric=False)
    c.check('control size readback',abs(c.read('shape.get',id=q)['shape']['chordFraction'][1]-.3)<.002)
    c.apply({'kind':'part.delete','partId':q})

def invalid_transaction():
    p=add();name=c.read('parts.get',id=p)['part']['name']
    bad({'kind':'part.update','partId':p,'changes':[{'path':'','attribute':'name','value':'SHOULD ROLL BACK'}]}, {'kind':'shape.update','partId':p,'patch':{'sections':[{'index':0,'cutting':{'top':.6,'bottom':.6}}]}})
    c.check('whole transaction restored',c.read('parts.get',id=p)['part']['name']==name)

def variables_outputs():
    begin_write();vars0=c.read('variables.list')['setters'];n=len(vars0['children']) if vars0 else 0
    c.apply({'kind':'variable.add','variable':'SP2AcceptanceOnly','function':'clamp(Throttle,0,1)'})
    c.apply({'kind':'variable.update','index':n,'function':'0.25'})
    c.apply({'kind':'variable.reorder','order':list(range(n+1))})
    c.apply({'kind':'variable.delete','index':n})
    p=add('JointRotator-1');outputs=c.read('outputs.list',part=p)['parts'][0]['modifiers']
    m=next(x for x in outputs if x['definitions']);out=m['definitions'][0]['id']
    c.apply({'kind':'output.bind','partId':p,'modifier':m['modifier'],'outputId':out,'variable':'SP2AcceptanceOutput'})
    c.apply({'kind':'output.update','partId':p,'modifier':m['modifier'],'outputId':out,'activator':'true','priority':2})
    c.apply({'kind':'output.unbind','partId':p,'modifier':m['modifier'],'outputId':out})

def guards():
    begin_write();ident=c.read('designer.status')['identity']
    args={'craftSessionId':ident['craftSessionId'],'expectedRevision':ident['revision'],'requestId':uuid.uuid4().hex,'operations':[{'kind':'part.add','templateId':template('JFuselage-1'),'position':[20,15,0]}]}
    one=c.call('batch.apply',args);two=c.call('batch.apply',args);c.check('dedup returns same operation',one['operationId']==two['operationId'])
    args['requestId']=uuid.uuid4().hex
    rejected=c.call('batch.apply',args,require=False);c.check('stale revision rejected',rejected.get('error',{}).get('code')=='revision_conflict')

def main():
    global baseline,checkpoint,entries,selection
    expected_build=os.environ.get('SP2_ACCEPTANCE_BUILD_ID')
    if not expected_build:raise RuntimeError('Set SP2_ACCEPTANCE_BUILD_ID to the compiled DLL MVID before running acceptance.')
    status=c.read('designer.status');c.check('loaded exact acceptance build',status['buildId']==expected_build)
    baseline=c.read('craft.snapshot',includeXml=True);selection=c.read('designer.selection')['selectedPartId']
    checkpoint=c.guarded('craft.checkpoint.create',name='0.2 full independent acceptance baseline')['data']['id']
    entries=c.read('catalog.list',limit=1000)['listing']['items'];save()
    case('read-only core',read_core);case('whole catalog',read_catalog);case('all present type shape/geometry reads',read_shapes)
    for typ in ('HingeRotator-1','SmallRotator-1','JointRotator-1'):case('joint role '+typ,lambda t=typ:roles(t),write=not any(p['type']==typ for p in baseline['parts']))
    case('typed length and collider refresh',length_geometry,True)
    case('raw length collider refresh',raw_geometry,True)
    case('explicit refresh and undo',refresh_undo,True)
    for typ in ('JFuselage-1','JFuselage-2','JFuselage-Cone-1'):case('complex '+typ,lambda t=typ:fuselage_complex(t),True)
    case('adjacent matching and connections',adjacency,True)
    case('symmetry lifecycle',symmetry,True)
    case('wing sections and airfoil validation',wing_geometry,True)
    for style in ('StandardFlap','FowlerFlap','BrakeFlap','Slat'):case('control '+style,lambda s=style:control(s),True)
    case('invalid transaction rollback',invalid_transaction,True)
    case('variables and outputs regression',variables_outputs,True)
    case('dedup and revision guards',guards,True)
    case('final snapshot and selection',lambda:(c.check('part count restored',c.read('craft.snapshot')['partCount']==baseline['partCount']),c.check('selection restored',c.read('designer.selection')['selectedPartId']==selection)))
    finish()

if __name__=='__main__':main()
