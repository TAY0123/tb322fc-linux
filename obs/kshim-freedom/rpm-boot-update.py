#!/usr/bin/python3
"""Refresh configured kShim boot once, after an RPM transaction finishes."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
from pathlib import Path
import subprocess
import sys


def load_updater(path):
    loader = SourceFileLoader('kshim_rpm_updater', str(path))
    spec = spec_from_loader(loader.name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def automatic_update(config_path=Path('/etc/kshim-freedom/config.json'),
                     updater_path=Path('/usr/bin/freedom-kernel-update'),
                     build_marker=Path('/.buildenv'),
                     compatible=Path('/sys/firmware/devicetree/base/compatible')):
    # Public rootfs assembly has no per-device configuration. Keep boot writes
    # opt-in and limited to a running Elden; the updater also validates root,
    # inputs, required KMPs, signing, backup and partition readback.
    if build_marker.exists() or not config_path.exists():
        return
    config = json.loads(config_path.read_text())
    if config.get('deploy_boot_a') is not True:
        return
    if not compatible.exists() or b'lenovo,elden' not in compatible.read_bytes().split(b'\0'):
        return
    updater = load_updater(updater_path)
    releases = updater.installed_kernel_releases(config)
    if not releases:
        return
    # Multiversion RPMs can coexist. Use version order (30 > 9), and only the
    # installed flavor selected by the updater's RPM ownership checks.
    release = subprocess.check_output(
        ['sort', '-V'], input='\n'.join(releases) + '\n', text=True,
        env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}).splitlines()[-1]
    print(f'kShim: updating boot_a for {release}', flush=True)
    subprocess.run([str(updater_path), '--config', str(config_path),
                    '--kernel', release, '--hook'], input='', text=True, check=True)


if __name__ == '__main__':
    # RPM supplies matching paths; selection must use all installed kernels,
    # including when only kShim defaults or an external module was updated.
    sys.stdin.read()
    automatic_update()
