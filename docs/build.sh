#!/usr/bin/env sh
# Builds the whole site into site/: the landing page at the root, the guide
# under /docs/. First the guide's claims about the apps (links into their
# repositories, ports, container sizes, images) are checked against the apps'
# code, and the stack files the Docker Compose builder writes are checked; last, every local link and image in the built site must resolve.
#
#   sh build.sh
#
# Deploy with: npx wrangler deploy        (wrangler.jsonc serves site/)
set -e
cd "$(dirname "$0")"
python3 tools/check-facts.py
# the Docker Compose builder (/compose/): the files its code writes, for the choices it offers
node tools/check-compose.js
rm -rf site docs/img
# the guide shows the landing page's screenshots and icons
mkdir -p docs/img && cp landing/img/* docs/img/
mkdocs build --strict
cp -R landing/. site/
# the wall display's flasher (/wall/): the firmware from the release wall-latest (.github/workflows/tab5-wall.yml),
# served from here because a browser writes over USB only what its own site serves. One for each board, and for
# each chip revision that needs its own; one not published (yet): no button for it.
WALL=https://github.com/avandeputte/iosuite/releases/download/wall-latest
v="$(curl -fsSL "$WALL/version.txt" || true)"
for fw in iowall iowall-waveshare7b iowall-waveshare7b-rev3; do
  case "$fw" in
    iowall) manifest=manifest.json; name="ioThing wall for the M5Stack Tab5" ;;
    *) manifest="manifest${fw#iowall}.json"; name="ioThing wall for the Waveshare ESP32-P4-WIFI6-Touch-LCD-7B" ;;
  esac
  if [ -n "$v" ] && curl -fsSL -o "site/wall/$fw-full.bin" "$WALL/$fw-full.bin"; then
    cat > "site/wall/$manifest" <<JSON
{"name": "$name", "version": "$v", "new_install_prompt_erase": false,
 "builds": [{"chipFamily": "ESP32-P4", "parts": [{"path": "$fw-full.bin", "offset": 0}]}]}
JSON
  else
    rm -f "site/wall/$fw-full.bin"
    python3 - site/wall/index.html "$fw" <<'PY'
import re, sys
p, fw = sys.argv[1:]
s = open(p).read()
s, n = re.subn(r'\s*<div class="wflash" data-fw="%s">.*?</div>' % re.escape(fw), "", s, flags=re.S)
assert n == 1, fw
open(p, "w").write(s)
PY
  fi
done
# a page for each app (/ioContact/ and the others), from landing/apps.toml and the apps' manifests
python3 tools/app-pages.py site
rm site/apps.toml
cat > site/sitemap.xml <<XML
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://iosuite.iothing.net/</loc></url>
  <url><loc>https://iosuite.iothing.net/compose/</loc></url>
  <url><loc>https://iosuite.iothing.net/wall/</loc></url>
$(python3 -c 'import json; d=json.load(open("../shared/iosuite_shared/apps.json")); print("\n".join("  <url><loc>https://iosuite.iothing.net/%s/</loc></url>" % m["name"] for m in d["apps"] if not m.get("adminTool")))')
$(grep -o '<loc>[^<]*</loc>' site/docs/sitemap.xml | sed 's/^/  <url>/; s/$/<\/url>/')
</urlset>
XML
# --strict cannot see raw HTML; this reads what was built, as a browser would
python3 tools/check-site.py site
