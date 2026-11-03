"""One bounded PC-supervised trial; never retries or renews a stopped pilot."""

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import socket
import threading
import time
import urllib.request
import uuid


BASE = 'http://192.168.137.60:5001'


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.inside = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.scripts.append(data)


def maintain_lease(heartbeat, deadline, stopped, failures, interval=.12):
    """PC-only lease with its own deadline; observation I/O cannot extend it."""
    while not stopped.is_set() and time.monotonic()<deadline:
        try:
            heartbeat()
        except Exception as error:
            failures.append(f'{type(error).__name__}: {error}')
            stopped.set()
            return
        stopped.wait(min(interval,max(0.,deadline-time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=2)
    parser.add_argument('--ready', action='store_true',
                        help='Observer confirmed placement, clear track and immediate stop readiness')
    parser.add_argument('--restore', nargs=2, metavar=('REFERENCE', 'STOPPED_RUN'))
    args = parser.parse_args()
    if not args.ready:
        parser.error('Explicit --ready is required after physical readiness confirmation')
    if not .2 <= args.seconds <= 10:
        parser.error('Use a supervised window between .2 and 10 seconds')
    with socket.create_connection(('192.168.137.60',5001),timeout=2) as connection:
        if connection.getsockname()[0] == connection.getpeername()[0]:
            parser.error('Run the supervisor on the external PC, never on the robot itself')
    client = 'codex-lap-' + uuid.uuid4().hex[:12]
    page = Scripts()
    page.feed(urllib.request.urlopen(BASE+'/', timeout=2).read().decode())
    options = next(json.loads(script.strip()[len('window.pilotOptions='):].rstrip(';'))
                   for script in page.scripts if script.strip().startswith('window.pilotOptions='))
    token = options.pop('token')

    def get():
        with urllib.request.urlopen(BASE+'/status', timeout=.4) as response:
            return json.load(response)

    def post(action, **values):
        request = urllib.request.Request(BASE+'/auto/'+action,
            data=json.dumps(dict(client=client, **values)).encode(),
            headers={'Content-Type':'application/json', 'X-Manual-Token':token})
        with urllib.request.urlopen(request, timeout=.4) as response:
            return json.load(response)

    status = get()
    assert not status['manual']['armed'] and not status['autonomous']['active'], 'Stop existing control'
    assert status['camera_online'] and status['autonomous']['settings']['lap_mode']
    assert not status['autonomous']['settings']['crosswalk_gesture']
    if args.restore:
        post('restore', reference_file=args.restore[0], stopped_run=args.restore[1])
        time.sleep(.35)
        status = get()
    assert status['autonomous']['blocked_reason'] is None, status['autonomous']['blocked_reason']
    attempted = False
    stopped=threading.Event()
    failures=[]
    worker=None
    try:
        attempted = True
        print('START', json.dumps(post('start')), flush=True)
        begin = time.monotonic()
        worker=threading.Thread(target=maintain_lease,
            args=(lambda:post('heartbeat'),begin+args.seconds,stopped,failures),daemon=True)
        worker.start()
        next_report = 0
        while time.monotonic()-begin < args.seconds:
            if failures:
                break
            status = get()
            pilot = status['autonomous']
            elapsed = time.monotonic()-begin
            if elapsed >= next_report or not pilot['active']:
                path = status['path_prediction']
                print(json.dumps(dict(t=round(elapsed,2), active=pilot['active'],
                    reason=pilot['reason'], angle=pilot['steering'], wanted=pilot['predicted_angle'],
                    path=path.get('reason'), heading=path.get('heading_error_degrees'),
                    error=path.get('normalized_error'), near=path.get('near_road_fraction'),
                    outputs=status['manual']['motor_outputs'], fps=status['fps'],
                    age=status['source_age_seconds'])), flush=True)
                next_report = elapsed+.25
            if not pilot['active']:
                break
            stopped.wait(.15)
    except Exception as error:
        failures.append(f'{type(error).__name__}: {error}')
    finally:
        stopped.set()
        if attempted:
            try:
                status = get()
                if status['autonomous']['active'] and status['autonomous']['client'] == client:
                    post('stop')
            except Exception:
                # The same-owner endpoint cannot stop someone else's session;
                # transport loss also lets the independent .7s lease expire.
                try:
                    post('stop')
                except Exception:
                    pass
        if worker:
            worker.join(.6)
    status = get()
    assert not status['autonomous']['active'] and not status['manual']['armed']
    print('STOPPED', json.dumps(status['autonomous']), flush=True)
    if failures:
        print('SUPERVISOR_FAULT',json.dumps(failures),flush=True)
    directory = Path(__file__).parent/'outputs'/'review_20261019'
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%H%M%S')
    (directory/('trial_'+stamp+'.json')).write_text(
        json.dumps(dict(status=status,supervisor_faults=failures),indent=2),encoding='utf-8')
    image = urllib.request.urlopen(BASE+'/snapshot/processed.jpg', timeout=2).read()
    (directory/('trial_'+stamp+'.jpg')).write_bytes(image)
    print('IMAGE', directory/('trial_'+stamp+'.jpg'), flush=True)


if __name__ == '__main__':
    main()
