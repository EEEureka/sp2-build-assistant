"""Finite checks on exported native meshes; no game writes or saved-craft access.

Run: python native_mesh_review.py review-plan.json --output review.json
The plan binds the mesh to an observed identity and declares every required check.
This supplements native views, topology/overlap checks and source comparison.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def add(a, b): return tuple(x+y for x, y in zip(a, b))
def mul(a, k): return tuple(x*k for x in a)
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a, a))


def point_triangle(p, tri):
    a, b, c = tri
    ab, ac = sub(b, a), sub(c, a)
    n = cross(ab, ac)
    nn = dot(n, n)
    if nn <= 1e-20:
        return math.inf, None
    n = mul(n, 1/math.sqrt(nn))
    d = dot(sub(p, a), n)
    q = sub(p, mul(n, d))
    aq = sub(q, a)
    aa, bb, cc = dot(ab, ab), dot(ab, ac), dot(ac, ac)
    det = aa*cc-bb*bb
    u = (cc*dot(aq, ab)-bb*dot(aq, ac))/det
    v = (aa*dot(aq, ac)-bb*dot(aq, ab))/det
    if u >= -1e-7 and v >= -1e-7 and u+v <= 1+1e-7:
        return abs(d), n
    best = math.inf
    for x, y in ((a, b), (b, c), (c, a)):
        e = sub(y, x)
        if dot(e, e) <= 1e-20:
            continue
        t = max(0, min(1, dot(sub(p, x), e)/dot(e, e)))
        best = min(best, norm(sub(p, add(x, mul(e, t)))))
    return best, n


def nearest(p, triangles, normal_hint):
    hint = mul(normal_hint, 1/norm(normal_hint))
    best = (math.inf, None)
    for tri in triangles:
        d, n = point_triangle(p, tri)
        # Exclude end caps and opposite/inner faces at the shared edge.
        if n is not None and dot(n, hint) >= .8 and d < best[0]:
            best = d, n
    return best


def envelope(triangles, height, height_axis, outline_axis):
    values = []
    for tri in triangles:
        for a, b in zip(tri, (tri[1], tri[2], tri[0])):
            da = a[height_axis]-height
            db = b[height_axis]-height
            if abs(da) <= 1e-8:
                values.append(a[outline_axis])
            if da*db < 0:
                t = -da/(db-da)
                values.append(a[outline_axis]+t*(b[outline_axis]-a[outline_axis]))
    return (min(values), max(values)) if values else None


def exposed_trim(triangles, station, axis, height_axis, side_axis, side, upper):
    """One exposed trim contour, excluding inner surfaces and longitudinal caps."""
    points = []
    for tri in triangles:
        n = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
        if norm(n) <= 1e-12 or side*n[side_axis] < .35*norm(n):
            continue
        for a, b in zip(tri, (tri[1], tri[2], tri[0])):
            da, db = a[axis]-station, b[axis]-station
            if abs(da) <= 1e-8 and side*a[side_axis] > 0:
                points.append(tuple(a))
            if da*db < 0:
                p = add(a, mul(sub(b, a), -da/(db-da)))
                if side*p[side_axis] > 0:
                    points.append(p)
    if not points:
        return None
    return (min if upper else max)(points, key=lambda p: p[height_axis])


def audit(plan, meshes):
    if not plan.get('identity'):
        raise ValueError('Bind the plan to the identity observed during mesh export.')
    mesh_identity = meshes.get('identity')
    if meshes.get('format') == 'indexed_triangles_v1' and not mesh_identity:
        raise ValueError('A native mesh export must retain its captured identity.')
    if mesh_identity is not None and mesh_identity != plan['identity']:
        raise ValueError('The plan and native mesh export belong to different captured states.')
    if meshes.get('units', 'metres') != 'metres':
        raise ValueError('Review witnesses and native meshes must use metres.')
    world_frame = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    if meshes.get('frameToWorldRows', world_frame) != world_frame:
        raise ValueError('Export native meshes in the world frame used by the review witnesses.')
    checks = [*plan.get('seams', []), *plan.get('silhouettes', []), *plan.get('curves', []),
              *plan.get('trimProfiles', [])]
    names = [c['name'] for c in checks]
    required = plan.get('requiredChecks', [])
    if not required or len(names) != len(set(names)) or set(required) != set(names):
        raise ValueError('requiredChecks must enumerate every unique regional check; missing coverage is not a pass.')
    by_id = {}
    for m in meshes['meshes']:
        v, idx = m['vertices'], m['indices']
        if len(idx) % 3:
            raise ValueError('Triangle index count must be divisible by three.')
        by_id.setdefault(m['partId'], []).extend(tuple(v[idx[j+k]] for k in range(3)) for j in range(0, len(idx), 3))

    def group(ids):
        if not ids or any(i not in by_id for i in ids):
            raise ValueError('Every declared part must have an exported mesh.')
        return [t for i in ids for t in by_id[i]]

    results = []
    for profile in plan.get('trimProfiles', []):
        if len(profile['stations']) < 3 or profile['side'] not in (-1, 1):
            raise ValueError('A trim profile requires both endpoints, intermediate stations and an explicit side.')
        ga, gb = group(profile['upperPartIds']), group(profile['lowerPartIds'])
        rows = []
        for z in profile['stations']:
            args = (z, profile.get('longitudinalAxis', 2), profile.get('heightAxis', 1),
                    profile.get('sideAxis', 0), profile['side'])
            a, b = exposed_trim(ga, *args, True), exposed_trim(gb, *args, False)
            gap = norm(sub(a, b)) if a is not None and b is not None else math.inf
            rows.append({'station': z, 'upperTrim': a, 'lowerTrim': b, 'gapM': gap})
        gap = max(r['gapM'] for r in rows)
        results.append({'name': profile['name'], 'kind': 'exposed-trim-contours',
                        'passed': gap <= profile['maxGapM'], 'maxTrimGapM': gap, 'samples': rows})
    for seam in plan.get('seams', []):
        if len(seam['points']) < 3:
            raise ValueError('A seam needs endpoints and interior witnesses.')
        if seam.get('crease') and not seam.get('creaseReason'):
            raise ValueError('Preserved creases require a physical reason.')
        ga, gb = group(seam['a']), group(seam['b'])
        hint_a = seam.get('normalHintA', seam.get('normalHint'))
        hint_b = seam.get('normalHintB', seam.get('normalHint'))
        if hint_a is None or hint_b is None:
            raise ValueError('Each surface requires an outward normal hint.')
        rows = []
        for p in seam['points']:
            da, na = nearest(p, ga, hint_a)
            db, nb = nearest(p, gb, hint_b)
            angle = math.degrees(math.acos(max(-1, min(1, dot(na, nb))))) if na and nb else math.inf
            rows.append({'point': p, 'distanceA': da, 'distanceB': db, 'normalAngleDegrees': angle})
        gap = max(max(r['distanceA'], r['distanceB']) for r in rows)
        angle = max(r['normalAngleDegrees'] for r in rows)
        ok = gap <= seam['maxGapM'] and (seam.get('crease', False) or angle <= seam['maxAngleDegrees'])
        results.append({'name': seam['name'], 'kind': 'shared-boundary', 'passed': ok, 'maxGapM': gap,
                        'maxNormalAngleDegrees': angle, 'creaseReason': seam.get('creaseReason'), 'samples': rows})
    for sil in plan.get('silhouettes', []):
        if len(sil['slices']) < 3:
            raise ValueError('A silhouette needs extrema and intermediate slices.')
        triangles = group(sil['partIds'])
        rows = []
        for row in sil['slices']:
            actual = envelope(triangles, row['height'], sil['heightAxis'], sil['outlineAxis'])
            error = max(abs(actual[0]-row['min']), abs(actual[1]-row['max'])) if actual else math.inf
            rows.append({'height': row['height'], 'expected': [row['min'], row['max']], 'actual': actual, 'errorM': error})
        error = max(r['errorM'] for r in rows)
        results.append({'name': sil['name'], 'kind': 'both-outline-extrema', 'passed': error <= sil['maxErrorM'],
                        'maxErrorM': error, 'samples': rows})
    for curve in plan.get('curves', []):
        # Select vertices on one actual face and near the declared circular edge.
        # This measures tessellation against the chosen circle, not source fidelity.
        points = set(tuple(p) for t in group(curve['partIds']) for p in t)
        angles = {}
        for p in points:
            q = sub(p, curve['origin'])
            if abs(dot(q, curve['faceNormal'])-curve.get('faceDistance', 0)) > curve['faceToleranceM']:
                continue
            u = dot(q, curve['u'])-curve['center2'][0]
            v = dot(q, curve['v'])-curve['center2'][1]
            radial_error = abs(math.hypot(u, v)-curve['radius'])
            angle = math.degrees(math.atan2(v, u))
            if angle > curve['angleRangeDegrees'][1]:
                angle -= 360
            if curve['angleRangeDegrees'][0] <= angle <= curve['angleRangeDegrees'][1] and radial_error <= curve['selectionBandM']:
                key = round(angle, 4)
                angles[key] = max(angles.get(key, 0), radial_error)
        ordered = sorted(angles)
        segments = max(0, len(ordered)-1)
        turn = max((b-a for a, b in zip(ordered, ordered[1:])), default=math.inf)
        radial_error = max(angles.values(), default=math.inf)
        chord = radial_error+curve['radius']*(1-math.cos(math.radians(turn)/2)) if math.isfinite(turn) else math.inf
        ok = segments >= curve['minSegments'] and turn <= curve['maxTurnDegrees'] and chord <= curve['maxChordErrorM']
        results.append({'name': curve['name'], 'kind': 'native-circle-tessellation', 'passed': ok,
                        'segments': segments, 'maxTurnDegrees': turn, 'maxRadialErrorM': radial_error,
                        'conservativeChordErrorM': chord, 'observedAngleRangeDegrees': [ordered[0], ordered[-1]] if ordered else None})
    return {'identity': plan['identity'], 'passed': all(c['passed'] for c in results), 'checks': results,
            'limitations': ['Finite declared witnesses only; omitted regions are not certified.',
                            'Outline extrema do not detect interior holes or duplicate surfaces; inspect those separately.',
                            'No native material, collider, FPS or player aesthetic approval is implied.']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('plan', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
    mesh_file = Path(plan['meshFile'])
    if not mesh_file.is_absolute():
        mesh_file = args.plan.parent/mesh_file
    raw = mesh_file.read_bytes()
    result = audit(plan, json.loads(raw))
    result.update(meshFile=str(mesh_file.resolve()), meshSha256=hashlib.sha256(raw).hexdigest())
    # Missing geometry is a failed check with valid JSON, not a NaN/Infinity blob.
    def finite_json(value):
        if isinstance(value, float) and not math.isfinite(value): return None
        if isinstance(value, dict): return {k: finite_json(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)): return [finite_json(v) for v in value]
        return value
    result = finite_json(result)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
