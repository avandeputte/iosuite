#!/usr/bin/env sh
# Builds the whole site into site/: the landing page at the root, the guide
# under /docs/. First the guide's claims about the apps (links into their
# repositories, ports, container sizes, images) are checked against the apps'
# code; last, every local link and image in the built site must resolve.
#
#   sh build.sh               # checks against fresh clones of the apps' main
#   sh build.sh ../src        # or against checkouts in ../src/<repo>
#
# Deploy with: npx wrangler pages deploy site --project-name iosuite
set -e
cd "$(dirname "$0")"
python3 tools/check-facts.py "$@"
rm -rf site docs/img
# the guide shows the landing page's screenshots and icons
mkdir -p docs/img && cp landing/img/* docs/img/
mkdocs build --strict
cp -R landing/. site/
cat > site/sitemap.xml <<XML
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://iosuite.iothing.net/</loc></url>
$(grep -o '<loc>[^<]*</loc>' site/docs/sitemap.xml | sed 's/^/  <url>/; s/$/<\/url>/')
</urlset>
XML
# --strict cannot see raw HTML; this reads what was built, as a browser would
python3 tools/check-site.py site
