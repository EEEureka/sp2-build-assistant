"""Finite-domain boundary and reference review of real captured triangles.

The certificates below bound every point of an explicitly selected polygonal
domain. They never extrapolate to a smooth underlying surface, omitted meshes,
native paint, or the rest of a craft. Distance to a closed set is 1-Lipschitz;
distance to each individual triangle/segment is convex. Both facts give safe
upper bounds when nearest primitives switch between samples (the usual hole in
endpoint-only tests). All work, including rejected candidates, has a budget.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .reference_storage import ReferenceError, digest
from .regional_geometry import (WORLD, EPS, _document, _number, _integer, _ids,
    _vec, add, sub, mul, dot, norm, normal, bounds, bounds_distance,
    point_segment, point_triangle, segment_segment, section, _evidence)


class WorkBudget:
    def __init__(self, maximum=100000):
        self.maximum = _integer(maximum, 'maxBoundaryDistanceTests', 1)
        if self.maximum > 5000000:
            raise ReferenceError('invalid_input', 'Boundary distance budget exceeds 5000000')
        self.used = 0

    def charge(self, count=1):
        if self.used+count > self.maximum:
            return False
        self.used += count
        return True


def edge_inventory(triangles, part_id=0, max_edges=100000, weld_tolerance=1e-7,
                   crease_degrees=1.):
    """Enumerate *all* welded triangle edges, retaining actual endpoints/faces."""
    max_edges = _integer(max_edges, 'maxBoundaryEdges', 1)
    if max_edges > 1000000:
        raise ReferenceError('invalid_input', 'Boundary edge budget exceeds 1000000')
    weld_tolerance = _number(weld_tolerance, 'weldToleranceM', EPS)
    key = lambda p: tuple(round(x/weld_tolerance) for x in p)
    table = {}; unfinished = 0
    for index, tri in enumerate(triangles):
        for a, b in zip(tri, (tri[1], tri[2], tri[0])):
            ka, kb = key(a), key(b)
            if ka == kb: continue
            k = tuple(sorted((ka, kb)))
            if k not in table:
                if len(table) >= max_edges:
                    unfinished += 1
                    continue
                table[k] = {'a': list(a), 'b': list(b), 'incidentTriangles': [],
                            'normals': [], 'endpointWeldKeys': [ka, kb]}
            table[k]['incidentTriangles'].append(index)
            n = normal(tri)
            if n is not None: table[k]['normals'].append(list(n))
    edges = []
    vertices = {}
    for index, (key_value, item) in enumerate(sorted(table.items())):
        ns = item['normals']
        angle = max((math.degrees(math.acos(max(-1., min(1., dot(a, b)))))
                     for a in ns for b in ns), default=0.)
        count = len(item['incidentTriangles'])
        item.update(id='p'+str(part_id)+'-e'+str(index), partId=part_id,
                    lengthM=norm(sub(item['a'], item['b'])), normalAngleDegrees=angle,
                    kind='open_boundary' if count == 1 else 'non_manifold' if count > 2
                    else 'crease_edge' if angle > crease_degrees else 'triangulation_edge')
        edges.append(item)
        for p, k in zip((item['a'], item['b']), item['endpointWeldKeys']):
            vertices.setdefault(tuple(k), {'pointWorld': p, 'incidentEdgeIds': [], 'kinds': set()})
            vertices[tuple(k)]['incidentEdgeIds'].append(item['id'])
            vertices[tuple(k)]['kinds'].add(item['kind'])
    bs = bounds(triangles)
    extrema = []
    for v in vertices.values():
        reasons = []
        for axis in range(3):
            if bs and abs(v['pointWorld'][axis]-bs['min'][axis]) <= weld_tolerance:
                reasons.append({'kind': 'coordinate_minimum', 'axis': axis})
            if bs and abs(v['pointWorld'][axis]-bs['max'][axis]) <= weld_tolerance:
                reasons.append({'kind': 'coordinate_maximum', 'axis': axis})
        if 'crease_edge' in v['kinds']: reasons.append({'kind': 'piecewise_normal_change'})
        if len(v['incidentEdgeIds']) == 1: reasons.append({'kind': 'boundary_endpoint'})
        if reasons:
            extrema.append({'pointWorld': v['pointWorld'], 'incidentEdgeIds': v['incidentEdgeIds'], 'reasons': reasons})
    return {'partId': part_id, 'edges': edges, 'criticalVertices': extrema,
            'coverage': {'status': 'complete' if not unfinished else 'incomplete',
                         'mode': 'all_captured_triangle_edges', 'edgeCount': len(edges),
                         'unprocessedEdgeOccurrences': unfinished,
                         'weldToleranceM': weld_tolerance},
            'limitations': ['Complete means the finite captured triangle mesh only.',
                            'Creases/open edges can be intentional; topology alone does not justify removal.']}


def event_stations(triangles, axis=2, max_stations=128):
    """Every vertex event and one independent interior of every event interval.

    For a finite triangle mesh the intersection primitives change only at vertex
    coordinate events. Interiors are useful independent observations, not a
    certificate of distances between stations. The continuous certificate is
    computed separately on the full segment/triangle domain.
    """
    axis = _integer(axis, 'sectionAxis')
    if axis > 2: raise ReferenceError('invalid_input', 'sectionAxis must be 0..2')
    maximum = _integer(max_stations, 'maxAutomaticStations', 1)
    if maximum > 4096: raise ReferenceError('invalid_input', 'Automatic station budget exceeds 4096')
    coords = sorted({p[axis] for tri in triangles for p in tri})
    rows = [{'stationM': x, 'selection': 'all_vertex_events_including_endpoints_extrema_and_normal_changes'} for x in coords]
    rows += [{'stationM': (a+b)/2, 'selection': 'independent_event_interval_interior'}
             for a, b in zip(coords, coords[1:]) if b-a > EPS]
    rows.sort(key=lambda x: x['stationM'])
    # Preserve endpoints, the global middle, and then distribute budget over the
    # entire extent. Missing rows stay explicit (never silently keep the front).
    if len(rows) <= maximum: selected, excluded = rows, []
    else:
        indices = {round(i*(len(rows)-1)/(maximum-1)) for i in range(maximum)} if maximum > 1 else {len(rows)//2}
        selected = [r for i, r in enumerate(rows) if i in indices]
        excluded = [r for i, r in enumerate(rows) if i not in indices]
    return {'stations': selected, 'uncoveredStations': excluded,
            'coverage': {'status': 'complete' if not excluded else 'incomplete',
                         'requiredStationCount': len(rows), 'selectedStationCount': len(selected),
                         'basis': 'all_finite_mesh_vertex_events_and_each_independent_interval_interior'}}


def _primitive_distance(point, primitive):
    if len(primitive) == 2:
        q = point_segment(point, *primitive)
        return norm(sub(point, q)), q
    # Use strict barycentric containment for certificates. The regional
    # discovery helper deliberately tolerates near-edge coordinates, which can
    # understate distance by edge_length*epsilon on large triangles.
    a, b, c = primitive
    ab, ac = sub(b, a), sub(c, a); n = normal(primitive)
    candidates = [point_segment(point, x, y) for x, y in ((a, b), (b, c), (c, a))]
    if n is not None:
        q = sub(point, mul(n, dot(sub(point, a), n))); aq = sub(q, a)
        aa, bb, cc = dot(ab, ab), dot(ab, ac), dot(ac, ac); determinant = aa*cc-bb*bb
        if determinant > EPS**4:
            u = (cc*dot(aq, ab)-bb*dot(aq, ac))/determinant
            v = (aa*dot(aq, ac)-bb*dot(aq, ab))/determinant
            if u >= 0 and v >= 0 and u+v <= 1: candidates.append(q)
    q = min(candidates, key=lambda p: norm(sub(point, p)))
    return norm(sub(point, q)), q


def directed_certificate(domains, targets, tolerance, budget=None, max_depth=18,
                         precision=1e-7):
    """Conservative directed Hausdorff bound over complete segment/triangle cells.

    ``upperBoundM`` is valid for the ENTIRE input domain only when complete=True.
    A failed sampled witness proves failure even if other cells are unmeasured.
    No nearest-vertex-only result is ever promoted to complete.
    """
    tolerance = _number(tolerance, 'distanceToleranceM')
    precision = _number(precision, 'certificatePrecisionM', EPS)
    budget = budget or WorkBudget()
    max_depth = _integer(max_depth, 'maxBoundarySubdivisionDepth')
    if max_depth > 30: raise ReferenceError('invalid_input', 'Subdivision depth exceeds 30')
    if not domains or not targets:
        return {'status': 'missing_evidence', 'complete': False, 'reason': 'Source or target domain is empty',
                'upperBoundM': None, 'lowerBoundM': None, 'uncoveredCellCount': len(domains)}
    if any(len(cell) not in (2, 3) for cell in domains) or any(len(cell) not in (2, 3) for cell in targets):
        raise ReferenceError('invalid_input', 'Certificates require finite line segments or triangles')
    # IEEE roundoff is explicitly separated from the geometric tolerance. This
    # guard scales with coordinates/extent, rather than pretending float-based
    # geometry is an exact symbolic proof at any model scale.
    magnitude = max((abs(x) for cell in list(domains)+list(targets) for p in cell for x in p), default=1.)
    roundoff = max(EPS*4, magnitude*1e-12)
    cache = {}; lower = 0.; largest_upper = 0.; witness = None
    passed = 0; failed = 0; unknown = []; terminal = []; tested = 0

    def distances(p):
        k = tuple(p)
        if k in cache: return cache[k]
        values = []
        for index, primitive in enumerate(targets):
            if not budget.charge(): return None
            d, q = _primitive_distance(p, primitive)
            values.append((d, q, index))
        cache[k] = values
        return values

    queue = [(tuple(tuple(p) for p in cell), 0, i) for i, cell in enumerate(domains)]
    while queue:
        cell, depth, original = queue.pop()
        center = tuple(sum(p[i] for p in cell)/len(cell) for i in range(3))
        points = list(cell)+[center]
        table = [distances(p) for p in points]
        if any(x is None for x in table):
            unknown.append({'domainIndex': original, 'cell': cell, 'reason': 'distance_test_budget_exceeded'})
            unknown += [{'domainIndex': i, 'cell': c, 'reason': 'distance_test_budget_exceeded'} for c, _, i in queue]
            queue.clear(); break
        tested += 1
        nearest = [min(values, key=lambda x: x[0]) for values in table]
        worst_index = max(range(len(points)), key=lambda i: nearest[i][0])
        lo = nearest[worst_index][0]
        # Distance to each convex primitive is convex. One primitive's vertex
        # maximum bounds all convex combinations, even when nearest faces switch.
        convex_upper = min(max(table[i][j][0] for i in range(len(cell))) for j in range(len(targets)))
        radius = max(norm(sub(p, center)) for p in cell)
        lip_upper = nearest[-1][0]+radius
        upper = min(convex_upper, lip_upper)+roundoff
        if witness is None or max(0., lo-roundoff) > lower:
            lower = max(0., lo-roundoff)
            target = nearest[worst_index]
            witness = {'sourceWorld': list(points[worst_index]), 'targetWorld': list(target[1]),
                       'distanceM': lo, 'sourceDomainIndex': original, 'targetPrimitiveIndex': target[2]}
        if upper <= tolerance:
            passed += 1; largest_upper = max(largest_upper, upper)
            terminal.append({'domainIndex': original, 'status': 'passed', 'upperBoundM': upper})
        elif lo-roundoff > tolerance:
            failed += 1; largest_upper = max(largest_upper, upper)
            terminal.append({'domainIndex': original, 'status': 'failed', 'upperBoundM': upper})
        elif depth >= max_depth or radius <= precision:
            unknown.append({'domainIndex': original, 'cell': cell, 'reason': 'subdivision_precision_or_depth_limit',
                            'lowerBoundM': lo, 'upperBoundM': upper})
        elif len(cell) == 2:
            queue.extend([((cell[0], center), depth+1, original), ((center, cell[1]), depth+1, original)])
        else:
            i, j = max(((0, 1), (1, 2), (2, 0)), key=lambda pair: norm(sub(cell[pair[0]], cell[pair[1]])))
            k = 3-i-j; middle = mul(add(cell[i], cell[j]), .5)
            queue.extend([((cell[i], middle, cell[k]), depth+1, original), ((middle, cell[j], cell[k]), depth+1, original)])
    complete = not unknown
    return {'status': 'failed' if failed else 'passed' if complete else 'missing_evidence',
            'complete': complete, 'mode': 'continuous_finite_polygonal_domain_certificate',
            'lowerBoundM': lower, 'upperBoundM': largest_upper if complete else None,
            'witness': witness, 'toleranceM': tolerance,
            'domainCellCount': len(domains), 'visitedCellCount': tested, 'certifiedLeafCount': passed,
            'failedLeafCount': failed, 'uncoveredCellCount': len(unknown), 'uncoveredCells': unknown,
            'distanceTests': budget.used,
            'numericalGuardM': roundoff,
            'numericalArithmetic': 'IEEE_float_with_explicit_scale_guard_not_symbolic_interval_arithmetic',
            'boundBasis': ['distance_to_closed_set_is_1_Lipschitz', 'distance_to_each_convex_primitive_is_convex'],
            'limitations': ['Certificate covers input polygonal cells only; no smooth surface or omitted geometry is inferred.',
                            'Distance enclosures use floating point with the reported numerical guard; near-limit cases remain unresolved.']}


def normalize_reference(value):
    """Normalize explicitly identified real reference triangles to world metres."""
    document = _document(value, 'referenceMesh')
    if document.get('format') != 'indexed_triangles_v1' or document.get('units') != 'metres':
        raise ReferenceError('invalid_reference_geometry', 'Reference requires indexed_triangles_v1 in explicit metres')
    if document.get('source') not in ('blender_mesh', 'reference_mesh', 'native_render_mesh', 'renderMesh'):
        raise ReferenceError('unverified_reference_source', 'Reference source must identify an exported actual mesh, never a proxy')
    if document.get('source') in ('native_render_mesh', 'renderMesh') and (
            not document.get('sampleId') or not document.get('geometryStamp')):
        raise ReferenceError('unverified_reference_source', 'A native reference additionally requires captured sampleId and geometryStamp')
    provenance = document.get('sourceProvenance')
    if (not isinstance(provenance, dict) or not all(provenance.get(k) for k in ('sourceId', 'contentHash', 'sourceVersion'))
            or not isinstance(document.get('identity'), dict) or not document['identity']):
        raise ReferenceError('unverified_reference_source', 'Reference requires identity and sourceProvenance sourceId/contentHash/sourceVersion')
    if document.get('staleAtDelivery') or document.get('stateUncertain'):
        raise ReferenceError('stale_evidence', 'Stale reference geometry is not accepted')
    rows = document.get('frameToWorldRows')
    if (not isinstance(rows, list) or len(rows) != 4 or any(not isinstance(r, list) or len(r) != 4 for r in rows)
            or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for r in rows for x in r)
            or rows[3] != [0, 0, 0, 1]):
        raise ReferenceError('coordinate_mismatch', 'Reference requires an explicit finite affine frameToWorldRows transform')
    det = (rows[0][0]*(rows[1][1]*rows[2][2]-rows[1][2]*rows[2][1])
           -rows[0][1]*(rows[1][0]*rows[2][2]-rows[1][2]*rows[2][0])
           +rows[0][2]*(rows[1][0]*rows[2][1]-rows[1][1]*rows[2][0]))
    if abs(det) < EPS:
        raise ReferenceError('coordinate_mismatch', 'Reference transform must be invertible')
    by_id = {}; count = 0
    entries = document.get('meshes')
    if not isinstance(entries, list): raise ReferenceError('invalid_reference_geometry', 'Reference meshes must be an array')
    for index, entry in enumerate(entries):
        pid = _integer(entry.get('partId', index), 'reference.mesh.partId')
        vertices = [_vec(p, 'reference vertex') for p in entry.get('vertices', [])]
        transformed = [tuple(sum(rows[i][j]*p[j] for j in range(3))+rows[i][3] for i in range(3)) for p in vertices]
        indices = entry.get('indices', [])
        if (not isinstance(indices, list) or len(indices) % 3
                or any(type(i) is not int or not 0 <= i < len(vertices) for i in indices)):
            raise ReferenceError('invalid_reference_geometry', 'Reference has invalid triangle indices')
        count += len(indices)//3
        if count > 250000: raise ReferenceError('geometry_budget_exceeded', 'Reference exceeds 250000 triangles')
        by_id.setdefault(pid, []).extend(tuple(transformed[indices[j+k]] for k in range(3)) for j in range(0, len(indices), 3))
    raw_hash = digest({'meshes': entries, 'units': document['units'], 'frameToWorldRows': rows})
    # contentHash names the upstream source version, while these hashes bind the
    # precise exported bytes/cells. Do not pretend arbitrary source hashes equal
    # a differently serialized triangle hash.
    return {'triangles': by_id, 'identity': deepcopy(document['identity']),
            'bounds': {pid: bounds(ts) for pid, ts in by_id.items()},
            'sourceProvenance': {**deepcopy(provenance), 'source': document['source'],
                                 'rawMeshSha256': raw_hash, 'worldMeshSha256': digest(by_id),
                                 'frameToWorldRows': rows, 'units': 'metres'},
            'complete': document.get('complete') is True}


def _selected_segments(cap, ids, spec, side, inventories):
    hint = spec.get('normalHint'+side, spec.get('normalHint'))
    if hint is None: return [], 'Independent outer-face normal hints are required'
    hint = _vec(hint)
    if norm(hint) <= EPS: raise ReferenceError('invalid_input', 'normalHint must be nonzero')
    hint = mul(hint, 1/norm(hint))
    selected = []
    selected_ids = spec.get('boundaryEdgeIds'+side)
    plane = spec.get('boundaryPlane'+side, spec.get('boundaryPlane'))
    if plane is not None:
        axis = _integer(plane.get('axis'), 'boundaryPlane.axis')
        if axis > 2: raise ReferenceError('invalid_input', 'boundaryPlane.axis must be 0..2')
        station = _number(plane.get('stationM'), 'boundaryPlane.stationM', -math.inf)
        for pid in ids:
            for index, tri in enumerate(cap['triangles'].get(pid, [])):
                n = normal(tri)
                if n is None or dot(n, hint) < .8: continue
                cut = section([tri], axis, station)
                selected.extend({**s, 'partId': pid, 'triangleIndex': index, 'normal': list(n)} for s in cut['segments'])
        return selected, None
    if selected_ids is None and spec.get('boundarySelection') != 'all_free_edges':
        return [], 'Declare boundaryPlane, explicit boundaryEdgeIdsA/B, or boundarySelection=all_free_edges'
    if selected_ids is not None and (not isinstance(selected_ids, list) or not selected_ids or any(not isinstance(i, str) for i in selected_ids)):
        raise ReferenceError('invalid_input', 'boundaryEdgeIds must be a nonempty string array')
    wanted = set(selected_ids or [])
    found = set()
    for pid in ids:
        inventory = inventories.get(pid)
        if not inventory or inventory['coverage']['status'] != 'complete':
            return [], 'Full edge enumeration is unavailable or exceeds budget'
        for edge in inventory['edges']:
            if (edge['id'] in wanted if wanted else edge['kind'] == 'open_boundary'):
                found.add(edge['id'])
                acceptable = [(index, normal(cap['triangles'][pid][index])) for index in edge['incidentTriangles']]
                acceptable = [(index, n) for index, n in acceptable if n is not None and dot(n, hint) >= .8]
                if acceptable:
                    index, n = acceptable[0]
                    selected.append({**edge, 'triangleIndex': index, 'normal': n})
    if wanted-found: return [], 'One or more selected actual edge IDs do not exist in this capture'
    return selected, None


def full_interface(spec, cap, inventories, budget):
    a, b = _ids(spec.get('a')), _ids(spec.get('b'))
    ids = sorted(set(a+b)); name = str(spec.get('id') or spec.get('name') or digest(spec)[:12])
    result = {'id': name+'-full-boundary', 'kind': 'continuous_boundary_certificate',
              'goalId': spec.get('goalId'), 'partIds': ids,
              'boundaryIds': spec.get('boundaryIds', [name]), 'expected': deepcopy(spec),
              'coverageMode': 'complete', 'evidence': _evidence(cap, ids, reference_bound=True)}
    if any(pid not in cap['triangles'] for pid in ids):
        return {**result, 'status': 'missing_evidence', 'reason': 'Missing actual interface mesh'}
    sa, reason_a = _selected_segments(cap, a, spec, 'A', inventories)
    sb, reason_b = _selected_segments(cap, b, spec, 'B', inventories)
    if reason_a or reason_b or not sa or not sb:
        return {**result, 'status': 'missing_evidence', 'reason': reason_a or reason_b or 'Expected outer boundary was not found'}
    if spec.get('maxGapM') is None or spec.get('maxAngleDegrees') is None:
        return {**result, 'status': 'missing_evidence', 'reason': 'Separate gap and angle tolerances are required'}
    if spec.get('crease') and not spec.get('creaseReason'):
        raise ReferenceError('invalid_input', 'Intentional crease requires creaseReason')
    tol = _number(spec['maxGapM'], 'maxGapM'); angle = _number(spec['maxAngleDegrees'], 'maxAngleDegrees')
    if angle > 180: raise ReferenceError('invalid_input', 'maxAngleDegrees cannot exceed 180')
    domains_a = [(s['a'], s['b']) for s in sa]; domains_b = [(s['a'], s['b']) for s in sb]
    ab = directed_certificate(domains_a, domains_b, tol, budget)
    ba = directed_certificate(domains_b, domains_a, tol, budget)
    folds = []; angle_complete = True; matched_a = set(); matched_b = set()
    for ai, x in enumerate(sa):
        ux = sub(x['b'], x['a']); lx = norm(ux)
        for bi, y in enumerate(sb):
            if not budget.charge(): angle_complete = False; break
            if bounds_distance(bounds([(x['a'], x['b'])]), bounds([(y['a'], y['b'])])) > tol: continue
            uy = sub(y['b'], y['a']); ly = norm(uy)
            if min(lx, ly) <= EPS or abs(dot(ux, uy)/(lx*ly)) < .95: continue
            direction = mul(ux, 1/lx)
            shared = min(lx, max(dot(sub(y['a'], x['a']), direction), dot(sub(y['b'], x['a']), direction)))-max(0., min(dot(sub(y['a'], x['a']), direction), dot(sub(y['b'], x['a']), direction)))
            # Vertex-only crossings between adjacent contour legs are not
            # competing outer faces. Compare normals on corresponding spans.
            if shared <= EPS: continue
            p, q = segment_segment(x['a'], x['b'], y['a'], y['b'])
            if norm(sub(p, q)) > tol: continue
            matched_a.add(ai); matched_b.add(bi)
            measured_angle = math.degrees(math.acos(max(-1., min(1., dot(x['normal'], y['normal'])))))
            if measured_angle > angle:
                folds.append({'witnessAWorld': list(p), 'witnessBWorld': list(q),
                              'normalA': x['normal'], 'normalB': y['normal'],
                              'angleDegrees': measured_angle, 'triangleA': x['triangleIndex'], 'triangleB': y['triangleIndex']})
        if not angle_complete: break
    unmatched = {'a': sorted(set(range(len(sa)))-matched_a), 'b': sorted(set(range(len(sb)))-matched_b)}
    if unmatched['a'] or unmatched['b']: angle_complete = False
    ok = ab['status'] == ba['status'] == 'passed' and angle_complete and (not folds or spec.get('crease'))
    failed = ab['status'] == 'failed' or ba['status'] == 'failed' or bool(folds and not spec.get('crease'))
    return {**result, 'status': 'passed' if ok else 'failed' if failed else 'missing_evidence',
            'coverageMode': 'complete' if ab['complete'] and ba['complete'] and angle_complete else 'finite_sampled',
            'measured': {'aToB': ab, 'bToA': ba, 'normalPairCoverageComplete': angle_complete,
                         'normalMismatches': folds, 'selectedBoundaryA': sa, 'selectedBoundaryB': sb,
                         'normalUnmatchedSegmentIndices': unmatched,
                         'intentionalCrease': bool(spec.get('crease'))},
            'limitations': ['Finite captured outer boundary only; selected orientation is part of the acceptance definition.',
                            'All in-tolerance segment pairs are conservatively checked for normal disagreement.']}


def boundary_review(cap, part_ids, payload):
    budget_spec = payload.get('budget', {})
    maximum = _integer(budget_spec.get('maxBoundaryEdges', 100000), 'maxBoundaryEdges', 1)
    remaining = maximum; inventories = {}; checks = []
    subject = set(payload.get('partIds', []))
    groups = [sorted(set(part_ids)&subject&set(cap['triangles'])),
              sorted((set(part_ids)-subject)&set(cap['triangles']))]
    for group in groups:
        for index, pid in enumerate(group):
            # Allocate among every subject before spending on contextual
            # neighbors. A low numeric neighbor ID cannot consume the whole
            # budget and erase both subjects' actual boundary evidence.
            allowance = remaining//(len(group)-index)
            if allowance <= 0:
                inv = {'partId': pid, 'edges': [], 'criticalVertices': [], 'coverage': {
                    'status': 'incomplete', 'mode': 'all_captured_triangle_edges', 'reason': 'shared_edge_inventory_budget_exceeded'}}
            else:
                inv = edge_inventory(cap['triangles'][pid], pid, allowance)
            inventories[pid] = inv; remaining -= len(inv['edges'])
    work = WorkBudget(budget_spec.get('maxBoundaryDistanceTests', 100000))
    for spec in payload.get('expectedInterfaces', []):
        if any(k in spec for k in ('boundaryPlane', 'boundaryPlaneA', 'boundaryPlaneB', 'boundaryEdgeIdsA', 'boundaryEdgeIdsB', 'boundarySelection')):
            checks.append(full_interface(spec, cap, inventories, work))
    complete = all(x['coverage']['status'] == 'complete' for x in inventories.values())
    return {'parts': list(inventories.values()), 'checks': checks,
            'coverage': {'status': 'complete' if complete else 'incomplete',
                         'scope': 'Complete enumeration of finite captured triangle edges, not whole-craft acceptance',
                         'distanceTests': work.used, 'maximumDistanceTests': work.maximum},
            'limitations': ['Edge inventory and continuous acceptance are distinct; enumeration alone proves no design requirement.']}


def geometric_boundary_relations(cap, frontier, radius, budget, inventories=None):
    """All candidate boundary pairs in a frontier, with real edge witnesses.

    The result distinguishes a geometrically shared span from a declared smooth
    interface. It never asserts that two nearby spans were intended to meet.
    Triangulation diagonals are excluded, but real creases/caps remain available
    to expose closed solids' external interfaces.
    """
    inventories = inventories if inventories is not None else {}
    result = []; pending = []
    for a in sorted(cap['triangles']):
        for b in sorted(cap['triangles']):
            if a >= b or not ({a, b} & set(frontier)): continue
            if bounds_distance(cap['bounds'][a], cap['bounds'][b]) > radius: continue
            for pid in (a, b):
                if pid not in inventories: inventories[pid] = edge_inventory(cap['triangles'][pid], pid)
            if any(inventories[pid]['coverage']['status'] != 'complete' for pid in (a, b)):
                pending.append({'partIds': [a, b], 'reason': 'boundary_inventory_incomplete'}); continue
            ea = [e for e in inventories[a]['edges'] if e['kind'] != 'triangulation_edge']
            eb = [e for e in inventories[b]['edges'] if e['kind'] != 'triangulation_edge']
            spans = []; minimum = None; complete = True; considered = 0
            for x in ea:
                if not complete: break
                u = sub(x['b'], x['a']); length = norm(u)
                if length <= EPS: continue
                direction = mul(u, 1/length)
                for y in eb:
                    if not budget.charge(): complete = False; break
                    considered += 1
                    if bounds_distance(bounds([(x['a'], x['b'])]), bounds([(y['a'], y['b'])])) > radius: continue
                    v = sub(y['b'], y['a']); vy = norm(v)
                    if vy <= EPS or abs(dot(direction, mul(v, 1/vy))) < .95: continue
                    overlap = min(length, max(dot(sub(y['a'], x['a']), direction), dot(sub(y['b'], x['a']), direction)))-max(0., min(dot(sub(y['a'], x['a']), direction), dot(sub(y['b'], x['a']), direction)))
                    if overlap <= max(EPS, min(length, vy)*.1): continue
                    p, q = segment_segment(x['a'], x['b'], y['a'], y['b'])
                    distance = norm(sub(p, q))
                    if distance > radius: continue
                    angles = [math.degrees(math.acos(max(-1., min(1., dot(nx, ny))))) for nx in x['normals'] for ny in y['normals']]
                    # Keep orientation mismatch separate from ownership: a cap
                    # may meet a side deliberately, or an outer wall may fold.
                    row = {'edgeAId': x['id'], 'edgeBId': y['id'], 'partIds': [a, b],
                           'witnessAWorld': list(p), 'witnessBWorld': list(q), 'distanceM': distance,
                           'projectedSharedSpanM': overlap, 'directionWorld': list(direction),
                           'edgeA': x, 'edgeB': y, 'normalAnglesDegrees': angles,
                           'outerSurfaceOwnership': 'unresolved', 'visibility': 'unobserved'}
                    spans.append(row)
                    if minimum is None or distance < minimum['distanceM']: minimum = row
            if spans:
                center_a = mul(add(cap['bounds'][a]['min'], cap['bounds'][a]['max']), .5)
                center_b = mul(add(cap['bounds'][b]['min'], cap['bounds'][b]['max']), .5)
                delta = sub(center_b, center_a)
                result.append({'id': 'boundary-relation-'+str(a)+'-'+str(b),
                    'kind': 'geometric_shared_boundary_candidate', 'partIds': [a, b],
                    'status': 'measured' if complete else 'missing_evidence', 'basis': 'all_actual_non_diagonal_edge_pairs',
                    'complete': complete, 'edgePairTests': considered, 'spans': spans,
                    'minimumBoundaryDistanceM': minimum['distanceM'],
                    'witnessAWorld': minimum['witnessAWorld'], 'witnessBWorld': minimum['witnessBWorld'],
                    'relativePosition': {'deltaWorldM': list(delta), 'dominantAxis': max(range(3), key=lambda i: abs(delta[i])),
                                         'meaning': 'world axes only; no inferred ship orientation'},
                    'evidence': _evidence(cap, [a, b]),
                    'limitations': ['Shared/nearby span is measured; continuity intent, visible ownership and physical support remain independent.']})
            if not complete: pending.append({'partIds': [a, b], 'reason': 'boundary_pair_budget_exceeded'})
    return result, pending


def replacement_mapping(payload, before_cap, cap):
    rows = payload.get('replacements', [])
    if not isinstance(rows, list): raise ReferenceError('invalid_input', 'replacements must be an array')
    if rows and before_cap is None:
        raise ReferenceError('replacement_baseline_required', 'Semantic replacements require an actual before capture')
    mapping = {}; semantics = []; owned_after = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('semanticId'), str) or not row['semanticId']:
            raise ReferenceError('invalid_input', 'Each replacement requires a stable explicit semanticId')
        old = _ids(row.get('fromPartIds'), 'replacements.fromPartIds')
        new = _ids(row.get('toPartIds'), 'replacements.toPartIds')
        if any(str(pid) not in before_cap['parts'] for pid in old) or any(str(pid) not in cap['parts'] for pid in new):
            raise ReferenceError('invalid_replacement', 'Replacement members must exist in their bound before/after snapshots')
        for pid in old:
            if pid in mapping and mapping[pid] != new:
                raise ReferenceError('ambiguous_replacement', 'An old part maps to conflicting semantic replacements', partId=pid)
            mapping[pid] = new
        for pid in new:
            if pid in owned_after and owned_after[pid] != row['semanticId']:
                raise ReferenceError('ambiguous_replacement', 'An after part has conflicting semantic ownership', partId=pid)
            owned_after[pid] = row['semanticId']
        semantics.append({'semanticId': row['semanticId'], 'fromPartIds': old, 'toPartIds': new,
                          'mappingType': 'one_to_many' if len(old) == 1 and len(new) > 1 else 'many_to_one' if len(old) > 1 and len(new) == 1 else 'explicit_group',
                          'basis': 'explicit_semantic_replacement_bound_to_before_after_identities',
                          'beforeIdentity': before_cap['identity'], 'afterIdentity': cap['identity']})
    return mapping, semantics


def propagate_impact(cap, seed, payload, native_relations, phase='after'):
    """Follow real boundary spans and typed cut/mirror dependencies in rounds."""
    radius = _number(payload.get('neighborDistanceM', .05), 'neighborDistanceM')
    settings = payload.get('budget', {})
    max_hops = _integer(settings.get('maxPropagationHops', 4), 'maxPropagationHops', 1)
    max_parts = _integer(settings.get('maxPropagationParts', 256), 'maxPropagationParts', 1)
    if max_hops > 64 or max_parts > 4096: raise ReferenceError('invalid_input', 'Impact propagation budget exceeds local ceiling')
    work = WorkBudget(settings.get('maxBoundaryPairTests', 100000))
    visited = set(seed); frontier = set(seed); records = {}; paths = []; pending = []; inv = {}
    declared = []
    for row in payload.get('expectedInterfaces', []):
        if not isinstance(row, dict): continue
        ids = sorted(set(row.get('a', [])+row.get('b', [])))
        declared.append({'id': row.get('id') or row.get('name'), 'kind': 'declared_expected_boundary',
                         'partIds': ids, 'basis': 'explicit_user_or_reference_continuity_expectation'})
    dependencies = [x for x in native_relations if x['kind'] in (
        'native_symmetry_group', 'nested_native_dependency', 'cut_or_target_dependency')]+declared
    exhausted = False
    for hop in range(max_hops):
        if not frontier: break
        edges, missing = geometric_boundary_relations(cap, frontier, radius, work, inv)
        pending.extend({'phase': phase, **x} for x in missing)
        for edge in edges: records[edge['id']] = edge
        next_frontier = set()
        for relation in edges+dependencies:
            ids = set(relation['partIds'])
            if not ids & frontier: continue
            for pid in sorted(ids-visited):
                if len(visited|next_frontier) >= max_parts:
                    pending.append({'phase': phase, 'partIds': sorted(ids), 'reason': 'propagation_part_budget_exceeded'})
                    continue
                if str(pid) not in cap['parts']:
                    pending.append({'phase': phase, 'partIds': [pid], 'reason': 'dependency_target_not_in_snapshot'}); continue
                next_frontier.add(pid)
                paths.append({'partId': pid, 'fromPartIds': sorted(ids & frontier), 'hop': hop+1,
                              'relationKind': relation['kind'], 'relationId': relation.get('id'),
                              'phase': phase, 'basis': relation.get('basis')})
        visited |= next_frontier; frontier = next_frontier
        if work.used >= work.maximum:
            exhausted = True
            if frontier: pending.append({'phase': phase, 'partIds': sorted(frontier), 'reason': 'boundary_pair_budget_exceeded'})
            break
    if frontier and not exhausted:
        pending.append({'phase': phase, 'partIds': sorted(frontier), 'reason': 'propagation_hop_budget_exceeded'})
    return {'partIds': sorted(visited), 'relations': list(records.values()), 'paths': paths,
            'pending': pending, 'coverage': {'status': 'complete' if not pending else 'incomplete',
                'boundaryPairTests': work.used, 'maxBoundaryPairTests': work.maximum,
                'maxHops': max_hops, 'maxParts': max_parts,
                'basis': 'iterative_actual_boundary_spans_plus_explicit_mirror_cut_and_expected_interfaces'}}


def reference_review(cap, payload, sections):
    if not payload.get('referenceMesh'):
        return {'status': 'not_compared', 'referenceHash': payload.get('referenceHash'),
                'reason': 'A reference hash alone is not a surface comparison'}
    ref = normalize_reference(payload['referenceMesh'])
    requested = payload.get('referenceMatches')
    if requested is None:
        requested = [{'partIds': _ids(payload.get('partIds')), 'referencePartIds': sorted(ref['triangles'])}]
    if not isinstance(requested, list) or not requested:
        raise ReferenceError('invalid_input', 'referenceMatches must be a nonempty array')
    checks = []; comparisons = []; section_tests = 0
    max_section_tests = _integer(payload.get('budget', {}).get('maxReferenceSectionTriangleTests', 500000), 'maxReferenceSectionTriangleTests', 1)
    if max_section_tests > 5000000: raise ReferenceError('invalid_input', 'Reference section budget exceeds local ceiling')
    budget = WorkBudget(payload.get('budget', {}).get('maxReferenceDistanceTests', 100000))
    for index, spec in enumerate(requested):
        actual_ids = _ids(spec.get('partIds')); reference_ids = _ids(spec.get('referencePartIds'))
        actual = [t for pid in actual_ids for t in cap['triangles'].get(pid, [])]
        reference = [t for pid in reference_ids for t in ref['triangles'].get(pid, [])]
        base = {'id': spec.get('id', 'reference-domain-'+str(index)), 'kind': 'actual_reference_surface_certificate',
                'partIds': actual_ids, 'referencePartIds': reference_ids, 'goalId': spec.get('goalId'),
                'boundaryIds': spec.get('boundaryIds', []), 'coverageMode': 'complete',
                'expected': deepcopy(spec), 'evidence': _evidence(cap, actual_ids, 'actual_reference_mesh_measurement')}
        base['evidence'].update(referenceIndependent=False, referenceHash=ref['sourceProvenance']['worldMeshSha256'],
                                referenceIdentity=ref['identity'], sourceProvenance=ref['sourceProvenance'])
        base['evidence']['id'] = 'reference-measurement-'+digest(base['evidence'])[:20]
        if any(pid not in cap['triangles'] for pid in actual_ids) or any(pid not in ref['triangles'] for pid in reference_ids):
            checks.append({**base, 'status': 'missing_evidence', 'reason': 'Requested actual/reference mesh is absent'})
        elif not actual or not reference:
            checks.append({**base, 'status': 'missing_evidence', 'reason': 'Actual/reference domain is empty'})
        elif spec.get('maxSurfaceDistanceM') is not None:
            tol = _number(spec['maxSurfaceDistanceM'], 'maxSurfaceDistanceM')
            ab = directed_certificate(actual, reference, tol, budget)
            ba = directed_certificate(reference, actual, tol, budget)
            complete = ab['complete'] and ba['complete'] and ref['complete'] and cap['mesh'].get('complete') is True
            status = 'failed' if 'failed' in (ab['status'], ba['status']) else 'passed' if complete and ab['status'] == ba['status'] == 'passed' else 'missing_evidence'
            checks.append({**base, 'status': status, 'coverageMode': 'complete' if complete else 'finite_sampled',
                           'measured': {'actualToReference': ab, 'referenceToActual': ba,
                                        'bothSourceExportsDeclareComplete': ref['complete'] and cap['mesh'].get('complete') is True}})
        else:
            checks.append({**base, 'status': 'needs_review', 'reason': 'No explicit surface-distance tolerance; actual sections are diagnostic only'})
        stations = sorted({(s['axis'], s['stationM']) for s in sections if s.get('partId') in actual_ids and 'axis' in s})
        for axis, station in stations:
            if section_tests+len(actual)+len(reference) > max_section_tests:
                comparisons.append({'actualPartIds': actual_ids, 'referencePartIds': reference_ids,
                    'axis': axis, 'stationM': station, 'status': 'missing_evidence',
                    'reason': 'reference_section_triangle_budget_exceeded', 'identity': cap['identity'],
                    'referenceIdentity': ref['identity'], 'sourceProvenance': ref['sourceProvenance'],
                    'coordinateFrame': {'units': 'm', 'frameToWorldRows': WORLD}})
                continue
            section_tests += len(actual)+len(reference)
            comparisons.append({'actualPartIds': actual_ids, 'referencePartIds': reference_ids,
                'axis': axis, 'stationM': station, 'actual': section(actual, axis, station),
                'reference': section(reference, axis, station), 'identity': cap['identity'],
                'referenceIdentity': ref['identity'], 'sourceProvenance': ref['sourceProvenance'],
                'coordinateFrame': {'units': 'm', 'frameToWorldRows': WORLD},
                'status': 'measured', 'limitations': ['Section overlays alone do not prove the continuous domain between stations.']})
    return {'status': 'compared' if checks else 'not_compared', 'identity': ref['identity'],
            'sourceProvenance': ref['sourceProvenance'], 'checks': checks, 'sectionComparisons': comparisons,
            'coordinateFrame': {'units': 'm', 'frameToWorldRows': WORLD},
            'distanceTests': budget.used, 'maximumDistanceTests': budget.maximum,
            'sectionTriangleTests': section_tests, 'maximumSectionTriangleTests': max_section_tests}
