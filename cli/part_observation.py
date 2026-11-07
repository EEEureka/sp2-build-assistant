"""Readable, identity-bound part observations and actual-mesh analysis images.

PNG/SVG images are orthographic wireframe projections of captured triangles,
not screenshots, proxies or visibility/material acceptance. No game calls.
"""
from __future__ import annotations

import html
import colorsys
import math
from pathlib import Path
import struct
import uuid
import zlib

from reference_storage import ReferenceError, digest, write_json
from regional_geometry import capture, review, topology, bounds, normal, dot, sub, section, _integer, _ids, _document
from review_cameras import plan_native_views, verify_native_views

COLORS = [(231, 129, 28), (42, 132, 183), (156, 82, 178), (32, 154, 128), (199, 80, 92), (138, 128, 46)]
FONT = {
    '0': ['111','101','101','101','111'], '1': ['010','110','010','010','111'],
    '2': ['111','001','111','100','111'], '3': ['111','001','111','001','111'],
    '4': ['101','101','111','001','001'], '5': ['111','100','111','001','111'],
    '6': ['111','100','111','101','111'], '7': ['111','001','010','010','010'],
    '8': ['111','101','111','101','111'], '9': ['111','101','111','001','111'],
    '#': ['101','111','101','111','101'], '-': ['000','000','111','000','000'],
    'A': ['010','101','111','101','101'], 'B': ['110','101','110','101','110'],
    'C': ['111','100','100','100','111'], 'D': ['110','101','101','101','110'],
    'E': ['111','100','110','100','111'], 'F': ['111','100','110','100','100'],
    'G': ['111','100','101','101','111'], 'H': ['101','101','111','101','101'],
    'I': ['111','010','010','010','111'], 'J': ['001','001','001','101','111'],
    'K': ['101','101','110','101','101'], 'L': ['100','100','100','100','111'],
    'M': ['101','111','111','101','101'], 'N': ['101','111','111','111','101'],
    'O': ['111','101','101','101','111'], 'P': ['110','101','110','100','100'],
    'Q': ['111','101','101','111','001'], 'R': ['110','101','110','101','101'],
    'S': ['111','100','111','001','111'], 'T': ['111','010','010','010','010'],
    'U': ['101','101','101','101','111'], 'V': ['101','101','101','101','010'],
    'W': ['101','101','111','111','101'], 'X': ['101','101','010','101','101'],
    'Y': ['101','101','010','010','010'], 'Z': ['111','001','010','100','111'],
    '.': ['000','000','000','000','010'], ':': ['000','010','000','010','000'],
    '/': ['001','001','010','100','100'], '+': ['000','010','111','010','000'],
    '=': ['000','111','000','111','000'], '|': ['010','010','010','010','010'],
    ' ': ['000','000','000','000','000']}


def _palette(part_ids):
    """One deterministic, unique map shared by every view in this report scope."""
    result = {}; used = set()
    for index, pid in enumerate(sorted(set(part_ids))):
        if index < len(COLORS): color = COLORS[index]
        else:
            rgb = colorsys.hsv_to_rgb((index*.618033988749895)%1, .68, .72 if index%2 else .88)
            color = tuple(round(c*255) for c in rgb)
        while color in used: color = ((color[0]+17)%220+20, (color[1]+31)%220+20, (color[2]+47)%220+20)
        used.add(color); result[pid] = color
    return result


def _png(path, width, height, pixels):
    def chunk(tag, data): return struct.pack('!I', len(data))+tag+data+struct.pack('!I', zlib.crc32(tag+data)&0xffffffff)
    rows = b''.join(b'\x00'+bytes(pixels[y*width*3:(y+1)*width*3]) for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))+
                     chunk(b'IDAT', zlib.compress(rows, 6))+chunk(b'IEND', b''))


def _clip(x0, y0, x1, y1, width, height):
    def out(x, y): return (1 if x < 0 else 2 if x >= width else 0)|(4 if y < 0 else 8 if y >= height else 0)
    for _ in range(12):
        a, b = out(x0, y0), out(x1, y1)
        if not a|b: return x0, y0, x1, y1
        if a&b: return None
        flag = a or b
        if flag&8:
            if y1 == y0: return None
            x, y = x0+(x1-x0)*(height-1-y0)/(y1-y0), height-1
        elif flag&4:
            if y1 == y0: return None
            x, y = x0+(x1-x0)*(-y0)/(y1-y0), 0
        elif flag&2:
            if x1 == x0: return None
            x, y = width-1, y0+(y1-y0)*(width-1-x0)/(x1-x0)
        else:
            if x1 == x0: return None
            x, y = 0, y0+(y1-y0)*(-x0)/(x1-x0)
        if flag == a: x0, y0 = x, y
        else: x1, y1 = x, y
    return None


def _pixel(pixels, width, height, x, y, color):
    if 0 <= x < width and 0 <= y < height:
        start = (y*width+x)*3; pixels[start:start+3] = bytes(color)


def _line(pixels, width, height, a, b, color):
    """Coverage-antialiased line rasterization; no host imaging dependency."""
    clipped = _clip(*a, *b, width, height)
    if clipped is None: return
    x0, y0, x1, y1 = clipped
    steep = abs(y1-y0) > abs(x1-x0)
    if steep: x0, y0, x1, y1 = y0, x0, y1, x1
    if x0 > x1: x0, y0, x1, y1 = x1, y1, x0, y0
    gradient = (y1-y0)/(x1-x0) if x1 != x0 else 0
    def blend(x, y, coverage):
        if steep: x, y = y, x
        if 0 <= x < width and 0 <= y < height:
            start = (y*width+x)*3
            for k in range(3): pixels[start+k] = round(pixels[start+k]*(1-coverage)+color[k]*coverage)
    for x in range(math.floor(x0), math.ceil(x1)+1):
        coverage = max(0., min(x+1, x1+1)-max(x, x0))
        y = y0+gradient*(x-x0); lower = math.floor(y); fraction = y-lower
        blend(x, lower, (1-fraction)*coverage); blend(x, lower+1, fraction*coverage)


def _label(pixels, width, height, text, x, y, color, scale=2):
    for char in str(text).upper():
        for j, row in enumerate(FONT.get(char, FONT['-'])):
            for i, active in enumerate(row):
                if active == '1':
                    for ox in range(scale):
                        for oy in range(scale): _pixel(pixels, width, height, x+i*scale+ox, y+j*scale+oy, color)
        x += 4*scale


def _view(directory, name, triangles_by_part, axes, width, height, max_triangles, witnesses=None, focal_bounds=None, sections=None, palette=None, polygons=None, edge_overlays=None, layer_labels=None):
    all_triangles = [t for triangles in triangles_by_part.values() for t in triangles]
    if not all_triangles and not sections: return None
    points = [p for t in all_triangles for p in t]
    if sections:
        points += [p for s in sections for segment in s.get('segments', []) for p in (segment['a'], segment['b'])]
    if not points: return None
    low = [min(p[i] for p in points) for i in range(3)]; high = [max(p[i] for p in points) for i in range(3)]
    if focal_bounds is not None: low, high = focal_bounds['min'], focal_bounds['max']
    horizontal, vertical = axes; ordered = sorted(triangles_by_part)
    palette = palette or _palette(ordered)
    layer_labels = layer_labels or {}
    text_scale = 2 if width >= 512 else 1
    legend_column_width = max(100 if text_scale == 2 else 52, max((len(layer_labels.get(pid, '#'+str(pid)))*4*text_scale+20 for pid in ordered), default=0))
    columns = max(1, (width-24)//legend_column_width)
    legend_rows = math.ceil(len(ordered)/columns)
    top_margin = (54 if text_scale == 2 else 28)+legend_rows*(14 if text_scale == 2 else 8)
    bottom_margin = 38 if text_scale == 2 else 20
    extent_u, extent_v = max(high[horizontal]-low[horizontal], .001), max(high[vertical]-low[vertical], .001)
    scale = min(max(16, width-96)/extent_u, max(16, height-top_margin-bottom_margin-24)/extent_v)
    center_u, center_v = (low[horizontal]+high[horizontal])/2, (low[vertical]+high[vertical])/2
    center_y = top_margin+(height-top_margin-bottom_margin)/2
    def project(p): return ((p[horizontal]-center_u)*scale+width/2, center_y-(p[vertical]-center_v)*scale)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="'+str(width)+'" height="'+str(height)+'" viewBox="0 0 '+str(width)+' '+str(height)+'">',
           '<desc>actual captured triangles; analysis wireframe including hidden edges</desc>',
           '<rect width="100%" height="100%" fill="#fafafa"/>']
    pixels = bytearray([250]*(width*height*3)); total = len(all_triangles)
    step = max(1, math.ceil(total/max_triangles)); rendered = 0; serial = 0
    visible_points = {pid: [] for pid in ordered}; labels = []
    def draw_edge(a, b, color, pid=None):
        _line(pixels, width, height, a, b, color)
        clipped = _clip(*a, *b, width, height)
        if pid is not None and clipped:
            x0, y0, x1, y1 = clipped
            if max(y0, y1) >= top_margin and min(y0, y1) <= height-bottom_margin:
                visible_points[pid].extend([(x0, max(top_margin, min(height-bottom_margin, y0))),
                                            (x1, max(top_margin, min(height-bottom_margin, y1)))])
    for k, pid in enumerate(ordered):
        color = palette[pid]; rgb = '#'+''.join(format(c, '02x') for c in color)
        group = triangles_by_part[pid]
        for tri in group:
            include = serial % step == 0; serial += 1
            if not include: continue
            rendered += 1; xy = [project(p) for p in tri]
            svg.append('<polygon points="'+' '.join(format(x, '.3f')+','+format(y, '.3f') for x, y in xy)+'" fill="none" stroke="'+rgb+'" stroke-width="0.8"/>')
            for a, b in zip(xy, (xy[1], xy[2], xy[0])): draw_edge(a, b, color, pid)
    for s in sections or []:
        color = palette[s['partId']]
        for segment in s.get('segments', []):
            a, b = project(segment['a']), project(segment['b'])
            draw_edge(a, b, color, s['partId'])
            svg.append('<line x1="'+str(a[0])+'" y1="'+str(a[1])+'" x2="'+str(b[0])+'" y2="'+str(b[1])+'" stroke="rgb'+str(color)+'" stroke-width="2"/>')
    boundary_annotations = []
    for edge_index, edge in enumerate(edge_overlays or []):
        a, b = project(edge['a']), project(edge['b']); color = (190, 0, 0) if edge.get('kind') in ('free_boundary', 'open_boundary') else (40, 40, 40)
        draw_edge(a, b, color)
        svg.append('<line x1="'+str(a[0])+'" y1="'+str(a[1])+'" x2="'+str(b[0])+'" y2="'+str(b[1])+'" stroke="rgb'+str(color)+'" stroke-width="2"/>')
        label = str(edge.get('id', 'EDGE'))
        if edge.get('normalAngleDegrees') is not None: label += ' '+format(edge['normalAngleDegrees'], '.3g')+' DEG'
        x, y = (a[0]+b[0])/2, (a[1]+b[1])/2
        label_rendered = edge_index < 12 and top_margin <= y < height-bottom_margin and 0 <= x < width
        if label_rendered:
            _label(pixels, width, height, label, int(x), int(y), color, 1)
            svg.append('<text x="'+str(x)+'" y="'+str(y)+'" font-size="10">'+html.escape(label)+'</text>')
        boundary_annotations.append({'id': edge.get('id'), 'partId': edge.get('partId'), 'kind': edge.get('kind'),
                                     'aWorld': edge['a'], 'bWorld': edge['b'], 'normalAngleDegrees': edge.get('normalAngleDegrees'),
                                     'basis': 'actual_native_topology_edge', 'projectedEndpoints': [a, b], 'labelRendered': label_rendered})
    polygon_records = []
    for polygon in polygons or []:
        xy = [project(p) for p in polygon]
        if len(xy) < 3: continue
        svg.append('<polygon points="'+' '.join(str(x)+','+str(y) for x, y in xy)+'" fill="#f44" fill-opacity="0.25" stroke="#d00" stroke-width="3"/>')
        # Scanline tint of the measured intersection polygon, never a proxy.
        for y in range(max(top_margin, int(math.floor(min(p[1] for p in xy)))), min(height-bottom_margin, int(math.ceil(max(p[1] for p in xy))))+1):
            crossings = []
            for a, b in zip(xy, xy[1:]+xy[:1]):
                if (a[1] > y+.5) != (b[1] > y+.5): crossings.append(a[0]+(b[0]-a[0])*(y+.5-a[1])/(b[1]-a[1]))
            crossings.sort()
            for a, b in zip(crossings[::2], crossings[1::2]):
                for x in range(max(0, int(math.ceil(a))), min(width-1, int(math.floor(b)))+1):
                    start = (y*width+x)*3
                    pixels[start:start+3] = bytes((int(pixels[start]*.7+255*.3), int(pixels[start+1]*.7+40*.3), int(pixels[start+2]*.7+40*.3)))
        for a, b in zip(xy, xy[1:]+xy[:1]):
            draw_edge(a, b, (220, 0, 0)); draw_edge((a[0]+1, a[1]), (b[0]+1, b[1]), (220, 0, 0))
        polygon_records.append({'basis': 'actual_triangle_intersection_polygon', 'vertexCount': len(polygon),
                                'fullyInsideImage': all(0 <= x < width and top_margin <= y < height-bottom_margin for x, y in xy)})
    for witness in witnesses or []:
        x, y = project(witness)
        svg.append('<circle cx="'+str(x)+'" cy="'+str(y)+'" r="5" fill="#d00"/>')
        for ox in range(-4, 5):
            for oy in range(-4, 5):
                if ox*ox+oy*oy <= 16: _pixel(pixels, width, height, int(x)+ox, int(y)+oy, (220, 0, 0))
    # Every image carries its own analysis/axis/scale key, not only metadata.
    pixels[:min(top_margin, height)*width*3] = bytes([250])*(min(top_margin, height)*width*3)
    svg.append('<rect x="0" y="0" width="100%" height="'+str(top_margin)+'" fill="#fafafa"/>')
    header = 'ANALYSIS WIREFRAME | HIDDEN EDGES'
    axis_key = 'WORLD '+('XYZ'[horizontal])+' / '+('XYZ'[vertical])+' | M | '+format(scale, '.2f')+' PX/M'
    for text, y in ((header, 10), (axis_key, 24 if text_scale == 2 else 18), (name, 38)):
        if text_scale == 1 and y == 38: continue
        _label(pixels, width, height, text, 12, y, (20, 20, 20), text_scale)
        svg.append('<text x="12" y="'+str(y+10)+'" font-size="12">'+html.escape(text)+'</text>')
    for index, pid in enumerate(ordered):
        x = 12+(index%columns)*legend_column_width; y = (54 if text_scale == 2 else 28)+(index//columns)*(14 if text_scale == 2 else 8)
        displayed_label = layer_labels.get(pid, '#'+str(pid))
        _label(pixels, width, height, displayed_label, x, y, palette[pid], text_scale)
        svg.append('<text x="'+str(x)+'" y="'+str(y+10)+'" fill="rgb'+str(palette[pid])+'" font-size="12">'+html.escape(displayed_label)+'</text>')
        points2 = visible_points[pid]
        if points2:
            lx = int(max(4, min(width-len(str(pid))*8-16, (min(p[0] for p in points2)+max(p[0] for p in points2))/2)))
            ly = int(max(top_margin+4, min(height-bottom_margin-12, (min(p[1] for p in points2)+max(p[1] for p in points2))/2)))
            while any(abs(lx-l['x']) < 48 and abs(ly-l['y']) < 13 for l in labels) and ly+14 < height-bottom_margin-12: ly += 14
            anchor = min(points2, key=lambda point: (point[0]-lx)**2+(point[1]-ly)**2)
            _line(pixels, width, height, anchor, (lx, ly), (70, 70, 70))
            svg.append('<line x1="'+str(anchor[0])+'" y1="'+str(anchor[1])+'" x2="'+str(lx)+'" y2="'+str(ly)+'" stroke="#444" stroke-width=".7"/>')
            _label(pixels, width, height, displayed_label, lx, ly, (10, 10, 10), text_scale)
            svg.append('<text x="'+str(lx)+'" y="'+str(ly+10)+'" font-size="14" fill="black" stroke="white" stroke-width=".3">'+html.escape(displayed_label)+'</text>')
            labels.append({'partId': pid, 'x': lx, 'y': ly, 'anchorPixel': list(anchor),
                           'anchorBasis': 'leader_to_projected_actual_triangle_or_section_edge_including_hidden', 'insideImage': True})
        else: labels.append({'partId': pid, 'x': x, 'y': y, 'anchorBasis': 'legend_only_no_visible_edges', 'insideImage': 0 <= y < height})
    # An explicit metre scale bar, not an unspecified view-dependent zoom.
    bar_m = 10**math.floor(math.log10(max(.0001, (width/5)/scale)))
    a, b = (24, height-24), (24+bar_m*scale, height-24)
    _line(pixels, width, height, a, b, (20, 20, 20))
    _label(pixels, width, height, format(bar_m, '.5g')+' M', 24, height-38, (20, 20, 20), text_scale)
    svg.append('<line x1="24" y1="'+str(height-24)+'" x2="'+str(b[0])+'" y2="'+str(height-24)+'" stroke="black" stroke-width="2"/>')
    svg.append('<text x="24" y="'+str(height-30)+'" font-size="12">'+format(bar_m, '.5g')+' m</text></svg>')
    svg_path, png_path = directory/(name+'.svg'), directory/(name+'.png')
    svg_path.write_text('\n'.join(svg), encoding='utf-8'); _png(png_path, width, height, pixels)
    return {'path': str(png_path), 'svgPath': str(svg_path), 'kind': 'actual_mesh_analysis_wireframe', 'viewed': False,
            'partIds': ordered, 'axes': {'horizontal': 'XYZ'[horizontal], 'vertical': 'XYZ'[vertical]},
            'partColorsRGB': {str(pid): list(palette[pid]) for pid in ordered}, 'labels': labels, 'intersectionOverlays': polygon_records,
            'boundaryAnnotations': boundary_annotations, 'layerLabels': {str(pid): label for pid, label in layer_labels.items()},
            'rasterization': {'method': 'analytic_subpixel_line_coverage', 'antialiasing': True, 'dependencies': 'python_standard_library'},
            'pngText': {'analysis': header, 'axisScale': axis_key, 'units': 'metres'},
            'partProjectedExtentsPixels': {str(pid): {'horizontal': max(p[0] for p in ps)-min(p[0] for p in ps),
                                                    'vertical': max(p[1] for p in ps)-min(p[1] for p in ps)}
                                           for pid, ps in visible_points.items() if ps},
            'pixelsPerMetre': scale, 'focalBoundsWorld': {'min': low, 'max': high}, 'width': width, 'height': height,
            'triangleCount': total, 'renderedTriangleCount': rendered, 'renderComplete': rendered == total,
            'projection': 'orthographic', 'occlusionPolicy': 'all_wireframe_edges_including_hidden_faces',
            'limitations': ['Analysis does not reproduce native paint, lighting, opacity or camera visibility.',
                            'A generated path does not mean this image has been inspected.',
                            'Context and witness views can crop neighbor geometry; image metadata identifies focal bounds.']+
                           ([] if rendered == total else ['Image triangle budget omitted triangles; use local detail or native capture.'])}


def _images(payload, cap, report):
    if not payload.get('outputDir'):
        return {'status': 'not_generated', 'reason': 'outputDir is required for analysis images', 'recommendedImages': [], 'imageRecommendations': []}
    root = Path(payload['outputDir']).expanduser().resolve(); directory = root/('observation-'+uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    budget = payload.get('budget', {}); width = _integer(budget.get('imageWidth', 1024), 'imageWidth', 128)
    height = _integer(budget.get('imageHeight', 768), 'imageHeight', 128)
    image_budget = _integer(budget.get('maxImages', 18), 'maxImages', 1)
    triangle_budget = _integer(budget.get('maxImageTriangles', 6000), 'maxImageTriangles', 1)
    if width > 2048 or height > 2048 or image_budget > 128 or triangle_budget > 100000:
        raise ReferenceError('invalid_input', 'Analysis image budget exceeds local ceiling')
    recommendations, skipped = [], []
    ids = sorted(set(report['coverage']['subjectPartIds']+report['coverage']['impactPartIds']))
    palette = {int(pid): tuple(color) for pid, color in report.get('partColorsRGB', {}).items()} or _palette(ids)
    available = {pid: cap['triangles'][pid] for pid in ids if pid in cap['triangles']}
    def emit(name, triangles, axes, purpose, view_role='detail', **kwargs):
        if len(recommendations) >= image_budget:
            skipped.append({'name': name, 'reason': 'image_budget_exceeded', 'purpose': purpose, 'partIds': sorted(triangles), 'viewRole': view_role}); return None
        image = _view(directory, name, triangles, axes, width, height, triangle_budget, palette=kwargs.pop('palette', palette), **kwargs)
        if image:
            image.update(purpose=purpose, viewRole=view_role, identity=cap['identity'], geometryStamp=cap['geometryStamp'])
            recommendations.append(image); return image
        skipped.append({'name': name, 'reason': 'no_actual_geometry', 'purpose': purpose, 'partIds': sorted(triangles), 'viewRole': view_role})
        return None
    subjects = report['coverage']['subjectPartIds']; subject_triangles = [t for pid in subjects for t in available.get(pid, [])]
    subject_bounds = bounds(subject_triangles)
    local_ids = set(subjects)
    for relation in report['relations']:
        if relation['kind'] == 'geometric_proximity' and relation.get('withinNeighborDistance') is not False: local_ids.update(relation['partIds'])
    local = {pid: available[pid] for pid in sorted(local_ids) if pid in available}
    distant_ids = sorted(set(available)-set(local))
    roi = None
    if subject_bounds:
        margins = [max(.025, (subject_bounds['max'][i]-subject_bounds['min'][i])*.15) for i in range(3)]
        roi = {'min': [subject_bounds['min'][i]-margins[i] for i in range(3)],
               'max': [subject_bounds['max'][i]+margins[i] for i in range(3)]}
    actual_edges = [{'partId': part['partId'], **edge} for part in report.get('boundaryReview', {}).get('parts', [])
                    for edge in part.get('edges', []) if edge.get('kind') in ('free_boundary', 'sharp_crease', 'open_boundary', 'crease_edge', 'non_manifold')]
    actual_edges.sort(key=lambda edge: (edge['partId'] not in subjects, -edge.get('lengthM', 0)))
    for axes in ((0, 1), (0, 2), (2, 1)):
        image = emit('context-'+''.join('xyz'[i] for i in axes), local, axes,
             'Local subject ROI with geometric neighbors; distant native attachments remain in relationships and overview',
             view_role='local_context', focal_bounds=roi, edge_overlays=actual_edges[:64])
        if image: image['boundaryOverlayCoverage'] = {'available': len(actual_edges), 'rendered': min(len(actual_edges), 64),
                                                     'status': 'complete_for_available_edges' if len(actual_edges) <= 64 else 'annotation_budget_exceeded'}
    # Reserve each subject's independent shape and a genuine interior section
    # before issue candidates can consume the budget.
    section_choices = {}
    for pid in subjects:
        emit('part-'+str(pid)+'-isolation', {pid: available.get(pid, [])}, _best_axes(available.get(pid, [])),
             'Actual independent shape; pair with local context', view_role='subject_isolation')
    for pid in subjects:
        candidates = [s for s in report['sections'] if s['partId'] == pid and s.get('segments')]
        if candidates:
            bs = cap['bounds'].get(pid)
            candidate = min(candidates, key=lambda s: abs(s['stationM']-(bs['min'][s['axis']]+bs['max'][s['axis']])/2))
            section_choices[pid] = candidate
            axes = tuple(i for i in range(3) if i != candidate['axis'])
            emit('part-'+str(pid)+'-section', {pid: []}, axes,
                 'Actual native interior section contour at '+('XYZ'[candidate['axis']])+'='+format(candidate['stationM'], '.6g')+' m',
                 view_role='subject_section', sections=[candidate])
        else:
            skipped.append({'name': 'part-'+str(pid)+'-section', 'reason': 'no_actual_section_available', 'partIds': [pid], 'viewRole': 'subject_section'})
    # Every layer retains actual captured triangles and an explicit identity.
    # All layers in each comparison share ONE projection, scale and world ROI.
    comparison = _comparison_layers(payload, cap, report)
    comparison_images = []
    if len(comparison['sources']) > 1:
        layers = comparison['triangles']; labels = comparison['labels']; layer_palette = _palette(layers)
        for record in comparison['layerRecords']:
            if record['sourceLayer'] == 'after': layer_palette[record['layerKey']] = palette[record['sourcePartId']]
        used_colors = {layer_palette[record['layerKey']] for record in comparison['layerRecords'] if record['sourceLayer'] == 'after'}
        for record in comparison['layerRecords']:
            if record['sourceLayer'] == 'after': continue
            key = record['layerKey']; color = layer_palette[key]
            while color in used_colors: color = ((color[0]+17)%220+20, (color[1]+31)%220+20, (color[2]+47)%220+20)
            layer_palette[key] = color; used_colors.add(color)
        def identify_comparison(image):
            lookup = {record['layerKey']: record for record in comparison['layerRecords']}
            image['analysisLayerKeys'] = image['partIds']; image['partIds'] = ids
            image['layerColorsRGB'] = image.pop('partColorsRGB'); image['partColorsRGB'] = {str(pid): list(palette[pid]) for pid in ids}
            image['layerCoverage'] = [{'layerKey': record['layerKey'], 'sourceLayer': record['sourceLayer'], 'sourcePartId': record['sourcePartId'],
                                       'status': 'included' if record['layerKey'] in image['analysisLayerKeys'] else 'no_plane_intersection_or_unavailable',
                                       'projectedExtentPixels': image['partProjectedExtentsPixels'].get(str(record['layerKey']))}
                                      for record in comparison['layerRecords']]
            for label in image['labels']:
                record = lookup[label.pop('partId')]; label.update(record)
                if record['sourceLayer'] == 'after': label['partId'] = record['sourcePartId']
        compare_bounds = comparison.get('commonBoundsWorld') or bounds([tri for group in layers.values() for tri in group])
        for axes in ((0, 1), (0, 2), (2, 1)):
            image = emit('comparison-'+''.join('xyz'[i] for i in axes), layers, axes,
                         'Actual before/after/reference mesh overlay in identical world metre projection; no registration is guessed',
                         view_role='mesh_comparison', focal_bounds=compare_bounds, palette=layer_palette, layer_labels=labels)
            if image:
                identify_comparison(image)
                image.update(sourceProvenance=comparison['sources'], layers=comparison['layerRecords'], semanticIdentityContinuity=comparison['semanticContinuity'])
                comparison_images.append(image['path'])
        # Independent current section stations, not before/after-specific auto-fit.
        chosen = list(section_choices.values())
        remaining_sections = [s for s in report['sections'] if s.get('segments') and s not in chosen]
        remaining_sections.sort(key=lambda s: (s['partId'] not in subjects, s['partId'], s['stationM']))
        chosen = (chosen+remaining_sections)[:max(3, len(subjects))]
        for index, current_section in enumerate(chosen):
            station, axis = current_section['stationM'], current_section['axis']; slice_layers = []; empty = {}
            for key, triangles in layers.items():
                result = section(triangles, axis, station)
                if result.get('segments'): slice_layers.append({'partId': key, **result}); empty[key] = []
            if len(slice_layers) < 2: continue
            image = emit('comparison-section-'+str(index), empty, tuple(i for i in range(3) if i != axis),
                         'Actual same-plane contours; '+('XYZ'[axis])+'='+format(station, '.6g')+' m',
                         view_role='section_comparison', sections=slice_layers, palette=layer_palette, layer_labels=labels)
            if image:
                identify_comparison(image)
                image.update(sourceProvenance=comparison['sources'], layers=comparison['layerRecords'], plane={'axis': axis, 'stationM': station})
                comparison_images.append(image['path'])
    report['comparisonPresentation'] = {k: v for k, v in comparison.items() if k not in ('triangles', 'labels')}
    report['comparisonPresentation'].update(images=comparison_images, visualAcceptance='unreviewed')
    # A remote dependency overview is explicitly separate from the local ROI.
    if distant_ids:
        emit('dependencies-overview', available, _best_axes([t for group in available.values() for t in group]),
             'Remote native dependencies overview; does not replace local fit inspection', view_role='dependency_overview')
    focus = list(report['findings'])
    for check in report['subjectChecks']+report['impactChecks']:
        if check['status'] != 'failed': continue
        measured = check.get('measured', {}); samples = measured.get('samples', [])
        row = max(samples, key=lambda x: x.get('gapM', 0)+x.get('angleDegrees', 0)) if samples else {}
        p = row.get('pointWorld') or next(iter(check.get('expected', {}).get('points', [])), None)
        if p:
            focus.insert(0, {'id': check['id'], 'partIds': check['partIds'], 'witnessWorld': p, 'measured': measured,
                             'kind': check['kind'], 'expected': check.get('expected'), 'failedCheck': True})
    # Select a representative for each real relationship/boundary, then rotate
    # subjects. Four triangles of one overlap must not hide the opposite side.
    representatives = {}
    for finding in focus:
        key = (tuple(sorted(finding['partIds'])), finding['kind'], finding['id'] if finding.get('failedCheck') else '')
        current = representatives.get(key)
        score = _focus_score(finding)
        if current is None or score > _focus_score(current): representatives[key] = finding
    buckets = {pid: sorted([f for f in representatives.values() if pid in f['partIds']], key=_focus_score, reverse=True) for pid in subjects}
    selected = []; selected_ids = set()
    while any(buckets.values()):
        for pid in subjects:
            while buckets[pid] and buckets[pid][0]['id'] in selected_ids: buckets[pid].pop(0)
            if buckets[pid]:
                finding = buckets[pid].pop(0); selected.append(finding); selected_ids.add(finding['id'])
    for j, finding in enumerate(selected):
        p = finding.get('witnessWorld')
        if not p: continue
        measured = finding.get('measured', {}); polygon = measured.get('polygonWorld')
        points = polygon or [p]+[measured[k] for k in ('witnessAWorld', 'witnessBWorld') if measured.get(k)]
        low = [min(q[i] for q in points) for i in range(3)]; high = [max(q[i] for q in points) for i in range(3)]
        margins = [max(.025, (high[i]-low[i])*.2) for i in range(3)]
        focal = {'min': [low[i]-margins[i] for i in range(3)], 'max': [high[i]+margins[i] for i in range(3)]}
        group = {pid: available.get(pid, []) for pid in finding['partIds']}
        axes = _finding_axes(finding, [t for triangles in group.values() for t in triangles])
        image = emit('finding-'+str(j)+'-'+''.join('xyz'[i] for i in axes), group, axes,
                     finding.get('kind', 'geometry_issue')+' witness; red polygon is the measured overlap; visibility unresolved',
                     view_role='issue_detail', witnesses=[p], focal_bounds=focal, polygons=[polygon] if polygon else [])
        if image: image.update(issueId=finding['id'], pairedPartIds=finding['partIds'], viewSelection='largest_actual_polygon_projection_or_gap_projection')
    # Spare budget can add more sections, round-robin by subject.
    for pid in subjects:
        for j, s in enumerate(report['sections']):
            if s['partId'] != pid or not s.get('segments') or s == section_choices.get(pid): continue
            axes = tuple(i for i in range(3) if i != s['axis'])
            emit('section-'+str(j), {pid: []}, axes, 'Additional actual section at '+format(s['stationM'], '.6g')+' m', view_role='additional_section', sections=[s])
    return {'status': 'generated_with_limits' if skipped else 'generated_unreviewed', 'outputDirectory': str(directory),
            'recommendedImages': [r['path'] for r in recommendations], 'imageRecommendations': recommendations, 'skippedImages': skipped,
            'localContextBoundsWorld': roi, 'localContextPartIds': sorted(local), 'remoteDependencyPartIds': distant_ids,
            'partColorsRGB': {str(pid): list(color) for pid, color in palette.items()},
            'subjectImageCoverage': {str(pid): {'isolation': any(r['viewRole'] == 'subject_isolation' and pid in r['partIds'] for r in recommendations),
                                               'section': any(r['viewRole'] == 'subject_section' and pid in r['partIds'] for r in recommendations),
                                               'issueDetail': any(r['viewRole'] == 'issue_detail' and pid in r['partIds'] for r in recommendations)} for pid in subjects},
            'visualAcceptance': 'unreviewed', 'nativeMaterialAcceptance': 'not_observed',
            'limitations': ['Images are measured geometry linework with hidden edges, not native screenshots.',
                            'PNG linework uses subpixel coverage antialiasing; SVG permits lossless zoom.']}


def _comparison_layers(payload, cap, report):
    all_ids = set(report['coverage']['subjectPartIds']+report['coverage']['impactPartIds'])
    local_ids = set(report['coverage']['subjectPartIds'])
    for relation in report['relations']+report.get('baselineRelations', []):
        if relation['kind'] == 'geometric_proximity' and relation.get('withinNeighborDistance') is not False: local_ids.update(relation['partIds'])
    ids = sorted(local_ids & all_ids)
    layers = {}; labels = {}; records = []; sources = []; next_key = 1
    def add(kind, triangles, provenance):
        nonlocal next_key
        sources.append({'layer': kind, **provenance})
        for pid in sorted(triangles):
            if not triangles[pid]: continue
            key = next_key; next_key += 1; layers[key] = triangles[pid]; labels[key] = kind.upper()+' #'+str(pid)
            records.append({'layerKey': key, 'sourceLayer': kind, 'sourcePartId': pid, 'label': labels[key]})
    add('after', {pid: cap['triangles'].get(pid, []) for pid in ids},
        {'identity': cap['identity'], 'geometryStamp': cap['geometryStamp'], 'sampleId': cap['mesh']['sampleId'],
         'units': 'metres', 'coordinateFrame': 'world', 'frameToWorldRows': cap['mesh']['frameToWorldRows'], 'basis': 'actual_native_render_mesh'})
    if payload.get('baseline'):
        before = capture(payload['baseline'].get('snapshot'), payload['baseline'].get('mesh') or payload['baseline'].get('actualMesh'))
        before_ids = set(ids)
        for replacement in report.get('impactPropagation', {}).get('semanticReplacements', []):
            if set(replacement['toPartIds']) & set(ids):
                before_ids -= set(replacement['toPartIds']); before_ids.update(replacement['fromPartIds'])
        add('before', {pid: before['triangles'].get(pid, []) for pid in sorted(before_ids)},
            {'identity': before['identity'], 'geometryStamp': before['geometryStamp'], 'sampleId': before['mesh']['sampleId'],
             'units': 'metres', 'coordinateFrame': 'world', 'frameToWorldRows': before['mesh']['frameToWorldRows'], 'basis': 'actual_native_render_mesh',
             'semanticReplacements': report.get('impactPropagation', {}).get('semanticReplacements', [])})
    common_bounds = bounds([tri for group in layers.values() for tri in group])
    if common_bounds:
        margins = [max(.25, (common_bounds['max'][i]-common_bounds['min'][i])*.15) for i in range(3)]
        common_bounds = {'min': [common_bounds['min'][i]-margins[i] for i in range(3)],
                         'max': [common_bounds['max'][i]+margins[i] for i in range(3)]}
    if payload.get('referenceMesh'):
        from boundary_review import normalize_reference
        reference = normalize_reference(payload['referenceMesh'])
        matches = payload.get('referenceMatches', [])
        reference_ids = {pid for match in matches if set(match.get('partIds', [])) & set(ids) for pid in match.get('referencePartIds', [])}
        if not reference_ids: reference_ids = set(payload.get('referencePartIds') or reference['triangles'])
        selected_reference = {pid: reference['triangles'].get(pid, []) for pid in reference_ids}
        counts = {str(pid): len(triangles) for pid, triangles in selected_reference.items()}
        if common_bounds:
            def within_roi(tri):
                return all(max(p[axis] for p in tri) >= common_bounds['min'][axis] and
                           min(p[axis] for p in tri) <= common_bounds['max'][axis] for axis in range(3))
            selected_reference = {pid: [tri for tri in triangles if within_roi(tri)] for pid, triangles in selected_reference.items()}
        add('reference', selected_reference,
            {'identity': reference['identity'], 'sourceProvenance': reference['sourceProvenance'],
             'units': 'metres', 'coordinateFrame': 'world', 'basis': 'source_mesh_with_explicit_affine_transform',
             'localROIScope': {'boundsWorld': common_bounds, 'sourceTriangleCounts': counts,
                               'displayedTriangleCounts': {str(pid): len(triangles) for pid, triangles in selected_reference.items()},
                               'meaning': 'Reference triangles outside the actual before/after local ROI are omitted from this view; no fidelity conclusion follows.'},
             'mappingBasis': 'declared_reference_matches' if matches else 'source_scope_only_no_semantic_match'})
    return {'status': 'comparison_available_unreviewed' if len(sources) > 1 else 'no_baseline_or_reference_supplied',
            'sources': sources, 'triangles': layers, 'labels': labels, 'layerRecords': records,
            'localPartIds': ids, 'remoteDependencyPartIds': sorted(all_ids-set(ids)),
            'commonBoundsWorld': common_bounds,
            'semanticContinuity': [{'partId': c.get('partId'), 'semanticId': c.get('semanticId'),
                                    'fromPartIds': c.get('fromPartIds'), 'toPartIds': c.get('toPartIds'),
                                    'status': c.get('identityContinuity')} for c in report.get('changes', [])],
            'limitations': ['One projection and scale per overlay; source transforms are explicit and never auto-registered.',
                            'Spatial overlay does not establish semantic continuity for reused or replaced part IDs.',
                            'Rendered triangles can be budget-limited; image records identify any omissions.']}


def _relationship_presentation(report, cap, images, payload):
    categories = {'attachment': [], 'geometry': [], 'cutting': [], 'symmetry': [], 'dependency': [], 'unclassified': []}
    for relation in report['relations']:
        kind = relation['kind']
        category = 'attachment' if kind == 'native_attachment' else 'geometry' if kind in ('geometric_proximity','geometric_shared_boundary_candidate') else 'symmetry' if kind == 'native_symmetry_group' else 'cutting' if kind in ('cut_or_target_dependency','implicit_cut_or_target_dependency') else 'dependency' if kind == 'nested_native_dependency' else 'unclassified'
        if kind == 'nested_native_dependency' and any(any(label in str(cap['parts'].get(str(pid),{}).get('type','')).lower() for label in ('hole','window')) for pid in relation['partIds']):
            category = 'cutting'
        entry = dict(relation)
        ids = relation['partIds']; members = ', '.join('#'+str(pid) for pid in ids)
        distance = relation.get('distanceM')
        if kind == 'geometric_shared_boundary_candidate':
            entry['readable'] = members+': actual boundary proximity candidate; inspect the listed edge witnesses. Shared continuity requires a declared expectation and complete boundary measurement'
        elif category == 'geometry':
            entry['readable'] = members+': measured nearest surface separation '+(format(distance, '.6g')+' m' if distance is not None else 'unresolved')+'; continuity is not implied'
        elif category == 'attachment': entry['readable'] = members+': native assembly attachment; surface continuity and physical support require separate evidence'
        elif category == 'symmetry': entry['readable'] = members+': native symmetry group; actual shape equivalence requires checking both sides'
        elif category == 'cutting': entry['readable'] = members+': native targeting/dependency '+str(relation.get('attribute') or relation.get('targetMode') or '')+'; actual clipping effect requires mesh inspection'
        elif category == 'dependency': entry['readable'] = members+': native ownership/reference dependency; no clipping or load-bearing conclusion'
        else: entry['readable'] = members+': unclassified relationship '+str(kind)+'; no clipping or continuity claim'
        categories[category].append(entry)
    expected = [{'id': row['id'], 'partIds': row.get('partIds', []), 'boundaryIds': row.get('boundaryIds', []),
                 'basis': 'explicit_expected_interface_criterion', 'expected': row.get('expected'),
                 'status': row['status'], 'measured': row.get('measured'),
                 'meaning': 'Declared continuity expectation, distinct from observed attachment or proximity'}
                for row in report.get('subjectChecks', [])+report.get('impactChecks', []) if row.get('kind') in ('interface', 'seam', 'expected_interface', 'surface_continuity') or row.get('expected', {}).get('a')]
    result = {'identity': cap['identity'], 'geometryStamp': cap['geometryStamp'], 'units': 'metres', 'coordinateFrame': 'world',
              'categories': categories, 'expectedBoundaries': expected, 'graphs': [],
              'limitations': ['Relation graphs are logical diagrams, not spatial or load-bearing diagrams.',
                              'Geometric relation witnesses refer to actual world positions in the spatial images.']}
    if not images.get('outputDirectory'): return result
    directory = Path(images['outputDirectory']); max_images = payload.get('budget', {}).get('maxImages', 18)
    for category, relations in categories.items():
        if not relations: continue
        if len(images['imageRecommendations']) >= max_images:
            images['skippedImages'].append({'name': 'relations-'+category, 'viewRole': 'typed_relation_graph', 'reason': 'image_budget_exceeded'}); continue
        graph = _relationship_graph(directory, category, relations, report['partColorsRGB'], cap['identity'])
        result['graphs'].append(graph); images['imageRecommendations'].append(graph); images['recommendedImages'].append(graph['path'])
    return result


def _relationship_graph(directory, category, relations, palette, identity):
    ids = sorted({pid for row in relations for pid in row['partIds']}); shown_ids = ids[:40]
    shown = [row for row in relations if set(row['partIds']) <= set(shown_ids)][:60]
    width, height = 1000, 760; pixels = bytearray([250]*(width*height*3))
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="760"><rect width="100%" height="100%" fill="#fafafa"/>']
    title = category.upper()+' RELATIONS | LOGICAL GRAPH | NOT SPATIAL'
    _label(pixels, width, height, title, 12, 12, (20, 20, 20), 2)
    svg.append('<text x="12" y="24" font-size="16">'+title+'</text>')
    _label(pixels, width, height, 'WORLD WITNESS DISTANCES IN M | NO SUPPORT CONCLUSION', 12, 34, (50, 50, 50), 1)
    positions = {pid: (width/2+310*math.cos(2*math.pi*i/max(1, len(shown_ids))), 360+250*math.sin(2*math.pi*i/max(1, len(shown_ids)))) for i, pid in enumerate(shown_ids)}
    graph_edges = []
    for index, row in enumerate(shown):
        owner = row.get('ownerPartId', row['partIds'][0]); targets = row.get('targetPartIds') or row['partIds'][1:]
        for other in targets:
            if owner not in positions or other not in positions or owner == other: continue
            a, b = positions[owner], positions[other]; _line(pixels, width, height, a, b, (115, 115, 115))
            svg.append('<line x1="'+str(a[0])+'" y1="'+str(a[1])+'" x2="'+str(b[0])+'" y2="'+str(b[1])+'" stroke="#777"/>')
            label = row['kind'].replace('native_', '').replace('geometric_', '')
            if row.get('distanceM') is not None: label += ' '+format(row['distanceM'], '.4g')+' M'
            x, y = (a[0]+b[0])/2, (a[1]+b[1])/2+(index%3)*10
            _label(pixels, width, height, label, int(x), int(y), (25, 25, 25), 1)
            svg.append('<text x="'+str(x)+'" y="'+str(y)+'" font-size="10">'+html.escape(label)+'</text>')
            graph_edges.append({'fromPartId': owner, 'toPartId': other, 'kind': row['kind'], 'relationId': row.get('id'),
                                'witnessAWorld': row.get('witnessAWorld'), 'witnessBWorld': row.get('witnessBWorld'), 'distanceM': row.get('distanceM')})
    for pid, (x, y) in positions.items():
        color = tuple(palette[str(pid)]) if str(pid) in palette else (80, 80, 80)
        for ox in range(-6, 7):
            for oy in range(-6, 7):
                if ox*ox+oy*oy <= 36: _pixel(pixels, width, height, int(x)+ox, int(y)+oy, color)
        _label(pixels, width, height, '#'+str(pid), int(x)+9, int(y)-5, color, 2)
        svg.append('<circle cx="'+str(x)+'" cy="'+str(y)+'" r="6" fill="rgb'+str(color)+'"/><text x="'+str(x+9)+'" y="'+str(y)+'" fill="rgb'+str(color)+'">#'+str(pid)+'</text>')
    svg.append('</svg>'); svg_path = directory/('relations-'+category+'.svg'); png_path = directory/('relations-'+category+'.png')
    svg_path.write_text('\n'.join(svg), encoding='utf-8'); _png(png_path, width, height, pixels)
    return {'path': str(png_path), 'svgPath': str(svg_path), 'kind': 'typed_relationship_graph', 'viewRole': 'typed_relation_graph',
            'category': category, 'identity': identity, 'partIds': shown_ids, 'graphEdges': graph_edges,
            'partColorsRGB': {str(pid): palette.get(str(pid), [80, 80, 80]) for pid in shown_ids},
            'labels': [{'partId': pid, 'x': x, 'y': y, 'anchorBasis': 'logical_relation_graph_node_not_world_geometry', 'insideImage': True}
                       for pid, (x, y) in positions.items()],
            'diagramCoordinates': 'logical_layout_pixels_not_world_geometry', 'viewed': False,
            'coverage': {'status': 'complete' if len(shown) == len(relations) and len(shown_ids) == len(ids) else 'graph_budget_exceeded',
                         'relationCount': len(relations), 'renderedRelationCount': len(shown), 'partCount': len(ids), 'renderedPartCount': len(shown_ids)},
            'limitations': ['Graph locations are not physical positions; use companion actual-mesh context images.', 'A generated graph is unreviewed.']}


def _best_axes(triangles):
    bs = bounds(triangles)
    if not bs: return (2, 1)
    return max(((0, 1), (0, 2), (2, 1)), key=lambda axes: (bs['max'][axes[0]]-bs['min'][axes[0]])*(bs['max'][axes[1]]-bs['min'][axes[1]]))


def _focus_score(finding):
    measured = finding.get('measured', {})
    return (1 if finding.get('failedCheck') else 0, measured.get('areaM2', 0), measured.get('distanceM', 0))


def _finding_axes(finding, triangles):
    measured = finding.get('measured', {}); polygon = measured.get('polygonWorld')
    axes = ((0, 1), (0, 2), (2, 1))
    if polygon:
        def area(pair):
            i, j = pair
            return abs(sum(a[i]*b[j]-b[i]*a[j] for a, b in zip(polygon, polygon[1:]+polygon[:1])))/2
        return max(axes, key=area)
    if measured.get('witnessAWorld') and measured.get('witnessBWorld'):
        delta = sub(measured['witnessAWorld'], measured['witnessBWorld'])
        return max(axes, key=lambda pair: sum(delta[i]**2 for i in pair))
    return _best_axes(triangles)


def _construction(part, payload, cap, pid):
    """Keep authored native controls distinct from effective native defaults."""
    controls = []; section_count = 0; authored_flags = {}
    def walk(node, path='', in_shape=False):
        nonlocal section_count
        if not isinstance(node, dict): return
        tag = node.get('tag') or node.get('element') or 'unknown'
        shape = in_shape or any(token in tag.lower() for token in ('fuselage', 'curved', 'wing', 'hole'))
        if shape:
            if tag == 'Slice': section_count += 1
            for field, value in node.get('attributes', {}).items():
                if field not in ('mass', 'drag', 'dragArea'):
                    controls.append({'nativePath': path+'/'+tag+'/@'+field, 'literal': value, 'basis': 'native_authored_serialized_state',
                                     'effectiveDefaultKnown': False})
                    if field.lower() in ('hollow', 'cutting', 'targetmode'): authored_flags.setdefault(field, []).append(value)
        counts = {}
        for child in node.get('children', []):
            name = child.get('tag') or child.get('element') or 'unknown'; index = counts.get(name, 0); counts[name] = index+1
            walk(child, path+'/'+tag+'/'+str(index), shape)
    walk(part.get('serializedState') or part.get('state'))
    effective = None; evidence = payload.get('shapeEvidence', {}).get(str(pid)); unavailable = None
    if isinstance(evidence, dict) and evidence.get('success') is False:
        unavailable = evidence.get('error', {}); evidence = None
    if evidence is not None:
        value = _document(evidence, 'shapeEvidence')
        if value.get('identity') != cap['identity']:
            raise ReferenceError('evidence_identity_mismatch', 'Effective shape evidence must match snapshot and actual mesh', partId=pid)
        if value.get('partId', value.get('id')) != pid:
            raise ReferenceError('part_not_found', 'Effective shape evidence refers to a different part', partId=pid)
        effective = value.get('shape') or value.get('configuration') or value
    return {'authoredPositionWorld': part.get('position'), 'rotationQuaternion': part.get('rotationQuaternion'),
            'scale': part.get('scale'), 'materialIds': part.get('materialIds'), 'authoredControls': controls,
            'controlSummary': {'authoredSectionControlCount': section_count, 'explicitAuthoredFlags': authored_flags,
                               'basis': 'native_authored_serialized_state',
                               'caution': 'Control section count and hollow/cutting declarations do not certify actual cut topology.'},
            'effectiveShape': effective, 'effectiveShapeStatus': 'same_state_native_read' if evidence else 'unavailable' if unavailable is not None else 'not_supplied',
            'effectiveShapeError': unavailable,
            'parameters': 'Authored controls explain construction; effective shape.get data is separate from the actual clipped mesh.',
            'limitations': ['Missing native defaults are unknown without same-state shape.get evidence.',
                            'A Curved middle slice is a control and is not necessarily the physical midpoint contour.']}


def _shape_description(pid, triangles, bs, sections):
    """Measured contour trends, without forcing meshes into primitive classes."""
    observed = []; rows = [s for s in sections if s['partId'] == pid and s.get('segments')]
    for s in rows:
        vertices = [p for segment in s['segments'] for p in (segment['a'], segment['b'])]
        spans = {('XYZ'[axis]): max(p[axis] for p in vertices)-min(p[axis] for p in vertices) for axis in range(3) if axis != s['axis']}
        observed.append({'axis': 'XYZ'[s['axis']], 'stationM': s['stationM'], 'transverseSpansM': spans,
                         'closedLoopCount': s.get('closedLoopCount'), 'openEndpointCount': s['openEndpointCount'],
                         'nestedContourLoops': s.get('nestedContourLoops', False), 'basis': s['basis']})
    trends = []
    for station_axis in sorted({s['axis'] for s in observed}):
        stations = sorted((s for s in observed if s['axis'] == station_axis), key=lambda s: s['stationM'])
        if len(stations) < 2: continue
        for transverse in stations[0]['transverseSpansM']:
            values = [s['transverseSpansM'][transverse] for s in stations]
            changes = [b-a for a, b in zip(values, values[1:])]; tolerance = max(1e-6, max(values)*1e-6)
            direction = 'constant_at_sampled_stations' if all(abs(x) <= tolerance for x in changes) else \
                        'narrows_toward_positive_axis' if all(x <= tolerance for x in changes) else \
                        'widens_toward_positive_axis' if all(x >= -tolerance for x in changes) else 'nonmonotonic_at_sampled_stations'
            trends.append({'stationAxis': station_axis, 'spanAxis': transverse, 'trend': direction,
                           'firstSpanM': values[0], 'lastSpanM': values[-1], 'minSpanM': min(values), 'maxSpanM': max(values),
                           'maxAtStationM': stations[values.index(max(values))]['stationM'],
                           'basis': 'actual_native_section_envelopes', 'stationCount': len(values)})
    directions = {}; first_normal = None; first_point = None; planar = bool(triangles)
    for tri in triangles:
        n = normal(tri)
        if n is None: continue
        if first_normal is None: first_normal, first_point = n, tri[0]
        if abs(dot(n, first_normal)) < .99999 or max(abs(dot(sub(p, first_point), first_normal)) for p in tri) > 1e-5: planar = False
        axis = max(range(3), key=lambda i: abs(n[i])); direction = ('+' if n[axis] >= 0 else '-')+'XYZ'[axis]
        if abs(n[axis]) < .95: direction = 'oblique'
        directions[direction] = directions.get(direction, 0)+1
    descriptions = []
    if bs:
        descriptions.append('World ranges '+', '.join('XYZ'[i]+' ['+format(bs['min'][i], '.5g')+', '+format(bs['max'][i], '.5g')+'] m' for i in range(3)))
    for t in trends:
        descriptions.append('Along +'+t['stationAxis']+', '+t['spanAxis']+' span '+format(t['firstSpanM'], '.5g')+' → '+format(t['lastSpanM'], '.5g')+' m ('+t['trend']+', '+str(t['stationCount'])+' stations)')
    if observed:
        descriptions.append('Observed closed contour counts: '+', '.join(str(s['closedLoopCount'])+' at '+s['axis']+'='+format(s['stationM'], '.5g') for s in observed[:8]))
    descriptions.append('No nondegenerate face normal was observed' if first_normal is None else
                        'All nondegenerate observed faces lie in one plane within 0.01 mm' if planar else
                        'Multiple face orientations or planes observed; no primitive or smooth-curvature classification is assumed')
    if any(s['nestedContourLoops'] for s in observed): descriptions.append('Nested loops indicate a cavity candidate at those stations only')
    return {'description': '; '.join(descriptions), 'observedSections': observed, 'contourTrends': trends,
            'normalDirectionTriangleCounts': directions, 'singlePlaneCandidate': planar and first_normal is not None,
            'basis': 'actual_native_triangles_and_plane_sections',
            'limitations': ['Finite section extrema and trends do not prove unsampled spans or global hollowness.',
                            'Normal direction counts are triangle counts, not surface area or visible-face ownership.']}


def compact_report(report):
    """Progressive presentation backed by the immutable full report artifact.

    Abbreviated checks are navigation records, never fresh measurement evidence.
    The goal loop consumes the full report path or detail=full response.
    """
    cards=[]
    for card in report['parts']:
        geometry=card['actualGeometry'];brief=geometry['geometryBrief']
        row={key:card[key] for key in ('partId','nativeType','name','summary','construction','editingData','imageReferences')}
        row['actualGeometry']={'boundsWorld':geometry['boundsWorld'],'axisExtentsM':geometry['axisExtentsM'],
            'description':brief['description'],'contourTrends':brief['contourTrends'],
            'observedSectionCount':len(brief['observedSections']),
            'details':'reportArtifact.path parts[].actualGeometry; actual contours, triangles and full checks retained there'}
        cards.append(row)
    result={'kind':report['kind'],'detail':'summary','identity':report['identity'],'geometryStamp':report['geometryStamp'],
            'parts':cards,'relations':report['relationshipPresentation']['categories'],
            'relationshipPresentation':report['relationshipPresentation'],
            'coverage':report['coverage'],'reportArtifact':report['reportArtifact'],
            'evidenceFreshness':report.get('evidenceFreshness'),'recommendedImages':report['recommendedImages'],
            'imageRecommendations':[{key:row[key] for key in ('path','viewRole','partIds','projection','viewed') if key in row} for row in report['imageRecommendations']],
            'nativeViewPlan':report['nativeViewPlan'],
            'detailPolicy':'Abbreviated navigation records do not replace measurement evidence. Supply reportArtifact.path to build.loop.review or request detail=full.',
            'limitations':report.get('limitations',[])}
    for key in ('subjectChecks','impactChecks','findings'):
        result[key]=[{k:row[k] for k in ('id','kind','status','partIds','goalId','reason','witnessWorld') if k in row} for row in report[key]]
    # Keep the public relations array contract; categories remain separately typed.
    result['relations']=report['relations']
    for key in ('captureReceipt','nativeCaptureResults','nativeViewVerification'):
        if key in report: result[key]=report[key]
    return result


def observe(payload, context=None):
    cap = capture(payload.get('snapshot'), payload.get('mesh') or payload.get('actualMesh'))
    report = review(payload, context=context)
    palette = _palette(report['coverage']['subjectPartIds']+report['coverage']['impactPartIds'])
    report['partColorsRGB'] = {str(pid): list(color) for pid, color in palette.items()}
    roles = payload.get('roles', {})
    if not isinstance(roles, dict): raise ReferenceError('invalid_input', 'Observation roles must be an explicit part-ID-to-role object')
    if not isinstance(payload.get('shapeEvidence', {}), dict): raise ReferenceError('invalid_input', 'shapeEvidence must map native part IDs to same-state shape.get results')
    cards = []
    for pid in report['coverage']['subjectPartIds']:
        part = cap['parts'][str(pid)]; triangles = cap['triangles'].get(pid, []); bs = cap['bounds'].get(pid)
        related = [r for r in report['relations'] if pid in r['partIds']]
        problems = [x for x in report['findings'] if pid in x['partIds']]
        issues = [x for x in report['subjectChecks']+report['impactChecks'] if pid in x.get('partIds', []) and x['status'] in ('failed', 'needs_review', 'missing_evidence')]
        top = topology(triangles) if triangles else None
        size = [bs['max'][i]-bs['min'][i] for i in range(3)] if bs else None
        role = roles.get(str(pid))
        geometry_brief = _shape_description(pid, triangles, bs, report['sections'])
        shape = geometry_brief['description'] if top else 'No captured surface; functional or excluded part remains unresolved'
        statements = [{'topic': 'native_type', 'text': str(part.get('typeName') or part.get('type') or 'unknown'), 'basis': 'native_snapshot', 'confidence': 'observed'},
                      {'topic': 'actual_shape', 'text': shape, 'basis': 'actual_native_triangles', 'confidence': 'measured' if triangles else 'unknown'},
                      {'topic': 'role', 'text': role or 'Unknown; part name alone is not proof of structural purpose',
                       'basis': 'explicit_annotation' if role else 'not_provided', 'confidence': 'annotated' if role else 'unknown'},
                      {'topic': 'position', 'text': 'World-frame bounds and native authored origin are shown separately; ship directions require a verified coordinate annotation',
                       'basis': 'actual_native_triangles_and_native_snapshot', 'confidence': 'measured' if bs else 'unknown'},
                      {'topic': 'relationships', 'text': str(len(related))+' observed or candidate relations; attachment, proximity, targeting and symmetry remain distinct',
                       'basis': 'typed_relationship_records', 'confidence': 'mixed'},
                      {'topic': 'problems', 'text': str(len(problems))+' candidates and '+str(len(issues))+' failed or unresolved checks; no automatic deletion recommendation',
                       'basis': 'regional_review', 'confidence': 'requires_review' if problems or issues else 'finite_checks_only'}]
        cards.append({'partId': pid, 'partHash': cap['partHashes'][str(pid)], 'nativeType': part.get('type'), 'name': part.get('name'),
                      'analysisColorRGB': list(palette[pid]),
                      'summary': statements, 'actualGeometry': {'boundsWorld': bs, 'axisExtentsM': size, 'topology': top,
                          'shapeClassification': 'unclassified_actual_mesh', 'cavityConclusion': 'station_candidates_only', 'geometryBrief': geometry_brief},
                      'construction': _construction(part, payload, cap, pid),
                      'relationships': related, 'findings': problems, 'unresolvedChecks': issues,
                      'editingData': {'snapshotPartId': pid, 'fields': ['position', 'rotationQuaternion', 'scale', 'materialIds', 'serializedState'],
                          'guard': {'identity': cap['identity'], 'partHash': cap['partHashes'][str(pid)]}},
                      'limitations': ['No primitive shape or ship role is guessed from bounds.', 'Native material colors are not observed in analysis images.']})
    report.update(kind='sp2build.partObservation', parts=cards, presentationVersion=2)
    comparison = _comparison_layers(payload, cap, report)
    report['comparisonPresentation'] = {k: v for k, v in comparison.items() if k not in ('triangles', 'labels')}
    report['comparisonPresentation'].update(images=[], visualAcceptance='unreviewed')
    images = _images(payload, cap, report); report['images'] = images
    report['relationshipPresentation'] = _relationship_presentation(report, cap, images, payload)
    if images.get('outputDirectory') and images.get('skippedImages'): images['status'] = 'generated_with_limits'
    report['nativeViewPlan'] = plan_native_views(cap, report, payload)
    if payload.get('nativeCaptureResults') is not None:
        report['nativeViewVerification'] = verify_native_views(report['nativeViewPlan'], payload['nativeCaptureResults'], payload.get('nativeImageReviews'))
    report['recommendedImages'] = images['recommendedImages']; report['imageRecommendations'] = images['imageRecommendations']
    for card in cards:
        card['imageReferences'] = [{'path': image['path'], 'viewRole': image['viewRole'], 'viewed': image.get('viewed', False)}
                                   for image in images['imageRecommendations'] if card['partId'] in image.get('partIds', [])]
        card['relationsByKind'] = {key: [r for r in values if card['partId'] in r['partIds']]
                                  for key, values in report['relationshipPresentation']['categories'].items()}
    if images.get('outputDirectory'):
        report['reportArtifact'] = {'path': str(Path(images['outputDirectory'])/'report.json')}
        artifact = write_json(report['reportArtifact']['path'], report, overwrite=False)
        # Hash cannot include itself; it binds the immutable bytes just written.
        report['reportArtifact'].update(artifact)
    return report


def dispatch(action, payload, context=None):
    if action not in ('parts.observe', 'part.observe'):
        raise ReferenceError('unsupported_command', 'Unsupported part observation action', action=action)
    return observe(payload, context=context)
