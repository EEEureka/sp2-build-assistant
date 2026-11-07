using System;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;

namespace SP2BuildAssistant
{
    // Binding evidence only. Atomic revision and outside-scope guards retain
    // their exact authored XML policy. The native loader omits identity scale.
    internal static class ModelBindingContent
    {
        internal const string Algorithm="part-content-native-default-scale-v1";
        internal static string Fingerprint(XElement part)
        {
            var copy=new XElement(part);
            foreach(string key in new[]{"id","position","rotation"})copy.Attribute(key)?.Remove();
            var attribute=copy.Attribute("scale");
            if(attribute!=null){
                var values=attribute.Value.Split(',');double number;
                if(values.Length==3&&values.All(value=>double.TryParse(value,NumberStyles.Float,CultureInfo.InvariantCulture,out number)&&number==1))attribute.Remove();
            }
            return SnapshotState.Fingerprint(copy);
        }
    }
}
