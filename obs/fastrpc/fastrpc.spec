%define libname libcdsprpc1
Name:           fastrpc
Version:        1.0.8
Release:        0
Summary:        Qualcomm CDSP client libraries
License:        BSD-3-Clause
URL:            https://github.com/quic/fastrpc
Source0:        fastrpc-%{version}.tar.gz
Source1:        70-tb322fc-cdsp.rules
Source2:        tb322fc.yaml
Source3:        fastrpc.conf
Source4:        fastrpc-rpmlintrc
ExclusiveArch:  aarch64
BuildRequires:  autoconf
BuildRequires:  automake
BuildRequires:  gcc
BuildRequires:  libtool
BuildRequires:  pkgconfig
BuildRequires:  systemd-rpm-macros
BuildRequires:  pkgconfig(libbsd-overlay)
BuildRequires:  pkgconfig(yaml-0.1)
%description
Native CDSP RPC support for applications using the upstream Linux driver.
This package does not install QNN, neural models or ADSP listener services.

%package tb322fc
Summary:        CDSP configuration for the Lenovo Y700 Gen 4
BuildArch:      noarch
Requires:       %{libname} = %{version}-%{release}
Requires:       udev

%description tb322fc
Board-specific DSP search paths, DMA heap loading and active-seat device
permissions. Firmware and generic DSP libraries are provisioned separately.

%package -n %{libname}
Summary:        Qualcomm CDSP FastRPC shared library

%description -n %{libname}
CDSP client library for applications using the upstream Linux FastRPC driver.
Includes the unversioned names required by vendor clients using dlopen.

%package devel
Summary:        FastRPC development headers
BuildArch:      noarch
Requires:       %{libname} = %{version}-%{release}

%description devel
Headers for native applications using CDSP remote calls and RPC memory.

%prep
printf '%s  %s\n' 'b8582e8d816fd89c0f8348740f682277ca639e22d557808703d7056477ef0f02' '%{SOURCE0}' | sha256sum -c
%autosetup
autoreconf -fi

%build
%configure --disable-static --with-config-base-dir=%{_datadir}/qcom/
# Only CDSP libraries are needed; do not build/install upstream ADSP daemons.
%make_build -C src libcdsprpc.la libcdsp_default_listener.la

%install
%make_build -C src install-libLTLIBRARIES DESTDIR=%{buildroot} lib_LTLIBRARIES="libcdsprpc.la libcdsp_default_listener.la"
find %{buildroot}%{_libdir} -name '*.la' -delete
%make_install -C inc
install -D -m644 %{SOURCE1} %{buildroot}%{_udevrulesdir}/70-tb322fc-cdsp.rules
install -D -m644 %{SOURCE2} %{buildroot}%{_datadir}/qcom/conf.d/tb322fc.yaml
install -D -m644 %{SOURCE3} %{buildroot}%{_modulesloaddir}/fastrpc.conf
install -d %{buildroot}%{_datadir}/qcom/tb322fc/dsp
install -d %{buildroot}%{_prefix}/lib/firmware/qcom/sm8750/cdsp
ln -s /usr/lib/firmware/qcom/sm8750/cdsp %{buildroot}%{_datadir}/qcom/tb322fc/dsp/cdsp

%post -n %{libname} -p /sbin/ldconfig
%postun -n %{libname} -p /sbin/ldconfig

%files tb322fc
%{_udevrulesdir}/70-tb322fc-cdsp.rules
%dir %{_modulesloaddir}
%{_modulesloaddir}/fastrpc.conf
%dir %{_datadir}/qcom
%dir %{_datadir}/qcom/conf.d
%{_datadir}/qcom/conf.d/tb322fc.yaml
%dir %{_datadir}/qcom/tb322fc
%dir %{_datadir}/qcom/tb322fc/dsp
%{_datadir}/qcom/tb322fc/dsp/cdsp
%dir %{_prefix}/lib/firmware
%dir %{_prefix}/lib/firmware/qcom
%dir %{_prefix}/lib/firmware/qcom/sm8750
%dir %{_prefix}/lib/firmware/qcom/sm8750/cdsp

%files -n %{libname}
%license LICENSE.txt
# QNN and the FastRPC listener load these exact unversioned names.
%{_libdir}/libcdsprpc.so*
%{_libdir}/libcdsp_default_listener.so*

%files devel
%{_includedir}/fastrpc

%changelog
