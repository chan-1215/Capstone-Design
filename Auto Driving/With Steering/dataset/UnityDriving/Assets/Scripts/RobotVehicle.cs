using UnityEngine;

// Deterministic bicycle model, not a measured motor/tyre physics model.
// +wheel angle and +servo command = right; metres and seconds throughout.
public class RobotVehicle
{
    public Transform root, frontLeft, frontRight;
    public Camera camera;
    public Transform cameraVisual;
    Transform cameraPost, cameraBracket, cameraBaseArm;
    const float FrameCentreY=.055f, FrameThickness=.018f;
    public float speed, wheelAngle, throttle, targetAngle;
    public float leftRearSpeed, rightRearSpeed;
    public Vector3 lastMotionWorld;
    readonly DrivingConfig c;
    readonly Transform[] wheels=new Transform[4];
    public RobotVehicle(Transform parent,DrivingConfig config)
    {
        c=config;root=new GameObject("Blue_ServoSteering_Robot").transform;root.SetParent(parent,false);
        Part("Rectangular blue frame",PrimitiveType.Cube,new Vector3(0,FrameCentreY,0),new Vector3(c.bodyWidth,FrameThickness,c.bodyLength),new Color(.035f,.10f,.8f));
        cameraPost=Part("Camera support - fixed to frame",PrimitiveType.Cube,Vector3.zero,Vector3.one,new Color(.035f,.10f,.8f));
        cameraBaseArm=Part("Camera rear mounting arm",PrimitiveType.Cube,Vector3.zero,Vector3.one,new Color(.035f,.10f,.8f));
        cameraBracket=Part("Camera bracket - connected to module",PrimitiveType.Cube,Vector3.zero,Vector3.one,new Color(.035f,.10f,.8f));
        cameraVisual=new GameObject("Camera visual - optical centre").transform;
        cameraVisual.SetParent(root,false);
        var module=Part("Camera module",PrimitiveType.Cube,new Vector3(0,0,-.006f),new Vector3(.028f,.025f,.008f),new Color(.02f,.2f,.09f));
        module.SetParent(cameraVisual,false);
        // A projecting lens barrel makes the +Z viewing side unambiguous.
        // It stays inside the real camera's 15mm near plane.
        var lens=Part("Forward lens barrel",PrimitiveType.Cylinder,new Vector3(0,0,.004f),new Vector3(.014f,.006f,.014f),new Color(.025f,.025f,.025f));
        lens.SetParent(cameraVisual,false);lens.localRotation=Quaternion.Euler(90,0,0);
        var glass=Part("Forward lens glass",PrimitiveType.Cylinder,new Vector3(0,0,.0104f),new Vector3(.011f,.0004f,.011f),new Color(.08f,.45f,.65f));
        glass.SetParent(cameraVisual,false);glass.localRotation=Quaternion.Euler(90,0,0);
        for(int i=0;i<4;i++)
        {
            bool front=i<2;float axleWidth=front?c.wheelTrack:c.rearWheelTrack;
            float x=i%2==0?-axleWidth/2:axleWidth/2;
            var pivot=new GameObject(front?"Front steer pivot":"Rear axle").transform;pivot.SetParent(root,false);
            pivot.localPosition=new Vector3(x,c.wheelRadius,front?c.wheelbase/2:-c.wheelbase/2);
            var tire=GameObject.CreatePrimitive(PrimitiveType.Cylinder);tire.name=front?"Blue front wheel":"Black rear tyre";
            tire.transform.SetParent(pivot,false);tire.transform.localRotation=Quaternion.Euler(0,0,90);
            tire.transform.localScale=new Vector3(c.wheelRadius*2,.009f,c.wheelRadius*2);
            tire.GetComponent<Renderer>().sharedMaterial=TrackGeometry.Mat(front?new Color(.035f,.10f,.8f):new Color(.02f,.02f,.025f));
            var hub=GameObject.CreatePrimitive(PrimitiveType.Cylinder);hub.name="Wheel hub";hub.transform.SetParent(pivot,false);
            hub.transform.localRotation=Quaternion.Euler(0,0,90);hub.transform.localScale=new Vector3(c.wheelRadius*1.05f,.009f,c.wheelRadius*1.05f);
            hub.GetComponent<Renderer>().sharedMaterial=TrackGeometry.Mat(front?new Color(.03f,.15f,.7f):new Color(1,.75f,.02f));
            var wheelModel=Resources.Load<GameObject>("Models/Hweel_Wheel");
            if(c.useCadWheels&&wheelModel!=null)
            {
                // Use one outer wheel surface. Overlapping a full-size CAD
                // wheel and a cylinder would create flickering coplanar faces.
                if(Application.isPlaying)Object.Destroy(tire);else Object.DestroyImmediate(tire);
                hub.transform.localScale=new Vector3(c.wheelRadius*1.05f,.0094f,c.wheelRadius*1.05f);
                var cad=Object.Instantiate(wheelModel,pivot);cad.name="User CAD - hweel";
                cad.transform.localPosition=Vector3.zero;cad.transform.localRotation=Quaternion.identity;
                cad.transform.localScale=Vector3.one*(c.wheelRadius*2/.067f);
                foreach(var r in cad.GetComponentsInChildren<Renderer>())r.sharedMaterial=TrackGeometry.Mat(front?new Color(.035f,.10f,.8f):new Color(.02f,.02f,.025f));
            }
            wheels[i]=pivot;
        }
        frontLeft=wheels[0];frontRight=wheels[1];
        camera=new GameObject("Robot_Camera_RGB").AddComponent<Camera>();camera.transform.SetParent(root,false);
        SetCameraPose(c.cameraHeight,c.cameraPitch);
        camera.fieldOfView=c.cameraVerticalFov;camera.nearClipPlane=.015f;camera.farClipPlane=20;
        // Disable automatic screen rendering only. VisionPolicy explicitly
        // calls Camera.Render into its input texture on each inference step.
        camera.enabled=false;
    }
    Transform Part(string n,PrimitiveType type,Vector3 p,Vector3 s,Color color)
    {
        var g=GameObject.CreatePrimitive(type);g.name=n;g.transform.SetParent(root,false);g.transform.localPosition=p;g.transform.localScale=s;
        g.GetComponent<Renderer>().sharedMaterial=TrackGeometry.Mat(color);
        return g.transform;
    }
    public void SetCameraPose(float height,float pitch)
    {
        Vector3 p=new Vector3(0,height,c.cameraForward);Quaternion q=Quaternion.Euler(pitch,0,0);
        camera.transform.localPosition=p;camera.transform.localRotation=q;
        cameraVisual.localPosition=p;cameraVisual.localRotation=q;
        // A vertical post starts on the frame; the short bracket meets the
        // bottom of the tilted camera body. Optical centre stays at p.
        Vector3 bottomOfModule=p-q*Vector3.forward*.006f-q*Vector3.up*.0125f;
        float anchorZ=Mathf.Clamp(c.cameraForward,-c.bodyLength/2+.006f,c.bodyLength/2-.006f);
        Vector3 basePoint=new Vector3(0,FrameCentreY+FrameThickness/2,anchorZ);
        Vector3 rearBase=new Vector3(0,basePoint.y,c.cameraForward-.020f);
        Vector3 topPoint=new Vector3(0,bottomOfModule.y,rearBase.z);
        SetBeam(cameraBaseArm,basePoint,rearBase,.008f);
        SetBeam(cameraPost,rearBase,topPoint,.008f);
        SetBeam(cameraBracket,topPoint,bottomOfModule,.008f);
    }
    static void SetBeam(Transform beam,Vector3 a,Vector3 b,float width)
    {
        Vector3 delta=b-a;
        beam.localPosition=(a+b)/2;
        beam.localRotation=delta.sqrMagnitude>.00000001f?Quaternion.FromToRotation(Vector3.up,delta.normalized):Quaternion.identity;
        beam.localScale=new Vector3(width,Mathf.Max(delta.magnitude,.001f),width);
    }
    public void Step(float desiredAngle,float desiredSpeed,float dt)
    {
        Vector3 previousPosition=root.position;
        targetAngle=Mathf.Clamp(desiredAngle,-c.leftWheelLimit,c.rightWheelLimit);
        wheelAngle=Mathf.MoveTowards(wheelAngle,targetAngle,c.steeringRate*dt);
        speed=Mathf.MoveTowards(speed,Mathf.Clamp(desiredSpeed,-c.maximumSpeed,c.maximumSpeed),c.acceleration*dt);
        throttle=desiredSpeed/c.maximumSpeed;
        float yawRate=speed/c.wheelbase*Mathf.Tan(wheelAngle*Mathf.Deg2Rad);
        Quaternion mid=root.rotation*Quaternion.Euler(0,yawRate*Mathf.Rad2Deg*dt*.5f,0);
        Vector3 rear=root.position-root.forward*c.wheelbase/2;
        rear+=mid*Vector3.forward*speed*dt;
        root.rotation*=Quaternion.Euler(0,yawRate*Mathf.Rad2Deg*dt,0);
        root.position=rear+root.forward*c.wheelbase/2;
        lastMotionWorld=root.position-previousPosition;
        UpdateWheelVisuals();
        leftRearSpeed=speed+yawRate*c.rearWheelTrack/2;rightRearSpeed=speed-yawRate*c.rearWheelTrack/2;
    }
    public void SetRecordedPose(Vector3 position,float yaw,float actualSpeed,float angle)
    {
        root.SetPositionAndRotation(position,Quaternion.Euler(0,yaw,0));
        speed=actualSpeed;wheelAngle=angle;targetAngle=angle;UpdateWheelVisuals();
    }
    void UpdateWheelVisuals()
    {
        // Ackermann visual angles, rear wheel speeds from the same turning circle.
        float t=Mathf.Tan(wheelAngle*Mathf.Deg2Rad);
        if(Mathf.Abs(t)<.0001f){frontLeft.localRotation=Quaternion.identity;frontRight.localRotation=Quaternion.identity;}
        else
        {
            float r=c.wheelbase/t;
            frontLeft.localRotation=Quaternion.Euler(0,Mathf.Atan(c.wheelbase/(r+c.wheelTrack/2))*Mathf.Rad2Deg,0);
            frontRight.localRotation=Quaternion.Euler(0,Mathf.Atan(c.wheelbase/(r-c.wheelTrack/2))*Mathf.Rad2Deg,0);
        }
    }
    public float ServoFor(float angle) { return angle<0?(-angle/c.leftWheelLimit)*c.leftServoCommand:(angle/c.rightWheelLimit)*c.rightServoCommand; }
    public void Stop() { speed=0;throttle=0;targetAngle=0; }
}
