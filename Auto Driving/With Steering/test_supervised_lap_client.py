"""The PC supervisor requires an explicit opt-in before any network/control."""

import subprocess
import sys
import threading
import time
import unittest

from supervised_lap_client import Scripts, maintain_lease


class SupervisorTests(unittest.TestCase):
    def test_lease_has_a_deadline_and_cannot_revive_a_stop(self):
        stopped=threading.Event();errors=[];calls=[]
        maintain_lease(lambda:calls.append(time.monotonic()),time.monotonic()+.04,
                       stopped,errors,interval=.01)
        self.assertGreater(len(calls),1)
        count=len(calls)
        stopped.set()
        maintain_lease(lambda:calls.append(0),time.monotonic()+1,stopped,errors)
        self.assertEqual(len(calls),count)

    def test_lease_does_not_retry_a_transport_fault(self):
        stopped=threading.Event();errors=[];calls=[]
        def fail():
            calls.append(1)
            raise TimeoutError('test')
        maintain_lease(fail,time.monotonic()+1,stopped,errors)
        self.assertEqual(calls,[1])
        self.assertTrue(stopped.is_set())
        self.assertEqual(len(errors),1)

    def test_no_ready_flag_never_attempts_a_trial(self):
        result=subprocess.run([sys.executable,'-B','supervised_lap_client.py'],
                              capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,2)
        self.assertIn('Explicit --ready',result.stderr)
        self.assertNotIn('START',result.stdout)

    def test_unbounded_windows_are_rejected_before_network_access(self):
        for seconds in ('0','11','nan','inf'):
            result=subprocess.run([sys.executable,'-B','supervised_lap_client.py','--ready',
                                   '--seconds',seconds],capture_output=True,text=True,timeout=3)
            self.assertEqual(result.returncode,2)
            self.assertIn('supervised window',result.stderr)

    def test_only_script_bodies_are_used_for_options(self):
        parser=Scripts()
        parser.feed('<p>window.pilotOptions=not-json;</p><script>window.pilotOptions={"ok":true};</script>')
        self.assertEqual(parser.scripts,['window.pilotOptions={"ok":true};'])


if __name__=='__main__':
    unittest.main()
