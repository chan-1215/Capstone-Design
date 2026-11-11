using System;
using System.IO;
using UnityEngine;

public partial class DrivingLab
{
    VisionPolicy policy;
    bool learned,policyTest;
    float policyAngle,policySpeed,nextInference,policyStart,maxPolicyCte,minPolicyMargin=float.MaxValue;
    int inferenceCount;
    [Serializable] class PolicyReport
    {
        public string status,controller="learned_camera_mlp";
        public int lane,completed_laps,predictions,ground_truth_action_fallbacks=0;
        public float seconds,max_cte_m,minimum_road_margin_m;
    }
    bool SetupPolicyMode()
    {
        var args=Environment.GetCommandLineArgs();policyTest=Array.IndexOf(args,"-policyTest")>=0;
        if(!policyTest&&(smoke||!config.autoStartLearned))return false;
        if(policyTest)
        {
            int i=Array.IndexOf(args,"-policyLane");if(i>=0&&i+1<args.Length)lane=int.Parse(args[i+1]);
            NewEpisode(false);Time.timeScale=2;
        }
        StartLearned();
        if(policyTest&&policy==null)EndPolicyTest("model_missing");
        return true;
    }
    void StartLearned()
    {
        var asset=Resources.Load<TextAsset>("VisionPolicy");
        if(asset==null){Stop();notice="학습 모델이 없습니다. VisionPolicy.json을 먼저 생성하세요.";return;}
        if(policy!=null){policy.Dispose();policy=null;}
        try{policy=new VisionPolicy(asset,config);}
        catch(Exception e){Stop();notice=e.Message;Debug.LogWarning(e.Message);return;}
        expert=false;learned=true;driving=true;nextInference=0;policyAngle=0;policySpeed=0;policyStart=Time.time;
        notice="학습 모델 주행: 카메라 영상으로 조향·속도를 결정합니다. SPACE 정지, H 상태창";
    }
    void StepLearned()
    {
        if(Time.time>=nextInference)
        {
            try
            {
                policy.Predict(car.camera);inferenceCount++;
                policyAngle=policy.Steering;policySpeed=policy.Speed*config.learnedSpeedScale;
                if(float.IsNaN(policyAngle)||float.IsNaN(policySpeed))throw new Exception("Non-finite policy output");
                nextInference=Time.time+1f/Mathf.Max(1,config.modelUpdatesHz);
            }
            catch(Exception e){Stop();notice=e.Message;if(policyTest)EndPolicyTest("inference_error");return;}
        }
        car.Step(policyAngle,policySpeed,Time.fixedDeltaTime);
    }
    void CheckPolicy()
    {
        if(!learned)return;
        maxPolicyCte=Mathf.Max(maxPolicyCte,Mathf.Abs(cte));minPolicyMargin=Mathf.Min(minPolicyMargin,margin);
        if(progress>track.length){completedLaps++;progress-=track.length;}
        if(margin<-.005f)
        {
            if(policyTest)EndPolicyTest("boundary_stop");else{Stop();notice="모델이 노면 경계에 도달해 정지했습니다.";}
        }
        if(policyTest&&(completedLaps>=2||Time.time-policyStart>=smokeSeconds))EndPolicyTest(completedLaps>=2?"completed":"time_limit");
    }
    void EndPolicyTest(string status)
    {
        string dir=Path.GetFullPath(Path.Combine(Application.dataPath,"../Diagnostics"));Directory.CreateDirectory(dir);
        var report=new PolicyReport{status=status,lane=lane,completed_laps=completedLaps,predictions=inferenceCount,
            seconds=Time.time-policyStart,max_cte_m=maxPolicyCte,minimum_road_margin_m=minPolicyMargin};
        File.WriteAllText(Path.Combine(dir,"policy_lane"+lane+".json"),JsonUtility.ToJson(report,true));
        CapturePreview();Stop();
        #if UNITY_EDITOR
        UnityEditor.EditorApplication.Exit(status=="completed"?0:3);
        #else
        Application.Quit(status=="completed"?0:3);
        #endif
    }
}
