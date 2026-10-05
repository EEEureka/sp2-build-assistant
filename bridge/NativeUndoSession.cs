using Assets.Scripts.Craft;
using Assets.Scripts.Design;
using HarmonyLib;
using UnityEngine;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        // Native Undo/Redo replaces AircraftScript synchronously, without loading
        // another craft. Track only this exact native path; a name/fingerprint
        // match must never let a separately loaded craft reuse session handles.
        private sealed class NativeUndoObservation
        {
            internal BuildRuntime Runtime;
            internal AircraftScript Before;
            internal string Session;
        }

        [HarmonyPatch(typeof(Designer), "RestoreFromUndoStep")]
        private static class RetainNativeUndoSession
        {
            private static void Prefix(Designer __instance, out NativeUndoObservation __state)
            {
                __state = null;
                var runtime = Object.FindObjectOfType<BuildRuntime>();
                if (runtime == null || Writing || runtime.session == null ||
                    Designer.Instance != __instance || runtime.observedAircraft != __instance.Aircraft) return;
                __state = new NativeUndoObservation { Runtime = runtime,
                    Before = __instance.Aircraft, Session = runtime.session };
            }

            private static void Postfix(Designer __instance, NativeUndoObservation __state)
            {
                if (__state == null || __state.Runtime == null || Designer.Instance != __instance ||
                    __instance.Aircraft == null || !__instance.Aircraft.gameObject.activeInHierarchy) return;
                var runtime = __state.Runtime;
                if (runtime.session != __state.Session ||
                    !ReferenceEquals(runtime.observedAircraft, __state.Before)) return;
                runtime.observedAircraft = __instance.Aircraft;
                // Leave the old fingerprint/revision until Observe samples the
                // restored state. Existing guards must reject stale revisions.
                // Preserve uncertain state too: native Undo is not a verified
                // recovery of a previously failed plugin transaction.
            }
        }
    }
}
