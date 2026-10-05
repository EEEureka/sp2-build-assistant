"""Independent native control/default/boundary parity for fixed F2 fixtures.

No desktop input. Enumerates every discovered field and records exclusions,
rather than treating untested/custom widgets as certified.
"""
import json, sys, uuid
from precision_acceptance import Run
from review_restore_state import audit

r=Run(sys.argv[1])
identity=None
def call(label,cmd,args=None,images=False):
    global identity
    result=r.call(label,cmd,args,images=images)
    assert result['success'],result
    data=result['data']
    if 'identity' in data: identity=data['identity']
    return data
def guard():
    return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def native(label,action,**kwargs):
    return call(label,'acceptance.native',{**guard(),'requestId':uuid.uuid4().hex,
        'expectedCraftName':'SP2Build 050 Precision Lab F2','action':action,**kwargs})
def batch(label,ops):
    return call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops})
def restore(label,checkpoint):
    return call(label,'craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':checkpoint})
base=call('baseline','craft.snapshot',{'includeXml':True})
assert base['name']=='SP2Build 050 Precision Lab F2' and base['partCount']==3
original=call('original-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'Matrix original'})['id']
templates={'window':'tpl-a0c296e1a01292ad','piston':'tpl-c2ea68c52a8d3473','hinge':'tpl-33195a9c4cfc6ff1',
    'jet':'tpl-1a5ee3557bbab375','gear':'tpl-86c024231d5edb41','bay':'tpl-0e1d278f1dc91cf6'}
inventory=[]
try:
    out=batch('prepare',[{'kind':'part.add','templateId':template,'temporaryId':key,'position':[5+5*i,3,0]} for i,(key,template) in enumerate(templates.items())])
    prepared=call('prepared','craft.snapshot',{'includeXml':True})
    baseline=call('prepared-checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'Matrix prepared'})['id']
    base_ids={p['id'] for p in base['parts']}
    for p in prepared['parts']:
        if p['id'] in base_ids:continue
        data=call('properties-'+str(p['id']),'properties.get',{'id':p['id'],'limit':1000})
        # Preserve all capability rows even when the native generic reference is inapplicable.
        for row in data['parts'][0]['fields']:
            if row.get('writeOperation')!='properties.set':continue
            entry={'partId':p['id'],'partType':p['type'],'property':row}
            inventory.append(entry)
    (r.root/'inventory.json').write_text(json.dumps(inventory,indent=2))
    if len(sys.argv)>2 and sys.argv[2]=='inventory':
        print(json.dumps({'count':len(inventory),'checkpointId':baseline,'originalCheckpointId':original}))
    else:
        for index,entry in enumerate(inventory):
            row=entry['property'];key=row['propertyId'];family=row['family'];part=entry['partId']
            tag=f'f{index:03}'
            restore(tag+'-initial',baseline)
            native_result=native(tag+'-controls','inspect',partId=part,modifierType=family+'Data',modifierIndex=int(key.split('[')[1].split(']')[0]))
            controls=[c for c in native_result['controls'] if c['member']==row['nativeMember']]
            if not controls or not controls[0]['referenceSetterSupported'] or not controls[0]['visible']:
                entry['coverage']='needs_custom_or_conditional_reference';continue
            c=controls[0];value=c['value'];values=[('default',value)]
            if isinstance(value,bool):values.append(('toggle',not value))
            elif isinstance(value,(int,float)):
                limits=row.get('limits',{})
                values += [(side,limits[side]) for side in ('min','max') if limits.get(side) is not None]
            elif row.get('enumValues'): values += [('enum-'+str(i),v) for i,v in enumerate(row['enumValues']) if v!=value]
            entry['cases']=[]
            for case,v in values:
                label=tag+'-'+case
                restore(label+'-reference-start',baseline)
                try:
                    native(label+'-native','property',partId=part,modifierType=family+'Data',modifierIndex=int(key.split('[')[1].split(']')[0]),member=c['member'],value=v)
                    target=call(label+'-target','craft.snapshot',{'includeXml':True})
                    restore(label+'-public-start',baseline)
                    batch(label+'-public',[{'kind':'properties.set','partId':part,'symmetric':False,'patch':{key:v}}])
                    actual=call(label+'-actual','craft.snapshot',{'includeXml':True})
                    proof=audit(target['xml'],actual['xml'])
                    r.check(label+' native/full-state parity',proof['equivalent'],proof)
                    entry['cases'].append({'case':case,'requested':v,'passed':proof['equivalent']})
                except AssertionError as exc:
                    r.check(label+' native/full-state parity',False,str(exc))
                    entry['cases'].append({'case':case,'requested':v,'passed':False,'error':str(exc)})
                    call(label+'-failure-state','craft.snapshot',{'includeXml':True})
                    restore(label+'-failure-recovery',baseline)
                (r.root/'inventory.json').write_text(json.dumps(inventory,indent=2))
            entry['coverage']='primitive_cases_executed'
finally:
    restore('restore-original',original)
    final=call('final','craft.snapshot',{'includeXml':True})
    proof=audit(base['xml'],final['xml']);r.check('complete original restored',proof['equivalent'],proof)
    (r.root/'inventory.json').write_text(json.dumps(inventory,indent=2))
