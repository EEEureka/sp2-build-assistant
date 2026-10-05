#if ACCEPTANCE_HOOKS
using System;
using System.IO;
using Assets.Scripts.Design;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SP2BuildAssistant
{
    // Test setup only: create an actual camera baseline that the stock desktop
    // designer UI cannot directly configure (FOV and optical-axis roll). The
    // ordinary public capture then has to restore THAT baseline over two frames.
    // Never compiled into distribution builds, and never edits craft content.
    internal sealed class AcceptanceCameraFixture : IDisposable
    {
        private readonly Camera camera, backup;
        private readonly GameObject backupObject;
        private readonly Vector3 localPosition;
        private readonly Quaternion localRotation;
        private readonly bool enabled;

        internal static AcceptanceCameraFixture Enter(Designer designer)
        {
            string path=Path.Combine(BepInEx.Paths.ConfigPath,"sp2build.acceptance-camera.json");
            if(!File.Exists(path))return null;
            if(!designer.Aircraft.Aircraft.Name.StartsWith("SP2Build 050 Precision Lab",StringComparison.Ordinal))
                throw new ApiError("test_fixture_required","Camera test setup requires a named precision lab copy.");
            var input=JObject.Parse(File.ReadAllText(path));
            VisualScope.Keys(input,"fieldOfViewDegrees","rollDegrees");
            float fov=(float)PropertyValues.Number(input["fieldOfViewDegrees"],5,170,"test fieldOfViewDegrees");
            float roll=(float)PropertyValues.Number(input["rollDegrees"],-180,180,"test rollDegrees");
            var camera=designer.CameraController.Camera;
            if(camera==null||!camera.isActiveAndEnabled)throw new ApiError("camera_unavailable","No active test camera.");
            File.Delete(path); // one public capture consumes one explicit fixture
            return new AcceptanceCameraFixture(camera,fov,roll);
        }

        private AcceptanceCameraFixture(Camera value,float fov,float roll)
        {
            camera=value;localPosition=camera.transform.localPosition;localRotation=camera.transform.localRotation;
            enabled=camera.enabled;
            backupObject=new GameObject("SP2BuildAcceptanceCameraBaseline"){hideFlags=HideFlags.HideAndDontSave};
            backup=backupObject.AddComponent<Camera>();backup.enabled=false;backup.CopyFrom(camera);backup.enabled=false;
            try {
                camera.fieldOfView=fov;
                camera.transform.rotation=camera.transform.rotation*Quaternion.AngleAxis(roll,Vector3.forward);
                camera.ResetProjectionMatrix();camera.ResetWorldToCameraMatrix();
            } catch { Dispose();throw; }
        }

        public void Dispose()
        {
            try {
                camera.CopyFrom(backup);camera.enabled=enabled;
                camera.transform.localPosition=localPosition;camera.transform.localRotation=localRotation;
            } finally {UnityEngine.Object.Destroy(backupObject);}
        }
    }
}
#endif
