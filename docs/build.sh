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
# a page for each app (/ioContact/ and the others), from landing/apps.toml
python3 tools/app-pages.py site
rm site/apps.toml
cat > site/sitemap.xml <<XML
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://iosuite.iothing.net/</loc></url>
  <url><loc>https://iosuite.iothing.net/compose/</loc></url>
$(python3 -c 'import tomllib; d=tomllib.load(open("landing/apps.toml","rb")); print("\n".join("  <url><loc>https://iosuite.iothing.net/%s/</loc></url>" % d[k]["name"] for k in d["order"]))')
$(grep -o '<loc>[^<]*</loc>' site/docs/sitemap.xml | sed 's/^/  <url>/; s/$/<\/url>/')
</urlset>
XML
# --strict cannot see raw HTML; this reads what was built, as a browser would
python3 tools/check-site.py site
