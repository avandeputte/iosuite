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
# the Tab5 wall's flasher (/wall/): the firmware from the release wall-latest (.github/workflows/tab5-wall.yml),
# served from here because a browser writes over USB only what its own site serves. None published yet: no button.
WALL=https://github.com/avandeputte/iosuite/releases/download/wall-latest
if curl -fsSL -o site/wall/iowall-full.bin "$WALL/iowall-full.bin" && v="$(curl -fsSL "$WALL/version.txt")"; then
  cat > site/wall/manifest.json <<JSON
{"name": "ioThing wall for the M5Stack Tab5", "version": "$v", "new_install_prompt_erase": false,
 "builds": [{"chipFamily": "ESP32-P4", "parts": [{"path": "iowall-full.bin", "offset": 0}]}]}
JSON
else
  rm -f site/wall/iowall-full.bin
  python3 - site/wall/index.html <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
s = re.sub(r'\s*<a class="btn btn-ghost" href="iowall-full.bin" download>.*?</a>', "", s)
open(p, "w").write(s)
PY
fi
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
