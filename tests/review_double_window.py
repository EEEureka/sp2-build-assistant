"""Supplemental audit of double-window parity; retain raw failed assertions.

Only two observed span encodings are compared as exact Decimal vectors, without
tolerance. Equal-distance collider hits have no tie-order guarantee; compare a
multiset of complete hit objects, retaining duplicates. No source state changes.
"""
import json,sys
from collections import Counter
from decimal import Decimal
from precision_acceptance import ROOT
from precision_diff import compare
root=ROOT/sys.argv[1]
def data(n):return json.loads((root/(n+'.json')).read_text(encoding='utf-8-sig'))['data']
diffs=compare(data('native-target')['xml'],data('cli-target')['xml'])
allowed={'Aircraft/Assembly[0]/Parts[0]/Part[id=6]/ProceduralWindow.State[0]/@'+n for n in ('lowerSpan','upperSpan')}
equivalent=all(d['path'] in allowed and [Decimal(v) for v in d['before'].split(',')]==[Decimal(v) for v in d['after'].split(',')] for d in diffs)
rays=[]
for i in range(3):
 a,b=(data(tag+'-'+str(i))['hits'] for tag in ('native-rays','cli-rays'))
 rays.append({'index':i,'sameCompleteHitMultiset':Counter(json.dumps(x,sort_keys=True) for x in a)==Counter(json.dumps(x,sort_keys=True) for x in b)})
before=data('baseline-rays-1')['hits'];after=data('cli-rays-1')['hits']
inner=lambda hits:any(h['partId']==5 and abs(h['distance']-2.2)<1e-6 for h in hits)
front=lambda hits:any(h['partId']==4 and abs(h['distance']-2)<1e-6 for h in hits)
out={'numericStateExactlyEquivalent':equivalent,'rawXmlDifferences':diffs,'rays':rays,
 'enlargedRegionOuterFrontRemoved':front(before) and not front(after),
 'untargetedInnerStillPresent':inner(before) and inner(after),
 'outsideWindowOuterFrontStillPresent':front(data('cli-rays-2')['hits']),
 'meaning':__doc__}
(root/'supplemental-window-audit.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
