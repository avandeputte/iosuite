/* ioCalendar web app: one module, no build step. Views: month, week, day and agenda, with the calendars to show in the
   sidebar; the event form (repeating events, people from ioContacts, reminders), search, import/export and settings
   (account, apps and devices, calendars, users, ioContacts, holidays, server). Events can be tagged with the family
   members they are for, and the sidebar filters the calendar by member. */

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
/** replaceChildren that leaves out null and false (as h() does) and flattens lists. */
const fill = (el, ...kids) => el.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
const ICONS = {
  today: 'M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z',
  agenda: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  chevL: 'M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z',
  chevR: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  clock: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z',
  repeat: 'M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z',
  bell: 'M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z',
  dup: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  globe: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z',
  contacts: 'M20 0H4v2h16V0zM4 24h16v-2H4v2zM20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-8 2.75c1.24 0 2.25 1.01 2.25 2.25s-1.01 2.25-2.25 2.25S9.75 10.24 9.75 9 10.76 6.75 12 6.75zM17 17H7v-1.5c0-1.67 3.33-2.5 5-2.5s5 .83 5 2.5V17z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  wrench: 'M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  star: 'M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z',
  starO: 'M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z',
  cake: 'M12 6c1.11 0 2-.9 2-2 0-.38-.1-.73-.29-1.03L12 0l-1.71 2.97c-.19.3-.29.65-.29 1.03 0 1.1.9 2 2 2zm4.6 9.99-1.07-1.07-1.08 1.07c-1.3 1.3-3.58 1.31-4.89 0l-1.07-1.07-1.09 1.07C6.75 16.64 5.88 17 4.96 17c-.73 0-1.4-.23-1.96-.61V21c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-4.61c-.56.38-1.23.61-1.96.61-.92 0-1.79-.36-2.44-1.01zM18 9h-5V7h-2v2H6c-1.66 0-3 1.34-3 3v1.54c0 1.08.88 1.96 1.96 1.96.52 0 1.02-.2 1.38-.57l2.14-2.13 2.13 2.13c.74.74 2.03.74 2.77 0l2.14-2.13 2.13 2.13c.37.37.86.57 1.38.57 1.08 0 1.96-.88 1.96-1.96V12C21 10.34 19.66 9 18 9z',
  mail: 'M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z',
  phone: 'M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z',
  place: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  tag: 'M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z',
  book: 'M20 0H4v2h16V0zM4 24h16v-2H4v2zM20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-8 2.75c1.24 0 2.25 1.01 2.25 2.25s-1.01 2.25-2.25 2.25S9.75 10.24 9.75 9 10.76 6.75 12 6.75zM17 17H7v-1.5c0-1.67 3.33-2.5 5-2.5s5 .83 5 2.5V17z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  tree: 'M22 11V3h-7v3H9V3H2v8h7V8h2v10h4v3h7v-8h-7v3h-2V8h2v3z',
  merge: 'M17 20.41 18.41 19 15 15.59 13.59 17 17 20.41zM7.5 8H11v5.59L5.59 19 7 20.41l6-6V8h3.5L12 3.5 7.5 8z',
  camera: 'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM9 2 7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z',
  key: 'M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  event: 'M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  open: 'M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z',
  work: 'M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-6 0h-4V4h4v2z',
  note: 'M3 18h12v-2H3v2zM3 6v2h18V6H3zm0 7h18v-2H3v2z',
  devices: 'M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z',
  image: 'M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  bulb: 'M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  server: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  org: 'M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z',
  select: 'M3 5h2V3c-1.1 0-2 .9-2 2zm0 8h2v-2H3v2zm4 8h2v-2H7v2zM3 9h2V7H3v2zm10-6h-2v2h2V3zm6 0v2h2c0-1.1-.9-2-2-2zM5 21v-2H3c0 1.1.9 2 2 2zm-2-4h2v-2H3v2zM9 3H7v2h2V3zm2 18h2v-2h-2v2zm8-8h2v-2h-2v2zm0 8c1.1 0 2-.9 2-2h-2v2zm0-12h2V7h-2v2zm0 8h2v-2h-2v2zm-4 4h2v-2h-2v2zm0-16h2V3h-2v2zM7 17h10V7H7v10zm2-8h6v6H9V9z',
};
const icon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'ic ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith('--')) el.style.setProperty(sk, sv); else el.style[sk] = sv; }
    else if (k === 'value') el.value = v;
    else if (k === 'checked') el.checked = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const add = (k) => { if (k == null || k === false) return; if (Array.isArray(k)) k.forEach(add); else el.append(k instanceof Node ? k : String(k)); };
  kids.forEach(add);
  return el;
}

async function api(path, opts = {}) {
  const o = { credentials: 'same-origin', ...opts, headers: { ...(opts.headers || {}) } };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers['Content-Type'] = 'application/json'; delete o.json; }
  const r = await fetch(path, o);
  if (r.status === 401 && !path.startsWith('/api/auth') && path !== '/api/status') { showSignIn(); throw new Error('Sign in first'); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* not JSON */ }
    throw new Error(msg || `Error ${r.status}`);
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}

let toastTimer;
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
}
const fail = (e) => toast(e.message || String(e));

function dialog(title, body, buttons) {
  return new Promise((resolve) => {
    const back = h('div', { class: 'dialog-back' });
    const close = (v) => { back.remove(); resolve(v); };
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `pillbtn noic ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''}`, onclick: () => close(typeof b.value === 'function' ? b.value() : b.value) }, b.label));
    back.append(h('div', { class: 'dialog', role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector('input,select,textarea'); if (f) f.focus();
  });
}
const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, h('p', null, text), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);

const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
async function copyText(t) { try { await navigator.clipboard.writeText(t); toast('Copied'); } catch { toast(t); } }
const copyRow = (v) => h('div', { class: 'copy' }, h('code', null, v), h('button', { class: 'iconbtn', title: 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));


// ------------------------------------------------------------------ dates
const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const parseDay = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const addMonths = (d, n) => { const x = new Date(d.getFullYear(), d.getMonth() + n, 1); x.setDate(Math.min(d.getDate(), new Date(x.getFullYear(), x.getMonth() + 1, 0).getDate())); return x; };
const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const weekStart = () => (S.settings.weekStart ?? 1);
const startOfWeek = (d) => { const x = dayStart(d); const diff = (x.getDay() - weekStart() + 7) % 7; return addDays(x, -diff); };
const fmtTime = (d) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const fmtDay = (d, opts = { weekday: 'long', month: 'long', day: 'numeric' }) => d.toLocaleDateString([], opts);
const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
const DOW = (i, style = 'short') => new Date(2026, 1, 1 + i).toLocaleDateString([], { weekday: style }); // 1 Feb 2026 is a Sunday
const RDAY = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
/** An occurrence's start and end as Dates (all-day: local midnights; the end is the day after the last day). */
function span(o) {
  if (o.allDay) return [parseDay(o.start), parseDay(o.end)];
  return [new Date(o.start), new Date(o.end)];
}
const ordinal = (n) => ({ 1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', '-1': 'last' })[n] || `${n}th`;

/** A repeat rule (RRULE) in words. */
function describeRule(rule, startDay) {
  if (!rule) return '';
  const p = Object.fromEntries(rule.split(';').map((x) => x.split('=')));
  const n = +(p.INTERVAL || 1);
  const unit = { DAILY: 'day', WEEKLY: 'week', MONTHLY: 'month', YEARLY: 'year' }[p.FREQ] || p.FREQ.toLowerCase();
  let s = n === 1 ? `Every ${unit}` : `Every ${n} ${unit}s`;
  if (p.FREQ === 'DAILY' && n === 1) s = 'Daily';
  if (p.FREQ === 'WEEKLY' && p.BYDAY) {
    const days = p.BYDAY.split(',');
    if (days.length === 5 && ['MO', 'TU', 'WE', 'TH', 'FR'].every((d) => days.includes(d))) s = n === 1 ? 'Every weekday' : `${s} on weekdays`;
    else s += ' on ' + days.map((d) => DOW(RDAY.indexOf(d), 'long')).join(', ');
  }
  if (p.FREQ === 'MONTHLY') {
    if (p.BYDAY) { const m = p.BYDAY.match(/^(-?\d)?([A-Z]{2})$/); if (m) s += ` on the ${ordinal(m[1] || 1)} ${DOW(RDAY.indexOf(m[2]), 'long')}`; }
    else if (p.BYMONTHDAY) s += ` on day ${p.BYMONTHDAY}`;
    else if (startDay) s += ` on day ${startDay.getDate()}`;
  }
  if (p.FREQ === 'YEARLY' && startDay && !p.BYMONTH) s += ` on ${startDay.toLocaleDateString([], { month: 'long', day: 'numeric' })}`;
  if (p.COUNT) s += `, ${p.COUNT} times`;
  if (p.UNTIL) { const u = p.UNTIL; s += `, until ${parseDay(`${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}`).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })}`; }
  return s;
}
function describeReminder(m, allDay) {
  if (allDay && m % 60 === 0 && m !== 0 && Math.abs(m) <= 40320) {
    // relative to midnight: -540 = on the day at 9:00, 900 = the day before at 9:00
    const days = Math.ceil(m / 1440), mins = days * 1440 - m;
    const at = new Date(2026, 0, 1, Math.floor(mins / 60), mins % 60);
    if (mins >= 0 && mins < 1440) return `${days === 0 ? 'On the day' : days === 1 ? 'The day before' : days === 7 ? 'A week before' : `${days} days before`} at ${fmtTime(at)}`;
  }
  if (m === 0) return 'At the start';
  if (m < 0) return `${-m} minutes after the start`;
  if (m % 10080 === 0) return `${m / 10080} week${m > 10080 ? 's' : ''} before`;
  if (m % 1440 === 0) return `${m / 1440} day${m > 1440 ? 's' : ''} before`;
  if (m % 60 === 0) return `${m / 60} hour${m > 60 ? 's' : ''} before`;
  return `${m} minutes before`;
}
function whenText(o) {
  const [s, e] = span(o);
  if (o.allDay) {
    const last = addDays(e, -1);
    return sameDay(s, last) ? fmtDay(s) : `${fmtDay(s, { weekday: 'short', month: 'short', day: 'numeric' })} – ${fmtDay(last, { weekday: 'short', month: 'short', day: 'numeric', year: last.getFullYear() !== s.getFullYear() ? 'numeric' : undefined })}`;
  }
  if (sameDay(s, e) || (e - s <= 86400000 && e.getHours() === 0 && e.getMinutes() === 0 && sameDay(addDays(s, 1), e))) return `${fmtDay(s)} · ${fmtTime(s)} – ${fmtTime(e)}`;
  return `${fmtDay(s, { weekday: 'short', month: 'short', day: 'numeric' })} ${fmtTime(s)} – ${fmtDay(e, { weekday: 'short', month: 'short', day: 'numeric' })} ${fmtTime(e)}`;
}

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, settings: {}, cals: [], hidden: new Set(), members: [], who: new Set(), view: 'month', date: dayStart(new Date()), occ: [], q: '', mini: null, editing: null };
const calOf = (id) => S.cals.find((c) => c.id === id) || {};
const colorOf = (id) => calOf(id).color || 'var(--brand)';
const writable = () => S.cals.filter((c) => c.writable);
const shownCals = () => S.cals.filter((c) => !S.hidden.has(c.id));
/** Filled by the server (Birthdays from ioContacts, public Holidays): nobody changes them here. */
const AUTO_KINDS = ['birthdays', 'holidays'];
const isAuto = (c) => AUTO_KINDS.includes(c.kind);
const memberOf = (id) => S.members.find((m) => m.id === id);
const MEMBER_COLORS = ['#1e8e3e', '#e0426a', '#1a73e8', '#e8710a', '#8e44d6', '#0b8a9e', '#b5452f', '#4b53c7', '#e8a100', '#5f6b7a'];
/** Each family member gets a colour of their own (by their place in the family list, so two never look alike). */
const memberColor = (m) => MEMBER_COLORS[Math.max(0, S.members.findIndex((x) => x.id === m.id)) % MEMBER_COLORS.length];
const memberBadge = (m) => h('span', { class: 'mem', title: m.displayName, style: { '--mc': memberColor(m) } }, initials(m.displayName));
/** With family members picked in the sidebar: only the events tagged with one of them (holidays and birthdays stay). */
const passesWho = (o) => !S.who.size || isAuto(calOf(o.calendarId)) || (o.members || []).some((id) => S.who.has(id));
function toggleWho(id) {
  if (id == null) S.who.clear(); else if (S.who.has(id)) S.who.delete(id); else S.who.add(id);
  saveSettings({ memberFilter: [...S.who].join(',') });
  drawNav();
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView();
}

async function loadCals() {
  const [cals, fam] = await Promise.all([api('/api/calendars'), api('/api/members').catch(() => ({ items: S.members }))]);
  S.cals = cals.items;
  S.members = fam.items || [];
  for (const id of [...S.who]) if (!memberOf(id)) S.who.delete(id);
  drawNav();
}
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('/api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}
function toggleCal(id) {
  if (S.hidden.has(id)) S.hidden.delete(id); else S.hidden.add(id);
  saveSettings({ hiddenCalendars: [...S.hidden].join(',') });
  drawNav();
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView();
}

// ------------------------------------------------------------------ chrome
function drawUser() {
  const m = $('#usermenu'); m.replaceChildren();
  if (!S.user) return;
  const btn = h('button', { class: 'iconbtn gear', title: `${S.user.displayName} · settings` }, icon('settings'));
  let menu = null;
  const closeMenu = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && e.target !== btn) closeMenu(); };
  btn.onclick = () => {
    if (menu) return closeMenu();
    const theme = localStorage.getItem('iocal.theme') || 'system';
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings/account', onclick: closeMenu }, icon('person', 's'), 'Account'),
      h('a', { class: 'mi', href: '#/settings/devices', onclick: closeMenu }, icon('devices', 's'), 'Connect apps and devices'),
      h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; localStorage.setItem('iocal.theme', n); applyTheme(); closeMenu(); toast(`Appearance: ${n}`); } },
        icon('theme', 's'), `Appearance: ${theme}`),
      h('button', { class: 'mi', onclick: async () => { const r = await api('/api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
function applyTheme() {
  const t = localStorage.getItem('iocal.theme') || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}

/** A small month in the sidebar: pick a day to go to it. */
function miniMonth() {
  const base = S.mini || new Date(S.date.getFullYear(), S.date.getMonth(), 1);
  const first = startOfWeek(base), today = new Date();
  const g = h('div', { class: 'g' }, [0, 1, 2, 3, 4, 5, 6].map((i) => h('span', { class: 'h' }, DOW((i + weekStart()) % 7, 'narrow'))));
  for (let i = 0; i < 42; i++) {
    const d = addDays(first, i);
    g.append(h('span', { class: [d.getMonth() !== base.getMonth() ? 'o' : '', sameDay(d, today) ? 't' : sameDay(d, S.date) ? 'sel' : ''].join(' '),
      onclick: () => go(S.view === 'agenda' ? 'day' : S.view, d) }, d.getDate()));
  }
  return h('div', { class: 'mini' }, h('div', { class: 'mh' },
    h('span', null, base.toLocaleDateString([], { month: 'long', year: 'numeric' })),
    h('span', null, h('button', { class: 'iconbtn', title: 'Previous month', onclick: () => { S.mini = addMonths(base, -1); drawNav(); } }, icon('chevL', 's')),
      h('button', { class: 'iconbtn', title: 'Next month', onclick: () => { S.mini = addMonths(base, 1); drawNav(); } }, icon('chevR', 's')))), g);
}

/* The sidebar, as in ioPix and ioContacts: the name on top, the destinations, the calendars (each with its colour as a
   check box that shows or hides it), Settings at the foot. It docks beside the page on a wide screen unless its button
   put it away (remembered); otherwise it slides over the page. Phones get a bottom bar instead. */
const DOCK_MIN = 1100;
function drawNav() {
  const nav = $('#nav'); const r = route();
  const calView = ['month', 'week', 'day'].includes(r.view);
  const link = (v, href, ic, label, n, on, hue) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hue ? { '--hue': `var(${hue})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const check = '<svg viewBox="0 0 24 24"><path d="' + ICONS.check + '"/></svg>';
  const calRow = (c) => {
    const ck = h('span', { class: 'ck' }); ck.innerHTML = check;
    return h('a', { href: '#', 'data-v': 'cal', class: `cal ${S.hidden.has(c.id) ? '' : 'shown'}`, title: `${S.hidden.has(c.id) ? 'Show' : 'Hide'} ${c.name}`,
      style: { '--hue': c.color }, onclick: (e) => { e.preventDefault(); toggleCal(c.id); } },
      ck, h('span', { class: 'nl' }, c.name), h('span', { class: 'n' }, isAuto(c) ? '' : c.count || ''));
  };
  const whoRow = (m) => h('a', { href: '#', 'data-v': 'who', class: `who ${S.who.has(m.id) ? 'picked' : ''}`, style: { '--mc': memberColor(m) },
    title: S.who.has(m.id) ? `Stop showing only ${m.displayName}'s events` : `Show only ${m.displayName}'s events`,
    onclick: (e) => { e.preventDefault(); toggleWho(m.id); } }, memberBadge(m), h('span', { class: 'nl' }, m.displayName));
  const shared = S.cals.filter((c) => c.shared), mine = S.cals.filter((c) => !c.shared);
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      h('a', { class: 'brand', href: '#/', title: 'Calendar' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
        h('span', { class: 'brand-name' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Calendar'))),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    link('calendar', `#/${S.view === 'agenda' ? 'month' : S.view}/${ymd(S.date)}`, 'today', 'Calendar', null, calView, '--c-rose'),
    link('agenda', '#/agenda', 'agenda', 'Agenda', null, r.view === 'agenda', '--c-blue'),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    miniMonth(),
    sec('Shared', S.user.role !== 'viewer' ? h('button', { class: 'iconbtn', title: 'New shared calendar', onclick: () => newCalendar(true) }, icon('add', 's')) : null),
    shared.map(calRow),
    S.members.length > 1 ? [h('div', { class: 'navgap' }),
      sec('Family', S.who.size ? h('button', { class: 'pillbtn noic tiny', title: 'Show everyone again', onclick: () => toggleWho(null) }, 'Everyone') : null),
      S.members.map(whoRow)] : null,
    h('div', { class: 'navgap' }),
    sec('Mine', h('button', { class: 'iconbtn', title: 'New private calendar', onclick: () => newCalendar(false) }, icon('add', 's'))),
    mine.map(calRow),
    h('div', { class: 'navgap' }), sec('Manage'),
    link('import', '#/import', 'upload', 'Import and export', null, r.view === 'import', '--c-green'),
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['import', 'settings', 'search'].includes(r.view));
}
function sideDockedPref() { try { return localStorage.getItem('iocal.sidebar') !== '0'; } catch { return true; } }
function applySidebar() {
  const body = document.body, btn = $('#sidebtn');
  const docked = innerWidth >= DOCK_MIN && sideDockedPref();
  body.classList.toggle('side-docked', docked);
  if (docked) closeNav();
  if (!btn) return;
  const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : innerWidth >= DOCK_MIN ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
  btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
}
function sidebarButton() {
  if (document.body.classList.contains('side-docked')) { try { localStorage.setItem('iocal.sidebar', '0'); } catch { /* */ } }
  else if (innerWidth >= DOCK_MIN) { try { localStorage.setItem('iocal.sidebar', '1'); } catch { /* */ } }
  else { closeNav(); return; }
  applySidebar();
}
function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }
/** Phones: what the bottom bar has no room for (the calendars to show, import, settings). */
function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hue, on, click) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hue }, onclick: click || null }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.cals.map((c) => tile('#', S.hidden.has(c.id) ? 'close' : 'check', c.name, c.color, !S.hidden.has(c.id), (e) => { e.preventDefault(); e.stopPropagation(); toggleCal(c.id); document.querySelector('.dialog-back')?.remove(); moreSheet(); })),
    S.members.length > 1 ? S.members.map((m) => tile('#', 'person', S.who.has(m.id) ? `Only ${m.displayName}` : m.displayName, memberColor(m), S.who.has(m.id),
      (e) => { e.preventDefault(); e.stopPropagation(); toggleWho(m.id); document.querySelector('.dialog-back')?.remove(); moreSheet(); })) : null,
    tile('#/import', 'upload', 'Import and export', 'var(--c-green)', r.view === 'import'),
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { const a = e.target.closest('a'); if (a && a.getAttribute('href') !== '#') document.querySelector('.dialog-back')?.remove(); });
  return p;
}

const SWATCHES = ['#8e44d6', '#0b8a9e', '#1a73e8', '#e0426a', '#1e8e3e', '#e8710a', '#4b53c7', '#e8a100', '#5f6b7a', '#b5452f'];
function colorPicker(value) {
  let cur = value || SWATCHES[0];
  const own = h('input', { type: 'color', value: cur, title: 'Another colour' });
  const row = h('div', { class: 'colors' });
  const draw = () => row.replaceChildren(...SWATCHES.map((c) => h('button', { type: 'button', class: c === cur ? 'on' : '', style: { '--c': c }, title: c, onclick: () => { cur = c; own.value = c; draw(); } })), own);
  own.oninput = () => { cur = own.value; draw(); };
  draw();
  row.get = () => cur;
  return row;
}
async function newCalendar(shared) {
  const name = h('input', { class: 't', placeholder: shared ? 'Name, e.g. Soccer or School' : 'Name, e.g. Work' });
  const col = colorPicker(SWATCHES[S.cals.length % SWATCHES.length]);
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, name, col,
    h('p', { class: 'muted small', style: { margin: 0 } }, shared ? 'Everyone in the family sees it; editors change it.' : 'Only you see it.'));
  if (!await dialog(shared ? 'New shared calendar' : 'New private calendar', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
  try { await api('/api/calendars', { method: 'POST', json: { name: name.value, shared, color: col.get(), timezone: LOCAL_TZ } }); await loadCals(); drawView(); } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ routing
function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query] = raw.split('?');
  const p = path.split('/').map(decodeURIComponent);
  const qs = new URLSearchParams(query || '');
  const [a, b] = p;
  if (!a) return { view: S.settings.defaultView || 'month', date: null };
  if (['month', 'week', 'day'].includes(a)) return { view: a, date: b && /^\d{4}-\d{2}-\d{2}$/.test(b) ? parseDay(b) : null };
  if (a === 'agenda') return { view: 'agenda', date: b && /^\d{4}-\d{2}-\d{2}$/.test(b) ? parseDay(b) : null };
  if (a === 'search') return { view: 'search', q: b || '' };
  if (a === 'event' && b) return { view: 'event', id: +b, rid: qs.get('rid') };
  if (a === 'edit' && b) return { view: 'edit', id: +b, rid: qs.get('rid') };
  if (a === 'new') return { view: 'new', date: qs.get('date'), time: qs.get('time'), allDay: qs.get('allday') === '1', copy: qs.get('copy') };
  if (a === 'import') return { view: 'import' };
  if (a === 'settings') return { view: 'settings', tab: b || 'account' };
  return { view: 'month' };
}
function go(view, date) { location.hash = `#/${view}/${ymd(date || S.date)}`; }

async function onRoute() {
  const r = route();
  const main = $('#main');
  try {
    if (['month', 'week', 'day', 'agenda'].includes(r.view)) {
      S.view = r.view;
      if (r.date) S.date = r.date;
      if (r.view !== 'agenda') { try { localStorage.setItem('iocal.view', r.view); } catch { /* */ } }
      S.mini = null;
      await drawView();
    } else {
      main.classList.remove('showdetail');
      const page = h('div', { class: 'page' });
      main.replaceChildren(page);
      await ({ search: showSearch, event: showEventPage, edit: showEdit, new: showEdit, import: showImport, settings: showSettings })[r.view](page, r);
    }
  } catch (e) { fail(e); }
  drawNav();
}

// ------------------------------------------------------------------ the calendar views
const daysBetween = (a, b) => Math.round((dayStart(b) - dayStart(a)) / 864e5);
function viewRange() {
  const d = S.date;
  if (S.view === 'month') {
    const s = startOfWeek(new Date(d.getFullYear(), d.getMonth(), 1));
    const last = new Date(d.getFullYear(), d.getMonth() + 1, 0);
    return [s, addDays(s, Math.ceil((daysBetween(s, last) + 1) / 7) * 7)];
  }
  if (S.view === 'week') { const s = startOfWeek(d); return [s, addDays(s, 7)]; }
  if (S.view === 'agenda') { const s = dayStart(d); return [s, addDays(s, S.agendaDays || 31)]; }
  const s = dayStart(d); return [s, addDays(s, 1)];
}
function viewTitle() {
  const d = S.date;
  if (S.view === 'month') return d.toLocaleDateString([], { month: 'long', year: 'numeric' });
  if (S.view === 'day') return d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  if (S.view === 'agenda') return sameDay(d, new Date()) ? 'Coming up' : `From ${d.toLocaleDateString([], { month: 'long', day: 'numeric', year: 'numeric' })}`;
  const s = startOfWeek(d), e = addDays(s, 6);
  if (s.getMonth() === e.getMonth()) return `${s.toLocaleDateString([], { month: 'long' })} ${s.getDate()} – ${e.getDate()}, ${e.getFullYear()}`;
  return `${s.toLocaleDateString([], { month: 'short', day: 'numeric', year: s.getFullYear() !== e.getFullYear() ? 'numeric' : undefined })} – ${e.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}`;
}
function stepView(n) {
  if (S.view === 'month') go('month', addMonths(S.date, n));
  else go(S.view, addDays(S.date, n * ({ week: 7, agenda: 30 }[S.view] || 1)));
}
function calbar() {
  return h('div', { class: 'calbar' },
    h('button', { class: 'pillbtn noic', title: 'Today (t)', onclick: () => go(S.view, new Date()) }, 'Today'),
    h('button', { class: 'iconbtn', title: 'Earlier (←)', onclick: () => stepView(-1) }, icon('chevL')),
    h('button', { class: 'iconbtn', title: 'Later (→)', onclick: () => stepView(1) }, icon('chevR')),
    h('h1', null, viewTitle()), h('span', { class: 'grow' }),
    h('div', { class: 'seg', role: 'tablist' }, [['day', 'Day', 'd'], ['week', 'Week', 'w'], ['month', 'Month', 'm'], ['agenda', 'Agenda', 'a']].map(([v, l, k]) =>
      h('button', { class: S.view === v ? 'on' : '', title: `${l} (${k})`, onclick: () => go(v, S.date) }, l))));
}

/** Occurrences by day (YYYY-MM-DD) for the days given: a long event is on each of its days. */
function byDay(days, items) {
  const m = new Map(days.map((d) => [ymd(d), []]));
  for (const o of items) {
    const [a, b] = span(o);
    const last = o.allDay ? addDays(b, -1) : new Date(Math.max(+a, +b - 1));
    for (let d = dayStart(a); d <= last; d = addDays(d, 1)) { const l = m.get(ymd(d)); if (l) l.push(o); }
  }
  return m;
}
/** Spans more than one day: drawn as a bar (month) or in the all-day row (week). */
const longEvent = (o) => { if (o.allDay) return true; const [a, b] = span(o); return b - a >= 864e5; };

let drawSeq = 0;
async function drawView() {
  const main = $('#main');
  main.classList.remove('showdetail');
  const [s, e] = viewRange();
  const seq = ++drawSeq;
  const ids = shownCals().map((c) => c.id);
  let items = [];
  if (ids.length) items = (await api(`/api/occurrences?start=${encodeURIComponent(s.toISOString())}&end=${encodeURIComponent(e.toISOString())}&calendars=${ids.join(',')}`)).items;
  if (seq !== drawSeq) return;
  S.occ = items.filter(passesWho);
  const body = h('div', { class: 'calbody' });
  const key = `${S.view}|${ymd(s)}`;
  const keep = S.drawn === key ? main.querySelector('.calbody')?.scrollTop : undefined;
  S.drawn = key;
  main.replaceChildren(h('div', { class: 'calpage' }, calbar(), body));
  ({ month: drawMonth, week: drawWeek, day: drawWeek, agenda: drawAgenda })[S.view](body, s, e, keep);
}

const canChange = (o) => !!calOf(o.calendarId).writable;
function chip(o, day) {
  const [a] = span(o);
  const long = longEvent(o);
  const el = h('div', { class: ['chip-ev', long ? 'allday' : '', o.status === 'CANCELLED' ? 'cancelled' : '', o.status === 'TENTATIVE' ? 'tentative' : ''].join(' '),
    style: { '--c': colorOf(o.calendarId) }, title: `${o.title || '(no title)'}\n${whenText(o)}${o.location ? '\n' + o.location : ''}`,
    draggable: canChange(o) ? 'true' : null,
    onclick: (ev) => { ev.stopPropagation(); openEvent(o); } },
  long ? null : h('span', { class: 'dot' }), !long && sameDay(a, day) ? h('span', { class: 't' }, fmtTime(a)) : null, h('span', { class: 'nm' }, o.title || '(no title)'),
  (o.members || []).map(memberOf).filter(Boolean).map(memberBadge));
  el.addEventListener('dragstart', (ev) => { S.drag = { o, from: day, grabMin: 0 }; ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', o.title || ''); });
  return el;
}

function drawMonth(body, s, e) {
  const weeks = Math.round(daysBetween(s, e) / 7);
  const days = Array.from({ length: weeks * 7 }, (_, i) => addDays(s, i));
  const map = byDay(days, S.occ), today = new Date(), month = S.date.getMonth();
  const grid = h('div', { class: 'month', style: { '--weeks': weeks } },
    h('div', { class: 'dows' }, [0, 1, 2, 3, 4, 5, 6].map((i) => h('div', null, DOW((i + weekStart()) % 7)))));
  for (let w = 0; w < weeks; w++) {
    const row = h('div', { class: 'wk' });
    for (const d of days.slice(w * 7, w * 7 + 7)) {
      const list = map.get(ymd(d)).slice().sort((x, y) => longEvent(y) - longEvent(x) || span(x)[0] - span(y)[0]);
      const cell = h('div', { class: ['mday', d.getMonth() !== month ? 'other' : '', sameDay(d, today) ? 'today' : ''].join(' '),
        onclick: () => newAt(d), title: 'New event' },
      h('span', { class: 'dnum', title: 'Open the day', onclick: (ev) => { ev.stopPropagation(); go('day', d); } }, d.getDate() === 1 ? d.toLocaleDateString([], { month: 'short', day: 'numeric' }) : d.getDate()),
      list.map((o) => chip(o, d)));
      dropTarget(cell, (o) => moveBy(o, daysBetween(S.drag.from, d) * 864e5, true));
      row.append(cell);
    }
    grid.append(row);
  }
  body.append(grid);
  // as many chips as fit; the rest behind "N more"
  requestAnimationFrame(() => grid.querySelectorAll('.mday').forEach((cell) => {
    const chips = [...cell.querySelectorAll('.chip-ev')];
    const fit = Math.max(1, Math.floor((cell.clientHeight - 34) / 24));
    if (chips.length <= fit) return;
    chips.slice(fit - 1).forEach((c) => { c.hidden = true; });
    const n = chips.length - fit + 1;
    const d = days[[...grid.querySelectorAll('.mday')].indexOf(cell)];
    cell.append(h('div', { class: 'more', onclick: (ev) => { ev.stopPropagation(); dayList(d, map.get(ymd(d))); } }, `${n} more`));
  }));
}
function dayList(d, list) {
  const body = h('div', { style: { display: 'flex', flexDirection: 'column', gap: '2px', minWidth: '280px' } }, list.map((o) => chip(o, d)));
  body.addEventListener('click', () => document.querySelector('.dialog-back')?.remove());
  dialog(fmtDay(d), body, [{ label: 'Open the day', value: () => go('day', d) }, { label: 'Close', value: null, primary: true }]);
}
function dropTarget(el, done) {
  el.addEventListener('dragover', (ev) => { if (!S.drag) return; ev.preventDefault(); el.classList.add('drop'); });
  el.addEventListener('dragleave', () => el.classList.remove('drop'));
  el.addEventListener('drop', (ev) => { ev.preventDefault(); el.classList.remove('drop'); if (S.drag) { const o = S.drag.o; done(o, ev); S.drag = null; } });
}

/** Move an occurrence by ms (whole days for all-day events), asking which ones when it repeats. */
async function moveBy(o, ms, days) {
  if (!ms) return;
  const [a, b] = span(o);
  let data;
  if (o.allDay) {
    const n = Math.round(ms / 864e5);
    if (!n) return;
    data = { start: ymd(addDays(a, n)), end: ymd(addDays(b, n)) };
  } else if (days) {
    const n = Math.round(ms / 864e5);
    data = { start: addDays(a, n).toISOString(), end: addDays(b, n).toISOString() };
  } else data = { start: new Date(+a + ms).toISOString(), end: new Date(+b + ms).toISOString() };
  await saveOccurrence(o, data, 'Move');
}
async function saveOccurrence(o, data, verb) {
  let scope = 'all';
  if (o.recurring && o.recurrenceId) { scope = await askScope(verb); if (!scope) return; }
  const qs = o.recurrenceId ? `?scope=${scope}&recurrenceId=${encodeURIComponent(o.recurrenceId)}` : '';
  try { await api(`/api/events/${o.id}${qs}`, { method: 'PATCH', json: data }); toast('Moved'); } catch (e) { fail(e); }
  drawView();
}
function askScope(verb) {
  const v = verb.toLowerCase();
  return dialog(`${verb} a repeating event`, h('p', null, `${verb} only this one, this one and the ones after it, or every one?`),
    [{ label: 'Cancel', value: null }, { label: 'This one', value: 'this' }, { label: 'This and later', value: 'following' }, { label: `All of them`, value: 'all', primary: v !== 'delete', danger: v === 'delete' }]);
}
function newAt(d, time) {
  const q = new URLSearchParams({ date: ymd(d) });
  if (time) q.set('time', time);
  location.hash = `#/new?${q}`;
}

// week and day: a column per day, hours down the side
const HH = 48;
function drawWeek(body, s, e, keep) {
  const n = S.view === 'day' ? 1 : 7;
  const days = Array.from({ length: n }, (_, i) => addDays(s, i));
  const map = byDay(days, S.occ), today = new Date();
  const grid = h('div', { class: 'tgrid', style: { '--days': n, '--hh': `${HH}px` } });
  grid.append(h('div', { class: 'head' }), ...days.map((d) => h('div', { class: `head thead-day ${sameDay(d, today) ? 'today' : ''}`, onclick: () => go('day', d) },
    h('div', { class: 'dow' }, DOW(d.getDay(), n === 1 ? 'long' : 'short')), h('span', { class: `dnum ${sameDay(d, today) ? 'today' : ''}` }, d.getDate()))));
  grid.append(h('div', { class: 'alldaylabel' }, 'all day'), ...days.map((d) => {
    const cell = h('div', { class: 'alldayrow', onclick: () => location.hash = `#/new?date=${ymd(d)}&allday=1` }, map.get(ymd(d)).filter(longEvent).map((o) => chip(o, d)));
    dropTarget(cell, (o) => moveBy(o, daysBetween(S.drag.from, d) * 864e5, true));
    return cell;
  }));
  const hours = h('div', { class: 'hours' }, Array.from({ length: 24 }, (_, i) => h('div', { class: 'hour' }, i ? new Date(2026, 0, 1, i).toLocaleTimeString([], { hour: 'numeric' }) : '')));
  grid.append(hours);
  days.forEach((d) => {
    const col = h('div', { class: `dcol ${sameDay(d, today) ? 'today' : ''}` });
    const minAt = (ev) => Math.max(0, Math.min(1440 - 15, Math.round((ev.clientY - col.getBoundingClientRect().top) / HH * 60 / 15) * 15));
    col.addEventListener('click', (ev) => { if (ev.target !== col) return; const m = Math.floor(minAt(ev) / 30) * 30; newAt(d, `${pad2(m / 60 | 0)}:${pad2(m % 60)}`); });
    dropTarget(col, (o, ev) => {
      const m = minAt(ev) - (S.drag.grabMin || 0);
      const [a] = span(o);
      const to = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, Math.round(m / 15) * 15);
      if (o.allDay) return; // an all-day event stays one
      moveBy(o, to - a, false);
    });
    const lay = layout(map.get(ymd(d)).filter((o) => !longEvent(o)), d);
    for (const x of lay) {
      const o = x.o, [a, b] = span(o);
      const el = h('div', { class: ['tev', o.status === 'CANCELLED' ? 'cancelled' : '', o.busy === false ? 'free' : ''].join(' '),
        style: { '--c': colorOf(o.calendarId), top: `${x.top / 60 * HH}px`, height: `${Math.max(18, (x.bottom - x.top) / 60 * HH - 2)}px`,
          left: `calc(${x.col / x.cols * 100}% + 1px)`, width: `calc(${100 / x.cols}% - 3px)` },
        title: `${o.title || '(no title)'}\n${whenText(o)}${o.location ? '\n' + o.location : ''}`, draggable: canChange(o) ? 'true' : null,
        onclick: (ev) => { ev.stopPropagation(); openEvent(o); } },
      h('div', { class: 'nm' }, o.title || '(no title)'),
      x.bottom - x.top >= 45 ? h('div', { class: 't' }, `${fmtTime(a)} – ${fmtTime(b)}`) : null,
      x.bottom - x.top >= 75 && o.location ? h('div', { class: 't' }, o.location) : null);
      el.addEventListener('dragstart', (ev) => {
        S.drag = { o, from: d, grabMin: Math.round((ev.clientY - el.getBoundingClientRect().top) / HH * 60 / 15) * 15 };
        ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', o.title || '');
      });
      col.append(el);
    }
    if (sameDay(d, today)) col.append(h('div', { class: 'nowline', style: { top: `${(today.getHours() * 60 + today.getMinutes()) / 60 * HH}px` } }));
    grid.append(col);
  });
  body.append(grid);
  const now = new Date();
  body.scrollTop = keep ?? (days.some((d) => sameDay(d, now)) ? Math.max(0, (now.getHours() - 2) * HH) : 7 * HH);
}
/** Timed occurrences of one day, side by side where they overlap: [{o, top, bottom (minutes), col, cols}]. */
function layout(list, d) {
  const d0 = dayStart(d), d1 = addDays(d0, 1);
  const xs = list.map((o) => {
    const [a, b] = span(o);
    const top = (Math.max(a, d0) - d0) / 6e4, bottom = (Math.min(Math.max(b, +a + 15 * 6e4), d1) - d0) / 6e4;
    return { o, top, bottom: Math.max(bottom, top + 15) };
  }).sort((x, y) => x.top - y.top || y.bottom - x.bottom);
  let group = [], cols = [], end = -1;
  const close = () => { group.forEach((x) => { x.cols = cols.length; }); group = []; cols = []; };
  for (const x of xs) {
    if (x.top >= end) { close(); end = -1; }
    let c = cols.findIndex((last) => last <= x.top);
    if (c < 0) { c = cols.length; cols.push(0); }
    cols[c] = x.bottom; x.col = c; group.push(x); end = Math.max(end, x.bottom);
  }
  close();
  return xs;
}
function moveNowLine() {
  const l = $('.nowline'); if (!l) return;
  const t = new Date();
  l.style.top = `${(t.getHours() * 60 + t.getMinutes()) / 60 * HH}px`;
}

function drawAgenda(body, s, e) {
  const days = Array.from({ length: daysBetween(s, e) }, (_, i) => addDays(s, i));
  const map = byDay(days, S.occ), today = new Date();
  const wrap = h('div', { class: 'agenda' });
  let any = false;
  for (const d of days) {
    const list = map.get(ymd(d));
    if (!list.length) continue;
    any = true;
    wrap.append(h('div', { class: `aday ${sameDay(d, today) ? 'today' : ''}` },
      h('div', { class: 'when', onclick: () => go('day', d), style: { cursor: 'pointer' } }, h('div', { class: 'n' }, d.getDate()),
        h('div', { class: 'w' }, d.toLocaleDateString([], { weekday: 'short', month: 'short' }))),
      h('div', { class: 'evs' }, list.map((o) => agendaRow(o, d)))));
  }
  if (!any) wrap.append(h('div', { class: 'empty' }, icon('agenda'), h('p', null, shownCals().length ? 'Nothing planned in these weeks.' : 'Every calendar is hidden: tick one in the sidebar.')));
  wrap.append(h('p', null, h('button', { class: 'pillbtn noic', onclick: () => { S.agendaDays = (S.agendaDays || 31) + 61; drawView(); } }, 'Show more')));
  body.append(wrap);
}
function agendaRow(o, d) {
  const [a, b] = span(o);
  const tm = o.allDay ? 'All day' : longEvent(o) || !sameDay(a, new Date(+b - 1)) ? (sameDay(a, d) ? `From ${fmtTime(a)}` : sameDay(b, d) ? `Until ${fmtTime(b)}` : 'All day') : `${fmtTime(a)} – ${fmtTime(b)}`;
  return h('div', { class: 'arow', style: { '--c': colorOf(o.calendarId) }, onclick: () => openEvent(o) },
    h('span', { class: 'dot' }), h('span', { class: 'tm' }, tm),
    h('div', { style: { minWidth: 0 } }, h('div', { class: 'nm', style: o.status === 'CANCELLED' ? { textDecoration: 'line-through' } : null }, o.title || '(no title)'),
      o.location || (o.people || []).length || (o.members || []).length ? h('div', { class: 'sub' }, [(o.members || []).map(memberOf).filter(Boolean).map((m) => m.displayName).join(', '),
        o.location, (o.people || []).map((p) => p.name || p.email).join(', ')].filter(Boolean).join(' · ')) : null));
}

// ------------------------------------------------------------------ one event
const ridQ = (rid) => (rid ? `?recurrenceId=${encodeURIComponent(rid)}` : '');
/** The event as shown for one occurrence (an occurrence that was not changed has the series' times moved to its date). */
function forOccurrence(j, rid) {
  if (!rid || (j.overrides || []).includes(rid) || !j.rrule) return j;
  const s = j.allDay ? parseDay(j.start) : new Date(j.start), e = j.allDay ? parseDay(j.end) : new Date(j.end);
  const ns = j.allDay ? parseDay(rid) : new Date(rid);
  const ne = new Date(+ns + (e - s));
  return { ...j, start: j.allDay ? ymd(ns) : ns.toISOString(), end: j.allDay ? ymd(ne) : ne.toISOString() };
}
function mapsLink(place) { return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place)}`; }
function eventCard(j, inDialog) {
  const c = calOf(j.calendarId), w = c.writable;
  const line = (ic, ...v) => h('div', { class: 'line' }, icon(ic), h('div', { class: 'v' }, ...v));
  const people = (j.people || []).filter((p) => p.name || p.email);
  const occ = { ...j, recurring: !!j.rrule, recurrenceId: j.recurrenceId };
  return h('div', { class: 'evd', style: { '--c': c.color || 'var(--brand)' } },
    h('div', { class: 'tools' },
      w ? h('a', { class: 'iconbtn', title: 'Change (e)', href: `#/edit/${j.id}${j.recurrenceId ? `?rid=${encodeURIComponent(j.recurrenceId)}` : ''}`, onclick: closeDialogs }, icon('edit')) : null,
      writable().length ? h('a', { class: 'iconbtn', title: 'Duplicate', href: `#/new?copy=${j.id}`, onclick: closeDialogs }, icon('dup')) : null,
      h('a', { class: 'iconbtn', title: 'Download (.ics)', href: `/api/events/${j.id}?format=ics`, download: `${(j.title || 'event').replace(/[^\w -]/g, '')}.ics` }, icon('download')),
      w ? h('button', { class: 'iconbtn', title: 'Delete', onclick: () => deleteEvent(occ) }, icon('delete')) : null,
      inDialog ? h('button', { class: 'iconbtn', title: 'Close', onclick: closeDialogs }, icon('close')) : null),
    h('h2', null, h('span', { class: 'sq' }), h('span', null, j.title || '(no title)',
      j.status === 'CANCELLED' ? h('span', { class: 'chip', style: { marginLeft: '8px' } }, 'Cancelled') : j.status === 'TENTATIVE' ? h('span', { class: 'chip', style: { marginLeft: '8px' } }, 'Tentative') : null)),
    line('clock', whenText(j), j.timezone && j.timezone !== LOCAL_TZ && !j.allDay ? h('div', { class: 'muted small' }, `Time zone ${j.timezone.replace(/_/g, ' ')}`) : null),
    j.rrule ? line('repeat', describeRule(j.rrule, j.allDay ? parseDay(j.start) : new Date(j.start))) : null,
    (j.members || []).length ? line('person', h('div', { class: 'chiprow' }, j.members.map((m) => h('span', { class: 'chip mchip' }, memberBadge(m), `For ${m.displayName}`)))) : null,
    j.location ? line('place', h('a', { class: 'lnk', href: mapsLink(j.location), target: '_blank', rel: 'noopener' }, j.location)) : null,
    people.length ? line('people', h('div', { class: 'chiprow' }, people.map((p) => {
      const label = p.name || p.email;
      const href = p.contactUrl || (p.email ? `mailto:${p.email}` : null);
      return h(href ? 'a' : 'span', { class: 'chip', href, target: p.contactUrl ? '_blank' : null, title: p.email || '' }, p.contactUrl ? icon('contacts', 's') : null, label);
    }))) : null,
    (j.reminders || []).length ? line('bell', (j.reminders || []).map((m) => describeReminder(m, j.allDay)).join(', ')) : null,
    j.notes ? line('note', h('div', { style: { whiteSpace: 'pre-wrap' } }, j.notes)) : null,
    j.url ? line('link', h('a', { class: 'lnk', href: j.url, target: '_blank', rel: 'noopener' }, j.url)) : null,
    line('today', c.name || '', j.busy === false ? h('span', { class: 'muted' }, ' · shown as free') : null,
      c.kind === 'birthdays' ? h('div', { class: 'muted small' }, 'From ioContacts; change the birthday there.') : null,
      c.kind === 'holidays' ? h('div', { class: 'muted small' }, 'A public holiday (Settings › Holidays).') : null));
}
function closeDialogs() { document.querySelectorAll('.dialog-back').forEach((d) => d.remove()); }
async function openEvent(o) {
  let j;
  try { j = await api(`/api/events/${o.id}${ridQ(o.recurrenceId)}`); } catch (e) { fail(e); return; }
  j = forOccurrence(j, o.recurrenceId);
  if (o.recurrenceId) j.recurrenceId = o.recurrenceId;
  closeDialogs();
  const back = h('div', { class: 'dialog-back' });
  back.addEventListener('click', (e) => { if (e.target === back) back.remove(); });
  back.append(h('div', { class: 'dialog', role: 'dialog' }, eventCard(j, true)));
  document.body.append(back);
  S.open = j;
}
async function showEventPage(page, r) {
  let j = await api(`/api/events/${r.id}${ridQ(r.rid)}`);
  j = forOccurrence(j, r.rid);
  if (r.rid) j.recurrenceId = r.rid;
  S.open = j;
  page.append(h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: `#/${S.view}/${ymd(S.date)}`, title: 'Back' }, icon('back')), h('h1', null, 'Event')),
    h('div', { class: 'box', style: { maxWidth: '640px' } }, eventCard(j, false)));
}
async function deleteEvent(o) {
  let scope = 'all';
  if (o.recurring && o.recurrenceId) { scope = await askScope('Delete'); if (!scope) return; }
  else if (!await confirmDialog('Delete event', `Delete “${o.title || 'this event'}”${o.recurring ? ' and every time it repeats' : ''}?`, 'Delete', true)) return;
  const qs = o.recurrenceId ? `?scope=${scope}&recurrenceId=${encodeURIComponent(o.recurrenceId)}` : '';
  try { await api(`/api/events/${o.id}${qs}`, { method: 'DELETE' }); closeDialogs(); toast('Deleted'); } catch (e) { fail(e); return; }
  await loadCals();
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView(); else go(S.view, S.date);
}

// ------------------------------------------------------------------ the event form
const TIMED_REMINDERS = [0, 5, 10, 15, 30, 60, 120, 1440, 2880, 10080];
const ALLDAY_REMINDERS = [-540, 900, 2340, 9540];
function zones(cur) {
  let list = [];
  try { list = Intl.supportedValuesOf('timeZone'); } catch { list = [LOCAL_TZ, 'UTC']; }
  if (!list.includes('UTC')) list = ['UTC', ...list];
  return [...new Set([cur, LOCAL_TZ, ...list].filter(Boolean))];
}
const hm = (d) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
const nthOf = (d) => { const n = Math.ceil(d.getDate() / 7); return n >= 5 || addDays(d, 7).getMonth() !== d.getMonth() && n === 5 ? -1 : n; };
const WEEKDAYS = ['MO', 'TU', 'WE', 'TH', 'FR'];

/** What the repeat menu shows for a rule: {kind, interval, freq, days, ends, until, count, text}. */
function readRule(rule, d) {
  const out = { kind: 'none', interval: 1, freq: 'WEEKLY', days: [RDAY[d.getDay()]], ends: 'never', until: '', count: 10, text: rule || '' };
  if (!rule) return out;
  const p = Object.fromEntries(rule.split(';').filter(Boolean).map((x) => x.split('=')));
  out.freq = p.FREQ || 'WEEKLY'; out.interval = +(p.INTERVAL || 1);
  if (p.COUNT) { out.ends = 'count'; out.count = +p.COUNT; }
  if (p.UNTIL) { out.ends = 'until'; const u = p.UNTIL; out.until = `${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}`; }
  const extra = Object.keys(p).filter((k) => !['FREQ', 'INTERVAL', 'COUNT', 'UNTIL', 'WKST', 'BYDAY', 'BYMONTHDAY'].includes(k));
  const days = p.BYDAY ? p.BYDAY.split(',') : [];
  const plainDays = days.every((x) => /^[A-Z]{2}$/.test(x));
  if (days.length) out.days = plainDays ? days : out.days;
  if (extra.length) { out.kind = 'keep'; return out; }
  const one = out.interval === 1;
  if (p.FREQ === 'DAILY' && !p.BYDAY && !p.BYMONTHDAY) out.kind = one ? 'daily' : 'custom';
  else if (p.FREQ === 'WEEKLY' && !p.BYMONTHDAY && plainDays) {
    if (one && (!days.length || (days.length === 1 && days[0] === RDAY[d.getDay()]))) out.kind = 'weekly';
    else if (one && days.length === 5 && WEEKDAYS.every((x) => days.includes(x))) out.kind = 'weekdays';
    else out.kind = 'custom';
  } else if (p.FREQ === 'MONTHLY' && one && !p.BYDAY && (!p.BYMONTHDAY || +p.BYMONTHDAY === d.getDate())) out.kind = 'monthly';
  else if (p.FREQ === 'MONTHLY' && one && days.length === 1 && !p.BYMONTHDAY && /^-?\d[A-Z]{2}$/.test(days[0])) out.kind = 'monthlyNth';
  else if (p.FREQ === 'YEARLY' && !p.BYDAY && !p.BYMONTHDAY) out.kind = one ? 'yearly' : 'custom';
  else if (['DAILY', 'MONTHLY', 'YEARLY'].includes(p.FREQ) && !p.BYDAY && !p.BYMONTHDAY) out.kind = 'custom';
  else out.kind = 'keep';
  return out;
}
/** The rule for what the repeat controls say. */
function makeRule(st, d, allDay) {
  const day = RDAY[d.getDay()];
  const base = {
    none: null, keep: st.text.split(';').filter((x) => !/^(UNTIL|COUNT)=/.test(x)).join(';'),
    daily: 'FREQ=DAILY', weekly: `FREQ=WEEKLY;BYDAY=${day}`, weekdays: 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR',
    monthly: `FREQ=MONTHLY;BYMONTHDAY=${d.getDate()}`, monthlyNth: `FREQ=MONTHLY;BYDAY=${nthOf(d)}${day}`, yearly: 'FREQ=YEARLY',
    custom: [`FREQ=${st.freq}`, st.interval > 1 ? `INTERVAL=${st.interval}` : null,
      st.freq === 'WEEKLY' ? `BYDAY=${(st.days.length ? st.days : [day]).join(',')}` : null].filter(Boolean).join(';'),
  }[st.kind];
  if (!base) return null;
  if (st.ends === 'count' && st.count > 0) return `${base};COUNT=${st.count}`;
  if (st.ends === 'until' && st.until) {
    const u = parseDay(st.until);
    return `${base};UNTIL=${allDay ? st.until.replace(/-/g, '') : new Date(u.getFullYear(), u.getMonth(), u.getDate(), 23, 59, 59).toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z')}`;
  }
  return base;
}

async function showEdit(page, r) {
  const editing = r.view === 'edit';
  const cals = writable().filter((c) => !isAuto(c));
  if (!cals.length) { page.append(h('div', { class: 'empty' }, icon('today'), h('p', null, 'You cannot add events to any calendar.'))); return; }
  let j;
  if (editing) {
    j = forOccurrence(await api(`/api/events/${r.id}${ridQ(r.rid)}`), r.rid);
  } else if (r.copy) {
    j = await api(`/api/events/${r.copy}`);
    delete j.id;
  } else {
    const d = r.date ? parseDay(r.date) : dayStart(new Date());
    let s;
    if (r.time) { const [hh, mm] = r.time.split(':').map(Number); s = new Date(d.getFullYear(), d.getMonth(), d.getDate(), hh, mm); }
    else if (sameDay(d, new Date())) { s = new Date(); s.setMinutes(0, 0, 0); s.setHours(s.getHours() + 1); }
    else s = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 9);
    const lastCal = cals.find((c) => c.id === +S.settings.lastCalendar && !S.hidden.has(c.id)) || cals.find((c) => !S.hidden.has(c.id)) || cals[0];
    const rem = S.settings.defaultReminder;
    j = { title: '', allDay: !!r.allDay, start: r.allDay ? ymd(d) : s.toISOString(), end: r.allDay ? ymd(addDays(d, 1)) : new Date(+s + 3600e3).toISOString(),
      calendarId: lastCal.id, timezone: lastCal.timezone || LOCAL_TZ, people: [], reminders: r.allDay || rem === undefined || rem === '' ? [] : [+rem], busy: true };
  }
  const original = j;
  const C = calOf(j.calendarId);
  const fld = (l, e, extra) => h('label', { class: 'field', style: extra }, h('span', null, l), e);
  const title = h('input', { class: 't', value: j.title || '', placeholder: 'Add a title', style: { fontSize: '20px', height: '48px' } });
  const calSel = h('select', { class: 't' }, cals.map((c) => h('option', { value: c.id, selected: c.id === j.calendarId ? true : null }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  if (editing && !cals.some((c) => c.id === j.calendarId)) calSel.prepend(h('option', { value: j.calendarId, selected: true }, C.name || 'This calendar'));
  // when
  const s0 = j.allDay ? parseDay(j.start) : new Date(j.start), e0 = j.allDay ? addDays(parseDay(j.end), -1) : new Date(j.end);
  const allDay = h('input', { type: 'checkbox', checked: j.allDay });
  const sd = h('input', { class: 't', type: 'date', value: ymd(s0), required: true }), st = h('input', { class: 't', type: 'time', value: hm(s0), step: 300 });
  const ed = h('input', { class: 't', type: 'date', value: ymd(e0), required: true }), et = h('input', { class: 't', type: 'time', value: hm(e0), step: 300 });
  const tz = h('select', { class: 't', style: { width: 'auto', maxWidth: '260px' } }, zones(j.timezone || C.timezone || LOCAL_TZ).map((z) => h('option', { value: z, selected: z === (j.timezone || C.timezone || LOCAL_TZ) ? true : null }, z.replace(/_/g, ' '))));
  const tzWrap = h('span', { class: 'prefck' }, icon('globe', 's'), tz);
  const startAt = () => (allDay.checked ? parseDay(sd.value) : new Date(`${sd.value}T${st.value || '00:00'}`));
  const endAt = () => (allDay.checked ? parseDay(ed.value) : new Date(`${ed.value}T${et.value || '00:00'}`));
  let length = endAt() - startAt();
  const onStart = () => { if (!sd.value) return; const e = new Date(+startAt() + Math.max(0, length)); ed.value = ymd(e); if (!allDay.checked) et.value = hm(e); drawRepeat(); drawReminders(); };
  const onEnd = () => { if (!ed.value) return; length = endAt() - startAt(); if (length < 0) { length = allDay.checked ? 0 : 3600e3; onStart(); } };
  sd.onchange = st.onchange = onStart; ed.onchange = et.onchange = onEnd;
  const timedBits = [st, et, tzWrap];
  const showTimes = () => { timedBits.forEach((x) => { x.hidden = allDay.checked; }); };
  allDay.onchange = () => {
    if (allDay.checked) { length = Math.max(0, daysBetween(startAt(), endAt()) * 864e5); reminders.splice(0, reminders.length, ...reminders.filter((m) => ALLDAY_REMINDERS.includes(m))); }
    else { length = 3600e3; if (sd.value === ed.value) { const e = new Date(+startAt() + length); et.value = hm(e); } reminders.splice(0, reminders.length, ...reminders.filter((m) => TIMED_REMINDERS.includes(m))); }
    showTimes(); drawReminders();
  };
  showTimes();
  // repeat
  const rs = readRule(j.rrule, s0);
  const repSel = h('select', { class: 't', style: { width: 'auto' } });
  const repMore = h('div', { style: { display: 'grid', gap: '8px', marginTop: '8px' } });
  const drawRepeat = () => {
    const d = startAt();
    const opts = [['none', 'Does not repeat'], ['daily', 'Every day'], ['weekly', `Every week on ${DOW(d.getDay(), 'long')}`], ['weekdays', 'Every weekday (Monday to Friday)'],
      ['monthly', `Every month on day ${d.getDate()}`], ['monthlyNth', `Every month on the ${ordinal(nthOf(d))} ${DOW(d.getDay(), 'long')}`],
      ['yearly', `Every year on ${d.toLocaleDateString([], { month: 'long', day: 'numeric' })}`], ['custom', 'Custom…']];
    if (rs.kind === 'keep') opts.push(['keep', describeRule(rs.text, d) + ' (as set elsewhere)']);
    repSel.replaceChildren(...opts.map(([v, l]) => h('option', { value: v, selected: v === rs.kind ? true : null }, l)));
    const every = h('input', { class: 't', type: 'number', min: 1, max: 99, value: rs.interval, style: { width: '80px' }, oninput: (e) => { rs.interval = Math.max(1, +e.target.value || 1); } });
    const unit = h('select', { class: 't', style: { width: 'auto' }, onchange: (e) => { rs.freq = e.target.value; drawRepeat(); } },
      [['DAILY', 'days'], ['WEEKLY', 'weeks'], ['MONTHLY', 'months'], ['YEARLY', 'years']].map(([v, l]) => h('option', { value: v, selected: v === rs.freq ? true : null }, l)));
    const days = h('div', { class: 'days7' }, [0, 1, 2, 3, 4, 5, 6].map((i) => {
      const k = RDAY[(i + weekStart()) % 7];
      const lab = h('label', { class: rs.days.includes(k) ? 'on' : '', title: DOW((i + weekStart()) % 7, 'long') }, DOW((i + weekStart()) % 7, 'narrow'));
      lab.onclick = (e) => { e.preventDefault(); rs.days = rs.days.includes(k) ? rs.days.filter((x) => x !== k) : [...rs.days, k]; lab.classList.toggle('on'); };
      return lab;
    }));
    const endSel = h('select', { class: 't', style: { width: 'auto' }, onchange: (e) => { rs.ends = e.target.value; drawRepeat(); } },
      [['never', 'Never ends'], ['until', 'Ends on'], ['count', 'Ends after']].map(([v, l]) => h('option', { value: v, selected: v === rs.ends ? true : null }, l)));
    const until = h('input', { class: 't', type: 'date', value: rs.until || ymd(addMonths(d, 3)), onchange: (e) => { rs.until = e.target.value; } });
    if (!rs.until) rs.until = until.value;
    const count = h('input', { class: 't', type: 'number', min: 1, max: 999, value: rs.count, style: { width: '90px' }, oninput: (e) => { rs.count = Math.max(1, +e.target.value || 1); } });
    fill(repMore, 
      rs.kind === 'custom' ? h('div', { class: 'when-row' }, 'Every', every, unit) : null,
      rs.kind === 'custom' && rs.freq === 'WEEKLY' ? days : null,
      rs.kind !== 'none' ? h('div', { class: 'when-row' }, endSel, rs.ends === 'until' ? until : null, rs.ends === 'count' ? [count, ' times'] : null) : null);
  };
  repSel.onchange = () => { rs.kind = repSel.value; drawRepeat(); };
  drawRepeat();
  // place, people
  const place = h('input', { class: 't', value: j.location || '', placeholder: 'Address or place' });
  const people = (j.people || []).filter((p) => p.role !== 'organizer').map((p) => ({ name: p.name, email: p.email, contactId: p.contactId }));
  const pchips = h('div', { class: 'chiprow' });
  const pin = h('input', { class: 't', placeholder: S.status.iocontacts ? 'Add someone (from ioContacts, or type a name or email)' : 'Add someone (a name or email)', autocomplete: 'off' });
  const drop = h('div', { class: 'drop', hidden: true });
  const drawPeople = () => pchips.replaceChildren(...people.map((p, i) => h('span', { class: 'chip', title: p.email || '' }, p.contactId ? icon('contacts', 's') : icon('person', 's'), p.name || p.email,
    h('span', { class: 'x', title: 'Remove', onclick: () => { people.splice(i, 1); drawPeople(); } }, icon('close', 's')))));
  const addPerson = (p) => {
    if (!p.name && !p.email) return;
    if (!people.some((x) => (x.email && x.email === p.email) || (!x.email && !p.email && x.name === p.name))) people.push(p);
    pin.value = ''; drop.hidden = true; drawPeople(); pin.focus();
  };
  const typed = () => { const v = pin.value.trim(); const m = v.match(/^(.*?)\s*<([^>]+@[^>]+)>$/); return m ? { name: m[1], email: m[2] } : /^\S+@\S+\.\S+$/.test(v) ? { name: null, email: v } : { name: v, email: null }; };
  let pt, pseq = 0;
  pin.addEventListener('input', () => {
    clearTimeout(pt);
    const v = pin.value.trim();
    if (!v) { drop.hidden = true; return; }
    pt = setTimeout(async () => {
      const n = ++pseq;
      let res = { items: [] };
      try { res = await api(`/api/people?q=${encodeURIComponent(v)}&limit=8`); } catch { /* typed only */ }
      if (n !== pseq) return;
      fill(drop, ...res.items.map((p) => h('div', { class: 'row', onmousedown: (e) => { e.preventDefault(); addPerson({ name: p.name, email: p.email, contactId: p.contactId }); } },
        p.contactId ? icon('contacts', 's') : icon('person', 's'), h('div', { class: 'who' }, h('div', { class: 'nm' }, p.name || p.email), p.email && p.name ? h('div', { class: 'sub' }, p.email) : null))),
      h('div', { class: 'row', onmousedown: (e) => { e.preventDefault(); addPerson(typed()); } }, icon('add', 's'), h('div', { class: 'who' }, h('div', { class: 'nm' }, `Add “${v}”`))),
      res.error ? h('div', { class: 'muted small', style: { padding: '6px 10px' } }, res.error) : null);
      drop.hidden = false;
    }, 180);
  });
  pin.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); addPerson(typed()); } if (e.key === 'Escape') drop.hidden = true; });
  pin.addEventListener('blur', () => setTimeout(() => { drop.hidden = true; }, 150));
  drawPeople();
  // the family members it is for (shared calendars)
  const forWho = new Set((j.members || []).map((m) => m.id));
  const mchips = h('div', { class: 'chiprow' });
  const drawMembers = () => fill(mchips, S.members.map((m) => h('button', { type: 'button', class: `chip mchip toggle ${forWho.has(m.id) ? 'on' : ''}`, 'aria-pressed': forWho.has(m.id) ? 'true' : 'false',
    onclick: () => { if (forWho.has(m.id)) forWho.delete(m.id); else forWho.add(m.id); drawMembers(); } }, memberBadge(m), m.displayName)));
  drawMembers();
  const forSec = h('div', null, h('div', { class: 'fsec' }, icon('person'), 'For'), mchips,
    h('p', { class: 'muted small', style: { margin: '4px 0 0' } }, 'Who in the family this is for. Calendar apps show it as a category.'));
  const showFor = () => { forSec.hidden = !S.members.length || !calOf(+calSel.value).shared; };
  calSel.addEventListener('change', showFor);
  showFor();
  // reminders
  const reminders = [...(j.reminders || [])];
  const rchips = h('div', { class: 'chiprow' });
  const drawReminders = () => {
    const opts = (allDay.checked ? ALLDAY_REMINDERS : TIMED_REMINDERS).filter((m) => !reminders.includes(m));
    const add = h('select', { class: 't', style: { width: 'auto', height: '32px' }, onchange: (e) => { if (e.target.value !== '') { reminders.push(+e.target.value); reminders.sort((a, b) => a - b); drawReminders(); } } },
      h('option', { value: '' }, reminders.length ? 'Add another' : 'Add a reminder'), opts.map((m) => h('option', { value: m }, describeReminder(m, allDay.checked))));
    fill(rchips, ...reminders.map((m, i) => h('span', { class: 'chip' }, icon('bell', 's'), describeReminder(m, allDay.checked),
      h('span', { class: 'x', title: 'Remove', onclick: () => { reminders.splice(i, 1); drawReminders(); } }, icon('close', 's')))), opts.length ? add : null);
  };
  drawReminders();
  const notes = h('textarea', { class: 't', placeholder: 'Notes' }, j.notes || '');
  const url = h('input', { class: 't', type: 'url', value: j.url || '', placeholder: 'https://' });
  const status = h('select', { class: 't' }, [['', 'Confirmed'], ['TENTATIVE', 'Tentative'], ['CANCELLED', 'Cancelled']].map(([v, l]) => h('option', { value: v, selected: (j.status === 'CONFIRMED' ? '' : j.status || '') === v ? true : null }, l)));
  const busy = h('select', { class: 't' }, h('option', { value: '1', selected: j.busy !== false ? true : null }, 'Busy'), h('option', { value: '0', selected: j.busy === false ? true : null }, 'Free'));

  const save = async () => {
    if (!sd.value || !ed.value) { toast('A date, please'); return; }
    if (endAt() < startAt()) { toast('The event ends before it starts'); return; }
    const data = { title: title.value.trim(), calendarId: +calSel.value, allDay: allDay.checked, location: place.value.trim() || null, notes: notes.value.trim() ? notes.value : null,
      people, reminders, url: url.value.trim() || null, status: status.value || null, busy: busy.value === '1' };
    if (pin.value.trim()) people.push(typed());
    if (!forSec.hidden) data.members = [...forWho];
    if (allDay.checked) { data.start = sd.value; data.end = ymd(addDays(parseDay(ed.value), 1)); }
    else { data.start = `${sd.value}T${st.value}`; data.end = `${ed.value}T${et.value}`; data.timezone = tz.value; }
    const rule = makeRule(rs, startAt(), allDay.checked);
    if (!editing || rule !== (original.rrule || null) || !r.rid) data.rrule = rule;
    try {
      if (!editing) {
        await api('/api/events', { method: 'POST', json: data });
        saveSettings({ lastCalendar: data.calendarId });
        toast('Saved');
      } else {
        let qs = '';
        if (original.rrule && r.rid) {
          const scope = await askScope('Change');
          if (!scope) return;
          qs = `?scope=${scope}&recurrenceId=${encodeURIComponent(r.rid)}`;
          if (scope === 'this') delete data.rrule;
        }
        await api(`/api/events/${r.id}${qs}`, { method: 'PATCH', json: data });
        toast('Saved');
      }
      await loadCals();
      go(S.view, parseDay(sd.value));
    } catch (e) { fail(e); }
  };
  page.classList.add('form');
  page.append(h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: `#/${S.view}/${ymd(S.date)}`, title: 'Cancel' }, icon('close')),
    h('h1', null, editing ? 'Change event' : 'New event')),
  title,
  h('div', { class: 'fsec' }, icon('clock'), 'When'),
  h('div', { class: 'when-row' }, sd, st, '–', ed, et, h('label', { class: 'check' }, allDay, ' All day'), tzWrap),
  h('div', { class: 'fsec' }, icon('repeat'), 'Repeat'), h('div', null, repSel, repMore),
  h('div', { class: 'fsec' }, icon('today'), 'Calendar'), h('div', { class: 'grid' }, fld('Calendar', calSel), fld('Show me as', busy), fld('Status', status)),
  forSec,
  h('div', { class: 'fsec' }, icon('place'), 'Where'), place,
  h('div', { class: 'fsec' }, icon('people'), 'Who'), pchips, h('div', { class: 'picker', style: { marginTop: '6px' } }, pin, drop),
  h('div', { class: 'fsec' }, icon('bell'), 'Reminders'), rchips,
  h('p', { class: 'muted small', style: { margin: '4px 0 0' } }, 'Reminders go to the calendar apps on your phone and computer (through CalDAV).'),
  h('div', { class: 'fsec' }, icon('note'), 'Notes'), notes,
  h('div', { class: 'fsec' }, icon('link'), 'Link'), url,
  h('div', { class: 'formbar' }, h('button', { class: 'pillbtn primary', onclick: save }, icon('check', 's'), 'Save'),
    h('a', { class: 'pillbtn noic', href: `#/${S.view}/${ymd(S.date)}` }, 'Cancel'), h('span', { style: { flex: 1 } }),
    editing ? h('button', { class: 'pillbtn danger', onclick: () => deleteEvent({ ...original, id: r.id, recurring: !!original.rrule, recurrenceId: r.rid }) }, icon('delete', 's'), 'Delete') : null));
  title.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); });
  page.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); } });
  if (!editing) title.focus();
}

// ------------------------------------------------------------------ search
async function showSearch(page, r) {
  S.q = r.q;
  if ($('#q').value !== r.q) $('#q').value = r.q;
  page.append(h('div', { class: 'pagehead' }, h('h1', null, r.q ? `“${r.q}”` : 'Search')));
  if (!r.q) { page.append(h('p', { class: 'muted' }, 'Type in the search box: a title, a place, a name or words from the notes.')); return; }
  const res = await api(`/api/events?q=${encodeURIComponent(r.q)}&limit=300`);
  const now = Date.now();
  const at = (x) => (x.next ? (x.allDay ? parseDay(x.next.start) : new Date(x.next.start)) : null);
  const soon = res.items.filter((x) => at(x) && (x.allDay ? +addDays(at(x), 1) : +new Date(x.next.end)) >= now).sort((a, b) => at(a) - at(b));
  const past = res.items.filter((x) => !soon.includes(x)).sort((a, b) => (at(b) || 0) - (at(a) || 0));
  const row = (x) => {
    const d = at(x);
    const href = `#/event/${x.id}${x.next && x.next.recurrenceId ? `?rid=${encodeURIComponent(x.next.recurrenceId)}` : ''}`;
    return h('a', { class: 'arow', href, style: { '--c': colorOf(x.calendarId), color: 'inherit', textDecoration: 'none' } }, h('span', { class: 'dot' }),
      h('span', { class: 'tm' }, d ? d.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' }) + (x.allDay ? '' : ` ${fmtTime(d)}`) : ''),
      h('div', { style: { minWidth: 0 } }, h('div', { class: 'nm' }, x.title || '(no title)', x.recurring ? h('span', { class: 'muted small' }, ' · repeats') : null),
        h('div', { class: 'sub' }, [x.location, calOf(x.calendarId).name].filter(Boolean).join(' · '))));
  };
  if (!res.items.length) { page.append(h('div', { class: 'empty' }, icon('search'), h('p', null, 'Nothing matches.'))); return; }
  if (soon.length) page.append(h('div', { class: 'fsec' }, 'Coming up'), h('div', { class: 'evs' }, soon.map(row)));
  if (past.length) page.append(h('div', { class: 'fsec' }, 'Earlier'), h('div', { class: 'evs' }, past.map(row)));
}

// ------------------------------------------------------------------ import and export
async function showImport(page) {
  const w = writable().filter((c) => !isAuto(c));
  const sel = h('select', { class: 't', style: { maxWidth: '320px' } }, w.map((c) => h('option', { value: c.id }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  const file = h('input', { type: 'file', accept: '.ics,.ical,.ifb,text/calendar', multiple: true });
  const replace = h('input', { type: 'checkbox', checked: true });
  const out = h('div');
  const run = async () => {
    if (!file.files.length) { toast('Pick a file first'); return; }
    const tot = { created: 0, updated: 0, skipped: 0, errors: [] };
    for (const f of file.files) {
      const fd = new FormData(); fd.append('file', f);
      try {
        const r = await api(`/api/calendars/${sel.value}/import?replace=${replace.checked}`, { method: 'POST', body: fd });
        tot.created += r.created; tot.updated += r.updated; tot.skipped += r.skipped; tot.errors.push(...r.errors);
      } catch (e) { tot.errors.push(`${f.name}: ${e.message}`); }
    }
    fill(out, h('p', null, `${tot.created} added, ${tot.updated} updated${tot.skipped ? `, ${tot.skipped} left as they were` : ''}.`),
      tot.errors.length ? h('details', null, h('summary', { class: 'lnk' }, `${tot.errors.length} could not be read`), h('ul', null, tot.errors.slice(0, 50).map((x) => h('li', null, x)))) : null);
    await loadCals();
  };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Import and export')),
    w.length ? h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Import'),
      h('p', null, 'An iCalendar file (.ics) from Google Calendar (Settings › Import & export › Export, then unzip), Apple Calendar (File › Export), Outlook or any other calendar. Repeating events, exceptions, reminders and time zones come along.'),
      h('div', { class: 'pform' }, h('label', { class: 'field' }, h('span', null, 'Into the calendar'), sel), file,
        h('label', { class: 'check' }, replace, ' Update events that are already here (same UID)'),
        h('p', null, h('button', { class: 'pillbtn primary', onclick: run }, icon('upload', 's'), 'Import'))), out) : null,
    h('div', { class: 'box' }, h('h2', null, icon('download'), 'Export'),
      h('p', null, 'Each calendar as one .ics file, which any calendar app can import.'),
      h('table', { class: 't' }, S.cals.map((c) => h('tr', null, h('td', null, h('span', { class: 'chip-ev', style: { '--c': c.color, display: 'inline-flex' } }, h('span', { class: 'dot' }), h('span', { class: 'nm' }, c.name))),
        h('td', { class: 'muted' }, c.kind === 'birthdays' ? 'from ioContacts' : `${c.count || 0} events`),
        h('td', { style: { textAlign: 'right' } }, h('a', { class: 'pillbtn noic', href: `/api/calendars/${c.id}/export` }, 'Download'))))),
      h('p', { class: 'muted small' }, 'To keep another app in step instead of copying once, connect it: ', h('a', { class: 'lnk', href: '#/settings/devices' }, 'Settings › Apps and devices'), '.')));
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['devices', 'Apps and devices'], ['calendars', 'Calendars'], ['holidays', 'Holidays'], ...(adm ? [['users', 'Users'], ['iocontacts', 'ioContacts'], ['server', 'Server']] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, devices: setDevices, calendars: setCalendars, holidays: setHolidays, users: setUsers, iocontacts: setContacts, server: setServer }[r.tab] || setAccount)(body);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);
const kv = (k, v) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k), h('div', { class: 'v', style: { flex: 1 } }, typeof v === 'string' ? copyRow(v) : v));

async function setAccount(el) {
  const u = S.user;
  const dn = h('input', { class: 't', value: u.displayName || '' }), em = h('input', { class: 't', type: 'email', value: u.email || '' });
  const old = h('input', { class: 't', type: 'password', autocomplete: 'current-password' }), nw = h('input', { class: 't', type: 'password', autocomplete: 'new-password' });
  const ws = h('select', { class: 't' }, [[1, 'Monday'], [0, 'Sunday'], [6, 'Saturday']].map(([v, l]) => h('option', { value: v, selected: v === weekStart() ? true : null }, l)));
  const dv = h('select', { class: 't' }, [['month', 'Month'], ['week', 'Week'], ['day', 'Day'], ['agenda', 'Agenda']].map(([v, l]) => h('option', { value: v, selected: v === (S.settings.defaultView || 'month') ? true : null }, l)));
  const cur = S.settings.defaultReminder ?? '';
  const dr = h('select', { class: 't' }, h('option', { value: '' }, 'None'), TIMED_REMINDERS.map((m) => h('option', { value: m, selected: String(m) === String(cur) ? true : null }, describeReminder(m, false))));
  el.append(h('div', { class: 'box' }, h('h2', null, icon('person'), 'You'), h('div', { class: 'grid' }, fld('Display name', dn), fld('Email (for sign-in at a proxy)', em)),
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => { try { S.user = (await api('/api/auth/me', { method: 'PATCH', json: { displayName: dn.value, email: em.value } })).user; drawUser(); toast('Saved'); } catch (e) { fail(e); } } }, icon('check', 's'), 'Save'))),
  h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Preferences'), h('div', { class: 'grid' }, fld('Weeks start on', ws), fld('Open on', dv), fld('Reminder for new events', dr)),
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => { await saveSettings({ weekStart: +ws.value, defaultView: dv.value, defaultReminder: dr.value }); drawNav(); toast('Saved'); } }, icon('check', 's'), 'Save'))),
  u.hasPassword ? h('div', { class: 'box' }, h('h2', null, icon('key'), 'Password'), h('div', { class: 'grid' }, fld('Current password', old), fld('New password (8 or more)', nw)),
    h('p', null, h('button', { class: 'pillbtn', onclick: async () => { try { await api('/api/auth/password', { method: 'POST', json: { current: old.value, password: nw.value } }); old.value = nw.value = ''; toast('Password changed'); } catch (e) { fail(e); } } }, 'Change password'), ' ',
      h('button', { class: 'pillbtn noic', onclick: async () => { if (await confirmDialog('Sign out everywhere', 'Sign out on every other browser and device? (Apps with an app password keep working.)', 'Sign out the others')) { try { await api('/api/auth/logout_all', { method: 'POST' }); toast('Signed out elsewhere'); } catch (e) { fail(e); } } } }, 'Sign out everywhere else'))) : null);
}

async function setDevices(el) {
  const info = await api('/api/connect');
  const canPw = S.user.hasPassword;
  const label = h('input', { class: 't', placeholder: 'e.g. Alex’s iPhone', style: 'max-width:280px' });
  const shown = h('div'), pwlist = h('div');
  const isApple = /iPhone|iPad|Macintosh/.test(navigator.userAgent);
  const drawPw = async () => {
    const items = (await api('/api/auth/app-passwords')).items;
    pwlist.replaceChildren(items.length ? h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'Made'), h('th', null, 'Last used'), h('th')),
      items.map((p) => h('tr', null, h('td', null, p.label), h('td', null, new Date(p.created).toLocaleDateString()), h('td', null, p.lastUsed ? new Date(p.lastUsed).toLocaleString() : 'never'),
        h('td', null, h('button', { class: 'pillbtn noic danger', onclick: async () => { await api(`/api/auth/app-passwords/${p.id}`, { method: 'DELETE' }); drawPw(); } }, 'Revoke'))))) : h('p', { class: 'muted' }, 'No app passwords yet.'));
  };
  const plabel = h('input', { class: 't', name: 'label', value: /iPad/.test(navigator.userAgent) ? 'iPad' : /Macintosh/.test(navigator.userAgent) ? 'Mac' : 'iPhone', style: 'max-width:200px' });
  el.append(...[
    canPw ? h('div', { class: 'box' }, h('h2', null, icon('devices'), 'iPhone, iPad and Mac: set up in one step'),
      h('p', null, 'Download a configuration profile that adds your calendars (CalDAV) to Apple Calendar, with reminders and two-way changes. ',
        isApple ? 'Tap Download here in Safari, then open Settings › Profile Downloaded › Install.' : 'Open this page on the iPhone or iPad in Safari and tap Download, then Settings › Profile Downloaded › Install. On a Mac, open the file, then System Settings › Privacy & Security › Profiles.'),
      h('form', { method: 'POST', action: '/api/apple-profile', class: 'pform', onsubmit: () => { setTimeout(drawPw, 1500); } },
        fld('Device name', plabel),
        fld('Password', h('select', { class: 't', name: 'password' }, h('option', { value: 'new' }, 'Include a new app password for this device'), h('option', { value: 'ask' }, 'Leave it out (the device asks while installing)'))),
        h('p', null, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Download the profile'))),
      h('p', { class: 'muted small' }, 'The profile holds the app password: install it and delete the file, and revoke that password below if the device is lost. The profile is not signed, so iOS shows it as “Not Verified”; that is expected.')) : null,
    canPw ? h('div', { class: 'box' }, h('h2', null, icon('key'), 'App passwords'),
      h('p', { class: 'muted' }, 'Give every app or device its own password instead of yours; you can revoke one without touching the others. Use your user name with it.'),
      h('div', { class: 'multi' }, label, h('button', { class: 'pillbtn primary', onclick: async () => {
        try {
          const r = await api('/api/auth/app-passwords', { method: 'POST', json: { label: label.value || 'Device' } });
          shown.replaceChildren(h('p', null, h('b', null, 'Copy it now: '), 'it is shown only once.'), copyRow(r.password));
          label.value = ''; drawPw();
        } catch (e) { fail(e); }
      } }, icon('add', 's'), 'New app password')), shown, pwlist)
      : h('div', { class: 'box' }, h('h2', null, icon('key'), 'App passwords'), h('p', { class: 'muted' }, 'Your account signs in with one click and has no password, so it cannot have app passwords. Ask an admin to give it a password to connect apps.')),
    h('div', { class: 'box' }, h('h2', null, icon('today'), 'Calendar apps (CalDAV): two-way'),
      h('p', null, 'Apple Calendar (Mac: Calendar › Settings › Accounts › Add › Other CalDAV Account › Manual; iPhone: Settings › Calendar › Accounts › Add Account › Other › Add CalDAV Account), DAVx⁵ on Android, Thunderbird, Evolution, GNOME Calendar, KDE, Outlook with a CalDAV add-in: give the server, your user name and an app password.'),
      kv('Server', info.server), kv('User name', info.user), kv('CalDAV', info.caldav),
      h('details', null, h('summary', { class: 'lnk' }, 'Address of each calendar (for apps that want one, like Thunderbird)'), info.calendars.map((c) => kv(c.name, c.caldav)))),
    h('div', { class: 'box' }, h('h2', null, icon('link'), 'Subscribe (read-only)'),
      h('p', null, 'For apps that cannot sign in: Google Calendar (Other calendars › From URL), Outlook (Add calendar › Subscribe from web), Apple Calendar (File › New Calendar Subscription). They refresh every few hours. The links are private to you: anyone who has one can read those events.'),
      kv('Everything', info.all),
      h('details', null, h('summary', { class: 'lnk' }, 'One calendar at a time'), info.calendars.map((c) => kv(c.name, c.ics))),
      kv('Free/busy', info.freebusy),
      h('p', null, h('a', { class: 'pillbtn', href: info.webcal }, icon('today', 's'), 'Open in my calendar app'), ' ',
        h('button', { class: 'pillbtn noic', onclick: async () => { if (await confirmDialog('New subscription links', 'The old links stop working; subscribed calendars need the new ones.', 'Make new links')) { await api('/api/feeds/reset', { method: 'POST' }); onRoute(); } } }, 'New links'))),
    S.status.mcp ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'),
      h('p', null, 'Claude and other assistants that speak the Model Context Protocol can read your agenda, find free time and add or change events, as you. Give the assistant its own app password (above), sent as a Bearer token.'),
      kv('MCP address', info.mcp),
      h('p', { class: 'muted small' }, 'Claude Code:'),
      copyRow(`claude mcp add --transport http iocalendar ${info.mcp} --header "Authorization: Bearer APP-PASSWORD"`),
      h('p', { class: 'muted small' }, 'Apps configured with JSON (Claude Desktop through mcp-remote, Cursor, VS Code…):'),
      copyRow(JSON.stringify({ mcpServers: { iocalendar: { command: 'npx', args: ['-y', 'mcp-remote', info.mcp, '--header', 'Authorization: Bearer APP-PASSWORD'] } } })))
      : (S.user.role === 'admin' ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'), h('p', { class: 'muted' }, 'The MCP server is off. Turn it on in ', h('a', { class: 'lnk', href: '#/settings/server' }, 'Settings › Server'), ' to let Claude and other assistants work with the calendars.')) : null),
    h('div', { class: 'box' }, h('h2', null, icon('link'), 'Other apps (REST API)'),
      h('p', null, 'JSON, iCalendar or jCal (RFC 7265) over HTTPS, with your user name and an app password (HTTP Basic) or the app password as a Bearer token. ', h('a', { class: 'lnk', href: info.api, target: '_blank' }, 'API documentation')),
      copyRow(`curl -u ${info.user}:APP-PASSWORD "${info.server}/api/occurrences?start=${ymd(new Date())}&end=${ymd(addDays(new Date(), 7))}"`))].filter(Boolean));
  if (canPw) drawPw();
}

async function setCalendars(el) {
  await loadCals();
  const tzs = zones(S.status.timezone);
  el.append(h('p', null, S.user.role !== 'viewer' ? h('button', { class: 'pillbtn', onclick: async () => { await newCalendar(true); onRoute(); } }, icon('add', 's'), 'New shared calendar') : null, ' ',
    h('button', { class: 'pillbtn', onclick: async () => { await newCalendar(false); onRoute(); } }, icon('add', 's'), 'New private calendar')),
  ...S.cals.map((c) => {
    const auto = isAuto(c);
    const name = h('input', { class: 't', value: c.name });
    const col = colorPicker(c.color);
    const tz = h('select', { class: 't' }, h('option', { value: '' }, `Server default (${S.status.timezone})`), tzs.map((z) => h('option', { value: z, selected: z === c.timezone ? true : null }, z.replace(/_/g, ' '))));
    const desc = h('input', { class: 't', value: c.description || '', placeholder: 'What it is for' });
    const canEdit = c.writable || (auto && S.user.role === 'admin');
    return h('div', { class: 'box', style: { '--c': c.color } },
      h('h2', null, h('span', { class: 'chip-ev allday', style: { '--c': c.color, display: 'inline-flex', width: '14px', height: '14px', padding: 0 } }), c.name,
        h('span', { class: 'muted small', style: { fontWeight: 400 } }, c.kind === 'birthdays' ? 'from ioContacts, read-only' : c.kind === 'holidays' ? 'public holidays, read-only' : c.shared ? 'shared with everyone' : 'only you')),
      canEdit ? [h('div', { class: 'grid' }, fld('Name', name), fld('Description', desc), auto ? null : fld('Time zone for floating times', tz)), h('div', { style: { margin: '10px 0' } }, col),
        h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => {
          const body = { name: name.value, color: col.get(), description: desc.value };
          if (!auto) body.timezone = tz.value || null;
          try { await api(`/api/calendars/${c.id}`, { method: 'PATCH', json: body }); await loadCals(); toast('Saved'); } catch (e) { fail(e); }
        } }, icon('check', 's'), 'Save'), ' ',
        !auto && (!c.shared || S.user.role === 'admin') ? h('button', { class: 'pillbtn noic danger', onclick: async () => {
          if (!await confirmDialog('Delete calendar', `Delete ${c.name} and its ${c.count || 0} events? Apps that sync it lose it too.`, 'Delete', true)) return;
          try { await api(`/api/calendars/${c.id}`, { method: 'DELETE' }); await loadCals(); onRoute(); } catch (e) { fail(e); }
        } }, 'Delete') : null)] : h('p', { class: 'muted' }, auto ? (c.kind === 'holidays' ? 'Filled from Settings › Holidays.' : 'Filled from ioContacts.') : `${c.count || 0} events. Editors and admins change shared calendars.`));
  }));
}

async function setUsers(el) {
  const [r, fam] = await Promise.all([api('/api/users'), api('/api/members')]);
  const leftOut = new Set(fam.leftOut || []);
  const roles = r.roles || ['viewer', 'editor', 'admin'];
  const name = h('input', { class: 't', placeholder: 'User name' }), pw = h('input', { class: 't', type: 'password', placeholder: 'Password (8 or more)' });
  const role = h('select', { class: 't' }, roles.map((x) => h('option', { value: x, selected: x === 'editor' ? true : null }, x)));
  const patch = async (u, body, msg) => { try { await api(`/api/users/${u.id}`, { method: 'PATCH', json: body }); toast(msg); return true; } catch (e) { fail(e); return false; } };
  el.append(h('div', { class: 'box' }, h('h2', null, icon('people'), 'Family members'),
    h('p', { class: 'muted' }, 'The accounts are the same as in the other io apps; the role here is for ioCalendar. Everyone sees the shared calendars and has a private one of their own. Viewers read the shared calendars and change only their own; editors change shared events too; admins also manage users and settings.'),
    h('p', { class: 'muted' }, 'In the family: the people events can be tagged with, each with a private calendar of their own. Leave out accounts that are not a person, such as admin.'),
    h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'Display name'), h('th', null, 'Role'), h('th', null, 'In the family'), h('th')),
      r.users.map((u) => {
        const rs = h('select', { class: 't', style: 'width:auto' }, [...new Set([...roles, u.role])].map((x) => h('option', { value: x, selected: x === u.role ? true : null }, x)));
        rs.onchange = async () => { if (!await patch(u, { role: rs.value }, 'Saved')) onRoute(); };
        const fk = h('input', { type: 'checkbox', checked: !leftOut.has(u.id), title: `${u.displayName} is someone events can be for` });
        fk.onchange = async () => {
          try { await api(`/api/members/${u.id}`, { method: 'PUT', json: { inFamily: fk.checked } }); await loadCals(); toast(fk.checked ? `${u.displayName} is in the family` : `${u.displayName} is left out of the family`); } catch (e) { fk.checked = !fk.checked; fail(e); }
        };
        return h('tr', null, h('td', null, u.name, u.suiteAdmin ? h('span', { class: 'muted small' }, ' · suite admin') : null), h('td', null, u.displayName), h('td', null, rs), h('td', null, h('label', { class: 'check' }, fk)), h('td', { style: { whiteSpace: 'nowrap' } },
          h('button', { class: 'pillbtn noic', onclick: async () => { const p = h('input', { class: 't', type: 'password' }); const v = await dialog(`New password for ${u.name}`, p, [{ label: 'Cancel', value: null }, { label: 'Set', value: () => p.value, primary: true }]); if (v) patch(u, { password: v }, 'Password set'); } }, 'Password'), ' ',
          u.role === 'viewer' && !u.passwordless ? [h('button', { class: 'pillbtn noic', title: 'One-click sign-in from the account picker', onclick: async () => { if (await confirmDialog('Remove password', `Remove ${u.name}’s password? Anyone on your home network can then sign in as ${u.name} with one click (from outside, never).`, 'Remove')) { if (await patch(u, { password: '' }, 'Password removed')) onRoute(); } } }, 'No password'), ' '] : null,
          u.id !== S.user.id ? h('button', { class: 'pillbtn noic danger', onclick: async () => { if (await confirmDialog('Delete account', `Delete ${u.name}? This removes the account from every io app, with their private calendars.`, 'Delete', true)) { try { await api(`/api/users/${u.id}`, { method: 'DELETE' }); onRoute(); } catch (e) { fail(e); } } } }, 'Delete') : null));
      })),
    h('h2', { style: { marginTop: '16px' } }, 'Add someone'), h('div', { class: 'multi' }, name, pw, role,
      h('button', { class: 'pillbtn primary', onclick: async () => { try { await api('/api/users', { method: 'POST', json: { name: name.value, password: pw.value, role: role.value } }); toast('Account made'); onRoute(); } catch (e) { fail(e); } } }, icon('add', 's'), 'Add'))));
}

async function setContacts(el) {
  const s = await api('/api/iocontacts/settings');
  const url = h('input', { class: 't', value: s.url, placeholder: 'https://contacts.example.com or http://192.168.1.10:8610', disabled: s.fromEnv ? true : null });
  const user = h('input', { class: 't', value: s.user, placeholder: 'An ioContacts user name' });
  const pw = h('input', { class: 't', type: 'password', placeholder: s.hasPassword ? '(kept)' : 'An app password made in ioContacts' });
  const cfId = h('input', { class: 't', value: s.cfId, placeholder: 'Only behind Cloudflare Access' });
  const cfSecret = h('input', { class: 't', type: 'password', placeholder: s.hasCfSecret ? '(kept)' : '' });
  const bdays = h('input', { type: 'checkbox', checked: s.birthdays });
  const out = h('div');
  const last = (x) => (x && x.synced ? `Birthdays last brought up to date ${new Date(x.synced * 1000).toLocaleString()} (${x.count} dates).` : x && x.error ? `The last sync failed: ${x.error}` : '');
  out.append(h('p', { class: 'muted small' }, last(s.lastSync)));
  el.append(h('div', { class: 'box' }, h('h2', null, icon('contacts'), 'ioContacts'),
    h('p', { class: 'muted' }, 'Optional. With ioContacts connected, the people on an event come from your contacts (with a link back to each), and a shared Birthdays calendar shows the birthdays and anniversaries kept there, brought up to date every six hours. ioCalendar talks to ioContacts from the server; make an app password for it in ioContacts (Settings › Apps and devices). Through Cloudflare Access, add a service token too.'),
    h('div', { class: 'grid' }, fld('ioContacts address', url), fld('User name', user), fld('App password', pw), fld('Cloudflare client ID', cfId), fld('Cloudflare client secret', cfSecret)),
    h('p', null, h('label', { class: 'check' }, bdays, ' Show the Birthdays calendar')),
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => {
      const body = { url: url.value, user: user.value, cfId: cfId.value, birthdays: bdays.checked };
      if (pw.value) body.password = pw.value; if (cfSecret.value) body.cfSecret = cfSecret.value;
      fill(out, h('p', null, 'Testing…'));
      try {
        const r = await api('/api/iocontacts/settings', { method: 'POST', json: body });
        S.status = await api('/api/status'); await loadCals();
        fill(out, h('p', { class: r.test && !r.test.ok ? 'warn' : null }, !r.enabled ? 'Saved (ioContacts link off).' : r.test.ok ? `Connected as ${r.test.user}: ${r.test.contacts ?? 'some'} contacts.` : `Saved, but ioContacts did not answer: ${r.test.error}`),
          r.sync ? h('p', { class: 'muted small' }, r.sync.ok ? (r.sync.count ? `Birthdays: ${r.sync.count} dates.` : 'The Birthdays calendar is off.') : `Birthdays: ${r.sync.error}`) : null);
      } catch (e) { fill(out, ); fail(e); }
    } }, icon('check', 's'), 'Save and test'), ' ',
    s.enabled ? h('button', { class: 'pillbtn noic', onclick: async () => { try { const r = await api('/api/iocontacts/sync', { method: 'POST' }); await loadCals(); toast(r.ok ? `Birthdays: ${r.count} dates` : r.error); } catch (e) { fail(e); } } }, 'Bring birthdays up to date now') : null), out));
}

async function setHolidays(el) {
  const s = await api('/api/holidays/settings');
  const adm = S.user.role === 'admin';
  const where = s.country ? [s.countryName, s.regionName].filter(Boolean).join(', ') : null;
  const last = (x) => (x && x.synced ? `Last filled ${new Date(x.synced * 1000).toLocaleString()} (${x.count} holidays, last year to three years ahead).` : x && x.error ? `The last fill failed: ${x.error}` : '');
  const box = h('div', { class: 'box' }, h('h2', null, icon('star'), 'Public holidays'),
    h('p', { class: 'muted' }, 'A shared, read-only Holidays calendar shows the public holidays of your country (and region), worked out on the server and kept up to date every day. Phones and apps get it like any other calendar; anyone can hide it in the sidebar.'),
    h('p', null, where ? `Showing the holidays of ${where}${s.guessed ? ' (from the time zone; pick another below)' : ''}.` : 'Off: no country picked.'));
  el.append(box);
  if (!adm) { box.append(h('p', { class: 'muted small' }, 'An admin picks the country.')); return; }
  const countries = (await api('/api/holidays/countries')).items;
  const country = h('select', { class: 't' }, h('option', { value: '' }, 'None (no Holidays calendar)'),
    countries.map((c) => h('option', { value: c.code, selected: c.code === s.country ? true : null }, c.name)));
  const region = h('select', { class: 't' });
  const lang = h('select', { class: 't' });
  const LANG = (code) => { try { return new Intl.DisplayNames([], { type: 'language' }).of(code.replace('_', '-')) || code; } catch { return code; } };
  const drawCountry = async (keep) => {
    const code = country.value;
    if (!code) { fill(region, h('option', { value: '' }, '—')); fill(lang, h('option', { value: '' }, '—')); region.disabled = lang.disabled = true; return; }
    const info = await api(`/api/holidays/countries/${code}`);
    fill(region, h('option', { value: '' }, info.regions.length ? 'The whole country' : 'No regions'),
      info.regions.map((r) => h('option', { value: r.code, selected: keep && r.code === s.region ? true : null }, r.name === r.code ? r.code : `${r.name} (${r.code})`)));
    fill(lang, h('option', { value: '' }, info.defaultLanguage ? `${LANG(info.defaultLanguage)} (default)` : 'Default'),
      info.languages.map((l) => h('option', { value: l, selected: keep && l === s.language ? true : null }, LANG(l))));
    region.disabled = !info.regions.length; lang.disabled = !info.languages.length;
  };
  country.onchange = () => drawCountry(false);
  await drawCountry(true);
  const out = h('div', null, h('p', { class: 'muted small' }, last(s.lastSync)));
  box.append(h('div', { class: 'grid' }, fld('Country', country), fld('Region (state, province…)', region), fld('Names in', lang)),
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => {
      try {
        const r = await api('/api/holidays/settings', { method: 'POST', json: { country: country.value, region: region.value, language: lang.value } });
        await loadCals();
        fill(out, h('p', { class: r.sync && !r.sync.ok ? 'warn' : 'muted small' }, !r.country ? 'The Holidays calendar is off.' : r.sync.ok ? `Holidays of ${[r.countryName, r.regionName].filter(Boolean).join(', ')}: ${r.sync.count} dates.` : r.sync.error));
        toast('Saved');
      } catch (e) { fail(e); }
    } }, icon('check', 's'), 'Save')), out);
}

async function setServer(el) {
  const draw = async () => {
    let s; try { s = await api('/api/server'); } catch (e) { el.replaceChildren(h('p', null, e.message)); return; }
    if (!el.isConnected) return;
    const c = s.check, p = s.progress, last = s.lastUpdate;
    const state = p.running ? 'Updating… ioCalendar restarts when it is done, and this page reloads.'
      : p.error ? `The last update failed: ${p.error}`
        : !c ? `You have v${s.version}${s.installed !== 'unknown' ? ` (${s.installed})` : ''}.`
          : c.status === 'current' ? `v${s.version} is the latest version.`
            : c.status === 'update' ? `You have v${s.version}; ${c.remoteVersion ? `v${c.remoteVersion}` : 'a newer build'} is available${c.remoteDate ? ` (${c.remoteDate})` : ''}${c.remoteMessage ? `: ${c.remoteMessage.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}.`
              : `Could not check: ${c.error}`;
    const sw = (on, label, key, locked) => h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: on, disabled: locked ? true : null, onchange: async (e) => {
      try { await api('/api/server', { method: 'POST', json: { [key]: e.target.checked } }); S.status = await api('/api/status'); toast('Saved'); draw(); } catch (err) { e.target.checked = !e.target.checked; fail(err); }
    } }), ' ', label);
    el.replaceChildren(
      h('div', { class: 'box' }, h('h2', null, icon('update'), 'ioCalendar version'),
        h('p', null, state),
        !p.running && !p.error && last ? h('p', { class: last.ok ? 'muted small' : 'warn small' }, `Last update: ${last.text}`) : null,
        h('p', null,
          h('button', { class: 'pillbtn', onclick: async () => { el.querySelector('.box p').textContent = 'Checking…'; try { await api('/api/server', { method: 'POST', json: { action: 'check' } }); } catch (e) { fail(e); } draw(); } }, icon('update', 's'), 'Check for updates'), ' ',
          s.docker ? h('span', { class: 'muted' }, 'Docker: update by pulling the image (docker compose pull && docker compose up -d).')
            : s.canRun ? h('button', { class: `pillbtn ${c && c.status === 'update' ? 'primary' : ''}`, disabled: p.running ? true : null, onclick: async () => {
              if (!await confirmDialog('Update ioCalendar', 'Fetch the newest version, refresh its packages and restart ioCalendar? Settings and events stay; the page reloads when the new version is up.', 'Update now')) return;
              if (await runUpdate()) setTimeout(draw, 2500);
            } }, icon('check', 's'), 'Update now')
              : h('span', { class: 'muted' }, 'This install cannot update itself from here (run ./update.sh in the app folder).')),
        h('p', null, sw(s.autoCheck, 'Check for a new version once a day (only GitHub’s public list of changes is asked; nothing about this server is sent)', 'autoCheck', s.autoCheckLocked)),
        s.autoCheckLocked ? h('p', { class: 'muted small' }, 'UPDATE_CHECK=0 in the environment keeps it off.') : null,
        h('p', { class: 'muted small' }, `Follows ${s.repo} (${s.branch}). Database ${s.database}; default time zone ${s.timezone}.`)),
      h('div', { class: 'box' }, h('h2', null, icon('ai'), 'MCP server'),
        h('p', null, 'The address /mcp that lets an AI assistant (Claude, for example) read the agenda, search events, find free time, add, change and move events and import calendars, and for admins check for and install updates. Each assistant signs in with an app password and acts as that account, with its rights. Off: /mcp does not answer at all.'),
        h('p', null, sw(s.mcpEnabled, 'The MCP server is on', 'mcpEnabled', s.mcpLocked)),
        s.mcpLocked ? h('p', { class: 'muted small' }, 'MCP=1 in the environment keeps it on.') : null,
        s.mcpEnabled ? [kv('Address', s.mcpUrl),
          h('p', { class: 'muted small' }, 'How to connect an assistant: ', h('a', { class: 'lnk', href: '#/settings/devices' }, 'Settings › Apps and devices'), '. On the server itself, `python -m app.mcp --user NAME` serves it over stdio.')] : null));
    if (p.running) setTimeout(() => { if (el.isConnected) draw(); }, 4000);
  };
  await draw();
}

/** Start update.sh on the server, then watch /api/status until another version or commit answers, and reload. */
async function runUpdate() {
  try { await api('/api/server', { method: 'POST', json: { action: 'update' } }); } catch (e) { fail(e); return false; }
  toast('Updating; ioCalendar restarts when it is done, and the page reloads.');
  const was = `${S.status.version}|${S.status.commit || ''}`, until = Date.now() + 240000;
  const look = async () => {
    try { const s = await fetch('/api/status', { credentials: 'same-origin' }).then((r) => r.json()); if (s.version && `${s.version}|${s.commit || ''}` !== was) { location.reload(); return; } } catch { /* restarting */ }
    if (Date.now() < until) setTimeout(look, 4000); else toast('The update did not finish; see Settings › Server.');
  };
  setTimeout(look, 4000);
  return true;
}

/** Admins: a note when the daily check found a newer version, with Update now. Hidden until the next version when dismissed. */
function updateBanner() {
  $('#updbanner')?.remove();
  const u = S.status && S.status.updateAvailable;
  let dismissed = null; try { dismissed = localStorage.getItem('iocal.updateDismissed'); } catch { /* private mode */ }
  if (!u || dismissed === u.remote) return;
  const b = h('div', { id: 'updbanner', role: 'status' }, icon('update'),
    h('span', null, `ioCalendar ${u.version ? `v${u.version}` : 'update'} is available${u.message ? `: ${u.message.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}`),
    h('button', { class: 'pillbtn primary noic', onclick: async () => { if (await confirmDialog('Update ioCalendar', 'Install the new version and restart? The page reloads when it is back.', 'Update now')) { b.remove(); runUpdate(); } } }, 'Update now'),
    h('a', { class: 'pillbtn noic', href: '#/settings/server', onclick: () => b.remove() }, 'Details'),
    h('button', { class: 'iconbtn', title: 'Not now (hidden until the next version)', onclick: () => { try { localStorage.setItem('iocal.updateDismissed', u.remote); } catch { /* */ } b.remove(); } }, icon('close', 's')));
  document.body.append(b);
}

// ------------------------------------------------------------------ sign-in
function showSignIn() {
  // as in the other io apps: a tile per account; one click for a passwordless viewer, a password for the others
  if (document.querySelector('.signin')) return;
  const first = !S.status.usersExist;
  const name = h('input', { class: 't', placeholder: 'User name', autocomplete: 'username', autocapitalize: 'none' });
  const pw = h('input', { class: 't', type: 'password', placeholder: first ? 'Password (8 or more)' : 'Password', autocomplete: first ? 'new-password' : 'current-password' });
  const err = h('div', { class: 'err' });
  const form = h('div', { class: 'signin-form' }, name, pw);
  const tiles = h('div', { class: 'accounts' });
  const btn = h('button', { class: 'pillbtn primary noic', type: 'submit' }, first ? 'Create the admin account' : 'Sign in');
  const login = async (n, p) => {
    err.textContent = '';
    try { await api(first ? '/api/auth/setup' : '/api/auth/login', { method: 'POST', json: { name: n, password: p } }); location.reload(); } catch (x) { err.textContent = x.message; }
  };
  const submit = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  document.body.append(h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: submit },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Calendar'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin, who adds the rest of the family in Settings. (Already use another io app? Sign in there first, or use the same name and password here once the apps share their accounts.)') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('/api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true; btn.hidden = true;
    tiles.append(...d.accounts.map((a) => {
      const t = h('button', { type: 'button', class: 'account', title: a.passwordless ? `Sign in as ${a.name}` : `${a.name} (password)`, onclick: () => {
        pick(t);
        if (a.passwordless) { login(a.name, ''); return; }
        name.value = a.name; name.hidden = true; form.hidden = false; btn.hidden = false; pw.value = ''; pw.focus();
      } }, h('span', { class: 'av big', style: { '--h': hue(a.displayName || a.name) } }, initials(a.displayName || a.name)), h('span', { class: 'nm' }, a.displayName || a.name), a.passwordless ? null : h('span', { class: 'muted small' }, 'password'));
      return t;
    }), h('button', { type: 'button', class: 'account', title: 'Type a user name', onclick: (e) => {
      pick(e.currentTarget); name.value = ''; name.hidden = false; form.hidden = false; btn.hidden = false; name.focus();
    } }, h('span', { class: 'av big other' }, '…'), h('span', { class: 'nm' }, 'Other')));
  }).catch(() => name.focus());
}

// ------------------------------------------------------------------ start
async function start() {
  applyTheme();
  document.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic)));
  S.status = await api('/api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('/api/auth/me')).settings || {}; } catch { S.settings = {}; }
  S.hidden = new Set(String(S.settings.hiddenCalendars || '').split(',').filter(Boolean).map(Number));
  S.who = new Set(String(S.settings.memberFilter || '').split(',').filter(Boolean).map(Number));
  drawUser();
  await loadCals();
  $('#newbtn').onclick = () => { const v = route(); newAt(['month', 'week', 'day', 'agenda'].includes(v.view) && !sameDay(S.date, new Date()) ? S.date : new Date()); };
  if (!writable().some((c) => !isAuto(c))) $('#newbtn').hidden = true;
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a:not(.cal)') && !document.body.classList.contains('side-docked')) closeNav(); });
  let rt;
  addEventListener('resize', () => { applySidebar(); clearTimeout(rt); rt = setTimeout(() => { if (S.view === 'month' && route().view === 'month') drawView(); }, 250); });
  let t;
  $('#q').addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      const q = e.target.value.trim();
      if (q) location.hash = `#/search/${encodeURIComponent(q)}`;
      else if (route().view === 'search') go(S.view, S.date);
    }, 250);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin')) return;
    const cal = ['month', 'week', 'day', 'agenda'].includes(route().view);
    const k = e.key;
    if (k === '/') { e.preventDefault(); $('#q').focus(); }
    else if (k === 'n' || k === 'c') { e.preventDefault(); $('#newbtn').click(); }
    else if (k === 'e' && S.open && document.querySelector('.evd') && calOf(S.open.calendarId).writable) { closeDialogs(); location.hash = `#/edit/${S.open.id}${S.open.recurrenceId ? `?rid=${encodeURIComponent(S.open.recurrenceId)}` : ''}`; }
    else if (document.querySelector('.dialog-back')) return;
    else if (k === 't') go(cal ? S.view : (S.settings.defaultView || 'month'), new Date());
    else if (k === 'm') go('month', S.date);
    else if (k === 'w') go('week', S.date);
    else if (k === 'd') go('day', S.date);
    else if (k === 'a') go('agenda', S.date);
    else if (cal && (k === 'ArrowLeft' || k === 'j' || k === 'p')) stepView(-1);
    else if (cal && (k === 'ArrowRight' || k === 'k')) stepView(1);
  });
  addEventListener('hashchange', onRoute);
  await onRoute();
  updateBanner();
  setInterval(moveNowLine, 60000);
  // come back to the tab: show what changed elsewhere (a phone, another person)
  let away = Date.now();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { away = Date.now(); return; }
    if (Date.now() - away > 60000 && ['month', 'week', 'day', 'agenda'].includes(route().view) && !document.querySelector('.dialog-back')) { loadCals().then(drawView).catch(() => {}); }
  });
  setInterval(async () => { try { S.status = await api('/api/status'); updateBanner(); } catch { /* restarting */ } }, 15 * 60 * 1000);
}
start().catch(fail);
