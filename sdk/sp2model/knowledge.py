"""Bounded, provenance-aware read-only knowledge services.

Only ``refresh`` accesses a bridge. No command writes a cache, examines a save,
creates a template, evaluates an expression, or changes editing permissions.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from .errors import ModelingError
from .transport import canonical_json


BUNDLE_SCHEMA = 'sp2model.knowledge.bundle/1'
DOCUMENT_SCHEMA = 'sp2model.knowledge/1'
MAX_RESPONSE_BYTES = 512 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
PART_COLLECTIONS = ('templates', 'parts', 'fields', 'sourceFields', 'enums', 'choices', 'boundaries', 'sources')
FUNKY_COLLECTIONS = ('functions', 'constants', 'variables', 'rules', 'inputs', 'outputs', 'examples', 'mfd', 'unknowns')
LIVE_COLLECTIONS = ('liveTemplates', 'liveFunctions')
COLLECTIONS = PART_COLLECTIONS + FUNKY_COLLECTIONS + LIVE_COLLECTIONS
SOURCE_KEYS = ('gameVersion', 'steamBuildId', 'xmlVersion', 'gameAssemblySha256', 'sourceInventorySha256')
_FILE_COLLECTIONS = {'parts.json': PART_COLLECTIONS, 'funky.json': FUNKY_COLLECTIONS}


def _digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def bundle_id(files):
    """Deterministic content identity shared by the publisher and reader."""
    return _digest({'schemaVersion': BUNDLE_SCHEMA, 'files': sorted(files, key=lambda row: row['name'])})


def _object(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False}


_COLLECTION = {'type': 'string', 'enum': list(COLLECTIONS)}
_CURSOR = {'type': 'string', 'minLength': 1, 'maxLength': 2048, 'pattern': r'^[A-Za-z0-9_-]+$'}
_FILTERS = {'query': {'type': 'string', 'maxLength': 256},
            'partType': {'type': 'string', 'minLength': 1, 'maxLength': 256},
            'role': {'type': 'string', 'minLength': 1, 'maxLength': 128}}
_PAGE = {'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'cursor': _CURSOR}
_REFRESH = {'type': 'boolean', 'const': True, 'description': 'Explicitly refresh the native in-memory directory before this query. Only liveTemplates/liveFunctions.'}
_INPUTS = {
    'knowledge.status': _object(),
    'knowledge.search': _object({'collection': _COLLECTION, **_FILTERS, **_PAGE, 'refresh': _REFRESH}, ['collection']),
    'knowledge.get': _object({'collection': _COLLECTION, 'id': {'type': 'string', 'minLength': 1, 'maxLength': 2048}, 'cursor': _CURSOR, 'refresh': _REFRESH}, ['collection', 'id']),
    'knowledge.export': _object({'collection': _COLLECTION, **_FILTERS, **_PAGE, 'refresh': _REFRESH}, ['collection']),
    'knowledge.refresh': _object(),
}
for _name in ('knowledge.search', 'knowledge.get', 'knowledge.export'):
    _INPUTS[_name]['allOf'] = [{'if': {'required': ['refresh']}, 'then': {'properties': {'collection': {'enum': list(LIVE_COLLECTIONS)}}}}]
_RESULT = {'type': 'object', 'required': ['dataSource', 'datasetId', 'version', 'coverage', 'gaps', 'compatibility'],
           'properties': {key: {} for key in ['dataSource', 'datasetId', 'version', 'coverage', 'gaps', 'compatibility']}}
COMMANDS = {name: {'inputSchema': deepcopy(spec), 'execution': 'local_with_live' if name.endswith('.refresh') else 'local',
                   'mutates': False, 'operationKind': None,
                   'outputSchema': {'type': 'object', 'properties': {'success': {'type': 'boolean'}, 'schemaVersion': {'type': 'string'}, 'data': deepcopy(_RESULT)}, 'required': ['success', 'schemaVersion']},
                   'description': 'Explicit read-only live directory refresh; memory only.' if name.endswith('.refresh') else 'Versioned offline knowledge; no instance discovery.'}
            for name, spec in _INPUTS.items()}


def input_schema(command):
    if command not in _INPUTS:
        raise ModelingError('unsupported_command', command)
    return deepcopy(_INPUTS[command])


def _error(code, message, **details):
    raise ModelingError(code, message, details)


def _json(raw, label):
    def pairs(rows):
        obj = {}
        for key, value in rows:
            if key in obj:
                raise ValueError('Duplicate JSON key: ' + key)
            obj[key] = value
        return obj
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
    except (ValueError, UnicodeError, RecursionError) as error:
        _error('knowledge_invalid', 'Invalid knowledge JSON.', file=label, reason=str(error))


class Knowledge:
    def __init__(self, runtime=None, *, resource_dir=None):
        self._runtime = runtime
        self._root = Path(resource_dir) if resource_dir is not None else Path(__file__).resolve().parent / 'resources' / 'knowledge' / 'v077'
        self._loaded = False
        self._collections = {}
        self._overlay = None
        self._refresh_status = {'status': 'not_attempted'}
        self._compatibility = {'status': 'offline_unverified', 'runtimeCertified': False,
                               'reason': 'Offline source version only. Call knowledge.refresh explicitly to compare a live directory.'}

    def _load(self):
        if self._loaded:
            return
        manifest_path = self._root / 'manifest.json'
        if not manifest_path.is_file():
            _error('knowledge_unavailable', 'The versioned knowledge bundle is missing.', missing='manifest.json')
        try:
            if manifest_path.is_symlink():
                _error('knowledge_invalid', 'Knowledge manifest must be a regular bundle file.')
            if manifest_path.stat().st_size > 65536:
                _error('knowledge_invalid', 'Knowledge manifest exceeds its size bound.')
            manifest = _json(manifest_path.read_bytes(), 'manifest.json')
            if not isinstance(manifest, dict) or manifest.get('schemaVersion') != BUNDLE_SCHEMA:
                _error('knowledge_invalid', 'Unsupported knowledge manifest schema.')
            files = manifest.get('files')
            if not isinstance(files, list) or len(files) != 2:
                _error('knowledge_invalid', 'Manifest must identify exactly the two knowledge documents.')
            names = set()
            for item in files:
                if not isinstance(item, dict) or set(item) != {'name', 'bytes', 'sha256'}:
                    _error('knowledge_invalid', 'Invalid manifest file descriptor.')
                if item['name'] not in _FILE_COLLECTIONS or item['name'] in names:
                    _error('knowledge_invalid', 'Manifest file name is not a unique permitted resource.')
                names.add(item['name'])
                if type(item['bytes']) is not int or not 0 < item['bytes'] <= MAX_FILE_BYTES or not isinstance(item['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
                    _error('knowledge_invalid', 'Invalid manifest byte count or digest.')
            if manifest.get('datasetId') != bundle_id(files):
                _error('knowledge_integrity', 'Manifest datasetId does not match its file descriptors.')
            collections, coverage, gaps, provenance, source = {}, {}, [], {}, None
            for item in files:
                path = self._root / item['name']
                if path.resolve().parent != self._root.resolve() or path.is_symlink():
                    _error('knowledge_invalid', 'Knowledge resources must be regular bundle files.')
                if not path.is_file():
                    _error('knowledge_unavailable', 'A knowledge document is missing.', missing=item['name'])
                if path.stat().st_size != item['bytes']:
                    _error('knowledge_integrity', 'Knowledge document size does not match manifest.', file=item['name'])
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != item['sha256']:
                    _error('knowledge_integrity', 'Knowledge document hash does not match manifest.', file=item['name'])
                document = _json(raw, item['name'])
                if not isinstance(document, dict) or document.get('schemaVersion') != DOCUMENT_SCHEMA:
                    _error('knowledge_invalid', 'Unsupported knowledge document schema.', file=item['name'])
                current = document.get('source')
                if not isinstance(current, dict) or any(key not in current for key in SOURCE_KEYS):
                    _error('knowledge_invalid', 'Knowledge source provenance is incomplete.', file=item['name'])
                if not isinstance(current['gameVersion'], str) or not current['gameVersion'] or type(current['xmlVersion']) is not int or current['xmlVersion'] < 1 or not isinstance(current['steamBuildId'], str) or not current['steamBuildId'].isdigit():
                    _error('knowledge_invalid', 'Knowledge source versions are invalid.', file=item['name'])
                if any(not isinstance(current[key], str) or not re.fullmatch(r'[0-9a-f]{64}', current[key]) for key in SOURCE_KEYS[-2:]):
                    _error('knowledge_invalid', 'Knowledge source hashes are invalid.', file=item['name'])
                provenance[item['name']] = deepcopy(current)
                if 'officialHelpComparison' in document:
                    provenance[item['name']]['officialHelpComparison'] = deepcopy(document['officialHelpComparison'])
                current = {key: current[key] for key in SOURCE_KEYS}
                if source is not None and source != current:
                    _error('knowledge_integrity', 'Knowledge documents refer to different source baselines.')
                source = current
                values = document.get('collections')
                if not isinstance(values, dict) or set(values) != set(_FILE_COLLECTIONS[item['name']]):
                    _error('knowledge_invalid', 'Document collections are incomplete or unsupported.', file=item['name'])
                for name, rows in values.items():
                    if not isinstance(rows, list):
                        _error('knowledge_invalid', 'Collection must contain a record list.', collection=name)
                    seen = set()
                    for row in rows:
                        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key] for key in ('id', 'title', 'summary')) or len(row['id']) > 2048 or row['id'] in seen:
                            _error('knowledge_invalid', 'Record identifiers must be unique and records must have text titles and summaries.', collection=name)
                        seen.add(row['id'])
                    collections[name] = sorted(rows, key=lambda row: row['id'])
                if not isinstance(document.get('coverage'), dict) or not isinstance(document.get('limitations'), list):
                    _error('knowledge_invalid', 'Document coverage and limitations are required.', file=item['name'])
                coverage[item['name'].removesuffix('.json')] = document['coverage']
                gaps.append({'document': item['name'], 'limitations': document['limitations']})
            for key in SOURCE_KEYS:
                if key in manifest and manifest[key] != source[key]:
                    _error('knowledge_integrity', 'Manifest source version differs from its documents.', field=key)
            self._collections, self._coverage, self._gaps, self._source = collections, coverage, gaps, source
            self._provenance = provenance
            self._dataset = manifest['datasetId']
            self._loaded = True
        except OSError as error:
            _error('knowledge_unavailable', 'Knowledge bundle could not be read.', reason=str(error))

    def _metadata(self, *, full_coverage=False):
        from . import __version__
        def compact(value):
            if isinstance(value, list) and len(value) > 25:
                return {'count': len(value), 'detailsCommand': 'knowledge.status'}
            if isinstance(value, dict):
                return {key: compact(child) for key, child in value.items()}
            return deepcopy(value)
        return {'dataSource': 'versioned_offline_knowledge', 'datasetId': self._dataset,
                'version': {**self._source, 'toolVersion': __version__},
                'coverage': deepcopy(self._coverage) if full_coverage else compact(self._coverage), 'gaps': deepcopy(self._gaps),
                'compatibility': deepcopy(self._compatibility)}

    def _bounded(self, result):
        if len(canonical_json(result)) > MAX_RESPONSE_BYTES:
            _error('knowledge_response_too_large', 'Knowledge metadata exceeds the response budget.', maxResponseBytes=MAX_RESPONSE_BYTES)
        return result

    def status(self):
        return self.call('knowledge.status')

    def search(self, collection, **arguments):
        return self.call('knowledge.search', {'collection': collection, **arguments})

    def get(self, collection, id, **arguments):
        return self.call('knowledge.get', {'collection': collection, 'id': id, **arguments})

    def export(self, collection, **arguments):
        return self.call('knowledge.export', {'collection': collection, **arguments})

    def refresh(self):
        return self.call('knowledge.refresh')

    def call(self, command, arguments=None):
        from .registry import validate
        args = deepcopy({} if arguments is None else arguments)
        validate(args, input_schema(command))
        try:
            self._load()
        except ModelingError as error:
            if command != 'knowledge.status':
                raise
            return {'dataSource': 'unavailable', 'datasetId': None, 'version': {}, 'coverage': {},
                    'gaps': [error.to_dict()], 'compatibility': {'status': 'unavailable', 'runtimeCertified': False}, 'available': False}
        if command == 'knowledge.status':
            result = self._metadata(full_coverage=True)
            result.update(available=True, collections={name: len(rows) for name, rows in self._collections.items()},
                          provenance=deepcopy(self._provenance),
                          live={'refreshed': self._overlay is not None, 'memoryOnly': True,
                                'datasetId': self._overlay['datasetId'] if self._overlay else None,
                                'lastRefreshStatus': deepcopy(self._refresh_status)},
                          limits={'maxPageSize': 100, 'maxResponseBytes': MAX_RESPONSE_BYTES, 'oversizedRecordEncoding': 'base64-json-utf8'},
                          sourceKinds=['native_description', 'source_analysis', 'static_inference', 'unknown'],
                          writesAllowed=False, defaultValuesAreCurrentInstanceValues=False)
            if self._overlay:
                result['collections'].update({name: len(self._overlay[name]) for name in LIVE_COLLECTIONS})
            return self._bounded(result)
        if command == 'knowledge.refresh':
            try:
                result = self._refresh()
            except ModelingError as error:
                self._refresh_status = {'status': 'failed', 'errorCode': error.code,
                                        'previousOverlayRetained': self._overlay is not None}
                self._compatibility = {**self._compatibility, 'status': 'stale_after_refresh_failure' if self._overlay else 'unavailable',
                                       'runtimeCertified': False, 'lastRefreshStatus': deepcopy(self._refresh_status)}
                raise
            self._refresh_status = {'status': 'succeeded', 'datasetId': self._overlay['datasetId']}
            result['lastRefreshStatus'] = deepcopy(self._refresh_status)
            return self._bounded(result)
        collection = args['collection']
        if args.get('refresh'):
            self.call('knowledge.refresh')
        result = self._metadata()
        if collection in LIVE_COLLECTIONS:
            if self._overlay is None:
                _error('knowledge_live_unavailable', 'Call knowledge.refresh explicitly before querying live collections.')
            rows = self._overlay[collection]
            result.update(dataSource='live_native', datasetId=self._overlay['datasetId'], baseDatasetId=self._dataset)
        else:
            rows = self._collections[collection]
        result['collection'] = collection
        if command == 'knowledge.get':
            rows = [row for row in rows if row['id'] == args['id']]
            if not rows:
                _error('knowledge_not_found', 'No record has this stable identifier.', collection=collection, id=args['id'])
        else:
            rows = self._filter(rows, args)
        return self._page(command, args, rows, result)

    def _filter(self, rows, args):
        part = args.get('partType')
        if part is not None:
            target = next((p for p in self._collections['parts'] if p['id'] == part), {})
            def matches(row):
                if row.get('partType') == part or part in row.get('partTypes', []):
                    return True
                return any(row['id'] in target.get(key, []) for key in ('fieldIds', 'sourceFieldIds', 'enumIds', 'templateIds'))
            rows = [row for row in rows if matches(row)]
        if args.get('role') is not None:
            role = args['role'].casefold()
            def roles(row):
                values = []
                for key in ('role', 'kind', 'fieldRole', 'classification', 'roles'):
                    value = row.get(key, [])
                    values.extend(value if isinstance(value, list) else [value])
                return [str(value).casefold() for value in values]
            rows = [row for row in rows if role in roles(row)]
        if args.get('query'):
            terms = args['query'].casefold().split()
            rows = [row for row in rows if all(term in json.dumps(row, ensure_ascii=False, sort_keys=True).casefold() for term in terms)]
        return rows

    @staticmethod
    def _cursor(view, query, offset, chunk):
        payload = {'v': 1, 'datasetId': view, 'query': query, 'offset': offset, 'chunk': chunk}
        payload['checksum'] = _digest(payload)
        return base64.urlsafe_b64encode(canonical_json(payload)).decode('ascii').rstrip('=')

    @staticmethod
    def _read_cursor(cursor, view, query):
        try:
            payload = _json(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True), 'cursor')
            if not isinstance(payload, dict) or set(payload) != {'v', 'datasetId', 'query', 'offset', 'chunk', 'checksum'}:
                raise ValueError('Malformed cursor')
            checksum = payload.pop('checksum')
            if checksum != _digest(payload) or payload['v'] != 1:
                raise ValueError('Cursor integrity check failed')
            if payload['datasetId'] != view or payload['query'] != query:
                _error('knowledge_cursor_mismatch', 'Cursor belongs to a different dataset, query, command or page size.')
            if any(type(payload[key]) is not int or payload[key] < 0 for key in ('offset', 'chunk')):
                raise ValueError('Invalid cursor position')
            return payload['offset'], payload['chunk']
        except (ValueError, UnicodeError, KeyError, TypeError) as error:
            _error('invalid_input', 'Invalid knowledge cursor.', reason=str(error))
        except ModelingError as error:
            if error.code == 'knowledge_invalid':
                _error('invalid_input', 'Invalid knowledge cursor.', reason=error.message)
            raise

    def _page(self, command, args, rows, result):
        query = _digest({'command': command, 'collection': args['collection'], 'id': args.get('id'),
                         'query': args.get('query', ''), 'partType': args.get('partType'), 'role': args.get('role'), 'limit': args.get('limit', 25)})
        offset, chunk = args.get('offset', 0), 0
        if args.get('cursor'):
            restored, chunk = self._read_cursor(args['cursor'], result['datasetId'], query)
            if 'offset' in args and offset != restored:
                _error('invalid_input', 'Offset conflicts with the continuation cursor.')
            offset = restored
        if offset > len(rows) or chunk and offset == len(rows):
            _error('invalid_input', 'Page position is outside the collection.')
        limit = 1 if command == 'knowledge.get' else args.get('limit', 25)
        result.update(total=len(rows), offset=offset, limit=limit, returned=0, truncated=False, nextOffset=None, nextCursor=None, records=[])
        # Reserve enough room for a continuation token and fragment metadata.
        budget = MAX_RESPONSE_BYTES - len(canonical_json(result)) - 4096
        if budget < 8192:
            _error('knowledge_response_too_large', 'Knowledge metadata leaves no room for records.', maxResponseBytes=MAX_RESPONSE_BYTES)
        used, next_offset, next_chunk = 0, offset, 0
        for row in rows[offset:offset + limit]:
            value = {key: deepcopy(row[key]) for key in ('id', 'title', 'summary', 'partType', 'partTypes', 'role', 'kind', 'fieldRole', 'classification', 'source') if key in row} if command == 'knowledge.search' else deepcopy(row)
            encoded = canonical_json(value)
            if len(encoded) > budget:
                if result['records']:
                    break
                if chunk >= len(encoded):
                    _error('invalid_input', 'Record chunk offset is outside the serialized record.')
                count = min(len(encoded) - chunk, budget * 3 // 4 - 1024)
                fragment = encoded[chunk:chunk + count]
                result['recordChunk'] = {'id': row['id'], 'encoding': 'base64-json-utf8', 'offset': chunk, 'bytes': len(fragment),
                                         'totalBytes': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest(),
                                         'content': base64.b64encode(fragment).decode('ascii')}
                next_chunk = chunk + count
                if next_chunk == len(encoded):
                    next_offset += 1
                    next_chunk = 0
                    result['returned'] = 1
                break
            if chunk:
                _error('invalid_input', 'Chunk cursor cannot address an unfragmented record.')
            if used + len(encoded) > budget:
                break
            result['records'].append(value)
            result['returned'] += 1
            used += len(encoded) + 1
            next_offset += 1
        if next_offset < len(rows):
            result.update(truncated=True, nextOffset=next_offset, nextCursor=self._cursor(result['datasetId'], query, next_offset, next_chunk))
        if command == 'knowledge.get':
            result['record'] = result['records'][0] if result['records'] else None
            del result['records']
        result['contentHash'] = _digest(rows) if command == 'knowledge.export' else None
        return self._bounded(result)

    def _refresh(self):
        if self._runtime is None:
            _error('knowledge_live_unavailable', 'A Runtime is required for explicit live refresh.')
        client = self._runtime.client
        capabilities = client.call('capabilities', {})
        catalog = client.call('catalog.export', {})
        funky = client.call('funky.list', {})
        if not isinstance(capabilities, dict) or not isinstance(catalog, dict) or not isinstance(funky, dict) or not isinstance(catalog.get('entries'), list) or not isinstance(catalog.get('schemas', []), list) or not isinstance(funky.get('entries'), list):
            _error('knowledge_live_invalid', 'Live directory responses have an unsupported shape.')
        if funky.get('evaluated') is True:
            _error('knowledge_live_invalid', 'Knowledge refresh requires an unevaluated FT directory.')
        mismatches, unchecked, live_versions = [], [], {}
        for name, response in (('capabilities', capabilities), ('catalog', catalog), ('funky', funky)):
            live_versions[name] = {key: response[key] for key in SOURCE_KEYS if key in response and type(response[key]) in (str, int)}
            for key, expected in self._source.items():
                if key not in live_versions[name]:
                    unchecked.append(name + '.' + key)
                elif str(live_versions[name][key]) != str(expected):
                    mismatches.append({'source': name, 'field': key, 'expected': expected, 'actual': live_versions[name][key]})
        templates, functions = [], []
        schemas = {row['id']: row for row in catalog.get('schemas', []) if isinstance(row, dict) and isinstance(row.get('id'), str)}
        for entry in catalog['entries']:
            if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or not 1 <= len(entry['id']) <= 2048 or not isinstance(entry.get('partTypes'), list) or any(not isinstance(value, str) for value in entry['partTypes']):
                _error('knowledge_live_invalid', 'Live catalog entries lack stable identifiers or member types.')
            types = sorted(set(entry['partTypes']))
            counts, composition_gap = {}, None
            schema = schemas.get(entry['id'])
            members = schema.get('parts') if schema else None
            if schema is None:
                composition_gap = 'Native catalog export did not include this template schema.'
            elif 'error' in schema:
                composition_gap = 'Native template schema export failed; member counts are unavailable.'
            elif not isinstance(members, list) or any(not isinstance(member, dict) or not isinstance(member.get('partType'), str) or not member['partType'] for member in members):
                composition_gap = 'Native template member records are missing or invalid.'
            else:
                for member in members:
                    counts[member['partType']] = counts.get(member['partType'], 0) + 1
                if sorted(counts) != types:
                    composition_gap = 'Native template members disagree with the catalog-declared part types.'
            if composition_gap:
                counts = None
            description = entry.get('description') if isinstance(entry.get('description'), str) else ''
            title = entry.get('name') if isinstance(entry.get('name'), str) else entry['id']
            templates.append({'id': entry['id'], 'title': title, 'summary': description or 'Live native template; member types: ' + ', '.join(types),
                              'nativeDescription': description, 'introduction': {'kind': 'member_composition', 'partTypes': types, 'componentCounts': counts,
                              'description': 'Catalog-declared types only; native member composition is unavailable.' if composition_gap else 'Member composition only; per-type knowledge is separate.'},
                              'partTypes': types, 'componentCounts': counts, 'compositionStatus': 'unavailable' if composition_gap else 'complete',
                              'compositionGap': composition_gap, 'category': entry.get('category') if isinstance(entry.get('category'), str) else '', 'subcategory': entry.get('subcategory') if isinstance(entry.get('subcategory'), str) else '',
                              'creatable': entry.get('creatable') is True, 'creatableReason': entry.get('reason') if isinstance(entry.get('reason'), str) else None,
                              'source': 'live_native', 'nativeSource': entry.get('source') if isinstance(entry.get('source'), str) else 'unknown',
                              'descriptionStatus': 'native' if description else 'unavailable', 'toolWriteStatus': 'not-certified'})
        for entry in funky['entries']:
            if not isinstance(entry, dict) or not isinstance(entry.get('name'), str) or not 1 <= len(entry['name']) <= 2048:
                _error('knowledge_live_invalid', 'Live FT entries lack stable names.')
            # Explicit allowlist: no expression evaluation or instance values.
            row = {key: entry[key] for key in ('kind', 'returns', 'description') if isinstance(entry.get(key), str)}
            parameters = entry.get('parameters', [])
            if not isinstance(parameters, list) or any(not isinstance(item, dict) or not isinstance(item.get('name'), str) or not isinstance(item.get('type'), str) for item in parameters):
                _error('knowledge_live_invalid', 'Live FT parameters have an unsupported shape.')
            row['parameters'] = [{'name': item['name'], 'type': item['type']} for item in parameters]
            if entry.get('kind') == 'constant' and type(entry.get('value')) in (str, int, float, bool):
                row['value'] = entry['value']
            row.update(id=entry['name'], title=entry['name'], summary=row.get('description') or 'Live native registration; detailed semantics may be unavailable.', source='live_native')
            functions.append(row)
        for name, rows in (('liveTemplates', templates), ('liveFunctions', functions)):
            if len({row['id'] for row in rows}) != len(rows):
                _error('knowledge_live_invalid', 'Live directory contains duplicate identifiers.', collection=name)
            rows.sort(key=lambda row: row['id'])
        overlay = {'liveTemplates': templates, 'liveFunctions': functions, 'versions': live_versions}
        overlay['datasetId'] = _digest({'baseDatasetId': self._dataset, **overlay})
        previous = self._overlay['liveTemplates'] if self._overlay else self._collections['templates']
        prior = {row['id']: row for row in previous}
        current = {row['id']: row for row in templates}
        added, removed = sorted(current.keys() - prior.keys()), sorted(prior.keys() - current.keys())
        def member_counts(row):
            value = row.get('componentCounts')
            if isinstance(value, dict):
                return value
            if isinstance(value, list) and all(isinstance(item, dict) and isinstance(item.get('partType'), str) and type(item.get('count')) is int for item in value):
                return {item['partType']: item['count'] for item in value}
            return None
        changed = []
        for key in sorted(current.keys() & prior.keys()):
            before, after = member_counts(prior[key]), member_counts(current[key])
            if sorted(current[key].get('partTypes', [])) != sorted(prior[key].get('partTypes', [])) or before is not None and after is not None and before != after:
                changed.append(key)
        compatibility = {'status': 'stale' if mismatches else 'version_matched' if all('gameVersion' in live_versions[name] for name in live_versions) else 'unverified',
                         'runtimeCertified': False, 'mismatches': mismatches, 'unchecked': unchecked,
                         'reason': 'Read-only directory comparison. No runtime behavior, write support, assembly identity or performance is certified.'}
        result = self._metadata()
        result.update(dataSource='live_native', datasetId=overlay['datasetId'], baseDatasetId=self._dataset, compatibility=compatibility,
                      refreshed=True, memoryOnly=True, nativeCommands=['capabilities', 'catalog.export', 'funky.list'],
                      counts={'liveTemplates': len(templates), 'liveFunctions': len(functions),
                              'compositionUnavailable': sum(row['compositionStatus'] == 'unavailable' for row in templates)},
                      diff={'comparedTo': 'previous_live_refresh' if previous is not self._collections['templates'] else 'offline_bundle',
                            'added': added, 'removed': removed, 'typeMappingsChanged': changed},
                      snapshotValuesRetained=False, evaluated=False)
        self._bounded(result)
        self._compatibility, self._overlay = compatibility, overlay
        return result
