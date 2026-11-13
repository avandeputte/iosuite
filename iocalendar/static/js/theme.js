// Applied before the page draws, so it never flashes the wrong theme: the device's by default, or what Settings › Appearance chose.
(function () { var t = 'system'; try { t = localStorage.getItem('iocalendar.theme') || 'system'; } catch (e) {} if (t !== 'system') document.documentElement.dataset.theme = t === 'dark' ? 'dark' : 'light'; })();
