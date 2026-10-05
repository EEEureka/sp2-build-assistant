using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    // Pure report math. Native sampling is confined to DesignerCenters.cs.
    internal static class CentersCore
    {
        internal const string Version = "native-designer-centers-v1";
        internal static bool Number(JToken t) { return t != null && (t.Type == JTokenType.Integer || t.Type == JTokenType.Float) && VisualCore.Finite(t.Value<double>()); }
        internal static bool Vector(JToken t) { return t is JArray a && a.Count == 3 && a.All(Number); }
        internal static VisualCore.V V(JToken t) { return new VisualCore.V(t[0].Value<double>(), t[1].Value<double>(), t[2].Value<double>()); }
        private static double Length(VisualCore.V v) { return Math.Sqrt(v.Dot(v)); }
        internal static JObject Warning(string code, string message, IEnumerable<int> ids = null)
        { return new JObject { ["code"] = code, ["severity"] = "warning", ["message"] = message, ["relatedPartIds"] = new JArray(ids ?? new int[0]) }; }

        internal static JObject Build(JObject metadata, JArray rows, JObject options, int[] focusIds)
        {
            var report = (JObject)metadata.DeepClone();
            report["calculationVersion"] = Version;
            var centers = new JObject(); var warnings = (JArray)report["warnings"];
            string[] metrics = { "mass", "lift", "thrust" }, keys = { "com", "col", "cot" };
            string[] methods = { "native_loaded_mass_weighted", "designer_projected_area_lift_scale", "native_weighted_position" };
            for (int k = 0; k < metrics.Length; k++)
            {
                var sources = rows.OfType<JObject>().Where(r => (string)r["metric"] == metrics[k]).ToArray();
                foreach (var row in sources)
                {
                    if (row.Value<bool>("included") && (!Number(row["nativeWeight"]) || row.Value<double>("nativeWeight") < 0 || !Vector(row["positionWorldMeters"]) || !Vector(row["positionFrameMeters"])))
                    { row["included"] = false; ((JArray)row["reasonCodes"]).Add("invalid_weight_or_position"); }
                }
                var valid = sources.Where(r => r.Value<bool>("included")).ToArray();
                double total = valid.Sum(r => r.Value<double>("nativeWeight"));
                bool available = total > 0 && VisualCore.Finite(total);
                var world = new VisualCore.V(); var local = new VisualCore.V();
                if (available) foreach (var r in valid) { double share = r.Value<double>("nativeWeight") / total; world += V(r["positionWorldMeters"]) * share; local += V(r["positionFrameMeters"]) * share; }
                available &= Vector(world.Json()) && Vector(local.Json());
                var reasons = new JArray(sources.SelectMany(r => r["reasonCodes"].Values<string>()).Distinct());
                if (!available) reasons.Add(sources.Length == 0 ? "no_sources" : "no_positive_finite_total");
                int excluded = sources.Length - valid.Length;
                var c = new JObject { ["status"] = !available ? "unavailable" : excluded > 0 ? "partial" : "valid",
                    ["quality"] = k == 0 ? "mass_weighted" : "designer_proxy", ["method"] = methods[k],
                    ["positionWorldMeters"] = available ? world.Json() : null, ["positionFrameMeters"] = available ? local.Json() : null,
                    ["nativeWeightTotal"] = VisualCore.Finite(total) ? (JToken)total : null,
                    ["weightMeaning"] = k == 0 ? "kilograms" : k == 1 ? "world_up_projected_area_times_lift_scale" : "native_designer_scalar_weights_not_uniform_force_units",
                    ["contributorCount"] = valid.Count(r => r.Value<double>("nativeWeight") > 0), ["sourceCount"] = sources.Length,
                    ["excludedCount"] = excluded, ["coverage"] = excluded == 0 ? "complete" : "partial",
                    ["nativeParity"] = excluded == 0 ? "source_formula_reconstruction_double_precision" : "incomplete_not_native_marker_equivalent", ["reasonCodes"] = reasons };
                if (k == 0) c["massKg"] = available ? (JToken)total : null;
                centers[keys[k]] = c;
                if (excluded > 0) warnings.Add(Warning("partial_" + metrics[k] + "_coverage", "Excluded sources are listed in contributors. This center is not a complete native marker reconstruction.", sources.Where(r => !r.Value<bool>("included")).Select(r => r["part"].Value<int>("id"))));
                foreach (var row in sources) row["nativeWeightFraction"] = available && row.Value<bool>("included") ? (JToken)(row.Value<double>("nativeWeight") / total) : null;
            }
            report["centers"] = centers;
            var relations = new JObject();
            foreach (var pair in new[] { new[] { "colFromCom", "com", "col" }, new[] { "cotFromCom", "com", "cot" }, new[] { "cotFromCol", "col", "cot" } })
                relations[pair[0]] = Relation(centers[pair[1]], centers[pair[2]]);
            report["relations"] = relations;
            report["positionRelationToleranceMeters"] = .001;
            report["assessment"] = new JObject {
                ["longitudinalStaticStability"] = new JObject { ["status"] = "not_assessed", ["reasonCodes"] = new JArray("designer_col_is_not_neutral_point", "pitch_moment_derivative_unavailable"), ["staticMargin"] = null },
                ["trim"] = new JObject { ["status"] = "not_assessed", ["reasonCodes"] = new JArray("flight_condition_unspecified") },
                ["thrustMoment"] = new JObject { ["status"] = "not_assessed", ["reasonCodes"] = new JArray("force_direction_or_scale_unverified"), ["momentNm"] = null } };
            foreach (JObject row in rows)
            {
                row["normalizationBasis"] = "included_whole_aircraft_sources_before_focus_or_paging";
                if (row.Value<string>("metric") != "mass") continue;
                row["massKg"] = row["nativeWeight"]?.DeepClone(); row["massFraction"] = row["nativeWeightFraction"]?.DeepClone();
                bool usable = row.Value<bool>("included") && Vector(centers["com"]["positionFrameMeters"]);
                var offset = usable ? V(row["positionFrameMeters"]) - V(centers["com"]["positionFrameMeters"]) : new VisualCore.V();
                row["offsetFromComMeters"] = usable ? offset.Json() : null;
                row["massMomentAboutComKgM"] = usable ? (offset * row.Value<double>("nativeWeight")).Json() : null;
            }
            string metric = (string)options["metric"] ?? "all";
            bool detailed = (string)options["detail"] == "contributors";
            int limit = (int?)options["limit"] ?? 20, offsetPage = (int?)options["offset"] ?? 0;
            var filtered = rows.OfType<JObject>().Where(r => (metric == "all" || r.Value<string>("metric") == metric) && (focusIds == null || focusIds.Contains(r["part"].Value<int>("id"))))
                .OrderBy(r => Array.IndexOf(metrics, (string)r["metric"]))
                .ThenByDescending(r => Vector(r["massMomentAboutComKgM"]) ? Length(V(r["massMomentAboutComKgM"])) : Number(r["nativeWeight"]) ? r.Value<double>("nativeWeight") : -1)
                .ThenBy(r => (string)r["sourceId"], StringComparer.Ordinal).ToArray();
            var page = detailed ? filtered.Skip(offsetPage).Take(limit).ToArray() : new JObject[0];
            report["contributors"] = new JObject { ["requested"] = detailed, ["metric"] = metric, ["total"] = filtered.Length,
                ["offset"] = offsetPage, ["limit"] = limit, ["returned"] = page.Length, ["truncated"] = detailed && offsetPage + page.Length < filtered.Length,
                ["nextOffset"] = detailed && offsetPage + page.Length < filtered.Length ? (JToken)(offsetPage + page.Length) : null,
                ["sort"] = "metric order mass/lift/thrust; descending mass-moment magnitude or native weight; sourceId tie break", ["items"] = new JArray(page) };
            report["visual"] = null;
            report["comparison"] = options["baseline"] is JObject baseline ? Compare(baseline, report) : null;
            return report;
        }
        private static JObject Relation(JToken from, JToken to)
        {
            if (!Vector(from["positionFrameMeters"]) || !Vector(to["positionFrameMeters"])) return null;
            var v = V(to["positionFrameMeters"]) - V(from["positionFrameMeters"]);
            Func<double, string, string, string> side = (n, positive, negative) => Math.Abs(n) <= .001 ? "aligned_within_display_tolerance" : n > 0 ? positive : negative;
            return new JObject { ["deltaFrameMeters"] = v.Json(), ["distanceMeters"] = Length(v),
                ["status"] = (string)from["status"] == "partial" || (string)to["status"] == "partial" ? "partial" : "valid",
                ["axisRelation"] = new JArray(side(v.X, "right", "left"), side(v.Y, "above", "below"), side(v.Z, "forward", "aft")),
                ["meaning"] = "Target minus origin in the declared frame convention; not a stability margin or force moment arm." };
        }
        internal static JObject Compare(JObject baseline, JObject current)
        {
            var reasons = new JArray();
            if ((string)baseline["calculationVersion"] != Version) reasons.Add("calculation_version_changed");
            if ((string)baseline["identity"]?["craftSessionId"] != (string)current["identity"]?["craftSessionId"]) reasons.Add("session_changed");
            foreach (string field in new[] { "mode", "loadCondition", "liftProjectionAxisWorld", "scopePolicy", "aircraftOrientationWorld", "gameVersion" })
                if (!Equivalent(baseline["basis"]?[field], current["basis"]?[field])) reasons.Add("basis_changed_" + field);
            foreach (string field in new[] { "kind", "partId", "referenceToken", "orientationWorld" })
                if (!Equivalent(baseline["frame"]?[field], current["frame"]?[field])) reasons.Add("frame_changed_" + field);
            if (!(baseline["centers"] is JObject) || !(baseline["relations"] is JObject)) reasons.Add("invalid_baseline_structure");
            var result = new JObject { ["status"] = reasons.Count == 0 ? "comparable" : "not_comparable", ["reasonCodes"] = reasons,
                ["baselineIdentity"] = baseline["identity"]?.DeepClone(), ["currentIdentity"] = current["identity"].DeepClone(),
                ["scopeMembershipChanged"] = !JToken.DeepEquals(baseline["scope"]?["connectedPartIds"], current["scope"]?["connectedPartIds"]),
                ["meaning"] = "Observed changes, not causal attribution or a stability score. Relative changes remove common translation; current images depict the current sample only.",
                ["centerChanges"] = null, ["relativeChanges"] = null,
                ["qualityNotice"] = "Changes involving partial centers use only covered sources. Designer lift/thrust weights remain proxies in both samples." };
            if (reasons.Count > 0) return result;
            var absolute = new JObject(); var relative = new JObject();
            foreach (string key in new[] { "com", "col", "cot" }) absolute[key] = Difference(baseline["centers"]?[key]?["positionFrameMeters"], current["centers"][key]["positionFrameMeters"]);
            foreach (string key in new[] { "colFromCom", "cotFromCom", "cotFromCol" }) { var before=(baseline["relations"]?[key] as JObject)?["deltaFrameMeters"];var after=(current["relations"][key] as JObject)?["deltaFrameMeters"];var change=Difference(before,after);
                change["beforeDistanceMeters"]=Vector(before)?(JToken)Length(V(before)):null;change["afterDistanceMeters"]=Vector(after)?(JToken)Length(V(after)):null;
                change["distanceChangeMeters"]=Vector(before)&&Vector(after)?(JToken)(Length(V(after))-Length(V(before))):null;relative[key]=change; }
            result["centerChanges"] = absolute; result["relativeChanges"] = relative; return result;
        }
        private static bool Equivalent(JToken a, JToken b)
        {
            if (a is JArray aa && b is JArray bb && aa.Count == bb.Count && aa.All(Number) && bb.All(Number))
                return aa.Zip(bb, (x, y) => Math.Abs(x.Value<double>() - y.Value<double>()) <= 1e-6).All(x => x);
            return JToken.DeepEquals(a, b);
        }
        private static JObject Difference(JToken before, JToken after)
        { return new JObject { ["beforeMeters"] = before?.DeepClone(), ["afterMeters"] = after?.DeepClone(), ["deltaMeters"] = Vector(before) && Vector(after) ? (V(after) - V(before)).Json() : null }; }
    }
}
