using System;
using System.Linq;
using System.Xml.Linq;
using Assets.Scripts.Design;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine;
using SP2Game=Assets.Scripts.Game;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private static object DesignerControlCapability(){return new{
            available=true,command="designer.control",savedCraftsCommand="designer.crafts",
            actions=new[]{"enter","load","select","menu","quit"},desktopInput=false,
            discardPolicy="load/menu/quit from Designer require fresh identity, expectedCraftName and discardCurrent=true. Save desired edits before leaving; session checkpoints expire on load.",
            scope="Native scene/selection APIs. Saved craft contents are editable only after native loading into the designer."};}
        private object DesignerCrafts(JObject a)
        {
            VisualScope.Keys(a,"query","offset","limit");
            string scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene().name;
            if(scene!="MainMenu"&&scene!="Designer")throw new ApiError("designer_not_ready","Wait for the native menu or designer before reading the craft catalog.");
            var db=SP2Game.Instance.CraftDatabase;
            if(!db.IsInitialized)throw new ApiError("designer_not_ready","Native craft database is initializing.");
            int offset=a["offset"]==null?0:VisualScope.Integer(a["offset"],"offset",0);
            int limit=a["limit"]==null?50:VisualScope.Integer(a["limit"],"limit",1,200);
            string query=(string)a["query"];
            var all=db.GetCrafts().Where(c=>c.Exists&&c.IsValid&&!c.IsHidden)
                .Where(c=>string.IsNullOrEmpty(query)||(c.Name??"").IndexOf(query,StringComparison.OrdinalIgnoreCase)>=0||c.Id.IndexOf(query,StringComparison.OrdinalIgnoreCase)>=0)
                .OrderBy(c=>c.Id,StringComparer.Ordinal).ToArray();
            return new {total=all.Length,offset,items=all.Skip(offset).Take(limit).Select(c=>new{craftId=c.Id,name=c.Name,subdirectory=c.SubdirectoryPath}),
                scope="Native saved-craft catalog metadata only. No offline part inspection or editing."};
        }
        private async UniTask<JObject> DesignerControl(JObject a,Job job)
        {
            if(string.IsNullOrWhiteSpace(job.Key))throw new ApiError("invalid_input","Designer control requires requestId.");
            VisualScope.Keys(a,"action","expectedScene","craftSessionId","expectedRevision","expectedCraftName","discardCurrent","craftId","partId","clear");
            foreach(string key in new[]{"action","expectedScene","craftSessionId","expectedCraftName","craftId"})if(a[key]!=null)VisualScope.String(a[key],key);
            foreach(string key in new[]{"discardCurrent","clear"})if(a[key]!=null)VisualScope.Boolean(a[key],key);
            string action=Required(a,"action"),scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene().name;
            if(!new[]{"enter","load","select","menu","quit"}.Contains(action))throw new ApiError("invalid_input","Unknown designer control action.");
            if(Required(a,"expectedScene")!=scene)throw new ApiError("scene_conflict","Native scene changed; query designer.status.");
            if(scene!="MainMenu"&&scene!="Designer")throw new ApiError("scene_not_supported","Control is limited to settled MainMenu and Designer scenes.");
            if(action!="load"&&a["craftId"]!=null)throw new ApiError("invalid_input","craftId is only valid for load.");
            if(action!="select"&&(a["partId"]!=null||a["clear"]!=null))throw new ApiError("invalid_input","Selection fields require select.");
            Designer d=null;XElement before=null;string previousSession=null;int? selected=null;
            if(scene=="Designer"){
                before=Observe();Guard(a);d=Current();EnsureDesignerSceneIntegrity(d);previousSession=session;
                if(Required(a,"expectedCraftName")!=d.Aircraft.Aircraft.Name)throw new ApiError("session_conflict","Current craft name changed.");
                if(new[]{"load","menu","quit"}.Contains(action)&&!VisualScope.Boolean(a["discardCurrent"],"discardCurrent"))
                    throw new ApiError("discard_confirmation_required","This action replaces/closes the in-memory craft and invalidates session checkpoints. Save desired work first, then explicitly supply discardCurrent=true. This command does not save the aircraft.");
            }
            if((action=="load"||action=="select"||action=="menu")&&d==null)throw new ApiError("designer_not_ready","Enter the designer first.");
            if(action=="enter"&&d!=null)throw new ApiError("scene_conflict","Already in Designer; no action taken.");
            XElement target=null;
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
                try{
                    if(action=="enter")SP2Game.Instance.SceneManager.LoadDesigner();
                    else if(action=="menu")SP2Game.Instance.SceneManager.LoadMenu();
                    else d.LoadXml(target,isNewAircraft:true);
                    string wanted=action=="menu"?"MainMenu":"Designer";float deadline=Time.realtimeSinceStartup+90;
                    for(int i=0;i<20;i++)await UniTask.NextFrame();
                    while(SP2Game.Instance.SceneManager.CurrentScene!=wanted||(wanted=="Designer"&&(Designer.Instance==null||Designer.Instance.Aircraft==null))){
                        if(Time.realtimeSinceStartup>deadline)throw new ApiError("scene_timeout","Native scene transition did not finish; inspect status before retrying.");
                        await UniTask.NextFrame();
                    }
                    if(wanted=="Designer"){Observe();await ReadSettled(Current(),null);EnsureDesignerSceneIntegrity(Current());}
                }catch(Exception failure){
                    if(action!="load")throw;
                    bool restored=false;string recoveryError=null;
                    try{d.LoadXml(new XElement(before));Observe();await ReadSettled(d,before);EnsureDesignerSceneIntegrity(d);restored=true;}
                    catch(Exception recovery){recoveryError=recovery.GetBaseException().Message;uncertain=true;}
                    throw new ApiError("craft_load_failed",failure.GetBaseException().Message,new JObject{
                        ["originalContentRestored"]=restored,["recoveryError"]=recoveryError,["identity"]=JToken.FromObject(Identity()),
                        ["meaning"]="Native recovery establishes a new session; old checkpoints are invalid."});
                }
            }
            bool ready=SP2Game.Instance.SceneManager.CurrentScene=="Designer"&&Designer.Instance?.Aircraft!=null;
            return new JObject{["action"]=action,["scene"]=SP2Game.Instance.SceneManager.CurrentScene,["desktopInputUsed"]=false,
                ["identity"]=ready?JToken.FromObject(Identity()):null,["craftName"]=ready?Current().Aircraft.Aircraft.Name:null,
                ["selectedPartId"]=ready&&Current().SelectedPart!=null?(JToken)Current().SelectedPart.Part.Id:null,
                ["sessionChanged"]=previousSession!=null&&(!ready||session!=previousSession),["saved"]=false};
        }
        private static async UniTaskVoid QuitAfterResponse(){await UniTask.Delay(2000,ignoreTimeScale:true);Application.Quit();}
    }
}
