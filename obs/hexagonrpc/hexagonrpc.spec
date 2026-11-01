%define libname libhexagonrpc0_5
Name:           hexagonrpc
Version:        0.5.0
Release:        1
Summary:        Pinned TB322FC hexagonrpc userspace support
License:        BSD-3-Clause
URL:            https://github.com/linux-msm/hexagonrpc.git
Source0:        hexagonrpc-598b591ae9da6a6cfe2ca5ea78998019ca6395ea.tar.gz
Source1:        file-list.py
Patch0:         tb322fc.patch

ExclusiveArch:  aarch64
BuildRequires:  gcc
BuildRequires:  meson
BuildRequires:  ninja
BuildRequires:  pkgconfig
BuildRequires:  python3
BuildRequires:  pkgconfig(json-c)

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
printf '%s  %s\n' '05181d130f1e3a3f4c368be606a627562f7abd972c5efff92a21d66d35a2fe51' '%{SOURCE0}' | sha256sum -c
%autosetup -p1 -n hexagonrpc-598b591ae9da6a6cfe2ca5ea78998019ca6395ea
sed -i "s|get_option('libdir') / 'systemd/system'|'/usr/lib/systemd/system'|" data/meson.build


%build
%meson
%meson_build

%install
%meson_install

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
