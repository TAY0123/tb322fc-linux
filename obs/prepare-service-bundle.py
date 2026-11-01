#!/usr/bin/env python3
"""Split the initial build bundle into own files and service-fetched sources."""
from pathlib import Path
import argparse,configparser,hashlib,importlib.machinery,json,re,shutil,subprocess,tarfile,urllib.parse,xml.etree.ElementTree as ET
from obsapi import ROOT,WORK,publish
simple=importlib.machinery.SourceFileLoader('simple',str(ROOT/'obs/prepare-simple.py')).load_module()

def prepare(name):
    bundle=WORK/'bundles'/name
    if name=='kshim-freedom':
        import sys
        subprocess.run([sys.executable,str(ROOT/'obs/kshim-freedom/adapt.py'),str(bundle)],check=True)
    metadata=simple.metadata(ROOT/'packages'/name/'PKGBUILD')
    version=metadata['pkgver'][0].replace('_','~')
    d=WORK/'serviced'/name
    if d.exists():shutil.rmtree(d)
    d.mkdir(parents=True)
    services=ET.Element('services');manifest={'sources':[]};exclude=set();number=10
    declarations=[]; prep_extra=''
    def service(name,params):
        element=ET.SubElement(services,'service',name=name,mode='serveronly')
        for key,value in params:ET.SubElement(element,'param',name=key).text=value
        return element
    def add(remote,alias,kind=None,dest=None,cache=None):
        nonlocal number
        parsed=urllib.parse.urlsplit(remote.removeprefix('git+'))
        if remote.startswith('git+'):
            ref=(urllib.parse.parse_qs(parsed.fragment).get('commit') or urllib.parse.parse_qs(parsed.fragment).get('tag'))[0]
            repo=parsed.path.rstrip('/').removesuffix('.git')
            cache=WORK/'cache'/(repo.split('/')[-1]+'-'+ref.replace('/','_')+'.tar.gz')
            if parsed.netloc=='github.com':url='https://codeload.github.com'+repo+'/tar.gz/'+ref
            elif parsed.netloc=='codeberg.org':url='https://codeberg.org'+repo+'/archive/'+ref+'.tar.gz';cache=WORK/'cache'/('service-'+cache.name)
            else:url=parsed.scheme+'://'+parsed.netloc+repo+'/-/archive/'+ref+'/'+repo.split('/')[-1]+'-'+ref+'.tar.gz';cache=WORK/'cache'/('service-'+cache.name)
            simple.fetch(url,cache)
            filename=cache.name.removeprefix('service-');kind='git';dest=dest or alias;exclude.add('sources/'+dest)
        else:
            url=remote;cache=cache or WORK/'cache'/alias
            if not cache.exists():simple.fetch(url,cache)
            filename=alias
            if kind is None:kind='archive' if tarfile.is_tarfile(cache) else 'file'
            dest=dest or alias
            exclude.add('sources/'+alias)
            if kind=='archive':
                with tarfile.open(cache) as tar:exclude.update('sources/'+x.name.split('/')[0] for x in tar.getmembers() if x.name)
        item={'file':filename,'kind':kind,'dest':dest,'sha256':hashlib.sha256(cache.read_bytes()).hexdigest()}
        if filename=='CrDK-b6c3335.tar.gz':item['keep']=True
        manifest['sources'].append(item)
        declarations.append(f'Source{number}:        {filename}');number+=1
        if filename.endswith('.patch'):
            # Patches stay independently editable in OBS.
            shutil.copyfile(cache,d/filename);item.pop('sha256')
        else:
            service=ET.SubElement(services,'service',name='download_url',mode='serveronly')
            for key,value in [('url',url),('filename',filename)]:ET.SubElement(service,'param',name=key).text=value
    for source in metadata['source']:
        alias,sep,remote=source.partition('::')
        if not sep:remote=source;alias=urllib.parse.urlsplit(remote.removeprefix('git+')).path.rsplit('/',1)[-1].removesuffix('.git') if remote.startswith('git+') else remote.rsplit('/',1)[-1]
        if '/llvm-mingw/releases/download/' in remote:continue
        if remote.startswith('git+') and 'mydanyi/armadaos-freedom' in remote:
            revision=remote.split('#commit=')[1]
            assert revision=='244b74516d99d06cb0518609ce4b842ab278be8a'
            exclude.add('sources/'+alias)
            for label,subdir in [('runtime','devices/lenovo-tb323fu/boot/kshim-success-source'),('tools','packages/kshim-tools/vendor')]:
                filename=f'freedom-{label}-{revision}.tar'
                service('tar_scm',[('url','https://github.com/mydanyi/armadaos-freedom.git'),('scm','git'),('revision',revision),('subdir',subdir),('filename','freedom-'+label),('version',revision),('submodules','disable')])
                manifest['sources'].append({'file':filename,'kind':'git','dest':alias+'/'+subdir})
                declarations.append(f'Source{number}:        {filename}');number+=1
            continue
        if remote.startswith(('https://','http://','git+')):add(remote,alias)
    if name=='gamescope-armada':
        manifest['copies']=[(Path(p).name,'gamescope/'+p) for p in ('src/reshade','subprojects/libdisplay-info','subprojects/libliftoff','subprojects/openvr','subprojects/vkroots','subprojects/wlroots','thirdparty/SPIRV-Headers')]
        manifest['overlays']=[]
        for lib in ('glm','stb'):
            c=configparser.ConfigParser();c.read(bundle/'sources/gamescope/subprojects'/(lib+'.wrap'))
            v=c['wrap-git'];dest='gamescope/subprojects/'+lib
            add('git+'+v['url']+'#commit='+v['revision'],lib,dest=dest)
            manifest['overlays'].append(('gamescope/subprojects/packagefiles/'+lib,dest))
    if name=='optiscaler-arm64ec-armada':
        manifest['copies']=[(lib,'Sloptiscaler/external/'+lib) for lib in ('simpleini','unordered_dense','xess','vulkan','spdlog','magic_enum','nvapi')]
        manifest['remove_suffixes']=['.dll','.exe','.lib','.pdb']
    for script in ('file-list.py','recipe-stage.sh'):
        shutil.copyfile(ROOT/'obs'/script,bundle/script)
    archive=f'{name}-{version}-local.tar.xz'
    npm_roots={
        'y700-charge':['local/decky'],
        'decky-render-tools':['sources'],
        'armada-decky-plugins':['local/armada-store','sources/freedom-control/decky/armada-control'],
    }
    if name in npm_roots or name=='decky-loader':
        if name=='decky-loader':
            # This is only a fetch manifest. pnpm still resolves the unchanged
            # upstream pnpm-lock.yaml, with --offline --frozen-lockfile.
            yaml_python=WORK/'tools-venv/bin/python'
            lock=bundle/'sources'/f'decky-loader-{version}'/'frontend/pnpm-lock.yaml'
            data=json.loads(subprocess.check_output([str(yaml_python),'-c','import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))',str(lock)]))
            packages={}
            for key,entry in data['packages'].items():
                module,v=key.rsplit('@',1);resolution=entry['resolution']
                assert 'integrity' in resolution,key
                url=resolution.get('tarball') or f'https://registry.npmjs.org/{module}/-/{module.rsplit("/",1)[-1]}-{v}.tgz'
                packages[f'cache/{len(packages)}/node_modules/{module}']={'version':v,'resolved':url,'integrity':resolution['integrity']}
            locks={'name':'decky-frontend-lock-downloads','lockfileVersion':3,'packages':packages}
        else:
            locks={path:json.loads((bundle/path/'package-lock.json').read_text()) for path in npm_roots[name]}
        (d/'npm-dependencies.json').write_text(json.dumps(locks,indent=2)+'\n')
        declarations.extend(['Source4:        npm-dependencies.json','%include %{_sourcedir}/node_modules.spec.inc'])
        service('node_modules',[('input','npm-dependencies.json'),('cpio','node_modules.obscpio'),('output','node_modules.spec.inc'),('legacy-container','true'),('source-offset','10000')])
        exclude.add('npm-cache')
        # OBS expands .obscpio into the source directory before %prep.
        # Seed npm's content-addressed cache from the verified local tarballs.
        prep_extra='mkdir -p npm-cache\nfind %{_sourcedir} -maxdepth 1 -name "*.tgz" -print0 | xargs -0 -r npm cache add --offline --ignore-scripts --cache "$PWD/npm-cache"\n'
        if name=='decky-loader':
            exclude.update(('pnpm-tool','pnpm-store'))
            service('download_url',[('url','https://registry.npmjs.org/pnpm/-/pnpm-10.11.0.tgz'),('filename','pnpm-10.11.0.tgz')])
            declarations.extend(['Source5:        pnpm-10.11.0.tgz','Source6:        seed-pnpm-store.py'])
            shutil.copyfile(ROOT/'obs/seed-pnpm-store.py',d/'seed-pnpm-store.py')
            prep_extra="printf '%s  %s\\n' 'a69e9cb077da419d47d18f1dd52e207245b29cac6e076acedbeb8be3b1a67bd7' '%{SOURCE5}' | sha256sum -c\nmkdir -p pnpm-tool\ntar -xf %{SOURCE5} -C pnpm-tool\npython3 %{SOURCE6} %{_sourcedir}\n"
    if name in ('armada-rgb','steamos-manager'):
        exclude.update(('vendor','cargo-home'))
        if name=='armada-rgb':
            params=[('src',archive),('custom-root','local')]
            dest='local'
        else:
            source=next(s for s in manifest['sources'] if s['dest']=='steamos-manager')
            params=[('src','*'+source['file'])]
            dest='sources/steamos-manager'
        # build.opensuse.org does not install cargo_vendor on source workers
        # (verified service error). Keep the official manual service workflow;
        # upload its locked dependency output separately from project sources.
        cargo_service=service('cargo_vendor',params+[('update','false'),('respect-lockfile','true'),('compression','zst')])
        cargo_service.set('mode','manual')
        rootdir=bundle/dest
        vendor_tar=d/'vendor.tar'
        with tarfile.open(vendor_tar,'w') as tar:
            prefix='local/' if name=='armada-rgb' else ''
            tar.add(bundle/'vendor',arcname=prefix+'vendor')
            tar.add(rootdir/'Cargo.lock',arcname=prefix+'Cargo.lock')
            config=(bundle/'cargo-home/config.toml.in').read_text().replace('@ROOT@/vendor','vendor')
            import io
            data=config.encode();info=tarfile.TarInfo(prefix+'.cargo/config');info.size=len(data);info.mode=0o644
            tar.addfile(info,io.BytesIO(data))
        subprocess.run(['zstd','-q','-T0',str(vendor_tar),'-o',str(d/'vendor.tar.zst')],check=True)
        vendor_tar.unlink()
        declarations.append('Source3:        vendor.tar.zst')
        if name=='armada-rgb':
            prep_extra='tar -xf %{SOURCE3}\n'
        else:
            prep_extra=f'tar -xf %{{SOURCE3}} -C {dest}\n'
        # The service writes a project-local .cargo/config pointing at vendor/.
        # Keep Cargo.lock pinned and let Cargo find this configuration itself.
    def keep(info):
        rel='/'.join(info.name.split('/')[1:])
        return None if any(rel==p or rel.startswith(p+'/') for p in exclude) else info
    with tarfile.open(d/archive,'w:xz',preset=1) as tar:tar.add(bundle,arcname=f'{name}-{version}',filter=keep)
    (d/'service-sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    shutil.copyfile(ROOT/'obs/extract-service-sources.py',d/'extract-service-sources.py')
    ET.indent(services,space='  ');(d/'_service').write_bytes(ET.tostring(services)+b'\n')
    spec=(WORK/'stage'/name/(name+'.spec')).read_text()
    if name in ('armada-rgb','steamos-manager'):
        for section in ('%build','%check'):
            export=section+'\nexport RUSTFLAGS="${RUSTFLAGS:-} %{?tb322fc_rustflags}"\n'
            if export not in spec:
                spec=spec.replace(section+'\n',export,1)
    for dependency in simple.BUILD.get(name,[]):
        if not re.search(r'(?m)^BuildRequires:\s+'+re.escape(dependency)+r'$',spec):
            spec=spec.replace('\n%description\n','\nBuildRequires:  '+dependency+'\n\n%description\n',1)
    spec=re.sub(r'(?m)^Source0:.*$', 'Source0:        '+archive+'\nSource1:        service-sources.json\nSource2:        extract-service-sources.py\n'+'\n'.join(declarations),spec)
    spec=spec.replace('%setup -q\n','%setup -q -n '+name+'-'+version+'\npython3 %{SOURCE2} %{_sourcedir} %{SOURCE1}\n'+prep_extra,1)
    if name=='kshim-freedom':
        shutil.copyfile(ROOT/'obs'/name/'rpm-boot-update.py',d/'rpm-boot-update.py')
        spec=spec.replace('Source2:        extract-service-sources.py\n',
                          'Source2:        extract-service-sources.py\nSource3:        rpm-boot-update.py\n',1)
        if not re.search(r'(?m)^Requires:\s+coreutils$',spec):
            spec=spec.replace('\n%description\n','\nRequires:       coreutils\n\n%description\n',1)
        spec=spec.replace('bash recipe-stage.sh install %{buildroot}\n',
                          'bash recipe-stage.sh install %{buildroot}\n'
                          'install -Dm644 %{SOURCE3} %{buildroot}%{_prefix}/lib/kshim-freedom/rpm-boot-update.py\n',1)
        spec=spec.replace('\n%files -f files.list\n',
                          '\n%transfiletriggerin -P 1000 -- /boot /usr/lib/modules /usr/lib/kshim-freedom /usr/libexec/plymouth /usr/lib64/plymouth /usr/share/plymouth /etc/plymouth /usr/share/pixmaps/distribution-logos\n'
                          '/usr/bin/python3 %{_prefix}/lib/kshim-freedom/rpm-boot-update.py\n'
                          '\n%files -f files.list\n',1)
    if name=='directx-shader-compiler-render':
        # DXC's old LLVM needs the lifetime-DSE workaround used by LLVM 18.
        # Keep the upstream source service and publish this patch separately.
        for filename in ('0001-preserve-llvm-object-storage-lifetime.patch','check-shaders.py'):
            shutil.copyfile(ROOT/'obs'/name/filename,d/filename)
        spec=spec.replace('Source2:        extract-service-sources.py\n',
                          'Source2:        extract-service-sources.py\n'
                          'Source3:        check-shaders.py\n'
                          'Patch0:         0001-preserve-llvm-object-storage-lifetime.patch\n',1)
        spec=spec.replace('bash recipe-stage.sh prepare\n',
                          '%patch -P 0 -p1 -d sources/DirectXShaderCompiler-01b62ad47db7dee3dd33f90e7339cf9e860b3f93\n'
                          'bash recipe-stage.sh prepare\n',1)
        spec=spec.replace('bash recipe-stage.sh check\n',
                          'bash recipe-stage.sh check\npython3 %{SOURCE3} sources/build/bin/dxc\n',1)
    if name=='gamescope-session-steam':
        patch='0001-use-packaged-python-interpreter.patch'
        shutil.copyfile(ROOT/'obs'/name/patch,d/patch)
        spec=spec.replace('Source2:        extract-service-sources.py\n',
                          'Source2:        extract-service-sources.py\nPatch0:         '+patch+'\n',1)
        spec=spec.replace('bash recipe-stage.sh prepare\n',
                          '%patch -P 0 -p1 -d sources/gamescope-session-steam\nbash recipe-stage.sh prepare\n',1)
    (d/(name+'.spec')).write_text(spec)
    for path in (WORK/'stage'/name).glob('*.changes'):shutil.copyfile(path,d/path.name)
    tracked=ROOT/'obs'/name
    for path in d.iterdir():
        if path.name!=archive and not path.name.endswith(('.tar.zst','.tar.xz')):shutil.copyfile(path,tracked/path.name)
    publish(name,d)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('packages',nargs='+')
    for name in p.parse_args().packages:prepare(name)
