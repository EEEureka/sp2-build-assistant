// Diagnostic only. Enumerates the stable default process heap, never private
// third-party heap handles that could disappear concurrently. No GC/compaction.
// Layout and flags: Microsoft PROCESS_HEAP_ENTRY / HeapWalk documentation.
using System;
using System.Runtime.InteropServices;

namespace SP2Acceptance
{
    internal static class Win32HeapProbe
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct NativeSample
        {
            internal int Complete, TimedOut;
            internal uint Error, UnlockError;
            internal long Entries, BusyBlocks, BusyBytes, FreeBlocks, FreeBytes;
            internal long BlockOverheadBytes, RegionCount, RegionCommittedBytes;
            internal long RegionUncommittedBytes, LargestBusyBlock;
            internal double Milliseconds;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst=33)] internal long[] SizeCounts;
        }
        internal sealed class Sample
        {
            public string heap, scope="Default Windows heap only; excludes custom allocators, other heaps, GPU allocations and managed-object attribution.";
            public bool complete, timedOut;
            public uint error, unlockError;
            public long entries, busyBlocks, busyBytes, freeBlocks, freeBytes, blockOverheadBytes;
            public long regionCount, regionCommittedBytes, regionUncommittedBytes, largestBusyBlock;
            public double milliseconds;
            public long[] busySizePowerOfTwoCounts;
            public string histogramMeaning="Index 0 covers <=1 byte; index n covers (2^(n-1), 2^n] bytes. Aggregate block metadata only; no allocation contents read.";
        }
        [DllImport("kernel32.dll")] private static extern IntPtr GetProcessHeap();
        [DllImport("SP2HeapProbe.dll", CallingConvention=CallingConvention.Cdecl)]
        private static extern int ReadOwnedHeap(IntPtr heap,uint budgetMilliseconds,ref NativeSample sample,uint bytes);

        internal static Sample ReadDefault(){return ReadOwned(GetProcessHeap(),2000);}
        // Tests may pass a private heap they created and retain until this ends.
        internal static Sample ReadOwned(IntPtr heap, int budgetMilliseconds)
        {
            if(IntPtr.Size!=8)throw new PlatformNotSupportedException("This probe uses the Windows x64 PROCESS_HEAP_ENTRY layout.");
            if(heap==IntPtr.Zero)throw new InvalidOperationException("Default heap unavailable.");
            var native=new NativeSample{SizeCounts=new long[33]};
            if(ReadOwnedHeap(heap,(uint)budgetMilliseconds,ref native,(uint)Marshal.SizeOf(typeof(NativeSample)))!=1)
                throw new InvalidOperationException("Native heap diagnostic ABI mismatch.");
            return new Sample{heap="0x"+heap.ToInt64().ToString("x"),complete=native.Complete!=0,timedOut=native.TimedOut!=0,
                error=native.Error,unlockError=native.UnlockError,entries=native.Entries,busyBlocks=native.BusyBlocks,
                busyBytes=native.BusyBytes,freeBlocks=native.FreeBlocks,freeBytes=native.FreeBytes,
                blockOverheadBytes=native.BlockOverheadBytes,regionCount=native.RegionCount,
                regionCommittedBytes=native.RegionCommittedBytes,regionUncommittedBytes=native.RegionUncommittedBytes,
                largestBusyBlock=native.LargestBusyBlock,milliseconds=native.Milliseconds,busySizePowerOfTwoCounts=native.SizeCounts};
        }
    }
}
