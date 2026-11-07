"""Bounded GitHub release notices. Never edits a craft or installs software.

status/guide only read local evidence. check is an explicit HTTPS GET; installed
live entrypoints schedule a hidden worker and never wait for its network work.
No game discovery, credentials, remote prose or downloaded executable content.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from .errors import ModelingError

RELEASE = json.loads((Path(__file__).parent / 'resources/release-info.json').read_text(encoding='utf-8'))
SCHEMA = 'sp2model.updates/1'
MAX_BYTES = 4 * 1024 * 1024
MAX_PAGES = 3
INTERVAL = 86400
_REPO = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z')
_VERSION = re.compile(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:(?:-)?(alpha|beta|rc|a|b)[.-]?(0|[1-9]\d*))?(?:\+[A-Za-z0-9.-]+)?\Z')


def version_key(value):
    """Numeric SemVer plus the SDK's aN/bN spelling; unknown tags stay unknown."""
    if not isinstance(value, str) or len(value) > 100:
        return None
    match = _VERSION.fullmatch(value)
    if not match:
        return None
    major, minor, patch, phase, number = match.groups()
    return (int(major), int(minor), int(patch), {'a': 0, 'alpha': 0, 'b': 1, 'beta': 1, 'rc': 2, None: 3}[phase], int(number or 0))


def _stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _json(path, limit=MAX_BYTES):
    if not path.is_file() or path.stat().st_size > limit:
        return None
    def reject(value):
        raise ValueError('Non-finite JSON')
    value = json.loads(path.read_text(encoding='utf-8-sig'), parse_constant=reject)
    return value


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(url, headers, timeout):
    """Only public release metadata; no browser/game/GitHub credentials."""
    request = Request(url, headers=headers, method='GET')
    try:
        response = build_opener(_NoRedirect()).open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        status = response.code
        public_headers = {k.lower(): v for k, v in response.headers.items()}
        raw = response.read(MAX_BYTES + 1) if status == 200 else b''
        if len(raw) > MAX_BYTES:
            raise ValueError('Release response exceeds bound')
        return status, public_headers, raw


def _safe_url(value, repository, *, asset=False):
    if not isinstance(value, str) or len(value) > 1500 or any(ord(c) < 33 for c in value):
        return None
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.netloc != 'github.com' or parsed.query or parsed.fragment:
        return None
    prefix = '/' + repository.lower() + ('/releases/download/' if asset else '/releases/tag/')
    return value if parsed.path.lower().startswith(prefix) and '/..' not in parsed.path else None


def _release(row, repository):
    if not isinstance(row, dict) or type(row.get('draft')) is not bool or type(row.get('prerelease')) is not bool:
        raise ValueError('Malformed release flags')
    if row['draft']:
        return None
    tag = row.get('tag_name')
    key = version_key(tag)
    if key is None:
        return None
    url = _safe_url(row.get('html_url'), repository)
    if not url:
        raise ValueError('Release URL does not match repository')
    result = {'version': tag, 'url': url, 'prerelease': row['prerelease'] or key[3] != 3, 'assets': []}
    assets = row.get('assets', [])
    if not isinstance(assets, list):
        raise ValueError('Malformed release assets')
    for item in assets[:30]:
        if not isinstance(item, dict):
            raise ValueError('Malformed asset')
        name = item.get('name')
        link = _safe_url(item.get('browser_download_url'), repository, asset=True)
        if not link or not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,159}', name):
            continue
        digest = item.get('digest')
        digest = digest if isinstance(digest, str) and re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest) else None
        result['assets'].append({'name': name, 'url': link, 'sha256': digest[7:].lower() if digest else None})
    # Names, descriptions, bodies and remote instructions are deliberately absent.
    return result


def _lease(path, now, seconds=60):
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    try:
        with path.open('x', encoding='ascii') as stream:
            json.dump({'token': token, 'expires': now + seconds}, stream)
        return token
    except FileExistsError:
        try:
            previous = _json(path, 1024)
            if previous and type(previous.get('expires')) in (int, float) and previous['expires'] < now:
                path.unlink()
                return _lease(path, now, seconds)
        except (OSError, ValueError, TypeError):
            # An unreadable lease is not permission to race another writer.
            pass
        return None


def _release_lease(path, token):
    try:
        if (_json(path, 1024) or {}).get('token') == token:
            path.unlink()
    except (OSError, ValueError, TypeError):
        pass


class Updates:
    def __init__(self, runtime=None, *, home=None, request=None, clock=None):
        self.runtime = runtime
        self.home = Path(home or os.environ.get('SP2MODEL_HOME') or Path.home() / '.sp2build').expanduser().resolve()
        self.request = request or _request
        self.clock = clock or time.time

    def _config(self, channel=None):
        config = {'repository': RELEASE['repository'], 'channel': RELEASE['channel'], 'automatic': True,
                  'intervalSeconds': INTERVAL, 'timeoutSeconds': 3}
        path = self.home / 'updates.json'
        if path.exists():
            custom = _json(path, 16384)
            if not isinstance(custom, dict) or custom.keys() - config.keys():
                raise ModelingError('invalid_update_config', 'Unknown update configuration fields.')
            config.update(custom)
        if channel is not None:
            config['channel'] = channel
        if (not isinstance(config['repository'], str) or not _REPO.fullmatch(config['repository']) or
                '..' in config['repository'] or config['channel'] not in ('stable', 'prerelease') or
                type(config['automatic']) is not bool or type(config['intervalSeconds']) is not int or
                not 3600 <= config['intervalSeconds'] <= 604800 or
                type(config['timeoutSeconds']) not in (int, float) or not 0.5 <= config['timeoutSeconds'] <= 10):
            raise ModelingError('invalid_update_config', 'Invalid repository, channel, interval or timeout.')
        return config

    def _path(self, config):
        key = hashlib.sha256((config['repository'].lower() + ':' + config['channel']).encode()).hexdigest()[:24]
        return self.home / 'updates' / ('cache-' + key + '.json')

    def _cache(self, config):
        try:
            cache = _json(self._path(config))
            if not isinstance(cache, dict) or cache.get('schemaVersion') != SCHEMA or cache.get('repository', '').lower() != config['repository'].lower() or cache.get('channel') != config['channel']:
                return {}
            for field in ('checkedAt', 'nextCheckAt', 'lastSuccessAt'):
                if field in cache and (type(cache[field]) not in (int, float) or not 0 <= cache[field] < 1e12):
                    return {}
            if ('failureCount' in cache and (type(cache['failureCount']) is not int or not 0 <= cache['failureCount'] <= 1000000) or
                    'complete' in cache and type(cache['complete']) is not bool or
                    'pages' in cache and (type(cache['pages']) is not int or not 1 <= cache['pages'] <= MAX_PAGES) or
                    'etag' in cache and cache['etag'] is not None and (not isinstance(cache['etag'], str) or len(cache['etag']) > 512 or any(ord(c) < 32 for c in cache['etag']))):
                return {}
            # Revalidate every cached release; never trust cached remote prose.
            candidate = cache.get('release')
            if candidate is not None:
                raw = {'tag_name': candidate.get('version'), 'html_url': candidate.get('url'), 'draft': False,
                       'prerelease': candidate.get('prerelease'), 'assets': [
                           {'name': a.get('name'), 'browser_download_url': a.get('url'), 'digest': 'sha256:' + a['sha256'] if a.get('sha256') else None} for a in candidate.get('assets', [])]}
                cache['release'] = _release(raw, config['repository'])
                if cache['release'] is None:
                    return {}
            return cache
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return {}

    def _components(self, live=False, observed=None):
        sdk = {'version': RELEASE['sdkVersion'], 'productVersion': RELEASE['productVersion'],
               'path': str(Path(__file__).resolve().parent), 'source': 'installed_sdk_release_resource'}
        installed = {'status': 'unavailable', 'version': None, 'path': None, 'source': 'no_installation_receipt'}
        installation = None
        try:
            installation = _json(self.home / 'installation.json', 32768)
            if isinstance(installation, dict) and installation.get('schemaVersion') == 'sp2model.installation/1':
                path = Path(installation['pluginPath'])
                installed.update(path=str(path), source='installation_receipt_and_current_file_sha256')
                actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
                if actual and actual == installation.get('pluginSha256') and version_key(installation.get('pluginVersion')):
                    installed.update(status='verified', version=installation['pluginVersion'], sha256=actual)
                else:
                    installed.update(status='file_changed_or_missing', sha256=actual)
        except (OSError, ValueError, KeyError, TypeError):
            installation = None
        loaded = {'status': 'unavailable', 'version': None, 'source': 'not_queried'}
        if live:
            if self.runtime is None or (getattr(self.runtime, '_client', None) is None and getattr(self.runtime, '_selector', None) is None):
                raise ModelingError('instance_required', 'Use Runtime(instance=...).updates.status(live=True).')
            caps = self.runtime.client.call('capabilities')
            loaded = {'status': 'observed', 'version': caps.get('pluginVersion'),
                      'source': 'explicit_capabilities_read', 'instance': self.runtime.client.instance}
        elif observed is not None:
            try:
                identity = observed.instance
                loaded = {'status': 'observed', 'version': identity.get('pluginVersion'),
                          'source': 'existing_authenticated_client_descriptor',
                          'instance': {k: identity.get(k) for k in ('instanceId', 'pid')}}
            except (AttributeError, TypeError):
                pass
        expected = version_key(RELEASE['pluginVersion'])
        ikey, lkey = version_key(installed['version']), version_key(loaded['version'])
        if ikey is None:
            action = 'installed_version_unknown'
        elif ikey != expected:
            action = 'component_mismatch'
        elif lkey is None:
            action = 'loaded_version_unknown'
        elif lkey < ikey:
            action = 'restart_required'
        elif lkey != ikey:
            action = 'component_mismatch'
        else:
            action = 'matched'
        return {'sdk': sdk, 'installedPlugin': installed, 'loadedPlugin': loaded,
                'action': action, 'installRoot': str(self.home),
                'backupPath': installation.get('backupPath') if isinstance(installation, dict) else None,
                'meaning': 'SDK alpha suffix is not a plugin mismatch. A file receipt is not loaded-module evidence.'}

    def status(self, *, channel=None, live=False, observed=None):
        config = self._config(channel)
        cache = self._cache(config)
        now = self.clock()
        candidate = cache.get('release')
        newer = bool(candidate and version_key(candidate['version']) > version_key(RELEASE['productVersion']))
        fresh = bool(cache.get('status') == 'checked' and now < cache.get('nextCheckAt', 0))
        if newer:
            state = 'update_available' if fresh else 'cached_update_unverified'
        elif fresh and cache.get('unrecognizedVersions'):
            state = 'unrecognized_release_versions'
        elif fresh and cache.get('complete'):
            state = 'up_to_date' if candidate else 'no_published_release'
        elif fresh:
            state = 'incomplete_release_scan'
        else:
            state = cache.get('status', 'not_checked')
        return {'schemaVersion': SCHEMA, 'state': state, 'repository': config['repository'], 'channel': config['channel'],
                'currentProductVersion': RELEASE['productVersion'], 'target': deepcopy(candidate),
                'checkedAt': _stamp(cache['checkedAt']) if 'checkedAt' in cache else None,
                'lastSuccessAt': _stamp(cache['lastSuccessAt']) if 'lastSuccessAt' in cache else None,
                'nextCheckAt': _stamp(cache['nextCheckAt']) if 'nextCheckAt' in cache else None,
                'fresh': fresh, 'stale': bool(cache and not fresh), 'complete': cache.get('complete', False),
                'errorCode': cache.get('errorCode'), 'automatic': config['automatic'],
                'components': self._components(live, observed), 'networkRequested': False, 'nativeReadRequested': bool(live),
                'limitation': 'Public metadata only. 404 does not distinguish private, missing repository or unavailable release. No software installed.'}

    def check(self, *, channel=None, force=False, live=False):
        config = self._config(channel)
        old = self._cache(config)
        now = self.clock()
        # Force bypasses a successful TTL; never bypass a server/error backoff.
        if now < old.get('nextCheckAt', 0) and (not force or old.get('status') != 'checked'):
            return self.status(channel=channel, live=live)
        path = self._path(config)
        lock = path.with_suffix('.lock')
        token = _lease(lock, now)
        if token is None:
            result = self.status(channel=channel, live=live)
            result['checkInProgress'] = True
            return result
        attempts = 0
        cache = {**old, 'schemaVersion': SCHEMA, 'repository': config['repository'], 'channel': config['channel'],
                 'checkedAt': now, 'status': 'check_failed', 'nextCheckAt': now + 60, 'errorCode': None}
        try:
            headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'SP2BuildAssistant/' + RELEASE['productVersion'],
                       'X-GitHub-Api-Version': '2022-11-28'}
            if old.get('complete') and old.get('pages') == 1 and isinstance(old.get('etag'), str):
                headers['If-None-Match'] = old['etag']
            url = 'https://api.github.com/repos/' + config['repository'] + '/releases?per_page=100'
            deadline = time.monotonic() + config['timeoutSeconds']
            candidates, complete, etag, unrecognized = [], False, None, 0
            for page in range(1, MAX_PAGES + 1):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                attempts += 1
                status, response_headers, raw = self.request(url, headers, remaining)
                if status == 304 and page == 1 and old.get('complete') and old.get('pages') == 1:
                    cache.update(status='checked', nextCheckAt=now + config['intervalSeconds'], lastSuccessAt=now,
                                 errorCode=None)
                    break
                if status != 200:
                    code = {404: 'release_source_unavailable', 403: 'access_denied_or_rate_limited', 429: 'rate_limited'}.get(status, 'http_' + str(status))
                    delay = 43200 if status == 404 else min(21600, 60 * 2 ** min(old.get('failureCount', 0), 8))
                    if status in (403, 429):
                        retry = response_headers.get('retry-after')
                        try:
                            delay = max(delay, float(retry))
                        except (TypeError, ValueError):
                            try:
                                delay = max(delay, parsedate_to_datetime(retry).timestamp() - now)
                            except (TypeError, ValueError, OverflowError):
                                pass
                        try:
                            if response_headers.get('x-ratelimit-remaining') == '0':
                                delay = max(delay, float(response_headers['x-ratelimit-reset']) - now)
                        except (ValueError, KeyError):
                            pass
                    cache.update(errorCode=code, nextCheckAt=now + min(604800, max(60, delay)),
                                 failureCount=old.get('failureCount', 0) + 1)
                    break
                if len(raw) > MAX_BYTES:
                    raise ValueError('Response too large')
                rows = json.loads(raw.decode('utf-8'))
                if not isinstance(rows, list) or len(rows) > 100:
                    raise ValueError('Malformed release list')
                for row in rows:
                    candidate = _release(row, config['repository'])
                    if not row.get('draft') and (config['channel'] == 'prerelease' or not row.get('prerelease')) and version_key(row.get('tag_name')) is None:
                        unrecognized += 1
                    if candidate and (config['channel'] == 'prerelease' or not candidate['prerelease']):
                        candidates.append(candidate)
                if page == 1:
                    etag = response_headers.get('etag')
                next_link = re.search(r'<([^>]+)>;\s*rel="next"', response_headers.get('link', ''))
                if next_link:
                    next_url = next_link.group(1)
                    parsed = urlsplit(next_url)
                    if parsed.scheme != 'https' or parsed.netloc != 'api.github.com' or parsed.path.lower() != ('/repos/' + config['repository'] + '/releases').lower() or parsed.fragment:
                        raise ValueError('Unsafe pagination link')
                    url = next_url
                    headers.pop('If-None-Match', None)
                else:
                    complete = True
                if complete or page == MAX_PAGES:
                    cache.update(status='checked', release=max(candidates, key=lambda r: version_key(r['version'])) if candidates else None,
                                 complete=complete, pages=page, etag=etag, lastSuccessAt=now, failureCount=0,
                                 unrecognizedVersions=unrecognized,
                                 nextCheckAt=now + config['intervalSeconds'])
                    break
            _save(path, cache)
        except (OSError, ValueError, TypeError, KeyError) as error:
            cache.update(errorCode='network_timeout' if isinstance(error, TimeoutError) else 'network_or_response_error',
                         failureCount=old.get('failureCount', 0) + 1,
                         nextCheckAt=now + min(21600, 60 * 2 ** min(old.get('failureCount', 0), 8)))
            _save(path, cache)
        finally:
            _release_lease(lock, token)
        result = self.status(channel=channel, live=live)
        result.update(networkRequested=bool(attempts), httpRequests=attempts)
        return result

    def schedule(self):
        """Installed use only. Fast local scheduling; never wait on the child."""
        config = self._config()
        if not config['automatic'] or not (self.home / 'installation.json').is_file():
            return False
        now = self.clock()
        if now < self._cache(config).get('nextCheckAt', 0):
            return False
        worker_lock = self._path(config).with_suffix('.worker')
        token = _lease(worker_lock, now, 90)
        if token is None:
            return False
        options = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL,
                   'close_fds': True, 'cwd': str(Path(__file__).parent)}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options['start_new_session'] = True
        try:
            subprocess.Popen([sys.executable, '-I', '-X', 'utf8', '-m', 'sp2model.update_worker',
                              '--home', str(self.home), '--lease', token], **options)
            return True
        except OSError:
            _release_lease(worker_lock, token)
            return False

    def guide(self, *, channel=None, live=False):
        status = self.status(channel=channel, live=live)
        parts = status['components']
        installed = parts['installedPlugin']
        exact = installed['status'] == 'verified'
        target = status['target']
        assets = target['assets'] if target else []
        packages = [a for a in assets if a['name'].endswith('.zip') and a['name'].startswith('agent-sdk-')]
        return {'schemaVersion': SCHEMA, 'status': status, 'installRoot': str(self.home),
                'pluginPath': installed['path'] if exact else None, 'exactInstallVerified': exact,
                'releaseUrl': target['url'] if target else 'https://github.com/' + status['repository'] + '/releases',
                'packageCandidates': packages, 'packageSelected': packages[0] if len(packages) == 1 else None,
                'steps': [
                    '先将上述当前/目标版本及检查时间告知玩家；询问是否需要更新。更新提示不授权安装。',
                    '取得官方Release完整agent-sdk发布包；保留制品及SHA256，按Release适用游戏版本和安装说明核对。多个候选包或无哈希时不得猜选或声称已校验。',
                    '等待玩家及其他Agent完成工作并保存craft，正常退出目标游戏后再更新；DLL不能热替换生效。',
                    '记录本次installRoot和pluginPath，备份现有DLL、工具入口、skill及安装回执；保留用户数据、项目和存档。安装位置未知时先核实，不猜Steam路径。',
                    '使用该目标版本完整包中附带的安装器和说明更新对应安装。游戏本地工具与旧全局工具分开，不因为更新游戏本地安装就替换全局命令/PATH。',
                    '正常启动目标游戏，显式选择新instance，运行sp2model doctor --live --instance ID以及sp2model updates status --live --instance ID，核对实际加载DLL与SDK；复制文件不等于已加载。',
                    '如果需要回退，先保存并退出目标游戏，按本次备份恢复成套DLL/SDK入口/skill/回执，再启动核验；不删除玩家数据。'],
                'backupPath': parts['backupPath'], 'automaticInstall': False, 'networkRequested': False}

    def call(self, command, arguments=None):
        from . import registry
        args = deepcopy(arguments or {})
        registry.validate(args, registry.schema(command))
        return getattr(self, command.split('.')[1])(**args)


def decorate(envelope, client=None):
    """Fail-open notification decoration: cannot turn an accepted edit into retry."""
    try:
        service = Updates()
        if client is not None:
            service.schedule()
        status = service.status(observed=client)
        target = status.get('target')
        notice = None
        if status['state'] in ('update_available', 'cached_update_unverified'):
            notice = {'code': 'tool_update_available', 'currentVersion': RELEASE['productVersion'],
                      'targetVersion': target['version'], 'releaseUrl': target['url'],
                      'fresh': status['fresh'], 'checkedAt': status['checkedAt'],
                      'message': '请告知玩家工具有更新版本。' + ('本次查询未核实，以下是上次成功缓存。' if not status['fresh'] else '')}
        elif status['components']['action'] == 'restart_required':
            notice = {'code': 'tool_restart_required', 'message': '新版文件已安装，但所选游戏仍加载旧版。请先告知玩家，等待保存及退出后再正常重启；不要中断正在建造的Agent。'}
        elif status['components']['action'] == 'component_mismatch':
            notice = {'code': 'tool_components_mismatch', 'message': '当前SDK、已安装插件或所选运行插件版本不一致，请告知玩家并先核对安装；不要自动替换或重启。'}
        if notice:
            notice.update(guideCommand='sp2model updates guide', statusCommand='sp2model updates status',
                          source='local_fixed_update_policy', delivery='emitted_not_player_acknowledgement',
                          automaticInstall=False)
            envelope['notices'] = [notice]
    except Exception:
        # No exception, remote data or notification failure replaces operation evidence.
        pass
    return envelope


def input_schema(command):
    props = {'channel': {'type': 'string', 'enum': ['stable', 'prerelease']}, 'live': {'type': 'boolean'}}
    if command == 'updates.check':
        props['force'] = {'type': 'boolean'}
    return {'type': 'object', 'properties': props, 'additionalProperties': False,
            'description': 'status/guide are local-only unless live=true explicitly reads capabilities. check GETs public GitHub release metadata, never installs.'}


COMMANDS = {name: {'execution': 'local', 'mutates': False, 'inputSchema': input_schema(name),
                   'outputSchema': {'type': 'object', 'properties': {'data': {'type': 'object'}}}}
            for name in ('updates.check', 'updates.status', 'updates.guide')}
