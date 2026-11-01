from pathlib import Path
import shutil,sys
root=Path(sys.argv[1])
source=Path(__file__).with_name('tb322fc-update-rpm.py')
shutil.copyfile(source,root/'sources/tb322fc-update-v2.py')
p=root/'sources/tb322fc-update'
p.write_text(p.read_text().replace('/usr/bin/python ','/usr/bin/python3 '))
