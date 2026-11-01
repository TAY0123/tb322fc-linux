#!/usr/bin/env python3
"""Provision verified local firmware into an assembled offline rootfs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--source', type=Path, default=REPO / 'inputs/firmware')
    parser.add_argument('--wifi-source', type=Path,
                        default=REPO / 'sources/freedom/system_files/usr/lib/firmware')
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    record_dir = root / 'usr/share/tb322fc/rootfs-build'
    if os.geteuid() != 0 or root == Path('/') or not (record_dir / 'configured').is_file():
        parser.error('Run as root against an assembled offline rootfs')
    rows = json.loads((REPO / 'firmware.json').read_text())['files']
    wifi = json.loads((REPO / 'configs/freedom-wifi-firmware.json').read_text())
    # Validate every source and destination before copying any local payload.
    for source, entries, size_key in ((args.source, rows, 'size'), (args.wifi_source, wifi['files'], 'bytes')):
        for entry in entries:
            relative = Path(entry['path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError(f'Invalid firmware path: {relative}')
            path = source / relative
            if path.is_symlink() or not path.is_file():
                raise ValueError(f'Expected regular firmware: {path}')
            if path.stat().st_size != entry[size_key] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError(f'Firmware checksum mismatch: {path}')
            target = root / 'usr/lib/firmware' / relative
            if not target.parent.resolve().is_relative_to(root):
                raise ValueError(f'Firmware destination escapes rootfs: {target}')
    for entry in rows:
        target = root / 'usr/lib/firmware' / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        shutil.copyfile(args.source / entry['path'], target)
        target.chmod(0o644)
    zap = root / 'usr/lib/firmware/qcom/sm8750/gen80000_zap.mbn'
    board_zap = zap.parent / 'lenovo/elden/gen80000_zap.mbn'
    if not board_zap.parent.resolve().is_relative_to(root):
        raise ValueError('Board firmware destination escapes rootfs')
    board_zap.parent.mkdir(parents=True, exist_ok=True)
    board_zap.unlink(missing_ok=True)
    shutil.copyfile(zap, board_zap)
    board_zap.chmod(0o644)
    subprocess.run([sys.executable, str(REPO / 'scripts/stage-freedom-wifi-firmware.py'),
                    '--source', str(args.wifi_source), '--root', str(root)], check=True,
                   stdout=subprocess.DEVNULL)
    record = {'android': rows, 'wifi': wifi, 'board_zap': str(board_zap.relative_to(root)),
              'note': 'Local firmware provisioned after RPM installation; not an OBS payload.'}
    (record_dir / 'firmware.json').write_text(json.dumps(record, indent=2) + '\n')
    print(f'Provisioned {len(rows)} local firmware files, {len(wifi["files"])} Wi-Fi files and the board ZAP alias.')


if __name__ == '__main__':
    main()
