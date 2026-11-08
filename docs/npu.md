# Y700 Gen 4 CDSP / NPU support

The SM8750 CDSP can run native ARM64 inference through FastRPC and the
Hexagon v79 backend. The base support consists of:

- `obs/kernel-source/tb322fc-cdsp.patch`: enables the CDSP using stock split
  firmware, expands the unsupported IOMMU stream mask, and supplies eight
  sessions on the context bank used in hardware testing.
- `obs/fastrpc`: the upstream 1.0.8 CDSP client libraries and headers, the
  board-specific DSP search path, system DMA heap loading, and active-seat
  access to `/dev/fastrpc-cdsp`. Secure domains remain restricted.
- `firmware.json`: hashes for the generic CDSP firmware and the unsigned
  shell, DSP libc++ and libc++abi. Import these from extracted stock firmware
  with `scripts/import-firmware.py`, just like the existing GPU/ADSP firmware.
  No per-device calibration is needed for this compute path.

`fastrpc-tb322fc` installs the board configuration under `/usr/share/qcom/conf.d`.
Its CDSP library directory points to `/usr/lib/firmware/qcom/sm8750/cdsp`.
Firmware remains outside OBS; the existing firmware bundle and rootfs staging
tools verify and provision it. The ADSP sensor service and its private
`/var/lib/hexagonrpc` data are separate.

After installing the new kernel, firmware and `fastrpc-tb322fc`, reboot normally.
Check that the `cdsp` remote processor is running, `/dev/fastrpc-cdsp` and
`/dev/dma_heap/system` exist, and the logged-in local user has access to both.
Applications still need their own compatible inference runtime and model;
the base package does not distribute QNN, ONNX Runtime or model weights.

## Validation on 2026-11-08

The equivalent configuration was exercised on the tablet with temporary
overlays before preparing the permanent DTS. Native ARM64 QNN/HTP v79 ran
real super-resolution models with CPU fallback disabled, including repeated
process/session creation and unprivileged shared-buffer inference. A retained
session survived a ten-second suspend and completed 100 further inferences
with finite, bit-identical output. The patched DTB compiles with the same
warnings as the baseline and contains the tested stream IDs and session count.

Two limitations remain: removing and reloading the temporary CDSP device in
the same boot can fail SCM memory assignment until reboot; QNN/FastRPC also
logs errors while releasing resources after the retained-session test, despite
successful post-resume inference. These are not evidence of a completely
validated runtime lifecycle. The permanent DTS still needs a cold-boot check
with the OBS-built kernel. No runtime overlay loader is shipped.

The OptiScaler bridge is a separate local experiment. Its models, Wine prefix,
helper, QNN/ORT libraries and test modules have been removed from the tablet;
the full backup remains on the development computer. They are not part of
this base support or the OBS packages.
