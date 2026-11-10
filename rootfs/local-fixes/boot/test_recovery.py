"""Offline checks for bootloader-message preservation and conflicting requests."""
import unittest
import contextlib
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import reboot_recovery as recovery
from reboot_recovery import recovery_message


class BootloaderMessageTests(unittest.TestCase):
    def test_preserves_status_stage_and_all_vendor_and_ab_metadata(self):
        original = bytearray(bytes(range(256)) * 256)
        original[:32] = bytes(32)
        original[64:832] = bytes(768)
        updated = recovery_message(bytes(original))
        self.assertEqual(len(updated), len(original))
        self.assertEqual(updated[32:64], original[32:64])
        self.assertEqual(updated[832:], original[832:])
        self.assertEqual(updated[:32].split(b'\0')[0], b'boot-recovery')
        self.assertEqual(updated[64:832].rstrip(b'\0'), b'recovery\n')

    def test_refuses_pending_update_instead_of_overwriting_it(self):
        original = bytearray(4096)
        original[:12] = b'update-radio'
        with self.assertRaises(RuntimeError):
            recovery_message(bytes(original))

    def test_refuses_existing_recovery_arguments_including_wipe(self):
        original = bytearray(4096)
        arguments = b'recovery\n--wipe_data\n'
        original[64:64 + len(arguments)] = arguments
        with self.assertRaises(RuntimeError):
            recovery_message(bytes(original))

    def test_can_refresh_argument_free_recovery_request(self):
        initial = recovery_message(bytes(4096))
        self.assertEqual(recovery_message(initial), initial)


class RecoveryActionTests(unittest.TestCase):
    def run_simulated_action(self, fail_reboot=False):
        original = bytes(4096)
        desired = recovery_message(original)
        calls = []
        state = {'slot': 'b', 'misc': original}
        guard = SimpleNamespace(snapshot_slots=lambda: ({}, {}, state['slot']))
        def fake_run(*args):
            if args[0] == recovery.SLOTCTL:
                self.assertEqual(args[1], 'select')
                state['slot'] = args[2]
                calls.append(('slot', args[2]))
            else:
                self.assertEqual(state['slot'], 'a')
                self.assertEqual(state['misc'], desired)
                self.assertEqual(args, ('/usr/bin/systemctl', 'reboot', '--reboot-argument=recovery'))
                calls.append(('reboot', 'recovery'))
                if fail_reboot:
                    raise subprocess.CalledProcessError(1, args, stderr='Reboot inhibited')
            return SimpleNamespace(stdout='')
        def fake_write(expected, target):
            self.assertEqual(state['misc'], expected)
            state['misc'] = target
            calls.append(('misc', 'recovery' if target == desired else 'original'))
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(recovery, 'STATE', Path(temp)), \
             patch.object(recovery, 'load_guard', return_value=guard), \
             patch.object(recovery, 'validate', return_value=('b', original, desired)), \
             patch.object(recovery, 'slot_lock', side_effect=contextlib.nullcontext), \
             patch.object(recovery, 'run', side_effect=fake_run), \
             patch.object(recovery, 'write_message', side_effect=fake_write), \
             patch.object(recovery.os, 'geteuid', return_value=0), \
             patch.object(recovery.os, 'umask'), \
             patch.object(recovery.sys, 'argv', ['tb322fc-reboot-recovery']):
            recovery.reboot_issued = False
            if fail_reboot:
                with self.assertRaises(subprocess.CalledProcessError):
                    recovery.main()
            else:
                recovery.main()
        return calls, state

    def test_selects_stock_kernel_before_arming_recovery_and_requesting_reboot(self):
        calls, state = self.run_simulated_action()
        self.assertEqual(calls, [('slot', 'a'), ('misc', 'recovery'), ('reboot', 'recovery')])

    def test_rejected_reboot_restores_misc_and_original_linux_slot(self):
        calls, state = self.run_simulated_action(fail_reboot=True)
        self.assertEqual(calls[-2:], [('misc', 'original'), ('slot', 'b')])
        self.assertEqual(state, {'slot': 'b', 'misc': bytes(4096)})


if __name__ == '__main__':
    unittest.main()
