"""Connect the inspected E3 fixture and give the bay an explicit sole host."""
import json,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
def call(label,cmd,args=None,**kw):
 x=r.call(label,cmd,args,**kw);assert x['success'],x;return x['data']
def guard():
 i=call('guard-'+str(len(r.calls)),'designer.status')['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def props(pid,patch):return {'kind':'properties.set','partId':pid,'patch':patch,'symmetric':False}
def pose(pid,attribute,value):return {'kind':'part.update','partId':pid,'changes':[{'path':'Part','attribute':attribute,'value':value}]}
def connect(a,b,ap,bp):return {'kind':'connection.connect','partA':a,'partB':b,'attachPointA':ap,'attachPointB':bp,'symmetric':False}
before=call('before','craft.snapshot',{'includeXml':True});assert before['name']=='SP2Build 050 Precision Lab F2' and before['partCount']==8
cp=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'Before E3 mounting'})['id']
ops=[{'kind':'shape.update','partId':4,'symmetric':False,'patch':{'autoResize':False,'sections':[{'index':i,'width':2.6,'height':1.2,'smoothing':False,'syncAdjacent':False} for i in (0,1)]}},
 connect(4,1,0,1),connect(7,4,0,4),connect(5,7,0,1),connect(8,4,1,4),
 pose(7,'rotation','270,0,0'),pose(7,'position','4,5.39,0'),
 pose(8,'position','5.4,5.1,0.7'),pose(8,'rotation','0,0,180'),
 props(7,{'PartTargeting[0].targetMode':'Custom'}),
 props(7,{'PartTargeting[0].customPartIds':[4],'GearBay[0].height':2.7,'GearBay[0].topWidth':2.1,'GearBay[0].bottomWidth':2.1,'GearBay[0].depth':1.1,'GearBay[0].penetration':.98,'GearBay[0].doorStyle':'DoubleLengthways','GearBay[0].cornerRadius':.1}),
 props(8,{'Piston[0].size':.6,'Piston[0].radius':.8,'Piston[0].range':.3,'Piston[0].speed':.7})]
try:
 out=call('mount-and-configure','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
 after=call('prepared','craft.snapshot',{'includeXml':True})
 for p in range(4,9):
  call('properties-'+str(p),'properties.get',{'id':p,'limit':1000})
  call('mounts-'+str(p),'connections.points',{'part':p})
  call('geometry-'+str(p),'parts.geometry',{'id':p})
 call('views','designer.capture',{**guard(),'focusPartIds':[4,5,6,7,8],'views':[{'view':'custom','azimuthDegrees':45,'elevationDegrees':-25,'projection':'perspective'},{'view':'front','projection':'orthographic'},{'view':'bottom','projection':'orthographic'}],'resolution':{'width':1280,'height':800}},images=True)
 cp2=call('configured-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'E3 mounted baseline'})['id']
 (r.root/'fixture.json').write_text(json.dumps({'checkpointId':cp2,'beforeCheckpointId':cp,'partIds':list(range(4,9))},indent=2))
except BaseException:
 call('failed-configure-restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});raise
