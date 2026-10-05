"""Real GPU emission branch test using the native Enviro day/night uniform.

Not a flight/weather/time-of-day transition test. The common background host
sets exactly the shader input used by EnviroLightingModule (night 0, day 1).
"""
import json,sys,uuid
from precision_acceptance import Run
from review_restore_state import audit
r=Run(sys.argv[1]);host=sys.argv[2];identity=None;name='SP2Build 050 Precision Lab F2'
def call(label,cmd,args=None,images=False,**kw):
    global identity
    x=r.call(label,cmd,args,images=images,**kw);assert x['success'],x
    data=x['data']
    if data.get('identity'):identity=data['identity']
    return data
def guard():return {'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
def batch(label,operations):return call(label,'batch.apply',{**guard(),'requestId':uuid.uuid4().hex,'operations':operations})
def lighting(label,value):return call(label,'acceptance.host',extra_args=['--host',host,'--action','lighting','--day-night-value',str(value),'--expected-craft-name',name])
base=call('baseline','craft.snapshot',{'includeXml':True});assert base['name']==name and base['partCount']==3
initial=call('host-initial','acceptance.host',extra_args=['--host',host]);assert initial['batchMode'] and initial['craftName']==name
cp=call('checkpoint','craft.checkpoint.create',{**guard(),'requestId':uuid.uuid4().hex,'name':'Night emission original'})['id']
part=next(p['id'] for p in base['parts'] if p['type']=='JFuselage-1')
look=call('materials','appearance.get',{'partIds':[part]})
slot=next(s for s in look['parts'][0]['slots'] if s['assignable'])
slots=[s['slot'] for s in look['parts'][0]['slots'] if s['assignable']]
images={}
try:
    batch('isolated-paint',[{'kind':'appearance.set','mode':'clone','materialId':slot['materialId'],'partIds':[part],'slots':slots,
        'patch':{'name':'Night emission probe','style':'SolidColor','colors':[{'index':0,'rgba':[.15,.35,.55,1]}],
            'metallic':0,'smoothness':0,'emissionDay':0,'emissionNight':0}}])
    look=call('isolated-material','appearance.get',{'partIds':[part]})
    mid=next(s['materialId'] for s in look['parts'][0]['slots'] if s['slot']==slot['slot'])
    for scene,value in [('day',1),('night',0)]:
        state=lighting(scene+'-uniform',value)
        r.check(scene+' native shader input',state['dayNightValue']==value,state)
        for mode,day,night in [('off',0,0),('day-only',4,0),('night-only',0,4)]:
            label=scene+'-'+mode
            batch(label+'-paint',[{'kind':'appearance.set','mode':'shared','materialId':mid,'patch':{'emissionDay':day,'emissionNight':night}}])
            call(label,'designer.capture',{**guard(),'focusPartIds':[part],
                'views':[{'view':'isometric','projection':'orthographic'}],'resolution':{'width':1000,'height':700}},images=True)
            images[label]=str(next((r.root/label).rglob('isometric.png')))
finally:
    lighting('restore-native-uniform',initial['dayNightValue'])
    call('restore-craft','craft.rollback',{**guard(),'requestId':uuid.uuid4().hex,'checkpointId':cp})
    final=call('final','craft.snapshot',{'includeXml':True})
    proof=audit(base['xml'],final['xml']);r.check('full craft restored',proof['equivalent'],proof)
(r.root/'images.json').write_text(json.dumps(images,indent=2))
from PIL import Image,ImageChops,ImageStat
def difference(a,b):
    ia=Image.open(images[a]).convert('RGB');ib=Image.open(images[b]).convert('RGB')
    delta=ImageChops.difference(ia,ib);changed=sum(max(p)>10 for p in delta.getdata())
    return {'changedPixelsOver10':changed,'meanRgbDelta':sum(ImageStat.Stat(delta).mean)/3,'bbox':delta.getbbox()}
evidence={}
for scene,active,inactive in [('day','day-only','night-only'),('night','night-only','day-only')]:
    active_diff=difference(scene+'-off',scene+'-'+active);inactive_diff=difference(scene+'-off',scene+'-'+inactive)
    evidence[scene]={'active':active_diff,'inactive':inactive_diff}
    r.check(scene+' emission branch visibly affects native pixels',active_diff['changedPixelsOver10']>1000,active_diff)
    r.check(scene+' other branch has no pixel effect',inactive_diff['changedPixelsOver10']==0,inactive_diff)
(r.root/'pixel-evidence.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps(evidence))
