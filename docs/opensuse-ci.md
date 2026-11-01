# openSUSE images

The [Build openSUSE images workflow](../.github/workflows/build-opensuse.yml)
assembles the current OBS packages into a Tumbleweed AArch64 rootfs and builds
a matching kShim `boot.img`. It is manually dispatched from the `opensuse`
branch. The artifact contains a rootfs tarball, boot image, package versions,
checksums and build manifests. No partition is written by CI.

## Builder and inputs

GitHub offers free ARM64 runners backed by Cobalt 100, but the tested VM did
not expose RNDR. The workflow therefore uses a free x86_64 `ubuntu-24.04` runner
with `qemu-aarch64-static` and `QEMU_CPU=max`. This is the same isolated chroot
path used by local x86_64 assembly; it leaves the `oryon-1+rng+fp16` RPM target
unchanged. It installs prebuilt RPMs and runs the boot packer, rather than
recompiling the kernel under emulation.
[GitHub runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
list both free architectures. A compressed rootfs archive also avoids keeping
a second full filesystem image alongside the staging tree.

OBS also supports [KIWI image builds](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-package-formats).
This project uses OBS for RPMs and GitHub for image assembly, keeping the model
firmware input separate from OBS source packages and avoiding two image recipes.

Inputs are pinned in `configs/opensuse/{rootfs,boot}.json`, `firmware.json` and
`configs/freedom-wifi-firmware.json`. `FIRMWARE_URL` and `FIRMWARE_SHA256` are the
existing repository secret/variable; workflow inputs can override them. The
bundle reader rejects every file outside the model firmware manifest. Freedom's
Wi-Fi payloads are taken from its fixed source commit, and the audio topology
is rebuilt from tracked source.

The stock Android boot is a verified TB322FC model image. Signing uses the
**AOSP AVB RSA4096 test key accepted by this device**, downloaded from a fixed
AOSP commit and checked against its SHA256. It is intentionally a public test
key, not a newly generated key or a personal secret. The key is kept outside
the rootfs, temporarily mounted only while signing, and omitted from artifacts.
The signer preserves stock AVB properties and verifies the finished image.

## Public image boundary

CI always starts with a fresh staging tree. It never restores a tablet backup
or copies the builder's home, SSH configuration, network profiles or calibration.
The export check rejects provisioned state rather than silently removing it.
Only explicit output paths are uploaded after the full build succeeds.

The generic boot selects **GPT partition label `rootfs`**, not an individual
PARTUUID. It uses exactly the kernel, DTB and early firmware installed into the
rootfs. A differently named existing Linux partition needs its own locally built
boot; this workflow does not rename or repartition anything. The Android menu
entry retains the pinned stock kernel. The image still requires the device's
existing compatible Android vendor/init_boot and bootloader setup.

## Local build

Use AArch64 Linux compatible with the package profile, or x86_64 Linux with
`qemu-aarch64-static` and binfmt_misc. Required host tools are Python 3.11+,
curl, GnuPG, tar, xz, zstd, util-linux, git and alsa-utils.
For an F2FS image also install f2fs-tools and use a kernel with
`CONFIG_F2FS_FS_SECURITY=y`. The pinned bootstrap is verified by signature and
hash; custom RPMs are checked against current OBS results and signed repository
metadata. No OBS credentials are needed.

```sh
# Set FIRMWARE_URL and FIRMWARE_SHA256 as documented above.
bash scripts/ci/prepare-inputs.sh
bash scripts/build-topology.sh
python3 scripts/fetch-sources.py freedom
sudo python3 scripts/opensuse/build-rootfs.py prepare --work build/opensuse-public-root
sudo python3 scripts/opensuse/build-rootfs.py assemble --work build/opensuse-public-root
sudo python3 scripts/opensuse/stage-firmware.py build/opensuse-public-root/rootfs
sudo python3 scripts/opensuse/export-rootfs.py build/opensuse-public-root/rootfs \
    artifacts/tb322fc-tumbleweed.tar.zst
```

Download/decompress the model stock boot and decode the base64 AOSP test key
from the URLs in `configs/opensuse/boot.json`. Verify both SHA256 values in that
file and restrict the key file to mode 0600. The workflow contains the same
fetch commands. Build the matching boot:

```sh
sudo python3 scripts/opensuse/make-boot.py build/opensuse-public-root/rootfs \
    artifacts/opensuse-boot --stock-boot build/stock-boot.img --key build/avb-test-key.pem
```

To convert the generic staging tree to F2FS locally:

```sh
sudo python3 scripts/opensuse/make-image.py build/opensuse-public-root/rootfs \
    artifacts/tb322fc-tumbleweed.f2fs.img --size-gib 24 --compress
```

The writer uses the [TWRP-derived F2FS profile](rootfs.md#f2fs-settings), preserves
ACLs, file capabilities and hardlinks, and writes the filesystem UUID into
`fstab`. It accepts only a new regular output file. Its final filesystem check
must succeed before treating the image as complete.

An artifact tarball can instead be extracted into a newly formatted, mounted
F2FS filesystem with `tar --numeric-owner --xattrs --xattrs-include='*' --acls
--zstd -xpf ROOTFS.tar.zst -C MOUNTPOINT`. Set that filesystem's UUID and the
profile's mount options in its `etc/fstab` before boot. Import only the target
tablet's own sensor data into the installed root, following
[the device-data instructions](rootfs.md#back-up-and-import-the-running-tablets-data).
Account creation and SSH authorization happen locally after installation.
CI validation does not replace testing a new boot/rootfs pair on hardware.
