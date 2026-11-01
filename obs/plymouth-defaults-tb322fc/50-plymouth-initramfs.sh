#!/bin/bash
# Collect the selected packaged theme and its dependencies, without host data.
set -euo pipefail
root=${1:?initramfs directory is required}
[[ "$root" = /* && "$root" != / && -d "$root" ]] || exit 1

# Keep the existing BusyBox init; only use Plymouth's asset collector.
SYSTEMD_UNIT_DIR=/nonexistent \
    /usr/libexec/plymouth/plymouth-populate-initrd --targetdir "$root"
/usr/lib/dracut/dracut-install -D "$root" -l -a \
    /usr/lib/systemd/systemd-udevd /usr/bin/udevadm \
    /usr/lib/udev/rules.d/60-drm.rules \
    /usr/lib/udev/rules.d/60-input-id.rules
if [[ -f /usr/lib/udev/hwdb.bin ]]; then
    /usr/lib/dracut/dracut-install -D "$root" /usr/lib/udev/hwdb.bin
fi

# New xkeyboard-config uses a versioned directory. Include all keymap
# fragments, including nested symbols, and preserve that canonical path.
xkb=$(readlink -f /usr/share/X11/xkb)
install -d "$root$xkb"
for part in compat keycodes rules symbols types; do
    cp -a "$xkb/$part" "$root$xkb/"
done
install -Dm755 /usr/lib/kshim-freedom/plymouth-init "$root/sbin/kshim-plymouth"
printf 'ID=tb322fc-initramfs\n' > "$root/etc/initrd-release"

# Check the assembled payload before signing/deploying a boot image.
chroot "$root" /usr/sbin/plymouthd --help >/dev/null
chroot "$root" /usr/bin/plymouth --get-splash-plugin-path >/dev/null
chroot "$root" /usr/lib/systemd/systemd-udevd --version >/dev/null
