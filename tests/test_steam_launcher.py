"""Exercise restart and termination against a fake Steam, without a desktop."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

LAUNCHER = Path(__file__).resolve().parents[1] / 'packages/steam-bootstrap/launch-steam'
FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, signal, sys, time
p = pathlib.Path(os.environ['FAKE_STEAM_STATE'])
calls = p / 'calls.json'
history = json.loads(calls.read_text()) if calls.exists() else []
history.append(sys.argv[1:])
calls.write_text(json.dumps(history))
if (p / 'wait').exists():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(42))
    (p / 'pid').write_text(str(os.getpid()))
    while True:
        time.sleep(0.05)
sys.exit(json.loads((p / 'codes.json').read_text())[len(history)-1])
'''


class SteamLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='steam-launcher-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        arm = self.root / 'steamrtarm64'
        arm.mkdir()
        self.fake = arm / 'steam'
        self.fake.write_text(FAKE)
        self.fake.chmod(0o755)
        self.env = dict(os.environ, STEAM_ROOT=str(self.root),
                        FAKE_STEAM_STATE=str(self.root))

    def launch(self, codes, *args):
        (self.root / 'codes.json').write_text(json.dumps(codes))
        proc = subprocess.Popen(['bash', str(LAUNCHER), *args], env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        self.addCleanup(self.stop, proc)
        return proc

    @staticmethod
    def stop(proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate(timeout=5)

    def calls(self):
        return json.loads((self.root / 'calls.json').read_text())

    def test_update_restarts_with_identical_arguments(self):
        args = ['-gamepadui', '-applaunch', 'a game with spaces', '']
        proc = self.launch([42, 42, 0], *args)
        proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.calls(), [args, args, args])

    def test_clean_exit_is_not_restarted(self):
        proc = self.launch([0])
        proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_failure_is_propagated(self):
        proc = self.launch([17])
        proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 17)
        self.assertEqual(len(self.calls()), 1)

    def test_desktop_argument_is_preserved_on_restart(self):
        proc = self.launch([42, 0], '--desktop', 'steam://open/main')
        proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.calls(), [['-steamdeck', 'steam://open/main']] * 2)

    def test_termination_cannot_trigger_restart(self):
        (self.root / 'wait').touch()
        proc = self.launch([42])
        deadline = time.monotonic() + 5
        while not (self.root / 'pid').exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue((self.root / 'pid').exists(), 'fake Steam never started')
        child = int((self.root / 'pid').read_text())
        proc.terminate()
        proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 143)
        self.assertEqual(len(self.calls()), 1)
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_missing_client_is_reported(self):
        self.fake.unlink()
        proc = self.launch([0])
        proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 127)


if __name__ == '__main__':
    unittest.main()
