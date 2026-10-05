"""Prepare an E1 modeling fixture, leaving it open for native UI target edits.

This preparation is not the reference result or a claimed E1 pass. The target
must subsequently be authored through the native UI and frozen for fitting.
"""
import json,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
def snap(label):
    a=r.call(label,'craft.snapshot',{'includeXml':True});assert a['success'],a
    assert a['data']['name']=='SP2Build 050 Precision Lab F2'
    return a['data']
def guard():
    i=snap('guard-'+str(len(r.calls)))['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def apply(label,ops):
    a=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert a['success'],a
    return a['data']
base=snap('baseline');assert base['partCount']==3
cp=r.call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'E1 original F2'})['data']['id']
try:
    positions={'rear':[0,5,0],'cabin':[0,5,.65],'nose':[0,5,1.65],
        'glass-lr':[-.26,5.5,.46],'glass-rr':[.26,5.5,.46],
        'glass-lf':[-.26,5.5,.84],'glass-rf':[.26,5.5,.84]}
    created=apply('add-fixture',[{'kind':'part.add','templateId':'tpl-a0c296e1a01292ad' if k.startswith('glass') else 'tpl-f748657136c8ca1a',
        'temporaryId':k,'position':p,**({'rotation':[90,0,0]} if k.startswith('glass') else {})} for k,p in positions.items()])
    ids=created['temporaryIds'];ops=[]
    for key,length,front in [('rear',.5,[1.2,1]),('cabin',.8,[1.2,1]),('nose',1.2,[.2,.25])]:
        ops.append({'kind':'shape.update','partId':ids[key],'symmetric':False,'patch':{'autoResize':False,'length':length,'sections':[
            {'index':i,'width':size[0],'height':size[1],'syncAdjacent':False,'smoothing':False,
             'cornerRadius':{c:.7 for c in ('topLeft','topRight','bottomLeft','bottomRight')}} for i,size in enumerate([[1.2,1],front])]}})
    for key in positions:
        host=1 if key=='rear' else ids['rear'] if key=='cabin' else ids['cabin']
        ops.append({'kind':'connection.connect','partA':ids[key],'partB':host,'attachPointA':0,'attachPointB':1,'symmetric':False})
    apply('shape-and-connections',ops)
    windows=[ids[k] for k in positions if k.startswith('glass')]
    apply('window-targets',[{'kind':'properties.set','partId':pid,'symmetric':False,'patch':{'PartTargeting[0].targetMode':'Custom'}} for pid in windows]+
        [{'kind':'properties.set','partId':pid,'symmetric':False,'patch':{'PartTargeting[0].customPartIds':[ids['cabin']],
        'ProceduralWindow[0].height':.28,'ProceduralWindow[0].topWidth':.35,'ProceduralWindow[0].bottomWidth':.4,
        'ProceduralWindow[0].topOffset':.02,'ProceduralWindow[0].bottomOffset':-.02,
        'ProceduralWindow[0].depth':.3,'ProceduralWindow[0].penetration':.5,'ProceduralWindow[0].cornerRadius':.08,
        'ProceduralWindow[0].hideGlass':False,'Transparency[0].opacity':.45}} for pid in windows])
    prepared=snap('prepared')
    r.call('native','designer.capture',{**guard(),'focusPartIds':list(ids.values()),'views':[{'view':'top','projection':'orthographic'},{'view':'right','projection':'orthographic'},{'view':'isometric','projection':'perspective'}],'resolution':{'width':1280,'height':800}},images=True)
    (r.root/'fixture.json').write_text(json.dumps({'originalCheckpointId':cp,'ids':ids,'status':'prepared_for_native_ui_target_not_gold','identity':prepared['identity']},indent=2),encoding='utf-8')
except BaseException:
    x=r.call('restore-on-error','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});assert x['success'],x
    raise
