#!/usr/bin/env python3
"""Small authenticated OBS source helper; credentials stay in osc's backend."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import osc.conf
import osc.core

PROJECT = 'home:h-cheung:tb322fc'
ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/obs-tb322fc'
osc.conf.get_config()
API = osc.conf.config['apiurl']

# Native userspace build tools/tests need the auto-generated vector/crypto
# instructions enabled by the Oryon target. RNDR is explicitly tested on the
# tablet: the public workers do not advertise RNG, so RNG-specific tests must
# use a runtime capability check instead of running it unconditionally.
TARGET_PACKAGES = {
    'als-bridge-kmp', 'armada-rgb', 'directx-shader-compiler-render', 'fastrpc', 'ffmpeg-v4l2m2m',
    'gamescope-armada', 'gtk2', 'hexagonrpc', 'iio-sensor-proxy-y700',
    'inputplumber-g9-2026', 'kernel-source', 'kettle-framegen-armada', 'kshim-freedom',
    'libcamera-y700', 'libkscreen6', 'libplacebo', 'libssc', 'llvm-mingw-arm64ec', 'mangohud-armada', 'mesa-y700-gen4',
    'msime', 'optiscaler-arm64ec-armada', 'plasma6-setup', 'plymouth',
    'steamos-manager', 'tb322fc-sensors', 'umtp-responder-freedom',
}


def target_constraints(package, directory):
    if package not in TARGET_PACKAGES:
        return
    path = directory / '_constraints'
    if not path.exists() and (directory / '_link').exists():
        upstream = ET.parse(directory / '_link').getroot().attrib['package']
        original = WORK / 'upstream' / upstream / '_constraints'
        if original.exists():
            shutil.copyfile(original, path)
    root = ET.parse(path).getroot() if path.exists() else ET.Element('constraints')
    hardware = root.find('hardware')
    if hardware is None:
        hardware = ET.SubElement(root, 'hardware')
    cpu = hardware.find('cpu')
    if cpu is None:
        cpu = ET.SubElement(hardware, 'cpu')
    existing = {x.text for x in cpu.findall('flag')}
    for flag in ('bf16', 'i8mm', 'sha3', 'sm4'):
        if flag not in existing:
            ET.SubElement(cpu, 'flag').text = flag
    ET.indent(root, space='  ')
    path.write_bytes(ET.tostring(root) + b'\n')
    tracked = ROOT / 'obs' / package
    tracked.mkdir(exist_ok=True)
    shutil.copyfile(path, tracked / '_constraints')


def url(path, query=None):
    return osc.core.makeurl(API, path.strip('/').split('/'), query or {})


def get(path, query=None):
    return osc.core.http_GET(url(path, query)).read()


def put(path, data):
    return osc.core.http_PUT(url(path), data=data).read()


def checkout(package, project='openSUSE:Factory'):
    directory = WORK / 'upstream' / package
    directory.mkdir(parents=True, exist_ok=True)
    listing = ET.fromstring(get(f'source/{project}/{package}', {'expand': '1'}))
    (directory / 'source-revision.xml').write_bytes(ET.tostring(listing))
    def download(entry):
        import hashlib
        name = entry.attrib['name']
        target = directory / name
        if target.is_file() and hashlib.md5(target.read_bytes()).hexdigest() == entry.attrib['md5']:
            return
        target.write_bytes(get(f'source/{project}/{package}/{name}', {'rev': listing.attrib['srcmd5']}))
        assert hashlib.md5(target.read_bytes()).hexdigest() == entry.attrib['md5'], name
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download, listing.findall('entry')))
    print(f'{package}: fetched {len(listing.findall("entry"))} files', flush=True)
    return directory


def publish(package, directory):
    import hashlib
    directory = Path(directory)
    target_constraints(package, directory)
    if not list(directory.glob('*.changes')) and not (directory/'_link').exists():
        (directory/(package+'.changes')).write_text('-------------------------------------------------------------------\nSat Oct 31 09:00:00 UTC 2026 - h0cheung <hcheunh@gmail.com>\n\n- Initial Tumbleweed aarch64 build evaluation for TB322FC.\n')
    for changes in directory.glob('*.changes'):
        changes.write_text(changes.read_text().replace(' - h-cheung\n',' - h0cheung <hcheunh@gmail.com>\n'))
    meta = directory / '_meta'
    if meta.exists():
        metadata = meta.read_bytes()
    else:
        try:
            metadata = get(f'source/{PROJECT}/{package}/_meta')
        except Exception as error:
            if getattr(error, 'code', None) != 404:
                raise
            metadata = ET.tostring(ET.fromstring(f'<package name="{package}" project="{PROJECT}"><title>{package}</title><description>TB322FC Tumbleweed build evaluation; see https://github.com/h0cheung/tb322fc-linux</description></package>'))
    put(f'source/{PROJECT}/{package}/_meta', metadata)
    entries = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.name in ('source-revision.xml', '_scmsync.obsinfo', 'build.specials.obscpio', '_meta'):
            continue
        entries.append((path, hashlib.md5(path.read_bytes()).hexdigest()))
    listing = ET.Element('directory')
    for path, digest in entries:
        ET.SubElement(listing, 'entry', name=path.name, md5=digest)
    query = {'cmd': 'commitfilelist', 'comment': 'Port TB322FC packages to Tumbleweed aarch64 for build evaluation'}
    response = ET.fromstring(osc.core.http_POST(url(f'source/{PROJECT}/{package}', query), data=ET.tostring(listing)).read())
    if response.attrib.get('error') == 'missing':
        missing = {e.attrib['name'] for e in response.findall('entry')}
        for path, digest in entries:
            if path.name in missing:
                print(f'{package}: uploading {path.name} ({path.stat().st_size // 1024} KiB)', flush=True)
                osc.core.http_PUT(url(f'source/{PROJECT}/{package}/{path.name}', {'rev': 'repository'}), file=str(path)).read()
        response = ET.fromstring(osc.core.http_POST(url(f'source/{PROJECT}/{package}', query), data=ET.tostring(listing)).read())
    if response.attrib.get('error'):
        raise RuntimeError(ET.tostring(response).decode())
    print(f'{package}: committed source revision {response.attrib.get("rev", "?")}', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['checkout', 'publish', 'results'])
    p.add_argument('packages', nargs='*')
    args = p.parse_args()
    if args.action == 'checkout':
        for package in args.packages:
            checkout(package)
    elif args.action == 'publish':
        for package in args.packages:
            publish(package, WORK / 'stage' / package)
    else:
        print(get(f'build/{PROJECT}/_result').decode())
