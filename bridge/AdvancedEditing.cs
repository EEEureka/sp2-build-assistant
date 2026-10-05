using System;
using System.Collections.Generic;
using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Parts.Fuselage;
using Assets.Scripts.Craft.Wings;
using Assets.Scripts.Craft.Wings.Airfoils;
using Assets.Scripts.Craft.Wings.ControlSurfaces;
using Assets.Scripts.Design.Symmetry;
using Newtonsoft.Json.Linq;
using Unity.Mathematics;
using UnityEngine;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private readonly HashSet<int> wingsToValidate=new HashSet<int>();
        private static void ValidateOperationFields(JObject op)
        {
            var fields=new Dictionary<string,string>{
                ["properties.set"]="partId patch symmetric",
                ["appearance.set"]="mode materialId partIds slots patch",
                ["transform.apply"]="partIds groupId frame mode translation position rotationQuaternion pivot anchorPartId symmetric",
                ["transform.align"]="partIds groupId sourcePartId sourcePointId targetPartId targetPointId offset axis symmetric",
                ["decal.pose.set"]="partId frame position rotationQuaternion symmetric",
                ["part.add"]="templateId temporaryId position rotation",["part.update"]="partId changes symmetric",["part.delete"]="partId symmetric assembly",
                ["connection.connect"]="partA partB attachPointA attachPointB symmetric",["connection.disconnect"]="partA partB symmetric",
                ["variable.add"]="variable function priority activator",["variable.update"]="index variable function priority activator",["variable.delete"]="index",["variable.reorder"]="order",
                ["output.bind"]="partId modifier outputId variable priority activator",["output.update"]="partId modifier outputId variable priority activator",["output.unbind"]="partId modifier outputId",
                ["craft.refresh"]="",["shape.update"]="partId patch symmetric",["wing.control.add"]="wingPartId style patch temporaryId",["fuselage.match"]="partId sectionIndex",
                ["symmetry.link"]="partIds",["symmetry.unlink"]="partId",["symmetry.create"]="partId",["symmetry.enable"]="partId enabled"
            };
            ShapeCodec.Keys(op,fields[(string)op["kind"]].Split(' ').Concat(new[]{"kind"}));
            if(op["symmetric"]!=null && op["symmetric"].Type!=JTokenType.Boolean)throw new ApiError("invalid_input","symmetric must be a JSON boolean.");
            if(op["assembly"]!=null && op["assembly"].Type!=JTokenType.Boolean)throw new ApiError("invalid_input","assembly must be a JSON boolean.");
        }
        private static bool IsAdvancedRead(string cmd)
        { return new[]{"designer.selection","parts.geometry","designer.raycast","shape.get","shape.schema","symmetry.get"}.Contains(cmd); }
        private static bool IsAdvancedWrite(string kind)
        { return kind=="craft.refresh" || kind=="shape.update" || kind=="wing.control.add" || kind=="fuselage.match" || kind.StartsWith("symmetry."); }
        private object AdvancedRead(string cmd,JObject a)
        {
            var d=Current();
            if(cmd=="designer.selection") {
                var p=d.SelectedPart?.Part;
                if(p!=null && d.SelectedPart.Aircraft!=d.Aircraft)
                    throw new ApiError("selection_not_in_current_aircraft","The selected scene object belongs to a stale or different aircraft instance. Do not use its numeric ID to edit the current craft; inspect designer.status.sceneIntegrity.");
                return new { identity=Identity(), selectedPartId=p==null?(int?)null:p.Id, part=p==null?null:PartInfo(p,true), shape=p==null?null:ShapeInfo(p),
                    meaning="The primary part actually selected by the player; null means no part selected." };
            }
            if(cmd=="designer.raycast") return Raycast(a);
            if(cmd=="shape.schema") return new { identity=Identity(), schema=ShapeCodec.Schema(Required(a,"family")) };
            if(cmd=="symmetry.get") return new { identity=Identity(), configuration=SymmetryConfiguration(), groups=new JArray(d.Aircraft.Aircraft.Assembly.Parts
                .Where(p=>p.SymmetryId!=0).GroupBy(p=>p.SymmetryId).Where(g=>a["part"]==null || g.Any(p=>p.Id==Int(a,"part")))
                .Select(g=>new JObject{["id"]=g.Key,["parts"]=new JArray(g.Select(p=>new JObject{["id"]=p.Id,["enabled"]=!p.SymmetryDisabled,["type"]=p.PartType.PartTypeId}))})),
                part=a["part"]==null?null:PartInfo(Part(Int(a,"part")),false), propagation="shape.update follows enabled native groups by default; symmetric:false opts out. Raw parts.update requires explicit symmetric:true." };
            var part=Part(Int(a,"id"));
            if(cmd=="parts.geometry") return new { identity=Identity(), geometry=GeometryInfo(part) };
            return new { identity=Identity(), partId=part.Id, shape=ShapeInfo(part) };
        }
        private static JObject ShapeInfo(PartData part)
        {
            var info=ShapeCodec.Read(part.GenerateXml());
            info["inputControllers"]=InputControllers(part,"live_part_modifier");
            if((string)info["family"]=="unmapped") {
                info["effectivePropertyCommand"]="properties.get";
                info["stateByModifier"]=Node(part.GenerateXml());
                info["nativePropertySchema"]=new JArray(part.GetOverloadMetadataLookup().Select(pair=>new JObject{["element"]=pair.Key,
                    ["attributes"]=JArray.FromObject(pair.Value.Attributes.Select(m=>new{name=m.Name,type=m.DataType.ToString(),label=m.Label,description=m.Tooltip,min=m.MinValue,max=m.MaxValue,enumValues=m.EnumValues,optional=m.IsOptional,readOnly=m.IsReadOnly}))}));
            }
            var wing=part.GetModifier<JWingData>();
            if(wing!=null) {
                info["spanMetres"]=wing.WingSpan;
                info["controlSurfaces"]=new JArray(wing.ControlSurfacesInformational.Select(c=>new JObject{["partId"]=c.Part.Id,["shape"]=ShapeCodec.Read(c.Part.GenerateXml())}));
            }
            var control=part.GetModifier<ControlSurfacePartData>();
            if(control!=null) {
                var attached=control.GetFirstConnectedWing();info["wingPartId"]=attached==null?(JToken)null:attached.Part.Id;
                if(control.ControlSurface is EdgeSurfaceBase edge && attached!=null) {
                    var slices=attached.WingSlices.Select(s=>s.Clone()).ToList();WingBuilder.InterpolateAllOffsetScale(slices);
                    var range=edge.Range; var start=edge.StartPos;
                    info["chordFraction"]=new JArray(ChordFraction(slices,range.x,start.x,edge.IsLeadingEdge),ChordFraction(slices,range.y,start.y,edge.IsLeadingEdge));
                }
                info["typedEditingSupported"]=control.ControlSurface is EdgeSurfaceBase;
            }
            var fuselage=part.GetModifier<JFuselageData>();
            if(fuselage!=null) {
                var sections=(JArray)info["configuration"]["sections"];
                for(int i=0;i<sections.Count;i++) {
                    bool has=fuselage.TryGetNeighbour(i,out JFuselageData neighbour,out int index);
                    sections[i]["adjacent"]=has?new JObject{["partId"]=neighbour.Part.Id,["sectionIndex"]=index}:null;
                    sections[i]["role"]=i==0?"back":i==sections.Count-1?"front":"intermediate";
                    var shape=fuselage[i];var max=FuselageJob.GetMaxCornerRadii(in shape);
                    sections[i]["cornerRadiusNativeMax"]=new JObject(ShapeCodec.Corners.Select((name,j)=>new JProperty(name,float.IsNaN(max[j]) || float.IsInfinity(max[j])?(JToken)null:max[j])));
                    sections[i]["cornerRadiusUnits"]="metres when cornerStretch=false; dimensionless stretched radius when true (tool range 0..1)";
                }
            }
            return info;
        }
        private SymmetryConfig EffectiveSymmetryConfig()
        {
            var d=Current(); var s=d.Symmetry.Clone(); var origin=d.Aircraft.MainCockpit.transform;
            // Save/AutoRecenter can translate the aircraft without refreshing the
            // native cache. Derive on a clone so read-only queries stay read-only.
            // This is the same basis as Designer.UpdateSymmetryConfig.
            s.UpdateConfig(origin.position,Vector3.right,d.Aircraft.Aircraft.MirrorPlaneOffset,origin.forward);
            return s;
        }
        private static JObject SymmetryFrame(SymmetryConfig s)
        {
            return new JObject { ["mirrorPlaneNormal"]=new JArray(Vec(s.MirrorPlane.Normal)), ["mirrorPlaneDistance"]=s.MirrorPlane.Distance,
                ["radialAxis"]=new JArray(Vec(s.RadialAxis.Axis)), ["radialOrigin"]=new JArray(Vec(s.RadialAxis.Point)) };
        }
        private object SymmetryConfiguration()
        {
            var d=Current();var s=EffectiveSymmetryConfig();var cached=d.Symmetry;var result=SymmetryFrame(s);
            bool stale=math.lengthsq(s.MirrorPlane.Normal-cached.MirrorPlane.Normal)>1e-10f || math.abs(s.MirrorPlane.Distance-cached.MirrorPlane.Distance)>1e-5f
                || math.lengthsq(s.RadialAxis.Axis-cached.RadialAxis.Axis)>1e-10f || math.lengthsq(s.RadialAxis.Point-cached.RadialAxis.Point)>1e-10f;
            result["mode"]=s.Mode.ToString();result["disabledForNewParts"]=s.SymmetryDisabledForNewParts;
            result["basis"]="current_main_control_pose_and_aircraft_mirror_offset";
            result["originPartId"]=d.Aircraft.MainCockpit.Part.Id;
            result["aircraftMirrorPlaneOffset"]=d.Aircraft.Aircraft.MirrorPlaneOffset;
            result["planeEquation"]="dot(mirrorPlaneNormal, worldPosition) + mirrorPlaneDistance = 0";
            result["nativeCacheStale"]=stale;result["nativeCachedFrame"]=SymmetryFrame(cached);
            result["meaning"]="Effective frame derived without modifying the aircraft or native cache. Guarded mutations refresh the native cache before each operation. Cached-frame mismatch tolerance is 0.00001 metres/direction units.";
            return result;
        }
        private List<PartData> SymmetricTargets(PartData source,bool enabled)
        {
            if(!enabled || source.SymmetryId==0 || source.SymmetryDisabled)return new List<PartData>();
            var peers=Current().Aircraft.Aircraft.Assembly.Parts.Where(p=>p!=source && p.SymmetryId==source.SymmetryId && !p.SymmetryDisabled).ToList();
            ValidateSymmetryGeometry(source,peers);
            return peers;
        }
        private void ValidateSymmetryGeometry(PartData source,List<PartData> peers)
        {
            var transforms=new List<SymmetryTransform>();var config=EffectiveSymmetryConfig();
            if(config.Mode==SymmetryMode.Disabled)config=config.Clone(SymmetryMode.Mirrored);
            SymmetryUtility.GetSymmetricTransforms(source,config,transforms);
            foreach(var peer in peers) {
                if(peer.PartType.PartTypeId!=source.PartType.PartTypeId)throw new ApiError("symmetry_type_mismatch","Symmetric parts must have identical part types.");
                int index=transforms.FindIndex(t=>Vector3.Distance(t.Position,peer.PartScript.transform.position)<.01f && Quaternion.Angle(t.Rotation,peer.PartScript.transform.rotation)<.1f);
                if(index<0)throw new ApiError("symmetry_geometry_mismatch","Part "+peer.Id+" does not match the designer's current symmetry plane/axis. Inspect symmetry.get, correct the group or use symmetric:false.");
                transforms.RemoveAt(index);
            }
        }
        private bool MirrorMode => Current().Symmetry.Mode==SymmetryMode.Mirrored || Current().Symmetry.Mode==SymmetryMode.Disabled;
        private JObject AdvancedWrite(JObject op,BatchReferences refs)
        {
            string kind=Required(op,"kind");var d=Current();var assembly=d.Aircraft.Aircraft.Assembly;
            if(kind=="craft.refresh") {Replace(d.Aircraft.Aircraft.GenerateXml(false));return new JObject{["kind"]=kind,["editMode"]="current_craft_rebuild"};}
            if(kind=="wing.control.add")return AddWingControl(op,refs);
            if(kind=="symmetry.link") {
                var ids=op["partIds"] as JArray;if(ids==null || ids.Count<2 || ids.Count>4)throw new ApiError("invalid_symmetry","partIds requires 2..4 distinct current parts.");
                var parts=ids.Select(x=>Part(Resolve(x,refs))).ToList();
                if(parts.Distinct().Count()!=parts.Count || parts.Any(p=>p.SymmetryId!=0))throw new ApiError("invalid_symmetry","Parts must be distinct and unlinked. Unlink existing groups explicitly first.");
                ValidateSymmetryGeometry(parts[0],parts.Skip(1).ToList());assembly.LinkSymmetricParts(parts,true);
                if(parts.Any(p=>p.SymmetryId==0 || p.SymmetryId!=parts[0].SymmetryId))throw new ApiError("symmetry_rejected","Native link did not take effect.");
                return new JObject{["kind"]=kind,["groupId"]=parts[0].SymmetryId,["partIds"]=new JArray(parts.Select(p=>p.Id))};
            }
            var part=Part(Resolve(op["partId"],refs));
            if(kind=="symmetry.unlink") {if(part.SymmetryId==0)throw new ApiError("symmetry_not_found","Part has no symmetry group.");uint group=part.SymmetryId;assembly.UnlinkSymmetricParts(group,false);return new JObject{["kind"]=kind,["groupId"]=group};}
            if(kind=="symmetry.enable") {
                if(op["enabled"]?.Type!=JTokenType.Boolean)throw new ApiError("invalid_symmetry","enabled must be boolean.");
                var group=part.SymmetryId==0?new List<PartData>{part}:assembly.Parts.Where(p=>p.SymmetryId==part.SymmetryId).ToList();
                foreach(var p in group)p.SymmetryDisabled=!(bool)op["enabled"];
                return new JObject{["kind"]=kind,["partIds"]=new JArray(group.Select(p=>p.Id)),["enabled"]=op["enabled"]};
            }
            if(kind=="symmetry.create") {
                if(part.SymmetryId!=0)throw new ApiError("invalid_symmetry","Source already belongs to a group.");
                var config=EffectiveSymmetryConfig();
                if(config.Mode==SymmetryMode.Disabled)throw new ApiError("symmetry_disabled","Choose mirror/radial mode in the designer before creating a group.");
                part.SymmetryDisabled=false;var created=new List<PartData>();SymmetryUtility.CreateSymmetricParts(part,false,config,created);
                if(created.Count==0 || part.SymmetryId==0)throw new ApiError("symmetry_rejected","Native symmetry creation produced no linked peers (possibly overlapping positions).");
                return new JObject{["kind"]=kind,["sourcePartId"]=part.Id,["groupId"]=part.SymmetryId,["createdPartIds"]=new JArray(created.Select(p=>p.Id))};
            }
            if(kind=="fuselage.match")return MatchFuselage(part,op);
            var peers=SymmetricTargets(part,op.Value<bool?>("symmetric")!=false);
            var xml=d.Aircraft.Aircraft.GenerateXml(false);var node=XmlPart(xml,part.Id);var patch=op["patch"] as JObject;
            ShapeCodec.Patch(node,patch,AirfoilValid);
            if(part.GetModifier<ControlSurfacePartData>()!=null)ValidateControlPatch(part,node,patch);
            foreach(var peer in peers) {
                var target=XmlPart(xml,peer.Id);var state=ShapeCodec.State(target);if(MirrorMode)ShapeCodec.Mirror(state);
                ShapeCodec.Patch(target,patch,AirfoilValid);
                if(peer.GetModifier<ControlSurfacePartData>()!=null)ValidateControlPatch(peer,target,patch);
                if(MirrorMode)ShapeCodec.Mirror(state);
            }
            var affected=new HashSet<int>(peers.Select(p=>p.Id)){part.Id};
            if(part.GetModifier<JFuselageData>()!=null && patch["sections"] is JArray)
                foreach(var source in new[]{part}.Concat(peers)) PropagateAdjacentSections(xml,source,patch,source!=part && MirrorMode,affected);
            foreach(var p in new[]{part}.Concat(peers)) {
                var w=p.GetModifier<JWingData>()??p.GetModifier<ControlSurfacePartData>()?.GetFirstConnectedWing();
                if(w!=null)wingsToValidate.Add(w.Part.Id);
            }
            Replace(xml);
            return new JObject{["kind"]=kind,["partId"]=part.Id,["synchronizedPartIds"]=new JArray(peers.Select(p=>p.Id)),["affectedPartIds"]=new JArray(affected.OrderBy(x=>x)),["editMode"]="current_craft_rebuild"};
        }
        private void PropagateAdjacentSections(XElement xml,PartData source,JObject patch,bool sourceMirrored,HashSet<int> affected)
        {
            var f=source.GetModifier<JFuselageData>();var state=ShapeCodec.State(XmlPart(xml,source.Id));
            foreach(JObject update in (JArray)patch["sections"]) {
                int index=(int)update["index"];var section=state.Elements("Slice").ElementAt(index);
                if((bool?)section.Attribute("syncSlices")==false || !f.TryGetNeighbour(index,out JFuselageData neighbour,out int neighbourIndex))continue;
                var target=XmlPart(xml,neighbour.Part.Id);var targetState=ShapeCodec.State(target);
                if((bool?)targetState.Elements("Slice").ElementAt(neighbourIndex).Attribute("syncSlices")==false)continue;
                bool mirror=sourceMirrored ^ (f.SliceIsFront(index)==neighbour.SliceIsFront(neighbourIndex));
                var adjacentPatch=(JObject)update.DeepClone();adjacentPatch["index"]=neighbourIndex;
                if(mirror)ShapeCodec.Mirror(targetState);
                ShapeCodec.Patch(target,new JObject{["sections"]=new JArray(adjacentPatch)},AirfoilValid);
                if(mirror)ShapeCodec.Mirror(targetState);
                affected.Add(neighbour.Part.Id);
            }
        }
        private void ValidateEditedWings()
        {
            foreach(int id in wingsToValidate) {
                var p=Current().Aircraft.Aircraft.Assembly.Parts.FirstOrDefault(x=>x.Id==id);var wing=p?.GetModifier<JWingData>();if(wing==null)continue;
                foreach(var control in wing.ControlSurfacesInformational)
                    if(control.ControlSurface is EdgeSurfaceBase) ValidateControlPatch(control.Part,control.Part.GenerateXml(),new JObject());
            }
        }
        private static XElement XmlPart(XElement xml,int id)
        {return xml.Element("Assembly").Element("Parts").Elements("Part").Single(p=>(int)p.Attribute("id")==id);}
        private JObject AddWingControl(JObject op,BatchReferences refs)
        {
            var wing=Part(Resolve(op["wingPartId"],refs));if(wing.GetModifier<JWingData>()==null)throw new ApiError("shape_not_supported","wingPartId must be a JWing.");
            var styles=new Dictionary<string,string>{{"StandardFlap","ControlSurface-Flap-1"},{"FowlerFlap","ControlSurface-Flap-2"},{"BrakeFlap","ControlSurface-Flap-3"},{"Slat","ControlSurface-Slat-1"}};
            if(!styles.TryGetValue(Required(op,"style"),out string type))throw new ApiError("invalid_control_surface","style must be StandardFlap, FowlerFlap, BrakeFlap or Slat.");
            var template=Templates().FirstOrDefault(t=>t.Value.Mod==null && !t.Value.IsSubassembly && Creatable(t.Value) && t.Value.AssemblyElement.Descendants("Part").Count()==1 && (string)t.Value.AssemblyElement.Descendants("Part").Single().Attribute("partType")==type);
            if(template.Value==null)throw new ApiError("template_not_found","No creatable native control surface template for "+type);
            string temporary=(string)op["temporaryId"]??("control-"+Guid.NewGuid().ToString("N"));
            var added=Apply(new JObject{["kind"]="part.add",["templateId"]=template.Key,["temporaryId"]=temporary,["position"]=new JArray(Vec(wing.PartScript.transform.position)),["rotation"]=new JArray(Vec(wing.PartScript.transform.eulerAngles))},refs);
            var control=Part(refs[temporary]);
            // Connecting invokes JWingScript.FindControlSurfaces synchronously. Prepare
            // valid dimensions before that callback sees the template's dummy span.
            var prepared=control.GenerateXml();var patch=op["patch"] as JObject;
            ShapeCodec.Patch(prepared,patch,AirfoilValid);
            ValidateControlPatch(control,prepared,patch,wing.GetModifier<JWingData>());
            control.GetModifier<ControlSurfacePartData>().RestoreFromState(ShapeCodec.State(prepared));
            // The native wing tool attaches controls to the wing surface receiver,
            // not the structural root. First-compatible selection used to consume
            // a free root and prevented attaching the wing to its host later.
            var pair=(from ap in control.AttachPoints from bp in wing.AttachPoints where bp.IsSurfaceAttachPoint && ap.AllowManualConnection && bp.AllowManualConnection && (ap.IsAvailable || ap.AllowMultipleManualConnections) && (bp.IsAvailable || bp.AllowMultipleManualConnections) && bp.CanReceive(ap) select new{ap,bp}).FirstOrDefault();
            if(pair==null)throw new ApiError("invalid_connection","No compatible available wing surface receive point for this control. Structural root attach points are reserved for attaching the wing to its host.");
            Apply(new JObject{["kind"]="connection.connect",["partA"]=temporary,["partB"]=op["wingPartId"].DeepClone(),["attachPointA"]=pair.ap.Id,["attachPointB"]=pair.bp.Id,["symmetric"]=false},refs);
            // Reconstruct membership and meshes using the already validated state.
            Replace(Current().Aircraft.Aircraft.GenerateXml(false));
            wingsToValidate.Add(wing.Id);
            return new JObject{["kind"]="wing.control.add",["partId"]=control.Id,["wingPartId"]=wing.Id,["temporaryId"]=temporary,["style"]=op["style"],["templateId"]=template.Key,
                ["controlAttachPointId"]=pair.ap.Id,["wingAttachPointId"]=pair.bp.Id,["attachmentBasis"]="native_wing_surface_receive_point",
                ["synchronizedPartIds"]=new JArray(),["affectedPartIds"]=new JArray(wing.Id,control.Id),["editMode"]="current_craft_rebuild"};
        }
        private static bool AirfoilValid(string name)
        {
            if(name.Length>128)return false;
            // A cambered NACA4 with a zero camber position is singular.
            var m=System.Text.RegularExpressions.Regex.Match(name,"^NACA([0-9])([0-9])([0-9]{2})$",System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if(m.Success && (m.Groups[3].Value=="00" || (m.Groups[1].Value!="0" && m.Groups[2].Value=="0")))return false;
            try{return AirfoilRegistry.ParseAirfoil(name)!=null;}catch{return false;}
        }
        private JObject MatchFuselage(PartData part,JObject op)
        {
            var f=part.GetModifier<JFuselageData>();if(f==null)throw new ApiError("shape_not_supported","fuselage.match requires JFuselage.");
            int index=Int(op,"sectionIndex");if(index<0 || index>=f.NumSlices)throw new ApiError("invalid_shape","sectionIndex outside this fuselage.");
            if(!f.TryGetNeighbour(index,out JFuselageData target,out int targetIndex))throw new ApiError("adjacent_fuselage_not_found","This section has no connected native fuselage neighbour.");
            var shape=target[targetIndex];var cut=target.GetCutting(targetIndex);
            if(shape.ThicknessMode!=f[index].ThicknessMode)throw new ApiError("thickness_mode_mismatch","Adjacent sections use different thickness units.");
            if(f.SliceIsFront(index)==target.SliceIsFront(targetIndex)){shape.Mirror();cut.Mirror();}
            f[index]=shape;f.SetCutting(index,cut);f.SetSmoothing(index,true);target.SetSmoothing(targetIndex,true);f.SyncSlice(index)=true;target.SyncSlice(targetIndex)=true;f.RaiseChange();target.RaiseChange();
            return new JObject{["kind"]="fuselage.match",["partId"]=part.Id,["sectionIndex"]=index,["matchedPartId"]=target.Part.Id,["matchedSectionIndex"]=targetIndex};
        }
        private static double ChordFraction(List<InputWingSlice> slices,float span,float hinge,bool leading)
        {
            ChordAt(slices,span,out float offset,out float chord);return leading?.5-(hinge-offset)/chord:.5+(hinge-offset)/chord;
        }
        private static void ChordAt(List<InputWingSlice> slices,float span,out float offset,out float chord)
        {
            int i=InputWingSlice.FindSliceAtPos(slices,span,out float t);
            if(i<0 || i>=slices.Count)throw new ApiError("invalid_control_surface","Control surface extends outside the wing span.");
            int j=Math.Min(i+1,slices.Count-1);offset=math.lerp(slices[i].Offset,slices[j].Offset,t);chord=math.lerp(slices[i].Scale,slices[j].Scale,t);
        }
        private static void ValidateControlPatch(PartData part,XElement partXml,JObject patch,JWingData targetWing=null)
        {
            var data=part.GetModifier<ControlSurfacePartData>();var wing=targetWing??data.GetFirstConnectedWing();
            if(wing==null)throw new ApiError("wing_connection_required","Connect this control surface to a wing before editing its shape.");
            var state=ShapeCodec.State(partXml);var control=ControlSurface.GetStyle(data.Style);control.Init(state);
            if(!(control is EdgeSurfaceBase edge))throw new ApiError("shape_not_supported","This native control style has no validated edge editor (Spoiler/SplitFlap are read-only).");
            var slices=wing.WingSlices.Select(s=>s.Clone()).ToList();WingBuilder.InterpolateAllOffsetScale(slices);
            var range=edge.Range;if(range.x<0 || range.y>wing.WingSpan || range.y-range.x<.001)throw new ApiError("invalid_control_surface","spanRange must lie within the attached wing span.");
            foreach(var other in wing.ControlSurfacesInformational.Where(c=>c.Part!=part)) {
                if(other.ControlSurface.Location!=edge.Location)continue;var r=other.ControlSurface.Range;
                if(Math.Min(r.y,range.y)-Math.Max(r.x,range.x)>.0001)throw new ApiError("control_surface_overlap","Span overlaps control surface part "+other.Part.Id+" on the same wing edge.");
            }
            var desired=edge.StartPos;
            if(patch["chordFraction"]!=null) {
                double[] fractions=ShapeCodec.ArrayNumbers(patch["chordFraction"],2,.05,edge.IsLeadingEdge?.4:.8,"chordFraction");
                ChordAt(slices,range.x,out float offset0,out float chord0);ChordAt(slices,range.y,out float offset1,out float chord1);
                desired=new float2(offset0+chord0*(float)(edge.IsLeadingEdge?.5-fractions[0]:-.5+fractions[0]),offset1+chord1*(float)(edge.IsLeadingEdge?.5-fractions[1]:-.5+fractions[1]));
            }
            var claims=new WingSurfaceClaims(slices);edge.AddToClaims(claims);
            var accepted=claims.TryEnforceChordSizeRange(new Claim{SpanRange=range},desired,new float2(.05f,edge.IsLeadingEdge?.4f:.8f),.5f,edge.IsLeadingEdge);
            if(!accepted.HasValue || math.any(math.abs(accepted.Value-desired)>.0001f))throw new ApiError("invalid_control_surface","The hinge/chord size is invalid across the wing sections. Requested geometry would require native clamping.");
            ShapeCodec.SetVector(state,"startPos",new[]{(double)desired.x,desired.y});
        }
    }
}
