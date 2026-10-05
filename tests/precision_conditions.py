"""Current prerequisite discovery vs guarded native writes, installed CLI only."""
import json,sys,uuid
from precision_acceptance import Run
r=Run(sys.argv[1])
def snap(label):
    x=r.call(label,'craft.snapshot',{'includeXml':True});assert x['success'],x
    assert x['data']['name']=='SP2Build 050 Precision Lab F2'
    return x['data']
def guard():
    i=snap('guard-'+str(len(r.calls)))['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
def apply(label,ops):
    x=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':ops});assert x['success'],x
    return x['data']
def prop(pid,patch):return {'kind':'properties.set','partId':pid,'patch':patch,'symmetric':False}
def fields(label,pid,field_ids=None):
    x=r.call(label,'properties.get',{'id':pid,**({'fields':field_ids} if field_ids else {'limit':1000})});assert x['success'],x
    return {f['propertyId']:f for f in x['data']['parts'][0]['fields']}
def condition(label,pid,key,expected):
    f=fields(label,pid,[key])[key]
    r.check(label+' discovered prerequisite',f.get('currentCondition',{}).get('satisfied','missing') is expected,f.get('currentCondition'))
    return f
def reject(label,pid,key,value):
    before=snap(label+'-before')
    x=r.call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':[prop(pid,{key:value})]})
    r.check(label+' rejects before setter',not x['success'] and x['error']['code']=='property_condition_failed',x.get('error'))
    r.check(label+' XML unchanged',snap(label+'-after')['xml']==before['xml'])

base=snap('baseline');assert base['partCount']==3
cp=r.call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'conditions original'})['data']['id']
try:
    tpl='tpl-86c024231d5edb41'
    catalog=r.call('template-no-live-mount','properties.describe',{'templateId':tpl,'fields':['GearLeg[0].supportStrutType0']});assert catalog['success'],catalog
    cf=next(f for p in catalog['data']['parts'] for f in p['fields'])
    r.check('catalog conditions explicitly unknown',cf.get('currentCondition',{}).get('satisfied','missing') is None,cf.get('currentCondition'))
    created=apply('add-fixtures',[{'kind':'part.add','templateId':t,'temporaryId':k,'position':p} for k,t,p in [
        ('aero',tpl,[4,3,0]),('nose','tpl-ef03f5b3e35e1bbe',[-4,3,0]),('bay','tpl-0e1d278f1dc91cf6',[0,4,-2])]])
    ids=created['temporaryIds'];gear=ids['aero'];nose=ids['nose'];bay=ids['bay']
    for key,pid in [('aero',gear),('nose',nose)]:
        f=fields(key+'-fields',pid)
        points=r.call(key+'-points','connections.points',{'part':pid});assert points['success'],points
        point=next(p for p in points['data']['points'] if p['id']==0)
        r.check(key+' combined connection types decoded',point.get('seekTypeMask')==1025 and set(point.get('seekTypes',[]))=={'Normal','GearBay'},point)
        for suffix in ('supportStrutType0','supportStrutType1','supportStrutType2','torqueLinkType','torqueLinkLength','catapultConnectorEnabled'):
            fid='GearLeg[0].'+suffix;row=f[fid];flag=row.get('currentCondition',{}).get('satisfied')
            r.check(key+' condition known '+suffix,isinstance(flag,bool),row.get('currentCondition'))
            if flag is False:
                value=(row['enumValues'][0] if row.get('enumValues') else row['value'])
                reject(key+'-disabled-'+suffix,pid,fid,value)
        if f['GearLeg[0].catapultConnectorEnabled']['currentCondition']['satisfied']:
            apply(key+'-catapult-off',[prop(pid,{'GearLeg[0].catapultConnectorEnabled':False})])
            condition(key+'-launch-disabled',pid,'GearLeg[0].targetLaunchSpeed',False)
            reject(key+'-launch-reject',pid,'GearLeg[0].targetLaunchSpeed',190)
            apply(key+'-catapult-on',[prop(pid,{'GearLeg[0].catapultConnectorEnabled':True})])
            condition(key+'-launch-enabled',pid,'GearLeg[0].targetLaunchSpeed',True)
            apply(key+'-launch-values',[prop(pid,{'GearLeg[0].targetLaunchSpeed':190,'GearLeg[0].catapultAcceleration':1.3,'GearLeg[0].catapultNoseCompression':.2})])
            read=fields(key+'-launch-readback',pid,['GearLeg[0].targetLaunchSpeed'])
            r.check(key+' launch value effective',read['GearLeg[0].targetLaunchSpeed']['value']==190)
    apply('no-suspension',[prop(gear,{'GearLeg[0].suspensionTravel':0})])
    condition('spring-disabled',gear,'GearLeg[0].springForceScale',False)
    condition('damper-disabled',gear,'GearLeg[0].damperScale',False)
    reject('disabled-spring',gear,'GearLeg[0].springForceScale',1.4)
    apply('enable-then-tune-suspension',[prop(gear,{'GearLeg[0].suspensionTravel':.4}),prop(gear,{'GearLeg[0].springForceScale':1.4,'GearLeg[0].damperScale':1.2})])
    condition('spring-enabled',gear,'GearLeg[0].springForceScale',True)
    apply('bay-auto',[prop(bay,{'GearBay[0].autoHingeAxis':True})])
    hinge=condition('manual-hinge-disabled',bay,'GearBay[0].hingeAxisPose',False)
    reject('auto-hinge-reject',bay,'GearBay[0].hingeAxisPose',hinge['value'])
    apply('bay-manual',[prop(bay,{'GearBay[0].autoHingeAxis':False})])
    condition('manual-hinge-enabled',bay,'GearBay[0].hingeAxisPose',True)
    apply('manual-hinge-noop',[prop(bay,{'GearBay[0].hingeAxisPose':hinge['value']})])
    r.call('fixture-status','designer.status')
finally:
    x=r.call('restore','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp});assert x['success'],x
    r.check('original full XML restored',snap('restored')['xml']==base['xml'])
    r.call('status','designer.status')
