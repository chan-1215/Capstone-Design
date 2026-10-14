"""Flask monitor for the steering robot camera and OpenCV line diagnostics."""

import argparse
from collections import deque
import io
import threading
import time
import zipfile

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template_string, request, send_file

from camera_test import Camera
from road_vision import analyze, curve_direction


PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>도로 인식 모니터</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#101214;color:#f3f4f5;font:16px system-ui,sans-serif}
header{padding:14px 18px;background:#1b1f22;border-bottom:1px solid #353a3e;font-weight:700}
main{max-width:1200px;margin:auto;padding:16px;display:grid;grid-template-columns:minmax(0,2fr) minmax(260px,1fr);gap:16px}
.switch{display:flex;gap:4px;margin-bottom:8px}button{background:#353c40;color:white;border:0;padding:9px 16px;cursor:pointer}
button[aria-pressed=true]{background:#41714d}img{display:block;width:100%;aspect-ratio:4/3;object-fit:contain;background:#050505;border:1px solid #353a3e}
section{background:#1b1f22;border:1px solid #353a3e;padding:16px;border-radius:6px;align-self:start}
h2{font-size:16px;margin:0 0 14px}dl{display:grid;grid-template-columns:1fr auto;gap:12px;margin:0}dt{color:#abb4b9}dd{margin:0;font-variant-numeric:tabular-nums;text-align:right}
.manual{display:grid;grid-template-columns:repeat(3,64px);gap:8px;justify-content:center;margin-top:12px;touch-action:none}
.manual button{height:52px;padding:0;font-size:24px;border-radius:4px}.manual button[data-held=true]{background:#41714d}
.manual button[data-key=w]{grid-column:2}.manual button[data-key=a]{grid-column:1;grid-row:2}
.manual button[data-key=x]{grid-column:2;grid-row:2;background:#9d3535}.manual button[data-key=d]{grid-column:3;grid-row:2}
.manual button[data-key=s]{grid-column:2;grid-row:3}
.speed-control{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:center;margin-top:16px}
.speed-control input{width:100%;accent-color:#41714d}.speed-control output{min-width:3.2em;text-align:right;font-variant-numeric:tabular-nums}
@media(max-width:750px){main{grid-template-columns:1fr}}
</style>
<header>도로 인식 모니터</header><main><div><div class="switch">
<button id="processed" aria-pressed="true" onclick="selectView('processed')">OpenCV</button>
<button id="raw" aria-pressed="false" onclick="selectView('raw')">원본</button>
{% if gesture %}<button id="gesture" aria-pressed="false" onclick="selectView('gesture')">제스처</button>{% endif %}</div>
<img id="video" src="/stream/processed" alt="카메라 영상"></div>
<section><h2>카메라 인식</h2><dl>
<dt>카메라</dt><dd id="camera">대기</dd><dt>차선</dt><dd id="lane">-</dd>
<dt>검출 신뢰도</dt><dd id="confidence">-</dd><dt>도로 표면</dt><dd id="surface">-</dd>
<dt>근거리 도로</dt><dd id="nearSurface">-</dd>
<dt>도로 경계</dt><dd id="roadEdge">-</dd>
<dt>커브 방향</dt><dd id="curveDirection">-</dd>
<dt>중심 오차</dt><dd id="error">-</dd><dt>카메라</dt><dd id="captureFps">-</dd>
<dt>인식 처리</dt><dd id="fps">-</dd>
{% if gesture %}<dt>제스처</dt><dd id="gestureLabel">-</dd>{% endif %}
</dl>{% if drive %}<div style="margin-top:18px;border-top:1px solid #353a3e;padding-top:16px">
<h2>시험 주행</h2><dl><dt>상태</dt><dd id="driveState">정지</dd>
<dt>서보 목표각</dt><dd id="steering">0°</dd><dt>남은 시간</dt><dd id="remaining">0.0초</dd>
<dt>시작 요청</dt><dd id="startRequests">0회</dd></dl>
<div class="speed-control"><label for="speedInput">속도</label>
<input id="speedInput" type="range" min="0.18" max="0.30" step="0.01" value="0.22">
<output id="speedValue" for="speedInput">0.22</output></div>
<div class="speed-control"><label for="motor1Scale" title="GPIO 20·21">모터 1</label>
<input id="motor1Scale" type="range" min="0.80" max="1.20" step="0.01" value="1.00">
<output id="motor1Value" for="motor1Scale">1.00x</output></div>
<div class="speed-control"><label for="motor2Scale" title="GPIO 23·24">모터 2</label>
<input id="motor2Scale" type="range" min="0.80" max="1.20" step="0.01" value="1.00">
<output id="motor2Value" for="motor2Scale">1.00x</output></div>
<div style="display:flex;gap:8px;margin-top:16px"><button id="startDrive" onclick="sendDriveCommand('start')">주행 시작</button>
<button id="straightDrive" onclick="sendDriveCommand('straight')">직진 보정</button>
<button style="background:#9d3535" onclick="stopAll()">정지</button></div>
<h2 style="margin-top:20px">수동 조작</h2><div class="manual">
<button data-key="w" aria-label="전진" title="전진 (W)">↑</button>
<button data-key="a" aria-label="좌회전" title="좌회전 (A)">←</button>
<button data-key="x" aria-label="정지" title="정지 (Space)">■</button>
<button data-key="d" aria-label="우회전" title="우회전 (D)">→</button>
<button data-key="s" aria-label="후진" title="후진 (S)">↓</button>
</div></div>{% endif %}
</section></main><script>
function selectView(view){document.getElementById('video').src='/stream/'+view;
for(const id of ['processed','raw','gesture'])document.getElementById(id)?.setAttribute('aria-pressed',id===view)}
const speedInput=document.getElementById('speedInput');let speedEditing=false;
if(speedInput){speedInput.addEventListener('input',()=>{speedEditing=true;
document.getElementById('speedValue').textContent=Number(speedInput.value).toFixed(2)});
speedInput.addEventListener('change',async()=>{try{const r=await fetch('/drive/speed',{
method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({speed:Number(speedInput.value)})});
if(!r.ok){const s=await r.json();document.getElementById('driveState').textContent=s.error||'속도 변경 실패'}}
catch(e){document.getElementById('driveState').textContent='연결 끊김'}
finally{speedEditing=false;refresh()}})}
const motorInputs=[document.getElementById('motor1Scale'),document.getElementById('motor2Scale')];
let motorEditing=false;
if(motorInputs[0])for(const [index,input] of motorInputs.entries()){
input.addEventListener('input',()=>{motorEditing=true;
document.getElementById('motor'+(index+1)+'Value').textContent=Number(input.value).toFixed(2)+'x'});
input.addEventListener('change',async()=>{try{const r=await fetch('/drive/motor-scales',{
method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({motor1_scale:Number(motorInputs[0].value),motor2_scale:Number(motorInputs[1].value)})});
if(!r.ok){const s=await r.json();document.getElementById('driveState').textContent=s.error||'모터 속도 변경 실패'}}
catch(e){document.getElementById('driveState').textContent='연결 끊김'}
finally{motorEditing=false;refresh()}})}
async function refresh(){try{const r=await fetch('/status',{cache:'no-store'}),s=await r.json();
for(const k of ['camera','lane'])document.getElementById(k).textContent=s[k];
document.getElementById('roadEdge').textContent=s.road_edge||'-';
document.getElementById('curveDirection').textContent=s.curve_direction||'-';
document.getElementById('confidence').textContent=(s.confidence*100).toFixed(0)+'%';
document.getElementById('surface').textContent=(s.surface*100).toFixed(0)+'%';
document.getElementById('nearSurface').textContent=(s.near_surface*100).toFixed(0)+'%';
document.getElementById('error').textContent=s.center_error===null?'-':s.center_error.toFixed(1)+' px';
document.getElementById('captureFps').textContent=s.capture_fps.toFixed(1)+' FPS';
document.getElementById('fps').textContent=s.fps.toFixed(1)+' FPS';
const gestureLabel=document.getElementById('gestureLabel');
if(gestureLabel)gestureLabel.textContent=({stop:'정지',go:'출발',unknown:'미인식'})[s.gesture_label]||s.gesture_label||'-';
if(s.drive){document.getElementById('driveState').textContent=s.drive.state;
document.getElementById('steering').textContent=s.drive.servo_target.toFixed(0)+'°';
document.getElementById('remaining').textContent=s.drive.remaining.toFixed(1)+'초';
document.getElementById('startRequests').textContent=s.drive.auto_start_requests+'회';
if(!speedEditing){speedInput.value=s.drive.forward_speed.toFixed(2);
document.getElementById('speedValue').textContent=s.drive.forward_speed.toFixed(2)}
if(!motorEditing)for(const [index,input] of motorInputs.entries()){
const value=s.drive['motor'+(index+1)+'_scale'];input.value=value.toFixed(2);
document.getElementById('motor'+(index+1)+'Value').textContent=value.toFixed(2)+'x'}
document.getElementById('startDrive').disabled=s.drive.active;}
if(s.drive)document.getElementById('straightDrive').disabled=s.drive.active;
}catch(e){document.getElementById('camera').textContent='연결 끊김'}}
async function sendDriveCommand(action){const state=document.getElementById('driveState');
if(action==='start')state.textContent='시작 요청 중';
try{const r=await fetch('/drive/'+action,{method:'POST'});
if(!r.ok){const s=await r.json();state.textContent=s.error||'시작할 수 없음';return}
await refresh()}catch(e){state.textContent='연결 끊김'}}
const held=new Set();let manualPending=false,manualDirty=false;
function manualState(){return {throttle:Number(held.has('w'))-Number(held.has('s')),
steer:Number(held.has('d'))-Number(held.has('a'))}}
async function sendManual(){if(manualPending)return;manualPending=true;manualDirty=false;
try{const r=await fetch('/drive/manual',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify(manualState()),cache:'no-store'});
if(!r.ok){held.clear();const s=await r.json();document.getElementById('driveState').textContent=s.error||'수동 조작 불가'}}
catch(e){held.clear();document.getElementById('driveState').textContent='연결 끊김'}
finally{manualPending=false;if(manualDirty)sendManual()}}
function updateManual(){for(const b of document.querySelectorAll('.manual button[data-key]'))
b.dataset.held=held.has(b.dataset.key);manualDirty=true;sendManual()}
function stopAll(){held.clear();updateManual();sendDriveCommand('stop')}
for(const b of document.querySelectorAll('.manual button[data-key]')){
if(b.dataset.key==='x'){b.addEventListener('pointerdown',e=>{e.preventDefault();stopAll()});continue}
b.addEventListener('pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);held.add(b.dataset.key);updateManual()});
for(const ev of ['pointerup','pointercancel','lostpointercapture'])b.addEventListener(ev,()=>{held.delete(b.dataset.key);updateManual()})}
const keyMap={w:'w',s:'s',a:'a',d:'d',arrowup:'w',arrowdown:'s',arrowleft:'a',arrowright:'d'};
const manualEnabled=Boolean(document.querySelector('.manual'));
window.addEventListener('keydown',e=>{if(!manualEnabled)return;if(e.code==='Space'){e.preventDefault();stopAll();return}
const k=keyMap[e.key.toLowerCase()];if(k){e.preventDefault();if(!held.has(k)){held.add(k);updateManual()}}});
window.addEventListener('keyup',e=>{if(!manualEnabled)return;const k=keyMap[e.key.toLowerCase()];if(k){e.preventDefault();held.delete(k);updateManual()}});
window.addEventListener('blur',()=>{if(held.size){held.clear();updateManual()}});
setInterval(()=>{if(held.size)sendManual()},120);
refresh();setInterval(refresh,500);
</script></html>"""


MANUAL_ONLY_STYLE = "<style>#startDrive,#straightDrive{display:none}</style>"


class Monitor:
    def __init__(self, camera, enable_gesture=False):
        self.camera = camera
        self.lock = threading.Lock()
        self.updated = threading.Condition(self.lock)
        self.processed = None
        self.gesture_recognizer = None
        self.gesture_processed = None
        self.gesture_label = "unknown"
        self.gesture_error = None
        if enable_gesture:
            from gesture_recognition_module import GestureRecognizer
            self.gesture_recognizer = GestureRecognizer()
        self.last_reading = None
        self.last_frame_at = 0.0
        self.recording = False
        self.recorded_frames = deque(maxlen=100)
        self.status = dict(camera="대기", lane="-", confidence=0.0,
                           surface=0.0, near_surface=0.0, center_error=None, road_edge=None,
                           curve_direction=None, fps=0.0,
                           capture_fps=0.0)
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.gesture_thread = (threading.Thread(target=self._gesture_loop, daemon=True)
                               if self.gesture_recognizer is not None else None)

    def start(self):
        self.thread.start()
        if self.gesture_thread is not None:
            self.gesture_thread.start()

    def begin_capture(self):
        with self.lock:
            self.recorded_frames.clear()
            self.recording = True

    def end_capture(self):
        with self.lock:
            self.recording = False

    def capture(self):
        with self.lock:
            return list(self.recorded_frames)

    def _loop(self):
        previous = None
        last_time = time.monotonic()
        while self.running and self.camera.running:
            with self.camera.condition:
                self.camera.condition.wait_for(
                    lambda: self.camera.frame is not previous or not self.camera.running,
                    timeout=0.2)
                jpeg = self.camera.frame
            if jpeg is None or jpeg is previous:
                continue
            previous = jpeg
            frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            reading = analyze(frame)
            ok, encoded = cv2.imencode(".jpg", reading.overlay,
                                       [cv2.IMWRITE_JPEG_QUALITY, 80])
            now = time.monotonic()
            fps = 1.0 / max(now - last_time, 0.001)
            last_time = now
            with self.camera.condition:
                capture_fps = self.camera.capture_fps
            with self.updated:
                if ok:
                    self.processed = encoded.tobytes()
                self.last_reading = reading
                self.last_frame_at = now
                if self.recording:
                    self.recorded_frames.append((now, jpeg))
                self.status = dict(camera="온라인", lane=reading.lane,
                                   confidence=reading.confidence, surface=reading.surface,
                                   near_surface=reading.near_surface,
                                   center_error=reading.center_error,
                                   road_edge=reading.road_edge,
                                   curve_direction=curve_direction(reading), fps=fps,
                                   capture_fps=capture_fps)
                self.updated.notify_all()
        with self.lock:
            self.status["camera"] = "오프라인"

    def _gesture_loop(self):
        previous = None
        while self.running and self.camera.running:
            with self.camera.condition:
                self.camera.condition.wait_for(
                    lambda: self.camera.frame is not previous or not self.camera.running,
                    timeout=0.2)
                jpeg = self.camera.frame
            if jpeg is None or jpeg is previous:
                continue
            previous = jpeg
            frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            try:
                result = self.gesture_recognizer.process(frame)
                ok, encoded = cv2.imencode(".jpg", result["debug_frame"],
                                           [cv2.IMWRITE_JPEG_QUALITY, 80])
            except Exception as exc:
                with self.updated:
                    self.gesture_error = str(exc)
                    self.updated.notify_all()
                return
            with self.updated:
                if ok:
                    self.gesture_processed = encoded.tobytes()
                self.gesture_label = result["label"]
                self.updated.notify_all()
            time.sleep(1 / 15)

    def stop(self):
        self.running = False
        self.thread.join(timeout=2)
        if self.gesture_thread is not None:
            self.gesture_thread.join(timeout=2)
            if not self.gesture_thread.is_alive():
                self.gesture_recognizer.close()


def build_app(monitor, driver=None, manual_only=False):
    app = Flask(__name__)

    @app.get("/")
    def index():
        page = PAGE + (MANUAL_ONLY_STYLE if manual_only else "")
        return render_template_string(page, drive=driver is not None,
                                      gesture=getattr(monitor, "gesture_recognizer", None) is not None)

    @app.get("/status")
    def status():
        with monitor.lock:
            result = monitor.status.copy()
            if getattr(monitor, "gesture_recognizer", None) is not None:
                result["gesture_label"] = monitor.gesture_label
                result["gesture_error"] = monitor.gesture_error
        if driver is not None:
            result["drive"] = driver.status()
        return jsonify(result)

    if driver is not None:
        @app.get("/record/sample")
        def record_sample():
            with monitor.camera.condition:
                jpeg = monitor.camera.frame
                frame_at = monitor.camera.frame_at
            if jpeg is None or time.monotonic() - frame_at > 0.5:
                return ("Camera frame unavailable", 503)
            throttle, steer, age, valid = driver.manual_state_at(frame_at)
            response = Response(jpeg, mimetype="image/jpeg")
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Frame-Time"] = f"{frame_at:.6f}"
            response.headers["X-Throttle"] = str(throttle)
            response.headers["X-Steer"] = str(steer)
            response.headers["X-Command-Age"] = "" if age is None else f"{age:.6f}"
            response.headers["X-Manual-Valid"] = "1" if valid else "0"
            return response

        @app.post("/drive/start")
        def start_drive():
            if manual_only:
                return jsonify({"error": "Manual collection only"}), 403
            error = driver.start("auto")
            return (jsonify({"error": error}), 409) if error else jsonify({"ok": True})

        @app.post("/drive/speed")
        def set_drive_speed():
            data = request.get_json(silent=True) or {}
            error = driver.set_forward_speed(data.get("speed"))
            return (jsonify({"error": error}), 400) if error else jsonify({"ok": True})

        @app.post("/drive/motor-scales")
        def set_motor_scales():
            data = request.get_json(silent=True) or {}
            error = driver.set_motor_scales(data.get("motor1_scale"), data.get("motor2_scale"))
            return (jsonify({"error": error}), 400) if error else jsonify({"ok": True})

        @app.post("/drive/straight")
        def straight_drive():
            if manual_only:
                return jsonify({"error": "Manual collection only"}), 403
            error = driver.start("straight")
            return (jsonify({"error": error}), 409) if error else jsonify({"ok": True})

        @app.post("/drive/recover/<direction>")
        def recover_drive(direction):
            if manual_only:
                return jsonify({"error": "Manual collection only"}), 403
            error = driver.start(f"recover_{direction}")
            return (jsonify({"error": error}), 409) if error else jsonify({"ok": True})

        @app.post("/drive/manual")
        def manual_drive():
            data = request.get_json(silent=True) or {}
            error = driver.manual_command(data.get("throttle"), data.get("steer"))
            return (jsonify({"error": error}), 409) if error else jsonify({"ok": True})

        @app.post("/drive/stop")
        def stop_drive():
            driver.stop()
            return jsonify({"ok": True})

        @app.get("/drive/history")
        def drive_history():
            return jsonify(driver.history())

        @app.get("/drive/capture")
        def drive_capture():
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as output:
                for index, (timestamp, jpeg) in enumerate(monitor.capture()):
                    output.writestr(f"{index:03d}_{timestamp:.3f}.jpg", jpeg)
            archive.seek(0)
            return send_file(archive, mimetype="application/zip", as_attachment=True,
                             download_name="drive_capture.zip")

    @app.get("/stream/<view>")
    def stream(view):
        if view not in {"raw", "processed", "gesture"} or (
                view == "gesture" and getattr(monitor, "gesture_recognizer", None) is None):
            return ("Not found", 404)

        def frames():
            previous = None
            next_send = 0.0
            while monitor.running and monitor.camera.running:
                if view == "raw":
                    condition = monitor.camera.condition
                    with condition:
                        condition.wait_for(
                            lambda: monitor.camera.frame is not previous or not monitor.camera.running,
                            timeout=1)
                        jpeg = monitor.camera.frame
                elif view == "processed":
                    condition = monitor.updated
                    with condition:
                        condition.wait_for(
                            lambda: monitor.processed is not previous or not monitor.running,
                            timeout=1)
                        jpeg = monitor.processed
                else:
                    condition = monitor.updated
                    with condition:
                        condition.wait_for(
                            lambda: monitor.gesture_processed is not previous or not monitor.running,
                            timeout=1)
                        jpeg = monitor.gesture_processed
                if jpeg is None or jpeg is previous:
                    continue
                previous = jpeg
                now = time.monotonic()
                if now < next_send:
                    time.sleep(next_send - now)
                next_send = time.monotonic() + 0.05
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")

        return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame",
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

    return app


def main():
    parser = argparse.ArgumentParser(description="Camera-only road recognition monitor")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--rotate", dest="rotate", action="store_true", default=True)
    parser.add_argument("--no-rotate", dest="rotate", action="store_false")
    parser.add_argument("--gesture", action="store_true",
                        help="Show gesture recognition without controlling the motors")
    args = parser.parse_args()
    camera = Camera("csi", 0, args.width, args.height, args.fps, args.rotate)
    monitor = Monitor(camera, enable_gesture=args.gesture)
    try:
        camera.start()
        deadline = time.monotonic() + 8
        while camera.frame is None and camera.error is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if camera.frame is None:
            raise RuntimeError(camera.error or "No camera frame received within 8 seconds")
        monitor.start()
        print(f"Road monitor: http://<pi-ip>:{args.port}/ (motors disabled)", flush=True)
        build_app(monitor).run(host="0.0.0.0", port=args.port, debug=False,
                               use_reloader=False, threaded=True)
    finally:
        monitor.running = False
        camera.stop()
        if monitor.thread.is_alive():
            monitor.stop()


if __name__ == "__main__":
    main()
