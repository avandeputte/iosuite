#!/bin/sh
# Builds dist/digikam-viewer-install.sh: a single self-extracting installer for Linux
# (the install script followed by a tarball of the application). Run it on the
# target machine with sh; see installer/install.sh for options.
#
#   ./installer/make-installer.sh            -> dist/digikam-viewer-install.sh
#
# The archive carries the code, static files, pyproject.toml and README; no models
# (they are downloaded at install time) and nothing from data/ or .venv/.
set -e
cd "$(dirname "$0")/.."
VERSION="${VERSION:-$(date +%Y.%m.%d)}"
mkdir -p dist
OUT="dist/digikam-viewer-install.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/digikam-viewer"
cp -R app static pyproject.toml README.md setup.sh run.sh update.sh "$TMP/digikam-viewer/"
git rev-parse HEAD > "$TMP/digikam-viewer/COMMIT" 2>/dev/null || echo unknown > "$TMP/digikam-viewer/COMMIT"
find "$TMP/digikam-viewer" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$TMP/digikam-viewer" -name '.DS_Store' -delete 2>/dev/null || true
cp installer/digikam-viewer.service "$TMP/digikam-viewer/digikam-viewer.service"
printf '%s\n' "$VERSION" > "$TMP/digikam-viewer/VERSION"
(cd "$TMP" && tar czf payload.tgz digikam-viewer)
{
  sed "s/@VERSION@/$VERSION/" installer/install.sh
  printf '\n__PAYLOAD_BELOW__\n'
  cat "$TMP/payload.tgz"
} > "$OUT"
chmod 755 "$OUT"
echo "built $OUT ($(du -h "$OUT" | cut -f1), version $VERSION)"
