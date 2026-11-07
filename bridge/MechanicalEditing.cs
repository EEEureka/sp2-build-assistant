using System;
using System.Linq;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers.Powertrain;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private JObject MechanicalInfo(PartData part)
        {
            var shaft=part.GetModifier<JDriveShaftData>();
            if(shaft==null||!shaft.IsVisual)throw new ApiError("mechanical_not_supported","This adapter covers native visual JDriveShaft only; use native.state for other discovered attributes.");
            var points=Points(part);var ends=new JArray();
            for(int i=0;i<2;i++){
                var point=part.AttachPoints[i];var info=(JObject)points.First(p=>(int)p["id"]==point.Id).DeepClone();
                info["endpoint"]=i==0?"start":"end";
                info["connectedPartIds"]=new JArray(point.PartConnections.Select(c=>c.GetOtherPart(part).Id));
                ends.Add(info);
            }
            var a=ReadPosition(ends[0]["worldPosition"]);var b=ReadPosition(ends[1]["worldPosition"]);
            return new JObject{["identity"]=JToken.FromObject(Identity()),["partId"]=part.Id,["family"]="driveShaft",["endpoints"]=ends,
                ["endpointDistanceMetres"]=Vector3.Distance(a,b),["radiusMultiplier"]=shaft.Radius,["bootA"]=shaft.BootA,["bootB"]=shaft.BootB,
                ["source"]="live_native_attach_point_transforms_and_JDriveShaftData",["endpointSerialization"]="Explicitly loaded sub-centimetre local endpoints retain float roundtrip precision; native two-decimal endpoints keep their original format.",
                ["limits"]=new JObject{["toolMinimumLengthMetres"]=.01,["toolMaximumLengthMetres"]=1000,["nativeDesignerRadiusMultiplierRange"]=new JArray(.5,2),
                    ["connectedEndpointPolicy"]="fixed; explicitly move reviewed hosts in the same plan before changing the endpoint",["lengthMeaning"]="endpoint spacing, not a visible-mesh or collision certificate"}};
        }
        private JObject MechanicalUpdate(JObject op,BatchReferences refs)
        {
            var part=Part(refs.Resolve(op["partId"]));var changes=PrepareMechanicalChanges(part,op);
            var result=NativeStateApply(new JObject{["kind"]="native.state",["partId"]=op["partId"].DeepClone(),["changes"]=changes},refs);
            result["kind"]="mechanical.update";result["requested"]=op.DeepClone();result["effectiveMechanical"]=MechanicalInfo(part);result["valueStage"]="immediate_before_native_settle";
            return result;
        }
        private JArray PrepareMechanicalChanges(PartData part,JObject op)
        {
            var shaft=part.GetModifier<JDriveShaftData>();
            if(shaft==null||!shaft.IsVisual)throw new ApiError("mechanical_not_supported","Native visual JDriveShaft required.");
            var t=part.PartScript.transform;var points=Points(part);
            var a=ReadPosition(points.First(p=>(int)p["id"]==part.AttachPoints[0].Id)["worldPosition"]);
            var b=ReadPosition(points.First(p=>(int)p["id"]==part.AttachPoints[1].Id)["worldPosition"]);
            var changes=new JArray();
            foreach(string field in new[]{"startWorld","endWorld"})if(op[field]!=null){
                var target=ReadPosition(op[field]);int index=field=="startWorld"?0:1;var point=part.AttachPoints[index];
                if(point.PartConnections.Count>0){
                    var connected=point.PartConnections.Select(c=>c.GetOtherAttachPoint(point).AttachPointScript.transform.position).ToArray();
                    if(connected.Any(p=>Vector3.Distance(p,target)>.00001f))throw new ApiError("fixed_connected_endpoint","The requested endpoint would leave its connected native host. Move the explicit reviewed host first or keep this endpoint fixed.",
                        new JObject{["partId"]=part.Id,["endpoint"]=index==0?"start":"end",["connectedPartIds"]=new JArray(point.PartConnections.Select(c=>c.GetOtherPart(part).Id)),["writableExpanded"]=false});
                }
                if(index==0)a=target;else b=target;
                changes.Add(new JObject{["action"]="set",["path"]="JDriveShaft.State",["attribute"]=index==0?"start":"end",["value"]=new JArray(Vec(t.InverseTransformPoint(target)))});
            }
            float length=Vector3.Distance(a,b);
            if(length<.01f||length>1000)throw new ApiError("out_of_range","Drive shaft endpoint spacing must be 0.01..1000 metres (tool limit; native visual direction has a 0.01 metre threshold).");
            if(op["radiusMultiplier"]!=null){double radius=(double)PropertyValues.Convert(op["radiusMultiplier"],typeof(double),.5,2,"radiusMultiplier");changes.Add(new JObject{["action"]="set",["path"]="JDriveShaft.State",["attribute"]="radius",["value"]=radius});}
            foreach(string field in new[]{"bootA","bootB"})if(op[field]!=null){if(op[field].Type!=JTokenType.Boolean)throw new ApiError("invalid_boolean",field);changes.Add(new JObject{["action"]="set",["path"]="JDriveShaft.State",["attribute"]=field,["value"]=op[field].DeepClone()});}
            if(changes.Count==0)throw new ApiError("invalid_input","Provide endpoints, radiusMultiplier or boots.");
            return changes;
        }
    }
}
