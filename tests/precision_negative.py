"""Discovered native adapter fields: invalid-type preview must reject without edits."""
import json
from precision_acceptance import Run

r=Run('dev5-negative-properties')
before=r.call('baseline','craft.snapshot',{'includeXml':True})['data']
assert before['name'].startswith('SP2Build 050 Precision Lab')
ident=before['identity'];guard={'craftSessionId':ident['craftSessionId'],'expectedRevision':ident['revision']}
ids=[76,215,218,129,293,189,180,181]
bay=next((p['id'] for p in before['parts'] if p['type'].startswith('GearBay')),None)
if bay is not None:ids.append(bay)
fields=[]
seen=set()
for pid in ids:
    result=r.call(f'fields-{pid}','properties.get',{'id':pid,'limit':1000})
    assert result['success']
    for field in result['data']['parts'][0]['fields']:
        if field.get('writeOperation')!='properties.set' or field['propertyId'] in seen:continue
        seen.add(field['propertyId']);fields.append({'partId':pid,**field})
(r.root/'denominator.json').write_text(json.dumps(fields,ensure_ascii=False,indent=2),encoding='utf-8')
for i,field in enumerate(fields):
    bad={}  # Invalid for each adapter's primitive/vector/list/pose representation.
    req={**guard,'operations':[{'kind':'properties.set','partId':field['partId'],'symmetric':False,'patch':{field['propertyId']:bad}}]}
    result=r.call(f'type-{i:03}','batch.preview',req)
    r.check(field['propertyId']+' wrong type rejects',not result['success'] and result['error']['code'] in ('invalid_property_value','invalid_input'),result.get('error'))
    if 'enumValues' in field:
        req['operations'][0]['patch'][field['propertyId']]='__not_a_native_resource__'
        result=r.call(f'enum-{i:03}','batch.preview',req)
        r.check(field['propertyId']+' invalid enum/resource rejects',not result['success'] and result['error']['code'] in ('invalid_property_value','invalid_resource_id'),result.get('error'))
    if field['type'] in ('number','integer') and field.get('limits',{}).get('max') is not None:
        req['operations'][0]['patch'][field['propertyId']]=field['limits']['max']+1
        result=r.call(f'range-{i:03}','batch.preview',req)
        r.check(field['propertyId']+' outside native limits rejects',not result['success'] and result['error']['code']=='property_out_of_range',result.get('error'))
after=r.call('final','craft.snapshot',{'includeXml':True})['data']
r.check('all previews leave fingerprint unchanged',before['identity']==after['identity'])
r.call('history','craft.history')
