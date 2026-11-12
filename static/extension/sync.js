/* ioSuite Bookmarks: the sync engine. Keeps the browser's own bookmarks (Bookmarks bar, Other bookmarks and, in
 * Firefox, the Bookmarks menu) the same as the start page's bookmarks, both ways.
 *
 * How the trees line up (the same in every browser, so every browser shows the same bars):
 *   the browser's Bookmarks bar / Favorites bar / Bookmarks Toolbar  <->  the top-level folder "Bookmarks bar"
 *   Firefox's Bookmarks menu                                          <->  the top-level folder "Bookmarks menu"
 *   Other bookmarks / Other favorites                                <->  everything else at the top level
 * (so in Chrome and Edge, which have no bookmarks menu, "Bookmarks menu" is a folder in Other bookmarks).
 * Vivaldi keeps everything in one tree, "Bookmarks", and shows one folder of it as its bookmark bar (the one set as
 * the bookmark bar folder; "Bookmarks bar" is made when there is none): that folder is the bar, and the rest of
 * "Bookmarks" (Speed Dial folders included) is what the other browsers show as Other bookmarks. What is deleted in
 * Vivaldi goes to its Trash, which does not sync: for the start page it is deleted.
 *
 * A sync: read the browser's tree; work out what changed in it since the tree last synced (`snap`, kept with the
 * server's revision): made, renamed, re-addressed, moved, reordered, deleted; send that as ops in one request
 * (app/bookmarkext.py applies them together); then make the browser's tree the tree that comes back. So a delete on
 * the server, or in another browser, goes from this browser too. The very first sync matches what is already on both
 * sides (folders by name, links by address) and adds the rest to the server ("merge"), or takes the server's tree
 * and drops what only this browser had ("server").
 *
 * No DOM, no extension globals: `bm` is the bookmarks API (chrome.bookmarks / browser.bookmarks) and `http` does the
 * requests, so the same file runs in the extension and in the tests (node).
 */
(function (root) {
  'use strict';

  const BAR = /^(bookmarks[ -]?(bar|toolbar)|favou?rites[ -]?bar|toolbar)$/i;
  const MENU = /^bookmarks[ -]?menu$/i;

  /** Vivaldi: its tree has a Trash, and its nodes say whether they are a speed dial or the bookmark bar. */
  function isVivaldi(top) {
    const own = (n) => n.trash !== undefined || n.speeddial !== undefined || n.bookmarkbar !== undefined;
    const kids = top.children || [];
    if (typeof navigator !== 'undefined' && /\bOPR\//.test(navigator.userAgent || '')) return false;  // Opera has a Trash too, but Chrome's tree
    return kids.some((c) => own(c) || (c.children || []).some(own))
      || kids.some((c) => c.url === undefined && Number(c.id) > 3 && /^trash$/i.test(c.title || '') && !c.folderType);
  }

  /** The browser's own top folders: {toolbar, other, menu?} -> its node. In Vivaldi `toolbar` may be missing. */
  function localRoots(top) {
    const out = {};
    if (isVivaldi(top)) {
      const main = (top.children || []).find((c) => c.id === '1' || c.folderType === 'bookmarks-bar');
      if (!main) return out;
      const flagged = (n) => { for (const c of n.children || []) { if (c.url === undefined && c.bookmarkbar === true) return c; const x = flagged(c); if (x) return x; } return null; };
      const bar = flagged(main) || (main.children || []).find((c) => c.url === undefined && BAR.test((c.title || '').trim()));
      if (bar) out.toolbar = bar;
      out.other = main;
      return out;
    }
    // Chrome signed in to a Google account can hold two of each (the account's and this device's): the account's, where
    // Chrome itself puts new bookmarks, is the one that syncs
    const tops = [...(top.children || [])].sort((a, b) => (b.syncing === true) - (a.syncing === true));
    for (const c of tops) {
      const kind = c.folderType === 'bookmarks-bar' || c.id === '1' || c.id === 'toolbar_____' ? 'toolbar'
        : c.folderType === 'other' || c.id === '2' || c.id === 'unfiled_____' ? 'other'
          : c.id === 'menu________' ? 'menu' : null;
      if (kind && !out[kind]) out[kind] = c;
    }
    return out;
  }

  /** The server's top folders that stand for the browser's: {toolbar, menu} -> id, keeping the ones known before. */
  function serverRoots(tree, known) {
    const out = {};
    for (const [kind, re] of [['toolbar', BAR], ['menu', MENU]]) {
      const keep = known && known[kind] && tree.find((n) => n.folder && n.id === known[kind]);
      const found = keep || tree.find((n) => n.folder && re.test((n.title || '').trim()));
      if (found) out[kind] = found.id;
    }
    return out;
  }

  const isSep = (n) => n.type === 'separator';  // Firefox only; left where they are
  const isFolder = (n) => n.type === 'folder' || (n.type === undefined && n.url === undefined);
  const K = (v) => (v === null || v === undefined ? 'top' : String(v));  // a server parent as a map key

  /** The server's tree as a snapshot: nodes by id {p, f, t, u} and the children of each parent in order. */
  function snapshot(tree) {
    const nodes = {}, kids = { top: [] };
    const walk = (list, p) => {
      for (const n of list) {
        nodes[n.id] = { p, f: !!n.folder, t: n.title || '', u: n.folder ? null : n.url };
        kids[K(p)].push(n.id);
        if (n.folder) { kids[K(n.id)] = []; walk(n.children || [], n.id); }
      }
    };
    walk(tree, null);
    return { nodes, kids };
  }

  /** The children of each server root as this browser shows them. */
  function serverParts(tree, roots, lroots) {
    const byId = Object.fromEntries(tree.map((n) => [n.id, n]));
    const used = new Set(Object.keys(lroots).filter((k) => k !== 'other' && roots[k]).map((k) => roots[k]));
    const parts = { other: { key: null, children: tree.filter((n) => !used.has(n.id)) } };
    for (const k of ['toolbar', 'menu']) {
      if (lroots[k] && roots[k] && byId[roots[k]]) parts[k] = { key: roots[k], children: byId[roots[k]].children || [] };
    }
    return parts;
  }

  class Sync {
    /** state: what the last sync left ({rev, snap, map: {serverId: localId}, roots}), kept by the caller. */
    constructor({ bm, http, state, log }) {
      this.bm = bm;
      this.http = http;
      this.state = state || {};
      this.log = log || (() => {});
      this.applying = false;
    }

    /** One sync. mode: 'merge' or 'server' for a first one (no snapshot yet). Returns a summary. */
    async run({ canWrite = true, mode = 'merge' } = {}) {
      const st = this.state;
      let [top] = await this.bm.getTree();
      let lroots = localRoots(top);
      const vivaldi = isVivaldi(top);
      let madeBar = false;
      if (lroots.other && !lroots.toolbar && vivaldi) {  // Vivaldi without a bookmark bar folder: one is made, and set as the bar
        this.applying = true;
        try {
          const f = await this.bm.create({ parentId: lroots.other.id, index: 0, title: 'Bookmarks bar' });
          await Promise.resolve(this.bm.update(f.id, { bookmarkbar: true })).catch(() => {});  // Vivaldi's own field; by hand when it refuses
          madeBar = true;
        } finally { this.applying = false; }
        [top] = await this.bm.getTree();
        lroots = localRoots(top);
      }
      this.rootIds = new Set(Object.values(lroots).map((r) => r.id));
      if (!lroots.toolbar || !lroots.other) throw new Error('This browser\'s bookmarks bar or other bookmarks were not found');
      // which of the browser's folders stand for what: when that is not what the last sync went by (another folder is
      // the bar now, or a version of this extension that lined them up differently), what it remembers no longer
      // says what changed here. It starts over by bringing both sides together, which deletes nothing.
      const layout = [vivaldi ? 'vivaldi' : 'plain', lroots.toolbar.id, lroots.other.id, lroots.menu ? lroots.menu.id : ''].join(':');
      if (st.snap && st.layout !== layout) {
        if (vivaldi) await this.dropHidden(top, lroots);
        delete st.snap; delete st.map; delete st.roots; delete st.rev;
        mode = 'merge';
      }
      st.layout = layout;
      const first = !st.snap;

      // nothing changed here and nothing on the server: done, with one small request
      if (!first) {
        const local = this.localOps(lroots, st.roots || {}, canWrite);
        if (!local.ops.length) {
          const { rev } = await this.http('GET', '/rev');
          if (rev === st.rev) return { changed: false, pushed: 0 };
        }
      }

      const got = await this.http('GET', '/tree');
      let roots = serverRoots(got.tree, st.roots);
      if (first && madeBar && roots.toolbar) {  // what is on the server's bar and loose in Vivaldi's tree goes into the new bar folder
        const bar = got.tree.find((n) => n.id === roots.toolbar);
        const onBar = new Set((bar.children || []).filter((n) => !n.folder).map((n) => n.url));
        const atTop = new Set(got.tree.filter((n) => !n.folder).map((n) => n.url));
        this.applying = true;
        try {
          for (const c of lroots.other.children || []) {
            if (c.url !== undefined && onBar.has(c.url) && !atTop.has(c.url)) await this.bm.move(c.id, { parentId: lroots.toolbar.id }).catch(() => {});
          }
        } finally { this.applying = false; }
        [top] = await this.bm.getTree();
        lroots = localRoots(top);
      }
      if (first) {
        st.map = {};
        this.match(lroots, serverParts(got.tree, roots, lroots));
        st.snap = snapshot(got.tree);
        st.rev = got.rev;
      }
      st.roots = roots;
      const { ops } = canWrite ? this.localOps(lroots, roots, canWrite, first, mode) : { ops: [] };
      let res = got;
      if (ops.length) {
        res = await this.http('POST', '/sync', { base: st.rev, ops });
        for (const [ref, id] of Object.entries(res.ids || {})) {
          if (ref.startsWith('l:')) st.map[id] = ref.slice(2);
        }
        roots = serverRoots(res.tree, { ...roots, toolbar: res.ids['root:toolbar'] || roots.toolbar, menu: res.ids['root:menu'] || roots.menu });
        st.roots = roots;
      }
      [top] = await this.bm.getTree();
      lroots = localRoots(top);
      const changed = await this.apply(res.tree, lroots, roots, first && mode === 'server');
      st.snap = snapshot(res.tree);
      st.rev = res.rev;
      return { changed: changed || ops.length > 0, pushed: ops.length };
    }

    /** First sync: what is on both sides already, folder by name and link by address (and name, when it can). */
    match(lroots, parts) {
      const map = this.state.map;
      const pair = (lkids, skids) => {
        const taken = new Set();
        const pick = (pred) => skids.find((s) => !taken.has(s.id) && pred(s));
        for (const l of lkids) {
          if (isSep(l) || this.rootIds.has(l.id)) continue;
          let s;
          if (isFolder(l)) s = pick((s) => s.folder && s.title === l.title);
          else s = pick((s) => !s.folder && s.url === l.url && s.title === l.title) || pick((s) => !s.folder && s.url === l.url);
          if (!s) continue;
          taken.add(s.id);
          map[s.id] = l.id;
          if (s.folder) pair(l.children || [], s.children || []);
        }
      };
      for (const k of Object.keys(parts)) if (lroots[k]) pair(lroots[k].children || [], parts[k].children);
    }

    /** What changed in the browser since the snapshot, as ops (see app/bookmarkext.py). */
    localOps(lroots, roots, canWrite, first = false, mode = 'merge') {
      const st = this.state, snap = st.snap, ops = [];
      if (!canWrite || (first && mode === 'server')) return { ops };
      const l2s = {};
      for (const [sid, lid] of Object.entries(st.map || {})) l2s[lid] = Number(sid);
      const keyOf = {};  // a local folder -> its server parent value: an id, null (the top) or a ref
      const rootKey = { other: null, toolbar: roots.toolbar, menu: roots.menu };
      const seen = new Set();
      const placedIn = {};  // server id -> local folder id it is in now

      for (const kind of ['toolbar', 'menu']) {
        const lr = lroots[kind];
        if (lr && !roots[kind] && (lr.children || []).some((c) => !isSep(c))) {
          const ref = 'root:' + kind;
          ops.push({ op: 'create', ref, parent: null, folder: true, title: kind === 'toolbar' ? 'Bookmarks bar' : 'Bookmarks menu' });
          rootKey[kind] = ref;
        }
      }
      const orders = [];
      const walk = (lfolder, pkey, isNew) => {
        const childKeys = [];
        let movedIn = false;
        for (const c of lfolder.children || []) {
          if (isSep(c) || this.rootIds.has(c.id)) continue;  // Vivaldi's bar is a folder among the others
          const sid = l2s[c.id];
          const s = sid !== undefined && snap.nodes[sid];
          let key;
          if (s && s.f === isFolder(c)) {
            key = sid;
            seen.add(sid);
            placedIn[sid] = lfolder.id;
            if (!first) {
              const up = {};
              if ((c.title || '') !== s.t) up.title = c.title || '';
              if (!s.f && c.url !== s.u) up.url = c.url;
              if (Object.keys(up).length) ops.push({ op: 'update', id: sid, ...up });
            }
            if (K(s.p) !== K(pkey)) movedIn = true;
          } else if (sid !== undefined && !s) {
            key = sid;  // put here by a sync that was cut short: the server has it, the next tree says where it goes
          } else {
            key = 'l:' + c.id;
            ops.push({ op: 'create', ref: key, parent: pkey, folder: isFolder(c), title: c.title || '', ...(isFolder(c) ? {} : { url: c.url }) });
          }
          childKeys.push(key);
          if (isFolder(c)) walk(c, key, typeof key === 'string');
        }
        orders.push({ lfolder, pkey, childKeys, isNew, movedIn });
      };
      for (const kind of ['other', 'toolbar', 'menu']) {
        if (lroots[kind] && rootKey[kind] !== undefined) walk(lroots[kind], rootKey[kind], typeof rootKey[kind] === 'string');
      }
      if (!first) {
        for (const o of orders) {
          if (o.isNew && !o.movedIn) continue;  // made here in this order already
          const before = (snap.kids[K(o.pkey)] || []).filter((sid) => placedIn[sid] === o.lfolder.id);
          const now = o.childKeys;
          if (o.movedIn || before.length !== now.length || before.some((sid, i) => sid !== now[i])) {
            ops.push({ op: 'order', parent: o.pkey, ids: now });
          }
        }
        for (const [sid, lid] of Object.entries(st.map || {})) {
          if (snap.nodes[sid] && lid && !seen.has(Number(sid))) ops.push({ op: 'delete', id: Number(sid) });
        }
      }
      return { ops };
    }

    /** The browser's tree made the server's. Returns whether anything here changed. */
    async apply(tree, lroots, roots, dropOwn) {
      const st = this.state, bm = this.bm;
      const parts = serverParts(tree, roots, lroots);
      const alive = new Set();
      (function walk(list) { for (const n of list) { alive.add(n.id); if (n.folder) walk(n.children || []); } })(tree);
      const local = {};
      const index = (n) => { local[n.id] = n; for (const c of n.children || []) index(c); };
      for (const k of Object.keys(lroots)) index(lroots[k]);
      let changed = false;
      this.applying = true;
      try {
        // what was deleted on the server goes here first (a folder takes what is still in it)
        for (const sid of Object.keys(st.map)) {
          if (alive.has(Number(sid))) continue;
          const lid = st.map[sid];
          delete st.map[sid];
          if (!local[lid] || Object.values(lroots).some((r) => r.id === lid)) continue;
          await (isFolder(local[lid]) ? bm.removeTree(lid) : bm.remove(lid)).catch(() => {});
          changed = true;
        }
        const placed = new Set();
        const fill = async (lfolderId, skids, first = 0) => {
          for (let i = 0; i < skids.length; i++) {
            const s = skids[i], k = i + first;
            let lid = st.map[s.id];
            let l = lid && (await bm.get(lid).then((r) => r[0], () => null));
            if (l && isFolder(l) !== !!s.folder) l = null;
            const kids = await bm.getChildren(lfolderId);
            if (!l) {
              const made = await bm.create({ parentId: lfolderId, index: Math.min(k, kids.length), title: s.title || '', ...(s.folder ? {} : { url: s.url }) })
                .catch((e) => { this.log(`could not add "${s.title}": ${e.message}`); return null; });
              if (!made) continue;
              lid = made.id;
              st.map[s.id] = lid;
              changed = true;
            } else {
              const up = {};
              if ((l.title || '') !== (s.title || '')) up.title = s.title || '';
              if (!s.folder && l.url !== s.url) up.url = s.url;
              if (Object.keys(up).length) { await bm.update(lid, up).catch((e) => this.log(`could not change "${s.title}": ${e.message}`)); changed = true; }
              if (l.parentId !== lfolderId || kids.findIndex((c) => c.id === lid) !== k) {
                await bm.move(lid, { parentId: lfolderId, index: k }).catch((e) => this.log(`could not move "${s.title}": ${e.message}`));
                changed = true;
              }
            }
            placed.add(lid);
            if (s.folder) await fill(lid, s.children || []);
          }
        };
        for (const k of Object.keys(parts)) {
          let first = 0;
          if (k === 'other' && lroots.toolbar && lroots.toolbar.parentId === lroots.other.id) {  // Vivaldi: the bar stays first
            if ((await bm.getChildren(lroots.other.id)).findIndex((c) => c.id === lroots.toolbar.id) !== 0) await bm.move(lroots.toolbar.id, { parentId: lroots.other.id, index: 0 }).catch(() => {});
            first = 1;
          }
          await fill(lroots[k].id, parts[k].children, first);
        }
        if (dropOwn) {  // "use the server's": what only this browser had goes
          const mapped = new Set(Object.values(st.map));
          for (const k of Object.keys(parts)) {
            for (const c of await bm.getChildren(lroots[k].id)) await this.dropUnmapped(c, mapped);
          }
          changed = true;
        }
      } finally {
        this.applying = false;
      }
      return changed;
    }

    /** Vivaldi does not show its "Other Bookmarks" folder: what an earlier sync put there (it is on the server) goes. */
    async dropHidden(top, lroots) {
      const hidden = (top.children || []).find((c) => c.id === '2' || c.folderType === 'other');
      if (!hidden || hidden.id === lroots.other.id) return;
      const mine = new Set(Object.values(this.state.map || {}));
      this.applying = true;
      try {
        const drop = async (n) => {
          if (!mine.has(n.id)) return false;
          let all = true;
          for (const c of n.children || []) if (!(await drop(c))) all = false;
          if (all) await (isFolder(n) ? this.bm.removeTree(n.id) : this.bm.remove(n.id)).catch(() => {});
          return all;
        };
        for (const c of hidden.children || []) await drop(c);
      } finally { this.applying = false; }
    }

    async dropUnmapped(n, mapped) {
      if (isSep(n) || this.rootIds.has(n.id)) return;
      if (!mapped.has(n.id)) { await (isFolder(n) ? this.bm.removeTree(n.id) : this.bm.remove(n.id)).catch(() => {}); return; }
      if (isFolder(n)) for (const c of await this.bm.getChildren(n.id)) await this.dropUnmapped(c, mapped);
    }
  }

  const api = { Sync, localRoots, serverRoots, snapshot, isVivaldi };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.IoSync = api;
})(typeof self !== 'undefined' ? self : this);
