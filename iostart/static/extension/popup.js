'use strict';
async function show() {
  const { account, status } = await ext.storage.local.get(['account', 'status']);
  const d = describe(account, status);
  $('dot').className = 'dot ' + d.cls;
  $('state').textContent = d.text;
  $('who').textContent = account ? `${account.user} · ${new URL(account.server).host}${account.canWrite === false ? ' · read only' : ''}` : 'Sign in to your start page to keep this browser\'s bookmarks the same as its bookmarks.';
  $('sync').hidden = !account;
  $('open').hidden = !account;
  $('signin').hidden = !!account;
}
$('sync').addEventListener('click', async () => {
  $('sync').disabled = true;
  $('state').textContent = 'Syncing…';
  await ext.runtime.sendMessage('sync').catch(() => {});
  $('sync').disabled = false;
  show();
});
$('signin').addEventListener('click', () => { ext.runtime.openOptionsPage(); window.close(); });
$('settings').addEventListener('click', () => { ext.runtime.openOptionsPage(); window.close(); });
$('open').addEventListener('click', async () => {
  const { account } = await ext.storage.local.get('account');
  ext.tabs.create({ url: account.server + '/#/bookmarks' });
  window.close();
});
ext.storage.onChanged.addListener(show);
show();
