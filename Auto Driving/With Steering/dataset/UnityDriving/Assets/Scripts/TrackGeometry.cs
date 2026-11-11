using System;
using System.Collections.Generic;
using UnityEngine;

// Approximation of the user's photographed notched, two-lane loop.
// World XZ plane; lane 0 and lane 1 each have a dashed WHITE centre.
public class TrackGeometry
{
    public readonly List<Vector3> points = new List<Vector3>();
    public float length;
    public float width;
    public Transform root;
    readonly List<float> distance = new List<float>();
    public TrackGeometry(Transform parent, DrivingConfig cfg)
    {
        width=cfg.roadWidth;
        root=new GameObject("PhotographedTrack_Approximation").transform;
        root.SetParent(parent,false);
        Vector2[] k = {
            new Vector2(-.45f,-1.22f),new Vector2(.35f,-1.22f),new Vector2(.81f,-1.18f),
            new Vector2(.99f,-.91f),new Vector2(.93f,-.53f),new Vector2(.77f,-.25f),
            new Vector2(.42f,-.17f),new Vector2(.05f,-.16f),new Vector2(-.15f,.04f),
            new Vector2(-.16f,.32f),new Vector2(.02f,.54f),new Vector2(.42f,.60f),
            new Vector2(.67f,.78f),new Vector2(.67f,1.04f),new Vector2(.42f,1.18f),
            new Vector2(-.25f,1.18f),new Vector2(-.77f,1.11f),new Vector2(-.95f,.81f),
            new Vector2(-.97f,.25f),new Vector2(-.97f,-.42f),new Vector2(-.92f,-1.02f)
        };
        for(int j=0;j<k.Length;j++) for(int n=0;n<30;n++)
        {
            float t=n/30f;
            Vector2 a=k[(j+k.Length-1)%k.Length],b=k[j],c=k[(j+1)%k.Length],d=k[(j+2)%k.Length];
            Vector2 p=.5f*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t);
            points.Add(new Vector3(p.x*cfg.trackScale,0,p.y*cfg.trackScale));
        }
        for(int j=0;j<points.Count;j++) { distance.Add(length); length+=Vector3.Distance(points[j],points[(j+1)%points.Count]); }
        Ribbon("Black road",0,width,0.002f,new Color(.025f,.027f,.03f));
        Ribbon("Yellow outer boundary L",-width/2,.013f,.004f,new Color(1,.81f,.02f));
        Ribbon("Yellow outer boundary R",width/2,.013f,.004f,new Color(1,.81f,.02f));
        Ribbon("Yellow lane divider",0,.012f,.004f,new Color(1,.81f,.02f));
        for(int lane=0;lane<2;lane++)
            for(float s=0;s<length;s+=.15f) Segment("White dash",s,s+.075f,LaneOffset(lane),.012f,.005f,Color.white);
        // Across a straight portion, not a part of the longitudinal centre-line labels.
        float cross=Station(Nearest(new Vector3(-.97f*cfg.trackScale,0,-.35f*cfg.trackScale)))-.2f;
        for(int i=0;i<7;i++) Segment("Crosswalk stripe",cross+i*.065f,cross+.03f+i*.065f,0,width*.88f,.006f,Color.white);
    }
    public float LaneOffset(int lane) { return lane==0?-width*.25f:width*.25f; }
    public Vector3 Tangent(int i) { return (points[(i+1)%points.Count]-points[(i+points.Count-1)%points.Count]).normalized; }
    public Vector3 Right(int i) { return Vector3.Cross(Vector3.up,Tangent(i)).normalized; }
    public Vector3 At(float s,float offset=0)
    {
        s=Mathf.Repeat(s,length); int i=distance.BinarySearch(s); if(i<0)i=~i-1; i=Mathf.Max(0,i);
        int next=(i+1)%points.Count;
        float span=Vector3.Distance(points[i],points[next]);
        float f=span>0?(s-distance[i])/span:0;
        return Vector3.Lerp(points[i],points[next],f)+Vector3.Lerp(Right(i),Right(next),f).normalized*offset;
    }
    public int Nearest(Vector3 p)
    {
        p.y=0; float best=float.MaxValue;int index=0;
        for(int i=0;i<points.Count;i++){float d=(points[i]-p).sqrMagnitude;if(d<best){best=d;index=i;}}
        return index;
    }
    public float Station(int i) { return distance[i]; }
    public float SignedOffset(Vector3 p,int i) { return Vector3.Dot(p-points[i],Right(i)); }
    public float Curvature(int i)
    {
        int a=(i+points.Count-4)%points.Count,b=(i+4)%points.Count;
        return Vector3.SignedAngle(Tangent(a),Tangent(b),Vector3.up)*Mathf.Deg2Rad/Mathf.Max(.001f,Vector3.Distance(points[a],points[b]));
    }
    public static Material Mat(Color color)
    {
        Material m=new Material(Shader.Find("Standard"));m.color=color;m.SetFloat("_Glossiness",.12f);return m;
    }
    void Ribbon(string name,float offset,float breadth,float y,Color color)
    {
        var v=new Vector3[(points.Count+1)*2];var uv=new Vector2[v.Length];var triangles=new int[points.Count*6];
        for(int j=0;j<=points.Count;j++)
        {
            int i=j%points.Count;var r=Right(i);
            v[j*2]=points[i]+r*(offset-breadth/2)+Vector3.up*y;
            v[j*2+1]=points[i]+r*(offset+breadth/2)+Vector3.up*y;
            uv[j*2]=new Vector2(0,j*.02f);uv[j*2+1]=new Vector2(1,j*.02f);
            if(j<points.Count){int z=j*6,q=j*2;triangles[z]=q;triangles[z+1]=q+2;triangles[z+2]=q+1;triangles[z+3]=q+1;triangles[z+4]=q+2;triangles[z+5]=q+3;}
        }
        Mesh mesh=new Mesh();mesh.vertices=v;mesh.uv=uv;mesh.triangles=triangles;mesh.RecalculateNormals();
        GameObject go=new GameObject(name);go.transform.SetParent(root,false);go.AddComponent<MeshFilter>().sharedMesh=mesh;
        go.AddComponent<MeshRenderer>().sharedMaterial=Mat(color);
    }
    void Segment(string name,float s0,float s1,float offset,float breadth,float y,Color color)
    {
        Vector3 a=At(s0,offset),b=At(s1,offset),r=Vector3.Cross(Vector3.up,(b-a).normalized)*breadth/2;
        Mesh mesh=new Mesh();mesh.vertices=new[]{a-r+Vector3.up*y,a+r+Vector3.up*y,b-r+Vector3.up*y,b+r+Vector3.up*y};
        mesh.triangles=new[]{0,2,1,1,2,3};mesh.RecalculateNormals();
        GameObject go=new GameObject(name);go.transform.SetParent(root,false);go.AddComponent<MeshFilter>().sharedMesh=mesh;
        go.AddComponent<MeshRenderer>().sharedMaterial=Mat(color);
    }
}
