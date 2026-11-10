# System and kernel change inventory — 2026-11-10

This inventory reconciles the earlier Codex patching conversations with `master`
at `5e7bc50`. It distinguishes source already shipped by this branch from changes
installed on the tablet and experimental kernels. The initial inventory commit added documentation only. The recovered source is
now available under [optional local fixes](../rootfs/local-fixes/README.md);
these helpers and experimental patches are not enabled by package recipes.

## Kernel and boot changes already on master

The packaged Freedom kernel is **7.2.6-21-freedom**, based on Freedom revision
`9788014a0293dc26745b000d02854ad88ef73e88`. The tablet inspected for this inventory
runs the separate **7.2.8-y700-r2-androidcrypt1** kernel. Results from either build
must not be treated as regression results for the other.

| Addition | Source and purpose |
| --- | --- |
| Native Arch kernel, headers, ALS DKMS and kShim packages | [Update contract](ci.md); coordinated v2 updates, exact source pins and matching boot/module inputs |
| Elden configuration | [Compatibility patches](../patches/freedom/README.md); F2FS and userspace compatibility, including Landlock |
| USB resume | Elden host-power-loss propagation to xHCI, suspend ordering and eUSB2 compatibility |
| Display resume | Atomic display state, refresh handling, live DSI link preservation, bonded-slave restoration and slave-first shutdown |
| Storage recovery | Elden UFS MCQ, ESI restoration, internal-command recovery and clock-scaling lock/queue ordering |
| Wi-Fi | Elden range scans now supplied by the pinned upstream patch chain; local cancelled-scan cleanup prevents continuation of a cancelled range batch |
| Bluetooth / PCIe | Configured Bluetooth address support and Elden fixed PCIe slot handling |
| Remote processor | Upstream Q6V5 one-shot handover fix plus attach compatibility |
| DPU rotation | Opt-in Gen4 scanout, candidate atomic bandwidth and rotated-plane performance calculations; hardware limits retained |
| kShim | SM8750 reboot compatibility, Android base replacement and exclusion of retained rollback kernels from automatic deployment |

The [kernel recipe](../packages/linux-freedom/PKGBUILD) is authoritative for the
active patch list. Historical patch files can remain after their implementation
moves upstream. See the [Freedom sync and DPU validation record](freedom-sync-20261029.md)
for authorship, rejected display changes and the actual device checks.

## System integration already on master

- Patched sensor services and calibration handling, desktop/session integration,
  audio routing and an ALS bridge that avoids the controller IMU and invalid lux.
- Armada power policy and device configuration using the distribution thermald
  package; charging estimates in the Steam session.
- Steam power-key handling and input-listener reconstruction after real suspend.
  The current gaming short-press action toggles the screen while games/audio
  continue; long press opens the Steam power menu.
- On-demand MTP and bounded diagnostics, plus opt-in per-game scaling and frame
  generation tools.
- G9 controller hotplug, DS controls, HID rumble and device-scoped hide rules.
  See [G9 resume validation](g9-resume-20261031.md).
- Gamescope restores plane colour state when reactivating pipelines, addressing
  night-mode state lost across suspend. See [night-mode validation](night-mode-20261030.md).

## Additional changes installed locally

These are recorded in the October 15–November 10 conversations and their saved
verification records. Their installation on one tablet does not mean the branch
packages include them. Names below identify the deployed helpers for inspection;
the source directory documents manual integration prerequisites.

| Area | Installed behavior | Verification and remaining limits |
| --- | --- | --- |
| Bluetooth startup | `tb322fc-bluetooth-identity` performs bounded initialization retries and resets the dedicated UART after firmware-upload failure. BlueZ applies privacy settings before powering on. A recovery timer retries failed startup without disturbing healthy or deliberately powered-off adapters. | Fourteen failure-path tests and live UART recovery passed; keyboard and mouse reconnected and mouse movement was confirmed. Cold-boot recovery remains unverified. Pairing keys and the existing address were preserved. |
| USB ADB | Root supervisor owns gadget setup; the child `adbd` runs as the login user. A resume hook restarts the bridge. UDC device-mode events start the service and removal stops it; boot startup is disabled. | Resume-hook invocation restored a configured connection with an unprivileged daemon. Unit/rule checks passed. Actual sleep/wake and physical plug/unplug behavior were not verified by those checks. |
| Sleep preparation | `tb322fc-sleep-power` saves radio state, stops/masks active motion/light sensor services, and restores prior states after wake or aborted preparation. Recovery state survives errors. Restoration timing and locking were corrected. | A short suspend completed and radios returned. Fifteen later helper/diagnostic tests passed. This establishes neither sustained standby nor a measured battery saving. |
| Wake diagnostics | Capture wake-source counters and interrupt activity before slower Bluetooth restoration, including `last-wake.json` and `last-wake-trace.json`. | Diagnostic support for investigating early wake; successful suspend counters alone do not prove the intended duration. |
| Sleep policy | Restored s2idle after a later configuration had overridden it with deep. Hibernation, hybrid sleep and suspend-then-hibernate were disabled after hangs/timeouts. | On November 10, `/sys/power/mem_sleep` reports `[s2idle] deep`. Earlier hibernation swap/resume setup was superseded by the disabled policy; hibernation is not a supported result. |
| Shutdown / charging mode | Local kernel preserves bootloader charging-mode metadata. Userspace preserves slot selection and enters a charging-only target on firmware charging boot. The percentage display blanks after 20 seconds; short Power shows it, a two-second hold starts KDE, and unplug requests power-off after debounce. | User confirmed unplugged shutdown stayed off for one minute. Framebuffer and injected key paths were checked. Charging boot is distinct from normal desktop boot. |
| Recovery selection | A recovery helper selects stock Android slot A before requesting recovery because the recovery ramdisk relies on the selected slot's kernel. | Dry-run/failure-path checks; no successful recovery boot established by the conversation. Slot layout is device-specific. |
| Battery profiles | Native KDE profiles select balanced/165 Hz on AC, balanced/90 Hz on battery and power-saver/60 Hz below 20%. A profile-load hook changes the enabled internal panel only. | Modes, existing CPU caps and AC hook were checked. Physical unplug/replug and low-battery crossing were not observed. No battery-life gain measured. |
| Desktop tap-to-wake | `y700-screen-blank.service` blanks only the internal backlight while touch/panel stay powered; short Power and idle scripts use it. The waking touch is consumed through release; brightness restores on wake/error/session exit. | Eight checks plus live zero-brightness, input-grab and injected-touch checks passed. Physical finger tap and Power-button confirmation remain pending. This consumes more power than panel-off and does not wake system suspend. |

The local Android-crypto kernel and modules were also developed separately from
the Freedom package. Enabling wrapped-key support does not establish that Android
userdata can be decrypted: key provisioning and access must be verified separately.
Do not distribute device keys, calibration, firmware blobs, signed boot images or
personal configuration with this inventory.

## Deep-sleep investigation and rejected candidates

The November 5 investigation found two distinct wake sources. Active sensor
streams produced immediate IPCRTR interrupts; stopping those streams addressed
that case. Later battery-status notification `0x80` arrived via shared PMIC GLINK
IRQ 239 and still woke deep sleep.

An initial notification-disable candidate received firmware acknowledgement and
held one 120.349-second interval, but a repeat woke at 215.449 seconds. It was
rejected and the stable local kernel restored. Ignoring the battery callback
cannot undo the interrupt that already woke the processor. No reliable deep-sleep
fix or standby-power measurement is claimed.

The November 6 replacement candidate uses display blank/unblank notification
control through DRM panel callbacks, with suspend preparation as fallback. It
tracks acknowledgements, invalidates state on remote-service restart, prevents
workers re-enabling notifications during preparation, matches reply opcodes, and
restores state on resume or abort. The policy is limited to SM8750 with an explicit
panel reference; the shared GLINK interrupt remains enabled.

That candidate passed a full kernel build, signature checks and 21 host checks.
It was **not installed or booted**. Firmware cooperation and repeated deep sleeps
beyond the previous failure point remain unverified. It must not be described as
an accepted fix or folded into the stable source pin on this evidence.

## Evidence scope

Sources for the local entries are the saved Codex discussions covering host sleep
(October 15 onward), Android partition/crypto work (October 22), ADB resume
(October 26), battery QoS (October 23 onward), Bluetooth startup (November 4 onward)
and USB-connect ADB (November 4), together with the November 5 investigation
checkpoint and November 6/10 helper validation records. Private transcript text,
network names, peer identifiers and workspace paths are intentionally omitted.

This inventory was checked against the branch files and the tablet's running
kernel and sleep selection. Source collection and offline checks do not establish new hardware results;
no suspend, reboot, shutdown, flash or physical interaction test was performed
while collecting these files.
