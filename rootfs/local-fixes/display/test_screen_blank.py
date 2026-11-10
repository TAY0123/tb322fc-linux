import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('blank', Path(__file__).with_name('y700_screen_blank.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScreenBlankTests(unittest.TestCase):
    def setUp(self):
        self.value = 1188
        self.saved = None
        self.grabbed = False
        self.clock = 1.0
        self.controller = module.BlankController(lambda: self.value, self.write, self.save,
                                                 self.clear, self.grab, lambda: self.clock)
        self.contact = module.ContactState()

    def write(self, value):
        self.value = value

    def save(self, value):
        self.saved = value

    def clear(self):
        self.saved = None

    def grab(self, enabled):
        self.grabbed = enabled

    def frame(self, *events):
        for event in events:
            self.contact.event(*event)
        self.controller.touch_frame(self.contact)

    def test_first_tap_restores_exact_brightness_and_is_consumed_through_release(self):
        self.controller.off()
        self.assertEqual((self.value, self.saved, self.grabbed), (0, 1188, True))
        self.clock += 1
        self.frame((1, 330, 1), (3, 47, 0), (3, 57, 25))
        self.assertEqual((self.value, self.saved, self.grabbed), (1188, None, True))
        self.frame((3, 57, -1), (1, 330, 0))
        self.assertFalse(self.grabbed)

    def test_waking_two_fingers_remains_grabbed_until_both_release(self):
        self.controller.off()
        self.clock += 1
        self.frame((3, 47, 0), (3, 57, 25), (3, 47, 1), (3, 57, 26))
        self.assertFalse(self.controller.blank)
        self.frame((3, 47, 0), (3, 57, -1))
        self.assertTrue(self.grabbed)
        self.frame((3, 47, 1), (3, 57, -1))
        self.assertFalse(self.grabbed)

    def test_launcher_touch_does_not_immediately_wake_the_blank_screen(self):
        self.frame((1, 330, 1))
        self.controller.off(held=self.contact.down)
        self.clock += 1
        self.frame((3, 47, 0), (3, 57, 20))
        self.assertTrue(self.controller.blank)
        self.frame((3, 57, -1), (1, 330, 0))
        self.assertTrue(self.controller.blank)
        self.frame((1, 330, 1))
        self.assertFalse(self.controller.blank)

    def test_stop_resume_or_keyboard_wake_releases_touch_and_restores(self):
        self.controller.off()
        self.controller.on()
        self.assertEqual((self.value, self.saved, self.grabbed), (1188, None, False))

    def test_repeated_off_does_not_replace_saved_brightness_with_zero(self):
        self.controller.off()
        self.controller.off()
        self.assertEqual(self.saved, 1188)
        self.controller.on()
        self.assertEqual(self.value, 1188)

    def test_failed_touch_grab_leaves_screen_lit_and_no_stale_state(self):
        def fail(enabled):
            if enabled:
                raise OSError('Already grabbed')
        self.controller.grab = fail
        with self.assertRaises(OSError):
            self.controller.off()
        self.assertEqual((self.value, self.saved, self.controller.blank), (1188, None, False))

    def test_failed_blank_write_restores_brightness_and_releases_touch(self):
        def write(value):
            if value == 0:
                raise OSError('Write failed')
            self.write(value)
        self.controller.write = write
        with self.assertRaises(OSError):
            self.controller.off()
        self.assertEqual((self.value, self.saved, self.grabbed), (1188, None, False))

    def test_failed_restore_retains_recovery_and_touch_grab(self):
        self.controller.off()
        def fail(value):
            raise OSError('Write failed')
        self.controller.write = fail
        with self.assertRaises(OSError):
            self.controller.on()
        self.assertEqual((self.saved, self.controller.blank, self.grabbed), (1188, True, True))


if __name__ == '__main__':
    unittest.main()
