using System;
using System.Collections.Generic;
using System.Linq;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Parts.Modifiers.LandingGear.Procedural;
using Assets.Scripts.Craft.Parts.Modifiers.Wheel;
using Assets.Scripts.Craft.Parts.Modifiers.Weapons;
using Assets.Scripts.Design.Symmetry;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private sealed class PartGroup {internal string Session;internal long Revision;internal PartData[] Parts;}
        private readonly Dictionary<string,PartGroup> partGroups=new Dictionary<string,PartGroup>();
        private readonly Dictionary<int,Pose> requiredPoses=new Dictionary<int,Pose>();
        private static Quaternion ReadQ(JToken t){return (Quaternion)PropertyValues.Convert(t,typeof(Quaternion),-double.MaxValue,double.MaxValue,"rotationQuaternion");}
        private static Vector3 ReadPosition(JToken t){return (Vector3)PropertyValues.Convert(t,typeof(Vector3),-100000,100000,"position metres");}
        private static JObject PoseInfo(Transform t){return new JObject{["position"]=PropertyValues.Read(t.position),["rotationQuaternion"]=PropertyValues.Read(t.rotation)};}
        private Pose TransformFrame(JToken token)
        {
            var a=token as JObject??(token==null?new JObject{["kind"]="world"}:null);VisualScope.Keys(a,"kind","partId","position","rotationQuaternion");
            string kind=Required(a,"kind");if(kind=="world"){if(a.Count!=1)throw new ApiError("invalid_input","world frame has no additional fields.");return new Pose(Vector3.zero,Quaternion.identity);}
            if(kind=="custom")return new Pose(ReadPosition(a["position"]),ReadQ(a["rotationQuaternion"]));
            Transform t=kind=="part"?Part(Int(a,"partId")).PartScript.transform:kind=="craft"?Current().Aircraft.MainCockpit.transform:null;
            if(t==null)throw new ApiError("invalid_input","frame kind: world, part, craft or custom.");
            return new Pose(t.position,t.rotation);
        }
        private int? NativeHost(PartData p)
        {
            var control=p.GetModifier<ControlSurfacePartData>();if(control!=null)return control.GetFirstConnectedWing()?.Part.Id;
            var missile=p.GetModifier<ProceduralMissileSubPartData>();if(missile!=null)return missile.Script?.GetConnectedMissile()?.PartScript.Part.Id;
            // Query the native provider's actual animated target. Graph
            // adjacency alone does not establish ownership (multiple wheels
            // may be attached, but the native leg drives only one).
            if(p.PartScript.GetModifierWithInterface<IGearLegCompatibleWheel>()!=null)
                foreach(var c in p.PartConnections){
                    var leg=c.GetOtherPart(p)?.PartScript?.GetModifier<GearLegScript>();
                    if(leg!=null && leg.GetAnimatableElements().Any(e=>e.Id=="Wheel" && e.Transform==p.PartScript.transform))return leg.PartScript.Part.Id;
                }
            return null;
        }
        private JObject GroupInfo(int[] ids)
        {
            var set=new HashSet<int>(ids);var parts=Current().Aircraft.Aircraft.Assembly.Parts;
            var dependencies=new JArray(parts.Where(p=>NativeHost(p).HasValue&&(set.Contains(p.Id)||set.Contains(NativeHost(p).Value))).Select(p=>new JObject{["partId"]=p.Id,["hostPartId"]=NativeHost(p),["bothIncluded"]=set.Contains(p.Id)&&set.Contains(NativeHost(p).Value),["kind"]="native_derived_transform"}));
            var boundary=new JArray(parts.Where(p=>set.Contains(p.Id)).SelectMany(p=>p.PartConnections).Distinct().Where(c=>set.Contains(c.PartA.Id)!=set.Contains(c.PartB.Id)).Select(c=>new JObject{["partA"]=c.PartA.Id,["partB"]=c.PartB.Id}));
            var targets=new JArray(parts.Where(p=>p.GetModifier<PartTargetingData>()!=null&&set.Contains(p.Id)).Select(p=>new JObject{["partId"]=p.Id,["targeting"]=Node(p.GenerateXml().Element("PartTargeting.State"))}));
            return new JObject{["partIds"]=new JArray(ids),["nativeDependencies"]=dependencies,["externalConnections"]=boundary,["targetReferences"]=targets,["meaning"]="Explicit rigid group. External connections are retained without snapping. Targeting references do not imply movement ownership."};
        }
        private object GroupsResolve(JObject a)
        {
            VisualScope.Keys(a,"craftSessionId","expectedRevision","selector");VisualGuard(a);
            var resolved=VisualResolve(new JObject{["craftSessionId"]=session,["expectedRevision"]=revision,["groups"]=new JArray(new JObject{["name"]="group",["selector"]=a["selector"]?.DeepClone()})});
            var ids=resolved["partIds"].Values<int>().ToArray();string id=Guid.NewGuid().ToString("N");
            foreach(string stale in partGroups.Where(x=>x.Value.Session!=session||x.Value.Revision!=revision).Select(x=>x.Key).ToArray())partGroups.Remove(stale);
            if(partGroups.Count>=64)partGroups.Remove(partGroups.Keys.First());partGroups[id]=new PartGroup{Session=session,Revision=revision,Parts=ids.Select(Part).ToArray()};
            var info=GroupInfo(ids);info["groupId"]=id;info["identity"]=JToken.FromObject(Identity());info["lifetime"]="Session and revision bound; any rebuild invalidates object continuity. Resolve again after edits.";return info;
        }
        private int[] TransformIds(JObject op,BatchReferences refs)
        {
            if((op["groupId"]!=null)==(op["partIds"]!=null))throw new ApiError("invalid_input","Choose groupId or explicit partIds.");
            if(op["partIds"]!=null){var a=op["partIds"] as JArray;if(a==null||a.Count<1||a.Count>2048)throw new ApiError("invalid_input","partIds requires 1..2048 references.");return PartIds(new JArray(a.Select(x=>refs.Resolve(x))));}
            PartGroup g;if(!partGroups.TryGetValue(Required(op,"groupId"),out g)||g.Session!=session||g.Revision!=revision||g.Parts.Any(p=>Current().Aircraft.Aircraft.Assembly.GetPartById(p.Id)!=p))throw new ApiError("stale_group","Group identity or object continuity changed. Use groups.resolve again.");
            foreach(var p in g.Parts)refs.Resolve(new JValue(p.Id));return g.Parts.Select(p=>p.Id).ToArray();
        }
        private JObject TransformApply(JObject op,BatchReferences refs)
        {
            var ids=TransformIds(op,refs);var set=new HashSet<int>(ids);var info=GroupInfo(ids);
            if(((JArray)info["nativeDependencies"]).Any(d=>!(bool)d["bothIncluded"]))throw new ApiError("incomplete_native_group","Include each derived part and its native host in the rigid group.",info);
            var frame=TransformFrame(op["frame"]);string mode=Required(op,"mode");var anchor=Part(op["anchorPartId"]==null?ids[0]:refs.Resolve(op["anchorPartId"]));
            if(!set.Contains(anchor.Id))throw new ApiError("invalid_input","anchorPartId must be a group member.");
            Quaternion localRotation=op["rotationQuaternion"]==null?Quaternion.identity:ReadQ(op["rotationQuaternion"]);
            Vector3 translation,pivot;Quaternion rotation;
            if(mode=="delta"){
                if(op["position"]!=null)throw new ApiError("invalid_input","delta uses translation, not position.");
                translation=frame.rotation*(op["translation"]==null?Vector3.zero:ReadPosition(op["translation"]));
                pivot=op["pivot"]==null?anchor.PartScript.transform.position:frame.position+frame.rotation*ReadPosition(op["pivot"]);
                rotation=frame.rotation*localRotation*Quaternion.Inverse(frame.rotation);
            }else if(mode=="absolute"){
                if(op["pivot"]!=null||op["translation"]!=null||op["rotationQuaternion"]==null||op["position"]==null)throw new ApiError("invalid_input","absolute requires anchor position and rotationQuaternion; no pivot/translation.");
                pivot=anchor.PartScript.transform.position;translation=frame.position+frame.rotation*ReadPosition(op["position"])-pivot;
                rotation=frame.rotation*localRotation*Quaternion.Inverse(anchor.PartScript.transform.rotation);
            }else throw new ApiError("invalid_input","mode is delta or absolute.");
            var desired=ids.ToDictionary(id=>id,id=>{var t=Part(id).PartScript.transform;return new Pose(pivot+rotation*(t.position-pivot)+translation,rotation*t.rotation);});
            bool symmetric=op.Value<bool?>("symmetric")??false;
            if(symmetric){var config=EffectiveSymmetryConfig();if(config.Mode==SymmetryMode.Disabled)config=config.Clone(SymmetryMode.Mirrored);
                foreach(int id in ids){var source=Part(id);var peers=SymmetricTargets(source,true);if(peers.Any(p=>set.Contains(p.Id)))throw new ApiError("symmetry_scope_overlap","A symmetric peer is already in the explicit group. Use symmetric:false or select one side.");
                    var old=new List<SymmetryTransform>();SymmetryUtility.GetSymmetricTransforms(source,config,old);
                    // Use the source-specific native mirror offset by temporarily sampling its pose, without yielding or callbacks.
                    var next=new List<SymmetryTransform>();var t=source.PartScript.transform;var p0=t.position;var q0=t.rotation;
                    try{t.SetPositionAndRotation(desired[id].position,desired[id].rotation);SymmetryUtility.GetSymmetricTransforms(source,config,next);}finally{t.SetPositionAndRotation(p0,q0);}
                    foreach(var peer in peers){int i=old.FindIndex(s=>Vector3.Distance(s.Position,peer.PartScript.transform.position)<.01f&&Quaternion.Angle(s.Rotation,peer.PartScript.transform.rotation)<.1f);
                        if(i<0||i>=next.Count||desired.ContainsKey(peer.Id))throw new ApiError("symmetry_scope_overlap","Cannot resolve a unique native mirror/radial peer.");desired[peer.Id]=new Pose(next[i].Position,next[i].Rotation);}
                }
            }
            var allInfo=GroupInfo(desired.Keys.ToArray());if(((JArray)allInfo["nativeDependencies"]).Any(d=>!(bool)d["bothIncluded"]))throw new ApiError("incomplete_native_group","Symmetric expansion omits a native host/dependent.",allInfo);
            foreach(var p in desired)if(p.Value.position.magnitude>100000)throw new ApiError("invalid_input","Transformed position exceeds 100000 metres.");
            // Match native rigid selection movement: all poses change once, with no graph traversal or independent scaling.
            foreach(var p in desired){Part(p.Key).PartScript.transform.SetPositionAndRotation(p.Value.position,p.Value.rotation);requiredPoses[p.Key]=p.Value;}
            Physics.SyncTransforms();Current().OnAircraftStructureChanged();
            allInfo["kind"]="transform.apply";allInfo["frame"]=op["frame"]?.DeepClone()??new JObject{["kind"]="world"};allInfo["mode"]=mode;allInfo["anchorPartId"]=anchor.Id;
            allInfo["effectivePoses"]=new JArray(desired.Keys.Select(id=>new JObject{["partId"]=id,["pose"]=PoseInfo(Part(id).PartScript.transform)}));return allInfo;
        }
        private void ValidateRequiredPoses()
        {
            foreach(var p in requiredPoses){var t=Part(p.Key).PartScript.transform;double pos=Vector3.Distance(t.position,p.Value.position),angle=CameraState.QuaternionAngle((JArray)PropertyValues.Read(t.rotation),(JArray)PropertyValues.Read(p.Value.rotation));
                if(pos>.0001||angle>.01)throw new ApiError("transform_native_normalization","Native dependent motion changed a requested rigid pose.",new JObject{["partId"]=p.Key,["positionErrorMetres"]=pos,["rotationErrorDegrees"]=angle});}
        }
        private object DecalPoseGet(JObject a)
        {
            var p=Part(Int(a,"id"));var script=p.PartScript.GetComponentInChildren<DecalScript>();if(script==null)throw new ApiError("not_decal","This part has no native decal projector.");
            var projector=(Transform)PrivateField(script,"_projectorTransform");var t=p.PartScript.transform;
            var size=script.Data.Size;
            return new {identity=Identity(),partId=p.Id,partPose=PoseInfo(t),projectorPose=PoseInfo(projector),projectorPositionInPart=PropertyValues.Read(t.InverseTransformPoint(projector.position)),projectorRotationInPart=PropertyValues.Read(Quaternion.Inverse(t.rotation)*projector.rotation),
                projectorLocalBox=new{min=PropertyValues.Read(new Vector3(-size.x/2,-size.y/2,0)),max=PropertyValues.Read(new Vector3(size.x/2,size.y/2,size.z))},projectorToWorldRows=MatrixRows(projector.localToWorldMatrix),
                meaning="Projector origin is the front of the projection volume, not its center. Local +Z spans 0..depth; X/Y bounds use effective dimensions including texture aspect ratio. Put the intended receiving surface strictly inside this volume: exact coincidence with its front plane can clip texture decals. Part origin also includes penetration/depth and prefab offsets; pose writes solve for the Part pose."};
        }
        private JObject DecalPoseSet(JObject op,BatchReferences refs)
        {
            int id=refs.Resolve(op["partId"]);var p=Part(id);var script=p.PartScript.GetComponentInChildren<DecalScript>();if(script==null)throw new ApiError("not_decal","This part has no decal projector.");
            var target=TransformFrame(op["frame"]);var projector=(Transform)PrivateField(script,"_projectorTransform");var part=p.PartScript.transform;
            var q=target.rotation*ReadQ(op["rotationQuaternion"]);var point=target.position+target.rotation*ReadPosition(op["position"]);
            var localRot=Quaternion.Inverse(part.rotation)*projector.rotation;var offset=Quaternion.Inverse(part.rotation)*(projector.position-part.position);var partQ=q*Quaternion.Inverse(localRot);
            var request=new JObject{["kind"]="transform.apply",["partIds"]=new JArray(id),["mode"]="absolute",["position"]=PropertyValues.Read(point-partQ*offset),["rotationQuaternion"]=PropertyValues.Read(partQ),["symmetric"]=op["symmetric"]?.DeepClone()??false};
            var result=TransformApply(request,refs);result["kind"]="decal.pose.set";result["projector"]=JToken.FromObject(DecalPoseGet(new JObject{["id"]=id}));return result;
        }
        private JObject TransformAlign(JObject op,BatchReferences refs)
        {
            var ids=TransformIds(op,refs);int source=refs.Resolve(op["sourcePartId"]),target=refs.Resolve(op["targetPartId"]);if(!ids.Contains(source)||ids.Contains(target))throw new ApiError("invalid_input","Source must be a moving group member; target must be outside the group.");
            var a=Part(source);var b=Part(target);var ap=a.AttachPoints.SingleOrDefault(x=>x.Id==Int(op,"sourcePointId"));var bp=b.AttachPoints.SingleOrDefault(x=>x.Id==Int(op,"targetPointId"));
            if(ap==null||bp==null)throw new ApiError("attach_point_not_found","Query connections.points.");
            var pa=(JObject)Points(a).Single(x=>(int)x["id"]==ap.Id);var pb=(JObject)Points(b).Single(x=>(int)x["id"]==bp.Id);
            var from=ReadPosition(pa["worldPosition"]);var to=ReadPosition(pb["worldPosition"]);
            string axis=op.Value<string>("axis")??"opposedNormals";Vector3 va,vb;
            if(axis=="jointAxes"){va=a.PartScript.transform.TransformDirection(ap.JointAxis);vb=b.PartScript.transform.TransformDirection(bp.JointAxis);}
            else if(axis=="opposedNormals"){va=a.PartScript.transform.TransformDirection(ap.Normal);vb=-b.PartScript.transform.TransformDirection(bp.Normal);}else throw new ApiError("invalid_input","axis is opposedNormals or jointAxes.");
            if(va.sqrMagnitude<1e-12||vb.sqrMagnitude<1e-12)throw new ApiError("invalid_axis","Native attachment axis is zero.");
            var offset=op["offset"]==null?Vector3.zero:b.PartScript.transform.rotation*ReadPosition(op["offset"]);
            var q=Quaternion.FromToRotation(va,vb);var result=TransformApply(new JObject{["partIds"]=new JArray(ids),["mode"]="delta",["pivot"]=PropertyValues.Read(from),["translation"]=PropertyValues.Read(to+offset-from),["rotationQuaternion"]=PropertyValues.Read(q),["symmetric"]=op["symmetric"]?.DeepClone()??false},refs);
            result["kind"]="transform.align";result["connectionCreated"]=false;result["rollPolicy"]="Shortest axis rotation; no additional roll constraint.";return result;
        }
    }
}
