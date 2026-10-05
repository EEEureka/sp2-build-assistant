using System;
using System.Collections.Generic;
using System.Linq;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    internal static class CraftDiff
    {
        private static void Flatten(XElement e,string path,Dictionary<string,string> fields)
        {
            foreach(var a in e.Attributes()) {
                string value=a.Value;
                if(e.Name.LocalName=="PartTargeting.State"&&a.Name.LocalName=="partIds"&&(string)e.Attribute("targetMode")!="Custom")
                    value=string.Join(",",value.Split(',').Where(x=>x.Length>0).Distinct().OrderBy(x=>x,StringComparer.Ordinal));
                fields[path+"/@"+a.Name]=value;
            }
            if(!e.HasElements&&!string.IsNullOrWhiteSpace(e.Value)) fields[path+"/#text"]=e.Value;
            var counts=new Dictionary<string,int>();
            foreach(var c in e.Elements()) {
                string name=c.Name.ToString(); int index=counts.ContainsKey(name)?counts[name]:0; counts[name]=index+1;
                string key=name=="Part"&&c.Attribute("id")!=null?"id="+(string)c.Attribute("id"):index.ToString();
                Flatten(c,path+"/"+name+"["+key+"]",fields);
            }
        }
        internal static JObject Compare(XElement before,XElement after,int limit=1000)
        {
            var a=new Dictionary<string,string>();var b=new Dictionary<string,string>();
            Flatten(before,"Aircraft",a);Flatten(after,"Aircraft",b);
            var keys=a.Keys.Union(b.Keys).Where(k=>!a.ContainsKey(k)||!b.ContainsKey(k)||a[k]!=b[k]).OrderBy(k=>k,StringComparer.Ordinal).ToArray();
            return new JObject{["totalChanges"]=keys.Length,["truncated"]=keys.Length>limit,["comparison"]="Exact serialized fields, except generated targeting sets; all ordered lists remain ordered.",
                ["changes"]=new JArray(keys.Take(limit).Select(k=>new JObject{["path"]=k,["before"]=a.ContainsKey(k)?a[k]:null,["after"]=b.ContainsKey(k)?b[k]:null}))};
        }
    }
}
