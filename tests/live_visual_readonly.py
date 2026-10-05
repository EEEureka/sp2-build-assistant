"""Read-only visual acceptance against the current open craft; records all cases."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT=Path(__file__).parent/'artifacts'/('visual-accept-'+uuid.uuid4().hex[:8])
ROOT.mkdir(parents=True)
CLI=shutil.which('sp2build')
if not CLI: raise SystemExit('Global sp2build is required')
cases=[]

def call(name, command, args=None, expected=None, extra=()):
    request=ROOT/(name+'.input.json'); output=ROOT/(name+'.json')
    argv=[CLI,*command.split(), '--output',str(output),'--timeout','90',*extra]
    if args is not None:
        request.write_text(json.dumps(args),encoding='utf-8');argv+=['--input',str(request)]
    started=time.monotonic()
    p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=115)
    result=json.loads(output.read_text(encoding='utf-8-sig')) if output.exists() else {'success':False,'error':{'code':'cli_failure','message':p.stderr.decode(errors='replace')}}
    ok=result.get('success') if expected is None else (not result.get('success') and result.get('error',{}).get('code')==expected)
    cases.append({'name':name,'pass':bool(ok),'seconds':round(time.monotonic()-started,3),'code':result.get('error',{}).get('code'),'operationId':result.get('operationId')})
    print(json.dumps(cases[-1]),flush=True)
    (ROOT/'report.json').write_text(json.dumps(cases,indent=2),encoding='utf-8')
    return result

b=call('baseline','craft snapshot',{'includeXml':True})['data'];identity=b['identity']
guard={'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision']}
call('history-before','craft history')
def groups(*selectors):return [{'name':f'group-{i+1}','selector':s} for i,s in enumerate(selectors)]
def req(*selectors,**kwargs):return {**guard,'groups':groups(*selectors),**kwargs}
def capture(name,*selectors,**kwargs):return call(name,'visual capture',req(*selectors,resolution={'width':384,'height':384},**kwargs),extra=('--output-dir',str(ROOT/'images')))
part=lambda *ids:{'kind':'parts','partIds':list(ids)}
all_scope=call('resolve-whole','visual resolve',req({'kind':'craft'}))
call('resolve-missile','visual resolve',req({'kind':'assembly','rootPartId':229}))
call('resolve-wing','visual resolve',req({'kind':'assembly','rootPartId':19}))
call('resolve-neighborhood','visual resolve',req({'kind':'neighborhood','rootPartId':229,'hops':1}))
call('selected-empty','visual resolve',guard,expected='selection_empty')
call('overlap','visual resolve',req(part(19),part(19)),expected='scope_overlap')
call('missing-part','visual resolve',req(part(999999)),expected='part_not_found')
call('stale-revision','visual resolve',{**req(part(19)),'expectedRevision':999999},expected='revision_conflict')
call('wrong-session','visual capture',{**req(part(19)),'craftSessionId':'wrong'},expected='session_conflict')
call('scope-budget','visual resolve',req({'kind':'craft'},maxParts=2),expected='scope_budget')
edge=next(e for e in all_scope['data']['connections'] if {e['partA'],e['partB']}=={229,103})
call('resolve-branch','visual resolve',req({'kind':'branch','rootPartId':229,'stopConnectionKeys':[edge['key']]}))
call('bad-boundary','visual resolve',req({'kind':'branch','rootPartId':229,'stopConnectionKeys':['unknown']}),expected='connection_not_found')
for name,selectors,options in [
    ('fuselage',(part(15),),{}),('two-wings',(part(18),part(19)),{'details':'perGroup'}),
    ('missile',({'kind':'assembly','rootPartId':229},),{}),
    ('two-missiles',({'kind':'assembly','rootPartId':228},{'kind':'assembly','rootPartId':229}),{'details':'perGroup'}),
    ('rotor',(part(20),),{}),('part-frame',(part(18),part(19)),{'frame':{'kind':'part','partId':19}}),
    ('custom-view',(part(19),),{'views':[{'name':'oblique','direction':[-1,-1,-2],'up':[0,1,0]}]}),
    ('whole',({'kind':'craft'},),{})]:
    r=capture(name,*selectors,**options)
    if r.get('success'):
        data=r['data'];manifest=json.loads(Path(data['manifestPath']).read_text())
        v=manifest['views'][0];image=Path(data['outputDirectory'])/v['partIdFile']
        # Decode unfiltered RGBA ID PNG with stdlib, then pick a known visible pixel.
        import struct,zlib
        raw=image.read_bytes();p=8;compressed=b''
        while p<len(raw):
            n=struct.unpack_from('>I',raw,p)[0]
            if raw[p+4:p+8]==b'IDAT':compressed+=raw[p+8:p+8+n]
            p+=n+12
        pixels=zlib.decompress(compressed);width=v['width'];height=v['height'];hit=None
        for y in range(height):
            for x in range(width):
                k=y*(width*4+1)+1+x*4;token=int.from_bytes(pixels[k:k+3],'little')
                if token:hit=(x,y,token);break
            if hit:break
        if hit:
            pick=call(name+'-pick','visual pick',{'captureId':data['captureId'],'view':v['name'],'x':hit[0],'y':hit[1]})
            expected_id=next(p['partId'] for p in manifest['partIdPalette'] if p['index']==hit[2])
            cases.append({'name':name+'-pick-matches-id','pass':pick.get('data',{}).get('partId')==expected_id})
call('bad-camera','visual capture',req(part(19),views=[{'name':'bad','direction':[0,1,0],'up':[0,2,0]}]),expected='invalid_view')
call('pixel-budget','visual capture',req(part(19),resolution={'width':2048}),expected='invalid_input')
final=call('final','craft snapshot',{'includeXml':True})['data']
history=call('history-after','craft history')['data'];old=json.loads((ROOT/'history-before.json').read_text())['data']
cases.append({'name':'aircraft-selection-history-unchanged','pass':b['xml']==final['xml'] and b['selectedPartId']==final['selectedPartId'] and old==history})
(ROOT/'report.json').write_text(json.dumps(cases,indent=2),encoding='utf-8')
print(json.dumps({'root':str(ROOT),'passed':sum(c['pass'] for c in cases),'total':len(cases)}),flush=True)
