"""Compare existing perception and experimental Hough on saved RAW inputs only."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import platform
import statistics
import time

import cv2
import numpy as np

from analyze_photos import read_image, write_image
from hough_vision import HoughConfig, TEXTBOOK_ROI, analyze_hough, overlay_hough
from lane_path import draw_path
from replay_path import predict_still, validate_reference
from track_vision import VisionConfig, analyze, overlay


def raw_input(path):
    path = Path(path).resolve()
    if (not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".mp4", ".avi")
            or not (path.stem.lower() == "raw" or path.stem.lower().endswith("_raw"))):
        raise ValueError("Use existing *_raw.png/jpg/mp4 camera files, not processed/screen recordings")
    return path


def file_sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def frames(path, sample_seconds, max_frames):
    if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
        yield 0, None, read_image(path)
        return
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot decode video: {path}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not np.isfinite(fps) or fps <= 0:
            raise ValueError("Video has no valid FPS; a timestamped raw recording is required")
        step = max(1, round(sample_seconds*fps))
        index, emitted = 0, 0
        while emitted < max_frames:
            available = capture.grab()
            if not available:
                break
            if index % step == 0:
                ok, frame = capture.retrieve()
                if not ok or frame is None:
                    raise ValueError(f"Cannot decode frame {index} from {path}")
                yield index, index/fps, frame
                emitted += 1
            index += 1
        if emitted == 0:
            raise ValueError(f"Video has no decoded frames: {path}")
    finally:
        capture.release()


def benchmark(function, repeats):
    function()  # Warm-up is excluded; image decode/render/report IO are outside timing.
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        result = function()
        samples.append((time.perf_counter()-start)*1000)
    return result, {"median_ms": statistics.median(samples),
                    "min_ms": min(samples), "max_ms": max(samples), "repeats": repeats}


def current_prediction(frame, config, reference, heading, lap, joint):
    result = analyze(frame, config)
    prediction = predict_still(result, reference, heading, lap, joint)
    return result, prediction


def tile(image, title, subtitle, width=480):
    canvas = np.full((420, width, 3), (28, 32, 34), np.uint8)
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    ratio = min(width/image.shape[1], 340/image.shape[0])
    preview = cv2.resize(image, (round(image.shape[1]*ratio), round(image.shape[0]*ratio)))
    x, y = (width-preview.shape[1])//2, 76+(340-preview.shape[0])//2
    canvas[y:y+preview.shape[0], x:x+preview.shape[1]] = preview
    cv2.putText(canvas, title, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, .58, (245, 245, 245), 1, cv2.LINE_AA)
    cv2.putText(canvas, subtitle, (12, 53), cv2.FONT_HERSHEY_SIMPLEX, .42, (195, 204, 205), 1, cv2.LINE_AA)
    return canvas


STAGE_LABELS = {
    "colour": "1. 색상 추출",
    "blur": "2. 가우시안 블러",
    "edges": "3. 캐니 윤곽선",
    "roi": "4. 관심 영역",
    "transformed": "5. 허프 검출 입력",
}

REASON_LABELS = {
    "two_sides": "화면 좌우 선분 검출",
    "left_only": "화면 왼쪽 선분만 검출",
    "right_only": "화면 오른쪽 선분만 검출",
    "unassigned_segments": "좌우로 나누기 어려운 선분",
    "no_segments": "선분 미검출",
    "central_dash_chain": "흰 점선 중심 연결",
    "single_dash_corroborated": "단일 점선과 주변 경계 확인",
    "near_centres_corroborated": "가까운 점선 중심과 경계 확인",
    "dash_boundary_corroborated": "점선과 노란 경계 함께 확인",
    "insufficient_dashes": "점선 후보 부족",
    "ambiguous_dash_chain": "점선 연결 경로가 모호함",
    "dash_association_failed": "점선 연결 실패",
    "insufficient_dash_span": "점선 관측 범위 부족",
    "inconsistent_dash_chain": "점선 연결 방향 불일치",
    "single_dash_uncorroborated": "단일 점선을 뒷받침할 경계 부족",
    "two_dashes_uncorroborated": "두 점선을 뒷받침할 경계 부족",
    "target_outside_observed_path": "목표점이 관측 경로 밖에 있음",
    "target_outside_image": "목표점이 화면 밖에 있음",
    "path_jump": "경로 위치가 급격히 변함",
    "partial_paint_uncorroborated": "일부만 보이는 표시의 경계 확인 부족",
}


def reason_label(reason):
    return REASON_LABELS.get(reason, "추가 확인 필요")


def profile_label(config):
    blur = config["blur_size"]
    smoothing = "블러 없음" if not blur else f"블러 {blur} × {blur}"
    return f"긴 변 {config['max_side']}픽셀 · {smoothing}"


def stage_filename(prefix, name, stage):
    return f"{prefix}_{name}_stage_{stage}.png"


def write_stage_previews(output, prefix, name, masks):
    # Browser captions support Korean without adding a font dependency on the Pi.
    for stage, mask in masks.items():
        write_image(output/stage_filename(prefix, name, stage), mask)


def html_report(records, summary):
    baseline = records[0]["current"]["config"]
    experiment = records[0]["candidates"][0]["config"]
    colour = {"yellow": "노란색", "white": "흰색", "both": "노란색과 흰색"}[experiment["colour"]]
    perspective = "사용" if experiment["bird_eye"] else "사용 안 함"
    sections = []
    for number, record in enumerate(records, 1):
        prefix = record["prefix"]
        rows, previews, stages = [], [], []
        for candidate in record["candidates"]:
            metrics = candidate["metrics"]
            error = metrics["error_px"]
            label = escape(profile_label(candidate["config"]))
            observation = reason_label(metrics["reason"])
            rows.append(f"<tr><td>{label}</td><td>{metrics['segment_count']}</td>"
                        f"<td>{observation}</td><td>{'계산 불가' if error is None else f'{error:.1f}'}</td>"
                        f"<td>{candidate['timing']['median_ms']:.2f}</td></tr>")
            previews.append(f'<figure><figcaption>{label}<small>{observation}</small></figcaption>'
                            f'<img loading="lazy" src="{escape(candidate["preview"], quote=True)}" '
                            f'alt="새 방식 검출 결과: {label}"></figure>')
            stage_images = "".join(
                f'<figure><figcaption>{title}</figcaption><img loading="lazy" '
                f'src="{escape(stage_filename(prefix, candidate["name"], stage), quote=True)}" '
                f'alt="{title}"></figure>' for stage, title in STAGE_LABELS.items())
            stages.append(f'<h3>{label}</h3><div class="stage-grid">{stage_images}</div>')
        prediction = record["current"]["prediction"]
        reference = "설정됨" if prediction.get("reference_set") else "설정 안 됨"
        sections.append(f"""<section><h2>사진 {number} · 원본 프레임 {record['frame_index']}</h2>
<p class="source">원본 파일: {escape(record['source_name'])}</p>
<div class="preview-grid">
<figure><figcaption>카메라 원본</figcaption><img loading="lazy" src="{escape(prefix)}_raw.png" alt="인식 표시 전 카메라 원본"></figure>
<figure><figcaption>기존 방식 · 흰 점선 경로<small>{reason_label(prediction['reason'])}</small></figcaption>
<img loading="lazy" src="{escape(prefix)}_current.png" alt="기존 방식의 흰 점선 경로 검출 결과"></figure></div>
<p>기존 방식 처리 시간: {record['current']['timing']['median_ms']:.2f}밀리초 · 중앙 기준: {reference}</p>
<h3>새 방식 · 색상 추출 → 블러 → 캐니 → 허프</h3>
<div class="preview-grid">{''.join(previews)}</div>
<div class="table-scroll"><table><thead><tr><th>비교 설정</th><th>선분 수</th><th>검출 상태</th><th>중심 오차<br>(픽셀)</th><th>처리 시간 중앙값<br>(밀리초)</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</div><details><summary>단계별 처리 결과</summary>{''.join(stages)}
</details></section>""")
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>도로 인식 방식 비교</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#101415;color:#edf0f1;font:15px/1.5 system-ui,sans-serif;letter-spacing:0}}
header,main{{max-width:1480px;margin:auto;padding:20px}}header{{border-bottom:1px solid #42494c}}h1{{font-size:24px;margin:0}}
h2{{font-size:19px;overflow-wrap:anywhere}}h3{{font-size:16px}}p{{color:#bcc8cc}}section{{padding:8px 0 24px;border-bottom:1px solid #42494c}}
img{{display:block;width:100%;height:auto;aspect-ratio:4/3;object-fit:contain;background:#000}}
.preview-grid,.stage-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
.stage-grid{{grid-template-columns:repeat(3,minmax(0,1fr))}}figure{{min-width:0;margin:0 0 16px}}
figcaption{{min-height:3.8em;padding:8px 0;overflow-wrap:anywhere}}small{{display:block;color:#bcc8cc}}
summary{{cursor:pointer;padding:12px 0}}.source{{overflow-wrap:anywhere;font-size:13px}}.table-scroll{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:8px;text-align:left;border-bottom:1px solid #42494c;overflow-wrap:anywhere}}
@media(max-width:700px){{header,main{{padding:12px}}.preview-grid,.stage-grid{{grid-template-columns:1fr}}
th,td{{padding:6px;font-size:12px}}table{{min-width:520px}}}}
</style><header><h1>도로 인식 방식 비교</h1><p>저장된 원본 {summary['frames']}장 비교 · 실시간 영상 아님 · 모터 제어 없음</p>
<p>기존 방식: 긴 변 {baseline['max_side']}픽셀 · 공통 상단 제외 비율: {baseline['roi_top']:.0%}<br>
새 방식 추출 색상: {colour} · 위에서 내려다보는 투시 변환: {perspective}</p>
<details><summary>결과 해석 시 주의점</summary>
<p>기존 방식은 흰 점선의 경로를 확인하고, 새 방식은 선택한 색상의 선분을 화면 좌우로 묶습니다.
노란 경계의 중간점과 흰 점선 경로는 서로 다른 기준입니다. 검출 개수는 정확도가 아닙니다.</p>
<p>처리 시간은 각 인식 계산만 측정한 값으로, 화면 그리기와 파일 저장은 제외됩니다.
카메라 프레임 수나 전체 영상 지연을 나타내지 않습니다. 실제 카메라의 투시 변환 보정은 검증되지 않았습니다.</p>
</details></header><main>
<p>새 방식 표시: 분홍색 = 검출 선분 · 노란색 = 화면 좌우 선분의 평균 위치 · 초록색 = 두 평균의 중간점 · 파란색 = 화면 중앙</p>
<p>하나의 굽은 경계도 화면 좌우에 동시에 잡힐 수 있습니다. 좌우 선분 검출이나 초록색 중간선만으로 주행 가능한 경로라고 판단할 수 없습니다.</p>
{''.join(sections)}</main></html>"""


def compare(paths, output, *, sizes=(480, 320), blurs=(0, 3, 5), roi_top=.20,
            colour="yellow", polygon=None, bird_eye=False, reference=None, heading=0.,
            lap=False, joint=False, repeats=3, sample_seconds=.5, max_frames=40):
    validate_reference(reference, heading)
    if joint and not lap:
        raise ValueError("Joint guidance requires lap mode")
    if (type(repeats) is not int or repeats < 1 or repeats > 20
            or type(max_frames) is not int or not 1 <= max_frames <= 500
            or not np.isfinite(sample_seconds) or sample_seconds <= 0):
        raise ValueError("Invalid repeat count, frame limit or sampling interval")
    if not sizes or not blurs or len(set(sizes)) != len(sizes) or len(set(blurs)) != len(blurs):
        raise ValueError("Provide nonempty unique size and blur lists")
    paths = [raw_input(path) for path in paths]
    if not paths:
        raise ValueError("At least one raw input is required")
    options = dict(roi_top=roi_top, colour=colour, bird_eye=bird_eye)
    if polygon is not None:
        options["polygon"] = polygon
    configs = [HoughConfig(max_side=size, blur_size=blur, **options) for size in sizes for blur in blurs]
    # Use the selected baseline resolution, regardless of candidate ordering.
    baseline_config = VisionConfig(max_side=max(sizes), roi_top=roi_top)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output directory already exists; use a new directory to preserve prior reports")
    if any(path.is_relative_to(output) for path in paths):
        raise ValueError("Output must not contain input material")
    output.mkdir(parents=True)
    records = []
    for path in paths:
        source_hash = file_sha256(path)
        for index, timestamp, frame in frames(path, sample_seconds, max_frames):
            prefix = f"frame_{len(records):04d}"
            current, current_timing = benchmark(
                lambda: current_prediction(frame, baseline_config, reference, heading, lap, joint), repeats)
            current_result, prediction = current
            current_view = overlay(current_result, lines_only=True)
            draw_path(current_view, prediction)
            write_image(output/f"{prefix}_raw.png", frame)
            write_image(output/f"{prefix}_current.png", current_view)
            candidates = []
            panels = [tile(frame, "RAW CAMERA", f"{path.suffix} / frame {index}"),
                      tile(current_view, "CURRENT / WHITE DASH PATH", prediction["reason"])]
            for config in configs:
                name = f"hough_{config.max_side}_blur{config.blur_size}"
                result, timing = benchmark(lambda: analyze_hough(frame, config), repeats)
                candidate_view = overlay_hough(result)
                preview = f"{prefix}_{name}.png"
                stages = f"{prefix}_{name}_stages.png"
                write_image(output/preview, candidate_view)
                write_stage_previews(output, prefix, name, result.masks)
                stage_tiles = [tile(mask, label.upper(), name, width=320)
                               for label, mask in result.masks.items()]
                write_image(output/stages, np.hstack(stage_tiles))
                panels.append(tile(candidate_view, name.upper(),
                                   f"{result.metrics['reason']} / {timing['median_ms']:.2f} ms"))
                candidates.append(dict(name=name, config=asdict(config), metrics=result.metrics,
                                       timing=timing, preview=preview, stages=stages))
            columns = 2
            if len(panels) % columns:
                panels.append(np.full_like(panels[0], (28, 32, 34)))
            sheet = np.vstack([np.hstack(panels[n:n+columns]) for n in range(0, len(panels), columns)])
            write_image(output/f"{prefix}_comparison.png", sheet)
            records.append(dict(prefix=prefix, source=str(path), source_name=path.name,
                                source_sha256=source_hash, frame_index=index, timestamp=timestamp,
                                decoded_bgr_sha256=hashlib.sha256(frame.tobytes()).hexdigest(),
                                current=dict(config=asdict(baseline_config), timing=current_timing,
                                             prediction=prediction, metrics=current_result.metrics),
                                candidates=candidates))
    profile_summary = {}
    for profile in records[0]["candidates"]:
        candidates = [c for record in records for c in record["candidates"]
                      if c["name"] == profile["name"]]
        profile_summary[profile["name"]] = dict(
            two_sided_observations=sum(c["metrics"]["two_sided_observation"] for c in candidates),
            median_processing_ms=statistics.median(c["timing"]["median_ms"] for c in candidates))
    summary = dict(frames=len(records), profiles=len(configs),
                   current_path_observations=sum(r["current"]["prediction"]["valid"] for r in records),
                   hough=profile_summary)
    directory = Path(__file__).resolve().parent
    report = dict(kind="offline_independent_frame_comparison", created=datetime.now(timezone.utc).isoformat(),
                  hardware_access=False, physical_calibration_verified=False,
                  environment=dict(platform=platform.platform(), python=platform.python_version(),
                                   opencv=cv2.__version__, numpy=np.__version__,
                                   opencv_threads=cv2.getNumThreads()),
                  source_hashes={name: file_sha256(directory/name)
                                 for name in ("hough_vision.py", "compare_vision.py", "track_vision.py",
                                              "lane_path.py", "boundary_guidance.py", "replay_path.py")},
                  reference_assumption=reference, heading_assumption=heading, lap_mode=lap, joint_guidance=joint,
                  summary=summary, records=records,
                  limitations=["Independent frames reset history; not a temporal driving test.",
                               "Yellow-boundary midpoint differs from the current white-dash target.",
                               "No ground truth; detection counts are not accuracy or lap success.",
                               "Current pipeline validates paths; Hough only groups segments. Work differs.",
                               "Hough endpoint means mix depths and can confuse the centre divider.",
                               "A single curved boundary can enter both image-side groups.",
                               "Missing sides produce no target, not invented image-edge coordinates.",
                               "No servo/motor commands, live FPS, latency or stop-fault validation.",
                               "Filename guards do not establish raw provenance. JPEG is lossy.",
                               "BEV, when enabled, uses supplied geometry and is not auto-calibrated."])
    def scalar(value):
        if hasattr(value, "item"):
            return value.item()
        raise TypeError(f"Cannot encode {type(value)}")
    (output/"report.json").write_text(json.dumps(report, indent=2, default=scalar), encoding="utf-8")
    (output/"index.html").write_text(html_report(records, summary), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sizes", nargs="+", type=int, default=[480, 320])
    parser.add_argument("--blurs", nargs="+", type=int, default=[0, 3, 5])
    parser.add_argument("--roi-top", type=float, default=.20)
    parser.add_argument("--colour", choices=["yellow", "white", "both"], default="yellow")
    geometry = parser.add_mutually_exclusive_group()
    geometry.add_argument("--textbook-geometry", action="store_true",
                          help="Use PDF crop .5 / example trapezoid / BEV, not physical calibration")
    geometry.add_argument("--geometry-file", type=Path,
                          help="JSON with roi_top, polygon (normalized crop BL/TL/TR/BR), bird_eye")
    parser.add_argument("--reference", type=float)
    parser.add_argument("--reference-heading", type=float, default=0.)
    parser.add_argument("--lap-mode", action="store_true")
    parser.add_argument("--boundary-guidance", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--sample-seconds", type=float, default=.5)
    parser.add_argument("--max-frames", type=int, default=40)
    args = parser.parse_args()
    options = dict(roi_top=args.roi_top, bird_eye=False)
    try:
        if args.textbook_geometry:
            options = dict(roi_top=.5, polygon=TEXTBOOK_ROI, bird_eye=True)
        elif args.geometry_file:
            options = json.loads(args.geometry_file.read_text(encoding="utf-8"))
            if not isinstance(options, dict) or set(options) != {"roi_top", "polygon", "bird_eye"}:
                raise ValueError("Geometry JSON requires exactly roi_top, polygon and bird_eye")
        report = compare(args.inputs, args.output, sizes=args.sizes, blurs=args.blurs,
                         colour=args.colour, reference=args.reference, heading=args.reference_heading,
                         lap=args.lap_mode, joint=args.boundary_guidance, repeats=args.repeats,
                         sample_seconds=args.sample_seconds, max_frames=args.max_frames, **options)
    except (ValueError, OSError, cv2.error) as error:
        parser.error(str(error))
    print(json.dumps(report["summary"], indent=2))
    print(f"Report: {(args.output/'index.html').resolve()}")


if __name__ == "__main__":
    main()
