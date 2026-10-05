using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Parts.Modifiers.CarverParts;
using Assets.Scripts.Craft.Parts.Modifiers.LandingGear.Procedural;
using Assets.Scripts.Craft.Parts.Modifiers.Propulsion.Jet;
using Assets.Scripts.Craft.Parts.Modifiers.Wheel;
using Assets.Scripts.Craft.CraftResourceData;
using Assets.Scripts.Design.PartProperties.Attributes;
using Assets.Scripts.Design.UI.PartProperties;
using Newtonsoft.Json.Linq;
using UnityEngine;
using SP2Game=Assets.Scripts.Game;

namespace SP2BuildAssistant
{
    internal static class NativePropertyAdapter
    {
        private static readonly Dictionary<string,string> Allowed=new Dictionary<string,string>{
            ["Transparency"]="_opacity",
            ["ProceduralWindow"]="_bottomOffset _bottomWidth _cornerRadius _depth _height _penetration _topOffset _topWidth _hideGlass",
            ["GearBay"]="_bottomOffset _bottomWidth _cornerRadius _depth _height _penetration _topOffset _topWidth _autoHingeAxis _doorStyle _doorThickness _hingeAxisPose _hingeAxisPose2",
            ["JetEngineShroud"]="_height _length _width _shroudStyleID",
            ["Piston"]="_cycle _extend _radius _range _size _speed PreventBreaking",
            ["JointRotator"]="_disableBaseMesh _range _speed _size",
            ["GearLeg"]="_catapultAcceleration _catapultConnectorEnabled _catapultNoseCompression _damperScale _flipped _size _springForceScale _supportStrutType0 _supportStrutType1 _supportStrutType2 _suspensionTravel _targetLaunchSpeed _torqueLinkLength _torqueLinkType _gearLegStyle",
            ["JWheelAssembly"]="_flipped _rimOffset _wheelAssemblyStyle _wheelOffset _brakeTorque _frictionPreset _reversedDirection _rim _size _tireTread _tractionForward _tractionSideways _turningAngle _turningAngleDampening _width",
            ["TextDecal"]="Font FontSize HorizontalAlignment Text VerticalAlignment DecalRotationZ Depth Height Opacity Penetration RenderPriority TintColor Width",
            ["TextureDecal"]="_decalId TextureOffset TextureTiling DecalRotationZ Depth Height Opacity Penetration RenderPriority TintColor Width",
            ["PartTargeting"]="_customPartIds _targetMode"
        };
        internal static void Configure(PropertyEntry e)
        {
            e.Writable=Allowed.ContainsKey(e.Family)&&Allowed[e.Family].Split(' ').Contains(e.MemberName);
            if(!e.Writable)return;
            e.Unit=e.ValueType==typeof(bool)?"boolean":e.ValueType.IsEnum||e.ValueType==typeof(string)?"native_id":e.ValueType==typeof(Pose)?"metres_and_quaternion":"ratio";
            if(e.Modifier is TrapezoidMeshModifierData){e.Frame="part_local_x_width_y_height_z_depth";if(new[]{"_bottomOffset","_bottomWidth","_depth","_height","_topOffset","_topWidth","_doorThickness"}.Contains(e.MemberName))e.Unit="metres";}
            if(e.Modifier is GearBayData&&e.ValueType==typeof(Pose))e.Condition="autoHingeAxis=false and a compatible doorStyle; hinge poses are part-local.";
            if(e.Modifier is JetEngineShroudData&&(e.MemberName=="_width"||e.MemberName=="_height"))e.Condition="Native overload-supported stretch. The ordinary UI shows width/height only for turboshaft-compatible styles; other styles can still be stretched. This can change the engine/shroud fit; inspect connected geometry.";
            if(e.Modifier is DecalData){
                e.Frame="projector_local";
                if(new[]{"Depth","Height","Width"}.Contains(e.MemberName))e.Unit="metres";
                if(e.MemberName=="DecalRotationZ")e.Unit="degrees";
                if(e.MemberName=="TintColor"){e.Unit="rgba_0_1";e.Min=0;e.Max=1;}
                if(e.MemberName=="Text")e.Unit="text";
                if(e.MemberName=="FontSize")e.Unit="native_font_size";
                if(e.MemberName=="RenderPriority")e.Unit="order";
            }
            if(e.Modifier is PistonData){if(e.MemberName=="_range")e.Unit="unscaled_metres";if(e.MemberName=="_extend"||e.MemberName=="_range")e.Condition="Direction cannot change with a part on the moving end; range cannot change there in Pull mode. Physical stroke = range * native part-axis scale.";}
            if(e.Modifier is JointRotatorData&&e.MemberName=="_range"){e.Min=0;e.Max=((JointRotatorData)e.Modifier).MaxRange;e.Unit="degrees";}
            if(e.Modifier is GearLegData){if(e.MemberName=="_targetLaunchSpeed")e.Unit="miles_per_hour";if(e.MemberName.StartsWith("_supportStrut")||e.MemberName.StartsWith("_torqueLink")||e.MemberName.StartsWith("_catapult"))e.Condition="Requires the corresponding mount/capability on the active native gear style.";}
            if(e.Modifier is GearLegData&&e.MemberName=="_gearLegStyle")e.Condition="Native serialized style edit preserves existing Animator keyframes, as Overload does. Re-query mount-dependent fields after changing style; set new prerequisites in a subsequent operation.";
            if(e.Modifier is BaseWheelData&&e.MemberName=="_turningAngle")e.Unit="degrees";
            if(e.Modifier is PartTargetingData){e.Unit=e.MemberName=="_customPartIds"?"part_ids":"native_id";e.Condition="customPartIds require targetMode=Custom; referenced IDs must exist in this revision.";}
            e.Choices=Choices(e);
        }
        internal static IEnumerable<PropertyEntry> Extras(PartModifierData modifier,string family,int index)
        {
            string[] names=modifier is PistonData?new[]{"PreventBreaking"}:modifier is GearLegData?new[]{"_gearLegStyle"}:modifier is JetEngineShroudData?new[]{"Radius","LengthScale","BaseScale"}:new string[0];
            foreach(string name in names){
                var m=modifier.GetType().GetMember(name,BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance).Single();
                var e=new PropertyEntry{Id=family+"["+index+"]."+name.TrimStart('_'),Family=family,Modifier=modifier,Member=m,MemberName=name,
                    Attribute=new DesignerPropertyTextInputAttribute{Label=name.TrimStart('_')},ValueType=m is FieldInfo?((FieldInfo)m).FieldType:((PropertyInfo)m).PropertyType};
                Configure(e);
                if(modifier is JetEngineShroudData){e.Derived=true;e.Unit="native_derived_scale";e.Condition="Derived from connected engine, shroud prefab and style; change engine/style/length through their supported adapters.";}
                yield return e;
            }
        }
        private static JArray Choices(PropertyEntry e)
        {
            var resources=SP2Game.Instance.CraftResourceData;
            if(e.Modifier is TextureDecalData&&e.MemberName=="_decalId")return new JArray(SP2Game.Instance.CraftDecalManager.CraftDecals.Select(x=>x.Id));
            if(e.Modifier is JetEngineShroudData&&e.MemberName=="_shroudStyleID"){
                var s=(JetEngineShroudData)e.Modifier;
                return new JArray(resources.JetEnginePrefabs.Shrouds.Where(x=>x.supportedJetEngineTypes.HasFlag(s.JetEngineType)).Select(x=>x.Id));
            }
            if(e.Modifier is GearLegData){var g=(GearLegData)e.Modifier;var r=resources.LandingGearPrefabs;
                if(e.MemberName=="_gearLegStyle")return new JArray(r.GearLegStyles.Select(x=>x.Id));
                if(e.MemberName=="_torqueLinkType")return new JArray(new[]{"None"}.Concat(r.TorqueLinkTypes.Select(x=>x.Id)));
                if(e.MemberName.StartsWith("_supportStrutType")){
                    int i=e.MemberName[e.MemberName.Length-1]-'0';var mounts=g.Script?.Animator?.SupportStrutMounts;
                    if(mounts!=null&&i<mounts.Length&&mounts[i].IsFixedStyle)return new JArray("None","Enabled");
                    return new JArray(new[]{"None"}.Concat(r.SupportStrutTypes.Select(x=>x.Id)));
                }
            }
            if(e.Modifier is JWheelAssemblyData){var w=resources.WheelPrefabs;
                if(e.MemberName=="_wheelAssemblyStyle")return new JArray(resources.LandingGearPrefabs.WheelAssemblyStyles.Select(x=>x.Id));
                if(e.MemberName=="_rim")return new JArray(w.Rims.Where(x=>x.group.HasFlag(WheelPrefabs.RimGroup.LandingGear)).Select(x=>x.Id));
                if(e.MemberName=="_tireTread")return new JArray(w.Tires.Where(x=>x.category.ToString()=="LandingGear").Select(x=>x.Id));
                if(e.MemberName=="_frictionPreset")return new JArray(w.FrictionPresets.Select(x=>x.id));
            }
            return null;
        }
        internal static object Validate(PropertyEntry e,JToken requested)
        {
            if(!e.Writable)throw new ApiError("property_not_editable",e.Id+" has no certified write adapter. Query properties.describe for alternatives.");
            object value=PropertyValues.Convert(requested,e.ValueType,e.Min,e.Max,e.Id);
            if(e.Choices!=null&&!e.Choices.Values<string>().Contains(value as string))throw new ApiError("invalid_resource_id",e.Id+" must use a resource ID returned by properties.describe.");
            return value;
        }
        internal static JObject CurrentCondition(PropertyEntry e,bool live)
        {
            var result=new JObject{["satisfied"]=null,["reason"]=null,["errorCode"]=null,
                ["source"]="registered_adapter_current_prerequisites",
                ["meaning"]="Checks current prerequisite conditions only, not a proposed value, geometry, symmetry peers or successful execution. Re-query after prerequisite edits."};
            if(!live){result["reason"]="Requires a live designer part; isolated templates have no instantiated mounts or connected-part state.";return result;}
            try{ValidateConditions(e,e.RawValue());result["satisfied"]=true;}
            catch(ApiError ex){result["satisfied"]=ex.Code=="property_condition_failed"?(JToken)false:null;result["reason"]=ex.Message;result["errorCode"]=ex.Code;}
            catch(Exception ex){result["reason"]=ex.GetBaseException().Message;result["errorCode"]="condition_unavailable";}
            return result;
        }
        internal static void ValidateConditions(PropertyEntry e,object value)
        {
            if(e.Modifier is PistonData){var p=(PistonData)e.Modifier;bool attached=!p.Part.AttachPoints[p.AttachPointIndex].IsAvailable;
                if(attached&&(e.MemberName=="_extend"||(e.MemberName=="_range"&&!p.Extend)))throw new ApiError("property_condition_failed",e.Condition);
            }
            // Match native visibility-dependent mechanical constraints without opening UI.
            if(e.Modifier is GearLegData||e.Modifier is GearBayData||e.Modifier is JointRotatorData){
                var c=new ConfigurableProperty(e.Member,e.Attribute);c.SetCurrentPartModifier(e.Modifier,e.Modifier);
                if(!c.IsVisible())throw new ApiError("property_condition_failed",e.Id+" is unavailable for the current native configuration; set its prerequisite in an earlier operation.");
            }
            if(e.Modifier is PartTargetingData&&e.MemberName=="_customPartIds"){
                var p=(PartTargetingData)e.Modifier;
                if(p.TargetMode.ToString()!="Custom")throw new ApiError("property_condition_failed","Set targetMode to Custom in an earlier operation.");
                foreach(int id in (List<int>)value)if(p.Part.PartScript.Aircraft.Aircraft.Assembly.GetPartById(id)==null)throw new ApiError("part_not_found","Target part "+id+" does not exist.");
            }
        }
        internal static int[] Set(PropertyEntry e,object value,bool symmetric)
        {
            var c=new ConfigurableProperty(e.Member,e.Attribute);c.SetCurrentPartModifier(e.Modifier,e.Modifier);
            bool oldDisabled=e.Modifier.SymmetryDisabled;
            try{
                if(!symmetric)e.Modifier.SymmetryDisabled=true;
                var targets=symmetric?c.GetSymmetricModifiers(true).Select(x=>x.PartModifier).ToArray():new[]{e.Modifier};
                if(e.Modifier is TextureDecalData&&e.MemberName=="_decalId"){
                    foreach(var m in targets){((TextureDecalData)m).CraftDecalData=SP2Game.Instance.CraftDecalManager.GetDecalData((string)value);m.OnGenericDesignerPropertyChanged(e.MemberName,(string)value);}
                }else{
                    // Same setter + per-modifier callback sequence as the native UI.
                    c.SetValue(value,false,symmetric,false);
                    foreach(var m in targets)m.OnGenericDesignerPropertyChanged(e.MemberName,System.Convert.ToString(value,CultureInfo.InvariantCulture));
                }
                return targets.Select(x=>x.Part.Id).Distinct().ToArray();
            }finally{e.Modifier.SymmetryDisabled=oldDisabled;}
        }
    }
}
