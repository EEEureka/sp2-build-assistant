"""Compare all thirty correct samples from byte-identical fixture hosts."""
import json,statistics
from precision_acceptance import ROOT

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
old=read(ROOT/'old-0411-native-reset-benchmark/performance.json')
new=read(ROOT/'dev21-native-reset-benchmark/performance.json')
old_launch=read(ROOT/'old-0411-native-reset-a/launch.json')
new_launch=read(ROOT/'dev21-native-reset-a/launch.json')
assert old['eligibleForThirtySampleGate'] and new['eligibleForThirtySampleGate']
assert old['samples']==new['samples']==30
assert old_launch['hostSha256']==new_launch['hostSha256']
assert old_launch['bridgeSha256']=='3EB3A44332A308850CBCD57FFD0447C1CC01944935306C8CC80FCC09FBF56EB7'
samples=read(ROOT/'dev21-native-reset-benchmark/samples.json')
improvement=1-new['medianSeconds']/old['medianSeconds']
report={'old':old,'new':new,'oldBridgeSha256':old_launch['bridgeSha256'],'newBridgeSha256':new_launch['bridgeSha256'],
        'commonHostSha256':new_launch['hostSha256'],'medianReductionPercent':100*improvement,
        'newAllRebuildCountOne':all(s['rebuildCount']==1 for s in samples),
        'gatePassed':improvement>=.30 and all(s['rebuildCount']==1 for s in samples),
        'scope':'Same 874-part saved lab, eight raw renames, native reload before every sample, identical graphics backend and host. No bridge patches. All samples retained. Preparation excluded; CLI round trip included.',
        'limitations':'Sequential runs on this Windows host; not a universal speedup for native property callbacks, geometry, screenshots or all aircraft. Old bridge did not report rebuildCount or main-thread stage timings.'}
(ROOT/'relative-performance-native-reset.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2));assert report['gatePassed'],report
