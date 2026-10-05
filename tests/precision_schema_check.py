"""Validate captured real CLI envelopes using installed command schemas."""
import json
from pathlib import Path
import subprocess
import sys
import argparse
import jsonschema
sys.path.insert(0,str(Path(__file__).parent))
from precision_acceptance import CLI,ROOT
issues=[];count=0;schemas={};infrastructure=[]
parser=argparse.ArgumentParser()
parser.add_argument('runs',nargs='+')
parser.add_argument('--report',default='schema-audit.json',help='Report basename under the evidence root; use a new name to retain older audits.')
opts=parser.parse_args()
if Path(opts.report).name!=opts.report:parser.error('--report must be a basename')
for run_name in opts.runs:
    root=ROOT/run_name
    checks=json.loads((root/'checks.json').read_text(encoding='utf-8-sig'))
    for call in checks['calls']:
        command=call['command'];result=json.loads((root/(call['label']+'.json')).read_text(encoding='utf-8-sig'))
        if command=='acceptance.host':
            infrastructure.append({'run':run_name,'call':call['label'],'reason':'Separate test-only native host; not part of released CLI contract'})
            continue
        if command not in schemas:
            r=subprocess.run([CLI,'commands','schema','--command',command],capture_output=True,text=True,encoding='utf-8',check=True)
            schemas[command]=json.loads(r.stdout)['data']
        mode='asyncOutputSchema' if call.get('async') else 'outputSchema'
        errors=list(jsonschema.Draft202012Validator(schemas[command][mode]).iter_errors(result))
        count+=1
        for error in errors:issues.append({'run':run_name,'call':call['label'],'path':list(error.path),'message':error.message[:600]})
report={'validatedRealEnvelopes':count,'errorCount':len(issues),'issues':issues,'excludedTestInfrastructure':infrastructure}
(ROOT/opts.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2)[:10000])
sys.exit(bool(issues))
