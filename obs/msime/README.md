# MSIME for TB322FC

This package tracks `home:msime/msime` through `_link`, initially based on
source revision 13 (`b7687c79737c25bef0e69108c60b4a19`, MSIME 0.15.0).
Only the spec difference, Steam alias patch, constraints and changelog are
uploaded. Source archives, vendored dependencies and the complete source build
are inherited. Upstream changes trigger link expansion and a new build; patch
conflicts still need review. No prebuilt release RPM is used as the build input.

## openSUSE test failure

The upstream Tumbleweed x86_64 build passed 107 of 108 tests. The failure was
`linux-candidate-native-canvas`, in `skin_layout()`: the width of `12.` at the
scaled number font must be smaller than its width at the normal text font.
The build installed Fontconfig/Pango but no fonts. The successful Fedora 44
build installed Cantarell and Noto Sans.

An isolated Fontconfig probe on Tumbleweed reproduced the failing Pango calls:

| Available fonts | Sans 8 px width | Sans 12 pt width | Assertion |
| --- | ---: | ---: | --- |
| None | 30 px | 30 px | Fails |
| Noto Sans only | 12 px | 22 px | Passes |

`BuildRequires: google-noto-sans-fonts` supplies the missing test fixture.
The renderer and its assertions are unchanged; the complete CTest suite stays
enabled. Logs and probe code are in
`build/opensuse-rootfs/msime-20261101/`.

## Steam engine alias

The optional `MSIME_IBUS_PINYIN_ALIAS` patch is ported from our earlier
`msime-bin-steam` package. It exposes `pinyin` and the original `msime-linux`
through the same native IBus host. XML, dynamic registration, the factory and
crash recovery all accept the alias. It uses the current `msime-linux` icon and
preserves the active keyboard layout. The RPM conflicts with `ibus-pinyin`;
it does not overwrite user input-method preferences or dictionaries.

With the option enabled, CTest adds `linux-ibus-pinyin-demand-activation`.
It uses the existing isolated real IBus daemon test to request `pinyin` as the
first engine, alongside the existing test for the original name. Actual Steam
candidate selection and text commit require separate interactive validation.

The project Oryon flags apply to C/C++ and Rust, and the inherited resource
constraints are extended with the project's required CPU features.

OBS built and published `msime-0.15.0-2.1.aarch64.rpm`: all 109 CTest cases
passed, including the native canvas case and both IBus demand-activation cases.
The package has not been installed on the tablet as part of this packaging task.
