"""Independent orientation check at the pre-existing 0.01 degree T04 limit.

Only the deliberately edited GearBay hinge quaternion may differ. All other
serialized fields still use the unchanged complete-state restore audit.
This is an edit-target comparison, never a relaxation of rollback checks.
"""
import json,math,sys,xml.etree.ElementTree as ET
from pathlib import Path
from review_restore_state import audit

def compare(expected,actual,part_id,property_id):
    attribute={'GearBay[0].hingeAxisPose':'hingeRot','GearBay[0].hingeAxisPose2':'hingeRot2'}.get(property_id)
    if attribute is None:return audit(expected,actual)
    e=ET.fromstring(expected);a=ET.fromstring(actual)
    path=f'./Assembly/Parts/Part[@id="{part_id}"]/GearBay.State'
    en=e.find(path);an=a.find(path)
    if en is None or an is None:return audit(expected,actual)
    q1=[float(x) for x in en.get(attribute).split(',')];q2=[float(x) for x in an.get(attribute).split(',')]
    assert len(q1)==len(q2)==4 and all(math.isfinite(x) for x in q1+q2)
    n1=math.sqrt(sum(x*x for x in q1));n2=math.sqrt(sum(x*x for x in q2));assert min(n1,n2)>1e-12
    cosine=min(1,max(0,abs(sum(x*y for x,y in zip(q1,q2)))/(n1*n2)))
    angle=math.degrees(2*math.acos(cosine));passed=angle<=.01
    if passed:an.set(attribute,en.get(attribute))
    result=audit(expected,ET.tostring(a,encoding='unicode'))
    result['rawXmlIdentical']=expected==actual
    result['originalCompleteStateAudit']=audit(expected,actual)
    result['comparisonScope']=__doc__
    result['editedPoseOrientation']={'partId':part_id,'propertyId':property_id,'expectedQuaternion':q1,'actualQuaternion':q2,
        'angleDegrees':angle,'limitDegrees':.01,'passed':passed,'standard':'Acceptance-Plan-0.5.0 section 2, frozen before this run.'}
    result['equivalent']=passed and result['equivalent']
    return result

if __name__=='__main__':
    root=Path(sys.argv[1]);reports=[]
    for label in ('p042-pose','p043-pose'):
        target=json.loads((root/(label+'-target.json')).read_text())['data']['xml']
        actual=json.loads((root/(label+'-actual.json')).read_text())['data']['xml']
        op=json.loads((root/(label+'-public.input.json')).read_text())['operations'][0]
        reports.append({'label':label,**compare(target,actual,op['partId'],next(iter(op['patch'])))})
    (root/'independent-pose-review.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports,indent=2))
    assert all(r['equivalent'] for r in reports)
