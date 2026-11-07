using System;
using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers.CarverParts;
using Assets.Scripts.Design.UI.Overload;
using Newtonsoft.Json.Linq;
using UnityEngine;
using AssemblyData=Assets.Scripts.Craft.Parts.Assembly;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private JObject NativeStateRead(JObject args)
        {
            var part=Part(Int(args,"id"));
            var metadata=new JArray(part.GetOverloadMetadataLookup().Select(pair=>new JObject{["element"]=pair.Key,["attributes"]=new JArray(pair.Value.Attributes.Select(m=>new JObject{
                ["name"]=m.Name,["type"]=m.DataType.ToString(),["defaultValue"]=m.DefaultValue,["min"]=m.MinValue,["max"]=m.MaxValue,["optional"]=m.IsOptional,["readOnly"]=m.IsReadOnly,["choices"]=m.EnumValues==null?null:JArray.FromObject(m.EnumValues)}))}));
            return new JObject{["identity"]=JToken.FromObject(Identity()),["partId"]=part.Id,["state"]=Node(part.GenerateXml()),["metadata"]=metadata,
                ["source"]="live_native_xml_and_overload_metadata",["unknownAttributePolicy"]="native_text_edit; absence of metadata is not unsupported",
                ["attributeOperations"]=new JArray("set","remove","rename"),["emptyValuePolicy"]="native_editor_omits_empty_attributes",
                ["nodeOperations"]=new JObject{["supported"]=false,["reason"]="The native Overload panel edits attributes on existing nodes; typed structural operations are separate."},
                ["structuralOperations"]=new JObject{["partType"]="part.retype",["id"]="identity_is_not_an_editable_handle"}};
        }
        private static void ValidateNativeStateEdit(PartData part,XElement node,string name,string action,JToken value)
        {
            try{XName.Get(name);}catch(Exception){throw new ApiError("invalid_attribute_name","Use a valid native XML attribute name.");}
            if(node.Name.LocalName=="Part"&&(name=="id"||name=="partType"))throw new ApiError("structural_operation_required",name=="id"?"Object IDs cannot be forged by a state patch.":"Use explicit part.retype and review its destroyed connections.");
            OverloadElementMetadata element;var metadata=part.GetOverloadMetadataLookup();
            var entry=metadata.TryGetValue(node.Name.LocalName,out element)?element.Attributes.FirstOrDefault(a=>a.Name==name):null;
            if(entry!=null&&entry.IsReadOnly)throw new ApiError("read_only","Native Overload marks this attribute read-only: "+name);
            if(action!="set"||value==null||value.Type==JTokenType.Null||XmlValue(value)=="")return;
            string text=XmlValue(value);
            // Match the native panel's metadata-based numeric validation. It
            // deliberately enables ordinary text editing when metadata is absent.
            if(entry!=null&&(entry.DataType==OverloadDataType.Int||entry.DataType==OverloadDataType.Float)){
                double number;
                if(!double.TryParse(text,System.Globalization.NumberStyles.Float,Inv,out number)||double.IsNaN(number)||double.IsInfinity(number))throw new ApiError("invalid_number",name);
                if(entry.DataType==OverloadDataType.Int&&(number!=Math.Truncate(number)||number<int.MinValue||number>int.MaxValue))throw new ApiError("invalid_integer",name);
                if(entry.MinValue.HasValue&&number<entry.MinValue.Value||entry.MaxValue.HasValue&&number>entry.MaxValue.Value)throw new ApiError("out_of_range",name);
            }
        }
        private void ReinitializeNativePart(PartData part,XElement xml,bool changeType)
        {
            // Same object-level native initialization path as Overload.ApplyXML,
            // without reconstructing unrelated parts or opening a UI panel.
            var aircraft=Current().Aircraft;var old=part.PartScript;
            var creation=part.PartCreationInfoUsedForInitialization;var parent=old.transform.parent;
            var connections=part.PartConnections.ToArray();var points=part.AttachPoints.ToArray();var decals=part.Decals.ToArray();
            bool main=aircraft.MainCockpit==old;
            if(changeType)foreach(var connection in connections)connection.DestroyConnection(false,false,true);
            UnityEngine.Object.Destroy(old.gameObject);
            var state=new XElement(xml);var position=CrossSectionNumbers("position",(string)state.Attribute("position"),3);
            state.SetAttributeValue("position",XmlValue(JArray.FromObject(Vec(new Vector3((float)position[0],(float)position[1],(float)position[2])-aircraft.transform.position))));
            part.Initialize(state,Assets.Scripts.Craft.AircraftData.CurrentXmlVersion);
            if(!changeType){
                if(part.AttachPoints.Count!=points.Length)throw new ApiError("native_structure_changed","Attach-point layout changed; use an explicit structural operation.");
                part.PartConnections.AddRange(connections);
                // Keep freshly initialized points. Native modifiers can cache
                // these during Initialize; replacing the list with old points
                // leaves face-connectivity caches pointing to disconnected ones.
                // Reattach the existing edge objects by their stable point IDs.
                foreach(var connection in connections){
                    bool sideA=connection.PartA==part;
                    var owned=sideA?connection.AttachPointsA:connection.AttachPointsB;
                    var ids=owned.Select(p=>p.Id).ToArray();
                    foreach(var oldPoint in owned)oldPoint.PartConnections.Remove(connection);
                    owned.Clear();
                    foreach(int id in ids){
                        var point=part.GetAttachPoint(id);
                        if(point==null)throw new ApiError("native_structure_changed","A connected attach-point ID was removed during initialization.");
                        if(sideA)connection.AddAttachPointA(point);else connection.AddAttachPointB(point);
                    }
                }
            }
            part.CreateGameObject(aircraft,creation);part.EnableModifiers();
            foreach(var decal in decals)part.PartScript.AssignDecal(decal);
            var current=part.PartScript;current.transform.parent=parent;
            AssemblyData.CreateEditorCollidersForPartScript(current);AssemblyData.RunPreStartInitialization(current);
            if(main)aircraft.UpdateMainCockpit(current);
            MeshModifierBaseScript.RefreshForRecreatedPart(part);
            Current().OnAircraftStructureChanged();
            foreach(var connection in part.PartConnections)connection.RaiseConnectionChangedEvents(false);
            TrackInternal();
        }
        private JObject NativeStateApply(JObject op,BatchReferences refs)
        {
            var part=Part(refs.Resolve(op["partId"]));var source=part.GenerateXml();var state=new XElement(source);
            var changes=op["changes"] as JArray;if(changes==null||changes.Count==0||changes.Count>500)throw new ApiError("invalid_changes","Use 1..500 native attribute operations.");
            foreach(JObject edit in changes){
                string action=Required(edit,"action"),path=(string)edit["path"]??"Part",name=Required(edit,"attribute");
                if(!new[]{"set","remove","rename"}.Contains(action))throw new ApiError("invalid_input","Unknown native attribute action.");
                var node=SelectPath(state,path);ValidateNativeStateEdit(part,node,name,action,edit["value"]);
                if(action=="rename"){
                    string target=Required(edit,"newName");ValidateNativeStateEdit(part,node,target,"set",edit["value"]);
                    var attr=node.Attribute(name);if(attr==null)throw new ApiError("attribute_not_found",name);
                    if(node.Attribute(target)!=null)throw new ApiError("attribute_exists",target);
                    string value=attr.Value;attr.Remove();node.SetAttributeValue(target,value);
                }else if(action=="remove"||edit["value"]==null||edit["value"].Type==JTokenType.Null||XmlValue(edit["value"])=="")node.Attribute(name)?.Remove();
                else node.SetAttributeValue(name,XmlValue(edit["value"]));
            }
            ReinitializeNativePart(part,state,false);
            foreach(JObject edit in changes){
                var node=SelectPath(state,(string)edit["path"]??"Part");string attr=(string)edit["attribute"];
                if(node.Name.LocalName=="InputController.State"&&(attr=="input"||attr=="activationGroup"))
                    ValidateInputControllerExpression(part,attr,(string)node.Attribute(attr)??(attr=="input"?"Trim":"0"));
            }
            return new JObject{["kind"]="native.state",["partId"]=part.Id,["requested"]=changes.DeepClone(),["effectiveChanges"]=CraftDiff.Compare(source,part.GenerateXml()),["state"]=Node(part.GenerateXml()),["source"]="native_overload_equivalent_reinitialize"};
        }

        private JObject RetypeNativePart(JObject op,BatchReferences refs)
        {
            var part=Part(refs.Resolve(op["partId"]));string type=Required(op,"partType");
            if(op.Value<bool?>("acceptConnectionLoss")!=true)throw new ApiError("structural_review_required","Explicit acceptConnectionLoss:true is required for native partType changes.");
            var source=part.GenerateXml();var state=new XElement(source);state.SetAttributeValue("partType",type);
            var prototype=new PartData(new XElement(state),Assets.Scripts.Craft.AircraftData.CurrentXmlVersion,Assets.Scripts.Craft.CraftLoadContext.Designer);
            if(prototype.PartType.PartTypeId!=type)throw new ApiError("part_type_not_found",type);
            if(type==part.PartType.PartTypeId)throw new ApiError("invalid_input","The requested partType is unchanged; use an attribute patch for ordinary edits.");
            var dropped=new JArray(part.PartConnections.Select(c=>Node(c.GenerateXml())));
            ReinitializeNativePart(part,state,true);
            modelLifetimes[part.Id]=new System.Collections.Generic.KeyValuePair<PartData,string>(part,Guid.NewGuid().ToString("N"));
            refs.ReplaceLifetime(part.Id,PartInfo(part,false),(string)op["temporaryId"]);
            return new JObject{["kind"]="part.retype",["partId"]=part.Id,["oldType"]=(string)source.Attribute("partType"),["newType"]=type,
                ["destroyedConnections"]=dropped,["effectiveChanges"]=CraftDiff.Compare(source,part.GenerateXml()),["lifetimeChanged"]=true};
        }
    }
}
