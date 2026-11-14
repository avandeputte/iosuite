/* ioHealth, the web app: a small single-page app over the receiver's /api. No build step: the modules in js/, one per
   page (dashboard.js, metrics.js, workouts.js…) beside core.js (helpers, health types, the router), shell.js (the
   sidebar, settings, the API), charts.js and accounts.js. uPlot draws the charts and Leaflet the maps, each loaded
   when a page first needs it. Pages are hash routes (#/workouts, #/workout/<uuid>, #/metrics?types=…). */
import './js/main.js';
