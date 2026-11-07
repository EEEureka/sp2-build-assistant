"""Read-only native camera requests and evidence verification for regional reviews.

Mesh ray tests are predictions, never native-pixel visibility or visual acceptance.
Requests use the existing designer.capture fixed-camera API without scene hiding.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct
import zlib

from reference_storage import ReferenceError, digest
from regional_geometry import bounds, bounds_distance, normal, dot, sub, norm, cross


def _unit(v):
    n = norm(v)
    return tuple(x/n for x in v) if n > 1e-12 else (0., 0., 1.)


def _corners(bs):
    return [[x, y, z] for x in (bs['min'][0], bs['max'][0])
            for y in (bs['min'][1], bs['max'][1]) for z in (bs['min'][2], bs['max'][2])]


def project_world(point, camera, width, height):
    """Unity camera basis projection, using its actual returned pose/scale."""
    forward = _unit(camera.get('forwardWorld') or camera.get('direction'))
    up = _unit(camera.get('upWorld') or camera.get('up'))
    right = _unit(cross(up, forward)); up = _unit(cross(forward, right))
    relative = sub(point, camera.get('positionWorld') or camera.get('position'))
    z = dot(relative, forward); aspect = width/height
    half_v = camera['orthographicSize'] if camera['projection'] == 'orthographic' else z*math.tan(math.radians(camera['fieldOfViewDegrees']/2))
    if half_v <= 0: return {'inside': False, 'behindCamera': True, 'depthM': z}
    x = width/2+dot(relative, right)*width/(2*half_v*aspect)
    y = height/2-dot(relative, up)*height/(2*half_v)
    near = camera.get('nearClipMetres', .01); far = camera.get('farClipMetres', 1000)
    return {'x': x, 'y': y, 'depthM': z, 'inside': 0 <= x < width and 0 <= y < height and near <= z <= far,
            'pixelsPerMetreAtDepth': height/(2*half_v)}


def _ray_triangle(origin, target, tri):
    direction = sub(target, origin); e1, e2 = sub(tri[1], tri[0]), sub(tri[2], tri[0])
    p = cross(direction, e2); determinant = dot(e1, p)
    if abs(determinant) < 1e-12: return None
    tvec = sub(origin, tri[0]); u = dot(tvec, p)/determinant
    if u < -1e-9 or u > 1+1e-9: return None
    q = cross(tvec, e1); v = dot(direction, q)/determinant
    if v < -1e-9 or u+v > 1+1e-9: return None
    distance_fraction = dot(e2, q)/determinant
    return distance_fraction if 1e-8 < distance_fraction < 1-1e-6 else None


def _occlusion(cap, position, witnesses, remaining):
    samples = []; tested = 0; budget_hit = False
    for point in witnesses:
        best = None
        for pid, triangles in cap['triangles'].items():
            for index, tri in enumerate(triangles):
                if tested >= remaining: budget_hit = True; break
                tested += 1
                fraction = _ray_triangle(position, point, tri)
                if fraction is not None and (best is None or fraction < best[0]): best = (fraction, pid, index)
            if budget_hit: break
        samples.append({'pointWorld': list(point), 'status': 'predicted_occluded' if best else 'unknown_budget' if budget_hit else 'no_captured_surface_blocker',
                        'occludingPartId': best[1] if best else None, 'occludingTriangle': best[2] if best else None})
        if budget_hit: break
    return {'status': 'incomplete' if budget_hit else 'predicted_occluded' if any(s['occludingPartId'] is not None for s in samples) else 'no_captured_surface_blocker',
            'samples': samples, 'triangleTests': tested, 'complete': not budget_hit,
            'basis': 'two_sided_ray_tests_on_same_identity_captured_render_mesh',
            'limitations': ['Native shaders, transparency, clipping, hidden or uncaptured scene geometry are not modelled; inspect actual pixels.']}


def _issues(cap, report):
    rows = list(report.get('findings', []))
    for check in report.get('subjectChecks', [])+report.get('impactChecks', []):
        if check.get('status') not in ('failed', 'needs_review', 'missing_evidence'): continue
        measured = check.get('measured', {}); samples = measured.get('samples', [])
        points = [s.get('pointWorld') for s in samples if s.get('pointWorld')]
        points += check.get('expected', {}).get('points', [])
        if points: rows.insert(0, {'id': check['id'], 'partIds': check['partIds'], 'kind': check['kind'], 'witnessWorld': points[0], 'measured': measured})
    # One representative per relationship, fairly interleaved among subjects.
    unique = {}
    for row in rows:
        if row.get('witnessWorld'): unique.setdefault((tuple(sorted(row['partIds'])), row['kind']), row)
    selected = []; seen = set()
    buckets = {pid: [r for r in unique.values() if pid in r['partIds']] for pid in report['coverage']['subjectPartIds']}
    while any(buckets.values()):
        for pid, bucket in buckets.items():
            while bucket and bucket[0]['id'] in seen: bucket.pop(0)
            if bucket: row = bucket.pop(0); selected.append(row); seen.add(row['id'])
    return selected


def _context_regions(cap, report):
    """Geometry neighborhoods, not a guessed outside face or arbitrary cap."""
    subjects = set(report['coverage']['subjectPartIds']); counterparts = set()
    for row in report['relations']:
        if row['kind'] == 'native_symmetry_group' and subjects.intersection(row['partIds']):
            counterparts.update(set(row['partIds'])-subjects)
    regions = {}; missing = []
    for pid in sorted(subjects | counterparts):
        scope = {pid}
        for relation in report['relations']:
            if pid not in relation['partIds']: continue
            kind = relation['kind']
            if kind in ('geometric_proximity', 'geometric_shared_boundary_candidate') and relation.get('withinNeighborDistance') is not False:
                scope.update(relation['partIds'])
            elif kind in ('cut_or_target_dependency', 'nested_native_dependency'):
                scope.update(other for other in relation['partIds'] if pid not in cap['bounds'] or other not in cap['bounds'] or
                             bounds_distance(cap['bounds'][pid], cap['bounds'][other]) <= .25)
        triangles = [tri for member in scope for tri in cap['triangles'].get(member, [])]
        region_bounds = bounds(triangles)
        if not region_bounds:
            missing.append({'partId': pid, 'reason': 'no_actual_subject_or_target_geometry_for_context'}); continue
        key = tuple(sorted(scope))
        if key not in regions: regions[key] = {'id': 'region-'+str(len(regions)), 'partIds': list(key), 'subjectPartIds': [],
                                               'bounds': region_bounds, 'counterpartPartIds': []}
        regions[key]['subjectPartIds' if pid in subjects else 'counterpartPartIds'].append(pid)
    return list(regions.values()), sorted(counterparts), missing


def _fit_context_camera(region_bounds, vector, resolution, name, padding=1.2):
    target = [(a+b)/2 for a, b in zip(region_bounds['min'], region_bounds['max'])]
    vector = _unit(vector); direction = [-x for x in vector]
    up = [0, 1, 0] if abs(direction[1]) < .95 else [0, 0, 1]
    right = _unit(cross(up, direction)); up = _unit(cross(direction, right))
    corners = _corners(region_bounds); relative = [sub(p, target) for p in corners]
    half_v = max(.01, max(abs(dot(p, up)) for p in relative),
                 max(abs(dot(p, right)) for p in relative)/(resolution['width']/resolution['height']))*padding
    radius = max(norm(p) for p in relative); distance = max(.1, radius*3+.1)
    return {'name': name, 'view': 'fixed', 'projection': 'orthographic',
            'position': [target[i]+vector[i]*distance for i in range(3)], 'direction': direction,
            'up': list(up), 'target': target, 'fieldOfViewDegrees': 40, 'orthographicSize': half_v,
            'nearClipMetres': .001, 'farClipMetres': max(1000, distance+radius*2)}


def _image_feedback(payload, expected_identity):
    """Only same-image inspected feedback can change the next camera attempt."""
    accepted = []
    captures = payload.get('nativeCaptureResults', {}) or {}
    for request_id, row in (payload.get('nativeImageReviews', {}) or {}).items():
        if not isinstance(row, dict) or row.get('status') != 'inspected' or row.get('visibility') not in ('occluded', 'uncertain'): continue
        supplied = captures.get(request_id, {})
        if not isinstance(supplied, dict): continue
        path = supplied.get('imagePath')
        if not path or not Path(path).is_file(): continue
        sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        raw = supplied.get('result', supplied)
        if raw.get('success') is True: raw = raw.get('data', {})
        if raw.get('identity') == expected_identity and row.get('sha256') == sha and any(f.get('sha256', '').lower() == sha for f in raw.get('files', [])):
            accepted.append({'requestId': request_id, 'imageSha256': sha, 'visibility': row['visibility']})
    return accepted


def plan_native_views(cap, report, payload):
    options = payload.get('nativeViews', {})
    if options is False: return {'status': 'not_requested', 'requests': []}
    if not isinstance(options, dict): raise ReferenceError('invalid_input', 'nativeViews requires an object or false')
    max_views = options.get('maxViews', 12); resolution = options.get('resolution', {'width': 1600, 'height': 1200})
    if type(max_views) is not int or not 1 <= max_views <= 64: raise ReferenceError('invalid_input', 'nativeViews.maxViews must be 1..64')
    if not isinstance(resolution, dict) or any(type(resolution.get(k)) is not int or not 128 <= resolution[k] <= 2048 for k in ('width', 'height')):
        raise ReferenceError('invalid_input', 'nativeViews.resolution requires width and height in 128..2048')
    minimum = options.get('minimumDetailPixels', 8)
    if type(minimum) not in (int, float) or not math.isfinite(minimum) or not 1 <= minimum <= 512:
        raise ReferenceError('invalid_input', 'minimumDetailPixels must be 1..512')
    rays = options.get('maxOcclusionTriangleTests', 100000)
    if type(rays) is not int or not 0 <= rays <= 2000000: raise ReferenceError('invalid_input', 'maxOcclusionTriangleTests must be 0..2000000')
    requests = []; skipped = []; remaining = rays
    issues = _issues(cap, report); regions, counterparts, context_missing = _context_regions(cap, report)
    feedback = _image_feedback(payload, cap['identity']); retry = bool(feedback)
    context_vectors = [(1, .45, 1), (-1, .45, -1), (1, .25, -1), (-1, .25, 1), (1, .12, .15), (-1, .12, -.15)]
    if retry: context_vectors = [(1, .65, -.35), (-1, .65, .35), (.35, .2, 1), (-.35, .2, -1), (1, .1, .4), (-1, .1, -.4)]
    # Reserve real complete context before close-ups. Fair pairs across regions
    # include actual counterpart geometry, not a second look at the same point.
    context_candidates = [(region, vector, index) for index, vector in enumerate(context_vectors[:2] if issues else context_vectors) for region in regions]
    def append_request(issue_id, ids, role, side, view, points, roi, feature=None, **extra):
        nonlocal remaining
        name = view['name']
        if len(requests) >= max_views:
            skipped.append({'issueId': issue_id, 'partIds': ids, 'viewRole': role, 'side': side, 'reason': 'native_view_budget_exceeded'}); return
        predicted = _occlusion(cap, view['position'], points[:3], remaining); remaining -= predicted['triangleTests']
        projected = [project_world(p, view, resolution['width'], resolution['height']) for p in points]
        ppm = resolution['height']/(2*view['orthographicSize'])
        requests.append({'id': name, 'issueId': issue_id, 'partIds': ids, 'viewRole': role, 'side': side,
                         'sideMeaning': 'opposite_local_context_azimuths_not_inferred_ship_port_starboard',
                         'expectedIdentity': cap['identity'], 'geometryStamp': cap['geometryStamp'], 'witnessesWorld': points,
                         'roiBoundsWorld': roi, 'minimumDetailPixels': minimum, 'measuredFeatureM': feature,
                         'predictedFeaturePixels': feature*ppm if feature else None,
                         'detailResolution': 'below_threshold' if feature and feature*ppm < minimum else 'predicted_sufficient' if feature else 'context_only_no_detail_resolution_claim',
                         'projectedWitnesses': projected, 'occlusionPrediction': predicted,
                         'designerCaptureRequest': {'craftSessionId': cap['identity']['craftSessionId'], 'expectedRevision': cap['identity']['revision'],
                                                     'focusPartIds': ids, 'resolution': resolution, 'views': [view]}, **extra})
    for region, vector, index in context_candidates:
        side = 1 if index % 2 == 0 else -1
        name = 'review-'+str(len(requests))+'-region-context-'+('positive' if side == 1 else 'negative')
        view = _fit_context_camera(region['bounds'], vector, resolution, name, 1.4 if retry else 1.2)
        append_request(region['id'], region['partIds'], 'region_context', side, view, _corners(region['bounds']), region['bounds'],
                       contextSubjectPartIds=region['subjectPartIds'], contextCounterpartPartIds=region['counterpartPartIds'],
                       orientationBasis='world_axis_oblique_silhouette_no_outer_face_claim', neighborContextMayBeCropped=False,
                       adaptiveZoomApplied=retry, roiMustBeFullyInsideImage=True, cameraOutsideContextBounds=True,
                       detailAcceptance='not_applicable_context_view', feedbackBasis=feedback,
                       purpose='Complete actual subject and local neighbors with silhouette padding; examine native pixels before claiming visible geometry')
    candidates = []
    for role in ('issue_detail', 'issue_oblique', 'issue_grazing'):
        for issue in issues:
            points = [issue['witnessWorld']]; measured = issue.get('measured', {})
            points += measured.get('polygonWorld', [])
            points += [measured[k] for k in ('witnessAWorld', 'witnessBWorld') if measured.get(k)]
            target = [sum(p[i] for p in points)/len(points) for i in range(3)]
            triangles = [tri for pid in issue['partIds'] for tri in cap['triangles'].get(pid, [])]
            candidate_tri = min(triangles, key=lambda t: sum((sum(p[i] for p in t)/3-target[i])**2 for i in range(3))) if triangles else None
            explicit_normal = issue.get('normalWorld') or issue.get('expected', {}).get('normalHint')
            face = explicit_normal or (normal(candidate_tri) if candidate_tri else None) or (1, 0, 0)
            face = _unit(face); tangent = _unit(cross(face, (0, 1, 0) if abs(face[1]) < .9 else (0, 0, 1)))
            vector = face if role == 'issue_detail' else _unit([face[i]+.65*tangent[i]+(.25 if i == 1 else 0) for i in range(3)]) if role == 'issue_oblique' else _unit([.2*face[i]+tangent[i]+(.12 if i == 1 else 0) for i in range(3)])
            if retry: vector = _unit([vector[i]+.8*tangent[i]+(.35 if i == 1 else 0) for i in range(3)])
            for side in (1, -1): candidates.append((issue, points, target, vector, role, side, explicit_normal))
    for issue, points, target, vector, role, side, explicit_normal in candidates:
        name = 'review-'+str(len(requests))+'-'+role.replace('_', '-')+'-'+('positive' if side == 1 else 'negative')
        if len(requests) >= max_views:
            skipped.append({'issueId': issue['id'], 'viewRole': role, 'side': side, 'reason': 'native_view_budget_exceeded'}); continue
        issue_bounds = bounds([tuple(points)])
        context = bounds([t for pid in issue['partIds'] for t in cap['triangles'].get(pid, [])])
        span = max((context['max'][i]-context['min'][i] for i in range(3)), default=.1) if context else .1
        detail = max((norm(sub(a, b)) for a in points for b in points), default=0)
        feature = issue.get('measured', {}).get('distanceM') or issue.get('measured', {}).get('gapM')
        if type(feature) not in (int, float) or feature <= 0: feature = detail if detail > 1e-6 else None
        half_v_context = max(.02, min(span*.2, 2.))
        half_v_detail = resolution['height']*feature/(minimum*2) if feature else half_v_context
        half_v = max(.01, min(half_v_context, half_v_detail))*(1.6 if retry else 1)
        distance = max(.1, span*1.5); direction = [-side*x for x in vector]
        position = [target[i]-direction[i]*distance for i in range(3)]
        up = [0, 1, 0] if abs(direction[1]) < .95 else [0, 0, 1]
        view = {'name': name, 'view': 'fixed', 'projection': 'orthographic', 'position': position,
                'direction': direction, 'up': up, 'target': target, 'fieldOfViewDegrees': 40,
                'orthographicSize': half_v, 'nearClipMetres': .001, 'farClipMetres': max(1000, distance+span*2)}
        append_request(issue['id'], issue['partIds'], role, side, view, points, issue_bounds, feature,
                       adaptiveZoomApplied=half_v < half_v_context, neighborContextMayBeCropped=bool(context and half_v < span/2),
                       roiMustBeFullyInsideImage=False, orientationBasis='explicit_normal_hint' if explicit_normal else 'nearest_triangle_candidate_not_certified_outer_face',
                       companionContextIds=[r['id'] for r in requests if r['viewRole'] == 'region_context' and set(r['partIds']) & set(issue['partIds'])],
                       feedbackBasis=feedback)
    return {'status': 'planned_with_limits' if skipped else 'planned_unexecuted', 'requests': requests, 'skipped': skipped,
            'identity': cap['identity'], 'geometryStamp': cap['geometryStamp'], 'units': 'metres', 'coordinateFrame': 'world',
            'localOppositeDirectionCoverage': {issue['id']: {'positive': any(r['issueId'] == issue['id'] and r['side'] == 1 for r in requests),
                                              'negative': any(r['issueId'] == issue['id'] and r['side'] == -1 for r in requests)} for issue in issues},
            'contextCoverage': {str(pid): {'contextPlanned': any(pid in r['partIds'] and r['viewRole'] == 'region_context' for r in requests),
                                          'actualCounterpart': pid in counterparts, 'nativeVisibility': 'unreviewed'}
                                for pid in sorted(set(report['coverage']['subjectPartIds']) | set(counterparts))},
            'contextMissing': context_missing, 'feedbackUsed': feedback,
            'occlusionTriangleTests': rays-remaining, 'visualAcceptance': 'unreviewed',
            'limitations': ['Execute designerCaptureRequest through sp2build; paths and ray predictions do not prove visual acceptance.',
                            'Two local sides do not establish ship port/starboard without verified ship-frame annotation.',
                            'Native scene geometry is preserved; no focus-only hiding or wireframe visibility substitution.']}


def _png_information(image_bytes):
    """Coarse native-pixel information diagnostic, never object recognition."""
    try:
        if image_bytes[:8] != b'\x89PNG\r\n\x1a\n': return {'status': 'unavailable', 'reason': 'not_png'}
        width, height, depth, color, compression, filtering, interlace = struct.unpack('!IIBBBBB', image_bytes[16:29])
        if depth != 8 or color not in (2, 6) or interlace != 0 or width*height > 4194304:
            return {'status': 'unavailable', 'reason': 'unsupported_png_pixel_profile'}
        compressed = []; offset = 8
        while offset+12 <= len(image_bytes):
            length = struct.unpack('!I', image_bytes[offset:offset+4])[0]; tag = image_bytes[offset+4:offset+8]
            if tag == b'IDAT': compressed.append(image_bytes[offset+8:offset+8+length])
            offset += 12+length
        channels = 3 if color == 2 else 4; stride = width*channels
        decompressor = zlib.decompressobj(); expected = (stride+1)*height
        decoded = decompressor.decompress(b''.join(compressed), expected+1)
        if len(decoded) != expected or not decompressor.eof: return {'status': 'unavailable', 'reason': 'incomplete_png_pixels'}
        previous = bytearray(stride); histogram = {}; sample_count = 0
        xstep, ystep = max(1, width//64), max(1, height//48)
        for y in range(height):
            base = y*(stride+1); method = decoded[base]; row = bytearray(decoded[base+1:base+1+stride])
            if method == 2:
                row = bytearray((a+b)&255 for a, b in zip(row, previous))
            elif method in (1, 3, 4):
                for i in range(stride):
                    left = row[i-channels] if i >= channels else 0; upper = previous[i]; corner = previous[i-channels] if i >= channels else 0
                    if method == 1: prediction = left
                    elif method == 3: prediction = (left+upper)//2
                    else:
                        p = left+upper-corner; a, b, c = abs(p-left), abs(p-upper), abs(p-corner)
                        prediction = left if a <= b and a <= c else upper if b <= c else corner
                    row[i] = (row[i]+prediction)&255
            elif method != 0: return {'status': 'unavailable', 'reason': 'unknown_png_filter'}
            if y % ystep == 0:
                for x in range(0, width, xstep):
                    rgb = tuple(value//16 for value in row[x*channels:x*channels+3]); histogram[rgb] = histogram.get(rgb, 0)+1; sample_count += 1
            previous = row
        dominant = max(histogram.values(), default=0)/max(1, sample_count)
        return {'status': 'measured', 'basis': 'native_png_sampled_quantized_rgb_histogram', 'sampleCount': sample_count,
                'quantizedColorCount': len(histogram), 'dominantColorFraction': dominant,
                'lowInformationCandidate': dominant >= .95 and len(histogram) <= 2,
                'limitations': ['A color histogram cannot identify the target or certify visibility; a flat image needs explicit inspection or another view.']}
    except (ValueError, IndexError, struct.error, zlib.error):
        return {'status': 'unavailable', 'reason': 'invalid_png_pixel_stream'}


def verify_native_views(plan, capture_results, image_reviews=None):
    """Verify returned capture geometry/ROI and separately require image inspection.

    capture_results maps request ID to the native response (optionally wrapped in
    result) plus imagePath. Reviews map request ID to {sha256, status:'inspected',
    visibility:'visible'|'occluded'|'uncertain', outcome:'passed'|'failed'|'uncertain'}.
    """
    rows = []; image_reviews = image_reviews or {}
    if not isinstance(capture_results, dict) or not isinstance(image_reviews, dict):
        raise ReferenceError('invalid_input', 'Native capture results and image reviews must map request IDs to evidence objects')
    for request in plan['requests']:
        supplied = capture_results.get(request['id'])
        if not supplied:
            rows.append({'id': request['id'], 'status': 'missing_evidence', 'reason': 'native_capture_not_supplied'}); continue
        if not isinstance(supplied, dict): raise ReferenceError('invalid_input', 'Native capture result must be an object', requestId=request['id'])
        raw = supplied.get('result', supplied)
        if raw.get('success') is True and isinstance(raw.get('data'), dict): raw = raw['data']
        if raw.get('identity') != request['expectedIdentity']:
            rows.append({'id': request['id'], 'status': 'missing_evidence', 'reason': 'capture_identity_mismatch'}); continue
        if raw.get('backend') != 'native_designer_camera' or not raw.get('nativeMaterials') or raw.get('staleAtDelivery'):
            rows.append({'id': request['id'], 'status': 'missing_evidence', 'reason': 'not_current_native_camera_evidence'}); continue
        views = raw.get('views', []); view = next((v for v in views if v.get('name') == request['id']), None)
        if not view:
            rows.append({'id': request['id'], 'status': 'missing_evidence', 'reason': 'requested_view_missing'}); continue
        camera = view['camera']; width, height = view['width'], view['height']
        witnesses = [project_world(p, camera, width, height) for p in request['witnessesWorld']]
        feature = request.get('measuredFeatureM')
        pixels = min((w.get('pixelsPerMetreAtDepth', 0)*feature for w in witnesses), default=0) if feature else None
        framed = all(w['inside'] for w in witnesses)
        roi = [project_world(p, camera, width, height) for p in _corners(request['roiBoundsWorld'])]
        path = supplied.get('imagePath'); sha = None; artifact_status = 'missing_local_image'; information = {'status': 'unavailable', 'reason': 'missing_local_image'}
        if path and Path(path).is_file():
            image_bytes = Path(path).read_bytes(); sha = hashlib.sha256(image_bytes).hexdigest()
            declared = next((f for f in raw.get('files', []) if f.get('name') == view.get('file')), None)
            dimensions = struct.unpack('!II', image_bytes[16:24]) if image_bytes[:8] == b'\x89PNG\r\n\x1a\n' and len(image_bytes) >= 24 else None
            artifact_status = 'verified_native_file_hash_and_png_dimensions' if declared and declared.get('sha256', '').lower() == sha and dimensions == (width, height) else 'native_file_hash_or_png_dimensions_mismatch'
            if artifact_status == 'verified_native_file_hash_and_png_dimensions': information = _png_information(image_bytes)
        inspection = image_reviews.get(request['id'], {})
        inspected = bool(artifact_status == 'verified_native_file_hash_and_png_dimensions' and sha and inspection.get('sha256') == sha and inspection.get('status') == 'inspected')
        scene_healthy = raw.get('sceneIntegrity', {}).get('status') == 'healthy'
        roi_inside = all(p['inside'] for p in roi)
        geometry_ok = framed and (not request.get('roiMustBeFullyInsideImage') or roi_inside) and (pixels is None or pixels+1e-6 >= request['minimumDetailPixels']) and raw.get('cameraRestored') is True and scene_healthy
        information_reviewed = not information.get('lowInformationCandidate') or inspected and inspection.get('lowInformationReviewed') is True
        visual = 'unreviewed' if not inspected else 'failed' if inspection.get('outcome') == 'failed' else 'passed' if geometry_ok and information_reviewed and inspection.get('outcome') == 'passed' and inspection.get('visibility') == 'visible' else 'needs_review'
        rows.append({'id': request['id'], 'issueId': request['issueId'], 'status': 'failed' if not geometry_ok else 'native_framing_verified' if artifact_status == 'verified_native_file_hash_and_png_dimensions' else 'missing_evidence',
                     'identity': raw['identity'], 'captureId': raw.get('captureId'), 'imagePath': path, 'imageSha256': sha,
                     'witnessesInsideImage': framed, 'roiFullyInsideImage': roi_inside,
                     'actualProjectedWitnesses': witnesses, 'actualFeaturePixels': pixels, 'minimumDetailPixels': request['minimumDetailPixels'],
                     'actualCamera': camera, 'visualReview': visual, 'pixelVisibility': inspection.get('visibility') if inspected else 'unreviewed',
                     'artifactEvidence': artifact_status,
                     'nativePixelInformation': information,
                     'cameraRestored': raw.get('cameraRestored'), 'sceneIntegrity': raw.get('sceneIntegrity'),
                     'limitations': ['Framing measurements do not determine native pixel occlusion; visualReview requires hash-bound image inspection.']})
    passed_ids = {r['id'] for r in rows if r.get('visualReview') == 'passed'}
    context_coverage = {pid: {**state, 'reviewedContext': bool(state.get('contextPlanned') and any(
        request['id'] in passed_ids and request.get('viewRole') == 'region_context' and int(pid) in request.get('partIds', [])
        for request in plan['requests']))} for pid, state in plan.get('contextCoverage', {}).items()}
    complete = bool(rows and all(r.get('visualReview') == 'passed' for r in rows) and not plan.get('skipped')
                    and not plan.get('contextMissing') and all(c['reviewedContext'] for c in context_coverage.values()))
    return {'kind': 'sp2build.nativeReviewViews', 'planHash': digest(plan), 'views': rows,
            'contextCoverage': context_coverage, 'contextMissing': plan.get('contextMissing', []),
            'status': 'passed' if complete else 'incomplete',
            'visualAcceptance': 'passed' if complete else 'unverified_or_incomplete'}
