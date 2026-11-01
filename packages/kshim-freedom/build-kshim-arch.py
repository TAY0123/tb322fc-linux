#!/usr/bin/env python3
"""Build a Gen4 kShim image for an explicit Linux root, without device writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import struct
import sys
import tempfile
import uuid


def boot_arguments(cmdline, root_selector):
    """Apply Gen4 console defaults while preserving explicit boot overrides."""
    if any(c in cmdline for c in "\x00\r\n"):
        raise ValueError("cmdline must be one line")
    tokens = [x for x in cmdline.split() if not x.startswith("root=")]
    fbcon_options = {option.split(':', 1)[0]
                     for token in tokens if token.startswith('fbcon=')
                     for option in token[len('fbcon='):].split(',')}
    for option, value in [('rotate', '3'), ('font', 'TER16x32')]:
        if option not in fbcon_options:
            tokens.append(f'fbcon={option}:{value}')
    # systemd-vconsole-setup would otherwise restore the distribution's 8x16
    # font after the kernel's 16x32 console has already appeared.
    if not any(token.startswith('vconsole.font=') for token in tokens):
        tokens.append('vconsole.font=latarcyrheb-sun32')
    tokens.append('root=' + root_selector)
    return ' '.join(tokens)


def main():
    project = next((p for p in Path(__file__).resolve().parents
                    if (p / "configs/freedom-sources.json").is_file()), Path("/usr/share/tb322fc"))
    source_manifest = project / "configs/freedom-sources.json"
    if not source_manifest.is_file():
        source_manifest = Path("/usr/share/tb322fc/freedom-sources.json")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--builder", type=Path, required=True,
                        help="Pinned Freedom system_files/usr/libexec/armada/kshim-build-boot.py")
    parser.add_argument("--manifest", type=Path, default=source_manifest)
    for name in ["stock-boot", "runtime", "image", "dtb", "initrd", "packer", "unpacker", "repacker", "avbtool", "out"]:
        parser.add_argument("--" + name, type=Path, required=True)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--root-partuuid")
    selector.add_argument("--root-partlabel", choices=['rootfs'])
    parser.add_argument("--header-template", type=Path,
                        help="Override the device-tested header profile with metadata from this Android v4 image")
    parser.add_argument("--cmdline", required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    original = args.builder.read_bytes()
    expected = manifest["freedom"]["kshim_builder_sha256"]
    if hashlib.sha256(original).hexdigest() != expected:
        parser.error("Freedom builder differs from the pinned source manifest")
    root_uuid = str(uuid.UUID(args.root_partuuid)) if args.root_partuuid else None
    root_selector = "PARTUUID=" + root_uuid if root_uuid else "PARTLABEL=rootfs"
    try:
        cmdline = boot_arguments(args.cmdline, root_selector)
    except ValueError as error:
        parser.error(str(error))
    # Keep upstream source intact; apply the reviewed Arch-layout delta.
    patches = []
    for name in manifest["kshim_builder_patches"]:
        candidates = [project / name, args.manifest.parent / Path(name).name]
        patch = next((p for p in candidates if p.is_file()), None)
        if patch is None:
            parser.error("missing kShim builder patch: " + name)
        patches.append(patch.resolve())
    with tempfile.TemporaryDirectory(prefix="kshim-arch-") as tmp:
        builder = Path(tmp) / "kshim-build-boot.py"
        builder.write_bytes(original)
        for patch in patches:
            subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(patch)],
                           cwd=tmp, check=True)
        command = [sys.executable, str(builder), "--layout", "maintenance",
                   "--default-entry", "maintenance", "--linux-image", str(args.image.resolve()),
                   "--dtb", str(args.dtb.resolve()), "--initrd", str(args.initrd.resolve()),
                   "--bootargs", cmdline, "--source-label", "TB322FC Linux / Freedom compatibility"]
        for name in ["stock-boot", "runtime", "packer", "unpacker", "repacker", "avbtool", "out"]:
            command += ["--" + name, str(getattr(args, name.replace("-", "_")).resolve())]
        subprocess.run(command, check=True)
    packed_dtb = args.out / "work/packed-dtb.dtb"
    for key, expected_value in [("armada,boot-stage", "os"), ("armada,root-medium", "internal")]:
        value = subprocess.check_output(["fdtget", "-t", "s", str(packed_dtb), "/chosen", key], text=True).strip()
        if value != expected_value:
            raise RuntimeError(f"Invalid Linux menu role: {key}={value!r}")
    # Keep the upstream byte-level report and its boot.img intact. Adapt only
    # the deployment image's OS version field, then regenerate its AVB hash.
    template = args.header_template.read_bytes() if args.header_template else None
    if template is not None:
        if template[:8] != b"ANDROID!" or struct.unpack_from("<I", template, 40)[0] != 4:
            parser.error("header-template must be an Android v4 boot image")
        os_version = struct.unpack_from("<I", template, 16)[0]
    else:
        profile = manifest["android_boot_header_compatibility"]
        major, minor, patch = map(int, profile["os_version"].split('.'))
        year, month = map(int, profile["os_patch_level"].split('-'))
        if not all(0 <= n <= 127 for n in [major, minor, patch]) or not (2000 <= year <= 2127 and 1 <= month <= 12):
            parser.error("invalid header compatibility profile")
        os_version = ((major << 14 | minor << 7 | patch) << 11) | ((year - 2000) << 4) | month
        if os_version != profile["encoded_os_version"]:
            parser.error("header profile encoding differs from recorded value")
    upstream_boot = args.out / "boot.img"
    # avbtool resolves the hash descriptor's partition name as boot.img in
    # the image directory, so each independently verified variant needs one.
    arch_boot = args.out / "arch/boot.img"
    arch_boot.parent.mkdir(exist_ok=True)
    shutil.copyfile(upstream_boot, arch_boot)
    avb = [sys.executable, str(args.avbtool.resolve())]
    subprocess.run(avb + ["erase_footer", "--image", str(arch_boot)], check=True)
    contents = bytearray(arch_boot.read_bytes())
    contents[16:20] = struct.pack("<I", os_version)
    arch_boot.write_bytes(contents)
    subprocess.run(avb + ["add_hash_footer", "--image", str(arch_boot), "--partition_size", "100663296",
                          "--partition_name", "boot", "--algorithm", "NONE"], check=True)
    subprocess.run(avb + ["verify_image", "--image", str(arch_boot)], check=True)
    before, after = upstream_boot.read_bytes(), arch_boot.read_bytes()
    kernel_size = struct.unpack_from("<I", before, 8)[0]
    if not (after[:16] == before[:16] and after[20:4096+kernel_size] == before[20:4096+kernel_size]):
        raise RuntimeError("Header adaptation changed unrelated boot payload")
    (args.out / "arch-root.json").write_text(json.dumps({
        "freedom_commit": manifest["freedom"]["commit"],
        "builder_sha256": expected,
        "root_partuuid": root_uuid,
        "root_selector": root_selector,
        "bootargs": cmdline,
        "layout": "Linux root with explicit kernel/DTB/initramfs payloads",
        "linux_menu_name": "机身 Linux",
        "boot_stage": "os",
        "root_medium": "internal",
        "header_template_sha256": hashlib.sha256(template).hexdigest() if template is not None else None,
        "os_version": os_version,
        "arch_boot": str(arch_boot.resolve()),
        "arch_boot_sha256": hashlib.sha256(after).hexdigest(),
        "header_only_changed": True,
        "flashed": False,
    }, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
