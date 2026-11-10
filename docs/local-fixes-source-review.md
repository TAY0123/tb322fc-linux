# Local fixes source review — 2026-11-10

The [optional local fixes](../rootfs/local-fixes/README.md) contain explicitly
selected text source, tests, units, rules, a crypto config fragment and kernel
deltas from the earlier work. No directory-wide export of a home, build,
configuration, backup or transcript directory was used.

## Privacy review

- The installed Bluetooth helper contained a per-device address. That value is
  absent from this source set. The public helper requires private environment
  configuration; tests use synthetic `02:00:00:00:00:01` and the invalid all-zero
  address. Existing runtime pairing keys were not copied.
- The ADB login account is supplied through a private environment file. The
  public supervisor requires an explicit unprivileged account.
- The staged files were scanned for private workspace paths/accounts, IPv4
  addresses, Bluetooth addresses, device UUIDs, private-key headers, common API
  credential formats and embedded credential/network assignments. No sensitive
  values were detected; address fixtures were reviewed separately.
- Firmware, kernel/module binaries, boot images, signing material, encryption
  keys, authentication state, partition dumps, attestation files, sensor
  calibration, personal desktop configuration, raw transcripts and runtime logs
  are excluded. The existing public source commits and hardware register/device
  paths are retained for reproducibility.

This review covers the newly collected files and documentation. It is not a
security audit of the repository's pre-existing history or the running system.
The recovery and diagnostic programs can create local state when deployed;
those generated files are not part of this source collection.

## Validation

| Check | Result |
| --- | --- |
| Bluetooth recovery failure paths | 14 tests passed |
| ADB explicit account selection and root rejection | 3 tests passed |
| Sleep restoration and wake diagnostics | 15 tests passed |
| Screen blanking and waking-touch consumption | 8 tests passed |
| Recovery-message preservation and rollback | 6 tests passed |
| Experimental battery notification C harness | 21 checks passed with ASan/UBSan |
| Kernel delta application | Legacy CDSP and boot-metadata patches apply to pinned source; all four experimental patches apply to saved stable baseline |
| Syntax and repository validation | Python parsing, shell syntax, repository checks and staged whitespace checks passed |

Total: 67 offline tests/checks. No hardware state transition or deployment was
performed. Full kernels and the Bluetooth module were not rebuilt during source
collection; the tablet lacks the matching legacy build headers. Earlier build
results remain historical evidence, as recorded in the change inventory.
