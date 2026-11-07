using System;
#if !NATIVE_INPUT_SAFETY_CORE_TEST
using Assets.Scripts.Design;
using Assets.Scripts.Design.UI;
using HarmonyLib;
using Newtonsoft.Json.Linq;
#endif

namespace SP2BuildAssistant
{
    // Ownership and scheduling only; no native calls or input polling here.
    internal sealed class DeferredNativeSavePolicy
    {
        internal string PendingSession { get; private set; }
        internal object PendingScript { get; private set; }
        internal bool Pending { get { return PendingScript != null; } }
        internal double RequestedAtMs { get; private set; }
        internal long Requests, CoalescedRequests, ExpiredRequests, SaveAttempts, FailedAttempts;
        internal string LastOutcome { get; private set; }
        internal string LastReason { get; private set; }
        internal bool Request(string session, object script, double nowMs)
        {
            Requests++;
            if (string.IsNullOrEmpty(session) || script == null) {
                ExpiredRequests++; LastOutcome = "unbound_request_discarded"; LastReason = "No captured designer session and script; never bind an old request to a later craft."; return false;
            }
            if (Pending && PendingSession == session && ReferenceEquals(PendingScript, script)) {
                CoalescedRequests++; LastOutcome = "same_session_request_coalesced"; return true;
            }
            if (Pending) Expire("superseded_by_a_separately_bound_native_request");
            PendingSession = session; PendingScript = script; RequestedAtMs = nowMs;
            LastOutcome = "deferred"; LastReason = "atomic_input_gate_closed"; return true;
        }
        private void Expire(string reason)
        {
            PendingSession = null; PendingScript = null; ExpiredRequests++;
            LastOutcome = "expired_without_saving"; LastReason = reason;
        }
        internal bool CanDrain(string session, object script, bool sceneReady, bool inputGateOpen, bool idle,
            string unsafeActivityReason, out string reason)
        {
            if (!Pending) { reason = "no_pending_native_save"; return false; }
            if (PendingSession != session || !ReferenceEquals(PendingScript, script)) {
                reason = "designer_session_or_script_changed"; Expire(reason); return false;
            }
            if (!sceneReady) { reason = "designer_scene_unavailable"; Expire(reason); return false; }
            reason = !inputGateOpen ? "atomic_input_gate_closed" : !idle ? "native_command_running" : unsafeActivityReason;
            if (reason != null) { LastReason = reason; return false; }
            return true;
        }
        internal bool TryTake(string session, object script, bool sceneReady, bool inputGateOpen, bool idle,
            string unsafeActivityReason, out string reason)
        {
            if (!CanDrain(session, script, sceneReady, inputGateOpen, idle, unsafeActivityReason, out reason)) return false;
            PendingSession = null; PendingScript = null; SaveAttempts++;
            LastOutcome = "native_save_attempt_started"; LastReason = null; return true;
        }
        internal void SaveCompleted(bool succeeded, string reason = null)
        {
            if (!succeeded) FailedAttempts++;
            LastOutcome = succeeded ? "native_save_returned" : "native_save_failed_no_automatic_retry";
            LastReason = reason;
        }
        internal void DiscardPending(string reason)
        {
            if (Pending) Expire(reason);
        }
        internal double PendingAgeMs(double nowMs) { return Pending ? Math.Max(0, nowMs - RequestedAtMs) : 0; }
    }

#if !NATIVE_INPUT_SAFETY_CORE_TEST
    public sealed partial class BuildRuntime
    {
        private static BuildRuntime nativeInputRuntime;
        private readonly DeferredNativeSavePolicy deferredNativeSave = new DeferredNativeSavePolicy();

        [HarmonyPatch(typeof(DesignerUIScript), "HandleKeyboardShortcuts")]
        private static class PauseNativeUiShortcuts
        {
            private static bool Prefix() { return !Writing && !AcceptanceInputBlocked; }
        }
        [HarmonyPatch(typeof(TransformToolPanelScript), "Update")]
        private static class PauseNativeTransformPanelInput
        {
            private static bool Prefix() { return !Writing && !AcceptanceInputBlocked; }
        }
        [HarmonyPatch(typeof(DesignerScript), "SaveDesignerCraft")]
        private static class DeferAtomicNativeEditorSave
        {
            private static bool Prefix(DesignerScript __instance)
            {
                if (!Writing && !AcceptanceInputBlocked) return true;
                var runtime = nativeInputRuntime;
                // A product mutation observes its session before entering its
                // atomic boundary. Never invent a binding during that boundary.
                if (runtime != null) runtime.deferredNativeSave.Request(runtime.session, __instance, InteractiveNowMs);
                return false;
            }
        }
        internal void DrainDeferredNativeSave()
        {
            nativeInputRuntime = this;
            if (!deferredNativeSave.Pending) return;
            var designer = Designer.Instance;
            var script = designer == null ? null : designer.DesignerScript;
            bool ready = DesignerReady();
            bool gateOpen = !Writing && !AcceptanceInputBlocked;
            string reason;
            string activity = interactiveWindow.BlockingReason(InteractiveNowMs, UnityEngine.Time.frameCount);
            if (!deferredNativeSave.CanDrain(session, script, ready, gateOpen, !busy, activity, out reason)) return;
            try {
                // DesignerScript can survive a normal user Load/New. Observe
                // first to discover the new Aircraft/session before consuming
                // the request. Internal verified rebuilds preserve the session.
                Observe();
                designer = Designer.Instance; script = designer == null ? null : designer.DesignerScript;
                if (!deferredNativeSave.TryTake(session, script, DesignerReady(), !Writing && !AcceptanceInputBlocked,
                    !busy, interactiveWindow.BlockingReason(InteractiveNowMs, UnityEngine.Time.frameCount), out reason)) return;
                script.SaveDesignerCraft();
                // Native AutoRecenter/shared changes invalidate old scopes via
                // normal Observe/Validate. Never refresh their captured guards.
                Observe(); deferredNativeSave.SaveCompleted(true);
            } catch (Exception error) {
                string failure = error.GetType().Name + ": " + error.Message;
                if (deferredNativeSave.Pending) deferredNativeSave.DiscardPending("native_identity_observation_failed: " + failure);
                else deferredNativeSave.SaveCompleted(false, failure);
                if (Log != null) Log.LogWarning("Deferred native editor save failed; inspect current state before retrying: " + error.Message);
            }
        }
        internal JObject NativeInputSafetyView()
        {
            return new JObject {
                ["foregroundInput"] = ForegroundInputGuard.View(),
                ["nativeUiKeyboardGate"] = "DesignerUIScript.HandleKeyboardShortcuts only; normal UI refresh remains enabled",
                ["nativeTransformPanelKeyboardGate"] = "TransformToolPanelScript.Update during the atomic boundary",
                ["deferredNativeEditorSave"] = new JObject {
                    ["pending"] = deferredNativeSave.Pending, ["pendingCraftSessionId"] = deferredNativeSave.PendingSession,
                    ["pendingAgeMs"] = deferredNativeSave.PendingAgeMs(InteractiveNowMs), ["requests"] = deferredNativeSave.Requests,
                    ["coalescedRequests"] = deferredNativeSave.CoalescedRequests, ["expiredRequests"] = deferredNativeSave.ExpiredRequests,
                    ["nativeSaveAttempts"] = deferredNativeSave.SaveAttempts, ["failedAttempts"] = deferredNativeSave.FailedAttempts,
                    ["lastOutcome"] = deferredNativeSave.LastOutcome, ["lastReason"] = deferredNativeSave.LastReason,
                    ["meaning"] = "Only SaveDesignerCraft calls during the atomic gate are deferred, merged within their session/script, then consumed once while idle and user-safe. Explicit CLI Designer.Save is unchanged. A normal native return does not prove disk persistence. Expired requests never save another craft; failures require inspection rather than automatic retry."
                }
            };
        }
    }
#endif
}
