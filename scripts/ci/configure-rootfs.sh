#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Internal entry point: called only inside the native AArch64 build chroot.
set -euo pipefail
[[ $EUID == 0 && $(uname -m) == aarch64 && -d /root/tb322fc-build/sources ]] || {
    echo 'Run build-rootfs.sh on a native AArch64 host; do not run this script on the host.' >&2
    exit 1
}
cd /root/tb322fc-build
export LC_ALL=C.UTF-8
JOBS=${JOBS:-$(nproc)}

# Disable CheckSpace in chroot where cachedir mount point cannot be probed via /proc/mounts.
sed -i 's/^[[:space:]]*CheckSpace/#CheckSpace/' /etc/pacman.conf

# The bootstrap may carry the distro's own kernel and its initramfs tooling.
# This staging root installs linux-freedom and its own boot tooling instead,
# so these bootstrap packages are unused;
# mkinitcpio's autodetect hook cannot work inside the build chroot, aborting
# with "failed to detect root filesystem" on every kernel upgrade. Drop them,
# if present, before the rolling upgrade would touch the kernel.
for package in linux-aarch64 mkinitcpio; do
    if pacman -Q "$package" >/dev/null 2>&1; then
        pacman -Rcns --noconfirm "$package"
    fi
done

# Keep package signatures enabled. The authenticated bootstrap contains the
# distro keyring; update it before the full rolling-release upgrade.
pacman-key --init
pacman-key --populate archlinux

# forge/core/extra packages - archlinux-keyring and archports-keyring included -
# are signed by the Arch Linux Ports key, which the bootstrap does not ship.
# Trust the key published next to the packages first; the fingerprint is pinned,
# so a substituted key fails the local signature. Then install the keyring
# package so its revoked-key list is authoritative.
curl --fail --location --retry 5 --proto '=https' --proto-redir '=https' \
    --output /tmp/archports.key \
    "https://arch-linux-repo.drzee.net/arch/extra/os/aarch64/public.key"
pacman-key --add /tmp/archports.key
pacman-key --lsign-key 9B2C213B21883BB65CE2FB900CF25682E6BA0751
rm -f /tmp/archports.key
pacman -Sy --noconfirm
pacman -S --noconfirm archports-keyring
pacman-key --populate archports

# The Ports key is trusted now, so every later download can be verified.
pacman -Sy --noconfirm archlinux-keyring
pacman -Syu --noconfirm
runtime_packages=(
    base systemd systemd-sysvcompat linux-firmware kmod sudo nano less
    networkmanager wpa_supplicant iw bluez bluez-utils
    plasma-desktop plasma-mobile plasma-settings sddm plasma-keyboard
    plasma-nm plasma-pa powerdevil polkit-kde-agent plasma-integration breeze kscreen
    xdg-desktop-portal-kde xorg-xwayland kwallet-pam bluedevil
    dolphin konsole spectacle firefox
    mesa vulkan-freedreno vulkan-icd-loader mesa-utils vulkan-tools
    alsa-ucm-conf alsa-utils pipewire pipewire-audio pipewire-alsa pipewire-pulse wireplumber
    noto-fonts noto-fonts-cjk ibus ibus-libpinyin
    libqmi protobuf-c glib2 libgudev polkit libyaml libevent qt6-base python python-gobject
    scx-scheds thermald
)
build_packages=(
    base-devel linux-api-headers meson ninja git python pkgconf clang llvm llvm-libs ccache
    glib2-devel protobuf gobject-introspection vala gettext
    python-jinja python-ply python-yaml openssl
)
pacman -S --needed --noconfirm "${runtime_packages[@]}" "${build_packages[@]}"

# Persistent caches, injected into the chroot by build-rootfs.sh and saved by
# the workflow. Downloads are always reusable; the compiled package and meson
# caches are gated by a dependency stamp so a rolling-release ABI bump rebuilds
# them instead of reusing stale objects. The cache lives outside /root because
# makepkg runs as the unprivileged alarm user and has to write into it.
CACHE=/var/cache/tb322fc-build
# shellcheck source=scripts/ci/configure-cache.sh
source ./configure-cache.sh


# Apply verified device firmware after distro package installation. Never copy
# directory contents from the input bundle that are absent from firmware.json.
python3 - <<'PY'
import json
from pathlib import Path
import shutil

for item in json.loads(Path('/usr/share/tb322fc/firmware.json').read_text())['files']:
    source = Path('firmware') / item['path']
    target = Path('/usr/lib/firmware') / item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o644)
# Freedom's Elden DT uses the board-qualified path for the same signed ZAP.
# Derive it from the verified payload, preserving the existing bundle manifest.
zap = Path('/usr/lib/firmware/qcom/sm8750/gen80000_zap.mbn')
board_zap = zap.parent / 'lenovo/elden/gen80000_zap.mbn'
board_zap.parent.mkdir(parents=True, exist_ok=True)
board_zap.unlink(missing_ok=True)
shutil.copyfile(zap, board_zap)
board_zap.chmod(0o644)
PY

mkdir -p build /usr/share/tb322fc/meson
build_component() {
    local component=$1
    shift
    local tarball="$CACHE/meson/$component.tar"
    local tree
    tree=$(python3 -c "import json, pathlib; print(json.loads(pathlib.Path('/usr/share/tb322fc/sources.json').read_text())['$component']['tree'])" 2>/dev/null || true)
    if [[ -f "$tarball" && -n "$tree" && -f "$CACHE/meson/$component.tree" && "$(cat "$CACHE/meson/$component.tree")" == "$tree" ]]; then
        echo "meson cache: restoring $component"
        tar -C / -xf "$tarball" --no-overwrite-dir
        ldconfig
        return
    fi
    local stage
    stage=$(mktemp -d)
    # mktemp -d creates 0700 and the archive records "." with the stage's mode,
    # so without this the install step below would chmod the live rootfs "/" to
    # 0700 and lock every non-root user out of the tree.
    chmod 755 "$stage"
    meson setup "build/$component" "sources/$component" --prefix=/usr --libdir=lib \
        --buildtype=release --wrap-mode=nodownload -Dwerror=false \
        -Dc_args="-Wno-error" -Dcpp_args="-Wno-error -Wno-error=array-bounds" "$@"
    meson compile -C "build/$component" -j "$JOBS"
    DESTDIR="$stage" meson install -C "build/$component"
    mkdir -p "$stage/usr/share/tb322fc/meson"
    cp "build/$component/meson-info/intro-buildoptions.json" "$stage/usr/share/tb322fc/meson/$component.json"
    tar -C "$stage" -cf "$tarball.part" .
    mv "$tarball.part" "$tarball"
    if [[ -n "$tree" ]]; then
        printf '%s\n' "$tree" > "$CACHE/meson/$component.tree"
    fi
    rm -rf "$stage"
    # The staged install is the cache entry; also install it into the live rootfs.
    # --no-overwrite-dir keeps pre-existing directory modes (notably "/") intact.
    tar -C / -xf "$tarball" --no-overwrite-dir
    ldconfig
}
build_component hexagonrpc
build_component libssc
build_component libcamera -Dpipelines=simple -Dipas=softisp -Dqcam=enabled -Dcam=enabled \
    -Ddocumentation=disabled -Dgstreamer=disabled -Dpycamera=disabled \
    -Dlc-compliance=disabled -Dv4l2=disabled -Dsoftisp-gpu=disabled \
    -Dapps-output-dng=disabled -Dtest=false -Dwerror=false \
    -Dcpp_args="-Wno-error -Wno-error=array-bounds"

# Keep pacman upgrades from replacing the patched libraries with distro builds.
# Manual installation of a conflicting package must first remove this guard
# and rebuild the device support; these builds are recorded in sources.json.
# iio-sensor-proxy is not listed: it ships as a renamed package
# (iio-sensor-proxy-y700) that provides/conflicts/replaces the repo package.
sed -i '/^\[options\]$/a IgnorePkg = hexagonrpc libssc libcamera libcamera-ipa libcamera-tools' /etc/pacman.conf
# The device thermal policy is written by this script and is not owned by the
# thermald package, so pin it: a future package that ships its own
# thermal-conf.xml must never overwrite it (pacman drops the package's copy as
# a .pacnew instead, and the overlay copy stays authoritative).
sed -i '/^\[options\]$/a NoUpgrade = etc/thermald/thermal-conf.xml' /etc/pacman.conf

# Point the image at this project's rolling package repository: the CI publishes
# userspace packages to the `repository-freedom-v2` pre-release,
# so the device can update them with plain pacman. Unsigned, like those assets.
cat >> /etc/pacman.conf <<'EOF'

[tb322fc]
SigLevel = Optional TrustAll
Server = https://github.com/h0cheung/tb322fc-linux/releases/download/repository-freedom-v2
EOF
# Fetch that database now. pacman refuses to prepare *any* transaction while a
# configured sync database is still missing ("could not find database"), and
# the build loop below installs dependencies with plain `pacman -S`.
# init-repo.sh publishes valid empty databases before the first build.
# A network/server failure must not silently masquerade as an empty repository.
curl --fail --location --retry 5 --output /var/lib/pacman/sync/tb322fc.db.part \
    https://github.com/h0cheung/tb322fc-linux/releases/download/repository-freedom-v2/tb322fc.db
bsdtar -tf /var/lib/pacman/sync/tb322fc.db.part >/dev/null
mv /var/lib/pacman/sync/tb322fc.db.part /var/lib/pacman/sync/tb322fc.db

# Allow building AUR/local packages that only specify x86_64 in PKGBUILD arch array.
echo 'IGNOREARCH=1' >> /etc/makepkg.conf

# Kernel, headers and DKMS are built natively below, after the build user exists.
python stage-freedom-wifi-firmware.py --manifest /usr/share/tb322fc/freedom-wifi-firmware.json \
    --source freedom-firmware --root /

# Preserve upstream UCM as a diagnostic backup before the device overlay.
tar -C /usr/share/alsa -czf /usr/share/tb322fc/ucm2-before-overlay.tar.gz ucm2
cp -a overlay/audio/ucm2/. /usr/share/alsa/ucm2/
install -Dm644 overlay/camera/70-libcamera-dma-heap.rules /etc/udev/rules.d/70-libcamera-dma-heap.rules
install -Dm644 overlay/camera/libcamera-qcam.desktop /usr/share/applications/libcamera-qcam.desktop
install -Dm644 overlay/sensors/hexagonrpcd-sensors.service /etc/systemd/system/hexagonrpcd-sensors.service
install -Dm644 overlay/sensors/iio-sensor-proxy.conf /etc/systemd/system/iio-sensor-proxy.service.d/ssc.conf
install -Dm644 overlay/sensors/61-sensor-matrix.rules /etc/udev/rules.d/61-sensor-matrix.rules
install -Dm644 overlay/sensors/81-iio-sensor-proxy-proximity.rules /etc/udev/rules.d/81-iio-sensor-proxy-proximity.rules
# Battery charge thresholds are owned at runtime by y700-charged
# (packages/y700-charge): it applies the configured limit and re-applies it on
# USB events, and ships the UPower hwdb entry that exposes the limit to KDE.
# Steam Game Mode charging ETA: a small bridge republishes UPower's battery
# estimates into the vpower files Game Mode reads (ported from armada PR #463).
install -Dm755 overlay/power/armada-steam-charging-eta /usr/libexec/armada/armada-steam-charging-eta
install -Dm644 overlay/power/armada-steam-charging-eta.service /usr/lib/systemd/user/armada-steam-charging-eta.service
install -Dm644 overlay/power/gamescope-session-plus@steam.service.d/20-armada-steam-charging-eta.conf \
    /usr/lib/systemd/user/gamescope-session-plus@steam.service.d/20-armada-steam-charging-eta.conf
install -Dm644 overlay/power/vpower.conf /etc/tmpfiles.d/vpower.conf
install -d -m 700 /var/lib/hexagonrpc /var/lib/hexagonrpc/sensors
ln -s /sys/devices/soc0 /var/lib/hexagonrpc/socinfo

# Device thermal policy is maintained by the overlay independently of the
# Arch Linux Ports thermald package installed above.
# The config must be root-owned and not group/world-writable, or thermald's
# open_validated_xml_file() refuses it with EPERM; regenerate it with
# rootfs/thermald/gen_thermal_conf.py when the policy changes.  The drop-in
# runs thermald with --exclusive-control, because upstream's --adaptive engine
# ignores thermal-conf.xml.
install -Dm644 overlay/thermald/thermal-conf.xml /etc/thermald/thermal-conf.xml
install -Dm755 overlay/thermald/adapt_thermal_conf.py /usr/libexec/tb322fc/adapt-thermal-conf
install -Dm755 overlay/power/hud-temps.sh /usr/local/bin/hud-temps.sh
install -Dm644 overlay/thermald/exclusive.conf \
    /etc/systemd/system/thermald.service.d/exclusive.conf
# Enablement is harmless before calibration is installed: both services are
# gated on the same required paths, including the per-device registry state.
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


# Turnip (Vulkan) plus Zink (OpenGL) is the tested A830 graphics path.
shopt -s nullglob
icds=(/usr/share/vulkan/icd.d/freedreno_icd*.json)
(( ${#icds[@]} == 1 )) || { echo 'Expected one native Freedreno Vulkan ICD.' >&2; exit 1; }
cat > /etc/environment <<EOF
GALLIUM_DRIVER=zink
MESA_LOADER_DRIVER_OVERRIDE=zink
VK_DRIVER_FILES=${icds[0]}
XMODIFIERS=@im=ibus
EOF
install -d /etc/sddm.conf.d /etc/systemd/system/sddm.service.d
cat > /etc/sddm.conf.d/20-autologin-user.conf <<'EOF'
[Autologin]
User=alarm
EOF
cat > /etc/sddm.conf.d/zz-holo-autologin.conf <<'EOF'
[Autologin]
Session=plasma-mobile.desktop
EOF
cat > /etc/systemd/system/sddm.service.d/graphics.conf <<EOF
[Service]
Environment=GALLIUM_DRIVER=zink MESA_LOADER_DRIVER_OVERRIDE=zink VK_DRIVER_FILES=${icds[0]}
EOF
# Keep IBus available to Steam without forcing Qt's input context globally.
# Plasma Mobile supplies its own on-screen keyboard through plasma-keyboard.
install -d /etc/xdg
cat > /etc/xdg/kwinrc <<'EOF'
[Wayland]
VirtualKeyboardEnabled=true
EOF

sed -i -E 's/^#(en_US.UTF-8 UTF-8|zh_CN.UTF-8 UTF-8)$/\1/' /etc/locale.gen
locale-gen
echo 'LANG=en_US.UTF-8' > /etc/locale.conf
ln -sf /usr/share/zoneinfo/UTC /etc/localtime
echo 'y700-gen4' > /etc/hostname
cat > /etc/hosts <<'EOF'
127.0.0.1 localhost
::1 localhost
127.0.1.1 y700-gen4
# The Steam UI's render transport (steamui <-> steamwebhelper websocket) is
# served from https://steamloopback.host; it must resolve to loopback, not
# through DNS (a TUN/fake-ip resolver hijacks it and the UI stays black).
127.0.0.1 steamloopback.host
EOF
# The G9 (PS5 mode) emulates a DualSense, and alsa-ucm-conf ships a DualSense
# UCM profile that maps its stereo UAC playback to an Internal Mono Speaker
# node - mono data on a stereo DAC plays as static. Its jack-detection
# kcontrols never update either, so the Headphones routes are always marked
# unavailable and wireplumber refuses to default to them. Use the raw
# pro-audio profile for this card: plain stereo nodes, always available.
mkdir -p /etc/wireplumber/wireplumber.conf.d
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
cat > /etc/fstab <<'EOF'
# kShim's initramfs selects root by PARTUUID and probes ext4/F2FS itself.
# Do not add a conflicting partition label or filesystem type here.
binder /dev/binderfs binder defaults,nofail 0 0
EOF

# gamescope from the Arch repo ships without the filecap SteamOS bakes into
# its own package; without CAP_SYS_NICE it cannot use realtime scheduling and
# logs a perf warning. A libalpm path hook re-applies the cap on every
# install/upgrade transaction that touches the binary.
mkdir -p /usr/share/libalpm/hooks
cat > /usr/share/libalpm/hooks/gamescope-cap-sys-nice.hook <<'EOF'
[Trigger]
Operation = Install
Operation = Upgrade
Type = Path
Target = usr/bin/gamescope

[Action]
Description = Applying CAP_SYS_NICE filecap to gamescope
When = PostTransaction
Exec = /usr/bin/setcap cap_sys_nice+ep /usr/bin/gamescope
EOF
if ! id alarm >/dev/null 2>&1; then
    useradd -m -s /bin/bash alarm
fi
usermod -aG wheel,video,input alarm
echo 'alarm:alarm' | chpasswd
chage -d 0 alarm
# makepkg runs as alarm and writes the shared source/package cache, so hand it
# over now that the user exists.
chown -R alarm:alarm "$CACHE"
passwd -l root
install -d -m 750 /etc/sudoers.d
echo '%wheel ALL=(ALL:ALL) ALL' > /etc/sudoers.d/10-wheel
chmod 440 /etc/sudoers.d/10-wheel
visudo -cf /etc/sudoers.d/10-wheel

export CACHE JOBS
bash build-freedom-kernel.sh
release=$(cat /usr/share/tb322fc/kernel.release)

# The pinned mesa PKGBUILD builds from a signed upstream tarball, so makepkg
# checks its signature against the *user's* gpg keyring. The repo ships the
# needed keys under packages/*/keys/pgp/*.asc, but makepkg only copies them
# into --allsource output - it never imports them into a keyring, so without
# this the first signed source fails with "unknown public key
# 8D8E31AFC32428A6". Import as alarm, since that is who runs makepkg.
shopt -s nullglob
key_files=(packages/*/keys/pgp/*.asc)
shopt -u nullglob
if (( ${#key_files[@]} )); then
    for key_file in "${key_files[@]}"; do
        sudo -u alarm gpg --batch --no-tty --quiet --import "$key_file"
    done
else
    echo "no PGP keys under packages/*/keys/pgp; skipping import"
fi

# Query the project rolling package repository (configured above) to check which
# packages are already built and available on the repository release.
declare -A repo_versions=()
while read -r _repo _name _ver _rest; do
    repo_versions[$_name]=$_ver
done < <(pacman -Sl tb322fc 2>/dev/null || true)

declare -A pkg_virtual_providers=([inputplumber]=inputplumber-g9-2026)
declare -A pkg_paths=()
declare -A pkg_deps=()
declare -A pkg_fullver=()
declare -A pkg_splits=()
for pkg_dir in packages/*/; do
    [[ -f "$pkg_dir/PKGBUILD" ]] || continue
    # Boot-related packages are handled separately.
    case "$pkg_dir" in
        packages/linux-freedom/|packages/als-bridge-dkms/|packages/kshim-freedom/) continue ;;
    esac
    mapfile -t info < <(sudo -u alarm bash -c \
        "source '$pkg_dir/PKGBUILD' && _fv=\"\$pkgver-\$pkgrel\"; (( \${epoch:-0} > 0 )) && _fv=\"\$epoch:\$_fv\"; _dyn=0; declare -F pkgver >/dev/null && _dyn=1; printf '%s\n%s\n%s\n%s\n%s\n' \"\${pkgname[0]}\" \"\$_fv\" \"\${depends[*]} \${makedepends[*]} \${checkdepends[*]}\" \"\${pkgname[*]}\" \"\$_dyn\"")
    pkgbase=${info[0]}
    pkg_paths[$pkgbase]=$pkg_dir
    pkg_fullver[$pkgbase]=${info[1]}
    pkg_deps[$pkgbase]=${info[2]:-}
    pkg_splits[$pkgbase]=${info[3]}
    is_dyn=${info[4]:-0}

    # For dynamic VCS packages, fetch sources and execute pkgver() to determine the actual target version.
    if (( is_dyn == 1 )); then
        pkg_workdir=$(mktemp -d -p /home/alarm "pkgver-$pkgbase.XXXXXX")
        cp -a "$pkg_dir/." "$pkg_workdir/"
        chown -R alarm:alarm "$pkg_workdir"
        echo "Fetching sources and running pkgver() for dynamic VCS package $pkgbase..."
        if sudo -u alarm bash -c "cd '$pkg_workdir' && makepkg -o --nodeps >/dev/null 2>&1"; then
            resolved_ver=$(sudo -u alarm bash -c "cd '$pkg_workdir' && source PKGBUILD && _fv=\"\$pkgver-\$pkgrel\"; (( \${epoch:-0} > 0 )) && _fv=\"\$epoch:\$_fv\"; printf '%s' \"\$_fv\"")
            if [[ -n "$resolved_ver" ]]; then
                pkg_fullver[$pkgbase]=$resolved_ver
                echo "$pkgbase resolved dynamic version: $resolved_ver"
            fi
        fi
        rm -rf "$pkg_workdir"
    fi
done

# Separate packages into those installable directly from the repository vs
# those that need to be built (due to missing assets or version bumps).
repo_install=()
to_build=()
for pkg_name in "${!pkg_paths[@]}"; do
    expected_ver=${pkg_fullver[$pkg_name]}
    in_repo=1
    # Mesa must match this runner's rolling LLVM ABI, not only pkgver.
    [[ $pkg_name == mesa-y700-gen4 ]] && in_repo=0
    for split in ${pkg_splits[$pkg_name]}; do
        if [[ "${repo_versions[$split]:-}" != "$expected_ver" ]]; then
            in_repo=0
            break
        fi
    done
    if (( in_repo )); then
        for split in ${pkg_splits[$pkg_name]}; do
            repo_install+=("tb322fc/$split")
        done
        echo "repo: $pkg_name $expected_ver is available in tb322fc repository"
    else
        to_build+=("$pkg_name")
        echo "build: $pkg_name $expected_ver is missing or updated in repo; will build with makepkg"
    fi
done

# Install all packages that exist in the repository with matching versions.
# pacman resolves intra-repo dependencies automatically.
#
# --ask 6 (REPLACE_PKG | CONFLICT_PKG) is required here for the same reason the
# makepkg path below uses it: several of our packages are renamed builds that
# stand in for their repo counterpart via provides + conflicts/replaces (mesa,
# gamescope, iio-sensor-proxy). In a fresh rootfs the repo counterpart is pulled
# in as a dependency (e.g. iio-sensor-proxy via powerdevil), so installing ours
# has to auto-remove it. Without --ask, --noconfirm answers the "Remove X?" prompt
# with its default (No) and pacman aborts with "unresolvable package conflicts".
if (( ${#repo_install[@]} )); then
    echo "Installing ${#repo_install[@]} package(s) from tb322fc repository..."
    pacman -S --needed --noconfirm --ask 6 "${repo_install[@]}"
fi

# Collect the packages a successful makepkg run just produced. The version is
# read back from the checked-out tree (makepkg --packagelist re-runs pkgver())
# instead of from the pre-scan above: a -git package tracking a moving branch
# can resolve to a newer version during the build than it did during the
# pre-scan, and globbing by the stale version then matches nothing - which used
# to hand pacman an empty argument ("error: '': wrong or NULL argument
# passed"). Filtering by the PKGBUILD's split names also drops makepkg's
# auto-generated -debug package, which is built but never installed.
_collect_built() {
    local _pkg=$1 _workdir=$2 _path _base _split
    while IFS= read -r _path; do
        [[ -n $_path ]] || continue
        _base=${_path##*/}
        for _split in ${pkg_splits[$_pkg]}; do
            [[ $_base == "$_split"-* && $_base != "$_split"-debug-* ]] && { printf '%s\n' "$_path"; break; }
        done
    done < <(sudo -u alarm bash -c "cd '$_workdir' && makepkg --packagelist" 2>/dev/null)
}

pending=("${to_build[@]}")
for _pass in 1 2 3; do
    (( ${#pending[@]} )) || break
    deferred=()
    for pkg_name in "${pending[@]}"; do
        pkg_dir=${pkg_paths[$pkg_name]}
        read -ra deps_list <<< "${pkg_deps[$pkg_name]}"
        mapfile -t pkg_missing < <(pacman -T "${deps_list[@]}" || true)
        install_list=()
        has_unmet_repo_dep=0
        for dep in "${pkg_missing[@]}"; do
            dep_name=${dep%%[\<\>\=]*}
            provider=${pkg_virtual_providers[$dep_name]:-$dep_name}
            if [[ -n "${pkg_paths[$provider]:-}" ]]; then
                has_unmet_repo_dep=1
            else
                install_list+=("$dep")
            fi
        done
        if (( has_unmet_repo_dep )); then
            deferred+=("$pkg_name")
            continue
        fi
        if (( ${#install_list[@]} )); then
            pacman -S --needed --noconfirm "${install_list[@]}"
        fi
        pkg_workdir=$(mktemp -d -p /home/alarm "pkg-$pkg_name.XXXXXX")
        cp -a "$pkg_dir/." "$pkg_workdir/"
        chown -R alarm:alarm "$pkg_workdir"
        pkg_log=$(sudo -u alarm mktemp -p /home/alarm "mk-$pkg_name.XXXXXX")
        echo "Building $pkg_name with makepkg..."
        if sudo -u alarm bash -c "cd '$pkg_workdir' && makepkg -f --skippgpcheck >'$pkg_log' 2>&1" \
            && mapfile -t built < <(_collect_built "$pkg_name" "$pkg_workdir") \
            && (( ${#built[@]} )) \
            && pacman -U --noconfirm --ask 6 "${built[@]}" ; then
            rm -rf "$pkg_workdir" "$pkg_log"
        else
            echo "Deferring $pkg_name; last makepkg output:" >&2
            tail -20 "$pkg_log" >&2
            deferred+=("$pkg_name")
            rm -rf "$pkg_workdir" "$pkg_log"
        fi
    done
    pending=("${deferred[@]}")
done
(( ${#pending[@]} == 0 )) || { echo "Packages failed to build: ${pending[*]}" >&2; exit 1; }

# Ensure packages downloaded by pacman from tb322fc repo into /var/cache/pacman/pkg
# are present in $CACHE/pkgs alongside freshly built ones, so publish-repo.sh can
# maintain the complete package set and database.
# Only copy packages that actually belong to our packages/ definitions,
# never copy generic distro packages or signature files.
for pkg_name in "${!pkg_paths[@]}"; do
    for split in ${pkg_splits[$pkg_name]}; do
        for f in /var/cache/pacman/pkg/"$split"-[0-9]*.pkg.tar.*; do
            [[ -f "$f" && "$f" != *.sig ]] || continue
            cp -n "$f" "$CACHE/pkgs/" 2>/dev/null || true
        done
    done
done

# Prune $CACHE/pkgs to ensure it contains only packages defined in our repository,
# and remove any signature (.sig) or stray files that would break repo-add.
declare -A project_splits=([linux-freedom]=1 [linux-freedom-headers]=1 [als-bridge-dkms]=1 [kshim-freedom]=1)
for pkg_name in "${!pkg_paths[@]}"; do
    for split in ${pkg_splits[$pkg_name]}; do
        project_splits["$split"]=1
    done
done

shopt -s nullglob
for f in "$CACHE/pkgs"/*; do
    [[ -f "$f" ]] || continue
    fname=$(basename "$f")
    if [[ "$fname" == *.sig ]]; then
        rm -f "$f"
        continue
    fi
    matched=0
    for split in "${!project_splits[@]}"; do
        if [[ "$fname" == "$split"-[0-9]* ]]; then
            matched=1
            break
        fi
    done
    if (( matched == 0 )); then
        rm -f "$f"
    fi
done
shopt -u nullglob

# Keep exactly the installed versions, including the four coordinated boot packages.
for file in "$CACHE/pkgs/"*.pkg.tar.*; do
    [[ -f "$file" && "$file" != *.sig ]] || continue
    read -r cached_name cached_version < <(pacman -Qp "$file")
    installed_version=$(pacman -Q "$cached_name" 2>/dev/null | cut -d' ' -f2) || installed_version=
    [[ $cached_version == "$installed_version" ]] || rm -f -- "$file"
done

# Use the stable Freedom-aligned Mesa splits built by the loop above.
# Check after installation; these renamed packages do not exist in stock Arch.
for package in mesa-y700-gen4 vulkan-freedreno-y700-gen4; do
    version=$(pacman -Q "$package" 2>/dev/null | cut -d' ' -f2) || true
    [[ -n "$version" ]] || { echo "$package was not installed by the build loop" >&2; exit 1; }
    if (( $(vercmp "${version#*:}" 26.2.1) < 0 )); then
        echo "$package $version is below this CI's tested Adreno 830 baseline (26.2.1)." >&2
        exit 1
    fi
done

cat > /etc/issue <<'EOF'
Arch Linux Ports on Lenovo Y700 Gen 4 (TB322FC)
Initial login: alarm / alarm. Change the password at first login.
EOF

# Use NetworkManager as the sole network manager. Never enable SSH by default.
for service in systemd-networkd.service systemd-networkd.socket systemd-networkd-wait-online.service dhcpcd.service sshd.service sshd.socket; do
    if [[ -f /usr/lib/systemd/system/$service || -L /etc/systemd/system/$service ]]; then
        systemctl disable "$service"
    fi
done
# MTP is controlled on demand through Freedom Control. Do not inherit an old
# image's enablement; connecting a controller must not start a USB gadget.
# Steam's power-key handler is pulled in by its packaged per-session drop-in,
# rather than enabled globally for desktop sessions.
systemctl disable armada-mtp.service >/dev/null 2>&1 || true
systemd-tmpfiles --create /usr/lib/tmpfiles.d/freedom-diagnostics.conf
systemctl enable NetworkManager.service bluetooth.service sddm.service hexagonrpcd-sensors.service als-bridge.service armada-powerd.service thermald.service steamos-manager.service armada-control.service armada-decky-sync.service decky-loader@alarm.service tb322fc-hall-lid.service tb322fc-gyro-bridge.service y700-charged.service
systemctl set-default graphical.target
systemctl --global enable pipewire.socket pipewire-pulse.socket wireplumber.service armada-steam-charging-eta.service steamos-manager.service steamos-manager-session-cleanup.service

# Record both pacman packages and the source-built components.
pacman -Q > /usr/share/tb322fc/rootfs.packages
{
    printf 'kernel_release=%s\n' "$release"
    printf 'architecture=%s\n' "$(uname -m)"
    printf 'ccache=%s\n' "$(ccache --version | head -1)"
    printf 'meson=%s\n' "$(meson --version)"
    printf 'hexagonrpc=from-sources.json\n'
    printf 'libssc=%s\n' "$(pkg-config --modversion libssc)"
    printf 'libcamera=%s\n' "$(pkg-config --modversion libcamera)"
    printf 'iio-sensor-proxy=%s\n' "$(pacman -Q iio-sensor-proxy-y700 2>/dev/null | awk '{print $2}')"
} > /usr/share/tb322fc/userspace-build.txt
ccache --show-stats > /usr/share/tb322fc/ccache.txt
[[ -x /usr/bin/hexagonrpcd && -x /usr/libexec/iio-sensor-proxy && -x /usr/bin/qcam && -x /sbin/init ]]
[[ -f /usr/share/wayland-sessions/plasma-mobile.desktop ]]
# Leave build tools installed for diagnosis. Remove downloads, host identities
# and transient state; package signatures and the distro trust database remain.
pacman -Scc --noconfirm
rm -f /etc/machine-id /var/lib/dbus/machine-id /var/lib/systemd/random-seed
: > /etc/machine-id
ln -s /etc/machine-id /var/lib/dbus/machine-id
rm -f /etc/ssh/ssh_host_* /root/.bash_history
find /var/log -type f -exec truncate -s 0 {} +
