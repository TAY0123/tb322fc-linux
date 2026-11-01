%{?!python_module:%define python_module() python3-%{**}}
Name:           python-kconfiglib
Version:        14.1.0
Release:        0
Summary:        Kconfig implementation in Python
License:        ISC
URL:            https://github.com/ulfalizer/Kconfiglib
Source0:        kconfiglib-14.1.0.tar.gz
BuildRequires:  %{python_module setuptools}
BuildRequires:  python-rpm-macros
BuildRequires:  fdupes
BuildRequires:  update-alternatives
Requires(post): update-alternatives
Requires(postun): update-alternatives
BuildArch:      noarch
%python_subpackages

%description
Python library for reading and modifying Kconfig configurations.

%prep
# Verify upstream kconfiglib-14.1.0.tar.gz
printf '%s  %s\n' 'bed2cc2216f538eca4255a83a4588d8823563cdd50114f86cf1a2674e602c93c' '%{SOURCE0}' | sha256sum -c
%setup -q -n kconfiglib-%{version}

%build
%python_build

%install
%python_install
%python_clone -a %{buildroot}%{_bindir}/alldefconfig
%python_clone -a %{buildroot}%{_bindir}/allmodconfig
%python_clone -a %{buildroot}%{_bindir}/allnoconfig
%python_clone -a %{buildroot}%{_bindir}/allyesconfig
%python_clone -a %{buildroot}%{_bindir}/defconfig
%python_clone -a %{buildroot}%{_bindir}/genconfig
%python_clone -a %{buildroot}%{_bindir}/guiconfig
%python_clone -a %{buildroot}%{_bindir}/listnewconfig
%python_clone -a %{buildroot}%{_bindir}/menuconfig
%python_clone -a %{buildroot}%{_bindir}/oldconfig
%python_clone -a %{buildroot}%{_bindir}/olddefconfig
%python_clone -a %{buildroot}%{_bindir}/savedefconfig
%python_clone -a %{buildroot}%{_bindir}/setconfig
%python_expand %fdupes %{buildroot}%{$python_sitelib}

%post
%python_install_alternative alldefconfig
%python_install_alternative allmodconfig
%python_install_alternative allnoconfig
%python_install_alternative allyesconfig
%python_install_alternative defconfig
%python_install_alternative genconfig
%python_install_alternative guiconfig
%python_install_alternative listnewconfig
%python_install_alternative menuconfig
%python_install_alternative oldconfig
%python_install_alternative olddefconfig
%python_install_alternative savedefconfig
%python_install_alternative setconfig

%postun
%python_uninstall_alternative alldefconfig
%python_uninstall_alternative allmodconfig
%python_uninstall_alternative allnoconfig
%python_uninstall_alternative allyesconfig
%python_uninstall_alternative defconfig
%python_uninstall_alternative genconfig
%python_uninstall_alternative guiconfig
%python_uninstall_alternative listnewconfig
%python_uninstall_alternative menuconfig
%python_uninstall_alternative oldconfig
%python_uninstall_alternative olddefconfig
%python_uninstall_alternative savedefconfig
%python_uninstall_alternative setconfig

%files %{python_files}
%license LICENSE.txt
%doc README.rst
%{python_sitelib}/*
%python_alternative %{_bindir}/alldefconfig
%python_alternative %{_bindir}/allmodconfig
%python_alternative %{_bindir}/allnoconfig
%python_alternative %{_bindir}/allyesconfig
%python_alternative %{_bindir}/defconfig
%python_alternative %{_bindir}/genconfig
%python_alternative %{_bindir}/guiconfig
%python_alternative %{_bindir}/listnewconfig
%python_alternative %{_bindir}/menuconfig
%python_alternative %{_bindir}/oldconfig
%python_alternative %{_bindir}/olddefconfig
%python_alternative %{_bindir}/savedefconfig
%python_alternative %{_bindir}/setconfig


%changelog
