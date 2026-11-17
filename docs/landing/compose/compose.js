/* The Docker Compose file builder of iosuite.iothing.net/compose/: build(answers) writes the stack file and what to
   do with it. Nothing here touches the page or the network, so tools/check-compose.js runs the same code under Node.

   The stack it writes: the apps that were picked, MariaDB (or a server that exists). One of the apps sets the
   stack up before it starts, at every start (`iosuite-shared stack ... -- python -m app`, in every app's image): it
   makes the databases, the first admin, and writes how the suite is reached into the Shared ioSuite database; the
   other apps wait until it is healthy. No service of its own for that: a container that stops when its work is done
   has Dockge and Portainer show the whole stack as exited. So the file is the whole install: nothing to edit, nothing
   to click afterwards.

   The apps, their ports and their folders on the suite's one address are the ones of the shared library
   (shared/iosuite_shared/install.py APPS, suite.py FOLDERS); tools/check-facts.py holds this list to them. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ioCompose = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var APPS = [
    {key:"iostart", name:"ioStart", port:8630, folder:"", sub:"home", what:"start page"},
    {key:"iopix", name:"ioPix", port:8600, folder:"pix", sub:"photos", what:"photos"},
    {key:"ionote", name:"ioNote", port:8610, folder:"notes", sub:"notes", what:"notes"},
    {key:"iocalendar", name:"ioCalendar", port:8620, folder:"calendar", sub:"calendar", what:"calendar"},
    {key:"iotask", name:"ioTask", port:8670, folder:"tasks", sub:"tasks", what:"tasks"},
    {key:"iorecipe", name:"ioRecipe", port:8690, folder:"recipes", sub:"recipes", what:"recipes"},
    {key:"iothings", name:"ioThings", port:8700, folder:"things", sub:"things", what:"inventory"},
    {key:"iomoney", name:"ioMoney", port:8710, folder:"money", sub:"money", what:"finances"},
    {key:"iocontact", name:"ioContact", port:8640, folder:"contacts", sub:"contacts", what:"contacts"},
    {key:"iohealth", name:"ioHealth", port:8650, folder:"health", sub:"health", what:"health"},
    {key:"iodns", name:"ioDNS", port:8660, folder:"dns", sub:"dns", what:"DNS records", tool:true},
    {key:"iobackup", name:"ioBackup", port:8680, folder:"backup", sub:"backup", what:"backups", tool:true}
  ];
  var BY = {};
  APPS.forEach(function (a) { BY[a.key] = a; });
  var IMAGE = "ghcr.io/avandeputte/iosuite/";
  var SITE = "https://iosuite.iothing.net/compose/";
  var MARK = "# answers: ";  // the line the page reads a file back from
  var SETUP_FIRST = ["iostart", "iocalendar", "iotask", "iocontact", "iothings", "iomoney", "iohealth", "iodns", "ionote", "iobackup", "iorecipe", "iopix"];  // the smaller images first

  /* ---- the answers ---- */
  function defaults(password, tz) {
    var apps = {}, names = {};
    APPS.forEach(function (a) { apps[a.key] = !a.tool; names[a.key] = a.sub; });
    return {
      apps: apps,
      db: {mode: "bundled", rootPassword: password(), host: "", port: "3306", create: "admin", adminUser: "root", adminPassword: "",
           user: "suite", password: password(), sharedName: "iosuite", sharedUser: "iosuite", sharedPassword: password()},
      admin: {user: "admin", password: ""},
      tz: tz || "Europe/Brussels",
      data: "/opt/iosuite",
      reach: {layout: "one", https: "none", address: "", port: "8630", domain: "", internalCert: false, proxyAt: "here", proxyIp: "", names: names},
      iopix: {photos: "", ai: true},
      iocontact: {ldap: false, ldapPort: "389"},
      iobackup: {folder: ""},
      demo: false,
      tag: "latest",
      subnet: "10.186.30.0/24"
    };
  }

  /* answers read back from a file may be older or hand-edited: only what defaults() knows is taken, with its type */
  function merge(base, given) {
    Object.keys(base).forEach(function (k) {
      var b = base[k], g = given ? given[k] : undefined;
      if (g === undefined || g === null) return;
      if (b !== null && typeof b === "object") { if (typeof g === "object") merge(b, g); }
      else if (typeof b === "boolean") base[k] = g === true;
      else if (typeof g === "string" || typeof g === "number") base[k] = String(g);
    });
    return base;
  }

  function b64(s) {
    if (typeof btoa === "function") return btoa(unescape(encodeURIComponent(s)));
    return Buffer.from(s, "utf8").toString("base64");
  }
  function unb64(s) {
    if (typeof atob === "function") return decodeURIComponent(escape(atob(s)));
    return Buffer.from(s, "base64").toString("utf8");
  }

  /* the answers a file made here holds, or null */
  function answersIn(text, password, tz) {
    var m = /^# answers: ([A-Za-z0-9+/=]+)\s*$/m.exec(text || "");
    if (!m) return null;
    try { return merge(defaults(password, tz), JSON.parse(unb64(m[1]))); } catch (e) { return null; }
  }

  /* ---- checks ---- */
  var IDENT = /^[A-Za-z0-9_]+$/;
  var HOSTNAME = /^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$/;
  var IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/;
  var LABEL = /^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/;
  var FULL = /^(\/|[A-Za-z]:[\\/])/;  // a full path on the server
  var SUBNET = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.0\/24$/;

  function port(v) { return /^\d{1,5}$/.test(v) && +v >= 1 && +v <= 65535; }
  function picked(s) { return APPS.filter(function (a) { return s.apps[a.key]; }); }
  function layout(s) { return s.reach.layout === "one" && s.apps.iostart ? "one" : "each"; }
  function under(s, sub) { return s.data.trim().replace(/[\\/]+$/, "") + "/" + sub; }  // a folder of the stack's data folder
  /* the folders of the data folder that the apps' containers write to as uid 1000 (MariaDB and Caddy see to their own) */
  function userFolders(s) {
    var out = [];
    if (s.apps.ionote) out.push(under(s, "ionote"));
    if (s.apps.iopix) out.push(under(s, "iopix"));
    if (s.apps.iobackup) { out.push(under(s, "iobackup/data")); if (!s.iobackup.folder.trim()) out.push(under(s, "iobackup/backups")); }
    return out;
  }
  function shq(p) { return /^[A-Za-z0-9_\/.:\\-]+$/.test(p) ? p : "'" + p.replace(/'/g, "'\\''") + "'"; }
  /* the one command to run before the first start: the folders the apps write to, theirs */
  function prepare(s) {
    var f = userFolders(s).map(shq).join(" ");
    return f ? "sudo mkdir -p " + f + " && sudo chown 1000:1000 " + f : "";
  }
  function loopback(h) { return /^(localhost|127(\.\d+){3}|::1|\[::1\])$/i.test(h); }

  /* [{at: the field (its data-k), text}] : what is still missing or wrong; empty when the file can be used */
  function problems(s) {
    var out = [], sel = picked(s), r = s.reach, d = s.db;
    function bad(at, text) { out.push({at: at, text: text}); }
    if (!sel.length) bad("apps", "Pick at least one app.");
    if (d.mode === "existing") {
      if (!d.host.trim()) bad("db.host", "The database server: its name or address.");
      else if (loopback(d.host.trim())) bad("db.host", "Inside a container, " + d.host.trim() + " is the container itself. For a database on this same machine, enter host.docker.internal; otherwise the server's name or address on your network.");
      else if (!HOSTNAME.test(d.host.trim()) && !IPV4.test(d.host.trim())) bad("db.host", "The database server is a name (db.example.lan) or an address (192.168.1.5), without http:// or a port.");
      if (!port(d.port)) bad("db.port", "The database server's port is a number (3306).");
      if (d.create === "admin") {
        if (!d.adminUser.trim()) bad("db.adminUser", "The database administrator's name (root, or an account that may create databases and users).");
        if (!d.adminPassword) bad("db.adminPassword", "The database administrator's password.");
      }
      if (!IDENT.test(d.user)) bad("db.user", "The apps' database user: letters, digits and _ only.");
      if (!d.password) bad("db.password", "A password for the apps' database user.");
      if (!IDENT.test(d.sharedName)) bad("db.sharedName", "The Shared ioSuite database's name: letters, digits and _ only.");
      if (!IDENT.test(d.sharedUser)) bad("db.sharedUser", "The Shared ioSuite database's user: letters, digits and _ only.");
      if (!d.sharedPassword) bad("db.sharedPassword", "The Shared ioSuite database user's password.");
    }
    var name = s.admin.user.trim();
    if (!name || name.length > 64) bad("admin.user", "A name for the first admin (up to 64 characters).");
    if (s.admin.password.length < 8) bad("admin.password", "A password of 8 characters or more for the admin.");
    if (!/^[A-Za-z0-9_+\-]+(\/[A-Za-z0-9_+\-]+)*$/.test(s.tz.trim())) bad("tz", "A time zone such as Europe/Brussels or America/New_York.");
    if (s.reach.layout === "one" && !s.apps.iostart && sel.length) bad("reach.layout", "One address for the whole suite is the start page's doing: pick ioStart too, or give each app its own address.");
    var one = layout(s) === "one";
    if (r.https === "none") {
      var addr = r.address.trim();
      if (addr && !HOSTNAME.test(addr) && !IPV4.test(addr)) bad("reach.address", "The server's name or address on your network (192.168.1.10 or nas.lan), without http:// or a port.");
      if (!addr && !one) bad("reach.address", "The server's name or address on your network (192.168.1.10 or nas.lan): the start page and the apps link to each other with it.");
      if (one && !port(r.port)) bad("reach.port", "The port the suite answers on is a number (8630).");
    } else {
      var dom = r.domain.trim().toLowerCase();
      if (!dom) bad("reach.domain", one ? "The name the suite is reached at (home.example.com)." : "The domain the apps' names are under (example.com).");
      else if (!HOSTNAME.test(dom) || dom.indexOf(".") < 0) bad("reach.domain", "A name such as " + (one ? "home.example.com" : "example.com") + ", without https:// or a path.");
      if (!one) {
        var seen = {};
        sel.forEach(function (a) {
          var n = (r.names[a.key] || "").trim().toLowerCase();
          if (!LABEL.test(n)) bad("reach.names." + a.key, a.name + "'s name: letters, digits and - only (" + a.sub + ").");
          else if (seen[n]) bad("reach.names." + a.key, a.name + " and " + seen[n] + " cannot both be " + n + "." + (dom || "example.com") + ".");
          else seen[n] = a.name;
        });
      }
      if (r.https === "proxy" && r.proxyAt === "other" && !IPV4.test(r.proxyIp.trim())) bad("reach.proxyIp", "The address the reverse proxy connects from (192.168.1.2).");
      if (r.https === "proxy" && one && !port(r.port)) bad("reach.port", "The port the suite answers on is a number (8630).");
    }
    if (s.apps.iopix && !FULL.test(s.iopix.photos.trim())) bad("iopix.photos", "ioPix: the folder with the photos on this server, as a full path (/srv/photos).");
    if (s.apps.iocontact && s.iocontact.ldap && !port(s.iocontact.ldapPort)) bad("iocontact.ldapPort", "ioContact: the LDAP port is a number (389).");
    if (!FULL.test(s.data.trim())) bad("data", "The folder for the stack's data, as a full path on this server (/opt/iosuite).");
    if (s.apps.iobackup && s.iobackup.folder.trim() && !FULL.test(s.iobackup.folder.trim())) bad("iobackup.folder", "ioBackup: the backups folder as a full path (/srv/backups), or empty for the stack's data folder.");
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(s.tag.trim())) bad("tag", "The version is latest, or a release such as v3.13.0.");
    var m = SUBNET.exec(s.subnet.trim());
    if (!m || +m[1] > 255 || +m[2] > 255 || +m[3] > 255) bad("subnet", "The stack's own network is written like 10.186.30.0/24.");
    return out;
  }

  /* ---- where everything is ---- */
  function net(s) {
    var m = SUBNET.exec(s.subnet.trim()) || [0, 10, 186, 30];
    var base = m[1] + "." + m[2] + "." + m[3] + ".";
    return {subnet: base + "0/24", range: base + "128/25", gateway: base + "1", iostart: base + "10", caddy: base + "11"};
  }

  /* the address people use for each app: {key: url or ""} */
  function addresses(s) {
    var out = {}, r = s.reach, one = layout(s) === "one", sel = picked(s);
    var dom = r.domain.trim().toLowerCase(), addr = r.address.trim();
    if (one) {
      var base = r.https === "none" ? (addr ? "http://" + addr + (r.port === "80" ? "" : ":" + r.port) : "") : (dom ? "https://" + dom : "");
      sel.forEach(function (a) { out[a.key] = !base ? "" : a.key === "iostart" ? base : base + "/" + a.folder; });
    } else if (r.https === "none") {
      sel.forEach(function (a) { out[a.key] = addr ? "http://" + addr + ":" + a.port : ""; });
    } else {
      sel.forEach(function (a) { out[a.key] = dom ? "https://" + (r.names[a.key] || a.sub).trim().toLowerCase() + "." + dom : ""; });
    }
    return out;
  }

  /* the addresses the apps believe a reverse proxy's headers from */
  function proxies(s) {
    var n = net(s), r = s.reach, out = [];
    if (layout(s) === "one") out.push(n.iostart);          // the start page passes the other apps' requests on
    if (r.https === "caddy") out.push(n.caddy);
    if (r.https === "proxy") out.push(r.proxyAt === "here" ? n.gateway : r.proxyIp.trim());  // a proxy on this server comes in through the stack's gateway
    return out.filter(Boolean);
  }

  function caddyfile(s, upstream) {
    var r = s.reach, urls = addresses(s), lines = [], one = layout(s) === "one";
    var tls = r.https === "caddy" && r.internalCert ? ["    tls internal"] : [];
    picked(s).forEach(function (a) {
      if (one && a.key !== "iostart") return;
      var host = (urls[a.key] || "").replace(/^https:\/\//, "");
      lines = lines.concat([host + " {"], tls, ["    reverse_proxy " + upstream(a)], ["}"]);
    });
    return lines;
  }

  /* ---- YAML ---- */
  function q(v) { return JSON.stringify(String(v)).replace(/\$/g, "$$$$"); }   // a quoted scalar; $ doubled so compose leaves it alone
  function sqlq(v) { return "'" + String(v).replace(/\\/g, "\\\\").replace(/'/g, "''") + "'"; }

  function build(s, when) {
    var sel = picked(s), r = s.reach, d = s.db, n = net(s), one = layout(s) === "one";
    var urls = addresses(s), trusted = proxies(s), bundled = d.mode !== "existing";
    var tag = s.tag.trim() || "latest", L = [];
    var dbHost = bundled ? "db" : d.host.trim(), dbPort = bundled ? "3306" : d.port;
    var dbUser = bundled ? "suite" : d.user, sharedName = bundled ? "iosuite" : d.sharedName, sharedUser = bundled ? "iosuite" : d.sharedUser;
    var admin = bundled ? "root" : (d.create === "admin" ? d.adminUser.trim() : "");
    var adminPassword = bundled ? d.rootPassword : d.adminPassword;
    var hostGateway = !bundled && /^host\.docker\.internal$/i.test(dbHost);
    var cookie = !one && r.https !== "none" ? r.domain.trim().toLowerCase() : "";
    var listen = r.https === "proxy" && r.proxyAt === "here" ? "127.0.0.1:" : "";
    var first = firstApp(s);
    function add() { for (var i = 0; i < arguments.length; i++) L.push(arguments[i]); }

    add("# ioSuite in one Docker stack: " + sel.map(function (a) { return a.name; }).join(", ") + (bundled ? ", and MariaDB." : ", on the database server " + dbHost + "."),
        "# Made" + (when ? " on " + when : "") + " at " + SITE,
        "#",
        "#   docker compose up -d        # in the folder that holds this file; or paste it as a stack in Dockge or Portainer",
        "#",
        "# Nothing to edit. " + first + " goes first, at every start: before it starts it makes the databases" + (admin ? "" : "' tables") + ", the first admin and",
        "# writes how the suite is reached into the Shared ioSuite database" + (sel.length > 1 ? "; the other apps start once it is up" : "") + ".",
        "# This file holds passwords: keep it private.",
        "# The data is in " + s.data.trim() + ", a folder per container." + (userFolders(s).length ? " Before the first start:" : ""));
    if (userFolders(s).length) add("#   " + prepare(s) + "   # the apps write as user 1000");
    add(
        "# To add or remove an app later, open this file on that page (Open a file), change the answers and start it again.",
        "",
        "name: iosuite",
        "",
        "x-app: &app",
        "  restart: unless-stopped",
        "  logging: &logging                    # what Docker keeps of an app's output: at most 3 files of 5 MB",
        "    driver: json-file",
        "    options: {max-size: 5m, max-file: \"3\"}");
    if (hostGateway) add("  extra_hosts: [\"host.docker.internal:host-gateway\"]   # the database server is this machine");
    add("",
        "x-env: &env                            # the same for every app: one database server, one Shared ioSuite database",
        "  TZ: " + q(s.tz.trim()),
        "  DB_TYPE: mysql",
        "  DB_HOST: " + q(dbHost),
        "  DB_PORT: " + q(dbPort),
        "  DB_USER: " + q(dbUser),
        "  DB_PASSWORD: " + q(d.password),
        "  IOSUITE_DB_HOST: " + q(dbHost),
        "  IOSUITE_DB_PORT: " + q(dbPort),
        "  IOSUITE_DB_NAME: " + q(sharedName),
        "  IOSUITE_DB_USER: " + q(sharedUser),
        "  IOSUITE_DB_PASSWORD: " + q(d.sharedPassword));
    if (cookie) add("  COOKIE_DOMAIN: " + q(cookie) + "         # one sign-in for every app under this domain");
    add("", "services:");

    if (bundled) {
      add("  db:",
          "    image: mariadb:11",
          "    container_name: iosuite-db",
          "    restart: unless-stopped",
          "    logging: *logging",
          "    environment:",
          "      MARIADB_ROOT_PASSWORD: " + q(d.rootPassword),
          "    volumes:",
          "      - " + q(under(s, "db") + ":/var/lib/mysql") + "   # the databases",
          "    healthcheck:",
          "      test: [\"CMD\", \"healthcheck.sh\", \"--connect\", \"--innodb_initialized\"]",
          "      interval: 10s",
          "      timeout: 5s",
          "      start_period: 30s",
          "      retries: 6",
          "");
    }

    var cmd = ["iosuite-shared", "stack"];
    if (admin) cmd = cmd.concat(["--db-admin", admin, "--databases", sel.map(function (a) { return a.key; }).join(",")]);
    cmd = cmd.concat(["--one-address", one ? "on" : "off", "--proxies", trusted.join(",")]);
    if (s.demo) cmd.push("--demo");  // the made-up Calloway family's accounts, and every app fills itself at its first start
    cmd = cmd.concat(["--", "python", "-m", "app"]);  // what the image runs by itself: the app, once the stack is set up

    sel.forEach(function (a) {
      var k = a.key, ports = [], vols = [], env = [];
      if (r.https !== "caddy" && (!one || k === "iostart")) ports.push(q(listen + (one ? r.port : a.port) + ":" + a.port));
      if (k === "iocontact" && s.iocontact.ldap) ports.push(q(s.iocontact.ldapPort + ":3890") + "          # the LDAP directory for mail apps (read-only)");
      env.push("DB_NAME: " + k);
      if (urls[k]) env.push("PUBLIC_URL: " + q(urls[k]));
      env.push("INTERNAL_URL: " + q("http://" + k + ":" + a.port) + "   # where the other apps of the stack find it");
      if (k === "ionote") vols.push(q(under(s, "ionote") + ":/data") + "   # the session secret and the log; the notes are in the database");
      if (k === "iopix") {
        vols.push(q(s.iopix.photos.trim() + ":/library/photos") + "   # the photos (read and write: ioPix keeps sidecar files beside them)");
        vols.push(q(under(s, "iopix") + ":/data") + "   # index, thumbnails, models");
        env.push("DIGIKAM_DB_TYPE: none", "DIGIKAM_CHECK: none", "PHOTOS_ROOT: /library/photos",
                 "AUTO_MODELS: " + q(s.iopix.ai ? "siglip2,yolox,geonames" : "") + (s.iopix.ai ? "   # search by content, objects, places: about 1.6 GB, fetched on the first start" : ""));
      }
      if (k === "iobackup") {
        vols.push(q(under(s, "iobackup/data") + ":/data") + "   # where a backup is put together before it is stored");
        vols.push(q((s.iobackup.folder.trim() || under(s, "iobackup/backups")) + ":/backups") + "   # where a local destination keeps the backups");
      }
      add("  " + k + ":" + (k === "iostart" ? "                               # the start page" + (one ? ": answers for every app, each in its folder" : "") : ""),
          "    <<: *app",
          "    image: " + IMAGE + k + ":" + tag,
          "    container_name: " + k);
      if (k !== first) add("    depends_on:", "      " + first + ":", "        condition: service_healthy       # " + first + " sets the stack up before it starts");
      else if (bundled) add("    depends_on:", "      db:", "        condition: service_healthy");
      if (ports.length) { add("    ports:"); ports.forEach(function (p) { add("      - " + p); }); }
      if (k === "iostart" && one) add("    networks:", "      default:", "        ipv4_address: " + n.iostart + "      # the address the other apps know the start page by");
      if (vols.length) { add("    volumes:"); vols.forEach(function (v) { add("      - " + v); }); }
      add("    environment:", "      <<: *env");
      env.forEach(function (e) { add("      " + e); });
      if (k === first) {
        add("      ADMIN_USER: " + q(s.admin.user.trim()) + "               # the first admin: made when there is no account yet",
            "      ADMIN_PASSWORD: " + q(s.admin.password));
        if (admin) add("      DB_ADMIN_PASSWORD: " + q(adminPassword) + "   # the database administrator " + admin + ": creates the databases and users that are missing");
        add("    # sets the stack up, then starts the app (no container of its own for that, so none is left stopped)",
            "    command: [" + cmd.map(q).join(", ") + "]");
        if (sel.length > 1) add("    healthcheck:", "      interval: 10s                      # the other apps start as soon as this one answers");
      }
      add("");
    });

    if (r.https === "caddy") {
      add("  caddy:                                 # HTTPS: gets and renews the certificate" + (one ? "" : "s") + " by itself",
          "    image: caddy:2",
          "    container_name: iosuite-caddy",
          "    restart: unless-stopped",
          "    logging: *logging",
          "    ports:",
          "      - \"80:80\"",
          "      - \"443:443\"",
          "      - \"443:443/udp\"",
          "    networks:",
          "      default:",
          "        ipv4_address: " + n.caddy,
          "    configs:",
          "      - source: caddyfile",
          "        target: /etc/caddy/Caddyfile",
          "    volumes:",
          "      - " + q(under(s, "caddy/data") + ":/data") + "   # the certificates",
          "      - " + q(under(s, "caddy/config") + ":/config"),
          "");
      add("configs:", "  caddyfile:", "    content: |");
      caddyfile(s, function (a) { return a.key + ":" + a.port; }).forEach(function (l) { add("      " + l); });
      add("");
    }

    if (trusted.length) {
      add("networks:",
          "  default:                               # a network of its own, so the proxies' addresses are known ahead of time",
          "    ipam:",
          "      config:",
          "        - subnet: " + n.subnet,
          "          ip_range: " + n.range + "    # what Docker hands out by itself, clear of the addresses set above",
          "          gateway: " + n.gateway,
          "");
    }
    add("# The answers this file was made from, for " + SITE + " to read back (Open a file):", MARK + b64(JSON.stringify(s)), "");

    return {yaml: L.join("\n"), steps: steps(s), problems: problems(s), addresses: urls};
  }

  /* ---- what to do with the file: [{title, text, code?, head?}] ---- */
  function firstApp(s) { return SETUP_FIRST.filter(function (k) { return s.apps[k]; })[0] || "iostart"; }  // sets the stack up before it starts; the others wait for it
  function steps(s) {
    var first = firstApp(s);
    var sel = picked(s), r = s.reach, d = s.db, n = net(s), one = layout(s) === "one", urls = addresses(s), out = [];
    var local = r.https === "proxy" && r.proxyAt === "here";

    if (d.mode === "existing" && d.create !== "admin") {
      var sql = ["CREATE DATABASE IF NOT EXISTS `" + d.sharedName + "` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
                 "CREATE USER IF NOT EXISTS '" + d.sharedUser + "'@'%' IDENTIFIED BY " + sqlq(d.sharedPassword) + ";",
                 "GRANT ALL PRIVILEGES ON `" + d.sharedName + "`.* TO '" + d.sharedUser + "'@'%';",
                 "CREATE USER IF NOT EXISTS '" + d.user + "'@'%' IDENTIFIED BY " + sqlq(d.password) + ";"];
      sel.forEach(function (a) {
        sql.push("CREATE DATABASE IF NOT EXISTS `" + a.key + "` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
                 "GRANT ALL PRIVILEGES ON `" + a.key + "`.* TO '" + d.user + "'@'%';");
      });
      sql.push("FLUSH PRIVILEGES;");
      out.push({title: "Create the databases", head: "sql, on " + (d.host.trim() || "the database server") + " as an administrator",
                text: "On the database server, once, before the first start. What exists already is left as it is.", code: sql.join("\n")});
    }

    var notes = [];
    if (d.mode === "existing") notes.push("The database server has to accept connections from this machine (its bind-address, its firewall).");
    if (s.apps.iopix) notes.push("ioPix runs as user 1000: the photos folder has to be readable by it, and writable for the sidecar files (chown -R 1000 on a new folder).");
    if (r.https === "caddy" && !r.internalCert) notes.push("For the certificate" + (one ? "" : "s") + ", " + (one ? "the name has" : "the names have") + " to lead to this server from the internet (DNS), with ports 80 and 443 open to it.");
    if (r.https === "caddy" && r.internalCert) notes.push("Caddy signs the certificate itself: browsers warn until its root certificate is trusted on each device (docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .).");
    out.push({title: "Start it", head: "on the server",
              text: "Save the file as docker-compose.yml in a folder of its own, then start it there. The first start pulls the images and takes a minute or two." +
                    (notes.length ? " " + notes.join(" ") : ""),
              code: (prepare(s) ? prepare(s) + "   # the folders the apps write to, as user 1000\n" : "") + "docker compose up -d\ndocker compose logs " + first + "     # what was set up (its first lines, up to ok)"});

    if (r.https === "proxy") {
      var at = local ? "127.0.0.1" : (r.address.trim() || "<this server>");
      var lines = caddyfile(s, function (a) { return at + ":" + (one ? r.port : a.port); });
      out.push({title: "Point your reverse proxy at it", head: "caddyfile" + (local ? "" : ", on the proxy"),
                text: (one ? "One site, one upstream: the start page passes every app's folder on." : "A site per app.") +
                      " For Caddy; the guide has the same for nginx and the others (Running them › Reverse proxy and HTTPS), and a Cloudflare Tunnel takes the same upstream" + (one ? "" : "s") + "." +
                      (local ? " The ports are open on this server only (127.0.0.1): the proxy is the one way in." : " The apps take the visitor's address from " + (r.proxyIp.trim() || "the proxy") + " only."),
                code: lines.join("\n")});
    }

    var open = sel.filter(function (a) { return urls[a.key]; }).map(function (a) { return (a.name + "            ").slice(0, 12) + urls[a.key] + (a.key !== "iostart" && one ? "/" : ""); });
    var where = open.length ? "" : (one ? " The suite is at http://<this server>:" + r.port + ", each app in its folder (/" + sel.filter(function (a) { return a.folder; }).slice(0, 2).map(function (a) { return a.folder; }).join("/, /") + "/ and so on)." : "");
    out.push({title: "Sign in", head: "addresses",
              text: "Sign in as " + (s.admin.user.trim() || "the admin") + " with the password you chose: it is a suite admin, an admin of every app. " +
                    (s.demo ? "The demo family signs in as morgan, riley, ava or theo, password calloway (Morgan is a suite admin too)." : "Add the family under Settings › Security › People.") + where +
                    (s.apps.iocontact && s.iocontact.ldap ? " ioContact's LDAP directory is on port " + s.iocontact.ldapPort + "." : ""),
              code: open.join("\n")});

    out.push({title: "Later", head: "on the server",
              text: "Update by pulling the images. To add or remove an app, or change an answer, open your file on this page (Open a file), change it and start the new file the same way: the data stays in " + s.data.trim() + (d.mode === "existing" ? " and on your database server" : "") + "." +
                    (d.mode !== "existing" ? " To start over from nothing, stop the stack and empty " + under(s, "db") + "." : "") +
                    (d.mode === "existing" && d.create === "admin" ? " Once it has started, the administrator's password can be taken out of the file (DB_ADMIN_PASSWORD and --db-admin … --databases … of " + first + ") until you add an app." : ""),
              code: "docker compose pull && docker compose up -d"});
    void n;
    return out;
  }

  return {APPS: APPS, quoted: q, prepare: prepare, MARK: MARK, defaults: defaults, merge: merge, answersIn: answersIn, problems: problems, build: build, addresses: addresses, proxies: proxies, layout: layout, net: net};
});
