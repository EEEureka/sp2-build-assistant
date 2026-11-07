using System;
using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Design;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.EventSystems;
using SP2Game=Assets.Scripts.Game;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private static object DesignerControlCapability(){return new{
            available=true,command="designer.control",savedCraftsCommand="designer.crafts",
            actions=new[]{"enter","load","select","save","new","delete","menu","quit"},desktopInput=false,
            discardPolicy="new/load/menu/quit from Designer require fresh identity, expectedCraftName and discardCurrent=true. Save desired edits first; session checkpoints expire on replacement.",
            savePolicy="save requires name without .xml; relative folders are allowed. Existing targets require overwrite=true. Native save may recenter the craft; read the returned identity.",
            newPolicy="new uses the native blank craft template, including its starter control part. It replaces the editor craft but does not create a named persistent save; use save afterwards.",
            scope="Native scene, selection, save and new-craft APIs. Saved craft contents are editable only after native loading into the designer."};}
        private object DesignerCrafts(JObject a)
        {
            VisualScope.Keys(a,"query","offset","limit");
            string scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene().name;
            if(scene!="MainMenu"&&!DesignerReady(scene))throw new ApiError("designer_not_ready","Wait for the native menu or active designer before reading the craft catalog.");
            var db=SP2Game.Instance.CraftDatabase;
            if(!db.IsInitialized)throw new ApiError("designer_not_ready","Native craft database is initializing.");
            int offset=a["offset"]==null?0:VisualScope.Integer(a["offset"],"offset",0);
            int limit=a["limit"]==null?50:VisualScope.Integer(a["limit"],"limit",1,200);
            string query=(string)a["query"];
            var all=db.GetCrafts().Where(c=>c.Exists&&c.IsValid&&!c.IsHidden)
                .Where(c=>string.IsNullOrEmpty(query)||(c.Name??"").IndexOf(query,StringComparison.OrdinalIgnoreCase)>=0||c.Id.IndexOf(query,StringComparison.OrdinalIgnoreCase)>=0)
                .OrderBy(c=>c.Id,StringComparer.Ordinal).ToArray();
            return new {total=all.Length,offset,items=all.Skip(offset).Take(limit).Select(c=>new{craftId=c.Id,name=c.Name,subdirectory=c.SubdirectoryPath,lastModifiedUtc=c.LastModified.ToUniversalTime().ToString("o")}),
                scope="Native saved-craft catalog metadata only. No offline part inspection or editing."};
        }
        private async UniTask<JObject> DesignerControl(JObject a,Job job)
        {
            if(string.IsNullOrWhiteSpace(job.Key))throw new ApiError("invalid_input","Designer control requires requestId.");
            VisualScope.Keys(a,"action","expectedScene","craftSessionId","expectedRevision","expectedCraftName","discardCurrent","craftId","partId","clear","name","overwrite","expectedSavedName","expectedSavedModifiedUtc");
            foreach(string key in new[]{"action","expectedScene","craftSessionId","expectedCraftName","craftId","name","expectedSavedName","expectedSavedModifiedUtc"})if(a[key]!=null)VisualScope.String(a[key],key);
            foreach(string key in new[]{"discardCurrent","clear","overwrite"})if(a[key]!=null)VisualScope.Boolean(a[key],key);
            if(a["expectedRevision"]!=null)VisualScope.Integer(a["expectedRevision"],"expectedRevision",0);
            string action=Required(a,"action"),scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene().name;
            if(!new[]{"enter","load","select","save","new","delete","menu","quit"}.Contains(action))throw new ApiError("invalid_input","Unknown designer control action.");
            if(Required(a,"expectedScene")!=scene)throw new ApiError("scene_conflict","Native scene changed; query designer.status.");
            bool inDesigner=DesignerReady(scene);
            if(scene!="MainMenu"&&!inDesigner)throw new ApiError("scene_not_supported","Control requires the settled menu or an active standalone/flight designer.");
            if(action!="load"&&action!="delete"&&a["craftId"]!=null)throw new ApiError("invalid_input","craftId is only valid for load/delete.");
            if(action!="delete"&&(a["expectedSavedName"]!=null||a["expectedSavedModifiedUtc"]!=null))throw new ApiError("invalid_input","Saved target guards require delete.");
            if(action!="select"&&(a["partId"]!=null||a["clear"]!=null))throw new ApiError("invalid_input","Selection fields require select.");
            if(action!="save"&&(a["name"]!=null||a["overwrite"]!=null))throw new ApiError("invalid_input","name and overwrite require save.");
            if(action=="save"&&a["discardCurrent"]!=null)throw new ApiError("invalid_input","save does not discard the current craft.");
            Designer d=null;XElement before=null;string previousSession=null;int? selected=null;
            if(inDesigner){
                before=Observe();Guard(a,action=="load"&&a.Value<bool?>("discardCurrent")==true);d=Current();EnsureDesignerSceneIntegrity(d);previousSession=session;
                if(Required(a,"expectedCraftName")!=d.Aircraft.Aircraft.Name)throw new ApiError("session_conflict","Current craft name changed.");
                if(new[]{"new","load","menu","quit"}.Contains(action)&&!VisualScope.Boolean(a["discardCurrent"],"discardCurrent"))
                    throw new ApiError("discard_confirmation_required","This action replaces/closes the in-memory craft and invalidates session checkpoints. Save desired work with action=save first, then explicitly supply discardCurrent=true.");
            }
            if(new[]{"load","select","save","new","menu"}.Contains(action)&&d==null)throw new ApiError("designer_not_ready","Enter the designer first.");
            if(action=="enter"&&d!=null)throw new ApiError("scene_conflict","Already in Designer; no action taken.");
            XElement target=null;
            if(action=="delete"){
                string id=Required(a,"craftId");var db=SP2Game.Instance.CraftDatabase;
                if(!db.IsInitialized)throw new ApiError("designer_not_ready","Native craft database is initializing.");
                if(!db.TryGetCraft(id,out var saved)||saved.Id!=id||!saved.Exists||!saved.IsValid||saved.IsHidden)
                    throw new ApiError("craft_not_found","Use an exact available craftId from designer.crafts.");
                try{CraftSaveTarget.Parse(id.EndsWith(".xml",StringComparison.OrdinalIgnoreCase)?id.Substring(0,id.Length-4):id);}
                catch(ArgumentException invalid){throw new ApiError("protected_craft",invalid.Message);}
                saved.Refresh();
                if(saved.Name!=Required(a,"expectedSavedName")||saved.LastModified.ToUniversalTime().ToString("o")!=Required(a,"expectedSavedModifiedUtc"))
                    throw new ApiError("saved_craft_changed","Saved craft metadata changed; refresh designer.crafts before deletion.");
                if(inDesigner&&saved.Name==d.Aircraft.Aircraft.Name)throw new ApiError("current_craft_protected","Cannot delete the current craft's named save.");
                db.DeleteCraft(saved);saved.Refresh();
                if(saved.Exists||db.GetCrafts().Any(c=>c.Id==id))throw new ApiError("craft_delete_failed","Native database did not confirm deletion.");
                return new JObject{["action"]="delete",["scene"]=scene,["desktopInputUsed"]=false,["saved"]=false,
                    ["identity"]=inDesigner?JToken.FromObject(Identity()):null,["sessionChanged"]=false,
                    ["deletedCraft"]=new JObject{["craftId"]=id,["name"]=(string)a["expectedSavedName"],["deletionVerified"]=true},
                    ["meaning"]="Deleted through native craft database; current in-memory craft was retained."};
            }
            CraftSaveTarget saveTarget=null;bool overwritten=false;
            if(action=="save"){
                try{saveTarget=CraftSaveTarget.Parse(Required(a,"name"));}
                catch(ArgumentException invalid){throw new ApiError("invalid_input",invalid.Message);}
                var db=SP2Game.Instance.CraftDatabase;
                if(!db.IsInitialized)throw new ApiError("designer_not_ready","Native craft database is initializing.");
                if(!db.ValidateCraftPath(saveTarget.Id))throw new ApiError("invalid_input","Native craft database rejected the save name.");
                var existing=db.GetCrafts().FirstOrDefault(c=>string.Equals(c.Id,saveTarget.Id,StringComparison.OrdinalIgnoreCase));
                // Native metadata also covers a file not yet in the catalog.
                if(existing==null)existing=new Assets.Scripts.Craft.CraftFiles.CraftFileInfo(saveTarget.Id);
                existing.Refresh();
                overwritten=existing.Exists;
                if(overwritten)saveTarget.UseExistingId(existing.Id);
                if(overwritten&&!VisualScope.Boolean(a["overwrite"],"overwrite"))
                    throw new ApiError("craft_exists","A craft already exists at this target. Explicitly supply overwrite=true to replace it.",new JObject{["craftId"]=existing.Id,["name"]=existing.Name});
            }
            if(action=="new"){
                if(Jundroo.Common.Platform.Device.IsDemoBuild)throw new ApiError("new_craft_unavailable","Creating new crafts is not available in the demo.");
                target=SP2Game.Instance.CraftDatabase.LoadBuiltinCraftXml("__new__",false);
                if(target==null)throw new ApiError("craft_new_failed","Native blank craft template is unavailable; current craft was not replaced.");
            }
            if((action=="new"||action=="save")&&d.DesignerScript.TutorialRunning)
                throw new ApiError("tutorial_running","Finish the native designer tutorial before saving or creating a craft.");
            if(action=="load"){
                string id=Required(a,"craftId");
                if(!SP2Game.Instance.CraftDatabase.TryGetCraft(id,out var craft)||craft.Id!=id||!craft.Exists||!craft.IsValid||craft.IsHidden)
                    throw new ApiError("craft_not_found","Use an exact available craftId from designer.crafts.");
                target=SP2Game.Instance.CraftDatabase.LoadCraftXml(id,false);
                if(target==null)throw new ApiError("craft_load_failed","Native loader did not return a craft.");
                target=new XElement(target);
            }
            if(action=="select"){
                bool clear=VisualScope.Boolean(a["clear"],"clear");
                if(clear==(a["partId"]!=null))throw new ApiError("invalid_input","Choose partId or clear=true, exclusively.");
                if(!clear)selected=Part(VisualScope.Integer(a["partId"],"partId",0)).Id;
            }
            lock(job.Sync)if(job.CancelRequested)throw new ApiError("cancelled","Cancelled before native control action.");
            if(action=="save")return await SaveDesignerCraft(d,saveTarget,overwritten,previousSession);
            if(action=="select"){
                d.SelectedPart=selected.HasValue?Part(selected.Value).PartScript:null;
                await UniTask.NextFrame();
                var after=Observe();
                if(session!=previousSession||!SnapshotState.EquivalentAfterNativeRestore(before,after))throw new ApiError("selection_state_changed","Aircraft changed during selection; inspect current state.");
                if((d.SelectedPart==null?(int?)null:d.SelectedPart.Part.Id)!=selected)throw new ApiError("selection_failed","Native selection did not match the requested part.");
            }else if(action=="quit"){
                QuitAfterResponse().Forget();
                return new JObject{["action"]=action,["scene"]=scene,["shutdownScheduled"]=true,["desktopInputUsed"]=false,
                    ["meaning"]="Application.Quit scheduled after a response grace period; confirm process exit separately. Native shutdown lifecycle may persist application settings."};
            }else{
                using(var inputScope=new DesignerControlWriteScope()){
                try{
                    if(action=="enter")SP2Game.Instance.SceneManager.LoadDesigner();
                    else if(action=="menu")SP2Game.Instance.SceneManager.LoadMenu();
                    else if(action=="new")d.CreateNewAircraft();
                    else d.LoadXml(target,isNewAircraft:true);
                    string wanted=action=="menu"?"MainMenu":"Designer";float deadline=Time.realtimeSinceStartup+90;
                    for(int i=0;i<20;i++)await UniTask.NextFrame();
                    while((wanted=="Designer"?!DesignerReady():SP2Game.Instance.SceneManager.CurrentScene!=wanted)){
                        if(Time.realtimeSinceStartup>deadline)throw new ApiError("scene_timeout","Native scene transition did not finish; inspect status before retrying.");
                        await UniTask.NextFrame();
                    }
                    if(wanted=="Designer"){
                        Observe();await ReadSettled(Current(),null);EnsureDesignerSceneIntegrity(Current());
                        if(action=="new"&&(session==previousSession||!MatchesBlankTemplate(target,Observe())))
                            throw new ApiError("craft_new_failed","Native new craft did not match the blank template; recovering original content.");
                    }
                }catch(Exception failure){
                    if(action!="load"&&action!="new")throw;
                    bool restored=false;string recoveryError=null;
                    try{d.LoadXml(new XElement(before));Observe();await ReadSettled(d,before);EnsureDesignerSceneIntegrity(d);restored=true;}
                    catch(Exception recovery){recoveryError=recovery.GetBaseException().Message;uncertain=true;}
                    throw new ApiError(action=="new"?"craft_new_failed":"craft_load_failed",failure.GetBaseException().Message,new JObject{
                        ["originalContentRestored"]=restored,["recoveryError"]=recoveryError,["identity"]=JToken.FromObject(Identity()),
                        ["meaning"]="Native recovery establishes a new session; old checkpoints are invalid."});
                }
                }
            }
            bool ready=DesignerReady();
            return new JObject{["action"]=action,["scene"]=SP2Game.Instance.SceneManager.CurrentScene,["desktopInputUsed"]=false,
                ["identity"]=ready?JToken.FromObject(Identity()):null,["craftName"]=ready?Current().Aircraft.Aircraft.Name:null,
                ["selectedPartId"]=ready&&Current().SelectedPart!=null?(JToken)Current().SelectedPart.Part.Id:null,
                ["sessionChanged"]=previousSession!=null&&(!ready||session!=previousSession),["saved"]=false,
                ["partCount"]=ready?(JToken)Current().Aircraft.Aircraft.Assembly.Parts.Count:null,
                ["meaning"]=action=="new"?"Native blank craft created with starter control part. Not a named persistent save; call save to name and persist it.":null};
        }
        private static bool MatchesBlankTemplate(XElement template,XElement actual)
        {
            var expected=template.Element("Assembly")?.Element("Parts")?.Elements("Part");
            var parts=actual.Element("Assembly")?.Element("Parts")?.Elements("Part");
            if(expected==null||parts==null||(string)template.Attribute("name")!=(string)actual.Attribute("name"))return false;
            return expected.Select(p=>(string)p.Attribute("id")+":"+(string)p.Attribute("partType")).OrderBy(p=>p,StringComparer.Ordinal)
                .SequenceEqual(parts.Select(p=>(string)p.Attribute("id")+":"+(string)p.Attribute("partType")).OrderBy(p=>p,StringComparer.Ordinal));
        }
        private async UniTask<JObject> SaveDesignerCraft(Designer d,CraftSaveTarget target,bool overwritten,string previousSession)
        {
            using(var inputScope=new DesignerControlWriteScope())
            using(var receipt=new NativeSaveReceipt(target.Id)){
                try{
                    d.DesignerScript.EndPartMovement();
                    d.Save(target.Id,target.Name);
                    Observe();await ReadSettled(d,null);EnsureDesignerSceneIntegrity(d);
                    var saved=receipt.Saved;
                    if(saved==null||!saved.Exists||!saved.IsValid||saved.Name!=target.Name)
                        throw new ApiError("craft_save_failed","Native save did not confirm a valid target craft. Inspect current state before retrying.");
                    if(session!=previousSession)throw new ApiError("session_conflict","Craft changed during native save.");
                    return new JObject{["action"]="save",["scene"]=SP2Game.Instance.SceneManager.CurrentScene,["desktopInputUsed"]=false,["saved"]=true,
                        ["identity"]=JToken.FromObject(Identity()),["craftName"]=d.Aircraft.Aircraft.Name,["sessionChanged"]=false,
                        ["selectedPartId"]=d.SelectedPart==null?null:(JToken)d.SelectedPart.Part.Id,["partCount"]=d.Aircraft.Aircraft.Assembly.Parts.Count,
                        ["persistedCraft"]=new JObject{["craftId"]=saved.Id,["name"]=saved.Name,["overwritten"]=overwritten,
                            ["lastModifiedUtc"]=saved.LastModified.ToUniversalTime().ToString("o"),["persistenceVerified"]=true,
                            ["verification"]="native_database_save_return"},
                        ["meaning"]="Native Designer.Save persisted the named craft, editor backup and native autosave. AutoRecenter and save-time metadata can change revision; use this returned identity."};
                }catch(Exception failure){
                    Observe();
                    throw new ApiError("craft_save_failed",failure.GetBaseException().Message,new JObject{
                        ["craftId"]=target.Id,["targetSaveCompleted"]=receipt.Saved!=null&&receipt.Saved.Exists&&receipt.Saved.IsValid,
                        ["identity"]=JToken.FromObject(Identity()),
                        ["meaning"]="Save can already have changed the craft or editor/autosave state. No file rollback was attempted; inspect state and resolve this request before retrying."});
                }
            }
        }
        private sealed class DesignerControlWriteScope : IDisposable
        {
            private readonly bool previousWriting,previousEventsEnabled;
            private readonly EventSystem events;
            internal DesignerControlWriteScope(){
                previousWriting=Writing;events=EventSystem.current;
                previousEventsEnabled=events!=null&&events.enabled;
                Writing=true;if(events!=null)events.enabled=false;
            }
            public void Dispose(){Writing=previousWriting;if(events!=null)events.enabled=previousEventsEnabled;}
        }
        private static async UniTaskVoid QuitAfterResponse(){await UniTask.Delay(2000,ignoreTimeScale:true);Application.Quit();}
    }
}
