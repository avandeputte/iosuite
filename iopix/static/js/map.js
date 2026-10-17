/** The map page (Leaflet, loaded on demand). */
import { $, api, date, dfTime, h, icon, main, nf } from './core.js';
import { S, applyFilter, filterParams, go, toast } from './state.js';
import { openLightbox, syncLightbox } from './lightbox.js';

export const M = { data: null, map: null, token: 0 };

export function loadLeaflet(cluster) {
  const css = (href) => document.head.append(h('link', { rel: 'stylesheet', href }));
  const js = (src) => new Promise((ok, fail) => document.head.append(h('script', { src, onload: ok, onerror: () => fail(new Error('offline')) })));
  S.leafletP ||= (css('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'), js('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'));
  if (!cluster) return S.leafletP;
  S.clusterP ||= S.leafletP.then(() => {
    css('https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css');
    css('https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css');
    return js('https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js');
  });
  return S.clusterP;
}
// tile provider from the server (OpenStreetMap, or Google Maps with the owner's key); fetched once, OSM until it arrives


export async function loadMaps() { if (S.mapsLoaded) return S.MAPS; try { S.MAPS = await api('/api/maps'); if (S.MAPS.error) toast(S.MAPS.error, null, null, 8000); } catch { /* keep OSM */ } S.mapsLoaded = true; return S.MAPS; }
export const tiles = () => window.L.tileLayer(S.MAPS.url, { maxZoom: S.MAPS.maxZoom, attribution: S.MAPS.attribution });
export const mapLink = (lat, lon) => S.MAPS.link.replaceAll('{lat}', lat).replaceAll('{lon}', lon);

export async function showMap(fp) {
  const token = ++M.token;
  M.data = null;
  M.map?.remove(); M.map = null;
  const el = h('div', { id: 'map' });
  const bar = h('div', { class: 'mapbar' });
  main.replaceChildren(el, bar);
  let d;
  try { [d] = await Promise.all([api('/api/map?' + fp.toString()), loadLeaflet(true)]); } catch {
    if (token === M.token && S.route.view === 'map') main.replaceChildren(h('div', { class: 'empty' }, 'The map needs an internet connection for map tiles. Everything else works offline.'));
    return;
  }
  if (token !== M.token || S.route.view !== 'map') return;
  const L = window.L;
  M.data = d;
  await loadMaps();
  const map = M.map = L.map(el, { worldCopyJump: true }).setView([30, 0], 2);
  tiles().addTo(map);
  const dot = L.divIcon({ className: '', html: '<div class="pm"></div>', iconSize: [14, 14], iconAnchor: [7, 7] });
  const group = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 55, showCoverageOnHover: false, zoomToBoundsOnClick: false });
  group.addLayers(d.id.map((id, i) => L.marker([d.lat[i], d.lon[i]], { icon: dot, idx: i }).on('click', () => openLightbox(M.data, i, true))));
  // clicking a bubble offers all of its photos at once instead of forcing a drill-down
  group.on('clusterclick', (ev) => {
    const idxs = ev.layer.getAllChildMarkers().map((m) => m.options.idx).sort((a, b) => a - b);
    const b = ev.layer.getBounds();
    const openAll = () => {
      map.closePopup();
      const q = filterParams();
      q.delete('bbox'); q.delete('ids');
      if (idxs.length <= 600) q.set('ids', idxs.map((i) => d.id[i]).join(','));
      else q.set('bbox', [b.getSouth() - 1e-4, b.getWest() - 1e-4, b.getNorth() + 1e-4, b.getEast() + 1e-4].map((x) => x.toFixed(5)).join(','));
      go('photos', q);
    };
    const el = h('div', { class: 'mpop' },
      h('div', { class: 'mthumbs' }, idxs.slice(0, 8).map((i) => h('img', { src: `/thumb/${d.id[i]}`, alt: '', onclick: () => { map.closePopup(); openLightbox(M.data, i, true); } }))),
      h('div', { class: 'mbtns' },
        h('button', { class: 'pillbtn on', onclick: openAll }, icon('photo'), `Open all ${nf.format(idxs.length)} photos`),
        h('button', { class: 'pillbtn', onclick: () => { map.closePopup(); ev.layer.zoomToBounds({ padding: [30, 30] }); } }, 'Zoom in')));
    L.popup({ maxWidth: 360, minWidth: 300, closeButton: false }).setLatLng(ev.layer.getLatLng()).setContent(el).openOn(map);
  });
  map.addLayer(group);
  if (d.id.length) map.fitBounds(L.latLngBounds(d.id.map((_, i) => [d.lat[i], d.lon[i]])).pad(0.1), { maxZoom: 15 });
  const trailDay = fp.get('trail') || (fp.get('from') && fp.get('from') === fp.get('to') ? fp.get('from') : null);
  if (trailDay) api(`/api/trail?day=${trailDay}`).then((t) => {
    if (token !== M.token || t.id.length < 2) return;
    const pts = t.id.map((_, i) => [t.lat[i], t.lon[i]]);
    L.polyline(pts, { color: '#ea4335', weight: 3, opacity: .8, dashArray: '6 6' }).addTo(map);
    L.circleMarker(pts[0], { radius: 7, color: '#34a853', fillOpacity: 1 }).bindTooltip('Start · ' + dfTime.format(date(t.ts[0]))).addTo(map);
    L.circleMarker(pts[pts.length - 1], { radius: 7, color: '#ea4335', fillOpacity: 1 }).bindTooltip('End · ' + dfTime.format(date(t.ts[t.ts.length - 1]))).addTo(map);
    const km = pts.reduce((a, p, i) => i ? a + Math.hypot(p[0] - pts[i - 1][0], (p[1] - pts[i - 1][1]) * Math.cos(p[0] * Math.PI / 180)) * 111.2 : 0, 0);
    bar.append(h('span', { class: 'pillbtn', style: 'cursor:default' }, `Trail: ${t.id.length} photos, ${km.toFixed(1)} km, ${dfTime.format(date(t.ts[0]))} to ${dfTime.format(date(t.ts[t.ts.length - 1]))}`));
    map.fitBounds(L.latLngBounds(pts).pad(0.15));
  }).catch(() => {});
  bar.append(h('span', { class: 'pillbtn', style: 'cursor:default' }, `${nf.format(d.id.length)} with location`),
    h('button', { class: 'pillbtn', onclick: () => {
      const b = map.getBounds();
      applyFilter((p) => p.set('bbox', [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()].map((x) => x.toFixed(4)).join(',')), 'photos');
    } }, icon('photo'), 'Show photos in this area'));
  syncLightbox();
}
