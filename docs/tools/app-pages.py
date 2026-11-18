#!/usr/bin/env python3
"""Writes a page for each app, site/<name>/index.html (https://iosuite.iothing.net/ioContact/ and the others), from
landing/apps.toml (what the page says) and the app's manifest (<app>/app.json, gathered in
shared/iosuite_shared/apps.json: its name, colour, port, one-line tag, and where it comes in the list). build.sh runs it after copying landing/ into site/; the pages use landing/site.css and
landing/app.js like the home page. Usage: python3 tools/app-pages.py site
"""
import html
import json
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RAW = "https://raw.githubusercontent.com/avandeputte/iosuite/main/"
REPO = "https://github.com/avandeputte/iosuite"
SITE = "https://iosuite.iothing.net"
GITHUB_SVG = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 '
              '0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 '
              '1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02'
              '.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56'
              '.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 '
              '16 8c0-4.42-3.58-8-8-8Z"/></svg>')
# every app with a page (the admin tools have none): its manifest, in order
MANIFESTS = [m for m in json.loads((HERE.parent / "shared" / "iosuite_shared" / "apps.json").read_text())["apps"] if not m.get("adminTool")]
SHORT = {m["key"]: (m.get("compose") or {}).get("what") or m["description"].lower() for m in MANIFESTS}


def e(s):
    return html.escape(str(s), quote=True)


def shot(img, alt, cls="shot"):
    return (f'<button class="{cls}" data-full="/img/{e(img)}" data-cap="{e(alt)}">'
            f'<img src="/img/{e(img)}" loading="lazy" alt="{e(alt)}" width="1600" height="1000"></button>')


def term(head, lines):
    body = "\n".join(f'<span class="c">{e(x)}</span>' if x.startswith("#") else f'<span class="p">$ </span>{e(x)}' for x in lines)
    return (f'<div class="term"><div class="term-head"><span>{e(head)}</span><button class="copy" data-copy>copy</button></div>'
            f'<pre><code>{body}</code></pre></div>')


def install(key, a):
    first = "" if key == "iostart" else f" -s -- --first {key}"
    ways = [
        ("oneline", "One line, any Linux server", term(f"any linux server — {a['name']}", [f"curl -fsSL {RAW}install.sh | bash{first}"]),
         "The suite's installer asks the app's questions (the database, the port, an admin) and installs it as a service. "
         "<strong>Run the same line again</strong> to add another app, remove one or change its settings."),
        ("proxmox", "Proxmox VE (LXC)", term("proxmox ve host, as root", [f'bash -c "$(curl -fsSL {RAW}{key}/proxmox/ct/{key}.sh)"']),
         "One container for the app. It asks for the databases and the admin, then for the container's resources; its "
         "“Also install” checklist can put other apps in the same container."),
        ("docker", "Docker", term(f"docker compose — {a['name']}", [f"mkdir {key} && cd {key}", f"curl -fsSLO {RAW}{key}/docker-compose.yml",
                                                                    "# fill in the CHANGE ME values, then", "docker compose up -d"]),
         f"The image is <code>ghcr.io/avandeputte/iosuite/{key}</code>, for amd64 and arm64; it holds no data of its own."),
        ("linux", "Any Linux or Mac", term("any linux or mac", [f"git clone {REPO} && cd iosuite/{key}", "./setup.sh"]),
         "<code>setup.sh</code> asks for the databases, the port and an admin, and installs a service (systemd, or launchd on a Mac)."),
    ]
    tabs = "".join(f'<button role="tab" aria-selected="{"true" if i == 0 else "false"}" data-way="{w}">{e(t)}</button>' for i, (w, t, _, _) in enumerate(ways))
    panes = "".join(f'<div class="way" data-way="{w}"{"" if i == 0 else " hidden"}>{cmd}<p class="pick-note">{note}</p></div>'
                    for i, (w, _, cmd, note) in enumerate(ways))
    return f'<div class="tabs" role="tablist" aria-label="Where to install">{tabs}</div>{panes}'


def page(key, a, apps, order):
    name, c = a["name"], a["color"]
    docs = f"/docs/apps/{key}/"
    title = f"{name} — {a['tag']} · ioThing suite"
    desc = html.unescape(a["lede"].replace("<strong>", "").replace("</strong>", ""))
    links = "".join(f'<a class="btn btn-ghost" href="{e(u)}" rel="noopener">{e(t)}</a>' for t, u in a.get("links", []))
    phone = ""
    if a.get("phone"):
        phone = (f'<button class="phone" data-full="/img/{e(a["phone"])}" data-cap="{e(a["phone_alt"])}">'
                 f'<img src="/img/{e(a["phone"])}" alt="{e(a["phone_alt"])}" width="585" height="1266"></button>')
    hls = "".join(f'<div class="hl"><div class="hl-text"><h3>{e(h["title"])}</h3><p>{e(h["text"])}</p></div>{shot(h["img"], h["alt"])}</div>'
                  for h in a["highlights"])
    feats = "".join(f'<div class="feat"><h3>{e(f["title"])}</h3><p>{e(f["text"])}</p></div>' for f in a["features"])
    works = ""
    if a.get("works_with"):
        works = '<div class="works"><b>Works with</b>' + "".join(f"<span>{e(w)}</span>" for w in a["works_with"]) + "</div>"
    together = "".join(
        f'<div class="titem"><img src="/img/{t["app"]}.svg" alt="" width="34" height="34"><p><a href="/{apps[t["app"]]["name"]}/">'
        f'{e(apps[t["app"]]["name"])}</a>: {e(t["text"])}</p></div>' for t in a.get("together", []))
    more = "".join(
        f'<a href="/{apps[k]["name"]}/"{" aria-current=\"page\"" if k == key else ""}><img src="/img/{k}.svg" alt="" width="38" height="38">'
        f'<b>{e(apps[k]["name"])}</b><small>{SHORT[k]}</small></a>' for k in order)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{SITE}/{name}/">
<link rel="icon" type="image/svg+xml" href="/img/{key}.svg">
<meta property="og:type" content="website">
<meta property="og:title" content="{e(name)} — {e(a['tag'])}">
<meta property="og:description" content="{e(a['headline'])}">
<meta property="og:url" content="{SITE}/{name}/">
<meta property="og:image" content="{SITE}/img/{e(a['hero'])}">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/site.css">
</head>
<body style="--c:{c}">

<header>
  <nav class="nav wrap" aria-label="Main">
    <a class="brand" href="/">
      <img src="/img/icon.svg" alt="" width="34" height="34">
      <b><span class="io">io</span>Thing <span class="suite">suite</span></b>
    </a>
    <a class="link" href="/#apps">All apps</a>
    <a class="link" href="#screens">{e(name)}</a>
    <a class="link" href="#install">Install</a>
    <a class="link" href="{docs}">Docs</a>
    <a class="gh" href="{REPO}/tree/main/{key}" rel="noopener">{GITHUB_SVG} GitHub</a>
  </nav>
</header>

<main id="top">
  <section class="ahero">
    <div class="wrap ahero-grid">
      <div>
        <div class="aname"><img src="/img/{key}.svg" alt="" width="56" height="56"><div><b>{e(name)}</b><span>{e(a['tag'])}</span></div></div>
        <span class="eyebrow">{e(a['eyebrow'])}</span>
        <h1>{e(a['headline'])}</h1>
        <p class="lede">{a['lede']}</p>
        <ul class="chips">{"".join(f"<li>{e(x)}</li>" for x in a['chips'])}</ul>
        <div class="cta">
          <a class="btn btn-primary" href="#install"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1v8.6L4.7 6.3 3.3 7.7 8 12.4l4.7-4.7-1.4-1.4L8 9.6V1H8zM2 13h12v2H2v-2z"/></svg>Install {e(name)}</a>
          <a class="btn btn-ghost" href="{docs}">The guide</a>
          {links}
        </div>
      </div>
      <div class="stage">
        <button class="desk" data-full="/img/{e(a['hero'])}" data-cap="{e(a['hero_alt'])}"><img src="/img/{e(a['hero'])}" alt="{e(a['hero_alt'])}" width="1600" height="1000"></button>
        {phone}
      </div>
    </div>
  </section>

  <section class="shots" id="screens">
    <div class="wrap">
      <div class="section-head">
        <span class="eyebrow">a closer look</span>
        <h2>{e(name)}, screen by screen.</h2>
        <p>The real app, holding made-up data: the Parker family is invented. Click a screenshot to see it full size.</p>
      </div>
      {hls}
    </div>
  </section>

  <section id="features">
    <div class="wrap">
      <div class="section-head">
        <span class="eyebrow">what it does</span>
        <h2>Everything in {e(name)}.</h2>
        <p>Every app of the suite also has a phone layout that installs on a home screen, light and dark themes, roles per person, app passwords and a REST API.</p>
      </div>
      <div class="fgrid">{feats}</div>
      {works}
      <div class="alone-box"><p><b>On its own.</b> {e(a['alone'])}</p></div>
    </div>
  </section>

  {f'''<section class="apps" id="together">
    <div class="wrap">
      <div class="section-head">
        <span class="eyebrow">with the other apps</span>
        <h2>Better together, never required.</h2>
        <p>Add another app of the suite and it signs in with the same accounts. Here is what {e(name)} does with them.</p>
      </div>
      <div class="tlist">{together}</div>
    </div>
  </section>''' if together else ''}

  <section class="install" id="install">
    <div class="wrap">
      <div class="section-head">
        <span class="eyebrow">install</span>
        <h2>Install {e(name)}.</h2>
        <p>It needs a MariaDB or MySQL server and somewhere to run: see the <a href="/docs/start/requirements/">requirements</a>. Then open <code>http://&lt;host&gt;:{a['port']}</code> and sign in with the admin you chose.</p>
      </div>
      {install(key, a)}
      <p class="pick-note">More apps at once? <a href="/#install">Pick them on the home page</a> and get one command for all of them.</p>
    </div>
  </section>

  <section class="docs" id="more">
    <div class="wrap">
      <div class="section-head">
        <span class="eyebrow">the suite</span>
        <h2>The other apps.</h2>
        <p>Each one installs on its own, and they share one sign-in.</p>
      </div>
      <nav class="more" aria-label="Apps">{more}</nav>
    </div>
  </section>

  <footer>
    <div class="wrap">
      <div class="frow">
        <span class="fbrand"><img src="/img/icon.svg" alt=""><span><span class="io">io</span>Thing suite</span></span>
        <a href="/">Home</a>
        <a href="/docs/">Docs</a>
        <a href="{docs}">{e(name)} in the guide</a>
        <a href="{REPO}/tree/main/{key}" rel="noopener">{e(name)} on GitHub</a>
        <a href="{REPO}/blob/main/docs/CREDITS.md" rel="noopener">Photo credits</a>
      </div>
      <p>Free and open source software, licensed under the GNU GPL v3 or later. An independent project. Apple Health, HealthKit and iPhone are trademarks of Apple Inc.; digiKam, Proxmox, Docker, MariaDB, MySQL, Monarch Money, Homebox, Mealie and Cloudflare are trademarks of their owners.</p>
    </div>
  </footer>
</main>

<dialog class="lightbox" id="lightbox">
  <img src="" alt="">
  <div class="lb-foot"><span id="lb-cap"></span><button id="lb-close" autofocus>Close</button></div>
</dialog>
<script src="/app.js"></script>
</body>
</html>
"""


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    data = tomllib.loads((HERE / "landing" / "apps.toml").read_text())
    order = [m["key"] for m in MANIFESTS]
    for m in MANIFESTS:
        if m["key"] not in data:
            sys.exit(f"apps.toml: no [{m['key']}]: every app with a manifest gets a page")
        data[m["key"]].update(name=m["name"], color=m["color"], port=m["port"], tag=m["tag"])
    for key in order:
        a = data[key]
        for img in [a["hero"], a.get("phone")] + [h["img"] for h in a["highlights"]]:
            if img and not (HERE / "landing" / "img" / img).is_file():
                sys.exit(f"apps.toml: {key}: no such picture landing/img/{img}")
        for t in a.get("together", []):
            if t["app"] not in data:
                sys.exit(f"apps.toml: {key}: unknown app {t['app']}")
        d = out / a["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page(key, a, data, order))
    print(f"wrote {len(order)} app pages")


if __name__ == "__main__":
    main()
