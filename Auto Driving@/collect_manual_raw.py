"""Save synchronized raw camera/command samples directly on the laptop."""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def collect(pi_url, output_dir, duration=60, fps=10):
    if not 1 <= duration <= 300 or not 1 <= fps <= 15:
        raise ValueError("Duration must be 1..300 seconds and FPS 1..15")
    session = output_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session.mkdir(parents=True, exist_ok=False)
    manifest = session / "frames.csv"
    last_frame_at = None
    start = time.monotonic()
    next_sample = start
    saved = 0
    with manifest.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("file", "pi_frame_at", "throttle", "steer",
                         "command_age", "manual_valid", "pc_received_at"))
        while time.monotonic() - start < duration:
            wait = next_sample - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            next_sample += 1 / fps
            try:
                request = Request(f"{pi_url.rstrip('/')}/record/sample",
                                  headers={"Cache-Control": "no-cache"})
                with urlopen(request, timeout=2) as response:
                    headers = response.headers
                    frame_at = headers.get("X-Frame-Time")
                    if frame_at is None or frame_at == last_frame_at:
                        continue
                    jpeg = response.read()
            except URLError as exc:
                print(f"Capture stopped: {exc}")
                break
            last_frame_at = frame_at
            filename = f"{saved:06d}.jpg"
            (session / filename).write_bytes(jpeg)
            writer.writerow((filename, frame_at, headers.get("X-Throttle"),
                             headers.get("X-Steer"), headers.get("X-Command-Age"),
                             headers.get("X-Manual-Valid"), f"{time.time():.6f}"))
            file.flush()
            saved += 1
    return session, saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-url", required=True)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).parent / "manual_dataset" / "raw_sessions")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--fps", type=int, default=10)
    args = parser.parse_args()
    session, saved = collect(args.pi_url, args.output_dir, args.duration, args.fps)
    print(f"Saved {saved} raw frames and command labels to {session}")


if __name__ == "__main__":
    main()
