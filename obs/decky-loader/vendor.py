from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tarfile,urllib.request
root=Path(sys.argv[1])
src, = [p for p in (root/'sources').glob('decky-loader-*') if p.is_dir()]
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from obsapi import WORK
archive=WORK/'cache/pnpm-10.11.0.tgz'
if not archive.exists():
    subprocess.run(['curl','-fLsS','--retry','3','-o',str(archive),'https://registry.npmjs.org/pnpm/-/pnpm-10.11.0.tgz'],check=True)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == 'a69e9cb077da419d47d18f1dd52e207245b29cac6e076acedbeb8be3b1a67bd7'
with tarfile.open(archive) as tar:tar.extractall(root/'pnpm-tool',filter='data')
frontend=src/'frontend'
# Fetch all optional platform packages, including aarch64 Rollup, on this
# x86_64 preparation host. The OBS build later installs exclusively offline.
subprocess.run(['node',str(root/'pnpm-tool/package/bin/pnpm.cjs'),'fetch','--frozen-lockfile','--force','--store-dir',str(root/'pnpm-store')],cwd=frontend,check=True)
for path in frontend.rglob('node_modules'):
    if path.exists() and not path.is_symlink():shutil.rmtree(path)
