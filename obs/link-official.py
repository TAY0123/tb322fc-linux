#!/usr/bin/env python3
"""Keep official RPM sources linked; upload only downstream differences."""
import argparse,difflib,hashlib,shutil,xml.etree.ElementTree as ET
from pathlib import Path
from obsapi import ROOT,WORK,publish

def prepare(upstream,target,tracking=False,publish_result=True):
    original=WORK/'upstream'/upstream;changed=WORK/'stage'/target
    revision=ET.parse(original/'source-revision.xml').getroot().attrib['srcmd5']
    d=WORK/'linked'/target
    if d.exists():shutil.rmtree(d)
    d.mkdir(parents=True)
    attrs={'project':'openSUSE:Factory','package':upstream,'baserev':revision}
    if not tracking:attrs['rev']=revision
    link=ET.Element('link',attrs);patches=ET.SubElement(link,'patches')
    diff=[]
    skip={'source-revision.xml','_scmsync.obsinfo','build.specials.obscpio','_servicedata','_link'}
    for path in sorted(changed.iterdir()):
        if not path.is_file() or path.name in skip:continue
        base=original/path.name
        if base.is_file() and path.read_bytes()==base.read_bytes():continue
        if base.is_file() and path.suffix in ('.spec','.changes'):
            diff.extend(difflib.unified_diff(base.read_text().splitlines(keepends=True),path.read_text().splitlines(keepends=True),fromfile=path.name+'.orig',tofile=path.name))
        else:shutil.copyfile(path,d/path.name)
    if diff:
        (d/'project.diff').write_text(''.join(diff))
        ET.SubElement(patches,'apply',name='project.diff')
    for entry in ET.parse(original/'source-revision.xml').getroot().findall('entry'):
        path=original/entry.attrib['name']
        # Keep the upstream service definition unless we supply a replacement.
        if path.name in skip or path.name=='_service':continue
        if not (changed/path.name).exists():ET.SubElement(patches,'delete',name=path.name)
    ET.indent(link,space='  ')
    (d/'_link').write_bytes(ET.tostring(link)+b'\n')
    tracked=ROOT/'obs'/target;tracked.mkdir(exist_ok=True)
    for path in d.iterdir():
        if path.suffix not in ('.xz','.bz2','.gz','.zst','.zip'):
            shutil.copyfile(path,tracked/path.name)
    # The expanded spec is reproducible from project.diff, not another editable
    # copy which could silently become stale against the official package.
    for path in tracked.glob('*.spec'):
        if not (d/path.name).exists():path.unlink()
    # Remove an obsolete downstream service when sources are inherited again.
    if not (d/'_service').exists():
        (tracked/'_service').unlink(missing_ok=True)
    if publish_result:
        publish(target,d)
    return d

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('upstream');p.add_argument('target');p.add_argument('--tracking',action='store_true')
    a=p.parse_args();prepare(a.upstream,a.target,a.tracking)
