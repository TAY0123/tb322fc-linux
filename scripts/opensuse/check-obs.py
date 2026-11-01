#!/usr/bin/env python3
"""Refuse stale OBS binaries, including builds not yet in the public repository."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
PROJECT = 'home:h-cheung:tb322fc'


def public_get(path, query=None):
    """Public read-only API: image builders never need an osc account/token."""
    url = 'https://api.opensuse.org/public/' + path
    if query:
        url += '?' + urllib.parse.urlencode(query)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except (OSError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def check(work):
    config = json.loads((REPO / 'configs/opensuse/rootfs.json').read_text())
    packages = json.loads((REPO / 'configs/opensuse/packages.json').read_text())
    if (work / 'local-repacks.json').exists():
        raise RuntimeError('Archive the retired local-repacks.json; device packages must come from OBS.')
    query = {'repository': 'openSUSE_Tumbleweed', 'arch': 'aarch64'}
    result_path = f'build/{PROJECT}/_result'
    xml = public_get(result_path, query)
    (work / 'obs-results.xml').write_bytes(xml)
    result = ET.fromstring(xml)
    statuses = {p.attrib['package']: p for p in result.findall('.//status')}
    pending = []
    for name in packages['obs_builds']:
        status = statuses.get(name)
        if status is None or status.attrib.get('code') != 'succeeded' or status.attrib.get('dirty') == 'true':
            pending.append(f"{name}: {status.attrib.get('code', 'unknown') if status is not None else 'missing'}")
    if pending:
        raise RuntimeError('Waiting for current builds:\n  ' + '\n  '.join(pending))

    def binaries(name):
        path = f'build/{PROJECT}/openSUSE_Tumbleweed/aarch64/{name}'
        listing = ET.fromstring(public_get(path, {'view': 'binaryversions'}))
        return [p.attrib['name'] for p in listing if p.attrib['name'].endswith(('.aarch64.rpm', '.noarch.rpm'))]

    with ThreadPoolExecutor(max_workers=4) as pool:
        expected = {name for listing in pool.map(binaries, packages['obs_builds']) for name in listing}
    base = config['repository']['url']
    with tempfile.TemporaryDirectory(prefix='published-', dir=work) as directory:
        directory = Path(directory)
        for name in ('repomd.xml', 'repomd.xml.asc'):
            with urllib.request.urlopen(base + 'repodata/' + name, timeout=90) as response:
                (directory / name).write_bytes(response.read())
        sig = subprocess.run(['gpg', '--homedir', str(work / 'gnupg'), '--batch',
                              '--status-fd=1', '--verify', str(directory / 'repomd.xml.asc'),
                              str(directory / 'repomd.xml')], check=True, capture_output=True, text=True)
        fingerprint = config['repository']['signing_key_fingerprint']
        if not any(line.startswith('[GNUPG:] VALIDSIG ') and fingerprint in line.split()[2:]
                   for line in sig.stdout.splitlines()):
            raise RuntimeError('Public metadata was not signed by the pinned OBS project key')
        ns = {'r': 'http://linux.duke.edu/metadata/repo', 'c': 'http://linux.duke.edu/metadata/common'}
        metadata = ET.parse(directory / 'repomd.xml')
        primary = metadata.find('.//r:data[@type="primary"]', ns)
        href = primary.find('r:location', ns).attrib['href']
        if not href.startswith('repodata/') or '..' in Path(href).parts:
            raise RuntimeError('Unexpected metadata location')
        with urllib.request.urlopen(base + href, timeout=90) as response:
            data = response.read()
        checksum = primary.find('r:checksum', ns)
        if hashlib.new(checksum.attrib['type'], data).hexdigest() != checksum.text:
            raise RuntimeError('Public primary metadata checksum mismatch')
        index = ET.fromstring(gzip.decompress(data))
        published = {Path(p.find('c:location', ns).attrib['href']).name
                     for p in index.findall('c:package', ns)}
        missing = sorted(expected - published)
        if missing:
            raise RuntimeError('Current binaries have not all been published:\n  ' + '\n  '.join(missing))
        versions = {}
        for p in index.findall('c:package', ns):
            filename = Path(p.find('c:location', ns).attrib['href']).name
            if filename not in expected:
                continue
            name = p.findtext('c:name', namespaces=ns)
            v = p.find('c:version', ns).attrib
            versions[name] = f"{v['ver']}-{v['rel']}"
        absent = set(packages['device']) - versions.keys()
        if absent:
            raise RuntimeError(f'Unaccounted device packages: {sorted(absent)}')
        latest = ET.fromstring(public_get(result_path, query))
        if latest.attrib.get('state') != result.attrib.get('state'):
            raise RuntimeError('OBS state changed during verification; retry before installing')
        ready = {'project': PROJECT, 'state': result.attrib['state'],
                 'repository_revision': metadata.findtext('r:revision', namespaces=ns),
                 'versions': versions, 'binaries': sorted(expected)}
        (work / 'obs-ready.json').write_text(json.dumps(ready, indent=2) + '\n')
    print('Current required OBS builds and publication verified; all device packages come from OBS.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=REPO / 'build/opensuse-rootfs')
    args = parser.parse_args()
    try:
        check(args.work.resolve())
    except RuntimeError as error:
        print(error, file=sys.stderr)
        sys.exit(75)
