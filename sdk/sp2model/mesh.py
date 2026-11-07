"""Captured native indexed meshes and diagnosed complete plane intersections."""
from copy import deepcopy
import math
from .errors import ModelingError
from .geometry import Frame, add, sub, scale, vector, unit, dot, magnitude, rotate, number


class MeshEvidence:
    def __init__(self, sample, data, *, frame=None, _artifact_verified=False):
        self._artifact_verified=_artifact_verified is True
        self.identity=deepcopy(data['identity']);self.sample=deepcopy(sample)
        self.meshes=deepcopy(data['meshes']);self.frame=frame or Frame.world()
        if frame is not None:
            q=self.frame.rotation_quaternion;inverse=(-q[0],-q[1],-q[2],q[3])
            for mesh in self.meshes:
                mesh['vertices']=[list(rotate(inverse,sub(point,self.frame.position))) for point in mesh['vertices']]
                attributes=mesh.get('attributes',{})
                if attributes.get('normalsStatus')=='available':attributes['normals']=[list(rotate(inverse,n)) for n in attributes['normals']]
                if attributes.get('tangentsStatus')=='available':attributes['tangents']=[list(rotate(inverse,t[:3]))+[t[3]] for t in attributes['tangents']]
                if attributes:
                    attributes['nativeAttributeFrame']={'kind':'world'}
                    attributes['attributeFrame']=self.frame.to_dict()
                    rows=attributes.get('meshToFrameRows')
                    if rows is not None:
                        attributes['nativeMeshToWorldRows']=deepcopy(rows)
                        columns=[rotate(inverse,[rows[i][j] for i in range(3)]) for j in range(3)]
                        translation=rotate(inverse,sub([rows[i][3] for i in range(3)],self.frame.position))
                        attributes['meshToFrameRows']=[[columns[j][i] for j in range(3)]+[translation[i]] for i in range(3)]+[[0,0,0,1]]
                    attributes['attributeStampFrame']='native world snapshot; artifact frame conversion is recorded separately'

    def to_dict(self, *, include_geometry=False):
        result={'identity':deepcopy(self.identity),'captureId':self.sample.get('captureId'),
                'geometryStamp':self.sample.get('geometryStamp'),'source':'native indexed meshes with artifact SHA256 verified' if self._artifact_verified else 'supplied indexed meshes; native artifact provenance not verified',
                'artifactSha256Verified':self._artifact_verified,
                'frame':self.frame.to_dict(),'meshCount':len(self.meshes),
                'vertexCount':sum(len(m['vertices']) for m in self.meshes),
                'triangleCount':sum(len(m['indices'])//3 for m in self.meshes),
                'exclusions':deepcopy(self.sample.get('exclusions',[])),
                'meaning':'Captured evidence at this identity; does not refresh references or certify unmeasured geometry.'}
        if include_geometry:result['meshes']=deepcopy(self.meshes)
        return result

    def planar_face(self, mesh_index, triangle_indices, *, boundary, normal, **tolerances):
        """Check a complete convex face footprint, actual normals and planarity.

        Indices belong to this immutable capture. A boundary and normal in this
        evidence frame are mandatory; one flat triangle cannot certify a face.
        """
        from .hard_surfaces import inspect_planar_face
        return inspect_planar_face(self,mesh_index,triangle_indices,boundary=boundary,normal=normal,**tolerances)

    def planar_face_region(self, mesh_index, *, boundary, normal, **options):
        from .hard_surfaces import inspect_face_region
        return inspect_face_region(self,mesh_index,boundary=boundary,normal=normal,**options)

    def section(self, origin, normal, *, weld_tolerance_m=1e-6):
        origin=vector(origin,'section origin metres');normal=unit(normal,'section normal')
        tolerance=number(weld_tolerance_m,'weld_tolerance_m',1e-12,.01)
        by_part={}
        for mesh in self.meshes:by_part.setdefault(mesh['partId'],[]).append(mesh)
        sections=[]
        for identifier,meshes in by_part.items():
            segments=[];coplanar=[];coplanar_count=0
            def key(point):return tuple(round(value/tolerance) for value in point)
            for mesh in meshes:
                vertices=mesh['vertices'];indices=mesh['indices']
                for offset in range(0,len(indices),3):
                    tri=[vertices[indices[offset+i]] for i in range(3)]
                    distances=[dot(sub(point,origin),normal) for point in tri]
                    if all(abs(value)<=tolerance for value in distances):
                        coplanar_count+=1;coplanar.extend((tri[i],tri[(i+1)%3]) for i in range(3));continue
                    points=[]
                    for i in range(3):
                        a,b=tri[i],tri[(i+1)%3];da,db=distances[i],distances[(i+1)%3]
                        if abs(da)<=tolerance:points.append(a)
                        if da*db<0:points.append(add(a,scale(sub(b,a),da/(da-db))))
                    unique=[]
                    for point in points:
                        if not any(magnitude(sub(point,p))<=tolerance for p in unique):unique.append(point)
                    if len(unique)==2:segments.append(tuple(unique))
            coplanar_edges={}
            for a,b in coplanar:
                edge=tuple(sorted((key(a),key(b))))
                if edge[0]==edge[1]:continue
                item=coplanar_edges.setdefault(edge,{'count':0,'segment':(a,b)});item['count']+=1
            segments.extend(item['segment'] for item in coplanar_edges.values() if item['count']%2)
            vertices={};edges={}
            for a,b in segments:
                ka,kb=key(a),key(b)
                if ka==kb:continue
                vertices.setdefault(ka,a);vertices.setdefault(kb,b)
                edges[tuple(sorted((ka,kb)))]=(a,b)
            adjacency={k:set() for k in vertices}
            for a,b in edges:adjacency[a].add(b);adjacency[b].add(a)
            open_nodes=[k for k,v in adjacency.items() if len(v)==1]
            branch_nodes=[k for k,v in adjacency.items() if len(v)>2]
            unused=set(edges);paths=[];loops=[]
            starts=sorted(open_nodes)+sorted(k for k in vertices if k not in open_nodes)
            for start in starts:
                while any(tuple(sorted((start,n))) in unused for n in adjacency[start]):
                    path=[start];current=start
                    while True:
                        choices=sorted(n for n in adjacency[current] if tuple(sorted((current,n))) in unused)
                        if not choices:break
                        next_=choices[0];unused.remove(tuple(sorted((current,next_))))
                        path.append(next_);current=next_
                        if current==start or len(adjacency[current])!=2:break
                    points=[list(vertices[k]) for k in path]
                    if path[-1]==start and len(path)>3 and all(len(adjacency[k])==2 for k in path):loops.append(points)
                    else:paths.append(points)
            closed=bool(loops) and not paths and not branch_nodes
            sections.append({'partId':identifier,'segments':[[list(a),list(b)] for a,b in edges.values()],
                             'loops':loops,'openPaths':paths,'openVertexCount':len(open_nodes),'branchVertexCount':len(branch_nodes),
                             'coplanarTriangleCount':coplanar_count,'closed':closed,
                             'status':'complete' if closed else 'incomplete',
                             'welding':'quantized grid; open or branching paths are never forcibly closed'})
        return {'identity':deepcopy(self.identity),'frame':self.frame.to_dict(),'origin':list(origin),'normal':list(normal),
                'weldToleranceMetres':tolerance,'parts':sections,'unionApplied':False,
                'coverage':'All selected captured mesh triangles at one plane, separated by native part. No inter-part Boolean union or full-surface certificate.'}


def compare_contours(reference, actual, *, tolerance_m, sample_spacing_m=.005, max_samples=250000):
    """Bidirectional point-to-segment distance with an explicit sampling bound."""
    tolerance=number(tolerance_m,'tolerance_m',0)
    spacing=number(sample_spacing_m,'sample_spacing_m',1e-9,1000)
    if type(max_samples) is not int or not 2 <= max_samples <= 10000000:
        raise ModelingError('measurement_budget','max_samples must be an integer in [2, 10000000]')
    def validated(segments):
        result=[]
        for segment in segments:
            if len(segment)!=2:raise ModelingError('invalid_contour','Each segment needs two three-dimensional endpoints')
            a,b=(vector(p,'contour metres') for p in segment)
            if magnitude(sub(a,b))>1e-12:result.append((a,b))
        return result
    reference,actual=validated(reference),validated(actual)
    if not reference or not actual:return {'status':'incomplete','reason':'Empty required contour','coverage':'one supplied contour pair'}
    def distance(point,segments):
        best=math.inf
        for a,b in segments:
            delta=sub(b,a);u=max(0,min(1,dot(sub(point,a),delta)/dot(delta,delta)))
            best=min(best,magnitude(sub(point,add(a,scale(delta,u)))))
        return best
    used=0
    def directed(source,target):
        nonlocal used
        worst=0.;interval=0.;witness=None
        for a,b in source:
            length=magnitude(sub(b,a));count=max(1,math.ceil(length/spacing))
            used+=count+1
            if used>max_samples:raise ModelingError('measurement_budget','Contour sample budget exceeded; choose an explicit spacing/budget')
            interval=max(interval,length/count)
            for i in range(count+1):
                point=add(a,scale(sub(b,a),i/count));value=distance(point,target)
                if value>=worst:worst=value;witness=point
        return {'sampledMaximumMetres':worst,'upperBoundMetres':worst+interval/2,'worstPoint':list(witness)}
    forward=directed(reference,actual);reverse=directed(actual,reference)
    lower=max(forward['sampledMaximumMetres'],reverse['sampledMaximumMetres'])
    upper=max(forward['upperBoundMetres'],reverse['upperBoundMetres'])
    return {'status':'passed' if upper<=tolerance else 'failed' if lower>tolerance else 'incomplete',
            'sampledMaximumMetres':lower,'upperBoundMetres':upper,'toleranceMetres':tolerance,'sampleSpacingMetres':spacing,
            'samples':used,'referenceToActual':forward,'actualToReference':reverse,
            'coverage':'Supplied piecewise-linear contour pair only; bound uses 1-Lipschitz segment distance, not a full mesh surface or semantic correspondence certificate.'}
