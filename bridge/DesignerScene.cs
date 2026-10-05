using System.Linq;
using Assets.Scripts.Craft;
using Assets.Scripts.Design;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private static JObject DesignerSceneIntegrity(Designer d)
        {
            var container = d.DesignerScript.transform.Find("AircraftContainer");
            var roots = container == null ? new AircraftScript[0] : container.GetComponentsInChildren<AircraftScript>(true);
            bool currentPresent = roots.Any(r => r == d.Aircraft);
            int extra = roots.Count(r => r != d.Aircraft);
            bool foreignSelection = d.SelectedPart != null && d.SelectedPart.Aircraft != d.Aircraft;
            bool currentActive = d.Aircraft != null && d.Aircraft.gameObject.activeInHierarchy;
            bool healthy = currentPresent && currentActive && extra == 0 && !foreignSelection;
            return new JObject {
                ["status"] = healthy ? "healthy" : "inconsistent", ["currentAircraftPresent"] = currentPresent, ["currentAircraftActive"] = currentActive,
                ["aircraftInstanceCount"] = roots.Length, ["extraAircraftInstanceCount"] = extra,
                ["activeAircraftInstanceCount"] = roots.Count(r => r.gameObject.activeInHierarchy),
                ["selectedPartBelongsToCurrentAircraft"] = d.SelectedPart == null ? (JToken)null : new JValue(!foreignSelection),
                ["instances"] = new JArray(roots.Select(r => new JObject {
                    ["instanceId"] = r.GetInstanceID(), ["name"] = r.name, ["isCurrent"] = r == d.Aircraft,
                    ["activeInHierarchy"] = r.gameObject.activeInHierarchy,
                    ["partCount"] = r.Aircraft?.Assembly?.Parts?.Count ?? 0
                })),
                ["scope"] = "AircraftScript instances under the active designer AircraftContainer, including inactive instances; plus the primary selected object's owner.",
                ["meaning"] = "Separate from serialized craft identity. Extra instances can be visible/pickable but absent from craft.snapshot and scoped visual meshes. No objects are removed by this query."
            };
        }
        private static void EnsureDesignerSceneIntegrity(Designer d)
        {
            var report = DesignerSceneIntegrity(d);
            if ((string)report["status"] != "healthy")
                throw new ApiError("designer_scene_inconsistent", "Designer scene does not contain exactly the current aircraft: " + report.ToString(Newtonsoft.Json.Formatting.None));
        }
    }
}
