using Cysharp.Threading.Tasks;
using Newtonsoft.Json.Linq;
#if ACCEPTANCE_HOOKS
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Xml.Linq;
using UnityEngine;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Design;
using Assets.Scripts.Design.Tools;
using Assets.Scripts.Design.PartProperties.Attributes;
using Assets.Scripts.Design.UI.PartProperties;
using Assets.Scripts.UI.Dialogs;
#endif

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
#if ACCEPTANCE_HOOKS
        private static bool AcceptanceInputBlocked;
        private static object AcceptanceNativeCapability() { return new { available=true,
            command="acceptance.native", fixturePrefix="SP2Build 050 Precision Lab",
            actions=new[]{"inspect","undo","redo","reload","property","overload"},
            evidence="native_ui_controls_api_not_desktop_input", desktopInput=false }; }

        // Bind the real native panel, so OnGenericDesignerPropertiesVisible
        // supplies dynamic ranges and resource choices (e.g. hinge MaxRange).
        // This is native UI code via APIs, without OS input or window activation.
        private static List<ConfigurableProperty> NativeControls(PartModifierData modifier)
        {
            var d=Designer.Instance;d.SelectedPart=modifier.Part.PartScript;
            var panel=d.DesignerScript.DesignerUI.Flyouts.PartProperties.Widget.GetComponentInChildren<PartPropertiesPanelScript>(true);
            typeof(PartPropertiesPanelScript).GetMethod("Update",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(panel,null);
            var groups=(List<GenericPartPropertiesScript>)typeof(PartPropertiesPanelScript).GetField("_partProperties",BindingFlags.NonPublic|BindingFlags.Instance).GetValue(panel);
            var group=groups.SingleOrDefault(g=>g.CurrentPartModifier==modifier);
            if(group==null)throw new ApiError("native_control_unavailable","Native panel did not bind this modifier instance.");
            // Selection queues this for the following UI update. Complete
            // that native lifecycle before using resource picker callbacks;
            // TextureProperty binds its handler in RefreshUI, not selection.
            group.RefreshUI();
            return (List<ConfigurableProperty>)typeof(GenericPartPropertiesScript).GetField("_properties",BindingFlags.NonPublic|BindingFlags.Instance).GetValue(group);
        }

        private static JToken NativeValue(object value)
        {
            if(value==null)return JValue.CreateNull();
            if(value is Vector2 v2)return new JArray(v2.x,v2.y);
            if(value is Vector3 v3)return new JArray(v3.x,v3.y,v3.z);
            if(value is Color color)return new JArray(color.r,color.g,color.b,color.a);
            if(value is Pose pose)return new JObject{["position"]=new JArray(pose.position.x,pose.position.y,pose.position.z),
                ["rotationQuaternion"]=new JArray(pose.rotation.x,pose.rotation.y,pose.rotation.z,pose.rotation.w)};
            if(value is List<int> ids)return new JArray(ids);
            if(value.GetType().IsEnum)return new JValue(value.ToString());
            if(value is string||value is bool||value is byte||value is short||value is int||value is long||value is float||value is double||value is decimal)return JToken.FromObject(value);
            return new JObject{["unavailable"]=true,["nativeType"]=value.GetType().FullName,["reason"]="Complex native control values require a specialized reference reader."};
        }

        private static object NativeInput(ConfigurableProperty c,JToken token)
        {
            if(token==null||token.Type==JTokenType.Null)throw new ApiError("invalid_input","A primitive native value is required.");
            Type type=c.FieldType;
            Func<JToken,int,float[]> vector=(t,n)=>{
                var a=t as JArray;
                if(a==null||a.Count!=n||a.Any(v=>v.Type!=JTokenType.Integer&&v.Type!=JTokenType.Float))throw new ApiError("invalid_input","Invalid native vector dimension/type.");
                var values=a.Select(v=>(float)v).ToArray();
                if(values.Any(v=>float.IsNaN(v)||float.IsInfinity(v)))throw new ApiError("invalid_input","Native vector must be finite.");
                return values;};
            if(c is VectorProperty vc){
                int n=type==typeof(Vector2)?2:type==typeof(Vector3)?3:0;
                if(n==0)throw new ApiError("native_control_unsupported","Unsupported native vector type.");
                var v=vector(token,n);var a=vc.VectorAttribute;
                if(v.Any(x=>(double)x<(double)a.MinValue||(double)x>(double)a.MaxValue))throw new ApiError("invalid_input","Native vector outside control bounds.");
                if(n==2)return new Vector2(v[0],v[1]);return new Vector3(v[0],v[1],v[2]);
            }
            if(c is ColorProperty){var v=vector(token,4);if(v.Any(x=>x<0||x>1))throw new ApiError("invalid_input","Native RGBA outside [0,1].");
                if(!((DesignerPropertyColorAttribute)c.Attribute).AllowTransparency&&v[3]!=1)throw new ApiError("native_control_unsupported","This native color widget does not expose alpha; use its opacity control for UI reference.");
                return new Color(v[0],v[1],v[2],v[3]);}
            if(c is PoseProperty){
                var o=token as JObject;if(o==null||o.Properties().Any(field=>field.Name!="position"&&field.Name!="rotationQuaternion"))throw new ApiError("invalid_input","Native pose needs position and rotationQuaternion.");
                var p=vector(o["position"],3);var q=vector(o["rotationQuaternion"],4);
                double length=Math.Sqrt(q.Sum(x=>(double)x*x));if(length<1e-8)throw new ApiError("invalid_input","Native quaternion cannot be zero.");
                return new Pose(new Vector3(p[0],p[1],p[2]),new Quaternion((float)(q[0]/length),(float)(q[1]/length),(float)(q[2]/length),(float)(q[3]/length)));
            }
            if(c is CustomWidgetProperty custom&&custom.Widget is PartListWidget){
                var a=token as JArray;if(a==null||a.Any(x=>x.Type!=JTokenType.Integer))throw new ApiError("invalid_input","Native part list needs integer IDs.");
                var ids=a.Values<int>().ToList();
                if(ids.Distinct().Count()!=ids.Count||ids.Any(id=>Designer.Instance.Aircraft.Aircraft.Assembly.GetPartById(id)==null))throw new ApiError("invalid_input","Native part list has duplicate or missing IDs.");
                if(ids.Any(id=>{var part=Designer.Instance.Aircraft.Aircraft.Assembly.GetPartById(id);return part.PartScript.HasModifier<DecalScript>()||part.PartScript.DecalTargets.Count==0;}))throw new ApiError("invalid_input","Native part picker does not offer that target.");return ids;
            }
            if(c is TextureProperty&&c.CurrentPartModifier is ITexturePropertyHandler textureHandler){
                if(token.Type!=JTokenType.String)throw new ApiError("invalid_input","Expected native texture ID.");
                var item=textureHandler.CreateItemsForTexturePicker(c).SingleOrDefault(x=>x.Id==(string)token);
                if(item==null)throw new ApiError("invalid_input","Texture is absent from the native picker.");return item;
            }
            if(type==typeof(bool)&&(c is ToggleButtonProperty||c is DropdownProperty)){
                if(token.Type!=JTokenType.Boolean)throw new ApiError("invalid_input","Expected a boolean.");
                return (bool)token;
            }
            if(type==typeof(string)&&(c is DropdownProperty||c is TextProperty)){
                if(token.Type!=JTokenType.String)throw new ApiError("invalid_input","Expected native text/resource ID.");
                var dropdown=c as DropdownProperty;
                if(dropdown!=null&&!dropdown.DropdownAttribute.Values.Contains((string)token))throw new ApiError("invalid_input","Value is not among the actual native dropdown options.");
                return (string)token;
            }
            if((c is ToggleButtonProperty||c is DropdownProperty)&&type.IsEnum){
                if(token.Type!=JTokenType.String||!Enum.GetNames(type).Contains((string)token))throw new ApiError("invalid_input","Expected an exact native enum name.");
                return Enum.Parse(type,(string)token);
            }
            if(c is SliderProperty||c is SpinnerProperty){
                if(token.Type!=JTokenType.Integer&&token.Type!=JTokenType.Float)throw new ApiError("invalid_input","Expected a finite number.");
                double number=(double)token;
                double min,max;
                var slider=c.Attribute as DesignerPropertySliderAttribute;
                var spinner=c.Attribute as DesignerPropertySpinnerAttribute;
                if(slider!=null){min=slider.MinValue;max=slider.MaxValue;}
                else{min=(double)spinner.MinValue;max=(double)spinner.MaxValue;}
                if(double.IsNaN(number)||double.IsInfinity(number)||number<min||number>max)throw new ApiError("invalid_input","Value is outside native control bounds.");
                if(type!=typeof(float)&&type!=typeof(double)&&type!=typeof(decimal)&&type!=typeof(int))throw new ApiError("native_control_unsupported","Unsupported numeric representation.");
                if(type==typeof(int)&&number!=Math.Truncate(number))throw new ApiError("invalid_input","Expected an integer.");
                return Convert.ChangeType(number,type,CultureInfo.InvariantCulture);
            }
            throw new ApiError("native_control_unsupported","Background reference setters currently support numeric sliders/spinners and boolean/enum controls. Custom widgets require a separate native reference path.");
        }

        private async UniTask<JObject> AcceptanceNative(JObject a,Job job)
        {
            if(string.IsNullOrWhiteSpace(job.Key))throw new ApiError("invalid_input","Native acceptance requests require requestId for idempotence.");
            VisualScope.Keys(a,"craftSessionId","expectedRevision","expectedCraftName","action","partId","modifierType","modifierIndex","member","value","element","attribute");
            var before=Observe();Guard(a);var d=Current();EnsureDesignerSceneIntegrity(d);
            var originalAircraft=d.Aircraft;string name=d.Aircraft.Aircraft.Name;
            if(!name.StartsWith("SP2Build 050 Precision Lab",StringComparison.Ordinal)||Required(a,"expectedCraftName")!=name)
                throw new ApiError("test_fixture_required","Native acceptance actions require the exact named precision lab currently open. Player aircraft are rejected.");
            string action=Required(a,"action");
            if(action=="overload")return await AcceptanceOverload(a,job,before);
            if(a["element"]!=null||a["attribute"]!=null)throw new ApiError("invalid_input","Overload fields require overload action.");
            if(!new[]{"inspect","undo","redo","reload","property"}.Contains(action))throw new ApiError("invalid_input","Unknown native acceptance action.");
            if(action=="inspect"&&(a["member"]!=null||a["value"]!=null))throw new ApiError("invalid_input","Inspect does not accept a setter payload.");
            if(action!="inspect"&&action!="property"&&new[]{"partId","modifierType","modifierIndex","member","value"}.Any(k=>a[k]!=null))throw new ApiError("invalid_input","History/reload actions do not accept property fields.");
            string beforeSession=session,beforeHash=fingerprint;
            ConfigurableProperty control=null;PartModifierData modifier=null;object value=null;JToken oldValue=null;
            if(action=="inspect"||action=="property"){
                var part=Part(Int(a,"partId"));string type=Required(a,"modifierType");int index=a.Value<int?>("modifierIndex")??0;
                var modifiers=part.Modifiers.Where(m=>m.GetType().Name==type).ToArray();
                if(index<0||index>=modifiers.Length)throw new ApiError("invalid_input","Native modifier type/index does not exist on this part.");
                modifier=modifiers[index];var controls=NativeControls(modifier);
                if(action=="inspect")return new JObject{["identity"]=JToken.FromObject(Identity()),["action"]=action,["desktopInputUsed"]=false,
                    ["evidenceSource"]="native_ui_controls_api_not_desktop_input",["controls"]=new JArray(controls.Select(c=>new JObject{
                        ["member"]=c.Member.Name,["controlType"]=c.GetType().Name,["nativeType"]=c.FieldType.FullName,
                        ["label"]=c.GetDefaultLabel(),["visible"]=c.IsVisible(),["value"]=NativeValue(c.GetValue()),
                        ["referenceSetterSupported"]=(c is SliderProperty||c is SpinnerProperty||c is VectorProperty||c is ColorProperty||c is PoseProperty||c is TextureProperty)||
                            (c is CustomWidgetProperty cw&&cw.Widget is PartListWidget)||((c is ToggleButtonProperty||c is DropdownProperty)&&(c.FieldType==typeof(bool)||c.FieldType.IsEnum))||(c.FieldType==typeof(string)&&(c is DropdownProperty||c is TextProperty))}))};
                string member=Required(a,"member");control=controls.SingleOrDefault(c=>c.Member.Name==member);
                if(control==null||!control.IsVisible())throw new ApiError("native_control_unavailable","Native field is absent or hidden in the current configuration.");
                value=NativeInput(control,a["value"]);oldValue=NativeValue(control.GetValue());
            }
            await d.UndoHistory.CompletePendingOperations();Observe();Guard(a);
            if(d.Aircraft!=originalAircraft)throw new ApiError("session_conflict","Native aircraft instance changed before acceptance action.");
            if(action=="undo"&&!d.UndoHistory.UndoStepsAvailable)throw new ApiError("undo_unavailable","No native undo step.");
            if(action=="redo"&&!d.UndoHistory.RedoStepsAvailable)throw new ApiError("redo_unavailable","No native redo step.");
            XElement expectedNative=null;
            if(action=="undo"||action=="redo"){
                var head=await d.UndoHistory.GetCurrentUndoStep();
                int headIndex=Array.IndexOf(d.UndoHistory.UndoSteps.ToArray(),head);
                int targetIndex=headIndex+(action=="undo"?-1:1);
                if(headIndex<0||targetIndex<0||targetIndex>=d.UndoHistory.NumUndoSteps)throw new ApiError("history_conflict","Native history target is unavailable.");
                expectedNative=new XElement(d.UndoHistory.UndoSteps[targetIndex].ReadXml());
                Observe();Guard(a);
                if(d.Aircraft!=originalAircraft)throw new ApiError("session_conflict","Native aircraft changed while resolving history.");
            }
            lock(job.Sync)if(job.CancelRequested)throw new ApiError("cancelled","Cancelled before native acceptance action.");
            AcceptanceInputBlocked=true;
            bool started=false;
            try{
                if(action=="property"){
                    await d.CreateUndoStepAsync("Acceptance native baseline",null,before);
                    bool disabled=modifier.SymmetryDisabled;
                    try{
                        modifier.SymmetryDisabled=true;started=true;
                        if(control is PoseProperty){
                            // Use the native gizmo's completion callback, not the
                            // production property setter. No pointer is synthesized.
                            ((IPoseEditWidgetHandler)modifier).BeginPoseEdit(control.Member.Name,PoseEditMode.Translate);
                            var tool=d.Tools.TranslateTool;
                            var target=(Transform)typeof(TransformTool).GetField("_externalTarget",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(tool);
                            var pose=(Pose)value;target.localPosition=pose.position;target.localRotation=pose.rotation;
                            typeof(TransformTool).GetMethod("OnExternalDoneClicked",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(tool,null);
                        }else if(control is TextureProperty){
                            typeof(TextureProperty).GetMethod("OnTextureSelected",BindingFlags.Instance|BindingFlags.NonPublic)
                                .Invoke(control,new object[]{null,new TexturePickerScript.TextureSelectedEventArgs((TexturePickerItem)value)});
                        }else if(control is CustomWidgetProperty custom&&custom.Widget is PartListWidget list){
                            list.SetPartList((List<int>)value,d.Aircraft.Aircraft.Assembly);
                            typeof(PartListWidget).GetMethod("OnValueChanged",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(list,null);
                        }else{
                            string nativeText=Convert.ToString(value,CultureInfo.CurrentCulture);
                            modifier.OnGenericDesignerPropertyChanging(control.Member.Name,nativeText);
                            control.SetValue(value,false,false,false);
                            modifier.OnGenericDesignerPropertyChanged(control.Member.Name,nativeText);
                        }
                    }finally{modifier.SymmetryDisabled=disabled;}
                }else{
                    started=true;
                    if(action=="undo")await d.Undo();
                    else if(action=="redo")await d.Redo();
                    else d.LoadXml(new XElement(before)); // current live XML only; no saved craft input
                }
                Observe();await ReadSettled(d,null);EnsureDesignerSceneIntegrity(d);
                if(action=="property")await d.CreateUndoStepAsync("Acceptance native property");
                var after=Observe();
                if(action=="reload"&&!SnapshotState.EquivalentAfterNativeRestore(before,after))throw new ApiError("native_reload_mismatch","Native reload changed serialized content.");
                if(action=="reload"&&session==beforeSession)throw new ApiError("native_reload_incomplete","Native reload did not establish a new craft session.");
                if(expectedNative!=null&&!SnapshotState.EquivalentAfterNativeRestore(expectedNative,after))throw new ApiError("native_history_mismatch","Native Undo/Redo did not restore its declared history target.");
                if(action!="reload"&&session!=beforeSession)throw new ApiError("session_conflict","Unexpected craft change during native action.");
                return new JObject{["identity"]=JToken.FromObject(Identity()),["action"]=action,["desktopInputUsed"]=false,
                    ["evidenceSource"]="native_ui_controls_api_not_desktop_input",["beforeFingerprint"]=beforeHash,["sessionChanged"]=session!=beforeSession,
                    ["beforeValue"]=oldValue,["effectiveValue"]=control==null?null:NativeValue(control.GetValue()),
                    ["changes"]=CraftDiff.Compare(before,after),["sceneIntegrity"]=DesignerSceneIntegrity(d),
                    ["limitations"]=new JArray("No actual pointer, keyboard, UI layout, slider quantization or mouse picking tested.","Reload invalidates prior session checkpoints. Failures after native mutation mark state uncertain; this reference path does not silently substitute the production setter or restore path.")};
            }catch(Exception ex){
                if(started)uncertain=true;
                var failure=Json.Fail(ex);failure["identity"]=JToken.FromObject(Identity());failure["nativeActionStarted"]=started;return failure;
            }finally{AcceptanceInputBlocked=false;}
        }
#else
        private static bool AcceptanceInputBlocked { get { return false; } }
        private static object AcceptanceNativeCapability() { return new { available=false,reason="acceptance_build_required" }; }
        private UniTask<JObject> AcceptanceNative(JObject a,Job job)
        { throw new ApiError("acceptance_build_required","Native acceptance actions are compiled out of distribution builds."); }
#endif
    }
}
