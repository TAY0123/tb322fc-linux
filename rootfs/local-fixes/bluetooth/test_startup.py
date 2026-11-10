"""Failure-path tests for the tablet's Bluetooth startup and recovery."""
import runpy
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).with_name('tb322fc-bluetooth-identity')
ns = runpy.run_path(str(SCRIPT))
g = ns['configure'].__globals__
SetupError = ns['SetupError']
Controller = ns['Controller']
ADDRESS = '02:00:00:00:00:01'  # Synthetic test identity.
g['ADDRESS'] = ADDRESS


class StartupTests(unittest.TestCase):
    def test_btmgmt_failure_with_success_exit_status(self):
        result = subprocess.CompletedProcess([], 0, '',
            'Set Powered for hci0 failed with status 0x03 (Failed)')
        with patch.object(subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(SetupError, 'status 0x03'):
                ns['command']('btmgmt', 'power', 'on', deadline=time.monotonic() + 5)

    def test_failed_systemd_state_is_data(self):
        result = subprocess.CompletedProcess([], 0, 'failed\n', '')
        with patch.object(subprocess, 'run', return_value=result):
            self.assertEqual(ns['command']('systemctl', 'show',
                deadline=time.monotonic() + 5), 'failed')

    def test_deadline_prevents_another_command(self):
        with patch.object(subprocess, 'run') as run:
            with self.assertRaises(SetupError):
                ns['command']('btmgmt', 'info', deadline=time.monotonic() - 1)
            run.assert_not_called()

    def test_uninitialized_address_rejected(self):
        output = 'addr 00:00:00:00:00:00 version 14 manufacturer 29\ncurrent settings: '
        with patch.dict(g, command=Mock(return_value=output)):
            with self.assertRaises(SetupError):
                ns['info'](time.monotonic() + 5)

    def test_powered_is_current_setting_not_supported_setting(self):
        output = f'addr {ADDRESS} version 14 manufacturer 29\nsupported settings: powered\ncurrent settings: bondable\n'
        with patch.dict(g, command=Mock(return_value=output)):
            self.assertFalse(ns['info'](time.monotonic() + 5).powered)

    def test_healthy_controller_does_not_power_cycle(self):
        module = Mock()
        module.is_dir.return_value = True
        run = Mock(return_value='2002')
        wait = Mock(return_value=Controller(ADDRESS, True))
        with patch.dict(g, MODULE=module, command=run, wait_for=wait):
            ns['configure'](time.monotonic() + 180)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], 'systemctl')

    def test_startup_leaves_radio_off_for_bluez_privacy_configuration(self):
        module = Mock()
        module.is_dir.return_value = True
        wait = Mock(return_value=Controller(ADDRESS, False))
        run = Mock()
        with patch.dict(g, MODULE=module, command=run, wait_for=wait):
            ns['configure'](time.monotonic() + 180)
        run.assert_not_called()

    def test_startup_turns_previously_powered_radio_off_before_bluez(self):
        module = Mock()
        module.is_dir.return_value = True
        wait = Mock(return_value=Controller(ADDRESS, True))
        run = Mock(return_value='0')
        with patch.dict(g, MODULE=module, command=run, wait_for=wait):
            ns['configure'](time.monotonic() + 180)
        self.assertEqual(run.call_args.args[:5], ('btmgmt', '--index', '0', 'power', 'off'))
        self.assertFalse(wait.call_args.kwargs['powered'])

    def test_failed_initialization_gets_fresh_uart(self):
        for failures in (0, 1, 2, 3):
            with self.subTest(failures=failures):
                device = Mock()
                device.__truediv__ = Mock(return_value=Mock(exists=Mock(return_value=True)))
                setup = Mock(side_effect=[SetupError('firmware timeout')] * failures +
                             ([None] if failures < 3 else []))
                reset = Mock()
                with patch.dict(g, DEVICE=device, UART=device, configure=setup, reset_controller=reset), patch.object(time, 'sleep'):
                    if failures == 3:
                        with self.assertRaises(SetupError):
                            ns['configure_with_retries']()
                    else:
                        ns['configure_with_retries']()
                self.assertEqual(setup.call_count, min(failures + 1, 3))
                self.assertEqual(reset.call_count, min(failures, 2))

    def test_reset_unloads_callback_before_unbind_and_rebinds_on_error(self):
        device = Mock()
        device.resolve.return_value.parts = ('sys', '898000.serial', 'serial0-0')
        device.name = 'serial0-0'
        driver_link = Mock()
        driver_link.exists.side_effect = [True, True, False]
        driver_link.resolve.return_value = ns['DRIVER']
        compatible = Mock()
        compatible.read_bytes.return_value = b'qcom,wcn7861-bt\0'
        device.__truediv__ = Mock(side_effect=lambda name:
                                  driver_link if name == 'driver' else compatible)
        uart = Mock()
        uart.name = '898000.serial'
        uart_driver_link = Mock()
        uart_driver_link.exists.side_effect = [True, True, False]
        uart_driver_link.resolve.return_value = ns['UART_DRIVER']
        uart.__truediv__ = Mock(side_effect=lambda name:
                                uart_driver_link if name == 'driver' else compatible)
        module = Mock()
        module.is_dir.return_value = True
        calls = []
        def run(*args, **kwargs):
            calls.append(args)
            if args[0] == 'systemctl':
                return '0'
            if args == ('tee', str(ns['UART_DRIVER'] / 'unbind')):
                raise SetupError('interrupted unbind')
            return ''
        with patch.dict(g, DEVICE=device, UART=uart, MODULE=module, command=run), patch.object(time, 'sleep'):
            with self.assertRaises(SetupError):
                ns['reset_controller']()
        self.assertEqual(calls[1], ('modprobe', '-r', 'bt_android_identity'))
        self.assertEqual(calls[2], ('tee', str(ns['UART_DRIVER'] / 'unbind')))
        self.assertEqual(calls[3], ('tee', str(ns['UART_DRIVER'] / 'bind')))

    def test_reset_refused_when_daemon_running(self):
        run = Mock(return_value='2002')
        with patch.dict(g, command=run):
            with self.assertRaisesRegex(SetupError, 'bluetoothd is running'):
                ns['reset_controller']()
        self.assertEqual(run.call_count, 1)

    def test_failed_startup_retried_but_intentional_stop_respected(self):
        for states in [('failed', 'inactive'), ('active', 'failed'),
                       ('active', 'inactive'), ('active', 'active'),
                       ('activating', 'inactive')]:
            with self.subTest(states=states):
                run = Mock(side_effect=[*states, ''])
                with patch.dict(g, command=run, info=Mock(return_value=Controller(ADDRESS, False)), UNAVAILABLE=Mock()):
                    ns['retry_failed_service']()
                self.assertEqual(run.call_count, 3 if 'failed' in states else 2)
                if 'failed' in states:
                    self.assertEqual(run.call_args.args, ('systemctl', '--no-block', 'start', 'bluetooth.service'))

    def test_running_daemon_with_missing_controller_eventually_reinitializes(self):
        for first, expected_calls in [(None, 2), (950, 2), (800, 3)]:
            with self.subTest(first=first):
                marker = Mock()
                if first is None:
                    marker.read_text.side_effect = FileNotFoundError()
                else:
                    marker.read_text.return_value = str(first)
                run = Mock(return_value='active')
                with patch.dict(g, command=run, info=Mock(side_effect=SetupError('Invalid Index')),
                                UNAVAILABLE=marker), patch.object(time, 'monotonic', return_value=1000):
                    ns['retry_failed_service']()
                self.assertEqual(run.call_count, expected_calls)
                if expected_calls == 3:
                    self.assertEqual(run.call_args.args, ('systemctl', '--no-block', 'restart',
                        'tb322fc-bluetooth-identity.service', 'bluetooth.service'))

    def test_healthy_powered_off_controller_does_not_trigger_recovery(self):
        run = Mock(return_value='active')
        marker = Mock()
        with patch.dict(g, command=run, info=Mock(return_value=Controller(ADDRESS, False)), UNAVAILABLE=marker):
            ns['retry_failed_service']()
        self.assertEqual(run.call_count, 2)
        marker.unlink.assert_called_once_with(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
