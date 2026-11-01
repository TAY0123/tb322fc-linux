#!/usr/bin/env python3
"""Replace uploaded upstream archives with pinned server-side downloads."""
from pathlib import Path
import hashlib,re,shutil,sys,xml.etree.ElementTree as ET
from obsapi import ROOT,WORK,publish

def download(package,filename,url,sha256=None):
    d=WORK/'stage'/package;archive=d/filename
    digest=sha256 or hashlib.sha256(archive.read_bytes()).hexdigest()
    path=d/'_service'
    services=ET.parse(path).getroot() if path.exists() else ET.Element('services')
    for old in list(services):
        if old.findtext("param[@name='filename']")==filename:services.remove(old)
    service=ET.SubElement(services,'service',name='download_url',mode='serveronly')
    for key,value in (('url',url),('filename',filename)):
        ET.SubElement(service,'param',name=key).text=value
    ET.indent(services,space='  ');path.write_bytes(ET.tostring(services,encoding='utf-8',xml_declaration=True)+b'\n')
    found=False
    for spec in d.glob('*.spec'):
        s=spec.read_text()
        # Expand only the common source-version macros for matching. Preserve
        # all other upstream spec contents and package split logic.
        variables=dict(re.findall(r'(?m)^%(?:define|global)\s+(\w+)\s+(\S+)',s))
        for field in ('Name','Version'):
            match=re.search(r'(?m)^'+field+r':\s+(\S+)',s)
            if match:variables[field.lower()]=match[1]
        def expand(value):
            for _ in range(4):
                for key,val in variables.items():
                    value=value.replace('%{'+key+'}',val)
                    value=re.sub('%'+re.escape(key)+r'\b',lambda _:val,value)
            return value
        sourceids=[]
        def replace(match):
            nonlocal found
            key,val=match.group(1),match.group(2)
            if expand(val).rsplit('/',1)[-1].removeprefix('_service:download_url:')==filename:
                found=True;sourceids.append(key.removeprefix('Source') or '0')
                # OBS strips the service prefix when staging build sources.
                return key+':        '+filename
            return match[0]
        s=re.sub(r'(?m)^(Source\d*):\s+(\S+)$',replace,s)
        for number in sourceids:
            marker=f'# Verify upstream {filename}'
            if marker not in s:
                s=s.replace('%prep\n',f"%prep\n{marker}\nprintf '%s  %s\\n' '{digest}' '%{{SOURCE{number}}}' | sha256sum -c\n",1)
        spec.write_text(s)
    if not found:raise ValueError('No Source tag for '+filename)
    if archive.exists():archive.unlink()
    tracked=ROOT/'obs'/package;tracked.mkdir(exist_ok=True)
    for f in [path,*d.glob('*.spec')]:shutil.copyfile(f,tracked/f.name)
    return d

if __name__=='__main__':
    package,filename,url=sys.argv[1:4]
    publish(package,download(package,filename,url))
