using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Design;
using Assets.Scripts.Design.UI.PartProperties;
using Newtonsoft.Json.Linq;
using UnityEngine;
using AssemblyData = Assets.Scripts.Craft.Parts.Assembly;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private int? retainedSelection;
        private bool selectionCaptured;
        private void CaptureSelection(Designer d)
        {
            if (selectionCaptured) return;
            retainedSelection = d.SelectedPart == null ? (int?)null : d.SelectedPart.Part.Id;
            selectionCaptured = true;
        }
        private void RestoreSelection(Designer d)
        {
            if (!selectionCaptured) return;
            d.SelectedPart = retainedSelection.HasValue ? d.Aircraft.Aircraft.Assembly.Parts.FirstOrDefault(p => p.Id == retainedSelection.Value)?.PartScript : null;
        }
        private static void RefreshSelectedPropertyWidgets(Designer d)
        {
            // In-place native setters leave the selected PartScript unchanged, so
            // the panel's selection-change loop does not schedule a refresh.
            // Rebuilt parts are rebound by the native panel on its next Update.
            if (d.SelectedPart == null) return;
            foreach (var modifier in d.SelectedPart.Part.Modifiers)
            {
                var ui = PartPropertiesPanelScript.GetPropertiesByType(modifier.GetType());
                if (ui == null || !ui.gameObject.activeInHierarchy || !ReferenceEquals(ui.CurrentPartModifier, modifier)) continue;
                ui.OnPropertiesOpened();
                ui.RefreshUI();
            }
            PartPropertiesPanelScript.RefreshSectionVisibility();
        }
        private static object PrivateField(object target, string field)
        {
            string key=target.GetType().FullName+":"+field;FieldInfo f;
            if(!privateFields.TryGetValue(key,out f)){
                for(Type type=target.GetType();type!=null&&f==null;type=type.BaseType)
                    f=type.GetField(field,BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.DeclaredOnly);
                if(f!=null)privateFields[key]=f;
            }
            if (f == null) throw new ApiError("game_version_unsupported", "Missing native geometry field: " + field);
            return f.GetValue(target);
        }
        private static readonly System.Collections.Generic.Dictionary<string,FieldInfo> privateFields=new System.Collections.Generic.Dictionary<string,FieldInfo>();
        [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Explicit)]
        private struct FloatWord { [System.Runtime.InteropServices.FieldOffset(0)] public float F; [System.Runtime.InteropServices.FieldOffset(0)] public uint U; }
        private static bool GeometryPending(Designer d)
        {
            foreach (var part in d.Aircraft.Aircraft.Assembly.Parts)
            {
                var wing = part.GetModifier<JWingData>();
                if (wing != null && wing.FailedGeneration) throw new ApiError("invalid_wing_geometry", "Native wing generation failed for part " + part.Id);
                foreach (var script in part.PartScript.GetComponentsInChildren<JFuselageScript>())
                    if (PrivateField(script, "_colliderBake") != null || PrivateField(script, "_bakingColliders") != null) return true;
            }
            var queueField = typeof(JFuselageScript).GetField("_suspendedChangeQueue", BindingFlags.Static | BindingFlags.NonPublic);
            if (queueField == null) throw new ApiError("game_version_unsupported", "Missing native fuselage generation queue.");
            var queue = (IDictionary)queueField.GetValue(null);
            return queue.Keys.Cast<JFuselageScript>().Any(s => s != null && s.transform.IsChildOf(d.Aircraft.transform));
        }
        private static string GeometrySignature(Designer d)
        {
            // Scan the hierarchy once. Float bit hashing avoids thousands of
            // culture-formatted bounds strings and preserves more precision.
            ulong hash=14695981039346656037UL;
            Action<uint> add=v=>{unchecked{hash=(hash^v)*1099511628211UL;}};
            Action<Vector3> vector=v=>{add(new FloatWord{F=v.x}.U);add(new FloatWord{F=v.y}.U);add(new FloatWord{F=v.z}.U);};
            Action<Bounds> bounds=b=>{vector(b.center);vector(b.size);};
            foreach(var m in d.Aircraft.GetComponentsInChildren<MeshFilter>())if(m.sharedMesh!=null){add((uint)m.GetInstanceID());add((uint)m.sharedMesh.GetInstanceID());add((uint)m.sharedMesh.vertexCount);bounds(m.sharedMesh.bounds);}
            foreach(var c in d.Aircraft.GetComponentsInChildren<Collider>())if(c.enabled){add((uint)c.GetInstanceID());bounds(c.bounds);}
            return hash.ToString("x16");
        }
        private static void RefreshEditorGeometry(Designer d)
        {
            if (GeometryPending(d)) throw new ApiError("geometry_pending", "Cannot refresh while native geometry jobs are active.");
            foreach (var meshCollider in d.Aircraft.GetComponentsInChildren<MeshCollider>())
            {
                var mesh = meshCollider.sharedMesh;
                if (mesh == null) continue;
                // Reassigning the same Mesh reference may retain a PhysX cooked shape.
                meshCollider.sharedMesh = null;
                meshCollider.sharedMesh = mesh;
            }
            Physics.SyncTransforms();
            EditorCollider.GlobalUpdateId++;
            foreach (var p in d.Aircraft.Aircraft.Assembly.Parts)
            {
                AssemblyData.CreateEditorCollidersForPartScript(p.PartScript);
                foreach (var c in p.PartScript.EditorColliders) c.Update();
            }
        }
        private static JObject BoundsInfo(Bounds bounds)
        { return new JObject { ["center"] = new JArray(Vec(bounds.center)), ["size"] = new JArray(Vec(bounds.size)), ["min"] = new JArray(Vec(bounds.min)), ["max"] = new JArray(Vec(bounds.max)) }; }
        private static JObject GeometryInfo(PartData p)
        {
            var script = p.PartScript;
            return new JObject {
                ["partId"] = p.Id, ["coordinateSystem"] = "world metres",
                ["renderers"] = new JArray(script.GetComponentsInChildren<Renderer>().Where(r => r.enabled).Select(r => new JObject { ["name"] = r.name, ["bounds"] = BoundsInfo(r.bounds) })),
                ["colliders"] = new JArray(script.GetComponentsInChildren<Collider>().Where(c => c.enabled && !c.isTrigger && c.gameObject.layer != 25).Select(c => new JObject { ["name"] = c.name, ["type"] = c.GetType().Name, ["layer"] = c.gameObject.layer, ["bounds"] = BoundsInfo(c.bounds) })),
                ["editorColliders"] = new JArray(script.EditorColliders.Select(c => new JObject { ["bounds"] = BoundsInfo(c.Bounds), ["includeInBounds"] = c.IncludeInBounds }))
            };
        }
        private object Raycast(JObject a)
        {
            var origin = Vector(a["origin"], Vector3.zero); var direction = Vector(a["direction"], Vector3.zero);
            if (direction.sqrMagnitude < 0.000001f) throw new ApiError("invalid_direction", "Ray direction cannot be zero.");
            float distance = a.Value<float?>("distance") ?? 10000f;
            if (float.IsNaN(distance) || float.IsInfinity(distance) || distance <= 0 || distance > 100000) throw new ApiError("invalid_distance", "distance must be in (0,100000].");
            Physics.SyncTransforms();
            return new { identity = Identity(), query = new { origin = Vec(origin), direction = Vec(direction.normalized), distanceMetres = distance,
                    mode = "all_collider_hits", order = "distance_ascending", deduplicatedByPart = false, truncated = false,
                    coordinateSystem = "Unity world; metres", filters = "current aircraft; interactable parts; non-trigger colliders; exclude layer 25",
                    meaning = "Multiple colliders can hit the same part. Ray intersections do not establish physical support. Unity raycasts may omit colliders containing the ray origin." },
                hits = new JArray(Physics.RaycastAll(origin, direction.normalized, distance, ~0, QueryTriggerInteraction.Ignore)
                .OrderBy(h => h.distance).Select(h => new { hit = h, part = h.collider.GetComponentInParent<PartScript>() })
                .Where(x => x.part != null && x.part.Aircraft == Current().Aircraft && x.part.IsInteractable && x.hit.collider.gameObject.layer != 25)
                .Select(x => new JObject { ["partId"] = x.part.Part.Id, ["part"] = PartSummary(x.part.Part), ["distance"] = x.hit.distance, ["point"] = new JArray(Vec(x.hit.point)), ["normal"] = new JArray(Vec(x.hit.normal)) })) };
        }
    }
}
