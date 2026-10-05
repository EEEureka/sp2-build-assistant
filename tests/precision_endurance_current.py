"""Full-session 30-cycle F3 acceptance using only the installed global CLI.

Process memory/handles are sampled from before the first cycle. This is bounded
observational evidence, not a proof of the absence of all possible leaks.
"""
import ctypes,json,statistics,sys,time,uuid
from ctypes import wintypes
from precision_acceptance import Run
from review_restore_state import audit
r=Run(sys.argv[1]);samples=[]

def state(label):
    a=r.call(label,'designer.status');assert a['success'],a
    d=a['data'];assert not d['identity']['stateUncertain'] and d['sceneIntegrity']['status']=='healthy',d
    return a
def guard(d):
    i=d['identity'];return {'craftSessionId':i['craftSessionId'],'expectedRevision':i['revision']}
class Memory(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(x,ctypes.c_size_t) for x in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
kernel.OpenProcess.restype=ctypes.c_void_p;kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.GetProcessHandleCount.argtypes=[ctypes.c_void_p,ctypes.POINTER(wintypes.DWORD)]
psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(Memory),wintypes.DWORD]
def memory(pid):
    h=kernel.OpenProcess(0x410,False,pid)
    if not h:raise ctypes.WinError(ctypes.get_last_error())
    try:
        m=Memory();m.cb=ctypes.sizeof(m);count=wintypes.DWORD()
        if not psapi.GetProcessMemoryInfo(h,ctypes.byref(m),m.cb):raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.GetProcessHandleCount(h,ctypes.byref(count)):raise ctypes.WinError(ctypes.get_last_error())
        return {'time':time.time(),'privateBytes':m.PrivateUsage,'workingSetBytes':m.WorkingSetSize,'handles':count.value}
    finally:kernel.CloseHandle(h)

base=r.call('baseline','craft.snapshot',{'includeXml':True})['data']
assert base['name']=='SP2Build 050 Precision Lab C17' and base['partCount']==874
ids=[4,76,77,78,79,129,215,218];parts={p['id']:p for p in base['parts']}
assert all(i in parts for i in ids) and parts[76]['type']=='ModifierWindow-1'
first=state('initial-status');pid=first['instancePid'];firstmem=memory(pid)
cp=r.call('baseline-checkpoint','craft.checkpoint.create',{**guard(first['data']),'requestId':uuid.uuid4().hex,'name':'F3 endurance original'})['data']['id']
(r.root/'initial-memory.json').write_text(json.dumps(firstmem,indent=2))
try:
    for i in range(30):
        tag=f'cycle-{i:02}';before=state(tag+'-state')['data'];g=guard(before);mem_before=memory(pid)
        query=r.call(tag+'-query','properties.get',{'id':76,'limit':1000});assert query['success'],query
        ops=[{'kind':'properties.set','partId':76,'patch':{'ProceduralWindow[0].height':.721+i*.00001},'symmetric':False}]
        ops += [{'kind':'part.update','partId':p,'changes':[{'path':'Part','attribute':'name','value':f'Endurance {i} {p}'}],'symmetric':False} for p in ids if p!=76]
        edit=r.call(tag+'-edit','batch.apply',{**g,'requestId':uuid.uuid4().hex,'operations':ops});assert edit['success'],edit
        g=guard(edit['data']);images=r.call(tag+'-capture','designer.capture',{**g,'focusPartIds':ids,'views':[{'view':v,'projection':'perspective' if v=='isometric' else 'orthographic'} for v in ('front','right','top','isometric')],'resolution':{'width':1280,'height':800}},images=True)
        r.check(tag+' native capture',images['success'],images.get('error'))
        geom=r.call(tag+'-geometry','geometry.measure',{**g,'partIdsA':[76],'partIdsB':[77]})
        r.check(tag+' geometry available',geom['success'] and geom['data']['complete'] and geom['data']['measurement'].get('status')!='unavailable',geom.get('error'))
        back=r.call(tag+'-restore','craft.rollback',{**g,'requestId':uuid.uuid4().hex,'checkpointId':cp});assert back['success'],back
        after=state(tag+'-restored')['data'];mem_after=memory(pid)
        actual=r.call(tag+'-restored-snapshot','craft.snapshot',{'includeXml':True})['data']
        restored_audit=audit(base['xml'],actual['xml'])
        (r.root/(tag+'-independent-restore.json')).write_text(json.dumps(restored_audit,indent=2))
        r.check(tag+' independent restored state and single aircraft',restored_audit['equivalent'] and after['sceneIntegrity']['aircraftInstanceCount']==1,{'fingerprintIdentical':after['identity']['fingerprint']==base['identity']['fingerprint'],'normalizedEuler':restored_audit['normalizedEuler'],'remainingDifferences':restored_audit['remainingDifferences']})
        assert restored_audit['equivalent'],restored_audit
        samples.append({'cycle':i,'memoryBefore':mem_before,'memoryAfter':mem_after,'runtimeRetention':after.get('runtimeRetention'),'identity':after['identity'],'sceneIntegrity':after['sceneIntegrity'],
            'timings':{c['command']:c['seconds'] for c in r.calls if c['label'].startswith(tag)},
            'stages':{'edit':edit['data'].get('stageTimings'),'geometry':geom.get('data',{}).get('stageTimings'),'capture':images.get('data',{}).get('stageTimings'),'restore':back['data'].get('stageTimings')},'rebuildCount':edit['data']['rebuildCount']})
        (r.root/'samples.json').write_text(json.dumps(samples,indent=2))
finally:
    current=state('cleanup-state')['data']
    if current['identity']['fingerprint']!=base['identity']['fingerprint']:
        back=r.call('cleanup-restore','craft.rollback',{**guard(current),'requestId':uuid.uuid4().hex,'checkpointId':cp});assert back['success'],back
    final=r.call('final','craft.snapshot',{'includeXml':True});assert final['success'],final
    final_audit=audit(base['xml'],final['data']['xml'])
    (r.root/'final-independent-restore.json').write_text(json.dumps(final_audit,indent=2))
    r.check('final full state restored under frozen policy',final_audit['equivalent'],final_audit)
summary={}
limits={'properties.get':2,'batch.apply':5,'designer.capture':10,'geometry.measure':2}
for command in ('properties.get','batch.apply','designer.capture','geometry.measure','craft.rollback'):
    values=sorted(row['timings'][command] for row in samples)
    summary[command]={'count':len(values),'p50':statistics.median(values),'p95':values[28],'max':max(values),'limitP95Seconds':limits.get(command)}
    if command in limits:r.check(command+' p95 threshold',values[28]<=limits[command],summary[command])
mems=[firstmem]+[x['memoryAfter'] for x in samples]
summary['memory']={'initial':firstmem,'final':mems[-1],'minPrivateBytes':min(m['privateBytes'] for m in mems),'maxPrivateBytes':max(m['privateBytes'] for m in mems),'privateByteSeries':[m['privateBytes'] for m in mems],'handleSeries':[m['handles'] for m in mems],'meaning':'Before first cycle and after every cycle; bounded observation only. Inspect warm-up and sustained growth separately.'}
(r.root/'performance.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
