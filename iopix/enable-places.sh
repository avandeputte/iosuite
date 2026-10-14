#!/bin/sh
# Turn on place names (town, region, country for every geotagged photo; the Places page;
# place tags). Downloads the GeoNames cities1000 gazetteer (geonames.org, CC BY 4.0; about
# 10 MB download, 30 MB in data/geonames). Lookups are offline afterwards. Nothing is installed.
# Restart the viewer when it finishes.
set -e
cd "$(dirname "$0")"
exec .venv/bin/python -m app.models download geonames
