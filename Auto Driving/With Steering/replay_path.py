"""Independent RAW still-image path review, with no server or GPIO access."""

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

import cv2

from analyze_photos import read_image, write_image
from boundary_guidance import guide_path
from crosswalk import detect_crosswalk, exclude_crosswalk_dashes
from lane_path import LanePath, draw_path
from track_vision import VisionConfig, analyze, overlay


def validate_reference(reference, heading):
    if reference is not None and (not math.isfinite(reference) or not 0 < reference < 1):
        raise ValueError('Reference must be a finite normalized value strictly between 0 and 1')
    if not math.isfinite(heading) or not -90 < heading < 90:
        raise ValueError('Reference heading must be finite and between -90 and 90')
    if reference is None and heading != 0:
        raise ValueError('A heading requires an explicit reference')


def raw_image(path):
    path = Path(path)
    if (path.suffix.lower() not in ('.png', '.jpg', '.jpeg') or
            not (path.stem.lower() == 'raw' or path.stem.lower().endswith('_raw'))):
        raise ValueError('Use a named raw-camera still (*_raw.png or *_raw.jpg), not a screen recording/overlay')
    return path


def predict_still(result, reference, heading, lap_mode, joint_guidance):
    tracker = LanePath()
    tracker.reference = reference
    tracker.reference_heading = heading
    prediction = tracker.predict(result, completion_priority=lap_mode)
    return guide_path(result, prediction, heading) if joint_guidance else prediction


def review(paths, output, *, config=None, reference=None, heading=0., lap_mode=False, joint_guidance=False):
    """Reset temporal state for EACH still; never infer a completed driving run."""
    validate_reference(reference, heading)
    if joint_guidance and not lap_mode:
        raise ValueError('Joint guidance requires lap mode')
    paths = [raw_image(path) for path in paths]
    if not paths:
        raise ValueError('At least one raw image is required')
    config = config or VisionConfig(max_side=480, roi_top=.20)
    output = Path(output).resolve()
    # Never overwrite source material, even when the chosen report directory is a capture folder.
    if output in {path.resolve().parent for path in paths}:
        raise ValueError('Choose an output directory separate from the source images')
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for index, path in enumerate(paths):
        frame = read_image(path)
        result = analyze(frame, config)
        crossing = detect_crosswalk(result, reference if reference is not None else .5)
        exclude_crosswalk_dashes(result, crossing)
        baseline = predict_still(result, reference, heading, lap_mode, False)
        selected = predict_still(result, reference, heading, lap_mode, joint_guidance)
        rendered = overlay(result, lines_only=True)
        draw_path(rendered, selected)
        preview = f'{index:03d}_{path.stem}_review.png'
        write_image(output / preview, rendered)
        records.append(dict(source=str(path.resolve()), source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            decoded_bgr_sha256=hashlib.sha256(frame.tobytes()).hexdigest(),
                            source_format=path.suffix.lower(),
                            pixel_exact_saved_frame=path.suffix.lower() == '.png',
                            preview=preview, metrics=result.metrics, markings=result.markings, crosswalk=crossing,
                            baseline=baseline, selected=selected))
    source_dir = Path(__file__).resolve().parent
    report = dict(kind='independent_raw_stills', hardware_access=False, config=asdict(config),
                  assumed_reference=reference, assumed_reference_heading=heading,
                  lap_mode=lap_mode, joint_guidance=joint_guidance,
                  source_hashes={name:hashlib.sha256((source_dir/name).read_bytes()).hexdigest()
                                 for name in ('track_vision.py', 'lane_path.py', 'boundary_guidance.py', 'crosswalk.py')},
                  limitations=['Independent images, not a temporal driving replay or a lap test.',
                               'Reference values are supplied assumptions, not a new physical calibration.',
                               'Raw filename validation is not proof of unannotated camera content.',
                               'JPEG can change threshold classifications; PNG preserves the saved BGR pixels.',
                               'No measured motor speed, wheel angle, current or stop-system validation.'],
                  summary=dict(images=len(records), valid=sum(bool(r['selected']['valid']) for r in records),
                               reasons=dict(Counter(r['selected']['reason'] for r in records))),
                  records=records)
    def scalar(value):
        if hasattr(value, 'item'):
            return value.item()
        raise TypeError(f'Unsupported JSON value: {type(value).__name__}')
    (output/'report.json').write_text(json.dumps(report, indent=2, default=scalar), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--reference', type=float)
    parser.add_argument('--reference-heading', type=float, default=0.)
    parser.add_argument('--lap-mode', action='store_true')
    parser.add_argument('--boundary-guidance', action='store_true')
    parser.add_argument('--analysis-max-side', type=int, default=480)
    parser.add_argument('--roi-top', type=float, default=.20)
    args = parser.parse_args()
    try:
        report = review(args.images, args.output,
                        config=VisionConfig(max_side=args.analysis_max_side, roi_top=args.roi_top),
                        reference=args.reference, heading=args.reference_heading,
                        lap_mode=args.lap_mode, joint_guidance=args.boundary_guidance)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report['summary']))
    print(f'Report: {(args.output / "report.json").resolve()}')


if __name__ == '__main__':
    main()
