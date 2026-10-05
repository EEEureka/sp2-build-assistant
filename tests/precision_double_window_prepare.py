"""Leave an explicit six-part F2 fixture for native UI parity, with checkpoints."""
import json,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
def call(n,c,a=None):
    x=r.call(n,c,a);assert x['success'],x;return x['data']
def guard():
    i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def write(n,ops):return call(n,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
base=call('original','craft.snapshot',{'includeXml':True});assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
original=call('original-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'double window original'})['id']
try:
    out=write('add',[{'kind':'part.add','templateId':tpl,'temporaryId':key,'position':pos} for key,tpl,pos in [('outer','tpl-f748657136c8ca1a',[4,2.25,0]),('inner','tpl-f748657136c8ca1a',[4,2.25,0]),('window','tpl-a0c296e1a01292ad',[4,2.25,-1])]])
    outer,inner,win=(out['temporaryIds'][x] for x in ('outer','inner','window'))
    write('hosts',[{'kind':'shape.update','partId':p,'symmetric':False,'patch':{'autoResize':False,'length':size,'sections':[{'index':i,'width':size,'height':size,'syncAdjacent':False} for i in (0,1)]}} for p,size in [(outer,2),(inner,1.6)]]+[
        {'kind':'connection.connect','partA':p,'partB':h,'attachPointA':0,'attachPointB':1,'symmetric':False} for p,h in [(outer,1),(inner,outer),(win,outer)]])
    def prop(p):return {'kind':'properties.set','partId':win,'patch':p,'symmetric':False}
    write('window',[prop({'PartTargeting[0].targetMode':'Custom'}),prop({'PartTargeting[0].customPartIds':[outer]}),prop({'ProceduralWindow[0].height':.8,'ProceduralWindow[0].topWidth':.6,'ProceduralWindow[0].bottomWidth':.6,'ProceduralWindow[0].topOffset':0,'ProceduralWindow[0].bottomOffset':0,'ProceduralWindow[0].depth':1,'ProceduralWindow[0].penetration':.75,'ProceduralWindow[0].cornerRadius':.1,'ProceduralWindow[0].hideGlass':False,'Transparency[0].opacity':.3})])
    call('prepared','craft.snapshot',{'includeXml':True});call('properties-'+str(win),'properties.get',{'id':win,'limit':1000})
    cp=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'double window UI baseline'})['id']
    metadata={'checkpointId':cp,'originalCheckpointId':original,'outer':outer,'inner':inner,'window':win,
        'views':[{'view':'back','projection':'orthographic'},{'view':'custom','azimuthDegrees':205,'elevationDegrees':15,'projection':'perspective'}],
        'parityRays':[{'origin':[x,2.25,-3],'direction':[0,0,1],'distance':6} for x in (4,4.45,4.75)]}
    (r.root/'fixture.json').write_text(json.dumps(metadata,indent=2));print(json.dumps(metadata))
except:
    call('prepare-failure-restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':original});raise
