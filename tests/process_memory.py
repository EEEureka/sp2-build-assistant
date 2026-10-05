"""Read-only Windows process memory sampling. Never triggers collection."""
import ctypes,time
from ctypes import wintypes
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
