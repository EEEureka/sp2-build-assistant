"""Bounded, lossless building guidance. No harness hooks or model-read claims."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from reference_storage import ReferenceError

ROOT = Path(__file__).resolve().parents[1] / 'skills' / 'sp2-build-assistant'
COMMANDS = {'build.prepare', 'build.guide', 'build.resume'}
LIVE = {'build.resume'}
KINDS = ('query', 'save', 'precision', 'continuous', 'complete', 'seam', 'recovery')
PHASES = ('inspect', 'model', 'split', 'verify', 'recover')
TOPICS = {
    'core': 'SKILL.md', 'contracts': 'operating-contracts.md',
    'precision': 'references/precision-building.md',
    'low-part': 'references/low-part-native-modeling.md',
    'loop': 'references/build-loop.md', 'continuity': 'references/continuity-review.md',
    'navigation': 'references/designer-navigation.md', 'edits': 'references/edits.md',
    'collaboration': 'references/scoped-collaboration.md',
}
FIELDS = {'taskKind': 'string', 'phase': 'string', 'topic': 'string', 'page': 'integer',
          'expectedVersion': 'string', 'journalPath': 'string', 'snapshot': ['object', 'string']}
LIMITATION = 'Tool delivery only: DSH may later prune/summarize this text. No claim of model receipt, retention, understanding or compliance.'
PAGE_CHARS = 2200


def input_schema(command):
    keys = {'build.prepare': ('taskKind', 'phase'),
            'build.guide': ('topic', 'page', 'expectedVersion'),
            'build.resume': ('journalPath', 'taskKind', 'phase', 'snapshot')}[command]
    props = {key: {'type': FIELDS[key]} for key in keys}
    for key, values in [('taskKind', KINDS), ('phase', PHASES), ('topic', tuple(TOPICS))]:
        if key in props: props[key]['enum'] = list(values)
    if 'page' in props: props['page']['minimum'] = 0
    return {'type': 'object', 'properties': props, 'additionalProperties': False,
            'required': ['topic'] if command == 'build.guide' else ['journalPath'] if command == 'build.resume' else [],
            'description': 'Read-only guidance. prepare defaults to complete modeling; guide returns whole Markdown blocks with version-bound pagination; resume reconciles the existing build-loop journal with a current snapshot without edits.'}


def _read(topic):
    if topic not in TOPICS:
        raise ReferenceError('invalid_topic', 'Unknown building topic', available=list(TOPICS))
    path = ROOT / TOPICS[topic]
    try: text = path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as exc:
        raise ReferenceError('guidance_unavailable', 'Required guidance is unavailable', topic=topic, path=str(path)) from exc
    if topic == 'core':
        match = re.search(r'<!-- core:start -->\n(.*?)\n<!-- core:end -->', text, re.S)
        if not match: raise ReferenceError('guidance_invalid', 'Core rule boundaries are missing')
        text = match.group(1)
    return text


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _blocks(text):
    """Keep fences and tables intact; blank-line separated rules are indivisible."""
    blocks, lines, fence = [], [], None
    for line in text.splitlines(keepends=True):
        if fence is None and lines and re.match(r'^(?:[-*] |\d+\. )', line):
            blocks.append(''.join(lines)); lines = []
        stripped = line.lstrip()
        if stripped.startswith(('```', '~~~')):
            marker = stripped[:3]
            fence = None if fence == marker else marker if fence is None else fence
        lines.append(line)
        if not line.strip() and fence is None:
            blocks.append(''.join(lines)); lines = []
    if lines: blocks.append(''.join(lines))
    if fence is not None: raise ReferenceError('guidance_invalid', 'Unclosed Markdown fence')
    return blocks


def _pages(text):
    pages, pending = [], ''
    for block in _blocks(text):
        if len(block) > PAGE_CHARS:
            raise ReferenceError('guidance_budget', 'An indivisible rule exceeds the page budget; restructure its source, never truncate', characters=len(block))
        if pending and len(pending) + len(block) > PAGE_CHARS:
            pages.append(pending); pending = ''
        pending += block
    if pending: pages.append(pending)
    if not pages: raise ReferenceError('guidance_invalid', 'Empty guidance topic')
    return pages


def select(task_kind='complete', phase='model'):
    if task_kind not in KINDS or phase not in PHASES:
        raise ReferenceError('invalid_task_kind', 'Choose a supported task kind and phase', taskKinds=KINDS, phases=PHASES)
    topics = [] if task_kind == 'query' else ['navigation'] if task_kind == 'save' else ['edits', 'collaboration'] if task_kind == 'recovery' else ['precision', 'loop']
    if task_kind in ('complete', 'continuous', 'seam') or phase == 'split':
        topics = list(dict.fromkeys(topics + ['precision', 'low-part', 'loop']))
    if task_kind == 'seam': topics.append('continuity')
    if phase == 'recover': topics = list(dict.fromkeys(topics + ['edits', 'collaboration']))
    if task_kind not in ('query', 'save'): topics.insert(0, 'contracts')
    return topics


def metadata(task_kind='complete', phase='model'):
    topics = ['core'] + select(task_kind, phase)
    versions = {topic: _hash(_read(topic)) for topic in topics}
    return {'taskKind': task_kind, 'phase': phase, 'requiredTopics': topics, 'versions': versions,
            'bundleVersion': _hash(json.dumps(versions, sort_keys=True)), 'meaning': 'Required resources, not a record of model reading or retained context.'}


def prepare(task_kind='complete', phase='model'):
    meta = metadata(task_kind, phase)
    required = []
    for topic in meta['requiredTopics']:
        pages = _pages(_read(topic))
        required.append({'topic': topic, 'version': meta['versions'][topic], 'pageCount': len(pages)})
    return {'coreRules': _read('core'), 'taskKind': task_kind, 'phase': phase,
            'requiredResources': required,
            'nextAction': 'Read ALL pages for each required topic with build guide --topic TOPIC --page N --expected-version VERSION before its decisions; coreRules is already supplied here.',
            'limitation': LIMITATION, 'writesIssued': False}


def guide(topic, page=0, expected_version=None):
    text = _read(topic); version = _hash(text); pages = _pages(text)
    if expected_version and expected_version != version:
        raise ReferenceError('guidance_changed', 'Topic changed; repeat prepare and retrieve the complete current topic', topic=topic, currentVersion=version)
    if type(page) is not int or page < 0 or page >= len(pages):
        raise ReferenceError('invalid_page', 'Page is out of range', pageCount=len(pages))
    return {'text': pages[page], 'topic': topic, 'version': version, 'page': page, 'pageCount': len(pages),
            'nextPage': page + 1 if page + 1 < len(pages) else None,
            'pageHash': _hash(pages[page]), 'source': TOPICS[topic],
            'deliveredPages': [page],
            'completionMeaning': 'This response delivers only the stated page. All pages concatenate to the full normalized source. A missing page leaves the topic incomplete; the last page alone proves neither earlier delivery nor model reading.',
            'limitation': LIMITATION}


def dispatch(command, payload, live=None):
    if command == 'build.guide': return guide(payload['topic'], payload.get('page', 0), payload.get('expectedVersion'))
    if command == 'build.prepare': return prepare(payload.get('taskKind', 'complete'), payload.get('phase', 'model'))
    if command != 'build.resume': raise ReferenceError('unsupported_command', 'Unknown guidance command')
    import build_loop
    from reference_storage import read_json
    from reference_binding import unwrap
    request = {'journalPath': payload['journalPath']}
    if 'snapshot' in payload:
        value = payload['snapshot']
        request['snapshot'] = unwrap(read_json(value) if isinstance(value, str) else value)
        freshness = 'supplied_snapshot_not_live_verified'
    else:
        if not callable(live): raise ReferenceError('live_required', 'Resume needs a current snapshot or an explicitly supplied historical one')
        request['snapshot'] = unwrap(live('craft.snapshot', {'includeXml': True}))
        freshness = 'live_read_only_snapshot'
    result = build_loop.dispatch('status', request)
    previous = result['loop'].get('guidance', {})
    kind = payload.get('taskKind', previous.get('taskKind', 'complete'))
    phase = payload.get('phase', 'recover')
    current = metadata(kind, phase)
    result = {'guidancePreparation': prepare(kind, phase), **result}
    result['ruleChanges'] = {'previous': previous.get('versions', {}), 'current': current['versions'],
                             'changed': previous.get('versions') != current['versions']}
    result['snapshotFreshness'] = freshness
    result['executionStatus'] = execution_status(result['loop'].get('executionJournals', []))
    result['resumeAction'] = ('reconcile_linked_operations_before_dependent_writes'
        if any(row['needsReconciliation'] for row in result['executionStatus']) else 'inspect_next_round_goals')
    result['writesIssued'] = False
    return result


def execution_status(paths):
    """References to the existing execution truth; never replay or copy a ledger."""
    import run_journal
    rows = []
    for path in paths:
        row = {'journalPath': path, 'receiptMeaning': 'historical execution evidence, not current authorization'}
        try:
            state = run_journal.status(path)
            if not state['entryCount']:
                raise ReferenceError('journal_missing', 'Linked execution journal is absent or empty')
            entries = state['entries']
            pending = []
            for prepared in state['pendingWrites']:
                matching = [e for e in entries if e.get('requestId') == prepared['requestId']]
                pending.append({'requestId': prepared['requestId'],
                                'operationId': next((e['operationId'] for e in reversed(matching) if e.get('operationId')), None)})
            receipt = next((e['receipt'] for e in reversed(entries) if e.get('receipt')), None)
            row.update(headHash=state['headHash'], state=state['state'], pendingWrites=pending,
                       lastReceipt=receipt, needsReconciliation=bool(pending))
        except (ReferenceError, OSError, ValueError) as exc:
            row.update(error={'code': getattr(exc, 'code', 'journal_unreadable'), 'message': str(exc)}, needsReconciliation=True)
        rows.append(row)
    return rows


def journal_metadata(payload, previous=None):
    previous = previous or {}
    return metadata(payload.get('taskKind', previous.get('taskKind', 'complete')),
                    payload.get('phase', previous.get('phase', 'model')))


def decorate(command, result):
    """Add short guidance without changing outcome, identity or retry semantics."""
    if command in COMMANDS or command.startswith(('commands.', 'catalog.', 'resources.')): return result
    rules, topic = None, 'core'
    code = result.get('error', {}).get('code', '')
    if code in ('wait_timeout', 'state_uncertain', 'native_settle_timeout', 'session_conflict', 'revision_conflict', 'scope_conflict') or command.startswith(('operation.', 'craft.undo', 'craft.rollback', 'structure.restore')):
        rules = ('C03',); topic = 'edits'
    elif command.startswith(('shape.plan', 'structure.plan', 'structure.replace', 'structure.reshape', 'representation.check')):
        rules = ('C05',); topic = 'low-part'
    elif command in _write_shortcuts() or command.startswith(('batch.apply', 'scoped.batch.apply', 'build.loop.')):
        rules = ('C06',); topic = 'loop'
    elif command in ('version', 'skill.path'):
        rules = ('C04', 'C07')
    if rules is None: return result
    try:
        core = _read('core')
        blocks = {block.split('.', 1)[0]: block.strip() for block in _blocks(core) if block.startswith('C')}
        text = '\n\n'.join(blocks[rule] for rule in rules)
        hint = {'text': text, 'topic': topic, 'source': TOPICS['core'], 'sourceRuleIds': list(rules),
                'sourceVersion': _hash(core), 'topicVersion': _hash(_read(topic)), 'read': 'sp2build build guide --topic ' + topic,
                'status': 'emitted_not_model_receipt', 'permanentRetentionGuaranteed': False}
    except Exception:
        # A hint failure must never turn a successful native write into a retry.
        hint = {'status': 'guidance_unavailable', 'text': 'Preserve this operation result. Do not retry an accepted write to obtain guidance.'}
    return {key: value for key, value in [('success', result.get('success')), ('guidance', hint)]} | {key: value for key, value in result.items() if key != 'success'}


def _write_shortcuts():
    # The executor owns the shortcut registry: new aliases inherit guidance.
    from sp2build import ALIASES
    return ALIASES
