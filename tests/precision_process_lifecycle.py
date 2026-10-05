"""Close an owned batch-mode fixture using the product CLI; audit saved files.

No process termination, desktop input, or direct writes to player craft files.
"""
import ctypes,hashlib,json,subprocess,sys,time,uuid
from ctypes import wintypes
from pathlib import Path
from precision_acceptance import ROOT,CLI

root=ROOT/sys.argv[1]
launch=json.loads((root/'launch.json').read_text(encoding='utf-8-sig'))
assert launch['batchMode'] is True
pid=str(launch['pid'])

def command(name,args=None):
    argv=[CLI,*name.split('.'),'--instance',pid,'--timeout','120']
    if args is not None:
        path=root/'native-quit.input.json';path.write_text(json.dumps(args));argv+=['--input',str(path)]
    result=json.loads(subprocess.check_output(argv,text=True,encoding='utf-8'));assert result['success'],result
    return result

status=command('designer.status')['data']
if '--legacy-host' in sys.argv:
    assert status['pluginVersion']=='0.4.11'
    host_info=json.loads((Path(launch['host'])/'host.json').read_text(encoding='utf-8-sig'))
    assert host_info['pid']==int(pid) and host_info['batchMode'] is True
    native=json.loads(subprocess.check_output([CLI,'acceptance','host','--host',launch['host'],
        '--timeout','30'],text=True,encoding='utf-8'))
    assert native['success'],native
    status['scene']=native['data']['scene']
args={'action':'quit','expectedScene':status['scene'],'requestId':uuid.uuid4().hex}
assert status['scene'] in ('Designer','MainMenu')
if status['scene']=='Designer':
    snap=command('craft.snapshot')['data'];assert snap['name'].startswith('SP2Build 050 Precision Lab')
    args.update(expectedCraftName=snap['name'],craftSessionId=snap['identity']['craftSessionId'],
                expectedRevision=snap['identity']['revision'],discardCurrent=True)
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=ctypes.c_void_p
k.WaitForSingleObject.argtypes=[ctypes.c_void_p,wintypes.DWORD];k.WaitForSingleObject.restype=wintypes.DWORD
k.CloseHandle.argtypes=[ctypes.c_void_p]
# Retain a handle to this exact process, so access errors or PID reuse cannot
# be mistaken for confirmed termination. This never kills a process.
h=k.OpenProcess(0x100000,False,int(pid))
if not h:raise ctypes.WinError(ctypes.get_last_error())
try:
    if '--legacy-host' in sys.argv:
        # 0.4.11 predates designer.control. The separately versioned native
        # fixture host calls Application.Quit; do not claim product coverage.
        assert status['pluginVersion']=='0.4.11'
        result=json.loads(subprocess.check_output([CLI,'acceptance','host','--host',launch['host'],
            '--action','shutdown','--timeout','30'],text=True,encoding='utf-8'))
        assert result['success'],result
        exit_method='acceptance-host Application.Quit (legacy bridge)'
    else:
        result=command('designer.control',args)
        exit_method='product designer.control quit'
    (root/'native-quit.json').write_text(json.dumps(result,indent=2))
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        waited=k.WaitForSingleObject(h,0)
        if waited==0:break
        if waited!=258:raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(.2)
    else:raise RuntimeError('Native shutdown returned but process exit was not confirmed; do not start another game.')
finally:k.CloseHandle(h)
before=json.loads((root/'craft-hashes-before.json').read_text(encoding='utf-8-sig'))
changed=[x['Path'] for x in before if not Path(x['Path']).is_file() or hashlib.sha256(Path(x['Path']).read_bytes()).hexdigest().upper()!=x['Hash']]
crafts=Path.home()/'AppData/LocalLow/Jundroo/SimplePlanes 2/Crafts'
known={x['Path'].lower() for x in before}
added=[str(p) for p in crafts.rglob('*') if p.is_file() and str(p).lower() not in known]
report={'pid':int(pid),'nativeExitConfirmed':True,'exitMethod':exit_method,'checked':len(before),'changedOrMissing':changed,'new':added,'passed':not changed and not added}
(root/'craft-preservation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
assert report['passed'],report
