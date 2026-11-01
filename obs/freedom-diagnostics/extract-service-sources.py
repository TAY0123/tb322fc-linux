#!/usr/bin/env python3
"""Recreate the recipe's source layout from OBS-generated upstream archives."""
from pathlib import Path
import hashlib,json,shutil,sys,tarfile,tempfile

def extract(sourcedir,root,manifest):
    sources=root/'sources';sources.mkdir(exist_ok=True)
    for item in manifest['sources']:
        archive=sourcedir/item['file']
        if item.get('sha256') and hashlib.sha256(archive.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Source checksum mismatch: '+item['file'])
        if item['kind']=='file':
            shutil.copyfile(archive,sources/item['dest'])
        elif item['kind']=='git':
            dest=sources/item['dest'];dest.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(dir=root) as tmp:
                with tarfile.open(archive) as tar:tar.extractall(tmp,filter='data')
                top,=Path(tmp).iterdir()
                if dest.exists():shutil.rmtree(dest)
                shutil.move(top,dest)
        else:
            with tarfile.open(archive) as tar:tar.extractall(sources,filter='data')
            if item.get('keep'):shutil.copyfile(archive,sources/item['dest'])
    for src,dst in manifest.get('copies',[]):
        target=sources/dst
        if target.exists():shutil.rmtree(target)
        shutil.copytree(sources/src,target)
    for src,dst in manifest.get('overlays',[]):
        shutil.copytree(sources/src,sources/dst,dirs_exist_ok=True)
    for suffix in manifest.get('remove_suffixes',[]):
        for path in sources.rglob('*'+suffix):
            if path.is_file():path.unlink()

if __name__=='__main__':
    extract(Path(sys.argv[1]),Path.cwd(),json.loads(Path(sys.argv[2]).read_text()))
