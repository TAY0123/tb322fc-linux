#!/usr/bin/env python3
"""Seed pinned pnpm 10.11's store from OBS node_modules service tarballs.

The source service checks each npm integrity from the upstream pnpm lockfile.
pnpm's local tarball import uses a file: locator; add the registry locator for
the same integrity so frozen offline installation can resolve the original lock.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
sourcedir = Path(sys.argv[1])
tool = root / 'pnpm-tool/package/bin/pnpm.cjs'
store = root / 'pnpm-store'
version = subprocess.check_output(['node', str(tool), '--version'], text=True).strip()
if version != '10.11.0':
    raise RuntimeError('Revalidate store index layout before changing pnpm: ' + version)
tarballs = sorted(p for p in sourcedir.glob('*.tgz') if p.name != 'pnpm-10.11.0.tgz')
if not tarballs:
    raise RuntimeError('The node_modules source service produced no npm tarballs')
subprocess.run(['node', str(tool), 'store', 'add', '--store-dir', str(store),
                *map(str, tarballs)], check=True,
               env={**os.environ, 'CI': '1', 'npm_config_offline': 'true',
                    'npm_config_update_notifier': 'false'})
for path in (store / 'v10/index').rglob('*.json'):
    data = json.loads(path.read_text())
    prefix = path.name.split('-', 1)[0]
    name = data['name'].replace('/', '+')
    target = path.with_name(f"{prefix}-{name}@{data['version']}.json")
    if target != path:
        target.write_bytes(path.read_bytes())
