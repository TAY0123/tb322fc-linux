#!/usr/bin/env python3
"""Build a generic signed boot.img from OBS kernel/kShim packages; never flash."""
import argparse
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile



def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inside():
    """Run only inside the disposable build root with explicit mounted inputs."""
    config = json.loads(Path('/mnt/boot.json').read_text())
    lib = Path('/usr/lib/kshim-freedom')
    out = Path('/mnt/output')
    out.mkdir()
    # Reuse the packaged F2FS handoff/firmware assembler, never its deploy path.
    spec = importlib.util.spec_from_loader('updater', SourceFileLoader('updater', '/usr/bin/freedom-kernel-update'))
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    initrd = out / 'initramfs.cpio.gz'
    updater.initramfs(config, initrd)
    release = config['kernel_release']
    run(sys.executable, '/mnt/build-kshim-arch.py', '--manifest', lib / 'freedom-sources.json',
        '--builder', lib / 'kshim-build-boot.py', '--stock-boot', '/mnt/boot.img',
        '--runtime', lib / 'kShimC.bin', '--image', f'/boot/Image-{release}',
        '--dtb', f'/boot/dtb-{release}/qcom/sm8750-lenovo-elden.dtb',
        '--initrd', initrd, '--packer', lib / 'MultiBootKernelPatcher',
        '--unpacker', lib / 'UnpackTool', '--repacker', lib / 'repack_boot_v4.py',
        '--avbtool', lib / 'avbtool.py', '--root-partlabel', 'rootfs',
        '--cmdline', config['cmdline'], '--out', out / 'unsigned')
    run(sys.executable, lib / 'sign-kshim-boot.py', '--image', out / 'unsigned/arch/boot.img',
        '--stock-boot', '/mnt/boot.img', '--key', '/mnt/avb-key.pem',
        '--out', out / 'signed/boot.img', '--avbtool', lib / 'avbtool.py')


def main():
    REPO = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path, help='New output directory')
    parser.add_argument('--stock-boot', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True, help='Pinned AOSP RSA4096 test key accepted by this model')
    parser.add_argument('--namespace', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root; x86_64 hosts also need qemu-aarch64-static')
    root, output = args.root.resolve(strict=True), args.output.absolute()
    stock, key = args.stock_boot.resolve(strict=True), args.key.resolve(strict=True)
    config = json.loads((REPO / 'configs/opensuse/boot.json').read_text())
    if root == Path('/') or not (root / '.tb322fc-opensuse-build').is_file():
        parser.error('Expected a marked offline staging root')
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(root):
        parser.error('Output must be a new directory outside the staging root')
    if not stock.is_file() or digest(stock) != config['stock_boot_sha256']:
        parser.error('Stock Android boot differs from the pinned model image')
    if not key.is_file() or key.stat().st_mode & 0o077 or key.is_relative_to(root):
        parser.error('Signing key must be private and outside the staging root')
    if digest(key) != config['avb_test_key_sha256']:
        parser.error('Use the pinned AOSP test key; arbitrary AVB keys are not compatible')
    if config['root_selector'] != 'PARTLABEL=rootfs':
        parser.error('Public boot must select the generic rootfs partition label')
    metadata = list((root / 'usr/lib/modules').glob('*/tb322fc-build.json'))
    if len(metadata) != 1:
        parser.error('Expected exactly one installed TB322FC kernel')
    kernel = json.loads(metadata[0].read_text())
    if kernel['package'] != 'kernel-freedom' or kernel['release'] != metadata[0].parent.name:
        parser.error('Unexpected kernel metadata')
    config['kernel_release'] = kernel['release']
    if not args.namespace:
        os.execvp('unshare', ['unshare', '--mount', '--propagation', 'private',
                             sys.executable, __file__, '--namespace', *sys.argv[1:]])
    os.umask(0o022)
    output.parent.mkdir(parents=True, exist_ok=True)
    mountpoint = root / 'mnt'
    if mountpoint.is_symlink() or not mountpoint.is_dir() or any(mountpoint.iterdir()):
        parser.error('The offline root needs an empty real /mnt directory')
    with tempfile.TemporaryDirectory(prefix='boot-build-', dir=output.parent) as temporary:
        work = Path(temporary)
        (work / 'boot.json').write_text(json.dumps(config))
        shutil.copyfile(__file__, work / 'make-boot.py')
        shutil.copyfile(REPO / 'packages/kshim-freedom/build-kshim-arch.py', work / 'build-kshim-arch.py')
        # avbtool resolves the stock descriptor as the sibling boot.img.
        for name in ('boot.img', 'avb-key.pem'):
            (work / name).touch(mode=0o600)
        mounts = []
        try:
            run('mount', '--bind', work, mountpoint)
            mounts.append(mountpoint)
            for source, name in ((stock, 'boot.img'), (key, 'avb-key.pem')):
                target = mountpoint / name
                run('mount', '--bind', source, target)
                mounts.append(target)
                run('mount', '-o', 'remount,bind,ro', target)
            run(REPO / 'scripts/opensuse/in-rootfs.sh', root,
                'python3', '/mnt/make-boot.py', '--inside')
        finally:
            for target in reversed(mounts):
                run('umount', target)
        image = work / 'output/signed/boot.img'
        if image.stat().st_size != 100663296:
            raise ValueError('Unexpected boot image size')
        signature = json.loads((image.parent / 'signing.json').read_text())
        output.mkdir()
        shutil.copyfile(image, output / 'boot.img')
        report = {'public': True, 'root_selector': config['root_selector'],
                  'kernel_release': kernel['release'], 'kernel_build_id': kernel['build_id'],
                  'sha256': digest(image), 'stock_boot_sha256': config['stock_boot_sha256'],
                  'avb_public_key_sha1': signature['signed_public_key'],
                  'private_key_in_image': False, 'flashed': False}
        (output / 'boot.json').write_text(json.dumps(report, indent=2) + '\n')
        (output / 'boot.img.sha256').write_text(f'{report["sha256"]}  boot.img\n')
    print(f'Created {output / "boot.img"}; no device partition was accessed')


if __name__ == '__main__':
    if sys.argv[1:] == ['--inside']:
        inside()
    else:
        main()
