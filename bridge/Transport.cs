using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using BepInEx;
using HarmonyLib;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant
{
    [BepInPlugin("local.sp2.buildassistant", "SP2 Build Assistant", "0.5.0")]
    public sealed class Plugin : BaseUnityPlugin
    {
        private Server server;
        private Harmony harmony;
        private void Awake()
        {
            var runtime = gameObject.AddComponent<BuildRuntime>();
            runtime.Log = Logger;
            harmony = new Harmony("local.sp2.buildassistant");
            harmony.PatchAll(typeof(Plugin).Assembly);
            NativeMeshLifetime.Install(harmony,Logger);
            DesignerExpressionLifetime.Install(harmony,Logger);
            server = new Server(runtime);
            server.Start();
            Logger.LogInfo("SP2 Build Assistant 0.5.0 ready: " + server.Url);
        }
        private void OnDestroy() { if (server != null) server.Dispose(); if (harmony != null) harmony.UnpatchSelf(); }
    }

    internal sealed class ApiError : Exception
    {
        public string Code;
        public JObject Details;
        public ApiError(string code, string message, JObject details = null) : base(message) { Code = code; Details = details; }
    }
    internal static class Json
    {
        public static JObject Ok(object data) { return new JObject { ["success"] = true, ["schemaVersion"] = "1", ["data"] = data == null ? null : JToken.FromObject(data) }; }
        public static JObject Fail(Exception e)
        {
            while (e is System.Reflection.TargetInvocationException && e.InnerException != null) e = e.InnerException;
            var result = new JObject { ["success"] = false, ["schemaVersion"] = "1", ["error"] = new JObject { ["code"] = (e as ApiError)?.Code ?? "execution_failed", ["message"] = e.Message } };
            if ((e as ApiError)?.Details != null) result["error"]["details"] = ((ApiError)e).Details.DeepClone();
            return result;
        }
        public static string Hash(string value)
        {
            using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(value))).Replace("-", "").ToLowerInvariant();
        }
    }
    internal sealed class Server : IDisposable
    {
        private readonly BuildRuntime runtime;
        private readonly HttpListener listener = new HttpListener();
        private readonly object gate = new object();
        private readonly Dictionary<string, Job> jobs = new Dictionary<string, Job>();
        private readonly Dictionary<string, string> keys = new Dictionary<string, string>();
        private readonly OperationResults results = new OperationResults();
        private readonly string token = Guid.NewGuid().ToString("N") + Guid.NewGuid().ToString("N");
        private string discovery;
        private bool stopped;
        public string Url { get; private set; }
        public Server(BuildRuntime runtime) { this.runtime = runtime; runtime.OperationResults = results; }
        public void Start()
        {
            for (int port = 24730; port < 24750; port++)
            {
                try { Url = "http://127.0.0.1:" + port + "/"; listener.Prefixes.Clear(); listener.Prefixes.Add(Url); listener.Start(); break; }
                catch (HttpListenerException) { if (port == 24749) throw; }
                catch (System.Net.Sockets.SocketException) { if (port == 24749) throw; }
            }
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SP2BuildAssistant", "instances");
            Directory.CreateDirectory(dir);
            int pid = Process.GetCurrentProcess().Id;
            discovery = Path.Combine(dir, pid + ".json");
            File.WriteAllText(discovery, new JObject { ["baseUrl"] = Url, ["token"] = token, ["pid"] = pid,
                ["instanceId"] = Guid.NewGuid().ToString("N"), ["pluginVersion"] = "0.5.0", ["protocolVersion"] = "1" }.ToString(), new UTF8Encoding(false));
            new Thread(Listen) { IsBackground = true, Name = "SP2BuildAssistant HTTP" }.Start();
        }
        private void Listen()
        {
            while (!stopped)
            {
                try { var context = listener.GetContext(); ThreadPool.QueueUserWorkItem(_ => Handle(context)); }
                catch (Exception) { if (!stopped) Thread.Sleep(100); }
            }
        }
        private void Handle(HttpListenerContext ctx)
        {
            JObject response;
            try
            {
                if (!IPAddress.IsLoopback(ctx.Request.RemoteEndPoint.Address)) throw new ApiError("forbidden", "Local connections only.");
                if (ctx.Request.Headers["X-SP2Build-Token"] != token) throw new ApiError("unauthorized", "Invalid instance token.");
                string route = ctx.Request.Url.AbsolutePath;
                if (route.StartsWith("/v1/visual/") && ctx.Request.HttpMethod == "GET")
                {
                    var segments=route.Substring("/v1/visual/".Length).Split('/');
                    if(segments.Length!=2)throw new ApiError("route_not_found","Expected capture ID and artifact name.");
                    byte[] artifact=runtime.VisualArtifact(segments[0],segments[1]);
                    ctx.Response.ContentType=segments[1].EndsWith(".png")?"image/png":"application/json; charset=utf-8";
                    ctx.Response.StatusCode=200;ctx.Response.ContentLength64=artifact.Length;
                    ctx.Response.OutputStream.Write(artifact,0,artifact.Length);ctx.Response.Close();return;
                }
                if (route == "/v1/operations" && ctx.Request.HttpMethod == "POST")
                {
                    if (ctx.Request.ContentLength64 > 4 * 1024 * 1024) throw new ApiError("input_too_large", "Request limit is 4 MiB.");
                    string body;
                    using (var reader = new StreamReader(ctx.Request.InputStream, Encoding.UTF8)) body = reader.ReadToEnd();
                    if (body.Length > 4 * 1024 * 1024) throw new ApiError("input_too_large", "Request limit is 4 MiB.");
                    JObject input = JObject.Parse(body);
                    string key = (string)input["requestId"];
                    string signature = Json.Hash(input.ToString(Formatting.None));
                    Job job;
                    lock (gate)
                    {
                        if (!string.IsNullOrEmpty(key) && keys.TryGetValue(key, out string old))
                        {
                            job = jobs[old];
                            if (job.Signature != signature) throw new ApiError("request_id_conflict", "The requestId was used with different content.");
                        }
                        else
                        {
                            // Never evict idempotence records while this game instance is alive.
                            if (jobs.Count >= 20000) throw new ApiError("operation_capacity", "Instance task capacity reached; no request was executed.");
                            job = new Job { Id = Guid.NewGuid().ToString("N"), Key = key, Signature = signature, Input = input, Results = results };
                            jobs.Add(job.Id, job);
                            if (!string.IsNullOrEmpty(key)) keys.Add(key, job.Id);
                            runtime.Queue.Enqueue(job);
                        }
                    }
                    response = Json.Ok(job.View());
                }
                else if (route.StartsWith("/v1/operations/"))
                {
                    string id = route.Substring("/v1/operations/".Length);
                    Job job;
                    lock (gate) { if (!jobs.TryGetValue(id, out job)) throw new ApiError("operation_not_found", "Task unavailable in this game instance; do not assume it did not execute."); }
                    if (ctx.Request.HttpMethod == "DELETE") lock (job.Sync) job.CancelRequested = true;
                    else if (ctx.Request.HttpMethod != "GET") throw new ApiError("method_not_allowed", "Use GET or DELETE.");
                    response = Json.Ok(job.View());
                }
                else throw new ApiError("route_not_found", "Unknown route.");
            }
            catch (Exception e) { response = Json.Fail(e); }
            try
            {
                byte[] bytes = Encoding.UTF8.GetBytes(response.ToString(Formatting.None));
                ctx.Response.ContentType = "application/json; charset=utf-8";
                ctx.Response.StatusCode = response.Value<bool>("success") ? 200 : 400;
                ctx.Response.ContentLength64 = bytes.Length;
                ctx.Response.OutputStream.Write(bytes, 0, bytes.Length);
                ctx.Response.Close();
            }
            catch (Exception) { }
        }
        public void Dispose()
        {
            stopped = true; listener.Close();
            try { if (discovery != null) File.Delete(discovery); } catch (IOException) { }
        }
    }
}
