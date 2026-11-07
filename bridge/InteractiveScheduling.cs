using System;
#if !INTERACTIVE_SCHEDULING_CORE_TEST
using System.Diagnostics;
using System.Linq;
using Assets.Scripts.Design;
using Assets.Scripts.Design.Tools;
using Newtonsoft.Json.Linq;
using UnityEngine;
#endif

namespace SP2BuildAssistant
{
    // Time and frame based policy only. This class never polls or injects input.
    internal sealed class InteractiveWindow
    {
        internal readonly double MinimumQuietMs, MinimumBetweenChunksMs;
        internal bool Focused { get; private set; }
        internal string ActivityReason { get; private set; }
        internal string LastActivityReason { get; private set; }
        internal double LastActivityMs { get; private set; } = double.NegativeInfinity;
        internal double LastChunkEndMs { get; private set; } = double.NegativeInfinity;
        internal int LastChunkEndFrame { get; private set; } = -2;
        internal double TotalDeferredMs { get; private set; }
        internal double MaxDeferredMs { get; private set; }
        private double pauseStartedMs = double.NaN;
        private bool sampled;

        internal InteractiveWindow(double minimumQuietMs = 150, double minimumBetweenChunksMs = 100)
        {
            if (!Finite(minimumQuietMs) || minimumQuietMs < 150 || !Finite(minimumBetweenChunksMs) || minimumBetweenChunksMs < 100)
                throw new ArgumentOutOfRangeException("Interactive windows require quiet >=150ms and chunk spacing >=100ms.");
            MinimumQuietMs = minimumQuietMs; MinimumBetweenChunksMs = minimumBetweenChunksMs;
        }
        private static bool Finite(double value) { return !double.IsNaN(value) && !double.IsInfinity(value); }
        internal void Sample(double nowMs, bool focused, bool keyOrMouseHeld, bool mouseMoved,
            bool scrollChanged, bool textInputFocused, bool dialogOpen, bool nativeGestureActive, bool samplingFailed = false,
            bool unadaptedToolActive = false, bool externalTransformActive = false)
        {
            if (!Finite(nowMs)) throw new ArgumentOutOfRangeException("nowMs");
            bool focusEntered = focused && (!sampled || !Focused);
            Focused = focused; sampled = true;
            // UI and native gestures are safety state, even if the app lost focus.
            // Legacy Input noise in an unfocused app must not starve background jobs.
            ActivityReason = samplingFailed ? "activity_state_unavailable" :
                externalTransformActive ? "native_external_transform_active" : unadaptedToolActive ? "native_stateful_tool_active" :
                nativeGestureActive ? "native_gesture_active" : textInputFocused ? "native_text_input_focused" :
                dialogOpen ? "native_dialog_open" : focused && keyOrMouseHeld ? "held_key_or_mouse_button" :
                focused && scrollChanged ? "mouse_scroll_activity" : focused && mouseMoved ? "mouse_pointer_activity" :
                focusEntered ? "application_focus_entered" : null;
            if (ActivityReason != null) { LastActivityMs = nowMs; LastActivityReason = ActivityReason; }
        }
        internal void ChunkCompleted(double nowMs, int frame)
        {
            if (!Finite(nowMs) || frame < 0) throw new ArgumentOutOfRangeException("chunk completion");
            LastChunkEndMs = nowMs; LastChunkEndFrame = frame;
        }
        internal string BlockingReason(double nowMs, int frame)
        {
            if (ActivityReason != null) return ActivityReason;
            if (nowMs - LastActivityMs < MinimumQuietMs) return "waiting_for_user_quiet_window";
            if (nowMs - LastChunkEndMs < MinimumBetweenChunksMs) return "minimum_time_between_chunks";
            // The whole next frame belongs to native input, irrespective of FPS.
            if (LastChunkEndFrame >= 0 && (long)frame <= (long)LastChunkEndFrame + 1) return "minimum_native_input_frame";
            return null;
        }
        internal static bool CanPreserveTool(string typeName)
        {
            return typeName == "ViewTool" || typeName == "MovePartTool" || typeName == "TranslateTool" || typeName == "RotateTool" || typeName == "ColorTool";
        }
        internal bool CanDispatch(string command, double nowMs, int frame, out string reason, bool cancellationRequested = false)
        {
            // Delayed scoped work must never hold up reads or lifecycle commands.
            if (command != "scoped.batch.apply" || cancellationRequested) { reason = null; return true; }
            reason = BlockingReason(nowMs, frame);
            if (reason != null) {
                if (double.IsNaN(pauseStartedMs)) pauseStartedMs = nowMs;
                MaxDeferredMs = Math.Max(MaxDeferredMs, Math.Max(0, nowMs - pauseStartedMs));
                return false;
            }
            if (!double.IsNaN(pauseStartedMs)) {
                double elapsed = Math.Max(0, nowMs - pauseStartedMs);
                TotalDeferredMs += elapsed; MaxDeferredMs = Math.Max(MaxDeferredMs, elapsed); pauseStartedMs = double.NaN;
            }
            return true;
        }
        internal double PausedMs(double nowMs) { return double.IsNaN(pauseStartedMs) ? 0 : Math.Max(0, nowMs - pauseStartedMs); }
        internal double QuietRemainingMs(double nowMs) { return Math.Max(0, MinimumQuietMs - (nowMs - LastActivityMs)); }
        internal double ChunkSpacingRemainingMs(double nowMs) { return Math.Max(0, MinimumBetweenChunksMs - (nowMs - LastChunkEndMs)); }
    }

#if !INTERACTIVE_SCHEDULING_CORE_TEST
    public sealed partial class BuildRuntime
    {
        private readonly InteractiveWindow interactiveWindow = new InteractiveWindow();
        private bool interactivePointerSampled;
        private Vector3 interactiveLastPointer;
        private static double InteractiveNowMs { get { return Stopwatch.GetTimestamp() * 1000d / Stopwatch.Frequency; } }

        internal void SampleInteractiveActivity()
        {
            bool focused = ForegroundInputGuard.OwnsForeground(), held = false, moved = false, scrolled = false;
            bool text = false, dialog = false, gesture = false, failed = false, statefulTool = false, externalTransform = false;
            try {
                if (focused) {
                    held = UnityEngine.Input.anyKey || UnityEngine.Input.anyKeyDown || Enumerable.Range(0, 3).Any(i =>
                        UnityEngine.Input.GetMouseButton(i) || UnityEngine.Input.GetMouseButtonDown(i) || UnityEngine.Input.GetMouseButtonUp(i));
                    var pointer = UnityEngine.Input.mousePosition;
                    moved = interactivePointerSampled && (pointer - interactiveLastPointer).sqrMagnitude > .25f;
                    interactiveLastPointer = pointer; interactivePointerSampled = true;
                    scrolled = UnityEngine.Input.mouseScrollDelta.sqrMagnitude > .00000001f;
                } else interactivePointerSampled = false;
                // Avoid initializing lazy Game.Instance during startup.
                var designer = Designer.Instance;
                if (designer != null && designer.Aircraft != null && designer.Aircraft.gameObject.activeInHierarchy) {
                    var ui = Assets.Scripts.Game.Instance.UserInterface;
                    text = ui.IsTextInputFocused; dialog = ui.AnyDialogsOpen;
                    gesture = designer.Aircraft.Aircraft.Assembly.Parts.Any(p => p.PartScript != null && p.PartScript.IsDragging);
                    var tool = designer.Tools.SelectedTool;
                    statefulTool = tool != null && (tool.GetType().Namespace != "Assets.Scripts.Design.Tools" || !InteractiveWindow.CanPreserveTool(tool.GetType().Name));
                    gesture |= tool != null && tool.ViewPortIsMoving;
                    var transform = tool as TransformTool;
                    gesture |= transform != null && transform.SelectedAxis != null;
                    externalTransform = designer.Tools.TranslateTool.IsExternalTargetActive || designer.Tools.RotateTool.IsExternalTargetActive;
                }
            } catch (Exception) { failed = true; }
            interactiveWindow.Sample(InteractiveNowMs, focused, held, moved, scrolled, text, dialog, gesture, failed, statefulTool, externalTransform);
        }
        internal bool CanDispatchScoped(Job job, out string reason, bool allowCancellationExit = true)
        {
            bool cancelled; lock (job.Sync) cancelled = allowCancellationExit && job.CancelRequested;
            return interactiveWindow.CanDispatch((string)job.Input["command"], InteractiveNowMs, Time.frameCount, out reason, cancelled);
        }
        internal void MarkInteractiveChunkCompleted()
        {
            interactiveWindow.ChunkCompleted(InteractiveNowMs, Time.frameCount);
        }
        internal JObject InteractiveSchedulingView()
        {
            double now = InteractiveNowMs;
            return new JObject {
                ["mode"] = "passive_user_activity_aware_scoped_dispatch", ["focused"] = interactiveWindow.Focused,
                ["minimumQuietMs"] = interactiveWindow.MinimumQuietMs, ["minimumBetweenChunksMs"] = interactiveWindow.MinimumBetweenChunksMs,
                ["minimumNativeInputFrames"] = 1, ["activityReason"] = interactiveWindow.ActivityReason,
                ["lastActivityReason"] = interactiveWindow.LastActivityReason, ["pauseReason"] = interactiveWindow.BlockingReason(now, Time.frameCount),
                ["pausedMs"] = interactiveWindow.PausedMs(now), ["maximumDeferredMs"] = Math.Max(interactiveWindow.MaxDeferredMs, interactiveWindow.PausedMs(now)),
                ["totalDeferredMs"] = interactiveWindow.TotalDeferredMs + interactiveWindow.PausedMs(now),
                ["quietRemainingMs"] = interactiveWindow.QuietRemainingMs(now), ["chunkSpacingRemainingMs"] = interactiveWindow.ChunkSpacingRemainingMs(now),
                ["lastChunkEndFrame"] = interactiveWindow.LastChunkEndFrame,
                ["meaning"] = "Passive activity postpones scoped mutations only; reads remain dispatchable. Delayed jobs must be requeued, not execute from an old baseline. This measures scheduling deferral, not input latency or visual acceptance."
            };
        }
    }
#endif
}
