// Test-only: one native call holds/unlocks the heap. No managed safepoints,
// callbacks, allocation, logging or serialization occur inside the walk.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

struct HeapSample {
    int complete, timedOut;
    DWORD error, unlockError;
    unsigned long long entries, busyBlocks, busyBytes, freeBlocks, freeBytes;
    unsigned long long blockOverheadBytes, regionCount, regionCommittedBytes;
    unsigned long long regionUncommittedBytes, largestBusyBlock;
    double milliseconds;
    unsigned long long busySizePowerOfTwoCounts[33];
};

extern "C" __declspec(dllexport) int __cdecl ReadOwnedHeap(
    HANDLE heap, DWORD budgetMilliseconds, HeapSample* out, DWORD outBytes)
{
    if (!heap || !out || outBytes != sizeof(HeapSample)) return 0;
    *out = {};
    LARGE_INTEGER start, frequency, finish;
    QueryPerformanceCounter(&start); QueryPerformanceFrequency(&frequency);
    const ULONGLONG deadline = GetTickCount64() + budgetMilliseconds;
    PROCESS_HEAP_ENTRY entry = {};
    if (!HeapLock(heap)) { out->error = GetLastError(); return 1; }
    __try {
        while (HeapWalk(heap, &entry)) {
            ++out->entries;
            if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY) {
                ++out->busyBlocks; out->busyBytes += entry.cbData;
                out->blockOverheadBytes += entry.cbOverhead;
                if (entry.cbData > out->largestBusyBlock) out->largestBusyBlock = entry.cbData;
                DWORD size = entry.cbData, bucket = 0;
                if (size > 1) { --size; while (size) { ++bucket; size >>= 1; } }
                ++out->busySizePowerOfTwoCounts[bucket];
            } else if (entry.wFlags & PROCESS_HEAP_REGION) {
                ++out->regionCount;
                out->regionCommittedBytes += entry.Region.dwCommittedSize;
                out->regionUncommittedBytes += entry.Region.dwUnCommittedSize;
            } else if (!(entry.wFlags & PROCESS_HEAP_UNCOMMITTED_RANGE)) {
                ++out->freeBlocks; out->freeBytes += entry.cbData;
                out->blockOverheadBytes += entry.cbOverhead;
            }
            if (!(out->entries & 1023) && GetTickCount64() >= deadline) { out->timedOut = 1; break; }
        }
        if (!out->timedOut) { out->error = GetLastError(); out->complete = out->error == ERROR_NO_MORE_ITEMS; }
    } __finally {
        if (!HeapUnlock(heap)) { out->unlockError = GetLastError(); out->complete = 0; }
    }
    QueryPerformanceCounter(&finish);
    out->milliseconds = (finish.QuadPart - start.QuadPart) * 1000.0 / frequency.QuadPart;
    return 1;
}
