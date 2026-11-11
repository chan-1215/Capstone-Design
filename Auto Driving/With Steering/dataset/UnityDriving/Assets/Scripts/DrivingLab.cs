using System;
using System.IO;
using UnityEngine;

public partial class DrivingLab : MonoBehaviour
{
    public DrivingConfig config;
    TrackGeometry track;
    RobotVehicle car;
    Camera overview;
    Light sun;
    DatasetRecorder recorder;
    RenderTexture preview;
    bool driving, expert, smoke, hudVisible, cameraInputVisible;
    int episode, seed, lane, completedLaps, offroadResets;
    float smokeSeconds=8;
    float episodeStart, nextCapture, manualAngle, manualSpeed, progress, lastStation;
    float cte, heading, margin, target;
    string notice="Parked. Start manual drive or teacher drive when ready.";
    GUIStyle style;
    OpenCvLaneView laneView;
    Texture2D parkedLaneImage;
    float nextLaneFrame;
    System.Random rng;

    public void Rebuild()
    {
        if(config==null)config=ScriptableObject.CreateInstance<DrivingConfig>();
        var old=transform.Find("Generated");
        if(old!=null){if(Application.isPlaying)Destroy(old.gameObject);else DestroyImmediate(old.gameObject);}
        var generated=new GameObject("Generated").transform;generated.SetParent(transform,false);
        RenderSettings.ambientMode=UnityEngine.Rendering.AmbientMode.Flat;
        RenderSettings.ambientLight=new Color(.67f,.69f,.72f);
        RenderSettings.skybox=null;
        MakeCube(generated,"White track mat",new Vector3(0,-.008f,0),new Vector3(2.65f*config.trackScale,.012f,3.05f*config.trackScale),new Color(.87f,.86f,.83f));
        track=new TrackGeometry(generated,config);
        car=new RobotVehicle(generated,config);
        sun=new GameObject("Directional light").AddComponent<Light>();sun.transform.SetParent(generated,false);
        sun.type=LightType.Directional;sun.intensity=1.1f;sun.transform.rotation=Quaternion.Euler(55,-30,0);sun.shadows=LightShadows.Soft;
        overview=new GameObject("Overview camera").AddComponent<Camera>();overview.transform.SetParent(generated,false);
        overview.tag="MainCamera";overview.transform.position=new Vector3(0,3.5f,-2.2f)*config.trackScale;
        overview.transform.LookAt(Vector3.zero);overview.fieldOfView=51;overview.nearClipPlane=.01f;overview.farClipPlane=30;
        overview.backgroundColor=new Color(.08f,.09f,.11f);overview.clearFlags=CameraClearFlags.SolidColor;
        overview.depth=-1;
        NewEpisode(false);
    }
    static void MakeCube(Transform parent,string name,Vector3 position,Vector3 scale,Color color)
    {
        var g=GameObject.CreatePrimitive(PrimitiveType.Cube);g.name=name;g.transform.SetParent(parent,false);g.transform.localPosition=position;
        g.transform.localScale=scale;g.GetComponent<Renderer>().sharedMaterial=TrackGeometry.Mat(color);
    }
    public void RefreshRobotPreview()
    {
        if(Application.isPlaying)return;
        var generated=transform.Find("Generated");if(generated==null)return;
        var old=generated.Find("Blue_ServoSteering_Robot");
        Vector3 p=old!=null?old.position:Vector3.zero;
        Quaternion q=old!=null?old.rotation:Quaternion.identity;
        if(old!=null)DestroyImmediate(old.gameObject);
        car=new RobotVehicle(generated,config);car.root.SetPositionAndRotation(p,q);
        var cameraNode=generated.Find("Overview camera");
        if(cameraNode!=null)overview=cameraNode.GetComponent<Camera>();
    }
    public void CleanFieldPreview()
    {
        if(Application.isPlaying)return;
        var generated=transform.Find("Generated");if(generated==null)return;
        for(int i=generated.childCount-1;i>=0;i--)
        {
            var item=generated.GetChild(i);
            if(item.name=="Floor"||item.name=="Floor joint"||item.name=="Lab desk"||item.name=="Desk leg")DestroyImmediate(item.gameObject);
        }
        RenderSettings.skybox=null;
    }
    void Start()
    {
        #if UNITY_EDITOR
        var canonical=UnityEditor.AssetDatabase.LoadAssetAtPath<DrivingConfig>("Assets/Settings/DrivingConfig.asset");
        if(canonical!=null)config=canonical;
        #endif
        Rebuild();Application.targetFrameRate=60;Time.fixedDeltaTime=.02f;
        hudVisible=config.showHud;
        preview=new RenderTexture(640,480,24);preview.Create();
        cameraInputVisible=config.showLaneTracking;
        if(config.showLaneTracking)laneView=new OpenCvLaneView(config.openCvPython);
        smoke=Array.IndexOf(Environment.GetCommandLineArgs(),"-simSmoke")>=0;
        if(smoke)
        {
            var args=Environment.GetCommandLineArgs();int at=Array.IndexOf(args,"-simSeconds");
            if(at>=0&&at+1<args.Length)float.TryParse(args[at+1],System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out smokeSeconds);
            smokeSeconds=Mathf.Clamp(smokeSeconds,1,180);Time.timeScale=4;
        }
        if(!SetupPolicyMode()&&smoke)
        {
            expert=true;driving=true;ToggleRecord();notice="Smoke test in progress";
        }
    }
    void NewEpisode(bool randomize)
    {
        episode++;seed=config.initialSeed+episode*9973;rng=new System.Random(seed);
        float s=randomize?(float)rng.NextDouble()*track.length:track.length-.5f;
        float offset=track.LaneOffset(lane),jitter=0,yaw=0;
        if(randomize && config.randomize)
        {
            jitter=Range(-config.initialOffsetRange,config.initialOffsetRange);yaw=Range(-config.initialYawRange,config.initialYawRange);
            car.SetCameraPose(config.cameraHeight+Range(-config.cameraHeightVariation,config.cameraHeightVariation),config.cameraPitch+Range(-config.cameraPitchVariation,config.cameraPitchVariation));
            sun.intensity=Range(.75f,1.3f);sun.transform.rotation=Quaternion.Euler(Range(40,70),Range(-50,50),0);
        }
        else
        {
            car.SetCameraPose(config.cameraHeight,config.cameraPitch);
        }
        car.root.position=track.At(s,offset+jitter);
        car.root.rotation=Quaternion.LookRotation(track.At(s+.025f,offset)-track.At(s,offset))*Quaternion.Euler(0,yaw,0);
        car.Stop();car.wheelAngle=0;episodeStart=Time.time;progress=0;lastStation=s;
        if(recorder!=null)recorder.Episode(episode,seed,lane,Time.time,car,sun.intensity);
        Observe();notice="Episode "+episode+", seed "+seed+", lane "+(lane+1);
    }
    float Range(float a,float b){return a+(float)rng.NextDouble()*(b-a);}
    void Observe()
    {
        int n=track.Nearest(car.root.position);float s=track.Station(n);cte=track.SignedOffset(car.root.position,n)-track.LaneOffset(lane);
        heading=Vector3.SignedAngle(car.root.forward,track.Tangent(n),Vector3.up);
        margin=float.MaxValue;
        float envelopeWidth=Mathf.Max(config.bodyWidth,Mathf.Max(config.wheelTrack,config.rearWheelTrack)+.018f);
        float envelopeLength=Mathf.Max(config.bodyLength,config.wheelbase+config.wheelRadius*2);
        foreach(float x in new[]{-envelopeWidth/2,envelopeWidth/2})foreach(float z in new[]{-envelopeLength/2,envelopeLength/2})
        {
            Vector3 p=car.root.TransformPoint(new Vector3(x,0,z));int k=track.Nearest(p);
            margin=Mathf.Min(margin,track.width/2-Mathf.Abs(track.SignedOffset(p,k)));
        }
        float ds=Mathf.Repeat(s-lastStation+track.length/2,track.length)-track.length/2;
        progress+=ds;lastStation=s;
        // Pure-pursuit teacher has access to simulated ground truth, not the camera.
        Vector3 rear=car.root.position-car.root.forward*config.wheelbase/2;
        Vector3 worldTarget=track.At(s+config.lookahead,track.LaneOffset(lane));
        Vector3 local=Quaternion.Inverse(car.root.rotation)*(worldTarget-rear);
        target=Mathf.Atan2(2*config.wheelbase*local.x,Mathf.Max(.001f,local.x*local.x+local.z*local.z))*Mathf.Rad2Deg;
        target=Mathf.Clamp(target,-config.leftWheelLimit,config.rightWheelLimit);
    }
    void Update()
    {
        if(Input.GetKeyDown(KeyCode.H))hudVisible=!hudVisible;
        if(Input.GetKeyDown(KeyCode.C))cameraInputVisible=!cameraInputVisible;
        if(Input.GetKey(KeyCode.Space)||Input.GetKey(KeyCode.Escape)){Stop();return;}
        if(Input.GetKeyDown(KeyCode.T)){learned=false;expert=!expert;driving=true;}
        if(Input.GetKeyDown(KeyCode.P))StartLearned();
        if(Input.GetKeyDown(KeyCode.R))ToggleRecord();
        if(Input.GetKeyDown(KeyCode.N))NewEpisode(true);
        float steer=(Input.GetKey(KeyCode.D)?1:0)-(Input.GetKey(KeyCode.A)?1:0);
        float motor=(Input.GetKey(KeyCode.W)?1:0)-(Input.GetKey(KeyCode.S)?1:0);
        if(steer!=0||motor!=0){learned=false;expert=false;driving=true;}
        manualAngle=steer<0?steer*config.leftWheelLimit:steer*config.rightWheelLimit;
        manualSpeed=motor*config.expertSpeed;
    }
    void FixedUpdate()
    {
        if(car==null)return;Observe();
        if(driving&&learned)StepLearned();
        else
        {
            float v=expert?config.expertSpeed/(1+Mathf.Abs(target)/70f):manualSpeed;
            car.Step(driving?(expert?target:manualAngle):0,driving?v:0,Time.fixedDeltaTime);
        }
        Observe();
    }
    void LateUpdate()
    {
        if(car==null)return;
        CheckPolicy();
        if(preview!=null&&!policyTest){car.camera.targetTexture=preview;car.camera.Render();car.camera.targetTexture=null;}
        UpdateLaneView();
        if(recorder!=null && Time.time>=nextCapture && Mathf.Abs(car.speed)>.015f)
        {
            Observe();nextCapture=Time.time+1f/Mathf.Max(1,config.captureHz);
            try{recorder.Save(car.camera,episode,seed,lane,Time.time,car,target,cte,heading,margin,margin>0,learned?"learned_camera_mlp":expert?"ground_truth_teacher":"manual");}
            catch(Exception e){notice="Recording stopped: "+e.Message;FinishRecording();Stop();Debug.LogException(e);}
            if(recorder!=null && recorder.count>=config.sampleLimit){FinishRecording();Stop();notice="Sample limit reached; stopped.";}
        }
        if(driving && (margin<-.02f||Mathf.Abs(cte)>config.roadWidth))
        {
            if(recorder!=null&&expert){offroadResets++;lane=1-lane;NewEpisode(true);}else{Stop();notice="Outside road margin. Stopped; N resets.";}
        }
        if(recorder!=null&&expert&&(Time.time-episodeStart>config.episodeSeconds||progress>track.length))
        {if(progress>track.length)completedLaps++;lane=1-lane;NewEpisode(true);}
        if(smoke && !policyTest && Time.time>smokeSeconds)
        {
            int samples=recorder==null?0:recorder.count;
            string dir=Path.GetFullPath(Path.Combine(Application.dataPath,"../Diagnostics"));Directory.CreateDirectory(dir);
            File.WriteAllText(Path.Combine(dir,"smoke.json"),"{\"samples\":"+samples+",\"episode\":"+episode+",\"completed_laps\":"+completedLaps+",\"offroad_resets\":"+offroadResets+",\"status\":\"rendered\"}");
            CapturePreview();
            FinishRecording();Stop();
            #if UNITY_EDITOR
            UnityEditor.EditorApplication.Exit(samples>0&&offroadResets==0?0:2);
            #else
            Application.Quit(samples>0?0:2);
            #endif
        }
    }
    [Serializable] class RobotLayout
    {
        public Vector3 camera_optical_centre_relative_to_frame_m;
        public float camera_height_above_ground_m;
        public Vector3 vehicle_forward_world,camera_forward_world,visible_lens_forward_world;
        public float forward_alignment;
        public float horizontal_forward_alignment,motion_forward_alignment;
        public string[] visible_parts;
    }
    public void CapturePreview()
    {
        if(car==null||overview==null)return;
        string dir=Path.GetFullPath(Path.Combine(Application.dataPath,"../Diagnostics"));Directory.CreateDirectory(dir);
        SaveView(overview,Path.Combine(dir,"unity_overview.png"),1280,960);
        SaveView(car.camera,Path.Combine(dir,"unity_camera.png"),config.imageWidth,config.imageHeight);
        if(policy!=null&&policy.InputImage!=null)File.WriteAllBytes(Path.Combine(dir,"unity_policy_input.png"),policy.InputImage.EncodeToPNG());
        if(laneView!=null&&laneView.Latest!=null&&laneView.Overlay!=null)
        {
            File.WriteAllBytes(Path.Combine(dir,"opencv_tracking.png"),laneView.Overlay.EncodeToPNG());
            var summary=laneView.Latest;summary.jpeg=null;
            File.WriteAllText(Path.Combine(dir,"opencv_tracking.json"),JsonUtility.ToJson(summary,true));
        }
        var modelCam=new GameObject("Diagnostic model camera").AddComponent<Camera>();modelCam.enabled=false;
        modelCam.transform.position=car.root.TransformPoint(new Vector3(.32f,.26f,.32f));modelCam.transform.LookAt(car.root.position+Vector3.up*.075f);
        modelCam.fieldOfView=45;modelCam.nearClipPlane=.005f;
        SaveView(modelCam,Path.Combine(dir,"unity_robot.png"),1000,800);
        if(Application.isPlaying)Destroy(modelCam.gameObject);else DestroyImmediate(modelCam.gameObject);
        File.WriteAllText(Path.Combine(dir,"robot_layout.json"),JsonUtility.ToJson(new RobotLayout{
            camera_optical_centre_relative_to_frame_m=car.camera.transform.localPosition,
            camera_height_above_ground_m=car.camera.transform.position.y,
            vehicle_forward_world=car.root.forward,camera_forward_world=car.camera.transform.forward,
            visible_lens_forward_world=car.cameraVisual.forward,
            forward_alignment=Vector3.Dot(car.root.forward,car.camera.transform.forward),
            horizontal_forward_alignment=Vector3.Dot(car.root.forward,Vector3.ProjectOnPlane(car.camera.transform.forward,Vector3.up).normalized),
            motion_forward_alignment=car.lastMotionWorld.sqrMagnitude>.00000001f?Vector3.Dot(car.lastMotionWorld.normalized,car.root.forward):0,
            visible_parts=new[]{"rectangular frame","four wheels","connected camera support and bracket","camera module and lens"}},true));
    }
    static void SaveView(Camera camera,string path,int width,int height)
    {
        var old=RenderTexture.active;var oldTarget=camera.targetTexture;
        var rt=new RenderTexture(width,height,24);rt.Create();
        var image=new Texture2D(width,height,TextureFormat.RGB24,false);
        try{camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;image.ReadPixels(new Rect(0,0,width,height),0,0);image.Apply();File.WriteAllBytes(path,image.EncodeToPNG());}
        finally
        {
            camera.targetTexture=oldTarget;RenderTexture.active=old;rt.Release();
            if(Application.isPlaying){Destroy(rt);Destroy(image);}else{DestroyImmediate(rt);DestroyImmediate(image);}
        }
    }
    void Stop(){driving=false;expert=false;learned=false;manualSpeed=0;if(car!=null)car.Stop();}
    void ToggleRecord()
    {
        if(recorder!=null){FinishRecording();return;}
        try
        {
            recorder=new DatasetRecorder(config,"{\"simulator\":\"Unity2022.3\",\"dynamics\":\"kinematic_bicycle\",\"teacher\":\"ground_truth_pure_pursuit\",\"dimensions\":\"cad_parts_and_interpreted_wheel_gaps_track_unmeasured\",\"servo_mapping\":\"assumed_linear_not_calibrated\",\"labels\":\"capture_pose_target_for_next_action_and_latest_applied_action\",\"synthetic\":true}");
            recorder.Episode(episode,seed,lane,Time.time,car,sun.intensity);
            notice="Recording: "+recorder.directory;nextCapture=Time.time;
        }
        catch(Exception e){notice=e.Message;Stop();Debug.LogException(e);}
    }
    void FinishRecording(){if(recorder!=null){notice="Saved "+recorder.count+" frames: "+recorder.directory;recorder.Dispose();recorder=null;}}
    void UpdateLaneView()
    {
        if(laneView==null)return;laneView.Poll();
        if(Time.realtimeSinceStartup<nextLaneFrame)return;
        nextLaneFrame=Time.realtimeSinceStartup+.1f;
        if(learned&&policy!=null){laneView.Submit(policy.InputImage);return;}
        if(preview==null||policyTest)return;
        if(parkedLaneImage==null)parkedLaneImage=new Texture2D(preview.width,preview.height,TextureFormat.RGB24,false);
        var old=RenderTexture.active;RenderTexture.active=preview;
        parkedLaneImage.ReadPixels(new Rect(0,0,preview.width,preview.height),0,0,false);parkedLaneImage.Apply(false);
        RenderTexture.active=old;laneView.Submit(parkedLaneImage);
    }
    void OnDisable(){FinishRecording();if(laneView!=null){laneView.Dispose();laneView=null;}if(parkedLaneImage!=null)Destroy(parkedLaneImage);if(policy!=null){policy.Dispose();policy=null;}if(preview!=null){preview.Release();Destroy(preview);}}
    void OnGUI()
    {
        if(car==null)return;
        if(cameraInputVisible)
        {
            float w=Mathf.Min(480,Screen.width-32),h=w*.75f;
            GUI.Box(new Rect(Screen.width-w-16,16,w,h+96),"");
            var input=laneView!=null&&laneView.Latest!=null?(Texture)laneView.Overlay:policy!=null?policy.InputImage:(Texture)preview;
            if(input!=null)GUI.DrawTexture(new Rect(Screen.width-w-12,48,w-8,h-8),input,ScaleMode.ScaleToFit);
            if(style==null){style=new GUIStyle(GUI.skin.label);style.font=Font.CreateDynamicFontFromOSFont("Malgun Gothic",17);style.fontSize=17;style.wordWrap=true;}
            GUI.Label(new Rect(Screen.width-w,20,w-16,26),"카메라 · OpenCV 차선 추적 / C 숨김",style);
            GUI.Label(new Rect(Screen.width-w,48+h,w-16,60),(laneView!=null?laneView.Status:"원본 영상")+"\n노랑: 경계 / 하늘색: 점선 / 초록: 점선 연결\n주행 제어: "+(learned?"학습 모델":"수동·교사·대기"),style);
        }
        if(!hudVisible)return;
        if(style==null){style=new GUIStyle(GUI.skin.label);style.font=Font.CreateDynamicFontFromOSFont("Malgun Gothic",17);style.fontSize=17;style.wordWrap=true;}
        GUI.skin.font=style.font;GUI.skin.button.fontSize=15;
        GUI.Box(new Rect(12,12,380,420),"");
        GUILayout.BeginArea(new Rect(25,22,352,400));
        GUILayout.Label("보행자와 소통하는 자율주행 데이터 실험",style);
        GUILayout.Label("사진 기반 근사 트랙 · 파란 서보 조향 로봇",style);
        GUILayout.Space(10);
        if(GUILayout.Button("학습 모델 주행 / P",GUILayout.Height(30)))StartLearned();
        if(GUILayout.Button(driving?"정지 / SPACE":"교사 주행 시작 / T",GUILayout.Height(34))){if(driving)Stop();else{expert=true;driving=true;}}
        if(GUILayout.Button(recorder==null?"데이터 기록 시작 / R":"데이터 기록 종료 / R",GUILayout.Height(30)))ToggleRecord();
        if(GUILayout.Button("새 구간 · 재배치 / N",GUILayout.Height(28)))NewEpisode(true);
        if(GUILayout.Button("차선 변경 (현재 "+(lane+1)+")",GUILayout.Height(28))){lane=1-lane;NewEpisode(false);}
        GUILayout.Label("W/S 전후진 · A/D 조향 · SPACE 즉시 정지",style);
        GUILayout.Label(string.Format("속도 {0:F2} m/s · 바퀴 조향 {1:F1}°\n서보 명령 {2:F1} · 경로 오차 {3:F3} m\n기록 {4}장 · {5}",car.speed,car.wheelAngle,car.ServoFor(car.wheelAngle),cte,recorder==null?0:recorder.count,learned?"학습 모델":expert?"교사":"수동/대기"),style);
        GUILayout.Label("치수·카메라·조향 보정: Assets/Settings/DrivingConfig",style);
        GUILayout.EndArea();
        if(preview!=null&&!cameraInputVisible){float w=Mathf.Min(480,Screen.width-415);if(w>100)GUI.DrawTexture(new Rect(Screen.width-w-12,12,w,w*.75f),preview,ScaleMode.ScaleToFit);}
        GUI.Box(new Rect(12,Screen.height-72,Screen.width-24,60),"");
        GUI.Label(new Rect(24,Screen.height-66,Screen.width-48,54),notice,style);
    }
}
