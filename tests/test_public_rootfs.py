"""Public artifacts must never inherit a provisioned tablet's identity/data."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts/opensuse' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


public = load('public-rootfs')


class PublicRootfs(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'root'
        self.write('usr/share/tb322fc/rootfs-build/configured')
        self.write('etc/machine-id')
        self.write('etc/passwd', 'root:x:0:0:root:/root:/bin/bash\nplasma-setup:x:499:499::/var/lib/plasma-setup:/bin/bash\n')
        self.write('etc/shadow', 'root:!:0:0:99999:7:::\nplasma-setup:!:0:0:99999:7:::\n')

    def write(self, name, data=''):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def audit(self):
        return public.audit(self.root, firmware=False)

    def test_empty_sensor_scaffolding_with_socinfo_link_is_public(self):
        data = self.root / 'var/lib/hexagonrpc'
        (data / 'sensors/state/registry').mkdir(parents=True)
        (data / 'socinfo').symlink_to('/sys/devices/soc0')
        self.assertTrue(self.audit()['public'])

    def test_refuses_calibration_even_without_import_manifest(self):
        self.write('var/lib/hexagonrpc/sensors/state/registry/gyro-bias', 'private calibration')
        with self.assertRaisesRegex(ValueError, 'private data'):
            self.audit()

    def test_rejects_ssh_trust_host_keys_wifi_and_signing_key(self):
        for name, data in [('root/.ssh/authorized_keys', 'test public key'),
                           ('etc/ssh/ssh_host_ed25519_key', 'test host key'),
                           ('var/lib/tb322fc/first-user-authorized-keys', 'test key'),
                           ('etc/NetworkManager/system-connections/home.nmconnection', 'psk=test'),
                           ('etc/kshim-freedom/avb-key.pem', '-----BEGIN PRIVATE KEY-----\nfake\n')]:
            with self.subTest(name=name):
                path = self.write(name, data)
                with self.assertRaises(ValueError):
                    self.audit()
                path.unlink()

    def test_refuses_personal_account_identity_password_and_sudo(self):
        for name, data in [('etc/passwd', 'owner:x:1000:1000::/home/owner:/bin/bash\n'),
                           ('etc/machine-id', 'a' * 32),
                           ('etc/shadow', 'root:$6$not-a-real-hash:0:0:99999:7:::\n'),
                           ('etc/sudoers.d/debug', '%wheel ALL=(ALL) NOPASSWD: ALL\n')]:
            with self.subTest(name=name):
                path = self.root / name
                previous = path.read_text() if path.exists() else None
                self.write(name, data)
                with self.assertRaises(ValueError):
                    self.audit()
                if previous is None:
                    path.unlink()
                else:
                    path.write_text(previous)

    def test_does_not_follow_private_directory_symlink(self):
        base = self.root / 'var/lib'
        base.mkdir(parents=True)
        (base / 'hexagonrpc').symlink_to(self.root.parent)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.audit()

    def test_requires_verified_model_firmware_for_real_export(self):
        with self.assertRaisesRegex(ValueError, 'Missing regular model firmware'):
            public.audit(self.root)



if __name__ == '__main__':
    unittest.main()
