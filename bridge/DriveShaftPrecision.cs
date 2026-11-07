using System;
using System.Globalization;
using System.Runtime.CompilerServices;
using System.Xml.Linq;
using Assets.Scripts.Craft.Parts.Modifiers.Powertrain;
using Assets.Scripts.Craft;
using System.Linq;
using HarmonyLib;
using UnityEngine;

namespace SP2BuildAssistant
{
    // Native GenerateStateXml passes Vector3 to XElement, which formats each
    // component to two decimals. Preserve explicitly loaded sub-centimetre
    // author endpoints instead of silently losing them on save/reopen. Native
    // two-decimal inputs keep their existing serialization and gameplay path.
    internal static class DriveShaftPrecision
    {
        private sealed class Marker {}
        private static readonly ConditionalWeakTable<JDriveShaftData,Marker> precise=new ConditionalWeakTable<JDriveShaftData,Marker>();
        internal static bool Preserves(JDriveShaftData data){Marker marker;return precise.TryGetValue(data,out marker);}
        private static bool SubCentimetre(Vector3 v)
        {return v.x!=(float)Math.Round(v.x,2)||v.y!=(float)Math.Round(v.y,2)||v.z!=(float)Math.Round(v.z,2);}
        internal static void Observe(JDriveShaftData data)
        {
            if(data.IsVisual&&(SubCentimetre(data.LocalAttachStart)||SubCentimetre(data.LocalAttachEnd)))precise.GetValue(data,_=>new Marker());
        }
        private static string Roundtrip(Vector3 v)
        {return string.Join(",",v.x.ToString("R",CultureInfo.InvariantCulture),v.y.ToString("R",CultureInfo.InvariantCulture),v.z.ToString("R",CultureInfo.InvariantCulture));}
        internal static void Serialize(JDriveShaftData data,XElement state)
        {
            Marker marker;if(state==null||!data.IsVisual||!precise.TryGetValue(data,out marker))return;
            // The original method already called OnSaveState, so these are the
            // actual current local native handles, never a cached target value.
            state.SetAttributeValue("start",Roundtrip(data.LocalAttachStart));state.SetAttributeValue("end",Roundtrip(data.LocalAttachEnd));
        }
    }
    [HarmonyPatch(typeof(JDriveShaftData),nameof(JDriveShaftData.RestoreFromState))]
    internal static class DriveShaftRestorePrecisionPatch
    {private static void Postfix(JDriveShaftData __instance){DriveShaftPrecision.Observe(__instance);}}
    [HarmonyPatch(typeof(JDriveShaftData),nameof(JDriveShaftData.GenerateStateXml))]
    internal static class DriveShaftSavePrecisionPatch
    {private static void Postfix(JDriveShaftData __instance,XElement __result){DriveShaftPrecision.Serialize(__instance,__result);}}

    [HarmonyPatch(typeof(JDriveShaftScript),"UpdateBeam")]
    internal static class DriveShaftFreeBeamPrecisionPatch
    {
        internal sealed class BeamState
        {internal Transform Root;internal Vector3 Position,Start,End;internal bool Symmetric;}
        private static void Prefix(JDriveShaftScript __instance,Vector3 left,Vector3 right,out BeamState __state)
        {
            __state=null;var data=__instance.Data;var part=data?.Part;
            if(data==null||!data.IsVisual||!DriveShaftPrecision.Preserves(data)||part?.PartScript==null||part.PartScript.LoadContext!=CraftLoadContext.Designer||part.AttachPoints.Any(p=>p.PartConnections.Count!=0))return;
            var points=part.PartScript.AttachPointScripts;if(points.Count<2)return;
            if(!left.Equals(points[0].transform.position)||!right.Equals(points[1].transform.position))return;
            var a=points[0].transform.localPosition;var b=points[1].transform.localPosition;
            __state=new BeamState{Root=part.PartScript.transform,Position=part.PartScript.transform.position,Start=a,End=b,Symmetric=a.Equals(-b)};
        }
        private static void Postfix(JDriveShaftScript __instance,Vector3 left,Vector3 right,BeamState __state)
        {
            if(__state==null)return;var points=__instance.Data.Part.PartScript.AttachPointScripts;
            if(__state.Symmetric){
                // An already centred free beam needs no second world-space
                // midpoint rounding. Keep authored local handles/pose exact.
                __state.Root.position=__state.Position;
                points[0].transform.localPosition=__state.Start;points[1].transform.localPosition=__state.End;
            }else{
                // First native recentre of an edited free beam. Express the
                // resulting beam with exact opposite local half-vectors, so
                // future native reloads retain author state without tolerances.
                var half=__state.Root.InverseTransformVector((right-left)*.5f);
                points[0].transform.localPosition=-half;points[1].transform.localPosition=half;
            }
        }
    }
}
