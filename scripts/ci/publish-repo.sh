#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Publish the packages built by build-rootfs.sh as a pacman repository on a
# separate GitHub pre-release (repository-freedom-v2), laid out for pacman:
# <repo>.db / <repo>.files plus the package tarballs, all under one release URL.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."

REPO=${REPO_NAME:-tb322fc}
TAG=${REPO_TAG:-repository-freedom-v2}
[[ $TAG == repository-freedom-v2 ]] || { echo "Refusing to replace the legacy package repository" >&2; exit 1; }
SLUG=${GITHUB_REPOSITORY:-h0cheung/tb322fc-linux}
PKGS=${REPO_PKGS:-build/rootfs-cache/pkgs}
PROJECT=$PWD

[[ -d "$PKGS" ]] || { echo "publish-repo: no packages at $PKGS (run build-rootfs.sh first)" >&2; exit 1; }
shopt -s nullglob
pkgs=()
for f in "$PKGS"/*.pkg.tar.*; do
    [[ "$f" != *.sig ]] || continue
    case ${f##*/} in
        linux-freedom-[0-9]*|linux-freedom-headers-[0-9]*|als-bridge-dkms-[0-9]*|kshim-freedom-[0-9]*) continue ;;
    esac
    pkgs+=("$f")
done
shopt -u nullglob
(( ${#pkgs[@]} )) || { echo "publish-repo: no .pkg.tar.* files under $PKGS" >&2; exit 1; }
bash "$PROJECT/scripts/ci/init-repo.sh"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# GitHub rewrites release-asset names (":" -> "."), but pacman builds the
# download URL from the db's %FILENAME%. Rename to the same safe charset first
# so the db and the served asset agree; the package contents are untouched.
for src in "${pkgs[@]}"; do
    [[ "$src" != *.sig ]] || continue
    base=$(basename "$src")
    cp -f "$src" "$work/${base//[!A-Za-z0-9._-]/.}"
done

cd "$work"
repo-add -q "$REPO.db.tar.gz" ./*.pkg.tar.* >/dev/null
# pacman fetches <repo>.db; GitHub cannot serve symlinks, so ship real copies
# (repo-add leaves <repo>.db as a symlink to <repo>.db.tar.gz).
rm -f "$REPO.db" "$REPO.files"
cp -f "$REPO.db.tar.gz" "$REPO.db"
cp -f "$REPO.files.tar.gz" "$REPO.files"

declare -A keep=()
for f in "$REPO.db" "$REPO.db.tar.gz" "$REPO.files" "$REPO.files.tar.gz" ./*.pkg.tar.*; do
    [[ "$f" != *.sig ]] || continue
    keep[$(basename "$f")]=1
done

mapfile -t existing < <(gh release view "$TAG" --repo "$SLUG" --json assets -q '.assets[].name')
declare -A existing_map=()
for name in "${existing[@]}"; do
    existing_map[$name]=1
done

upload_list=()
for f in "${!keep[@]}"; do
    if [[ "$f" == "$REPO.db"* || "$f" == "$REPO.files"* || -z "${existing_map[$f]:-}" ]]; then
        upload_list+=("$f")
    fi
done

if (( ${#upload_list[@]} )); then
    echo "publish-repo: uploading ${#upload_list[@]} asset(s) to $TAG..."
    gh release upload "$TAG" --repo "$SLUG" --clobber "${upload_list[@]}"
fi

# Drop superseded assets (for example an older package version) so the
# release only ever holds the current package set.
for name in "${existing[@]}"; do
    [[ -n "$name" && -z "${keep[$name]:-}" ]] || continue
    gh release delete-asset "$TAG" "$name" --repo "$SLUG" --yes
done

echo "publish-repo: published ${#pkgs[@]} packages to $SLUG@$TAG"
