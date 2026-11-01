from pathlib import Path
import sys
root=Path(sys.argv[1])
(root/'rpm-overrides.sh').write_text('''build() {
  export DECKY_VERSION="${pkgver/_/-}"
  cd "$srcdir/decky-loader-$DECKY_VERSION/frontend"
  node "$root/pnpm-tool/package/bin/pnpm.cjs" install --offline --frozen-lockfile --ignore-scripts --store-dir "$root/pnpm-store"
  node "$root/pnpm-tool/package/bin/pnpm.cjs" run build
  cd ../backend
  python3 - <<'PY'
from pathlib import Path
import os
p=Path('pyproject.toml');s=p.read_text()
s=s.replace('version = "0.0.0"','version = "'+os.environ['DECKY_VERSION']+'"')
s=s.replace('"decky_loader/static/*"','{ path = "decky_loader/static/**/*", format = ["wheel"] }')
s=s.replace('requires = ["poetry-core>=1.0.0", "poetry-dynamic-versioning>=1.0.0,<2.0.0"]','requires = ["poetry-core>=1.0.0"]')
s=s.replace('build-backend = "poetry_dynamic_versioning.backend"','build-backend = "poetry.core.masonry.api"')
p.write_text(s)
PY
  python3 -m build --wheel --no-isolation
  sed -i 's|${HOMEBREW_FOLDER}|/home/%i/.local/var/opt/decky-loader|' "$srcdir/decky-loader@.service"
  sed -i "/^ExecStart=/i ExecStartPre=/usr/bin/decky-loader-helper v$DECKY_VERSION %i" "$srcdir/decky-loader@.service"
}
package() {
  python3 -m installer --destdir="$pkgdir" "$srcdir"/decky-loader-${pkgver/_/-}/backend/dist/*.whl
  install -Dm644 "$srcdir/decky-loader@.service" "$pkgdir/usr/lib/systemd/system/decky-loader@.service"
  install -Dm755 "$srcdir/decky-loader-helper" "$pkgdir/usr/bin/decky-loader-helper"
}
''')
