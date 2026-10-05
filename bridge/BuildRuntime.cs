using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Assets.Scripts;
using Assets.Scripts.Craft;
using Assets.Scripts.Craft.Exceptions;
using Assets.Scripts.Craft.Parts;
using Assets.Scripts.Craft.Parts.Modifiers;
using Assets.Scripts.Craft.Parts.Modifiers.Variables;
using Assets.Scripts.Design;
using Assets.Scripts.Design.Tools;
using Assets.Scripts.Design.UI.Overload;
using BepInEx.Logging;
using HarmonyLib;
using Cysharp.Threading.Tasks;
using Jundroo.Common.Expressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.EventSystems;
using AssemblyData = Assets.Scripts.Craft.Parts.Assembly;
using SP2Game = Assets.Scripts.Game;

namespace SP2BuildAssistant
{
    public sealed partial class BuildRuntime : MonoBehaviour
    {
        internal readonly ConcurrentQueue<Job> Queue = new ConcurrentQueue<Job>();
        internal ManualLogSource Log;
        internal OperationResults OperationResults;
        private bool busy, uncertain;
        private AircraftScript observedAircraft;
        private string session, fingerprint;
        private long revision;
        private readonly Dictionary<string, XElement> checkpoints = new Dictionary<string, XElement>();
        private readonly Dictionary<string, object> checkpointInfo = new Dictionary<string, object>();
        private readonly List<object> operations = new List<object>();
        private readonly Dictionary<string, JObject> schemaCache = new Dictionary<string, JObject>();
        private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
        public static bool Writing;

        [HarmonyPatch(typeof(Designer), "Update")]
        private static class PauseDesignerInput { private static bool Prefix() { return !Writing && !AcceptanceInputBlocked; } }
        [HarmonyPatch(typeof(Designer), "HandleInput")]
        private static class PausePointerInput { private static bool Prefix() { return !Writing && !AcceptanceInputBlocked; } }

        private void Update() { if (!busy && Queue.TryDequeue(out Job job)) Execute(job).Forget(); }
        private async UniTaskVoid Execute(Job job)
        {
            busy = true;
            lock (job.Sync)
            {
                if (job.CancelRequested) { job.Complete(Json.Fail(new ApiError("cancelled", "Cancelled before execution."))); busy = false; return; }
                job.State = "running";
            }
            JObject result;
            try
            {
                string command = Required(job.Input, "command");
                JObject args = job.Input["args"] as JObject ?? new JObject();
                if (command == "acceptance.native") {
                    var native=await AcceptanceNative(args,job);
                    result=native["success"]==null?Json.Ok(native):native;
                }
                else if (command == "designer.control") result = Json.Ok(await DesignerControl(args,job));
                else if (command == "visual.capture") result = Json.Ok(await VisualCapture(args, job));
                else if (command == "designer.capture") result = Json.Ok(await DesignerCapture(args, job));
                else if (command == "craft.centers") result = Json.Ok(await CraftCenters(args, job));
                else if(new[]{"geometry.measure","geometry.section","geometry.seam","geometry.symmetry"}.Contains(command))result=Json.Ok(await GeometryQuery(command,args,job));
                else if (command == "batch.apply" || command == "craft.undo" || command == "craft.rollback")
                    result = await Mutate(command, args, job);
                else result = Json.Ok(Read(command, args));
            }
            catch (Exception e) { result = Json.Fail(e); Log.LogWarning("Command failed: " + e.Message); }
            job.Complete(result);
            busy = false;
        }
        private Designer Current()
        {
            var d = Designer.Instance;
            if (d == null || d.Aircraft == null || !d.Aircraft.gameObject.activeInHierarchy)
                throw new ApiError("designer_not_ready", "Enter the designer and open an aircraft before inspecting or editing its parts.");
            return d;
        }
        private XElement Observe()
        {
            var d = Current();
            XElement xml = d.Aircraft.Aircraft.GenerateXml(false);
            string hash = SnapshotState.Fingerprint(xml);
            if (observedAircraft != d.Aircraft)
            {
                observedAircraft = d.Aircraft; session = Guid.NewGuid().ToString("N"); revision = 1;
                checkpoints.Clear(); checkpointInfo.Clear(); operations.Clear(); nativeRotations.Clear(); uncertain = false;
            }
            else if (hash != fingerprint) revision++;
            fingerprint = hash; RememberRotations(xml,hash);
            return xml;
        }
        private object Identity() { return new { craftSessionId = session, revision, fingerprint, fingerprintAlgorithm = SnapshotState.Algorithm, gameVersion = SP2Game.Version.ToString(), xmlVersion = AircraftData.CurrentXmlVersion, stateUncertain = uncertain }; }
        private object Read(string cmd, JObject a)
        {
            if (cmd == "capabilities" || cmd == "designer.status")
            {
                // Game.Instance is lazy: querying status during Startup must
                // not construct it before native runtime initialization.
                string nativeScene=UnityEngine.SceneManagement.SceneManager.GetActiveScene().name;
                bool ready = nativeScene=="Designer" && Designer.Instance != null && Designer.Instance.Aircraft != null;
                if (ready) Observe();
                AcceptanceMemoryInventory();
                return new { pluginVersion = "0.5.0", releaseStatus = "released", registryVersion=PropertyRegistry.Version, buildId = typeof(BuildRuntime).Assembly.ManifestModule.ModuleVersionId.ToString(), gameVersion = SP2Game.Version.ToString(), designerReady = ready,
                    identity = ready ? Identity() : null, target = "current_open_designer_only", acceptanceNative=AcceptanceNativeCapability(),
                    scene=nativeScene,designerControl=DesignerControlCapability(),
                    fuselageCrossSectionAttributes = CrossSectionAttributes,
                    fuselageStateAttributes = ExtendedStateAttributes,
                    inputControllerEditing = InputControllerFields.Description(),
                    sceneIntegrity = ready ? DesignerSceneIntegrity(Designer.Instance) : null,
                    runtimeRetention = new { operationResults = OperationResults?.Describe(), managedBytes = GC.GetTotalMemory(false),
                        nativeMeshLifetime=NativeMeshLifetime.Describe(),
                        expressionLifetime=DesignerExpressionLifetime.Describe(),
                        checkpointCount = checkpoints.Count, operationHistoryCount = operations.Count, rotationSnapshotCount = nativeRotations.Count,
                        nativeUndo = ready ? new { count = Designer.Instance.UndoHistory.NumUndoSteps, maximum = Designer.Instance.UndoHistory.MaxUndoSteps,
                            maximumRetainedStates = (long)Designer.Instance.UndoHistory.MaxUndoSteps + 1,
                            meaning = "count includes the current state; maximum is the native undo transition limit. Native history can retain maximum + 1 serialized states.",
                            xmlBytes = Designer.Instance.UndoHistory.UndoSteps.Sum(s => (long)(s.XmlBytes?.Length ?? 0)) } : null,
                        unityMemory = new { allocatedBytes = UnityEngine.Profiling.Profiler.GetTotalAllocatedMemoryLong(),
                            reservedBytes = UnityEngine.Profiling.Profiler.GetTotalReservedMemoryLong(), unusedReservedBytes = UnityEngine.Profiling.Profiler.GetTotalUnusedReservedMemoryLong(),
                            monoUsedBytes = UnityEngine.Profiling.Profiler.GetMonoUsedSizeLong(), monoHeapBytes = UnityEngine.Profiling.Profiler.GetMonoHeapSizeLong(),
                            graphicsDriverAllocatedBytes = UnityEngine.Profiling.Profiler.GetAllocatedMemoryForGraphicsDriver() },
                        meaning = "Diagnostic counts and sampled bytes without forcing garbage collection. Native undo bytes cover XML byte arrays, not all object overhead. Unity counters have overlapping scopes, may report zero on unsupported platforms, and must not be summed or equated with OS private bytes or proof of leak freedom." },
                    commands = new[] { "designer.crafts", "designer.control", "properties.describe", "properties.get", "resources.list", "appearance.get", "groups.resolve", "decal.pose.get", "geometry.measure", "geometry.section", "geometry.seam", "geometry.symmetry", "craft.diff", "craft.snapshot", "parts.list", "parts.get", "parts.assembly", "connections.list", "connections.points", "spatial.query",
                        "catalog.categories", "catalog.subcategories", "catalog.list", "catalog.search", "catalog.get", "catalog.schema", "catalog.export",
                        "outputs.list", "variables.list", "funky.list", "funky.describe", "funky.validate", "batch.preview", "batch.apply",
                        "craft.history", "craft.undo", "craft.checkpoint.create", "craft.checkpoint.list", "craft.checkpoint.get", "craft.rollback",
                        "designer.selection", "parts.geometry", "designer.raycast", "designer.capture", "shape.get", "shape.schema", "symmetry.get", "visual.resolve", "visual.capture", "visual.pick", "craft.centers" },
                    designerCapture = new { backend="native_designer_camera", nativeMaterials=true, includesUi=false, includesGizmos=(bool?)null, gizmoPolicy="native_scene_helpers_preserved_separate_overlay_cameras_excluded", preservesPlayerCamera=true,
                        projections=new[]{"current","perspective","orthographic"}, maxViews=8, maxResolution=2048, allowsInconsistentSceneForDiagnosis=true },
                    centersAnalysis = new { calculationVersion=CentersCore.Version, readOnly=true, scope="native_designer", images=true, baselineComparison=true, flightStabilitySolver=false },
                    visualInspection = new { backend="cpu_mesh_analysis", nativeMaterials=false, coordinateFrames=new[]{"world","part"}, maxGroups=8, maxParts=2048, maxTriangles=500000, maxVertices=1200000, maxPixels=16000000, selectors=new[]{"parts","selected","craft","assembly","branch","neighborhood"}, artifactRetentionMinutes=15, detailModes=new[]{"auto","none","perGroup"}, defaultDetails="auto" },
                    partReferencePolicy = "Numeric IDs are revision-scoped. Deleted numeric and temporary references are invalid within a batch; use a fresh temporaryId for replacements. Reuse events use zero-based operation indices.",
                    structuredReadViews = new[] { "connections.list", "variables.list", "outputs.list" },
                    revisionMeaning = "Revision tracks the observed XML fingerprint, not successful command count. A failed batch can advance it after native recovery; use the returned identity or read a fresh status.",
                    geometryRefresh = "native_rebuild_then_recook_physics_and_editor_caches",
                    assemblyDeletion = new { supportedRoots=new[]{"proceduralMissile","wing"}, preview="parts.assembly", defaultCascade=false, recursiveGraphTraversal=false },
                    limitations = new[] { "Typed shape updates support JFuselage, JWing and native control surfaces; query shape.schema for exact coverage.",
                        "Mod-specific behavior is not fully certified.", "No offline saved-aircraft operations, telemetry evaluation or persistent cross-restart checkpoints." } };
            }
            if (cmd=="designer.crafts")return DesignerCrafts(a);
            if (cmd.StartsWith("catalog.")) return Catalog(cmd, a);
            if (cmd=="properties.describe" || cmd=="properties.get") { Observe(); return PropertiesRead(cmd,a); }
            if (cmd == "funky.list" || cmd == "funky.describe") return Funky(a, cmd == "funky.describe");
            if (cmd == "visual.pick") return VisualPick(a);
            if (cmd == "visual.resolve") return VisualResolve(a);
            XElement xml = Observe();
            var d = Current();
            if (IsAdvancedRead(cmd)) return AdvancedRead(cmd, a);
            if(cmd=="appearance.get")return AppearanceGet(a);
            if(cmd=="resources.list")return ResourcesList(a);
            if(cmd=="groups.resolve")return GroupsResolve(a);
            if(cmd=="decal.pose.get")return DecalPoseGet(a);
            if (cmd == "craft.snapshot")
            {
                var result = new JObject { ["identity"] = JToken.FromObject(Identity()), ["name"] = d.Aircraft.Aircraft.Name,
                    ["partCount"] = d.Aircraft.Aircraft.Assembly.Parts.Count,
                    ["selectedPartId"] = d.SelectedPart == null ? (JToken)null : d.SelectedPart.Part.Id,
                    ["parts"] = new JArray(d.Aircraft.Aircraft.Assembly.Parts.Select(p => PartInfo(p, false))),
                    ["connections"] = Node(xml.Element("Assembly")?.Element("Connections")),
                    ["variables"] = Node(xml.Element("Variables")), ["coordinateSystem"] = "Unity world; metres; Euler degrees; quaternion x,y,z,w" };
                if (a.Value<bool?>("includeXml") == true) {
                    result["xml"] = xml.ToString(SaveOptions.DisableFormatting);
                    result["xmlMetadataCaveat"]="Aircraft size/boundsMin/boundsOffset are native save-time metadata and may lag current part geometry. The XML preserves those values unchanged. Use parts.geometry or a same-revision visual capture for current bounds; do not infer live craft dimensions from these XML attributes.";
                }
                return result;
            }
            if (cmd == "parts.list") return new { identity = Identity(), listing = Page(d.Aircraft.Aircraft.Assembly.Parts
                .Where(p => a["type"] == null || p.PartType.PartTypeId == (string)a["type"])
                .Where(p => a["query"] == null || (p.Name ?? "").IndexOf((string)a["query"], StringComparison.OrdinalIgnoreCase) >= 0)
                .Select(p => (object)PartInfo(p, false)), a) };
            if (cmd == "parts.get") return new { identity = Identity(), part = PartInfo(Part(Int(a, "id")), true) };
            if (cmd == "parts.assembly") {
                if(a["symmetric"]!=null && a["symmetric"].Type!=JTokenType.Boolean)throw new ApiError("invalid_input","symmetric must be a JSON boolean.");
                return new { identity=Identity(), assembly=AssemblyInfo(Part(Int(a,"id")),a.Value<bool?>("symmetric")==true) };
            }
            if (cmd == "connections.list") {
                string view = ReadModels.View(a); var nodes = xml.Element("Assembly")?.Element("Connections");
                if (view == "structured") { var rows = ReadModels.Connections(nodes); return new { identity = Identity(), view, connections = rows, count = rows.Count,
                    meaning = "Native connection rows. Each endpoint can contain multiple attach-point IDs; graph connectivity does not imply physical support or snapping." }; }
                return new { identity = Identity(), view, connections = Node(nodes) };
            }
            if (cmd == "connections.points") return new { identity = Identity(), points = Points(Part(Int(a, "part"))) };
            if (cmd == "spatial.query")
            {
                var pa = Part(Int(a, "partA")); var pb = Part(Int(a, "partB"));
                return new { identity = Identity(), deltaWorld = Vec(pb.PartScript.transform.position - pa.PartScript.transform.position),
                    positionBInA = Vec(pa.PartScript.transform.InverseTransformPoint(pb.PartScript.transform.position)),
                    distanceMetres = Vector3.Distance(pa.PartScript.transform.position, pb.PartScript.transform.position) };
            }
            if (cmd == "outputs.list") {
                string view = ReadModels.View(a); var selected = d.Aircraft.Aircraft.Assembly.Parts.Where(p => a["part"] == null || p.Id == Int(a, "part"));
                if (view == "structured") { var sources = OutputSources(selected); return new { identity = Identity(), view, sources, sourceCount = sources.Count,
                    meaning = "Only parts with output definitions; sources[].modifiers is shared with variables.list structured view." }; }
                return new { identity = Identity(), view, parts = new JArray(selected.Select(p => new JObject { ["partId"] = p.Id, ["modifiers"] = Outputs(p) })) };
            }
            if (cmd == "variables.list") {
                string view = ReadModels.View(a);
                if (view == "structured") { var setters = ReadModels.Setters(xml.Element("Variables")); var sources = OutputSources(d.Aircraft.Aircraft.Assembly.Parts);
                    return new { identity = Identity(), view, setters, setterCount = setters.Count, sources, sourceCount = sources.Count,
                        meaning = "Setters are in native evaluation order; index is the current zero-based position. Re-query after edits. Sources use the same structure as outputs.list structured view." }; }
                return new { identity = Identity(), view, setters = Node(xml.Element("Variables")), sources = new JArray(d.Aircraft.Aircraft.Assembly.Parts.Select(p => new JObject { ["partId"] = p.Id, ["outputs"] = Outputs(p) })) };
            }
            if (cmd == "funky.validate")
            {
                string expression = Required(a, "expression");
                if ((string)a["type"] == "bool") Parser.Process<bool>(expression, d.Aircraft.ExpressionContext);
                else Parser.Process<float>(expression, d.Aircraft.ExpressionContext);
                return new { identity = Identity(), valid = true, compiledOnly = true, evaluated = false };
            }
            if(cmd=="craft.diff") {
                string id=Required(a,"checkpointId");
                if(!checkpoints.ContainsKey(id)) throw new ApiError("checkpoint_not_found","Checkpoint does not belong to this session.");
                return new {identity=Identity(),checkpointId=id,diff=CraftDiff.Compare(checkpoints[id],xml,a.Value<int?>("limit")??1000)};
            }
            if (cmd == "craft.checkpoint.create")
            {
                Guard(a);
                if (checkpoints.Count >= 64) throw new ApiError("checkpoint_capacity", "Maximum 64 checkpoints per open craft session.");
                string id = Guid.NewGuid().ToString("N");
                checkpoints.Add(id, new XElement(xml));
                var info = new { id, name = (string)a["name"] ?? id, craftSessionId = session, revision, fingerprint, createdAt = DateTime.UtcNow.ToString("o") };
                checkpointInfo.Add(id, info); return info;
            }
            if (cmd == "craft.checkpoint.list") return new { identity = Identity(), checkpoints = checkpointInfo.Values.ToArray() };
            if (cmd == "craft.checkpoint.get")
            {
                string id = Required(a, "id");
                if (!checkpointInfo.ContainsKey(id)) throw new ApiError("checkpoint_not_found", "Checkpoint does not belong to the current open craft session.");
                return new { identity = Identity(), checkpoint = checkpointInfo[id] };
            }
            if (cmd == "craft.history") return new { identity = Identity(), operations,
                nativeSteps = d.UndoHistory.UndoSteps.Select((s, index) => new { index, s.Description, time = s.DateTime.ToString("o"), hash = BitConverter.ToString(s.Hash).Replace("-", "").ToLowerInvariant() }).ToArray(),
                canUndo = d.UndoHistory.UndoStepsAvailable, canRedo = d.UndoHistory.RedoStepsAvailable };
            if (cmd == "batch.preview")
            {
                return PreviewEditPlan(a);
            }
            throw new ApiError("unsupported_command", "Unknown command: " + cmd);
        }
        private void Guard(JObject a, bool explicitRecovery = false)
        {
            if (uncertain && !explicitRecovery) throw new ApiError("state_uncertain", "Previous recovery failed. Inspect the current craft; explicitly roll back to a known session checkpoint or reopen it.");
            if (Required(a, "craftSessionId") != session) throw new ApiError("session_conflict", "The current open aircraft changed.");
            if (a["expectedRevision"] == null || a.Value<long>("expectedRevision") != revision) throw new ApiError("revision_conflict", "Aircraft changed. Read a fresh snapshot and replan.");
        }
        private static void CheckBatch(JObject a)
        {
            var ops = a["operations"] as JArray;
            if (ops == null || ops.Count == 0 || ops.Count > 100) throw new ApiError("invalid_batch", "operations must contain 1..100 operations.");
            var kinds = new[] { "part.add", "part.update", "part.delete", "connection.connect", "connection.disconnect", "variable.add", "variable.update", "variable.delete", "variable.reorder", "output.bind", "output.update", "output.unbind", "craft.refresh", "shape.update", "wing.control.add", "fuselage.match", "symmetry.link", "symmetry.unlink", "symmetry.create", "symmetry.enable" };
            foreach (JToken token in ops) {
                var op = token as JObject; if (op == null || !(kinds.Contains(Required(op, "kind")) || new[]{"properties.set","appearance.set","transform.apply","transform.align","decal.pose.set"}.Contains((string)op["kind"]))) throw new ApiError("unsupported_operation", "Unsupported operation kind.");
                ValidateOperationFields(op);
            }
        }
        private async UniTask<JObject> Mutate(string command, JObject a, Job job)
        {
            Observe(); Guard(a, command == "craft.rollback");
            if (string.IsNullOrEmpty(job.Key)) throw new ApiError("request_id_required", "Writes require an outer requestId for retry safety.");
            var d = Current();
            if (command == "batch.apply") CheckBatch(a);
            EnsureDesignerSceneIntegrity(d);
            if (command == "craft.rollback" && !checkpoints.ContainsKey(Required(a, "checkpointId"))) throw new ApiError("checkpoint_not_found", "Checkpoint is unavailable in this craft session.");
            await d.UndoHistory.CompletePendingOperations();
            XElement before = Observe(); Guard(a, command == "craft.rollback");
            var priorHead = await d.UndoHistory.GetCurrentUndoStep();
            if (command == "craft.undo")
            {
                if (!d.UndoHistory.UndoStepsAvailable) throw new ApiError("undo_unavailable", "No previous native history step.");
                string expected = (string)a["expectedHeadHash"];
                if (expected != null && expected != BitConverter.ToString(priorHead.Hash).Replace("-", "").ToLowerInvariant()) throw new ApiError("history_conflict", "History head changed.");
            }
            var events = EventSystem.current;
            bool oldEventsEnabled = events != null && events.enabled;
            if (events != null) events.enabled = false;
            Writing = true;
            selectionCaptured = false; CaptureSelection(d);
            wingsToValidate.Clear();
            requiredPoses.Clear();
            rebuildCount=0;var clock=System.Diagnostics.Stopwatch.StartNew();var timings=new JObject();double previousStage=0;
            Action<string> stage=name=>{double now=clock.Elapsed.TotalMilliseconds;timings[name]=now-previousStage;previousStage=now;};
            var changed = new JArray(); var refs = new BatchReferences(ReferenceParts());
            string beforeHash = fingerprint;
            long beforeRevision = revision;
            bool beforeUncertain = uncertain;
            var recoveryHead = priorHead;
            XElement restorationTarget = null;
            try
            {
                // Ensure the exact initial state is in native history, including uncommitted player edits.
                if (command != "craft.undo" && (priorHead == null || SnapshotState.Fingerprint(priorHead.ReadXml()) != beforeHash))
                    recoveryHead = await d.CreateUndoStepAsync("SP2Build baseline", null, before);
                if (command == "craft.undo")
                {
                    var undoStep = await d.UndoHistory.GetNextUndoStep();
                    if (undoStep == null) throw new ApiError("undo_unavailable", "No previous native history step.");
                    restorationTarget = undoStep.ReadXml();
                    Replace(new XElement(restorationTarget));
                    changed.Add(new JObject { ["kind"] = "craft.undo" });
                }
                else if (command == "craft.rollback")
                {
                    string checkpoint = Required(a, "checkpointId");
                    if (!checkpoints.TryGetValue(checkpoint, out XElement target)) throw new ApiError("checkpoint_not_found", "Checkpoint is unavailable in this craft session.");
                    restorationTarget = new XElement(target);
                    Replace(new XElement(target)); changed.Add(new JObject { ["kind"] = "craft.rollback", ["checkpointId"] = checkpoint });
                }
                else
                {
                    CheckBatch(a);
                    await ApplyOperationSequence((JArray)a["operations"],refs,changed);
                    d.OnAircraftStructureChanged();
                }
                AcceptanceFault("after_operations");
                ValidateDesignerExpressions(d.Aircraft);
                stage("nativeOperationsAndExpressionsMs");
                // Native geometry/intersection queues finish after Update, sometimes
                // across several physics frames. Do not validate a partially rebuilt craft.
                await ReadSettled(d, restorationTarget);
                stage("firstSettleMs");
                ValidateEditedWings();
                ValidateRequiredPoses();
                RefreshEditorGeometry(d);
                await ReadSettled(d, restorationTarget);
                stage("physicsAndEditorRefreshMs");
                AcceptanceFault("after_refresh");
                d.UpdateSymmetryConfig();
                RestoreSelection(d);
                EnsureDesignerSceneIntegrity(d);
                if (retainedSelection.HasValue && refs.WasDeleted(retainedSelection.Value)) d.SelectedPart = null;
                AcceptanceFault("before_commit");
                if (command != "craft.undo") await d.CreateUndoStepAsync("SP2Build " + job.Id.Substring(0, 8));
                AcceptanceFault("after_commit");
                RefreshSelectedPropertyWidgets(d);
                XElement readback = Observe();
                stage("historyAndReadbackMs");
                foreach(JObject row in changed.Where(x=>(string)x["kind"]=="properties.set")){
                    var p=d.Aircraft.Aircraft.Assembly.GetPartById((int)row["partId"]);
                    if(p==null){row["supersededByLaterOperation"]=true;continue;}
                    var finalFields=PropertyRegistry.Entries(p).ToDictionary(x=>x.Id);
                    foreach(JObject field in (JArray)row["effectiveChanges"]){PropertyEntry entry;
                        if(finalFields.TryGetValue((string)field["propertyId"],out entry)){field["effective"]=PropertyValues.Read(entry.RawValue());field["valueStage"]="final_settled_batch";field["normalizationReason"]=JToken.DeepEquals(field["requested"],field["effective"])?null:"Final native state differs from requested representation or was superseded by a later operation.";}
                    }
                }
                bool restorationVerified = restorationTarget == null || SnapshotState.EquivalentAfterNativeRestore(restorationTarget, readback);
                if (!restorationVerified) throw new ApiError("restore_mismatch", "Native restore changed fields beyond the documented Euler reconstruction tolerance.");
                if (command == "craft.rollback") uncertain = false;
                string automaticId = "before-" + job.Id;
                if (checkpoints.Count < 64) { checkpoints[automaticId] = new XElement(before); checkpointInfo[automaticId] = new { id = automaticId, name = "Before " + job.Id, craftSessionId = session, fingerprint = beforeHash }; }
                var data = new { identity = Identity(), operationId = job.Id, actualChanges = changed, temporaryIds = refs.LiveBindings, rebuildCount, stageTimings=timings, effectiveChanges=CraftDiff.Compare(before,readback),
                    reusedPartIds = refs.ReusedPartIds, invalidatedTemporaryIds = refs.InvalidatedBindings,
                    beforeCheckpointId = checkpoints.ContainsKey(automaticId) ? automaticId : null,
                    validation = new { readBack = true, expressionCompile = true, geometryRefreshed = true, physicsSynchronized = true, editorCachesRebuilt = true, partCount = d.Aircraft.Aircraft.Assembly.Parts.Count,
                        sceneIntegrityVerified = true, restorationVerified = restorationTarget == null ? (bool?)null : restorationVerified, restoreEulerToleranceDegrees = SnapshotState.RestoreEulerToleranceDegrees, retainedNativeCaches=new JArray(retainedRestoreCaches) },
                    rollbackResult = new { required = false }, selectedPartId = d.SelectedPart == null ? (int?)null : d.SelectedPart.Part.Id };
                operations.Add(new { operationId = job.Id, command, revision, beforeFingerprint = beforeHash, fingerprint });
                return Json.Ok(data);
            }
            catch (Exception error)
            {
                Log.LogWarning("Mutation failed: " + error);
                bool restored = false; string recoveryError = null;
                try
                {
                    // Guard errors inside the try may occur before mutation; never load another craft.
                    if (Current() != d || observedAircraft != d.Aircraft) throw new ApiError("session_conflict", "Designer session changed during execution.");
                    Replace(new XElement(before));
                    ValidateDesignerExpressions(d.Aircraft);
                    if (recoveryHead != null) await d.UndoHistory.SetCurrentUndoStep(recoveryHead);
                    await ReadSettled(d, before);
                    RefreshEditorGeometry(d);
                    RestoreSelection(d);
                    EnsureDesignerSceneIntegrity(d);
                    XElement recovered = Observe(); restored = SnapshotState.EquivalentAfterNativeRestore(before, recovered);
                    if (!restored) recoveryError = "Native normalization differs from the starting snapshot; inspect readback.";
                }
                catch (Exception recovery) { recoveryError = recovery.Message; }
                // A timeout must never leave a stale fingerprint in a failure receipt.
                bool recoveryReadback=false;
                try { if(Current()==d && observedAircraft==d.Aircraft) { Observe(); recoveryReadback=true; } }
                catch(Exception readbackError) { recoveryError += "; readback: "+readbackError.Message; }
                uncertain = !restored || beforeUncertain;
                var result = Json.Fail(error);
                result["rollbackResult"] = new JObject { ["attempted"] = true, ["restored"] = restored, ["error"] = recoveryError,
                    ["beforeRevision"] = beforeRevision, ["currentRevision"] = revision, ["revisionChanged"] = revision != beforeRevision,
                    ["revisionMeaning"] = "Failure does not freeze revision: native recovery can change serialized Euler angles within tolerance. Use returned identity; never blindly reuse the previous revision.",
                    ["readBack"] = recoveryReadback, ["restoreEulerToleranceDegrees"] = SnapshotState.RestoreEulerToleranceDegrees, ["fingerprintIdentical"] = recoveryReadback?(JToken)(fingerprint == beforeHash):null, ["beforeFingerprint"] = beforeHash, ["currentFingerprint"] = recoveryReadback?fingerprint:null };
                result["rollbackResult"]["retainedNativeCaches"]=new JArray(retainedRestoreCaches);
                result["identity"] = JToken.FromObject(Identity());
                return result;
            }
            finally { Writing = false; selectionCaptured = false; wingsToValidate.Clear(); requiredPoses.Clear(); retainedRestoreCaches.Clear(); if (events != null) events.enabled = oldEventsEnabled; }
        }
        private void TrackInternal() { observedAircraft = Current().Aircraft; }
        private async UniTask ReadSettled(Designer designer, XElement expected)
        {
            string previous = null; int stableFrames = 0; XElement last=null;bool pending=true;int frames=0;bool cachesRetained=false;
            float deadline = Time.realtimeSinceStartup + 15f;
            for (int frame = 0; frame < 900; frame++)
            {
                await UniTask.NextFrame(PlayerLoopTiming.LastPostLateUpdate);
                if (Current() != designer || observedAircraft != designer.Aircraft)
                    throw new ApiError("session_conflict", "Designer session changed while waiting for native geometry.");
                XElement xml = designer.Aircraft.Aircraft.GenerateXml(false);last=xml;frames=frame+1;pending=GeometryPending(designer);
                string hash = SnapshotState.Fingerprint(xml) + GeometrySignature(designer);
                stableFrames = hash == previous && !pending ? stableFrames + 1 : 0; previous = hash;
                if (stableFrames >= 3 && (expected == null || SnapshotState.EquivalentAfterNativeRestore(expected, xml))) return;
                if(stableFrames>=3 && expected!=null && !cachesRetained && RetainNativeRestoreCaches(designer,expected,xml))
                {
                    cachesRetained=true;stableFrames=0;previous=null;
                }
                if (Time.realtimeSinceStartup >= deadline) break;
            }
            throw new ApiError("native_settle_timeout", "Native state did not settle within fifteen seconds; inspect details to distinguish geometry from restore mismatch.",new JObject{
                ["geometryPending"]=pending,["stableFrames"]=stableFrames,["frames"]=frames,["restoreComparison"]=expected==null?null:CraftDiff.Compare(expected,last,100)});
        }
        private static void ValidateDesignerExpressions(AircraftScript aircraft)
        {
            // Native VariableOutput.InitScript is flight-only. RecompileAll dereferences
            // its uninitialized flight script for any output activator in the designer.
            // Compile the same activators against the part/aircraft context without
            // initializing flight getters or evaluating aircraft telemetry.
            aircraft.VariableSystem.RefreshVariables();
            foreach (var setter in aircraft.VariableSystem.Setters) setter.Compile(aircraft);
            foreach (var part in aircraft.Aircraft.Assembly.Parts)
                foreach (var modifier in part.Modifiers)
                    foreach (var output in modifier.VariableOutputs)
                        if (!string.IsNullOrEmpty(output.Activator)) Parser.Process<bool>(output.Activator, aircraft.ExpressionContext);
        }
        private void Replace(XElement xml)
        {
            rebuildCount++;
            var d = Current();
            CaptureSelection(d);
            var retainedRotations=RetainedRotations(xml);
            var data = new AircraftData(new XElement(xml), CraftLoadContext.Designer);
            if (data.Assembly.MissingParts.Count != 0) throw new ApiError("missing_parts", string.Join(",", data.Assembly.MissingParts));
            RetainSerializedScales(data, xml);
            GameObject created = null;
            try
            {
                created = AircraftData.GenerateGameObject(data, CreationInfo(), 0);
                RestoreNativeRotations(created.GetComponent<AircraftScript>(),retainedRotations);
                ValidateDesignerExpressions(created.GetComponent<AircraftScript>());
                // Destroy is deferred by Unity: disable the outgoing colliders immediately.
                var outgoing = d.Aircraft.gameObject;
                d.SelectedPart = null; d.Tools.SelectMovePartTool();
                ReplacementLifetime.Adopt(
                    () => { try { d.AssignAircraft(created); } finally { TrackInternal(); } },
                    () => d.Aircraft != null && d.Aircraft.gameObject == outgoing,
                    () => outgoing.SetActive(false),
                    () => { if (outgoing != null) outgoing.SetActive(true); },
                    () => { if (outgoing != null) UnityEngine.Object.Destroy(outgoing); });
            }
            catch (Exception e)
            {
                if (created != null && created != d.Aircraft.gameObject) UnityEngine.Object.Destroy(created);
                var load = e as CraftLoadException;
                if (load?.CraftScript != null && load.CraftScript != d.Aircraft) UnityEngine.Object.Destroy(load.CraftScript.gameObject);
                throw;
            }
        }
        private static PartData.PartCreationInfo CreationInfo()
        { return new PartData.PartCreationInfo { CreateHingeJoints = false, IsRigidBodyKinematic = true, CreateRigidBody = false, EnableWingScript = false }; }
        private IEnumerable<JObject> ReferenceParts()
        { return Current().Aircraft.Aircraft.Assembly.Parts.Select(PartSummary); }
        private JObject Apply(JObject op, BatchReferences refs)
        {
            // Native symmetry callbacks in connect/delete also read this cache.
            // Refresh after the guard and before every operation, including after
            // earlier operations moved/rebuilt the main control part.
            Current().UpdateSymmetryConfig();
            if((string)op["kind"]=="part.update"&&(op["changes"] as JArray)?.Any(c=>((string)c["path"]=="Part"||c["path"]==null)&&new[]{"position","rotation"}.Contains((string)c["attribute"]))==true){
                var p=Part(refs.Resolve(op["partId"]));requiredPoses.Remove(p.Id);foreach(var peer in SymmetricTargets(p,op.Value<bool?>("symmetric")??false))requiredPoses.Remove(peer.Id);
            }
            var change = ApplyCore(op, refs);
            int[] removed = refs.Observe(ReferenceParts());
            foreach(int id in removed)requiredPoses.Remove(id);
            if (removed.Length > 0 && change["deletedPartIds"] == null) change["deletedPartIds"] = new JArray(removed);
            return change;
        }
        private JObject ApplyCore(JObject op, BatchReferences refs)
        {
            string kind = Required(op, "kind"); var d = Current();
            if (kind=="properties.set") return PropertiesSet(op,refs);
            if (kind=="appearance.set") return AppearanceSet(op);
            if (kind=="transform.apply") return TransformApply(op,refs);
            if (kind=="transform.align") return TransformAlign(op,refs);
            if (kind=="decal.pose.set") return DecalPoseSet(op,refs);
            if (IsAdvancedWrite(kind)) return AdvancedWrite(op, refs);
            if (kind == "part.add")
            {
                DesignerPart template = FindTemplate(Required(op, "templateId"));
                if (!Creatable(template)) throw new ApiError("part_restricted", "Template is not creatable in this level.");
                var assembly = new AssemblyData(new XElement(template.AssemblyElement), AircraftData.CurrentXmlVersion, CraftLoadContext.Designer);
                var newParts = assembly.Parts.ToList();
                assembly.CreateGameObjects(d.Aircraft, CreationInfo(), d.Aircraft.Children);
                Vector3 origin = newParts[0].PartScript.transform.position;
                Quaternion rotation = Quaternion.Euler(Vector(op["rotation"], Vector3.zero));
                Vector3 position = Vector(op["position"], origin);
                foreach (PartData p in newParts)
                {
                    p.PartScript.transform.position = position + rotation * (p.PartScript.transform.position - origin);
                    p.PartScript.transform.rotation = rotation * p.PartScript.transform.rotation;
                    p.PartScript.OnPartAdded();
                }
                d.Aircraft.Aircraft.Assembly.Absorb(assembly);
                string temp = (string)op["temporaryId"];
                if (!string.IsNullOrEmpty(temp))
                { if (refs.ContainsKey(temp)) throw new ApiError("duplicate_temporary_id", "Duplicate temporary ID."); refs.Add(temp, newParts[0].Id); }
                return new JObject { ["kind"] = kind, ["partIds"] = new JArray(newParts.Select(p => p.Id)), ["templateId"] = (string)op["templateId"] };
            }
            int id = Resolve(op["partId"], refs);
            if (kind == "part.delete")
            {
                var p = Part(id);
                if(op.Value<bool?>("assembly")==true)return DeleteAssembly(p,op.Value<bool?>("symmetric")==true);
                if (p.PartScript == d.Aircraft.MainCockpit) throw new ApiError("main_cockpit_delete", "Replace the main cockpit in the game before deleting it.");
                d.DeletePart(p.PartScript, op.Value<bool?>("symmetric") == true);
                return new JObject { ["kind"] = kind, ["partId"] = id };
            }
            if (kind == "connection.connect" || kind == "connection.disconnect")
            {
                var pa = Part(Resolve(op["partA"], refs)); var pb = Part(Resolve(op["partB"], refs));
                if (pa == pb) throw new ApiError("invalid_connection", "Cannot connect a part to itself.");
                if (kind == "connection.disconnect")
                {
                    var connections = pa.PartConnections.Where(c => c.PartA == pb || c.PartB == pb).ToArray();
                    if (connections.Length == 0) throw new ApiError("connection_not_found", "No connection between the specified parts.");
                    foreach (var c in connections) c.DestroyConnection(false, op.Value<bool?>("symmetric") == true, true);
                }
                else
                {
                    var ap = pa.GetAttachPoint(Int(op, "attachPointA")); var bp = pb.GetAttachPoint(Int(op, "attachPointB"));
                    var reasons = new JArray();
                    if (ap == null) reasons.Add("source_attach_point_missing");
                    else if (!ap.IsAvailable && !ap.AllowMultipleManualConnections) reasons.Add("source_attach_point_occupied");
                    if (bp == null) reasons.Add("target_attach_point_missing");
                    else if (!bp.IsAvailable && !bp.AllowMultipleManualConnections) reasons.Add("target_attach_point_occupied");
                    if (ap != null && bp != null && !bp.CanReceive(ap)) reasons.Add("target_cannot_receive_source");
                    if (reasons.Count > 0)
                        throw new ApiError("invalid_connection", "Connection creation is directed: partB's attach point must receive partA's. Inspect reasons and endpoint metadata.", new JObject {
                            ["operationIndex"] = refs.OperationIndex, ["reasons"] = reasons,
                            ["source"] = new JObject { ["part"] = PartSummary(pa), ["attachPointId"] = Int(op,"attachPointA"), ["point"] = Points(pa).FirstOrDefault(p => (int)p["id"] == Int(op,"attachPointA")) },
                            ["target"] = new JObject { ["part"] = PartSummary(pb), ["attachPointId"] = Int(op,"attachPointB"), ["point"] = Points(pb).FirstOrDefault(p => (int)p["id"] == Int(op,"attachPointB")) },
                            ["reverseDirectionCompatible"] = ap != null && bp != null && ap.CanReceive(bp),
                            ["meaning"] = "connections.list rows are undirected stored topology, not a directed connect recipe. reverseDirectionCompatible tests native type compatibility only; availability and other native callbacks must still succeed. No endpoints were automatically swapped."
                        });
                    int count = pa.PartConnections.Count;
                    MovePartTool.ConnectPartToAttachPoint(ap.AttachPointScript, bp.AttachPointScript, op.Value<bool?>("symmetric") == true, false, new List<(PartData, PartData)>());
                    if (pa.PartConnections.Count == count) throw new ApiError("connection_rejected", "Native game did not create the connection.");
                }
                return new JObject { ["kind"] = kind, ["partA"] = pa.Id, ["partB"] = pb.Id };
            }
            XElement xml = d.Aircraft.Aircraft.GenerateXml(false);
            if (kind == "part.update")
            {
                var p = Part(id);
                XElement partXml = xml.Element("Assembly").Element("Parts").Elements("Part").Single(e => (int)e.Attribute("id") == id);
                var changes = op["changes"] as JArray;
                if (changes == null || changes.Count == 0) throw new ApiError("invalid_changes", "changes must contain path/attribute/value objects.");
                ApplyRawChanges(p,partXml,changes);
                foreach(var peer in SymmetricTargets(p,op.Value<bool?>("symmetric")==true))
                {
                    if(changes.Cast<JObject>().Any(c=>(string.IsNullOrEmpty((string)c["path"]) || (string)c["path"]=="Part") && new[]{"position","rotation","scale"}.Contains((string)c["attribute"])))throw new ApiError("symmetry_transform_unsupported","Raw position/rotation/scale propagation requires individual poses; use symmetric:false and explicit target poses.");
                    var target=XmlPart(xml,peer.Id);var shape=ShapeCodec.State(target);
                    if(shape!=null && MirrorMode)ShapeCodec.Mirror(shape);
                    ApplyRawChanges(peer,target,changes);
                    if(shape!=null && MirrorMode)ShapeCodec.Mirror(shape);
                }
            }
            else if (kind.StartsWith("variable.")) EditSetter(xml, kind, op);
            else if (kind.StartsWith("output.")) EditOutput(xml, Part(id), kind, op);
            else throw new ApiError("unsupported_operation", kind);
            Replace(xml);
            return new JObject { ["kind"] = kind, ["partId"] = id == 0 ? (JToken)null : id, ["editMode"] = "current_craft_rebuild" };
        }
        private static void ApplyRawChanges(PartData part,XElement xml,JArray changes)
        {
            foreach(JObject change in changes) {
                string path=(string)change["path"]??"", attribute=Required(change,"attribute");
                if(new[]{"id","partType","symmetryId","symmetryDisabled","materials"}.Contains(attribute))throw new ApiError("read_only","Use specialized editing for structural references.");
                XElement node=SelectPath(xml,path);ValidateAttribute(part,node,attribute,change["value"]);node.SetAttributeValue(attribute,XmlValue(change["value"]));
                if(node.Name.LocalName=="InputController.State" && (attribute=="input" || attribute=="activationGroup"))
                    ValidateInputControllerExpression(part,attribute,(string)node.Attribute(attribute));
            }
        }
        private void EditSetter(XElement xml, string kind, JObject op)
        {
            XElement vars = xml.Element("Variables"); if (vars == null) { vars = new XElement("Variables"); xml.Add(vars); }
            var setters = vars.Elements("Setter").ToList();
            int index = op.Value<int?>("index") ?? -1;
            if (kind == "variable.reorder")
            {
                int[] order = ReadModels.Reorder(op["order"], setters.Count);
                vars.ReplaceNodes(order.Select(i => setters[i])); return;
            }
            XElement target;
            if (kind == "variable.add") { target = new XElement("Setter"); vars.Add(target); }
            else { if (index < 0 || index >= setters.Count) throw new ApiError("setter_not_found", "Use the zero-based setter index."); target = setters[index]; }
            if (kind == "variable.delete") { target.Remove(); return; }
            if (op["variable"] != null) { VariableName((string)op["variable"]); target.SetAttributeValue("variable", (string)op["variable"]); }
            if (op["function"] != null) target.SetAttributeValue("function", (string)op["function"]);
            if (op["priority"] != null) target.SetAttributeValue("priority", Int(op, "priority"));
            else if (kind == "variable.add") target.SetAttributeValue("priority", 0);
            if (op["activator"] != null) target.SetAttributeValue("activator", (string)op["activator"]);
            if (target.Attribute("variable") == null || target.Attribute("function") == null) throw new ApiError("invalid_setter", "variable and function are required.");
        }
        private void EditOutput(XElement xml, PartData part, string kind, JObject op)
        {
            string state = Required(op, "modifier"); string outputId = Required(op, "outputId");
            var modifier = part.Modifiers.FirstOrDefault(m => m.StateElementName == state);
            if (modifier?.VariableOutputDefinitions == null || !modifier.VariableOutputDefinitions.Any(v => v.Id == outputId)) throw new ApiError("output_not_found", "Query outputs.list for the native modifier and output IDs.");
            XElement node = xml.Element("Assembly").Element("Parts").Elements("Part").Single(e => (int)e.Attribute("id") == part.Id).Element(state);
            if (node == null) throw new ApiError("modifier_not_found", state);
            XElement variables = node.Element("Variables"); if (variables == null) { variables = new XElement("Variables"); node.Add(variables); }
            var target = variables.Elements("VariableOutput").FirstOrDefault(e => (string)e.Attribute("id") == outputId);
            if (kind == "output.unbind") { if (target != null) target.Remove(); return; }
            if (kind == "output.update" && target == null) throw new ApiError("binding_not_found", outputId);
            if (target == null) { target = new XElement("VariableOutput", new XAttribute("id", outputId), new XAttribute("priority", 0)); variables.Add(target); }
            if (op["variable"] != null) { VariableName((string)op["variable"]); target.SetAttributeValue("variable", (string)op["variable"]); }
            if (op["priority"] != null) target.SetAttributeValue("priority", Int(op, "priority"));
            if (op["activator"] != null) target.SetAttributeValue("activator", (string)op["activator"]);
            if (target.Attribute("variable") == null) throw new ApiError("invalid_binding", "variable is required.");
        }
        private void VariableName(string name)
        {
            if (name == null || !Regex.IsMatch(name, "^[A-Za-z_][A-Za-z_0-9]*$")) throw new ApiError("invalid_variable_name", "Use ASCII letters, digits and underscore; do not start with a digit.");
            var context = Current().Aircraft.ExpressionContext;
            var userNames = Current().Aircraft.VariableSystem.Variables.Select(v => v.Name);
            if ((context.Properties.ContainsKey(name) && !userNames.Contains(name)) || context.Constants.ContainsKey(name) || context.Functions.ContainsKey(name) || context.SpecialFunctions.ContainsKey(name))
                throw new ApiError("built_in_name_conflict", "Name conflicts with a built-in expression symbol.");
        }
        private static XElement SelectPath(XElement root, string path)
        {
            if (path == "" || path == "Part") return root;
            XElement node = root;
            foreach (string segment in path.Split('/'))
            {
                Match m = Regex.Match(segment, "^([A-Za-z_][A-Za-z_0-9.]*)(?:\\[([0-9]+)\\])?$");
                if (!m.Success) throw new ApiError("invalid_path", "Use StateName/Child[index]; indices are zero-based.");
                var children = node.Elements(m.Groups[1].Value).ToArray(); int index = m.Groups[2].Success ? int.Parse(m.Groups[2].Value, Inv) : 0;
                if (index >= children.Length) throw new ApiError("path_not_found", path);
                node = children[index];
            }
            return node;
        }
        private static readonly string[] CrossSectionElements = { "Slice", "SectionA", "SectionB" };
        private static readonly string[] CrossSectionAttributes = { "size", "cornerRadii", "cornerStretch", "cornerSamples", "edgeCurvature", "edgeSamples", "smoothing", "trapezium", "thickness", "cutting" };
        private static readonly string[] ExtendedStateAttributes = { "offset" };
        private static void ValidateAttribute(PartData p, XElement node, string attribute, JToken value)
        {
            string element = node.Name.LocalName;
            if (InputControllerFields.TryValidate(element, attribute, value)) return;
            var metadata = p.GetOverloadMetadataLookup();
            if (!metadata.TryGetValue(element, out OverloadElementMetadata elementMetadata))
            {
                if (!CrossSectionElements.Contains(element) || (node.Parent?.Name.LocalName != "JFuselage.State" && node.Parent?.Name.LocalName != "Fuselage.State")) throw new ApiError("unsupported_property", "No current native metadata for element " + element);
                if (value == null || value.Type == JTokenType.Null) throw new ApiError("required_attribute", attribute);
                ValidateCrossSectionAttribute(node, attribute, XmlValue(value));
                return;
            }
            var attr = elementMetadata.Attributes.FirstOrDefault(m => m.Name == attribute);
            if (attr == null)
            {
                if (!ValidateExtendedStateAttribute(element, attribute, value)) throw new ApiError("unsupported_property", "No native metadata for attribute " + attribute);
                return;
            }
            if (attr.IsReadOnly) throw new ApiError("read_only", attribute);
            if (value == null || value.Type == JTokenType.Null) { if (!attr.IsOptional) throw new ApiError("required_attribute", attribute); return; }
            string text = XmlValue(value);
            if (attr.DataType == OverloadDataType.Float || attr.DataType == OverloadDataType.Int)
            {
                if (!double.TryParse(text, NumberStyles.Float, Inv, out double number) || double.IsNaN(number) || double.IsInfinity(number)) throw new ApiError("invalid_number", attribute);
                if (attr.DataType == OverloadDataType.Int && number != Math.Truncate(number)) throw new ApiError("invalid_integer", attribute);
                if ((attr.MinValue.HasValue && number < attr.MinValue.Value) || (attr.MaxValue.HasValue && number > attr.MaxValue.Value)) throw new ApiError("out_of_range", attribute);
            }
            if (attr.DataType == OverloadDataType.Bool && text != "true" && text != "false") throw new ApiError("invalid_boolean", attribute);
            if (attr.EnumValues != null && attr.EnumValues.Length > 0 && !attr.EnumValues.Contains(text)) throw new ApiError("invalid_enum", attribute);
            if (attr.DataType.ToString().StartsWith("Vector"))
            {
                int count = int.Parse(attr.DataType.ToString().Substring(6), Inv);
                var numbers = text.Split(',');
                if (numbers.Length != count || numbers.Any(n => !double.TryParse(n, NumberStyles.Float, Inv, out double num) || double.IsNaN(num) || double.IsInfinity(num))) throw new ApiError("invalid_vector", attribute);
            }
        }
        private static void ValidateInputControllerExpression(PartData part, string attribute, string value)
        {
            var script=part.PartScript;
            if(script==null || script.Aircraft==null)throw new ApiError("designer_not_ready","Input expression requires a live part context.");
            try
            {
                if(attribute=="input")
                {
                    // Native resolver recognizes axis IDs and uses the special wing
                    // context for Aileron/WingFlipped expressions. Never invoke the getter.
                    if(script.Aircraft.Controls.GetAxisGetter(value,-1f,script,returnNull:true)==null)
                        throw new ApiError("invalid_expression","InputController input did not compile for part "+part.Id+".");
                }
                else if(!int.TryParse(value,NumberStyles.Integer,Inv,out int group))
                    Parser.Process<bool>(value,script.ExpressionContext);
            }
            catch(ApiError){throw;}
            catch(Exception e){throw new ApiError("invalid_expression","InputController "+attribute+" on part "+part.Id+": "+e.Message);}
        }
        // Fuselage length is the offset vector separating the two cross-sections. The designer writes it through
        // its own length tool, and the state element publishes no native metadata for it.
        private static bool ValidateExtendedStateAttribute(string element, string attribute, JToken value)
        {
            if (attribute != "offset" || (element != "JFuselage.State" && element != "Fuselage.State")) return false;
            if (value == null || value.Type == JTokenType.Null) throw new ApiError("required_attribute", attribute);
            double[] vector = CrossSectionNumbers("offset", XmlValue(value), 3);
            double squared = 0;
            foreach (double axis in vector)
            {
                if (Math.Abs(axis) > 100) throw new ApiError("out_of_range", "offset expects each axis between -100 and 100 metres.");
                squared += axis * axis;
            }
            if (Math.Sqrt(squared) < 0.0001) throw new ApiError("out_of_range", "offset must separate the two cross-sections; a zero vector has no length.");
            return true;
        }
        // Fuselage cross-sections (Slice / SectionA / SectionB) carry no native overload metadata, so their
        // attributes are validated here against the documented XML shape instead of the game UI metadata.
        private static void ValidateCrossSectionAttribute(XElement slice, string attribute, string text)
        {
            switch (attribute)
            {
                case "size": CrossSectionVector(attribute, text, 2, 0.01, 50); return;
                case "cornerSamples": CrossSectionIntegers(attribute, text, 4, 1, 64); return;
                case "edgeSamples": CrossSectionIntegers(attribute, text, 4, 1, 64); return;
                case "edgeCurvature": CrossSectionVector(attribute, text, 4, -10, 10); return;
                case "trapezium": CrossSectionNumber(attribute, text, -10, 10); return;
                case "thickness": CrossSectionNumber(attribute, text, 0.0001, 10); return;
                case "smoothing": CrossSectionBooleans(attribute, text, 1); return;
                case "cornerStretch": CrossSectionBooleans(attribute, text, 4); return;
                case "cutting": CrossSectionCutting(attribute, text); return;
                case "cornerRadii": CrossSectionCornerRadii(slice, text); return;
                default: throw new ApiError("unsupported_property", "Attribute " + attribute + " is not writable on fuselage cross-section " + slice.Name.LocalName + ". Writable: " + string.Join(", ", CrossSectionAttributes) + ".");
            }
        }
        private static double[] CrossSectionNumbers(string attribute, string text, int count)
        {
            var parts = text == null ? new string[0] : text.Split(',');
            if (parts.Length != count) throw new ApiError("invalid_vector", attribute + " requires " + count + " comma-separated numbers.");
            var values = new double[count];
            for (int i = 0; i < count; i++)
            {
                if (!double.TryParse(parts[i].Trim(), NumberStyles.Float, Inv, out values[i]) || double.IsNaN(values[i]) || double.IsInfinity(values[i])) throw new ApiError("invalid_number", attribute + " entry " + i + " is not a number.");
            }
            return values;
        }
        private static void CrossSectionVector(string attribute, string text, int count, double min, double max)
        {
            foreach (double value in CrossSectionNumbers(attribute, text, count))
            {
                if (value < min || value > max) throw new ApiError("out_of_range", attribute + " expects values between " + min.ToString(Inv) + " and " + max.ToString(Inv) + ".");
            }
        }
        private static void CrossSectionIntegers(string attribute, string text, int count, int min, int max)
        {
            foreach (double value in CrossSectionNumbers(attribute, text, count))
            {
                if (value != Math.Truncate(value)) throw new ApiError("invalid_integer", attribute + " expects whole numbers.");
                if (value < min || value > max) throw new ApiError("out_of_range", attribute + " expects integers between " + min + " and " + max + ".");
            }
        }
        private static void CrossSectionNumber(string attribute, string text, double min, double max)
        {
            if (!double.TryParse(text, NumberStyles.Float, Inv, out double value) || double.IsNaN(value) || double.IsInfinity(value)) throw new ApiError("invalid_number", attribute + " is not a number.");
            if (value < min || value > max) throw new ApiError("out_of_range", attribute + " expects a value between " + min.ToString(Inv) + " and " + max.ToString(Inv) + ".");
        }
        private static void CrossSectionBooleans(string attribute, string text, int count)
        {
            var parts = text == null ? new string[0] : text.Split(',');
            if (parts.Length != count) throw new ApiError("invalid_boolean", attribute + " requires " + count + " comma-separated true/false values.");
            foreach (string part in parts)
            {
                string value = part.Trim();
                if (value != "true" && value != "false") throw new ApiError("invalid_boolean", attribute + " accepts only true or false.");
            }
        }
        private static void CrossSectionCutting(string attribute, string text)
        {
            var parts = text == null ? new string[0] : text.Split(',');
            if (parts.Length > 4) throw new ApiError("invalid_vector", attribute + " accepts at most four comma-separated entries.");
            foreach (string part in parts)
            {
                if (part.Trim().Length == 0) continue;
                if (!double.TryParse(part.Trim(), NumberStyles.Float, Inv, out double value) || double.IsNaN(value) || double.IsInfinity(value) || value < 0 || value > 1)
                    throw new ApiError("out_of_range", attribute + " entries must be empty or a number between 0 and 1.");
            }
        }
        private static void CrossSectionCornerRadii(XElement slice, string text)
        {
            double[] radii = CrossSectionNumbers("cornerRadii", text, 4);
            double[] size = { 1, 1 };
            string sizeText = (string)slice.Attribute("size");
            if (!string.IsNullOrWhiteSpace(sizeText))
            {
                var parts = sizeText.Split(',');
                for (int i = 0; i < 2 && i < parts.Length; i++)
                {
                    if (!double.TryParse(parts[i].Trim(), NumberStyles.Float, Inv, out size[i]) || size[i] <= 0) size[i] = 1;
                }
            }
            bool[] stretch = new bool[4];
            string stretchText = (string)slice.Attribute("cornerStretch");
            if (!string.IsNullOrWhiteSpace(stretchText))
            {
                var parts = stretchText.Split(',');
                for (int i = 0; i < 4 && i < parts.Length; i++) stretch[i] = string.Equals(parts[i].Trim(), "true", StringComparison.OrdinalIgnoreCase);
            }
            double absoluteLimit = Math.Max(size[0], size[1]);
            for (int i = 0; i < 4; i++)
            {
                if (radii[i] < 0) throw new ApiError("out_of_range", "cornerRadii entries cannot be negative.");
                double limit = stretch[i] ? 1.0 : absoluteLimit;
                if (radii[i] > limit) throw new ApiError("out_of_range", "cornerRadii entry " + i + " must be <= " + limit.ToString(Inv) + " here (stretched corners use a 0-1 factor, unstretched corners use metres).");
            }
        }
        private List<KeyValuePair<string, DesignerPart>> Templates()
        {
            var list = Designer.Instance?.PartList ?? SP2Game.Instance.CachedDesignerParts;
            if (list == null) throw new ApiError("catalog_not_ready", "Game part library has not initialized.");
            return list.Parts.Where(p => !p.IsLegacy).Select(p => new KeyValuePair<string, DesignerPart>("tpl-" + Json.Hash((p.Mod == null ? "builtin" : p.Mod.ToString()) + "|" + p.Name + "|" + p.AssemblyElement.ToString(SaveOptions.DisableFormatting)).Substring(0, 16), p)).ToList();
        }
        private DesignerPart FindTemplate(string id)
        { var match = Templates().FirstOrDefault(t => t.Key == id); if (match.Value == null) throw new ApiError("template_not_found", "Refresh catalog.list for a current template ID."); return match.Value; }
        private bool Creatable(DesignerPart p)
        {
            var level = SP2Game.Instance.CurrentLevel;
            return level == null || (!level.RestrictedCategories.Contains(p.Category) && !level.RestrictedDesignerParts.Contains(p.Name));
        }
        private object Catalog(string cmd, JObject a)
        {
            var entries = new List<JObject>();
            foreach (var group in Templates().GroupBy(t => t.Value.Category))
            {
                string header = "";
                foreach (var t in group)
                {
                    if (!string.IsNullOrWhiteSpace(t.Value.Header)) header = t.Value.Header;
                    entries.Add(new JObject { ["id"] = t.Key, ["name"] = t.Value.Name, ["description"] = t.Value.Description,
                        ["category"] = group.Key, ["subcategory"] = header, ["creatable"] = Creatable(t.Value),
                        ["source"] = t.Value.Mod == null ? (t.Value.IsSubassembly ? "loaded_subassembly" : "builtin") : "mod",
                        ["partTypes"] = new JArray(t.Value.AssemblyElement.Descendants("Part").Select(p => (string)p.Attribute("partType")).Distinct()) });
                }
            }
            if (cmd == "catalog.categories") return new { gameVersion = SP2Game.Version.ToString(), categories = entries.GroupBy(e => (string)e["category"]).Select(g => new { id = g.Key, name = g.Key, count = g.Count() }).ToArray() };
            if (cmd == "catalog.subcategories") return new { category = Required(a, "category"), subcategories = entries.Where(e => (string)e["category"] == (string)a["category"]).GroupBy(e => (string)e["subcategory"]).Select(g => new { id = g.Key, name = g.Key, count = g.Count() }).ToArray() };
            if (cmd == "catalog.get") return entries.SingleOrDefault(e => (string)e["id"] == Required(a, "id")) ?? throw new ApiError("template_not_found", "Unknown template ID.");
            if (cmd == "catalog.schema")
            {
                var templates = Templates().Where(t => a["id"] != null ? t.Key == (string)a["id"] : t.Value.AssemblyElement.Descendants("Part").Any(p => (string)p.Attribute("partType") == Required(a, "type"))).ToList();
                if (templates.Count == 0) throw new ApiError("template_not_found", "No available template for this ID/type.");
                return new { gameVersion = SP2Game.Version.ToString(), dataSource = "isolated_template_data_and_native_overload_metadata", templates = templates.Select(t => Schema(t.Key, t.Value)).ToArray() };
            }
            if (cmd == "catalog.export") return new { gameVersion = SP2Game.Version.ToString(), generatedAt = DateTime.UtcNow.ToString("o"), entries,
                schemas = Templates().Select(t => { try { return Schema(t.Key, t.Value); } catch (Exception e) { return new JObject { ["id"] = t.Key, ["error"] = Json.Fail(e) }; } }).ToArray() };
            if (cmd != "catalog.list" && cmd != "catalog.search") throw new ApiError("unsupported_command", cmd);
            var filtered = entries.Where(e => a["category"] == null || (string)e["category"] == (string)a["category"])
                .Where(e => a["subcategory"] == null || (string)e["subcategory"] == (string)a["subcategory"])
                .Where(e => a["query"] == null || e.ToString(Formatting.None).IndexOf((string)a["query"], StringComparison.OrdinalIgnoreCase) >= 0);
            return new { gameVersion = SP2Game.Version.ToString(), listing = Page(filtered.Cast<object>(), a) };
        }
        private JObject Schema(string id, DesignerPart template)
        {
            if (schemaCache.TryGetValue(id, out JObject cached)) return cached;
            var parts = new JArray();
            foreach (XElement px in template.AssemblyElement.Descendants("Part"))
            {
                var part = new PartData(new XElement(px), AircraftData.CurrentXmlVersion, CraftLoadContext.Designer);
                var metadata = new JArray(part.GetOverloadMetadataLookup().Select(pair => new JObject { ["element"] = pair.Key,
                    ["attributes"] = JArray.FromObject(pair.Value.Attributes.Select(m => new { name = m.Name, type = m.DataType.ToString(), label = m.Label, description = m.Tooltip,
                        defaultValue = m.DefaultValue, min = m.MinValue, max = m.MaxValue, enumValues = m.EnumValues, optional = m.IsOptional, readOnly = m.IsReadOnly })),
                    ["childElements"] = new JArray(pair.Value.Children.Select(c => c.ElementName)) }));
                parts.Add(new JObject { ["partType"] = part.PartType.PartTypeId, ["templatePartId"] = part.Id, ["defaultState"] = Node(px), ["metadata"] = metadata, ["outputs"] = Outputs(part),
                    ["inputControllers"] = InputControllers(part, "isolated_template_modifier"),
                    ["toolEditableExtensions"] = new JArray(part.Modifiers.OfType<InputControllerData>().Any() ? new[]{InputControllerFields.Description()} : new JObject[0]) });
            }
            var result = new JObject { ["id"] = id, ["name"] = template.Name, ["description"] = template.Description,
                ["parts"] = parts, ["coverage"] = "native_overload_metadata_plus_all_template_attributes",
                ["limitations"] = new JArray("Metadata can omit undocumented optional fields and instance-dependent UI limits; unknown template attributes remain visible in defaultState.") };
            schemaCache[id] = result; return result;
        }
        private static JObject PartSummary(PartData p)
        { return new JObject { ["id"] = p.Id, ["type"] = p.PartType.PartTypeId, ["name"] = p.Name, ["typeName"] = p.PartType.Name }; }
        private static JObject PartInfo(PartData p, bool detailed)
        {
            var t = p.PartScript.transform;
            var result = new JObject { ["id"] = p.Id, ["type"] = p.PartType.PartTypeId, ["name"] = p.Name, ["typeName"] = p.PartType.Name,
                ["position"] = JArray.FromObject(Vec(t.position)), ["rotationEulerDegrees"] = JArray.FromObject(Vec(t.eulerAngles)),
                ["rotationQuaternion"] = new JArray(t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w), ["scale"] = JArray.FromObject(Vec(t.localScale)),
                ["symmetryId"] = p.SymmetryId, ["materialIds"] = JArray.FromObject(p.MaterialIds), ["connectedPartIds"] = new JArray(p.PartConnections.Select(c => c.PartA == p ? c.PartB.Id : c.PartA.Id).Distinct()) };
            if (detailed) { result["state"] = Node(p.GenerateXml()); result["outputs"] = Outputs(p); result["attachPoints"] = Points(p); result["inputControllers"] = InputControllers(p, "live_part_modifier"); }
            return result;
        }
        private static JArray InputControllers(PartData p, string valueSource)
        {
            // Read configuration from native data; serialized XML omits some defaults.
            // Do not evaluate controller scripts or flight telemetry in the designer.
            return new JArray(p.Modifiers.OfType<InputControllerData>().Select((c, index) => new JObject {
                ["index"] = index, ["path"] = "InputController.State[" + index + "]", ["name"] = c.Name,
                ["description"] = c.PropertyEditorDesc, ["input"] = c.Input, ["activationGroup"] = c.ActivationGroup,
                ["invert"] = c.Invert, ["invertType"] = c.InvertType.ToString(), ["min"] = c.MinValue, ["max"] = c.MaxValue,
                ["zeroOnDeactivate"] = c.ZeroOnDeactivate, ["invertOnMirror"] = c.InvertOnMirror,
                ["serializedAttributes"] = new JArray(c.GenerateStateXml().Attributes().Select(a => a.Name.LocalName)),
                ["valueSource"] = valueSource
            }));
        }
        private static JArray Outputs(PartData p)
        {
            return new JArray(p.Modifiers.Where(m => m.VariableOutputDefinitions != null).Select(m => new JObject {
                ["modifier"] = m.StateElementName, ["definitions"] = JArray.FromObject(m.VariableOutputDefinitions.Select(v => new { id = v.Id, name = v.DescriptiveName, defaultVariable = v.DefaultOutputVariable, defaultPriority = v.DefaultOutputPriority })),
                ["bindings"] = JArray.FromObject(m.VariableOutputs.Select(v => new { outputId = v.Definition.Id, variable = v.Variable, priority = v.Priority, activator = v.Activator })) }));
        }
        private static JArray OutputSources(IEnumerable<PartData> parts)
        {
            var sources = new JArray();
            foreach (var p in parts) {
                var modifiers = Outputs(p); if (modifiers.Count == 0) continue;
                var source = PartSummary(p); source["partId"] = p.Id; source.Remove("id"); source["modifiers"] = modifiers; sources.Add(source);
            }
            return sources;
        }
        private static JArray ConnectionFlags(AttachPointConnectionType mask)
        {
            // The native enum is a bitmask but lacks [Flags]; ToString() returns
            // an opaque integer (e.g. 1025) for combined Normal + GearBay.
            return new JArray(Enum.GetValues(typeof(AttachPointConnectionType)).Cast<AttachPointConnectionType>()
                .Where(flag=>(int)flag!=0&&(mask&flag)==flag).Select(flag=>flag.ToString()));
        }
        private static JArray Points(PartData p)
        {
            var rotator = p.GetModifier<JointRotatorData>();
            var piston=p.GetModifier<PistonData>();
            return new JArray(p.AttachPoints.Select(ap => {
                // Powertrain UpdateAttachPointsScript moves the live handle transform without
                // updating AttachPointData.Position. The latter can revert after native undo.
                var live=p.PartScript.AttachPointScripts.FirstOrDefault(s=>s!=null&&s.AttachPoint==ap);
                Vector3 world=live!=null?live.transform.position:p.PartScript.transform.TransformPoint(ap.Position);
                Vector3 local=live!=null?p.PartScript.transform.InverseTransformPoint(world):ap.Position;
                return new JObject { ["id"] = ap.Id, ["localPosition"] = JArray.FromObject(Vec(local)),
                ["worldPosition"] = JArray.FromObject(Vec(world)), ["definitionLocalPosition"]=JArray.FromObject(Vec(ap.Position)),
                ["positionSource"]=live!=null?"live_attach_point_transform":"native_part_definition", ["normal"] = JArray.FromObject(Vec(ap.Normal)),
                ["available"] = ap.IsAvailable, ["allowManualConnection"] = ap.AllowManualConnection, ["allowMultiple"] = ap.AllowMultipleManualConnections,
                ["seekType"] = ap.SeekType.ToString(), ["receiveType"] = ap.ReceiveType.ToString(), ["jointType"] = ap.JointType.ToString(),
                ["seekTypes"]=ConnectionFlags(ap.SeekType),["receiveTypes"]=ConnectionFlags(ap.ReceiveType),["excludeTypes"]=ConnectionFlags(ap.ExcludeType),
                ["seekTypeMask"]=(int)ap.SeekType,["receiveTypeMask"]=(int)ap.ReceiveType,["excludeTypeMask"]=(int)ap.ExcludeType,
                ["role"] = rotator != null ? (rotator.AttachPointIndex >= 0 && rotator.AttachPointIndex < p.AttachPoints.Count && p.AttachPoints[rotator.AttachPointIndex] == ap ? "rotor" : "housing") : piston!=null?(piston.AttachPointIndex>=0&&piston.AttachPointIndex<p.AttachPoints.Count&&p.AttachPoints[piston.AttachPointIndex]==ap?"moving_end":"housing"):(ap.RequiresPhysicsJoint ? "articulated" : "attachment"),
                ["roleSource"] = rotator != null ? "native JointRotatorData.AttachPointIndex (array index, not point ID)" : piston!=null?"native PistonData.AttachPointIndex (array index, not point ID)":"native attach point joint metadata; no housing/rotor claim",
                ["jointAxisLocal"] = new JArray(Vec(ap.JointAxis)), ["jointAxisWorld"] = new JArray(Vec(p.PartScript.transform.TransformDirection(ap.JointAxis))),
                ["requiresPhysicsJoint"] = ap.RequiresPhysicsJoint, ["bodyIslandBoundary"] = ap.BodyIslandBoundary,
                ["mirrorId"] = ap.MirrorId, ["surface"] = ap.IsSurfaceAttachPoint,
                ["connectedPartIds"] = new JArray(ap.PartConnections.Select(c => c.PartA == p ? c.PartB.Id : c.PartA.Id).Distinct()) }; }));
        }
        private object Funky(JObject a, bool describe)
        {
            var ctx = Designer.Instance?.Aircraft?.ExpressionContext ?? new Context();
            var list = new List<object>();
            foreach (var c in ctx.Constants) list.Add(new { name = c.Key, kind = "constant", value = c.Value });
            foreach (var f in ctx.Functions) list.Add(new { name = f.Key, kind = "function", returns = f.Value.Method.ReturnType.Name,
                parameters = f.Value.Method.GetParameters().Select(p => new { name = p.Name, type = p.ParameterType.Name }).ToArray(), description = FunctionDescription(f.Key) });
            foreach (var f in ctx.SpecialFunctions) list.Add(new { name = f.Key, kind = "stateful_function", description = FunctionDescription(f.Key) });
            foreach (var p in ctx.Properties) list.Add(new { name = p.Key, kind = "input_or_variable", returns = p.Value.GetMethod.ReturnType.Name });
            var array = JArray.FromObject(list);
            return new { gameVersion = SP2Game.Version.ToString(), source = "native_expression_context", trigUnit = "degrees", evaluated = false,
                entries = describe ? new JArray(array.Where(v => (string)v["name"] == Required(a, "name"))) : array };
        }
        private static string FunctionDescription(string name)
        {
            switch (name) { case "clamp": return "clamp(value,min,max): restrict value to the inclusive range.";
                case "clamp01": return "Restrict value to [0,1]."; case "smooth": return "Move toward input at maxRate per second; stateful, first call returns input.";
                case "sum": return "Time integral of input; stateful."; case "rate": return "Rate of change of input over time; stateful.";
                case "PID": return "Stateful proportional-integral-derivative controller; consult native implementation for parameters.";
                default: return "Native function; signature is authoritative. Semantic description not yet curated in v0.1."; }
        }
        private PartData Part(int id) { return Current().Aircraft.Aircraft.Assembly.Parts.FirstOrDefault(p => p.Id == id) ?? throw new ApiError("part_not_found", "No current part with ID " + id); }
        private static int Resolve(JToken value, BatchReferences refs) { return refs.Resolve(value); }
        private static object Page(IEnumerable<object> input, JObject a)
        { var list = input.ToList(); int offset = a.Value<int?>("offset") ?? 0; int limit = a.Value<int?>("limit") ?? 100; if (offset < 0 || limit < 1 || limit > 1000) throw new ApiError("invalid_pagination", "offset >= 0; limit 1..1000."); return new { total = list.Count, offset, limit, items = list.Skip(offset).Take(limit).ToArray() }; }
        private static JObject Node(XElement e)
        { if (e == null) return null; return new JObject { ["element"] = e.Name.LocalName, ["attributes"] = new JObject(e.Attributes().Select(a => new JProperty(a.Name.LocalName, a.Value))), ["children"] = new JArray(e.Elements().Select(Node)), ["text"] = e.HasElements ? null : e.Value }; }
        private static float[] Vec(Vector3 v) { return new[] { v.x, v.y, v.z }; }
        private static Vector3 Vector(JToken value, Vector3 fallback)
        { if (value == null) return fallback; var a = value as JArray; if (a == null || a.Count != 3) throw new ApiError("invalid_vector", "Use three numeric values."); var v = a.Values<float>().ToArray(); if (v.Any(x => float.IsNaN(x) || float.IsInfinity(x))) throw new ApiError("invalid_vector", "Finite values only."); return new Vector3(v[0], v[1], v[2]); }
        private static string XmlValue(JToken value)
        { if (value == null || value.Type == JTokenType.Null) return null; if (value is JArray array) return string.Join(",", array.Select(XmlValue)); if (value.Type == JTokenType.Boolean) return value.Value<bool>() ? "true" : "false"; return value.Type == JTokenType.String ? (string)value : value.ToString(Formatting.None); }
        private static string Required(JObject a, string key) { string value = (string)a[key]; if (string.IsNullOrWhiteSpace(value)) throw new ApiError("invalid_input", key + " is required."); return value; }
        private static int Int(JObject a, string key) { if (a[key] == null) throw new ApiError("invalid_input", key + " is required."); return a.Value<int>(key); }
    }
}
