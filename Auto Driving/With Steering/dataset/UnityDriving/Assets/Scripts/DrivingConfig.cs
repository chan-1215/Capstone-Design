using UnityEngine;

[CreateAssetMenu(menuName="Capstone/Driving configuration")]
public class DrivingConfig : ScriptableObject
{
    [Header("Metres; wheel gaps interpreted as free space between tyres")]
    public float trackScale = 1.0f;
    public float roadWidth = 0.46f;
    public float wheelbase = 0.122f;
    public float wheelTrack = 0.120f;
    public float rearWheelTrack = 0.128f;
    public float wheelRadius = 0.0335f;
    public float bodyLength = 0.1305101f;
    public float bodyWidth = 0.0881144f;
    public bool useCadWheels = true;
    [Header("Calibration: servo commands are NOT road-wheel angles")]
    public float leftWheelLimit = 35f;
    public float rightWheelLimit = 35f;
    public float leftServoCommand = -105f;
    public float rightServoCommand = 85f;
    public float steeringRate = 140f;
    public float maximumSpeed = 0.65f;
    public float acceleration = 0.7f;
    public float expertSpeed = 0.28f;
    public float lookahead = 0.17f;
    [Header("Camera matches adjustable robot mount")]
    public float cameraHeight = 0.155f;
    [Tooltip("Camera optical centre relative to frame centre. Negative Z is rearward.")]
    public float cameraForward = 0.02f;
    public float cameraPitch = 30f;
    public float cameraVerticalFov = 48f;
    public int imageWidth = 640;
    public int imageHeight = 480;
    public int captureHz = 10;
    [Header("Episodes and variation")]
    public int initialSeed = 20261110;
    public float initialOffsetRange = 0.035f;
    public float initialYawRange = 7f;
    public float cameraPitchVariation = 2f;
    public float cameraHeightVariation = 0f;
    public float episodeSeconds = 60f;
    public int sampleLimit = 3000;
    public bool randomize = true;
    [Header("Display")]
    public bool showHud = false;
    public bool showLaneTracking = true;
    public string openCvPython = "python";
    public bool autoStartLearned = true;
    public float modelUpdatesHz = 15f;
    public float learnedSpeedScale = .85f;
    void OnValidate()
    {
        trackScale=Mathf.Max(.5f,trackScale);roadWidth=Mathf.Max(.15f,roadWidth);
        wheelbase=Mathf.Max(.05f,wheelbase);wheelRadius=Mathf.Max(.01f,wheelRadius);
        leftWheelLimit=Mathf.Clamp(leftWheelLimit,1,60);rightWheelLimit=Mathf.Clamp(rightWheelLimit,1,60);
        maximumSpeed=Mathf.Max(.05f,maximumSpeed);lookahead=Mathf.Max(.05f,lookahead);
        imageWidth=Mathf.Clamp(imageWidth,64,1920);imageHeight=Mathf.Clamp(imageHeight,64,1080);
        captureHz=Mathf.Clamp(captureHz,1,30);sampleLimit=Mathf.Max(1,sampleLimit);
    }
}
