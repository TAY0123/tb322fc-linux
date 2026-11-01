#!/usr/bin/env python3
"""Package the pinned Qualcomm userspace dependencies as native RPMs."""
import argparse
import json
import shutil
import subprocess
import tarfile
import hashlib
import urllib.parse
import importlib.machinery
import xml.etree.ElementTree as ET
from obsapi import ROOT, WORK, publish

PACKAGES={
 'hexagonrpc':('0.5.0','BSD-3-Clause', ['pkgconfig(json-c)'], ''),
 'libssc':('0.4.4','GPL-3.0-or-later', ['pkgconfig(glib-2.0)','pkgconfig(gio-unix-2.0)','pkgconfig(qmi-glib)','pkgconfig(libprotobuf-c)','protobuf-devel','protobuf-c','gobject-introspection-devel','vala','python3-devel','python3-protobuf'], ''),
 'libcamera-y700':('0.7.2','LGPL-2.1-or-later', ['gcc-c++','pkgconfig(gnutls)','pkgconfig(libevent_pthreads)','pkgconfig(libdrm)','pkgconfig(libudev)','pkgconfig(libjpeg)','pkgconfig(libtiff-4)','pkgconfig(yaml-0.1)','pkgconfig(gstreamer-video-1.0)','pkgconfig(Qt6Widgets)','pkgconfig(Qt6OpenGL)','pkgconfig(Qt6OpenGLWidgets)','python3-ply','python3-Jinja2','python3-PyYAML','python3-pybind11'], '-Dauto_features=auto -Dpipelines=simple -Dipas=softisp -Dqcam=enabled -Dcam=enabled -Ddocumentation=disabled -Dtest=false -Dpycamera=disabled -Dtracing=disabled -Dlc-compliance=disabled'),
}

def prepare(name):
    if name == 'libcamera-y700':
        raise ValueError('Use prepare-official.py for the official libcamera source link')
    source_name='libcamera' if name=='libcamera-y700' else name
    source=ROOT/'sources'/source_name
    expected=json.loads((ROOT/'sources.json').read_text())[source_name]
    assert subprocess.check_output(['git','-C',str(source),'write-tree'],text=True).strip()==expected['tree']
    subprocess.run(['git','-C',str(source),'diff','--exit-code'],check=True)
    version,license,deps,options=PACKAGES[name]
    d=WORK/'stage'/name; d.mkdir(parents=True,exist_ok=True)
    parsed=urllib.parse.urlsplit(expected['url']);repo=parsed.path.removesuffix('.git')
    filename=f"{name}-{expected['commit']}.tar.gz"
    if parsed.netloc=='github.com':
        url='https://codeload.github.com'+repo+'/tar.gz/'+expected['commit']
    else:
        url='https://codeberg.org'+repo+'/archive/'+expected['commit']+'.tar.gz'
    simple=importlib.machinery.SourceFileLoader('simple',str(ROOT/'obs/prepare-simple.py')).load_module()
    cached=WORK/'cache'/('service-'+filename)
    digest=simple.fetch(url,cached)
    with tarfile.open(cached) as tar:
        top=tar.getmembers()[0].name.split('/')[0]
    for old in d.glob(f'{name}-*.tar.*'):old.unlink()
    services=ET.Element('services')
    service=ET.SubElement(services,'service',name='download_url',mode='serveronly')
    for key,value in [('url',url),('filename',filename)]:ET.SubElement(service,'param',name=key).text=value
    ET.indent(services,space='  ');(d/'_service').write_bytes(ET.tostring(services)+b'\n')
    patch=subprocess.check_output(['git','-C',str(source),'diff','--cached','--binary'])
    if patch:(d/'tb322fc.patch').write_bytes(patch)
    library={'hexagonrpc':'libhexagonrpc0_5','libssc':'libssc2','libcamera-y700':'libcamera0_7'}[name]
    spec=f'''%define libname {library}
Name:           {name}
Version:        {version}
Release:        1
Summary:        Pinned TB322FC {source_name} userspace support
License:        {license}
URL:            {expected['url']}
Source0:        {filename}
Source1:        file-list.py
'''+('Patch0:         tb322fc.patch\n' if patch else '')+f'''
ExclusiveArch:  aarch64
BuildRequires:  gcc
BuildRequires:  meson
BuildRequires:  ninja
BuildRequires:  pkgconfig
BuildRequires:  python3
'''+''.join('BuildRequires:  '+dep+'\n' for dep in deps)
    if name=='libcamera-y700': spec+='Provides: libcamera = %{version}\nConflicts: libcamera\n'
    spec+='''
%description
Qualcomm userspace support at the revision validated by tb322fc-linux.
The source tree includes the repository's pinned device patches. Calibration
and Android firmware are not included.

%package -n %{libname}
Summary: Shared library

%description -n %{libname}
Versioned shared library for the matching Qualcomm userspace tools.

%package devel
Summary: Development files
Requires: %{libname} = %{version}-%{release}

%description devel
Headers and pkg-config data for the matching library.

%prep
'''+f'''printf '%s  %s\\n' '{digest}' '%{{SOURCE0}}' | sha256sum -c
%autosetup -p1 -n {top}
'''+('''sed -i "s|get_option('libdir') / 'systemd/system'|'/usr/lib/systemd/system'|" data/meson.build
''' if name=='hexagonrpc' else '')+'''

%build
%meson '''+options+'''
%meson_build

%install
%meson_install
'''+('''# Mock sensor server is used by upstream tests, not at runtime.
rm -rf %{buildroot}%{_libexecdir}/installed-tests/libssc
find %{buildroot}/usr/lib* -type d -name ssc_server -prune -exec rm -rf {} +
''' if name=='libssc' else '')+'''
find %{buildroot} -type f -name '*.a' -delete
python3 %{SOURCE1} %{buildroot} > all-files
grep -E '/include/|/pkgconfig[/"]|[.]so"$|/gir-1.0[/"]|/vala[/"]' all-files > devel-files || :
grep -E '^"/usr/lib64/lib[^/]+[.]so[.]' all-files > library-files
grep -v -F -x -f devel-files -f library-files all-files > runtime-files

%post -n %{libname} -p /sbin/ldconfig
%postun -n %{libname} -p /sbin/ldconfig

%files -f runtime-files
%files devel -f devel-files
%files -n %{libname} -f library-files

%changelog
'''
    (d/(name+'.spec')).write_text(spec)
    shutil.copyfile(ROOT/'obs/file-list.py',d/'file-list.py')
    tracked=ROOT/'obs'/name;tracked.mkdir(parents=True,exist_ok=True)
    (tracked/(name+'.spec')).write_text(spec)
    (tracked/'source.json').write_text(json.dumps(expected,indent=2)+'\n')
    shutil.copyfile(d/'_service',tracked/'_service')
    if patch:shutil.copyfile(d/'tb322fc.patch',tracked/'tb322fc.patch')
    publish(name,d)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages',nargs='+')
    for name in parser.parse_args().packages: prepare(name)
