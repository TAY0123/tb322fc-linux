# FFmpeg stateful V4L2

The complete Arch Linux FFmpeg recipe is based on [packaging commit
5c4a25f039c060c421a1cd887551d491dff4d55d](https://gitlab.archlinux.org/archlinux/packaging/packages/ffmpeg/-/tree/5c4a25f039c060c421a1cd887551d491dff4d55d).
It retains the signed 9.0.2 source, Chromium compatibility patch, codec
configuration and shared-library ABI. `ffmpeg-v4l2m2m` provides `ffmpeg`
and its library sonames and conflicts with the distribution package.

Three checksum-pinned patches are referenced from [Project-SunUEFI
be307364](https://github.com/slwyts/Project-SunUEFI/tree/be3073644216a413776b973203d4222e8950703a/linux/bsp/patches/ffmpeg):
stateful source-change sequencing, capture-buffer lifetime across resolution
changes, and P010 capture format handling. Patches retain the licenses and
notices of the original FFmpeg files.

Full Iris resolution-change validation also needs the kernel PSC_LAST fix;
building or installing this userspace package alone does not supply it.
Vivaldi's Chromium-specific `libffmpeg.so` is a separate build and cannot be
replaced by this package's `libavcodec.so` or command-line executable.

On the tablet with kernel `7.2.6-11-freedom`, Iris decoded the 12-frame H.264
sample and all 36 frames across 640x480 -> 1280x720 -> 640x480. Hardware
encoding produced 12 decodable frames; unloading and reloading Iris also
completed. Other codecs and P010 were not tested.

The raw H.264 encoder test has a remaining timing limitation: ffprobe reports
60 fps for a 25 fps input with both this package and the stock 9.0.2 package
on the same kernel. This port does not correct that encoder behavior.

Arch's [Vivaldi codec recipe](https://gitlab.archlinux.org/archlinux/packaging/packages/vivaldi-ffmpeg-codecs/-/blob/main/PKGBUILD)
builds a selected set of software codecs from Chromium's FFmpeg fork into
`/opt/vivaldi/libffmpeg.so.<browser-major>`. Replacing that library requires
a matching Chromium build; its preload path does not enable these V4L2 fixes.

## openSUSE hardware decoder build

`obs/ffmpeg-v4l2m2m` inherits the reduced official FFmpeg 9 recipe and adds
only `h264_v4l2m2m` and `hevc_v4l2m2m` to its decoder allowlist. These wrappers
send compressed video to the kernel Iris driver; they do not depend on Mesa,
libx264 or libx265. Native H.264/HEVC and OpenH264 software decoders are disabled.
Build checks require both V4L2 decoders and reject libx264, libx265 or nonfree
configuration. Existing official encoder settings and dependencies stay intact.
This does not enable codec support in Chromium's separate FFmpeg build.

On TB322FC with kernel `7.2.6-28-freedom`, a standalone build with the same
three V4L2 patches passed FFmpeg's reference frame checksums for H.264 Baseline
(299 frames), H.264 Main (50), HEVC Main (30) and HEVC Main10 (8, using P010
capture). Automatic decoder selection also worked. Two ordinary H.264 High
MP4 files decoded fully; concatenating their elementary streams exercised
432x240 -> 1280x720 -> 432x240 and decoded all 1,240 frames.

A separate Baseline -> Main -> Baseline conformance-stream concatenation
failed at the first transition with an Iris firmware session error. The test
changes both profile and resolution, so it does not isolate the cause; do not
treat arbitrary in-stream profile changes as supported. Fresh sessions decoded
normally afterward. Validation logs are under
`build/opensuse-rootfs/ffmpeg-hwonly-20261101/`.

The OBS `9.0.2-4.1` RPMs were subsequently installed and passed the same
reference checks, automatic decoder selection, MP4 and High-profile resolution
change tests, with no new kernel messages. The runtime RPM dependencies contain
neither libx264 nor libx265; the official OpenH264 encoder dependency remains.
