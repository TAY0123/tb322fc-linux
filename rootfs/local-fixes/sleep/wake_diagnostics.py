#!/usr/bin/env python3
"""Capture the next suspend's wake evidence without triggering a power action."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

STATE = Path('/var/lib/tb322fc-sleep-power')
TRACE = Path('/sys/kernel/tracing/instances/tb322fc-wake')
TRACE_EVENTS = ('power/suspend_resume', 'power/wakeup_source_activate', 'irq/irq_handler_entry')


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def snapshot():
    result = {'wall_time': time.time(), 'monotonic': time.monotonic(),
              'boot_time': time.clock_gettime(time.CLOCK_BOOTTIME),
              'boot_id': read(Path('/proc/sys/kernel/random/boot_id')),
              'mem_sleep': read(Path('/sys/power/mem_sleep')),
              'pm_wakeup_irq': read(Path('/sys/power/pm_wakeup_irq')),
              'interrupts': read(Path('/proc/interrupts')),
              'wakeup_sources': read(Path('/sys/kernel/debug/wakeup_sources')),
              'wakeup': []}
    for node in Path('/sys/class/wakeup').glob('*'):
        name = read(node / 'name')
        if name:
            result['wakeup'].append({key: read(node / key) for key in
                ['name', 'event_count', 'wakeup_count', 'active_count', 'last_change_ms']})
    return result


def irq_counts(text):
    result = {}
    for line in (text or '').splitlines():
        match = re.match(r'^\s*(\d+):\s+(.*)', line)
        if not match:
            continue
        fields = match.group(2).split()
        values = []
        while fields and fields[0].isdigit():
            values.append(int(fields.pop(0)))
        result[match.group(1)] = {'count': sum(values), 'description': ' '.join(fields)}
    return result


def irq_delta(before, after):
    first, last = irq_counts(before), irq_counts(after)
    result = []
    for irq, item in last.items():
        difference = item['count'] - first.get(irq, {'count': item['count']})['count']
        if difference > 0:
            result.append({'irq': int(irq), 'delta': difference, 'description': item['description']})
    return sorted(result, key=lambda x: x['delta'], reverse=True)


def wake_delta(before, after):
    first = {item['name']: item for item in before.get('wakeup', [])}
    result = []
    for item in after.get('wakeup', []):
        old = first.get(item['name'])
        if not old:
            continue
        changes = {}
        for key in ['event_count', 'wakeup_count', 'active_count']:
            try:
                difference = int(item[key]) - int(old[key])
                if difference:
                    changes[key] = difference
            except (TypeError, ValueError):
                pass
        if changes:
            result.append({'name': item['name'], **changes})
    return result


def save(path, data):
    temp = path.with_suffix('.new')
    with temp.open('w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def start_trace():
    TRACE.mkdir(exist_ok=True)
    (TRACE / 'tracing_on').write_text('0\n')
    (TRACE / 'events/enable').write_text('0\n')
    (TRACE / 'buffer_size_kb').write_text('512\n')
    (TRACE / 'trace').write_text('')
    for event in TRACE_EVENTS:
        (TRACE / 'events' / event / 'enable').write_text('1\n')
    (TRACE / 'tracing_on').write_text('1\n')


def finish_trace():
    if not TRACE.exists():
        return
    (TRACE / 'tracing_on').write_text('0\n')
    (TRACE / 'events/enable').write_text('0\n')
    # Only this private instance is touched; other tracing sessions are retained.
    text = (TRACE / 'trace').read_text()
    save(STATE / 'last-wake-trace.json', {'trace': text})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['pre', 'post', 'self-check'])
    parser.add_argument('operation', nargs='?')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run with sudo')
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.action == 'pre':
        save(STATE / 'wake-before.json', snapshot())
        try:
            start_trace()
        except OSError as error:
            if TRACE.exists():
                (TRACE / 'tracing_on').write_text('0\n')
                (TRACE / 'events/enable').write_text('0\n')
            print(f'Wake trace unavailable; counter diagnostics retained: {error}', file=sys.stderr)
    elif args.action == 'post':
        after = snapshot()
        try:
            finish_trace()
        except OSError as error:
            print(f'Could not save wake trace: {error}', file=sys.stderr)
        path = STATE / 'wake-before.json'
        before = json.loads(path.read_text()) if path.exists() else {}
        report = {'before': before, 'after': after, 'wake_source_deltas': wake_delta(before, after),
                  'irq_deltas': irq_delta(before.get('interrupts'), after['interrupts']),
                  'interpretation': 'IRQ deltas include suspend/resume activity and are candidates, not proof of the wake source.'}
        save(STATE / 'last-wake.json', report)
        print('Wake-source counters and interrupt trace saved for this suspend.')
    else:
        # Validate read access and a private trace instance without sleeping.
        original_instances = {p.name for p in TRACE.parent.iterdir()}
        TRACE.mkdir(exist_ok=True)
        (TRACE / 'tracing_on').write_text('0\n')
        (TRACE / 'events/enable').write_text('0\n')
        for event in TRACE_EVENTS:
            assert (TRACE / 'events' / event / 'enable').exists()
        assert snapshot()['interrupts']
        assert original_instances <= {p.name for p in TRACE.parent.iterdir()}
        print('Wake diagnostics ready; private trace remains off. No suspend triggered.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, AssertionError) as error:
        # Diagnostics must never prevent sleep or restoration.
        print('Wake diagnostics: ' + str(error), file=sys.stderr)
        if 'self-check' in sys.argv[1:]:
            sys.exit(1)
