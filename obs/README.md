# Tumbleweed / OBS packages

Target: [`home:h-cheung:tb322fc`](https://build.opensuse.org/project/show/home:h-cheung:tb322fc),
`openSUSE_Tumbleweed/aarch64`.

These are the maintained RPM recipes for the Tumbleweed installation and
[image workflow](../docs/opensuse-ci.md). Device validation is recorded separately
from build success. Shared upstream source and device patches remain in
`packages/`; the OBS recipes retain official openSUSE package splits where possible.

The `openSUSE_Tumbleweed` repository builds against
`openSUSE:Tumbleweed/standard` as of 2026-10-31, replacing
`openSUSE:Factory:ARM/standard`. This follows published aarch64 packages via
openSUSE's download-on-demand repository. The pinned source `_link` revisions
remain independent of this binary dependency base. The Oryon target flags and
worker constraints are unchanged.

InputPlumber excludes its unused IIO software-trigger modules-load file so
it does not pull in a second generic kernel. The image uses published OBS
packages only; the temporary local repack repository is retired. kShim declares
its `patch` runtime dependency. The old Arch-style RPM kernel/DKMS prototypes
are retired in favor of `kernel-source` and `als-bridge-kmp`.

The FFmpeg dependency addition is the separate `libplacebo/_link`, pinned to
the official Factory libplacebo 7.387.0 recipe. FFmpeg built against Factory ARM
required `libplacebo.so.387`, while the published Tumbleweed snapshot provided
`.so.360`. Building that library in this project supplies `libplacebo387` and
its matching development package; `configs/opensuse/packages.json` includes
the runtime package and build gate. FFmpeg's own spec already requires
`pkgconfig(libplacebo)`, and ELF dependency generation selects the runtime
SONAME, so no FFmpeg dependency patch was added. Its recorded rebuild reason
was changed libplacebo build dependencies, with its source revision unchanged.
This library link remains present and now also builds against Tumbleweed.

Plasma Setup is linked from KDE:Frameworks at the revision matching the image's
Plasma 6.8.0, with the openSUSE session-name fix and a private QML self-import
filter. It is not currently part of the main Factory or Tumbleweed package set.

`iio-sensor-proxy-y700` enables the SSC backend and adds its libssc build
dependency. Carrying only the startup-race patch on the official recipe leaves
SSC disabled and makes the physical ambient-light sensor unavailable to KDE.

`libkscreen6` is pinned to the official Factory 6.8.0 source revision matching
the published desktop. Its small Wayland patch sends the current transform
when disabling automatic rotation, so KWin also saves that angle as the manual
orientation. Otherwise the current session stays horizontal but the next login
can restore an older portrait angle. The official RPM split is retained; no
login-time rotation script is needed. Rebase this pin with the desktop stack,
not independently onto a newer Factory Plasma dependency set.

RPM recipes and adaptation scripts live here. Downloaded source archives, OBS
working copies and build logs live under `build/obs-tb322fc/` and are not committed.
Only the specific source files needed for each package are uploaded; the full
Freedom checkout contains firmware and must not be uploaded as a source bundle.

Policy:

* Reuse openSUSE packages where no device changes are needed.
* Keep the official FFmpeg software codec restrictions; add only the Iris
  H.264/HEVC V4L2 hardware wrappers, with build checks against libx264/libx265
  and software H.264/HEVC decoders.
* Keep Mesa's default permitted video codec selection.
* Download LSFG payloads at runtime from the owner's GitHub release, verifying
  a pinned SHA256 before extraction. No LSFG binary payload belongs in OBS.
* Generate boot images locally from the user's verified Android base/firmware.
* Record source revisions and results; a successful RPM build does not imply
  suspend, audio, game mode or boot installation have been tested on hardware.

Official package definitions are retained through `_link` and `project.diff`.
Libcamera additionally fetches the source commit from `sources.json` with
`tar_scm`: the device autofocus patch requires its newer SoftISP protocol.
Its library, IPA, Python, GStreamer, cam and qcam RPM split remains the official
one. The distribution's OV02E10 patch is rebased to that same source commit.

`msime` tracks `home:msime/msime` through a source link. Its downstream changes
add the missing font dependency for the native canvas tests and the optional
Steam `pinyin` IBus alias, retaining the original engine and complete test suite.
Details and the failure reproduction are in [msime/README.md](msime/README.md).

`prepare-kernel-suse.py` reads and verifies the current Arch recipe's patch
inputs, applies the full stack with zero fuzz, and prepares the official kernel
source/development packages plus the `freedom` flavor. `--publish` uploads the
downstream link and patch archives; the kernel tarball is fetched by `_service`.
ALS uses the standard KMP macros and waits for matching kernel development RPMs.

The Freedom kernel RPM also owns the versioned
`/usr/lib/modules/<release>/freedom-dpu-rotation` capability marker, matching
the Arch recipe. The updated Gamescope session package defaults to DPU rotation
when the running kernel has this marker, and falls back to GPU rotation on
older Freedom kernels. No per-user configuration is needed. To force GPU
rotation, set `Y700_ROTATION=gpu` in
`~/.config/gamescope-session-plus/sessions.d/steam` and restart the game session.
`Y700_ROTATION=auto` (or removing the override) restores the default. See the
[device validation record](../docs/freedom-sync-20261029.md) for the expected
DRM plane state and GPU fallback.

The active project target profile is maintained in `project.conf`: native
C/C++ uses `-mcpu=oryon-1+rng+fp16`, kernel/KMP builds pass the same CPU setting
through `KCFLAGS`, and Rust uses `target-cpu=oryon-1` with `+rand,+fp16`.
Distribution optimization and hardening flags remain inherited. Native build
tools/tests are scheduled on workers with BF16, I8MM, SHA3 and SM4 support.
The Windows cross runtimes retain their own target flags.

Keep warnings inherited from Freedom or the official RPM recipe unchanged;
do not carry downstream patches solely to silence those warnings. The two
vendor input-driver initialization fixes and the accompanying cosmetic RPM
cleanup from the initial warning review were withdrawn on that basis.

The official Factory ARM `kernel-default` 7.3.0-1.1 build also emits the missing
kernel-scriptlet, duplicate-file, double-separator, missing-symbol-table and
`find-provides.ksyms` integer diagnostics. The scriptlets are absent in the OBS
install-check environment; real installations require `suse-kernel-rpm-scriptlets`.
The dependency helper also misparses the uncompressed `vmlinux` placeholder and
adds a bogus `kernel-uname-r = vmlinux`. Do not rename the kernel or alter its
code to silence these inherited packaging issues. Compare the RPM's actual
`ksym(freedom:...)` capabilities against `Module.symvers` before accepting a new
kernel/KMP combination.

`llvm-mingw-arm64ec` builds Windows CRT, compiler-rt, libc++, libunwind and
winpthreads from source using the distribution's Clang/LLVM 23 binaries.
Its `%check` compiles an ARM64EC object and links a DLL that uses C++ containers,
exceptions and Win32 imports. It does not run Windows binaries on the builder.
The check uses the installed layout after SUSE's symlink normalization, including
both target-prefixed `clang-scan-deps` aliases. This package disables only the
GNU strip and objcopy archive-normalization passes with `NO_BRP_STRIP_DEBUG`
and `NO_BRP_AR`: GNU binutils cannot rewrite the ARM64EC/ARM64X libraries.
LLVM already writes deterministic archives, and the native wrapper build strips
its own executables. The other RPM policy checks remain enabled.
Windows headers, archives and C++ module sources are in the required `-devel`
subpackage. `%check` parses every archive with LLVM and verifies the three
empty upstream compatibility archives. The RPMLint exceptions apply only to
GNU readelf diagnostics for the Windows archives and those empty placeholders.
