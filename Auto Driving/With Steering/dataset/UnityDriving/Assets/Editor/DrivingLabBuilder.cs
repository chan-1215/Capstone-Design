using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class DrivingLabBuilder
{
    const string ScenePath="Assets/Scenes/DrivingLab.unity";
    static DrivingLabBuilder()
    {
        EditorApplication.delayCall+=ApplyPendingRefresh;
        EditorApplication.playModeStateChanged+=state=>
        {if(state==PlayModeStateChange.EnteredEditMode)EditorApplication.delayCall+=ApplyPendingRefresh;};
    }
    static void ApplyPendingRefresh()
    {
            if(EditorApplication.isPlayingOrWillChangePlaymode)return;
            if(File.Exists("Tools/refresh-robot.request"))
            {
                File.Delete("Tools/refresh-robot.request");
                // Apply the requested pose to the loaded asset too: a live
                // editor may still hold its previous serialized values in RAM.
                var cfg=AssetDatabase.LoadAssetAtPath<DrivingConfig>("Assets/Settings/DrivingConfig.asset");
                if(cfg!=null)
                {
                    cfg.cameraHeight=.155f;cfg.cameraForward=.02f;cfg.cameraHeightVariation=0;
                    cfg.showLaneTracking=true;
                    if(File.Exists("C:/Users/a/AppData/Local/Programs/Python/Python39/python.exe"))
                        cfg.openCvPython="C:/Users/a/AppData/Local/Programs/Python/Python39/python.exe";
                    cfg.showHud=false;cfg.autoStartLearned=true;
                    EditorUtility.SetDirty(cfg);
                }
                RefreshRobot();
            }
            else if(!File.Exists(ScenePath))Build();
    }
    [MenuItem("Capstone/Refresh robot only")]
    public static void RefreshRobot()
    {
        if(EditorApplication.isPlayingOrWillChangePlaymode)return;
        var lab=Object.FindObjectOfType<DrivingLab>();if(lab==null){Debug.LogWarning("Open DrivingLab scene first.");return;}
        var settings=AssetDatabase.LoadAssetAtPath<DrivingConfig>("Assets/Settings/DrivingConfig.asset");
        if(settings!=null)lab.config=settings;
        lab.CleanFieldPreview();
        lab.RefreshRobotPreview();
        const string generated="Assets/Generated/SceneResources.asset";
        foreach(var renderer in lab.GetComponentsInChildren<Renderer>())
            foreach(var material in renderer.sharedMaterials)
                if(material!=null&&!AssetDatabase.Contains(material))AssetDatabase.AddObjectToAsset(material,generated);
        EditorSceneManager.MarkSceneDirty(lab.gameObject.scene);
        EditorSceneManager.SaveScene(lab.gameObject.scene);
        AssetDatabase.SaveAssets();lab.CapturePreview();
        PresentField();
        Debug.Log("Robot-only refresh completed; camera optical centre Y="+lab.config.cameraHeight+"m, Z="+lab.config.cameraForward+"m.");
    }
    [MenuItem("Capstone/Build or reset driving lab")]
    public static void Build()
    {
        Directory.CreateDirectory("Assets/Scenes");Directory.CreateDirectory("Assets/Settings");AssetDatabase.Refresh();
        var cfg=AssetDatabase.LoadAssetAtPath<DrivingConfig>("Assets/Settings/DrivingConfig.asset");
        if(cfg==null){cfg=ScriptableObject.CreateInstance<DrivingConfig>();AssetDatabase.CreateAsset(cfg,"Assets/Settings/DrivingConfig.asset");}
        var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
        var lab=new GameObject("PedestrianDrivingLab").AddComponent<DrivingLab>();lab.config=cfg;lab.Rebuild();
        Directory.CreateDirectory("Assets/Generated");
        const string generated="Assets/Generated/SceneResources.asset";
        AssetDatabase.DeleteAsset(generated);
        AssetDatabase.CreateAsset(new Material(Shader.Find("Standard")),generated);
        foreach(var filter in lab.GetComponentsInChildren<MeshFilter>())
            if(filter.sharedMesh!=null&&!AssetDatabase.Contains(filter.sharedMesh))AssetDatabase.AddObjectToAsset(filter.sharedMesh,generated);
        foreach(var renderer in lab.GetComponentsInChildren<Renderer>())
            foreach(var material in renderer.sharedMaterials)
                if(material!=null&&!AssetDatabase.Contains(material))AssetDatabase.AddObjectToAsset(material,generated);
        EditorSceneManager.SaveScene(scene,ScenePath);
        EditorBuildSettings.scenes=new[]{new EditorBuildSettingsScene(ScenePath,true)};
        AssetDatabase.SaveAssets();Selection.activeObject=lab;
        lab.CapturePreview();
        PresentField();
        Debug.Log("Driving lab ready: "+ScenePath);
    }
    static void PresentField()
    {
        var view=SceneView.lastActiveSceneView;
        if(view!=null){view.drawGizmos=false;view.showGrid=false;view.Repaint();}
    }
    public static void Smoke()
    {
        Build();
        var args=System.Environment.GetCommandLineArgs();int f=System.Array.IndexOf(args,"-featureImage");
        if(f>=0&&f+1<args.Length)
        {
            var image=new Texture2D(2,2,TextureFormat.RGB24,false);image.LoadImage(File.ReadAllBytes(args[f+1]));
            Directory.CreateDirectory("Diagnostics");
            File.WriteAllText("Diagnostics/unity_features.json",JsonUtility.ToJson(new FeatureCheck{values=VisionPolicy.Features(image.GetPixels32(),image.width,image.height)}));
            Object.DestroyImmediate(image);
        }
        EditorApplication.isPlaying=true;
    }
    [System.Serializable] class FeatureCheck{public float[] values;}
    public static void AlignData()
    {
        Build();var args=System.Environment.GetCommandLineArgs();
        int a=System.Array.IndexOf(args,"-sourceDataset"),b=System.Array.IndexOf(args,"-alignedOutput");
        if(a<0||b<0)throw new System.ArgumentException("sourceDataset and alignedOutput are required");
        Object.FindObjectOfType<DrivingLab>().RenderAlignedDataset(args[a+1],args[b+1]);
    }
}
