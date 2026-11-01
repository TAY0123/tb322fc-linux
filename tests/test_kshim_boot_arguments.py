"""Check console defaults and administrator overrides in generated bootargs."""
import importlib.util
from pathlib import Path
import unittest
import tempfile

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

    def test_package_defaults_preserve_debug_and_orientation_overrides(self):
        defaults = ['splash', 'plymouth.panel-rotation=270']
        result = MODULE.boot_arguments('console=tty0', 'PARTLABEL=rootfs', defaults)
        self.assertIn(' splash ', result)
        self.assertIn('plymouth.panel-rotation=270', result)
        source = 'splash=verbose plymouth.panel-rotation=90'
        result = MODULE.boot_arguments(source, 'PARTLABEL=rootfs', defaults).split()
        self.assertNotIn('splash', result)
        self.assertNotIn('plymouth.panel-rotation=270', result)
        self.assertIn('splash=verbose', result)
        self.assertIn('plymouth.panel-rotation=90', result)

    def test_package_defaults_cannot_replace_root_or_escape_kernel_arguments(self):
        for token in ['root=/dev/other', '--', 'splash\ninit=/bin/sh']:
            with self.subTest(token=token), self.assertRaises(ValueError):
                MODULE.boot_arguments('', 'PARTLABEL=rootfs', [token])

    def test_package_defaults_parse_comments_without_shell_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(MODULE.package_boot_defaults(root), [])
            (root/'50-plymouth.conf').write_text('# Package defaults\nsplash\nplymouth.panel-rotation=270\n')
            (root/'ignored.rpmnew').write_text('ignored')
            self.assertEqual(MODULE.package_boot_defaults(root),
                             ['splash', 'plymouth.panel-rotation=270'])

    def test_command_line_stays_single_line(self):
        for separator in ['\n', '\r', '\0']:
            with self.subTest(separator=separator), self.assertRaises(ValueError):
                MODULE.boot_arguments('console=tty0' + separator, 'PARTLABEL=rootfs')


if __name__ == '__main__':
    unittest.main()
