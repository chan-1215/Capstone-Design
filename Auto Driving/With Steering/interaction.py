"""Per-run crossing latch and fresh go gate. No hardware or automatic arming."""


class CrossingGate:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state = 'follow'
        self.latched = False
        self.wait_started = None
        self.absent_since = None
        self.absent_count = 0
        self.last_frame = None
        self.last_gesture = None
        self.go_since = self.last_go = None
        self.go_count = 0
        self.gesture_epoch = None

    @property
    def waiting(self):
        return self.state == 'wait_gesture'

    def observe_crosswalk(self, crossing, number, now):
        if type(number) is not int or self.last_frame is not None and number <= self.last_frame:
            return
        self.last_frame = number
        if not self.latched:
            self.state = 'crosswalk_approach' if crossing.get('stable') else 'follow'
        if not self.latched and crossing.get('stop'):
            self.latched = True
            self.state = 'wait_gesture'
            self.wait_started = now
            self.go_since = self.last_go = None
            self.go_count = 0
            self.gesture_epoch = None
        if self.state == 'depart':
            if crossing.get('detected'):
                self.absent_since = None
                self.absent_count = 0
            else:
                if self.absent_since is None:
                    self.absent_since = now
                self.absent_count += 1
                if self.absent_count >= 5 and now-self.absent_since >= .6:
                    self.reset()

    def authorize(self, result, now, path_ready):
        if not self.waiting:
            return False
        received = result.get('received_at')
        current = (result.get('mode') == 'wait' and result.get('ready')
                   and result.get('hand_detected') and not result.get('error')
                   and type(received) in (float, int) and self.wait_started <= received <= now
                   and now-received <= .2 and result.get('epoch') is not None)
        if not current or result.get('decision_label') != 'go':
            self.go_since = self.last_go = None
            self.go_count = 0
            return False
        identity = (result['epoch'], result.get('number'))
        if identity == self.last_gesture:
            return False
        self.last_gesture = identity
        if self.gesture_epoch != result['epoch'] or self.last_go is None or received-self.last_go > .2:
            self.go_since = received
            self.go_count = 0
        if self.last_go is not None and self.gesture_epoch == result['epoch'] and received <= self.last_go:
            return False
        self.gesture_epoch = result['epoch']
        self.last_go = received
        self.go_count += 1
        if self.go_count >= 5 and received-self.go_since >= .5 and path_ready:
            self.state = 'depart'
            self.absent_since = None
            self.absent_count = 0
            return True
        return False

    def status(self):
        return dict(state=self.state, crossing_latched=self.latched, go_frames=self.go_count)
