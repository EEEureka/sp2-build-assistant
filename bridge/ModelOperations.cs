using System;
using System.Collections.Generic;
using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Craft;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Parts.Modifiers.CarverParts;
using Newtonsoft.Json.Linq;
using UnityEngine;
using AssemblyData=Assets.Scripts.Craft.Parts.Assembly;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private Tuple<int,int> ClosestModelAttachment(PartData a,PartData b)
        {
            var pa=Points(a).ToDictionary(x=>(int)x["id"]);var pb=Points(b).ToDictionary(x=>(int)x["id"]);
            var candidates=(from ap in a.AttachPoints from bp in b.AttachPoints
                where ap.AllowManualConnection&&bp.AllowManualConnection&&(ap.IsAvailable||ap.AllowMultipleManualConnections)&&(bp.IsAvailable||bp.AllowMultipleManualConnections)&&bp.CanReceive(ap)
                let distance=Vector3.Distance(ReadPosition(pa[ap.Id]["worldPosition"]),ReadPosition(pb[bp.Id]["worldPosition"]))
                orderby distance select new{a=ap.Id,b=bp.Id,distance}).ToArray();
            if(candidates.Length==0)throw new ApiError("invalid_connection","No available directed compatible native attachment pair.");
            if(candidates.Length>1&&Math.Abs(candidates[0].distance-candidates[1].distance)<.000001)throw new ApiError("binding_ambiguous","Several compatible attachment pairs are equally near; choose explicit point IDs.",new JObject{["candidates"]=new JArray(candidates.Take(8).Select(x=>new JObject{["sourcePointId"]=x.a,["targetPointId"]=x.b,["distanceMetres"]=x.distance}))});
            return Tuple.Create(candidates[0].a,candidates[0].b);
        }
        private JObject AutoModelConnection(JObject op,BatchReferences refs)
        {
            var a=Part(refs.Resolve(op["partA"]));var b=Part(refs.Resolve(op["partB"]));if(a==b)throw new ApiError("invalid_connection","Cannot connect a part to itself.");
            var pair=ClosestModelAttachment(a,b);
            // Forward the caller's lifetime-bearing references. Resolving again
            // as a bare ID incorrectly rejects a newly created part whose ID
            // was reused after a deletion in this same batch.
            var result=ApplyCore(new JObject{["kind"]="connection.connect",["partA"]=op["partA"].DeepClone(),["partB"]=op["partB"].DeepClone(),["attachPointA"]=pair.Item1,["attachPointB"]=pair.Item2,["symmetric"]=op["symmetric"]?.DeepClone()??false},refs);
            result["kind"]="connection.auto";result["sourcePointId"]=pair.Item1;result["targetPointId"]=pair.Item2;result["selection"]="unique_closest_directed_compatible_available_native_pair";return result;
        }
        private static readonly Dictionary<int,KeyValuePair<PartData,string>> modelLifetimes=new Dictionary<int,KeyValuePair<PartData,string>>();
        private string observedModelLifetimes;
        private void ObserveModelLifetimes(bool preserve=false)
        {
            var parts=Current().Aircraft.Aircraft.Assembly.Parts;
            foreach(int id in modelLifetimes.Keys.Except(parts.Select(p=>p.Id)).ToArray())modelLifetimes.Remove(id);
            foreach(var part in parts){KeyValuePair<PartData,string> old;string token;
                token=modelLifetimes.TryGetValue(part.Id,out old)&&(preserve||ReferenceEquals(old.Key,part))?old.Value:Guid.NewGuid().ToString("N");
                modelLifetimes[part.Id]=new KeyValuePair<PartData,string>(part,token);
            }
        }
        private static string ModelContentFingerprint(PartData part)
        {
            return ModelBindingContent.Fingerprint(part.GenerateXml());
        }
        private JObject CloneModelParts(JObject op,BatchReferences refs)
        {
            int[] ids=PartIds(op["partIds"],refs);var names=op["temporaryIds"] as JArray;
            if(names==null||names.Count!=ids.Length||names.Any(x=>x.Type!=JTokenType.String||string.IsNullOrWhiteSpace((string)x))||names.Values<string>().Distinct().Count()!=names.Count)
                throw new ApiError("invalid_input","part.clone requires a unique temporaryIds string for every explicit source, in the same order.");
            foreach(string name in names.Values<string>())if(refs.ContainsKey(name))throw new ApiError("duplicate_temporary_id",name);
            var group=GroupInfo(ids);if(((JArray)group["nativeDependencies"]).Any(x=>!(bool)x["bothIncluded"]))throw new ApiError("incomplete_native_group","Copy the host and all native dependents explicitly.",group);
            var set=new HashSet<int>(ids);var sources=ids.Select(Part).ToArray();
            foreach(var p in sources){
                if(!new[]{"JFuselage-1","JFuselage-Cone-1","JFuselage-2","JWing-1","ModifierWindow-1","ControlSurface-Flap-1","ControlSurface-Flap-2","ControlSurface-Flap-3","ControlSurface-Slat-1"}.Contains(p.PartType.PartTypeId))
                    throw new ApiError("unsupported_clone","Native copy is certified for fuselages, wings, controls and Hole; other parts need a separate capability certification.");
                var target=p.GetModifier<PartTargetingData>();
                if(target!=null){var state=p.GenerateXml().Element("PartTargeting.State");
                    if(target.TargetMode.ToString()!="Custom"||ScopeState.ParseIds((string)state?.Attribute("customPartIds")).Any(id=>!set.Contains(id)))
                        throw new ApiError("incomplete_native_group","A copied cutter must explicitly include all custom target parts; automatic targeting cannot be copied safely.");
                }
            }
            var xml=Current().Aircraft.Aircraft.GenerateXml(false);var nodes=new XElement("Parts",sources.Select(p=>new XElement(p.GenerateXml())));
            foreach(var node in nodes.Elements()){node.SetAttributeValue("symmetryId",0);node.SetAttributeValue("symmetryDisabled",true);}
            var edges=new XElement("Connections",(xml.Element("Assembly")?.Element("Connections")?.Elements()??Enumerable.Empty<XElement>()).Where(e=>set.Contains((int?)e.Attribute("partA")??-1)&&set.Contains((int?)e.Attribute("partB")??-1)).Select(e=>new XElement(e)));
            var assembly=new AssemblyData(new XElement("Assembly",nodes,edges),AircraftData.CurrentXmlVersion,CraftLoadContext.Designer);
            var copied=ids.Select(id=>assembly.GetPartById(id)).ToArray();
            assembly.CreateGameObjects(Current().Aircraft,CreationInfo(),Current().Aircraft.Children);
            for(int i=0;i<copied.Length;i++){copied[i].PartScript.transform.SetPositionAndRotation(sources[i].PartScript.transform.position,sources[i].PartScript.transform.rotation);copied[i].PartScript.OnPartAdded();}
            Current().Aircraft.Aircraft.Assembly.Absorb(assembly);
            for(int i=0;i<copied.Length;i++)refs.Add((string)names[i],copied[i].Id);
            return new JObject{["kind"]="part.clone",["sourcePartIds"]=new JArray(ids),["partIds"]=new JArray(copied.Select(p=>p.Id)),["temporaryIds"]=names.DeepClone(),["externalConnections"]="detached",["symmetry"]="unlinked",["internalConnectionCount"]=edges.Elements().Count()};
        }
        private void ConfigureModelHole(XElement node,JObject op,BatchReferences refs)
        {
            if((string)node.Attribute("partType")!="ModifierWindow-1")throw new ApiError("shape_not_supported","Hole requires the native procedural window/cutter part.");
            var window=node.Element("ProceduralWindow.State");if(window==null){window=new XElement("ProceduralWindow.State");node.Add(window);}
            window.SetAttributeValue("hideGlass",true);
            if(op["size"]!=null){var size=ShapeCodec.ArrayNumbers(op["size"],3,.01,10,"Hole size metres");
                window.SetAttributeValue("upperSpan",(-size[0]/2).ToString(Inv)+","+(size[0]/2).ToString(Inv));window.SetAttributeValue("lowerSpan",(-size[0]/2).ToString(Inv)+","+(size[0]/2).ToString(Inv));
                window.SetAttributeValue("height",size[1].ToString(Inv));window.SetAttributeValue("depth",size[2].ToString(Inv));window.SetAttributeValue("penetration",.5);window.SetAttributeValue("cornerRadius",0);
            }
            if(op["targetPartIds"]!=null){int[] targets=PartIds(op["targetPartIds"],refs);foreach(int id in targets)if(Part(id).GetModifier<JFuselageData>()==null)throw new ApiError("invalid_hole_target","Hole supports explicit native fuselage targets only.");
                var target=node.Element("PartTargeting.State");if(target==null){target=new XElement("PartTargeting.State");node.Add(target);}target.SetAttributeValue("targetMode","Custom");target.SetAttributeValue("customPartIds",string.Join(",",targets));target.Attribute("partIds")?.Remove();
            }
            if(op["position"]!=null)node.SetAttributeValue("position",XmlValue(new JArray(Vec(ReadPosition(op["position"])))));
            if(op["rotationQuaternion"]!=null)node.SetAttributeValue("rotation",XmlValue(new JArray(Vec(ReadQ(op["rotationQuaternion"]).eulerAngles))));
            node.SetAttributeValue("scale","1,1,1");
        }
        private JObject ModelHole(JObject op,BatchReferences refs)
        {
            bool create=(string)op["kind"]=="hole.create";int id;
            if(create){
                if(op["size"]==null||op["targetPartIds"]==null||op["position"]==null||op["rotationQuaternion"]==null)throw new ApiError("invalid_input","hole.create requires size, explicit targets and an absolute world pose.");
                var template=FindTemplate(Required(op,"templateId"));if(!Creatable(template)||template.Name!="Hole"||template.Mod!=null)throw new ApiError("unsupported_template","Choose the builtin Hole template.");
                var assemblyXml=new XElement(template.AssemblyElement);var node=assemblyXml.Element("Parts")?.Elements("Part").Single();ConfigureModelHole(node,op,refs);
                var assembly=new AssemblyData(assemblyXml,AircraftData.CurrentXmlVersion,CraftLoadContext.Designer);var part=assembly.Parts.Single();
                assembly.CreateGameObjects(Current().Aircraft,CreationInfo(),Current().Aircraft.Children);Current().Aircraft.Aircraft.Assembly.Absorb(assembly);id=part.Id;
                string temporary=Required(op,"temporaryId");refs.Add(temporary,id);part.PartScript.transform.SetPositionAndRotation(ReadPosition(op["position"]),ReadQ(op["rotationQuaternion"]));part.PartScript.OnPartAdded();
            }else{
                id=refs.Resolve(op["partId"]);var xml=Current().Aircraft.Aircraft.GenerateXml(false);ConfigureModelHole(XmlPart(xml,id),op,refs);Replace(xml);
            }
            return new JObject{["kind"]=(string)op["kind"],["partId"]=id,["targeting"]=Node(Part(id).GenerateXml().Element("PartTargeting.State")),["effectiveShape"]=Node(Part(id).GenerateXml().Element("ProceduralWindow.State")),["position"]=new JArray(Vec(Part(id).PartScript.transform.position)),["rotationQuaternion"]=PropertyValues.Read(Part(id).PartScript.transform.rotation)};
        }
    }
}
