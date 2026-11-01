#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run the repository's shared source/install logic inside an RPM build root.
# No makepkg or pacman is used. RPM dependencies and integration are in the spec.
set -euo pipefail
root=$(pwd)
export startdir="$root/local" srcdir="$root/sources"
export CARCH=aarch64
export CARGO_NET_OFFLINE=true
export CARGO_HOME="$root/cargo-home"
if [[ -f "$CARGO_HOME/config.toml.in" ]]; then
    sed "s|@ROOT@|$root|g" "$CARGO_HOME/config.toml.in" > "$CARGO_HOME/config.toml"
fi
export npm_config_cache="$root/npm-cache"
export npm_config_offline=true
export npm_config_audit=false npm_config_fund=false
export CFLAGS="${CFLAGS:--O2 -g}" CXXFLAGS="${CXXFLAGS:--O2 -g}" LDFLAGS="${LDFLAGS:-}"
source "$startdir/PKGBUILD"
if [[ -f "$root/rpm-overrides.sh" ]]; then source "$root/rpm-overrides.sh"; fi
cd "$srcdir"
case "$1" in
    prepare) if declare -F prepare >/dev/null; then prepare; fi ;;
    build) if declare -F build >/dev/null; then build; fi ;;
    check) if declare -F check >/dev/null; then check; fi ;;
    install)
        export pkgdir="$2"
        mkdir -p "$pkgdir"
        package
        ;;
    *) exit 2 ;;
esac
