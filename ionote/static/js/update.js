/** Running update.sh from the web app (Maintenance › Updates and logs, or the banner), then waiting for the new version:
 *  /api/status every 3 s until its version or commit differs from what was running, then the page reloads. After
 *  3 minutes without a change the update is reported as not finished. onState(text, failed) gets the words to show. */
import { api, fail } from './core.js';

export async function runUpdate(onState) {
  let was;
  try { const s = await api('/api/status'); was = `${s.version}|${s.commit || ''}`; } catch (e) { was = ''; }
  try { await api('/api/server', { method: 'POST', body: { action: 'update' } }); } catch (e) { fail(e); return false; }
  onState('Updating… the page reloads when the new version is up.', false);
  const until = Date.now() + 180000;
  const t = setInterval(async () => {
    try {
      const s = await api('/api/status');
      if (`${s.version}|${s.commit || ''}` !== was) { clearInterval(t); location.reload(); return; }
    } catch (e) { /* restarting */ }
    if (Date.now() > until) {
      clearInterval(t);
      let msg = 'ionotes did not come back with a new version within 3 minutes.';
      try { const u = await api('/api/server'); if (u.lastUpdate && !u.lastUpdate.ok) msg = u.lastUpdate.text; } catch (e) { /* still down */ }
      onState(msg, true);
    }
  }, 3000);
  return true;
}
