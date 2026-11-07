"""Rigid point registration. Pure Python Horn/Jacobi solver, no hidden scale fit."""
from __future__ import annotations

import math
from .reference_storage import ReferenceError


def vector(value, length=3):
    if not isinstance(value, (list, tuple)) or len(value) != length or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ReferenceError("invalid_input", "Expected finite vector", length=length)
    return [float(v) for v in value]


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def norm(v):
    return math.sqrt(sum(x*x for x in v))


def rotation_matrix(q):
    x, y, z, w = vector(q, 4)
    size = norm(q)
    if size < 1e-15:
        raise ReferenceError("invalid_input", "Zero quaternion")
    x, y, z, w = [a/size for a in (x, y, z, w)]
    return [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]


def transform_point(transform, point):
    p = vector(point)
    matrix = transform.get("matrix")
    if matrix is None:
        rot = rotation_matrix(transform["rotationQuaternion"])
        t = vector(transform["translation"])
        return [sum(rot[i][j]*p[j] for j in range(3))+t[i] for i in range(3)]
    if len(matrix) != 4 or any(len(row) != 4 for row in matrix):
        raise ReferenceError("invalid_input", "Transform must be a 4x4 matrix")
    for row in matrix:
        vector(row, 4)
    return [sum(matrix[i][j]*p[j] for j in range(3))+matrix[i][3] for i in range(3)]


def identity_transform():
    return {"rotationQuaternion": [0., 0., 0., 1.], "translation": [0., 0., 0.], "matrix": [[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]}


def _eigen_symmetric(matrix):
    """Jacobi diagonalization avoids power iteration's magnitude/eigenvalue ambiguity."""
    a = [row[:] for row in matrix]
    n = len(a)
    eigenvectors = [[float(i == j) for j in range(n)] for i in range(n)]
    for _ in range(100):
        p, q = max(((i,j) for i in range(n) for j in range(i+1,n)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) < 1e-14 * max(1., max(abs(a[i][i]) for i in range(n))):
            break
        theta = .5 * math.atan2(2*a[p][q], a[q][q]-a[p][p])
        c, s = math.cos(theta), math.sin(theta)
        app, aqq, apq = a[p][p], a[q][q], a[p][q]
        for k in range(n):
            if k not in (p,q):
                akp, akq = a[k][p], a[k][q]
                a[k][p] = a[p][k] = c*akp-s*akq
                a[k][q] = a[q][k] = s*akp+c*akq
        a[p][p] = c*c*app-2*c*s*apq+s*s*aqq
        a[q][q] = s*s*app+2*c*s*apq+c*c*aqq
        a[p][q] = a[q][p] = 0.
        for k in range(n):
            vp, vq = eigenvectors[k][p], eigenvectors[k][q]
            eigenvectors[k][p], eigenvectors[k][q] = c*vp-s*vq, s*vp+c*vq
    return [a[i][i] for i in range(n)], eigenvectors


def _spread(points):
    origin = points[0]
    diffs = [[p[j]-origin[j] for j in range(3)] for p in points[1:]]
    longest = max(diffs, key=norm)
    scale = norm(longest)
    area = max((norm(cross(longest,d)) for d in diffs), default=0.)
    return scale > 1e-12 and area > 1e-10*scale*scale


def register_points(source, target, tolerance=None):
    source, target = [vector(v) for v in source], [vector(v) for v in target]
    if len(source) != len(target) or len(source) < 3:
        raise ReferenceError("underconstrained", "Rigid registration needs at least three paired anchors")
    if not _spread(source) or not _spread(target):
        raise ReferenceError("underconstrained", "Collinear or coincident anchors do not determine a rigid frame")
    cs = [sum(p[i] for p in source)/len(source) for i in range(3)]
    ct = [sum(p[i] for p in target)/len(target) for i in range(3)]
    s = [[sum((a[i]-cs[i])*(b[j]-ct[j]) for a,b in zip(source,target)) for j in range(3)] for i in range(3)]
    xx,xy,xz = s[0]; yx,yy,yz=s[1]; zx,zy,zz=s[2]
    n = [[xx+yy+zz,yz-zy,zx-xz,xy-yx],
         [yz-zy,xx-yy-zz,xy+yx,zx+xz],
         [zx-xz,xy+yx,-xx+yy-zz,yz+zy],
         [xy-yx,zx+xz,yz+zy,-xx-yy+zz]]
    eigenvalues, eigenvectors = _eigen_symmetric(n)
    index = max(range(4), key=lambda i:eigenvalues[i])
    w,x,y,z = [eigenvectors[j][index] for j in range(4)]
    q = [x,y,z,w]
    if q[3] < 0: q = [-v for v in q]
    r = rotation_matrix(q)
    t = [ct[i]-sum(r[i][j]*cs[j] for j in range(3)) for i in range(3)]
    transform = {"rotationQuaternion":q,"translation":t,"matrix":[r[i]+[t[i]] for i in range(3)]+[[0.,0.,0.,1.]]}
    residuals = [norm([x-y for x,y in zip(transform_point(transform,a),b)]) for a,b in zip(source,target)]
    maximum = max(residuals)
    return {**transform,"anchorCount":len(source),"rmsMetres":math.sqrt(sum(d*d for d in residuals)/len(residuals)),
            "maxMetres":maximum,"residualsMetres":residuals,"scaleEstimated":False,
            "status":"registered" if tolerance is None or maximum <= tolerance else "residual_exceeds_tolerance"}


def compose(after, before):
    """Return after(before(p)); preserves explicit transform chain for save recentering."""
    a,b=after["matrix"],before["matrix"]
    m=[[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
    return {"matrix":m,"translation":[m[i][3] for i in range(3)]}
