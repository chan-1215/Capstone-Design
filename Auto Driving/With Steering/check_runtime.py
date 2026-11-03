"""Read-only Flask health check. Never sends POST, arms GPIO or starts motion."""

import argparse
import json
from pathlib import Path
import time
import urllib.request


def summarize(samples, expect_preview=False):
    if not samples:
        raise ValueError('No observations received')
    problems = []
    for data in samples:
        if not data.get('camera_online'):
            problems.append('camera_offline')
        if data.get('error'):
            problems.append('camera_error')
        runtime = data.get('runtime', {})
        if not runtime.get('python_version', '').startswith('3.11.'):
            problems.append('wrong_runtime')
        if expect_preview and runtime.get('hardware_enabled'):
            problems.append('hardware_not_expected_in_preview')
        manual, pilot = data.get('manual') or {}, data.get('autonomous') or {}
        if manual.get('armed') or pilot.get('active') or manual.get('pwm_active') or any(manual.get('motor_outputs', [])):
            problems.append('robot_control_active')
        gesture = data.get('gesture')
        if gesture is not None and (not gesture.get('initialized') or gesture.get('error')):
            problems.append('gesture_not_ready')
        if data.get('source_age_seconds') is None or data['source_age_seconds'] > .2:
            problems.append('source_frame_stale')
    numbers = [x.get('source_frame_number') for x in samples]
    if len(samples) > 1 and len(set(numbers)) < 2:
        problems.append('camera_not_advancing')
    fps = [x.get('fps',0) for x in samples]
    ages = [x['source_age_seconds'] for x in samples if x.get('source_age_seconds') is not None]
    return dict(ok=not problems, problems=sorted(set(problems)), samples=len(samples),
                runtime=samples[-1].get('runtime'), fps_min=min(fps),fps_max=max(fps),
                max_source_age_seconds=max(ages) if ages else None,
                gesture=samples[-1].get('gesture'),
                note='Command/freshness check only; not measured wheel motion or recognition accuracy.')


def collect(url, count=10, interval=.1):
    samples = []
    for index in range(count):
        with urllib.request.urlopen(url.rstrip('/')+'/status',timeout=3) as response:
            samples.append(json.load(response))
        if index+1 < count:
            time.sleep(interval)
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:5001')
    parser.add_argument('--samples',type=int,default=10)
    parser.add_argument('--expect-preview',action='store_true')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if not 1 <= args.samples <= 100:
        parser.error('--samples must be1..100')
    try:
        samples = collect(args.url,args.samples)
        report = summarize(samples,args.expect_preview)
    except (OSError,ValueError,KeyError,TypeError) as error:
        samples = []
        report = dict(ok=False,problems=[f'{type(error).__name__}: {error}'])
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(dict(report=report,samples=samples),indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
