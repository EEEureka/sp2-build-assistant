"""Read-only regional observations of captured native triangles.

This module never calls the game. Broad-phase bounds select candidates only;
surface distances, sections and overlap witnesses use actual exported triangles.
The result deliberately separates measured facts, review candidates and missing
coverage. It cannot certify an entire craft or native paint from an export.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import math
from pathlib import Path

from reference_storage import ReferenceError, digest, read_json
from reference_binding import identity, part_signature, snapshot_parts, snapshot_context, unwrap

WORLD = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
EPS = 1e-9


def _document(value, name):
    if isinstance(value, str):
        value = read_json(value)
    if not isinstance(value, dict):
        raise ReferenceError('invalid_input', name + ' requires an object or UTF-8 JSON path')
    return unwrap(value)


def _number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ReferenceError('invalid_input', name + ' must be a finite number >= ' + str(minimum))
    return float(value)


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ReferenceError('invalid_input', name + ' must be an integer >= ' + str(minimum))
    return value


def _ids(values, name='partIds'):
    if not isinstance(values, list) or not values:
        raise ReferenceError('invalid_scope', name + ' must be a nonempty array')
    return sorted({_integer(i, name) for i in values})


def _vec(value, name='point'):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ReferenceError('invalid_input', name + ' must contain three finite coordinates')
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in value):
        raise ReferenceError('invalid_input', name + ' must contain three finite coordinates')
    return tuple(float(x) for x in value)


def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def add(a, b): return tuple(x+y for x, y in zip(a, b))
def mul(a, k): return tuple(x*k for x in a)
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a, a))


def normal(tri):
    n = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
    return mul(n, 1/norm(n)) if norm(n) > EPS*EPS else None


def bounds(triangles):
    points = [p for tri in triangles for p in tri]
    return {'min': [min(p[i] for p in points) for i in range(3)],
            'max': [max(p[i] for p in points) for i in range(3)]} if points else None


def bounds_distance(a, b):
    return math.sqrt(sum(max(0, a['min'][i]-b['max'][i], b['min'][i]-a['max'][i])**2 for i in range(3)))


def point_segment(p, a, b):
    e = sub(b, a); ee = dot(e, e)
    return add(a, mul(e, max(0, min(1, dot(sub(p, a), e)/ee)))) if ee > EPS*EPS else a


def point_triangle(p, tri):
    """Exact closest point (including degenerate triangles), not centroid distance."""
    a, b, c = tri; ab, ac = sub(b, a), sub(c, a)
    n = normal(tri)
    candidates = [point_segment(p, x, y) for x, y in ((a, b), (b, c), (c, a))]
    if n is not None:
        q = sub(p, mul(n, dot(sub(p, a), n))); aq = sub(q, a)
        aa, bb, cc = dot(ab, ab), dot(ab, ac), dot(ac, ac); det = aa*cc-bb*bb
        if det > EPS**4:
            u = (cc*dot(aq, ab)-bb*dot(aq, ac))/det
            v = (aa*dot(aq, ac)-bb*dot(aq, ab))/det
            if u >= -EPS and v >= -EPS and u+v <= 1+EPS:
                candidates.append(q)
    q = min(candidates, key=lambda x: norm(sub(p, x)))
    return norm(sub(p, q)), q


def segment_segment(p, q, a, b):
    # Endpoints plus the stationary solution cover finite segment minima.
    result = [(p, point_segment(p, a, b)), (q, point_segment(q, a, b)),
              (point_segment(a, p, q), a), (point_segment(b, p, q), b)]
    u, v, w = sub(q, p), sub(b, a), sub(p, a)
    aa, bb, cc, dd, ee = dot(u, u), dot(u, v), dot(v, v), dot(u, w), dot(v, w)
    den = aa*cc-bb*bb
    if den > EPS**4:
        s, t = (bb*ee-cc*dd)/den, (aa*ee-bb*dd)/den
        if 0 <= s <= 1 and 0 <= t <= 1:
            result.append((add(p, mul(u, s)), add(a, mul(v, t))))
    return min(result, key=lambda x: norm(sub(*x)))


def segment_triangle(a, b, tri):
    n = normal(tri)
    if n is None: return None
    da, db = dot(sub(a, tri[0]), n), dot(sub(b, tri[0]), n)
    if abs(da-db) <= EPS or da*db > 0: return None
    t = da/(da-db)
    if not -EPS <= t <= 1+EPS: return None
    p = add(a, mul(sub(b, a), t))
    return p if point_triangle(p, tri)[0] <= EPS else None


def triangle_distance(a, b):
    witnesses = []
    for p in a:
        _, q = point_triangle(p, b); witnesses.append((p, q))
    for q in b:
        _, p = point_triangle(q, a); witnesses.append((p, q))
    for x, y in zip(a, (a[1], a[2], a[0])):
        hit = segment_triangle(x, y, b)
        if hit is not None: return 0., hit, hit
        for p, q in zip(b, (b[1], b[2], b[0])):
            witnesses.append(segment_segment(x, y, p, q))
    for p, q in zip(b, (b[1], b[2], b[0])):
        hit = segment_triangle(p, q, a)
        if hit is not None: return 0., hit, hit
    x, y = min(witnesses, key=lambda pair: norm(sub(*pair)))
    return norm(sub(x, y)), x, y


def coplanar_overlap(a, b, tolerance):
    """Positive-area intersection on nearly coplanar actual triangles.

    This is a duplicate-skin *candidate*: exposure, intentional embedded caps and
    boolean ownership require independent context/visibility inspection.
    """
    na, nb = normal(a), normal(b)
    if na is None or nb is None or abs(dot(na, nb)) < .9999: return None
    if max(abs(dot(sub(p, a[0]), na)) for p in b) > tolerance: return None
    dropped = max(range(3), key=lambda i: abs(na[i])); axes = [i for i in range(3) if i != dropped]
    project = lambda p: (p[axes[0]], p[axes[1]])
    poly = [project(p) for p in a]; clip = [project(p) for p in b]
    signed = lambda p, q, r: (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    winding = 1 if signed(*clip) >= 0 else -1
    for x, y in zip(clip, (clip[1], clip[2], clip[0])):
        old, poly = poly, []
        if not old: break
        for p, q in zip(old, old[1:]+old[:1]):
            dp, dq = winding*signed(x, y, p), winding*signed(x, y, q)
            if dp >= -EPS: poly.append(p)
            if (dp > EPS and dq < -EPS) or (dp < -EPS and dq > EPS):
                t = dp/(dp-dq); poly.append(tuple(p[i]+t*(q[i]-p[i]) for i in range(2)))
    if len(poly) < 3: return None
    area = abs(sum(p[0]*q[1]-q[0]*p[1] for p, q in zip(poly, poly[1:]+poly[:1])))/2/abs(na[dropped])
    if area <= EPS*EPS: return None
    points = []
    for p in poly:
        v = [0., 0., 0.]; v[axes[0]], v[axes[1]] = p
        v[dropped] = a[0][dropped]-sum(na[i]*(v[i]-a[0][i]) for i in axes)/na[dropped]
        points.append(v)
    return {'areaM2': area, 'polygonWorld': points, 'witnessWorld': [sum(v[i] for v in points)/len(points) for i in range(3)]}


def capture(snapshot, mesh):
    snapshot, mesh = _document(snapshot, 'snapshot'), _document(mesh, 'mesh')
    ident = identity(snapshot)
    if mesh.get('identity') != ident:
        raise ReferenceError('evidence_identity_mismatch', 'Snapshot and mesh must retain the same captured identity')
    if mesh.get('staleAtDelivery') or mesh.get('stateUncertain'):
        raise ReferenceError('stale_evidence', 'Stale or uncertain native geometry cannot be reviewed')
    if mesh.get('format') != 'indexed_triangles_v1':
        raise ReferenceError('invalid_geometry', 'Expected actual indexed_triangles_v1 native mesh export')
    if mesh.get('source') != 'renderMesh' or not isinstance(mesh.get('sampleId'), str) or not mesh['sampleId'] or not mesh.get('geometryStamp'):
        raise ReferenceError('unverified_geometry_source', 'Native observation requires renderMesh source, captured sampleId and geometryStamp; proxy or unstamped geometry is not native evidence')
    if mesh.get('units') != 'metres' or mesh.get('frameToWorldRows') != WORLD:
        raise ReferenceError('coordinate_mismatch', 'Native observations require explicitly declared world-frame metres')
    parts = snapshot_parts(snapshot); by_id = {}
    entries = mesh.get('meshes')
    if not isinstance(entries, list): raise ReferenceError('invalid_geometry', 'meshes must be an array')
    count = 0
    for entry in entries:
        pid = _integer(entry.get('partId'), 'mesh.partId')
        if str(pid) not in parts: raise ReferenceError('part_not_found', 'Native mesh part is absent from snapshot', partId=pid)
        vertices = [_vec(v, 'mesh vertex') for v in entry.get('vertices', [])]
        indices = entry.get('indices', [])
        if not isinstance(indices, list) or len(indices) % 3:
            raise ReferenceError('invalid_geometry', 'Triangle indices must be divisible by three')
        if any(type(i) is not int or i < 0 or i >= len(vertices) for i in indices):
            raise ReferenceError('invalid_geometry', 'Triangle contains an invalid vertex index')
        count += len(indices)//3
        if count > 250000: raise ReferenceError('geometry_budget_exceeded', 'Capture exceeds 250000 triangle local review budget')
        by_id.setdefault(pid, []).extend(tuple(vertices[indices[j+k]] for k in range(3)) for j in range(0, len(indices), 3))
    by_id = {pid: triangles for pid, triangles in by_id.items() if triangles}
    return {'snapshot': snapshot, 'mesh': mesh, 'identity': ident, 'parts': parts, 'triangles': by_id,
            'bounds': {pid: bounds(triangles) for pid, triangles in by_id.items()},
            'triangleBounds': {pid: [bounds([tri]) for tri in triangles] for pid, triangles in by_id.items()},
            'geometryStamp': mesh.get('geometryStamp') or {'meshSha256': digest(mesh)},
            'partHashes': {key: part_signature(part) for key, part in parts.items()}}


def section(triangles, axis, station, tolerance=1e-7):
    """Triangle/plane segments, including coplanar surface outlines; no proxy."""
    axis = _integer(axis, 'section.axis')
    if axis > 2: raise ReferenceError('invalid_input', 'section.axis must be 0, 1 or 2')
    station = _number(station, 'section.station', -math.inf)
    segments = {}; coplanar = {}
    key = lambda p: tuple(round(x/tolerance) for x in p)
    def insert(a, b, table):
        if norm(sub(a, b)) <= tolerance: return
        ka, kb = key(a), key(b); k = tuple(sorted((ka, kb)))
        if table is coplanar:
            if k in table: table[k]['count'] += 1
            else: table[k] = {'a': list(a), 'b': list(b), 'count': 1}
        else: table[k] = {'a': list(a), 'b': list(b)}
    for tri in triangles:
        distances = [p[axis]-station for p in tri]
        if all(abs(d) <= tolerance for d in distances):
            for a, b in zip(tri, (tri[1], tri[2], tri[0])): insert(a, b, coplanar)
            continue
        hits = {}
        for a, b, da, db in zip(tri, (tri[1], tri[2], tri[0]), distances, distances[1:]+distances[:1]):
            if abs(da) <= tolerance: hits[key(a)] = a
            if da*db < 0:
                p = add(a, mul(sub(b, a), -da/(db-da))); hits[key(p)] = p
        values = list(hits.values())
        if len(values) >= 2:
            a, b = max(((a, b) for a in values for b in values), key=lambda pair: norm(sub(*pair)))
            insert(a, b, segments)
    for k, value in coplanar.items():
        if value['count'] == 1: segments[k] = {'a': value['a'], 'b': value['b']}
    degree = {}
    adjacency = {}; positions = {}
    for item in segments.values():
        ka, kb = key(item['a']), key(item['b'])
        positions[ka], positions[kb] = item['a'], item['b']
        adjacency.setdefault(ka, set()).add(kb); adjacency.setdefault(kb, set()).add(ka)
        for p in (item['a'], item['b']): degree[key(p)] = degree.get(key(p), 0)+1
    loops = []; remaining = set(adjacency)
    while remaining:
        start = min(remaining); connected = {start}; queue = [start]
        while queue:
            current = queue.pop()
            for neighbor in adjacency[current]-connected: connected.add(neighbor); queue.append(neighbor)
        remaining -= connected
        if not all(degree[p] == 2 for p in connected): continue
        polygon = []; previous = None; current = start
        for _ in range(len(connected)+1):
            polygon.append(positions[current]); options = sorted(adjacency[current]-({previous} if previous is not None else set()))
            next_point = options[0]
            if next_point == start: break
            previous, current = current, next_point
        if len(polygon) >= 3: loops.append(polygon)
    plane_axes = [i for i in range(3) if i != axis]
    def inside(point, polygon):
        x, y = point[plane_axes[0]], point[plane_axes[1]]; result = False
        for a, b in zip(polygon, polygon[1:]+polygon[:1]):
            ax, ay, bx, by = a[plane_axes[0]], a[plane_axes[1]], b[plane_axes[0]], b[plane_axes[1]]
            if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax: result = not result
        return result
    nested = any(inside(inner[0], outer) for i, inner in enumerate(loops) for j, outer in enumerate(loops) if i != j)
    return {'axis': axis, 'stationM': station, 'segments': list(segments.values()), 'segmentCount': len(segments),
            'openEndpointCount': sum(d == 1 for d in degree.values()), 'branchVertexCount': sum(d > 2 for d in degree.values()),
            'closedLoopCount': len(loops), 'nestedContourLoops': nested,
            'cavityCandidate': 'nested_loops_at_this_station_only' if nested else 'not_established',
            'basis': 'actual_native_triangle_plane_intersections', 'toleranceM': tolerance,
            'limitations': ['Section topology is finite and tolerance-welded; no automatic solid, cavity or missing-face classification.']}


def topology(triangles, tolerance=1e-7):
    edges = {}; degenerate = 0
    key = lambda p: tuple(round(x/tolerance) for x in p)
    for tri in triangles:
        if normal(tri) is None: degenerate += 1
        for a, b in zip(tri, (tri[1], tri[2], tri[0])):
            ka, kb = key(a), key(b)
            if ka == kb: continue
            k = tuple(sorted((ka, kb)))
            if k not in edges: edges[k] = {'a': list(a), 'b': list(b), 'count': 0}
            edges[k]['count'] += 1
    free = [v for v in edges.values() if v['count'] == 1]
    return {'triangleCount': len(triangles), 'boundaryEdgeCount': len(free), 'boundaryEdgeSamples': free[:64],
            'nonManifoldEdgeCount': sum(v['count'] > 2 for v in edges.values()), 'degenerateTriangleCount': degenerate,
            'weldToleranceM': tolerance, 'classification': 'observed_open_edges' if free else 'no_open_edges_detected',
            'limitations': ['Open edges can be intentional, split meshes or missing export coverage; they are not proof of a defect.']}


def _evidence(cap, ids, kind='native_mesh_measurement', reference_bound=False):
    hashes = {str(i): cap['partHashes'][str(i)] for i in sorted(set(ids)) if str(i) in cap['partHashes']}
    reference_hash = cap.get('criterionReferenceHash') if reference_bound else None
    return {'id': 'measurement-'+digest({'identity': cap['identity'], 'parts': hashes, 'geometryStamp': cap['geometryStamp'],
                                        'referenceHash': reference_hash, 'referenceBound': reference_bound})[:20],
            'kind': kind, 'identity': cap['identity'], 'geometryStamp': cap['geometryStamp'], 'partIds': sorted(set(ids)),
            'scopeHash': digest(hashes), 'coordinateFrame': {'units': 'm', 'frameToWorldRows': WORLD},
            'referenceHash': reference_hash, 'referenceIndependent': not reference_bound,
            'referenceBindingMeaning': 'Declared acceptance criterion only; not evidence of reference surface fitting' if reference_bound else 'Native measured geometry independent of reference fitting'}


def _nearest_point(p, triangles, hint=None):
    best = None
    if hint is not None:
        hint = _vec(hint, 'normalHint'); n = norm(hint)
        if n <= EPS: raise ReferenceError('invalid_input', 'normalHint must have nonzero length')
        hint = mul(hint, 1/n)
    for index, tri in enumerate(triangles):
        n = normal(tri)
        if n is None or (hint is not None and dot(n, hint) < .8): continue
        d, q = point_triangle(p, tri)
        if best is None or d < best[0]: best = (d, q, n, index)
    return best


def _interface(spec, cap, index):
    a, b = _ids(spec.get('a'), 'interface.a'), _ids(spec.get('b'), 'interface.b')
    ids = sorted(set(a+b)); name = str(spec.get('id') or spec.get('name') or 'interface-'+str(index))
    boundary_ids = spec.get('boundaryIds', [name])
    if not isinstance(boundary_ids, list) or not boundary_ids or any(not isinstance(i, str) or not i for i in boundary_ids):
        raise ReferenceError('invalid_input', 'Interface boundaryIds must contain explicit nonempty strings')
    result = {'id': name, 'kind': 'declared_surface_continuity', 'partIds': ids,
              'boundaryIds': sorted(set(boundary_ids)),
              'goalId': spec.get('goalId'), 'expected': deepcopy(spec), 'evidence': _evidence(cap, ids, reference_bound=True),
              'limitations': ['Finite declared witnesses only; full boundary coverage is not certified.']}
    if any(i not in cap['triangles'] for i in ids):
        return {**result, 'status': 'missing_evidence', 'reason': 'One or more interface meshes are absent'}
    points = spec.get('points')
    if not isinstance(points, list) or len(points) < 3:
        return {**result, 'status': 'missing_evidence', 'reason': 'Provide endpoints and at least one independent intermediate witness'}
    if len({_vec(p) for p in points}) < 3:
        return {**result, 'status': 'missing_evidence', 'reason': 'Repeated points do not cover independent boundary witnesses'}
    ha, hb = spec.get('normalHintA', spec.get('normalHint')), spec.get('normalHintB', spec.get('normalHint'))
    if ha is None or hb is None:
        return {**result, 'status': 'missing_evidence', 'reason': 'Independent outer-face normal hints are required; arbitrary nearest caps cannot prove continuity'}
    if spec.get('maxGapM') is None or spec.get('maxAngleDegrees') is None:
        return {**result, 'status': 'missing_evidence', 'reason': 'Separate seam-distance and normal-angle tolerances must be explicitly declared'}
    gap = _number(spec.get('maxGapM'), 'maxGapM')
    angle = _number(spec.get('maxAngleDegrees'), 'maxAngleDegrees')
    if angle > 180: raise ReferenceError('invalid_input', 'maxAngleDegrees cannot exceed 180')
    if spec.get('crease') and not spec.get('creaseReason'):
        raise ReferenceError('invalid_input', 'An intentional crease requires its physical reason')
    ta = [t for pid in a for t in cap['triangles'][pid]]; tb = [t for pid in b for t in cap['triangles'][pid]]
    rows = []
    for point in points:
        p = _vec(point); x, y = _nearest_point(p, ta, ha), _nearest_point(p, tb, hb)
        if x is None or y is None:
            return {**result, 'status': 'missing_evidence', 'reason': 'Expected outer-facing surface not found at a witness'}
        rows.append({'pointWorld': list(p), 'pointAWorld': list(x[1]), 'pointBWorld': list(y[1]),
                     'distanceToAM': x[0], 'distanceToBM': y[0], 'gapM': norm(sub(x[1], y[1])),
                     'normalA': list(x[2]), 'normalB': list(y[2]),
                     'angleDegrees': math.degrees(math.acos(max(-1, min(1, dot(x[2], y[2])))))})
    # A distant coincident surface cannot satisfy witnesses placed on another interface.
    max_gap = max(r['gapM'] for r in rows); max_distance = max(max(r['distanceToAM'], r['distanceToBM']) for r in rows)
    max_angle = max(r['angleDegrees'] for r in rows)
    ok = max_gap <= gap and max_distance <= gap and (spec.get('crease') or max_angle <= angle)
    return {**result, 'status': 'passed' if ok else 'failed',
            'measured': {'maxGapM': max_gap, 'maxWitnessSurfaceDistanceM': max_distance, 'maxNormalAngleDegrees': max_angle, 'samples': rows}}


def _relations(cap, subject, radius, max_pairs, max_tests, overlap_tolerance):
    triangles, bs = cap['triangles'], cap['bounds']; records = []; pending = []; count = 0
    candidates = sorted((bounds_distance(bs[a], bs[b]), a, b) for a in triangles for b in triangles
                        if a < b and (a in subject or b in subject) and bounds_distance(bs[a], bs[b]) <= radius)
    for lower, a, b in candidates:
        if len(records) >= max_pairs:
            pending.append({'partIds': [a, b], 'reason': 'candidate_pair_budget_exceeded'}); continue
        best = None; overlaps = []; complete = True; evaluated = 0
        for i, ta in enumerate(triangles[a]):
            for j, tb in enumerate(triangles[b]):
                if count >= max_tests:
                    complete = False; break
                # Charge every visited pair, including broad-phase rejection, so
                # large disjoint meshes cannot evade the computational budget.
                count += 1; evaluated += 1
                td = bounds_distance(cap['triangleBounds'][a][i], cap['triangleBounds'][b][j])
                if td > max(radius, best[0] if best else radius): continue
                d, p, q = triangle_distance(ta, tb)
                if best is None or d < best[0]: best = (d, p, q, i, j)
                overlap = coplanar_overlap(ta, tb, overlap_tolerance)
                if overlap and len(overlaps) < 8: overlaps.append({'triangleA': i, 'triangleB': j, **overlap})
            if not complete: break
        record = {'id': 'geometry-'+str(a)+'-'+str(b), 'kind': 'geometric_proximity', 'partIds': [a, b],
                  'status': 'measured' if complete else 'missing_evidence', 'basis': 'actual_native_triangle_pairs',
                  'boundsLowerDistanceM': lower, 'trianglePairTests': evaluated, 'complete': complete,
                  'evidence': _evidence(cap, [a, b]), 'limitations': ['Proximity is not an expected seam, attachment, visible duplicate or physical-support conclusion.']}
        if best:
            record.update(distanceM=best[0], minimumSurfaceDistanceM=best[0] if best[0] <= radius else None,
                          distanceMeaning='minimum_surface_distance_within_neighbor_radius' if best[0] <= radius else 'closest_tested_witness_outside_radius_not_a_global_minimum',
                          withinNeighborDistance=True if best[0] <= radius else False if complete else None,
                          witnessAWorld=list(best[1]), witnessBWorld=list(best[2]), triangleA=best[3], triangleB=best[4])
            na, nb = normal(triangles[a][best[3]]), normal(triangles[b][best[4]])
            if na and nb: record['nearestTriangleNormalAngleDegrees'] = math.degrees(math.acos(max(-1, min(1, dot(na, nb)))))
        else:
            record['distanceLowerBoundM'] = radius
            record['withinNeighborDistance'] = False if complete else None
        if overlaps: record['overlapCandidates'] = overlaps
        # Independent free-edge witnesses discover possible undeclared gaps.
        # They are candidates only: not every pair of nearby edges should meet.
        gaps = []
        cached_topology = cap.setdefault('_topology', {})
        if a not in cached_topology: cached_topology[a] = topology(triangles[a])
        if b not in cached_topology: cached_topology[b] = topology(triangles[b])
        ea = cached_topology[a]['boundaryEdgeSamples']; eb = cached_topology[b]['boundaryEdgeSamples']
        for x in ea[:24]:
            ux = sub(x['b'], x['a'])
            for y in eb[:24]:
                uy = sub(y['b'], y['a'])
                if norm(ux) <= EPS or norm(uy) <= EPS or abs(dot(ux, uy)/(norm(ux)*norm(uy))) < .9: continue
                p, q = segment_segment(x['a'], x['b'], y['a'], y['b']); distance = norm(sub(p, q))
                if overlap_tolerance < distance <= radius:
                    gaps.append({'distanceM': distance, 'witnessAWorld': list(p), 'witnessBWorld': list(q),
                                 'edgeA': x, 'edgeB': y})
                if len(gaps) >= 3: break
            if len(gaps) >= 3: break
        if gaps: record['boundaryGapCandidates'] = gaps
        record['boundaryCandidateCoverage'] = {'mode': 'finite_sampled', 'maxEdgesPerPart': 24,
                                               'limitations': ['Only tolerance-welded free edges sampled; full edge spans and extrema are not certified.']}
        records.append(record)
        if not complete: pending.append({'partIds': [a, b], 'reason': 'triangle_pair_budget_exceeded'})
    return records, pending, {'candidatePairCount': len(candidates), 'trianglePairTests': count}


def _native_relations(cap, subject):
    parts = cap['parts']; relations = []
    seen = set()
    for key, part in parts.items():
        pid = int(key)
        for other in part.get('connectedPartIds', []):
            if str(other) not in parts or (pid not in subject and other not in subject): continue
            pair = tuple(sorted((pid, other)))
            if pair in seen: continue
            seen.add(pair); relations.append({'kind': 'native_attachment', 'partIds': list(pair), 'basis': 'snapshot.connectedPartIds',
                                             'status': 'observed', 'limitations': ['Attachment does not prove surface contact or support.']})
    groups = {parts[str(i)].get('symmetryId') for i in subject if str(i) in parts}-{None, 0}
    for group in sorted(groups, key=str):
        ids = sorted(int(key) for key, part in parts.items() if part.get('symmetryId') == group)
        relations.append({'kind': 'native_symmetry_group', 'groupId': group, 'partIds': ids, 'status': 'observed',
                          'basis': 'snapshot.symmetryId', 'limitations': ['A symmetry group does not prove equal actual geometry.']})
    def nodes(node):
        if not isinstance(node, dict): return
        yield node
        for child in node.get('children', []): yield from nodes(child)
    xml_present = bool(cap['snapshot'].get('xml'))
    for key, part in parts.items():
        pid = int(key)
        for node in nodes(part.get('serializedState')):
            attrs = node.get('attributes', {})
            # Match the existing structure planner's explicit reference allowlist.
            for attribute in ('customPartIds', 'targetPartIds', 'hostPartId', 'parentPartId', 'targetPartId', 'cuttingPartIds'):
                if attribute not in attrs: continue
                try: targets = sorted({int(x.strip()) for x in str(attrs[attribute]).split(',') if x.strip()})
                except ValueError:
                    if pid in subject: relations.append({'kind': 'nested_native_dependency', 'partIds': [pid], 'status': 'unknown',
                                                         'attribute': attribute, 'reason': 'Unparsed native references'})
                    continue
                if pid in subject or subject.intersection(targets):
                    relations.append({'kind': 'nested_native_dependency', 'partIds': sorted(set([pid]+targets)),
                                      'ownerPartId': pid, 'targetPartIds': targets, 'attribute': attribute,
                                      'status': 'observed', 'basis': 'native_serialized_allowlist',
                                      'limitations': ['Reference declaration does not prove spatial contact or the evaluated native effect.']})
            if node.get('tag') == 'PartTargeting.State':
                mode = attrs.get('targetMode')
                if mode != 'Custom':
                    relations.append({'kind': 'implicit_cut_or_target_dependency', 'partIds': [pid], 'status': 'unknown',
                                      'basis': 'native_targeting_state', 'targetMode': mode,
                                      'limitations': ['Implicit target ownership requires same-state native evaluation.']})
                else:
                    target_field = 'customPartIds' if 'customPartIds' in attrs else 'partIds'
                    legacy = target_field == 'partIds'
                    try: targets = sorted({int(x.strip()) for x in str(attrs.get(target_field, '')).split(',') if x.strip()})
                    except (ValueError, AttributeError):
                        relations.append({'kind': 'cut_or_target_dependency', 'partIds': [pid], 'status': 'unknown', 'reason': 'Unparsed custom targets'}); continue
                    if pid in subject or subject.intersection(targets):
                        relations.append({'kind': 'cut_or_target_dependency', 'partIds': sorted(set([pid]+targets)), 'ownerPartId': pid,
                                          'targetPartIds': targets, 'status': 'observed' if targets else 'observed_empty_targets',
                                          'basis': 'legacy_partIds_targeting_fallback' if legacy else 'native_customPartIds_targeting',
                                          'targetAttribute': target_field, 'legacyFallback': legacy,
                                          'limitations': ['Target declaration does not certify actual cut result.']+
                                              (['Legacy partIds fallback is retained for old fixtures; current native Custom targeting uses customPartIds.'] if legacy else [])})
    return relations, xml_present


def _functional_surface_absence(part):
    """Only explicitly known native functional absence, never AABB heuristics."""
    if 'hole' in str(part.get('type', '')).lower(): return True
    def visit(node):
        if not isinstance(node, dict): return False
        if node.get('tag') == 'ProceduralWindow.State':
            value = node.get('attributes', {}).get('hideGlass')
            if value is True or isinstance(value, str) and value.lower() == 'true': return True
        return any(visit(child) for child in node.get('children', []))
    return visit(part.get('serializedState'))


def _mesh_plan_review(plan, cap):
    """Reuse the skill's real mesh audit, recomputing rather than trusting booleans."""
    path = Path(__file__).resolve().parents[1]/'skills/sp2-build-assistant/scripts/native_mesh_review.py'
    if not path.is_file(): path = Path.home()/'.agents/skills/sp2-build-assistant/scripts/native_mesh_review.py'
    if not path.is_file():
        return [{'id': 'native-review-plan', 'kind': 'native_mesh_review', 'status': 'missing_evidence', 'partIds': [],
                 'reason': 'The native mesh audit helper is not available; a supplied passed flag is not evidence'}]
    spec = importlib.util.spec_from_file_location('_regional_native_mesh_review', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    try: result = module.audit(_document(plan, 'reviewPlan'), cap['mesh'])
    except (ValueError, KeyError, TypeError, ArithmeticError) as error:
        return [{'id': 'native-review-plan', 'kind': 'native_mesh_review', 'status': 'missing_evidence', 'partIds': [], 'reason': str(error)}]
    rows = []
    declarations = [x for name in ('seams', 'silhouettes', 'curves', 'trimProfiles') for x in plan.get(name, [])]
    for check in result.get('checks', []):
        declaration = next((x for x in declarations if x.get('name') == check.get('name')), {})
        ids = sorted({pid for field in ('a', 'b', 'partIds', 'upperPartIds', 'lowerPartIds') for pid in declaration.get(field, [])})
        rows.append({'id': check['name'], 'kind': check['kind'], 'goalId': declaration.get('goalId'), 'partIds': ids,
                     'boundaryIds': declaration.get('boundaryIds', [check['name']]),
                     'status': 'passed' if check['passed'] else 'failed', 'expected': declaration, 'measured': _finite(check),
                     'evidence': _evidence(cap, ids, reference_bound=True), 'limitations': result['limitations']})
    return rows


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value): return None
    if isinstance(value, dict): return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_finite(v) for v in value]
    return value


def _scoped_coverage_summary(checks, cap, coverage, findings, channel):
    """A goal-domain certificate can complete without certifying the whole craft.

    Keep the global unknown inventory intact. This summary is explicitly about
    the declared goal/interface domains and direct affected IDs, rather than an
    accidental promotion of every captured surface to acceptance.
    """
    ids = set(coverage.get(channel+'PartIds', []))
    required = [c for c in checks if c.get('goalId')]
    covered = {pid for c in required if c['status'] == 'passed' for pid in c.get('partIds', [])}
    blocking = [c for c in checks if c['status'] != 'passed' and c.get('kind') != 'full_region_coverage']
    missing = sorted(ids & set(coverage.get('missingMeshPartIds', [])))
    # Pair/propagation failures are already represented as coverage checks. An
    # Every impact channel needs completed discovery; otherwise even a passed
    # discovered neighbor would hide additional uncaptured indirect pieces.
    search_complete = coverage.get('impactDiscoveryComplete') is True
    no_impact = channel == 'impact' and not ids and not blocking and not findings and search_complete
    complete = (no_impact or bool(required) and ids <= covered
                and all(c['status'] == 'passed' and c.get('coverageMode') == 'complete' for c in required))
    complete = complete and not missing and not blocking and not findings
    discovery_missing = channel == 'impact' and not search_complete
    complete = complete and not discovery_missing
    return {'status': 'complete' if complete else 'incomplete' if missing or blocking or discovery_missing else 'finite_sampled',
            'partIds': sorted(ids), channel+'PartIds': sorted(ids), 'missingMeshPartIds': missing,
            'boundaryIds': sorted({bid for c in required for bid in c.get('boundaryIds', [])}),
            'scope': 'Declared goal/interface domains and discovered affected pieces only; all-region certification remains separate',
            'certifiedGoalIds': sorted({c['goalId'] for c in required if c['status'] == 'passed' and c.get('coverageMode') == 'complete'}),
            'unobserved': [] if complete else ['Some affected goal/interface domains are unresolved or only finitely sampled.']+(['Indirect discovery is incomplete; additional affected parts may be uncaptured.'] if discovery_missing else []),
            'completeCraftAcceptance': False,
            'noImpactReason': 'Completed before/after proximity, shared-boundary, symmetry and cut-dependency discovery found no indirect piece within this captured scope' if no_impact else None}


def _review_wrapper(checks, cap, coverage, findings, channel='subject', discovery=None):
    evidences = {check['evidence']['id']: check['evidence'] for check in checks if check.get('evidence')}
    for finding in findings:
        ev = finding.get('evidence')
        if ev: evidences[ev['id']] = ev
    statuses = {'passed': 'pass', 'failed': 'fail', 'excluded': 'excluded', 'needs_review': 'unknown', 'missing_evidence': 'unknown'}
    issues = [{'id': x['id'], 'status': 'fail' if x['status'] == 'failed' else 'unknown',
               'partIds': x.get('partIds', []), 'goalId': x.get('goalId'), 'expected': x.get('expected'),
               'verification': x.get('kind'), 'evidenceIds': [x['evidence']['id']] if x.get('evidence') else [],
               'reason': x.get('reason'), 'relation': x.get('kind')} for x in checks
              if x['status'] in ('failed', 'needs_review', 'missing_evidence') and
              (x.get('kind') != 'full_region_coverage' or x.get('goalId'))]
    issues.extend({'id': x['id'], 'status': 'unknown', 'partIds': x['partIds'], 'evidenceIds': [x['evidence']['id']],
                   'reason': x.get('reason'), 'relation': x['kind'], 'witnessWorld': x.get('witnessWorld'),
                   'measured': deepcopy(x.get('measured')), 'expected': deepcopy(x.get('expected')),
                   'inspectionHints': {'kind': x['kind'], 'witnessWorld': x.get('witnessWorld'),
                                       'measured': deepcopy(x.get('measured')), 'automaticDeletionAllowed': False}}
                  for x in findings)
    summary = _scoped_coverage_summary(checks, cap, coverage, findings, channel)
    return {'identity': cap['identity'], 'partHashes': cap['partHashes'], 'evidence': list(evidences.values()),
            'checks': [{**x, 'status': statuses[x['status']], 'evidenceIds': [x['evidence']['id']] if x.get('evidence') else [],
                        'boundaryIds': x.get('boundaryIds', [])} for x in checks],
            'coverage': [{'goalId': x['goalId'], 'status': statuses[x['status']], 'evidenceIds': [x['evidence']['id']],
                          'partIds': x.get('partIds', []), 'boundaryIds': x.get('boundaryIds', []),
                          'coverageMode': x.get('coverageMode', 'finite_sampled'), 'limitations': x.get('limitations', [])}
                         for x in checks if x.get('goalId') and x.get('evidence')],
            'issues': issues, 'coverageSummary': summary, 'noImpactReason': summary.get('noImpactReason'),
            **({'discovery': deepcopy(discovery)} if discovery is not None else {})}


def review(payload, context=None):
    from boundary_review import (boundary_review, event_stations, reference_review,
                                 replacement_mapping, propagate_impact)
    cap = capture(payload.get('snapshot'), payload.get('mesh') or payload.get('actualMesh'))
    cap['criterionReferenceHash'] = payload.get('referenceHash')
    subject = set(_ids(payload.get('partIds')))
    absent = subject-{int(i) for i in cap['parts']}
    if absent: raise ReferenceError('part_not_found', 'Subject parts are missing from current snapshot', partIds=sorted(absent))
    budget = payload.get('budget', {})
    radius = _number(payload.get('neighborDistanceM', .05), 'neighborDistanceM')
    max_pairs = _integer(budget.get('maxCandidatePairs', 128), 'maxCandidatePairs', 1)
    max_tests = _integer(budget.get('maxTrianglePairTests', 100000), 'maxTrianglePairTests', 1)
    if max_pairs > 2048 or max_tests > 2000000: raise ReferenceError('invalid_input', 'Regional computational budget exceeds safe local ceiling')
    relations, pending, stats = _relations(cap, subject, radius, max_pairs, max_tests, _number(payload.get('overlapToleranceM', .0001), 'overlapToleranceM'))
    native, xml_present = _native_relations(cap, subject); relations += native
    impacted = {pid for r in relations if r.get('kind') != 'geometric_proximity' or r.get('withinNeighborDistance') is not False
                for pid in r['partIds']}-subject
    # User-declared interfaces/sections close the scope even if distant or newly
    # separated geometry is no longer selected by a proximity broad phase.
    affected_ids = payload.get('affectedPartIds', [])
    if not isinstance(affected_ids, list) or any(type(i) is not int or i < 0 for i in affected_ids):
        raise ReferenceError('invalid_input', 'affectedPartIds must be an array of nonnegative integer IDs')
    declared = set(affected_ids)
    for spec in payload.get('expectedInterfaces', []):
        if isinstance(spec, dict): declared.update(spec.get('a', [])+spec.get('b', []))
    for spec in payload.get('sections', []) or []:
        if isinstance(spec, dict): declared.update(spec.get('partIds', []))
    if payload.get('reviewPlan'):
        plan = _document(payload['reviewPlan'], 'reviewPlan')
        for field in ('seams', 'silhouettes', 'curves', 'trimProfiles'):
            for item in plan.get(field, []):
                for key in ('a', 'b', 'partIds', 'upperPartIds', 'lowerPartIds'): declared.update(item.get(key, []))
    if any(type(i) is not int or i < 0 for i in declared): raise ReferenceError('invalid_input', 'Declared affected part IDs must be nonnegative integers')
    impacted |= declared-subject
    baseline_relations = []; before_cap = None; previous = payload.get('baseline')
    if previous:
        previous = _document(previous, 'baseline')
        before_cap = capture(previous.get('snapshot'), previous.get('mesh') or previous.get('actualMesh'))
        if before_cap['identity']['craftSessionId'] != cap['identity']['craftSessionId']:
            raise ReferenceError('evidence_session_mismatch', 'Before/after comparisons require the same craft session and explicit rebind outside this review')
        if before_cap['identity']['revision'] > cap['identity']['revision']:
            raise ReferenceError('evidence_order_mismatch', 'Baseline revision cannot be later than current revision')
        old_subject = set(_ids(previous.get('partIds', sorted(subject)), 'baseline.partIds'))
        baseline_relations, before_pending, before_stats = _relations(before_cap, old_subject, radius, max_pairs, max_tests, .0001)
        before_native, _ = _native_relations(before_cap, old_subject); baseline_relations += before_native
        old_neighbors = {pid for r in baseline_relations if r.get('kind') != 'geometric_proximity' or r.get('withinNeighborDistance') is not False
                         for pid in r['partIds']}-old_subject
        mapping, semantic_replacements = replacement_mapping(payload, before_cap, cap)
        impacted |= {current for old in old_neighbors for current in mapping.get(old, [old])}
        pending += [{'phase': 'before', **x} for x in before_pending]
        stats['before'] = before_stats
    else:
        mapping, semantic_replacements = replacement_mapping(payload, None, cap)
    # Geometry interfaces can propagate beyond the first selected neighbor.
    # Native attachment edges remain informative, but are intentionally not used
    # to flood-fill the craft: remote roots do not imply geometric coupling.
    all_native, _ = _native_relations(cap, {int(i) for i in cap['parts']})
    propagation = propagate_impact(cap, subject|declared, payload, all_native)
    impacted |= set(propagation['partIds'])-subject
    relations += propagation['relations']
    # Show dependencies of newly reached pieces as well as the initial subject.
    relation_keys = {digest(x) for x in relations}
    for row in all_native:
        if set(row['partIds']) & set(propagation['partIds']) and digest(row) not in relation_keys:
            relations.append(row); relation_keys.add(digest(row))
    pending += propagation['pending']
    before_propagation = None
    if before_cap:
        before_native, _ = _native_relations(before_cap, {int(i) for i in before_cap['parts']})
        before_discovery_options = {'neighborDistanceM': radius, 'budget': deepcopy(budget), **previous}
        before_discovery_options['budget'] = {**budget, **previous.get('budget', {})}
        before_propagation = propagate_impact(before_cap, old_subject, before_discovery_options, before_native, 'before')
        impacted |= {new for old in before_propagation['partIds'] for new in mapping.get(old, [old])}-subject
        baseline_relations += before_propagation['relations']
        pending += before_propagation['pending']
    boundary = boundary_review(cap, subject|impacted, payload)
    missing = sorted((subject|impacted)-set(cap['triangles']))
    subject_checks = []; impact_checks = []; findings = []
    for pid in sorted(subject|impacted):
        check = {'id': 'geometry-availability-'+str(pid), 'kind': 'geometry_availability', 'partIds': [pid], 'evidence': _evidence(cap, [pid])}
        if pid in cap['triangles']:
            check.update(status='passed', measured={'triangleCount': len(cap['triangles'][pid])},
                         limitations=['Geometry availability alone does not verify shape, material or continuity.'])
        else:
            part = cap['parts'].get(str(pid), {}); functional = 'hole' in str(part.get('type', '')).lower() or 'hole' in str(part.get('typeName', '')).lower()
            check.update(status='missing_evidence', reason='Functional part has no exported surface; dependency effect still needs inspection' if functional else 'Current mesh is absent (hidden, excluded, retired or uncaptured)')
        (subject_checks if pid in subject else impact_checks).append(check)
    interfaces = payload.get('expectedInterfaces', [])
    if not isinstance(interfaces, list): raise ReferenceError('invalid_input', 'expectedInterfaces must be an array')
    for index, spec in enumerate(interfaces):
        if not isinstance(spec, dict): raise ReferenceError('invalid_input', 'Expected interface must be an object')
        if any(k in spec for k in ('boundaryPlane', 'boundaryPlaneA', 'boundaryPlaneB', 'boundaryEdgeIdsA', 'boundaryEdgeIdsB', 'boundarySelection')):
            continue  # Complete-domain check below supersedes point-only sampling.
        check = _interface(spec, cap, index)
        (impact_checks if set(check['partIds'])-subject else subject_checks).append(check)
    for check in boundary['checks']:
        (impact_checks if set(check['partIds'])-subject else subject_checks).append(check)
    if payload.get('reviewPlan'):
        plan = _document(payload['reviewPlan'], 'reviewPlan')
        for check in _mesh_plan_review(plan, cap):
            (impact_checks if set(check['partIds'])-subject else subject_checks).append(check)
    for r in relations:
        for j, overlap in enumerate(r.get('overlapCandidates', [])):
            findings.append({'id': r['id']+'-overlap-'+str(j), 'kind': 'near_coplanar_overlap_candidate', 'status': 'needs_review',
                             'partIds': r['partIds'], 'witnessWorld': overlap['witnessWorld'], 'measured': overlap,
                             'reason': 'Actual triangles have positive-area projected overlap; visible duplication versus embedded cap is unresolved',
                             'evidence': r['evidence'], 'automaticDeletionAllowed': False})
        for j, gap in enumerate(r.get('boundaryGapCandidates', [])):
            findings.append({'id': r['id']+'-boundary-gap-'+str(j), 'kind': 'nearby_free_edge_gap_candidate', 'status': 'needs_review',
                             'partIds': r['partIds'], 'witnessWorld': list(mul(add(gap['witnessAWorld'], gap['witnessBWorld']), .5)),
                             'measured': gap, 'reason': 'Nearby parallel free edges are separated; intended continuity is not yet established',
                             'evidence': r['evidence'], 'automaticDeletionAllowed': False})
        if r.get('kind') == 'geometric_shared_boundary_candidate':
            candidates = [s for s in r.get('spans', []) if s['distanceM'] > _number(payload.get('overlapToleranceM', .0001), 'overlapToleranceM')]
            if candidates:
                # Every non-diagonal edge pair has been visited or is explicitly
                # budget-incomplete. Present one strongest witness per pair;
                # complete spans remain in the relation for progressive reads.
                gap = max(candidates, key=lambda s: s['distanceM'])
                findings.append({'id': r['id']+'-full-edge-gap', 'kind': 'nearby_boundary_span_gap_candidate',
                    'status': 'needs_review', 'partIds': r['partIds'],
                    'witnessWorld': list(mul(add(gap['witnessAWorld'], gap['witnessBWorld']), .5)),
                    'measured': gap, 'reason': 'Actual parallel boundary/crease spans are separated; outer ownership and intended continuity need review',
                    'evidence': r['evidence'], 'automaticDeletionAllowed': False})
    for item in pending:
        impact_checks.append({'id': 'unmeasured-'+digest(item)[:16], 'kind': 'geometric_neighbor_coverage', 'status': 'missing_evidence',
                              'partIds': item['partIds'], 'reason': item['reason'], 'evidence': _evidence(cap, item['partIds'])})
    sections = []
    section_tests = 0
    max_section_tests = _integer(budget.get('maxSectionTriangleTests', 500000), 'maxSectionTriangleTests', 1)
    if max_section_tests > 5000000: raise ReferenceError('invalid_input', 'Section triangle budget exceeds local ceiling')
    specs = payload.get('sections'); station_coverage = []
    if specs is None:
        axis = _integer(payload.get('sectionAxis', 2), 'sectionAxis')
        if axis > 2: raise ReferenceError('invalid_input', 'sectionAxis must be 0..2')
        specs = []
        for pid in sorted(subject):
            if pid in cap['bounds']:
                low, high = cap['bounds'][pid]['min'][axis], cap['bounds'][pid]['max'][axis]
                events = event_stations(cap['triangles'][pid], axis, budget.get('maxAutomaticStations', 128))
                station_coverage.append({'partId': pid, 'axis': axis, **events})
                specs.append({'partIds': [pid], 'axis': axis, 'stations': [x['stationM'] for x in events['stations']],
                              'selection': 'all_vertex_events_and_independent_event_interval_interiors'})
    if not isinstance(specs, list) or len(specs) > 128: raise ReferenceError('invalid_input', 'sections must contain at most 128 requests')
    for spec in specs:
        ids = _ids(spec.get('partIds'), 'sections.partIds'); stations = spec.get('stations', [])
        if not isinstance(stations, list) or not stations or len(stations) > 4096: raise ReferenceError('invalid_input', 'Section stations must contain 1..4096 positions')
        for pid in ids:
            for station in stations:
                if pid not in cap['triangles']:
                    sections.append({'partId': pid, 'status': 'missing_evidence', 'stationM': station}); continue
                if section_tests+len(cap['triangles'][pid]) > max_section_tests:
                    sections.append({'partId': pid, 'status': 'missing_evidence', 'stationM': station, 'reason': 'section_triangle_budget_exceeded'})
                    continue
                section_tests += len(cap['triangles'][pid])
                result = section(cap['triangles'][pid], spec.get('axis', 2), station)
                sections.append({'partId': pid, 'status': 'measured' if result['segments'] else 'no_intersection', 'selection': spec.get('selection', 'declared'), **result})
    reference = reference_review(cap, payload, sections)
    for check in reference.get('checks', []):
        (impact_checks if set(check['partIds'])-subject else subject_checks).append(check)
    # Preserve actual witnesses for diagnosis; diagnostic hints do not supply
    # or override a goal's verification requirements.
    for check in boundary['checks']:
        measurement = check.get('measured', {})
        for direction in ('aToB', 'bToA'):
            certificate = measurement.get(direction, {})
            witness = certificate.get('witness')
            if certificate.get('status') != 'failed' or not witness: continue
            delta = sub(witness['sourceWorld'], witness['targetWorld'])
            kind = 'boundary_width_step_candidate' if abs(delta[0]) >= max(abs(delta[1]), abs(delta[2])) else 'boundary_gap_candidate'
            findings.append({'id': check['id']+'-'+direction, 'kind': kind, 'status': 'needs_review',
                'partIds': check['partIds'], 'goalId': check.get('goalId'), 'witnessWorld': witness['sourceWorld'],
                'measured': witness, 'reason': 'Actual full-boundary distance exceeds its explicitly declared tolerance',
                'evidence': check['evidence'], 'automaticDeletionAllowed': False})
        for index, fold in enumerate(measurement.get('normalMismatches', [])):
            if measurement.get('intentionalCrease'): continue
            findings.append({'id': check['id']+'-fold-'+str(index), 'kind': 'outer_boundary_fold_candidate',
                'status': 'needs_review', 'partIds': check['partIds'], 'goalId': check.get('goalId'),
                'witnessWorld': fold['witnessAWorld'], 'measured': fold,
                'reason': 'Selected outer boundary normals exceed the declared smooth-interface angle',
                'evidence': check['evidence'], 'automaticDeletionAllowed': False})
    for check in reference.get('checks', []):
        for direction, kind in (('actualToReference', 'extra_geometry_or_protrusion_candidate'), ('referenceToActual', 'missing_reference_shape_candidate')):
            result = check.get('measured', {}).get(direction, {})
            if result.get('status') == 'failed' and result.get('witness'):
                witness = result['witness']
                findings.append({'id': check['id']+'-'+direction, 'kind': kind, 'status': 'needs_review',
                    'partIds': check['partIds'], 'goalId': check.get('goalId'), 'witnessWorld': witness['sourceWorld'] if direction == 'actualToReference' else witness['targetWorld'],
                    'measured': witness, 'reason': 'Actual/reference directed surface distance exceeds a declared shape tolerance',
                    'evidence': check['evidence'], 'automaticDeletionAllowed': False})
    checks = subject_checks+impact_checks
    unobserved = ['Automatic enumeration covers captured polygonal mesh events only; hidden/unexported surfaces and underlying smooth curvature remain unobserved.',
                  'Native appearance, collider behavior, physical support and aesthetic/reference fidelity require separate evidence.',
                  'Automatically discovered proximity has no implied continuity expectation; declare interfaces or review the candidate.']
    if not xml_present: unobserved.append('Snapshot has no authored XML: nested/implicit cut dependencies may be incomplete.')
    if cap['mesh'].get('complete') is False: unobserved.append('Native export explicitly reports incomplete capture coverage.')
    elif cap['mesh'].get('complete') is not True: unobserved.append('Native export does not explicitly declare complete coverage.')
    if not interfaces and not payload.get('reviewPlan'): unobserved.append('No user/reference-derived continuity or shape acceptance checks were supplied.')
    if any(s['status'] == 'missing_evidence' for s in sections): unobserved.append('One or more actual sections are unavailable or exceed the finite computational budget.')
    for inventory in boundary['parts']:
        if inventory['coverage']['status'] != 'complete':
            check = {'id': 'edge-enumeration-'+str(inventory['partId']), 'kind': 'automatic_boundary_coverage', 'status': 'missing_evidence',
                     'partIds': [inventory['partId']], 'reason': 'Complete native edge enumeration exceeds the declared budget',
                     'evidence': _evidence(cap, [inventory['partId']])}
            (subject_checks if inventory['partId'] in subject else impact_checks).append(check)
    for entry in station_coverage:
        if entry['coverage']['status'] != 'complete':
            subject_checks.append({'id': 'station-enumeration-'+str(entry['partId']), 'kind': 'automatic_section_coverage', 'status': 'missing_evidence',
                'partIds': [entry['partId']], 'reason': 'Some mesh event or independent interval stations exceed the station budget',
                'measured': entry['coverage'], 'evidence': _evidence(cap, [entry['partId']])})
    for pid in sorted(impacted):
        if not any(x['kind'] != 'geometry_availability' and pid in x.get('partIds', []) for x in impact_checks):
            impact_checks.append({'id': 'impact-inspection-'+str(pid), 'kind': 'indirect_part_inspection', 'status': 'missing_evidence',
                                  'partIds': [pid], 'reason': 'An indirect neighbor was discovered but its affected shape/interface has no acceptance check',
                                  'evidence': _evidence(cap, [pid])})
    # Require explicit missing-coverage records, not just prose, for the loop.
    subject_checks.append({'id': 'full-region-coverage', 'kind': 'full_region_coverage', 'status': 'missing_evidence',
                           'partIds': sorted(subject), 'reason': 'Finite sections and proximity discovery do not cover every full edge span, curvature extremum, inner face or reference mismatch',
                           'evidence': _evidence(cap, sorted(subject))})
    checks = subject_checks+impact_checks
    stats['sectionTriangleTests'] = section_tests
    coverage = {'status': 'incomplete' if missing or pending or boundary['coverage']['status'] != 'complete' or any(x['coverage']['status'] != 'complete' for x in station_coverage) or any(s['status'] == 'missing_evidence' for s in sections) else 'issues_found' if any(x['status'] == 'failed' for x in checks) or findings else 'finite_sampled',
                'subjectPartIds': sorted(subject), 'impactPartIds': sorted(impacted), 'missingMeshPartIds': missing,
                'scope': 'Captured native triangles, bounded pair discovery and finite declared/automatic section stations only',
                'candidateBudget': stats, 'unobserved': unobserved, 'hasCandidateOrFailedChecks': bool(findings or any(x['status'] == 'failed' for x in checks)),
                'completeCraftAcceptance': False}
    uncaptured_current = sorted(int(pid) for pid, part in cap['parts'].items()
                                if int(pid) not in cap['triangles'] and not _functional_surface_absence(part))
    uncaptured_before = sorted(int(pid) for pid, part in before_cap['parts'].items()
                               if int(pid) not in before_cap['triangles'] and not _functional_surface_absence(part)) if before_cap else []
    coverage['uncapturedInventoryPartIds'] = uncaptured_current
    coverage['beforeUncapturedInventoryPartIds'] = uncaptured_before
    coverage['captureScope'] = deepcopy(cap['mesh'].get('captureScope'))
    coverage['impactDiscoveryComplete'] = not pending and not uncaptured_current and not uncaptured_before and propagation['coverage']['status'] == 'complete' and (
        before_propagation is None or before_propagation['coverage']['status'] == 'complete') and cap['mesh'].get('complete') is True
    discovery = {'source': 'regional_geometry', 'identity': cap['identity'],
                 'complete': coverage['impactDiscoveryComplete'],
                 'inventoryPartIds': sorted(map(int, cap['parts'])), 'geometryStamp': cap['geometryStamp'],
                 'coordinateFrame': {'frame': 'world', 'units': 'metres'},
                 'captureScope': coverage['captureScope'],
                 'beforeIdentity': before_cap['identity'] if before_cap else None,
                 'beforeInventoryPartIds': sorted(map(int, before_cap['parts'])) if before_cap else [],
                 'beforeComplete': bool(before_cap and before_cap['mesh'].get('complete') is True and not uncaptured_before
                                        and not before_pending and before_propagation['coverage']['status'] == 'complete')}
    if uncaptured_current or uncaptured_before:
        coverage['status'] = 'incomplete'
        unobserved.append('Capture completeness applies to its declared captureScope; uncaptured snapshot pieces leave geometric impact discovery unresolved.')
    changes = []
    if before_cap:
        for pid in sorted(subject|impacted):
            old, new = before_cap['parts'].get(str(pid)), cap['parts'].get(str(pid))
            old_mesh, new_mesh = before_cap['triangles'].get(pid), cap['triangles'].get(pid)
            changes.append({'partId': pid, 'authoredChanged': old != new, 'geometryChanged': old_mesh != new_mesh,
                            'beforeBounds': before_cap['bounds'].get(pid), 'afterBounds': cap['bounds'].get(pid),
                            'identityContinuity': 'retired' if new is None else 'new' if old is None else 'needs_mapping_review' if old.get('type') != new.get('type') else 'same_numeric_id_only',
                            'limitations': ['Numeric ID and name alone do not prove stable semantic ownership across replacement.']})
        for row in semantic_replacements:
            old_triangles = [t for pid in row['fromPartIds'] for t in before_cap['triangles'].get(pid, [])]
            new_triangles = [t for pid in row['toPartIds'] for t in cap['triangles'].get(pid, [])]
            changes.append({**row, 'partIds': row['toPartIds'], 'identityContinuity': 'explicit_semantic_replacement',
                'authoredChanged': True, 'geometryChanged': old_triangles != new_triangles,
                'beforeBounds': bounds(old_triangles), 'afterBounds': bounds(new_triangles),
                'limitations': ['Explicit ownership mapping preserves scope; it does not prove equal shape or valid replacement coverage.']})
    report = {'schemaVersion': 1, 'kind': 'sp2build.regionalReview', 'identity': cap['identity'], 'geometryStamp': cap['geometryStamp'],
              'coordinateFrame': {'units': 'm', 'frameToWorldRows': WORLD}, 'partHashes': cap['partHashes'],
              'subjectChecks': subject_checks, 'impactChecks': impact_checks, 'coverage': coverage, 'findings': findings,
              'relations': relations, 'baselineRelations': baseline_relations, 'sections': sections, 'changes': changes,
              'boundaryReview': boundary, 'sectionCoverage': station_coverage,
              'impactPropagation': {'after': propagation, 'before': before_propagation, 'semanticReplacements': semantic_replacements},
              'impactDiscovery': discovery,
              'reference': reference,
              'limitations': unobserved}
    report['subjectReview'] = _review_wrapper(subject_checks, cap, coverage, [x for x in findings if set(x['partIds']) <= subject], 'subject')
    report['impactReview'] = _review_wrapper(impact_checks, cap, coverage, [x for x in findings if set(x['partIds'])-subject], 'impact', discovery)
    return _finite(report)


def dispatch(action, payload, context=None):
    if action not in ('regional.review', 'geometry.review'):
        raise ReferenceError('unsupported_command', 'Unsupported regional observation action', action=action)
    return review(payload, context=context)
