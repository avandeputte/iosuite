/* ioThings web app: one module, no build step. Everything you own as cards or a table (all of them, what needs
   upkeep, warranties ending, archived, by place, by label, found by words); one thing with its photos, facts,
   purchase and warranty, files (manuals, receipts, photos), upkeep (optionally a repeating ioTask task) and
   maintenance log; the form to add or change one; the places as a tree; Homebox CSV import and export; and settings
   (account, display, and for admins things and server, and for suite admins security and global settings), laid out
   as in the other ioThing apps. */
import { client, h, safeUrl } from '../api/auth/ui.js';  // the suite's shared helpers (iosuite-shared static/account-panel.js)
const api = client(document.baseURI, { signIn: () => showSignIn() });

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
/** replaceChildren that leaves out null and false (as h() does) and flattens lists. */
const fill = (el, ...kids) => el.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
/** append with the same manners. */
const put = (el, ...kids) => el.append(...kids.flat(9).filter((k) => k != null && k !== false));
const ICONS = {
  list: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  print: 'M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z',
  book: 'M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z',
  box: 'M20 2H4c-1 0-2 .9-2 2v3.01c0 .72.43 1.34 1 1.69V20c0 1.1 1.1 2 2 2h14c.9 0 2-.9 2-2V8.7c.57-.35 1-.97 1-1.69V4c0-1.1-1-2-2-2zm-5 12H9v-2h6v2zm5-7H4V4l16-.02V7z',
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z',
  tag: 'M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z',
  timer: 'M15 1H9v2h6V1zm-4 13h2V8h-2v6zm8.03-6.61 1.42-1.42c-.43-.51-.9-.99-1.41-1.41l-1.42 1.42A8.962 8.962 0 0 0 12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9a8.994 8.994 0 0 0 7.03-14.61zM12 20c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z',
  dish: 'M8.1 13.34l2.83-2.83L3.91 3.5a4.008 4.008 0 0 0 0 5.66l4.19 4.18zm6.78-1.81c1.53.71 3.68.21 5.27-1.38 1.91-1.91 2.28-4.65.81-6.12-1.46-1.46-4.2-1.1-6.12.81-1.59 1.59-2.09 3.74-1.38 5.27L3.7 19.87l1.41 1.41L12 14.41l6.88 6.88 1.41-1.41L13.41 13l1.47-1.47z',
  photo: 'M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z',
  favorite: 'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z',
  favoriteBorder: 'M16.5 3c-1.74 0-3.41.81-4.5 2.09C10.91 3.81 9.24 3 7.5 3 4.42 3 2 5.42 2 8.5c0 3.78 3.4 6.86 8.55 11.54L12 21.35l1.45-1.32C18.6 15.36 22 12.28 22 8.5 22 5.42 19.58 3 16.5 3zm-4.4 15.55l-.1.1-.1-.1C7.14 14.24 4 11.39 4 8.5 4 6.5 5.5 5 7.5 5c1.54 0 3.04.99 3.57 2.36h1.87C13.46 5.99 14.96 5 16.5 5c2 0 3.5 1.5 3.5 3.5 0 2.89-3.14 5.74-7.9 10.05z',
  star: 'M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z',
  starBorder: 'M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z',
  cart: 'M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49A1.003 1.003 0 0 0 20 4H5.21l-.94-2H1zm16 16c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2z',
  camera: 'M3 4V1h2v3h3v2H5v3H3V6H0V4h3zm3 6V7h3V4h7l1.83 2H21c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V10h3zm7 9c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5zm-3.2-5c0 1.77 1.43 3.2 3.2 3.2s3.2-1.43 3.2-3.2-1.43-3.2-3.2-3.2-3.2 1.43-3.2 3.2z',
  books: 'M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 10l-2.5-1.5L15 12V4h5v8z',
  text: 'M3 18h12v-2H3v2zM3 6v2h18V6H3zm0 7h18v-2H3v2z',
  file: 'M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
  prev: 'M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z',
  next: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  minus: 'M19 13H5v-2h14v2z',
  globe: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z',
  build: 'M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z',
  shield: 'M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z',
  archive: 'M20.54 5.23l-1.39-1.68C18.88 3.21 18.47 3 18 3H6c-.47 0-.88.21-1.16.55L3.46 5.23C3.17 5.57 3 6.02 3 6.5V19c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6.5c0-.48-.17-.93-.46-1.27zM12 17.5 6.5 12H10v-2h4v2h3.5L12 17.5zM5.12 5l.81-1h12l.94 1H5.12z',
  place: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 0 1 0-5 2.5 2.5 0 0 1 0 5z',
  subdir: 'M19 15l-6 6-1.42-1.42L15.17 16H4V4h2v10h9.17l-3.59-3.58L13 9l6 6z',
  grid: 'M4 11h5V5H4v6zm0 7h5v-6H4v6zm6 0h5v-6h-5v6zm6 0h5v-6h-5v6zm-6-7h5V5h-5v6zm6-6v6h5V5h-5z',
  money: 'M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z',
  stack: 'M11.99 18.54l-7.37-5.73L3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z',
  receipt: 'M18 17H6v-2h12v2zm0-4H6v-2h12v2zm0-4H6V7h12v2zM3 22l1.5-1.5L6 22l1.5-1.5L9 22l1.5-1.5L12 22l1.5-1.5L15 22l1.5-1.5L18 22l1.5-1.5L21 22V2l-1.5 1.5L18 2l-1.5 1.5L15 2l-1.5 1.5L12 2l-1.5 1.5L9 2 7.5 3.5 6 2 4.5 3.5 3 2v20z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  pdf: 'M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8.5 7.5c0 .83-.67 1.5-1.5 1.5H9v2H7.5V7H10c.83 0 1.5.67 1.5 1.5v1zm5 2c0 .83-.67 1.5-1.5 1.5h-2.5V7H15c.83 0 1.5.67 1.5 1.5v3zm4-3H19v1h1.5V11H19v2h-1.5V7h3v1.5zM9 9.5h1v-1H9v1zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm10 5.5h1v-3h-1v3z',
  history: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z',
  info: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z',
};
const icon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'ic ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

let toastTimer;
/** A note at the foot of the page. */
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
}
const fail = (e) => toast(e.message || String(e));

function dialog(title, body, buttons, cls = '') {
  return new Promise((resolve) => {
    const back = h('div', { class: 'dialog-back' });
    const close = (v) => { back.remove(); resolve(v); };
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `pillbtn noic ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''}`, onclick: () => close(typeof b.value === 'function' ? b.value() : b.value) }, b.label));
    back.append(h('div', { class: `dialog ${cls}`, role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector('input,select,textarea'); if (f) f.focus();
  });
}
const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, h('p', null, text), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);
function closeDialogs() { document.querySelectorAll('.dialog-back').forEach((d) => d.remove()); }

/** A menu that drops from a button: items are [icon, label, what it does (a function, or an address)]; a second click
    on the button, a click elsewhere, Escape or scrolling puts it away. */
let openMenu = null;
function closeMenu() {
  if (!openMenu) return;
  openMenu.el.remove(); document.removeEventListener('click', openMenu.outside); openMenu = null;
}
function popMenu(btn, items) {
  const mine = openMenu && openMenu.btn === btn;
  closeMenu();
  if (mine) return;
  const el = h('div', { class: 'menu pop', role: 'menu' }, items.filter(Boolean).map(([ic, label, act]) => (typeof act === 'string'
    ? h('a', { class: 'mi', role: 'menuitem', href: act, onclick: closeMenu }, icon(ic, 's'), label)
    : h('button', { class: 'mi', role: 'menuitem', onclick: () => { closeMenu(); act(); } }, icon(ic, 's'), label))));
  document.body.append(el);
  const r = btn.getBoundingClientRect();
  el.style.left = `${Math.round(Math.max(8, Math.min(r.right - el.offsetWidth, innerWidth - el.offsetWidth - 8)))}px`;
  el.style.top = `${Math.round(r.bottom + 4 + el.offsetHeight > innerHeight - 8 ? Math.max(8, r.top - el.offsetHeight - 4) : r.bottom + 4)}px`;
  const outside = (e) => { if (!el.contains(e.target) && !btn.contains(e.target)) closeMenu(); };
  openMenu = { el, btn, outside };
  setTimeout(() => document.addEventListener('click', outside), 0);
  $('#main').addEventListener('scroll', closeMenu, { once: true });
}

const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
const store = { get: (k) => { try { return localStorage.getItem(`iothings.${k}`); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(`iothings.${k}`, v); } catch { /* private mode */ } } };


// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, counts: {}, locations: [], labels: [], currency: 'EUR', may: {}, tasks: false };
// the suite's roles, each able to do what the one before can: a viewer only looks, a member adds things and keeps
// their upkeep, an editor changes everything and keeps the places and labels in order
const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
const canAdd = () => roleAtLeast('member');
const canEditAll = () => roleAtLeast('editor');
/** What goes around the things: how many, the places and the labels (the summary). */
function around(d) { S.counts = d.counts; S.locations = d.locations; S.labels = d.labels; S.currency = d.currency || 'EUR'; S.may = d.may || {}; S.tasks = !!d.tasks; }
async function refreshAround() { try { around(await api('api/summary')); } catch { /* the page says so */ } drawNav(); }
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}
/** An amount in the app's currency: € 1,299.50. */
const money = (v) => (v == null || v === '' ? '' : new Intl.NumberFormat(undefined, { style: 'currency', currency: S.currency }).format(v));
/** A day as people read it: 15 Nov 2026. */
const fmtDay = (iso) => (iso ? new Date(`${iso.slice(0, 10)}T00:00`).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' }) : '');
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
/** "in 3 days", "today", "5 days late" */
function dueWords(days) {
  if (days === 0) return 'today';
  if (days === 1) return 'tomorrow';
  if (days === -1) return 'yesterday';
  if (days < 0) return `${-days} days late`;
  if (days < 45) return `in ${days} days`;
  if (days < 365) return `in ${Math.round(days / 30)} months`;
  const y = days / 365; return `in ${y < 1.5 ? 'a year' : `${Math.round(y)} years`}`;
}
const sizeWords = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(n < 10485760 ? 1 : 0)} MB`);
const placeOf = (id) => S.locations.find((l) => l.id === id);

// ------------------------------------------------------------------ chrome
function drawUser() {
  const m = $('#usermenu'); m.replaceChildren();
  if (!S.user) return;
  const btn = h('button', { class: 'avatarbtn', title: S.user.displayName, style: { background: `hsl(${hue(S.user.name)} 45% 45%)` } }, initials(S.user.displayName));
  let menu = null;
  const closeMenu = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && e.target !== btn) closeMenu(); };
  btn.onclick = () => {
    if (menu) return closeMenu();
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { const r = await api('api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to all the things. */
async function loadSuite() {
  try {
    const r = await api('api/auth/suite');
    S.suite = (r.items || []).filter((a) => a.url); suiteSelf = r.app;  // in the suite's one order, this app too
    if (!S.suite.some((a) => a.app !== r.app)) S.suite = [];  // only this app: no menu
  } catch { S.suite = []; }
  const b = $('#suitebtn');
  if (b) { b.hidden = !S.suite.length; b.onclick = () => toggleSuite(b); }
  if (!S.suite.length) closeSuite();
  drawNav();
}
let suiteSelf = null;  // this app's key, marked in the menu
let suitePop = null;
function closeSuite() {
  if (!suitePop) return;
  suitePop.remove(); suitePop = null;
  document.removeEventListener('click', suiteOutside, true);
  document.removeEventListener('keydown', suiteKey);
  removeEventListener('resize', closeSuite);
}
function suiteOutside(e) { if (suitePop && !suitePop.contains(e.target) && !e.target.closest('.suitebtn')) closeSuite(); }
function suiteKey(e) { if (e.key === 'Escape') closeSuite(); }
function appTile(a) {
  const mark = (a.name || a.app).replace(/^io(?=[A-Z])/, '').slice(0, 1).toUpperCase();
  const fallback = () => h('span', { class: 'appic fb', style: { background: a.color || 'var(--brand)' } }, mark);
  const ic = a.icon ? h('img', { class: 'appic', src: a.icon, alt: '', onerror: (e) => e.currentTarget.replaceWith(fallback()) }) : fallback();
  const el = h('a', { class: 'apptile', href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite },
    ic, h('span', { class: 'appnm' }, a.name || a.app));
  el.classList.toggle('tool', !!a.adminTool);  // admin tools: a smaller icon
  if (a.app === suiteSelf) { el.classList.add('cur'); el.setAttribute('aria-current', 'page'); }
  return el;
}
function toggleSuite(btn) {
  if (suitePop) { closeSuite(); return; }
  if (!S.suite.length) return;
  // the apps, then the admin tools in a section of their own: the server sends those to their admins only
  const apps = S.suite.filter((a) => !a.adminTool), tools = S.suite.filter((a) => a.adminTool);
  suitePop = h('div', { class: 'suitepop', role: 'menu', 'aria-label': 'ioThing apps', style: { '--cols': String(Math.min(3, Math.max(apps.length, tools.length))) } },
    ...apps.map(appTile), ...(tools.length ? [h('div', { class: 'suitesec' }, 'Admin tools'), ...tools.map(appTile)] : []));
  document.body.append(suitePop);
  const r = btn.getBoundingClientRect();
  suitePop.style.top = `${Math.round(r.bottom + 6)}px`;
  suitePop.style.left = `${Math.round(Math.max(8, Math.min(r.left - 6, innerWidth - suitePop.offsetWidth - 8)))}px`;
  setTimeout(() => { document.addEventListener('click', suiteOutside, true); document.addEventListener('keydown', suiteKey); addEventListener('resize', closeSuite); }, 0);
}
/** The theme: the account's (Settings › Display), remembered in this browser too so the sign-in page has it. */
function applyTheme(choice) {
  if (choice) store.set('theme', choice);
  const t = choice || store.get('theme') || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}


/* The sidebar, as in the other io apps: the name on top, the things (all of them, what needs upkeep, warranties ending,
   archived), the places as a tree, the labels, adding and import, Settings at the foot. It docks beside the page on a
   wide screen unless its button put it away (remembered); otherwise it slides over the page. Phones get a bottom bar. */
const DOCK_MIN = 1100;
const VIEWS = { all: ['All things', 'box', '--c-blue'], upkeep: ['Upkeep', 'build', '--c-orange'], warranty: ['Warranties', 'shield', '--c-green'],
  archived: ['Archived', 'archive', '--c-slate'] };
const viewCount = (k) => ({ all: S.counts.items, upkeep: S.counts.upkeepDue, warranty: S.counts.warrantySoon, archived: S.counts.archived }[k] || null);
function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar, depth) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: { ...(hueVar ? { '--hue': `var(${hueVar})` } : {}), ...(depth ? { paddingLeft: `${12 + depth * 14}px` } : {}) } },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Things')];
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'All things' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'All things' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    Object.entries(VIEWS).map(([k, [label, ic, hv]]) => link(k, `#/${k}`, ic, label, viewCount(k), r.view === k, hv)),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    S.locations.length || canAdd() ? [h('div', { class: 'navgap' }),
      sec('Places', canAdd() ? h('button', { class: 'iconbtn', title: 'New place', 'aria-label': 'New place', onclick: () => placeDialog(null) }, icon('add', 's')) : null),
      S.locations.map((l) => link('place', `#/place/${l.id}`, l.depth ? 'subdir' : 'place', l.name, l.count || null, r.view === 'place' && r.id === l.id, '--c-indigo', l.depth))] : null,
    S.labels.length ? [h('div', { class: 'navgap' }), sec('Labels'),
      S.labels.slice(0, 30).map((t) => link('label', `#/label/${t.id}`, 'tag', t.name, t.count || null, r.view === 'label' && r.id === t.id, t.color ? null : '--c-slate'))] : null,
    canAdd() ? [h('div', { class: 'navgap' }), sec('Add'),
      link('new', '#/new', 'add', 'New thing', null, r.view === 'new', '--c-blue'),
      link('import', '#/import', 'download', 'Import and export', null, r.view === 'import', '--c-teal')] : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  // a label's own colour on its icon
  nav.querySelectorAll('a[data-v="label"]').forEach((a, i) => { const t = S.labels[i]; if (t && t.color) a.style.setProperty('--hue', t.color); });
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['place', 'label', 'import', 'new', 'settings', 'search', 'places'].includes(r.view));
}
function applySidebar() {
  const body = document.body, btn = $('#sidebtn');
  const docked = innerWidth >= DOCK_MIN && store.get('sidebar') !== '0';
  body.classList.toggle('side-docked', docked);
  if (docked) closeNav();
  if (!btn) return;
  const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : innerWidth >= DOCK_MIN ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
  btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
}
function sidebarButton() {
  if (document.body.classList.contains('side-docked')) store.set('sidebar', '0');
  else if (innerWidth >= DOCK_MIN) store.set('sidebar', '1');
  else { closeNav(); return; }
  applySidebar();
}
function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }

/** Phones: what the bottom bar has no room for (the places, the labels, adding, settings). */
function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    canAdd() ? [tile('#/new', 'add', 'New thing', 'var(--c-blue)', r.view === 'new'), tile('#/import', 'download', 'Import', 'var(--c-teal)', r.view === 'import')] : null,
    tile('#/places', 'place', 'Places', 'var(--c-indigo)', r.view === 'places'),
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'),
    S.locations.filter((l) => !l.depth).map((l) => tile(`#/place/${l.id}`, 'place', l.name, 'var(--c-indigo)', r.view === 'place' && r.id === l.id)),
    S.labels.slice(0, 18).map((t) => tile(`#/label/${t.id}`, 'tag', t.name, t.color || 'var(--c-slate)', r.view === 'label' && r.id === t.id)));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) closeDialogs(); });
  return p;
}

// ------------------------------------------------------------------ routing
function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const p = raw.split('?')[0].split('/').map((x) => { try { return decodeURIComponent(x); } catch { return x; } });
  const [a, b, c] = p;
  if (!a) return { view: VIEWS[S.settings.startView] ? S.settings.startView : 'all' };
  if (VIEWS[a]) return { view: a };
  if (a === 'place' && b) return { view: 'place', id: +b };
  if (a === 'label' && b) return { view: 'label', id: +b };
  if (a === 'search') return { view: 'search', q: b || '' };
  if (a === 'item' && b) return { view: c === 'edit' ? 'edit' : 'item', id: +b };
  if (a === 'new') return { view: 'new' };
  if (a === 'places') return { view: 'places' };
  if (a === 'import') return { view: 'import' };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  return { view: 'all' };
}
const GRID_VIEWS = ['all', 'warranty', 'archived', 'place', 'label', 'search'];

async function onRoute() {
  const r = route();
  const main = $('#main');
  closeMenu();
  try {
    const page = h('div', { class: 'page' });
    if (GRID_VIEWS.includes(r.view)) await drawItems(page, r);
    else await ({ item: showItem, edit: showForm, new: showForm, upkeep: showUpkeep, places: showPlaces, import: showImport, settings: showSettings })[r.view](page, r);
    main.replaceChildren(page);
    main.scrollTop = 0;
  } catch (e) { main.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'empty' }, icon('box'), h('p', null, e.message || String(e)), h('p', null, h('a', { class: 'lnk', href: '#/' }, 'All things'))))); }
  drawNav();
}

// ------------------------------------------------------------------ the things, as cards or as a table
const SORTS = { name: 'A to Z', new: 'Newest first', updated: 'Last changed', bought: 'Last bought', price: 'Most expensive', warranty: 'Warranty ending' };
async function fetchItems(r) {
  const q = new URLSearchParams();
  if (r.view === 'archived') q.set('archived', 'only');
  if (r.view === 'warranty') q.set('warranty', 'soon');
  if (r.view === 'place') q.set('location', r.id);
  if (r.view === 'label') q.set('label', r.id);
  if (r.view === 'search') { q.set('q', r.q); q.set('archived', 'also'); }
  if (SORTS[S.settings.sort] && S.settings.sort !== 'name' && r.view !== 'warranty') q.set('sort', S.settings.sort);
  return (await api(`api/items?${q}`)).items;
}
function warrantyBadge(w, short = false) {
  if (!w) return null;
  const [cls, text] = w.state === 'lifetime' ? ['ok', 'Lifetime warranty'] : w.state === 'expired' ? ['off', short ? 'Warranty over' : `Warranty ended ${fmtDay(new Date(Date.now() + w.daysLeft * 864e5).toISOString())}`]
    : w.state === 'soon' ? ['warn', `Warranty ends ${dueWords(w.daysLeft)}`] : ['ok', short ? 'Under warranty' : `Under warranty, ${dueWords(w.daysLeft)} left`.replace('in ', '')];
  return h('span', { class: `badge ${cls}` }, icon('shield', 'xs'), text);
}
function card(x) {
  return h('a', { class: 'rcard', href: `#/item/${x.id}` },
    x.photo ? h('img', { class: 'rpic', src: `${x.photo}?size=small`, alt: '', loading: 'lazy' })
      : h('span', { class: 'rpic none', style: { '--h': hue(x.name) } }, icon(x.archived ? 'archive' : 'box')),
    x.quantity > 1 ? h('span', { class: 'qty', title: `${x.quantity} of them` }, `×${x.quantity}`) : null,
    h('span', { class: 'rbody' },
      h('span', { class: 'rtitle' }, x.name),
      h('span', { class: 'rmeta' }, x.location ? [icon('place', 'xs'), x.location.path] : [x.manufacturer, x.modelNumber].filter(Boolean).join(' ') || ' '),
      x.warranty && x.warranty.state === 'soon' ? warrantyBadge(x.warranty, true) : null,
      x.labels.length ? h('span', { class: 'labs' }, x.labels.slice(0, 3).map(labelChip)) : null));
}
const labelChip = (t) => h('span', { class: 'lchip', style: t.color ? { '--lc': t.color } : null }, t.name);
function table(items) {
  return h('div', { class: 'tablewrap' }, h('table', { class: 'things' },
    h('thead', null, h('tr', null, ['Name', 'Place', 'Maker and model', 'Bought', 'Price', 'Warranty'].map((t) => h('th', null, t)))),
    h('tbody', null, items.map((x) => h('tr', { onclick: () => { location.hash = `#/item/${x.id}`; } },
      h('td', null, h('a', { href: `#/item/${x.id}`, class: 'lnk' }, x.name), x.quantity > 1 ? h('span', { class: 'muted' }, ` ×${x.quantity}`) : null),
      h('td', null, x.location ? x.location.path : ''), h('td', null, [x.manufacturer, x.modelNumber].filter(Boolean).join(' ')),
      h('td', null, fmtDay(x.purchaseDate)), h('td', { class: 'num' }, money(x.purchasePrice)),
      h('td', null, x.warranty ? warrantyBadge(x.warranty, true) : ''))))));
}
async function drawItems(page, r) {
  const items = await fetchItems(r);
  const place = r.view === 'place' ? placeOf(r.id) : null;
  const lab = r.view === 'label' ? S.labels.find((t) => t.id === r.id) : null;
  if (r.view === 'place' && !place) throw new Error('No such place');
  if (r.view === 'label' && !lab) throw new Error('No such label');
  const title = place ? place.name : lab ? lab.name : r.view === 'search' ? `“${r.q}”` : VIEWS[r.view][0];
  if (place || lab) document.title = `${title} · ioThings`;
  page.classList.add('wide');
  const asTable = S.settings.layout === 'table';
  const sort = r.view === 'warranty' ? null : h('select', { class: 't sortsel', title: 'In what order', 'aria-label': 'In what order', onchange: async (e) => { await saveSettings({ sort: e.target.value }); onRoute(); } },
    Object.entries(SORTS).map(([k, l]) => h('option', { value: k, selected: k === (S.settings.sort || 'name') ? true : null }, l)));
  const layout = h('button', { class: 'iconbtn', title: asTable ? 'As cards' : 'As a table', onclick: async () => { await saveSettings({ layout: asTable ? 'cards' : 'table' }); onRoute(); } }, icon(asTable ? 'grid' : 'list'));
  put(page, h('div', { class: 'pagehead' }, h('h1', null, title), h('span', { class: 'count' }, items.length || ''), h('span', { class: 'grow' }),
    items.length > 1 ? sort : null, items.length ? layout : null,
    place && canEditAll() ? h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
      ['edit', 'Change this place', () => placeDialog(place)],
      ['add', 'A place inside it', () => placeDialog(null, place.id)],
      ['delete', 'Delete this place', () => removePlace(place)]]) }, icon('more')) : null,
    lab && canEditAll() ? h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
      ['edit', 'Change this label', () => labelDialog(lab)], ['delete', 'Delete this label', () => removeLabel(lab)]]) }, icon('more')) : null));
  if (place) put(page, h('p', { class: 'muted bookabout' }, icon('place', 'xs'), place.path, place.description ? ` · ${place.description}` : ''));
  if (r.view === 'warranty') put(page, h('p', { class: 'muted bookabout' }, 'Warranties that end in the next 30 days, or ended last week.'));
  if (r.view === 'all' && items.length) {
    const c = S.counts;
    put(page, h('div', { class: 'facts' },
      h('span', { class: 'fact' }, icon('box', 's'), h('span', null, h('small', null, 'Things'), String(c.items))),
      c.worth ? h('span', { class: 'fact' }, icon('money', 's'), h('span', null, h('small', null, 'What they cost'), money(c.worth))) : null,
      h('a', { class: 'fact', href: '#/upkeep' }, icon('build', 's'), h('span', null, h('small', null, 'Upkeep this week'), String(c.upkeepDue || 'None'))),
      h('a', { class: 'fact', href: '#/warranty' }, icon('shield', 's'), h('span', null, h('small', null, 'Warranties ending'), String(c.warrantySoon || 'None')))));
  }
  if (!items.length) {
    const first = r.view === 'all';
    put(page, h('div', { class: 'empty' }, icon(r.view === 'archived' ? 'archive' : r.view === 'warranty' ? 'shield' : 'box'),
      h('p', null, r.view === 'search' ? 'Nothing has those words.' : r.view === 'archived' ? 'Nothing archived: a thing that is sold or thrown out goes here, with its story.'
        : r.view === 'warranty' ? 'No warranty ends in the next 30 days.' : r.view === 'place' ? 'Nothing in this place yet.' : r.view === 'label' ? 'Nothing has this label.'
          : 'Nothing yet. Add what you own, or bring them over from Homebox.'),
      first && canAdd() ? h('p', { class: 'emptybtns' }, h('a', { class: 'pillbtn primary', href: '#/new' }, icon('add', 's'), 'New thing'),
        h('a', { class: 'pillbtn', href: '#/import' }, icon('download', 's'), 'Import from Homebox')) : null));
    return;
  }
  put(page, asTable ? table(items) : h('div', { class: 'rgrid' }, items.map(card)));
}

// ------------------------------------------------------------------ places and labels
const placeOptions = (sel, skip = null) => [h('option', { value: '' }, '(none)'),
  ...S.locations.filter((l) => skip == null || !(l.path + ' /').startsWith(placeOf(skip).path + ' /'))
    .map((l) => h('option', { value: l.id, selected: l.id === sel ? true : null }, `${'  '.repeat(l.depth)}${l.path}`))];
async function placeDialog(place, parentId = null) {
  if (!canAdd()) return null;
  const name = h('input', { class: 't', value: place ? place.name : '', maxlength: 191, placeholder: 'Kitchen, Garage, Attic, Drawer by the sink' });
  const about = h('input', { class: 't', value: (place && place.description) || '', placeholder: 'What it is (if you like)' });
  const parent = h('select', { class: 't' }, placeOptions(place ? place.parentId : parentId, place ? place.id : null));
  const ok = await dialog(place ? 'Change the place' : 'New place', h('div', { class: 'pform' }, fld('Name', name), fld('Inside', parent), fld('About', about)),
    [{ label: 'Cancel', value: false }, { label: place ? 'Save' : 'Add', value: true, primary: true }]);
  if (!ok) return null;
  try {
    const got = await api(place ? `api/locations/${place.id}` : 'api/locations', { method: place ? 'PATCH' : 'POST', json: { name: name.value, description: about.value, parentId: parent.value ? +parent.value : null } });
    await refreshAround(); if (route().view !== 'edit' && route().view !== 'new') onRoute();
    return got;
  } catch (e) { fail(e); return null; }
}
async function removePlace(place) {
  if (!await confirmDialog('Delete this place?', `“${place.path}” goes; what is in it moves up to ${place.parentId ? `“${placeOf(place.parentId).path}”` : 'no place'}.`, 'Delete', true)) return;
  try { await api(`api/locations/${place.id}`, { method: 'DELETE' }); toast('Deleted'); await refreshAround(); location.hash = place.parentId ? `#/place/${place.parentId}` : '#/'; } catch (e) { fail(e); }
}
const COLORS = ['', '#d93025', '#e8710a', '#f9ab00', '#1e8e3e', '#12b5cb', '#1a73e8', '#9334e6', '#e52592', '#5f6368'];
async function labelDialog(lab) {
  const name = h('input', { class: 't', value: lab ? lab.name : '', maxlength: 100 });
  let color = (lab && lab.color) || '';
  const sw = h('div', { class: 'swatches' });
  const draw = () => fill(sw, COLORS.map((c) => h('button', { type: 'button', class: `sw${c === color ? ' on' : ''}`, title: c || 'No colour', style: { background: c || 'var(--bg2)' }, onclick: () => { color = c; draw(); } })));
  draw();
  if (!await dialog(lab ? 'Change the label' : 'New label', h('div', { class: 'pform' }, fld('Name', name), fld('Colour', sw)),
    [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  try { await api(lab ? `api/labels/${lab.id}` : 'api/labels', { method: lab ? 'PATCH' : 'POST', json: { name: name.value, color } }); await refreshAround(); onRoute(); } catch (e) { fail(e); }
}
async function removeLabel(lab) {
  if (!await confirmDialog('Delete this label?', `“${lab.name}” comes off every thing; the things stay.`, 'Delete', true)) return;
  try { await api(`api/labels/${lab.id}`, { method: 'DELETE' }); toast('Deleted'); await refreshAround(); location.hash = '#/'; } catch (e) { fail(e); }
}
/** Places and labels, to tidy up (the page phones reach from More; the sidebar holds the same). */
async function showPlaces(page) {
  await refreshAround();
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Places and labels'), h('span', { class: 'grow' }),
    canAdd() ? h('button', { class: 'pillbtn', onclick: () => placeDialog(null) }, icon('add', 's'), 'Place') : null,
    canAdd() ? h('button', { class: 'pillbtn', onclick: () => labelDialog(null) }, icon('add', 's'), 'Label') : null),
  h('div', { class: 'box' }, h('h2', null, icon('place'), 'Places'),
    S.locations.length ? h('div', { class: 'tree' }, S.locations.map((l) => h('div', { class: 'treerow', style: { paddingLeft: `${l.depth * 20}px` } },
      h('a', { class: 'lnk', href: `#/place/${l.id}` }, l.name), h('span', { class: 'muted small' }, l.count ? ` ${l.count}` : ''), h('span', { class: 'grow' }),
      canEditAll() ? h('button', { class: 'iconbtn', title: 'Change', onclick: () => placeDialog(l) }, icon('edit', 's')) : null,
      canEditAll() ? h('button', { class: 'iconbtn', title: 'Delete', onclick: () => removePlace(l) }, icon('delete', 's')) : null)))
      : h('p', { class: 'muted' }, 'No places yet.')),
  h('div', { class: 'box' }, h('h2', null, icon('tag'), 'Labels'),
    S.labels.length ? h('div', { class: 'chiprow' }, S.labels.map((t) => h('span', { class: 'lchip big', style: t.color ? { '--lc': t.color } : null },
      h('a', { href: `#/label/${t.id}` }, t.name, t.count ? ` · ${t.count}` : ''),
      canEditAll() ? h('button', { class: 'iconbtn', title: 'Change', onclick: () => labelDialog(t) }, icon('edit', 'xs')) : null)))
      : h('p', { class: 'muted' }, 'No labels yet.')));
}

// ------------------------------------------------------------------ one thing
function lightbox(pics, at, x) {
  let i = at;
  const img = h('img', { alt: '' });
  const count = h('span', { class: 'lbcount' });
  const show = () => { img.src = pics[i].url; count.textContent = pics.length > 1 ? `${i + 1} of ${pics.length}` : ''; };
  const go = (d) => { i = (i + d + pics.length) % pics.length; show(); };
  const close = () => { back.remove(); document.removeEventListener('keydown', key, true); };
  const key = (e) => {
    if (e.key === 'Escape') { e.stopPropagation(); close(); } else if (e.key === 'ArrowLeft') go(-1); else if (e.key === 'ArrowRight') go(1);
  };
  const remove = async () => {
    if (!await confirmDialog('Remove this photo?', 'It goes for good.', 'Remove', true)) return;
    try { await api(`api/items/${x.id}/files/${pics[i].id}`, { method: 'DELETE' }); close(); onRoute(); } catch (e) { fail(e); }
  };
  const first = async () => { try { await api(`api/items/${x.id}/files/${pics[i].id}`, { method: 'PATCH', json: { first: true } }); close(); onRoute(); } catch (e) { fail(e); } };
  const back = h('div', { class: 'lightbox', onclick: (e) => { if (e.target === back) close(); } },
    img,
    h('div', { class: 'lbbar' }, count, h('span', { class: 'grow' }),
      canAdd() && pics.length > 1 ? h('button', { class: 'pillbtn', onclick: first }, icon('star', 's'), 'Show on the card') : null,
      x.writable ? h('button', { class: 'pillbtn danger', onclick: remove }, icon('delete', 's'), 'Remove') : null,
      h('button', { class: 'iconbtn', title: 'Close', onclick: close }, icon('close'))),
    pics.length > 1 ? [h('button', { class: 'iconbtn lbnav prev', title: 'The one before', onclick: () => go(-1) }, icon('prev')),
      h('button', { class: 'iconbtn lbnav next', title: 'The next', onclick: () => go(1) }, icon('next'))] : null);
  show();
  document.body.append(back);
  document.addEventListener('keydown', key, true);
}
/** Files from the device, as a promise ([] when none was picked). */
function pickFiles(accept, multiple = true) {
  return new Promise((resolve) => {
    const inp = h('input', { type: 'file', accept, multiple: multiple || null, hidden: true });
    inp.onchange = () => { resolve([...inp.files]); inp.remove(); };
    inp.addEventListener('cancel', () => { resolve([]); inp.remove(); });
    document.body.append(inp);
    inp.click();
  });
}
const sendFile = (id, file, kind) => api(`api/items/${id}/files?${new URLSearchParams({ name: file.name, ...(kind ? { kind } : {}) })}`,
  { method: 'POST', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' } });
async function upload(x, kind, accept, given) {
  const picked = given || await pickFiles(accept);
  if (!picked.length) return;
  toast(picked.length > 1 ? `Sending ${picked.length} files…` : 'Sending…');
  let n = 0;
  for (const f of picked) { try { await sendFile(x.id, f, kind); n += 1; } catch (e) { fail(e); } }
  if (n) { toast(n > 1 ? `${n} files added` : 'Added'); onRoute(); }
}
const FILE_KINDS = { photo: ['Photos', 'photo'], manual: ['Manuals', 'book'], receipt: ['Receipts', 'receipt'], warranty: ['Warranty', 'shield'], other: ['Other files', 'file'] };
const kv = (k, v) => (v == null || v === '' || v === false ? null : h('div', { class: 'kv' }, h('span', { class: 'k' }, k), h('span', { class: 'v' }, v)));

async function showItem(page, r) {
  const x = await api(`api/items/${r.id}`);
  document.title = `${x.name} · ioThings`;
  const pics = x.files.filter((f) => f.kind === 'photo');
  const docs = x.files.filter((f) => f.kind !== 'photo');
  const more = h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
    canAdd() ? ['copy', 'Duplicate', async () => { try { const d = await api(`api/items/${x.id}/duplicate`, { method: 'POST' }); location.hash = `#/item/${d.id}/edit`; } catch (err) { fail(err); } }] : null,
    x.writable ? ['archive', x.archived ? 'Not archived' : 'Archive (sold, given away, thrown out)', async () => { try { await api(`api/items/${x.id}`, { method: 'PATCH', json: { archived: !x.archived } }); await refreshAround(); onRoute(); } catch (err) { fail(err); } }] : null,
    ['print', 'Print', () => print()],
    x.writable ? ['delete', 'Delete', () => removeItem(x)] : null]) }, icon('more'));
  const place = x.location ? h('a', { class: 'fact', href: `#/place/${x.location.id}` }, icon('place', 's'), h('span', null, h('small', null, 'Where'), x.location.path)) : null;
  const facts = h('div', { class: 'facts' }, place,
    x.quantity !== 1 ? h('span', { class: 'fact' }, icon('stack', 's'), h('span', null, h('small', null, 'How many'), String(x.quantity))) : null,
    x.purchasePrice != null ? h('span', { class: 'fact' }, icon('money', 's'), h('span', null, h('small', null, x.purchaseDate ? `Bought ${fmtDay(x.purchaseDate)}` : 'Price'), money(x.purchasePrice))) : null,
    x.warranty ? h('span', { class: `fact w-${x.warranty.state}` }, icon('shield', 's'), h('span', null, h('small', null, 'Warranty'),
      x.warranty.state === 'lifetime' ? 'For life' : x.warranty.state === 'expired' ? `Ended ${fmtDay(x.warrantyExpires)}` : `Until ${fmtDay(x.warrantyExpires)}`)) : null,
    x.insured ? h('span', { class: 'fact' }, icon('lock', 's'), h('span', null, h('small', null, 'Insurance'), 'Insured')) : null);
  const details = [kv('Maker', x.manufacturer), kv('Model', x.modelNumber), kv('Serial number', x.serialNumber ? h('code', null, x.serialNumber) : null),
    kv('Asset id', x.assetId), kv('Link', safeUrl(x.url) ? h('a', { class: 'lnk', href: x.url, target: '_blank', rel: 'noopener noreferrer' }, (() => { try { return new URL(x.url).hostname.replace(/^www\./, ''); } catch { return x.url; } })()) : null),
    ...x.fields.map((f) => kv(f.name, f.value))].filter(Boolean);
  const bought = [kv('Bought', fmtDay(x.purchaseDate)), kv('From', x.purchaseFrom), kv('Price', money(x.purchasePrice)),
    kv('Warranty', x.warranty ? (x.warranty.state === 'lifetime' ? 'For life' : `Until ${fmtDay(x.warrantyExpires)}`) : null), kv('Warranty details', x.warrantyDetails)].filter(Boolean);
  const sold = x.archived || x.soldDate || x.soldTo ? [kv('Sold', fmtDay(x.soldDate)), kv('To', x.soldTo), kv('For', money(x.soldPrice)), kv('Notes', x.soldNotes)].filter(Boolean) : [];
  page.classList.add('item');
  put(page,
    h('div', { class: 'pagehead' }, h('h1', null, x.name), x.archived ? h('span', { class: 'badge off' }, icon('archive', 'xs'), 'Archived') : null,
      h('span', { class: 'grow' }),
      x.writable ? h('a', { class: 'pillbtn', href: `#/item/${x.id}/edit` }, icon('edit', 's'), 'Edit') : null, more),
    x.labels.length ? h('div', { class: 'chiprow labels' }, x.labels.map((t) => h('a', { class: 'lchip big', href: `#/label/${t.id}`, style: t.color ? { '--lc': t.color } : null }, t.name))) : null,
    h('div', { class: 'itemtop' },
      pics.length ? h('div', { class: 'gallery' }, h('img', { class: 'hero', src: pics[0].url, alt: '', onclick: () => lightbox(pics, 0, x) }),
        pics.length > 1 ? h('div', { class: 'thumbs' }, pics.slice(1, 9).map((p, i) => h('img', { src: `${p.url}?size=small`, alt: '', loading: 'lazy', onclick: () => lightbox(pics, i + 1, x) }))) : null)
        : canAdd() ? h('button', { class: 'gallery nophoto', onclick: () => upload(x, 'photo', 'image/*') }, icon('camera'), h('span', null, 'Add a photo')) : null,
      h('div', { class: 'itemfacts' }, facts, x.description ? h('p', { class: 'desc notes' }, x.description) : null,
        details.length ? h('div', { class: 'kvs' }, details) : null)),
    h('div', { class: 'cols2' },
      h('section', null,
        upkeepBox(x),
        logBox(x)),
      h('section', null,
        filesBox(x, docs, pics),
        bought.length ? h('div', { class: 'box' }, h('h2', null, icon('receipt'), 'Purchase and warranty'), bought) : null,
        sold.length ? h('div', { class: 'box' }, h('h2', null, icon('archive'), 'Sold or gone'), sold) : null,
        x.notes ? h('div', { class: 'box' }, h('h2', null, icon('text'), 'Notes'), h('p', { class: 'notes' }, x.notes)) : null)),
    linkedBox(x.id),
    h('p', { class: 'muted small source' }, x.createdBy ? `Added by ${x.createdBy} on ${fmtDay(x.created)}` : `Added on ${fmtDay(x.created)}`));
}
function filesBox(x, docs, pics) {
  const add = canAdd() ? h('button', { class: 'iconbtn', title: 'Add files', onclick: (e) => popMenu(e.currentTarget, [
    ['photo', 'Photos', () => upload(x, 'photo', 'image/*')], ['book', 'A manual', () => upload(x, 'manual', '')],
    ['receipt', 'A receipt', () => upload(x, 'receipt', '')], ['shield', 'A warranty', () => upload(x, 'warranty', '')], ['file', 'Another file', () => upload(x, 'other', '')]]) }, icon('add')) : null;
  const row = (f) => h('div', { class: 'filerow' },
    h('a', { class: 'fileic', href: f.url, target: '_blank', rel: 'noopener' }, f.thumb ? h('img', { src: `${f.url}?size=small`, alt: '' }) : icon(f.mime === 'application/pdf' ? 'pdf' : FILE_KINDS[f.kind][1])),
    h('a', { class: 'filename lnk', href: f.url, target: '_blank', rel: 'noopener' }, f.name),
    h('span', { class: 'muted small' }, sizeWords(f.size)),
    h('a', { class: 'iconbtn', href: `${f.url}?download=true`, title: 'Download', download: f.name }, icon('download', 's')),
    canAdd() ? h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
      ...Object.entries(FILE_KINDS).filter(([k]) => k !== f.kind && k !== 'photo').map(([k, [l, ic]]) => [ic, `Move to ${l.toLowerCase()}`, async () => { try { await api(`api/items/${x.id}/files/${f.id}`, { method: 'PATCH', json: { kind: k } }); onRoute(); } catch (err) { fail(err); } }]),
      ['edit', 'Rename', async () => {
        const n = h('input', { class: 't', value: f.name });
        if (!await dialog('Rename the file', n, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
        try { await api(`api/items/${x.id}/files/${f.id}`, { method: 'PATCH', json: { name: n.value } }); onRoute(); } catch (err) { fail(err); }
      }],
      ['delete', 'Remove', async () => { if (!await confirmDialog('Remove this file?', `“${f.name}” goes for good.`, 'Remove', true)) return; try { await api(`api/items/${x.id}/files/${f.id}`, { method: 'DELETE' }); onRoute(); } catch (err) { fail(err); } }]]) }, icon('more', 's')) : null);
  const groups = Object.entries(FILE_KINDS).filter(([k]) => k !== 'photo').map(([k, [label]]) => [label, docs.filter((f) => f.kind === k)]).filter(([, l]) => l.length);
  // files dropped on the box: images become photos, PDFs manuals, the rest other files (the server decides)
  const drops = canAdd() ? {
    ondragover: (e) => { if ([...e.dataTransfer.types].includes('Files')) { e.preventDefault(); e.currentTarget.classList.add('drop'); } },
    ondragleave: (e) => e.currentTarget.classList.remove('drop'),
    ondrop: (e) => { e.preventDefault(); e.currentTarget.classList.remove('drop'); upload(x, null, '', [...e.dataTransfer.files]); },
  } : {};
  return h('div', { class: 'box files', ...drops }, h('h2', null, icon('file'), 'Manuals, receipts and files', h('span', { class: 'grow' }), add),
    groups.length ? groups.map(([label, list]) => [h('h3', null, label), list.map(row)])
      : h('p', { class: 'muted' }, canAdd() ? 'Keep the manual, the receipt and the warranty card here: the + button, or drop files on this box.' : 'No files.'),
    pics.length ? h('p', { class: 'muted small' }, `${pics.length} ${pics.length === 1 ? 'photo' : 'photos'} above.`) : null);
}
function upkeepBox(x) {
  const add = canAdd() ? h('button', { class: 'iconbtn', title: 'Add upkeep', onclick: () => upkeepDialog(x, null) }, icon('add')) : null;
  return h('div', { class: 'box' }, h('h2', null, icon('build'), 'Upkeep', h('span', { class: 'grow' }), add),
    x.upkeep.length ? x.upkeep.map((k) => upkeepRow(k, x)) : h('p', { class: 'muted' }, canAdd() ? 'What it needs every so often: a service every year, a new filter every three months. It can go in ioTask as a repeating task.' : 'Nothing set.'));
}
function upkeepRow(k, x) {
  const late = k.daysLeft < 0, soon = k.daysLeft <= 14;
  return h('div', { class: `uprow${late ? ' late' : soon ? ' soon' : ''}` },
    h('span', { class: 'updue' }, h('b', null, fmtDay(k.nextDue)), h('small', null, dueWords(k.daysLeft))),
    h('span', { class: 'upwhat' }, x ? null : h('a', { class: 'lnk upitem', href: `#/item/${k.itemId}` }, k.item.name), h('span', null, k.title),
      h('small', { class: 'muted' }, k.every, k.task ? [' · ', k.task.url ? h('a', { class: 'lnk', href: k.task.url, target: '_blank', rel: 'noopener' }, 'in ioTask') : 'in ioTask'] : null)),
    canAdd() ? h('button', { class: 'pillbtn tiny', onclick: () => doneDialog(k) }, icon('check', 's'), 'Done') : null,
    canAdd() ? h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
      ['edit', 'Change', () => upkeepDialog(x || { id: k.itemId, name: k.item.name }, k)],
      ['delete', 'Remove', async () => {
        if (!await confirmDialog('Remove this upkeep?', k.task ? 'Its repeating task in ioTask goes too. The log keeps what was done.' : 'The log keeps what was done.', 'Remove', true)) return;
        try { await api(`api/upkeep/${k.id}`, { method: 'DELETE' }); await refreshAround(); onRoute(); } catch (err) { fail(err); }
      }]]) }, icon('more', 's')) : null);
}
let taskLists = null;
async function upkeepDialog(x, k) {
  const title = h('input', { class: 't', value: k ? k.title : '', placeholder: 'Service, MOT, Replace the filter, Clean the gutters' });
  const n = h('input', { class: 't', type: 'number', min: 1, max: 1000, value: k ? k.everyN : 1 });
  const unit = h('select', { class: 't' }, [['day', 'days'], ['week', 'weeks'], ['month', 'months'], ['year', 'years']].map(([v, l]) => h('option', { value: v, selected: (k ? k.everyUnit : 'year') === v ? true : null }, l)));
  const due = h('input', { class: 't', type: 'date', value: k ? k.nextDue : today() });
  const notes = h('input', { class: 't', value: (k && k.notes) || '', placeholder: 'Who to call, which filter (if you like)' });
  let list = null, note = null;
  if (!k && S.tasks) {
    taskLists = taskLists || await api('api/upkeep/lists').catch(() => ({ available: false, lists: [] }));
    if (taskLists.lists.length) {
      const saved = S.settings.taskList;
      list = h('select', { class: 't' }, h('option', { value: '' }, 'No, keep it in ioThings only'),
        taskLists.lists.map((l) => h('option', { value: l.id, selected: l.id === saved ? true : null }, l.name)));
    } else if (taskLists.available) note = h('p', { class: 'muted small' }, taskLists.error || 'None of your lists in ioTask takes new tasks.');
  }
  const body = h('div', { class: 'pform' }, fld('What needs doing', title),
    h('div', { class: 'every' }, fld('Every', n), fld(' ', unit)), fld(k ? 'Next due' : 'First due', due), fld('Notes', notes),
    list ? fld('Also a repeating task in ioTask', list) : null, note);
  if (!await dialog(k ? 'Change the upkeep' : `Upkeep of ${x.name}`, body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  const json = { title: title.value, everyN: +n.value || 1, everyUnit: unit.value, nextDue: due.value, notes: notes.value };
  if (list && list.value) { json.listId = +list.value; saveSettings({ taskList: +list.value }); }
  try {
    await api(k ? `api/upkeep/${k.id}` : `api/items/${x.id}/upkeep`, { method: k ? 'PATCH' : 'POST', json });
    toast(json.listId ? 'Saved, and added to ioTask' : 'Saved'); await refreshAround(); onRoute();
  } catch (e) { fail(e); }
}
async function doneDialog(k) {
  const on = h('input', { class: 't', type: 'date', value: today() });
  const cost = h('input', { class: 't', inputmode: 'decimal', placeholder: money(0).replace(/[\d.,\s]+/, '') || '0' });
  const by = h('input', { class: 't', placeholder: 'You, or the company' });
  const notes = h('textarea', { class: 't', rows: 2, placeholder: 'What was done, what to remember next time' });
  if (!await dialog(`${k.title}: done`, h('div', { class: 'pform' }, h('p', { class: 'muted' }, `It goes in the log, and comes back ${/^every \d/.test(k.every) ? k.every.replace('every ', 'in ') : k.every.replace('every ', 'in a ')}${k.task ? ' (in ioTask too)' : ''}.`),
    fld('Done on', on), h('div', { class: 'every' }, fld('Cost', cost), fld('By', by)), fld('Notes', notes)),
  [{ label: 'Cancel', value: false }, { label: 'Done', value: true, primary: true }])) return;
  try {
    const got = await api(`api/upkeep/${k.id}/done`, { method: 'POST', json: { date: on.value, cost: cost.value, doneBy: by.value, notes: notes.value } });
    toast(`Logged. Next: ${fmtDay(got.upkeep.nextDue)}`); await refreshAround(); onRoute();
  } catch (e) { fail(e); }
}
function logBox(x) {
  const add = canAdd() ? h('button', { class: 'iconbtn', title: 'Write in the log', onclick: () => logDialog(x, null) }, icon('add')) : null;
  const total = x.maintenance.reduce((s, m) => s + (m.cost || 0), 0);
  return h('div', { class: 'box' }, h('h2', null, icon('history'), 'Maintenance log', h('span', { class: 'grow' }), total ? h('span', { class: 'muted small' }, money(total)) : null, add),
    x.maintenance.length ? h('div', { class: 'log' }, x.maintenance.map((m) => h('div', { class: 'logrow' },
      h('span', { class: 'logday' }, fmtDay(m.date)),
      h('span', { class: 'logwhat' }, h('b', null, m.title), m.doneBy ? h('small', { class: 'muted' }, ` · ${m.doneBy}`) : null, m.notes ? h('span', { class: 'notes muted' }, m.notes) : null),
      m.cost != null ? h('span', { class: 'logcost' }, money(m.cost)) : null,
      canAdd() ? h('button', { class: 'iconbtn', title: 'Change', onclick: () => logDialog(x, m) }, icon('edit', 's')) : null)))
      : h('p', { class: 'muted' }, 'Nothing written yet: services, repairs, parts replaced.'));
}
async function logDialog(x, m) {
  const on = h('input', { class: 't', type: 'date', value: m ? m.date : today() });
  const what = h('input', { class: 't', value: m ? m.title : '', placeholder: 'Replaced the pump, Annual service' });
  const cost = h('input', { class: 't', inputmode: 'decimal', value: m && m.cost != null ? m.cost : '' });
  const by = h('input', { class: 't', value: (m && m.doneBy) || '' });
  const notes = h('textarea', { class: 't', rows: 3 }, (m && m.notes) || '');
  const buttons = [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }];
  if (m) buttons.unshift({ label: 'Delete', value: 'delete', danger: true });
  const got = await dialog(m ? 'Change the line' : `Log for ${x.name}`, h('div', { class: 'pform' }, fld('What was done', what), fld('On', on),
    h('div', { class: 'every' }, fld('Cost', cost), fld('By', by)), fld('Notes', notes)), buttons);
  if (!got) return;
  try {
    if (got === 'delete') await api(`api/maintenance/${m.id}`, { method: 'DELETE' });
    else await api(m ? `api/maintenance/${m.id}` : `api/items/${x.id}/maintenance`, { method: m ? 'PATCH' : 'POST', json: { date: on.value, title: what.value, cost: cost.value, doneBy: by.value, notes: notes.value } });
    onRoute();
  } catch (e) { fail(e); }
}
/** "Linked" under a thing: the events, tasks, notes, contacts, recipes and photos of the other apps linked to it. */
let linkUi = null;
function linkedBox(id) {
  const el = h('div', { class: 'linked' });
  (async () => {
    try { linkUi = linkUi || await import(new URL('api/related/ui.js', document.baseURI).href); } catch (e) { return; }
    linkUi.mount(el, { kind: 'item', id, toast });
  })();
  return el;
}
async function removeItem(x) {
  if (!await confirmDialog('Delete this thing?', `“${x.name}” goes for good, with its files, upkeep and log. Archive it instead to keep its story.`, 'Delete', true)) return;
  try { await api(`api/items/${x.id}`, { method: 'DELETE' }); toast('Deleted'); await refreshAround(); location.hash = '#/'; } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ upkeep, all of it
async function showUpkeep(page) {
  const d = await api('api/upkeep');
  const late = d.items.filter((k) => k.daysLeft < 0), week = d.items.filter((k) => k.daysLeft >= 0 && k.daysLeft <= 7),
    month = d.items.filter((k) => k.daysLeft > 7 && k.daysLeft <= 31), later = d.items.filter((k) => k.daysLeft > 31);
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Upkeep'), h('span', { class: 'count' }, d.items.length || '')));
  if (!d.items.length) {
    put(page, h('div', { class: 'empty' }, icon('build'), h('p', null, 'No upkeep yet. Open a thing (the boiler, the car) and add what it needs every so often.')));
    return;
  }
  const group = (label, list) => (list.length ? h('div', { class: 'box' }, h('h2', null, label), list.map((k) => upkeepRow(k, null))) : null);
  put(page, group('Late', late), group('This week', week), group('This month', month), group('Later', later));
}

// ------------------------------------------------------------------ one thing: the form
async function showForm(page, r) {
  const x = r.view === 'edit' ? await api(`api/items/${r.id}`) : { quantity: 1, labels: [], fields: [], location: S.settings.lastPlace ? { id: S.settings.lastPlace } : null };
  if (r.view === 'edit' && !x.writable) { location.hash = `#/item/${x.id}`; return; }
  if (r.view === 'new' && !canAdd()) throw new Error('A viewer only looks: a member or more adds things.');
  const back = x.id ? `#/item/${x.id}` : '#/';
  const inp = (v, attrs = {}) => h('input', { class: 't', value: v == null ? '' : v, ...attrs });
  const area = (v, attrs = {}) => h('textarea', { class: 't', ...attrs }, v || '');
  const f = {
    name: inp(x.name, { class: 't big', placeholder: 'What it is', maxlength: 255 }),
    description: area(x.description, { rows: 2, placeholder: 'A few words (if you like)' }),
    quantity: inp(x.quantity, { type: 'number', min: 0 }),
    location: h('select', { class: 't' }),
    manufacturer: inp(x.manufacturer, { placeholder: 'Bosch, Miele, Makita' }), modelNumber: inp(x.modelNumber), serialNumber: inp(x.serialNumber),
    assetId: inp(x.assetId), url: inp(x.url, { type: 'url', placeholder: 'https://' }),
    purchaseDate: inp(x.purchaseDate, { type: 'date' }), purchasePrice: inp(x.purchasePrice, { inputmode: 'decimal' }), purchaseFrom: inp(x.purchaseFrom),
    warrantyExpires: inp(x.warrantyExpires, { type: 'date' }), warrantyDetails: area(x.warrantyDetails, { rows: 2 }),
    soldDate: inp(x.soldDate, { type: 'date' }), soldPrice: inp(x.soldPrice, { inputmode: 'decimal' }), soldTo: inp(x.soldTo), soldNotes: area(x.soldNotes, { rows: 2 }),
    notes: area(x.notes, { rows: 4 }),
  };
  const lifetime = h('input', { type: 'checkbox', checked: !!x.lifetimeWarranty });
  const insured = h('input', { type: 'checkbox', checked: !!x.insured });
  const archived = h('input', { type: 'checkbox', checked: !!x.archived });
  const drawPlaces = (sel) => fill(f.location, placeOptions(sel));
  drawPlaces(x.location ? x.location.id : null);
  const newPlace = h('button', { type: 'button', class: 'lnk small', onclick: async () => { const p = await placeDialog(null, f.location.value ? +f.location.value : null); if (p) drawPlaces(p.id); } }, 'New place…');
  // labels: ticked chips, and a box to add another
  const chosen = new Set(x.labels.map((t) => t.name));
  const labBox = h('div', { class: 'chiprow' });
  const labIn = h('input', { class: 't', placeholder: 'Another label, then Enter', list: 'labelnames' });
  const drawLabels = () => fill(labBox, [...new Set([...S.labels.map((t) => t.name), ...chosen])].map((n) => {
    const t = S.labels.find((l) => l.name === n);
    return h('button', { type: 'button', class: `lchip big pick${chosen.has(n) ? ' on' : ''}`, style: t && t.color ? { '--lc': t.color } : null,
      onclick: () => { if (chosen.has(n)) chosen.delete(n); else chosen.add(n); drawLabels(); } }, chosen.has(n) ? icon('check', 'xs') : null, n);
  }));
  labIn.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); const v = labIn.value.trim(); if (v) { chosen.add(v); labIn.value = ''; drawLabels(); } } });
  drawLabels();
  // own fields
  const fieldRows = h('div', { class: 'ownfields' });
  const addField = (n = '', v = '') => fieldRows.append(h('div', { class: 'ownfield' }, inp(n, { placeholder: 'Name (Filter, Colour, PIN)' }), inp(v, { placeholder: 'Value' }),
    h('button', { type: 'button', class: 'iconbtn', title: 'Remove', onclick: (e) => e.currentTarget.parentElement.remove() }, icon('close', 's'))));
  x.fields.forEach((o) => addField(o.name, o.value));
  const save = async () => {
    const json = Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.value]));
    json.locationId = f.location.value ? +f.location.value : null; delete json.location;
    json.lifetimeWarranty = lifetime.checked; json.insured = insured.checked; json.archived = archived.checked;
    json.labels = [...chosen];
    json.fields = [...fieldRows.children].map((row) => { const [a, b] = row.querySelectorAll('input'); return { name: a.value, value: b.value }; }).filter((o) => o.name.trim() && o.value.trim());
    try {
      const got = await api(x.id ? `api/items/${x.id}` : 'api/items', { method: x.id ? 'PATCH' : 'POST', json });
      if (!x.id && json.locationId) saveSettings({ lastPlace: json.locationId });
      await refreshAround(); location.hash = `#/item/${got.id}`;
    } catch (e) { fail(e); }
  };
  const sec = (ic, label) => h('div', { class: 'fsec' }, icon(ic), label);
  page.classList.add('form');
  put(page, h('form', { onsubmit: (e) => { e.preventDefault(); save(); } },
    h('div', { class: 'pagehead' }, h('h1', null, x.id ? 'Change' : 'New thing')),
    f.name, h('div', { class: 'grid', style: { marginTop: '10px' } }, h('label', { class: 'field wide' }, h('span', null, 'Description'), f.description)),
    sec('place', 'Where'),
    h('div', { class: 'grid' }, h('label', { class: 'field' }, h('span', null, 'Place'), f.location, canAdd() ? newPlace : null), fld('How many', f.quantity)),
    sec('tag', 'Labels'), labBox, h('div', { class: 'grid', style: { marginTop: '6px' } }, labIn), h('datalist', { id: 'labelnames' }, S.labels.map((t) => h('option', { value: t.name }))),
    sec('info', 'What it is'),
    h('div', { class: 'grid' }, fld('Maker', f.manufacturer), fld('Model', f.modelNumber), fld('Serial number', f.serialNumber), fld('Asset id', f.assetId), fld('Link (the product page)', f.url)),
    sec('receipt', 'Bought'),
    h('div', { class: 'grid' }, fld('On', f.purchaseDate), fld(`Price (${S.currency})`, f.purchasePrice), fld('From', f.purchaseFrom)),
    sec('shield', 'Warranty and insurance'),
    h('div', { class: 'grid' }, fld('Warranty until', f.warrantyExpires),
      h('label', { class: 'check' }, lifetime, h('span', null, 'Warranty for life')), h('label', { class: 'check' }, insured, h('span', null, 'Insured'))),
    h('div', { class: 'grid', style: { marginTop: '10px' } }, h('label', { class: 'field wide' }, h('span', null, 'Warranty details'), f.warrantyDetails)),
    sec('tune', 'Its own details'), fieldRows, h('button', { type: 'button', class: 'lnk small', onclick: () => addField() }, 'Add a detail…'),
    sec('text', 'Notes'), f.notes,
    sec('archive', 'Sold or gone'),
    h('label', { class: 'check' }, archived, h('span', null, 'Archived: sold, given away or thrown out (it keeps its story)')),
    h('div', { class: 'grid', style: { marginTop: '10px' } }, fld('On', f.soldDate), fld('To', f.soldTo), fld(`For (${S.currency})`, f.soldPrice)),
    h('div', { class: 'grid', style: { marginTop: '10px' } }, h('label', { class: 'field wide' }, h('span', null, 'Notes on the sale'), f.soldNotes)),
    h('div', { class: 'formbar' }, h('button', { class: 'pillbtn primary noic', type: 'submit' }, x.id ? 'Save' : 'Add'), h('a', { class: 'pillbtn noic', href: back }, 'Cancel'),
      !x.id ? h('span', { class: 'muted small' }, 'Photos, manuals and receipts come next, on the thing’s page.') : null)));
  setTimeout(() => f.name.focus(), 0);
}

// ------------------------------------------------------------------ import and export
async function showImport(page) {
  const out = h('div', { class: 'importres' });
  const pick = async () => {
    const [file] = await pickFiles('.csv,.tsv,text/csv,text/tab-separated-values', false);
    if (!file) return;
    fill(out, h('p', { class: 'muted' }, `Reading ${file.name}…`));
    try {
      const r = await api('api/import/homebox', { method: 'POST', body: file, headers: { 'Content-Type': 'text/csv' } });
      fill(out, h('div', { class: 'draftnote' }, icon('check', 's'), `${r.added} added, ${r.changed} brought up to date; ${r.locations} new places, ${r.labels} new labels.`),
        r.skipped.length ? [h('p', null, `${r.skipped.length} rows were left out:`), h('ul', { class: 'muted small' }, r.skipped.map((s) => h('li', null, s)))] : null,
        h('p', null, h('a', { class: 'pillbtn', href: '#/' }, 'See them')));
      refreshAround();
    } catch (e) { fill(out, h('p', { class: 'err' }, e.message)); }
  };
  // from a running Homebox, through its API: everything, the photos, manuals, receipts and the log too
  const srvOut = h('div', { class: 'importres' });
  const hbUrl = h('input', { class: 't', type: 'url', placeholder: 'https://homebox.example.com', value: store.get('homebox') || '', autocomplete: 'off' });
  const hbUser = h('input', { class: 't', placeholder: 'Email', autocomplete: 'off', autocapitalize: 'none' });
  const hbPw = h('input', { class: 't', type: 'password', placeholder: 'Password', autocomplete: 'off' });
  let timer = null;
  const showJob = (j) => {
    if (!j || j.state === 'idle') { fill(srvOut); return; }
    const counts = `${j.added} added, ${j.changed} brought up to date, ${j.files} ${j.files === 1 ? 'file' : 'files'}, ${j.log} log ${j.log === 1 ? 'line' : 'lines'}`;
    fill(srvOut,
      j.state === 'running' ? h('div', { class: 'draftnote' }, icon('download', 's'), j.total ? `${j.done} of ${j.total} things: ${counts}…` : `${j.step || 'Starting'}…`)
        : j.state === 'failed' ? h('p', { class: 'err' }, `The import stopped: ${j.error}`)
          : h('div', { class: 'draftnote' }, icon('check', 's'), `Done: ${j.total} things from ${j.source}. ${counts}.`),
      j.skipped && j.skipped.length ? [h('p', null, `Left out (${j.skipped.length}):`), h('ul', { class: 'muted small' }, j.skipped.map((x) => h('li', null, x)))] : null,
      j.state === 'done' ? h('p', null, h('a', { class: 'pillbtn', href: '#/' }, 'See them')) : null);
    clearTimeout(timer);
    if (j.state === 'running') timer = setTimeout(poll, 1500);
    else if (j.state === 'done') refreshAround();
  };
  const poll = async () => { if (!document.body.contains(srvOut)) return; try { showJob(await api('api/import/homebox-server')); } catch (e) { fill(srvOut, h('p', { class: 'err' }, e.message)); } };
  const fromServer = async (e) => {
    e.preventDefault();
    fill(srvOut, h('p', { class: 'muted' }, 'Signing in to Homebox…'));
    try {
      const j = await api('api/import/homebox-server', { method: 'POST', json: { url: hbUrl.value.trim(), username: hbUser.value.trim(), password: hbPw.value } });
      store.set('homebox', hbUrl.value.trim()); hbPw.value = '';
      showJob(j);
    } catch (x) { fill(srvOut, h('p', { class: 'err' }, x.message)); }
  };
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Import and export')),
    canEditAll() ? h('form', { class: 'box importbox', onsubmit: fromServer }, h('h2', null, icon('download'), 'From a Homebox server'),
      h('p', null, 'Everything in your Homebox, the photos, manuals, receipts, warranties and the maintenance log too, straight from Homebox itself. Give its address and the email and password you sign in to it with: they are used for this import and not kept.'),
      h('div', { class: 'grid' }, fld('Homebox address', hbUrl), fld('Email', hbUser), fld('Password', hbPw)),
      h('p', { class: 'muted small' }, 'Running it again brings things up to date instead of adding them twice, and things from an earlier CSV import are taken over (same name, same place). Maintenance that was only scheduled is not brought: add it here as upkeep.'),
      h('p', null, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Bring everything over')), srvOut) : null,
    h('div', { class: 'box importbox' }, h('h2', null, icon('download'), 'From a Homebox export (CSV)'),
      h('p', null, 'In Homebox, open ', h('b', null, 'Tools'), ' and choose ', h('b', null, 'Export inventory'), '. Pick that file here: every thing comes over with its place (the places are made), its labels, its purchase, warranty and sale details and its own fields.'),
      h('p', { class: 'muted small' }, 'Importing the same export again brings the things it added up to date instead of adding them twice. Homebox’s export has no photos, manuals or maintenance log: the import from a Homebox server above brings those.'),
      canAdd() ? h('p', null, h('button', { class: 'pillbtn primary', onclick: pick }, icon('upload', 's'), 'Pick the CSV file')) : h('p', { class: 'muted' }, 'A viewer only looks.'), out),
    h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Export'),
      h('p', null, 'Every thing as a spreadsheet (CSV), in Homebox’s columns: open it in a spreadsheet, or take it to Homebox or another app.'),
      h('div', { class: 'exports chiprow' }, h('a', { class: 'pillbtn', href: 'api/export.csv', download: '' }, icon('download', 's'), 'Everything'),
        h('a', { class: 'pillbtn', href: 'api/export.csv?archived=false', download: '' }, icon('download', 's'), 'Only what you still have'))));
  if (canEditAll()) poll();  // an import that is running (or just ran) shows where it is
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'],
    ...(adm ? [['things', 'Things'], ['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, things: setThings, server: setServer, security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);

const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
/** Settings › Account: display name, email and password, then the app passwords: iosuite-shared's panels (the same in every io app). */
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast });
}

/** Settings › Display: the theme (saved with the account) and what the app opens on. */
async function setDisplay(el) {
  const ui = await accountUi();
  const sv = h('select', { class: 't', onchange: async (e) => { await saveSettings({ startView: e.target.value }); toast('Saved'); } },
    Object.entries(VIEWS).map(([v, [l]]) => h('option', { value: v, selected: v === (S.settings.startView || 'all') ? true : null }, l)));
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || store.get('theme') || 'system', (t) => { S.settings.theme = t; applyTheme(t); })),
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Things'), h('div', { class: 'grid' }, fld('Open on', sv))));
}

/** Settings › Things (admins): the currency, for prices and what the things are worth together. */
const CURRENCIES = ['EUR', 'GBP', 'USD', 'CHF', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'CAD', 'AUD', 'NZD', 'JPY'];
async function setThings(el) {
  const cur = (await api('api/things-settings')).currency || S.currency;
  const list = CURRENCIES.includes(cur) ? CURRENCIES : [cur, ...CURRENCIES];
  const sel = h('select', { class: 't', onchange: async (e) => {
    try { await api('api/things-settings', { method: 'PUT', json: { currency: e.target.value } }); S.currency = e.target.value; toast('Saved'); } catch (x) { fail(x); }
  } }, list.map((c) => h('option', { value: c, selected: c === cur ? true : null }, c)));
  el.append(h('div', { class: 'box' }, h('h2', null, icon('money'), 'Money'), h('div', { class: 'grid' }, fld('Currency', sel)),
    h('p', { class: 'muted small' }, 'Prices are kept as plain amounts: changing the currency changes how they show, not what they are.')));
}

/** Settings › Security and Global settings (suite admins): the people, their role in every app, app
    passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite-shared. */
const SUITE_TABS = { security: 'Security', global: 'Global settings' };
async function setSuite(el, r) {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { el.append(h('p', { class: 'warn' }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}

/** Settings › Server (admins): the MCP switch, the version and its updates, the server log and Restart
    (iosuite-shared's panel, the same in every io app). */
async function setServer(el) {
  let ui;
  try { ui = await serverUi(); } catch (e) { el.append(h('p', { class: 'warn' }, `The Server panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { toast });
}
const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);

// ------------------------------------------------------------------ sign-in
function showSignIn() {
  // as in the other io apps: a tile per account; one click for a passwordless account, a password for the others
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
    try { await api(first ? 'api/auth/setup' : 'api/auth/login', { method: 'POST', json: { name: n, password: p } }); location.reload(); } catch (x) { err.textContent = x.message; }
  };
  const submit = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  document.body.append(h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: submit },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Things'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin, who adds the rest of the family in Settings. (Already use another io app? Sign in there first, or use the same name and password here once the apps share their accounts.)') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('api/auth/accounts').then((d) => {
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
  S.status = await api('api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('api/auth/me')).settings || {}; } catch { S.settings = {}; }
  if (S.settings.theme) applyTheme(S.settings.theme);
  drawUser();
  const nb = $('#newbtn');
  nb.hidden = !canAdd();
  nb.onclick = () => { location.hash = '#/new'; };
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', applySidebar);
  let t;
  $('#q').addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      const q = e.target.value.trim();
      if (q) location.hash = `#/search/${encodeURIComponent(q)}`;
      else if (route().view === 'search') location.hash = '#/';
    }, 250);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (document.querySelector('.lightbox')) return; if (openMenu) closeMenu(); else if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin, .dialog-back, .lightbox')) return;
    if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
    else if (e.key === 'n' && canAdd()) location.hash = '#/new';
  });
  addEventListener('hashchange', () => { document.title = 'ioThings'; onRoute(); });
  try { around(await api('api/summary')); } catch { /* the page says so */ }
  await onRoute();
  loadSuite();
}
start().catch(fail);
