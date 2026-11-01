#!/usr/bin/env python3
"""Create RPM source bundles from the maintained device package recipes.

The PKGBUILD is used only for shared prepare/build/install functions. RPM owns
dependency resolution, file ownership and scriptlets. All network inputs are
fetched and checked here, outside the offline OBS builder.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
from obsapi import ROOT, WORK, publish

FIELDS=('pkgname','pkgver','pkgrel','pkgdesc','license','depends','makedepends','source','sha256sums','provides','conflicts')
def metadata(recipe):
    command='source "$1"; for f in '+ ' '.join(FIELDS) + '; do declare -n a="$f"; printf "%s\\0" "$f" "${a[@]}"; printf "\\n"; done'
    raw=subprocess.check_output(['bash','-c',command,'bash',str(recipe)])
    result={}
    for row in raw.decode().splitlines():
        fields=row.rstrip('\0').split('\0')
        result[fields[0]]=[s for s in fields[1:] if s]
    return result

DEPS={
 'python':'python3','python-gobject':'python3-gobject','glib2':'libglib-2_0-0',
 'gcc-libs':'libgcc_s1 libstdc++6','libgcc':'libgcc_s1','libstdc++':'libstdc++6',
 'systemd-libs':'libsystemd0','procps-ng':'procps','gtk2':'libgtk-2_0-0',
 'xorg-server-xvfb':'xorg-x11-server-Xvfb','openal':'libopenal1',
 'xorg-xprop':'xprop','kde-cli-tools':'kde-cli-tools6','kdialog':'kdialog',
 'python-aiohttp':'python3-aiohttp','python-aiohttp-cors':'python3-aiohttp_cors',
 'python-aiohttp-jinja2':'python3-aiohttp-jinja2',
 'python-watchdog':'python3-watchdog','python-certifi':'python3-certifi',
 'python-packaging':'python3-packaging','python-multidict':'python3-multidict',
 'python-setproctitle':'python3-setproctitle','vulkan-icd-loader':'libvulkan1',
 'libarchive':'bsdtar','pacman':'zypper rpm','scx-scheds':'scx',
 'als-bridge-dkms':'als-bridge-kmp-freedom',
}
BUILD={
 'tb322fc-sensors':['gcc','make','pkgconfig','pkgconfig(glib-2.0)','pkgconfig(libssc)'],
 'umtp-responder-freedom':['gcc','make','pkgconfig(systemd)','pkgconfig(libsystemd)'],
 'armada-rgb':['cargo','rust','gcc','pkgconfig','zstd'],
 'y700-charge':['nodejs','npm'],
 'decky-render-tools':['nodejs','npm'],
 'armada-decky-plugins':['nodejs','npm'],
 'kettle-framegen-armada':['gcc','gcc-c++','make','glslang-devel','vulkan-devel'],
 'directx-shader-compiler-render':['gcc','gcc-c++','cmake','ninja','python3','git','zlib-devel','libxml2-devel','ncurses-devel'],
 'steamos-manager':['cargo','rust','clang-devel','llvm-devel','pkgconfig','pkgconfig(glib-2.0)','pkgconfig(libsystemd)','speech-dispatcher-devel','zstd'],
 'kshim-freedom':['gcc','gcc-c++','make','cmake','ninja','git','dtc','python3-kconfiglib','glibc-devel-static','libopenssl-devel','zlib-devel'],
 'decky-loader':['nodejs','python3-build','python3-installer','python3-poetry-core'],
 'optiscaler-arm64ec-armada':['gcc','gcc-c++','cmake','ninja','python3','directx-shader-compiler-render','llvm-mingw-arm64ec'],
 'gamescope-armada':['gcc-c++','cmake','meson','ninja','pkgconfig','glslang-devel','git','vim','xorg-x11-server-Xvfb',*[f'pkgconfig({n})' for n in ('benchmark','catch2-with-main','hwdata','libavif','libcap','libdecor-0','libdrm','libeis-1.0','libpipewire-0.3','sdl2','vulkan','wayland-protocols','x11','xcomposite','xcursor','xdamage','xext','xrender','xres','xtst','xwayland','xxf86vm','egl','gbm','glesv2','lcms2','libavcodec','libavformat','libavutil','libinput','libpng','libseat','libudev','luajit','pixman-1','wayland-client','wayland-egl','wayland-server','x11-xcb','xcb','xcb-composite','xcb-errors','xcb-icccm','xcb-image','xcb-render','xcb-renderutil','xcb-xfixes','xcb-xkb','xkbcommon','xmu')]],
}
NATIVE={'tb322fc-sensors','umtp-responder-freedom','armada-rgb','kettle-framegen-armada','directx-shader-compiler-render','steamos-manager','kshim-freedom','gamescope-armada'}

def fetch(url,destination,expected=None):
    if not destination.exists():
        temporary=destination.with_name(destination.name+'.part-'+str(os.getpid()))
        subprocess.run(['curl','--fail','--location','--silent','--show-error','--retry','3','--retry-all-errors','--connect-timeout','20','--max-time','600','--output',str(temporary),url],check=True)
        temporary.replace(destination)
    actual=hashlib.sha256(destination.read_bytes()).hexdigest()
    if expected and expected!='SKIP' and actual!=expected:
        raise RuntimeError('SHA256 mismatch: '+url)
    return actual

def export_git(remote, destination):
    parsed=urllib.parse.urlsplit(remote.removeprefix('git+'))
    selector=urllib.parse.parse_qs(parsed.fragment)
    ref=(selector.get('commit') or selector.get('tag') or [None])[0]
    if not ref: raise RuntimeError('An immutable Git revision is required: '+remote)
    upstream=urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))
    repo=parsed.path.rstrip('/').removesuffix('.git')
    archive=WORK/'cache'/(repo.split('/')[-1]+'-'+ref.replace('/','_')+'.tar.gz')
    if upstream=='https://github.com/mydanyi/armadaos-freedom.git':
        assert ref=='244b74516d99d06cb0518609ce4b842ab278be8a'
        with archive.open('wb') as out:
            subprocess.run(['git','-C',str(ROOT/'sources/freedom'),'archive','--format=tar.gz','--prefix=source/',ref,'devices/lenovo-tb323fu/boot/kshim-success-source','packages/kshim-tools/vendor','LICENSE'],stdout=out,check=True)
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    elif parsed.netloc=='github.com':
        digest=fetch('https://codeload.github.com'+repo+'/tar.gz/'+ref,archive)
    else:
        cached=WORK/'git'/(repo.split('/')[-1])
        if not cached.exists():
            cached.mkdir(parents=True)
            subprocess.run(['git','init','--bare',str(cached)],check=True,stdout=subprocess.DEVNULL)
        exists=subprocess.run(['git','-C',str(cached),'cat-file','-e',ref+'^{commit}'],capture_output=True).returncode==0
        if not exists:
            subprocess.run(['git','-C',str(cached),'fetch','--depth=1',upstream,ref],check=True)
        with archive.open('wb') as out:
            subprocess.run(['git','-C',str(cached),'archive','--format=tar.gz','--prefix=source/',ref],stdout=out,check=True)
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    with tarfile.open(archive) as tar:
        members=tar.getmembers()
        prefix=members[0].name.split('/')[0]
        temp=destination.parent/(destination.name+'.extract')
        temp.mkdir()
        tar.extractall(temp,filter='data')
        shutil.move(temp/prefix,destination)
        temp.rmdir()
    return {'url':upstream,'revision':ref,'sha256':digest}

def bundle(name):
    package=ROOT/'packages'/name
    data=metadata(package/'PKGBUILD')
    version=data['pkgver'][0].replace('_','~')
    build=WORK/'bundles'/name
    if build.exists(): shutil.rmtree(build)
    local=build/'local'; sources=build/'sources'
    local.mkdir(parents=True); sources.mkdir()
    # Only repository source files, including the user's pending source edits.
    listed=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--',str(package)],cwd=ROOT,text=True).splitlines()
    for entry in listed:
        path=ROOT/entry
        if not path.is_file(): continue
        relative=path.relative_to(package)
        if '__pycache__' in relative.parts: continue
        dest=local/relative; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,dest); shutil.copymode(path,dest)
    provenance=[]
    for index,source in enumerate(data['source']):
        if not source: continue
        alias,sep,remote=source.partition('::')
        if not sep: remote=source; alias=remote.rsplit('/',1)[-1]
        if name=='optiscaler-arm64ec-armada' and '/llvm-mingw/releases/download/' in remote:
            # The RPM must depend on a source-built native ARM64EC toolchain,
            # never import the Arch recipe's Ubuntu compiler binary archive.
            continue
        if remote.startswith('git+'):
            if not sep:
                alias=urllib.parse.urlsplit(remote.removeprefix('git+')).path.rsplit('/',1)[-1].removesuffix('.git')
            provenance.append(export_git(remote,sources/alias))
            continue
        target=sources/alias
        if remote.startswith(('https://','http://')):
            cached=WORK/'cache'/alias
            expected=data['sha256sums'][index] if index<len(data['sha256sums']) else None
            digest=fetch(remote,cached,expected)
            shutil.copyfile(cached,target)
            provenance.append({'url':remote,'sha256':digest})
            if tarfile.is_tarfile(target):
                with tarfile.open(target) as tar: tar.extractall(sources,filter='data')
                if alias!='CrDK-b6c3335.tar.gz': target.unlink()
        else:
            shutil.copyfile(local/remote,target)
    for script in ('recipe-stage.sh','file-list.py'):
        shutil.copyfile(ROOT/'obs'/script,build/script)
    (build/'SOURCE-PROVENANCE.json').write_text(json.dumps(provenance,indent=2)+'\n')
    return data,version,build

def finish(name,data,version,build):
    stage=WORK/'stage'/name; stage.mkdir(parents=True,exist_ok=True)
    override=ROOT/'obs'/name/'adapt.py'
    if override.exists():
        subprocess.run([sys.executable,str(override),str(build)],check=True)
    vendor=ROOT/'obs'/name/'vendor.py'
    if vendor.exists():
        subprocess.run([sys.executable,str(vendor),str(build)],check=True)
    archive=f'{name}-{version}.tar.xz'
    with tarfile.open(stage/archive,'w:xz') as tar:
        tar.add(build,arcname=f'{name}-{version}')
    requires=[]
    for dep in data['depends']:
        m=re.match(r'([^<>=]+)(.*)',dep)
        mapped=DEPS.get(m[1],m[1])
        suffix=re.sub(r'([<>=]+)',r' \1 ',m[2])
        requires += [n+suffix for n in mapped.split()]
    if name=='gamescope-armada':
        # Native ELF dependency generation supplies shared-library SONAMEs.
        requires=['xorg-x11-server-wayland','hwdata']
    license=' AND '.join(data['license']).replace('GPL-2.0 AND','GPL-2.0-only AND')
    if license=='GPL-2.0': license='GPL-2.0-only'
    if license=='LicenseRef-NCSA AND Apache-2.0': license='NCSA AND Apache-2.0'
    spec=f'''# Generated by obs/prepare-simple.py from the maintained device source recipe.
Name:           {name}
Version:        {version}
Release:        {data['pkgrel'][0]}
Summary:        {data['pkgdesc'][0].replace('%','%%')}
License:        {license}
URL:            https://github.com/h0cheung/tb322fc-linux
Source0:        {archive}
'''
    spec += 'ExclusiveArch:  aarch64\n' if name in NATIVE else 'BuildArch:      noarch\n'
    if name in ('armada-rgb','steamos-manager','directx-shader-compiler-render','kshim-freedom'):
        spec += '%global debug_package %{nil}\n'
    if name=='kshim-freedom':
        spec += '%global __strip /bin/true\n%global __brp_strip /bin/true\n%global _lto_cflags %{nil}\n'
    spec += ''.join('BuildRequires:  '+s+'\n' for s in ['bash','python3','patch','systemd-rpm-macros',*BUILD.get(name,[])])
    spec += ''.join('Requires:       '+s+'\n' for s in sorted(set(requires)))
    for key in ('provides','conflicts'):
        for value in data[key]:
            if value==name: continue
            value=re.sub(r'([<>=]+)',r' \1 ',value)
            spec+=key.title()+': '+value+'\n'
    spec+='''
%description
Device integration from tb322fc-linux, packaged for Tumbleweed. Firmware and
per-device calibration are provisioned separately. Hardware validation of
this RPM port is pending.

%prep
%setup -q
bash recipe-stage.sh prepare

%build
export CFLAGS="%{optflags}" CXXFLAGS="%{optflags}"
export RUSTFLAGS="${RUSTFLAGS:-} %{?tb322fc_rustflags}"
bash recipe-stage.sh build

%install
bash recipe-stage.sh install %{buildroot}
python3 file-list.py %{buildroot} > files.list

%check
export RUSTFLAGS="${RUSTFLAGS:-} %{?tb322fc_rustflags}"
bash recipe-stage.sh check

%files -f files.list
%defattr(-,root,root)

%changelog
'''
    tracked=ROOT/'obs'/name; tracked.mkdir(parents=True,exist_ok=True)
    (tracked/(name+'.spec')).write_text(spec)
    (stage/(name+'.spec')).write_text(spec)
    if any('https://' in s or 'http://' in s for s in data['source']) or name in ('armada-rgb','y700-charge'):
        # The expanded bundle is only a preparation cache. Publish upstream
        # sources through _service and keep their patches independently editable.
        import importlib.machinery
        converter=importlib.machinery.SourceFileLoader('service_bundle',str(ROOT/'obs/prepare-service-bundle.py')).load_module()
        converter.prepare(name)
    else:
        publish(name,stage)

if __name__=='__main__':
    import sys
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('packages',nargs='+')
    for name in p.parse_args().packages:
        data,version,build=bundle(name)
        finish(name,data,version,build)
