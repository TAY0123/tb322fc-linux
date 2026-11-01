#!/usr/bin/env python3
"""Prepare a verified AArch64 staging tree; install only after OBS is current.

This tool never writes a block device. Use make-image.py for a new local F2FS image.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
CONFIG = json.loads((REPO / 'configs/opensuse/rootfs.json').read_text())


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(url, path):
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + '.part')
    run('curl', '--fail', '--location', '--http1.1', '--retry', '4',
        '--retry-all-errors', '--proto', '=https', '--proto-redir', '=https',
        '--continue-at', '-', '--output', partial, url)
    partial.rename(path)


def verify_key(key, fingerprint, gnupg):
    listing = run('gpg', '--homedir', gnupg, '--batch', '--with-colons',
                  '--show-keys', key, capture_output=True, text=True).stdout
    # The first fingerprint belongs to the primary key, not a signing subkey.
    actual = next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
    if actual != fingerprint:
        raise RuntimeError(f'Unexpected signing key: {actual}')
    run('gpg', '--homedir', gnupg, '--batch', '--import', key)


def prepare(work):
    cache, reference = work / 'cache', work / 'reference'
    reference.mkdir(parents=True, exist_ok=True)
    gnupg = work / 'gnupg'
    gnupg.mkdir(mode=0o700, exist_ok=True)
    base = CONFIG['bootstrap']
    archive = cache / Path(urlparse(base['url']).path).name
    for url, path in (
        (base['url'], archive),
        (base['url'] + '.sha256', reference / 'bootstrap.sha256'),
        (base['url'] + '.sha256.asc', reference / 'bootstrap.sha256.asc'),
        (base['signing_key_url'], reference / 'opensuse-signing-key.asc'),
        (CONFIG['repository']['url'] + 'repodata/repomd.xml.key', reference / 'tb322fc-signing-key.asc'),
    ):
        fetch(url, path)
    verify_key(reference / 'opensuse-signing-key.asc', base['signing_key_fingerprint'], gnupg)
    signature = run('gpg', '--homedir', gnupg, '--batch', '--status-fd=1', '--verify',
                    reference / 'bootstrap.sha256.asc', reference / 'bootstrap.sha256',
                    capture_output=True, text=True)
    valid = [line.split() for line in signature.stdout.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
    if not any(base['signing_key_fingerprint'] in fields[2:] for fields in valid):
        raise RuntimeError('Bootstrap checksum signature is not from the pinned openSUSE key')
    signed = (reference / 'bootstrap.sha256').read_text()
    if base['sha256'] not in signed.split() or sha256(archive) != base['sha256']:
        raise RuntimeError('Bootstrap SHA256 mismatch')
    verify_key(reference / 'tb322fc-signing-key.asc', CONFIG['repository']['signing_key_fingerprint'], gnupg)
    root = work / 'rootfs'
    marker = root / '.tb322fc-opensuse-build'
    if root.exists():
        if not marker.is_file():
            raise RuntimeError('Existing staging tree has no build marker; refusing to modify it')
    else:
        stage = work / 'rootfs.extracting'
        stage.mkdir(mode=0o755)
        # Even an authenticated upstream archive must not escape the staging root.
        with tarfile.open(archive) as tar:
            for item in tar:
                if item.name.startswith('/') or '..' in Path(item.name).parts:
                    raise RuntimeError(f'Unsafe archive member: {item.name}')
        run('tar', '--numeric-owner', '--xattrs', '--xattrs-include=*', '--acls',
            '-xJpf', archive, '-C', stage)
        (stage / '.tb322fc-opensuse-build').write_text('TB322FC openSUSE staging tree\n')
        stage.rename(root)
    root.chmod(0o755)
    dest = root / 'usr/share/tb322fc/rootfs-build'
    dest.mkdir(parents=True, exist_ok=True)
    for name in ('opensuse-signing-key.asc', 'tb322fc-signing-key.asc'):
        shutil.copyfile(reference / name, dest / name)
    for name in ('rootfs.json', 'packages.json'):
        shutil.copyfile(REPO / 'configs/opensuse' / name, dest / name)
    for name in ('configure-rootfs.sh', 'first-user.sh'):
        shutil.copyfile(REPO / 'scripts/opensuse' / name, dest / name)
    shutil.copytree(REPO / 'rootfs', dest / 'overlay', dirs_exist_ok=True)
    repos = root / 'etc/zypp/repos.d'
    for path in repos.glob('*.repo'):
        path.unlink()
    for alias, url, priority in (
        ('repo-oss', 'https://download.opensuse.org/ports/aarch64/tumbleweed/repo/oss/', 99),
        ('tb322fc', CONFIG['repository']['url'], 50),
    ):
        (repos / f'{alias}.repo').write_text(
            f'[{alias}]\nname={alias}\nbaseurl={url}\nenabled=1\nautorefresh=1\nkeeppackages=1\n'
            f'gpgcheck=1\nrepo_gpgcheck=1\npkg_gpgcheck=1\npriority={priority}\n')
    resolver = root / 'etc/resolv.conf'
    resolver.unlink(missing_ok=True)
    resolver.symlink_to('/run/netconfig/resolv.conf')
    print(f'Prepared {root}; no package installation performed.', flush=True)


def stage_verified(work):
    # Live checks happen on every attempt; a previous successful build is not enough.
    run(REPO / 'scripts/opensuse/check-obs.py', '--work', work)
    root = work / 'rootfs'
    dest = root / 'usr/share/tb322fc/rootfs-build'
    shutil.copyfile(work / 'obs-ready.json', dest / 'obs-ready.json')
    # Retire the temporary repack repository from older staging trees.
    shutil.rmtree(dest / 'local-rpms', ignore_errors=True)
    (dest / 'local-repack-signing-key.asc').unlink(missing_ok=True)
    (root / 'etc/zypp/repos.d/tb322fc-local-repacks.repo').unlink(missing_ok=True)


def assemble(work):
    stage_verified(work)
    root = work / 'rootfs'
    run(REPO / 'scripts/opensuse/in-rootfs.sh', root, '/bin/bash',
        '/usr/share/tb322fc/rootfs-build/configure-rootfs.sh')
    (work / 'assembled').write_text('RPM installation and rootfs configuration complete\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'stage', 'assemble'])
    parser.add_argument('--work', type=Path, default=REPO / 'build/opensuse-rootfs')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root (filesystem ownership, chroot and mount namespaces)')
    work = args.work.resolve()
    if work == Path('/'):
        parser.error('The work directory cannot be /')
    work.mkdir(parents=True, exist_ok=True)
    if args.action == 'prepare':
        prepare(work)
    elif args.action == 'stage':
        stage_verified(work)
    else:
        assemble(work)


if __name__ == '__main__':
    main()
