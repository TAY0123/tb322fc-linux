from pathlib import Path
import sys
root=Path(sys.argv[1])
recipe=root/'local/PKGBUILD'
text=recipe.read_text()
text=text.replace('install DESTDIR="$pkgdir" PREFIX=/usr','install DESTDIR="$pkgdir" PREFIX=/usr LIBDIR=/usr/lib64')
recipe.write_text(text)
# The source Makefile and layer manifest determine the final location; keep
# the manifest consistent even if its Makefile does not honour LIBDIR.
(root/'rpm-overrides.sh').write_text('''eval "$(declare -f package | sed '1s/package/package_shared/')"
package() {
  package_shared
  if [[ -f "$pkgdir/usr/lib/libkettle_framegen.so" ]]; then
    install -d "$pkgdir/usr/lib64"
    mv "$pkgdir/usr/lib/libkettle_framegen.so" "$pkgdir/usr/lib64/"
  fi
  find "$pkgdir/usr/share/vulkan" -name '*.json' -exec sed -i 's|/usr/lib/|/usr/lib64/|g' {} +
}
''')
