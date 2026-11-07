using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Design;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        // A newly reconstructed fuselage has no previous LateUpdate pose. A
        // subsequent in-place move in the same batch can therefore miss the
        // native pose-change invalidation. Refresh only after native targeting
        // and final transforms have settled, before accepting the operation.
        private static JArray RefreshMovedCarverTargets(Designer designer, XElement before)
        {
            var oldParts = before == null ? null : before.Descendants("Part")
                .Where(p => p.Attribute("id") != null).ToDictionary(p => (int)p.Attribute("id"));
            var current = designer.Aircraft.Aircraft.GenerateXml(false).Descendants("Part")
                .Where(p => p.Attribute("id") != null).ToDictionary(p => (int)p.Attribute("id"));
            System.Func<int, bool> changed = id => {
                XElement old, now;
                if (oldParts == null || !oldParts.TryGetValue(id, out old) || !current.TryGetValue(id, out now)) return true;
                // Include shape/targeting changes as well as final pose. A
                // move -> rebuild -> move-back batch has no net pose delta,
                // but its Boolean mesh can still be built in the intermediate
                // frame before the fresh native script gets a previous pose.
                return !XNode.DeepEquals(old, now);
            };
            var refreshed = new JArray();
            foreach (var part in designer.Aircraft.Aircraft.Assembly.Parts)
            {
                var target = part.PartScript.GetModifier<JFuselageScript>();
                if (target == null || target.MeshModifiers.Count == 0) continue;
                var modifiers = target.MeshModifiers.Where(m => m != null).ToArray();
                if (!changed(part.Id) && !modifiers.Any(m => changed(m.PartScript.Part.Id))) continue;
                target.RaiseMeshModifierChanged();
                refreshed.Add(new JObject { ["partId"] = part.Id,
                    ["modifierPartIds"] = new JArray(modifiers.Select(m => m.PartScript.Part.Id)),
                    ["reason"] = "final_pose_native_modifier_invalidation" });
            }
            return refreshed;
        }
    }
}
