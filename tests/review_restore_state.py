"""Independent serialized restore audit using the previously frozen rules.

Generated targeting sets are unordered; Custom lists are ordered. Native Euler
roundtrip differences are allowed only within the pre-existing 0.0001 degrees.
No other fields, including generated geometry/mass caches, are excluded.
"""
import json,math,sys,xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from precision_diff import fields

def audit(expected,actual):
    left=ET.fromstring(expected);right=ET.fromstring(actual);normalized=[]
    for root in (left,right):
        for node in root.iter('PartTargeting.State'):
            if node.get('targetMode')!='Custom' and 'partIds' in node.attrib:
                node.set('partIds',','.join(map(str,sorted(set(map(int,filter(None,node.get('partIds').split(','))))))))
    for p,q in zip(left.findall('./Assembly/Parts/Part'),right.findall('./Assembly/Parts/Part')):
        if p.get('id')!=q.get('id'):continue
        a=p.get('rotation');b=q.get('rotation')
        if a!=b and a is not None and b is not None:
            av=list(map(Decimal,a.split(',')));bv=list(map(Decimal,b.split(',')))
            if len(av)==len(bv)==3:
                # Compare serialized decimal angles without binary cancellation
                # at the frozen 0.0001 degree boundary. Do not add an epsilon.
                ds=[abs(x-y)%360 if x.is_finite() and y.is_finite() else Decimal('Infinity') for x,y in zip(av,bv)]
                ds=[min(d,360-d) if d.is_finite() else d for d in ds]
                if all(d.is_finite() and d<=Decimal('0.0001') for d in ds):
                    normalized.append({'partId':int(p.get('id')),'before':a,'after':b,'maxEulerDeltaDegrees':float(max(ds))})
                    q.set('rotation',a)
    a=fields(left);b=fields(right)
    differences=[{'path':k,'before':a.get(k),'after':b.get(k)} for k in sorted(a.keys()|b.keys()) if a.get(k)!=b.get(k)]
    return {'equivalent':not differences,'rawXmlIdentical':expected==actual,'normalizedEuler':normalized,'remainingDifferences':differences,'policy':__doc__}

if __name__=='__main__':
    data=[json.loads(Path(p).read_text(encoding='utf-8-sig'))['data']['xml'] for p in sys.argv[1:3]]
    result=audit(*data)
    if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
