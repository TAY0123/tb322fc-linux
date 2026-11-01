from pathlib import Path
import sys,subprocess
root=Path(sys.argv[1]); src=root/'sources'
p=src/'freedom-kernel-update.py'
p.write_text((root/'local/freedom-kernel-update.py').read_text())
subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(Path(__file__).with_name('rpm-kernel-layout.patch').resolve())],cwd=src,check=True)
p=src/'build-tools.py'
p.write_text(p.read_text().replace('"python",','"python3",'))
recipe=root/'local/PKGBUILD'
text=recipe.read_text().replace('  python "$srcdir/build-tools.py"','  python3 "$srcdir/build-tools.py"')
text=text.replace('${SRCDEST:-$startdir}/CrDK-b6c3335.tar.gz','$srcdir/CrDK-b6c3335.tar.gz')
text='\n'.join(line for line in text.splitlines() if 'install -Dm644' not in line or '/usr/share/libalpm/hooks/' not in line)+'\n'
recipe.write_text(text)
