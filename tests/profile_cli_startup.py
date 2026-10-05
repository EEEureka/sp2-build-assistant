"""Compare launcher overhead without submitting any game operation.

Use installed global sp2build in every tool sample. The empty Python sample
only measures interpreter startup; it never imports or bypasses the CLI.
"""
import json, os, shutil, statistics, subprocess, sys, time
from pathlib import Path

root = Path(__file__).resolve().parent / 'artifacts' / 'precision-0.5.0' / sys.argv[1]
root.mkdir(parents=True, exist_ok=False)
cli = shutil.which('sp2build')
assert cli
cases = {
    'global_cli': [cli, 'version'],
    'cmd_no_autorun': [os.environ['COMSPEC'], '/d', '/c', cli, 'version'],
    'empty_python': [sys.executable, '-c', 'pass'],
}
samples = []
env = dict(os.environ, SP2BUILD_TRACE_TIMINGS='1')
for _ in range(4):
    for label, argv in cases.items():
        started = time.perf_counter()
        proc = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', env=env, timeout=30)
        elapsed = time.perf_counter() - started
        assert proc.returncode == 0, proc.stderr
        if label != 'empty_python':
            assert json.loads(proc.stdout)['success']
        samples.append({'case': label, 'seconds': elapsed, 'trace': proc.stderr})
        (root/'samples.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')
print(json.dumps({k: statistics.median(x['seconds'] for x in samples if x['case']==k) for k in cases}))
