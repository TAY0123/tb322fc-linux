# Rootfs setup

The maintained image targets openSUSE Tumbleweed AArch64 on Lenovo TB322FC.
See [CI and local build instructions](opensuse-ci.md) for the matching rootfs
and boot artifacts. The older Arch integration is retained for reference below.
This project does not repartition the tablet.

## openSUSE configuration

The builder verifies a signed official JeOS bootstrap and the current published
packages from `home:h-cheung:tb322fc`. It refuses stale or failed required OBS
builds and uses the published Tumbleweed package repository as its base.
Package installation uses a disposable mount/PID namespace; no RPM is installed
into the host. No osc account or API token is needed for image assembly.

`configs/opensuse/packages.json` explicitly selects the `kde_plasma` pattern
with recommendations, without the full KDE office/PIM/games application set.
Other packages retain JeOS's no-recommends policy. Plasma Desktop, Plasma Mobile,
Steam, the virtual keyboard and the openSUSE Plasma/SDDM branding and wallpaper
packages are included. `xdg-utils` provides `xdg-su` and `xdg-open`; `xauth`
supports KDE's graphical privilege helper. If adding YaST, also install
`libyui-qt16` and `libyui-qt-pkg16` for its graphical package interface.

Plasma Setup creates the owner's account and configures language, time zone
and Wi-Fi. SDDM uses Breeze-openSUSE and Plasma Keyboard through KWin. The first
user joins `wheel`, `video` and `input`; sudo requires that user's password.
Completing setup returns to the greeter, which offers Plasma Desktop (initial
default), Plasma Mobile and Steam. The completion hook initializes Steam/Decky
for the chosen user. There is no fixed username, preset password, SSH key
import hook or passwordless-sudo configuration.

openSUSE reads the SDDM autologin account from
`/etc/sysconfig/displaymanager`. Only the temporary `plasma-setup` account is
selected before first boot, and the completion hook clears it. Subsequent
autologin/session choices belong to the user and SteamOS Manager; the image
does not pin a human account or override its session drop-ins.

The SSC backend and the libkscreen rotation-lock patch are included. Desktop
startup, touch/virtual-keyboard account creation, Plasma Mobile, automatic
brightness and rotation persistence were tested on the tablet. These results
do not establish a complete suspend or game compatibility regression pass.

Model firmware is copied only from the fixed manifests. The public image
contains empty Hexagon data scaffolding; sensor services wait for the target
tablet's own data. Import that data into the installed filesystem using the
instructions below. Never import it into a tree that will be distributed.
Both the tarball exporter and F2FS image builder reject populated calibration,
user accounts, SSH trust/host keys, private signing keys and machine identity.
Steam and LSFG payloads are obtained by their runtime helpers.

### F2FS settings

The profile follows Y700 Gen4 TWRP's
[device fstab](https://github.com/polygraphene/android_device_lenovo_TB322FC/blob/c9c6a9f1287e5b416c3480c5fe06b23dc54c9ab8/recovery.fstab#L47)
and [formatting code](https://github.com/polygraphene/android_bootable_recovery/blob/ced4ad75f311fc8a3350e21de415c23d5f0aec74/partition.cpp#L2552).
It uses 4096-byte sectors/blocks, `-g android`, and
`-O project_quota,extra_attr`. Formatting a sparse local image additionally
uses `-t 0`; this does not disable runtime discard.

The Android profile creates internal quota files. The boot kernel therefore
needs built-in `CONFIG_QFMT_V2=y` as well as F2FS support. The image writer now
checks that requirement. The first 7.2.6-27 RPM lacked this format: file I/O
continued, but quota accounting was skipped and marked for repair. The OBS
kernel configuration was updated in source revision 7. On 2026-11-01,
`7.2.6-28-freedom` was installed and the unmounted root partition was checked
in TWRP. Fsck rebuilt all three quota files; an independent dry-run passed and
the `quota_need_fsck` flag cleared. After booting the new kernel, `Q_GETFMT`
confirmed active user, group and project quotas, all using VFS v1 format.

For offline maintenance, openSUSE's `fsck.f2fs` 1.16 requires a numeric argument
after `-q`, although its short help omits that argument. Use `-f -q 1` for
repair while preserving limits, and `-f --dry-run -q 1` for verification.
Confirm that the verification log explicitly says `Info: Dry run`. A plain
`-q --dry-run` consumes the latter as the quota option's argument and therefore
does not perform a dry-run. Never repair the mounted root filesystem.

The root mount options are:

```text
rw,noatime,discard,reserve_root=32768,resuid=0,resgid=0,fsync_mode=posix,errors=remount-ro
```

The 32768 reserved 4 KiB blocks retain TWRP's 128 MiB root reserve. The Android
reserved GID 1065 becomes Linux root's GID 0. Root needs device nodes and setuid
programs, so TWRP's `nodev,nosuid` are not copied. POSIX fsync with write barriers
is retained instead of `fsync_mode=nobarrier`. Android encryption, inline crypto,
metadata-key paths and checkpoint-manager options are not copied; this Linux
root is unencrypted. TWRP's optional casefold/compression formatting paths are
not enabled automatically. The filesystem UUID is written into the image's
`fstab`; kShim still selects the partition by PARTUUID, and systemd applies the
full mount options after handoff.

## Base system

The rootfs needs an executable `/sbin/init`, a normal `/usr` and `/etc`, and
writable `/var`. The initramfs mounts tmpfs `/run` and carries the required
firmware into it. No fixed UUID, rootfs size, filesystem-resize tool or private
ADB payload is required by the handoff.

Install the normal distro packages for systemd, udev, D-Bus, networking and a
login account. Configure NetworkManager and Wi-Fi credentials before boot if
SSH is your primary access method. Install/configure OpenSSH separately; do
not embed personal SSH keys in an image or this repository. A USB ADB gadget
is optional rootfs configuration, not a dependency of this boot image.

For a desktop, install a Wayland compositor/session, greeter, libdrm and Mesa
with Adreno 830 Turnip/Zink support. Mesa 26.2.1 has been used successfully.
Speaker playback uses ALSA UCM, PipeWire and WirePlumber. The kernel's tested
device drivers are built in; missing unrelated kernel modules are not a reason
to copy a private module directory.

## Build the patched userspace

The following are **native AArch64 build commands**, run inside the target
distro or an AArch64 build environment. They are not host-x86 binaries to copy
onto the tablet. Fetch the source trees using the umbrella's source script
before running them. Use distro packages for these build dependencies:

| Component | Build/runtime development dependencies |
| --- | --- |
| All | C/C++ compiler, Meson >= 1.4, Ninja, pkg-config, Python 3 |
| hexagonrpc | libc and Linux headers |
| libssc | GLib/GIO, libqmi (qmi-glib >= 1.33.4), protobuf-c, `protoc`, `protoc-gen-c`, GObject introspection, Vala |
| iio-sensor-proxy | GLib/GIO >= 2.76, libgudev >= 237, polkit, udev/systemd, libssc, gettext |
| libcamera/qcam | libyaml, libudev, OpenSSL or GnuTLS, libevent, Qt6 Core/Gui/Widgets/OpenGL, Python Jinja2/PLY/PyYAML, OpenSSL command-line tools |

Build and install in dependency order. These installation commands modify the
target userspace under `/usr`, so run them in the intended rootfs/build system:

```sh
meson setup build/hexagonrpc sources/hexagonrpc --prefix=/usr --libdir=lib
meson compile -C build/hexagonrpc
sudo meson install -C build/hexagonrpc

meson setup build/libssc sources/libssc --prefix=/usr --libdir=lib
meson compile -C build/libssc
sudo meson install -C build/libssc

meson setup build/iio-sensor-proxy sources/iio-sensor-proxy \
    --prefix=/usr --libdir=lib --libexecdir=libexec -Dssc-support=enabled
meson compile -C build/iio-sensor-proxy
sudo meson install -C build/iio-sensor-proxy

meson setup build/libcamera sources/libcamera --prefix=/usr --libdir=lib \
    -Dpipelines=simple -Dipas=softisp -Dqcam=enabled -Dcam=enabled \
    -Ddocumentation=disabled -Dgstreamer=disabled -Dpycamera=disabled \
    -Dlc-compliance=disabled -Dv4l2=disabled -Dsoftisp-gpu=disabled \
    -Dapps-output-dng=disabled -Dtest=false
meson compile -C build/libcamera
sudo meson install -C build/libcamera
sudo ldconfig
```

Meson installs the library, IPA, worker and default configuration together;
keep them from the same build. The included patches require no uncommitted
files or prebuilt private payload. Do not copy a historical camera bundle or
per-unit lens calibration into a generic rootfs. Generic manual capture works
without claiming calibrated autofocus on every module.

## Sensors: data and services

The ADSP filesystem needs data copied **read-only from your own Android system**:

| Linux path | Source |
| --- | --- |
| `/var/lib/hexagonrpc/acdb` | `/vendor/etc/acdbdata` |
| `/var/lib/hexagonrpc/dsp` | `/vendor/dsp` |
| `/var/lib/hexagonrpc/sensors/config` | `/vendor/etc/sensors/config` |
| `/var/lib/hexagonrpc/sensors/state` | `/mnt/vendor/persist/sensors/registry` contents, including its `registry/` child, `sns_reg_version` and companion state files |
| `/var/lib/hexagonrpc/sensors/sns_reg.conf` | `/vendor/etc/sensors/sns_reg_config` |
| `/var/lib/hexagonrpc/socinfo` | Symlink to the running Linux `/sys/devices/soc0` |

Keep this directory private to root. Only `sensors/state` is writable through
HexagonFS; configuration and DSP libraries stay read-only. Preserve existing
Linux sensor state on upgrades. Never write Android persist. A kernel driver
alone cannot replace this device-specific calibration/registry input.

### Back up and import the running tablet's data

`scripts/device-data.py` copies `/var/lib/hexagonrpc` over SSH using passwordless
sudo. It compares complete source inventories before and after copying and
then verifies the extracted archive's SHA256s, owners, modes and timestamps.
The output must be a new directory. Use a private, ignored directory:

```sh
sudo scripts/device-data.py backup --host USER@TABLET_IP \
    --output inputs/device-data/y700-gen4-YYYYMMDD
sudo scripts/device-data.py verify inputs/device-data/y700-gen4-YYYYMMDD
sudo scripts/device-data.py restore inputs/device-data/y700-gen4-YYYYMMDD \
    --root /mnt/installed-root
```

Import can be done into the offline rootfs before making the local image, or
with `--root /` on a fresh installation on **the same physical tablet**. It
accepts empty service scaffolding but refuses to replace existing device data,
especially a live sensor registry. It does not start services or write Android
persist. Do not distribute an image containing this per-device backup.

The 2026-10-31 verified backup contains 962 regular files (283,920,195 bytes):

| Directory | Files | Purpose |
| --- | ---: | --- |
| `acdb/` | 85 | Vendor DSP/audio databases and models, about 228 MiB; not all are per-device calibration |
| `dsp/` | 99 | 77 ADSP and 22 CDSP libraries, about 42 MiB; CDSP files are retained even though Linux currently disables CDSP |
| `sensors/config/` | 139 | Sensor/platform JSON definitions and `json.lst` |
| `sensors/sns_reg.conf` | 1 | Registry input/output configuration |
| `sensors/state/` | 638 | 634 registry files plus sensor lists, parsed-file list, camera-registry dump and `odp` state |

The state includes accelerometer/gyro bias and correction matrices, gyro
temperature compensation, magnetometer bias, ambient-light/proximity calibration,
and Hall/orientation/gesture configuration. Vendor files also include alternate
sensor models; their presence does not mean every listed sensor exists on the
tablet. The HexagonFS mapping exposes local `sensors/state/` as Android's
`/mnt/vendor/persist/sensors/registry/`, so `sns_reg.conf`'s Android output path
ending in `registry/registry` resolves to local `sensors/state/registry/`.
The current Linux tree also contains a deeper `registry/registry/` copy whose
contents differ. This backup preserves both without deciding that either can
be deleted. Preserve `sns_reg_version`'s symlink and recreate
`socinfo -> /sys/devices/soc0`. Older versions of this page named the Android
source one level too high; the table above follows the actual HexagonFS mapping.

Cross-check against Freedom `main` at
[`9788014a0293dc26745b000d02854ad88ef73e88`](https://github.com/mydanyi/armadaos-freedom/tree/9788014a0293dc26745b000d02854ad88ef73e88):

* Its Gen4 integration does not add a separate private SSC data import. The
  [ALS bridge](https://github.com/mydanyi/armadaos-freedom/blob/9788014a0293dc26745b000d02854ad88ef73e88/packages/kernel/out-of-tree/als-bridge/README.md)
  consumes SensorProxy readings and has no calibration file of its own.
* `/etc/armada/input-calibration.json` applies to the `rsinput`, `retroid` and
  `mangmi` built-in-controller backends, not the G9. It is absent on this tablet.
* The `aw_cali.bin` mentioned in Freedom's out-of-tree AW882xx documentation is
  for the Gen5 amplifier driver, which does not use that file on Linux either.
  Gen4's AW88461 driver uses the already pinned speaker firmware and does not
  import an Android persist calibration file.
* The running tablet has no separate `/etc/libcamera` calibration; its SoftISP
  uses `uncalibrated.yaml`. This backup does not claim to contain camera OTP/EEPROM
  calibration or an image of the entire Android persist partition.
* Sensor mount matrices, udev rules and service configuration are software
  integration maintained in `rootfs/sensors/` and `packages/tb322fc-sensors/`.
  Kernel/ADSP/GPU/Wi-Fi/Bluetooth firmware is separate: the existing 83-file
  `firmware.json` and seven-file Freedom Wi-Fi manifest were also hash-verified.

No additional private data required by the current working Linux sensor stack
was found outside the backed-up tree. The private `manifest.json` contains the
complete per-file inventory and device identity; it must stay out of Git/OBS.

After the binaries and data are installed:

```sh
sudo install -Dm644 rootfs/sensors/hexagonrpcd-sensors.service \
    /etc/systemd/system/hexagonrpcd-sensors.service
sudo install -Dm644 rootfs/sensors/iio-sensor-proxy.conf \
    /etc/systemd/system/iio-sensor-proxy.service.d/ssc.conf
sudo systemctl daemon-reload
sudo udevadm control --reload
sudo systemctl enable hexagonrpcd-sensors.service
```

The openSUSE iio-sensor-proxy package must enable `ssc-support` and build against
libssc: the official recipe disables this backend. The physical light sensor
is accessed through SSC; `als-bridge` only mirrors its readings for Steam.
The accelerometer is read from the gyro bridge's input device rather than
opening a second SSC accelerometer client. Restart the sensor services on the
target after installation. iio-sensor-proxy does not provide a generic desktop
gyro stream.

## Speakers and cameras

Install the files under `rootfs/audio/ucm2/` into `/usr/share/alsa/ucm2/`, retaining
the hierarchy. The matching amplifier profiles and generated topology are
already carried by the boot image. Back up existing UCM files before replacing
them. The supplied UCM exposes the HiFi/Speaker route only.

For cameras, install `rootfs/camera/70-libcamera-dma-heap.rules` into
`/etc/udev/rules.d/` and the desktop file into `/usr/share/applications/`.
The desktop launcher runs the native `qcam` installed above. Active local users
need the normal video/media-node permissions and DMA-heap access. Use the
libcamera default tuning until the individual sensor/lens module is calibrated.
