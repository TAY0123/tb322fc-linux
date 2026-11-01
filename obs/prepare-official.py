#!/usr/bin/env python3
"""Adapt existing openSUSE specs, retaining distro ABI and codec policy."""
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from obsapi import ROOT, WORK, publish
from importlib.machinery import SourceFileLoader

OFFICIAL = {
    'inputplumber-g9-2026': ('inputplumber', True),
    'ffmpeg-v4l2m2m': ('ffmpeg-9', False),
    'iio-sensor-proxy-y700': ('iio-sensor-proxy', True),
    'mangohud-armada': ('mangohud', False),
    'mesa-y700-gen4': ('Mesa', True),
    'libcamera-y700': ('libcamera', False),
    'gtk2': ('gtk2', True),
    'python-aiohttp_cors': ('python-aiohttp_cors', True),
    'python-aiohttp-jinja2': ('python-aiohttp-jinja2', True),
}

def stage(upstream, target):
    destination = WORK / 'stage' / target
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for path in (WORK / 'upstream' / upstream).iterdir():
        if path.is_file() and path.name not in ('source-revision.xml', '_service', '_servicedata', '_scmsync.obsinfo', 'build.specials.obscpio'):
            shutil.copyfile(path, destination / path.name)
    return destination

def add_patches(spec, directory, patches, extra=''):
    text = spec.read_text()
    declarations = []
    for index, path in enumerate(patches, 900):
        shutil.copyfile(path, directory / path.name)
        declarations.append(f'Patch{index}: {path.name}')
    text = text.replace('%description\n', '\n'.join(declarations)+'\n'+extra+'\n%description\n', 1)
    # autosetup/autopatch applies all declared patches in numeric order.
    if '%autosetup' not in text and '%autopatch' not in text:
        apply='\n'.join(f'%patch -P {index} -p1' for index in range(900,900+len(patches)))
        text=text.replace('%build\n',apply+'\n\n%build\n',1)
    spec.write_text(text)

def enable_ffmpeg_hwdec(spec):
    """Add only the two Iris decoder wrappers to the official reduced build."""
    text = spec.read_text()
    allowlist = '\t--enable-decoder="$(perl -pe \'s{^(\\w*).*}{$1,}gs\' <%_sourcedir/enable_decoders)" \\\n'
    assert allowlist in text, 'official decoder allowlist changed'
    text = text.replace(allowlist, allowlist +
        '\t--enable-v4l2-m2m \\\n'
        '\t--enable-decoder=h264_v4l2m2m,hevc_v4l2m2m \\\n'
        '\t--disable-decoder=h264,hevc,libopenh264 \\\n', 1)
    guard = '''for i in H264 HEVC VC1 VVC; do
\tgrep -q "#define CONFIG_${i}_DECODER 0" config_components.h
done
'''
    assert guard in text, 'official software decoder checks changed'
    text = text.replace(guard, guard + '''# TB322FC uses Iris through V4L2; retain no software H.264/HEVC fallback.
grep -q "#define CONFIG_LIBOPENH264_DECODER 0" config_components.h
for i in H264_V4L2M2M HEVC_V4L2M2M; do
\tgrep -q "#define CONFIG_${i}_DECODER 1" config_components.h
done
for i in LIBX264 LIBX265 NONFREE; do
\tgrep -q "#define CONFIG_${i} 0" config.h
done
''', 1)
    spec.write_text(text)

def prepare(name):
    if name == 'inputplumber-g9-2026':
        d = stage('inputplumber', name)
        spec = d / 'inputplumber.spec'
        add_patches(spec, d, [ROOT/'packages'/name/p for p in ('0001-add-legion-g9-rumble.patch','0002-scope-hidraw-hide-rules-to-device-path.patch')])
        shutil.copyfile(ROOT/'packages'/name/'legion_g9.rs', d/'legion_g9.rs')
        text = spec.read_text().replace('Name:           inputplumber\n','Name:           inputplumber-g9-2026\n').replace('Release:        0%{?dist}', 'Release:        2')
        text = text.replace('Source1:        vendor.tar.zst', 'Source1:        vendor.tar.zst\nSource2:        legion_g9.rs\nProvides:       inputplumber = %{version}\nConflicts:      inputplumber')
        text = text.replace('%autosetup -p1 -a1 -n InputPlumber-%{version}', '%autosetup -p1 -a1 -n InputPlumber-%{version}\ninstall -m644 %{SOURCE2} src/input/source/hidraw/legion_g9.rs')
        text = text.replace('%make_build build', 'cargo build --frozen --release --bin inputplumber').replace('%make_build test','cargo test --frozen --release --lib --bin inputplumber')
        for section in ('%build','%check'):
            text=text.replace(section+'\n',section+'\nexport RUSTFLAGS="${RUSTFLAGS:-} %{?tb322fc_rustflags}"\n',1)
        spec.write_text(text)
        (d/'_constraints').write_text('<constraints><hardware><physicalmemory><size unit="G">4</size></physicalmemory></hardware></constraints>\n')
    elif name == 'ffmpeg-v4l2m2m':
        d = stage('ffmpeg-9', name)
        spec = d/'ffmpeg-9.spec'
        # Chromium compatibility is already carried by the official spec.
        patches=[]
        base='https://raw.githubusercontent.com/slwyts/Project-SunUEFI/be3073644216a413776b973203d4222e8950703a/linux/bsp/patches/ffmpeg/'
        for file in ('0004-v4l2m2m-ffmpeg9-stateful.patch','0005-v4l2m2m-orphan-capture-ffmpeg9.patch','0006-v4l2m2m-p010-capture.patch'):
            path=WORK/'cache'/file
            if not path.exists(): urllib.request.urlretrieve(base+file,path)
            patches.append(path)
        add_patches(spec,d,patches)
        # The public build must not be switchable into an unrestricted build
        # through a project-level macro. The complete build uses a separate CI.
        spec.write_text('%define BUILD_ORIG 0\n'+spec.read_text())
        enable_ffmpeg_hwdec(spec)
        shutil.copyfile(ROOT/'obs'/name/(name+'.changes'), d/(name+'.changes'))
    elif name == 'iio-sensor-proxy-y700':
        d=stage('iio-sensor-proxy',name)
        spec=d/'iio-sensor-proxy.spec'
        add_patches(spec,d,[ROOT/'packages'/name/'iio-sensor-proxy.patch'])
        # The official package disables SSC. TB322FC's physical light sensor
        # is only accessible through libssc; the IIO device is our mirror.
        text=spec.read_text()
        assert '-Dssc-support=disabled' in text
        text=text.replace('BuildRequires:  pkgconfig(systemd)',
                          'BuildRequires:  pkgconfig(libssc) >= 0.2.1\nBuildRequires:  pkgconfig(systemd)',1)
        spec.write_text(text.replace('-Dssc-support=disabled','-Dssc-support=enabled'))
    elif name == 'mangohud-armada':
        d=stage('mangohud',name)
        add_patches(d/'mangohud.spec',d,sorted((ROOT/'packages'/name).glob('*.patch')))
    elif name == 'mesa-y700-gen4':
        d=stage('Mesa',name)
        spec=d/'Mesa.spec'
        # Inherit the official version and archives. The three device patches
        # were verified on 26.2.5 with zero fuzz, after the distribution patches.
        spec.write_text('%define BUILD_ORIG 0\n'+spec.read_text())
        add_patches(spec,d,sorted((ROOT/'sources/freedom/packages/mesa/patches').glob('*.patch')))
        spec.write_text(spec.read_text().replace('%build\n','%build\nexport RUSTFLAGS="${RUSTFLAGS:-} %{?tb322fc_rustflags}"\n',1))
    elif name=='libcamera-y700':
        d=stage('libcamera',name)
        source=json.loads((ROOT/'sources.json').read_text())['libcamera']
        # Device autofocus uses the post-0.7.2 SoftISP protocol. Keep the same
        # pinned source as the validated Arch installation and the SUSE RPM
        # split, rather than applying that protocol patch to an older API.
        version='0.7.2+git20260911.'+source['commit'][:7]
        shutil.copyfile(ROOT/source['patch'],d/'tb322fc-camera.patch')
        shutil.copyfile(ROOT/'obs'/name/'libcamera-ov02e10-initial-support.patch',
                        d/'libcamera-ov02e10-initial-support.patch')
        spec=d/'libcamera.spec'
        s=spec.read_text().replace('Patch1:         libcamera-ov02e10-initial-support.patch','Patch1:         libcamera-ov02e10-initial-support.patch\nPatch900:       tb322fc-camera.patch')
        s=s.replace('Version:        0.7.2','Version:        '+version)
        s=s.replace('-Dv4l2=false','-Dv4l2=disabled')
        s=s.replace('-Dpipelines=auto,vimc','-Dpipelines=simple -Dipas=softisp -Dsoftisp-gpu=disabled')
        spec.write_text(s)
        for archive in d.glob('libcamera-*.tar.xz'):
            archive.unlink()
        services=ET.Element('services')
        service=ET.SubElement(services,'service',name='tar_scm',mode='serveronly')
        for key,value in (('scm','git'),('url',source['url']),('revision',source['commit']),
                          ('filename','libcamera'),('version',version),('submodules','disable')):
            ET.SubElement(service,'param',name=key).text=value
        service=ET.SubElement(services,'service',name='recompress',mode='serveronly')
        ET.SubElement(service,'param',name='file').text='*.tar'
        ET.SubElement(service,'param',name='compression').text='xz'
        ET.indent(services,space='  ')
        (d/'_service').write_bytes(ET.tostring(services)+b'\n')
    elif name in ('gtk2','python-aiohttp_cors','python-aiohttp-jinja2'):
        d=stage(name,name)
    else:
        raise ValueError(name)
    # Upload only downstream files and a spec diff. Inherit official sources
    # through _link rather than uploading an expanded snapshot of the package.
    linker = SourceFileLoader('link_official', str(ROOT/'obs/link-official.py')).load_module()
    upstream, tracking = OFFICIAL[name]
    linker.prepare(upstream, name, tracking=tracking)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('packages',nargs='+')
    for name in p.parse_args().packages:
        prepare(name)
