"""Read-only committed virtual-memory metadata for the actual game PID.

No process bytes are read or changed. Allocation kinds do not identify owners.
"""
import ctypes,json,sys,collections
from ctypes import wintypes
from pathlib import Path

class Region(ctypes.Structure):
    _fields_=[('base',ctypes.c_void_p),('allocationBase',ctypes.c_void_p),('allocationProtect',wintypes.DWORD),('partitionId',wintypes.WORD),('size',ctypes.c_size_t),('state',wintypes.DWORD),('protect',wintypes.DWORD),('kind',wintypes.DWORD)]
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=ctypes.c_void_p
k.CloseHandle.argtypes=[ctypes.c_void_p]
k.VirtualQueryEx.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(Region),ctypes.c_size_t];k.VirtualQueryEx.restype=ctypes.c_size_t

def sample(pid):
    h=k.OpenProcess(0x400,False,pid)
    if not h:raise ctypes.WinError(ctypes.get_last_error())
    sums={};allocations={};address=0
    try:
        while True:
            row=Region();count=k.VirtualQueryEx(h,address,ctypes.byref(row),ctypes.sizeof(row))
            if not count:break
            if row.state==0x1000:
                kind={0x20000:'private',0x40000:'mapped',0x1000000:'image'}.get(row.kind,str(row.kind))
                key=kind+('-executable' if row.protect&0xf0 else '-nonexecutable')
                sums[key]=sums.get(key,0)+row.size
                base=row.allocationBase or 0;entry=allocations.setdefault(base,{'base':hex(base),'bytes':0,'kind':kind,'executableBytes':0})
                entry['bytes']+=row.size
                if row.protect&0xf0:entry['executableBytes']+=row.size
            next_address=(row.base or 0)+row.size
            if next_address<=address:break
            address=next_address
    finally:k.CloseHandle(h)
    sizes=collections.Counter((x['kind'],x['bytes']) for x in allocations.values())
    return {'pid':pid,'committedBytesByKind':sums,'allocationCount':len(allocations),
        'allocationSizeHistogram':[{'kind':kind,'bytesEach':size,'count':count} for (kind,size),count in sorted(sizes.items())],
        'largestAllocations':sorted(allocations.values(),key=lambda x:x['bytes'],reverse=True)[:40],'meaning':__doc__}

if __name__=='__main__':
    report=sample(int(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(report,indent=2));print(json.dumps(report['committedBytesByKind']))
