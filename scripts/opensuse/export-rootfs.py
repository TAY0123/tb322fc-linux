#!/usr/bin/env python3
"""Export an audited generic rootfs tarball, preserving ACLs and capabilities."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('public_rootfs', Path(__file__).with_name('public-rootfs.py'))
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path, help='New .tar.zst file outside the rootfs')
    args = parser.parse_args()
    root, output = args.root.resolve(strict=True), args.output.absolute()
    if os.geteuid() != 0:
        parser.error('Run as root to preserve ownership, ACLs and capabilities')
    if not output.name.endswith('.tar.zst') or output.resolve().is_relative_to(root):
        parser.error('Output must be a .tar.zst outside the source root')
    for p in (output, output.with_name(output.name + '.part'),
              output.with_name(output.name + '.sha256'), output.with_name(output.name + '.json')):
        if p.exists() or p.is_symlink():
            parser.error(f'Refusing to replace {p}')
    # No mount may hide private content or include the builder's /proc, /dev,
    # /sys or /run. Assemble runs in namespaces which are gone at this point.
    for row in Path('/proc/self/mountinfo').read_text().splitlines():
        mounted = Path(row.split()[4].replace('\\040', ' ').replace('\\134', '\\'))
        if mounted != root and mounted.is_relative_to(root):
            parser.error(f'Staging tree still contains a mount: {mounted}')
    report = public.audit(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + '.part')
    subprocess.run(['tar', '--numeric-owner', '--xattrs', '--xattrs-include=*', '--acls',
                    '--sparse', '--one-file-system', '--use-compress-program=zstd -T0 -3',
                    '-cpf', str(partial), '-C', str(root), '.'], check=True)
    public.audit(root)
    with partial.open('rb') as stream:
        report['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    report.update(format='tar.zst', firmware_manifest='firmware.json',
                  boot_image_included=False, calibration_import='after installation only')
    partial.rename(output)
    output.chmod(0o644)
    output.with_name(output.name + '.sha256').write_text(f'{report["sha256"]}  {output.name}\n')
    output.with_name(output.name + '.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Exported audited public rootfs: {output}')


if __name__ == '__main__':
    main()
