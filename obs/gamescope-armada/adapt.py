from pathlib import Path
import configparser,importlib.util,shutil,sys
root=Path(sys.argv[1]); src=root/'sources'; game=src/'gamescope'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
spec=importlib.util.spec_from_file_location('simple',Path(__file__).resolve().parents[1]/'prepare-simple.py')
simple=importlib.util.module_from_spec(spec);spec.loader.exec_module(simple)
for relative in ('src/reshade','subprojects/libdisplay-info','subprojects/libliftoff','subprojects/openvr','subprojects/vkroots','subprojects/wlroots','thirdparty/SPIRV-Headers'):
    destination=game/relative
    if destination.exists():shutil.rmtree(destination)
    shutil.copytree(src/Path(relative).name,destination)
for name in ('glm','stb'):
    config=configparser.ConfigParser();config.read(game/'subprojects'/(name+'.wrap'))
    section=config['wrap-git']
    simple.export_git('git+'+section['url']+'#commit='+section['revision'],game/'subprojects'/name)
    shutil.copytree(game/'subprojects/packagefiles'/name,game/'subprojects'/name,dirs_exist_ok=True)
(root/'rpm-overrides.sh').write_text('''prepare() {
  cd "$srcdir/gamescope"
  for p in "$srcdir"/*.patch; do patch -Np1 --fuzz=0 -i "$p"; done
}
arch-meson() {
  local source=$1 output=$2; shift 2
  meson setup "$output" "$source" --prefix=/usr --libdir=lib64 --buildtype=release --wrap-mode=nodownload "$@"
}
''')
