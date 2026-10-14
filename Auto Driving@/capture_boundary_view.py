"""Save a stationary Pi camera view and recognition status on the laptop."""

import argparse
from datetime import datetime
import json
from pathlib import Path
from urllib.request import urlopen


def capture(pi_url, label, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    with urlopen(f"{pi_url.rstrip('/')}/stream/raw", timeout=5) as stream:
        jpeg = None
        for _ in range(5):
            if stream.readline().strip() != b"--frame":
                raise ValueError("Unexpected camera stream boundary")
            headers = {}
            while line := stream.readline().strip():
                key, value = line.split(b":", 1)
                headers[key.lower()] = value.strip()
            jpeg = stream.read(int(headers[b"content-length"]))
            stream.read(2)
    with urlopen(f"{pi_url.rstrip('/')}/status", timeout=5) as response:
        status = json.load(response)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = output_dir / f"{stamp}_{label}"
    base.with_suffix(".jpg").write_bytes(jpeg)
    base.with_suffix(".json").write_text(json.dumps(status, indent=2,
                                                     ensure_ascii=False), encoding="utf-8")
    return base, status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", choices=("inside", "on_line", "outside"))
    parser.add_argument("--pi-url", default="http://192.168.137.155:5001")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).parent / "manual_dataset" / "boundary_checks")
    args = parser.parse_args()
    base, status = capture(args.pi_url, args.label, args.output_dir)
    print(f"Saved {base}.jpg/.json: {status}")


if __name__ == "__main__":
    main()
