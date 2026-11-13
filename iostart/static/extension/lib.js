/* What the popup and the settings page share. */
'use strict';
const ext = globalThis.browser || globalThis.chrome;
const $ = (id) => document.getElementById(id);

function ago(at) {
  const s = Math.max(0, Math.round((Date.now() - at) / 1000));
  if (s < 50) return 'just now';
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(at).toLocaleDateString();
}

/** {cls, text} for the line that says how the sync is doing. */
function describe(account, status) {
  if (!account) return { cls: '', text: 'Not signed in' };
  if (!status) return { cls: '', text: 'First sync…' };
  if (status.ok) return { cls: 'ok', text: `In sync · checked ${ago(status.at)}` };
  return { cls: status.offline ? '' : 'bad', text: `${status.error} · ${ago(status.at)}` };
}

function browserName() {
  const ua = navigator.userAgent;
  return /Firefox\//.test(ua) ? 'Firefox' : /Edg\//.test(ua) ? 'Edge' : /OPR\//.test(ua) ? 'Opera' : /Vivaldi/.test(ua) ? 'Vivaldi' : 'Chrome';
}
