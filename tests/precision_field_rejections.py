"""Complete discovered adapter type/range rejection matrix on fixed lab fixtures."""
import json,sys,uuid
from concurrent.futures import ThreadPoolExecutor
from precision_acceptance import Run
from review_restore_state import audit
r=Run(sys.argv[1]);identity=None
def call(n,c,a=None):
 global identity
 x=r.call(n,c,a);assert x['success'],x;d=x['data']
 if d.get('identity'):identity=d['identity']
 return d
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
base=call('baseline','craft.snapshot',{'includeXml':True});assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
cp=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'Rejection matrix original'})['id']
templates=['tpl-2eb27a8bdfcc3166','tpl-7da5fd121ac144c6','tpl-0107631356a369e6','tpl-ef03f5b3e35e1bbe',
 'tpl-0e1d278f1dc91cf6','tpl-c2ea68c52a8d3473','tpl-33195a9c4cfc6ff1','tpl-86c024231d5edb41']
rows=[]
try:
 call('prepare','batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[
  {'kind':'part.add','templateId':t,'temporaryId':'p'+str(i),'position':[5+i*5,4,0]} for i,t in enumerate(templates)]})
 prepared=call('prepared','craft.snapshot',{'includeXml':True})
 seen=set()
 for p in prepared['parts']:
  for f in call('properties-'+str(p['id']),'properties.get',{'id':p['id'],'limit':1000})['parts'][0]['fields']:
   if f.get('writeOperation')!='properties.set' or f['propertyId'] in seen:continue
   seen.add(f['propertyId']);rows.append({'partId':p['id'],'partType':p['type'],**f})
 (r.root/'denominator.json').write_text(json.dumps(rows,indent=2))
 h0=call('history-before','craft.history')
 pending=[]
 for i,f in enumerate(rows):
  key=f['propertyId'];cases=[('type',{})]
  if f.get('enumValues'):cases.append(('unknown-resource','__SP2BUILD_INVALID_NATIVE_ID__'))
  if f['type'] in ('number','integer'):
   cases += [('nan',float('nan')),('infinity',float('inf'))]
   for side,delta in [('min',-1),('max',1)]:
    if f.get('limits',{}).get(side) is not None:
     value=f['limits'][side]+delta
     cases.append((side,int(value) if f['type']=='integer' else value))
   if f['type']=='integer':cases.append(('fractional',.5))
  if f['type']=='array' and f['nativeType']!='System.Collections.Generic.List`1[System.Int32]':
   v=f.get('value');dim=len(v) if isinstance(v,list) else 2
   if dim in (2,3,4):
    cases += [('wrong-dimension',[0]*(dim+1)),('component-nan',[float('nan')]+[0]*(dim-1))]
    for side,delta in [('min',-1),('max',1)]:
     if f.get('limits',{}).get(side) is not None:cases.append((side,[f['limits'][side]+delta]*dim))
  if f['type']=='pose':cases += [('zero-quaternion',{'position':[0,0,0],'rotationQuaternion':[0,0,0,0]}),('wrong-pose-dimension',{'position':[0,0],'rotationQuaternion':[0,0,0,1]})]
  if key.endswith('customPartIds'):cases += [('duplicate-id',[1,1]),('fractional-id',[1.5])]
  for case,value in cases:
   n=f'f{i:03}-{case}'
   allowed=('property_out_of_range',) if case in ('min','max') else ('invalid_property_value','property_out_of_range','invalid_input','invalid_resource_id')
   pending.append((n,n+' rejects invalid field',{'kind':'properties.set','partId':f['partId'],'patch':{key:value},'symmetric':False},allowed))
  # Never silently fall back from an absent modifier index to index zero.
  if '[0]' in key:
   bad=key.replace('[0]','[99]',1)
   pending.append((f'f{i:03}-missing-instance',key+' absent modifier rejected',{'kind':'properties.set','partId':f['partId'],'patch':{bad:f['value']},'symmetric':False},('property_not_found',)))
 # Independent read-only previews share the same frozen identity. The DLL
 # serializes them on its main thread. No edits or performance tests overlap.
 def reject(item):
  n,label,op,allowed=item
  x=r.call(n,'batch.preview',{**guard(),'operations':[op]})
  r.check(label,not x['success'] and x.get('error',{}).get('code') in allowed,x.get('error'))
 with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(reject,pending))
 final=call('after-previews','craft.snapshot',{'includeXml':True});proof=audit(prepared['xml'],final['xml'])
 r.check('all previews preserve full craft and identity',proof['equivalent'] and final['identity']==prepared['identity'],proof)
 h1=call('history-after','craft.history');r.check('previews preserve native history',h0==h1)
finally:
 call('restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
 final=call('final','craft.snapshot',{'includeXml':True});proof=audit(base['xml'],final['xml'])
 r.check('original full craft restored',proof['equivalent'],proof)
