using System;
using System.Linq;
using System.Text;
using Assets.Scripts.Craft.Parts;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime
    {
        private static Vector3 UnityV(VisualCore.V v){return new Vector3((float)v.X,(float)v.Y,(float)v.Z);}
        private static JObject CameraInfo(Camera c,Vector3 target)
        {
            return new JObject{["positionWorld"]=new JArray(Vec(c.transform.position)),["targetWorld"]=new JArray(Vec(target)),
                ["forwardWorld"]=new JArray(Vec(c.transform.forward)),["upWorld"]=new JArray(Vec(c.transform.up)),
                ["rotationQuaternion"]=new JArray(c.transform.rotation.x,c.transform.rotation.y,c.transform.rotation.z,c.transform.rotation.w),
                ["projection"]=c.orthographic?"orthographic":"perspective",["fieldOfViewDegrees"]=c.fieldOfView,["orthographicSize"]=c.orthographicSize,
                ["aspect"]=c.aspect,["nearClipMetres"]=c.nearClipPlane,["farClipMetres"]=c.farClipPlane,
                ["worldToCameraRows"]=MatrixRows(c.worldToCameraMatrix),["projectionRows"]=MatrixRows(c.projectionMatrix),
                ["localPosition"]=new JArray(Vec(c.transform.localPosition)),
                ["localRotationQuaternion"]=new JArray(c.transform.localRotation.x,c.transform.localRotation.y,c.transform.localRotation.z,c.transform.localRotation.w),
                ["parentInstanceId"]=c.transform.parent==null?0:c.transform.parent.GetInstanceID(),["cameraInstanceId"]=c.GetInstanceID(),
                ["targetTextureInstanceId"]=c.targetTexture==null?0:c.targetTexture.GetInstanceID(),["enabled"]=c.enabled,
                ["rect"]=new JArray(c.rect.x,c.rect.y,c.rect.width,c.rect.height),["cullingMask"]=c.cullingMask,["clearFlags"]=c.clearFlags.ToString()};
        }
        private async UniTask<JObject> DesignerCapture(JObject args,Job job)
        {
#if ACCEPTANCE_HOOKS
            using(var fixture=AcceptanceCameraFixture.Enter(Current()))
                return await DesignerCaptureCore(args,job);
#else
            return await DesignerCaptureCore(args,job);
#endif
        }
        private async UniTask<JObject> DesignerCaptureCore(JObject args,Job job)
        {
            VisualScope.Keys(args,"craftSessionId","expectedRevision","views","resolution","focusPartIds","cuttingOutlinesVisible");
            Observe();
            Action guard=()=>{
                if(VisualScope.String(args["craftSessionId"],"craftSessionId")!=session)throw new ApiError("session_conflict","Screenshot belongs to another designer session.");
                if(args["expectedRevision"]!=null&&VisualScope.Integer(args["expectedRevision"],"expectedRevision",1)!=revision)throw new ApiError("revision_conflict","Aircraft changed; read fresh status.");
            };
            guard();var d=Current();await ReadSettled(d,null);Observe();guard();
            var camera=d.CameraController?.Camera;
            if(camera==null||!camera.isActiveAndEnabled)throw new ApiError("camera_unavailable","Active designer camera unavailable.");
            // Deliberately allow inconsistent scene instances: this is a diagnostic of the actual scene.
            var scene=DesignerSceneIntegrity(d);var identity=JToken.FromObject(Identity());
            var focus=args["focusPartIds"] as JArray;
            if(args["focusPartIds"]!=null&&(focus==null||focus.Count<1||focus.Count>2048))throw new ApiError("invalid_input","focusPartIds needs 1..2048 part IDs.");
            var ids=focus==null?d.Aircraft.Aircraft.Assembly.Parts.Select(p=>p.Id).ToArray():focus.Select(t=>VisualScope.Integer(t,"focusPartIds",0)).Distinct().ToArray();
            var bounds=new VisualCore.Box();int surfaces=0;
            foreach(int id in ids){var ps=Part(id).PartScript;
                var registered=ps.PartMaterialScript.RendererMaps.Select(m=>(Renderer)m.Renderer).Where(r=>r!=null).Distinct();
                foreach(var r in registered){if(!r.enabled||!r.gameObject.activeInHierarchy||r.GetComponentInParent<PartScript>()!=ps)continue;bounds.Add(VV(r.bounds.min));bounds.Add(VV(r.bounds.max));surfaces++;}
            }
            if(surfaces==0){foreach(int id in ids)bounds.Add(VV(Part(id).PartScript.transform.position));}
            if(ids.Length==0)throw new ApiError("scope_empty","No aircraft parts to frame.");
            var resolution=args["resolution"] as JObject??(args["resolution"]==null?new JObject():null);
            VisualScope.Keys(resolution,"width","height");
            // Preserve the actual viewport aspect by default; no silent 16:9 crop on a 16:10 display.
            double scale=Math.Min(1,1280.0/Math.Max(camera.pixelWidth,camera.pixelHeight));
            int width=resolution["width"]==null?Math.Max(128,(int)Math.Round(camera.pixelWidth*scale)):VisualScope.Integer(resolution["width"],"width",128,2048);
            int height=resolution["height"]==null?Math.Max(128,(int)Math.Round(camera.pixelHeight*scale)):VisualScope.Integer(resolution["height"],"height",128,2048);
            if(args["resolution"]!=null&&(resolution["width"]==null||resolution["height"]==null))throw new ApiError("invalid_input","resolution requires both width and height, or omit it to preserve viewport aspect.");
            var target=d.CameraController.TargetPosition;
            var current=new DesignerViewPlan.Pose{Position=VV(camera.transform.position),Forward=VV(camera.transform.forward),Up=VV(camera.transform.up),Target=VV(target),
                Orthographic=camera.orthographic,FieldOfView=camera.fieldOfView,OrthographicSize=camera.orthographicSize,Near=camera.nearClipPlane,Far=camera.farClipPlane};
            var views=DesignerViewPlan.Plan(args["views"] as JArray??(args["views"]==null?new JArray("current"):null),current,bounds,width,height);
            var designerUI=d.DesignerScript.DesignerUI;
            bool oldCuttingOutlines=designerUI.CuttingOutlinesVisible;
            bool captureCuttingOutlines=VisualScope.Boolean(args["cuttingOutlinesVisible"],"cuttingOutlinesVisible",oldCuttingOutlines);
            string gizmoPolicy=args["cuttingOutlinesVisible"]==null?"native_scene_helpers_preserved_separate_overlay_cameras_excluded":"explicit_native_cutting_outline_visibility_other_helpers_preserved";
            GraphicsReadback.Verify();
            var before=CameraInfo(camera,target);var oldPosition=camera.transform.position;var oldRotation=camera.transform.rotation;
            var oldLocalPosition=camera.transform.localPosition;var oldLocalRotation=camera.transform.localRotation;
            var active=RenderTexture.active;var backupObject=new GameObject("SP2BuildScreenshotCameraBackup"){hideFlags=HideFlags.HideAndDontSave};
            var backup=backupObject.AddComponent<Camera>();backup.enabled=false;backup.CopyFrom(camera);backup.enabled=false;
            bool oldEnabled=camera.enabled;var oldAmbientLight=RenderSettings.ambientLight;float oldAmbientIntensity=RenderSettings.ambientIntensity;
            var result=new VisualCore.Result();var images=new JArray();
            Exception captureError=null,restoreError=null;string stage="prepare";JArray worldRestoreDiff=null;
            try{
                if(args["cuttingOutlinesVisible"]!=null)designerUI.CuttingOutlinesVisible=captureCuttingOutlines;
                // Synchronous on the Unity thread: no player-input frame occurs with a temporary pose.
                foreach(var view in views){
                    stage="render:"+view.Name;
                    lock(job.Sync)if(job.CancelRequested)throw new ApiError("cancelled","Screenshot cancelled.");
                    camera.CopyFrom(backup);camera.enabled=oldEnabled;
                    var pose=view.Camera;camera.transform.SetPositionAndRotation(UnityV(pose.Position),Quaternion.LookRotation(UnityV(pose.Forward),UnityV(pose.Up)));
                    camera.orthographic=pose.Orthographic;camera.fieldOfView=(float)pose.FieldOfView;camera.orthographicSize=(float)pose.OrthographicSize;
                    camera.nearClipPlane=(float)pose.Near;camera.farClipPlane=(float)pose.Far;camera.aspect=(float)width/height;camera.rect=new Rect(0,0,1,1);
                    camera.ResetProjectionMatrix();camera.ResetWorldToCameraMatrix();
                    RenderTexture rt=null;Texture2D pixels=null;
                    try{
                        rt=RenderTexture.GetTemporary(width,height,24,RenderTextureFormat.ARGB32,RenderTextureReadWrite.Default,1);
                        camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;
                        AcceptanceFault("capture_render_"+images.Count);
                        pixels=new Texture2D(width,height,TextureFormat.RGB24,false);pixels.ReadPixels(new Rect(0,0,width,height),0,0);pixels.Apply(false,false);
                        AcceptanceFault("capture_encode_"+images.Count);
                        string file=view.Name+".png";result.Files[file]=pixels.EncodeToPNG();
                        images.Add(new JObject{["name"]=view.Name,["view"]=view.Preset,["file"]=file,["width"]=width,["height"]=height,
                            ["camera"]=CameraInfo(camera,UnityV(pose.Target)),["autoDistance"]=view.AutoDistance,["autoOrthographicSize"]=view.AutoSize});
                    }finally{camera.targetTexture=backup.targetTexture;RenderTexture.active=active;if(pixels!=null)UnityEngine.Object.Destroy(pixels);if(rt!=null)RenderTexture.ReleaseTemporary(rt);}
                }
                stage="graphics_readback_verification";GraphicsReadback.Verify();
            }catch(Exception error){captureError=error;}finally{
                try{
                    camera.CopyFrom(backup);camera.enabled=oldEnabled;camera.transform.SetPositionAndRotation(oldPosition,oldRotation);
                    worldRestoreDiff=CameraState.Compare(before,CameraInfo(camera,target));
                    // Restore exactly in the representation owned by the native controller.
                    // A world -> parent-local round trip needlessly loses float precision.
                    camera.transform.localPosition=oldLocalPosition;camera.transform.localRotation=oldLocalRotation;
                }catch(Exception error){restoreError=error;}finally{
                    try{designerUI.CuttingOutlinesVisible=oldCuttingOutlines;}catch(Exception error){restoreError=error;}
                    RenderSettings.ambientLight=oldAmbientLight;RenderSettings.ambientIntensity=oldAmbientIntensity;
                    RenderTexture.active=active;UnityEngine.Object.Destroy(backupObject);
                }
            }
            var after=CameraInfo(camera,d.CameraController.TargetPosition);
            var fieldDiff=CameraState.Compare(before,after);
            var diagnostic=new JObject{["stage"]=stage,["completedViewCount"]=images.Count,["cameraBefore"]=before,["cameraAfter"]=after,["fieldDiff"]=fieldDiff,
                ["worldPoseRoundTripDiff"]=worldRestoreDiff,["restoreException"]=restoreError?.Message,["captureException"]=captureError?.Message};
            var helperDisplay=new JObject{["cuttingOutlinesBefore"]=oldCuttingOutlines,["cuttingOutlinesDuring"]=captureCuttingOutlines,["cuttingOutlinesAfter"]=designerUI.CuttingOutlinesVisible,["restored"]=oldCuttingOutlines==designerUI.CuttingOutlinesVisible,["scope"]="Native cutting-volume editor outlines only; selected-part helpers may remain. No geometry, lighting, material or physical input changes."};
            diagnostic["helperDisplay"]=helperDisplay;
            if(!(bool)helperDisplay["restored"])throw new ApiError("display_restore_failed","Native cutting outline display was not restored.",diagnostic);
            if(restoreError!=null||!CameraState.Passed(fieldDiff))throw new ApiError("camera_restore_failed","Designer camera restoration failed semantic checks; inspect error.details.fieldDiff.",diagnostic);
            bool nativeCameraMoved=false;
            Assets.Scripts.Design.CameraController.CameraMoveDelegate moved=(r,p,z)=>nativeCameraMoved=true;
            var followingFrames=new JArray();d.CameraController.CameraMoved+=moved;
            try{for(int i=0;i<2;i++){await UniTask.NextFrame(PlayerLoopTiming.LastPostLateUpdate);if(Current()!=d)throw new ApiError("session_conflict","Designer changed during screenshot verification.");
                var next=CameraInfo(camera,d.CameraController.TargetPosition);followingFrames.Add(new JObject{["frame"]=Time.frameCount,["nativeCameraMoved"]=nativeCameraMoved,["cameraState"]=next,["fieldDiff"]=CameraState.Compare(after,next)});}}
            finally{d.CameraController.CameraMoved-=moved;}
            diagnostic["followingFrames"]=followingFrames;
            if(!nativeCameraMoved&&followingFrames.Any(f=>!CameraState.Passed((JArray)f["fieldDiff"])))throw new ApiError("camera_restore_failed","Camera changed on a following native frame without a camera movement event.",diagnostic);
            if(captureError!=null)throw new ApiError((captureError as ApiError)?.Code??"capture_failed",captureError.Message,diagnostic);
            Observe();guard();
            result.Files["overview.png"]=result.Files[(string)images[0]["file"]];
            var warnings=new JArray("Native designer scene camera rendering includes native materials, lighting, background and all objects visible to its culling mask. Screen-space menus, cursor and separate gizmo/overlay cameras are not composited. Native scene helpers such as selected outlines and window cutting volumes remain visible when enabled in the designer; includesGizmos is null because their presence is not classified.",
                "focusPartIds and target control framing only; no parts or extra aircraft instances are hidden. Named views use Unity world axes, not inferred aircraft nose orientation.",
                "overview.png duplicates the first view. Use recommendedImages to inspect every requested view. This is not a part-ID/picking image or a collision test.");
            if((string)scene["status"]!="healthy")warnings.Add("Designer scene integrity is inconsistent; screenshot is retained for diagnosis. Do not infer health from a scoped mesh capture.");
            if(args["cuttingOutlinesVisible"]!=null)warnings.Add("Native cutting-outline visibility was explicitly overridden for these images and restored afterward; inspect helperDisplay. No geometry or material was changed.");
            var recommended=new JArray(images.Select(x=>x["file"].DeepClone()));
            var displayOverrides=new JArray(ids.Select(id=>{var state=NativeDisplayState(Part(id));state["partId"]=id;return state;})
                .Where(s=>(bool)s["isDisconnected"]||(bool)s["isHidden"]||(bool)s["overrideMaterialPresent"]||(bool)s["customMaterialPresent"]));
            if(displayOverrides.Count>0)warnings.Add("Some focus parts have native display overrides; inspect nativeDisplayOverrides. A disconnected grey appearance does not prove palette edits failed. Capture preserves this native state.");
            var repeatable=new JArray(views.Select(v=>{var c=v.Camera;var spec=new JObject{["name"]=v.Name,["view"]="fixed",["projection"]=c.Orthographic?"orthographic":"perspective",["position"]=c.Position.Json(),["direction"]=c.Forward.Json(),["up"]=c.Up.Json(),["target"]=c.Target.Json(),["fieldOfViewDegrees"]=c.FieldOfView,["nearClipMetres"]=c.Near,["farClipMetres"]=c.Far};if(c.Orthographic)spec["orthographicSize"]=c.OrthographicSize;return spec;}));
            result.Manifest=new JObject{["captureId"]=job.Id,["identity"]=identity,["capturedAt"]=DateTime.UtcNow.ToString("o"),["capturedFrame"]=Time.frameCount,
                ["backend"]="native_designer_camera",["nativeMaterials"]=true,["includesUi"]=false,["includesGizmos"]=JValue.CreateNull(),["gizmoPolicy"]=gizmoPolicy,["sceneIntegrity"]=scene,["focusPartIds"]=new JArray(ids),
                ["framingBoundsWorld"]=bounds.Json(),["views"]=images,["cameraBefore"]=before,["cameraAfter"]=after,["cameraRestored"]=true,["restorationDiagnostics"]=diagnostic,["warnings"]=warnings,["recommendedImages"]=recommended};
            result.Manifest["files"]=new JArray(result.Files.Select(f=>new JObject{["name"]=f.Key,["bytes"]=f.Value.Length,["sha256"]=VisualCore.Hash(f.Value),["mimeType"]="image/png"}));
            result.Manifest["nativeDisplayOverrides"]=displayOverrides;result.Manifest["repeatableViews"]=repeatable;result.Manifest["repeatableResolution"]=new JObject{["width"]=width,["height"]=height};
            result.Manifest["helperDisplay"]=helperDisplay;
            result.Files["manifest.json"]=Encoding.UTF8.GetBytes(result.Manifest.ToString());SaveVisual(job.Id,result);
            return new JObject{["captureId"]=job.Id,["identity"]=identity.DeepClone(),["backend"]="native_designer_camera",["nativeMaterials"]=true,["includesUi"]=false,["includesGizmos"]=JValue.CreateNull(),["gizmoPolicy"]=gizmoPolicy,
                ["cameraRestored"]=true,["helperDisplay"]=helperDisplay.DeepClone(),["nativeDisplayOverrides"]=displayOverrides.DeepClone(),["repeatableViews"]=repeatable.DeepClone(),["repeatableResolution"]=new JObject{["width"]=width,["height"]=height},["sceneIntegrity"]=scene.DeepClone(),["views"]=images.DeepClone(),["artifactBase"]="v1/visual/"+job.Id+"/",
                ["files"]=new JArray(result.Files.Select(f=>new JObject{["name"]=f.Key,["bytes"]=f.Value.Length,["sha256"]=VisualCore.Hash(f.Value)})),
                ["recommendedImages"]=recommended.DeepClone(),["warnings"]=warnings.DeepClone(),["retention"]="Shared visual cache: up to 15 minutes, 3 captures or 192 MiB; CLI downloads persist."};
        }
    }
}
