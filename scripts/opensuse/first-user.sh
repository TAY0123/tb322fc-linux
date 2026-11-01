#!/usr/bin/env bash
set -euo pipefail
[[ -f /etc/plasma-setup-done ]] || exit 1
[[ ! -f /var/lib/tb322fc/first-user-ready ]] || exit 0
account=$(/usr/libexec/armada/session-user)
# The setup session can still be active when it writes the completion flag.
# Never initialize its system account as the newly created desktop user.
uid=$(id -u "$account" 2>/dev/null || true)
if [[ ! $uid =~ ^[0-9]+$ ]] || (( uid < 1000 || uid >= 65534 )); then
    account=$(python3 - <<'PY'
import pwd
users = [u.pw_name for u in pwd.getpwall()
         if 1000 <= u.pw_uid < 65534
         and not u.pw_shell.endswith(('nologin', 'false'))
         and u.pw_dir not in ('', '/', '/nonexistent')]
print(users[0] if len(users) == 1 else '')
PY
)
fi
[[ -n $account ]] || { echo 'No unique desktop user was created by Plasma Setup.' >&2; exit 1; }
# openSUSE's SDDM sysconfig value overrides its normal autologin drop-ins.
# Completing setup returns to the greeter instead of logging into setup again.
sed -i 's/^DISPLAYMANAGER_AUTOLOGIN="plasma-setup"$/DISPLAYMANAGER_AUTOLOGIN=""/' /etc/sysconfig/displaymanager
group=$(id -gn "$account")
printf 'd /run/vpower 0755 %s %s -\n' "$account" "$group" > /etc/tmpfiles.d/vpower.conf
systemd-tmpfiles --create /etc/tmpfiles.d/vpower.conf
# Decky's working directory and Steam debugging marker must exist before its
# first start, even if Steam has not downloaded its payload yet.
# HOME must be expanded by the new user's shell.
# shellcheck disable=SC2016
runuser -u "$account" -- /bin/sh -c '
    set -e
    mkdir -p "$HOME/.local/var/opt/decky-loader/plugins" "$HOME/.local/share/Steam" "$HOME/.steam"
    if [ ! -e "$HOME/.steam/steam" ] && [ ! -L "$HOME/.steam/steam" ]; then
        ln -s ../.local/share/Steam "$HOME/.steam/steam"
    fi
    touch "$HOME/.local/share/Steam/.cef-enable-remote-debugging"
'
unit=$(systemd-escape --template=decky-loader@.service "$account")
systemctl enable "$unit"
systemctl --no-block start "$unit"
install -d -m755 /var/lib/tb322fc
touch /var/lib/tb322fc/first-user-ready
