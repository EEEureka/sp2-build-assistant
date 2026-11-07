"""Reference-driven, bounded comparisons over captured native geometry.

Feature coordinates are already in the frozen task frame, in metres. The
reference's source-to-task transform is *not* a native-world transform. This
module never fits, recentres, edits, or silently selects a subset of a component.
It reuses the SDK contour/surface/probe evaluators; planar union is explicitly
limited to valid closed polygon sections and is not a 3D Boolean engine.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import html
import math

from .errors import ModelingError
from .geometry import Frame, add, sub, scale, dot, cross, magnitude, unit, vector, number
from .mesh import MeshEvidence, compare_contours
from .surface import compare_surfaces, triangles
from .transport import canonical_json
from .project import same_identity
from .verification import closed_mesh, point_inside


_KINDS = {'contour': 'section_contour', 'section_contour': 'section_contour',
          'section_center': 'section_center', 'section_boundary': 'section_boundary',
          'relative_pose': 'relative_pose', 'negative_space': 'negative_space',
          'surface': 'surface', 'mesh_extent': 'mesh_extent', 'visual': 'visual'}
_SHAPE_KINDS = {'section_contour', 'surface'}
_LIMITS = {'max_targets': 256, 'max_union_edges': 1000, 'max_union_tests': 2000000, 'max_contour_samples': 100000,
           'max_surface_samples': 50000, 'max_triangle_tests': 2000000,
           'max_diagnostic_tests': 1000000}


def _incomplete(reason, **details):
    return {'status': 'incomplete', 'reason': reason, **details}


def _budget(values=None):
    result = dict(_LIMITS)
    for key, value in (values or {}).items():
        if key not in result or type(value) is not int or not 1 <= value <= _LIMITS[key]:
            raise ModelingError('measurement_budget', 'Unknown or excessive comparison budget', {'field': key, 'maximum': _LIMITS.get(key)})
        result[key] = value
    return result


def _features(reference):
    values = reference.get('features', [])
    if not isinstance(values, list) or len(values) > _LIMITS['max_targets']:
        raise ModelingError('invalid_reference', 'features must be a bounded list')
    ids = [f.get('id') for f in values if isinstance(f, dict)]
    if len(ids) != len(values) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ModelingError('invalid_reference', 'Each feature needs a unique nonempty id')
    return values


def _stamp(reference):
    return {'referenceId': reference.get('referenceId'), 'referenceVersion': reference.get('version'),
            'referenceContentHash': reference.get('contentHash'), 'frameId': reference.get('frameId')}


def reference_targets(reference, *, tolerance_m=.01, required_features=None, component=None):
    """Generate reviewable checks from explicit frozen features, not guessed CAD.

Each feature supplies id, component, kind, expected (or geometry), scope,
viewId, parameters and evidenceSource. Missing geometric truth stays a coverage
issue. Photo estimates need an explicitly accepted assumption before a point
target can be treated as a precise acceptance value.
    """
    tolerance = number(tolerance_m, 'tolerance_m', 0, 1000)
    features = _features(reference)
    if component is not None:
        features = [feature for feature in features if feature.get('component') == component]
        if not features: raise ModelingError('invalid_component', 'Reference has no features for this component')
    if required_features is not None and (not isinstance(required_features, (list, tuple)) or any(not isinstance(value, str) for value in required_features)):
        raise ModelingError('invalid_feature', 'required_features must be an explicit list of feature ids')
    required = set([f['id'] for f in features if f.get('required', True)] if required_features is None else required_features)
    unknown = required - {f['id'] for f in features}
    if unknown:
        raise ModelingError('invalid_feature', 'Unknown required features', {'featureIds': sorted(unknown)})
    targets = []
    for feature in features:
        target = {'id': feature['id'], 'featureId': feature['id'], 'component': feature.get('component'),
                  'kind': _KINDS.get(feature.get('kind'), feature.get('kind')),
                  'expected': deepcopy(feature.get('expected', feature.get('geometry', {}))),
                  'required': feature['id'] in required, 'priority': feature.get('priority', 'P0'),
                  'scope': deepcopy(feature.get('scope', feature.get('component'))),
                  'frameId': feature.get('frameId', reference.get('frameId')),
                  'units': feature.get('units', 'm'), 'viewId': feature.get('viewId'),
                  'toleranceMetres': number(feature.get('toleranceMetres', feature.get('tolerance_m', tolerance)), 'feature tolerance', 0, 1000),
                  'parameters': deepcopy(feature.get('parameters', [])),
                  'evidenceSource': deepcopy(feature.get('evidenceSource', reference.get('source'))),
                  'evidenceKind': feature.get('evidenceKind', 'unspecified'),
                  'certainty': 'exact' if feature.get('evidenceKind') in ('measured', 'user') else 'uncertain',
                  'assumptionAccepted': feature.get('assumptionAccepted', False)}
        targets.append(target)
    result = {'schemaVersion': 'sp2model.comparison-targets/1', **_stamp(reference), 'targets': targets,
              'scopeComponents': [component] if component is not None else None}
    result['coverage'] = validate_coverage(reference, result)
    result['targetHash'] = _target_hash(result)
    result['meaning'] = 'Reviewable acceptance suggestions. Coordinates are task-frame metres; freezing and amendments belong to the persistent task.'
    return result


def _target_hash(contract):
    return hashlib.sha256(canonical_json({**{k: contract.get(k) for k in _stamp({})}, 'scopeComponents': contract.get('scopeComponents'), 'targets': contract.get('targets', [])})).hexdigest()


def _validate_expected(kind, expected):
    """Validate geometry truth before a dependent construction is admitted."""
    if kind in ('section_contour', 'section_center', 'section_boundary'):
        origin, normal, _, _ = _basis(expected['origin'], expected['normal'])
        tolerance = number(expected.get('weldToleranceMetres', 1e-6), 'weld tolerance', 1e-10, .01)
        if expected.get('boundaryRule', 'planar_union') not in ('planar_union', 'cap_boundary', 'single_part'):
            raise ModelingError('invalid_boundary', 'Unsupported explicit section boundary rule')
        if kind == 'section_contour':
            loops = _reference_section(expected)['parts'][0]['loops']
            if any(abs(dot(sub(point, origin), normal)) > tolerance for loop in loops for point in loop):
                raise ModelingError('invalid_contour', 'Reference contour is outside its declared plane')
        elif kind == 'section_center':
            if expected.get('definition') != 'boundary_bbox':
                raise ModelingError('invalid_center', 'Declare boundary_bbox center semantics explicitly')
            if abs(dot(sub(vector(expected['center']), origin), normal)) > tolerance:
                raise ModelingError('invalid_center', 'Reference section center is outside its plane')
        else:
            axis = unit(expected['axis'])
            if abs(dot(axis, normal)) > 1 - 1e-8 or expected.get('side') not in ('min', 'max'):
                raise ModelingError('invalid_boundary', 'Section boundary needs an in-plane direction and min/max side')
            number(expected['valueMetres'], 'boundary coordinate')
    elif kind == 'mesh_extent':
        unit(expected['axis']); number(expected.get('valueMetres', expected.get('value_m')), 'extent', 0)
    elif kind == 'surface':
        if not triangles(expected.get('triangles', [])):
            raise ModelingError('invalid_surface', 'A required reference surface cannot be empty')
    elif kind == 'negative_space':
        probes = expected.get('probes')
        if not isinstance(probes, list) or not 1 <= len(probes) <= 1000:
            raise ModelingError('invalid_probe', 'Declare 1..1000 required void probes')
        for probe in probes:
            vector(probe['point'] if isinstance(probe, dict) else probe)
            if isinstance(probe, dict) and probe.get('inside', False) is not False:
                raise ModelingError('invalid_probe', 'Negative-space targets must require outside, not inside')
    elif kind == 'relative_pose':
        vector(expected['deltaMetres'])
        if expected.get('anchor') != 'mesh_bbox_center' or not isinstance(expected.get('otherComponent'), str):
            raise ModelingError('invalid_relative_pose', 'Declare the opposite component and mesh_bbox_center anchor semantics')
    elif kind == 'visual':
        if not expected.get('requiredViews'):
            raise ModelingError('invalid_visual', 'Declare required views; image generation alone is never visual acceptance')


def validate_coverage(reference, contract):
    """Reject a bbox-only or selectively scoped contract before model writes."""
    targets = contract.get('targets', []) if isinstance(contract, dict) else contract
    features = _features(reference)
    scope = contract.get('scopeComponents') if isinstance(contract, dict) else None
    if scope is not None:
        if not isinstance(scope, list) or not scope or any(not isinstance(c, str) for c in scope):
            raise ModelingError('invalid_component', 'Comparison scopeComponents must be nonempty component names')
        unknown = set(scope) - {feature.get('component') for feature in features}
        if unknown: raise ModelingError('invalid_component', 'Comparison scope names unknown reference components', {'components': sorted(unknown)})
        features = [feature for feature in features if feature.get('component') in scope]
    issues = []
    if reference.get('status') != 'ready':
        issues.append({'code': 'reference_unresolved', 'action': 'Resolve selection, frame and assumptions before dependent construction.'})
    if not reference.get('referenceId') or reference.get('version') is None or not reference.get('contentHash') or not reference.get('frameId'):
        issues.append({'code': 'reference_identity_missing', 'action': 'Bind a versioned reference and a task frame.'})
    if not isinstance(targets, list) or len(targets) > _LIMITS['max_targets']:
        raise ModelingError('invalid_targets', 'targets must be a bounded list')
    required = [t for t in targets if t.get('required', True)]
    if not required:
        issues.append({'code': 'no_required_targets', 'action': 'Declare the important features and measurable acceptance targets.'})
    target_ids = [t.get('id') for t in targets]
    if any(not isinstance(i, str) or not i for i in target_ids) or len(set(target_ids)) != len(target_ids):
        issues.append({'code': 'duplicate_or_missing_target_id'})
    components = {f.get('component') for f in features if f.get('required', True)}
    for component in sorted(components, key=str):
        if not component:
            issues.append({'code': 'component_missing'})
        elif not any(t.get('component') == component and t.get('kind') in _SHAPE_KINDS for t in required):
            issues.append({'code': 'shape_coverage_missing', 'component': component, 'action': 'Add a main contour or surface target; dimensions and probes alone do not certify shape.'})
    for feature in features:
        matches = [t for t in required if t.get('featureId') == feature['id']]
        if feature.get('required', True) and not matches:
            issues.append({'code': 'required_feature_missing', 'featureId': feature['id']})
        for target in [t for t in targets if t.get('featureId') == feature['id']]:
            if target.get('component') != feature.get('component') or target.get('scope') != feature.get('scope', feature.get('component')):
                issues.append({'code': 'scope_mismatch', 'featureId': feature['id'], 'action': 'Use the exact reference component scope; do not bind base-inclusive height to shell only.'})
            if target.get('kind') != _KINDS.get(feature.get('kind'), feature.get('kind')):
                issues.append({'code': 'feature_kind_mismatch', 'featureId': feature['id']})
            if target.get('expected') != feature.get('expected', feature.get('geometry', {})):
                issues.append({'code': 'feature_truth_mismatch', 'featureId': feature['id'], 'action': 'Update the reference version explicitly; targets cannot silently replace frozen reference geometry.'})
            declared_tolerance = feature.get('toleranceMetres', feature.get('tolerance_m'))
            if declared_tolerance is not None and target.get('toleranceMetres') != declared_tolerance:
                issues.append({'code': 'feature_tolerance_mismatch', 'featureId': feature['id']})
            certainty = 'exact' if feature.get('evidenceKind') in ('measured', 'user') else 'uncertain'
            if target.get('certainty') != certainty or target.get('evidenceKind') != feature.get('evidenceKind', 'unspecified') or target.get('assumptionAccepted', False) != feature.get('assumptionAccepted', False):
                issues.append({'code': 'feature_evidence_mismatch', 'featureId': feature['id']})
    required_views = reference.get('requiredViewIds', [v['id'] for v in reference.get('views', []) if isinstance(v, dict) and v.get('required')])
    if scope is not None:
        required_views = [view for view in required_views if any(f.get('viewId') == view for f in features)]
    for view in required_views:
        if not any(t.get('viewId') == view for t in required):
            issues.append({'code': 'required_view_missing', 'viewId': view})
    for target in targets:
        tid = target.get('id')
        if not any(f['id'] == target.get('featureId') for f in features):
            issues.append({'code': 'target_feature_outside_scope', 'targetId': tid})
        if target.get('frameId') != reference.get('frameId') or target.get('units') != 'm':
            issues.append({'code': 'frame_or_units_mismatch', 'targetId': tid})
        if target.get('kind') not in _KINDS.values() or not isinstance(target.get('expected'), dict) or not target.get('expected'):
            issues.append({'code': 'target_truth_missing', 'targetId': tid})
        else:
            try: _validate_expected(target['kind'], target['expected'])
            except (ModelingError, KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as error:
                issues.append({'code': 'invalid_target_geometry', 'targetId': tid, 'reason': str(error)})
        if target.get('kind') == 'relative_pose' and (target.get('expected', {}).get('otherComponent') == target.get('component') or target.get('expected', {}).get('otherComponent') not in {f.get('component') for f in _features(reference)}):
            issues.append({'code': 'invalid_relative_component', 'targetId': tid})
        if target.get('certainty') != 'exact' and not target.get('assumptionAccepted'):
            issues.append({'code': 'uncertain_target_not_accepted', 'targetId': tid, 'action': 'Keep the estimate uncertain or explicitly accept and record this modeling assumption.'})
        try:
            number(target.get('toleranceMetres'), 'toleranceMetres', 0, 1000)
        except ModelingError:
            issues.append({'code': 'invalid_tolerance', 'targetId': tid})
    return {'status': 'passed' if not issues else 'incomplete', 'issues': issues,
            'requiredTargets': len(required), 'coverage': 'Declared features and views only; automatic detection of all important visual features is not claimed.'}


def _basis(origin, normal):
    origin = vector(origin, 'plane origin')
    normal = unit(normal, 'plane normal')
    hint = min(((1, 0, 0), (0, 1, 0), (0, 0, 1)), key=lambda a: abs(dot(a, normal)))
    x = unit(cross(hint, normal)); y = cross(normal, x)
    return origin, normal, x, y


def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _point_segment(point, a, b):
    delta = sub(b, a); length = dot(delta, delta)
    t = max(0., min(1., dot(sub(point, a), delta) / length)) if length else 0.
    nearest = add(a, scale(delta, t))
    return magnitude(sub(point, nearest)), nearest


def _inside2(point, loops, tolerance):
    inside = False
    for loop in loops:
        for a, b in zip(loop, loop[1:]):
            if _point_segment(point, a, b)[0] <= tolerance:
                return None
            if (a[1] > point[1]) != (b[1] > point[1]):
                crossing = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                if crossing > point[0]: inside = not inside
    return inside


def _loops_from_segments(segments, tolerance):
    points = {}; neighbors = {}; edges = set()
    for a, b in segments:
        a, b = vector(a), vector(b)
        ka, kb = (tuple(round(x / tolerance) for x in p) for p in (a, b))
        if ka == kb: continue
        edge = tuple(sorted((ka, kb)))
        if edge in edges: continue
        edges.add(edge); points.setdefault(ka, a); points.setdefault(kb, b)
        neighbors.setdefault(ka, set()).add(kb); neighbors.setdefault(kb, set()).add(ka)
    if not edges or any(len(value) != 2 for value in neighbors.values()):
        raise ModelingError('invalid_boundary', 'Section must be nonempty closed nonbranching loops')
    loops = []; unused = set(edges)
    while unused:
        start, current = min(unused); unused.remove(tuple(sorted((start, current))))
        loop = [points[start], points[current]]
        while current != start:
            choices = [n for n in sorted(neighbors[current]) if tuple(sorted((current, n))) in unused]
            if not choices: raise ModelingError('invalid_boundary', 'Boundary traversal did not close')
            following = choices[0]; unused.remove(tuple(sorted((current, following))))
            current = following; loop.append(points[current])
        loops.append(loop)
    return loops


def planar_exterior(section, *, boundary_rule='planar_union', max_edges=1000, max_tests=2000000):
    """Split and classify closed planar polygon edges, retaining union exterior.

Nested loops use even/odd fill per native part, then OR across parts. Shared
internal edges and overlapping interiors are removed. Coplanar slice triangles
are permitted only by the explicit ``cap_boundary`` policy; that result says
nothing about separation normal to the plane.
    """
    if type(max_edges) is not int or not 1 <= max_edges <= _LIMITS['max_union_edges'] or type(max_tests) is not int or not 1 <= max_tests <= _LIMITS['max_union_tests']:
        raise ModelingError('measurement_budget', 'Planar union budget is outside its supported bounds')
    tolerance = number(section.get('weldToleranceMetres', 1e-6), 'weld tolerance', 1e-10, .01)
    origin, normal, x, y = _basis(section['origin'], section['normal'])
    intersecting = [p for p in section.get('parts', []) if p.get('segments') or p.get('loops')]
    if not intersecting: return _incomplete('Required section is empty')
    if any(not p.get('closed') or p.get('openPaths') or p.get('branchVertexCount', 0) for p in intersecting):
        return _incomplete('Required section is open or branching')
    coplanar = sum(p.get('coplanarTriangleCount', 0) for p in intersecting)
    if coplanar and boundary_rule != 'cap_boundary':
        return _incomplete('Coplanar triangles need explicit cap_boundary interpretation or a declared near-plane sample', coplanarTriangleCount=coplanar)
    if boundary_rule not in ('planar_union', 'cap_boundary', 'single_part'):
        return _incomplete('Unsupported boundary rule', boundaryRule=boundary_rule)
    if boundary_rule == 'single_part' and len(intersecting) != 1:
        return _incomplete('single_part cannot select one member of a multi-part component')
    groups = []; edges = []
    for part in intersecting:
        loops = part.get('loops') or _loops_from_segments(part['segments'], tolerance)
        projected = []
        for loop in loops:
            if len(loop) < 4 or magnitude(sub(loop[0], loop[-1])) > tolerance:
                return _incomplete('Section loop is not closed')
            points = []
            for point in loop:
                point = vector(point)
                if abs(dot(sub(point, origin), normal)) > tolerance:
                    return _incomplete('Section points do not share the declared plane')
                points.append((dot(sub(point, origin), x), dot(sub(point, origin), y)))
            projected.append(points)
            edges.extend((a, b) for a, b in zip(points, points[1:]) if magnitude(sub(a, b)) > tolerance)
        groups.append(projected)
    if len(edges) > max_edges: return _incomplete('Planar union edge budget exhausted', edgeCount=len(edges), maximumEdges=max_edges)
    # Split at proper crossings and collinear-overlap endpoints.
    cuts = [{0., 1.} for _ in edges]; tests = 0
    for i, (a, b) in enumerate(edges):
        r = sub(b, a); rr = dot(r, r)
        for j in range(i + 1, len(edges)):
            tests += 1
            if tests > max_tests: return _incomplete('Planar union intersection budget exhausted', boundaryTests=tests, maximumTests=max_tests)
            c, d = edges[j]; s = sub(d, c); ss = dot(s, s); delta = sub(c, a)
            det = _cross2(r, s)
            if abs(det) > tolerance * min(math.sqrt(rr), math.sqrt(ss)):
                t, u = _cross2(delta, s) / det, _cross2(delta, r) / det
                if -1e-10 <= t <= 1 + 1e-10 and -1e-10 <= u <= 1 + 1e-10:
                    cuts[i].add(max(0., min(1., t))); cuts[j].add(max(0., min(1., u)))
            elif abs(_cross2(delta, r)) <= tolerance * math.sqrt(rr):
                for point in (c, d):
                    t = dot(sub(point, a), r) / rr
                    if 0 <= t <= 1: cuts[i].add(t)
                for point in (a, b):
                    t = dot(sub(point, c), s) / ss
                    if 0 <= t <= 1: cuts[j].add(t)
        if sum(len(values) for values in cuts) > max_edges * 8:
            return _incomplete('Planar union split-edge budget exhausted', maximumSplitEdges=max_edges * 8)
    boundary = {}
    def occupancy(point):
        values = [_inside2(point, loops, tolerance / 10) for loops in groups]
        return True if True in values else None if None in values else False
    for (a, b), positions in zip(edges, cuts):
        delta = sub(b, a)
        for lo, hi in zip(sorted(positions), sorted(positions)[1:]):
            start, end = add(a, scale(delta, lo)), add(a, scale(delta, hi))
            length = magnitude(sub(end, start))
            if length <= tolerance: continue
            tests += len(edges) * 3
            if tests > max_tests: return _incomplete('Planar union classification budget exhausted', boundaryTests=tests, maximumTests=max_tests)
            midpoint = scale(add(start, end), .5)
            direction = scale(sub(end, start), 1 / length); perpendicular = (-direction[1], direction[0])
            near = [_point_segment(midpoint, c, d)[0] for c, d in edges]
            if any(tolerance / 10 < distance <= tolerance for distance in near):
                return _incomplete('A feature separation is below the weld resolution; increase native geometric resolution before comparison')
            clearance = min((v for v in near if v > tolerance), default=length)
            epsilon = min(tolerance * 8, clearance / 4, length / 8)
            if epsilon <= tolerance / 2:
                return _incomplete('Boundary separation is below the declared numerical resolution')
            left, right = (occupancy(add(midpoint, scale(perpendicular, sign * epsilon))) for sign in (1, -1))
            if left is None or right is None: return _incomplete('Boundary classification remains numerically ambiguous')
            if left == right: continue
            if not left: start, end = end, start
            key = tuple(sorted(tuple(round(v / tolerance) for v in p) for p in (start, end)))
            boundary[key] = (start, end)
    if not boundary: return _incomplete('Union has no resolved external boundary')
    degree = {}
    for a, b in boundary:
        degree[a] = degree.get(a, 0) + 1; degree[b] = degree.get(b, 0) + 1
    if any(value != 2 for value in degree.values()):
        return _incomplete('Union exterior has point contacts, open edges or branching; no contour certificate')
    segments = [[list(add(origin, add(scale(x, a[0]), scale(y, a[1])))),
                 list(add(origin, add(scale(x, b[0]), scale(y, b[1]))))] for a, b in boundary.values()]
    area = sum(_cross2(a, b) for a, b in boundary.values()) / 2
    return {'status': 'complete', 'segments': segments, 'areaSquareMetres': abs(area), 'boundaryRule': boundary_rule,
            'unionApplied': len(intersecting) > 1, 'partIds': [p.get('partId') for p in intersecting],
            'origin': list(origin), 'normal': list(normal), 'weldToleranceMetres': tolerance,
            'coplanarTriangleCount': coplanar,
            'boundaryTests': tests, 'maximumTests': max_tests,
            'coverage': 'Finite planar polygon exterior at this plane, even/odd per part then union; no 3D surface or normal-gap certificate.'}


def _reference_section(expected):
    segments = expected.get('segments', [])
    tolerance = expected.get('weldToleranceMetres', 1e-6)
    loops = _loops_from_segments(segments, tolerance)
    return {'origin': expected['origin'], 'normal': expected['normal'], 'weldToleranceMetres': tolerance,
            'parts': [{'partId': 'reference', 'segments': segments, 'loops': loops, 'closed': True}]}


def _contour_diagnostics(reference, actual, tolerance, max_tests):
    values = []; witnesses = []; tests = 0
    spacing = max(tolerance / 2, .001)
    for source, target, direction in ((reference, actual, 'referenceToActual'), (actual, reference, 'actualToReference')):
        for a, b in source:
            count = max(1, math.ceil(magnitude(sub(b, a)) / spacing))
            if tests + (count + 1) * len(target) > max_tests:
                return {'status': 'incomplete', 'reason': 'Diagnostic percentile budget exhausted', 'distanceTests': tests}
            for i in range(count + 1):
                point = add(a, scale(sub(b, a), i / count))
                distance, nearest = min((_point_segment(point, c, d) for c, d in target), key=lambda item: item[0])
                tests += len(target); values.append(distance)
                witnesses.append((distance, direction, point, nearest))
    values.sort(); worst = sorted(witnesses, key=lambda item: item[0], reverse=True)[:8]
    return {'status': 'complete', 'sampledP95Metres': values[max(0, math.ceil(.95 * len(values)) - 1)],
            'sampledMaximumMetres': values[-1], 'distanceTests': tests, 'sampleCount': len(values),
            'percentileDefinition': 'Nearest-rank p95 of equally spaced per-segment samples in both directions, including endpoints; diagnostic, not a certified surface percentile.',
            'worstResiduals': [{'distanceMetres': d, 'direction': direction, 'point': list(p), 'nearest': list(q),
                                'suggestedActualDeltaMetres': list(sub(p, q) if direction == 'referenceToActual' else sub(q, p)),
                                'suggestionMeaning': 'Local residual direction; not an optimal parameter update.'} for d, direction, p, q in worst]}


def _triangles(mesh):
    by_part = {}
    for row in mesh.meshes:
        by_part.setdefault(row['partId'], []).extend(tuple(row['vertices'][row['indices'][i + j]] for j in range(3)) for i in range(0, len(row['indices']), 3))
    return by_part


def _section(mesh, expected, budget):
    section = mesh.section(expected['origin'], expected['normal'], weld_tolerance_m=expected.get('weldToleranceMetres', 1e-6))
    result = planar_exterior(section, boundary_rule=expected.get('boundaryRule', 'planar_union'), max_edges=budget['max_union_edges'], max_tests=budget['max_union_tests'])
    if expected.get('nearPlane'):
        near = expected['nearPlane']
        result['nearPlane'] = deepcopy(near)
        if 'offsetMetres' not in near or 'referenceOrigin' not in near or 'maximumVariationMetres' not in near:
            return _incomplete('Near-plane interpretation needs offsetMetres, referenceOrigin and maximumVariationMetres')
        offset = number(near['offsetMetres'], 'near plane offset')
        expected_origin = add(vector(near['referenceOrigin']), scale(unit(expected['normal']), offset))
        if magnitude(sub(expected_origin, expected['origin'])) > 1e-7:
            return _incomplete('Near-plane origin is inconsistent with the declared offset')
        result['nearPlaneMeaning'] = 'Scoped offset-plane comparison only. Maximum variation is a declared bound, not a measured interface-gap certificate.'
    return result


def _evaluate(target, meshes, budget):
    mesh = meshes.get(target['component'])
    if not isinstance(mesh, MeshEvidence) or not mesh.meshes:
        return _incomplete('Required component has no captured indexed mesh')
    if mesh.sample.get('exclusions'):
        return _incomplete('Capture excludes required native geometry', exclusions=deepcopy(mesh.sample['exclusions']))
    expected = target['expected']; kind = target['kind']; tolerance = target['toleranceMetres']
    points = [p for row in mesh.meshes for p in row['vertices']]
    if not points: return _incomplete('Native vertex evidence is empty')
    if kind in ('section_contour', 'section_center', 'section_boundary'):
        boundary = _section(mesh, expected, budget)
        if boundary['status'] != 'complete': return boundary
        actual = boundary['segments']; vertices = [p for row in actual for p in row]
        if kind == 'section_center':
            if expected.get('definition') != 'boundary_bbox':
                return _incomplete('Section center requires an explicit boundary_bbox definition; centroid and design-origin are not interchangeable')
            origin, normal, x, y = _basis(expected['origin'], expected['normal'])
            center = origin
            for axis in (x, y):
                values = [dot(sub(p, origin), axis) for p in vertices]
                center = add(center, scale(axis, (max(values) + min(values)) / 2))
            error = magnitude(sub(center, vector(expected['center'])))
            return {'status': 'passed' if error <= tolerance else 'failed', 'errorMetres': error, 'actualCenterMetres': list(center),
                    'suggestedDeltaMetres': list(sub(expected['center'], center)), 'boundary': boundary,
                    'coverage': 'Center of this complete planar boundary projected bounding box; not mass centroid.'}
        if kind == 'section_boundary':
            axis = unit(expected['axis']); values = [dot(p, axis) for p in vertices]
            actual_value = min(values) if expected.get('side') == 'min' else max(values) if expected.get('side') == 'max' else None
            if actual_value is None: return _incomplete('Boundary side must be min or max')
            delta = number(expected['valueMetres'], 'boundary coordinate') - actual_value
            return {'status': 'passed' if abs(delta) <= tolerance else 'failed', 'actualMetres': actual_value, 'errorMetres': abs(delta),
                    'suggestedDeltaMetres': list(scale(axis, delta)), 'boundary': boundary, 'coverage': 'Declared extremal boundary at one plane.'}
        reference_section = _reference_section(expected)
        ref = planar_exterior(reference_section, max_edges=budget['max_union_edges'], max_tests=budget['max_union_tests'])
        if ref['status'] != 'complete': return _incomplete('Reference contour is unresolved', referenceBoundary=ref)
        result = compare_contours(ref['segments'], actual, tolerance_m=tolerance,
                                  sample_spacing_m=max(tolerance / 4, 1e-6), max_samples=budget['max_contour_samples'])
        numerical_bound = 4 * (ref['weldToleranceMetres'] + boundary['weldToleranceMetres'])
        result['sectionNumericalAllowanceMetres'] = numerical_bound
        result['lowerBoundMetres'] = max(0., result['sampledMaximumMetres'] - numerical_bound)
        result['upperBoundMetres'] += numerical_bound
        result['status'] = 'passed' if result['upperBoundMetres'] <= tolerance else 'failed' if result['lowerBoundMetres'] > tolerance else 'incomplete'
        combined = deepcopy(reference_section)
        combined['parts'].append({'partId': 'actual-exterior', 'closed': True, 'segments': actual, 'loops': _loops_from_segments(actual, boundary['weldToleranceMetres'])})
        union = planar_exterior(combined, max_edges=budget['max_union_edges'], max_tests=budget['max_union_tests'])
        if union['status'] == 'complete' and union['areaSquareMetres'] > 0:
            intersection = ref['areaSquareMetres'] + boundary['areaSquareMetres'] - union['areaSquareMetres']
            result['planarIoU'] = max(0., min(1., intersection / union['areaSquareMetres']))
            result['iouMeaning'] = 'Intersection/union area of supplied filled plane sections; not a fidelity percentage or whole-model score.'
        else: result['iouStatus'] = 'incomplete'
        result.update(boundary=boundary, referenceBoundary=ref,
                      diagnostics=_contour_diagnostics(ref['segments'], actual, tolerance, budget['max_diagnostic_tests']))
        if result['status'] == 'passed' and (union['status'] != 'complete' or result['diagnostics']['status'] != 'complete'):
            result.update(status='incomplete', reason='Required contour diagnostics or filled-area comparison could not complete within the declared budget')
        return result
    if kind == 'mesh_extent':
        values = [dot(p, unit(expected['axis'])) for p in points]; actual = max(values) - min(values)
        error = abs(actual - number(expected.get('valueMetres', expected.get('value_m')), 'extent'))
        return {'status': 'passed' if error <= tolerance else 'failed', 'actualMetres': actual, 'errorMetres': error, 'coverage': 'Vertex extent only; does not certify shape.'}
    if kind == 'negative_space':
        parts = _triangles(mesh)
        if any(not closed_mesh(rows) for rows in parts.values()):
            return _incomplete('Negative-space probes need individually closed native part surfaces')
        probes = expected.get('probes', [])
        if not isinstance(probes, list) or not probes or len(probes) > 1000:
            return _incomplete('Declare 1..1000 negative-space probe points')
        triangle_tests = sum(len(rows) for rows in parts.values()) * len(probes) * 3
        if triangle_tests > budget['max_triangle_tests']:
            return _incomplete('Negative-space occupancy budget exhausted before ray evaluation', requiredTriangleTests=triangle_tests, maximumTriangleTests=budget['max_triangle_tests'])
        rows = []
        for value in probes:
            point = vector(value['point'] if isinstance(value, dict) else value)
            occupancy = [point_inside(tri, point) for tri in parts.values()]
            actual = True if True in occupancy else None if None in occupancy else False
            rows.append({'point': list(point), 'actualInside': actual, 'status': 'incomplete' if actual is None else 'failed' if actual else 'passed'})
        status = 'failed' if any(r['status'] == 'failed' for r in rows) else 'incomplete' if any(r['status'] == 'incomplete' for r in rows) else 'passed'
        return {'status': status, 'probes': rows, 'boundaryRule': 'union_occupancy_of_individually_closed_parts',
                'coverage': 'Only the declared void probes, not all volume between them. Pair with required contours for shape acceptance.'}
    if kind == 'relative_pose':
        other = meshes.get(expected.get('otherComponent'))
        if not isinstance(other, MeshEvidence) or other.sample.get('exclusions'): return _incomplete('Other relative-pose component evidence is missing or excluded')
        if expected.get('anchor') != 'mesh_bbox_center':
            return _incomplete('Declare mesh_bbox_center anchors; native part origins need the pose evaluator')
        def center(value):
            points = [p for row in value.meshes for p in row['vertices']]
            if not points: raise ModelingError('empty_mesh', 'Relative anchor mesh is empty')
            return tuple((min(p[i] for p in points) + max(p[i] for p in points)) / 2 for i in range(3))
        actual = sub(center(mesh), center(other)); delta = sub(vector(expected['deltaMetres']), actual); error = magnitude(delta)
        return {'status': 'passed' if error <= tolerance else 'failed', 'errorMetres': error,
                'actualDeltaMetres': list(actual), 'suggestedDeltaMetres': list(delta), 'coverage': 'Component minus otherComponent bounding-box anchor displacement; no rotation certificate.'}
    if kind == 'surface':
        parts = _triangles(mesh)
        if len(parts) != 1:
            return _incomplete('3D exterior union is unsupported; use explicit planar exterior checks or separate declared non-overlapping surface components', boundaryRule=expected.get('boundaryRule', 'unresolved'))
        actual = next(iter(parts.values()))
        return compare_surfaces(expected.get('triangles', []), actual, tolerance_m=tolerance,
                                max_samples=budget['max_surface_samples'], max_triangle_tests=budget['max_triangle_tests'])
    if kind == 'visual':
        return {'status': 'not_assessed', 'reason': 'Generated or captured image paths do not prove viewing or visual assessment.'}
    return _incomplete('Unsupported feature evaluator', kind=kind)


def compare_model(reference, contract, evidence, *, candidate_id, budget=None):
    """Compare exact component meshes in one task frame. No best-fit alignment.

evidence = {frameId, components: {component: MeshEvidence}, identity?}.
For native acceptance prefer measure_candidate(), which captures and freshness
checks all bindings. Offline supplied meshes remain explicitly unverified.
    """
    limits = _budget(budget)
    if contract.get('targetHash') != _target_hash(contract):
        raise ModelingError('contract_changed', 'Comparison targets changed; explicitly review a new version before checking')
    if any(contract.get(key) != value for key, value in _stamp(reference).items()):
        raise ModelingError('reference_changed', 'Targets belong to another reference version or frame')
    if evidence.get('frameId') != reference.get('frameId'):
        raise ModelingError('frame_mismatch', 'Native evidence must use the frozen task frame; per-part fitting is forbidden')
    coverage = validate_coverage(reference, contract)
    targets = contract['targets']
    if len(targets) > limits['max_targets']: raise ModelingError('measurement_budget', 'Target count exceeds the frozen measurement budget')
    meshes = evidence.get('components', {})
    frames = [mesh.frame.to_dict() for mesh in meshes.values() if isinstance(mesh, MeshEvidence)]
    if frames and any(frame != frames[0] for frame in frames):
        raise ModelingError('frame_mismatch', 'All native components must use one common frame')
    identity = evidence.get('identity')
    if identity is None:
        identity = next((mesh.identity for mesh in meshes.values() if isinstance(mesh, MeshEvidence)), None)
    if identity is not None and any(not same_identity(mesh.identity, identity) for mesh in meshes.values() if isinstance(mesh, MeshEvidence)):
        raise ModelingError('stale_evidence', 'Component captures have different native identities')
    results = []
    for target in targets:
        try: measured = _evaluate(target, meshes, limits)
        except (ModelingError, KeyError, TypeError, ValueError, IndexError) as error:
            measured = _incomplete('Measurement could not evaluate its declared target', error=error.to_dict() if isinstance(error, ModelingError) else {'code': 'invalid_target', 'message': str(error)})
        results.append({'targetId': target['id'], 'featureId': target['featureId'], 'component': target['component'],
                        'kind': target['kind'], 'required': target['required'], 'priority': target['priority'],
                        'viewId': target.get('viewId'), 'toleranceMetres': target['toleranceMetres'],
                        'adjustableParameters': deepcopy(target.get('parameters', [])), **measured})
    required = [row for row in results if row['required']]
    status = 'failed' if any(row['status'] == 'failed' for row in required) else 'incomplete' if coverage['status'] != 'passed' or not required or any(row['status'] != 'passed' for row in required) else 'passed'
    residuals = sorted(({'featureId': row['featureId'], 'component': row['component'], 'viewId': row['viewId'],
                         'status': row['status'], 'priority': row['priority'], 'parameters': row['adjustableParameters'],
                         'errorMetres': row.get('errorMetres', row.get('sampledMaximumMetres')),
                         'suggestedDeltaMetres': row.get('suggestedDeltaMetres'),
                         'localResiduals': row.get('diagnostics', {}).get('worstResiduals', []),
                         'nextAction': 'Inspect this feature and its declared parameters; suggestions are local heuristics, not a proven optimal edit.' if row['status'] == 'failed' else 'Supply or repair the stated evidence before editing.'}
                        for row in results if row['required'] and row['status'] != 'passed'),
                       key=lambda row: (str(row['priority']), -(row['errorMetres'] or 0)))
    return {'schemaVersion': 'sp2model.comparison/1', **_stamp(reference), 'candidateId': candidate_id,
            'targetHash': contract['targetHash'], 'status': status, 'coverage': coverage,
            'results': results, 'residuals': residuals, 'budget': limits, 'identity': deepcopy(identity),
            'nativeArtifactVerified': bool(meshes) and all(isinstance(m, MeshEvidence) and m._artifact_verified for m in meshes.values()),
            'evidence': {name: mesh.to_dict() for name, mesh in meshes.items() if isinstance(mesh, MeshEvidence)},
            'visual': {'generated': False, 'provided': False, 'viewed': 'not_observed', 'assessment': 'not_assessed'},
            'stopReason': 'within_tolerance' if status == 'passed' else 'measurement_invalid' if status == 'incomplete' else None,
            'meaning': 'All required checks must pass. Passing supplied geometry is not native verification without verified captures; no inference of unseen shape or image understanding.'}


def measure_candidate(session, bindings, reference, contract, *, candidate_id, native_frame=None, budget=None):
    """Read-only native convenience wrapper; bindings map semantic names to refs.

native_frame maps task coordinates to native world and must be common to every
component. It is separate from reference.frame (source-to-task). Captures are
fenced against one current native identity; mutations require a new check.
    """
    native_frame = native_frame or Frame.world()
    identity = deepcopy(session.identity); meshes = {}
    for name, parts in bindings.items():
        parts = list(parts); ids = {session._resolve_ref(p) for p in parts}
        mesh = session.mesh(parts, frame=native_frame)
        if {row['partId'] for row in mesh.meshes} != ids:
            raise ModelingError('component_coverage', 'Captured geometry does not cover exactly the declared native members', {'component': name})
        if not mesh._artifact_verified or not same_identity(identity, mesh.identity):
            raise ModelingError('stale_evidence', 'Capture changed identity or lacks verified artifact provenance')
        if mesh.frame.to_dict() != native_frame.to_dict():
            raise ModelingError('frame_mismatch', 'Native capture ignored the common requested task frame')
        meshes[name] = mesh
    session._fresh(identity)
    report = compare_model(reference, contract, {'frameId': reference['frameId'], 'components': meshes, 'identity': identity}, candidate_id=candidate_id, budget=budget)
    session._fresh(identity)
    return report


def compare_progress(previous, current, *, minimum_improvement_m=.001):
    """Per-feature changes; one improved view never erases another regression."""
    threshold = number(minimum_improvement_m, 'minimum improvement', 0)
    if previous is None:
        return {'comparablePriorIteration': False, 'significantImprovement': False, 'metricDifferences': [],
                'regressedRequiredFeatureIds': [], 'reason': 'No previous measured iteration'}
    keys = ('referenceId', 'referenceVersion', 'referenceContentHash', 'frameId', 'targetHash')
    if any(previous.get(key) != current.get(key) for key in keys):
        raise ModelingError('comparison_contract_changed', 'Progress requires the same reference version, frame and target contract; amendments start a separate evaluation')
    old = {row['targetId']: row for row in previous.get('results', []) if row.get('required')}
    new = {row['targetId']: row for row in current.get('results', []) if row.get('required')}
    if not old or set(old) != set(new):
        return {'comparablePriorIteration': False, 'significantImprovement': False, 'metricDifferences': [],
                'regressedRequiredFeatureIds': [], 'reason': 'Required feature coverage differs or is empty'}
    differences = []; regressions = []; unknown = []
    for identifier, after in new.items():
        before = old[identifier]
        def error(row):
            value = row.get('errorMetres', row.get('upperBoundMetres'))
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None
        first, second = error(before), error(after)
        improvement = None if first is None or second is None else first - second
        regression = (before.get('status') == 'passed' and after.get('status') != 'passed') or (improvement is not None and improvement < -threshold)
        if regression: regressions.append(after['featureId'])
        if after.get('status') not in ('passed', 'failed'): unknown.append(after['featureId'])
        differences.append({'targetId': identifier, 'featureId': after['featureId'], 'viewId': after.get('viewId'),
                            'priority': after.get('priority'), 'beforeStatus': before.get('status'), 'afterStatus': after.get('status'),
                            'beforeMetres': first, 'afterMetres': second, 'improvementMetres': improvement,
                            'significant': (improvement is not None and improvement >= threshold) or
                                           (before.get('status') != 'passed' and after.get('status') == 'passed'),
                            'regressed': regression})
    return {'comparablePriorIteration': True, 'metricDifferences': differences,
            'regressedRequiredFeatureIds': regressions, 'unresolvedRequiredFeatureIds': unknown,
            'minimumImprovementMetres': threshold,
            'significantImprovement': any(row['significant'] for row in differences) and not regressions and not unknown,
            'meaning': 'Per-feature conservative errors/statuses in one frozen evaluation; an average or IoU gain cannot cancel a required-feature regression.'}


def convergence_review(reports, *, minimum_improvement_m=.001, stagnation_window=3):
    """Read-only stop advice and best evidence index, never an automatic restore."""
    if type(stagnation_window) is not int or not 2 <= stagnation_window <= 100:
        raise ModelingError('invalid_input', 'stagnation_window must be an integer in [2,100]')
    if not isinstance(reports, list) or not reports:
        return {'status': 'incomplete', 'stopReason': 'measurement_invalid', 'reason': 'No measured iterations'}
    comparisons = [compare_progress(a, b, minimum_improvement_m=minimum_improvement_m) for a, b in zip(reports, reports[1:])]
    def score(report):
        rows = [row for row in report.get('results', []) if row.get('required')]
        values = []
        for priority in sorted({str(row.get('priority', 'P0')) for row in rows}):
            group = [row for row in rows if str(row.get('priority', 'P0')) == priority]
            unresolved = sum(row.get('status') not in ('passed', 'failed') for row in group)
            failed = sum(row.get('status') == 'failed' for row in group)
            errors = [row.get('errorMetres', row.get('upperBoundMetres', math.inf)) for row in group]
            worst = max((value if isinstance(value, (int, float)) and math.isfinite(value) else math.inf for value in errors), default=math.inf)
            values.extend((unresolved, failed, worst))
        return (not bool(rows), *values)
    best_index = min(range(len(reports)), key=lambda index: score(reports[index]))
    current = reports[-1]
    recent = comparisons[-stagnation_window:]
    stagnant = len(recent) == stagnation_window and all(row['comparablePriorIteration'] and not row['significantImprovement'] for row in recent)
    reason = 'within_tolerance' if current.get('status') == 'passed' else 'measurement_invalid' if current.get('status') == 'incomplete' else 'stagnation' if stagnant else None
    best = reports[best_index]
    return {'status': 'reviewed', 'stopReason': reason, 'comparisons': comparisons,
            'stagnationWindow': stagnation_window, 'bestEvidenceIndex': best_index,
            'bestCandidateId': best.get('candidateId'), 'bestEvidenceIdentity': deepcopy(best.get('identity')),
            'nextFeatures': deepcopy(current.get('residuals', [])[:5]),
            'restoreAvailable': False,
            'meaning': 'Best measured evidence is ranked by frozen priority, unresolved/failed counts and worst conservative error. This is not a checkpoint; only an explicitly retained native version can be restored.'}


def render_overlay(report, path):
    """Write same-frame SVG contour overlays; generation is not visual approval."""
    rows = [row for row in report.get('results', []) if row.get('boundary', {}).get('segments') and row.get('referenceBoundary', {}).get('segments')]
    if not rows: return _incomplete('No complete contour pairs available for an overlay')
    panels = []; width = 800; height = 420 * len(rows)
    for index, row in enumerate(rows):
        actual = row['boundary']; reference = row['referenceBoundary']
        origin, normal, x, y = _basis(actual['origin'], actual['normal'])
        def project(point): return (dot(sub(point, origin), x), dot(sub(point, origin), y))
        values = [project(p) for segments in (reference['segments'], actual['segments']) for segment in segments for p in segment]
        lo = [min(p[i] for p in values) for i in (0, 1)]; hi = [max(p[i] for p in values) for i in (0, 1)]
        factor = min(720 / max(hi[0] - lo[0], .001), 320 / max(hi[1] - lo[1], .001))
        def pixels(point):
            a, b = project(point)
            return 40 + (a - lo[0]) * factor, index * 420 + 370 - (b - lo[1]) * factor
        title = html.escape(f"{row['featureId']} | {row.get('viewId')} | {row['status']} | frame {report.get('frameId')} | ref {report.get('referenceId')} v{report.get('referenceVersion')} | candidate {report.get('candidateId')}")
        panels.append(f'<text x="20" y="{index * 420 + 25}" font-size="13">{title}</text>')
        panels.append(f'<text x="20" y="{index * 420 + 45}" font-size="12">Reference blue; actual orange. Same plane and scale. No alignment fit.</text>')
        for segments, color in ((reference['segments'], '#1269d3'), (actual['segments'], '#de6c12')):
            for a, b in segments:
                a, b = pixels(a), pixels(b)
                panels.append(f'<line x1="{a[0]:.5f}" y1="{a[1]:.5f}" x2="{b[0]:.5f}" y2="{b[1]:.5f}" stroke="{color}" stroke-width="1.6"/>')
        panels.append(f'<text x="20" y="{index * 420 + 405}" font-size="12">Scale: {factor:.4f} pixels/metre; axis x={html.escape(str(x))}, y={html.escape(str(y))}</text>')
    payload = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>{"".join(panels)}</svg>'
    path = Path(path).resolve(); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(payload, encoding='utf-8')
    return {'status': 'generated', 'path': str(path), 'sha256': hashlib.sha256(payload.encode()).hexdigest(),
            'referenceId': report.get('referenceId'), 'candidateId': report.get('candidateId'), 'frameId': report.get('frameId'),
            'viewIds': [row['viewId'] for row in rows], 'provided': False, 'viewed': 'not_observed', 'assessment': 'not_assessed'}


def render_overlay_png(report, path):
    """Raster plot for image-capable Agents using the bundled stdlib PNG writer.

At most six 900x420 panels share a file. Larger reports produce numbered sheets,
retaining all contour views. Each panel projects both contours through exactly
one plane basis, bounding region and scale. Text is an ASCII bitmap legend; full
Unicode identities and axis definitions remain in returned metadata/SVG.
    """
    from ._services.part_observation import _png, _line, _label
    rows = [row for row in report.get('results', []) if row.get('boundary', {}).get('segments') and row.get('referenceBoundary', {}).get('segments')]
    if not rows: return _incomplete('No complete contour pairs available for a PNG overlay')
    if len(rows) > _LIMITS['max_targets']: return _incomplete('PNG view budget exceeded')
    panels = []
    try:
        for row in rows:
            actual, reference = row['boundary'], row['referenceBoundary']
            origin, normal, x, y = _basis(actual['origin'], actual['normal'])
            if abs(dot(normal, unit(reference['normal']))) < 1 - 1e-8:
                return _incomplete('Reference and actual contours do not share one plane normal')
            projected = []
            for boundary in (reference, actual):
                lines = []
                for segment in boundary['segments']:
                    ends = []
                    for point in segment:
                        point = vector(point)
                        if abs(dot(sub(point, origin), normal)) > max(actual.get('weldToleranceMetres', 1e-6), reference.get('weldToleranceMetres', 1e-6)):
                            return _incomplete('Reference and actual contours do not share one frozen plane')
                        value = (dot(sub(point, origin), x), dot(sub(point, origin), y))
                        if not all(math.isfinite(v) for v in value): return _incomplete('Contour projection exceeds finite numeric range')
                        ends.append(value)
                    lines.append(ends)
                projected.append(lines)
            points = [p for lines in projected for line in lines for p in line]
            low = [min(p[i] for p in points) for i in (0, 1)]; high = [max(p[i] for p in points) for i in (0, 1)]
            factor = min(800 / max(high[0] - low[0], .001), 300 / max(high[1] - low[1], .001))
            if not math.isfinite(factor) or factor <= 0: return _incomplete('Contour extent cannot be plotted at a finite common scale')
            panels.append({'row': row, 'projected': projected, 'low': low, 'high': high, 'factor': factor,
                           'basis': {'origin': list(origin), 'horizontalAxis': list(x), 'verticalAxis': list(y)}})
    except (ModelingError, KeyError, TypeError, ValueError, OverflowError) as error:
        return _incomplete('Invalid contour data for PNG overlay', detail=str(error))
    path = Path(path).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    files = []; pages = math.ceil(len(panels) / 6); width = 900
    for page in range(pages):
        selected = panels[page * 6:page * 6 + 6]; height = len(selected) * 420
        pixels = bytearray([255] * (width * height * 3)); metadata = []
        for index, panel in enumerate(selected):
            row = panel['row']; low, factor = panel['low'], panel['factor']
            title = f"{row['featureId']} | {row.get('viewId')} | {row['status']}"
            _label(pixels, width, height, title[:105], 20, index * 420 + 15, (35, 35, 35), scale=2)
            _label(pixels, width, height, 'REF BLUE / ACTUAL ORANGE - SAME PLANE AND SCALE', 20, index * 420 + 35, (55, 55, 55), scale=2)
            def pixel(point): return (50 + (point[0] - low[0]) * factor, index * 420 + 365 - (point[1] - low[1]) * factor)
            for lines, color in zip(panel['projected'], ((18, 105, 211), (222, 108, 18))):
                for start, end in lines: _line(pixels, width, height, pixel(start), pixel(end), color)
            _label(pixels, width, height, f"{factor:.3f} PX/M - NO ALIGNMENT FIT - NUMERIC GEOMETRY PLOT", 20, index * 420 + 390, (45, 45, 45), scale=2)
            metadata.append({'featureId': row['featureId'], 'viewId': row.get('viewId'), 'status': row['status'],
                             'panelPixels': [0, index * 420, width, 420], 'pixelsPerMetre': factor,
                             'projectedBoundsMetres': {'min': panel['low'], 'max': panel['high']}, **panel['basis']})
        destination = path if pages == 1 else path.with_name(f'{path.stem}-{page + 1:02d}.png')
        _png(destination, width, height, pixels)
        files.append({'path': str(destination), 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                      'width': width, 'height': height, 'panels': metadata})
    return {'status': 'generated', 'path': files[0]['path'], 'files': files,
            'referenceId': report.get('referenceId'), 'referenceVersion': report.get('referenceVersion'),
            'candidateId': report.get('candidateId'), 'frameId': report.get('frameId'),
            'legend': {'reference': '#1269d3', 'actual': '#de6c12'},
            'provided': False, 'viewed': 'not_observed', 'assessment': 'not_assessed',
            'meaning': 'Orthographic contour comparison plots, not game screenshots, visibility or appearance certification.'}
