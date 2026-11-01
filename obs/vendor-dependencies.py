#!/usr/bin/env python3
"""Fetch pinned Cargo/npm dependencies before entering the offline builder."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile

def cargo(root,manifest):
    vendor=root/'vendor'
    config=subprocess.check_output(['cargo','vendor','--locked','--versioned-dirs','--manifest-path',str(root/manifest),str(vendor)],cwd=root,text=True)
    home=root/'cargo-home'; home.mkdir(exist_ok=True)
    config=config.replace(str(vendor),'@ROOT@/vendor')
    (home/'config.toml.in').write_text(config)

def npm(root,manifests):
    for relative in manifests:
        path=root/relative
        with tempfile.TemporaryDirectory(prefix='tb322fc-npm-') as temp:
            temporary=Path(temp)
            for name in ('package.json','package-lock.json'):
                shutil.copyfile(path/name,temporary/name)
            subprocess.run(['npm','ci','--ignore-scripts','--no-audit','--no-fund','--cpu=arm64','--os=linux','--cache',str(root/'npm-cache')],cwd=temporary,check=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['cargo','npm'])
    parser.add_argument('root',type=Path)
    parser.add_argument('paths',nargs='+')
    args=parser.parse_args()
    if args.mode=='cargo': cargo(args.root,args.paths[0])
    else: npm(args.root,args.paths)
