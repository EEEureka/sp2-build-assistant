"""Place the gear bay on a fuselage side surface, rather than its end cap."""
import sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
s=r.call('before','craft.snapshot',{'includeXml':True})['data'];assert s['name']=='SP2Build 050 Precision Lab F2'
assert {p['id'] for p in s['parts']}==set(range(1,12))
i=s['identity']
x=r.call('side-host','batch.apply',{'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision'],'requestId':uuid.uuid4().hex,'operations':[
 {'kind':'shape.update','partId':11,'symmetric':False,'patch':{'length':2,'autoResize':False}},
 {'kind':'part.update','partId':11,'changes':[{'path':'Part','attribute':'rotation','value':'0,90,0'}]},
 {'kind':'part.update','partId':10,'changes':[{'path':'Part','attribute':'position','value':'0,2.25,-2.21'}]}]});assert x['success'],x
r.call('bay-geometry','parts.geometry',{'id':10})
r.call('host-geometry','parts.geometry',{'id':11})
r.call('after','craft.snapshot',{'includeXml':True})
