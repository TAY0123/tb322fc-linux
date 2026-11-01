Name:           lsfg-vk-dual-runtime
Version:        2.0.0
Release:        2
Summary:        Bootstrap pinned LSFG runtimes from the owner's GitHub release
License:        GPL-3.0-or-later
URL:            https://github.com/h0cheung/tb322fc-linux
Source0:        lsfg-runtime-setup
Source1:        lsfg-v2
Source2:        VkLayer_LSFGVK_frame_generation_arm64.json
Source3:        VkLayer_LS_frame_generation_classic_arm64.json
Source4:        lsfg-vk-cli
BuildArch:      noarch
BuildRequires:  python3
Requires:       python3
Requires:       bsdtar
Requires:       ca-certificates
Requires:       libvulkan1
Requires:       libstdc++6

%description
Downloader and integration files only. At runtime, lsfg-runtime-setup retrieves
a fixed package from h0cheung/tb322fc-linux on GitHub, checks SHA256, and copies
an explicit allowlist of unmodified libraries, CLI, archives and their original
licenses into /var/lib/lsfg-vk. No LSFG runtime or source is hosted in this OBS
package. The user's purchased Lossless Scaling DLL is still required.

%prep
%build

%install
install -Dm755 %{SOURCE0} %{buildroot}%{_bindir}/lsfg-runtime-setup
install -Dm755 %{SOURCE1} %{buildroot}%{_bindir}/lsfg-v2
install -Dm755 %{SOURCE4} %{buildroot}%{_bindir}/lsfg-vk-cli
install -Dm644 %{SOURCE2} %{buildroot}/usr/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation_arm64.json
install -Dm644 %{SOURCE3} %{buildroot}/usr/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation_classic_arm64.json
sed -i 's|/usr/lib/|/var/lib/lsfg-vk/current/usr/lib/|g' %{buildroot}/usr/share/vulkan/implicit_layer.d/*.json
mkdir -p %{buildroot}/usr/lib/systemd/system/decky-loader@.service.d
printf '[Service]\nExecStartPre=-/usr/bin/lsfg-runtime-setup\n' > %{buildroot}/usr/lib/systemd/system/decky-loader@.service.d/00-lsfg-download.conf

%check
python3 -m py_compile %{SOURCE0}

%files
%{_bindir}/lsfg-runtime-setup
%{_bindir}/lsfg-v2
%{_bindir}/lsfg-vk-cli
%dir /usr/share/vulkan
%dir /usr/share/vulkan/implicit_layer.d
/usr/share/vulkan/implicit_layer.d/*.json
%dir /usr/lib/systemd
%dir /usr/lib/systemd/system
/usr/lib/systemd/system/decky-loader@.service.d

%changelog
