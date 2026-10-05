// Separate test infrastructure: identical binary can accompany old/new bridges.
// Never packaged. Inert unless a batch-mode process explicitly opts in.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Xml.Linq;
using BepInEx;
using HarmonyLib;
using Newtonsoft.Json.Linq;
using UnityEngine;
using Assets.Scripts.Design;
using Assets.Scripts.Design.UI.PartProperties;
using Assets.Scripts.Craft.CraftFiles;
using SP2Game = Assets.Scripts.Game;

namespace SP2Acceptance
{
    [BepInPlugin("local.sp2.acceptancehost", "SP2 Background Acceptance Host", "1.0.7")]
    public sealed class Host : BaseUnityPlugin
    {
        private string root, token, phase="inactive", error;
        private float poll;
        private Harmony harmony;
        private bool loading;
        private int deniedSaves;
        private long blockedKeyboardChecks, blockedPointerEvents, blockedClipboardLoads;
        private static Host active;
        private void Awake()
        {
            root=Environment.GetEnvironmentVariable("SP2BUILD_TEST_HOST");
            token=Environment.GetEnvironmentVariable("SP2BUILD_TEST_TOKEN");
            if(!Application.isBatchMode || string.IsNullOrEmpty(root) || string.IsNullOrEmpty(token) || token.Length<32)return;
            root=Path.GetFullPath(root);
            Directory.CreateDirectory(root);
            active=this;
            Application.runInBackground=true;
            Application.targetFrameRate=60;
            QualitySettings.vSyncCount=0;
            harmony=new Harmony("local.sp2.acceptancehost");
            // The launcher requires the previous game to have exited. Use
            // original bridge transport code and ports for both benchmark
            // binaries; no bridge methods are patched by this host.
            var prefix=new HarmonyMethod(typeof(Host).GetMethod("DenySave",BindingFlags.Static|BindingFlags.NonPublic));
            foreach(var type in new[]{typeof(Designer),typeof(CraftDatabase)})
                foreach(var m in type.GetMethods(BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic)
                    .Where(m=>new[]{"Save","Autosave","Quicksave","SaveCraft"}.Contains(m.Name)))harmony.Patch(m,prefix:prefix);
            // Batch mode can still poll the desktop's physical keyboard.
            // Isolate this opted-in test process without injecting OS input or
            // changing the normal game's controls. Native API calls continue.
            var uiType=typeof(SP2Game).GetProperty("UserInterface").PropertyType;
            harmony.Patch(uiType.GetProperty("AllowKeyboardInputs").GetGetMethod(),
                prefix:new HarmonyMethod(typeof(Host).GetMethod("DenyKeyboard",BindingFlags.Static|BindingFlags.NonPublic)));
            harmony.Patch(typeof(Designer).GetMethod("HandleInput"),
                prefix:new HarmonyMethod(typeof(Host).GetMethod("DenyPointer",BindingFlags.Static|BindingFlags.NonPublic)));
            harmony.Patch(typeof(DesignerScript).GetMethod("LoadAircraftFromClipboardOrUrl"),
                prefix:new HarmonyMethod(typeof(Host).GetMethod("DenyClipboardLoad",BindingFlags.Static|BindingFlags.NonPublic)));
            phase="waiting_for_menu";
            Write("host.json",new JObject{["pid"]=System.Diagnostics.Process.GetCurrentProcess().Id,["token"]=token,["protocol"]=1,["batchMode"]=true});
            StartCoroutine(Boot());
        }
        private static bool DenySave(){if(active==null)return true;active.deniedSaves++;return false;}
        private static bool DenyKeyboard(ref bool __result){if(active==null)return true;active.blockedKeyboardChecks++;__result=false;return false;}
        private static bool DenyPointer(){if(active==null)return true;active.blockedPointerEvents++;return false;}
        private static bool DenyClipboardLoad(){if(active==null)return true;active.blockedClipboardLoads++;return false;}
        private void Write(string name,JObject data)
        {
            var path=Path.Combine(root,name);var temp=path+".tmp";
            File.WriteAllText(temp,data.ToString());
            if(File.Exists(path))File.Delete(path);
            File.Move(temp,path);
        }
        private IEnumerator Boot()
        {
            var start=Time.realtimeSinceStartup;
            // Do not touch Game.Instance before native Startup has initialized it.
            // The getter constructs the singleton; calling it from plugin Awake
            // precedes Unity runtime initializers and corrupts native startup.
            while(UnityEngine.SceneManagement.SceneManager.GetActiveScene().name!="MainMenu"){
                if(Time.realtimeSinceStartup-start>150){phase="failed";error="Native startup did not reach MainMenu in 150 seconds.";yield break;}
                yield return null;
            }
            while(!SP2Game.Instance.CraftDatabase.IsInitialized)yield return null;
            phase="loading_designer";
            SP2Game.Instance.SceneManager.LoadDesigner();
            while(Designer.Instance==null || Designer.Instance.Aircraft==null){
                if(Time.realtimeSinceStartup-start>240){phase="failed";error="Native designer startup timed out.";yield break;}
                yield return null;
            }
            for(int i=0;i<20;i++)yield return null;
            yield return Load("F2");
        }
        private IEnumerator Load(string fixture, bool functionTreeControl=false)
        {
            loading=true;phase="loading_fixture";
            bool previous=Jundroo.Common.Expressions.Parser.ForceFunk;
            try{
                if(functionTreeControl)Jundroo.Common.Expressions.Parser.ForceFunk=true;
                var xml=SP2Game.Instance.CraftDatabase.LoadCraftXml("SP2Build 050 Precision Lab "+fixture+".xml",false);
                if(xml==null)throw new InvalidOperationException("Named native test fixture is unavailable.");
                Designer.Instance.LoadXml(new XElement(xml),isNewAircraft:true);
            }catch(Exception ex){phase="failed";error=ex.ToString();loading=false;yield break;}
            finally { Jundroo.Common.Expressions.Parser.ForceFunk=previous; }
            for(int i=0;i<20;i++)yield return null;
            phase="ready";loading=false;
        }
        private JObject State(){return new JObject{
            ["phase"]=phase,["error"]=error,["batchMode"]=Application.isBatchMode,
            ["graphicsDevice"]=SystemInfo.graphicsDeviceName,["graphicsDeviceType"]=SystemInfo.graphicsDeviceType.ToString(),
            ["scene"]=UnityEngine.SceneManagement.SceneManager.GetActiveScene().name,
            ["craftName"]=Designer.Instance?.Aircraft?.Aircraft?.Name,["deniedSaveCalls"]=deniedSaves,
            ["dayNightValue"]=Shader.GetGlobalFloat("_DAY_NIGHT_VALUE"),
            ["physicalInputIsolation"]=new JObject{["enabled"]=true,["blockedKeyboardChecks"]=blockedKeyboardChecks,
                ["blockedPointerEvents"]=blockedPointerEvents,["blockedClipboardLoads"]=blockedClipboardLoads},
            ["desktopInputUsed"]=false,["evidenceKind"]="headless_native_api"};}
        private JObject ModifierSymmetry(JObject req)
        {
            var d=Designer.Instance;
            if(phase!="ready" || loading || d?.Aircraft?.Aircraft?.Name!="SP2Build 050 Precision Lab F2" ||
                (string)req["expectedCraftName"]!=d.Aircraft.Aircraft.Name)
                throw new InvalidOperationException("Modifier toggle reference requires the exact open F2 lab.");
            if(req["partId"]?.Type!=JTokenType.Integer || req["enabled"]?.Type!=JTokenType.Boolean)
                throw new InvalidOperationException("Exact partId and boolean enabled required.");
            var part=d.Aircraft.Aircraft.Assembly.GetPartById((int)req["partId"]);
            if(part==null || part.SymmetryId==0)throw new InvalidOperationException("Expected an existing linked test part.");
            var modifier=part.Modifiers.Single(m=>m.GetType().Name=="GearLegData");
            d.SelectedPart=part.PartScript;
            var panel=d.DesignerScript.DesignerUI.Flyouts.PartProperties.Widget.GetComponentInChildren<PartPropertiesPanelScript>(true);
            var flags=BindingFlags.Instance|BindingFlags.NonPublic;
            typeof(PartPropertiesPanelScript).GetMethod("Update",flags).Invoke(panel,null);
            var groups=(List<GenericPartPropertiesScript>)typeof(PartPropertiesPanelScript).GetField("_partProperties",flags).GetValue(panel);
            var group=groups.Single(g=>g.CurrentPartModifier==modifier);group.RefreshUI();
            group.Header.SetPartModifier(modifier);
            if(modifier.SymmetryDisabled==(bool)req["enabled"])
                group.Header.GetType().GetMethod("ToggleSymmetryClicked",flags).Invoke(group.Header,new object[]{null});
            if(modifier.SymmetryDisabled==(bool)req["enabled"])throw new InvalidOperationException("Native header toggle did not apply.");
            return new JObject{["partId"]=part.Id,["modifier"]="GearLegData",["enabled"]=!modifier.SymmetryDisabled,
                ["evidence"]="actual_native_modifier_header_toggle_callback",["desktopInputUsed"]=false};
        }
        private void Update()
        {
            if(active!=this || Time.realtimeSinceStartup<poll)return;
            poll=Time.realtimeSinceStartup+.1f;
            Write("state.json",State());
            foreach(var file in Directory.GetFiles(root,"request-*.json")){
                var id=Path.GetFileNameWithoutExtension(file).Substring(8);
                if(id.Length!=32 || id.Any(c=>!Uri.IsHexDigit(c)))continue;
                var output="result-"+id+".json";
                if(File.Exists(Path.Combine(root,output))){File.Delete(file);continue;}
                JObject answer;
                try{
                    var req=JObject.Parse(File.ReadAllText(file));
                    if((string)req["token"]!=token)throw new InvalidOperationException("Invalid host token.");
                    string action=(string)req["action"];
                    JObject probe=null;
                    if(action=="load" || action=="load-function-tree-control"){
                        if(phase!="ready" || loading)throw new InvalidOperationException("Host is not ready.");
                        if((string)req["expectedCraftName"]!=Designer.Instance.Aircraft.Aircraft.Name)throw new InvalidOperationException("Current craft changed.");
                        string fixture=(string)req["fixture"];
                        if(!new[]{"F2","C17","E1","E2","E3"}.Contains(fixture))throw new InvalidOperationException("Unknown fixed fixture.");
                        StartCoroutine(Load(fixture,action=="load-function-tree-control"));
                    }else if(action=="lighting"){
                        if(phase!="ready" || (string)req["expectedCraftName"]!=Designer.Instance.Aircraft.Aircraft.Name)throw new InvalidOperationException("Current test craft changed.");
                        float value=(float)req["dayNightValue"];
                        if(float.IsNaN(value)||value<0||value>1)throw new InvalidOperationException("dayNightValue must be in [0,1].");
                        // Same shader input as native EnviroLightingModule:
                        // night=0, day=1. This certifies shader emission, not a
                        // flight time/weather transition or atmospheric scene.
                        Shader.SetGlobalFloat("_DAY_NIGHT_VALUE",value);
                    }else if(action=="heap-inventory"){
                        string craft=Designer.Instance?.Aircraft?.Aircraft?.Name;
                        if(phase!="ready" || loading || craft==null || !craft.StartsWith("SP2Build 050 Precision Lab ",StringComparison.Ordinal) ||
                            (string)req["expectedCraftName"]!=craft)throw new InvalidOperationException("Heap probe requires the exact open native test fixture.");
                        probe=JObject.FromObject(Win32HeapProbe.ReadDefault());
                    }else if(action=="mesh-lifetime-reference" || action=="expression-template-reference"){
                        if(phase!="ready" || loading || (string)req["expectedCraftName"]!=Designer.Instance?.Aircraft?.Aircraft?.Name ||
                            !((string)req["expectedCraftName"]).StartsWith("SP2Build 050 Precision Lab ",StringComparison.Ordinal))
                            throw new InvalidOperationException("Mesh reference requires the exact named test fixture.");
                        probe=action=="mesh-lifetime-reference"?MeshLifetimeReference.Run(harmony):ExpressionTemplateReference.Run(harmony);
                    }else if(action=="modifier-symmetry")probe=ModifierSymmetry(req);
                    else if(action=="shutdown")Application.Quit();
                    else if(action!="status")throw new InvalidOperationException("Unsupported test-host action.");
                    answer=new JObject{["success"]=true,["schemaVersion"]="1",["data"]=State()};
                    if(probe!=null)answer["data"]["probe"]=probe;
                }catch(Exception ex){answer=new JObject{["success"]=false,["schemaVersion"]="1",["error"]=new JObject{["code"]="acceptance_host_error",["message"]=ex.Message}};}
                Write(output,answer);File.Delete(file);
            }
        }
        private void OnDestroy(){if(active==this){active=null;harmony?.UnpatchSelf();}}
    }
}
