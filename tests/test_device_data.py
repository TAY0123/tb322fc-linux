"""Guard private data imports against corruption, archive escape and rollback."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('device_data', REPO / 'scripts/device-data.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class DeviceData(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.bundle = self.work / 'bundle'
        self.bundle.mkdir()
        self.target = self.work / 'target'
        self.target.mkdir()

    def bundle_with_member(self, name):
        archive = self.bundle / 'hexagonrpc.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            member = tarfile.TarInfo(name)
            member.size = 4
            tar.addfile(member, io.BytesIO(b'data'))
        manifest = {'format': 1, 'archive': archive.name,
                    'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                    'entries': [{'path': name.removeprefix('hexagonrpc/'), 'type': 'file'}]}
        (self.bundle / 'manifest.json').write_text(json.dumps(manifest))
        return archive

    def test_corrupted_archive_is_rejected_before_extraction(self):
        archive = self.bundle_with_member('hexagonrpc/file')
        with archive.open('ab') as stream:
            stream.write(b'corruption')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            helper.unpack_verified(self.bundle, self.target)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_parent_path_cannot_escape_archive_root(self):
        self.bundle_with_member('hexagonrpc/../../outside')
        with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
            helper.unpack_verified(self.bundle, self.target)
        self.assertFalse((self.work / 'outside').exists())
        self.assertEqual(list(self.target.iterdir()), [])

    def test_existing_live_registry_is_never_replaced(self):
        (self.target / 'etc').mkdir()
        (self.target / 'etc/os-release').write_text('ID=opensuse-tumbleweed\n')
        state = self.target / 'var/lib/hexagonrpc/sensors/state/registry'
        state.mkdir(parents=True)
        calibration = state / 'gyro-bias'
        calibration.write_bytes(b'newer calibrated state')
        with self.assertRaisesRegex(ValueError, 'preserving its live registry'):
            helper.restore(self.bundle, self.target)
        self.assertEqual(calibration.read_bytes(), b'newer calibrated state')

    def test_rootfs_parent_symlink_cannot_redirect_import(self):
        (self.target / 'etc').mkdir()
        (self.target / 'etc/os-release').touch()
        outside = self.work / 'outside'
        outside.mkdir()
        (self.target / 'var').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'parent escapes'):
            helper.restore(self.bundle, self.target)
        self.assertEqual(list(outside.iterdir()), [])

    def test_image_builder_refuses_an_existing_output(self):
        marker = self.target / 'usr/share/tb322fc/rootfs-build/configured'
        marker.parent.mkdir(parents=True)
        marker.touch()
        image = self.work / 'existing.img'
        image.write_bytes(b'existing user image')
        result = subprocess.run(['python3', str(REPO / 'scripts/opensuse/make-image.py'),
                                 str(self.target), str(image)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(image.read_bytes(), b'existing user image')


if __name__ == '__main__':
    unittest.main()
