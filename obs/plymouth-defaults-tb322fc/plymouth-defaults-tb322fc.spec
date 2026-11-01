Name:           plymouth-defaults-tb322fc
Version:        1.0
Release:        0
Summary:        Plymouth display and button settings for Lenovo Legion Y700 Gen 4
License:        GPL-3.0-or-later
URL:            https://github.com/h0cheung/tb322fc-linux
Source0:        plymouthd.conf
Source1:        50-plymouth.conf
BuildArch:      noarch
Requires:       plymouth >= 26.134.222
Requires:       plymouth-branding-openSUSE
Requires:       plymouth-theme-bgrt >= 26.134.222
Requires:       plymouth-plugin-label-ft >= 26.134.222
Requires:       cantarell-fonts
Requires:       kshim-boot-argument-defaults >= 1

%description
Display scaling, landscape rendering and a Volume Up alternative to Escape
for the TB322FC tablet. Theme, artwork, colours and timing remain those of
the official openSUSE Plymouth branding. kShim incorporates the packaged
boot defaults when generating the boot image; explicit arguments win.

%prep

%build

%install
install -Dm644 %{SOURCE0} %{buildroot}%{_sysconfdir}/plymouth/plymouthd.conf
install -Dm644 %{SOURCE1} %{buildroot}%{_prefix}/lib/kshim-freedom/cmdline.d/50-plymouth.conf

%files
%dir %{_sysconfdir}/plymouth
%config(noreplace) %{_sysconfdir}/plymouth/plymouthd.conf
%dir %{_prefix}/lib/kshim-freedom
%dir %{_prefix}/lib/kshim-freedom/cmdline.d
%{_prefix}/lib/kshim-freedom/cmdline.d/50-plymouth.conf

%changelog
