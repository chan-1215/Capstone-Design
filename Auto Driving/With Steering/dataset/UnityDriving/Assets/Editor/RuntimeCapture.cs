using System;
using System.IO;
using UnityEditor;
using UnityEngine;

// Batch command: -executeMethod RuntimeCapture.Run -simSmoke -policyTest
// -policyLane 0 -simSeconds 150. The existing learned policy runs unchanged.
[InitializeOnLoad]
public static class RuntimeCapture
{
    static readonly float[] Times={6,16,26,36};
    static int index;
    static RuntimeCapture()
    {
        // Entering Play reloads assemblies, so restore the callback afterward.
        if(Array.IndexOf(Environment.GetCommandLineArgs(),"RuntimeCapture.Run")>=0)
            EditorApplication.update+=Tick;
    }
    public static void Run()
    {
        index=0;DrivingLabBuilder.Smoke();
    }
    static void Tick()
    {
        if(!EditorApplication.isPlaying||index>=Times.Length||Time.time<Times[index])return;
        var lab=UnityEngine.Object.FindObjectOfType<DrivingLab>();if(lab==null)return;
        lab.CapturePreview();
        string root=Path.GetFullPath("Diagnostics");
        string output=Path.Combine(root,"runtime_20261111","frame_"+(index+1).ToString("D2"));Directory.CreateDirectory(output);
        foreach(string name in new[]{"unity_overview.png","unity_robot.png","unity_camera.png","unity_policy_input.png","opencv_tracking.png","opencv_tracking.json","robot_layout.json"})
            if(File.Exists(Path.Combine(root,name)))File.Copy(Path.Combine(root,name),Path.Combine(output,name),true);
        var robot=lab.transform.Find("Generated/Blue_ServoSteering_Robot");
        var stamp=new CaptureStamp{simulation_seconds=Time.time,position=robot!=null?robot.position:Vector3.zero,
            yaw_deg=robot!=null?robot.eulerAngles.y:0,source="Unity Camera.Render during learned_camera_mlp runtime",note="OpenCV overlay updates asynchronously; it is not the steering controller."};
        File.WriteAllText(Path.Combine(output,"capture.json"),JsonUtility.ToJson(stamp,true));
        Debug.Log("Runtime capture saved at "+Time.time+"s: "+output);index++;
        if(index>=Times.Length)EditorApplication.update-=Tick;
    }
    [Serializable] class CaptureStamp
    {
        public float simulation_seconds,yaw_deg;
        public Vector3 position;
        public string source,note;
    }
}
