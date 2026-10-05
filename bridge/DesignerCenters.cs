using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using Assets.Scripts;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Parts.Modifiers.Propulsion.Jet;
using Assets.Scripts.Craft.Parts.Modifiers.Propulsion.Propeller;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine;
using ModernJet = Assets.Scripts.Craft.Parts.Modifiers.Propulsion.Jet.JetEngineScript;
using LegacyJet = Assets.Scripts.Craft.Parts.Modifiers.JetEngineScript;
using SP2Game = Assets.Scripts.Game;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private sealed class CenterReference { internal readonly string Token = Guid.NewGuid().ToString("N"); }
        private readonly ConditionalWeakTable<PartData, CenterReference> centerReferences = new ConditionalWeakTable<PartData, CenterReference>();
        private static JArray CenterVec(Vector3 v) { return new JArray(v.x, v.y, v.z); }
        private static JArray CenterRotation(Quaternion q) { return new JArray(q.x, q.y, q.z, q.w); }
        private static void CenterOptions(JObject a)
        {
            VisualScope.Keys(a,"craftSessionId","expectedRevision","detail","metric","focus","focusSelector","limit","offset","frame","images","resolution","baseline");
            string detail = VisualScope.String(a["detail"], "detail", "summary"), metric = VisualScope.String(a["metric"], "metric", "all"), focus = VisualScope.String(a["focus"], "focus", "all");
            if (detail != "summary" && detail != "contributors") throw new ApiError("invalid_input", "detail must be summary or contributors.");
            if (!new[] { "all", "mass", "lift", "thrust" }.Contains(metric)) throw new ApiError("invalid_input", "metric must be all, mass, lift or thrust.");
            if (focus != "all" && focus != "selected") throw new ApiError("invalid_input", "focus must be all or selected; use focusSelector for explicit parts/assembly.");
            if (a["focusSelector"] != null && a["focus"] != null) throw new ApiError("invalid_input", "Specify focus or focusSelector, not both.");
            if (a["focusSelector"] != null && !(a["focusSelector"] is JObject)) throw new ApiError("invalid_input", "focusSelector must be an object.");
            if (a["baseline"] != null && !(a["baseline"] is JObject)) throw new ApiError("invalid_input", "CLI must load baseline as a validated centers report.");
            if (a["limit"] != null) VisualScope.Integer(a["limit"], "limit", 1, 200);
            if (a["offset"] != null) VisualScope.Integer(a["offset"], "offset", 0);
            VisualScope.Boolean(a["images"], "images");
            if (a["resolution"] != null) { var res = a["resolution"] as JObject; VisualScope.Keys(res,"width","height"); foreach (string key in new[]{"width","height"}) if(res[key]!=null) VisualScope.Integer(res[key],key,384,1024); }
        }
        private async UniTask<JObject> CraftCenters(JObject args, Job job)
        {
            CenterOptions(args); Observe();
            var guard = new JObject { ["craftSessionId"] = args["craftSessionId"] ?? session, ["expectedRevision"] = args["expectedRevision"] ?? revision };
            VisualGuard(guard);
            if (VisualScope.Boolean(args["images"], "images"))
            {
                var visual = (JObject)guard.DeepClone();
                visual["groups"] = new JArray(new JObject { ["name"] = "aircraft", ["selector"] = new JObject { ["kind"] = "craft" } });
                visual["views"] = new JArray("right", "top", "front"); visual["details"] = "none";
                if (args["frame"] != null) visual["frame"] = args["frame"].DeepClone();
                if (args["resolution"] != null) visual["resolution"] = args["resolution"].DeepClone();
                var capture = await VisualCapture(visual, job, args);
                var report = (JObject)capture["centersReport"].DeepClone(); capture.Remove("centersReport");
                report["visual"] = capture; report["staleAtDelivery"] = capture["staleAtDelivery"].DeepClone(); return report;
            }
            var d = Current(); await ReadSettled(d, null); Observe(); VisualGuard(guard);
            lock (job.Sync) if (job.CancelRequested) throw new ApiError("cancelled", "Centers request cancelled.");
            var result = CollectCenters(args);
            Observe(); VisualGuard(guard); return result;
        }
        private JObject CollectCenters(JObject options)
        {
            CenterOptions(options); var d = Current(); var aircraft = d.Aircraft;
            var all = aircraft.Aircraft.Assembly.Parts.ToArray(); var connected = aircraft.Parts.ToArray(); var set = new HashSet<int>(connected.Select(p => p.Id));
            var frame = options["frame"] as JObject ?? (options["frame"] == null ? new JObject { ["kind"] = "world" } : null);
            VisualScope.Keys(frame, "kind", "partId"); string kind = VisualScope.String(frame["kind"], "frame.kind");
            var matrix = Matrix4x4.identity; var frameInfo = new JObject { ["kind"] = kind, ["partId"] = null, ["referenceToken"] = null, ["orientationWorld"] = CenterRotation(Quaternion.identity) };
            if (kind == "part")
            {
                var p = Part(VisualScope.Integer(frame["partId"], "frame.partId")); var t = p.PartScript.transform;
                matrix = Matrix4x4.TRS(t.position, t.rotation, Vector3.one);
                frameInfo["partId"] = p.Id; frameInfo["referencePart"] = PartSummary(p); frameInfo["referenceToken"] = centerReferences.GetValue(p, _ => new CenterReference()).Token;
                frameInfo["orientationWorld"] = CenterRotation(t.rotation);
            }
            else if (kind != "world" || frame["partId"] != null) throw new ApiError("invalid_input", "frame must be world or part with partId.");
            frameInfo["frameToWorldRows"] = MatrixRows(matrix); frameInfo["axisLabels"] = new JArray("right", "up", "forward");
            frameInfo["orientationBasis"] = kind == "world" ? "designer_world_axis_convention" : "reference_part_local_axis_convention";
            frameInfo["meaning"] = "+X right, +Y up, +Z forward by coordinate convention only; aircraft nose direction is not inferred. Reference scale is ignored.";
            var inverse = matrix.inverse; var rows = new JArray(); var warnings = new JArray();
            int[] focusIds = null; string focusStatus = "all";
            if (options["focusSelector"] is JObject selector)
            {
                string selectorKind = (string)selector["kind"];
                if (selectorKind != "parts" && selectorKind != "assembly") throw new ApiError("invalid_input", "focusSelector supports parts or native assembly only.");
                focusIds = VisualScope.Resolve(selector, new HashSet<int>(all.Select(p => p.Id)), new VisualScope.Edge[0], null, VisualAssembly, 2048); focusStatus = "explicit";
            }
            else if ((string)options["focus"] == "selected") { focusIds = d.SelectedPart == null ? new int[0] : new[] { d.SelectedPart.Part.Id }; focusStatus = focusIds.Length == 0 ? "no_selection" : "selected"; }
            Func<PartData, string, string, JObject> rowFor = (p, metric, source) => {
                var r = new JObject { ["part"] = PartSummary(p), ["metric"] = metric, ["sourceId"] = p.Id + "/" + source,
                    ["connectedToMainCockpit"] = set.Contains(p.Id), ["activeInHierarchy"] = p.PartScript.gameObject.activeInHierarchy,
                    ["included"] = true, ["reasonCodes"] = new JArray(), ["positionWorldMeters"] = null, ["positionFrameMeters"] = null, ["nativeWeight"] = null };
                rows.Add(r); return r; };
            Action<JObject, Vector3, double> fill = (r, p, w) => {
                r["positionWorldMeters"] = CentersCore.Vector(CenterVec(p)) ? CenterVec(p) : null;
                var local = CenterVec(inverse.MultiplyPoint3x4(p)); r["positionFrameMeters"] = CentersCore.Vector(local) ? local : null;
                r["nativeWeight"] = VisualCore.Finite(w) ? (JToken)w : null;
            };
            Action<JObject, string> exclude = (r, reason) => { r["included"] = false; ((JArray)r["reasonCodes"]).Add(reason); };
            foreach (var p in connected)
            {
                var r = rowFor(p, "mass", "loaded_mass"); r["weightMeaning"] = "kilograms_current_loaded_mass";
                try { double mass = p.LoadedMass / .01; fill(r, p.PartScript.transform.TransformPoint(p.CenterOfMass), mass); if (!VisualCore.Finite(p.EmptyMass)) exclude(r, "invalid_native_empty_mass"); }
                catch (Exception) { exclude(r, "native_mass_read_failed"); }
            }
            if (SP2Game.Version.ToString()=="0.7.8.103")
            {
                var affected=connected.Where(p=>p.GetModifier<JWingData>()?.Flipped==true).Select(p=>p.Id).ToArray();
                if(affected.Length>0) warnings.Add(CentersCore.Warning("native_flipped_wing_com_y_zeroed",
                    "Game 0.7.8.103 WingBuilder zeroes local mass-center Y for flipped procedural wings (y -= y). This report preserves the game's actual mass center; a geometrically mirrored pair need not have mirrored vertical mass centers. The plugin does not patch native mass/flight physics.",affected));
            }
            int wingIndex = 0;
            foreach (var wing in aircraft.Wings)
            {
                var component = wing as PartModifierScript;
                if (component == null || component.PartScript == null) throw new ApiError("unsupported_center_source", "Native wing list contains an unidentifiable source.");
                var r = rowFor(component.PartScript.Part, "lift", "wing/" + wingIndex++); r["weightMeaning"] = "projected_area_square_metres_times_lift_scale";
                if (wing.GetType() != typeof(JWingScript)) { exclude(r, "legacy_or_mod_wing_not_readonly_verified"); continue; }
                try { Vector3 center; float area = wing.GetProjectedAreaMoment(Vector3.up, out center), liftScale = wing.LiftScale;
                    fill(r, center, (double)area * liftScale); r["projectedAreaSquareMeters"] = VisualCore.Finite(area) ? (JToken)area : null;
                    r["liftScale"] = VisualCore.Finite(liftScale) ? (JToken)liftScale : null;
                } catch (Exception) { exclude(r, "native_lift_read_failed"); }
            }
            var propulsionTypes = new HashSet<string>(); int propCount = 0;
            foreach (var p in connected)
            {
                var thrust = p.PartScript.GetModifierWithInterface<IDesignerThrust>(); if (thrust == null) continue;
                var r = rowFor(p, "thrust", "designer_thrust/" + thrust.GetType().FullName); r["directionStatus"] = "unverified"; r["directionWorld"] = null;
                bool known = thrust.GetType().Assembly == typeof(PartData).Assembly && (thrust is ModernJet || thrust is PropellerAssemblyScript || thrust is EngineScript);
                if (!known) { r["weightMeaning"] = "unknown"; r["propulsionType"] = thrust.GetType().FullName; exclude(r, "mod_thrust_not_readonly_verified"); continue; }
                try
                {
                    double weight;
                    if (thrust is ModernJet jet)
                    {
                        // The native getter updates MathParams. Run the same calculation on a shallow
                        // data clone with fresh math state so a read never changes the live engine cache.
                        var clone = typeof(object).GetMethod("MemberwiseClone", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(jet.Data, null);
                        var math = jet.Data.GetType().GetProperty("MathParams"); math.GetSetMethod(true).Invoke(clone, new[] { Activator.CreateInstance(math.PropertyType) });
                        weight = ((Assets.Scripts.Craft.Parts.Modifiers.Propulsion.Jet.JetEngineData)clone).CalculateThrustAtSeaLevel();
                        r["weightMeaning"] = "native_sea_level_static_thrust_newtons_including_available_afterburner";
                    }
                    else { weight = thrust.DesignerThrust; r["weightMeaning"] = thrust is PropellerAssemblyScript ? "diameter_squared_times_blade_count_proxy" : "legacy_engine_power_proxy"; }
                    string type = thrust.DesignerThrustType.ToString(); r["propulsionType"] = type; propulsionTypes.Add(type);
                    if (thrust is PropellerAssemblyScript || type == "LegacyProp") propCount++;
                    fill(r, thrust.DesignerCenterOfThrust, weight);
                } catch (Exception) { exclude(r, "native_thrust_read_failed"); }
            }
            // Preserve the native manager's includeInactive hierarchy scope without calling Refresh.
            var manager = aircraft.VtolManagerScript;
            if (manager != null)
            {
                var engines = manager.GetComponentsInChildren<LegacyJet>(true).Where(e => e.Engine.DuctedThrust).ToArray();
                var ports = manager.GetComponentsInChildren<EngineThrustPortScript>(true);
                double power = engines.Sum(e => (double)e.Engine.Power);
                if (engines.Length > 0 && (!VisualCore.Finite(power) || power < 0 || (power > 0 && ports.Length == 0)))
                {
                    foreach (var e in engines) { var r = rowFor(e.PartScript.Part, "thrust", "legacy_vtol_missing_ports"); r["weightMeaning"] = "legacy_engine_power_proxy"; exclude(r, "invalid_vtol_power_or_no_nozzles"); }
                }
                else if (power > 0)
                {
                    int index = 0; propulsionTypes.Add("LegacyEngine");
                    foreach (var port in ports)
                    {
                        var r = rowFor(port.PartScript.Part, "thrust", "legacy_vtol_nozzle/" + index++); r["weightMeaning"] = "shared_legacy_ducted_engine_power_proxy";
                        r["propulsionType"] = "LegacyEngine"; r["directionStatus"] = "unverified"; r["directionWorld"] = null; fill(r, port.transform.position, power / ports.Length);
                    }
                    warnings.Add(CentersCore.Warning("legacy_vtol_scope", "Native VTOL adds all hierarchy nozzles including inactive or disconnected objects, in addition to main-loop engine sources. This can count an engine in both native paths.", ports.Select(p => p.PartScript.Part.Id)));
                }
            }
            if (propulsionTypes.Count > 1) warnings.Add(CentersCore.Warning("mixed_propulsion_weights", "Native CoT mixes unlike scalar weights; its total is not newtons or usable for thrust-to-weight ratio."));
            if (propCount > 1) warnings.Add(CentersCore.Warning("multiple_propeller_approximation", "Native CoT is approximate for multiple propellers with different configurations."));
            warnings.Add(CentersCore.Warning("axis_convention", "Right/up/forward are declared coordinate directions. Confirm that +Z points toward this craft's nose before interpreting longitudinal layout."));
            var meta = new JObject { ["identity"] = JToken.FromObject(Identity()), ["analysisId"] = Guid.NewGuid().ToString("N"), ["capturedAt"] = DateTime.UtcNow.ToString("o"), ["capturedFrame"] = Time.frameCount,
                ["geometryStamp"] = Json.Hash(GeometrySignature(d)), ["staleAtDelivery"] = false,
                ["basis"] = new JObject { ["mode"] = "native_designer", ["loadCondition"] = "current_editor_configuration", ["liftProjectionAxisWorld"] = new JArray(0,1,0),
                    ["scopePolicy"] = "native_connected_mass_and_wings_and_thrust_plus_legacy_vtol_hierarchy", ["aircraftOrientationWorld"] = aircraft.MainCockpit == null ? null : CenterRotation(aircraft.MainCockpit.transform.rotation),
                    ["massConversion"] = "kilograms = native LoadedMass / 0.01; EmptyMass is not dry fuel mass", ["gameVersion"] = SP2Game.Version.ToString() },
                ["frame"] = frameInfo, ["scope"] = new JObject { ["assemblyPartCount"] = all.Length, ["connectedPartCount"] = connected.Length, ["disconnectedPartCount"] = all.Count(p => !set.Contains(p.Id)), ["connectedPartIds"] = new JArray(set.OrderBy(i=>i)), ["meaning"] = "Whole native designer scope regardless of focus, detail, metric, pagination or visual groups." },
                ["focus"] = new JObject { ["status"] = focusStatus, ["partIds"] = focusIds == null ? null : new JArray(focusIds), ["meaning"] = "Contributor filter and visual highlight only; centers remain whole aircraft." }, ["warnings"] = warnings };
            return CentersCore.Build(meta, rows, options, focusIds);
        }
    }
}
