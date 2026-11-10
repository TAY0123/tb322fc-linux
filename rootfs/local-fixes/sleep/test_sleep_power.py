import copy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import fcntl
import threading
from unittest.mock import patch

import sleep_power as power


class SleepRadioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.radios = [dict(type='bluetooth', name='hci0', id=0, soft=0, hard=0),
                       dict(type='wlan', name='phy0', id=1, soft=0, hard=0)]
        self.bt_on = True
        self.events = []
        self.fail_wifi_block = False
        self.fail_power_restore = False
        patches = [patch.object(power, 'STATE', self.root),
                   patch.object(power, 'SENSOR_SERVICES', ()),
                   patch.object(power, 'PENDING', self.root / 'pending.json'),
                   patch.object(power, 'radios', side_effect=lambda: copy.deepcopy(self.radios)),
                   patch.object(power, 'controllers', return_value=['hci0']),
                   patch.object(power, 'powered', side_effect=lambda name: self.bt_on),
                   patch.object(power, 'set_power', side_effect=self.set_power),
                   patch.object(power, 'run', side_effect=self.run_command),
                   patch.object(power, 'metrics', return_value={'suspend_success': '0'}),
                   patch.object(power, 'log')]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def set_power(self, name, enabled):
        if enabled and self.fail_power_restore:
            raise RuntimeError('Firmware setup timed out')
        self.events.append(('power', enabled))
        self.bt_on = enabled

    def run_command(self, *args, **kwargs):
        self.assertEqual(args[0], '/usr/bin/rfkill')
        item = next(x for x in self.radios if x['id'] == int(args[2]))
        if self.fail_wifi_block and item['type'] == 'wlan' and args[1] == 'block':
            raise RuntimeError('Cannot block Wi-Fi')
        item['soft'] = int(args[1] == 'block')
        self.events.append((args[1], item['type']))
        return ''

    def test_cycle_restores_wifi_before_bluetooth_and_records_diagnostics(self):
        power.prepare()
        self.assertFalse(self.bt_on)
        self.assertEqual([x['soft'] for x in self.radios], [1, 1])
        self.assertTrue(power.PENDING.exists())
        power.restore()
        self.assertTrue(self.bt_on)
        self.assertEqual([x['soft'] for x in self.radios], [0, 0])
        self.assertLess(self.events.index(('unblock', 'wlan')), self.events.index(('power', True)))
        self.assertFalse(power.PENDING.exists())
        self.assertIn('wake_or_abort', json.loads((self.root / 'last-cycle.json').read_text()))

    def test_original_off_and_blocked_radios_stay_off_and_blocked(self):
        self.bt_on = False
        self.radios[0]['soft'] = 1
        self.radios[1]['soft'] = 1
        power.prepare()
        power.restore()
        self.assertFalse(self.bt_on)
        self.assertEqual([x['soft'] for x in self.radios], [1, 1])
        self.assertEqual(self.events, [])

    def test_failed_preparation_rolls_back_all_changed_radios(self):
        self.fail_wifi_block = True
        with self.assertRaisesRegex(RuntimeError, 'Cannot block Wi-Fi'):
            power.prepare()
        self.assertTrue(self.bt_on)
        self.assertEqual([x['soft'] for x in self.radios], [0, 0])
        self.assertFalse(power.PENDING.exists())

    def test_restore_failure_keeps_state_and_restores_wifi_for_retry(self):
        power.prepare()
        self.fail_power_restore = True
        with self.assertRaisesRegex(RuntimeError, 'saved state retained'):
            power.restore()
        self.assertEqual(self.radios[1]['soft'], 0)
        self.assertTrue(power.PENDING.exists())
        self.fail_power_restore = False
        power.restore()
        self.assertTrue(self.bt_on)
        self.assertFalse(power.PENDING.exists())

    def test_second_restore_does_not_change_any_radio(self):
        power.prepare()
        power.restore()
        events = self.events.copy()
        power.restore()
        self.assertEqual(self.events, events)

    def test_abort_recovery_matches_radios_by_name_when_rfkill_ids_change(self):
        power.prepare()
        self.radios[0]['id'] = 5
        self.radios[1]['id'] = 9
        power.restore()
        self.assertTrue(self.bt_on)
        self.assertEqual([x['soft'] for x in self.radios], [0, 0])

    def test_originally_off_bluetooth_is_restored_off_if_auto_enabled(self):
        self.bt_on = False
        power.prepare()
        self.bt_on = True
        power.restore()
        self.assertFalse(self.bt_on)


class PowerTransitionTests(unittest.TestCase):
    def test_waits_for_asynchronous_power_on(self):
        with patch.object(power, 'run') as command, \
             patch.object(power, 'powered', side_effect=[False, False, True]) as query, \
             patch.object(power.time, 'sleep') as delay:
            power.set_power('hci0', True)
        command.assert_called_once_with('/usr/bin/btmgmt', '--index', '0', 'power', 'on', timeout=180)
        self.assertEqual(query.call_count, 3)
        self.assertEqual(delay.call_count, 2)

    def test_tolerates_temporary_query_failure_during_firmware_setup(self):
        with patch.object(power, 'run'), \
             patch.object(power, 'powered', side_effect=[RuntimeError('Not ready'), False, True]), \
             patch.object(power.time, 'sleep'):
            power.set_power('hci0', True)

    def test_failed_transition_has_a_bounded_wait(self):
        with patch.object(power, 'run'), \
             patch.object(power, 'powered', return_value=False), \
             patch.object(power.time, 'monotonic', side_effect=[0, 31]), \
             patch.object(power.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'did not reach requested power state'):
                power.set_power('hci0', True)


class RestoreLockTests(unittest.TestCase):
    def test_waits_for_previous_restore_instead_of_failing_with_eagain(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lock'
            with path.open('w') as owner, path.open('r') as waiting:
                fcntl.flock(owner, fcntl.LOCK_EX)
                timer = threading.Timer(0.1, fcntl.flock, args=(owner, fcntl.LOCK_UN))
                timer.start()
                try:
                    power.acquire_lock(waiting, 2)
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    timer.join()

    def test_lock_wait_times_out_instead_of_hanging_sleep(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lock'
            with path.open('w') as owner, path.open('r') as waiting:
                fcntl.flock(owner, fcntl.LOCK_EX)
                with self.assertRaisesRegex(RuntimeError, 'restoration is still running'):
                    power.acquire_lock(waiting, 0)


if __name__ == '__main__':
    unittest.main()
