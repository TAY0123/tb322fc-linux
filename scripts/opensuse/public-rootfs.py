#!/usr/bin/env python3
"""Refuse to export a provisioned tablet as a public installation image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]


def audit(root, firmware=True):
    root = Path(root).resolve(strict=True)
    if root == Path('/') or not (root / 'usr/share/tb322fc/rootfs-build/configured').is_file():
        raise ValueError('Expected a configured offline staging root')
    errors = []

    def path(name):
        p = root / name
        if not p.parent.resolve().is_relative_to(root):
            raise ValueError(f'Path escapes staging root: {name}')
        return p

    def absent(name):
        p = path(name)
        if p.exists() or p.is_symlink():
            errors.append(f'private/provisioned state: {name}')

    for name in ('etc/plasma-setup-done', 'etc/kshim-freedom/config.json',
                 'var/lib/tb322fc/first-user-ready',
                 'var/lib/tb322fc/first-user-authorized-keys',
                 'var/lib/alsa/asound.state', 'var/lib/systemd/random-seed',
                 'var/lib/NetworkManager/secret_key', 'var/lib/dbus/machine-id'):
        absent(name)
    for name in ('home', 'etc/NetworkManager/system-connections',
                 'var/lib/bluetooth', 'var/lib/kshim-freedom', 'var/lib/sss',
                 'var/lib/AccountsService/users', 'var/lib/AccountsService/icons',
                 'var/lib/systemd/coredump', 'var/lib/hexagonrpc', 'var/log/journal'):
        base = path(name)
        if base.is_symlink():
            errors.append(f'private state directory is a symlink: {name}')
            continue
        if not base.exists():
            continue
        for p in base.rglob('*'):
            if (name == 'var/lib/hexagonrpc' and p == base / 'socinfo'
                    and p.is_symlink() and os.readlink(p) == '/sys/devices/soc0'):
                continue
            if p.is_symlink() or not p.is_dir():
                errors.append(f'private data: {p.relative_to(root)}')
    machine_id = path('etc/machine-id')
    if machine_id.is_symlink() or machine_id.read_text().strip() not in ('', 'uninitialized'):
        errors.append('machine-id must be empty or uninitialized')
    passwd = path('etc/passwd')
    for line in passwd.read_text().splitlines():
        fields = line.split(':')
        if len(fields) != 7:
            errors.append('invalid passwd record')
        elif 1000 <= int(fields[2]) < 65534:
            errors.append(f'pre-created human account: {fields[0]}')
    shadow = path('etc/shadow')
    for line in shadow.read_text().splitlines():
        fields = line.split(':')
        if len(fields) < 2 or not fields[1].startswith(('!', '*')):
            errors.append(f'unlocked or preset password: {fields[0]}')

    # Walk without following directory links, including the special socinfo
    # link above. No host /sys or user home is ever inspected through a link.
    private_names = re.compile(r'^(authorized_keys\d*|known_hosts(?:\.old)?|'
                               r'id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|'
                               r'ssh_host_.+_key(?:\.pub)?|hexagonrpc\.tar\..+|'
                               r'persist(?:\.[^.]+)?|first-user-authorized-keys)$')
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            if private_names.fullmatch(name):
                errors.append(f'private file: {(Path(directory) / name).relative_to(root)}')
    for name in ('etc/sudoers', *[str(p.relative_to(root)) for p in path('etc/sudoers.d').glob('*')]):
        p = path(name)
        if p.is_symlink():
            errors.append(f'sudo configuration symlink: {name}')
        elif p.is_file() and re.search(r'(?m)^[^#\n]*\bNOPASSWD\s*:', p.read_text()):
            errors.append(f'passwordless sudo policy: {name}')
    # AVB keys and other debug credentials must not hide under arbitrary names.
    for name in ('root', 'home', 'etc'):
        base = path(name)
        for directory, _, files in os.walk(base, followlinks=False):
            for filename in files:
                p = Path(directory) / filename
                if p.is_symlink() or not p.is_file() or p.stat().st_size > 4 * 1024 * 1024:
                    continue
                data = p.read_bytes()
                if re.search(rb'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----', data):
                    errors.append(f'private key: {p.relative_to(root)}')
    if errors:
        raise ValueError('Public rootfs audit failed:\n  ' + '\n  '.join(sorted(set(errors))))
    if firmware:
        rows = json.loads((REPO / 'firmware.json').read_text())['files']
        wifi = json.loads((REPO / 'configs/freedom-wifi-firmware.json').read_text())['files']
        for row in [*rows, *wifi]:
            p = path('usr/lib/firmware/' + row['path'])
            if p.is_symlink() or not p.is_file():
                raise ValueError(f'Missing regular model firmware: {row["path"]}')
            if hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError(f'Model firmware hash mismatch: {row["path"]}')
    return {'public': True, 'personal_calibration': False, 'ssh_authorizations': False,
            'preset_human_accounts': False, 'model_firmware_verified': firmware}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), indent=2))
