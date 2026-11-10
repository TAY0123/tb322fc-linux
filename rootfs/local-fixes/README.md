# Optional local system fixes

Source recovered from the October–November 2026 tablet work. These files are
reviewable inputs, separate from the active Freedom package recipes. They do not
install themselves or alter the running tablet. The historical local kernel is
7.2.8-y700-r2-androidcrypt1; Freedom uses a different baseline. Do not apply the
legacy kernel patches to the Freedom package without a separate port and test.

## Contents and installation layout

| Directory | Source | Destination / prerequisites |
| --- | --- | --- |
| `bluetooth` | Identity module, initialization/recovery helper, units and offline tests | Helper in `/usr/local/sbin`; module built against matching kernel headers; unit files in `/etc/systemd/system`; numbered `.conf` files are service drop-ins as described below |
| `adb` | FunctionFS supervisor, USB rule and resume hook | Supervisor in `/usr/local/libexec`; service in `/etc/systemd/system`; rule in `/etc/udev/rules.d`; `resume-hook` installed as `/usr/lib/systemd/system-sleep/tb322fc-adbd` |
| `sleep` | Radio/sensor state handling, wake diagnostics and s2idle policy | `sleep_power.py` installed as `/usr/local/libexec/tb322fc-sleep-power`; `wake_diagnostics.py` as `/usr/local/libexec/tb322fc-wake-diagnostics`; units in `/etc/systemd/system`; diagnostic hook in `/usr/lib/systemd/system-sleep`; sleep policy in `/etc/systemd/sleep.conf.d` |
| `display` | Backlight tap-to-wake and profile-based refresh | `y700_screen_blank.py` installed as `/usr/local/libexec/y700-screen-blank`; command wrappers and refresh hook in the user's executable path; service under the user's systemd configuration; desktop entry in the user's applications directory; rule in `/etc/udev/rules.d` |
| `boot` | Slot validation, boot attestation, recovery request, charging UI and generator | `tb322fc-*` helpers in `/usr/local/libexec`, except the boot-control UI in `/usr/local/bin` and `reboot_recovery.py` installed as `/usr/local/sbin/tb322fc-reboot-recovery`; charger generator in `/etc/systemd/system-generators`; units and corresponding drop-in directories in `/etc/systemd/system` |
| `kernel` | Legacy CDSP baseline, crypto config delta, charging metadata repair and experimental notification control | Apply only to the baseline and in the order below; no images, modules, signing material or firmware included |

Install executable helpers as root-owned mode 0755 and system units/rules as
root-owned mode 0644. User units and launchers belong to the chosen desktop user.
Reload systemd and udev after installing configuration. Installation/enabling is
manual because the services depend on the boot layout and optional device setup.
These sources were collected without changing any installed services.

## Bluetooth configuration

The public helper contains **no device address**. Create a root-owned mode 0600
`/etc/tb322fc/bluetooth-identity.conf` locally with
`TB322FC_BLUETOOTH_ADDRESS=<your existing public Bluetooth address>`.
Do not commit that file or pairing keys. Missing/invalid configuration fails
before invoking controller commands; test fixtures use a synthetic address.

Build the module with `make -C /usr/lib/modules/<matching-release>/build M="$PWD" modules`
inside `bluetooth`, install it for that kernel and run depmod. The supplied base
unit deliberately retains the exact historical kernel/module conditions.
`60-startup-recovery.conf` belongs under
`tb322fc-bluetooth-identity.service.d`; `20-android-identity.conf` and
`30-restart.conf` belong under `bluetooth.service.d`. Enable the recovery timer
only after verifying the identity service on the matching hardware. The timer's
historical `nohibernate` condition is retained. Bluetooth dependencies must be
installed together; installing only the BlueZ dependency drop-in can prevent
Bluetooth startup. Cold-boot recovery remains unverified.

## ADB configuration

Create root-owned mode 0600 `/etc/tb322fc/adbd.conf` locally containing
`ADBD_USER=<existing unprivileged login account>`. No account name is embedded in
the public files. The supervisor rejects root as its daemon account. It expects
an existing `tb322fc` ACM/NCM configfs gadget and a compatible USB FunctionFS
`/usr/local/bin/adbd`; the daemon binary and its authentication state are not
included. ADB authentication policy depends on that daemon build and must be
configured separately. The service remains disabled at boot for event-based
startup. The rule starts it on the expected UDC's add/change events; the
supervisor stops its child daemon on disconnect and waits for a returning host.
Physical cable and actual resume verification remain pending.

## Sleep and display configuration

Sleep helpers require rfkill, BlueZ management tools, NetworkManager and the
existing SSC sensor units. Enable `tb322fc-sleep-power.service` under
`sleep.target` and the recovery unit under `multi-user.target`. Preserve existing
configuration overrides; the effective policy must be s2idle. Bluetooth and Wi-Fi
are unavailable as wake sources while powered down. Wake diagnostics write
root-private runtime evidence; no captured evidence is included here.

Display helpers require Python GI/Gio, evdev access and KDE/Wayland; profile
refresh also requires KScreen. The backlight rule grants the existing video group
access only to the internal brightness attribute. Use the user service under
`plasma-workspace.target`. Configure PowerDevil manually: short Power action 0,
idle script `y700-screen-off` instead of native dimming/DPMS; retain long-press
PowerDown and real suspend policy. Historical idle timeouts were AC 600 seconds,
battery 300 seconds and low battery 120 seconds. For profile-load hooks invoke
`y700-panel-refresh`, with balanced AC/battery and power-saver below 20%.
No user's PowerDevil configuration is supplied. Screen blanking keeps the panel
and touch powered and consumes more power than full panel-off.

## Legacy boot prerequisites

The boot helpers assume Linux on slot B and stock Android/recovery on A. They
validate layout and image attestation before metadata operations, preserve
unrelated bootloader-message fields, and restore disk write protection. They
are unsuitable for a Freedom installation that uses a different slot/layout.
They require a separately installed qbootctl at commit
`39a6e6daaf029fb0a083777679a15ea2c18f72de`, and a locally generated,
root-owned `/etc/tb322fc/boot-success.json` for the verified installed image.
The boot-success helper's `--attest-image` option emits the image identity;
review and install it locally. No attestation or partition snapshot is shipped.
The UI requires kdialog and separately configured sudo/polkit authorization.
The reboot/poweroff drop-ins activate the preparation unit; no new sudoers or
polkit policy is supplied. The charger generator requires the metadata patch
and framebuffer/input/backlight drivers. It activates only for charger boot.

## Kernel provenance and patch order

Legacy source: https://github.com/h0cheung/tb322fc-linux-kernel at
`87834e9d970dff2cd6329f585ee68eb17b182e4e`.

1. `legacy-cdsp-baseline.patch` preserves the pre-existing CDSP devicetree delta
   used by the local kernel; it does not claim new DSP application validation.
2. Merge `android-crypto.config` with the appropriate legacy configuration.
   The dm-default-key implementation is already in that pinned kernel tree.
   This delta contains no encryption keys and does not establish decryption.
3. `boot-metadata.patch` preserves checked boot mode/reason from the bootloader
   while retaining the built-in hardware tree and embedded Linux initramfs.
4. Optionally, the four numbered patches in `experimental-battmgr` apply the
   November 6 display-based notification policy on top of the stable baseline.
   This candidate is **not boot-tested and not an accepted deep-sleep fix**.

The experimental policy follows the display-blank behavior of the Qualcomm
vendor charger driver in LineageOS/android_kernel_qcom_sm8550 at
`2aba31013945217584433b1695a97dbafd897288`. Its shared GLINK IRQ stays enabled.
The earlier suspend-only candidate failed a repeated long interval and is omitted.

## Offline verification

Run these commands from the repository root. They do not suspend, reboot or
write device partitions:

```sh
python3 -m unittest discover -s rootfs/local-fixes/bluetooth -p 'test_*.py'
python3 -m unittest discover -s rootfs/local-fixes/adb -p 'test_*.py'
python3 -m unittest discover -s rootfs/local-fixes/sleep -p 'test_*.py'
python3 -m unittest discover -s rootfs/local-fixes/display -p 'test_*.py'
python3 -m unittest discover -s rootfs/local-fixes/boot -p 'test_*.py'
```

The experimental C harness requires a source tree with the four patches applied:
run its `test_notification_control.py` with that tree's
`drivers/power/supply/qcom_battmgr.c` path as its argument. It compiles extracted
production functions with ASan/UBSan and runs 21 lifecycle/ACK checks. Those host
checks cannot establish firmware cooperation or sustained deep sleep.

See the [change inventory](../../docs/system-kernel-changes-20261110.md) for
historical hardware verification and remaining limitations.
