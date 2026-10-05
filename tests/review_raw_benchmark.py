"""Offline full-state review; retain original benchmark failures unmodified."""
import json, sys, xml.etree.ElementTree as ET
from pathlib import Path
from review_restore_state import audit

root = Path(sys.argv[1])
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
base = read(root / 'baseline.json')['data']['xml']
checks = []
for path in sorted(root.glob('state-[0-9][0-9].json')):
    index = int(path.stem.split('-')[1])
    expected = ET.fromstring(base)
    for part in expected.findall('./Assembly/Parts/Part'):
        pid = int(part.get('id'))
        if pid in (4, 76, 77, 78, 79, 129, 215, 218):
            part.set('name', f'Raw benchmark {index:02} {pid}')
    checks.append({'state': path.name, **audit(ET.tostring(expected, encoding='unicode'), read(path)['data']['xml'])})
if len(sys.argv) > 2:
    checks.append({'state': 'after failed rollback', **audit(base, read(Path(sys.argv[2]))['data']['xml'])})
report = {'meaning': 'Exact decimal comparison at the unchanged 0.0001 degree boundary; original run and runtime failure retained.', 'checks': checks}
(root / 'supplemental-decimal-audit.json').write_text(json.dumps(report, indent=2))
print(json.dumps([{'state': c['state'], 'equivalent': c['equivalent'], 'remainingDifferences': c['remainingDifferences']} for c in checks], indent=2))
