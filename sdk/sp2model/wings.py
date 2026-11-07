"""Native wing section lofts and host-relative edge-surface dimensions."""
from dataclasses import dataclass
from copy import deepcopy
import math
from .geometry import GeometryError,number,vector,magnitude,sub
from .errors import ModelingError

UNSET=object()


@dataclass(frozen=True)
class WingSection:
    span_position: float
    chord: float | None = None
    offset: float | None = None
    airfoil: str | None = None
    bend_deg: float = 0
    smooth_join: bool = False
    bend_radius_multiplier: float = 1

    def to_patch(self,unit_scale=1):
        patch={'spanPosition':number(number(self.span_position,'span_position')*unit_scale,'station metres',0,1000),
               'airfoil':self.airfoil,'bendDegrees':number(self.bend_deg,'bend_deg',-170,170),
               'bendRadiusMultiplier':number(self.bend_radius_multiplier,'bend_radius_multiplier',.01,100)}
        if type(self.smooth_join) is not bool:raise GeometryError('smooth_join must be boolean')
        patch['smoothJoin']=self.smooth_join
        if self.chord is not None:patch['chord']=number(number(self.chord,'chord')*unit_scale,'chord metres',.001,1000)
        if self.offset is not None:patch['offset']=number(number(self.offset,'offset')*unit_scale,'offset metres',-1000,1000)
        if self.airfoil is not None and (not isinstance(self.airfoil,str) or not self.airfoil.strip()):raise GeometryError('airfoil must be a native name or None for interpolation')
        return patch


@dataclass(frozen=True)
class ControlHandle:
    part: object
    host: object
    kind: str
    endpoint: str
    value: float
    identity: dict
    position_world: tuple | None
    position_status: str

    def to_dict(self):
        return {'partId':self.part.id,'hostPartId':self.host.id,'kind':self.kind,'endpoint':self.endpoint,
                'value':self.value,'unit':'native_span_metres' if self.kind=='span' else 'fraction_of_local_chord',
                'identity':deepcopy(self.identity),'positionWorld':self.position_world,'positionStatus':self.position_status,
                'nativeNeutralBaseline':True}


class WingPlanMixin:
    def wing_sections(self,name,sections,*,position=(0,0,0),rotation_quaternion=(0,0,0,1),flipped=False,wingtip=None,aerodynamics=None):
        sections=tuple(sections)
        if not 2<=len(sections)<=32 or any(not isinstance(s,WingSection) for s in sections):raise GeometryError('Use 2..32 WingSection objects')
        patches=[s.to_patch(self.unit_scale) for s in sections]
        if patches[0]['spanPosition']!=0 or any(b['spanPosition']-a['spanPosition']<.001 for a,b in zip(patches,patches[1:])):raise GeometryError('Wing stations start at zero and increase by at least .001 metre')
        if any('chord' not in s or 'offset' not in s for s in (patches[0],patches[-1])) or patches[0]['airfoil'] is None:
            raise GeometryError('Root and tip need chord and offset; root also needs an airfoil')
        if type(flipped) is not bool:raise GeometryError('flipped must be boolean')
        patch={'replaceSections':patches,'flipped':flipped,'wingtip':wingtip}
        if aerodynamics is not None:
            allowed={'liftScale','zeroLiftDragScale','viscousDragScale','physicsSamples','chordSamples','colliderSamples','disableWingtipVortices','fuelFraction'}
            if not isinstance(aerodynamics,dict) or set(aerodynamics)-allowed:raise GeometryError('Use discovered native aerodynamic fields; arbitrary attributes use native state')
            patch.update(deepcopy(aerodynamics))
        point,q=self._point(position),self.frame.orientation(rotation_quaternion)
        return self._create(name,self.session._resolve_template('Wing'),point,q,patch,
                            {'family':'wing','implementationStrategy':'one_native_multi_section_wing','nativePartCount':1,
                             'spanMetres':patches[-1]['spanPosition'],'position':list(point),'rotationQuaternion':list(q),'geometryStatus':'not_assessed'})

    def wing_planform(self,name,span,root_chord,tip_chord,*,sweep_deg=0,sweep_reference=.25,root_offset=0,
                      root_airfoil='NACA2412',tip_airfoil='NACA0012',position=(0,0,0),rotation_quaternion=(0,0,0,1),flipped=False):
        span=number(span,'span',.001/self.unit_scale,1000/self.unit_scale)
        reference=number(sweep_reference,'sweep_reference fraction LE=0 TE=1',0,1)
        angle=number(sweep_deg,'aft-positive sweep_deg',-85,85)
        root_chord=number(root_chord,'root_chord',.001/self.unit_scale,1000/self.unit_scale)
        tip_chord=number(tip_chord,'tip_chord',.001/self.unit_scale,1000/self.unit_scale)
        tip_offset=number(root_offset,'root_offset')-span*math.tan(math.radians(angle))+(.5-reference)*(root_chord-tip_chord)
        return self.wing_sections(name,[WingSection(0,root_chord,root_offset,root_airfoil),WingSection(span,tip_chord,tip_offset,tip_airfoil)],
                                  position=position,rotation_quaternion=rotation_quaternion,flipped=flipped)

    def wing_airfoils(self,part,*,root=UNSET,tip=UNSET,stations=None):
        state=self._shape_state(part)
        if state['family']!='wing':raise GeometryError('Native wing required')
        sections=state['configuration'].get('sections',state['configuration'].get('replaceSections',[]))
        updates={} if stations is None else dict(stations)
        if root is not UNSET:updates[0]=root
        if tip is not UNSET:updates[len(sections)-1]=tip
        if not updates:raise GeometryError('Specify root, tip or station airfoils')
        for i,value in updates.items():
            if type(i) is not int or not 0<=i<len(sections):raise GeometryError('Airfoil station index is outside the native wing')
            if (value is None and i==0) or (value is not None and (not isinstance(value,str) or not value.strip())):raise GeometryError('Root needs a native airfoil; other None values explicitly restore native interpolation')
        return self.shape(part,{'sections':[{'index':i,'airfoil':v} for i,v in sorted(updates.items())]})

    def _control_context(self,part):
        state=self._shape_state(part)
        if state.get('family')!='controlSurface':raise GeometryError('Native supported edge control surface required')
        host_id=state.get('wingPartId')
        if host_id is None:raise GeometryError('Control must be bound to its native wing before dimension editing')
        host=next((p for p in self.session.inspect().parts if p.id==host_id),None)
        if host is None:raise GeometryError('Control host disappeared')
        self._ref(host)  # Native host callbacks are part of the reviewed write set.
        return state,host

    def control_resize(self,part,*,span_m=None,span_fraction=None,chord_m=None,chord_fraction=None,span_anchor='inner',width_policy='fraction'):
        return self._control_edit(part,span_m=span_m,span_fraction=span_fraction,chord_m=chord_m,chord_fraction=chord_fraction,span_anchor=span_anchor,width_policy=width_policy)

    def control_shift(self,part,span_offset_m,*,width_policy='fraction'):
        return self._control_edit(part,span_offset_m=span_offset_m,width_policy=width_policy)

    def _control_edit(self,part,*,span_m=None,span_fraction=None,chord_m=None,chord_fraction=None,span_anchor='inner',width_policy='fraction',span_offset_m=None,target_range=None):
        if span_m is not None and span_fraction is not None:raise GeometryError('Choose span_m OR span_fraction')
        if chord_m is not None and chord_fraction is not None:raise GeometryError('Choose chord_m OR chord_fraction')
        if span_anchor not in ('inner','outer','center') or width_policy not in ('fraction','metres'):raise GeometryError('Choose a valid span_anchor and width_policy')
        state,host=self._control_context(part);config=state['configuration'];start,end=config['spanRange']
        stations=self.session.wing_stations(host,[start,end]);rows=stations['stations']
        native_scale=rows[0]['worldSpanVectorPerStation']
        if native_scale is None or rows[1]['worldSpanVectorPerStation'] is None:raise GeometryError('Native bend geometry is unresolved at this interval; use explicit station parameters and measure its mesh')
        factor=magnitude(native_scale)
        if factor<=0:raise GeometryError('Host has degenerate span scaling')
        new_start,new_end=start,end
        if span_m is not None or span_fraction is not None:
            length=number(span_m,'span_m',.001,1000)/factor if span_m is not None else number(span_fraction,'span_fraction',.000001,1)*stations['spanMetres']
            if span_anchor=='inner':new_end=start+length
            elif span_anchor=='outer':new_start=end-length
            else:new_start,new_end=(start+end-length)/2,(start+end+length)/2
        if span_offset_m is not None:
            delta=number(span_offset_m,'span_offset_m',-1000,1000)/factor;new_start+=delta;new_end+=delta
        if target_range is not None:new_start,new_end=vector(target_range,'target native span range',2)
        if new_start<0 or new_end>stations['spanMetres'] or new_end-new_start<.001:raise GeometryError('Requested control span is outside its host; automatic clipping is disabled')
        new_rows=self.session.wing_stations(host,[new_start,new_end])['stations']
        old_fractions=config.get('chordFraction',state.get('chordFraction'))
        if old_fractions is None:raise GeometryError('Native chord fractions unavailable')
        def pair(value,label):return (number(value,label),)*2 if isinstance(value,(int,float)) and not isinstance(value,bool) else vector(value,label,2)
        if chord_fraction is not None:fractions=pair(chord_fraction,'chord_fraction')
        elif chord_m is not None:fractions=tuple(w/row['effectiveChordMetres'] for w,row in zip(pair(chord_m,'chord_m'),new_rows))
        elif width_policy=='metres':fractions=tuple(f*old['effectiveChordMetres']/new['effectiveChordMetres'] for f,old,new in zip(old_fractions,rows,new_rows))
        else:fractions=old_fractions
        maximum=.4 if state.get('style')=='Slat' else .8
        fractions=[number(f,'native chord fraction',.05,maximum) for f in fractions]
        patch={'spanRange':[new_start,new_end],'chordFraction':fractions}
        self.shape(part,patch)
        self._shapes[self._ref(part)]['configuration']['chordFraction']=fractions
        return self

    def control_handle(self,handle,value):
        if not isinstance(handle,ControlHandle):raise GeometryError('Use a currently discovered ControlHandle')
        self._ref(handle.part);self._ref(handle.host)
        if handle.identity!=self.baseline_identity:raise ModelingError('stale_reference','Control handle belongs to another native state')
        state=self._shape_state(handle.part);index=0 if handle.endpoint=='inner' else 1
        if handle.kind=='span':
            span=list(state['configuration']['spanRange']);span[index]=number(value,'native span metres',0,1000)
            return self._control_edit(handle.part,target_range=span)
        fractions=list(state['configuration'].get('chordFraction',state['chordFraction']));fractions[index]=number(value,'chord fraction',.05,.4 if state.get('style')=='Slat' else .8)
        return self._control_edit(handle.part,chord_fraction=fractions)
