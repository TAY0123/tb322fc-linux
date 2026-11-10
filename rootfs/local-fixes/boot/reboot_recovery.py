#!/usr/bin/env python3
"""Reboot a Linux-running TB322FC into stock recovery using Android slot A.

Slot A stays selected afterward. Return to Linux with fastboot set_active b.
--dry-run validates the layout without changing the slot, misc, or power state.
"""

import argparse
import contextlib
import fcntl
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import struct
import subprocess
import sys
import time

SLOTCTL = Path('/usr/local/libexec/tb322fc-select-boot-slot')
MISC = Path('/dev/disk/by-partlabel/misc')
STATE = Path('/var/lib/tb322fc-recovery')
SLOT_LOCK = Path('/var/lib/tb322fc-boot-success/boot-success.lock')
reboot_issued = False


def load_guard():
    loader = importlib.machinery.SourceFileLoader('recovery_slot_guard', str(SLOTCTL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    guard = importlib.util.module_from_spec(spec)
    loader.exec_module(guard)
    return guard


def run(*args):
    result = subprocess.run([str(x) for x in args], check=True, text=True, capture_output=True, timeout=90)
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def recovery_message(original):
    if len(original) < 4096:
        raise RuntimeError('The misc partition is too small')
    command = original[:32].split(b'\0', 1)[0]
    arguments = original[64:832].split(b'\0', 1)[0]
    if command not in (b'', b'boot-recovery'):
        raise RuntimeError('Another bootloader operation is pending; leaving it unchanged')
    if arguments.strip() not in (b'', b'recovery'):
        raise RuntimeError('Recovery already has pending arguments; leaving them unchanged')
    updated = bytearray(original)
    updated[:32] = b'boot-recovery'.ljust(32, b'\0')
    updated[64:832] = b'recovery\n'.ljust(768, b'\0')
    assert updated[32:64] == original[32:64]
    assert updated[832:] == original[832:]
    return bytes(updated)


@contextlib.contextmanager
def slot_lock():
    with SLOT_LOCK.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def validate(guard):
    guard.verify_installed_linux()
    snapshots, pairs, active = guard.snapshot_slots()
    guard.verify_parent_protection(snapshots)
    guard.payload_inventory(pairs)
    assert guard.read_lun(guard.ufs_attribute(snapshots)) == (1 if active == 'a' else 2)
    for label, is_recovery in [('boot_a', False), ('recovery_a', True)]:
        path = Path('/dev/disk/by-partlabel') / label
        with path.open('rb') as stream:
            header = stream.read(4096)
        if header[:8] != b'ANDROID!' or struct.unpack_from('<I', header, 40)[0] != 4:
            raise RuntimeError(f'{label} is not the expected Android v4 image')
        kernel_bytes, ramdisk_bytes = struct.unpack_from('<II', header, 8)
        if is_recovery:
            assert kernel_bytes == 0 and ramdisk_bytes > 1024 * 1024
        else:
            assert kernel_bytes > 1024 * 1024
    assert Path('/sys/bus/platform/devices/reboot-mode/driver').resolve().name == 'nvmem-reboot-mode'
    assert stat.S_ISBLK(MISC.stat().st_mode)
    sysfs = Path('/sys/class/block') / MISC.resolve().name
    assert 'PARTNAME=misc' in (sysfs / 'uevent').read_text().splitlines()
    size = int((sysfs / 'size').read_text()) * 512
    assert 4096 <= size <= 16 * 1024 * 1024
    parent = guard.boot.partition_disk(MISC)
    snapshot = guard.boot.read_gpt(parent)
    guard.verify_partition_geometry(MISC, snapshot, size)
    assert snapshot['read_only'] == 0  # misc shares the mounted rootfs parent.
    assert run('blockdev', '--getro', MISC).stdout.strip() == '1'
    original = MISC.read_bytes()
    assert len(original) == size
    return active, original, recovery_message(original)


def write_message(expected, desired):
    assert len(expected) == len(desired)
    assert expected[32:64] == desired[32:64] and expected[832:] == desired[832:]
    assert MISC.read_bytes() == expected
    protected = run('blockdev', '--getro', MISC).stdout.strip()
    assert protected == '1'
    try:
        run('blockdev', '--setrw', MISC)
        with MISC.open('r+b', buffering=0) as stream:
            def write_fields(payload):
                # Clear/set recovery arguments first; arm the command last.
                for offset, length in [(64, 768), (0, 32)]:
                    stream.seek(offset)
                    assert stream.write(payload[offset:offset + length]) == length
                os.fsync(stream.fileno())
            try:
                write_fields(desired)
                assert MISC.read_bytes() == desired
            except BaseException:
                write_fields(expected)
                assert MISC.read_bytes() == expected
                raise
    finally:
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try:
            run('blockdev', '--setro', MISC)
            assert run('blockdev', '--getro', MISC).stdout.strip() == protected
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


def save(path, content):
    with path.open('xb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    global reboot_issued
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('run with sudo')
    os.umask(0o077)
    guard = load_guard()
    with slot_lock():
        active, original, desired = validate(guard)
    if args.dry_run:
        run(SLOTCTL, 'select', 'a', '--dry-run')
        print('Verified Android boot_a + kernel-free recovery_a and recovery reboot-mode driver.')
        print('Would select slot A, write boot-recovery with no recovery arguments, then request reboot to recovery.')
        print('DRY RUN: no slot, misc, boot image or power-state changes made.')
        return
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = STATE / f'{time.time_ns()}-{os.getpid()}'
    backup.mkdir(mode=0o700)
    save(backup / 'misc.before.bin', original)
    save(backup / 'misc.recovery.bin', desired)
    plan = {'original_slot': active, 'target_slot': 'a', 'misc_device': str(MISC.resolve()),
            'misc_before_sha256': digest(original), 'misc_recovery_sha256': digest(desired),
            'boot_images_modified': False, 'recovery_arguments': [],
            'reboot_command': ['/usr/bin/systemctl', 'reboot', '--reboot-argument=recovery']}
    save(backup / 'plan.json', (json.dumps(plan, indent=2) + '\n').encode())
    for directory in (backup, STATE):
        fd = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    switched = armed = False
    try:
        run(SLOTCTL, 'select', 'a')
        switched = active != 'a'
        with slot_lock():
            assert guard.snapshot_slots()[2] == 'a'
            write_message(original, desired)
            armed = True
        print(f'Recovery prepared on Android slot A. Backup: {backup}', flush=True)
        reboot_issued = True
        run('/usr/bin/systemctl', 'reboot', '--reboot-argument=recovery')
    except BaseException as error:
        # A signal after requesting reboot can mean shutdown is already running.
        # Leave the verified recovery request intact in that case.
        if reboot_issued and (not isinstance(error, subprocess.CalledProcessError) or error.returncode < 0):
            raise RuntimeError(f'Reboot may already be queued; recovery remains prepared. Backup: {backup}') from error
        if armed:
            with slot_lock():
                write_message(desired, original)
        if switched:
            run(SLOTCTL, 'select', active)
        raise


if __name__ == '__main__':
    def interrupted(signum, frame):
        if not reboot_issued:
            raise InterruptedError(f'Interrupted by signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        main()
    except (OSError, RuntimeError, AssertionError, subprocess.SubprocessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(f'Recovery request failed: {detail}', file=sys.stderr)
        sys.exit(1)
