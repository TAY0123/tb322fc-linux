#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Steam update backend for the experimental Tumbleweed installation."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)

def main():
    if '--supports-duplicate-detection' in sys.argv:
        return 0
    if os.geteuid() != 0:
        raise RuntimeError('Run through the privileged steamos-update helper')
    release = Path('/etc/os-release').read_text()
    if 'ID="opensuse-tumbleweed"' not in release and 'ID=opensuse-tumbleweed\n' not in release:
        raise RuntimeError('This updater requires openSUSE Tumbleweed')
    Path('/run/lock').mkdir(exist_ok=True)
    with Path('/run/lock/tb322fc-update.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(['zypper', '--non-interactive', 'refresh'])
        if 'check' in sys.argv:
            result = run(['zypper', '--xmlout', '--non-interactive', 'list-updates'], capture_output=True, text=True)
            updates = ET.fromstring(result.stdout).findall('.//update')
            if not updates:
                return 7
            print('Tumbleweed package updates available')
            return 0
        # The kernel RPM hooks back up modules/boot first and regenerate the
        # candidate image after the transaction. Deployment remains controlled
        # by the owner's existing kShim config; never infer permission here.
        print('0%', flush=True)
        run(['zypper', '--non-interactive', 'dup', '--no-allow-vendor-change'])
        print('100%', flush=True)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('tb322fc-update: '+str(error), file=sys.stderr)
        sys.exit(1)
