from pathlib import Path
import sys
root=Path(sys.argv[1]); local=root/'local'
p=local/'PKGBUILD'
p.write_text(('\n'.join(line for line in p.read_text().splitlines() if 'ln -s "/usr/share/lsfg-vk/payloads/' not in line)+'\n').replace('python -m', 'python3 -m'))
p=local/'plugins/decky-lsfg-vk/py_modules/lsfg_vk/installation.py'
p.write_text(p.read_text().replace('"/usr/bin/lsfg-vk-cli"','"/var/lib/lsfg-vk/current/usr/bin/lsfg-vk-cli"'))
p=local/'tests/test_port.py'
p.write_text(p.read_text().replace('"/usr/bin/lsfg-vk-cli"','"/var/lib/lsfg-vk/current/usr/bin/lsfg-vk-cli"'))
p=local/'lsfg-sync'
text=p.read_text().replace('    chown -R', '''    if [[ "$name" == decky-lsfg-vk ]]; then archive=lsfg-vk-2.0.0.tar.xz; else archive=lsfg-vk_noui.zip; fi
    mkdir -p "$staging_dir/bin"
    ln -sfn "/var/lib/lsfg-vk/current/usr/share/lsfg-vk/payloads/$archive" "$staging_dir/bin/$archive"
    chown -R''')
p.write_text(text)
