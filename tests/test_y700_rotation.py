"""Exercise session policy with old/new kernels and user configuration overrides."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RotationPolicy(unittest.TestCase):
    def policy(self, request=None, supported=False, orientation=None, kernel='7.2.6-20-freedom'):
        with tempfile.TemporaryDirectory() as tmp:
            if supported:
                (Path(tmp)/'freedom-dpu-rotation').touch()
            env = dict(os.environ, TEST_KERNEL=kernel)
            env.pop('Y700_ROTATION', None)
            env.pop('ORIENTATION', None)
            env.pop('FORCE_COMPOSITION_ROTATION', None)
            if request is not None:
                env['Y700_ROTATION'] = request
            if orientation is not None:
                env['ORIENTATION'] = orientation
            result = subprocess.run(['bash', '-c', '''
uname() { printf '%s\\n' "$TEST_KERNEL"; }
source "$1"
y700_rotation_policy "$2"
printf '%s,%s' "${FORCE_COMPOSITION_ROTATION:-unset}" "${ORIENTATION:-unset}"
''', '_', str(ROOT/'packages/gamescope-session/y700-rotation'), tmp],
                                    env=env, text=True, capture_output=True, check=True)
            return result.stdout, result.stderr

    def test_default_uses_dpu_with_matching_kernel(self):
        self.assertEqual(self.policy(supported=True), ('0,right', ''))
        self.assertEqual(self.policy('auto', supported=True), ('0,right', ''))

    def test_default_falls_back_without_matching_kernel(self):
        self.assertEqual(self.policy(), ('1,unset', ''))
        self.assertEqual(self.policy('auto'), ('1,unset', ''))

    def test_dpu_requires_matching_kernel(self):
        output, error = self.policy('dpu')
        self.assertEqual(output, '1,unset')
        self.assertIn('matching updated Freedom kernel', error)
        self.assertEqual(self.policy('dpu', supported=True), ('0,right', ''))

    def test_gpu_override_and_explicit_orientation(self):
        self.assertEqual(self.policy('gpu', supported=True)[0], '1,unset')
        self.assertEqual(self.policy('dpu', True, 'left')[0], '0,left')
        self.assertEqual(self.policy(supported=True, orientation='left')[0], '0,left')
        self.assertEqual(self.policy('gpu', True, kernel='7.3.1-custom')[0], '1,unset')

    def test_other_kernel_default_is_untouched(self):
        self.assertEqual(self.policy(kernel='7.3.1-custom')[0], 'unset,unset')


if __name__ == '__main__':
    unittest.main()
