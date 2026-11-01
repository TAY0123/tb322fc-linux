"""Exercise optional asset collectors and failure propagation before signing."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'kshim_updater', ROOT / 'packages/kshim-freedom/freedom-kernel-update.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class InitramfsCollectors(unittest.TestCase):
    def test_missing_optional_collectors_keeps_minimal_handoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            MODULE.populate_initramfs_hooks(root, root / 'missing')
            self.assertEqual(list(root.iterdir()), [])

    def test_collectors_receive_destination_in_name_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hooks = root / 'hooks'
            hooks.mkdir()
            for name, body in [('20-check.sh', 'test -f "$1/asset"'),
                               ('10-asset.sh', ': > "$1/asset"'),
                               ('30-ignore.rpmnew', 'exit 9')]:
                hook = hooks / name
                hook.write_text('#!/bin/sh\n' + body + '\n')
                hook.chmod(0o755)
            MODULE.populate_initramfs_hooks(root, hooks)
            self.assertTrue((root / 'asset').exists())

    def test_missing_required_assets_abort_remaining_collectors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hooks = root / 'hooks'
            hooks.mkdir()
            for name, body in [('10-fail.sh', 'exit 3'),
                               ('20-later.sh', ': > "$1/should-not-exist"')]:
                hook = hooks / name
                hook.write_text('#!/bin/sh\n' + body + '\n')
                hook.chmod(0o755)
            with self.assertRaises(subprocess.CalledProcessError):
                MODULE.populate_initramfs_hooks(root, hooks)
            self.assertFalse((root / 'should-not-exist').exists())


if __name__ == '__main__':
    unittest.main()
