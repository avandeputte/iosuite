import { applySections, refreshStatus, render } from './core.js';
import { applyTheme, buildNav, loadSettings, loadSuite } from './shell.js';
import { loadMe, me, renderUserMenu, signIn } from './accounts.js';

// the pages: each registers itself in core.pages
import './dashboard.js';
import './metrics.js';
import './correlations.js';
import './workouts.js';
import './sleep.js';
import './glucose.js';
import './records.js';
import './day.js';
import './settings.js';

// ---------- start ----------

loadMe().then(async () => {
  renderUserMenu();
  if (!me.user) { signIn(true); return; }
  buildNav();
  loadSuite();
  await loadSettings();
  applyTheme();
  applySections();
  refreshStatus();
  setInterval(refreshStatus, 60000);
  render();
});
