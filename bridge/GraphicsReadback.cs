using System;
using UnityEngine;

namespace SP2BuildAssistant
{
    // Unity can log device-removal errors without throwing from Camera.Render
    // or ReadPixels. Verify the actual GPU -> CPU path, not image variance:
    // a legitimate view may contain only sky or a uniformly painted surface.
    internal static class GraphicsReadback
    {
        internal static void Verify()
        {
            var previous=RenderTexture.active;
            RenderTexture target=null;Texture2D pixels=null;
            try{
                target=RenderTexture.GetTemporary(2,2,0,RenderTextureFormat.ARGB32,RenderTextureReadWrite.Linear,1);
                // A pooled RenderTexture can have a lazily created hardware
                // resource. Ask Unity to create it before judging the device.
                if(!target.IsCreated()&&!target.Create())throw new InvalidOperationException("Probe render target could not be created.");
                pixels=new Texture2D(2,2,TextureFormat.RGB24,false,true);
                foreach(var expected in new[]{new Color32(255,0,0,255),new Color32(0,0,255,255)}){
                    RenderTexture.active=target;GL.Clear(false,true,expected);
                    pixels.ReadPixels(new Rect(0,0,2,2),0,0);pixels.Apply(false,false);
                    foreach(var actual in pixels.GetPixels32())
                        if(Math.Abs(actual.r-expected.r)>1||Math.Abs(actual.g-expected.g)>1||Math.Abs(actual.b-expected.b)>1)
                            throw new InvalidOperationException("GPU readback did not match two successive known colors.");
                }
            }catch(Exception ex){
                throw new ApiError("graphics_readback_failed","Native screenshot cannot be trusted: "+ex.Message+" Inspect the game graphics log; restart the game if its graphics device has failed.");
            }finally{
                RenderTexture.active=previous;
                if(pixels!=null)UnityEngine.Object.Destroy(pixels);
                if(target!=null)RenderTexture.ReleaseTemporary(target);
            }
        }
    }
}
