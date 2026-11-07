using System;
using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Craft;
using Assets.Scripts.Craft.Paint;
using Newtonsoft.Json.Linq;
using UnityEngine;
using SP2Game=Assets.Scripts.Game;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private static JObject NativeDisplayState(Assets.Scripts.Craft.Parts.PartData p)
        {
            var m=p.PartScript.PartMaterialScript;
            return new JObject{["isDisconnected"]=m.IsDisconnected,["isHidden"]=m.IsHidden,["isHighlighted"]=m.IsHighlighted,
                ["overrideMaterialPresent"]=m.OverrideMaterial!=null,["customMaterialPresent"]=m.CustomMaterial!=null,
                ["meaning"]="Native live display flags, not serialized paint. Disconnected parts use the designer grey material; hidden/override/custom materials can also mask palette changes. Modifier callbacks may customize rendering further."};
        }
        private static readonly PaintStyle[] WritablePaintStyles={PaintStyle.SolidColor,PaintStyle.SinglePlaneTextureColorMask,PaintStyle.TriPlaneTextureColorMask};
        private static JObject MaterialInfo(PartMaterial m)
        {
            return new JObject{["id"]=m.Id,["name"]=m.Name,["reserved"]=m.IsReserved,["style"]=m.Style.ToString(),
                ["metallic"]=m.Metallic,["smoothness"]=m.Smoothness,["emissionDay"]=m.EmissionDay,["emissionNight"]=m.EmissionNight,
                ["colors"]=new JArray(m.ColorData.Select((c,i)=>new JObject{["index"]=i,["rgba"]=PropertyValues.Read(c.Color),["metallic"]=c.Metallic,["smoothness"]=c.Smoothness,["emissionDay"]=c.EmissionDay,["emissionNight"]=c.EmissionNight})),
                ["textureId"]=m.Texture?.Id,["texturePresetId"]=m.TexturePresetId,["textureBlend"]=m.TextureBlend,["textureOffset"]=PropertyValues.Read(m.TextureOffset),["textureRotation"]=PropertyValues.Read(m.TextureRotation),["textureScale"]=PropertyValues.Read(m.TextureScale),["textureWrapMode"]=new JArray(m.TextureWrapMode.Select(x=>x.ToString()))};
        }
        private object AppearanceGet(JObject a)
        {
            VisualScope.Keys(a,"partIds","offset","limit");var craft=Current().Aircraft.Aircraft;
            int[] ids=a["partIds"]==null?craft.Assembly.Parts.Select(p=>p.Id).ToArray():PartIds(a["partIds"]);
            int offset=a["offset"]==null?0:VisualScope.Integer(a["offset"],"offset",0),limit=a["limit"]==null?100:VisualScope.Integer(a["limit"],"limit",1,2048);
            return new {identity=Identity(),themeName=craft.CurrentTheme.Name,globalCustomThemeFingerprint=SnapshotState.Fingerprint(SP2Game.Instance.AircraftThemes.CustomTheme.GenerateXml()),palette=new JArray(craft.CurrentTheme.AllMaterials.Select(MaterialInfo)),editablePaletteCapacity=50-Enum.GetValues(typeof(PaintStyle)).Length,
                totalParts=ids.Length,offset,capturedFrame=Time.frameCount,parts=new JArray(ids.Skip(offset).Take(limit).Select(id=>new JObject{["partId"]=id,["designerDisplayState"]=NativeDisplayState(Part(id)),["slots"]=new JArray(Part(id).MaterialIds.Select((m,s)=>new JObject{["slot"]=s,["materialId"]=m,["assignable"]=m>=0}))})),
                scope="Current aircraft only. Clone edits create a local Custom theme; global themes are never changed. Colors serialize to native RGBA8."};
        }
        private int[] PartIds(JToken token,BatchReferences refs=null)
        {
            if(!(token is JArray a)||a.Count<1||a.Count>2048)throw new ApiError("invalid_input","partIds requires 1..2048 IDs.");
            var ids=a.Select(t=>refs==null?VisualScope.Integer(t,"partId",0):refs.Resolve(t)).ToArray();if(ids.Distinct().Count()!=ids.Length)throw new ApiError("invalid_input","Duplicate part IDs.");foreach(int id in ids)Part(id);return ids;
        }
        private JObject AppearanceSet(JObject op,bool preview=false,BatchReferences refs=null)
        {
            string mode=Required(op,"mode");if(!new[]{"assign","clone","shared"}.Contains(mode))throw new ApiError("invalid_input","mode must be assign, clone or shared.");
            var craft=Current().Aircraft.Aircraft;int source=Int(op,"materialId");
            var theme=new ThemeData(new XElement(craft.CurrentTheme.GenerateXml()),AircraftData.CurrentXmlVersion);
            var material=theme.Materials.FirstOrDefault(m=>m.Id==source);
            if(material==null)throw new ApiError("material_not_editable","Choose an existing non-reserved palette material.");
            int[] ids=mode=="shared"?craft.Assembly.Parts.Where(p=>p.MaterialIds.Contains(source)).Select(p=>p.Id).ToArray():PartIds(op["partIds"],refs);
            if(mode=="shared"&&(op["partIds"]!=null||op["slots"]!=null))throw new ApiError("invalid_input","Shared mode explicitly affects all users; omit partIds and slots.");
            var patch=op["patch"] as JObject;
            if(mode=="assign"&&op["patch"]!=null)throw new ApiError("invalid_input","assign cannot edit material values.");
            if(mode!="assign"&&(patch==null||!patch.HasValues))throw new ApiError("invalid_input","clone/shared requires patch.");
            if(mode=="clone") {
                if(theme.Materials.Count>=50-Enum.GetValues(typeof(PaintStyle)).Length)throw new ApiError("palette_capacity","Native craft palette is full.");
                material=material.Clone();material.Id=theme.Materials.Count;theme.Materials.Add(material);
            }
            if(patch!=null)PatchMaterial(material,patch);
            var xml=craft.GenerateXml(false);var affected=new JArray();
            if(mode!="shared")foreach(int id in ids) {
                var p=Part(id);var slots=op["slots"] as JArray;
                if(slots==null||slots.Count<1)throw new ApiError("invalid_input","assign/clone requires explicit slot indices.");
                var slotIds=slots.Select(s=>VisualScope.Integer(s,"slot",0,p.MaterialIds.Count-1)).Distinct().ToArray();
                var values=p.MaterialIds.ToArray();foreach(int slot in slotIds){if(values[slot]<0)throw new ApiError("reserved_material_slot","Native reserved slots cannot be reassigned.");values[slot]=material.Id;}
                xml.Element("Assembly").Element("Parts").Elements("Part").Single(e=>(int)e.Attribute("id")==id).SetAttributeValue("materials",string.Join(",",values));
            }
            if(mode!="assign") {theme.Name="Custom";xml.SetAttributeValue("theme","Custom");xml.Element("Theme")?.Remove();xml.Add(theme.GenerateXml());}
            if(preview)return new JObject{["kind"]="appearance.set",["mode"]=mode,["sourceMaterialId"]=source,["materialId"]=material.Id,["affectedPartIds"]=new JArray(ids),["candidateMaterial"]=MaterialInfo(material),["previewOnly"]=true};
            Replace(xml);
            return new JObject{["kind"]="appearance.set",["mode"]=mode,["sourceMaterialId"]=source,["materialId"]=material.Id,["affectedPartIds"]=new JArray(ids),["effectiveMaterial"]=MaterialInfo(Current().Aircraft.Aircraft.CurrentTheme.AllMaterials.Single(m=>m.Id==material.Id)),["scope"]="current_aircraft"};
        }
        private static void PatchMaterial(PartMaterial m,JObject p)
        {
            VisualScope.Keys(p,"name","style","colors","metallic","smoothness","emissionDay","emissionNight","textureId","texturePresetId","textureBlend","textureOffset","textureRotation","textureScale","textureWrapMode");
            if(p["name"]!=null)m.Name=(string)PropertyValues.Convert(p["name"],typeof(string),0,0,"name");
            if(p["style"]!=null){var s=(PaintStyle)PropertyValues.Convert(p["style"],typeof(PaintStyle),0,0,"style");if(!WritablePaintStyles.Contains(s))throw new ApiError("invalid_input","This paint style is reserved for native assets.");m.Style=s;}
            if(p["metallic"]!=null)m.Metallic=(float)PropertyValues.Number(p["metallic"],0,1,"metallic");
            if(p["smoothness"]!=null)m.Smoothness=(float)PropertyValues.Number(p["smoothness"],0,1,"smoothness");
            if(p["emissionDay"]!=null)m.EmissionDay=(float)PropertyValues.Number(p["emissionDay"],0,5,"emissionDay");
            if(p["emissionNight"]!=null)m.EmissionNight=(float)PropertyValues.Number(p["emissionNight"],0,5,"emissionNight");
            if(p["colors"]!=null){if(!(p["colors"] is JArray colors)||colors.Count<1||colors.Count>4)throw new ApiError("invalid_input","colors contains 1..4 indexed patches.");var seen=new System.Collections.Generic.HashSet<int>();
                foreach(JToken t in colors){var c=t as JObject;VisualScope.Keys(c,"index","rgba","metallic","smoothness","emissionDay","emissionNight");int i=VisualScope.Integer(c["index"],"color.index",0,3);if(!seen.Add(i))throw new ApiError("invalid_input","Duplicate color index.");var target=m.ColorData[i];
                    if(c["rgba"]!=null)target.Color=(Color)PropertyValues.Convert(c["rgba"],typeof(Color),0,1,"rgba");
                    foreach(string k in new[]{"metallic","smoothness","emissionDay","emissionNight"})if(c.Property(k)!=null){float? v=c[k].Type==JTokenType.Null?(float?)null:(float)PropertyValues.Number(c[k],0,k.StartsWith("emission")?5:1,k);if(k=="metallic")target.Metallic=v;if(k=="smoothness")target.Smoothness=v;if(k=="emissionDay")target.EmissionDay=v;if(k=="emissionNight")target.EmissionNight=v;}
                    if(m.Style==PaintStyle.SolidColor&&(i!=0||c.Properties().Any(x=>x.Name!="index"&&x.Name!="rgba")))throw new ApiError("invalid_input","SolidColor supports only color 0 RGBA; use material-level finish values.");
                }}
            if(p["textureId"]!=null){m.Texture=SP2Game.Instance.PaintTextureManager.GetTextureData(m.Style,VisualScope.String(p["textureId"],"textureId"));if(m.Texture==null||!m.Texture.Available)throw new ApiError("invalid_resource_id","Texture is unavailable for this paint style.");m.TexturePresetId=null;}
            if(m.Style!=PaintStyle.SolidColor&&(m.Texture==null||m.Texture.PaintStyle!=m.Style))throw new ApiError("invalid_resource_id","Textured styles require a compatible textureId.");
            if(p["texturePresetId"]!=null){string id=VisualScope.String(p["texturePresetId"],"texturePresetId");if(m.Texture?.FindPreset(id)==null)throw new ApiError("invalid_resource_id","Unknown texture preset.");m.TexturePresetId=id;}
            if(p["textureBlend"]!=null)m.TextureBlend=(float)PropertyValues.Number(p["textureBlend"],0,1,"textureBlend");
            if(p["textureOffset"]!=null)m.TextureOffset=(Vector3)PropertyValues.Convert(p["textureOffset"],typeof(Vector3),-10000,10000,"textureOffset");
            if(p["textureRotation"]!=null)m.TextureRotation=(Vector3)PropertyValues.Convert(p["textureRotation"],typeof(Vector3),-360,360,"textureRotation degrees");
            if(p["textureScale"]!=null)m.TextureScale=(Vector3)PropertyValues.Convert(p["textureScale"],typeof(Vector3),0.0001,10000,"textureScale");
            if(p["textureWrapMode"]!=null){var modes=p["textureWrapMode"] as JArray;if(modes==null||modes.Count!=3||m.Style!=PaintStyle.SinglePlaneTextureColorMask)throw new ApiError("invalid_input","textureWrapMode requires three native enum IDs and flat texture style.");m.TextureWrapMode=modes.Select(x=>(PaintTextureWrapMode)PropertyValues.Convert(x,typeof(PaintTextureWrapMode),0,0,"textureWrapMode")).ToArray();}
            if(m.Style==PaintStyle.SolidColor&&p.Properties().Any(x=>x.Name.StartsWith("texture")))throw new ApiError("invalid_input","Texture fields do not apply to SolidColor.");
        }
        private object ResourcesList(JObject a)
        {
            VisualScope.Keys(a,"category","partId","offset","limit");string category=Required(a,"category");var rows=new JArray();
            if(category=="textures")foreach(var s in WritablePaintStyles.Where(x=>x!=PaintStyle.SolidColor))foreach(var t in SP2Game.Instance.PaintTextureManager.GetTextureData(s))rows.Add(new JObject{["id"]=t.Id,["name"]=t.DisplayName,["category"]=t.Category,["paintStyle"]=s.ToString(),["available"]=t.Available,["presets"]=new JArray(t.Presets.Select(x=>new JObject{["id"]=x.Id,["name"]=x.DisplayName}))});
            else if(category=="decals")foreach(var t in SP2Game.Instance.CraftDecalManager.CraftDecals)rows.Add(new JObject{["id"]=t.Id,["name"]=t.DisplayName,["category"]=t.Category,["aspectRatio"]=t.AspectRatio});
            else if(category=="propertyChoices"){var p=Part(Int(a,"partId"));foreach(var e in PropertyRegistry.Entries(p)){var d=e.Describe(true);if(d["enumValues"]!=null)rows.Add(new JObject{["propertyId"]=e.Id,["values"]=d["enumValues"].DeepClone(),["condition"]=e.Condition});}}
            else throw new ApiError("invalid_input","category: textures, decals, propertyChoices (with partId).");
            int offset=a["offset"]==null?0:VisualScope.Integer(a["offset"],"offset",0),limit=a["limit"]==null?100:VisualScope.Integer(a["limit"],"limit",1,1000);
            return new {identity=Identity(),category,total=rows.Count,offset,items=new JArray(rows.Skip(offset).Take(limit))};
        }
    }
}
