using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Craft;
using Assets.Scripts.Craft.Parts.Modifiers;
using UnityEngine;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private static void RetainSerializedScales(AircraftData data, XElement requested)
        {
            // The native loader drops explicit near-unit scales using Vector3's
            // approximate equality. Keep both the presence and exact float values
            // before creating geometry; checkpoint validation remains strict.
            foreach (var node in requested.Element("Assembly").Element("Parts").Elements("Part"))
            {
                var attribute = node.Attribute("scale");
                if (attribute == null) continue;
                var values = attribute.Value.Split(',').Select(x => float.Parse(x, CultureInfo.InvariantCulture)).ToArray();
                if (values.Length != 3) throw new ApiError("invalid_scale", "Serialized part scale must have three components.");
                var part = data.Assembly.GetPartById((int)node.Attribute("id"));
                if (part == null) continue;
                bool loaderOmittedScale = !part.PartScale.HasValue;
                part.PartScale = new Vector3(values[0], values[1], values[2]);
                if (loaderOmittedScale)
                {
                    // These native adapters derive their UI size/radius during
                    // RestoreFromState, before scripts are created. Re-derive
                    // against the preserved scale rather than exposing stale 1s.
                    foreach (var modifier in part.Modifiers)
                        if (modifier is PistonData || modifier is JointRotatorData || modifier is SuspensionData ||
                            modifier is DetacherData || modifier is BeaconLightData || modifier is LandingGearData)
                            modifier.RestoreFromState(modifier.GenerateStateXml());
                }
            }
        }
        private sealed class SavedRotation {
            public string Type, Euler, SerializedPosition;
            public Quaternion Rotation;
            public Vector3 Position;
            public bool KeepRotation=true, KeepPosition=true;
        }
        private readonly Dictionary<string,Dictionary<int,SavedRotation>> nativeRotations = new Dictionary<string,Dictionary<int,SavedRotation>>();
        private void RememberRotations(XElement xml,string knownHash=null)
        {
            string hash=knownHash??SnapshotState.Fingerprint(xml);
            if(nativeRotations.ContainsKey(hash)) return;
            if(nativeRotations.Count>=128){
                // Session checkpoints must retain their exact native quaternion even
                // after hundreds of intermediate observations (Euler is not lossless).
                var pinned=new HashSet<string>(checkpoints.Values.Select(SnapshotState.Fingerprint));
                string evict=nativeRotations.Keys.FirstOrDefault(k=>!pinned.Contains(k));
                if(evict!=null)nativeRotations.Remove(evict);
            }
            var parts=Current().Aircraft.Aircraft.Assembly.Parts.ToDictionary(p=>p.Id);
            var values=new Dictionary<int,SavedRotation>();
            foreach(var p in xml.Element("Assembly").Element("Parts").Elements("Part")) {
                int id=(int)p.Attribute("id");
                if(parts.ContainsKey(id)) values[id]=new SavedRotation{Type=(string)p.Attribute("partType"),Euler=(string)p.Attribute("rotation"),SerializedPosition=(string)p.Attribute("position"),Rotation=parts[id].PartScript.transform.rotation,Position=parts[id].PartScript.transform.position};
            }
            nativeRotations[hash]=values;
        }
        private Dictionary<int,SavedRotation> RetainedRotations(XElement requested)
        {
            var current=Current().Aircraft.Aircraft.GenerateXml(false); RememberRotations(current);
            Dictionary<int,SavedRotation> values;
            if(nativeRotations.TryGetValue(SnapshotState.Fingerprint(requested),out values)) return values;
            // XML's decimal positions are also lossy. Rounding a gear host by
            // one float ULP can change its animated wheel's serialized position
            // after every rebuild. Retain the actual trusted source pose, not
            // a tolerance in snapshot validation. Each explicitly edited pose
            // channel independently goes through the native loader.
            values=nativeRotations[SnapshotState.Fingerprint(current)];
            return requested.Element("Assembly").Element("Parts").Elements("Part")
                .Where(p=>values.ContainsKey((int)p.Attribute("id")) && values[(int)p.Attribute("id")].Type==(string)p.Attribute("partType"))
                .ToDictionary(p=>(int)p.Attribute("id"),p=>{
                    var v=values[(int)p.Attribute("id")];
                    return new SavedRotation{Type=v.Type,Euler=v.Euler,SerializedPosition=v.SerializedPosition,Rotation=v.Rotation,Position=v.Position,
                        KeepRotation=v.Euler==(string)p.Attribute("rotation"),KeepPosition=v.SerializedPosition==(string)p.Attribute("position")};
                });
        }
        private static void RestoreNativeRotations(AircraftScript aircraft,Dictionary<int,SavedRotation> values)
        {
            foreach(var p in aircraft.Aircraft.Assembly.Parts) {
                SavedRotation value;
                if(values.TryGetValue(p.Id,out value) && value.Type==p.PartType.PartTypeId) {
                    if(value.KeepPosition)p.PartScript.transform.position=value.Position;
                    if(value.KeepRotation)p.PartScript.transform.rotation=value.Rotation;
                }
            }
        }
    }
}
