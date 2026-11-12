/* The settings page: signing in (one click: the start page asks whoever is signed in there to say yes, and hands
 * this extension an app password of its own), the state of the sync, signing out. */
'use strict';
let waiting = null;  // the sign-in under way: {stop}

async function show() {
  const { account, status, sync } = await ext.storage.local.get(['account', 'status', 'sync']);
  $('in').hidden = !account;
  $('out').hidden = !!account;
  if (!account) return;
  const d = describe(account, status);
  $('dot').className = 'dot ' + d.cls;
  $('state').textContent = d.text;
  const vivaldi = sync && String(sync.layout || '').startsWith('vivaldi');
  $('who').textContent = `Signed in as ${account.user} at ${account.server}` + (vivaldi ? ' · lined up for Vivaldi' : '') + (account.canWrite === false ? '. This account can read the bookmarks, not change them: changes made here are not kept.' : '');
}

function address(text) {
  let t = (text || '').trim();
  if (!t) throw new Error('Type the address of your start page');
  if (!/^https?:\/\//i.test(t)) t = 'https://' + t;
  let u;
  try { u = new URL(t); } catch (e) { throw new Error('That is not an address'); }
  return (u.origin + u.pathname).replace(/\/+$/, '');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function signIn() {
  $('error').textContent = '';
  let server;
  try { server = address($('server').value); } catch (e) { $('error').textContent = e.message; return; }
  const mode = document.querySelector('input[name="mode"]:checked').value;
  // the browser asks whether this extension may talk to that one site (asked here, on the click)
  const granted = await ext.permissions.request({ origins: [new URL(server).origin + '/*'] }).catch(() => false);
  if (!granted) { $('error').textContent = 'The browser did not allow the extension to reach that address.'; return; }
  $('signin').disabled = true;
  $('wait').textContent = 'Asking the start page…';
  let tab = null, stopped = false;
  waiting = { stop: () => { stopped = true; } };
  try {
    const nc = server + '/dav/nextcloud/index.php/login/v2';
    const [top] = await ext.bookmarks.getTree();
    const name = IoSync.isVivaldi(top) ? 'Vivaldi' : browserName();
    const r = await fetch(`${nc}?client=${encodeURIComponent('ioSuite Bookmarks in ' + name)}`, { method: 'POST', credentials: 'omit' }).catch(() => null);
    if (!r || !r.ok) throw new Error(r ? `That address did not answer as an ioSuite start page (${r.status}).` : 'That address cannot be reached.');
    const flow = await r.json();
    // the addresses the start page answers with are as it sees itself; this goes by the address typed here
    const page = String(flow.login || '').split('/').pop(), token = flow.poll && flow.poll.token;
    if (!page || !token) throw new Error('That address did not answer as an ioSuite start page.');
    tab = await ext.tabs.create({ url: `${nc}/flow/${encodeURIComponent(page)}` });
    $('wait').textContent = 'Say yes in the tab that opened…';
    let got = null;
    for (let i = 0; i < 600 && !stopped && !got; i++) {  // 20 minutes, as long as the start page keeps the question
      await sleep(2000);
      const p = await fetch(nc + '/poll', { method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) }).catch(() => null);
      if (p && p.ok) got = await p.json();
    }
    if (!got) throw new Error('Nobody said yes in time. Try again.');
    await ext.storage.local.remove(['sync', 'status']);
    await ext.storage.local.set({ account: { server, user: got.loginName, password: got.appPassword }, mode });
    if (tab) ext.tabs.remove(tab.id).catch(() => {});
    ext.runtime.sendMessage('sync').catch(() => {});
  } catch (e) {
    $('error').textContent = e.message;
  } finally {
    waiting = null;
    $('signin').disabled = false;
    $('wait').textContent = '';
    show();
  }
}

$('signin').addEventListener('click', signIn);
$('server').addEventListener('keydown', (e) => { if (e.key === 'Enter') signIn(); });
$('sync').addEventListener('click', async () => {
  $('sync').disabled = true;
  $('state').textContent = 'Syncing…';
  await ext.runtime.sendMessage('sync').catch(() => {});
  $('sync').disabled = false;
  show();
});
$('open').addEventListener('click', async () => {
  const { account } = await ext.storage.local.get('account');
  ext.tabs.create({ url: account.server + '/#/bookmarks' });
});
$('signout').addEventListener('click', async () => {
  const { account } = await ext.storage.local.get('account');
  await ext.storage.local.remove(['account', 'sync', 'status', 'mode']);
  ext.runtime.sendMessage('signed-out').catch(() => {});
  if (account) $('server').value = account.server;
  show();
});
ext.storage.onChanged.addListener(show);
show();
