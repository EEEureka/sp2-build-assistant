"""Re-read the host pose after native auto-recenter before placing the bay."""
import sys,uuid,xml.etree.ElementTree as ET
from precision_acceptance import Run
r=Run(sys.argv[1]);s=r.call('before','craft.snapshot',{'includeXml':True})['data']
assert s['name']=='SP2Build 050 Precision Lab F2'
p=next(p for p in ET.fromstring(s['xml']).findall('./Assembly/Parts/Part') if p.get('id')=='11')
pos=list(map(float,p.get('position').split(',')));pos[2]-=.71
i=s['identity'];x=r.call('align-bay','batch.apply',{'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision'],'requestId':uuid.uuid4().hex,'operations':[{'kind':'part.update','partId':10,'changes':[{'path':'Part','attribute':'position','value':','.join(map(str,pos))}]}]});assert x['success'],x
g=r.call('bay-geometry','parts.geometry',{'id':10});r.check('actual door renderers exist',bool(g['data']['geometry']['renderers']))
r.call('after','craft.snapshot',{'includeXml':True})
