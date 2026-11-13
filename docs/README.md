# iosuite.iothing.net

The website of the suite, in `docs/` of the suite's repository. The source of [iosuite.iothing.net](https://iosuite.iothing.net): the landing page for the ioThing suite
([ioPix](https://github.com/avandeputte/iosuite/tree/main/iopix), [ioNote](https://github.com/avandeputte/iosuite/tree/main/ionote),
[ioCalendar](https://github.com/avandeputte/iosuite/tree/main/iocalendar), [ioTask](https://github.com/avandeputte/iosuite/tree/main/iotask), [ioRecipe](https://github.com/avandeputte/iosuite/tree/main/iorecipe), [ioContact](https://github.com/avandeputte/iosuite/tree/main/iocontact),
[ioHealth](https://github.com/avandeputte/iosuite/tree/main/iohealth) and the [ioStart](https://github.com/avandeputte/iosuite/tree/main/iostart) start
page), and its guide under [/docs/](https://iosuite.iothing.net/docs/).

The message of the site: **every app installs and runs on its own**. Someone who only wants a photo app installs ioPix
and is done; the other apps, and the start page, are optional and can come later. Keep it that way when adding pages.

```
landing/            the landing page, served at /  (index.html, 404.html, robots.txt, _headers)
landing/img/        the app icons (each app's static/icons/mark.svg) and the screenshots
docs/               the guide (MkDocs Material), served at /docs/
docs/stylesheets/   the Material theme in the landing page's palette
overrides/          the header brand
tools/check-facts.py  holds the pages to the apps' code (links, ports, container sizes, images)
tools/check-site.py   every local link and image in the built site resolves
mkdocs.yml          site settings and the nav
build.sh            check, build into site/, lay the landing page over it, write the sitemap
CLOUDFLARE.md       hosting on Cloudflare Workers: the Worker, the domain, the deploy token
wrangler.jsonc      the Worker: serves site/ as static assets at iosuite.iothing.net
```

## Writing

Edit the markdown in `docs/`, add a page to the `nav` in `mkdocs.yml`, push. The guide is the suite-level view: what
every app shares, how to install one or several, how to run them. What belongs to one app in depth stays in that app's
README (and, for ioPix, at [iopix.net](https://iopix.net/docs/)); link there rather than copy it.

Screenshots live in `landing/img/` (the guide gets a copy at build time), 1600 × 1000 JPEGs, under 400 KB each. They
are the real apps holding made-up data (the Parker family); the ioPix ones are from
[iopix/docs/screenshots](https://github.com/avandeputte/iosuite/tree/main/iopix/docs/screenshots), whose photo credits the
landing page links to.

## Building

```bash
pip install -r requirements.txt
sh build.sh                          # checks the pages against the apps' folders beside docs/
python3 -m http.server -d site 8000  # http://localhost:8000/ and /docs/
```

`mkdocs build --strict` fails on a page the nav names that does not exist, or a link that resolves nowhere.
`tools/check-facts.py` fails when a page has drifted from the apps: a link to a file an app no longer has, a default
port, a Proxmox container size or a Docker image that is not what the app's code says. Both on purpose.

## Deploying

The site is a Cloudflare Worker (`iosuite`, in `wrangler.jsonc`) that serves `site/` as static assets, on the custom
domain `iosuite.iothing.net`. The workflow
(`.github/workflows/docs.yml` at the root) builds every pull request that touches the site or an app, and deploys on
every push to `main` that does, and on demand, with
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` from the repository secrets. By hand:

```bash
sh build.sh && npx wrangler deploy
```

The one-time setup in Cloudflare is in [CLOUDFLARE.md](CLOUDFLARE.md).

## License

GPL-3.0-or-later, like the apps.
