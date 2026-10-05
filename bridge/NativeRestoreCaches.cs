using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Xml.Linq;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Design;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private readonly JArray retainedRestoreCaches=new JArray();
        private bool RetainNativeRestoreCaches(Designer designer,XElement expected,XElement regenerated)
        {
            var plan=NativeRestoreCachePlan.Create(expected,regenerated);
            if(plan==null)return false;
            var com=typeof(JFuselageData).GetField("_com",BindingFlags.Instance|BindingFlags.NonPublic);
            var mass=typeof(JFuselageData).GetField("_mass",BindingFlags.Instance|BindingFlags.NonPublic);
            if(com==null || mass==null)return false;
            var targets=new List<JFuselageData>();
            foreach(var e in plan)
            {
                var part=designer.Aircraft.Aircraft.Assembly.GetPartById(e.PartId);
                var modifiers=part?.Modifiers.OfType<JFuselageData>().ToArray();
                if(modifiers==null || e.ModifierIndex>=modifiers.Length)return false;
                targets.Add(modifiers[e.ModifierIndex]);
            }
            for(int i=0;i<plan.Count;i++)
            {
                var e=plan[i];var v=e.Values;
                com.SetValue(targets[i],new Unity.Mathematics.float3(v[0],v[1],v[2])); mass.SetValue(targets[i],v[3]);
                retainedRestoreCaches.Add(new JObject{["partId"]=e.PartId,["modifierIndex"]=e.ModifierIndex,["field"]="JFuselage.State.mass",
                    ["checkpointValue"]=e.Expected,["regeneratedValue"]=e.Regenerated,
                    ["meaning"]="Exact trusted checkpoint center/mass cache retained after bounded native regeneration drift; all other state must already match. Final restore validation remains exact except documented Euler reconstruction."});
            }
            designer.SetAircraftStructureChanged(); return true;
        }
    }
}
