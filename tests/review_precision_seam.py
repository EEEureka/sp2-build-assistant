"""Independent y=0 triangle-plane cuts for the frozen F1 seam fixture.

Consumes exported native triangles only; does not import bridge math or use its
returned section segments as ground truth. The opposite reference face is x=2.5.
"""
import json
import math
from pathlib import Path

root = Path(__file__).parent / 'artifacts/precision-0.5.0/dev6-seam-valid'
mesh = json.loads(next((root/'dense').rglob('meshes.json')).read_text())
cuts = []
for m in mesh['meshes']:
    if m['partId'] != 5:
        continue
    vertices = m['vertices']
    for i in range(0, len(m['indices']), 3):
        tri = [vertices[k] for k in m['indices'][i:i+3]]
        hits = []
        for a, b in zip(tri, tri[1:]+tri[:1]):
            if a[1]*b[1] < 0:
                t = -a[1]/(b[1]-a[1])
                hits.append([a[j]+t*(b[j]-a[j]) for j in range(3)])
            elif a[1] == 0:
                hits.append(a)
        if len(hits) == 2 and all(2.499 <= p[0] <= 2.53 for p in hits):
            cuts.append(hits)
assert cuts, 'No independently computed near-face intersections'
# For a linear segment, maximum x distance from the parallel x=2.5 plane
# is at an endpoint. Crop z to the frozen ROI before comparing endpoints.
cropped = []
for a,b in cuts:
    lo,hi=0.0,1.0
    if b[2] != a[2]:
        t=sorted([(-.49-a[2])/(b[2]-a[2]),(.49-a[2])/(b[2]-a[2])])
        lo=max(lo,t[0]);hi=min(hi,t[1])
    if lo <= hi:
        cropped.extend([[a[j]+t*(b[j]-a[j]) for j in range(3)] for t in (lo,hi)])
worst=max(cropped,key=lambda p:abs(p[0]-2.5))
expected=abs(worst[0]-2.5)
checks=[]
for mode in ('dense','sparse'):
    actual=json.loads((root/(mode+'.json')).read_text())['data']['measurement']
    checks.append({'check':mode+' maximum agrees with independent mesh-plane cut',
                   'pass':abs(actual['sampledMaxMetres']-expected)<=.0001,
                   'expectedMetres':expected,'actualMetres':actual['sampledMaxMetres']})
checks.append({'check':'midpoint defect, not endpoint-only gap',
               'pass':abs(worst[2])<1e-6 and expected>.0069})
report={'method':__doc__,'cutSegments':len(cuts),'worstPoint':worst,'checks':checks,
        'scope':'Frozen piecewise-linear native mesh fixture only. General sampled seams have no certified continuous upper bound.'}
(root/'independent-seam-audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
assert all(x['pass'] for x in checks)
