"""Text/texture projector behavior and target scope in the connected F2 fixture."""
import json,math,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1] if len(sys.argv)>1 else 'dev7-decals')
def snap(label):
 x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
 assert x['data']['name'].startswith('SP2Build 050 Precision Lab');assert not x['data']['identity']['stateUncertain']
 return x['data']
def guard():
 i=snap('guard-'+str(len(r.calls)))['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def apply(label,ops):
 x=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert x['success'],x
 return x['data']
def prop(pid,patch):return {'kind':'properties.set','partId':pid,'patch':patch,'symmetric':False}
base=snap('baseline')
cps=r.call('checkpoints','craft.checkpoint.list')['data']['checkpoints']
cp=next((c['id'] for c in cps if c['fingerprint']==base['identity']['fingerprint']),None)
if not cp:cp=r.call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'decal-baseline'})['data']['id']
try:
 added=apply('add-fixture',[{'kind':'part.add','templateId':tpl,'temporaryId':key,'position':pos} for key,tpl,pos in [('body','tpl-f748657136c8ca1a',[4,2.25,0]),('text','tpl-2eb27a8bdfcc3166',[4,2.5,-.5]),('decal','tpl-7da5fd121ac144c6',[4,2,-.5])]])
 ids=added['temporaryIds'];body,text,decal=ids['body'],ids['text'],ids['decal']
 apply('connect',[{'kind':'shape.update','partId':body,'symmetric':False,'patch':{'autoResize':False,'sections':[{'index':i,'width':2,'height':1.5} for i in (0,1)]}}]+
       [{'kind':'connection.connect','partA':pid,'partB':host,'attachPointA':0,'attachPointB':1,'symmetric':False} for pid,host in [(body,1),(text,body),(decal,body)]])
 r.call('text-fields','properties.get',{'id':text,'limit':1000});r.call('decal-fields','properties.get',{'id':decal,'limit':1000})
 r.call('decal-resources','resources.list',{'category':'decals','offset':0,'limit':1000})
 apply('targets',[prop(pid,{'PartTargeting[0].targetMode':'Custom'}) for pid in (text,decal)]+[prop(pid,{'PartTargeting[0].customPartIds':[body]}) for pid in (text,decal)])
 patches={text:{'TextDecal[0].Text':'SP2 050','TextDecal[0].Font':'Roboto','TextDecal[0].FontSize':2.5,'TextDecal[0].HorizontalAlignment':'Center','TextDecal[0].VerticalAlignment':'Center',
   'TextDecal[0].Width':1.5,'TextDecal[0].Height':.35,'TextDecal[0].Depth':.3,'TextDecal[0].Penetration':.5,'TextDecal[0].Opacity':1,'TextDecal[0].TintColor':[0,0,0,1],'TextDecal[0].RenderPriority':3},
  decal:{'TextureDecal[0].decalId':'Decals_Shapes_Arrow1','TextureDecal[0].TextureTiling':[1,1],'TextureDecal[0].TextureOffset':[0,0],
   'TextureDecal[0].Width':1.2,'TextureDecal[0].Height':.35,'TextureDecal[0].Depth':.3,'TextureDecal[0].Penetration':.5,'TextureDecal[0].Opacity':.8,'TextureDecal[0].TintColor':[.8,.08,.05,1],'TextureDecal[0].RenderPriority':2}}
 apply('configure',[prop(pid,patch) for pid,patch in patches.items()])
 for pid,patch in patches.items():
  item=r.call('readback-'+str(pid),'properties.get',{'id':pid,'fields':list(patch)})['data']['parts'][0]
  fields=item['fields'];actual={f['propertyId']:f['value'] for f in fields}
  if pid==text:r.check('English glyphs available',item['textRendering']['status']=='glyphs_available',item['textRendering'])
  for key,value in patch.items():
   got=actual.get(key);passed=(abs(got-value)<1e-6 if isinstance(value,(int,float)) else all(abs(a-b)<1e-6 for a,b in zip(got,value)) if isinstance(value,list) else got==value)
   r.check(key+' effective',passed,{'requested':value,'effective':got})
 # Place the actual projectors, not a guessed Part origin. A +Z projector paints the -Z facing surface.
 apply('projector-poses',[{'kind':'decal.pose.set','partId':pid,'frame':{'kind':'world'},'position':[4,y,-.5],'rotationQuaternion':[0,0,0,1],'symmetric':False} for pid,y in [(text,2.5),(decal,2)]])
 for pid,y in [(text,2.5),(decal,2)]:
  p=r.call('pose-'+str(pid),'decal.pose.get',{'id':pid})['data'];r.check('projector exact position '+str(pid),math.dist(p['projectorPose']['position'],[4,y,-.5])<.0001,p)
  box=p['projectorLocalBox'];matrix=p['projectorToWorldRows']
  r.check('projector front plane and depth '+str(pid),box['min'][2]==0 and abs(box['max'][2]-.3)<1e-6,box)
  r.check('projector matrix translation '+str(pid),math.dist([row[3] for row in matrix[:3]],[4,y,-.5])<.0001,matrix)
 views=[{'view':'back','projection':'orthographic'},{'view':'custom','azimuthDegrees':-155,'elevationDegrees':12,'projection':'perspective'}]
 capture=r.call('native-letters-arrow','designer.capture',{**guard(),'focusPartIds':[body,text,decal],'views':views,'resolution':{'width':1280,'height':800}},images=True);assert capture['success'],capture
 fixed=capture['data']['repeatableViews']
 # Test a surface strictly inside the projection volume, as well as on its boundary.
 apply('inset-projector',[{'kind':'decal.pose.set','partId':pid,'frame':{'kind':'world'},'position':[4,y,-.51],'rotationQuaternion':[0,0,0,1],'symmetric':False} for pid,y in [(text,2.5),(decal,2)]])
 r.call('inset-native','designer.capture',{**guard(),'views':fixed,'resolution':{'width':1280,'height':800}},images=True)
 # Immutable native input/Animator data and the unrelated baseline parts must survive.
 after=snap('configured')
 old={p['id']:p for p in base['parts']};new={p['id']:p for p in after['parts']}
 r.check('unrelated baseline poses unchanged',all(old[k]['position']==new[k]['position'] and old[k]['rotationQuaternion']==new[k]['rotationQuaternion'] for k in old))
 apply('unicode-text',[prop(text,{'TextDecal[0].Text':'测试 • Ω <&>'})])
 unicode=r.call('unicode-native','designer.capture',{**guard(),'views':fixed,'resolution':{'width':1280,'height':800}},images=True);assert unicode['success'],unicode
 unicode_state=r.call('unicode-state','properties.get',{'id':text,'fields':['TextDecal[0].Text']})['data']['parts'][0]
 r.check('unicode content survives serialization',unicode_state['fields'][0]['value']=='测试 • Ω <&>')
 glyph=unicode_state['textRendering']
 r.check('missing Chinese glyphs explicitly diagnosed',glyph['status']=='missing_glyphs' and all(c in glyph['missingCharacters'] for c in '测试'),glyph)
 r.checks.append({'check':'unicode glyph appearance','status':'not_verified','details':'Content roundtrip is separate; open images to evaluate actual font glyphs.'});r.save()
 # Invalid IDs must reject; do not replace with a silent default.
 for label,pid,patch in [('bad-font',text,{'TextDecal[0].Font':'NoSuchFont'}),('bad-decal',decal,{'TextureDecal[0].decalId':'NoSuchDecal'}),('bad-target',text,{'PartTargeting[0].customPartIds':[999999]})]:
  x=r.call(label,'batch.preview',{**guard(),'operations':[prop(pid,patch)]});r.check(label+' rejected',not x['success'],x.get('error'))
finally:
 x=r.call('restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});assert x['success'],x
 r.check('restore full F2',snap('restored')['xml']==base['xml'])
