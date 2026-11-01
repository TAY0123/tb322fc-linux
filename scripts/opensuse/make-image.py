#!/usr/bin/env python3
"""Copy an assembled rootfs into a NEW regular F2FS image using the TWRP profile."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import uuid

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('public_rootfs', Path(__file__).with_name('public-rootfs.py'))
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('image', type=Path)
    parser.add_argument('--size-gib', type=int, default=24)
    parser.add_argument('--compress', action='store_true')
    parser.add_argument('--namespace', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    output = args.image.absolute()
    if os.geteuid() != 0:
        parser.error('Run as root')
    if root == Path('/') or not (root / 'usr/share/tb322fc/rootfs-build/configured').is_file():
        parser.error('Expected a configured staging root; refusing the host root')
    if output.exists() or output.is_symlink():
        parser.error('Output must be a NEW regular file, never an existing image or block device')
    if output.resolve().is_relative_to(root):
        parser.error('The image must be outside the source rootfs')
    if args.size_gib < 1:
        parser.error('Image size must be at least 1 GiB')
    # Import this tablet's calibration only after installing the generic image.
    public.audit(root)
    kernels = list((root / 'usr/lib/modules').glob('*/tb322fc-build.json'))
    if len(kernels) != 1:
        parser.error('Expected one selected TB322FC kernel in the staging root')
    kernel_config = (kernels[0].parent / 'config').read_text().splitlines()
    if 'CONFIG_QFMT_V2=y' not in kernel_config:
        parser.error('The TWRP-style F2FS image needs CONFIG_QFMT_V2=y in its boot kernel; '
                     'quota formats must be available before the rootfs is mounted')
    if not args.namespace:
        os.execvp('unshare', ['unshare', '--mount', '--propagation', 'private',
                             sys.executable, __file__, '--namespace', *sys.argv[1:]])
    config = json.loads((REPO / 'configs/opensuse/rootfs.json').read_text())['f2fs']
    fs_uuid = str(uuid.uuid4())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise RuntimeError('Output is not a regular file')
        stream.truncate(args.size_gib * 1024**3)
    # -t0 applies only to construction of a sparse image. It is not a runtime
    # mount option; the final root still enables discard just like TWRP /data.
    run('mkfs.f2fs', *config['mkfs_args'], '-t', '0', '-l', config['label'], '-U', fs_uuid, output)
    with tempfile.TemporaryDirectory(prefix='f2fs-mount-', dir=output.parent) as directory:
        mountpoint = Path(directory)
        run('mount', '-t', 'f2fs', '-o', 'loop,' + ','.join(config['mount_options']), output, mountpoint)
        try:
            probe = mountpoint / '.capability-probe'
            probe.touch()
            capability = struct.pack('<5I', 0x02000001, 1 << 23, 0, 0, 0)
            try:
                os.setxattr(probe, 'security.capability', capability)
                if os.getxattr(probe, 'security.capability') != capability:
                    raise RuntimeError('File capability round-trip failed')
            except OSError as error:
                raise RuntimeError('The image-writing kernel needs CONFIG_F2FS_FS_SECURITY=y; '
                                   'this host cannot preserve executable capabilities. '
                                   'Use a suitable native Linux host (the TB322FC kernel enables it).') from error
            finally:
                probe.unlink()
            # cp -a preserves hardlinks, numeric owners, ACLs and file capabilities;
            # sload.f2fs does not preserve all of these rootfs properties.
            # Request xattrs explicitly as well: plain -a can silently ignore an
            # unsupported security namespace, e.g. the default WSL2 F2FS module.
            run('cp', '-a', '--preserve=xattr', '--reflink=never', str(root) + '/.', mountpoint)
            (mountpoint / 'etc/fstab').write_text(
                '# kShim selects the partition by PARTUUID; systemd applies these root options.\n'
                f"UUID={fs_uuid} / f2fs {','.join(config['mount_options'])} 0 1\n"
                'binder /dev/binderfs binder defaults,nofail 0 0\n')
            (mountpoint / '.tb322fc-opensuse-build').unlink(missing_ok=True)
            record = {'uuid': fs_uuid, 'size_bytes': args.size_gib * 1024**3, **config}
            (mountpoint / 'usr/share/tb322fc/rootfs-build/filesystem.json').write_text(json.dumps(record, indent=2) + '\n')
            run('sync', '-f', mountpoint)
        finally:
            run('umount', mountpoint)
    run('fsck.f2fs', '-f', output)
    run('blkid', '-p', output)
    if args.compress:
        run('zstd', '-T0', '-3', '--keep', output, '-o', str(output) + '.zst')
    artifact = Path(str(output) + '.zst') if args.compress else output
    with artifact.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    artifact.with_name(artifact.name + '.sha256').write_text(f'{checksum}  {artifact.name}\n')
    output.with_name(output.name + '.json').write_text(json.dumps(record, indent=2) + '\n')
    print(f'Created {artifact}; no block device was written.')


if __name__ == '__main__':
    main()
