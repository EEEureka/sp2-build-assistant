using System;
using System.Runtime.InteropServices;
using SP2Acceptance;
internal static class Win32HeapProbeTests
{
    [DllImport("kernel32.dll",SetLastError=true)] private static extern IntPtr HeapCreate(uint options,UIntPtr initial,UIntPtr maximum);
    [DllImport("kernel32.dll",SetLastError=true)] private static extern IntPtr HeapAlloc(IntPtr heap,uint flags,UIntPtr bytes);
    [DllImport("kernel32.dll",SetLastError=true)] private static extern bool HeapFree(IntPtr heap,uint flags,IntPtr block);
    [DllImport("kernel32.dll",SetLastError=true)] private static extern bool HeapDestroy(IntPtr heap);
    private static void Check(bool test,string name){if(!test)throw new Exception(name);Console.WriteLine("PASS "+name);}
    private static void Main()
    {
        var heap=HeapCreate(0,new UIntPtr(1024*1024),new UIntPtr(4*1024*1024));
        if(heap==IntPtr.Zero)throw new Exception("Private test heap creation failed.");
        try{
            var first=Win32HeapProbe.ReadOwned(heap,2000);
            Check(first.complete && !first.timedOut,"empty private heap enumeration completed");
            var a=HeapAlloc(heap,0,new UIntPtr(65536));var b=HeapAlloc(heap,0,new UIntPtr(131072));
            Check(a!=IntPtr.Zero && b!=IntPtr.Zero,"known allocations created");
            var busy=Win32HeapProbe.ReadOwned(heap,2000);
            Check(busy.complete && busy.busyBytes-first.busyBytes==196608,"x64 layout measures exact live payload bytes");
            Check(busy.busyBlocks-first.busyBlocks==2,"exact live block count");
            Check(busy.busySizePowerOfTwoCounts[16]==first.busySizePowerOfTwoCounts[16]+1 &&
                busy.busySizePowerOfTwoCounts[17]==first.busySizePowerOfTwoCounts[17]+1,"size bins distinguish allocations");
            Check(HeapFree(heap,0,a) && HeapFree(heap,0,b),"known blocks freed");
            var freed=Win32HeapProbe.ReadOwned(heap,2000);
            Check(freed.complete && freed.busyBytes==first.busyBytes,"live bytes return after frees without compacting");
            Console.WriteLine("Before/allocated/freed busy bytes: {0}/{1}/{2}; free bytes: {3}/{4}/{5}; region committed bytes: {6}/{7}/{8}",
                first.busyBytes,busy.busyBytes,freed.busyBytes,first.freeBytes,busy.freeBytes,freed.freeBytes,
                first.regionCommittedBytes,busy.regionCommittedBytes,freed.regionCommittedBytes);
            // Windows may return freed pages instead of retaining a free block.
            // The probe must distinguish that from payload still being live.
            Check(freed.freeBytes>=0 && freed.regionCommittedBytes<=busy.regionCommittedBytes,
                "free blocks and committed regions remain distinct after automatic decommit");
            var again=Win32HeapProbe.ReadOwned(heap,2000);
            Check(again.complete && again.busyBytes==freed.busyBytes && again.freeBytes==freed.freeBytes,"read-only repeated census stable");
            var blocks=new IntPtr[2048];
            for(int i=0;i<blocks.Length;i++){blocks[i]=HeapAlloc(heap,0,new UIntPtr(32));if(blocks[i]==IntPtr.Zero)throw new Exception("Test allocation failed.");}
            var bounded=Win32HeapProbe.ReadOwned(heap,0);
            Check(bounded.timedOut && !bounded.complete && bounded.unlockError==0,"time budget reports partial census and releases lock");
            for(int i=0;i<blocks.Length;i++)if(!HeapFree(heap,0,blocks[i]))throw new Exception("Timed probe left heap unusable.");
            Check(Win32HeapProbe.ReadOwned(heap,2000).complete,"heap remains usable after partial probe");
        }finally{if(!HeapDestroy(heap))throw new Exception("Test heap cleanup failed.");}
        var process=Win32HeapProbe.ReadDefault();
        Check(process.complete && !process.timedOut && process.unlockError==0,"default process heap census completes in one native call");
        Console.WriteLine("Default heap: {0} blocks, {1} busy bytes, {2} free bytes, {3:F3} ms",
            process.busyBlocks,process.busyBytes,process.freeBytes,process.milliseconds);
    }
}
