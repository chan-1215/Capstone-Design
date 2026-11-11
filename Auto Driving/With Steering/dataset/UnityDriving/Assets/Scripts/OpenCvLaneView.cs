using System;
using System.IO;
using System.Diagnostics;
using System.Threading.Tasks;
using UnityEngine;

// Asynchronous diagnostics only. The learned controller consumes unpainted RGB.
public sealed class OpenCvLaneView : IDisposable
{
    [Serializable] public class Result
    {
        public bool ready,valid;
        public int dashes,boundaries,pathPoints;
        public string jpeg,error,opencv;
    }
    Process process;
    Task<string> pending;
    float sentAt;
    bool ready;
    public Texture2D Overlay {get;private set;}
    public Result Latest {get;private set;}
    public string Status {get;private set;}="OpenCV 시작 중";
    public OpenCvLaneView(string python)
    {
        string script=Path.GetFullPath(Path.Combine(Application.dataPath,"../Tools/opencv_lane_view.py"));
        process=new Process{StartInfo=new ProcessStartInfo(python,"-u \""+script+"\""){
            UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,
            RedirectStandardOutput=true,RedirectStandardError=true}};
        try
        {
            process.ErrorDataReceived+=(s,e)=>{if(!string.IsNullOrEmpty(e.Data))Status=e.Data;};
            process.Start();process.BeginErrorReadLine();
            pending=process.StandardOutput.ReadLineAsync();sentAt=Time.realtimeSinceStartup;
            Overlay=new Texture2D(2,2,TextureFormat.RGB24,false);
        }
        catch(Exception e){Status="OpenCV 실행 실패: "+e.Message;Dispose();}
    }
    public void Poll()
    {
        if(pending==null)return;
        if(!pending.IsCompleted)
        {
            if(Time.realtimeSinceStartup-sentAt>10){Status="OpenCV 응답 시간 초과";Dispose();}
            return;
        }
        try
        {
            string line=pending.GetAwaiter().GetResult();pending=null;
            if(line==null)throw new IOException("OpenCV 프로세스 종료");
            var result=JsonUtility.FromJson<Result>(line);
            if(result.ready){ready=true;Status="OpenCV "+result.opencv+" 연결됨";return;}
            if(!string.IsNullOrEmpty(result.error))throw new IOException(result.error);
            Overlay.LoadImage(Convert.FromBase64String(result.jpeg));Latest=result;
            Status=result.valid?"점선 추적 경로 검출":"점선 추적 경로 미확인";
        }
        catch(Exception e){Status="OpenCV 오류: "+e.Message;Dispose();}
    }
    public void Submit(Texture2D image)
    {
        Poll();if(!ready||pending!=null||process==null||image==null)return;
        try
        {
            process.StandardInput.WriteLine(Convert.ToBase64String(image.EncodeToPNG()));
            pending=process.StandardOutput.ReadLineAsync();sentAt=Time.realtimeSinceStartup;
        }
        catch(Exception e){Status=e.Message;Dispose();}
    }
    public void Dispose()
    {
        ready=false;pending=null;
        if(process!=null){try{if(!process.HasExited)process.Kill();}catch{}process.Dispose();process=null;}
        if(Overlay!=null){UnityEngine.Object.Destroy(Overlay);Overlay=null;}
    }
}
