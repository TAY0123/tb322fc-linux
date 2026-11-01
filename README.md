# Lenovo Y700 Gen4 Linux

Mainline Linux for the Lenovo Legion Tab Y700 Gen4, based on Qualcomm SM8750
(Snapdragon 8 Elite), device codename **elden**.

The default `opensuse` branch integrates Tumbleweed AArch64 with the
[`home:h-cheung:tb322fc` OBS project](https://build.opensuse.org/project/show/home:h-cheung:tb322fc).
It includes Plasma Desktop, Plasma Mobile and a Steam session. Device packages
use the Snapdragon 8 Elite CPU profile; the kernel and ALS module retain
openSUSE's kernel/KMP package layout.

Start with the [openSUSE build and installation notes](docs/opensuse-ci.md).
The image workflow builds a matching rootfs and boot image. Public artifacts
contain hash-pinned model firmware, never personal sensor calibration, login
credentials or trusted SSH keys. First boot creates your own account through
Plasma Setup. The earlier Arch packaging remains available on `master`.

See the [2026-10-29 Freedom sync and Gen4 DPU rotation notes](docs/freedom-sync-20261029.md)
for the imported changes, candidate switch and validation status.

The device runs Plasma Mobile through SDDM, with ordinary Plasma and Steam
sessions available. F2FS is supported by the packaged kernel. Historical direct
kernel development remains in [tb322fc-linux-kernel](https://github.com/h0cheung/tb322fc-linux-kernel).

## Hardware support

The table combines the current Freedom baseline with earlier device tests.
Bluetooth, suspend (s2idle) and the microphone worked on the earlier kernel;
these are not a complete regression pass of the current package release.

| Component | Status | Notes |
| --- | --- | --- |
| Kernel / UFS | Working | Linux 7.2.6; F2FS rootfs |
| Display | Working | 24/40/60/90/120/144/165 Hz modes |
| Touch | Working | Novatek NT36536 |
| GPU | Working | Adreno 830 with Mesa Turnip and Zink |
| Wi-Fi | Working | Freedom ath12k; range scanning |
| Bluetooth | Working | QCA UART firmware load, discovery and pairing |
| Speakers | Working | AW88461; supplied AudioReach topology and UCM |
| Microphone | Working | Built-in analog capture (AMIC1/AMIC4 via the WCD9395) |
| Haptics | Working | Two AW86927-family devices; force-feedback replay |
| Accelerometer / gyro / light | Working | ADSP/SSC; patched sensor services required |
| Cameras | Unavailable on current Freedom kernel | SM8750 CAMSS and board sensor bindings are missing; front/rear capture worked on the previous kernel |
| Suspend | Working | s2idle on USB-attached sleep; hibernate-to-disk untested |
| Battery / charging | Partial | Charger wake and power/reporting issues remain |

See the [support matrix](docs/hardware.md) for test scope and unverified features.

## Build and use

### Native Arch packages and coordinated updates

The **Build Freedom Arch packages** workflow builds on ARM64 inside an authenticated
Arch AArch64 bootstrap, without a Linux cross compiler. Releases use the v2
manifest plus kernel, headers, DKMS and kShim packages. The old boot/module asset
names and legacy rolling repository are kept outside the new update path.

See the [native CI and update contract](docs/ci.md). These are package updates for
an initialized Freedom boot setup; fresh-install flashing and automatic migration
from legacy direct-boot systems are not offered by v2 releases. The internal CI
rootfs is not published as a standalone installation image.

### Historical direct boot image builder

1. [Install the build dependencies](docs/build.md#host-dependencies).
2. Fetch the pinned source trees with `python3 scripts/fetch-sources.py`.
3. [Extract and import matching firmware](docs/firmware.md).
4. Build with `bash scripts/build-boot.sh`.
5. Prepare the [rootfs and device services](docs/rootfs.md).
6. Test with `fastboot boot artifacts/boot.img`.

The build produces `boot.img`, `Image`, `sm8750-lenovo-elden.dtb`,
`kernel.config` and `SHA256SUMS` under `artifacts/`. Images and firmware binaries
are not stored in Git. The firmware comes from your own matching stock system;
sensor calibration stays with your device. Rootfs artifacts can be built through
the workflow; no prebuilt tested rootfs release is supplied.

## Project files

| Path | Purpose |
| --- | --- |
| [`sources.json`](sources.json) | Public source URLs, exact commits and expected trees |
| [`patches/`](patches) | Libcamera, hexagonrpc and iio-sensor-proxy changes |
| [`configs/`](configs) | Kernel, BusyBox, command line and initramfs layout |
| [`initramfs/`](initramfs) | Rootfs selection and handoff |
| [`rootfs/`](rootfs) | Audio, sensor and camera integration files |
| [`firmware.json`](firmware.json) | Required firmware paths, sizes and SHA256 hashes |

## Development

- Keep changes scoped to this device and demonstrated dependencies.
- Use devicetree for hardware distinctions; avoid board-specific kernel switches.
- Build verified drivers and their dependencies into the kernel.
- Test with `fastboot boot`; do not flash partitions.
- Preserve a working boot image and device calibration before testing changes.
- Keep generated images, personal logs and device state out of Git.

See [contributing](CONTRIBUTING.md), [boot design](docs/boot.md) and
[validation](docs/validation.md). The repository structure follows the compact
umbrella approach used by [tb321fu-linux](https://github.com/GUF296/tb321fu-linux);
its hardware-specific configurations do not apply to this tablet.
