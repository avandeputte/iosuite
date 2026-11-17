#!/usr/bin/env node
/* Runs the Docker Compose builder's own code (landing/compose/compose.js) over the choices it offers and fails when a
   file it writes is not what the choice calls for.

       node tools/check-compose.js

   With Docker on the machine, every file is also read by `docker compose config`, which is what catches a file that
   is not valid at all (CHECK_COMPOSE_DOCKER=0 skips it; =1 fails when Docker is missing). build.sh runs this. */
"use strict";
const path = require("path"), fs = require("fs"), os = require("os"), cp = require("child_process");
const C = require(path.join(__dirname, "..", "landing", "compose", "compose.js"));

let n = 0;
const pw = () => "pw" + (++n) + "Abcdefghijkl";
const none = () => Object.fromEntries(C.APPS.map(a => [a.key, false]));
function answers(change) {
  const s = C.defaults(pw, "Europe/Brussels");
  s.admin.password = 'It\'s $ecret "1"';
  s.iopix.photos = "/srv/photos";
  return C.merge(s, change || {});
}
const failures = [];
function check(name, ok, detail) { if (!ok) failures.push(name + (detail ? ": " + detail : "")); }
const has = (y, line) => y.split("\n").some(l => l.trim().startsWith(line));

const CASES = {
  "the default: every app, MariaDB, one address": [answers(), (y, s) => {
    check("one address is on", y.includes('"--one-address", "on", "--proxies", "10.186.30.10"'));
    check("only the start page is published", (y.match(/^ {6}- "\d+:\d+"$/gm) || []).join() === '      - "8630:8630"');
    check("every app's database is made", y.includes('"--databases", "' + C.APPS.filter(a => s.apps[a.key]).map(a => a.key).join(",") + '"'));
    check("the admin's password is quoted with $ doubled", has(y, 'ADMIN_PASSWORD: "It\'s $$ecret \\"1\\""'));
    check("the start page has its fixed address", y.includes("ipv4_address: 10.186.30.10"));
    check("no demo data unless asked", !y.includes('"--demo"'));
  }],
  "with demo data": [answers({demo: true}), y => {
    check("setup adds the demo", y.includes('"--proxies", "10.186.30.10", "--demo"]'));
  }],
  "everything, with the admin tools": [answers({apps: {iodns: true, iobackup: true}, iobackup: {folder: "/srv/backups"}, iocontact: {ldap: true}}), y => {
    check("ldap is published", y.includes('- "389:3890"'));
    check("the backups folder is mounted", y.includes('- "/srv/backups:/backups"'));
  }],
  "one app, an address per app, no https": [answers({apps: Object.assign(none(), {iocalendar: true}), reach: {layout: "each", address: "192.168.1.10"}}), y => {
    check("no volumes section when nothing needs one besides the database", has(y, "volumes:") && has(y, "iosuite-db:"));
    check("its public address", has(y, 'PUBLIC_URL: "http://192.168.1.10:8620"'));
    check("no network of its own without a proxy", !has(y, "networks:"));
    check("one address is off", y.includes('"--one-address", "off", "--proxies", ""'));
  }],
  "one address asked for without the start page": [answers({apps: {iostart: false}, reach: {address: "nas.lan"}}), y => {
    check("falls back to a port per app", has(y, 'PUBLIC_URL: "http://nas.lan:8620"') && y.includes('"--one-address", "off"'));
  }, ["reach.layout"]],
  "caddy, one name": [answers({reach: {https: "caddy", domain: "Home.Example.com"}}), y => {
    check("caddy passes on to the start page", y.includes("      home.example.com {\n          reverse_proxy iostart:8630\n      }"));
    check("no app port is published", !/^ {6}- "\d+:\d+"$/m.test(y.replace('- "80:80"', "").replace('- "443:443"', "")));
    check("both proxies are believed", y.includes('"--proxies", "10.186.30.10,10.186.30.11"'));
    check("folders of the name", has(y, 'PUBLIC_URL: "https://home.example.com/calendar"'));
  }],
  "caddy, a name per app, its own certificates": [answers({reach: {layout: "each", https: "caddy", domain: "example.com", internalCert: true, names: {iopix: "pix"}}}), y => {
    check("a site per app", y.includes("      pix.example.com {\n          tls internal\n          reverse_proxy iopix:8600\n      }"));
    check("one sign-in", has(y, 'COOKIE_DOMAIN: "example.com"'));
    check("only caddy is believed", y.includes('"--proxies", "10.186.30.11"'));
  }],
  "own proxy on this server, one name": [answers({reach: {https: "proxy", domain: "home.example.com", port: "9000"}}), (y, s, out) => {
    check("open on this machine only", y.includes('- "127.0.0.1:9000:8630"'));
    check("the gateway is believed", y.includes('"--proxies", "10.186.30.10,10.186.30.1"'));
    check("the proxy's site is given", out.steps.some(t => t.code && t.code.includes("reverse_proxy 127.0.0.1:9000")));
  }],
  "own proxy elsewhere, a name per app": [answers({reach: {layout: "each", https: "proxy", domain: "example.com", proxyAt: "other", proxyIp: "192.168.1.2", address: "192.168.1.10"}}), (y, s, out) => {
    check("open on the network", y.includes('- "8620:8620"'));
    check("the proxy's address is believed", y.includes('"--proxies", "192.168.1.2"'));
    check("upstreams at the server's address", out.steps.some(t => t.code && t.code.includes("reverse_proxy 192.168.1.10:8620")));
  }],
  "a database server that exists, made by an administrator": [answers({db: {mode: "existing", host: "host.docker.internal", port: "3307", adminPassword: "r$t", user: "fam"}}), y => {
    check("no database container", !has(y, "db:") && !y.includes("mariadb:11"));
    check("this machine is reachable", (y.match(/host\.docker\.internal:host-gateway/g) || []).length === 2);
    check("the administrator is used", y.includes('"--db-admin", "root"') && has(y, 'DB_ADMIN_PASSWORD: "r$$t"'));
    check("the apps' user", has(y, 'DB_USER: "fam"') && has(y, 'DB_PORT: "3307"'));
  }],
  "a database server that exists, databases made by hand": [answers({db: {mode: "existing", create: "manual", host: "db.lan", password: "it's"}}), (y, s, out) => {
    check("no administrator in the file", !y.includes("--db-admin") && !y.includes("DB_ADMIN_PASSWORD"));
    const sql = (out.steps.find(t => t.title === "Create the databases") || {}).code || "";
    check("the sql is given, quoted", sql.includes("IDENTIFIED BY 'it''s'") && sql.includes("GRANT ALL PRIVILEGES ON `iomoney`.* TO 'suite'@'%';"));
  }],
  "a pinned version and another network": [answers({tag: "v3.13.0", subnet: "172.29.7.0/24"}), y => {
    check("the version on every image", !y.includes(":latest") && y.includes("iosuite/iostart:v3.13.0"));
    check("the network", y.includes("subnet: 172.29.7.0/24") && y.includes('"--proxies", "172.29.7.10"'));
  }],
};

const docker = process.env.CHECK_COMPOSE_DOCKER !== "0" && cp.spawnSync("docker", ["compose", "version"], {stdio: "ignore"}).status === 0;
if (!docker && process.env.CHECK_COMPOSE_DOCKER === "1") failures.push("docker compose is not on this machine");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "check-compose-"));
let files = 0;
for (const [name, [s, test, expected]] of Object.entries(CASES)) {
  const before = failures.length;
  const out = C.build(s, "2026-01-01");
  const wrong = out.problems.map(p => p.at);
  check("nothing is missing", JSON.stringify(wrong) === JSON.stringify(expected || []), JSON.stringify(out.problems));
  check("no tabs, no trailing spaces", !/\t| +$/m.test(out.yaml));
  const back = C.answersIn(out.yaml, pw, "UTC");
  check("the answers come back from the file", back && JSON.stringify(back) === JSON.stringify(s));
  check("the file made from them is the same", back && C.build(back, "2026-01-01").yaml === out.yaml);
  test(out.yaml, s, out);
  if (docker) {
    const f = path.join(tmp, "docker-compose.yml");
    fs.writeFileSync(f, out.yaml);
    const r = cp.spawnSync("docker", ["compose", "-f", f, "config", "--format", "json"], {encoding: "utf8", env: Object.assign({}, process.env, {ADMIN_PASSWORD: "", DB_PASSWORD: ""})});
    check("docker compose reads it", r.status === 0, (r.stderr || "").trim().split("\n").pop());
    if (r.status === 0) {
      const cfg = JSON.parse(r.stdout);
      check("the admin's password reaches the setup step as typed", cfg.services.setup.environment.ADMIN_PASSWORD === s.admin.password.replace(/\$/g, "$$$$"));  // config prints $ doubled again
      check("a service per app", C.APPS.every(a => !!cfg.services[a.key] === !!s.apps[a.key]));
      check("every app waits for setup", C.APPS.filter(a => s.apps[a.key]).every(a => (cfg.services[a.key].depends_on || {}).setup));
    }
    files++;
  }
  failures.slice(before).forEach((f, i) => { failures[before + i] = name + " — " + f; });
}
fs.rmSync(tmp, {recursive: true, force: true});

/* what must be refused */
const REFUSED = [
  [{apps: none()}, "apps"], [{admin: {password: "short"}}, "admin.password"], [{iopix: {photos: "photos"}}, "iopix.photos"],
  [{db: {mode: "existing", host: "localhost"}}, "db.host"], [{db: {mode: "existing", host: "db.lan", user: "a b"}}, "db.user"],
  [{reach: {https: "caddy"}}, "reach.domain"], [{reach: {https: "caddy", domain: "home"}}, "reach.domain"],
  [{reach: {layout: "each"}}, "reach.address"], [{reach: {layout: "each", https: "caddy", domain: "example.com", names: {ionote: "calendar"}}}, "reach.names.iocalendar"],
  [{reach: {https: "proxy", domain: "home.example.com", proxyAt: "other"}}, "reach.proxyIp"], [{subnet: "10.0.0.0/8"}, "subnet"], [{tz: "Brussels time"}, "tz"],
];
for (const [change, at] of REFUSED) {
  check("refused: " + JSON.stringify(change), C.problems(answers(change)).some(p => p.at === at), "no problem at " + at);
}

console.log(`checked ${Object.keys(CASES).length} stack files and ${REFUSED.length} wrong answers` + (docker ? `; docker compose read ${files} files` : "; docker compose is not here, so the files were not read by it"));
if (failures.length) {
  console.log(`\n${failures.length} wrong:`);
  failures.forEach(f => console.log("  - " + f));
  process.exit(1);
}
console.log("every file is what its answers call for");
