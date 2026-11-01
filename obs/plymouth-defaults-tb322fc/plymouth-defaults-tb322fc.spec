Name:           plymouth-defaults-tb322fc
Version:        1.0
Release:        0
Summary:        Plymouth display and button settings for Lenovo Legion Y700 Gen 4
License:        GPL-3.0-or-later
URL:            https://github.com/h0cheung/tb322fc-linux
Source0:        plymouthd.conf
Source1:        50-plymouth.conf
Source2:        50-retain-splash.conf
Source3:        50-plymouth-initramfs.sh
Source4:        plymouth-init
BuildArch:      noarch
BuildRequires:  systemd-rpm-macros
Requires:       plymouth >= 26.134.222
Requires:       plymouth-dracut >= 26.134.222
Requires:       plymouth-branding-openSUSE
Requires:       plymouth-theme-spinner >= 26.134.222-4
Requires:       plymouth-plugin-label-ft >= 26.134.222
Requires:       cantarell-fonts
Requires:       distribution-logos-openSUSE-Tumbleweed
Requires:       kshim-boot-argument-defaults >= 2
Requires:       kshim-initramfs-hooks >= 1
Requires:       dracut
Requires:       udev
Requires:       coreutils
Requires:       findutils
Requires:       fontconfig

%description
Display scaling, landscape rendering and a Volume Up alternative to Escape
for the TB322FC tablet. The packaged Spinner theme displays the official
Tumbleweed logo without relying on ACPI BGRT. Theme artwork, colours and
timing stay unchanged. kShim incorporates the packaged boot defaults when
generating the boot image; explicit arguments win. The last splash frame
is retained for desktop handoff.
The initramfs includes Plymouth, the selected theme, fonts and input data;
the same daemon continues across the existing BusyBox F2FS root handoff.

%prep

%build

%install
install -Dm644 %{SOURCE0} %{buildroot}%{_sysconfdir}/plymouth/plymouthd.conf
install -Dm644 %{SOURCE1} %{buildroot}%{_prefix}/lib/kshim-freedom/cmdline.d/50-plymouth.conf
install -Dm644 %{SOURCE2} %{buildroot}%{_unitdir}/plymouth-quit.service.d/50-retain-splash.conf
install -Dm755 %{SOURCE3} %{buildroot}%{_prefix}/lib/kshim-freedom/initramfs.d/50-plymouth.sh
install -Dm755 %{SOURCE4} %{buildroot}%{_prefix}/lib/kshim-freedom/plymouth-init

%files
%dir %{_sysconfdir}/plymouth
%config(noreplace) %{_sysconfdir}/plymouth/plymouthd.conf
%dir %{_prefix}/lib/kshim-freedom
%dir %{_prefix}/lib/kshim-freedom/cmdline.d
%{_prefix}/lib/kshim-freedom/cmdline.d/50-plymouth.conf
%dir %{_prefix}/lib/kshim-freedom/initramfs.d
%{_prefix}/lib/kshim-freedom/initramfs.d/50-plymouth.sh
%{_prefix}/lib/kshim-freedom/plymouth-init
%dir %{_unitdir}/plymouth-quit.service.d
%{_unitdir}/plymouth-quit.service.d/50-retain-splash.conf

%changelog
