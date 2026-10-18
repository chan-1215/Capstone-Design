"""Analyze saved track images and write a local, static visual report."""

import argparse
from dataclasses import asdict
from html import escape
import json
from pathlib import Path

import cv2
import numpy as np

from track_vision import VisionConfig, analyze, overlay


def read_image(path):
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot decode image: {path}")
    return image


def write_image(path, image):
    ok, encoded = cv2.imencode(path.suffix, image)
    if not ok:
        raise ValueError(f"Cannot encode image: {path}")
    encoded.tofile(str(path))


def report_html(records):
    rows = []
    for record in records:
        metrics = record["metrics"]
        prefix = record["prefix"]
        rows.append(f'''<section><h2>{escape(record['name'])}</h2>
<p class="metrics">{escape(metrics['status'])} &middot; white markings {metrics['white_marking_count']}
&middot; dash candidates {metrics['dash_candidate_count']}</p>
<div class="images"><figure><img src="{prefix}_overlay.jpg" alt="Track segmentation overlay"><figcaption>Overlay</figcaption></figure>
<figure><img src="{prefix}_original.jpg" alt="Original track photo"><figcaption>Original</figcaption></figure></div>
<details><summary>Masks</summary><div class="masks">
{''.join(f'<figure><img src="{prefix}_{name}.png" alt="{name} mask"><figcaption>{name}</figcaption></figure>' for name in ('road', 'yellow', 'white', 'dashes'))}
</div></details></section>''')
    return '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Track Vision</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f5f6f7;color:#182024;font:15px/1.5 system-ui,sans-serif;letter-spacing:0}
header{padding:20px 28px;background:#182024;color:white}h1{font-size:24px;margin:0}header p{margin:4px 0 0;color:#d1d9dd}
main{max-width:1600px;margin:auto;padding:0 28px}section{padding:24px 0;border-bottom:1px solid #ccd2d5}h2{font-size:18px;overflow-wrap:anywhere;margin:0}
.metrics{color:#43515b;margin:8px 0}.images{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}figure{margin:0;min-width:0}
img{width:100%;height:auto;display:block}figcaption{font-size:13px;padding:6px 0;color:#43515b}summary{cursor:pointer;padding:12px 0}
.masks{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.legend{display:flex;flex-wrap:wrap;gap:18px;margin-top:12px}.legend span:before{content:"";display:inline-block;width:12px;height:12px;margin-right:7px;background:var(--c)}
@media(max-width:700px){main{padding:0 14px}header{padding:16px 14px}.images{grid-template-columns:1fr}.masks{grid-template-columns:1fr 1fr}}
</style><header><h1>Track Vision</h1><p>Offline photo review / no vehicle control</p>
<div class="legend"><span style="--c:#235a96">Road region</span><span style="--c:#ffa500">Yellow candidates</span><span style="--c:#ff64b4">White candidates</span><span style="--c:#00ffff">Dash candidates</span></div></header>
<main>''' + "\n".join(rows) + "</main></html>"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("outputs"))
    parser.add_argument("--roi-top", type=float, default=0.0)
    parser.add_argument("--max-side", type=int, default=1280)
    parser.add_argument("--white-min-value", type=int, default=175)
    parser.add_argument("--road-max-value", type=int, default=155)
    args = parser.parse_args()
    config = VisionConfig(max_side=args.max_side, roi_top=args.roi_top,
                          white_min_value=args.white_min_value,
                          road_max_value=args.road_max_value)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for index, path in enumerate(args.images, 1):
        result = analyze(read_image(path), config)
        prefix = f"photo_{index:02d}"
        write_image(args.output / f"{prefix}_original.jpg", result.frame)
        write_image(args.output / f"{prefix}_overlay.jpg", overlay(result))
        for name in ("road", "yellow", "white", "dashes"):
            write_image(args.output / f"{prefix}_{name}.png", getattr(result, name))
        records.append({"name": path.name, "prefix": prefix,
                        "metrics": result.metrics, "markings": result.markings})
        print(json.dumps({"image": path.name, **result.metrics}, ensure_ascii=True))
    report = {"config": asdict(config), "records": records,
              "limitations": ["No physical scale or turning-radius estimate.",
                              "White candidates may include glare or crosswalk stripes.",
                              "No lane selection, traffic-light decisions, or motor commands.",
                              "Reference photos are not an onboard-camera validation set."]}
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.output / "index.html").write_text(report_html(records), encoding="utf-8")
    print(f"Report: {(args.output / 'index.html').resolve()}")


if __name__ == "__main__":
    main()
