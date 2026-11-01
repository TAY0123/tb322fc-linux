#!/usr/bin/env python3
"""Port the official openSUSE kernel-source packaging to the Freedom flavor."""
from pathlib import Path
import argparse,difflib,hashlib,json,re,shutil,subprocess,tarfile
from importlib.machinery import SourceFileLoader
from obsapi import ROOT,WORK,publish

p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');args=p.parse_args()
up=WORK/'upstream/kernel-source';stage=WORK/'stage/kernel-source'
if stage.exists():shutil.rmtree(stage)
stage.mkdir(parents=True,exist_ok=True)
for f in up.iterdir():
    if f.is_file() and not (f.suffix in ('.spec','.changes') or f.name in ('source-revision.xml','build.specials.obscpio','_constraints','_multibuild') or f.name.startswith('linux-7.3')):
        shutil.copyfile(f,stage/f.name)
archive=WORK/'cache/linux-7.2.6.tar.xz'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='039aef84f2b0994aeda3f4fcfc3d02ec9d7a9bbb9020ea264c43f446c860f606'
shutil.copyfile(archive,stage/archive.name)
work=WORK/'kernel-suse-prep';work.mkdir(exist_ok=True)
src=work/'linux-7.2.6'
if src.exists():shutil.rmtree(src)
subprocess.run(['tar','-xf',str(archive),'-C',str(work)],check=True)
addon=work/'patches.addon';shutil.rmtree(addon,ignore_errors=True);addon.mkdir()
series=[]
def apply(path):
    subprocess.run(['patch','-p1','--batch','--forward','-F0','--no-backup-if-mismatch','-i',str(path.resolve())],cwd=src,check=True,stdout=subprocess.DEVNULL)
def add(path):
    target=addon/f'{len(series):04d}-{path.name}'
    shutil.copyfile(path,target);apply(target);series.append(target.name)
# Retain SUSE's module paths, ksym-provides, and packaging fixes. No unrelated
# distro kernel tuning is imported into the device's validated patch stack.
with tarfile.open(stage/'patches.rpmify.tar.bz2') as t:t.extractall(work,filter='data')
rpmify=[x.strip() for x in (up/'series.conf').read_text().splitlines() if x.strip().startswith('patches.rpmify/')]
for name in rpmify:
    if name.endswith('btf-pahole-j1-option.patch'):
        # 7.2.6 has additional BTF features; retain them when rebasing the
        # identical two -j1 substitutions from SUSE's 7.3 packaging patch.
        before=(src/'scripts/Makefile.btf').read_text()
        assert before.count('-j$(JOBS)')==2
        after=before.replace('-j$(JOBS)','-j1')
        (work/name).write_text('From: TB322FC packaging\nSubject: Rebase SUSE pahole -j1 workaround onto 7.2.6\n\n'+''.join(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),fromfile='a/scripts/Makefile.btf',tofile='b/scripts/Makefile.btf')))
    apply(work/name)
with tarfile.open(stage/'patches.rpmify.tar.bz2','w:bz2') as t:t.add(work/'patches.rpmify',arcname='patches.rpmify')
(stage/'series.conf').write_text('# openSUSE packaging prerequisites\n'+'\n'.join(rpmify)+'\n')
freedom=ROOT/'sources/freedom/packages/kernel'
for line in (freedom/'patches/series').read_text().splitlines():
    name=line.split('#',1)[0].strip()
    if name:add(freedom/'patches'/name)
# Preserve the original order: upstream patches, board files, DTS patches,
# then the local TB322FC patches. Board copies become reviewable patches.
dts='arch/arm64/boot/dts/qcom'
patch=work/'install-freedom-board-trees.patch';chunks=[]
for f in sorted((freedom/'dts').iterdir()):
    if f.suffix not in ('.dts','.dtsi'):continue
    before=src/dts/f.name
    old=before.read_text().splitlines(keepends=True) if before.exists() else []
    chunks.extend(difflib.unified_diff(old,f.read_text().splitlines(keepends=True),fromfile='a/'+dts+'/'+f.name if before.exists() else '/dev/null',tofile='b/'+dts+'/'+f.name))
patch.write_text(''.join(chunks));add(patch)
for f in sorted((freedom/'dts').glob('*.patch')):add(f)
inputs=WORK/'kernel-inputs/inputs'
simple=SourceFileLoader('kernel_recipe_metadata',str(ROOT/'obs/prepare-simple.py')).load_module()
recipe=ROOT/'packages/linux-freedom'
metadata=simple.metadata(recipe/'PKGBUILD')
for item,digest in zip(metadata['source'],metadata['sha256sums'],strict=True):
    name,separator,_=item.partition('::')
    if not name.endswith('.patch'):continue
    f=inputs/name if separator else recipe/name
    assert hashlib.sha256(f.read_bytes()).hexdigest()==digest
    add(f)
(addon/'series').write_text('\n'.join(series)+'\n')
with tarfile.open(stage/'patches.addon.tar.bz2','w:bz2') as t:t.add(addon,arcname='patches.addon')
config=work/'config/arm64';config.mkdir(parents=True,exist_ok=True)
shutil.copyfile(ROOT/'build/freedom-sync-20261029/kernel-input/headers/.config',config/'freedom')
subprocess.run([str(src/'scripts/config'),'--file',str(config/'freedom'),'--enable','MODVERSIONS','--disable','LOCALVERSION_AUTO'],check=True)
for line in (ROOT/'configs/opensuse/kernel.config').read_text().splitlines():
    if not line or line.startswith('#'):continue
    symbol,value=line.split('=',1)
    action={'y':'--enable','m':'--module','n':'--disable'}[value]
    subprocess.run([str(src/'scripts/config'),'--file',str(config/'freedom'),action,symbol],check=True)
with tarfile.open(stage/'config.tar.bz2','w:bz2') as t:t.add(config.parent,arcname='config')
(stage/'config.conf').write_text('+arm64 arm64/freedom\n')
(stage/'source-timestamp').write_text('2026-10-31 09:00:00 +0000\nGIT Revision: 9788014a0293dc26745b000d02854ad88ef73e88\n')
(stage/'config.sh').write_text((up/'config.sh').read_text().replace('SRCVERSION=7.3','SRCVERSION=7.2.6'))
(stage/'_multibuild').write_text('<multibuild><package>kernel-freedom</package><package>kernel-syms</package></multibuild>\n')
(stage/'_constraints').write_text('<constraints><hardware><disk><size unit="G">50</size></disk><physicalmemory><size unit="G">16</size></physicalmemory><processors>4</processors><jobs>4</jobs></hardware></constraints>\n')
# Compiler-derived config symbols differ on the OBS worker; oldconfig retains
# the validated board options while selecting the matching toolchain symbols.
(stage/'TOLERATE-UNKNOWN-NEW-CONFIG-OPTIONS').write_text('Compiler-derived symbols are regenerated on the OBS worker.\n')
changes='-------------------------------------------------------------------\nSat Oct 31 09:00:00 UTC 2026 - h-cheung\n\n- Add TB322FC Freedom flavor with the maintained device patches.\n- Reuse official kernel sources, development packages and KMP macros.\n'
(stage/'kernel-source.changes').write_text(changes)
for name in ('kernel-source','kernel-freedom','kernel-syms'):
    original='kernel-default' if name=='kernel-freedom' else name
    s=(up/(original+'.spec')).read_text()
    s=s.replace('%define srcversion 7.3','%define srcversion 7.2.6').replace('%define patchversion 7.3.0','%define patchversion 7.2.6')
    s=s.replace('7f1f6b13bae94d7fa8dab0b17bf0dee081868ed0','9788014a0293dc26745b000d02854ad88ef73e88')
    s=re.sub(r'(?m)^(Version:\s*)7\.3\.0$',r'\g<1>7.2.6',s)
    s=re.sub(r'(?m)^Release:.*$', 'Release:        22',s)
    s=re.sub(r'(?m)^ExclusiveArch:.*$','ExclusiveArch:  aarch64',s)
    s=re.sub(r'(?m)^Source[12]:.*\n','',s)
    if name=='kernel-source':
        s=s.replace('%define do_vanilla "%variant" == ""','%define do_vanilla 0')
    elif name=='kernel-syms':
        s=re.sub(r'(?m)^Requires:\s+kernel-(64kb|default|lpae|pae)-devel.*\n','',s)
        s=s.replace('Requires:       kernel-devel', 'Requires:       kernel-freedom-devel = %version-%source_rel\nRequires:       kernel-devel',1)
    else:
        s=s.replace('Name:           kernel-default','Name:           kernel-freedom').replace('%define build_flavor default','%define build_flavor freedom')
        s=s.replace('The Standard Kernel','The TB322FC Freedom Kernel')
        s=s.replace('BuildRequires:  %gcc_package','BuildRequires:  %gcc_package\nBuildRequires:  clang\nBuildRequires:  llvm\nBuildRequires:  lld')
        s=s.replace('%define use_suse_kabi_tools 1','%define use_suse_kabi_tools 0')
        s=s.replace('export KBUILD_BUILD_HOST=buildhost','export KBUILD_BUILD_HOST=buildhost\nexport LLVM=1\nexport PAHOLE_FLAGS=-j1\nexport KBUILD_LDFLAGS=--threads=4\nexport KCFLAGS="${KCFLAGS:-} %{?tb322fc_cflags}"')
        # These SUSE-specific Kconfig settings do not exist in upstream/Freedom.
        s=s.replace('\t--set-str CONFIG_LOCALVERSION -%source_rel-%build_flavor \\\n\t--enable  CONFIG_SUSE_KERNEL \\\n\t$CONFIG_SUSE_KERNEL_RELEASED \\\n\t$CONFIG_SUSE_HAVE_STABLE_KABI','\t--set-str CONFIG_LOCALVERSION -%source_rel-%build_flavor')
        # Restrict DTBs to this tablet; install in a versioned /boot directory.
        s=s.replace('make all $MAKE_ARGS','make Image modules qcom/sm8750-lenovo-elden.dtb $MAKE_ARGS')
        s=s.replace('%files -f kernel-main.files','%files -f kernel-main.files\n/boot/dtb-%kernelrelease-%build_flavor\n%modules_dir/tb322fc-build.json\n%modules_dir/freedom-dpu-rotation',1)
        extra='''
# Tablet boot inputs alongside the distro kernel image and configuration.
cd %kernel_build_dir
install -Dm644 arch/arm64/boot/dts/qcom/sm8750-lenovo-elden.dtb %buildroot/boot/dtb-%kernelrelease-%build_flavor/qcom/sm8750-lenovo-elden.dtb
# Match the Arch package's versioned Gamescope capability check.
printf '%s\\n' 'SM8750 inline rotation: split, allocation and clock fixes (Freedom 0224)' > %buildroot%modules_dir/freedom-dpu-rotation
python3 - <<'METADATA'
import json,re,subprocess
from pathlib import Path
notes=subprocess.check_output(['readelf','-n','vmlinux'],text=True)
info={'release':'%kernelrelease-%build_flavor','build_id':re.search(r'Build ID: ([0-9a-f]+)',notes)[1],'package':'kernel-freedom'}
Path('%buildroot%modules_dir/tb322fc-build.json').write_text(json.dumps(info,indent=2)+'\\n')
METADATA
'''
        s=s.replace('%changelog',extra+'\n%changelog')
    (stage/(name+'.spec')).write_text(s)
tracked=ROOT/'obs/kernel-source';tracked.mkdir(exist_ok=True)
for name in ('kernel-source.spec','kernel-freedom.spec','kernel-syms.spec','_multibuild','_constraints','config.conf','series.conf','kernel-source.changes'):
    shutil.copyfile(stage/name,tracked/name)
shutil.copyfile(up/'source-revision.xml',tracked/'upstream-source-revision.xml')
print(f'Validated {len(rpmify)+len(series)} patches without fuzz',flush=True)
services=SourceFileLoader('kernel_source_services',str(ROOT/'obs/source-services.py')).load_module()
services.download('kernel-source',archive.name,
                  'https://cdn.kernel.org/pub/linux/kernel/v7.x/'+archive.name)
linker=SourceFileLoader('kernel_official_link',str(ROOT/'obs/link-official.py')).load_module()
linker.prepare('kernel-source','kernel-source',publish_result=args.publish)
