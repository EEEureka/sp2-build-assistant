using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;

namespace SP2BuildAssistant
{
    // Bounds permit exact cache retention, not weaker final validation.
    public static class NativeRestoreCachePlan
    {
        public const double CenterGateMetres = 0.0000001;
        public const double MassGateNativeUnits = 0.000001;
        public sealed class Entry
        {
            public int PartId, ModifierIndex;
            public string Expected, Regenerated;
            public float[] Values;
        }
        public static List<Entry> Create(XElement expected, XElement actual)
        {
            var plan = new List<Entry>(); var copy = new XElement(actual);
            var ep = expected.Element("Assembly")?.Element("Parts");
            var ap = copy.Element("Assembly")?.Element("Parts");
            if(ep == null || ap == null) return null;
            foreach(var part in ep.Elements("Part"))
            {
                int id; if(!int.TryParse((string)part.Attribute("id"),out id)) return null;
                var candidates=ap.Elements("Part").Where(p=>(string)p.Attribute("id")==id.ToString(CultureInfo.InvariantCulture)).ToArray();
                if(candidates.Length!=1) return null;
                var wanted=part.Elements("JFuselage.State").ToArray();
                var regenerated=candidates[0].Elements("JFuselage.State").ToArray();
                if(wanted.Length!=regenerated.Length) return null;
                for(int index=0;index<wanted.Length;index++)
                {
                    string a=(string)wanted[index].Attribute("mass"), b=(string)regenerated[index].Attribute("mass");
                    if(a==b) continue;
                    float[] av,bv; if(!Parse(a,out av) || !Parse(b,out bv)) return null;
                    for(int k=0;k<4;k++) if(Math.Abs((double)av[k]-bv[k])>(k==3?MassGateNativeUnits:CenterGateMetres))return null;
                    plan.Add(new Entry{PartId=id,ModifierIndex=index,Expected=a,Regenerated=b,Values=av});
                    regenerated[index].SetAttributeValue("mass",a);
                }
            }
            // No configuration, pose, target, connection, fuel or other cache
            // difference may be hidden by this plan.
            return plan.Count>0 && SnapshotState.EquivalentAfterNativeRestore(expected,copy)?plan:null;
        }
        private static bool Parse(string value,out float[] parsed)
        {
            parsed=null;if(value==null)return false;
            string[] pieces=value.Split(',');if(pieces.Length!=4)return false;
            var result=new float[4];
            for(int i=0;i<4;i++)if(!float.TryParse(pieces[i],NumberStyles.Float,CultureInfo.InvariantCulture,out result[i])||float.IsNaN(result[i])||float.IsInfinity(result[i]))return false;
            if(result[3]<0)return false;
            parsed=result;return true;
        }
    }
}
