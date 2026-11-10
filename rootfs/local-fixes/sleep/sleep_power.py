#!/usr/bin/env python3
"""Save radio state before sleep and restore it on wake, abort, or the next boot."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

STATE = Path('/var/lib/tb322fc-sleep-power')
PENDING = STATE / 'pending.json'
SYS_RFKILL = Path('/sys/class/rfkill')
SYS_BT = Path('/sys/class/bluetooth')
SENSOR_SERVICES = ('als-bridge.service', 'tb322fc-gyro-bridge.service', 'iio-sensor-proxy.service')
RUNTIME_UNITS = Path('/run/systemd/system')


def run(*args, timeout=20):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{args[0]} {" ".join(args[1:])}: {(result.stderr or result.stdout).strip()}')
    return result.stdout


def log(message):
    print(message, flush=True)


def save(data, path=None):
    if path is None:
        path = PENDING
    temp = path.with_suffix('.new')
    with temp.open('w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def radios():
    result = []
    for node in sorted(SYS_RFKILL.glob('rfkill*')):
        kind = (node / 'type').read_text().strip()
        if kind in ('bluetooth', 'wlan'):
            result.append({'type': kind, 'name': (node / 'name').read_text().strip(),
                           'id': int(node.name[6:]),
                           'soft': int((node / 'soft').read_text()),
                           'hard': int((node / 'hard').read_text())})
    return result


def find_radio(item):
    matches = [x for x in radios() if (x['type'], x['name']) == (item['type'], item['name'])]
    if len(matches) != 1:
        raise RuntimeError(f'Cannot identify radio {item["type"]}/{item["name"]}')
    return matches[0]


def controllers():
    return sorted(p.name for p in SYS_BT.glob('hci*') if re.fullmatch(r'hci\d+', p.name))


def powered(controller):
    text = run('/usr/bin/btmgmt', '--index', controller[3:], 'info')
    match = re.search(r'^\s*current settings:([^\n]*)', text, re.M)
    if not match:
        # A failed QCA initialization leaves a sysfs hci entry which is not
        # registered with the management API. rfkill below still blocks it.
        if 'status 0x11 (Invalid Index)' in text:
            return None
        raise RuntimeError(f'Cannot read power state of {controller}')
    return 'powered' in match.group(1).split()


def set_power(controller, enabled):
    run('/usr/bin/btmgmt', '--index', controller[3:], 'power', 'on' if enabled else 'off',
        timeout=180 if enabled else 20)
    # BlueZ and firmware initialization can update management state after the
    # power command returns. Do not report failure from the first observation.
    deadline = time.monotonic() + 30
    last_error = 'controller still transitioning'
    while True:
        try:
            if powered(controller) == enabled:
                return
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            last_error = str(error)
        if time.monotonic() >= deadline:
            raise RuntimeError(f'{controller} did not reach requested power state: {last_error}')
        time.sleep(0.25)


def metrics():
    result = {'wall_time': time.time(), 'boot_time': time.clock_gettime(time.CLOCK_BOOTTIME),
              'monotonic_time': time.monotonic()}
    for name in ['success', 'fail', 'last_failed_dev']:
        path = Path('/sys/power/suspend_stats') / name
        if path.exists():
            result['suspend_' + name] = path.read_text().strip()
    for node in Path('/sys/class/power_supply').glob('*'):
        try:
            if (node / 'type').read_text().strip() == 'Battery':
                result['battery'] = {name: (node / name).read_text().strip()
                                     for name in ['capacity', 'charge_counter', 'voltage_now', 'status']
                                     if (node / name).exists()}
        except OSError:
            pass
    for name in ['apss', 'aosd', 'cxsd', 'ddr']:
        path = Path('/sys/kernel/debug/qcom_stats') / name
        try:
            result['qcom_' + name] = path.read_text().strip()
        except OSError:
            pass
    return result


def restore():
    if not PENDING.exists():
        return
    data = json.loads(PENDING.read_text())
    # Preserve the time and counters from the first wake, including on retries.
    if 'wake_or_abort' not in data:
        data['wake_or_abort'] = metrics()
    errors = []
    # Runtime masks prevent D-Bus clients from restarting streaming sensors
    # during suspend preparation. Remove only the masks this cycle created.
    for item in data.get('services', []):
        if not item.get('mask_pending'):
            continue
        try:
            path = RUNTIME_UNITS / item['name']
            if path.is_symlink() and os.readlink(path) == '/dev/null':
                run('/usr/bin/systemctl', 'unmask', '--runtime', item['name'])
            elif path.exists() or path.is_symlink():
                raise RuntimeError('Runtime sensor unit changed while asleep: ' + item['name'])
            item['mask_pending'] = False
            save(data)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(str(error))
    # Recover Wi-Fi first so a slow Bluetooth firmware reload does not delay it.
    for item in sorted(data['radios'], key=lambda x: x['type'] != 'wlan'):
        if not item.get('restore_pending'):
            continue
        try:
            current = find_radio(item)
            if current['soft']:
                run('/usr/bin/rfkill', 'unblock', str(current['id']))
            if find_radio(item)['soft']:
                raise RuntimeError('Radio remained blocked')
            item['restore_pending'] = False
            save(data)
            log(f'Restored {item["type"]} radio {item["name"]}')
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(str(error))
    for controller, item in data['controllers'].items():
        if not item.get('restore_pending'):
            continue
        try:
            if powered(controller) != item['powered']:
                set_power(controller, item['powered'])
            item['restore_pending'] = False
            save(data)
            log(f'Restored Bluetooth controller {controller}')
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(str(error))
    for item in data.get('services', []):
        if not item.get('restore_pending') or item.get('mask_pending'):
            continue
        try:
            run('/usr/bin/systemctl', 'start', item['name'], timeout=60)
            item['restore_pending'] = False
            save(data)
            log('Restored sensor service ' + item['name'])
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(str(error))
    if errors:
        raise RuntimeError('; '.join(errors) + '; saved state retained for retry')
    data['after'] = metrics()
    save(data, STATE / 'last-cycle.json')
    PENDING.unlink()
    log('Radio states restored. Battery and suspend diagnostics saved in last-cycle.json.')


def prepare():
    if PENDING.exists():
        restore()
    sensor_services = []
    for name in SENSOR_SERVICES:
        state = run('/usr/bin/systemctl', 'show', '--property=ActiveState', '--value', name).strip()
        if state == 'active':
            path = RUNTIME_UNITS / name
            if path.exists() or path.is_symlink():
                raise RuntimeError('Existing runtime sensor unit will not be overwritten: ' + name)
            sensor_services.append({'name': name, 'restore_pending': False, 'mask_pending': False})
        elif state in ('activating', 'deactivating', 'reloading'):
            raise RuntimeError('Sensor service still transitioning: ' + name)
    controller_states = {name: powered(name) for name in controllers()}
    unavailable = [name for name, state in controller_states.items() if state is None]
    if unavailable:
        log('Unavailable Bluetooth controllers will be handled by rfkill: ' + ', '.join(unavailable))
    data = {'before': metrics(), 'radios': radios(),
            'unavailable_controllers': unavailable,
            'services': sensor_services,
            'controllers': {name: {'powered': state, 'restore_pending': False}
                            for name, state in controller_states.items() if state is not None}}
    save(data)
    try:
        for item in sensor_services:
            item['mask_pending'] = True
            item['restore_pending'] = True
        save(data)
        if sensor_services:
            names = [item['name'] for item in sensor_services]
            run('/usr/bin/systemctl', 'mask', '--runtime', *names)
            run('/usr/bin/systemctl', 'stop', *names, timeout=60)
            log('Stopped streaming sensor clients for sleep: ' + ', '.join(names))
        # Powering HCI down sets QCA_BT_OFF, bypassing the failing IBS handshake.
        for controller, item in data['controllers'].items():
            item['restore_pending'] = True
            save(data)
            if item['powered']:
                set_power(controller, False)
                log(f'Powered down Bluetooth controller {controller}')
        for item in data['radios']:
            if not item['soft'] and not item['hard']:
                item['restore_pending'] = True
                save(data)
                current = find_radio(item)
                run('/usr/bin/rfkill', 'block', str(current['id']))
                if not find_radio(item)['soft']:
                    raise RuntimeError(f'{item["name"]} remained unblocked')
                log(f'Blocked {item["type"]} radio {item["name"]} for sleep')
        log('Radios prepared for sleep. Existing blocked/off states were preserved.')
    except BaseException:
        restore()
        raise


def status():
    print(json.dumps({'radios': radios(), 'controllers': {x: powered(x) for x in controllers()},
                      'pending_restore': PENDING.exists(), 'metrics': metrics()}, indent=2))


def acquire_lock(stream, timeout):
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Previous sleep restoration is still running; retry after it finishes')
            time.sleep(0.2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'restore', 'status'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('run with sudo')
    if args.action == 'status':
        status()
        return
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'state.lock').open('a') as lock:
        # A rapid second sleep can race the previous ExecStop restoration.
        # Wait for it to finish instead of failing immediately with EAGAIN.
        acquire_lock(lock, 60 if args.action == 'prepare' else 210)
        (prepare if args.action == 'prepare' else restore)()


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        log('Sleep radio preparation/restoration failed: ' + str(error))
        sys.exit(1)
