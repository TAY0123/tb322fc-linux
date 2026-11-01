#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""List the installed payload without claiming shared distro directories."""
from pathlib import Path
import sys
import shutil
import subprocess
root=Path(sys.argv[1])
shared={'/usr','/usr/bin','/usr/sbin','/usr/lib','/usr/lib64','/usr/libexec','/usr/src','/usr/share','/usr/share/doc','/usr/share/licenses','/usr/include','/etc','/var','/var/lib'}
for path in sorted(root.rglob('*')):
    name='/' + path.relative_to(root).as_posix()
    if path.is_dir() and not path.is_symlink():
        # SUSE filesystem owns additional standard directories (some are
        # symlinks after usrmerge). Never replace their attributes/type.
        if shutil.which('rpm'):
            owner=subprocess.run(['rpm','-qf','--qf','%{NAME}\n','--',name],capture_output=True,text=True)
            if owner.returncode==0 and 'filesystem' in owner.stdout.splitlines():
                continue
        if name not in shared:
            print('%dir "'+name.replace('%','%%')+'"')
        continue
    prefix='%config(noreplace) ' if name.startswith('/etc/') else ''
    if name.startswith('/usr/share/man/'):
        if any(c.isspace() for c in name):
            raise ValueError('Unexpected whitespace in manual page path: '+name)
        print(prefix+name.replace('%','%%')+'*')
        continue
    print(prefix+'"'+name.replace('%','%%').replace('"','\\"')+'"')
