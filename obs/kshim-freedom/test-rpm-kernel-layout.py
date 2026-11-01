#!/usr/bin/env python3
"""Check kernel selection against RPM ownership without touching a device."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class KernelSelection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        src = self.root / 'freedom-kernel-update.py'
        shutil.copyfile(ROOT / 'packages/kshim-freedom/freedom-kernel-update.py', src)
        subprocess.run(['patch', '--quiet', '--batch', '--fuzz=0', '-p1', '-i',
                        str(HERE / 'rpm-kernel-layout.patch')], cwd=self.root, check=True)
        spec = importlib.util.spec_from_file_location('rpm_kernel_update', src)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.config = {'pkgbase': 'kernel-freedom'}

    def kernel(self, release, package='kernel-freedom'):
        directory = self.root / 'modules' / release
        directory.mkdir(parents=True)
        (directory / 'tb322fc-build.json').write_text(json.dumps({
            'release': release, 'package': package, 'build_id': '1234abcd'}))
        return directory

    def test_only_installed_flavor_selected(self):
        installed = self.kernel('7.2.6-24-freedom')
        self.kernel('7.2.6-23-freedom')  # retained rollback tree, no RPM owner
        self.kernel('7.3.0-1-default', 'kernel-default')

        def owner(args, **kwargs):
            self.assertEqual(args[:4], ['rpm', '-qf', '--qf', '%{NAME}\\n'])
            current = Path(args[-1]).parent == installed
            return subprocess.CompletedProcess(args, 0 if current else 1,
                                               'kernel-freedom\n' if current else '')

        with patch.object(self.module.subprocess, 'run', side_effect=owner):
            self.assertEqual(self.module.installed_kernel_releases(
                self.config, self.root / 'modules'), {'7.2.6-24-freedom'})

    def test_wrong_owner_rejected(self):
        directory = self.kernel('7.2.6-24-freedom')
        with patch.object(self.module.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 0, 'unrelated-package\n')):
            self.assertIsNone(self.module.kernel_metadata(self.config, directory))

    def test_mismatched_release_rejected(self):
        directory = self.kernel('7.2.6-24-freedom')
        metadata = directory / 'tb322fc-build.json'
        data = json.loads(metadata.read_text())
        data['release'] = '../incorrect'
        metadata.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.module.kernel_metadata(self.config, directory)


if __name__ == '__main__':
    unittest.main()
