"""Plot actual retention samples; trends are observations, not a leak-free pass."""
import json,statistics,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from precision_acceptance import ROOT

root=ROOT/sys.argv[1];samples=json.loads((root/'samples.json').read_text())
summary=json.loads((root/'summary.json').read_text())
rows=[x for x in samples if 0<=x['cycle']<summary['cycles']]
# The original suite assumed 250 stored snapshots; retain its failures. Native
# UndoHistory.MaxUndoSteps counts transitions and retains the current state too.
# Verified against UndoHistory.PushUndo and the observed stable 251 count.
capacity=[x for x in rows if x['runtimeRetention']['nativeUndo']['count']==x['runtimeRetention']['nativeUndo']['maximum']+1]
def trend(items,key):
    xs=[r['cycle'] for r in items];ys=[key(r)/1e6 for r in items]
    if len(xs)<2:return None
    mx=statistics.mean(xs);my=statistics.mean(ys)
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sum((x-mx)**2 for x in xs)
    n=min(10,len(ys)//2)
    return {'samples':len(xs),'minMB':min(ys),'maxMB':max(ys),'firstMB':ys[0],'lastMB':ys[-1],
        'olsMBPerCycle':slope,'edgeWindow':n,'lastMinusFirstWindowMedianMB':statistics.median(ys[-n:])-statistics.median(ys[:n])}
report={'cycleSamples':len(rows),'firstCapacityCycle':capacity[0]['cycle'] if capacity else None,
        'capacitySamples':len(capacity),'postCapacity':{},'meaning':__doc__,
        'capacityInterpretation':'Native MaxUndoSteps counts transitions; maximum retained states is maximum + 1. Original checks are not overwritten.'}
metrics={'privateBytes':lambda r:r['memory']['privateBytes'],
    'managedBytes':lambda r:r['runtimeRetention']['managedBytes'],
    'monoHeapBytes':lambda r:r['runtimeRetention']['unityMemory']['monoHeapBytes'],
    'unityAllocatedBytes':lambda r:r['runtimeRetention']['unityMemory']['allocatedBytes'],
    'unityReservedBytes':lambda r:r['runtimeRetention']['unityMemory']['reservedBytes']}
for k,f in metrics.items():report['postCapacity'][k]=trend(capacity,f)
fully_filled=[x for x in capacity if x['runtimeRetention']['rotationSnapshotCount']==128 and x['runtimeRetention']['checkpointCount']==64 and x['runtimeRetention']['nativeUndo']['xmlBytes']==rows[-1]['runtimeRetention']['nativeUndo']['xmlBytes']]
report['fullyFilled']={'firstCycle':fully_filled[0]['cycle'] if fully_filled else None,'trends':{k:trend(fully_filled,f) for k,f in metrics.items()}}
report['correctedLimitsAudit']={'sampleCount':len(rows),'allSamplesWithinLimits':all(x['runtimeRetention']['nativeUndo']['count']<=x['runtimeRetention']['nativeUndo']['maximum']+1 and x['runtimeRetention']['checkpointCount']<=64 and x['runtimeRetention']['rotationSnapshotCount']<=128 and x['runtimeRetention']['operationResults']['compressedBytes']<=67108864 for x in rows),'originalReportRetained':True}
report['tailWindows']={str(n):{k:trend(rows[-n:],f) for k,f in metrics.items()} for n in (30,50,100) if len(rows)>=n}
inventories=[]
for path in root.glob('*-inventory.json'):
    d=json.loads(path.read_text());label=d['label']
    cycle=-1 if label=='initial' else summary['cycles'] if label=='final' else int(label.split('-')[1])
    inventories.append({'cycle':cycle,'totalObjects':d['totalObjects'],'sumObjectBytes':d['sumObjectBytes'],
        'nativeCleanupLastScheduledSeconds':d.get('nativeResourceCleanupLastScheduledSeconds'),
        'realtimeSeconds':d.get('realtimeSeconds'),'types':d['types']})
inventories.sort(key=lambda x:x['cycle'])
report['objectInventories']=inventories
report['cleanupTimingMeaning']='Native timestamps report scheduling, not independent coroutine completion; no collection is forced. Compare object census and all memory counters, not only the scheduling timestamp.'
heaps=[]
for path in root.glob('*-default-heap.json'):
    label=path.name.removesuffix('-default-heap.json')
    cycle=-1 if label=='initial' else summary['cycles'] if label=='final' else int(label.split('-')[1])
    h=json.loads(path.read_text())['data']['probe']
    assert h['complete'] and not h['timedOut'] and not h['unlockError']
    heaps.append({'cycle':cycle,'busyBytes':h['busyBytes'],'freeBytes':h['freeBytes'],'busyBlocks':h['busyBlocks']})
heaps.sort(key=lambda x:x['cycle'])
report['defaultHeap']={'samples':heaps,'scope':'Default Windows heap only. Busy blocks are allocated, not necessarily leaked; other heaps and allocator reservations are excluded.',
    'afterHistoriesFilled':{k:trend([r for r in heaps if fully_filled and r['cycle']>=fully_filled[0]['cycle'] and r['cycle']<summary['cycles']],lambda r:r[k]) for k in ('busyBytes','freeBytes')}}
fig,axes=plt.subplots(3 if heaps else 2,2,figsize=(13,11 if heaps else 8),constrained_layout=True);xs=[r['cycle'] for r in samples]
axes[0,0].plot(xs,[r['memory']['privateBytes']/1e6 for r in samples],label='OS private');axes[0,0].set_title('OS private memory (MB)')
for key,label in [('managedBytes','Managed used'),('monoHeapBytes','Mono heap')]:
    vals=[(r['runtimeRetention'][key] if key=='managedBytes' else r['runtimeRetention']['unityMemory'][key])/1e6 for r in samples]
    axes[0,1].plot(xs,vals,label=label)
axes[0,1].set_title('Managed memory (overlapping counters, MB)')
for key,label in [('allocatedBytes','Unity allocated'),('reservedBytes','Unity reserved')]:
    axes[1,0].plot(xs,[r['runtimeRetention']['unityMemory'][key]/1e6 for r in samples],label=label)
axes[1,0].set_title('Unity native memory (MB)')
for key,label in [('nativeUndo','Native Undo'),('checkpointCount','Plugin checkpoints'),('rotationSnapshotCount','Native pose snapshots')]:
    axes[1,1].plot(xs,[(r['runtimeRetention'][key]['count'] if key=='nativeUndo' else r['runtimeRetention'][key]) for r in samples],label=label)
axes[1,1].set_title('History / snapshot counts')
if heaps:
    for key,label in [('busyBytes','Heap busy'),('freeBytes','Heap free')]:
        axes[2,0].plot([r['cycle'] for r in heaps],[r[key]/1e6 for r in heaps],marker='o',label=label)
    axes[2,0].set_title('Default Windows heap only (MB)')
    for kind in ('UnityEngine.Mesh','UnityEngine.Material'):
        axes[2,1].plot([r['cycle'] for r in inventories],[next((t['count'] for t in r['types'] if t['type']==kind),0) for r in inventories],marker='o',label=kind.split('.')[-1])
    axes[2,1].set_title('Native resource census (sampled counts)')
for ax in axes.flat:
    ax.set_xlabel('Completed edit + restore cycle');ax.grid(alpha=.25);ax.legend()
    if capacity:ax.axvline(capacity[0]['cycle'],color='black',linestyle=':',alpha=.6)
fig.suptitle('874-part test copy: measured retention; no forced GC')
fig.savefig(root/'retention-observation.png',dpi=145);plt.close(fig)
(root/'independent-memory-analysis.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
