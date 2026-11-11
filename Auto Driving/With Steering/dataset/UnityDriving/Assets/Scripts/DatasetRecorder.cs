using System;
using System.IO;
using System.Text;
using UnityEngine;

public class DatasetRecorder : IDisposable
{
    [Serializable] class EpisodeInfo
    {
        public int episode,seed,lane;
        public float start_sim_time_s,camera_height_m,camera_pitch_deg,light_intensity;
        public Vector3 start_position_m;
        public float start_yaw_deg;
    }
    public string directory;
    public int count;
    StreamWriter csv;
    Texture2D rgb;
    public RenderTexture target;
    public DatasetRecorder(DrivingConfig c,string metadata)
    {
        directory=Path.GetFullPath(Path.Combine(Application.dataPath,"../Dataset",DateTime.UtcNow.ToString("yyyyMMdd_HHmmss_fff")));
        Directory.CreateDirectory(Path.Combine(directory,"images"));
        File.WriteAllText(Path.Combine(directory,"config.json"),JsonUtility.ToJson(c,true),Encoding.UTF8);
        File.WriteAllText(Path.Combine(directory,"metadata.json"),metadata,Encoding.UTF8);
        csv=new StreamWriter(Path.Combine(directory,"labels.csv"),false,new UTF8Encoding(false));
        csv.WriteLine("image,episode,seed,lane,sim_time_s,x_m,z_m,yaw_deg,speed_m_s,applied_wheel_deg,applied_servo_estimate,target_wheel_deg,target_servo_estimate,command_wheel_deg,throttle_normalized,left_rear_speed_m_s,right_rear_speed_m_s,cte_m,heading_error_deg,road_margin_m,valid,mode");
        target=new RenderTexture(c.imageWidth,c.imageHeight,24);target.Create();
        rgb=new Texture2D(c.imageWidth,c.imageHeight,TextureFormat.RGB24,false);
    }
    public void Save(Camera cam,int episode,int seed,int lane,float time,RobotVehicle car,float expertWheel,float cte,float heading,float margin,bool valid,string mode)
    {
        // UI and overhead view never enter the training image.
        var previous=RenderTexture.active;var previousTarget=cam.targetTexture;
        try
        {
            cam.targetTexture=target;cam.Render();RenderTexture.active=target;
            rgb.ReadPixels(new Rect(0,0,target.width,target.height),0,0,false);rgb.Apply(false);
            string file="images/"+count.ToString("D7")+".png";
            File.WriteAllBytes(Path.Combine(directory,file),rgb.EncodeToPNG());
            Vector3 p=car.root.position;
            string[] row={file,episode.ToString(),seed.ToString(),lane.ToString(),F(time),F(p.x),F(p.z),F(car.root.eulerAngles.y),F(car.speed),F(car.wheelAngle),F(car.ServoFor(car.wheelAngle)),F(expertWheel),F(car.ServoFor(expertWheel)),F(car.targetAngle),F(car.throttle),F(car.leftRearSpeed),F(car.rightRearSpeed),F(cte),F(heading),F(margin),valid?"1":"0",mode};
            csv.WriteLine(string.Join(",",row));csv.Flush();count++;
        }
        finally { cam.targetTexture=previousTarget;RenderTexture.active=previous; }
    }
    public void Episode(int id,int seed,int lane,float time,RobotVehicle car,float intensity)
    {
        var e=new EpisodeInfo{episode=id,seed=seed,lane=lane,start_sim_time_s=time,
            start_position_m=car.root.position,start_yaw_deg=car.root.eulerAngles.y,
            camera_height_m=car.camera.transform.localPosition.y,
            camera_pitch_deg=car.camera.transform.localEulerAngles.x,light_intensity=intensity};
        File.AppendAllText(Path.Combine(directory,"episodes.jsonl"),JsonUtility.ToJson(e)+"\n",Encoding.UTF8);
    }
    static string F(float f){return f.ToString("F6",System.Globalization.CultureInfo.InvariantCulture);}
    public void Dispose()
    {
        if(csv!=null){csv.Dispose();csv=null;}
        if(target!=null){target.Release();UnityEngine.Object.Destroy(target);target=null;}
        if(rgb!=null){UnityEngine.Object.Destroy(rgb);rgb=null;}
    }
}
