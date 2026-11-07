using System;
using System.Collections.Generic;
using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Design.Symmetry;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        // Uses native modifier mirror hooks, rather than assuming a reflected
        // transform also mirrors a wing, asymmetric section, cutter or input.
        private JObject MirrorModelParts(JObject op, BatchReferences refs)
        {
            int[] ids = PartIds(op["partIds"], refs);
            var names = op["temporaryIds"] as JArray;
            if (names == null || names.Count != ids.Length || names.Any(x => x.Type != JTokenType.String || string.IsNullOrWhiteSpace((string)x)) || names.Values<string>().Distinct().Count() != names.Count)
                throw new ApiError("invalid_input", "part.mirror requires one unique temporaryIds string for every explicit source, in source order.");
            if (op["linked"]?.Type != JTokenType.Boolean)
                throw new ApiError("invalid_input", "part.mirror linked must be an explicit boolean.");
            foreach (string name in names.Values<string>())
                if (refs.ContainsKey(name)) throw new ApiError("duplicate_temporary_id", name);
            bool linked = (bool)op["linked"];
            var symmetry = EffectiveSymmetryConfig();
            if (symmetry.Mode != SymmetryMode.Mirrored)
                throw new ApiError("invalid_symmetry", "Group mirror requires the designer's Mirrored mode and its reviewed effective plane.");
            var group = GroupInfo(ids);
            if (((JArray)group["nativeDependencies"]).Any(x => !(bool)x["bothIncluded"]))
                throw new ApiError("incomplete_native_group", "Include the host and all native dependents explicitly before mirroring.", group);
            var sources = ids.Select(Part).ToArray();
            var set = new HashSet<int>(ids);
            var poses = new Dictionary<int, SymmetryTransform>();
            foreach (var source in sources)
            {
                if (source.SymmetryId != 0)
                    throw new ApiError("invalid_symmetry", "Mirror sources must be unlinked; unlink their existing symmetry groups explicitly first.");
                if (!new[] { "JFuselage-1", "JFuselage-Cone-1", "JFuselage-2", "JWing-1", "ModifierWindow-1", "ControlSurface-Flap-1", "ControlSurface-Flap-2", "ControlSurface-Flap-3", "ControlSurface-Slat-1" }.Contains(source.PartType.PartTypeId))
                    throw new ApiError("unsupported_mirror", "Group mirror supports native fuselages, wings, controls and explicit-target Hole parts.");
                var targeting = source.GetModifier<PartTargetingData>();
                if (targeting != null)
                {
                    var state = source.GenerateXml().Element("PartTargeting.State");
                    if (targeting.TargetMode.ToString() != "Custom" || ScopeState.ParseIds((string)state?.Attribute("customPartIds")).Any(id => !set.Contains(id)))
                        throw new ApiError("incomplete_native_group", "A mirrored cutter must explicitly include every custom target; automatic targeting cannot be mirrored safely.");
                }
                var transforms = new List<SymmetryTransform>();
                SymmetryUtility.GetSymmetricTransforms(source, symmetry, transforms);
                if (transforms.Count != 1) throw new ApiError("invalid_symmetry", "Expected exactly one native mirrored transform per source.");
                poses.Add(source.Id, transforms[0]);
            }
            // Capture directed pairs before creating any native objects. External
            // connections are deliberately excluded from the new assembly.
            var edges = sources.SelectMany(p => p.PartConnections).Distinct()
                .Where(c => set.Contains(c.PartA.Id) && set.Contains(c.PartB.Id)).ToArray();
            var copied = new Dictionary<int, PartData>();
            foreach (var source in sources)
            {
                var part = SymmetryUtility.DuplicatePart(source, true);
                part.SymmetryDisabled = true;
                var pose = poses[source.Id];
                part.PartScript.transform.SetPositionAndRotation(pose.Position, pose.Rotation);
                copied.Add(source.Id, part);
            }
            var idMap = copied.ToDictionary(pair => pair.Key, pair => pair.Value.Id);
            foreach (var part in copied.Values)
                foreach (var modifier in part.Modifiers)
                    if (modifier is IPartIDChangedListener listener) listener.OnPartIDsRemapped(idMap);
            SymmetryUtility.RegenerateUniqueGroupIds(copied.Values);
            var mirroredFuselages = copied.Values.Where(p => p.GetModifier<JFuselageData>() != null)
                .ToDictionary(p => p, p => new XElement(p.GenerateXml().Element("JFuselage.State")));

            // Connection callbacks are needed for the native Wing/control host
            // relationship. Temporarily suppress resize, which would otherwise
            // change the geometry being copied while rebuilding old edges.
            var resize = copied.Values.Select(p => p.GetModifier<JFuselageData>()).Where(f => f != null)
                .ToDictionary(f => f, f => f.AutoResizeOnConnected);
            foreach (var fuselage in resize.Keys) fuselage.AutoResizeOnConnected = false;
            int pairCount = 0;
            try
            {
                foreach (var edge in edges)
                {
                    if (edge.AttachPointsA.Count != edge.AttachPointsB.Count)
                        throw new ApiError("invalid_connection", "Source connection has an unequal attachment pair count.");
                    var a = copied[edge.PartA.Id]; var b = copied[edge.PartB.Id];
                    for (int i = 0; i < edge.AttachPointsA.Count; i++)
                    {
                        var ap = MirroredModelAttachPoint(edge.AttachPointsA[i], a, symmetry);
                        var bp = MirroredModelAttachPoint(edge.AttachPointsB[i], b, symmetry);
                        a.PartScript.ConnectToPart(ap.AttachPointScript, bp.AttachPointScript, true);
                        pairCount++;
                    }
                }
            }
            finally
            {
                foreach (var entry in resize) entry.Key.AutoResizeOnConnected = entry.Value;
            }
            foreach (var entry in mirroredFuselages)
                if (!XNode.DeepEquals(entry.Value, entry.Key.GenerateXml().Element("JFuselage.State")))
                    throw new ApiError("mirror_geometry_mismatch", "Native connection callbacks changed a mirrored fuselage shape; the transaction must be rolled back.");
            foreach (var source in sources)
            {
                var part = copied[source.Id];
                var control = part.GetModifier<ControlSurfacePartData>();
                if (control != null)
                {
                    var wing = control.GetFirstConnectedWing();
                    if (wing == null || !copied.Values.Contains(wing.Part))
                        throw new ApiError("incomplete_native_group", "Mirrored control surface did not attach to its copied wing.");
                    control.UpdateDummyWingParams(wing);
                    control.UpdateMeshes(false);
                    wingsToValidate.Add(wing.Part.Id);
                }
                var pose = poses[source.Id];
                if (Vector3.Distance(part.PartScript.transform.position, pose.Position) > .001f || Quaternion.Angle(part.PartScript.transform.rotation, pose.Rotation) > .1f)
                    throw new ApiError("mirror_geometry_mismatch", "Native connection callbacks moved a mirrored part; the transaction must be rolled back.");
                // The normal post-settle guard enforces the same strict pose
                // contract as explicit transforms, after native mesh callbacks.
                requiredPoses[part.Id] = new Pose(pose.Position, pose.Rotation);
                if (linked)
                {
                    Current().Aircraft.Aircraft.Assembly.LinkSymmetricParts(new List<PartData> { source, part }, true);
                    if (source.SymmetryId == 0 || source.SymmetryId != part.SymmetryId)
                        throw new ApiError("symmetry_rejected", "Native linking of a mirrored pair did not take effect.");
                }
            }
            for (int i = 0; i < ids.Length; i++) refs.Add((string)names[i], copied[ids[i]].Id);
            return new JObject
            {
                ["kind"] = "part.mirror", ["sourcePartIds"] = new JArray(ids),
                ["partIds"] = new JArray(ids.Select(id => copied[id].Id)), ["temporaryIds"] = names.DeepClone(),
                ["linked"] = linked, ["externalConnections"] = "detached", ["internalConnectionCount"] = edges.Length,
                ["internalAttachmentPairCount"] = pairCount, ["mirrorFrame"] = SymmetryFrame(symmetry)
            };
        }

        private static AttachPointData MirroredModelAttachPoint(AttachPointData source, PartData mirrored, SymmetryConfig symmetry)
        {
            // Native explicit MirrorId has priority over geometric coincidence.
            if (source.MirrorId >= 0)
            {
                var explicitPoint = mirrored.AttachPoints.SingleOrDefault(p => p.Id == source.MirrorId);
                if (explicitPoint != null) return explicitPoint;
            }
            var matches = mirrored.AttachPoints.Where(p => SymmetryUtility.IsSymmetricAttachPoint(source, p, 1, symmetry)).ToArray();
            if (matches.Length != 1)
                throw new ApiError("binding_ambiguous", "A mirrored attachment has no unique native mapping; refusing to invent a connection.");
            return matches[0];
        }
    }
}
