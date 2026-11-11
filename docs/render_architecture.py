"""Render README architecture diagrams with Korean fonts; no external assets."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
S=2
BG='#0d1117'; PANEL='#121923'; LINE='#273449'; WHITE='#edf3fb'; MUTED='#a4b2c6'
BLUE='#79a7ff'; TEAL='#49d2c5'; PURPLE='#bc9afa'; AMBER='#f3bc67'; GREEN='#94d378'; RED='#f58b93'
FONT=Path('C:/Windows/Fonts/malgun.ttf');BOLD=Path('C:/Windows/Fonts/malgunbd.ttf')

class Diagram:
    def __init__(self,height):
        self.im=Image.new('RGB',(1440*S,height*S),BG);self.d=ImageDraw.Draw(self.im)
        for x in range(20,1440,24):
            for y in range(100,height-40,24):self.d.ellipse((x*S,y*S,x*S+2,y*S+2),fill='#202937')
    def text(self,x,y,t,size=22,fill=WHITE,bold=False,anchor=None):
        font=ImageFont.truetype(str(BOLD if bold else FONT),size*S)
        self.d.text((x*S,y*S),t,font=font,fill=fill,anchor=anchor)
    def box(self,x,y,w,h,fill=PANEL,outline=LINE,r=16):
        self.d.rounded_rectangle((x*S,y*S,(x+w)*S,(y+h)*S),r*S,fill=fill,outline=outline,width=2*S)
    def group(self,x,y,w,h,label,color=BLUE):
        self.box(x,y,w,h,outline=LINE,r=22)
        # Dashes preserve the visual distinction between a host and a module.
        for a in range(x+20,x+w-20,24):
            self.d.line((a*S,y*S,min(a+12,x+w-20)*S,y*S),fill=color,width=2*S)
            self.d.line((a*S,(y+h)*S,min(a+12,x+w-20)*S,(y+h)*S),fill=color,width=2*S)
        for a in range(y+20,y+h-20,24):
            self.d.line((x*S,a*S,x*S,min(a+12,y+h-20)*S),fill=color,width=2*S)
            self.d.line(((x+w)*S,a*S,(x+w)*S,min(a+12,y+h-20)*S),fill=color,width=2*S)
        self.text(x+20,y-32,label,24,color,True)
    def node(self,x,y,title,body,color=TEAL,w=230,h=135,tag=''):
        self.box(x,y,w,h,outline=color)
        self.box(x+14,y+14,34,32,fill=BG,outline=color,r=8)
        def fit(t,size,width,bold=False):
            while size>10 and ImageFont.truetype(str(BOLD if bold else FONT),size*S).getlength(t)>width*S:size-=1
            return size
        self.text(x+31,y+28,tag or '·',fit(tag or '·',16,28,True),color,True,anchor='mm')
        self.text(x+60,y+17,title,fit(title,23,w-72,True),WHITE,True)
        for n,line in enumerate(body):self.text(x+16,y+58+n*27,line,fit(line,21,w-32),MUTED)
    def arrow(self,points,color=TEAL,label=None,labelxy=None):
        p=[(x*S,y*S) for x,y in points];self.d.line(p,fill=color,width=2*S,joint='curve')
        x,y=p[-1];a,b=p[-2];dx,dy=x-a,y-b;l=(dx*dx+dy*dy)**.5;ux,uy=dx/l,dy/l
        self.d.polygon([(x,y),(x-ux*10*S+uy*4*S,y-uy*10*S-ux*4*S),(x-ux*10*S-uy*4*S,y-uy*10*S+ux*4*S)],fill=color)
        if label:
            tx,ty=labelxy;f=ImageFont.truetype(str(FONT),19*S);b=self.d.textbbox((0,0),label,font=f);w=(b[2]-b[0])/S+18
            self.box(tx-w/2,ty-14,w,29,fill=BG,outline=LINE,r=10);self.text(tx,ty,label,19,WHITE,anchor='mm')
    def save(self,name):
        path=ROOT/'images'/name;path.parent.mkdir(exist_ok=True);self.im.save(path,optimize=True)

def robot():
    d=Diagram(1040)
    d.text(32,24,'실물 로봇 · 인식에서 주행과 응답까지',34,bold=True)
    d.text(32,70,'색상은 기능 구분 · 실물 기본 주행은 OpenCV 경로 추종',21,MUTED)
    d.group(240,148,895,790,'Raspberry Pi · Python / Flask 서버')
    d.node(25,205,'Pi 카메라',['실시간 RGB 영상','Picamera2 / rpicam'],BLUE,w=185,tag='IN')
    d.node(270,205,'영상 수신',['최신 프레임 관리','camera_source'],BLUE,tag='01')
    d.node(560,205,'도로·경로 인식',['OpenCV · NumPy','경계·점선 → 경로'],TEAL,tag='02')
    d.node(850,205,'자율 제어',['위치·방향 오차','조향각·속도 계산'],AMBER,tag='03')
    d.node(270,465,'손 관절 추출',['MediaPipe · 21관절','영상에서 손 추적'],PURPLE,tag='02')
    d.node(560,465,'손동작 분류',['정규화 · 30프레임','KNN → GO / STOP'],PURPLE,tag='03')
    d.node(850,465,'횡단보도 연동',['접근 → 정차·대기','최신 판정·경로 확인'],AMBER,tag='04')
    d.node(560,725,'횡단보도 검출',['흰 줄무늬 분석','접근·정차 조건'],TEAL,tag='02')
    d.node(850,765,'출력 검사·GPIO',['입력 신선도·한계','GPIO Zero · lgpio'],GREEN,tag='05')
    d.node(1190,205,'웹 조작 화면',['Flask · 수동/자율','영상·설정·정지'],RED,w=225,tag='UI')
    d.node(1190,465,'웹 디스플레이',['차량 GO → 빨강','차량 STOP → 초록'],PURPLE,w=225,tag='GIF')
    d.node(1190,765,'모터·조향장치',['앞바퀴 서보 조향','좌우 DC 모터'],GREEN,w=225,tag='OUT')
    d.arrow([(210,272),(270,272)],BLUE)
    d.arrow([(500,272),(560,272)],TEAL)
    d.arrow([(790,272),(850,272)],TEAL,'경로·오차',(820,249))
    d.arrow([(385,340),(385,465)],PURPLE,'RGB 프레임',(385,407))
    d.arrow([(500,532),(560,532)],PURPLE)
    d.arrow([(790,532),(850,532)],PURPLE,'최신 판정',(820,509))
    d.arrow([(965,465),(965,340)],AMBER,'대기 / 출발 허가',(965,404))
    d.arrow([(285,340),(255,340),(255,792),(560,792)],TEAL,'동일 프레임',(400,792))
    d.arrow([(790,792),(817,792),(817,621),(965,621),(965,600)],TEAL,'횡단보도 상태',(940,622))
    d.arrow([(1080,272),(1114,272),(1114,832),(1080,832)],AMBER,'목표 명령',(1114,695))
    d.arrow([(1080,832),(1190,832)],GREEN,'제한된 출력',(1144,809))
    d.arrow([(790,500),(821,500),(821,389),(1165,389),(1165,532),(1190,532)],PURPLE,'표시용 판정',(1088,389))
    d.arrow([(385,205),(385,173),(1302,173),(1302,205)],BLUE,'영상 스트림 · 인식 상태',(1004,174))
    d.arrow([(1190,300),(1150,300),(1150,913),(965,913),(965,900)],RED,'수동·정지 명령',(1280,913))
    d.text(32,970,'선택 기능: 횡단보도·제스처 연동은 별도 활성화  |  표시용 GO와 실제 출발 허가는 분리',22,MUTED)
    d.text(32,1005,'PC의 YOLO 사람 윤곽 검출은 별도 실험이며, 위 기본 Pi 처리에는 항상 포함되지 않습니다.',20,MUTED)
    d.save('architecture-robot.png')

def learning():
    d=Diagram(910)
    d.text(32,24,'가상 환경 · 카메라 데이터 생성과 학습',34,bold=True)
    d.text(32,72,'실물 제어와 분리된 PC 실험 · 두 차량 구조에 맞는 정답을 각각 생성',22,MUTED)
    d.group(30,154,1380,610,'PC · 시뮬레이터 + Python 학습 도구')
    xs=[60,335,610,885,1160];w=220
    for y,color,label,sub,data,prep,model,out in [
        (215,BLUE,'Webots','사륜 · 좌우 출력','9,000장 선별','회색조 · 32×18','릿지 회귀','좌우 PWM'),
        (505,TEAL,'Unity','앞바퀴 조향','현재 시야 2,377장','색 분포 · 12×8×3','MLP','조향각·목표 속도')]:
        d.node(xs[0],y,label,[sub,'가상 카메라·교사'],color,w,155,'SIM')
        d.node(xs[1],y,'영상 + 정답',[data,'CSV · 출처·조건'],color,w,155,'DATA')
        d.node(xs[2],y,'학습 입력 준비',[prep,'분할·정규화·증강'],PURPLE,w,155,'PRE')
        d.node(xs[3],y,model,[out,'카메라 → 예측'],PURPLE,w,155,'AI')
        d.node(xs[4],y,'가상 주행 평가',['경로 이탈·오차','연속 주행 확인'],GREEN,w,155,'TEST')
        for n in range(4):d.arrow([(xs[n]+w,y+78),(xs[n+1],y+78)],color)
        d.text(60,y+175,'교사는 가상 위치·경로로 정답 생성  /  학습 모델은 카메라 영상으로 예측',21,MUTED)
    d.text(45,796,'Unity: 학습 모델이 조향·속도 결정 · OpenCV는 별도 인식 표시',22,TEAL)
    d.text(45,835,'Webots 최종 평가: 영상 오차 보정 결합  |  실물 이식에는 별도 보정·검증 필요',22,MUTED)
    d.save('architecture-learning.png')

if __name__=='__main__':robot();learning()
