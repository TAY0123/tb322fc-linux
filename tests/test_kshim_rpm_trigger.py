"""RPM updates must refresh the newest owned kernel, without implicit opt-in."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'kshim_rpm_trigger', ROOT / 'obs/kshim-freedom/rpm-boot-update.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RpmBootTrigger(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config.json'
        self.compatible = self.root / 'compatible'
        self.compatible.write_bytes(b'lenovo,elden\0qcom,sm8750\0')
        self.marker = self.root / '.buildenv'

    def invoke(self):
        MODULE.automatic_update(self.config, self.root / 'updater',
                                self.marker, self.compatible)

    def test_no_configuration_or_opt_in_does_not_load_updater(self):
        with patch.object(MODULE, 'load_updater') as loader:
            self.invoke()
            for enabled in (False, None, 'true'):
                self.config.write_text(json.dumps({'deploy_boot_a': enabled}))
                self.invoke()
            loader.assert_not_called()

    def test_build_environment_and_other_hardware_skip_update(self):
        self.config.write_text('{"deploy_boot_a": true}')
        with patch.object(MODULE, 'load_updater') as loader:
            self.marker.touch()
            self.invoke()
            self.marker.unlink()
            self.compatible.write_bytes(b'other,tablet\0')
            self.invoke()
            loader.assert_not_called()

    def test_multiversion_uses_newest_kernel_once(self):
        self.config.write_text('{"deploy_boot_a": true}')
        updater = SimpleNamespace(installed_kernel_releases=lambda _: {
            '7.2.6-9-freedom', '7.2.6-28-freedom', '7.2.6-30-freedom'})
        real_run = subprocess.run
        with patch.object(MODULE, 'load_updater', return_value=updater), \
             patch.object(MODULE.subprocess, 'run', wraps=subprocess.run) as run:
            # Keep the real version sort; intercept only the deployment helper.
            def dispatch(args, **kwargs):
                if args[0] == 'sort':
                    return real_run(args, **kwargs)
                return subprocess.CompletedProcess(args, 0)
            run.side_effect = dispatch
            self.invoke()
            deployments = [call for call in run.call_args_list if call.args[0][0] != 'sort']
            self.assertEqual(len(deployments), 1)
            args = deployments[0].args[0]
            self.assertEqual(args[-3:], ['--kernel', '7.2.6-30-freedom', '--hook'])
            self.assertNotIn('--deploy', args)

    def test_failed_update_is_reported_without_older_kernel_retry(self):
        self.config.write_text('{"deploy_boot_a": true}')
        updater = SimpleNamespace(installed_kernel_releases=lambda _: {'7.2.6-30-freedom'})
        with patch.object(MODULE, 'load_updater', return_value=updater), \
             patch.object(MODULE.subprocess, 'check_output', return_value='7.2.6-30-freedom\n'), \
             patch.object(MODULE.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'update')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                self.invoke()
            self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
