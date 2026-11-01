#!/usr/bin/env bash
# Run package tools in a disposable mount/PID namespace, including on x86_64.
set -euo pipefail

if [[ ${1:-} != --namespace ]]; then
    [[ $EUID == 0 && $# -ge 2 ]] || { echo "Usage: sudo $0 ROOT COMMAND [ARG...]" >&2; exit 2; }
    exec unshare --mount --pid --fork --kill-child --propagation private "$0" --namespace "$@"
fi
shift
root=$(realpath -e -- "$1")
shift
[[ $root != / && -f $root/.tb322fc-opensuse-build && -x $root/usr/bin/rpm ]] || {
    echo 'Refusing a root without the TB322FC staging marker and RPM.' >&2; exit 2;
}

handler=
cleanup() {
    if [[ -n $handler && -e /proc/sys/fs/binfmt_misc/$handler ]]; then
        echo -1 > "/proc/sys/fs/binfmt_misc/$handler"
    fi
    # Only mounts created inside this private namespace disappear on exit.
}
trap cleanup EXIT
if [[ $(uname -m) != aarch64 ]]; then
    interpreter=$(command -v qemu-aarch64-static)
    [[ -e /proc/sys/fs/binfmt_misc/register ]] || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
    handler=tb322fc-opensuse-$$
    python3 - "$handler" "$interpreter" <<'PY'
import pathlib, sys
magic = bytes.fromhex('7f454c460201010000000000000000000200b700')
mask = bytes.fromhex('ffffffffffffff000000000000000000feffffff')
escape = lambda data: ''.join(f'\\x{b:02x}' for b in data)
record = f':{sys.argv[1]}:M::{escape(magic)}:{escape(mask)}:{sys.argv[2]}:F\n'
pathlib.Path('/proc/sys/fs/binfmt_misc/register').write_text(record)
PY
    export QEMU_CPU=max
fi

mount -t proc proc "$root/proc"
mount --bind /sys "$root/sys"
mount -o remount,bind,ro "$root/sys"
mount -t tmpfs -o mode=755,nosuid tmpfs "$root/dev"
for spec in 'null 1 3 666' 'zero 1 5 666' 'random 1 8 666' 'urandom 1 9 666' 'tty 5 0 666'; do
    read -r name major minor mode <<< "$spec"
    mknod -m "$mode" "$root/dev/$name" c "$major" "$minor"
done
mkdir -p "$root/dev/pts" "$root/dev/shm"
mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts "$root/dev/pts"
mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs "$root/dev/shm"
ln -s pts/ptmx "$root/dev/ptmx"
ln -s /proc/self/fd "$root/dev/fd"
ln -s /proc/self/fd/0 "$root/dev/stdin"
ln -s /proc/self/fd/1 "$root/dev/stdout"
ln -s /proc/self/fd/2 "$root/dev/stderr"
mount -t tmpfs -o mode=755,nosuid,nodev tmpfs "$root/run"
mkdir -p "$root/run/netconfig"
cp -L /etc/resolv.conf "$root/run/netconfig/resolv.conf"
# openSUSE's resolver symlink points here. A regular resolv.conf is bound instead.
if [[ ! -L $root/etc/resolv.conf ]]; then
    touch "$root/etc/resolv.conf"
    mount --bind /etc/resolv.conf "$root/etc/resolv.conf"
fi
export SYSTEMD_OFFLINE=1 LC_ALL=C.UTF-8 PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
chroot "$root" "$@"
