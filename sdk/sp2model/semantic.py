"""Explicit spherical targets compiled to a small adaptive native loft group.

The analytical estimate covers the ideal quadratic meridian and circular
cross-section polygon only. Native longitudinal tessellation, clipping,
connections and render meshes must subsequently be measured.
"""
from copy import deepcopy
import math
from .geometry import (Section, GeometryError, CORNERS, add, sub, scale,
                       unit, vector, dot, rotate, multiply, magnitude, number)


def radius_value(radius, diameter, unit_scale):
    if (radius is None)==(diameter is None):
        raise GeometryError('Provide exactly one of radius or diameter')
    value=number(radius,'radius',0) if radius is not None else number(diameter,'diameter',0)/2
    return number(value*unit_scale,'radius metres',.001,250)


def spherical_profile(radius, low, high, tolerance, max_parts):
    """Return (kind,z0,z1,r0,controlRadius,r1) in metres about circle centre."""
    if type(max_parts) is not int or not 1<=max_parts<=20:
        raise GeometryError('max_parts must be 1..20; native plans remain bounded at 100 operations')
    meridian_budget=tolerance/3
    left,right=0.,math.pi/2
    for _ in range(60):
        angle=(left+right)/2
        if radius*((math.cos(angle/2)+1/math.cos(angle/2))/2-1)<=meridian_budget:left=angle
        else:right=angle
    angle=left
    cap_z=radius*math.cos(angle)
    bands=[]
    def r(z):return math.sqrt(max(0,radius*radius-z*z))
    def middle(a,b):
        zmax=max(abs(a),abs(b))
        derivative=3*radius*radius*zmax/(radius*radius-zmax*zmax)**2.5
        bound=derivative*(b-a)**3/(72*math.sqrt(3))
        if bound>meridian_budget:
            if len(bands)>=max_parts:raise GeometryError('Requested tolerance exceeds the explicit native part budget')
            mid=(a+b)/2;middle(a,mid);middle(mid,b);return
        control=2*r((a+b)/2)-(r(a)+r(b))/2
        bands.append(('curved',a,b,r(a),control,r(b)))
    if low<=-radius+1e-12:
        end=min(high,-cap_z);theta=math.acos(-end/radius)
        bands.append(('cap',end,-radius,r(end),radius*math.tan(theta/2),0))
        low=end
    middle_high=min(high,cap_z) if high>=radius-1e-12 else high
    if middle_high-low>=1e-12:middle(low,middle_high)
    if high>=radius-1e-12:
        start=max(low,cap_z);theta=math.acos(start/radius)
        bands.append(('cap',start,radius,r(start),radius*math.tan(theta/2),0))
    if not bands or len(bands)>max_parts:
        raise GeometryError('Requested tolerance exceeds the explicit native part budget')
    # A circle made by four rounded corners has 4*(samples-1) segments.
    radial_budget=tolerance/3
    samples=4
    while (radius+meridian_budget)*(1-math.cos(math.pi/(4*(samples-1))))>radial_budget:
        samples+=1
        if samples>32:raise GeometryError('Requested tolerance exceeds the certified corner sampling limit (32 per corner)')
    for _,a,b,*_ in bands:
        if abs(a-b)<.001:raise GeometryError('A spherical loft segment would be shorter than the native 0.001 metre limit')
    return bands,samples,{'idealMeridianUpperBoundMetres':meridian_budget,
                          'idealCrossSectionSagittaMetres':(radius+meridian_budget)*(1-math.cos(math.pi/(4*(samples-1)))),
                          'nativeMeshStatus':'not_assessed',
                          'coverage':'Ideal curves and circular cross-section polygon only; longitudinal tessellation and final native exterior require measurement.'}


class SphericalPlanMixin:
    def sphere(self,name,*,radius=None,diameter=None,center=(0,0,0),axis=(0,1,0),
               tolerance_m=.006,max_parts=12,allow_approximation=False):
        r=radius_value(radius,diameter,self.unit_scale)
        return self._spherical(name,'sphere',r,2*r,center,axis,tolerance_m,max_parts,allow_approximation)

    def dome(self,name,*,radius=None,diameter=None,depth,base_center=(0,0,0),axis=(0,1,0),
             tolerance_m=.006,max_parts=12,allow_approximation=False):
        r=radius_value(radius,diameter,self.unit_scale)
        d=number(number(depth,'depth')*self.unit_scale,'depth metres',.001,500)
        return self._spherical(name,'dome',r,d,base_center,axis,tolerance_m,max_parts,allow_approximation)

    def _spherical(self,name,kind,base_radius,depth,center,axis,tolerance,max_parts,accepted):
        if accepted is not True:
            raise GeometryError('Native spherical lofts are approximations; explicitly set allow_approximation=True and measure the native result')
        self._name(name);self._current()
        tolerance=number(tolerance,'tolerance_m',1e-6,1)
        if tolerance>=min(base_radius,depth)/2:raise GeometryError('Tolerance must be less than half the target radius and depth')
        circle_r=base_radius if kind=='sphere' else (base_radius*base_radius+depth*depth)/(2*depth)
        if circle_r>500:raise GeometryError('Spherical cap curvature exceeds the supported 500 metre radius')
        center_world=self._point(center);direction=unit(self.frame.direction(axis),'spherical axis')
        low=-circle_r if kind=='sphere' else circle_r-depth
        curve_center=center_world if kind=='sphere' else add(center_world,scale(direction,depth-circle_r))
        bands,samples,estimate=spherical_profile(circle_r,low,circle_r,tolerance,max_parts)
        # body consumes four operations, a cap one extra; connections consume
        # one operation with native_resize (autoResize is explicitly false).
        required=sum(5 if band[0]=='cap' else 4 for band in bands)+3*(len(bands)-1)
        if len(self.operations)+required>100:raise GeometryError('Spherical representation exceeds remaining native operation budget')
        q=self.frame.rotation_quaternion;inverse=(-q[0],-q[1],-q[2],q[3])
        def local(point):return scale(rotate(inverse,sub(point,self.frame.position)),1/self.unit_scale)
        up=(0,1,0) if abs(dot(unit(vector(axis)),(0,1,0)))<.9 else (1,0,0)
        def section(r):return Section(2*r/self.unit_scale,2*r/self.unit_scale,corner_radius=1,corner_stretch=True)
        with self._atomic_edit():
            pieces=[]
            for i,(style,a,b,r0,control,r1) in enumerate(bands):
                start,end=(local(add(curve_center,scale(direction,z))) for z in (a,b))
                if style=='cap':
                    part=self.cone(f'{name}/loft-{i}',start,end,[section(r0),section(0)],up=up)
                    patch={'noseconeRoundness':1,'sections':[section(control).to_patch(1,unit_scale=self.unit_scale,role='curve_control')]}
                    patch['sections'][0]['cornerSamples']=dict.fromkeys(CORNERS,samples)
                    self.shape(part,patch)
                else:
                    part=self.curved(f'{name}/loft-{i}',start,end,[section(r0),section(control),section(r1)],up=up)
                # Add sampling to the original create patch without an extra
                # native rebuild. All changes are still a side-effect-free plan.
                create=next(op for op in self.operations if op['kind']=='shape.update' and op['partId']==part.temporary_id)
                for item in create['patch']['sections']:item['cornerSamples']=dict.fromkeys(CORNERS,samples)
                for item in self._shapes[part.temporary_id]['configuration']['sections']:item['cornerSamples']=dict.fromkeys(CORNERS,samples)
                part.expected.update(semantic=kind,geometryStatus='not_assessed')
                pieces.append(part)
            # Select current compatible native endpoints; curve slice indices
            # are not attachment IDs (Curved's control has no endpoint).
            for i in range(1,len(pieces)):
                self.connect(pieces[i-1],pieces[i],shape_policy='preserve')
            group=self.group(name,pieces)
            self.semantic_shapes[name]={'kind':kind,'radiusMetres':base_radius,'depthMetres':depth,
                'centerWorld':list(center_world),'axisWorld':list(direction),'toleranceMetres':tolerance,
                'maxParts':max_parts,'actualParts':len(pieces),'cornerSamples':samples,'approximationAccepted':True,
                'strategy':'adaptive_native_quadratic_lofts_and_rounded_polar_caps',
                'estimate':estimate,'parts':[p.temporary_id for p in pieces],
                'poses':{p.temporary_id:deepcopy(self._poses[p.temporary_id]) for p in pieces},
                'configurations':{p.temporary_id:deepcopy(self._shapes[p.temporary_id]['configuration']) for p in pieces}}
            return group

    def reshape_semantic(self,name,*,radius=None,diameter=None,depth=None,tolerance_m=None,allow_approximation=False):
        """Change a bound sphere/dome in place, preserving other native state.

        A change requiring a different loft partition is rejected before writes;
        callers must explicitly review a new candidate and connection migration.
        """
        definition,parts=self.session.semantic(name)
        for part in parts:self._ref(part)
        if definition['kind']=='sphere' and depth is not None:raise GeometryError('Sphere depth is determined by its diameter')
        poses=definition['poses'];first=parts[0];old=poses[str(first.id)]
        current_position,current_q=self._known_pose(first);old_q=old['rotationQuaternion']
        delta_q=multiply(current_q,(-old_q[0],-old_q[1],-old_q[2],old_q[3]))
        def moved(p):return add(current_position,rotate(delta_q,sub(p,old['position'])))
        for part in parts:
            pos,q=self._known_pose(part);stored=poses[str(part.id)]
            from .geometry import rotation_distance_degrees
            if magnitude(sub(pos,moved(stored['position'])))>.0001 or rotation_distance_degrees(q,multiply(delta_q,stored['rotationQuaternion']))>.001:
                raise GeometryError('Semantic group changed nonrigidly; review its representation before reusing parameters')
            actual=self._shape_state(part)['configuration'];expected=definition['configurations'][str(part.id)]
            # Native readers add derived fields; compare only authored fields.
            def subset(a,e):
                if isinstance(e,dict):return isinstance(a,dict) and all(k in a and subset(a[k],v) for k,v in e.items())
                if isinstance(e,list):return isinstance(a,list) and len(a)==len(e) and all(subset(x,y) for x,y in zip(a,e))
                if isinstance(e,(int,float)) and not isinstance(e,bool):return isinstance(a,(int,float)) and abs(a-e)<1e-5
                return a==e
            if not subset(actual,expected):raise GeometryError('Native shape changed independently; review before semantic reshaping')
        r=definition['radiusMetres'] if radius is None and diameter is None else radius_value(radius,diameter,self.unit_scale)
        d=(2*r if definition['kind']=='sphere' else definition['depthMetres']) if depth is None else number(depth,'depth')*self.unit_scale
        center=moved(definition['centerWorld']);axis=rotate(delta_q,definition['axisWorld'])
        from .geometry import Frame
        candidate=type(self)(self.session,frame=Frame.world(),writable=[])
        candidate._spherical(name,definition['kind'],r,d,center,axis,definition['toleranceMetres'] if tolerance_m is None else tolerance_m,definition['maxParts'],allow_approximation)
        fresh=candidate.semantic_shapes[name]
        if fresh['actualParts']!=len(parts):raise GeometryError('New target requires a different loft partition; create a reviewed replacement candidate instead')
        with self._atomic_edit():
            pose_map={};config_map={}
            for part,new in zip(parts,candidate.groups[name].parts):
                config=candidate._shapes[new.temporary_id]['configuration'];pose=candidate._poses[new.temporary_id]
                self.shape(part,config)
                self._append({'kind':'transform.apply','partIds':[self._ref(part)],'mode':'absolute','frame':{'kind':'world'},
                              'position':pose['position'],'rotationQuaternion':pose['rotationQuaternion'],'symmetric':False})
                self._poses[part.id]=deepcopy(pose);pose_map[str(part.id)]=deepcopy(pose);config_map[str(part.id)]=deepcopy(config)
            fresh.update(parts=[p.id for p in parts],poses=pose_map,configurations=config_map)
            self.semantic_shapes[name]=fresh
        return self
