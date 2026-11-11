using System;
using UnityEngine;

// Learned RGB -> steering/speed policy. No world position or track coordinates.
public sealed class VisionPolicy : IDisposable
{
    [Serializable] public class Model
    {
        public int columns,rows,hidden1,hidden2;
        public int cameraMountRevision;
        public float cameraHeight,cameraZ,cameraPitch,verticalFov;
        public float cropTop,cropBottom;
        public int[] yEdges;
        public float[] mean,std,w1,b1,w2,b2,w3,b3;
    }
    readonly Model m;
    readonly RenderTexture rt;
    readonly Texture2D image;
    public float Steering,Speed;
    public Texture2D InputImage {get{return image;}}
    public VisionPolicy(TextAsset asset,DrivingConfig config)
    {
        m=JsonUtility.FromJson<Model>(asset.text);
        if(m.cameraMountRevision!=3||Mathf.Abs(config.cameraHeight-m.cameraHeight)>.001f||Mathf.Abs(config.cameraForward-m.cameraZ)>.001f||Mathf.Abs(config.cameraPitch-m.cameraPitch)>.1f||Mathf.Abs(config.cameraVerticalFov-m.verticalFov)>.1f)
            throw new ArgumentException("카메라 위치·지지대에 맞춘 모델 재학습이 필요합니다.");
        if(m.mean.Length!=m.columns*m.rows*3)throw new ArgumentException("Invalid policy feature size");
        rt=new RenderTexture(320,240,24);rt.Create();image=new Texture2D(320,240,TextureFormat.RGB24,false);
    }
    public void Predict(Camera camera)
    {
        var previous=RenderTexture.active;var oldTarget=camera.targetTexture;
        try
        {
            camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;
            image.ReadPixels(new Rect(0,0,320,240),0,0,false);image.Apply(false);
            float[] x=Features(image.GetPixels32(),320,240,m.columns,m.rows,m.cropTop,m.cropBottom,m.yEdges);
            for(int i=0;i<x.Length;i++)x[i]=(x[i]-m.mean[i])/m.std[i];
            float[] a=Dense(x,m.w1,m.b1,true),b=Dense(a,m.w2,m.b2,true),y=Dense(b,m.w3,m.b3,false);
            Steering=Mathf.Clamp(y[0]*35,-35,35);Speed=Mathf.Clamp(y[1]*.28f,.08f,.4f);
        }
        finally {camera.targetTexture=oldTarget;RenderTexture.active=previous;}
    }
    static float[] Dense(float[] input,float[] weights,float[] bias,bool relu)
    {
        float[] result=(float[])bias.Clone();
        for(int i=0;i<input.Length;i++)for(int j=0;j<result.Length;j++)result[j]+=input[i]*weights[i*result.Length+j];
        if(relu)for(int j=0;j<result.Length;j++)result[j]=Mathf.Max(0,result[j]);return result;
    }
    static readonly int[] DefaultYEdges={9,26,44,61,79,96,113,131,148};
    public static float[] Features(Color32[] pixels,int width,int height,int columns=12,int rows=8,float top=.04f,float bottom=.62f,int[] yEdges=null)
    {
        float[] f=new float[columns*rows*3];int at=0;
        if(yEdges==null&&height==240&&rows==8)yEdges=DefaultYEdges;
        for(int row=0;row<rows;row++)for(int col=0;col<columns;col++)
        {
            int x0=col*width/columns,x1=(col+1)*width/columns;
            int y0=yEdges!=null?yEdges[row]:Mathf.FloorToInt((top+(bottom-top)*row/rows)*height);
            int y1=yEdges!=null?yEdges[row+1]:Mathf.FloorToInt((top+(bottom-top)*(row+1)/rows)*height);
            int count=0,dark=0,white=0,yellow=0;
            for(int y=y0;y<y1;y+=2)for(int x=x0;x<x1;x+=2)
            {
                Color32 p=pixels[(height-1-y)*width+x];int max=Mathf.Max(p.r,Mathf.Max(p.g,p.b)),min=Mathf.Min(p.r,Mathf.Min(p.g,p.b));
                if(max<115&&max-min<60)dark++;
                if(min>150&&max-min<60)white++;
                if(p.r>100&&p.g>90&&p.b<110&&p.r>p.b*1.35f&&p.g>p.b*1.25f)yellow++;
                count++;
            }
            f[at++]=dark/(float)count;f[at++]=white/(float)count;f[at++]=yellow/(float)count;
        }
        return f;
    }
    public void Dispose(){rt.Release();if(Application.isPlaying){UnityEngine.Object.Destroy(rt);UnityEngine.Object.Destroy(image);}else{UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(image);}}
}
