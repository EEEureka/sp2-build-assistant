"""Bidirectional distance bounds over explicit piecewise triangular surfaces.

No Boolean union, correspondence, solid occupancy or ideal CAD inference is
performed. A budget-limited unresolved bound remains incomplete.
"""
import heapq
import math
from .errors import ModelingError
from .geometry import vector,sub,add,scale,dot,cross,number


def triangles(values):
    if not isinstance(values,(list,tuple)) or len(values)>200000:raise ModelingError('invalid_surface','Supply at most 200000 explicit triangles')
    result=[]
    for row in values:
        if not isinstance(row,(list,tuple)) or len(row)!=3:
            raise ModelingError('invalid_surface','Each surface triangle needs three 3D vertices')
        tri=tuple(vector(point,'surface metres') for point in row)
        if any(abs(x)>1000000 for p in tri for x in p):raise ModelingError('invalid_surface','Surface coordinates exceed the numerical tool range of one million metres')
        a,b,c=tri;ab=sub(b,a);ac=sub(c,a);area=dot(cross(ab,ac),cross(ab,ac));edge=max(dot(ab,ab),dot(ac,ac))
        if area and area<1e-26*edge*edge:
            raise ModelingError('invalid_surface','Numerically ill-conditioned triangle; review the reference or native geometry')
        result.append(tri)
    return result


def _segment_squared(p,a,b):
    delta=sub(b,a);length=dot(delta,delta)
    t=0 if length==0 else max(0,min(1,dot(sub(p,a),delta)/length))
    diff=sub(p,add(a,scale(delta,t)));return dot(diff,diff)


def _triangle_squared(p,tri):
    a,b,c=tri;ab=sub(b,a);ac=sub(c,a);ap=sub(p,a)
    normal=cross(ab,ac);area=dot(normal,normal)
    if area:
        # Cross products retain the projected barycentrics without subtracting
        # nearly equal squared edge products in the denominator.
        v=dot(cross(ap,ac),normal)/area;w=dot(cross(ab,ap),normal)/area
        if v>=0 and w>=0 and v+w<=1:
            return dot(ap,normal)**2/area
    return min(_segment_squared(p,a,b),_segment_squared(p,b,c),_segment_squared(p,c,a))


class _Budget(Exception):pass


class _Tree:
    def __init__(self,values,stats):
        self.values=values;self.stats=stats
        def node(ids):
            lo=tuple(min(values[i][v][a] for i in ids for v in range(3)) for a in range(3))
            hi=tuple(max(values[i][v][a] for i in ids for v in range(3)) for a in range(3))
            if len(ids)<=8:return (lo,hi,ids,None)
            axis=max(range(3),key=lambda a:hi[a]-lo[a]);ids.sort(key=lambda i:sum(v[axis] for v in values[i]))
            middle=len(ids)//2;return (lo,hi,None,(node(ids[:middle]),node(ids[middle:])))
        self.root=node(list(range(len(values))))

    def distance_squared(self,p,index):
        if self.stats['triangleTests']>=self.stats['maximumTriangleTests']:raise _Budget()
        self.stats['triangleTests']+=1;return _triangle_squared(p,self.values[index])

    def nearest(self,p):
        def bound(node):return sum(max(node[0][a]-p[a],0,p[a]-node[1][a])**2 for a in range(3))
        serial=0;queue=[(bound(self.root),serial,self.root)];best=math.inf;identifier=None
        while queue:
            lower,_,node=heapq.heappop(queue)
            if lower>best:continue
            if node[2] is not None:
                for index in node[2]:
                    value=self.distance_squared(p,index)
                    if value<best:best=value;identifier=index
            else:
                for child in node[3]:serial+=1;heapq.heappush(queue,(bound(child),serial,child))
        return math.sqrt(best),identifier


def compare_surfaces(reference,actual,*,tolerance_m,max_samples=50000,max_triangle_tests=2000000):
    """Numerical Hausdorff bounds covering both full supplied triangle sets."""
    tolerance=number(tolerance_m,'tolerance_m',0)
    for name,value,maximum in [('max_samples',max_samples,1000000),('max_triangle_tests',max_triangle_tests,20000000)]:
        if type(value) is not int or not 1<=value<=maximum:raise ModelingError('measurement_budget',name+' is outside its explicit tool budget')
    reference,actual=triangles(reference),triangles(actual)
    if not reference or not actual:return {'status':'incomplete','reason':'Both required surfaces must be nonempty','coverage':'supplied triangle sets'}
    extent=max(1.,max(abs(x) for tri in reference+actual for p in tri for x in p))
    padding=extent*2e-12
    stats={'samples':0,'maximumSamples':max_samples,'triangleTests':0,'maximumTriangleTests':max_triangle_tests}

    def directed(source,target):
        tree=_Tree(target,stats);cache={};lower=0.;witness=None;queue=[];serial=0;initialized=0
        def point(p):
            nonlocal lower,witness
            if p not in cache:
                if stats['samples']>=max_samples:raise _Budget()
                stats['samples']+=1;cache[p]=tree.nearest(p)
                distance=cache[p][0]
                if distance>=lower:lower=distance;witness=p
            return cache[p]
        def cell(tri):
            a,b,c=tri;center=scale(add(add(a,b),c),1/3)
            samples=[point(p) for p in tri];middle=point(center)
            upper=middle[0]+max(math.dist(center,p) for p in tri)
            # Distance to one convex target triangle is convex. The maximum
            # vertex distance to that same triangle bounds the entire cell;
            # independent nearest vertices alone would not be a valid bound.
            for index in {s[1] for s in samples+[middle]}:
                upper=min(upper,math.sqrt(max(tree.distance_squared(p,index) for p in tri)))
            return upper+padding
        try:
            for tri in source:
                upper=cell(tri);heapq.heappush(queue,(-upper,serial,tri));serial+=1;initialized+=1
            while queue and -queue[0][0]>tolerance and max(0,lower-padding)<=tolerance:
                upper,_,tri=queue[0];a,b,c=tri;ab=scale(add(a,b),.5);bc=scale(add(b,c),.5);ca=scale(add(c,a),.5)
                children=[(a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)]
                # Do not remove the parent's valid bound if child evaluation
                # exhausts a budget half way through this refinement.
                refined=[(cell(child),child) for child in children]
                heapq.heappop(queue)
                for bound,child in refined:heapq.heappush(queue,(-bound,serial,child));serial+=1
        except _Budget:pass
        upper=-queue[0][0] if queue and initialized==len(source) else None
        return {'sampledMaximumMetres':lower,'lowerBoundMetres':max(0,lower-padding),'upperBoundMetres':upper,
                'worstSample':None if witness is None else list(witness),'initializedTriangleCount':initialized,'sourceTriangleCount':len(source)}
    forward=directed(reference,actual);reverse=directed(actual,reference)
    lower=max(forward['lowerBoundMetres'],reverse['lowerBoundMetres'])
    upper=None if any(r['upperBoundMetres'] is None for r in (forward,reverse)) else max(forward['upperBoundMetres'],reverse['upperBoundMetres'])
    return {'status':'failed' if lower>tolerance else 'passed' if upper is not None and upper<=tolerance else 'incomplete',
            'sampledMaximumMetres':max(forward['sampledMaximumMetres'],reverse['sampledMaximumMetres']),
            'lowerBoundMetres':lower,'upperBoundMetres':upper,'toleranceMetres':tolerance,'numericalPaddingMetres':padding,
            'referenceToActual':forward,'actualToReference':reverse,**stats,
            'coverage':'Both entire supplied piecewise triangular surfaces using convex-cell and 1-Lipschitz numerical bounds. No Boolean union, semantic correspondence, ideal curved surface, solid occupancy or collision certificate.'}
