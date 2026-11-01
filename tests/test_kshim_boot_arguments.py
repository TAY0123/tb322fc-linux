"""Check console defaults and administrator overrides in generated bootargs."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'kshim_boot', ROOT / 'packages/kshim-freedom/build-kshim-arch.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BootArguments(unittest.TestCase):
    def test_existing_device_config_gains_readable_console(self):
        result = MODULE.boot_arguments(
            'console=tty0 fbcon=map:0 fbcon=font:TER16x32 root=PARTUUID=old',
            'PARTLABEL=rootfs').split()
        self.assertIn('fbcon=rotate:3', result)
        self.assertIn('vconsole.font=latarcyrheb-sun32', result)
        self.assertEqual(result.count('fbcon=font:TER16x32'), 1)
        self.assertEqual([x for x in result if x.startswith('root=')],
                         ['root=PARTLABEL=rootfs'])

    def test_combined_fbcon_and_userspace_font_overrides_survive(self):
        source = 'console=tty0 fbcon=map:0,rotate:1,font:VGA8x16 vconsole.font=custom'
        result = MODULE.boot_arguments(source, 'PARTLABEL=rootfs')
        self.assertEqual(result, source + ' root=PARTLABEL=rootfs')

    def test_defaults_are_idempotent(self):
        result = MODULE.boot_arguments('console=tty0', 'PARTLABEL=rootfs')
        self.assertEqual(MODULE.boot_arguments(result, 'PARTLABEL=rootfs'), result)

    def test_command_line_stays_single_line(self):
        for separator in ['\n', '\r', '\0']:
            with self.subTest(separator=separator), self.assertRaises(ValueError):
                MODULE.boot_arguments('console=tty0' + separator, 'PARTLABEL=rootfs')


if __name__ == '__main__':
    unittest.main()
