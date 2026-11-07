"""Authenticated artifact delivery, without a legacy CLI or token export."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import uuid
from .errors import ModelingError


def download(client, result, directory):
    data = deepcopy(result)
    if 'artifactBase' not in data: return data
    capture = data.get('captureId', '')
    def fail(message): raise ModelingError('invalid_artifact', message, {'captureId': capture})
    if not re.fullmatch(r'[a-f0-9]{32}', capture) or data['artifactBase'] != 'v1/visual/' + capture + '/': fail('Invalid artifact identity')
    files = data.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 220: fail('Invalid file count')
    names, total = set(), 0
    for row in files:
        name, size, digest = row.get('name', ''), row.get('bytes'), row.get('sha256', '')
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.(png|json)', name) or name in names or '..' in name: fail('Unsafe/duplicate artifact name')
        if type(size) is not int or not 0 < size <= 80 * 1024 * 1024 or not re.fullmatch(r'[a-f0-9]{64}', digest): fail('Invalid hash or size')
        names.add(name); total += size
    if total > 192 * 1024 * 1024 or 'manifest.json' not in names: fail('Artifact set incomplete or too large')
    root = Path(directory).expanduser().resolve()
    target = root / capture
    if target.is_symlink() or target.exists() and target.resolve().parent != root: fail('Output escapes selected directory')
    target.mkdir(parents=True, exist_ok=True)
    for row in files:
        path = target / row['name']
        if path.is_symlink(): fail('Refusing symlink output')
        if path.is_file() and path.stat().st_size == row['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']: continue
        blob = client.artifact(capture, row['name'])
        if len(blob) != row['bytes'] or hashlib.sha256(blob).hexdigest() != row['sha256']:
            raise ModelingError('artifact_integrity', 'Downloaded artifact differs from its manifest.', {'captureId': capture, 'name': row['name']})
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
        try: temporary.write_bytes(blob); os.replace(temporary, path)
        finally: temporary.unlink(missing_ok=True)
    images = data.get('recommendedImages', [])
    if any(name not in names or not name.endswith('.png') for name in images): fail('Invalid recommended image')
    data.update(outputDirectory=str(target), manifestPath=str(target / 'manifest.json'), recommendedImages=[str(target / name) for name in images])
    for recommendation in data.get('imageRecommendations', []):
        for key in ('primary', 'secondary'):
            if key in recommendation:
                if recommendation[key] not in names: fail('Unknown image recommendation')
                recommendation[key] = str(target / recommendation[key])
    return data
