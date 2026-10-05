"""Craft-local material scope and recovery; native UI parity remains separate."""
import json,sys,uuid
from pathlib import Path
from precision_acceptance import Run
r=Run(sys.argv[1] if len(sys.argv)>1 else 'dev7-materials')
def snap(label):
 x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
 assert x['data']['name'].startswith('SP2Build 050 Precision Lab');assert not x['data']['identity']['stateUncertain']
 return x['data']
def guard():
 i=snap('guard-'+str(len(r.calls)))['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def apply(label,ops):
 x=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert x['success'],x
 return x['data']
def appearance(label,ids):
 x=r.call(label,'appearance.get',{'partIds':ids});assert x['success'],x
 return x['data']
def capture(label,ids,views=None):
 x=r.call(label,'designer.capture',{**guard(),'focusPartIds':ids,'views':views or [{'view':'back','projection':'orthographic'},{'view':'custom','azimuthDegrees':-150,'elevationDegrees':15,'projection':'perspective'}],'resolution':{'width':1280,'height':800}},images=True);assert x['success'],x
 return x['data']
base=snap('baseline');before_global=appearance('global-before',[1,2,3])['globalCustomThemeFingerprint']
cp=r.call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'material-scope-baseline'})['data']['id']
try:
 added=apply('add-three',[{'kind':'part.add','templateId':'tpl-f748657136c8ca1a','temporaryId':'m'+str(i),'position':[4+i*1.4,2.25,0]} for i in range(3)])
 ids=[added['temporaryIds']['m'+str(i)] for i in range(3)]
 disconnected=appearance('disconnected-state',ids)
 r.check('disconnected native state explicit',all(p['designerDisplayState']['isDisconnected'] for p in disconnected['parts']),disconnected['parts'])
 grey=capture('disconnected-view',ids)
 r.check('capture identifies grey native override',set(ids).issubset({p['partId'] for p in grey['nativeDisplayOverrides']}),grey['nativeDisplayOverrides'])
 # Native designer renders disconnected parts with a grey override material.
 # Preserve arbitrary placement while connecting the fixture for paint inspection.
 apply('connect-fixtures',[{'kind':'shape.update','partId':pid,'symmetric':False,'patch':{'autoResize':False}} for pid in ids]+
       [{'kind':'connection.connect','partA':pid,'partB':1,'attachPointA':0,'attachPointB':1,'symmetric':False} for pid in ids])
 old=appearance('initial-materials',ids);source=next(s['materialId'] for s in old['parts'][0]['slots'] if s['assignable'])
 r.check('connected native state explicit',all(not p['designerDisplayState']['isDisconnected'] for p in old['parts']),old['parts'])
 slots=[s['slot'] for s in old['parts'][0]['slots'] if s['assignable']]
 # A local shared material assigned to all three isolates this scope from the baseline aircraft.
 cloned=apply('isolated-shared-baseline',[{'kind':'appearance.set','mode':'clone','materialId':source,'partIds':ids,'slots':slots,'patch':{'name':'Acceptance shared','style':'SolidColor','colors':[{'index':0,'rgba':[.8,.8,.8,1]}],'metallic':.1,'smoothness':.25}}])
 material=cloned['actualChanges'][0]['materialId']
 baseline_appearance=appearance('three-share',ids)
 fixed=capture('shared-before-view',ids)['repeatableViews']
 op={'kind':'appearance.set','mode':'clone','materialId':material,'partIds':[ids[0]],'slots':slots,'patch':{'name':'Acceptance only A','style':'SolidColor','colors':[{'index':0,'rgba':[.92,.1,.12,1]}],'metallic':.3,'smoothness':.4,'emissionDay':0,'emissionNight':.1}}
 before=snap('before-preview');preview=r.call('clone-preview','batch.preview',{**guard(),'operations':[op]})
 r.check('material preview valid',preview['success'],preview.get('error'))
 r.check('material preview no mutation',snap('after-preview')['xml']==before['xml'])
 clone=apply('clone-one',[op]);after=appearance('clone-one-state',ids)
 r.check('other two material slots unchanged',after['parts'][1:]==baseline_appearance['parts'][1:])
 r.check('only A affected',clone['actualChanges'][0]['affectedPartIds']==[ids[0]])
 new_id=clone['actualChanges'][0]['materialId'];new_m=next(m for m in after['palette'] if m['id']==new_id)
 r.check('color normalized to RGBA8',all(abs(x-y)<=1/255 for x,y in zip(new_m['colors'][0]['rgba'],[.92,.1,.12,1])),new_m)
 capture('clone-one-view',ids,fixed)
 shared=apply('shared-two',[{'kind':'appearance.set','mode':'shared','materialId':material,'patch':{'name':'Acceptance B C blue','colors':[{'index':0,'rgba':[.1,.25,.9,1]}],'metallic':.25,'smoothness':.35}}])
 after_shared=appearance('shared-two-state',ids)
 r.check('shared explicitly affects B and C',sorted(shared['actualChanges'][0]['affectedPartIds'])==sorted(ids[1:]),shared['actualChanges'][0])
 r.check('A cloned material preserved',next(m for m in after_shared['palette'] if m['id']==new_id)==new_m)
 capture('shared-two-view',ids,fixed)
 assign=apply('assign-one',[{'kind':'appearance.set','mode':'assign','materialId':new_id,'partIds':[ids[1]],'slots':[slots[0]]}])
 assigned=appearance('assign-one-state',ids)
 r.check('assign retains palette',assigned['palette']==after_shared['palette'])
 r.check('assign affects requested slot only',assigned['parts'][1]['slots'][0]['materialId']==new_id and assigned['parts'][1]['slots'][1:]==after_shared['parts'][1]['slots'][1:])
 negatives=[('reserved-id',{'kind':'appearance.set','mode':'shared','materialId':-1,'patch':{'metallic':.2}},'material_not_editable'),
  ('invalid-texture',{'kind':'appearance.set','mode':'shared','materialId':material,'patch':{'style':'SinglePlaneTextureColorMask','textureId':'no-such-native-resource'}},'invalid_resource_id'),
  ('invalid-slot',{'kind':'appearance.set','mode':'assign','materialId':material,'partIds':[ids[0]],'slots':[999]},'invalid_input'),
  ('style-fields-conflict',{'kind':'appearance.set','mode':'shared','materialId':material,'patch':{'style':'SolidColor','textureBlend':.5}},'invalid_input')]
 before=snap('before-invalid')
 for label,op,error in negatives:
  x=r.call(label,'batch.preview',{**guard(),'operations':[op]})
  r.check(label+' rejected',not x['success'] and x.get('error',{}).get('code')==error,x.get('error'))
 r.check('invalid previews preserve all XML',snap('after-invalid')['xml']==before['xml'])
 final=appearance('global-after-operations',ids)
 r.check('global custom theme not touched',final['globalCustomThemeFingerprint']==before_global)
finally:
 x=r.call('restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});assert x['success'],x
 r.check('complete base restored',snap('restored')['xml']==base['xml'])
 r.check('global custom theme unchanged after recovery',appearance('global-after-restore',[1,2,3])['globalCustomThemeFingerprint']==before_global)
