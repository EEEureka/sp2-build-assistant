"""Versioned, read-only native capability observations; never a write planner.

Schema readability, actual polygonal observations, and calibrated expressibility
are separate claims. A case is measured only at its exact native parameter
vector and observation domain. Missing support/calibration never implies that a
shape requires splitting or thin-panel construction.
"""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path

from .reference_storage import ReferenceError, digest, file_hash
from .regional_geometry import (capture, _document, _ids, _integer, _number,
    _vec, _native_relations, bounds, topology, section, WORLD, sub, norm, dot, mul, add)
from .boundary_review import normalize_reference, directed_certificate, WorkBudget


CAPABILITIES = ('closed_body', 'hollow_body', 'corner_controls', 'edge_curvature',
                'curved_body', 'section_cutting', 'hole', 'window', 'cut_edge_sampling')


def _functional_role(part):
    """Hole and Window can share ModifierWindow-1; inspect native hideGlass."""
    name = str(part.get('type', '')).lower()
    if 'hole' in name: return 'hole'
    if 'window' not in name: return None
    fields = _native_fields(part.get('serializedState'))
    flag = next((r['value'] for r in fields if '/ProceduralWindow.State' in r['path'] and r['path'].endswith('/@hideGlass')), None)
    if isinstance(flag, bool): return 'hole' if flag else 'window'
    if isinstance(flag, str) and flag.lower() in ('true', 'false'): return 'hole' if flag.lower() == 'true' else 'window'
    return 'window_or_hole_unresolved'


def _flatten(value, path=''):
    if isinstance(value, dict):
        return [row for key, item in value.items() for row in _flatten(item, path+'/'+str(key).replace('~', '~0').replace('/', '~1'))]
    if isinstance(value, list):
        return [row for index, item in enumerate(value) for row in _flatten(item, path+'/'+str(index))]
    return [{'path': path or '/', 'value': deepcopy(value)}]


def _native_fields(node, prefix=''):
    if not isinstance(node, dict): return []
    def walk(value, path):
        rows = [{'path': path+'/@'+str(key), 'value': item} for key, item in value.get('attributes', {}).items()]
        counts = {}
        for child in value.get('children', []):
            tag = str(child.get('tag', 'unknown')); index = counts.get(tag, 0); counts[tag] = index+1
            rows += walk(child, path+'/'+tag+'['+str(index)+']')
        return rows
    return walk(node, prefix+'/'+str(node.get('tag', 'unknown')))


def _shape_evidence(payload, cap):
    mapping = payload.get('shapeEvidence', {})
    if not isinstance(mapping, dict): raise ReferenceError('invalid_input', 'shapeEvidence must map part IDs to native shape.get evidence')
    values = {}
    for key, raw in mapping.items():
        try: pid = int(key)
        except (ValueError, TypeError) as error: raise ReferenceError('invalid_input', 'shapeEvidence keys must be native part IDs') from error
        if str(pid) not in cap['parts']: raise ReferenceError('part_not_found', 'shapeEvidence part is absent', partId=pid)
        if isinstance(raw, dict) and raw.get('success') is False:
            values[pid] = {'status': 'unavailable', 'error': deepcopy(raw.get('error'))}; continue
        value = _document(raw, 'shapeEvidence')
        if value.get('identity') != cap['identity'] or value.get('partId') != pid:
            raise ReferenceError('evidence_identity_mismatch', 'Capability shape evidence must match exact captured identity and part ID')
        shape = value.get('shape')
        if not isinstance(shape, dict): raise ReferenceError('invalid_input', 'Native shape.get evidence requires a shape object')
        values[pid] = {'status': 'readable' if shape.get('typedEditingSupported') else 'unmapped', 'shape': shape,
                       'fields': _flatten(shape), 'evidenceSha256': digest(value)}
    return values


def _versions(payload, cap):
    value = payload.get('versions')
    if not isinstance(value, dict) or any(not isinstance(value.get(k), str) or not value[k] for k in ('gameVersion', 'pluginVersion', 'toolVersion')):
        raise ReferenceError('capability_version_required', 'Capability audit requires explicit gameVersion, pluginVersion and toolVersion')
    if not cap['identity'].get('gameVersion') or value['gameVersion'] != cap['identity']['gameVersion']:
        raise ReferenceError('capability_version_mismatch', 'Game version must agree with the actual native identity')
    build = {}; receipt = payload.get('versionEvidence', {})
    if not isinstance(receipt, dict): raise ReferenceError('invalid_input', 'versionEvidence must be an object')
    if receipt.get('designerStatus') is not None:
        loaded = _document(receipt['designerStatus'], 'versionEvidence.designerStatus')
        if (loaded.get('identity') != cap['identity'] or loaded.get('pluginVersion') != value['pluginVersion']
                or loaded.get('gameVersion') != value['gameVersion'] or not loaded.get('buildId')):
            raise ReferenceError('capability_version_mismatch', 'Loaded plugin build receipt must match the actual native identity and versions')
        dll_hash = receipt.get('pluginDllSha256'); dll_path = receipt.get('pluginDllPath')
        if (not isinstance(dll_hash, str) or len(dll_hash) != 64
                or any(c not in '0123456789abcdef' for c in dll_hash.lower())):
            raise ReferenceError('capability_version_required', 'A loaded build receipt requires an exact plugin DLL SHA256')
        if dll_path and file_hash(dll_path).lower() != dll_hash.lower():
            raise ReferenceError('capability_version_mismatch', 'Plugin DLL changed since its declared build receipt')
        build = {'pluginBuildId': loaded['buildId'], 'pluginDllSha256': dll_hash.lower(),
                 'loadedBuildEvidenceSha256': digest(loaded), 'versionBinding': 'native_loaded_build_and_exact_dll_receipt'}
    build['auditImplementationSha256'] = file_hash(str(Path(__file__).resolve()))
    catalog = payload.get('catalogEvidence')
    if catalog is None:
        return {**deepcopy(value), **build, 'catalogStatus': 'missing', 'catalogSha256': None}
    catalog = _document(catalog, 'catalogEvidence')
    catalog_game = catalog.get('gameVersion') or catalog.get('identity', {}).get('gameVersion')
    if catalog_game != value['gameVersion']:
        raise ReferenceError('capability_version_mismatch', 'Catalog capability version differs from the actual mesh game version')
    return {**deepcopy(value), **build, 'catalogStatus': 'readable_native_schema', 'catalogSha256': digest(catalog),
            'versionSource': deepcopy(payload.get('versionEvidence', {'status': 'explicitly_declared_tool_versions'}))}


def _baseline(raw, cap):
    if raw is None: return None
    raw = _document(raw, 'case.baseline')
    before = capture(raw.get('snapshot'), raw.get('mesh') or raw.get('actualMesh'))
    if (before['identity'].get('gameVersion') != cap['identity'].get('gameVersion')
            or before['identity']['craftSessionId'] != cap['identity']['craftSessionId']
            or before['identity']['revision'] > cap['identity']['revision']):
        raise ReferenceError('evidence_identity_mismatch', 'Native calibration before/after requires ordered same-session and same-game-version captures')
    return before


def _capability_traits(capability, ids, shapes, cap, relations):
    fields = [row for pid in ids for row in shapes.get(pid, {}).get('fields', [])]
    if capability in ('closed_body', 'hollow_body'):
        wanted = capability == 'hollow_body'
        found = [r for r in fields if r['path'] == '/configuration/hollow' and r['value'] is wanted]
        return {'status': 'readable' if found else 'uncalibrated', 'evidence': found,
                'reason': 'Native effective hollow flag must agree with the requested representation'}
    if capability in ('corner_controls', 'edge_curvature', 'section_cutting'):
        field = {'corner_controls': '/cornerRadius/', 'edge_curvature': '/edgeCurvature/', 'section_cutting': '/cutting/'}[capability]
        found = [r for r in fields if field in r['path'] and (capability != 'section_cutting' or r['value'] is not None)]
        return {'status': 'readable' if found else 'uncalibrated', 'evidence': found,
                'reason': 'Relevant effective native controls must be present; XML/default guesses are insufficient'}
    if capability == 'curved_body':
        found = [r for r in fields if r['path'].startswith('/sectionCapabilities/') and r['path'].endswith('/role') and r['value'] == 'curve_control']
        return {'status': 'readable' if found else 'uncalibrated', 'evidence': found,
                'reason': 'Native curve_control role is required; three observed stations do not imply three native controls'}
    if capability in ('hole', 'window'):
        owners = [pid for pid in ids if _functional_role(cap['parts'][str(pid)]) == capability]
        dependencies = [r for r in relations if r.get('ownerPartId') in owners and set(r.get('targetPartIds', [])) & set(ids)]
        return {'status': 'readable' if owners and dependencies else 'uncalibrated',
                'evidence': dependencies, 'functionalOwnerPartIds': owners,
                'reason': 'Functional native type and explicit target declaration are required; own render mesh is optional'}
    if capability == 'cut_edge_sampling':
        owners = [pid for pid in ids if _functional_role(cap['parts'][str(pid)]) in ('hole', 'window')]
        dependencies = [r for r in relations if r.get('ownerPartId') in owners and set(r.get('targetPartIds', [])) & set(ids)]
        return {'status': 'readable' if owners and dependencies else 'uncalibrated', 'evidence': dependencies,
                'reason': 'Requires independent before/after measurement of the actual cutter-generated edge, not host samples or triangle count'}
    return {'status': 'uncalibrated', 'reason': 'Unknown native capability needs a versioned measured protocol'}


def _clip_segments(segments, region):
    low, high = _vec(region.get('min'), 'regionWorld.min'), _vec(region.get('max'), 'regionWorld.max')
    if any(a > b for a, b in zip(low, high)): raise ReferenceError('invalid_input', 'regionWorld bounds must be ordered')
    result = []
    for row in segments:
        a, b = row['a'], row['b']; delta = sub(b, a); enter, leave = 0., 1.
        for axis in range(3):
            if abs(delta[axis]) < 1e-12:
                if a[axis] < low[axis]-1e-9 or a[axis] > high[axis]+1e-9: enter, leave = 1., 0.; break
            else:
                t0, t1 = (low[axis]-a[axis])/delta[axis], (high[axis]-a[axis])/delta[axis]
                enter, leave = max(enter, min(t0, t1)), min(leave, max(t0, t1))
        if leave-enter > 1e-10:
            result.append({'a': list(add(a, mul(delta, enter))), 'b': list(add(a, mul(delta, leave)))})
    return result


def _polyline_metrics(segments, tolerance=1e-7):
    """Collapse collinear tessellation so host re-triangulation is not refinement."""
    key = lambda p: tuple(round(v/tolerance) for v in p)
    positions = {}; edges = set()
    for s in segments:
        a, b = key(s['a']), key(s['b'])
        positions[a], positions[b] = s['a'], s['b']
        if a != b: edges.add(tuple(sorted((a, b))))
    changed = True
    while changed:
        changed = False; adjacency = {}
        for a, b in edges:
            adjacency.setdefault(a, set()).add(b); adjacency.setdefault(b, set()).add(a)
        for pivot, neighbors in adjacency.items():
            if len(neighbors) != 2: continue
            a, b = sorted(neighbors); u, v = sub(positions[a], positions[pivot]), sub(positions[b], positions[pivot])
            if norm(u)*norm(v) > tolerance*tolerance and dot(u, v)/(norm(u)*norm(v)) < -1+1e-9:
                edges.remove(tuple(sorted((a, pivot)))); edges.remove(tuple(sorted((b, pivot))))
                edges.add(tuple(sorted((a, b)))); changed = True; break
    adjacency = {}; turns = []; lengths = []
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b); adjacency.setdefault(b, set()).add(a)
        lengths.append(norm(sub(positions[a], positions[b])))
    for pivot, neighbors in adjacency.items():
        if len(neighbors) != 2: continue
        a, b = sorted(neighbors); u, v = sub(positions[a], positions[pivot]), sub(positions[b], positions[pivot])
        cosine = max(-1., min(1., dot(u, v)/(norm(u)*norm(v))))
        turns.append(180-math.degrees(math.acos(cosine)))
    return {'rawSegmentCount': len(segments), 'effectiveNoncollinearSegmentCount': len(edges),
            'maximumTurnDegrees': max(turns, default=0.), 'maximumEffectiveSegmentLengthM': max(lengths, default=0.),
            'totalLengthM': sum(lengths), 'endpointCount': sum(len(n) == 1 for n in adjacency.values()),
            'basis': 'actual_clipped_section_with_collinear_retriangulation_removed',
            'limitations': ['Turn/length are polygonal discretization metrics, not an analytic arc chord-error bound.']}


def _sampling_comparison(spec, cap, ids, before, work, base):
    if before is None or before['mesh'].get('complete') is not True or cap['mesh'].get('complete') is not True:
        return {**base, 'status': 'uncalibrated', 'reason': 'Complete ordered native before/after captures are required'}
    host = _integer(spec.get('hostPartId'), 'hostPartId'); generator = _integer(spec.get('generatorPartId'), 'generatorPartId')
    if host not in ids or generator not in ids:
        raise ReferenceError('invalid_scope', 'Sampling host and generator must belong to observation scope')
    if any(str(pid) not in before['parts'] for pid in (host, generator)) or host not in before['triangles'] or host not in cap['triangles']:
        return {**base, 'status': 'uncalibrated', 'reason': 'Actual host or functional generator is absent before/after'}
    generator_equal = before['partHashes'][str(generator)] == cap['partHashes'][str(generator)]
    original = {r['path']: r['value'] for r in _native_fields(before['parts'][str(host)].get('serializedState'))}
    current = {r['path']: r['value'] for r in _native_fields(cap['parts'][str(host)].get('serializedState'))}
    differences = [{'path': path, 'before': original.get(path), 'after': current.get(path)}
                   for path in sorted(set(original)|set(current)) if original.get(path) != current.get(path)]
    samples_only = bool(differences) and all(r['path'].endswith('/@cornerSamples') or r['path'].endswith('/@edgeSamples') for r in differences)
    increases = []
    for change in differences:
        try:
            old_values = [int(v) for v in str(change['before']).split(',')]
            new_values = [int(v) for v in str(change['after']).split(',')]
            increases.append(len(old_values) == len(new_values) and all(b >= a for a, b in zip(old_values, new_values)) and any(b > a for a, b in zip(old_values, new_values)))
        except (ValueError, TypeError): increases.append(False)
    samples_increased = samples_only and all(increases)
    stable_pose = all(before['parts'][str(host)].get(k) == cap['parts'][str(host)].get(k)
                      for k in ('position', 'rotationQuaternion', 'rotationEuler', 'scale', 'materialIds', 'connectedPartIds'))
    relations, _ = _native_relations(cap, set(ids))
    dependencies = [r for r in relations if r.get('ownerPartId') == generator and host in r.get('targetPartIds', [])]
    if not generator_equal or not samples_only or not samples_increased or not stable_pose or not dependencies:
        return {**base, 'status': 'uncalibrated', 'reason': 'Isolate host sample fields while keeping actual generator/host pose and targets unchanged',
                'measured': {'generatorFingerprintUnchanged': generator_equal, 'hostOnlySampleFieldsChanged': samples_only,
                             'hostSamplesIncreased': samples_increased,
                             'hostPoseMaterialsConnectionsUnchanged': stable_pose, 'hostNativeChanges': differences,
                             'generatorDependencies': dependencies}}
    axis = _integer(spec.get('axis'), 'sampling.axis')
    if axis > 2: raise ReferenceError('invalid_input', 'sampling.axis must be 0..2')
    station = _number(spec.get('stationM'), 'sampling.stationM', -math.inf)
    region = spec.get('regionWorld')
    if not isinstance(region, dict): raise ReferenceError('invalid_input', 'Sampling comparison requires an explicit actual cutter regionWorld')
    low, high = _vec(region.get('min')), _vec(region.get('max'))
    origin = _vec(cap['parts'][str(generator)].get('position'))
    if any(origin[i] < low[i]-1e-7 or origin[i] > high[i]+1e-7 for i in range(3)) or not low[axis]-1e-7 <= station <= high[axis]+1e-7:
        return {**base, 'status': 'uncalibrated', 'reason': 'The declared section ROI must include the actual native cutter origin and section plane'}
    cost = len(before['triangles'][host])+len(cap['triangles'][host])
    if work.section_used+cost > work.section_maximum:
        return {**base, 'status': 'uncalibrated', 'reason': 'capability_section_triangle_budget_exceeded'}
    work.section_used += cost
    before_section = section(before['triangles'][host], axis, station)
    after_section = section(cap['triangles'][host], axis, station)
    first = _clip_segments(before_section['segments'], region); second = _clip_segments(after_section['segments'], region)
    if not first or not second:
        return {**base, 'status': 'uncalibrated', 'reason': 'No actual cutter-region contour was observed at this plane'}
    tolerance = _number(spec.get('expected', {}).get('maxContourDistanceM'), 'expected.maxContourDistanceM')
    ab = directed_certificate([(s['a'], s['b']) for s in first], [(s['a'], s['b']) for s in second], tolerance, work)
    ba = directed_certificate([(s['a'], s['b']) for s in second], [(s['a'], s['b']) for s in first], tolerance, work)
    metrics_a, metrics_b = _polyline_metrics(first), _polyline_metrics(second)
    relation = spec.get('expected', {}).get('relation', 'unchanged')
    angle_tolerance = _number(spec.get('expected', {}).get('maxTurnChangeDegrees', .0001), 'expected.maxTurnChangeDegrees')
    length_tolerance = _number(spec.get('expected', {}).get('maxSegmentLengthChangeM', tolerance), 'expected.maxSegmentLengthChangeM')
    same = (metrics_a['effectiveNoncollinearSegmentCount'] == metrics_b['effectiveNoncollinearSegmentCount']
            and abs(metrics_a['maximumTurnDegrees']-metrics_b['maximumTurnDegrees']) <= angle_tolerance
            and abs(metrics_a['maximumEffectiveSegmentLengthM']-metrics_b['maximumEffectiveSegmentLengthM']) <= length_tolerance)
    improved = metrics_b['maximumTurnDegrees'] < metrics_a['maximumTurnDegrees']-angle_tolerance and metrics_b['effectiveNoncollinearSegmentCount'] > metrics_a['effectiveNoncollinearSegmentCount']
    if relation not in ('unchanged', 'improved'): raise ReferenceError('invalid_input', 'Sampling expected.relation must be unchanged or improved')
    geometric_ok = ab['status'] == ba['status'] == 'passed'
    status = 'measured' if geometric_ok and (same if relation == 'unchanged' else improved) else 'failed' if 'failed' in (ab['status'], ba['status']) or geometric_ok else 'uncalibrated'
    return {**base, 'status': status, 'measured': {'hostPartId': host, 'generatorPartId': generator,
        'axis': axis, 'stationM': station, 'regionWorld': region, 'beforeContour': first, 'afterContour': second,
        'beforeToAfter': ab, 'afterToBefore': ba, 'beforeMetrics': metrics_a, 'afterMetrics': metrics_b,
        'generatorFingerprintUnchanged': generator_equal, 'generatorFingerprint': cap['partHashes'][str(generator)],
        'hostNativeChanges': differences, 'onlyHostSampleFieldsChanged': samples_only,
        'hostSamplesIncreased': samples_increased,
        'generatorDependencies': dependencies,
        'comparisonTolerances': {'contourDistanceM': tolerance, 'turnChangeDegrees': angle_tolerance,
                                 'segmentLengthChangeM': length_tolerance},
        'conclusion': 'host_sampling_did_not_refine_this_cut_contour' if geometric_ok and same else 'actual_cut_polygon_discretization_improved' if geometric_ok and improved else 'requested_sampling_relation_not_established'},
        'limitations': ['This exact finite cutter ROI and same-version controls only; no universal sampling rule or smooth arc fit is asserted.',
                        'Native source annotations may explain the result but never substitute for these actual contour measurements.']}


def _observe(spec, cap, case_ids, before, work):
    if not isinstance(spec, dict): raise ReferenceError('invalid_input', 'Capability observation must be an object')
    kind = spec.get('kind'); ids = _ids(spec.get('partIds', case_ids))
    if not set(ids) <= set(case_ids):
        raise ReferenceError('invalid_scope', 'Observation parts must belong to the case including its functional host')
    triangles = [t for pid in ids for t in cap['triangles'].get(pid, [])]
    base = {'kind': kind, 'partIds': ids, 'expected': deepcopy(spec.get('expected', {})),
            'basis': 'actual_native_captured_triangles', 'identity': cap['identity']}
    expected = spec.get('expected', {})
    if not isinstance(expected, dict): raise ReferenceError('invalid_input', 'Observation expected must be an object')
    if kind == 'functional_dependency':
        owner = _integer(spec.get('ownerPartId'), 'ownerPartId'); targets = _ids(spec.get('targetPartIds'))
        if owner not in case_ids or not set(targets) <= set(case_ids):
            raise ReferenceError('invalid_scope', 'Functional owner and targets must belong to the case')
        relations, _ = _native_relations(cap, set(case_ids))
        found = [r for r in relations if r.get('ownerPartId') == owner and set(targets) <= set(r.get('targetPartIds', []))]
        return {**base, 'status': 'readable' if found else 'uncalibrated', 'basis': 'native_serialized_target_declaration',
                'measured': {'relations': found, 'ownerHasVisibleMesh': owner in cap['triangles']},
                'limitations': ['A target declaration does not prove evaluated cut effect, its shape or visible opening.']}
    if kind == 'cut_edge_sampling_comparison':
        return _sampling_comparison(spec, cap, ids, before, work, base)
    if kind == 'geometry_change':
        if before is None:
            return {**base, 'status': 'uncalibrated', 'reason': 'An independently captured native baseline is required'}
        if any(pid not in cap['triangles'] or pid not in before['triangles'] for pid in ids):
            return {**base, 'status': 'uncalibrated', 'reason': 'Actual host surfaces are absent before or after'}
        rows = [{'partId': pid, 'changed': before['triangles'][pid] != cap['triangles'][pid],
                 'beforeMeshSha256': digest(before['triangles'][pid]), 'afterMeshSha256': digest(cap['triangles'][pid]),
                 'beforeBounds': before['bounds'][pid], 'afterBounds': cap['bounds'][pid],
                 'authoredHostUnchanged': before['partHashes'][str(pid)] == cap['partHashes'][str(pid)]} for pid in ids]
        ok = all(r['changed'] for r in rows)
        if spec.get('requireAuthoredHostUnchanged'): ok = ok and all(r['authoredHostUnchanged'] for r in rows)
        return {**base, 'status': 'measured' if ok else 'failed', 'measured': {'parts': rows},
                'limitations': ['Change demonstrates an effect at these controls only, not which operator caused it without isolation.']}
    if any(pid not in cap['triangles'] for pid in ids):
        return {**base, 'status': 'uncalibrated', 'reason': 'A required actual surface is unavailable; functional absence does not imply redundancy'}
    if kind == 'mesh_available':
        count = len(triangles); minimum = _integer(expected.get('minimumTriangles', 1), 'minimumTriangles')
        return {**base, 'status': 'measured' if count >= minimum else 'failed', 'measured': {'triangleCount': count},
                'limitations': ['Geometry availability alone cannot calibrate shape expressibility.']}
    if kind == 'topology':
        result = topology(triangles); ok = True; tested = 0
        for field in ('boundaryEdgeCount', 'nonManifoldEdgeCount', 'degenerateTriangleCount'):
            if field in expected:
                ok = ok and result[field] == _integer(expected[field], 'expected.'+field); tested += 1
        return {**base, 'status': ('measured' if ok else 'failed') if tested else 'readable', 'measured': result,
                'limitations': ['Welded polygonal topology does not establish closed solid volume or collision correctness.']}
    if kind == 'section':
        if work.section_used+len(triangles) > work.section_maximum:
            return {**base, 'status': 'uncalibrated', 'reason': 'capability_section_triangle_budget_exceeded'}
        work.section_used += len(triangles)
        result = section(triangles, spec.get('axis'), spec.get('stationM')); tested = 0; ok = bool(result['segments'])
        for field in ('closedLoopCount', 'nestedContourLoops', 'openEndpointCount', 'branchVertexCount', 'segmentCount'):
            if field in expected:
                tested += 1; ok = ok and result[field] == expected[field]
        spans = []
        for span in expected.get('spans', []):
            axis = _integer(span.get('axis'), 'span.axis')
            if axis > 2: raise ReferenceError('invalid_input', 'span.axis must be 0..2')
            positions = [p[axis] for s in result['segments'] for p in (s['a'], s['b'])]
            measured = max(positions)-min(positions) if positions else None
            if 'expectedM' in span:
                value = _number(span.get('expectedM'), 'span.expectedM'); tolerance = _number(span.get('toleranceM'), 'span.toleranceM')
                passed = measured is not None and abs(measured-value) <= tolerance
                spans.append({'axis': axis, 'actualM': measured, 'expectedM': value, 'toleranceM': tolerance, 'passed': passed})
            else:
                minimum = _number(span.get('minimumM'), 'span.minimumM'); maximum = _number(span.get('maximumM'), 'span.maximumM')
                if minimum > maximum: raise ReferenceError('invalid_input', 'Expected span bounds must be ordered')
                passed = measured is not None and minimum <= measured <= maximum
                spans.append({'axis': axis, 'actualM': measured, 'minimumM': minimum, 'maximumM': maximum, 'passed': passed})
            tested += 1; ok = ok and passed
        return {**base, 'status': ('measured' if ok else 'failed') if tested else 'readable',
                'measured': {**result, 'spanChecks': spans},
                'limitations': ['Calibrated observation at this plane only; native control slice is not substituted for actual mesh.']}
    if kind == 'reference_fit':
        reference = normalize_reference(spec.get('referenceMesh'))
        targets = [t for rows in reference['triangles'].values() for t in rows]
        tolerance = _number(expected.get('maxSurfaceDistanceM'), 'expected.maxSurfaceDistanceM')
        ab = directed_certificate(triangles, targets, tolerance, work)
        ba = directed_certificate(targets, triangles, tolerance, work)
        complete = ab['complete'] and ba['complete'] and reference['complete']
        status = 'failed' if 'failed' in (ab['status'], ba['status']) else 'measured' if complete and ab['status'] == ba['status'] == 'passed' else 'uncalibrated'
        return {**base, 'status': status, 'measured': {'actualToReference': ab, 'referenceToActual': ba},
                'referenceIdentity': reference['identity'], 'sourceProvenance': reference['sourceProvenance'],
                'limitations': ['Continuous finite polygonal domain only; no extrapolation to other native control vectors.']}
    return {**base, 'status': 'uncalibrated', 'reason': 'Unsupported observation kind; calibrate or extend the measured protocol instead of assuming a split is required'}


def audit(payload, context=None):
    cap = capture(payload.get('snapshot'), payload.get('mesh') or payload.get('actualMesh'))
    versions = _versions(payload, cap); shapes = _shape_evidence(payload, cap)
    cases = payload.get('cases')
    if not isinstance(cases, list) or not cases or len(cases) > 128:
        raise ReferenceError('invalid_input', 'Capability audit requires 1..128 bounded cases')
    work = WorkBudget(payload.get('budget', {}).get('maxCapabilityDistanceTests', 100000))
    work.section_used = 0
    work.section_maximum = _integer(payload.get('budget', {}).get('maxCapabilitySectionTriangleTests', 500000), 'maxCapabilitySectionTriangleTests', 1)
    if work.section_maximum > 5000000: raise ReferenceError('invalid_input', 'Capability section budget exceeds local ceiling')
    results = []; names = set()
    relations, _ = _native_relations(cap, {int(pid) for pid in cap['parts']})
    for spec in cases:
        if not isinstance(spec, dict) or not isinstance(spec.get('id'), str) or not spec['id'] or spec['id'] in names:
            raise ReferenceError('invalid_input', 'Capability cases require unique nonempty IDs')
        names.add(spec['id']); ids = _ids(spec.get('partIds'))
        if any(str(pid) not in cap['parts'] for pid in ids): raise ReferenceError('part_not_found', 'Capability case refers to absent parts')
        before = _baseline(spec.get('baseline'), cap)
        controls = []; missing_controls = []
        for control in spec.get('controls', []):
            pid = _integer(control.get('partId'), 'control.partId'); source = control.get('source', 'shape')
            if pid not in ids: raise ReferenceError('invalid_scope', 'Control part must belong to its capability case')
            fields = shapes.get(pid, {}).get('fields', []) if source == 'shape' else _native_fields(cap['parts'][str(pid)].get('serializedState')) if source == 'native' else []
            found = next((row for row in fields if row['path'] == control.get('path')), None)
            item = {'partId': pid, 'source': source, 'path': control.get('path'), 'status': 'readable' if found else 'missing',
                    'value': deepcopy(found['value']) if found else None, 'basis': 'same_state_shape_get' if source == 'shape' else 'authored_serialized_native_field'}
            if found and 'equals' in control:
                item['expectedValue'] = deepcopy(control['equals'])
                item['status'] = 'readable' if found['value'] == control['equals'] else 'mismatch'
            controls.append(item)
            if item['status'] != 'readable': missing_controls.append(item)
        observation_specs = spec.get('observations', [])
        if not isinstance(observation_specs, list) or len(observation_specs) > 256:
            raise ReferenceError('invalid_input', 'Each capability case supports at most 256 observations')
        observations = [_observe(row, cap, ids, before, work) for row in observation_specs]
        capability = spec.get('capability'); supported = capability in CAPABILITIES
        traits = _capability_traits(capability, ids, shapes, cap, relations)
        # Availability, raw topology and declared dependencies cannot by
        # themselves prove a native representation's shape capability.
        substantive = [r for r in observations if r['kind'] in ('section', 'reference_fit', 'geometry_change', 'cut_edge_sampling_comparison')]
        if capability == 'cut_edge_sampling':
            substantive = [r for r in observations if r['kind'] == 'cut_edge_sampling_comparison']
        source_complete = cap['mesh'].get('complete') is True
        measured = source_complete and supported and traits['status'] == 'readable' and bool(controls) and not missing_controls and substantive and all(r['status'] in ('measured', 'readable') for r in observations) and all(r['status'] == 'measured' for r in substantive)
        conclusion = 'measured' if measured else 'readable' if supported and traits['status'] == 'readable' and controls and not missing_controls and not any(r['status'] in ('failed', 'uncalibrated') for r in observations) else 'uncalibrated'
        functional = [{'partId': pid, 'nativeType': cap['parts'][str(pid)].get('type'), 'functionalRole': _functional_role(cap['parts'][str(pid)]),
                       'functionalRoleBasis': 'native_type_and_explicit_ProceduralWindow_hideGlass_flag', 'hasVisibleMesh': pid in cap['triangles'],
                       'dependencies': [r for r in relations if r.get('ownerPartId') == pid],
                       'redundancyConclusion': 'not_inferred_from_mesh_absence'} for pid in ids
                      if any(label in str(cap['parts'][str(pid)].get('type', '')).lower() for label in ('hole', 'window'))]
        generators = []
        for row in spec.get('edgeGenerators', []):
            host = _integer(row.get('hostPartId'), 'edgeGenerator.hostPartId')
            generator = _integer(row.get('generatorPartId'), 'edgeGenerator.generatorPartId')
            if host not in ids or generator not in ids: raise ReferenceError('invalid_scope', 'Host and edge generator must belong to their capability case')
            relevant = [r for r in relations if r.get('ownerPartId') == generator and host in r.get('targetPartIds', [])]
            declared_native = row.get('kind') == 'native_section' and host == generator
            generators.append({**deepcopy(row), 'status': 'native_dependency_readable' if relevant or declared_native else 'unresolved',
                'basis': 'native_target_declaration' if relevant else 'explicit_same_part_native_section_annotation' if declared_native else 'annotation_only',
                'relations': relevant, 'samplingConclusion': 'Host samples do not prove refinement of a cutter-generated edge; compare actual edge geometry after changing its generator'})
        domain = {'partIds': ids, 'exactControlVector': controls,
                  'nativeShapeHashes': {str(pid): shapes[pid]['evidenceSha256'] for pid in ids if shapes.get(pid, {}).get('evidenceSha256')},
                  'actualMeshHashes': {str(pid): digest(cap['triangles'].get(pid, [])) for pid in ids},
                  'observedPlanes': [{'axis': o['measured']['axis'], 'stationM': o['measured']['stationM']} for o in observations if o['kind'] == 'section' and o.get('measured')],
                  'interpolationOrExtrapolationCalibrated': False, 'scope': 'exact observed native controls and explicitly measured polygonal domains only'}
        results.append({'id': spec['id'], 'capability': capability, 'partIds': ids, 'role': spec.get('role'),
            'conclusion': conclusion, 'calibrationStatus': 'measured_exact_case_only' if conclusion == 'measured' else 'requires_calibration',
            'sourceCoverageStatus': 'complete' if source_complete else 'uncertain_export_completeness_not_declared',
            'versions': versions, 'identity': cap['identity'], 'geometryStamp': cap['geometryStamp'],
            'controls': controls, 'observations': observations, 'domain': domain,
            'capabilityTraits': traits,
            'sourceAnnotations': {'items': deepcopy(spec.get('sourceAnnotations', [])),
                                  'meaning': 'Versioned read-only source context; never native measurement or calibration evidence'},
            'nativeTraits': {str(pid): shapes.get(pid, {'status': 'not_read'}) for pid in ids},
            'functionalParts': functional, 'edgeGenerators': generators,
            'splitRequired': None, 'writeOperations': [],
            'limitations': ['No unmeasured native family/domain is declared unsupported or split-required.',
                'Readable controls/schema are not a fitting or aesthetic acceptance result.',
                'Mass, buoyancy, collisions and native appearance require independent observations.']})
    result = {'schemaVersion': 1, 'kind': 'sp2build.nativeCapabilityAudit', 'identity': cap['identity'],
        'geometryStamp': cap['geometryStamp'], 'versions': versions,
        'coordinateFrame': {'units': 'm', 'frameToWorldRows': WORLD}, 'cases': results,
        'distanceTests': work.used, 'maximumDistanceTests': work.maximum,
        'sectionTriangleTests': work.section_used, 'maximumSectionTriangleTests': work.section_maximum,
        'versionInvalidation': 'Game/plugin/tool/catalog changes require fresh same-version calibration; do not silently reuse prior cases',
        'completeCapabilityAcceptance': False}
    result['reportSha256'] = digest(result)
    return result


def dispatch(action, payload, context=None):
    if action not in ('knowledge.capabilityAudit', 'knowledge.capabilityaudit', 'capability.audit'):
        raise ReferenceError('unsupported_command', 'Unsupported native capability audit action', action=action)
    return audit(payload, context=context)
