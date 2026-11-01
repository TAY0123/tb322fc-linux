# Uses the standard openSUSE kernel_module_package macros, as in bbswitch.
Name:           als-bridge-kmp
Version:        20260929
Release:        3
Summary:        Ambient light bridge kernel module for TB322FC
License:        GPL-2.0-only
Group:          System/Kernel
URL:            https://github.com/h0cheung/tb322fc-linux
Source0:        als-bridge-%{version}.tar.xz
ExclusiveArch:  aarch64
BuildRequires:  %{kernel_module_package_buildreqs}
BuildRequires:  kernel-syms = 7.2.6
BuildRequires:  kernel-freedom-devel = 7.2.6
BuildRequires:  kernel-devel = 7.2.6
BuildRequires:  clang
BuildRequires:  llvm
BuildRequires:  lld
BuildRequires:  libelf-devel
%kernel_module_package -n als-bridge freedom

%description
The ambient light bridge exposes SensorProxy illuminance to the Steam client.
This KMP is built against the matching Freedom kernel development package.

%prep
%setup -q -n als-bridge-%{version}
mkdir source
mv als-bridge.c Makefile source/
mkdir obj

%build
export KCFLAGS="${KCFLAGS:-} %{?tb322fc_cflags}"
for flavor in %{flavors_to_build}; do
    cp -r source obj/$flavor
    make %{?_smp_mflags} -C %{kernel_source $flavor} LLVM=1 ARCH=arm64 modules M=$PWD/obj/$flavor
done

%install
for flavor in %{flavors_to_build}; do
    make -C %{kernel_source $flavor} LLVM=1 ARCH=arm64 modules_install M=$PWD/obj/$flavor INSTALL_MOD_PATH=%{buildroot} INSTALL_MOD_DIR=updates
done

%changelog
