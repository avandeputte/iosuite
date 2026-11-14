import { S, api, avatar, h, icon } from './core.js';

// ------------------------------------------------------------------ the family tree
// <kin> pure functions (no DOM): who is how related to the viewed contact, which generation they are in, and where
// their card goes. tests/test_tree.py runs this block under node.
export const TREE = { W: 150, H: 136, GAP: 20, CGAP: 12, ROW: 206, PAD: 24 };
export const UP_STEP = { parent: 1, step_parent: 1, parent_in_law: 1, grandparent: 2, great_grandparent: 3, aunt_uncle: 1, godparent: 1,
  child: -1, step_child: -1, child_in_law: -1, grandchild: -2, great_grandchild: -3, niece_nephew: -1, godchild: -1 };
export const SPOUSE_TYPES = new Set(['spouse', 'partner', 'ex_spouse']);

// The relation a blood path "u generations up, then d down" reads as, for someone of `gender`.
export function kinWord(u, d, gender, flags = {}) {
  const g = (m, f, n) => (gender === 'M' ? m : gender === 'F' ? f : n);
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const greats = (k) => 'great-'.repeat(Math.max(0, k));
  const step = (w) => (flags.step ? `step${w.length > 6 ? '-' : ''}${w}` : w);
  if (u === 0 && d === 0) return 'This contact';
  if (d === 0) return cap(step(u === 1 ? g('father', 'mother', 'parent') : `${greats(u - 2)}grand${g('father', 'mother', 'parent')}`));
  if (u === 0) return cap(step(d === 1 ? g('son', 'daughter', 'child') : `${greats(d - 2)}grand${g('son', 'daughter', 'child')}`));
  if (u === 1 && d === 1) return cap(flags.half ? `half-${g('brother', 'sister', 'sibling')}` : step(g('brother', 'sister', 'sibling')));
  if (d === 1) return cap(`${greats(u - 2)}${g('uncle', 'aunt', 'aunt or uncle')}`);
  if (u === 1) return cap(`${d > 2 ? `${greats(d - 3)}grand` : ''}${g('nephew', 'niece', 'niece or nephew')}`);
  const deg = Math.min(u, d) - 1, rem = Math.abs(u - d);
  const ord = ['', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth'][deg] || `${deg}th`;
  const times = rem === 0 ? '' : [' once removed', ' twice removed', ' three times removed'][rem - 1] || ` ${rem} times removed`;
  return cap(`${deg === 1 ? '' : `${ord} `}cousin${times}`);
}

// One step of a blood path: from "u up, d down" over an edge of `type`, or null when the step says nothing certain.
export function bloodStep(type, u, d) {
  switch (type) {
    case 'parent': case 'step_parent': return d ? null : [u + 1, 0];
    case 'grandparent': return d ? null : [u + 2, 0];
    case 'great_grandparent': return d ? null : [u + 3, 0];
    case 'child': case 'step_child': return [u, d + 1];
    case 'grandchild': return [u, d + 2];
    case 'great_grandchild': return [u, d + 3];
    case 'sibling': case 'half_sibling': case 'step_sibling': return d ? [u, d] : [u + 1, 1];
    case 'aunt_uncle': return d ? null : [u + 2, 1];
    case 'niece_nephew': return d ? null : [u + 1, 2];
    case 'cousin': return d ? null : [u + 2, 2];
    default: return null;
  }
}

// g: {root, nodes, edges} from /api/contacts/{id}/family; famTypes: the family relation types; typeWord(type, gender);
// hidden: people left out of the drawing (a collapsed branch). Labels always cover everyone.
// Returns {gen, label, from, x, y, width, height, couples, sibGroups, families, order} for drawing; `from` says through whom
// each person was reached (a tree rooted at the viewed contact, which is what collapsing follows).
export function familyLayout(g, famTypes, typeWord, hidden = new Set()) {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const adj = new Map(g.nodes.map((n) => [n.id, []]));
  const seenEdge = new Set();
  const addEdge = (from, to, type, implied) => {
    const k = `${from}|${to}|${type}`;
    if (seenEdge.has(k) || !adj.has(from) || !adj.has(to) || from === to) return;
    seenEdge.add(k); adj.get(from).push({ to, type, implied });
  };
  const INV = { parent: 'child', child: 'parent', sibling: 'sibling', half_sibling: 'half_sibling', spouse: 'spouse', partner: 'partner',
    ex_spouse: 'ex_spouse', grandparent: 'grandchild', grandchild: 'grandparent', great_grandparent: 'great_grandchild',
    great_grandchild: 'great_grandparent', aunt_uncle: 'niece_nephew', niece_nephew: 'aunt_uncle', cousin: 'cousin',
    parent_in_law: 'child_in_law', child_in_law: 'parent_in_law', sibling_in_law: 'sibling_in_law', step_parent: 'step_child',
    step_child: 'step_parent', step_sibling: 'step_sibling', godparent: 'godchild', godchild: 'godparent', relative: 'relative' };
  const fam = g.edges.filter((e) => famTypes.has(e.type));
  // stored relations first (they come with their inverse), then what the server inferred for the root
  for (const e of fam.filter((x) => !x.implied)) { addEdge(e.from, e.to, e.type, false); if (INV[e.type]) addEdge(e.to, e.from, INV[e.type], false); }
  for (const e of fam.filter((x) => x.implied)) addEdge(e.from, e.to, e.type, true);

  // --- labels relative to the root: blood paths, then spouses, then the spouses' blood relatives, then anything else
  const lab = new Map([[g.root, { segs: [], gen: 0, from: null }]]);
  const order = [g.root];
  const put = (id, v) => { lab.set(id, v); order.push(id); };
  const bloodFrom = (seed) => {
    const base = lab.get(seed), found = [];
    const st = new Map([[seed, { u: 0, d: 0, step: false, half: false }]]);
    const q = [seed];
    while (q.length) {
      const cur = q.shift(), s = st.get(cur);
      for (const e of adj.get(cur)) {
        if (st.has(e.to) || lab.has(e.to)) continue;
        const nx = bloodStep(e.type, s.u, s.d);
        if (!nx) continue;
        const ns = { u: nx[0], d: nx[1], step: s.step || e.type.startsWith('step_'), half: s.half || e.type === 'half_sibling' };
        st.set(e.to, ns); q.push(e.to);
        if (ns.u === 0 && ns.d === 0) continue;
        put(e.to, { segs: [...base.segs, { kind: 'blood', u: ns.u, d: ns.d, step: ns.step, half: ns.half, id: e.to }], gen: base.gen + ns.u - ns.d, from: cur });
        found.push(e.to);
      }
    }
    return found;
  };
  let fresh = [g.root, ...bloodFrom(g.root)];
  for (let guard = 0; guard < 8 && fresh.length; guard++) {
    const next = [];
    for (const id of fresh) {
      for (const e of adj.get(id)) {
        if (!SPOUSE_TYPES.has(e.type) || lab.has(e.to)) continue;
        const b = lab.get(id);
        put(e.to, { segs: [...b.segs, { kind: 'spouse', type: e.type, id: e.to }], gen: b.gen, from: id });
        next.push(e.to, ...bloodFrom(e.to));
      }
    }
    if (!next.length) {
      // nothing left over a spouse: one step over any other family relation (godparents, in-laws, "relative"…)
      for (const id of [...order]) {
        for (const e of adj.get(id)) {
          if (lab.has(e.to)) continue;
          const b = lab.get(id);
          put(e.to, { segs: [...b.segs, { kind: 'type', type: e.type, id: e.to }], gen: b.gen + (UP_STEP[e.type] || 0), from: id });
          next.push(e.to, ...bloodFrom(e.to));
        }
      }
    }
    fresh = next;
  }

  const gender = (id) => (byId.get(id) || {}).gender;
  const segWord = (s) => (s.kind === 'blood' ? kinWord(s.u, s.d, gender(s.id), s) : typeWord(s.type, gender(s.id)));
  const label = new Map();
  for (const [id, v] of lab) {
    const segs = v.segs, words = [];
    for (let i = 0; i < segs.length; i++) {
      const a = segs[i], b = segs[i + 1], gw = (m, f, n) => (gender(b && b.id) === 'M' ? m : gender(b && b.id) === 'F' ? f : n);
      const isB = (s, u, d) => s && s.kind === 'blood' && s.u === u && s.d === d && !s.step;
      const isSp = (s) => s && s.kind === 'spouse' && s.type !== 'ex_spouse';
      let w = null;
      if (isB(a, 1, 1) && isSp(b)) w = gw('Brother-in-law', 'Sister-in-law', 'Sibling-in-law');
      else if (isB(a, 0, 1) && isSp(b)) w = gw('Son-in-law', 'Daughter-in-law', 'Child-in-law');
      else if (isB(a, 1, 0) && isSp(b)) w = gw('Stepfather', 'Stepmother', 'Step-parent');
      else if (a.kind === 'blood' && a.d === 1 && a.u >= 2 && isSp(b)) w = `${kinWord(a.u, 1, gender(b.id))} by marriage`;
      else if (isSp(a) && isB(b, 1, 0)) w = gw('Father-in-law', 'Mother-in-law', 'Parent-in-law');
      else if (isSp(a) && isB(b, 1, 1)) w = gw('Brother-in-law', 'Sister-in-law', 'Sibling-in-law');
      else if (isSp(a) && isB(b, 0, 1)) w = gw('Stepson', 'Stepdaughter', 'Stepchild');
      if (w) { words.push(w); i++; } else words.push(segWord(a));
    }
    label.set(id, id === g.root ? 'This contact' : words.map((w, i) => (i ? w.charAt(0).toLowerCase() + w.slice(1) : w)).join("'s "));
  }
  const from = new Map([...lab].map(([id, v]) => [id, v.from]));
  // whose branch starts folded: people who married into a relative's family (a nephew's wife: her own family), and
  // cousins and anyone further out (their spouses and children)
  const far = new Set([...lab].filter(([, v]) => {
    const t = v.segs[v.segs.length - 1];
    return t && ((v.segs.length >= 2 && t.kind !== 'blood') || (t.kind === 'blood' && t.u >= 2 && t.d >= 2));
  }).map(([id]) => id));
  const gen = new Map([...lab].filter(([id]) => id === g.root || !hidden.has(id)).map(([id, v]) => [id, v.gen]));

  // --- structure to draw: parent-child links (stored, plus siblings sharing a parent), couples, sibling groups
  const parents = new Map([...gen.keys()].map((id) => [id, new Set()]));
  for (const [id, list] of adj) {
    if (!gen.has(id)) continue;
    for (const e of list) {
      if (e.implied || !gen.has(e.to)) continue;
      if (e.type === 'child' || e.type === 'step_child') parents.get(e.to).add(id);
      if (e.type === 'parent' || e.type === 'step_parent') parents.get(id).add(e.to);
    }
  }
  for (let pass = 0; pass < 2; pass++) {
    for (const [id, list] of adj) {
      if (!gen.has(id)) continue;
      for (const e of list) if (!e.implied && e.type === 'sibling' && gen.has(e.to)) for (const p of parents.get(id)) parents.get(e.to).add(p);
    }
  }
  const children = new Map([...gen.keys()].map((id) => [id, new Set()]));
  for (const [c, ps] of parents) for (const p of ps) children.get(p).add(c);

  const rowsOf = new Map();
  for (const id of order) { if (!gen.has(id)) continue; const r = gen.get(id); if (!rowsOf.has(r)) rowsOf.set(r, []); rowsOf.get(r).push(id); }
  const gens = [...rowsOf.keys()].sort((a, b) => b - a);
  const born = (id) => ((byId.get(id) || {}).birthday || {}).year || 9999;
  const stored = (id, pred) => adj.get(id).filter((e) => !e.implied && gen.has(e.to) && pred(e));

  // --- units: a couple (or someone alone) drawn side by side; the member order is settled when the unit is placed
  const unitOf = new Map(), units = [], couples = [];
  for (const r of gens) {
    for (const id of rowsOf.get(r)) {
      if (unitOf.has(id)) continue;
      const sp = stored(id, (e) => SPOUSE_TYPES.has(e.type) && e.type !== 'ex_spouse' && gen.get(e.to) === r && !unitOf.has(e.to))[0]
        || stored(id, (e) => e.type === 'ex_spouse' && gen.get(e.to) === r && !unitOf.has(e.to))[0];
      const u = { ids: sp ? [id, sp.to] : [id], gen: r };
      if (sp) couples.push({ a: id, b: sp.to, ex: sp.type === 'ex_spouse' });
      u.ids.forEach((m) => unitOf.set(m, u)); units.push(u);
    }
  }
  // brothers and sisters with no parent in the tree: kept together under a bracket
  const sibRoot = new Map();
  const find = (a) => { while (sibRoot.get(a) !== a) a = sibRoot.get(a); return a; };
  for (const id of gen.keys()) sibRoot.set(id, id);
  for (const id of gen.keys()) {
    if (parents.get(id).size) continue;
    for (const e of stored(id, (x) => (x.type === 'sibling' || x.type === 'half_sibling') && gen.get(x.to) === gen.get(id) && !parents.get(x.to).size)) sibRoot.set(find(id), find(e.to));
  }
  const groups = new Map();
  for (const id of gen.keys()) { const r = find(id); if (!groups.has(r)) groups.set(r, []); groups.get(r).push(id); }
  const sibOf = new Map();  // person -> their group (only groups of two or more)
  for (const g2 of groups.values()) if (g2.length > 1) g2.forEach((id) => sibOf.set(id, g2));
  const sibGroups = [];

  // --- blocks: cards with x positions relative to the block, and per-row extents so blocks nest closely
  const W = TREE.W, GAP = TREE.GAP, CGAP = TREE.CGAP;
  const x = new Map();
  const mkBlock = () => ({ cards: [], rows: new Map() });
  const rowOf = (B, r) => { if (!B.rows.has(r)) B.rows.set(r, []); return B.rows.get(r); };
  const addCard = (B, id, r, left) => { B.cards.push(id); x.set(id, left); rowOf(B, r).push(id); };
  const extent = (B, r) => { const ids = B.rows.get(r); return ids && ids.length ? [Math.min(...ids.map((i) => x.get(i))), Math.max(...ids.map((i) => x.get(i))) + W] : null; };
  const shift = (B, d) => { for (const id of B.cards) x.set(id, x.get(id) + d); };
  const merge = (A, B) => { A.cards.push(...B.cards); for (const [r, ids] of B.rows) rowOf(A, r).push(...ids); return A; };
  // B to the right of A, as close as the rows allow
  const hcat = (A, B, gap = GAP) => {
    if (!A.cards.length) return B;
    if (!B.cards.length) return A;
    let d = -Infinity, common = false;
    for (const r of B.rows.keys()) { const ea = extent(A, r), eb = extent(B, r); if (ea && eb) { common = true; d = Math.max(d, ea[1] + gap - eb[0]); } }
    if (!common) d = Math.max(...A.cards.map((i) => x.get(i))) + W + gap - Math.min(...B.cards.map((i) => x.get(i)));
    shift(B, d);
    return merge(A, B);
  };
  // the nearest place for a strip [left, left + w] on row r of B that overlaps none of its cards
  const freeSpot = (B, r, left, w) => {
    const taken = (B.rows.get(r) || []).map((i) => [x.get(i) - GAP, x.get(i) + W + GAP]).sort((p, q) => p[0] - q[0]);
    const clash = (l) => taken.some(([a, b]) => l < b && l + w > a);
    if (!clash(left)) return left;
    let l = left, rgt = left;
    for (let i = 0; i < 50 && (clash(l) || clash(rgt)); i++) { if (clash(l)) l = Math.min(...taken.filter(([a, b]) => l < b && l + w > a).map(([a]) => a)) - w; if (clash(rgt)) rgt = Math.max(...taken.filter(([a, b]) => rgt < b && rgt + w > a).map(([, b]) => b)); }
    return left - l <= rgt - left ? l : rgt;
  };
  const cx = (id) => x.get(id) + W / 2;

  const placed = new Set();
  // the block of unit U and everything hanging off it: its children below (and their families), its members' parents
  // above (with the members' brothers and sisters beside). `via`: the child block being wrapped, with the member it
  // hangs from; `side`: where U's other children go relative to that block (left, right, or both by birth order).
  const expand = (U, lead, via = null, side = 'both') => {
    placed.add(U);
    if (U.virtual) {
      // no cards: just the brothers and sisters of `via` beside it
      const group = U.children.filter((c) => !placed.has(unitOf.get(c)) || unitOf.get(c) === via.unit);
      const blocks = rowBlocks(group, via, side);
      const K = blocks.reduce((acc, b) => hcat(acc, b), mkBlock());
      sibGroups.push(group.filter((c) => K.cards.includes(c)).sort((a, b) => cx(a) - cx(b)));
      return K;
    }
    // member order: the one we came through first, otherwise the man on the left (his side of the family goes left)
    const ids = [...U.ids];
    if (lead != null && ids.indexOf(lead) === 1) ids.reverse();
    else if (lead == null && ids.length === 2 && (byId.get(ids[1]) || {}).gender === 'M' && (byId.get(ids[0]) || {}).gender !== 'M') ids.reverse();
    U.ids = ids;
    const uw = ids.length * W + (ids.length - 1) * CGAP;
    // children: every child of a member, one row down, as a unit each (a child and their spouse)
    const kidIds = [];
    for (const m of ids) for (const c of children.get(m)) if (gen.get(c) === U.gen - 1 && !kidIds.includes(c)) kidIds.push(c);
    const mine = kidIds.filter((c) => !placed.has(unitOf.get(c)) || (via && unitOf.get(c) === via.unit));
    let B;
    if (mine.length) {
      const K = rowBlocks(mine, via, side).reduce((acc, b) => hcat(acc, b), mkBlock());
      const members = mine.filter((c) => K.cards.includes(c));
      const mid = (Math.min(...members.map(cx)) + Math.max(...members.map(cx))) / 2;
      // the parents themselves go over the middle of their children: both of a couple, or just the one who is the parent
      const who = ids.filter((m) => members.some((c) => parents.get(c).has(m)));
      const anchor = (who.length ? who : ids).reduce((t, m) => t + ids.indexOf(m) * (W + CGAP) + W / 2, 0) / (who.length || ids.length);
      const left = freeSpot(K, U.gen, mid - anchor, uw);
      ids.forEach((m, i) => addCard(K, m, U.gen, left + i * (W + CGAP)));
      B = K;
    } else {
      B = mkBlock();
      ids.forEach((m, i) => addCard(B, m, U.gen, i * (W + CGAP)));
    }
    // up: each member's parents (one unit, or two when they split up), and parentless siblings
    ids.forEach((m, i) => {
      const mside = ids.length === 1 ? 'both' : i === 0 ? 'left' : 'right';
      const pus = [];
      for (const p of parents.get(m)) { const pu = unitOf.get(p); if (pu && gen.get(p) === U.gen + 1 && !placed.has(pu) && !pus.includes(pu)) pus.push(pu); }
      if (!pus.length && !parents.get(m).size && sibOf.get(m) && !sibOf.get(m).done) { sibOf.get(m).done = true; pus.push({ virtual: true, children: sibOf.get(m), gen: U.gen + 1 }); }
      for (const pu of pus) B = expand(pu, null, { block: B, unit: U, member: m }, mside);
    });
    return B;
  };
  // the blocks of a row of children (each expanded downwards), in birth order, with the wrapped block among them
  const rowBlocks = (kidIds, via, side) => {
    const out = [];
    const sorted = [...kidIds].sort((a, b) => born(a) - born(b));
    const viaKid = via ? sorted.find((c) => unitOf.get(c) === via.unit) : null;
    for (const c of sorted) {
      if (c === viaKid) { out.push({ block: via.block, kid: c }); continue; }
      const cu = unitOf.get(c);
      if (placed.has(cu)) continue;
      out.push({ block: expand(cu, c), kid: c });
    }
    if (!viaKid) return out.map((o) => o.block);
    const i = out.findIndex((o) => o.kid === viaKid), others = out.filter((o) => o.kid !== viaKid).map((o) => o.block);
    if (side === 'left') return [...others, via.block];
    if (side === 'right') return [via.block, ...others];
    return [...others.slice(0, i), via.block, ...others.slice(i)];
  };
  let main = expand(unitOf.get(g.root), g.root);
  // whoever is left (reached over a godparent, a "relative", an aunt with no parent link…): beside the tree, on their row
  for (const id of order) {
    const u = unitOf.get(id);
    if (!u || placed.has(u)) continue;
    main = hcat(main, expand(u, id), GAP * 2);
  }
  for (const u of units) if (!placed.has(u)) u.ids.forEach((m, i) => { x.set(m, (main.cards.length ? Math.max(...main.cards.map((c) => x.get(c))) + W + GAP : 0) + i * (W + CGAP)); main.cards.push(m); });
  const minX = Math.min(...x.values());
  for (const [id, v] of x) x.set(id, Math.round(v - minX + TREE.PAD));
  const y = new Map([...gen].map(([id, r]) => [id, TREE.PAD + gens.indexOf(r) * TREE.ROW]));
  const width = Math.max(...x.values()) + TREE.W + TREE.PAD, height = TREE.PAD * 2 + (gens.length - 1) * TREE.ROW + TREE.H;
  const families = new Map();
  for (const [c, ps] of parents) { if (!ps.size) continue; const k = [...ps].sort((a, b) => a - b).join(','); if (!families.has(k)) families.set(k, { parents: [...ps], children: [] }); families.get(k).children.push(c); }
  // each family's horizontal line gets its own lane between the two rows, so lines of different families never run together
  const fams = [...families.values()];
  const span = (f) => { const xs = [...f.parents, ...f.children].map(cx); return [Math.min(...xs), Math.max(...xs)]; };
  const lanes = new Map();
  for (const f of fams.sort((a, b) => span(a)[0] - span(b)[0])) {
    const k = Math.max(...f.parents.map((p) => gen.get(p)));
    if (!lanes.has(k)) lanes.set(k, []);
    const used = lanes.get(k), [lo, hi] = span(f);
    let lane = 0;
    while (used.some((o) => o.lane === lane && o.lo - 12 < hi && lo < o.hi + 12)) lane++;
    used.push({ lane, lo, hi }); f.lane = lane;
  }
  for (const f of fams) f.lanes = lanes.get(Math.max(...f.parents.map((p) => gen.get(p)))).reduce((m, o) => Math.max(m, o.lane + 1), 0);
  return { gen, label, from, far, x, y, width, height, gens, couples, sibGroups, families: fams, order: order.filter((id) => gen.has(id)) };
}
// </kin>

export const treeFolds = new Map();  // root id -> the people whose branch is folded (kept while the app is open)

export async function showTree(page, r) {
  const g = await api(`api/contacts/${r.id}/family?depth=4`);
  const types = S.rel.groups[0].types;
  const famTypes = new Set(types.map((t) => t.type));
  const typeWord = (t, gender) => { const x = types.find((y) => y.type === t); return x ? (gender === 'M' ? x.male : gender === 'F' ? x.female : x.label) : t; };
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const root = byId.get(g.root);
  page.classList.add('treepage');
  const head = h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: `#/c/${g.root}` }, icon('back')), h('h1', null, `${root.fn}'s family`));
  let L = familyLayout(g, famTypes, typeWord);
  if (L.gen.size < 2) {
    page.append(head, h('div', { class: 'empty' }, h('p', null, 'No family relations to other contacts yet. Edit the contact and add parents, siblings, children…')));
    return;
  }
  // the branches: who was reached through whom
  const kids = new Map();
  for (const [id, f] of L.from) if (f != null) { if (!kids.has(f)) kids.set(f, []); kids.get(f).push(id); }
  const below = (id, out = []) => { for (const k of kids.get(id) || []) { out.push(k); below(k, out); } return out; };
  if (!treeFolds.has(g.root)) treeFolds.set(g.root, new Set([...L.far].filter((id) => kids.has(id))));
  const folds = treeFolds.get(g.root);
  const hiddenNow = () => { const hd = new Set(); for (const f of folds) if (!hd.has(f)) below(f).forEach((k) => hd.add(k)); return hd; };

  const { W, H } = TREE;
  const NS = 'http://www.w3.org/2000/svg';
  const canvas = h('div', { class: 'ftree-canvas' });
  const view = h('div', { class: 'ftree' }, canvas);
  const zoomLbl = h('span', { class: 'zl' });
  let s = 1, tx = 0, ty = 0;
  const apply = () => { canvas.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`; zoomLbl.textContent = `${Math.round(s * 100)}%`; };
  const zoomAt = (k, px, py) => {
    const ns = Math.min(2, Math.max(0.1, s * k));
    tx = px - (px - tx) * (ns / s); ty = py - (py - ty) * (ns / s); s = ns; apply();
  };
  const center = () => {
    const vw = view.clientWidth, vh = view.clientHeight;
    tx = vw / 2 - (L.x.get(g.root) + W / 2) * s; ty = vh / 2 - (L.y.get(g.root) + H / 2) * s; apply();
  };
  const fit = () => {
    const vw = view.clientWidth, vh = view.clientHeight;
    s = Math.min(1, Math.max(0.1, Math.min(vw / L.width, vh / L.height)));
    tx = (vw - L.width * s) / 2; ty = (vh - L.height * s) / 2; apply();
  };

  const draw = () => {
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', L.width); svg.setAttribute('height', L.height); svg.setAttribute('class', 'ftree-lines');
    const line = (pts, cls = '') => { const p = document.createElementNS(NS, 'polyline'); p.setAttribute('points', pts.map((q) => q.join(',')).join(' ')); if (cls) p.setAttribute('class', cls); svg.append(p); };
    const X = (id) => L.x.get(id), Y = (id) => L.y.get(id);
    const coupleOf = new Map(); L.couples.forEach((c) => { coupleOf.set(c.a, c); coupleOf.set(c.b, c); });
    for (const c of L.couples) {
      const [a, b] = X(c.a) < X(c.b) ? [c.a, c.b] : [c.b, c.a];
      line([[X(a) + W, Y(a) + H / 2], [X(b), Y(b) + H / 2]], c.ex ? 'ex' : '');
    }
    for (const f of L.families) {
      const c = f.parents.length === 2 && coupleOf.get(f.parents[0]) === coupleOf.get(f.parents[1]) ? coupleOf.get(f.parents[0]) : null;
      const pBottom = Math.max(...f.parents.map((p) => Y(p) + H));
      const cTop = Math.min(...f.children.map(Y));
      const step = Math.min(16, (cTop - pBottom - 16) / Math.max(1, f.lanes));
      const bus = Math.max(pBottom + 8, (pBottom + cTop) / 2 + (f.lane - (f.lanes - 1) / 2) * step);
      const xs = [];
      if (c) { const ox = (Math.min(X(c.a), X(c.b)) + W + Math.max(X(c.a), X(c.b))) / 2; xs.push(ox); line([[ox, Y(c.a) + H / 2], [ox, bus]]); }
      else for (const p of f.parents) { const ox = X(p) + W / 2; xs.push(ox); line([[ox, Y(p) + H], [ox, bus]]); }
      for (const ch of f.children) { const ox = X(ch) + W / 2; xs.push(ox); line([[ox, bus], [ox, Y(ch)]]); }
      line([[Math.min(...xs), bus], [Math.max(...xs), bus]]);
    }
    for (const sg of L.sibGroups) {
      const top = Y(sg[0]) - 14, xs = sg.map((id) => X(id) + W / 2);
      line([[Math.min(...xs), top], [Math.max(...xs), top]], 'sib');
      xs.forEach((ox, i) => line([[ox, top], [ox, Y(sg[i])]], 'sib'));
    }
    canvas.style.width = `${L.width}px`; canvas.style.height = `${L.height}px`;
    canvas.replaceChildren(svg, ...L.order.map((id) => {
      const n = byId.get(id), isRoot = id === g.root, folded = folds.has(id), n2 = kids.has(id) ? below(id).length : 0;
      const nm = n.given && n.family ? [n.given, n.family] : (n.fn || '').includes(' ') ? [n.fn.slice(0, n.fn.indexOf(' ')), n.fn.slice(n.fn.indexOf(' ') + 1)] : [n.fn || '', ''];
      return h('a', { class: `fcard ${isRoot ? 'root' : ''}`, draggable: 'false', style: { left: `${X(id)}px`, top: `${Y(id)}px`, width: `${W}px`, height: `${H}px` },
        href: isRoot ? `#/c/${id}` : `#/tree/${id}`, title: isRoot ? 'Open the contact' : `${n.fn}: ${L.label.get(id)}. Show the tree from their side` },
      avatar({ id, fn: n.fn, hasPhoto: n.hasPhoto, iopixPersonId: n.iopixPersonId }),
      h('div', { class: 'fbody' }, h('b', null, nm[0]), nm[1] ? h('b', null, nm[1]) : null, h('div', { class: 'muted small rel' }, L.label.get(id)),
        n.birthday && n.birthday.year ? h('div', { class: 'muted small' }, `born ${n.birthday.year}`) : null),
      n2 && !isRoot ? h('button', { class: `fold ${folded ? 'on' : ''}`, title: folded ? `Show the ${n2} relatives reached through ${n.fn}` : `Hide the ${n2} relatives reached through ${n.fn}`,
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); toggle(id); } }, folded ? `+${n2}` : '−') : null);
    }));
  };
  const relayout = (keep) => {
    // keep the card that was clicked (or the contact) where it is on screen
    const ox = L.x.get(keep), oy = L.y.get(keep);
    L = familyLayout(g, famTypes, typeWord, hiddenNow());
    draw();
    tx += (ox - L.x.get(keep)) * s; ty += (oy - L.y.get(keep)) * s; apply();
  };
  const toggle = (id) => { if (folds.has(id)) folds.delete(id); else folds.add(id); relayout(id); };

  // pan with a drag or two-finger scroll, zoom with a pinch, ctrl/⌘ + wheel or the buttons
  const pts = new Map();
  let dragged = false, pinch = null;
  view.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button')) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY });
    if (pts.size === 1) dragged = false;
    if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = Math.hypot(a.x - b.x, a.y - b.y); }
  });
  view.addEventListener('pointermove', (e) => {
    const p = pts.get(e.pointerId);
    if (!p) return;
    if (pts.size === 2 && pinch) {
      p.x = e.clientX; p.y = e.clientY;
      const [a, b] = [...pts.values()], d = Math.hypot(a.x - b.x, a.y - b.y), rc = view.getBoundingClientRect();
      zoomAt(d / pinch, (a.x + b.x) / 2 - rc.left, (a.y + b.y) / 2 - rc.top); pinch = d; dragged = true;
      return;
    }
    if (!dragged && Math.hypot(e.clientX - p.x0, e.clientY - p.y0) < 5) return;
    if (!dragged) { dragged = true; view.setPointerCapture(e.pointerId); view.classList.add('grabbing'); }
    tx += e.clientX - p.x; ty += e.clientY - p.y; p.x = e.clientX; p.y = e.clientY; apply();
  });
  const up = (e) => { pts.delete(e.pointerId); if (pts.size < 2) pinch = null; if (!pts.size) view.classList.remove('grabbing'); };
  view.addEventListener('pointerup', up); view.addEventListener('pointercancel', up);
  view.addEventListener('click', (e) => { if (dragged) { e.preventDefault(); e.stopPropagation(); dragged = false; } }, true);
  view.addEventListener('wheel', (e) => {
    e.preventDefault();
    const rc = view.getBoundingClientRect();
    if (e.ctrlKey || e.metaKey) zoomAt(Math.exp(-Math.max(-60, Math.min(60, e.deltaY)) * 0.01), e.clientX - rc.left, e.clientY - rc.top);
    else if (e.deltaMode === 1) zoomAt(Math.exp(-Math.max(-6, Math.min(6, e.deltaY)) * 0.1), e.clientX - rc.left, e.clientY - rc.top);  // a mouse wheel that scrolls by lines
    else { tx -= e.deltaX; ty -= e.deltaY; apply(); }
  }, { passive: false });
  const mid = (k) => zoomAt(k, view.clientWidth / 2, view.clientHeight / 2);
  const tb = (label, title, fn) => h('button', { class: 'pillbtn', title, onclick: fn }, label);
  const bar = h('div', { class: 'ftree-bar' },
    tb('−', 'Zoom out', () => mid(1 / 1.25)), zoomLbl, tb('+', 'Zoom in', () => mid(1.25)),
    tb('Fit', 'Show the whole tree', fit), tb(`Center`, `Back to ${root.fn}`, center),
    tb('Expand all', 'Show everyone', () => { folds.clear(); relayout(g.root); }),
    tb('Collapse', 'Fold away cousins\' families and the families of people who married in', () => { folds.clear(); L.far.forEach((id) => kids.has(id) && folds.add(id)); relayout(g.root); }));
  page.append(head, h('div', { class: 'ftree-top' }, h('p', { class: 'muted small' },
    `Labels say how everyone is related to ${root.fn}. Drag to move, pinch or ctrl/⌘ + scroll to zoom, click someone to see the tree from their side; + and − on a card show or hide the relatives reached through them.`), bar), view);
  L = familyLayout(g, famTypes, typeWord, hiddenNow());
  draw();
  requestAnimationFrame(() => { s = Math.min(1, Math.max(0.85, Math.min(view.clientWidth / L.width, view.clientHeight / L.height))); center(); });
}
