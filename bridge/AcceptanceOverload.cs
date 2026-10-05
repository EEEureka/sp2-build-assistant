#if ACCEPTANCE_HOOKS
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Xml.Linq;
using Assets.Scripts.Design.UI;
using Assets.Scripts.Design.UI.Overload;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        // Independent native Overload panel reference for mandatory settings
        // with no ordinary generic widget. No arbitrary XML/path input.
        private async UniTask<JObject> AcceptanceOverload(JObject a,Job job,XElement before)
        {
            if(a["modifierType"]!=null||a["modifierIndex"]!=null||a["member"]!=null)throw new ApiError("invalid_input","Overload uses element and attribute, not generic member names.");
            string element=Required(a,"element"),attribute=Required(a,"attribute");
            string key=element+"@"+attribute;
            if(!new[]{"Piston.State@preventBreaking","GearLeg.State@gearLegStyle","JetEngineShroud.State@width","JetEngineShroud.State@height"}.Contains(key))
                throw new ApiError("native_control_unsupported","Reference overload is limited to four explicitly audited native fields.");
            if(a["value"]?.Type!=JTokenType.String)throw new ApiError("invalid_input","Overload reference requires native text.");
            string value=(string)a["value"];var p=Part(VisualScope.Integer(a["partId"],"partId",0));var d=Current();
            var nodes=p.GenerateXml().Elements(element).ToArray();
            if(nodes.Length!=1||nodes[0].Attribute(attribute)==null)throw new ApiError("native_control_unavailable","Expected one existing native field.");
            if(key=="Piston.State@preventBreaking"&&value!="true"&&value!="false")throw new ApiError("invalid_input","Native boolean text required.");
            if(key=="GearLeg.State@gearLegStyle"){
                var choices=p.GetOverloadMetadataLookup()[element].Attributes.Single(x=>x.Name==attribute).EnumValues;
                if(choices==null||!choices.Contains(value))throw new ApiError("invalid_input","Style absent from native Overload metadata.");
            }
            if(element=="JetEngineShroud.State"){
                if(!float.TryParse(value,System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out float f)||float.IsNaN(f)||float.IsInfinity(f)||f<.1f||f>10f)
                    throw new ApiError("invalid_input","Reference stretch is limited to [0.1,10].");
            }
            await d.UndoHistory.CompletePendingOperations();Observe();Guard(a);
            lock(job.Sync)if(job.CancelRequested)throw new ApiError("cancelled","Cancelled before native Overload.");
            bool started=false;AcceptanceInputBlocked=true;
            try{
                d.SelectedPart=p.PartScript;
                var panel=d.DesignerScript.DesignerUI.Flyouts.Overload.Widget.GetComponentInChildren<OverloadPanelScript>(true);
                var type=typeof(OverloadPanelScript);var flags=BindingFlags.Instance|BindingFlags.NonPublic;
                type.GetMethod("Update",flags).Invoke(panel,null);
                var elements=(List<OverloadElement>)type.GetField("_elements",flags).GetValue(panel);
                var field=elements.Single(x=>x.Name==element).Attributes.Single(x=>x.Name==attribute);
                var symmetry=panel.Widget.FindWidget("apply-symmetry-button");bool wasSymmetric=panel.SymmetryEnabled;
                await d.CreateUndoStepAsync("Acceptance native Overload baseline",null,before);
                try{
                    symmetry.RemoveClass("btn-primary");field.Value=value;started=true;
                    type.GetMethod("OnApplyClicked",flags).Invoke(panel,new object[]{null});
                }finally{if(wasSymmetric)symmetry.AddClass("btn-primary");}
                Observe();await ReadSettled(d,null);EnsureDesignerSceneIntegrity(d);
                string effective=(string)Part(p.Id).GenerateXml().Element(element).Attribute(attribute);
                if(effective!=value)throw new ApiError("native_overload_mismatch","Native Overload did not apply the requested text.");
                await d.CreateUndoStepAsync("Acceptance native Overload");
                return new JObject{["identity"]=JToken.FromObject(Identity()),["action"]="overload",["desktopInputUsed"]=false,
                    ["evidenceSource"]="native_overload_panel_api_not_desktop_input",["beforeValue"]=(string)nodes[0].Attribute(attribute),["effectiveValue"]=effective,
                    ["changes"]=CraftDiff.Compare(before,Observe()),["sceneIntegrity"]=DesignerSceneIntegrity(d)};
            }catch(Exception ex){if(started)uncertain=true;var fail=Json.Fail(ex);fail["identity"]=JToken.FromObject(Identity());fail["nativeActionStarted"]=started;return fail;}
            finally{AcceptanceInputBlocked=false;}
        }
    }
}
#endif
