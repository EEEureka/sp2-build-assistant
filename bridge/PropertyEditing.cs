using System;
using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Craft;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Parts.Modifiers.LandingGear.Procedural;
using Newtonsoft.Json.Linq;
using SP2Game=Assets.Scripts.Game;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private static JToken TextRenderingInfo(PartData p,bool live)
        {
            var text=p.GetModifier<TextDecalData>();if(text==null||!live)return JValue.CreateNull();
            try{
                // Query only existing glyph tables/fallbacks. Never add glyphs or mutate font atlases.
                var font=text.GetFont();uint[] missing;
                if(font==null)return new JObject{["status"]="unavailable",["reason"]="Native font asset is unavailable."};
                string printable=new string((text.Text??"").Where(c=>!char.IsControl(c)).ToArray());
                bool complete=font.HasCharacters(printable,out missing,true,false);
                var codes=(missing??new uint[0]).Distinct().ToArray();
                return new JObject{["status"]=complete?"glyphs_available":"missing_glyphs",["font"]=text.Font.ToString(),["fontAsset"]=font.name,
                    ["missingCodePoints"]=new JArray(codes.Select(c=>"U+"+c.ToString("X4"))),
                    ["missingCharacters"]=new JArray(codes.Select(c=>c<=0x10ffff&&!(c>=0xd800&&c<=0xdfff)?char.ConvertFromUtf32((int)c):"invalid Unicode scalar")),
                    ["meaning"]="Checks existing native font/fallback glyph tables for current raw non-control text, without adding glyphs. Missing glyphs may display replacement boxes. Availability does not certify layout, rich-text parsing, projection, occlusion or final pixels; inspect a native capture."};
            }catch(Exception e){return new JObject{["status"]="unavailable",["reason"]=e.GetBaseException().Message};}
        }
        private object PropertiesRead(string cmd,JObject args)
        {
            VisualScope.Keys(args,"id","templateId","type","family","query","fields","offset","limit");
            if(args["fields"]!=null&&(!(args["fields"] is JArray filter)||filter.Any(x=>x.Type!=JTokenType.String)))throw new ApiError("invalid_input","fields must be an array of propertyId strings.");
            if(cmd=="properties.get"&&args["id"]==null)throw new ApiError("invalid_input","properties.get requires a live part id.");
            if(new[]{"id","templateId","type"}.Count(x=>args[x]!=null)!=1)throw new ApiError("invalid_input","Choose exactly one of id, templateId or type.");
            var parts=new JArray();
            JObject templateSource=null;
            Action<PartData,XElement,bool,int?> add=(p,xml,live,templatePartId)=>{
                var all=PropertyRegistry.Describe(p,xml,live);var filtered=all.Where(x=>args["family"]==null||(string)x["family"]==(string)args["family"])
                    .Where(x=>args["query"]==null||x.ToString().IndexOf((string)args["query"],StringComparison.OrdinalIgnoreCase)>=0)
                    .Where(x=>args["fields"]==null||((JArray)args["fields"]).Values<string>().Contains((string)x["propertyId"])).ToArray();
                int offset=args["offset"]==null?0:VisualScope.Integer(args["offset"],"offset",0),limit=args["limit"]==null?100:VisualScope.Integer(args["limit"],"limit",1,1000);
                string shapeFamily=ShapeCodec.Family(xml);var editors=new JArray();
                if(shapeFamily!=null)editors.Add(new JObject{["family"]=shapeFamily,["readCommand"]="shape.get",["writeOperation"]="shape.update",["schemaCommand"]="shape.schema",["schemaArgs"]=new JObject{["family"]=shapeFamily},["configuration"]=ShapeCodec.Read(xml),["meaning"]="Use the existing typed shape editor for this family. Its schema is authoritative; UI/XML discovery does not create a duplicate generic setter."});
                if(xml.Elements("InputController.State").Any())editors.Add(new JObject{["family"]="inputControllers",["readCommand"]="parts.get",["writeOperation"]="part.update",["contract"]=JToken.FromObject(InputControllerFields.Description())});
                parts.Add(new JObject{["partType"]=p.PartType.PartTypeId,["partId"]=live?(JToken)p.Id:null,["templatePartId"]=templatePartId,["templateSource"]=live?null:templateSource?.DeepClone(),["specializedEditors"]=editors,
                    ["total"]=filtered.Length,["offset"]=offset,["fields"]=new JArray(filtered.Skip(offset).Take(limit)),["textRendering"]=TextRenderingInfo(p,live),
                    ["coverage"]=new JObject{["discovered"]=all.Count,["byEditability"]=new JObject(all.GroupBy(x=>(string)x["editability"]).Select(g=>new JProperty(g.Key,g.Count()))),
                        ["denominator"]="native UI attributes plus serialized attributes and overload metadata; complex nested custom widgets remain explicitly unsupported"}});
            };
            if(args["id"]!=null){var p=Part(VisualScope.Integer(args["id"],"id",0));add(p,p.GenerateXml(),true,null);}
            else{
                var templates=(args["templateId"]!=null?Templates().Where(x=>x.Key==(string)args["templateId"]):Templates().Where(x=>x.Value.AssemblyElement.Descendants("Part").Any(p=>(string)p.Attribute("partType")== (string)args["type"]))).ToArray();
                if(args["templateId"]==null&&templates.Length>1)throw new ApiError("template_ambiguous","Several native templates use this partType. Select an explicit templateId for its actual defaults.",new JObject{
                    ["partType"]=args["type"].DeepClone(),["candidates"]=new JArray(templates.Select(t=>new JObject{["templateId"]=t.Key,["templateName"]=t.Value.Name,["source"]=t.Value.Mod==null?(t.Value.IsSubassembly?"loaded_subassembly":"builtin"):"mod"}))});
                foreach(var t in templates)foreach(var px in t.Value.AssemblyElement.Descendants("Part")){
                    if(args["type"]!=null&&(string)px.Attribute("partType")!=(string)args["type"])continue;
                    templateSource=new JObject{["templateId"]=t.Key,["templateName"]=t.Value.Name,["source"]=t.Value.Mod==null?(t.Value.IsSubassembly?"loaded_subassembly":"builtin"):"mod"};
                    var p=new PartData(new XElement(px),AircraftData.CurrentXmlVersion,CraftLoadContext.Designer);add(p,px,false,p.Id);
                }
                if(parts.Count==0)throw new ApiError("template_not_found","No available template matched the requested ID or part type.");
            }
            return new JObject{["identity"]=args["id"]==null?null:JToken.FromObject(Identity()),["gameVersion"]=SP2Game.Version.ToString(),["registryVersion"]=PropertyRegistry.Version,["parts"]=parts,
                ["valueMeaning"]="Typed UI fields contain effective native values. xml: fields retain exact serialization; an omitted value is not an effective default.",
                ["developmentStatus"]="Registered adapters have representative native evidence in knowledge/native-adapter-evidence.json. This does not certify every catalog type, resource or dynamic combination; inspect currentCondition and the release acceptance report."};
        }
        private JObject PropertiesSet(JObject op,BatchReferences refs)
        {
            var part=Part(Resolve(op["partId"],refs));var patch=op["patch"] as JObject;
            if(patch==null||!patch.HasValues||patch.Count>100)throw new ApiError("invalid_input","patch needs 1..100 propertyId/value members.");
            var entries=PropertyRegistry.Entries(part).ToDictionary(e=>e.Id);var pending=patch.Properties().Select(p=>{
                if(!entries.ContainsKey(p.Name))throw new ApiError("property_not_found",p.Name+"; query properties.describe.");
                var e=entries[p.Name];return new{entry=e,requested=p.Value,value=NativePropertyAdapter.Validate(e,p.Value)};
            }).ToArray();
            // Validate every value and current-state condition before the first setter.
            foreach(var p in pending)NativePropertyAdapter.ValidateConditions(p.entry,p.value);
            bool symmetric=op.Value<bool?>("symmetric")??true;SymmetricTargets(part,symmetric);
            int partId=part.Id;bool rebuiltStyle=false;
            var affected=new System.Collections.Generic.HashSet<int>();var changes=new JArray();
            foreach(var p in pending){
                // A style edit can replace live modifier instances. Rebind
                // subsequent fields rather than writing to the retired part.
                var entry=PropertyRegistry.Entries(Part(partId)).Single(e=>e.Id==p.entry.Id);
                var value=NativePropertyAdapter.Validate(entry,p.requested);
                NativePropertyAdapter.ValidateConditions(entry,value);
                if(entry.Modifier is GearLegData&&entry.MemberName=="_gearLegStyle"){
                    // The generic callback resets Animator poses when changing
                    // prefab. This extra field is exposed by native Overload,
                    // whose serialized edit preserves existing keyframes.
                    var source=Part(partId);
                    // Match native property propagation: a modifier header's
                    // disabled sync overrides the operation's default true.
                    var peers=SymmetricTargets(source,symmetric&&!entry.Modifier.SymmetryDisabled);
                    int index=Array.IndexOf(source.Modifiers.OfType<GearLegData>().ToArray(),(GearLegData)entry.Modifier);
                    var xml=Current().Aircraft.Aircraft.GenerateXml(false);
                    foreach(var target in new[]{source}.Concat(peers)){
                        XmlPart(xml,target.Id).Elements("GearLeg.State").ElementAt(index).SetAttributeValue("gearLegStyle",(string)value);
                        affected.Add(target.Id);
                    }
                    Replace(xml);rebuiltStyle=true;
                }else{
                    foreach(int id in NativePropertyAdapter.Set(entry,value,symmetric))affected.Add(id);
                }
                var effective=PropertyValues.Read(PropertyRegistry.Entries(Part(partId)).Single(e=>e.Id==p.entry.Id).RawValue());
                changes.Add(new JObject{["propertyId"]=p.entry.Id,["requested"]=p.requested.DeepClone(),["effective"]=effective,
                    ["normalizationReason"]=JToken.DeepEquals(p.requested,effective)?null:"Native setter representation; re-query after settle for final effective values."});
            }
            return new JObject{["kind"]="properties.set",["partId"]=partId,["affectedPartIds"]=new JArray(affected.OrderBy(x=>x)),["effectiveChanges"]=changes,["editMode"]=rebuiltStyle?"native_style_rebuild_and_property_callbacks":"native_ui_setter_and_callbacks"};
        }
    }
}
