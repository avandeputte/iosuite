/* A browser's bookmarks API, in memory, for the tests: Chrome's shape (ids "0", "1", "2"; folders have no type) or
 * Firefox's (toolbar_____, menu________, unfiled_____; type on every node, separators), or Vivaldi's (Chrome's, with a
 * Trash and the flags speeddial / bookmarkbar on every node; set them with flag()). */
'use strict';

class FakeBookmarks {
  constructor(kind = 'chrome') {
    this.kind = kind;
    this.n = 100;
    this.calls = 0;  // changes made through the API (what a sync did to the browser)
    this.nodes = {};
    const root = this._add({ id: kind !== 'firefox' ? '0' : 'root________', title: '', folder: true, parentId: undefined });
    const tops = kind === 'vivaldi'
      ? [['1', 'Bookmarks', 'bookmarks-bar'], ['2', 'Other Bookmarks', 'other'], ['3', 'Mobile Bookmarks', 'mobile'], ['4', 'Trash']]
      : kind === 'chrome'
      ? [['1', 'Bookmarks bar', 'bookmarks-bar'], ['2', 'Other bookmarks', 'other'], ['3', 'Mobile bookmarks', 'mobile']]
      : [['menu________', 'Bookmarks Menu'], ['toolbar_____', 'Bookmarks Toolbar'], ['unfiled_____', 'Other Bookmarks'], ['mobile______', 'Mobile Bookmarks']];
    for (const [id, title, folderType] of tops) this._add({ id, title, folder: true, parentId: root.id, folderType });
    this.rootId = root.id;
  }

  _add({ id, title, url, folder, parentId, index, folderType, separator }) {
    const n = { id: id || String(++this.n), title: title || '', parentId, kids: folder ? [] : undefined, url: folder || separator ? undefined : url, folderType, separator };
    this.nodes[n.id] = n;
    if (parentId !== undefined) {
      const k = this.nodes[parentId].kids;
      k.splice(index === undefined ? k.length : index, 0, n.id);
    }
    return n;
  }

  _out(n, deep) {
    const o = { id: n.id, title: n.title };
    if (n.parentId !== undefined) { o.parentId = n.parentId; o.index = this.nodes[n.parentId].kids.indexOf(n.id); }
    if (n.url !== undefined) o.url = n.url;
    if (n.folderType && this.kind !== 'firefox') o.folderType = n.folderType;
    if (this.kind === 'vivaldi') { o.trash = n.id === '4'; o.speeddial = !!n.speeddial; o.bookmarkbar = !!n.bookmarkbar; }
    if (this.kind === 'firefox') o.type = n.separator ? 'separator' : n.kids ? 'folder' : 'bookmark';
    if (n.kids && deep) o.children = n.kids.map((id) => this._out(this.nodes[id], true));
    return o;
  }

  _need(id) {
    const n = this.nodes[id];
    if (!n) throw new Error(`Can't find bookmark for id ${id}`);
    return n;
  }

  async getTree() { return [this._out(this.nodes[this.rootId], true)]; }
  async get(id) { return [this._out(this._need(id))]; }
  async getChildren(id) { return this._need(id).kids.map((c) => this._out(this.nodes[c])); }

  async create({ parentId, index, title, url, type }) {
    const p = this._need(parentId);
    if (!p.kids || p.id === this.rootId) throw new Error('Cannot add there');
    this.calls++;
    return this._out(this._add({ title, url, folder: url === undefined && type !== 'separator', separator: type === 'separator', parentId, index }));
  }

  async update(id, { title, url }) {
    const n = this._need(id);
    if (n.parentId === this.rootId) throw new Error('Cannot change a root folder');
    this.calls++;
    if (title !== undefined) n.title = title;
    if (url !== undefined) n.url = url;
    return this._out(n);
  }

  async move(id, { parentId, index }) {
    const n = this._need(id);
    if (n.parentId === this.rootId) throw new Error('Cannot move a root folder');
    const to = this._need(parentId === undefined ? n.parentId : parentId);
    const from = this.nodes[n.parentId].kids;
    const old = from.indexOf(id);
    from.splice(old, 1);
    let at = index === undefined ? to.kids.length : index;
    if (to.id === n.parentId && at > old && this.kind !== 'firefox') at--;  // Chrome counts the place before taking it out
    to.kids.splice(Math.min(at, to.kids.length), 0, id);
    n.parentId = to.id;
    this.calls++;
    return this._out(n);
  }

  async remove(id) {
    const n = this._need(id);
    if (n.kids && n.kids.length) throw new Error('Folder is not empty');
    return this.removeTree(id);
  }

  async removeTree(id) {
    const n = this._need(id);
    if (n.parentId === this.rootId || id === this.rootId) throw new Error('Cannot remove a root folder');
    this.calls++;
    const drop = (x) => { for (const c of x.kids || []) drop(this.nodes[c]); delete this.nodes[x.id]; };
    const k = this.nodes[n.parentId].kids;
    k.splice(k.indexOf(id), 1);
    drop(n);
  }

  flag(id, name) { this._need(id)[name] = true; }

  /** The tree under a top folder as text, for asserting: "Folder[a,b],link". */
  show(topId) {
    const f = (id) => { const n = this.nodes[id]; return n.separator ? '---' : n.kids ? `${n.title}[${n.kids.map(f).join(',')}]` : n.title; };
    return this.nodes[topId].kids.map(f).join(',');
  }
}

module.exports = { FakeBookmarks };
