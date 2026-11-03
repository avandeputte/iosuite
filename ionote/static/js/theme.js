// Applied before the page draws, so it never flashes the wrong theme: light by default, or what Settings › Appearance chose.
(function () { var t = 'light'; try { t = localStorage.getItem('ionotes.theme') || 'light'; } catch (e) {} if (t !== 'system') document.documentElement.dataset.theme = t === 'dark' ? 'dark' : 'light'; })();
