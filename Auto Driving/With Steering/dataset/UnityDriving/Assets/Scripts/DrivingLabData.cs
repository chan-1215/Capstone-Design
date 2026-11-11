using System;
using System.IO;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

public partial class DrivingLab
{
    // Reuse recorded positions and labels, rendering observations at today's
    // camera mount. Recovery perturbations receive new teacher labels.
    public void RenderAlignedDataset(string sourceRoot,string outputRoot)
    {
        Directory.CreateDirectory(Path.Combine(outputRoot,"images"));
        var rt=new RenderTexture(320,240,24);rt.Create();var image=new Texture2D(320,240,TextureFormat.RGB24,false);
        var old=RenderTexture.active;var oldTarget=car.camera.targetTexture;
        int count=0,sources=0;
        using(var csv=new StreamWriter(Path.Combine(outputRoot,"labels.csv")))
        {
            csv.WriteLine("image,run,episode,seed,lane,variant,source_image,label_wheel_deg,label_speed_m_s");
            try
            {
                car.camera.targetTexture=rt;
                foreach(string path in Directory.GetFiles(sourceRoot,"labels.csv",SearchOption.AllDirectories))
                {
                    string[] lines=File.ReadAllLines(path);string[] header=lines[0].TrimStart('\ufeff').Split(',');
                    var index=new Dictionary<string,int>();for(int i=0;i<header.Length;i++)index[header[i]]=i;
                    string run=new DirectoryInfo(Path.GetDirectoryName(path)).Name;
                    for(int row=1;row<lines.Length;row++)
                    {
                        if(string.IsNullOrWhiteSpace(lines[row]))continue;
                        string[] v=lines[row].Split(',');if(v[index["valid"]]!="1")continue;
                        Vector3 p=new Vector3(Parse(v[index["x_m"]]),0,Parse(v[index["z_m"]]));
                        float yaw=Parse(v[index["yaw_deg"]]),speed=Parse(v[index["speed_m_s"]]),wheel=Parse(v[index["applied_wheel_deg"]]);
                        lane=int.Parse(v[index["lane"]]);sources++;
                        float[] offsets={0,-.025f,.025f,0,0};float[] turns={0,0,0,-6,6};
                        for(int j=0;j<offsets.Length;j++)
                        {
                            Quaternion q=Quaternion.Euler(0,yaw,0);Vector3 pos=p+q*Vector3.right*offsets[j];
                            car.SetRecordedPose(pos,yaw+turns[j],speed,wheel);car.SetCameraPose(config.cameraHeight,config.cameraPitch);
                            Observe();if(margin<0)continue;
                            float label=j==0?Parse(v[index["target_wheel_deg"]]):target;
                            sun.intensity=j==1?.85f:j==2?1.25f:1.1f;
                            car.camera.Render();RenderTexture.active=rt;
                            image.ReadPixels(new Rect(0,0,320,240),0,0,false);image.Apply(false);
                            string filename="images/"+count.ToString("D6")+".png";
                            File.WriteAllBytes(Path.Combine(outputRoot,filename),image.EncodeToPNG());
                            csv.WriteLine(string.Join(",",new[]{filename,run,v[index["episode"]],v[index["seed"]],v[index["lane"]],j.ToString(),v[index["image"]],F(label),F(config.expertSpeed/(1+Mathf.Abs(label)/70))}));
                            count++;
                        }
                    }
                }
            }
            finally
            {
                car.camera.targetTexture=oldTarget;RenderTexture.active=old;rt.Release();
                if(Application.isPlaying){Destroy(rt);Destroy(image);}else{DestroyImmediate(rt);DestroyImmediate(image);}
            }
        }
        File.WriteAllText(Path.Combine(outputRoot,"metadata.json"),"{\"source_frames\":"+sources+",\"aligned_images\":"+count+",\"camera_height_m\":"+F(config.cameraHeight)+",\"camera_z_m\":"+F(config.cameraForward)+",\"width\":320,\"height\":240,\"label_rule\":\"original_teacher_for_base_pose_recomputed_teacher_for_recovery_perturbations\"}");
        File.WriteAllText(Path.Combine(outputRoot,"render_config.json"),JsonUtility.ToJson(config,true));
        lane=0;NewEpisode(false);Debug.Log("Aligned dataset complete: "+count+" images from "+sources+" source frames.");
    }
    static float Parse(string value){return float.Parse(value,CultureInfo.InvariantCulture);}
    static string F(float value){return value.ToString("F6",CultureInfo.InvariantCulture);}
}
