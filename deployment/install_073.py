"""Transactional sp2model-only installer and confirmed legacy entry retirement.

Only explicit install roots are eligible for retirement. Shared data, unknown
files and historical backups are not removed. No recursive deletion is used.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args, *, env=None, timeout=300):
    result = subprocess.run(list(map(str, args)), capture_output=True, encoding='utf-8', errors='replace',
                            timeout=timeout, env=env,
                            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    if result.returncode: raise ValueError('Subprocess failed: ' + result.stdout[-1000:] + result.stderr[-3000:])
    return result.stdout


def verify_package(package, expected):
    package = Path(package).resolve()
    archive = Path(str(package) + '.zip')
    if sha(archive).lower() != expected.lower(): raise ValueError('ZIP hash differs from the frozen package')
    with zipfile.ZipFile(archive) as zipped:
        seen = set()
        for entry in zipped.infolist():
            if entry.is_dir(): continue
            path = (package / entry.filename).resolve()
            if not path.is_relative_to(package) or path in seen: raise ValueError('Unsafe/duplicate archive destination')
            seen.add(path)
            if path.is_symlink() or sha(path) != hashlib.sha256(zipped.read(entry)).hexdigest(): raise ValueError('Unpacked file differs from ZIP: ' + entry.filename)
        actual = {p.resolve() for p in package.rglob('*') if p.is_file()}
        if actual != seen: raise ValueError('Unpacked package contains missing/extra files')
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8-sig'))
    if not re.fullmatch(r'0\.7\.[34678](?:a\d+)?', str(manifest['version'])) or manifest['acceptanceHooks'] is not False or manifest['testHostIncluded'] is not False: raise ValueError('Production 0.7.3/0.7.4/0.7.6/0.7.7/0.7.8 package required')
    for row in manifest['files']:
        path = (package / row['name']).resolve()
        if not path.is_relative_to(package) or sha(path).lower() != row['sha256'].lower(): raise ValueError('Manifest content mismatch')
    if (package / 'cli/sp2build.py').exists(): raise ValueError('Package must not contain the old public executor')
    return manifest


def legacy_entries(roots):
    entries = []
    for supplied in roots:
        root = Path(supplied).absolute()
        if root.is_symlink() or root.resolve() != root: raise ValueError('Legacy root is redirected; review before retirement: ' + str(root))
        for relative in ('bin/sp2build.cmd', 'bin/sp2build.bat', 'bin/sp2build.ps1', 'bin/sp2build.exe',
                         'app/cli/sp2build.py', 'app/cli/sp2build.pyc', 'app/sp2build.py'):
            path = root / relative
            if not path.exists(): continue
            if path.is_symlink() or not path.resolve().is_relative_to(root): raise ValueError('Legacy entry escapes its confirmed root')
            if path.suffix.lower() in ('.exe', '.pyc'):
                raise ValueError('Binary legacy entry needs explicit ownership review: ' + str(path))
            text = path.read_text(encoding='utf-8-sig')
            if path.suffix.lower() == '.py':
                if 'SP2 Build Assistant CLI' not in text or 'def main(' not in text: raise ValueError('Unknown script ownership: ' + str(path))
            elif 'sp2build.py' not in text or str(root).lower().replace('\\', '/') not in text.lower().replace('\\', '/'):
                raise ValueError('Unknown launcher ownership: ' + str(path))
            entries.append({'path': str(path), 'sha256': sha(path), 'root': str(root)})
    return list({row['path'].lower(): row for row in entries}.values())


def resolution(env=None):
    if os.name != 'nt': return {'powershell': [], 'where': []}
    script = '[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); @(Get-Command sp2build -All -ErrorAction SilentlyContinue | Select-Object Name,CommandType,Source,Definition) | ConvertTo-Json -Compress'
    shell = run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], env=env)
    rows = json.loads(shell) if shell.strip() else []
    if isinstance(rows, dict): rows = [rows]
    where = subprocess.run(['cmd.exe', '/d', '/c', 'where.exe sp2build'], capture_output=True, env=env,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    if where.returncode not in (0, 1): raise ValueError('Cannot verify cmd resolution')
    import ctypes
    encoding = 'cp' + str(ctypes.windll.kernel32.GetOEMCP())
    return {'powershell': rows, 'where': where.stdout.decode(encoding).splitlines()}


def assert_stopped(game):
    if os.name != 'nt': return
    # JSON is passed on stdin, not interpolated into executable shell text.
    script = "[Console]::InputEncoding=[Text.UTF8Encoding]::new($false); [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $taskGamePath=[Console]::In.ReadToEnd().Trim(); @(Get-CimInstance Win32_Process -Filter \"Name='SimplePlanes 2.exe'\" | Where-Object {$_.ExecutablePath -ieq $taskGamePath} | Select-Object ProcessId) | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            input=str(game / 'SimplePlanes 2.exe'), capture_output=True, encoding='utf-8', errors='strict',
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or result.stdout.strip(): raise ValueError('Selected game must be closed before DLL replacement')


def main():
    parser = argparse.ArgumentParser()
    for name in ('package', 'expected-sha256', 'game', 'install-root', 'skill', 'python'): parser.add_argument('--' + name, required=True)
    parser.add_argument('--legacy-root', action='append', default=[])
    parser.add_argument('--isolated', action='store_true')
    parser.add_argument('--acceptance')
    args = parser.parse_args()
    package, game, root, skill = [Path(p).resolve() for p in (args.package, args.game, args.install_root, args.skill)]
    manifest = verify_package(package, args.expected_sha256)
    if sha(game / 'SimplePlanes 2_Data/Managed/Game.dll').lower() != manifest['gameAssemblySha256'].lower(): raise ValueError('Game assembly changed since build')
    global_root = Path.home() / '.sp2build'
    legacy_roots = args.legacy_root or ([str(root)] if args.isolated else [str(root), str(Path(os.environ['LOCALAPPDATA']) / 'SP2BuildAssistant')])
    if args.isolated and (root == global_root.resolve() or any(Path(p).resolve() in (global_root.resolve(), (Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'SP2BuildAssistant').resolve()) for p in legacy_roots)):
        raise ValueError('Isolated installation cannot retire the real global roots')
    if not args.isolated:
        if not args.acceptance: raise ValueError('Global deployment requires a concrete completed migration acceptance receipt')
        acceptance = json.loads(Path(args.acceptance).read_text(encoding='utf-8'))
        if acceptance.get('status') != 'passed' or acceptance.get('packageSha256', '').lower() != args.expected_sha256.lower(): raise ValueError('Acceptance receipt does not certify this package')
    assert_stopped(game)
    entries = legacy_entries(legacy_roots)
    environment = os.environ.copy()
    if args.isolated:
        # Keep OS executables discoverable, while old global PATH entries are
        # excluded from the explicitly isolated acceptance environment.
        managed_global_bins = [str(global_root / 'bin').lower(), str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'SP2BuildAssistant/bin').lower()]
        environment['PATH'] = ';'.join([str(Path(p) / 'bin') for p in legacy_roots] + [p for p in environment.get('PATH', '').split(';') if p.lower().rstrip('\\/') not in managed_global_bins])
    resolved = resolution(environment)
    confirmed = {row['path'].lower() for row in entries}
    exposed = [row.get('Source') or row.get('Definition') for row in resolved['powershell']] + resolved['where']
    if any(not p or p.lower() not in confirmed for p in exposed): raise ValueError('Unmanaged old entry/alias remains; review exact ownership: ' + json.dumps(resolved))
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + os.urandom(3).hex()
    backup = root / 'backups' / ('sp2model-073-' + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    runtime = root / 'sdk' / (manifest['version'] + '-' + stamp)
    plugin = game / 'BepInEx/plugins/SP2BuildAssistant.dll'
    app_skill = root / 'app/skills/sp2-build-assistant'
    launcher = root / 'bin/sp2model.cmd'
    installation = root / 'installation.json'
    paths = [(plugin, backup / 'original.dll'), (skill, backup / 'agent-skill'), (app_skill, backup / 'app-skill'), (launcher, backup / 'sp2model.cmd'), (installation, backup / 'installation.json')]
    had = {}
    for path, saved in paths:
        had[str(path)] = path.exists()
        if path.is_dir(): shutil.copytree(path, saved)
        elif path.exists(): shutil.copy2(path, saved)
    (backup / 'retirement-plan.json').write_text(json.dumps({'entries': entries, 'resolutionBefore': resolved}, indent=2), encoding='utf-8')
    run([args.python, '-I', '-X', 'utf8', '-m', 'venv', runtime])
    python = runtime / 'Scripts/python.exe'
    wheel = package / ('sp2model-' + manifest['version'] + '-py3-none-any.whl')
    run([python, '-I', '-X', 'utf8', '-m', 'pip', 'install', '--no-index', '--no-deps', wheel])
    run([python, '-I', '-X', 'utf8', '-m', 'sp2model', 'version'])
    # Owned worker: fully offline and with new code/resources, no old fallback.
    worker_env = environment.copy(); worker_env['SP2MODEL_HOME'] = str(root)
    worker_env.pop('SP2MODEL_REFERENCE_PYTHON', None)
    worker_code = "from sp2model import Runtime; import sys,json; print(json.dumps(Runtime().call('feature.setup',{'python':sys.argv[1],'offline':True,'wheelhouse':sys.argv[2]})))"
    run([python, '-I', '-X', 'utf8', '-c', worker_code, args.python, package / 'worker-wheelhouse'], env=worker_env)
    run([python, '-I', '-X', 'utf8', Path(__file__).with_name('verify_sdk_install.py'), '--wheel', wheel, '--skill', package / 'skills/sp2-build-assistant', '--output', backup / 'staged-verification.json'])
    retired, installed_files = [], []
    def install_file(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        installed_files.append(destination)
        shutil.copy2(source, destination)
    receipt = {'status': 'staged', 'version': manifest['version'], 'packageSha256': args.expected_sha256,
               'runtime': str(runtime), 'backup': str(backup), 'isolated': args.isolated,
               'legacyDataDeleted': False, 'testHostInstalled': False, 'acceptanceHooks': False}
    try:
        assert_stopped(game)
        install_file(package / 'SP2BuildAssistant.dll', plugin)
        for destination in (skill, app_skill):
            for source in (package / 'skills/sp2-build-assistant').rglob('*'):
                if source.is_file(): install_file(source, destination / source.relative_to(package / 'skills/sp2-build-assistant'))
        launcher.parent.mkdir(parents=True, exist_ok=True)
        installed_files.append(launcher)
        launcher.write_text('@echo off\nsetlocal\nset "SP2MODEL_HOME=%~dp0.."\n"' + str(python) + '" -I -X utf8 -m sp2model %*\nexit /b %errorlevel%\n', encoding='utf-8')
        # Retirement occurs only after the staged new installation verifies.
        for index, row in enumerate(entries):
            path = Path(row['path'])
            if sha(path) != row['sha256']: raise ValueError('Legacy entry changed since inventory')
            destination = backup / 'retired' / (str(index) + '-' + path.name)
            destination.parent.mkdir(exist_ok=True)
            os.replace(path, destination)
            retired.append((path, destination))
        after = resolution(environment)
        if after['powershell'] or after['where']: raise ValueError('Old tool still resolves after retirement')
        if any(Path(row['path']).exists() for row in entries): raise ValueError('Known absolute entry remains callable')
        if sha(plugin).lower() != sha(package / 'SP2BuildAssistant.dll').lower(): raise ValueError('Installed DLL mismatch')
        if manifest['version'].startswith('0.7.8'):
            info = json.loads((package / 'release-info.json').read_text(encoding='utf-8'))
            if info['sdkVersion'] != manifest['version']: raise ValueError('Release/SDK versions disagree')
            installed_files.append(installation)
            installation.write_text(json.dumps({'schemaVersion': 'sp2model.installation/1',
                'pluginPath': str(plugin.resolve()), 'pluginSha256': sha(plugin), 'pluginVersion': info['pluginVersion'],
                'sdkVersion': manifest['version'], 'runtime': str(runtime), 'installRoot': str(root),
                'backupPath': str(backup), 'packageSha256': args.expected_sha256}, indent=2), encoding='utf-8')
        run([python, '-I', '-X', 'utf8', Path(__file__).with_name('verify_sdk_install.py'), '--wheel', wheel, '--skill', skill, '--output', backup / 'installed-verification.json'])
        receipt.update(status='installed_retired_pending_native_verification', retired=entries, resolutionAfter=after,
                       python=str(python), launcher=str(launcher), plugin=str(plugin), workerManaged=True)
    except Exception as error:
        for path, saved in reversed(retired): os.replace(saved, path)
        # Exact files added by this transaction can be removed individually;
        # never recursively delete shared directories or junctions.
        for path in reversed(installed_files):
            if path.is_file() and not path.is_symlink(): path.unlink()
        for path, saved in paths:
            if not had[str(path)]: continue
            if saved.is_dir(): shutil.copytree(saved, path, dirs_exist_ok=True)
            else: path.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(saved, path)
        receipt.update(status='rolled_back_old_entries_restored', error=str(error), oldToolRetired=False)
        (backup / 'deployment.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        raise
    (backup / 'deployment.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__': main()
