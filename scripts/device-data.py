#!/usr/bin/env python3
"""Back up and import this tablet's private Hexagon sensor/DSP data.

The backup contains no raw Android partitions. Import refuses to overwrite an
existing sensor registry. Keep bundles out of Git, OBS and distributable images.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Expected a real Hexagon data directory')
    result = []
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        item = {'path': path.relative_to(root).as_posix(), 'mode': stat.S_IMODE(info.st_mode),
                'uid': info.st_uid, 'gid': info.st_gid, 'mtime_ns': info.st_mtime_ns}
        if path.is_symlink():
            item.update(type='symlink', target=os.readlink(path))
        elif stat.S_ISDIR(info.st_mode):
            item['type'] = 'directory'
        elif stat.S_ISREG(info.st_mode):
            item.update(type='file', size=info.st_size, sha256=digest(path))
        else:
            raise ValueError(f'Unexpected special file: {path}')
        result.append(item)
    return result


def ssh(host, command, **kwargs):
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                           '--', host, command], check=True, **kwargs)


def remote_inventory(host):
    code = Path(__file__).read_bytes()
    result = ssh(host, 'sudo -n python3 - inventory /var/lib/hexagonrpc',
                 input=code, capture_output=True)
    return json.loads(result.stdout)


def backup(host, output):
    output = output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    output.chmod(0o700)
    before = remote_inventory(host)
    archive = output / 'hexagonrpc.tar.gz'
    partial = archive.with_suffix('.gz.part')
    with partial.open('xb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        ssh(host, "sudo -n tar --format=pax --numeric-owner --xattrs --acls --hard-dereference "
                  "--use-compress-program='gzip -1' -cf - -C /var/lib hexagonrpc", stdout=stream)
    after = remote_inventory(host)
    if before != after:
        raise RuntimeError('Source data changed during backup; the .part file is not a verified bundle. Retry into a new directory.')
    partial.rename(archive)
    identity = json.loads(ssh(host, "python3 -", input=b'''import json
from pathlib import Path
paths = {'model':'/sys/firmware/devicetree/base/model',
         'compatible':'/sys/firmware/devicetree/base/compatible',
         'serial':'/sys/devices/soc0/serial_number'}
print(json.dumps({k:Path(v).read_text().strip('\\x00\\n').replace('\\x00', ',')
                  for k,v in paths.items() if Path(v).is_file()}))
''', capture_output=True).stdout)
    manifest = {'format': 1, 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'source': '/var/lib/hexagonrpc', 'device': identity,
                'archive': archive.name, 'sha256': digest(archive), 'entries': before}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'manifest.json').chmod(0o600)
    (output / 'SHA256SUMS').write_text(f"{manifest['sha256']}  {archive.name}\n{digest(output/'manifest.json')}  manifest.json\n")
    verify(output)
    print(f'Backup saved to {output}')


def unpack_verified(bundle, parent):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest['format'] != 1 or manifest['archive'] != 'hexagonrpc.tar.gz':
        raise ValueError('Unknown bundle format')
    archive = bundle / manifest['archive']
    if digest(archive) != manifest['sha256']:
        raise ValueError('Archive SHA256 mismatch')
    expected = {entry['path']: entry for entry in manifest['entries']}
    with tarfile.open(archive) as tar:
        names, links = set(), set()
        for member in tar:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'hexagonrpc':
                raise ValueError(f'Unsafe archive path: {member.name}')
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if relative in names or relative not in expected:
                raise ValueError(f'Duplicate/unlisted archive path: {member.name}')
            names.add(relative)
            entry = expected[relative]
            if member.issym():
                if entry['type'] != 'symlink' or member.linkname != entry['target']:
                    raise ValueError('Symlink differs from manifest')
                if relative == 'socinfo':
                    if member.linkname != '/sys/devices/soc0':
                        raise ValueError('Unexpected socinfo link')
                elif PurePosixPath(member.linkname).is_absolute() or '..' in PurePosixPath(member.linkname).parts:
                    raise ValueError('Non-socinfo symlink escapes the data directory')
                links.add(relative)
            elif member.isdir():
                if entry['type'] != 'directory':
                    raise ValueError('Directory differs from manifest')
            elif member.isfile():
                if entry['type'] != 'file':
                    raise ValueError('File differs from manifest')
            else:
                raise ValueError(f'Unexpected special archive entry: {member.name}')
        if names != expected.keys():
            raise ValueError('Archive inventory differs from manifest')
        for name in names:
            if any(parent.as_posix() in links for parent in PurePosixPath(name).parents):
                raise ValueError('Archive writes through a symlink')
    subprocess.run(['tar', '--numeric-owner', '--same-owner', '--xattrs', '--acls',
                    '-xzpf', str(archive), '-C', str(parent)], check=True)
    data = parent / 'hexagonrpc'
    if inventory(data) != manifest['entries']:
        raise ValueError('Extracted file data/ownership/modes/timestamps differ from manifest')
    required = ['acdb', 'dsp', 'sensors/config', 'sensors/state/registry',
                'sensors/state/sns_reg_version', 'sensors/sns_reg.conf']
    for path in required:
        if not (data / path).exists():
            raise ValueError(f'Missing required sensor data: {path}')
    return data, manifest


def verify(bundle):
    with tempfile.TemporaryDirectory(prefix='.verify-', dir=bundle) as directory:
        _, manifest = unpack_verified(bundle, Path(directory))
    files = [x for x in manifest['entries'] if x['type'] == 'file']
    print(f"Verified {len(files)} files, {sum(x['size'] for x in files)} bytes; source stayed unchanged during backup.")


def restore(bundle, root):
    root = root.resolve(strict=True)
    if not (root / 'etc/os-release').is_file():
        raise ValueError('Target is not a Linux rootfs')
    destination = root / 'var/lib/hexagonrpc'
    if not destination.parent.resolve().is_relative_to(root):
        raise ValueError('Destination parent escapes the target rootfs')
    if destination.is_symlink():
        raise ValueError('Destination must not be a symlink')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        for entry in inventory(destination):
            # Accept the empty scaffolding created by the rootfs builder only.
            if entry['type'] == 'directory':
                continue
            if entry['path'] == 'socinfo' and entry.get('target') == '/sys/devices/soc0':
                continue
            raise ValueError('Destination already has device data; preserving its live registry. Import into a fresh rootfs instead.')
    with tempfile.TemporaryDirectory(prefix='.hexagonrpc-import-', dir=destination.parent) as directory:
        data, _ = unpack_verified(bundle, Path(directory))
        data.chmod(0o700)
        if destination.exists():
            shutil.rmtree(destination)  # Only the validated empty scaffolding above.
        data.rename(destination)
    print(f'Imported verified device data into {destination}; no services or Android partitions changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('backup')
    p.add_argument('--host', required=True)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('verify')
    p.add_argument('bundle', type=Path)
    p = commands.add_parser('restore')
    p.add_argument('bundle', type=Path)
    p.add_argument('--root', type=Path, required=True)
    p = commands.add_parser('inventory')
    p.add_argument('directory', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root to preserve ownership and private file permissions')
    os.umask(0o077)
    if args.command == 'backup':
        backup(args.host, args.output)
    elif args.command == 'verify':
        verify(args.bundle.resolve())
    elif args.command == 'restore':
        restore(args.bundle.resolve(), args.root)
    else:
        print(json.dumps(inventory(args.directory)))


if __name__ == '__main__':
    main()
