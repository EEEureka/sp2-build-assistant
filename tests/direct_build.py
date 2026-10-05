"""Recorded integration/build sessions through the installed global CLI only.

Import helpers from one-shot stage scripts. Never replays a mutation automatically.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).parent / 'artifacts/staged-build/direct-0.4.8'
if os.name == 'nt':
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
        os.environ['PATH'] = winreg.QueryValueEx(key, 'Path')[0] + ';' + os.environ['PATH']
CLI = shutil.which('sp2build')
if not CLI: raise RuntimeError('Global sp2build command missing')

class Session:
    def __init__(self, stage):
        self.path=ROOT/stage; self.path.mkdir(parents=True,exist_ok=True)
        self.sequence=max([int(p.name.split('-')[0]) for p in self.path.glob('[0-9][0-9][0-9][0-9]-*.json')]+[0])
        self.checks=[]
    def call(self, command, payload=None, flags=(), label=None, require=True):
        self.sequence+=1
        base=f'{self.sequence:04d}-{label or command}'
        args=[CLI,*command.split('.'),'--json','--timeout','90',*map(str,flags)]
        if payload is not None:
            input_path=(self.path/(base+'-input.json')).resolve()
            input_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            args+=['--input',str(input_path)]
        proc=subprocess.run(args,capture_output=True,encoding='utf-8',timeout=105)
        try: data=json.loads(proc.stdout)
        except Exception:
            (self.path/(base+'-unknown.txt')).write_text(proc.stdout+'\n'+proc.stderr,encoding='utf-8')
            raise RuntimeError('Unknown CLI outcome. Inspect saved request; do not retry mutation.')
        (self.path/(base+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        with (self.path/'calls.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'file':base+'.json','command':command,'args':args[1:],'exitCode':proc.returncode,'success':data.get('success'),'operationId':data.get('operationId')})+'\n')
        if not data.get('success'):
            print('ERROR',base,json.dumps({'error':data.get('error'),'rollbackResult':data.get('rollbackResult')}),flush=True)
            if require or data.get('error',{}).get('code')=='wait_timeout': raise RuntimeError('CLI failure; see '+base)
        elif proc.returncode: raise RuntimeError('CLI exit mismatch')
        return data
    def read(self,command,payload=None,flags=(),label=None):
        return self.call(command,payload,flags,label)['data']
    def guard(self,command,**payload):
        identity=self.read('designer.status')['identity']
        return self.call(command,{'requestId':uuid.uuid4().hex,'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision'],**payload})['data']
    def apply(self,*operations,require=True,label='batch'):
        identity=self.read('designer.status')['identity']
        result=self.call('batch.apply',{'requestId':uuid.uuid4().hex,'craftSessionId':identity['craftSessionId'],'expectedRevision':identity['revision'],'operations':operations},label=label,require=require)
        if result.get('success'): print('APPLIED',label,'rev',result['data']['identity']['revision'],'changes',json.dumps(result['data']['actualChanges']),flush=True)
        return result
    def check(self,label,result):
        self.checks.append({'name':label,'pass':bool(result)})
        (self.path/'checks.json').write_text(json.dumps(self.checks,indent=2),encoding='utf-8')
        print('PASS' if result else 'FAIL',label,flush=True)
        if not result: raise AssertionError(label)
    def capture(self,groups=None,label='capture',details='auto'):
        ident=self.read('designer.status')['identity']
        data=self.read('visual.capture',{'craftSessionId':ident['craftSessionId'],'expectedRevision':ident['revision'],
            'groups':groups or [{'name':'craft','selector':{'kind':'craft'}}],
            'views':['front','right','top','isometric'],'resolution':{'width':640,'height':640},'details':details},
            flags=('--output-dir',str((self.path/'visual').resolve())),label=label)
        print('IMAGES',json.dumps(data['recommendedImages']),flush=True)
        return data

def raw(part, **attrs):
    return {'kind':'part.update','partId':part,'changes':[{'path':'InputController.State','attribute':k,'value':v} for k,v in attrs.items()]}

def states(part):
    return {n['element']:n['attributes'] for n in part['state']['children']}
