#!/usr/bin/env bash
# Internal entry point, always invoked through in-rootfs.sh.
set -euo pipefail
[[ $EUID == 0 && $(uname -m) == aarch64 && -f /.tb322fc-opensuse-build ]] || exit 2
build=/usr/share/tb322fc/rootfs-build
[[ -s $build/obs-ready.json ]] || { echo 'Missing current OBS build verification.' >&2; exit 2; }
export SYSTEMD_OFFLINE=1 LC_ALL=C.UTF-8
rpm --import "$build"/*-signing-key.asc
zypper --non-interactive refresh --force

# The tablet boots through kShim, not the generic JeOS kernel or GRUB.
if rpm -q kernel-default >/dev/null 2>&1; then
    zypper --non-interactive remove kernel-default
fi
zypper --non-interactive addlock kernel-default kernel-default-base kernel-64kb kernel-vanilla \
    kernel-longterm kernel-longterm-base kernel-rt kernel-rt-base

# Select exact versions verified against OBS's current successful builds. Never
# fall back to an older published kernel or to a distribution device package.
python3 - "$build" > /run/tb322fc-device-packages <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
packages = json.loads((p/'packages.json').read_text())['device']
ready = json.loads((p/'obs-ready.json').read_text())
versions = ready['versions']
for name in packages:
    print(f'tb322fc:{name}={versions[name]}')
PY
mapfile -t device < /run/tb322fc-device-packages
python3 -c "import json; print('\n'.join(json.load(open('$build/packages.json'))['distribution']))" > /run/tb322fc-distribution-packages
mapfile -t distribution < /run/tb322fc-distribution-packages
(( ${#device[@]} > 0 && ${#distribution[@]} > 0 ))
zypper --non-interactive install --no-recommends --allow-vendor-change "${device[@]}" "${distribution[@]}"
zypper --non-interactive dist-upgrade --no-recommends --allow-vendor-change --no-allow-downgrade
# Install recommendations only for the explicitly selected desktop patterns;
# retain JeOS's no-recommends default for other package operations.
python3 -c "import json; print('\n'.join(json.load(open('$build/packages.json')).get('patterns_with_recommends', [])))" > /run/tb322fc-desktop-patterns
mapfile -t patterns < /run/tb322fc-desktop-patterns
if [[ ${patterns[0]:-} ]]; then
    zypper --non-interactive install --recommends --type pattern "${patterns[@]}"
fi
zypper --non-interactive verify

overlay=$build/overlay
cp -a "$overlay/audio/ucm2/." /usr/share/alsa/ucm2/
install -Dm644 "$overlay/camera/70-libcamera-dma-heap.rules" /etc/udev/rules.d/70-libcamera-dma-heap.rules
install -Dm644 "$overlay/camera/libcamera-qcam.desktop" /usr/share/applications/libcamera-qcam.desktop
install -Dm644 "$overlay/sensors/hexagonrpcd-sensors.service" /etc/systemd/system/hexagonrpcd-sensors.service
install -Dm644 "$overlay/sensors/iio-sensor-proxy.conf" /etc/systemd/system/iio-sensor-proxy.service.d/ssc.conf
for name in 61-sensor-matrix.rules 81-iio-sensor-proxy-proximity.rules; do
    install -Dm644 "$overlay/sensors/$name" "/etc/udev/rules.d/$name"
done
install -d -m700 /var/lib/hexagonrpc /var/lib/hexagonrpc/sensors
ln -sfn /sys/devices/soc0 /var/lib/hexagonrpc/socinfo
for service in hexagonrpcd-sensors iio-sensor-proxy; do
    install -d "/etc/systemd/system/$service.service.d"
    cat > "/etc/systemd/system/$service.service.d/require-device-data.conf" <<'EOF'
[Unit]
ConditionDirectoryNotEmpty=/var/lib/hexagonrpc/acdb
ConditionDirectoryNotEmpty=/var/lib/hexagonrpc/dsp
ConditionDirectoryNotEmpty=/var/lib/hexagonrpc/sensors/config
ConditionDirectoryNotEmpty=/var/lib/hexagonrpc/sensors/state/registry
ConditionPathExists=/var/lib/hexagonrpc/sensors/state/sns_reg_version
ConditionPathExists=/var/lib/hexagonrpc/sensors/sns_reg.conf
EOF
done
install -Dm755 "$overlay/power/armada-steam-charging-eta" /usr/libexec/armada/armada-steam-charging-eta
install -Dm644 "$overlay/power/armada-steam-charging-eta.service" /usr/lib/systemd/user/armada-steam-charging-eta.service
install -Dm644 "$overlay/power/gamescope-session-plus@steam.service.d/20-armada-steam-charging-eta.conf" \
    /usr/lib/systemd/user/gamescope-session-plus@steam.service.d/20-armada-steam-charging-eta.conf
# The desktop account is chosen in Plasma Setup; first-user.sh assigns this
# runtime directory after that account exists.
echo 'd /run/vpower 0755 root root -' > /etc/tmpfiles.d/vpower.conf

shopt -s nullglob
icds=(/usr/share/vulkan/icd.d/freedreno_icd*.json)
(( ${#icds[@]} == 1 )) || { echo 'Expected one native Freedreno Vulkan ICD.' >&2; exit 1; }
cat > /etc/environment <<EOF
GALLIUM_DRIVER=zink
MESA_LOADER_DRIVER_OVERRIDE=zink
VK_DRIVER_FILES=${icds[0]}
XMODIFIERS=@im=ibus
EOF
install -d /etc/sddm.conf.d /etc/systemd/system/display-manager.service.d /etc/systemd/system/sddm.service.d
cat > /etc/sddm.conf.d/80-tb322fc.conf <<'EOF'
[General]
DisplayServer=wayland
DefaultSession=/usr/share/wayland-sessions/plasmawayland.desktop
# Leave Qt's native Wayland input context enabled. Breeze's Wayland keyboard
# button controls KWin's input method rather than an embedded Qt InputPanel.
InputMethod=

[Theme]
Current=breeze-openSUSE

[Wayland]
CompositorCommand=kwin_wayland --drm --no-lockscreen --no-global-shortcuts --locale1 --inputmethod /usr/bin/plasma-keyboard

[Autologin]
# Plasma Setup temporarily overrides these in 99-plasma-setup.conf.
User=
Session=plasmawayland.desktop
Relogin=false
EOF
test -f /usr/share/wayland-sessions/plasmawayland.desktop
test -f /usr/share/sddm/themes/breeze-openSUSE/Main.qml
test -r /usr/share/wallpapers/openSUSEdefault/contents/images/1920x1200.png
install -d -m750 -o sddm -g sddm /var/lib/sddm
cat > /var/lib/sddm/state.conf <<'EOF'
[Last]
Session=/usr/share/wayland-sessions/plasmawayland.desktop
User=
EOF
chown sddm:sddm /var/lib/sddm/state.conf
chmod 600 /var/lib/sddm/state.conf
for service in display-manager sddm; do
    cat > "/etc/systemd/system/$service.service.d/graphics.conf" <<EOF
[Service]
Environment=GALLIUM_DRIVER=zink MESA_LOADER_DRIVER_OVERRIDE=zink VK_DRIVER_FILES=${icds[0]}
EOF
done
install -d /etc/wireplumber/wireplumber.conf.d
cat > /etc/wireplumber/wireplumber.conf.d/51-g9-alsa.conf <<'EOF'
monitor.alsa.rules = [
  {
    matches = [
      { device.name = "~alsa_card.usb-Sony_Interactive_Entertainment_Legion_Gaming_Controller_G9*" }
    ]
    actions = {
      update-props = {
        device.profile = "pro-audio"
        api.alsa.split-enable = false
        alsa.use-ucm = false
        api.alsa.use-acp = false
      }
    }
  }
]
EOF
echo y700-gen4 > /etc/hostname
cat > /etc/hosts <<'EOF'
127.0.0.1 localhost
::1 localhost
127.0.1.1 y700-gen4
127.0.0.1 steamloopback.host
EOF
echo LANG=en_US.UTF-8 > /etc/locale.conf
ln -sfn /usr/share/zoneinfo/UTC /etc/localtime
# Plasma Setup provides a touch-capable first boot. The JeOS console wizard
# cannot provide an on-screen keyboard, so it must not precede the greeter.
groupadd -f wheel
systemctl --root=/ disable jeos-firstboot.service
systemctl --root=/ mask jeos-firstboot.service
rm -f /var/lib/YaST2/reconfig_system
install -d /etc/xdg
cat > /etc/xdg/plasmasetuprc <<'EOF'
[Accounts]
UserGroups=wheel,video,input
EOF
cat > /etc/xdg/kwinrc <<'EOF'
[Wayland]
InputMethod=/usr/share/applications/org.kde.plasma.keyboard.desktop
VirtualKeyboardEnabled=true
EOF
systemd-sysusers /usr/lib/sysusers.d/plasma-setup-sysuser.conf
# openSUSE's SDDM reads this after its normal drop-ins and overwrites User=.
# The completion hook clears the temporary setup account again.
sed -i 's/^DISPLAYMANAGER_AUTOLOGIN=.*/DISPLAYMANAGER_AUTOLOGIN="plasma-setup"/' /etc/sysconfig/displaymanager
grep -qx 'DISPLAYMANAGER_AUTOLOGIN="plasma-setup"' /etc/sysconfig/displaymanager
install -Dm755 "$build/first-user.sh" /usr/libexec/tb322fc-first-user
cat > /etc/systemd/system/tb322fc-first-user.service <<'EOF'
[Unit]
Description=Prepare the first TB322FC desktop user's Steam and Decky directories
After=display-manager.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/libexec/tb322fc-first-user
EOF
cat > /etc/systemd/system/tb322fc-first-user.path <<'EOF'
[Unit]
Description=Finish TB322FC user setup after Plasma Setup completes

[Path]
PathExists=/etc/plasma-setup-done
Unit=tb322fc-first-user.service

[Install]
WantedBy=multi-user.target
EOF
install -d -m750 /etc/sudoers.d
cat > /etc/sudoers.d/90-tb322fc-wheel <<'EOF'
Defaults:%wheel !targetpw
%wheel ALL=(ALL:ALL) ALL
EOF
chmod 440 /etc/sudoers.d/90-tb322fc-wheel
visudo -cf /etc/sudoers.d/90-tb322fc-wheel
systemctl --root=/ enable NetworkManager bluetooth sshd chronyd hexagonrpcd-sensors plasma-setup tb322fc-first-user.path \
    als-bridge armada-powerd steamos-manager armada-control inputplumber \
    tb322fc-hall-lid tb322fc-gyro-bridge y700-charged
systemctl --root=/ enable --force sddm
systemctl --root=/ set-default graphical.target

# A generic image must acquire its machine identity and host keys on first boot.
passwd --lock root
truncate -s0 /etc/machine-id
rm -f /var/lib/dbus/machine-id /etc/ssh/ssh_host_*key /etc/ssh/ssh_host_*key.pub
rpm -qa --qf '%{NAME}\t%{VERSION}-%{RELEASE}\t%{ARCH}\n' | sort > "$build/installed-packages.tsv"
zypper --non-interactive clean --all
touch "$build/configured"
