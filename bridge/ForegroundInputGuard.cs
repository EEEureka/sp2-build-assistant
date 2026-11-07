using System;
#if !FOREGROUND_INPUT_CORE_TEST
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.InteropServices;
using Assets.Scripts.Design;
using Assets.Scripts.Design.UI;
using Assets.Scripts.Input;
using Assets.Scripts.UI;
using BepInEx.Logging;
using HarmonyLib;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.EventSystems;
#endif

namespace SP2BuildAssistant
{
    // Focus transitions must not deliver a key held in another application.
    internal sealed class ForegroundInputPolicy
    {
        private bool focused, armed;
        private int quietFrame = -1;
        internal string Reason { get; private set; } = "not_sampled";
        internal bool Allow(bool ownsForeground, bool held, int frame)
        {
            if (!ownsForeground) {
                focused = armed = false; quietFrame = -1;
                Reason = "application_not_foreground"; return false;
            }
            if (!focused) { focused = true; armed = false; quietFrame = -1; }
            if (!armed) {
                if (held) { quietFrame = -1; Reason = "waiting_for_key_and_pointer_release"; return false; }
                if (quietFrame < 0) quietFrame = frame;
                if ((long)frame <= (long)quietFrame + 1) { Reason = "focus_return_quiet_frames"; return false; }
                armed = true;
            }
            Reason = null; return true;
        }
    }

#if !FOREGROUND_INPUT_CORE_TEST
    // Also compiled as a small standalone hotfix for the released 0.7.2 plugin.
    // No server, save/load action, input injection, or activation of a window.
    public static class ForegroundInputGuard
    {
        public const string Owner = "local.sp2.buildassistant.foreground-input";
        private static readonly ForegroundInputPolicy policy = new ForegroundInputPolicy();
        private static readonly int pid = Process.GetCurrentProcess().Id;
        private static Harmony harmony;
        private static int nativeTargets, legacyTargets;
        private static long blockedReads, blockedCallbacks;
        private static readonly Dictionary<MethodInfo, MethodInfo> replacements = LegacyReplacements();
        private static readonly Dictionary<short, OpCode> opcodes = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)).ToDictionary(o => o.Value);
        [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

        public static bool OwnsForeground()
        {
            // Batch mode can report Application.isFocused=true without any game
            // window being foreground. It never needs physical input.
            if (Application.isBatchMode || !Application.isFocused) return false;
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) return true;
            try {
                uint foregroundPid;
                var window = GetForegroundWindow();
                return window != IntPtr.Zero && GetWindowThreadProcessId(window, out foregroundPid) != 0 && foregroundPid == pid;
            } catch { return false; }
        }
        public static bool InputAllowed()
        {
            bool foreground = OwnsForeground();
            bool held = foreground && (UnityEngine.Input.anyKey || UnityEngine.Input.GetMouseButton(0) ||
                UnityEngine.Input.GetMouseButton(1) || UnityEngine.Input.GetMouseButton(2));
            return policy.Allow(foreground, held, Time.frameCount);
        }
        public static void FocusLost() { policy.Allow(false, false, Time.frameCount); }
        private static bool ReadAllowed() { bool allow = InputAllowed(); if (!allow) blockedReads++; return allow; }
        private static bool CallbackAllowed() { bool allow = InputAllowed(); if (!allow) blockedCallbacks++; return allow; }
        private static bool BoolInput(ref bool __result) { if (ReadAllowed()) return true; __result = false; return false; }
        private static bool AxisInput(ref float __result) { if (ReadAllowed()) return true; __result = 0f; return false; }
        private static void Patch(MethodInfo method, string prefix)
        {
            if (method == null) throw new MissingMethodException("Foreground guard native input entry point changed.");
            harmony.Patch(method, prefix: new HarmonyMethod(typeof(ForegroundInputGuard), prefix) { priority = Priority.First });
            nativeTargets++;
        }
        public static void Install(ManualLogSource log)
        {
            if (harmony != null || Harmony.HasAnyPatches(Owner)) {
                log.LogInfo("Foreground input guard already installed; duplicate patching skipped."); return;
            }
            harmony = new Harmony(Owner);
            try {
                foreach (var m in typeof(GameInput).GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)) {
                    if (m.GetParameters().Length != 0) continue;
                    if (m.Name.StartsWith("GetButton", StringComparison.Ordinal) && m.ReturnType == typeof(bool)) Patch(m, "BoolInput");
                    if (m.Name.StartsWith("GetAxis", StringComparison.Ordinal) && m.ReturnType == typeof(float)) Patch(m, "AxisInput");
                }
                foreach (var m in typeof(InputWrapper).GetMethods(BindingFlags.Public | BindingFlags.Static)) {
                    if (m.Name == "GetButton" || m.Name == "GetButtonDown" || m.Name == "GetButtonUp") Patch(m, "BoolInput");
                    if (m.Name == "GetAxis") Patch(m, "AxisInput");
                }
                Patch(typeof(UserInterface).GetProperty("AllowKeyboardInputs").GetGetMethod(), "BoolInput");
                foreach (string name in new[] { "HandleInput", "HandleScroll", "HandlePinch", "MouseHover" })
                    Patch(AccessTools.Method(typeof(Designer), name), "CallbackAllowed");
                // Do not suppress Designer/DesignerScript.Update or ordinary UI
                // refresh: native settlement, rendering and API work must continue.
                Patch(AccessTools.Method(typeof(DesignerUIScript), "HandleKeyboardShortcuts"), "CallbackAllowed");
                Patch(AccessTools.Method(typeof(TransformToolPanelScript), "Update"), "CallbackAllowed");
                Patch(AccessTools.Method(typeof(EventSystem), "Update"), "CallbackAllowed");
                // Replace only legacy input reads in game methods. Dialog timers,
                // UI refresh and non-input logic still execute while unfocused.
                foreach (var type in typeof(Designer).Assembly.GetTypes())
                    foreach (var method in type.GetMethods(BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public |
                        BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
                        if (!method.ContainsGenericParameters && UsesLegacyInput(method)) {
                            harmony.Patch(method, transpiler: new HarmonyMethod(typeof(ForegroundInputGuard), "FilterLegacyInput"));
                            legacyTargets++;
                        }
                log.LogInfo("Foreground input guard installed: " + nativeTargets + " native gates, " + legacyTargets +
                    " legacy input readers; Windows foreground PID + Unity focus, batch input denied.");
            } catch {
                harmony.UnpatchSelf(); harmony = null; nativeTargets = legacyTargets = 0; throw;
            }
        }
        public static void Uninstall() { if (harmony != null) harmony.UnpatchSelf(); harmony = null; }
        public static JObject View()
        {
            return new JObject { ["enabled"] = Harmony.HasAnyPatches(Owner), ["ownsForeground"] = OwnsForeground(),
                ["unityFocused"] = Application.isFocused, ["batchMode"] = Application.isBatchMode,
                ["inputAllowed"] = InputAllowed(), ["reason"] = policy.Reason,
                ["nativeGateCount"] = nativeTargets, ["legacyReaderCount"] = legacyTargets,
                ["blockedReads"] = blockedReads, ["blockedCallbacks"] = blockedCallbacks,
                ["focusSource"] = "Windows foreground process AND Unity focus; batch mode always blocked",
                ["focusReturn"] = "Release all keys/buttons, then two quiet frames before rearming",
                ["bridgeAndRenderingContinue"] = true, ["desktopInputInjected"] = false };
        }
        private static Dictionary<MethodInfo, MethodInfo> LegacyReplacements()
        {
            var map = new Dictionary<MethodInfo, MethodInfo>();
            foreach (var replacement in typeof(ForegroundInputGuard).GetMethods(BindingFlags.NonPublic | BindingFlags.Static)) {
                if (!replacement.Name.StartsWith("Legacy_", StringComparison.Ordinal)) continue;
                var original = typeof(UnityEngine.Input).GetMethod(replacement.Name.Substring(7),
                    BindingFlags.Public | BindingFlags.Static, null, replacement.GetParameters().Select(p => p.ParameterType).ToArray(), null);
                if (original == null || original.ReturnType != replacement.ReturnType)
                    throw new MissingMethodException("Legacy input signature changed: " + replacement.Name);
                map.Add(original, replacement);
            }
            return map;
        }
        private static bool UsesLegacyInput(MethodInfo method)
        {
            var body = method.GetMethodBody(); if (body == null) return false;
            var il = body.GetILAsByteArray();
            for (int pos = 0; pos < il.Length;) {
                short value = il[pos++]; if (value == 0xfe) value = (short)(0xfe00 | il[pos++]);
                OpCode op; if (!opcodes.TryGetValue(value, out op)) throw new InvalidOperationException("Unknown IL opcode.");
                if (op.OperandType == OperandType.InlineMethod && (op == OpCodes.Call || op == OpCodes.Callvirt)) {
                    var target = method.Module.ResolveMethod(BitConverter.ToInt32(il, pos), method.DeclaringType.GetGenericArguments(), null) as MethodInfo;
                    if (target != null && replacements.ContainsKey(target)) return true;
                }
                switch (op.OperandType) {
                    case OperandType.InlineNone: break;
                    case OperandType.ShortInlineBrTarget: case OperandType.ShortInlineI: case OperandType.ShortInlineVar: pos += 1; break;
                    case OperandType.InlineVar: pos += 2; break;
                    case OperandType.InlineI8: case OperandType.InlineR: pos += 8; break;
                    case OperandType.InlineSwitch: pos += 4 + 4 * BitConverter.ToInt32(il, pos); break;
                    default: pos += 4; break;
                }
            }
            return false;
        }
        private static IEnumerable<CodeInstruction> FilterLegacyInput(IEnumerable<CodeInstruction> instructions)
        {
            foreach (var code in instructions) {
                MethodInfo replacement;
                if ((code.opcode == OpCodes.Call || code.opcode == OpCodes.Callvirt) && code.operand is MethodInfo &&
                    replacements.TryGetValue((MethodInfo)code.operand, out replacement)) {
                    code.opcode = OpCodes.Call; code.operand = replacement;
                }
                yield return code;
            }
        }
        private static bool Legacy_GetKey(KeyCode key) { return ReadAllowed() && UnityEngine.Input.GetKey(key); }
        private static bool Legacy_GetKey(string key) { return ReadAllowed() && UnityEngine.Input.GetKey(key); }
        private static bool Legacy_GetKeyDown(KeyCode key) { return ReadAllowed() && UnityEngine.Input.GetKeyDown(key); }
        private static bool Legacy_GetKeyDown(string key) { return ReadAllowed() && UnityEngine.Input.GetKeyDown(key); }
        private static bool Legacy_GetKeyUp(KeyCode key) { return ReadAllowed() && UnityEngine.Input.GetKeyUp(key); }
        private static bool Legacy_GetKeyUp(string key) { return ReadAllowed() && UnityEngine.Input.GetKeyUp(key); }
        private static bool Legacy_GetMouseButton(int button) { return ReadAllowed() && UnityEngine.Input.GetMouseButton(button); }
        private static bool Legacy_GetMouseButtonDown(int button) { return ReadAllowed() && UnityEngine.Input.GetMouseButtonDown(button); }
        private static bool Legacy_GetMouseButtonUp(int button) { return ReadAllowed() && UnityEngine.Input.GetMouseButtonUp(button); }
        private static bool Legacy_GetButton(string button) { return ReadAllowed() && UnityEngine.Input.GetButton(button); }
        private static bool Legacy_GetButtonDown(string button) { return ReadAllowed() && UnityEngine.Input.GetButtonDown(button); }
        private static bool Legacy_GetButtonUp(string button) { return ReadAllowed() && UnityEngine.Input.GetButtonUp(button); }
        private static float Legacy_GetAxis(string axis) { return ReadAllowed() ? UnityEngine.Input.GetAxis(axis) : 0f; }
        private static float Legacy_GetAxisRaw(string axis) { return ReadAllowed() ? UnityEngine.Input.GetAxisRaw(axis) : 0f; }
        private static bool Legacy_get_anyKey() { return ReadAllowed() && UnityEngine.Input.anyKey; }
        private static bool Legacy_get_anyKeyDown() { return ReadAllowed() && UnityEngine.Input.anyKeyDown; }
        private static string Legacy_get_inputString() { return ReadAllowed() ? UnityEngine.Input.inputString : ""; }
        private static Vector2 Legacy_get_mouseScrollDelta() { return ReadAllowed() ? UnityEngine.Input.mouseScrollDelta : Vector2.zero; }
    }
#if STANDALONE_INPUT_GUARD
    [BepInEx.BepInPlugin("local.sp2.foregroundinputguard", "SP2 Foreground Input Guard", "0.7.2.1")]
    public sealed class ForegroundInputGuardPlugin : BepInEx.BaseUnityPlugin
    {
        private void Awake() { ForegroundInputGuard.Install(Logger); }
        private void OnApplicationFocus(bool focused) { if (!focused) ForegroundInputGuard.FocusLost(); }
        private void OnApplicationPause(bool paused) { if (paused) ForegroundInputGuard.FocusLost(); }
        private void OnDestroy() { ForegroundInputGuard.Uninstall(); }
    }
#endif
#endif
}
