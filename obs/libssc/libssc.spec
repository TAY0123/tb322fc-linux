%define libname libssc2
Name:           libssc
Version:        0.4.4
Release:        1
Summary:        Pinned TB322FC libssc userspace support
License:        GPL-3.0-or-later
URL:            https://codeberg.org/DylanVanAssche/libssc.git
Source0:        libssc-54dd13e36d65c21263cf5b0f4a70c230a77b26bc.tar.gz
Source1:        file-list.py

ExclusiveArch:  aarch64
BuildRequires:  gcc
BuildRequires:  meson
BuildRequires:  ninja
BuildRequires:  pkgconfig
BuildRequires:  python3
BuildRequires:  pkgconfig(glib-2.0)
BuildRequires:  pkgconfig(gio-unix-2.0)
BuildRequires:  pkgconfig(qmi-glib)
BuildRequires:  pkgconfig(libprotobuf-c)
BuildRequires:  protobuf-devel
BuildRequires:  protobuf-c
BuildRequires:  gobject-introspection-devel
BuildRequires:  vala
BuildRequires:  python3-devel
BuildRequires:  python3-protobuf

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
printf '%s  %s\n' 'ff723a4aa39f692e3a53d6dbf64d5b7831c6a6839eb98a9dfb2acd5de2030357' '%{SOURCE0}' | sha256sum -c
%autosetup -p1 -n libssc


%build
%meson
%meson_build

%install
%meson_install
# Mock sensor server is used by upstream tests, not at runtime.
rm -rf %{buildroot}%{_libexecdir}/installed-tests/libssc
find %{buildroot}/usr/lib* -type d -name ssc_server -prune -exec rm -rf {} +

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
