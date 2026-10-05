"""Independent review of captured 0.4.6 S04 runtime acceptance evidence."""
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator

root = Path(__file__).parents[1]
source = Path('D:/codeSpace/sp2_craft_edit/staged-build/S04/retest-0.4.6')
load = lambda name: json.loads((source / name).read_text(encoding='utf-8-sig'))
checks = []
def check(name, value):
    checks.append({'name': name, 'pass': bool(value)})
def points(name):
    return {p['id']: p for p in load(name)['data']['part']['attachPoints']}
def connection(name, a, b, ap, bp):
    return any((c['partA'], c['partB'], c['attachPointsA'], c['attachPointsB'])
               in [(a,b,[ap],[bp]), (b,a,[bp],[ap])]
               for c in load(name)['data']['connections'])

spec = importlib.util.spec_from_file_location('s04_runtime_contracts', root/'cli/contracts.py')
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)

for batch, wing, control, partfile in [
    ('batch-b-add-control-first',13,14,'part-13-tempwing-after-ctl.json'),
    ('batch-e2-add-second-control',13,15,'part-15-tempctl2.json'),
    ('batch-h-add-control-on-flipwing',16,17,'part-16-flipwing-after-ctl.json')]:
    response = load(batch+'.response.json')
    check(batch+' schema', not list(Draft202012Validator(contracts.output_schema('batch.apply')).iter_errors(response)))
    change = response['data']['actualChanges'][0]
    check(batch+' selected surface metadata', response['success'] and change['wingPartId']==wing and change['partId']==control
          and change['controlAttachPointId']==0 and change['wingAttachPointId']==1
          and change['attachmentBasis']=='native_wing_surface_receive_point')
    catalog = load('catalog-'+change['templateId']+'.json')['data']
    check(batch+' real native template provenance', catalog['partTypes']==['ControlSurface-Flap-1'] and catalog['source']=='builtin')
    ps = points(partfile)
    check(batch+' independent connection readback',
          ps[0]['connectedPartIds']==[wing] if control==15 else ps[1]['surface'] and control in ps[1]['connectedPartIds'])
    check(batch+' same revision readback', load(partfile)['data']['identity']==response['data']['identity'])

for wing, partfile, finalpart, connfile in [
    (13,'part-13-tempwing-after-ctl.json','part-13-tempwing-after-hostconnect.json','connections-after-step2.json'),
    (16,'part-16-flipwing-after-ctl.json','part-16-flipwing-final.json','connections-after-step4.json')]:
    ps = points(partfile)
    check(f'{wing} first control left structural root free', not ps[0]['surface'] and ps[0]['available'] and ps[0]['connectedPartIds']==[])
    ps = points(finalpart)
    check(f'{wing} root subsequently connects to host', ps[0]['connectedPartIds']==[1] and connection(connfile,wing,1,0,6))
    check(f'{wing} surface persists after host connection', ps[1]['surface'] and ps[1]['connectedPartIds']==([14] if wing==13 else [17]))

# The file named after-ctl2 was captured at rev6 after a guard rejection,
# before the successful retry. Use the later independent connection read.
check('Two controls share surface without replacing host link',
      all(connection('connections-after-step4.json',control,13,0,1) for control in [14,15])
      and connection('connections-after-step4.json',13,1,0,6))
check('Flipped test actually used mirrored wing', load('shape-16-flipwing-after-mirror.json')['data']['shape']['configuration']['flipped'] is True)
for control, shape, wing in [(14,'shape-14-tempctl-after-add.json',13),(15,'shape-15-tempctl2.json',13),(17,'shape-17-flipctl.json',16)]:
    check(f'{control} actual native owner', load(shape)['data']['shape']['wingPartId']==wing)
rejected = load('batch-f-overlap-must-fail.response.json')
check('Overlap rejected with fingerprint-identical recovery', not rejected['success'] and rejected['error']['code']=='control_surface_overlap'
      and rejected['rollbackResult']['restored'] and rejected['rollbackResult']['fingerprintIdentical'])
check('Independent post-failure fingerprint', load('parts-list-after-step3c.json')['data']['identity']['fingerprint']==rejected['rollbackResult']['beforeFingerprint'])
check('Guard rejection distinguished from overlap', load('batch-e-add-second-control.response.json')['error']['code']=='revision_conflict')

baseline = load('snapshot-baseline.json')['data']
final = load('final-snapshot.json')['data']
checkpoint = load('checkpoint-create.json')['data']
check('New loaded DLL verified', load('capabilities-start.json')['data']['pluginVersion']=='0.4.6')
check('Rollback validated independently', load('rollback-response.json')['data']['validation']['restorationVerified']
      and baseline['identity']['fingerprint']==checkpoint['fingerprint']==final['identity']['fingerprint'])
check('All original part content restored', final['partCount']==12 and baseline['parts']==final['parts'])
connections = load('final-connections.json')['data']['connections']
seen = {3}
while True:
    added = {i for c in connections if c['partA'] in seen or c['partB'] in seen for i in (c['partA'],c['partB'])}-seen
    if not added: break
    seen.update(added)
check('Twelve parts connected by eleven edges', len(connections)==11 and seen=={p['id'] for p in final['parts']})
check('Symmetry groups preserved', load('final-symmetry.json')['data']['groups']==load('symmetry-baseline.json')['data']['groups'])
check('Native three-center values restored', load('final-centers.json')['data']['centers']==load('centers-baseline.json')['data']['centers'])
for path in sorted(source.glob('final-*.json')):
    j=load(path.name)
    check(path.name+' final identity', j['success'] and j['data'].get('identity')==final['identity'])
    kind=next((cmd for prefix,cmd in [('final-parts-list','parts.list'),('final-shape','shape.get'),('final-geometry','parts.geometry'),('final-assembly','parts.assembly'),('final-connections','connections.list'),('final-symmetry','symmetry.get'),('final-centers','craft.centers')] if path.name.startswith(prefix)),None)
    if kind: check(path.name+' schema', not list(Draft202012Validator(contracts.output_schema(kind)).iter_errors(j)))
for name in ['capture-whole-envelope.json','capture-tail-envelope.json']:
    j=load(name)['data']
    check(name+' final complete capture', j['complete'] and not j['staleAtDelivery'] and j['identity']==final['identity'])
    check(name+' images exist', all(Path(f).is_file() for f in j['recommendedImages']))

report={'source':str(source),'identity':final['identity'],'passed':sum(c['pass'] for c in checks),'total':len(checks),'checks':checks,
        'boundary':'Native 0.4.6 runtime readbacks. Whole and tail overview images opened separately. No flight or paint comparison.'}
out=root/'tests/artifacts/staged-build/S04-review/runtime-0.4.6-review.json'
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'total':report['total'],'failures':[c for c in checks if not c['pass']]}))
raise SystemExit(any(not c['pass'] for c in checks))
