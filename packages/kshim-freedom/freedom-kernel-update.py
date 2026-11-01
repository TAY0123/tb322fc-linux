#!/usr/bin/env python3
"""Generate and optionally install kShim boot images for packaged kernels."""
import argparse
import datetime
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def populate_initramfs_hooks(root, directory):
    """Run packaged asset collectors; a failed collector must stop the build."""
    for hook in sorted(directory.glob('*.sh')):
        if hook.is_file() and os.access(hook, os.X_OK):
            run([hook, root])


def initramfs(config, output):
    """Use the already tested minimal F2FS handoff and early GPU firmware."""
    lib = Path('/usr/lib/kshim-freedom')
    with tempfile.TemporaryDirectory(prefix='kshim-initramfs-') as temp:
        root = Path(temp)
        for name in ['bin', 'sbin', 'etc', 'proc', 'sys', 'dev/pts', 'newroot', 'run',
                     'lib/firmware', 'usr/lib/firmware']:
            (root / name).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(lib / 'busybox', root / 'bin/busybox')
        os.chmod(root / 'bin/busybox', 0o755)
        shutil.copyfile(lib / 'init', root / 'init')
        os.chmod(root / 'init', 0o755)
        os.symlink('/bin/busybox', root / 'bin/sh')
        os.symlink('/init', root / 'sbin/init')
        for name, mode, major, minor in [('console', 0o600, 5, 1), ('null', 0o666, 1, 3),
                                         ('tty', 0o666, 5, 0), ('tty0', 0o600, 4, 0),
                                         ('ptmx', 0o666, 5, 2)]:
            os.mknod(root / 'dev' / name, stat.S_IFCHR | mode, os.makedev(major, minor))
        for relative in config['early_firmware']:
            assert not Path(relative).is_absolute() and '..' not in Path(relative).parts
            src = Path('/usr/lib/firmware') / relative
            dst = root / 'lib/firmware' / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_file():
                shutil.copyfile(src, dst)
            elif Path(str(src) + '.zst').is_file():
                with dst.open('wb') as out:
                    run(['zstd', '-dc', str(src) + '.zst'], stdout=out)
            elif Path(str(src) + '.xz').is_file():
                with dst.open('wb') as out:
                    run(['xz', '-dc', str(src) + '.xz'], stdout=out)
            else:
                raise FileNotFoundError(src)
        populate_initramfs_hooks(root, lib / 'initramfs.d')
        # The init script copies early firmware into the real root's view.
        paths = sorted(root.rglob('*'))
        for path in paths:
            os.utime(path, (0, 0), follow_symlinks=False)
        listing = b'\0'.join(os.fsencode(str(p.relative_to(root))) for p in paths)
        archive = subprocess.check_output(['cpio', '--null', '-o', '--format=newc', '--owner=0:0', '--reproducible'],
                                          input=listing + b'\0', cwd=root, stderr=subprocess.DEVNULL)
        with output.open('wb') as out:
            out.write(gzip.compress(archive, mtime=0))


def deploy(image, config, directory):
    """Write the named Linux slot, with verified backup, readback and rollback."""
    compatibles = Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
    if b'lenovo,elden' not in compatibles:
        raise RuntimeError('This boot deployment is configured for lenovo,elden only')
    uuid = config['root_partuuid']
    root = Path('/dev/disk/by-partuuid') / uuid
    actual = subprocess.check_output(['findmnt', '-no', 'SOURCE', '/'], text=True).strip()
    if root.resolve() != Path(actual).resolve():
        raise RuntimeError('Configured root PARTUUID differs from the running root')
    # This project reserves A for Linux; B and recovery are never deployment targets.
    dev = Path('/dev/disk/by-partlabel/boot_a')
    if not stat.S_ISBLK(dev.stat().st_mode):
        raise RuntimeError('boot_a is not a block device')
    size = int(subprocess.check_output(['blockdev', '--getsize64', str(dev)]))
    if size != image.stat().st_size or size != 100663296:
        raise RuntimeError('Image does not match the boot_a partition size')
    parent = Path('/dev') / subprocess.check_output(['lsblk', '-ndo', 'PKNAME', str(dev.resolve())], text=True).strip()
    assert parent.is_block_device() and parent != dev.resolve()
    before = digest(dev)
    backup = directory / 'boot_a-before.img'
    with dev.open('rb') as src, backup.open('xb') as dst:
        shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if digest(backup) != before:
        raise RuntimeError('Rollback backup verification failed')
    flags = {str(p): int(subprocess.check_output(['blockdev', '--getro', str(p)])) for p in [parent, dev]}

    def write(source):
        with source.open('rb') as src, dev.open('r+b', buffering=0) as dst:
            while chunk := src.read(4 * 1024 * 1024):
                if dst.write(chunk) != len(chunk):
                    raise OSError('Short boot write')
            os.fsync(dst.fileno())

    try:
        run(['blockdev', '--setrw', parent])
        run(['blockdev', '--setrw', dev])
        try:
            write(image)
            if digest(dev) != digest(image):
                raise RuntimeError('boot_a readback differs from the generated image')
        except BaseException:
            write(backup)
            if digest(dev) != before:
                raise RuntimeError('boot_a rollback readback failed')
            raise
    finally:
        for path in [str(dev), str(parent)]:
            run(['blockdev', '--setro' if flags[path] else '--setrw', path])
    return dict(before=before, after=digest(dev), backup=str(backup), readback_verified=True)


def backup_kernel(release, modules, state):
    """Keep modules as well as boot bytes before pacman removes an old release."""
    directory = state / 'rollback' / release
    if (directory / 'backup.json').exists():
        return
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / 'modules.tar.zst'
    run(['tar', '--zstd', '--exclude=' + release + '/build', '-cf', archive,
         '-C', '/usr/lib/modules', release])
    dev = Path('/dev/disk/by-partlabel/boot_a')
    image = directory / 'boot_a.img'
    with dev.open('rb') as src, image.open('wb') as dst:
        shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    sha = digest(dev)
    if digest(image) != sha:
        raise RuntimeError('Pre-upgrade boot backup differs from boot_a')
    result = dict(release=release, modules=str(archive), modules_sha256=digest(archive),
                  boot=str(image), boot_sha256=sha)
    (directory / 'backup.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Saved kernel rollback files:', directory)


def installed_kernel_releases(config, module_root=Path('/usr/lib/modules')):
    """Ignore retained rollback trees when a module-only hook has no release."""
    releases = set()
    for path in module_root.glob('*/pkgbase'):
        if path.read_text().strip() != config['pkgbase']:
            continue
        owner = subprocess.run(['pacman', '-Qqo', '--', str(path)],
                               capture_output=True, text=True, timeout=10)
        if owner.returncode == 1:  # Preserved module tree, no installed package.
            continue
        owner.check_returncode()
        if owner.stdout.strip() == config['pkgbase']:
            releases.add(path.parent.name)
    return releases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', help='Packaged kernel release; otherwise derive from hook targets')
    parser.add_argument('--hook', action='store_true')
    parser.add_argument('--backup-hook', action='store_true', help='Pre-transaction backup before removal')
    parser.add_argument('--deploy', action='store_true', help='Install the verified image to Linux boot_a')
    parser.add_argument('--stage-only', action='store_true', help='Override automatic deployment')
    parser.add_argument('--config', type=Path, default=Path('/etc/kshim-freedom/config.json'))
    parser.add_argument('--lock-fd', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root')
    if not args.config.exists() and (args.hook or args.backup_hook):
        print('kShim is not configured; no boot image was changed.')
        return
    config = json.loads(args.config.read_text())
    state = Path('/var/lib/kshim-freedom')
    state.mkdir(mode=0o700, exist_ok=True)
    os.umask(0o077)
    if args.lock_fd is None:
        lock = (state / 'update.lock').open('a+')
        fcntl.flock(lock, fcntl.LOCK_EX)
    else:
        lock = os.fdopen(os.dup(args.lock_fd), 'r+')
        expected, inherited = (state / 'update.lock').stat(), os.fstat(lock.fileno())
        if (expected.st_dev, expected.st_ino) != (inherited.st_dev, inherited.st_ino):
            raise ValueError('Inherited lock does not refer to the kernel update lock')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    targets = sys.stdin.read().splitlines() if (args.hook or args.backup_hook) else []
    releases = {args.kernel} if args.kernel else set()
    for target in targets:
        m = re.match(r'usr/lib/modules/([^/]+)/', target)
        if m:
            releases.add(m[1])
    if not releases:
        releases = installed_kernel_releases(config)
    if args.backup_hook:
        for release in releases:
            if not re.fullmatch(r'[A-Za-z0-9_.+\-]+', release):
                raise ValueError('Invalid kernel release')
            modules = Path('/usr/lib/modules') / release
            if (modules / 'pkgbase').exists() and (modules / 'pkgbase').read_text().strip() == config['pkgbase']:
                backup_kernel(release, modules, state)
        return
    lib = Path('/usr/lib/kshim-freedom')
    stock = Path(config['stock_boot'])
    if digest(stock) != config['stock_boot_sha256']:
        raise RuntimeError('Stock boot differs from the configured factory image')
    key = Path(config['avb_key'])
    if key.stat().st_mode & 0o077:
        raise PermissionError('AVB private key must not be group/world accessible')
    for release in sorted(releases):
        if not re.fullmatch(r'[A-Za-z0-9_.+\-]+', release):
            raise ValueError('Invalid kernel release')
        modules = Path('/usr/lib/modules') / release
        if not (modules / 'pkgbase').exists() or (modules / 'pkgbase').read_text().strip() != config['pkgbase']:
            continue
        # If the configured external module failed to build, retain the old boot.
        for module in config.get('required_modules', []):
            run(['modinfo', '-k', release, module], stdout=subprocess.DEVNULL)
        directory = state / 'candidates' / release / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        directory.mkdir(parents=True)
        initrd = directory / 'initramfs.cpio.gz'
        initramfs(config, initrd)
        unsigned = directory / 'unsigned'
        run([sys.executable, lib / 'build-kshim-arch.py', '--manifest', lib / 'freedom-sources.json',
             '--builder', lib / 'kshim-build-boot.py', '--stock-boot', stock, '--runtime', lib / 'kShimC.bin',
             '--image', modules / 'vmlinuz', '--dtb', modules / 'dtbs/qcom/sm8750-lenovo-elden.dtb',
             '--initrd', initrd, '--packer', lib / 'MultiBootKernelPatcher', '--unpacker', lib / 'UnpackTool',
             '--repacker', lib / 'repack_boot_v4.py', '--avbtool', lib / 'avbtool.py',
             '--root-partuuid', config['root_partuuid'], '--cmdline', config['cmdline'], '--out', unsigned])
        image = directory / 'signed/boot.img'
        run([sys.executable, lib / 'sign-kshim-boot.py', '--image', unsigned / 'arch/boot.img',
             '--stock-boot', stock, '--key', key, '--out', image, '--avbtool', lib / 'avbtool.py'])
        metadata = json.loads((modules / 'build-manifest.json').read_text())
        result = dict(release=release, kernel_build_id=metadata['build_id'], image=str(image), sha256=digest(image), deployed=False)
        if not args.stage_only and (args.deploy or config.get('deploy_boot_a', False)):
            result['flash'] = deploy(image, config, directory)
            result['deployed'] = True
        (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        temporary = state / '.latest.json'
        temporary.write_text(json.dumps(result, indent=2) + '\n')
        os.replace(temporary, state / 'latest.json')
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
