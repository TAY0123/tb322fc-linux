from pathlib import Path
import re,shutil,sys
root=Path(sys.argv[1]);src=root/'sources';local=root/'local'
for name in ('simpleini','unordered_dense','xess','vulkan','spdlog','magic_enum','nvapi'):
    destination=src/'Sloptiscaler/external'/name
    if destination.exists():shutil.rmtree(destination)
    shutil.copytree(src/name,destination)
p=local/'PKGBUILD';s=p.read_text()
s=re.sub(r'  git submodule init.*?  git -c protocol.file.allow=always submodule update[^\n]*\n','',s,flags=re.S)
s=s.replace('python - ', 'python3 - ').replace('LLVM_MINGW="$srcdir/$_llvm"','LLVM_MINGW="/usr/libexec/llvm-mingw-arm64ec"')
p.write_text(s)
# Header dependencies ship optional Windows runtimes which this build never
# consumes. Keep their headers/licenses, remove binary payloads from the bundle.
for path in src.rglob('*'):
    if path.is_file() and path.suffix.lower() in ('.dll','.exe','.lib','.pdb'):
        path.unlink()
(root/'rpm-overrides.sh').write_text('export CFLAGS="" CXXFLAGS="" LDFLAGS=""\n')
