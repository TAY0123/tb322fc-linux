from pathlib import Path
import sys
root=Path(sys.argv[1]); recipe=root/'local/PKGBUILD'
recipe.write_text(recipe.read_text().replace('"$pkgdir/usr/lib"','"$pkgdir/usr/lib64"'))
