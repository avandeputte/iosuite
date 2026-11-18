/* ioDocs web app: one module, no build step. The family's papers as cards or a table (all of them, the ones to renew,
   archived, by kind, by person, found by words); one document with its scans, facts, number (hidden until asked),
   reminder and who sees it; adding one from a scan (read on the server: OCR, a passport's machine-readable zone, a
   license's barcode) or typed in; and settings (account, display, and for admins the server, and for suite admins
   security and global settings), laid out as in the other ioThing apps. */
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
  alert: 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
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
  folder: 'M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z',
  passport: 'M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-6 3c2.21 0 4 1.79 4 4s-1.79 4-4 4-4-1.79-4-4 1.79-4 4-4zm4 13H8v-2h8v2zm-4-11c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  badge: 'M20 7h-5V4c0-1.1-.9-2-2-2h-2c-1.1 0-2 .9-2 2v3H4c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V9c0-1.1-.9-2-2-2zM9 12c.83 0 1.5.67 1.5 1.5S9.83 15 9 15s-1.5-.67-1.5-1.5S8.17 12 9 12zm3 6H6v-.75c0-1 2-1.5 3-1.5s3 .5 3 1.5V18zm1-9h-2V4h2v5zm5 7.5h-4V15h4v1.5zm0-3h-4V12h4v1.5z',
  car: 'M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z',
  plane: 'M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z',
  home: 'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z',
  health: 'M19 3H5c-1.1 0-1.99.9-1.99 2L3 19c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-1 11h-4v4h-4v-4H6v-4h4V6h4v4h4v4z',
  cert: 'M4 3c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h8v5l3-3 3 3v-5h2c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2H4zm8 2h8v3h-8V5zm0 5h8v3h-8v-3zM4 5h6v8H4V5z',
  gavel: 'M1 21h12v2H1zM5.245 8.07l2.83-2.827 14.14 14.142-2.828 2.828zM12.317 1l5.657 5.656-2.83 2.83-5.654-5.66zM3.825 9.485l5.657 5.657-2.828 2.828-5.657-5.657z',
  school: 'M5 13.18v4L12 21l7-3.82v-4L12 17l-7-3.82zM12 3 1 9l11 6 9-4.91V17h2V9L12 3z',
  card: 'M20 4H4c-1.11 0-1.99.89-1.99 2L2 18c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm0 14H4v-6h16v6zm0-10H4V6h16v2z',
  calendar: 'M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10z',
  bell: 'M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z',
  eye: 'M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z',
  eyeOff: 'M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46A11.804 11.804 0 0 0 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z',
  lockFill: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM9 6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9V6z',
  open: 'M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z',
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
const store = { get: (k) => { try { return localStorage.getItem(`iodocs.${k}`); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(`iodocs.${k}`, v); } catch { /* private mode */ } } };


// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, counts: {}, family: [], kinds: [], reads: {}, may: {} };
// the suite's roles, each able to do what the one before can: a viewer only looks, a member adds documents and changes
// their own, an editor changes every document they see
const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
const canAdd = () => roleAtLeast('member');
/** What goes around the documents: how many, the kinds, the family (the summary). */
function around(d) { S.counts = d.counts; S.family = d.family || []; S.kinds = d.kinds || []; S.reads = d.reads || {}; S.may = d.may || {}; }
async function refreshAround() { try { around(await api('api/summary')); } catch { /* the page says so */ } drawNav(); }
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}
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
const personOf = (id) => S.family.find((m) => m.id === id);
/** A family member's badge (the suite's family, Settings › Security › Family: the same colour, initials and face in every
    io app): their initials on their colour; `face`: their face (ioPix, else their ioContact card) when they have one. */
const memberBadge = (m, face = false) => h('span', { class: `mem${face && m.hasFace ? ' face' : ''}`, title: m.displayName, style: { '--mc': m.color || '#5f6b7a' } }, m.initials || initials(m.displayName),
  face && m.hasFace ? h('img', { src: `api/auth/family/${m.id}/face`, alt: '', loading: 'lazy', onerror: (e) => { e.currentTarget.parentNode.classList.remove('face'); e.currentTarget.remove(); } }) : null);
/** "Emma's" / "Chris'" */
const possessive = (n) => (/s$/i.test(n) ? `${n}’` : `${n}’s`);

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
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to all the documents. */
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


/* The sidebar, as in the other io apps: the name on top, the documents (all of them, what expires, archived), the
   kinds, the family, adding, Settings at the foot. It docks beside the page on a wide screen unless its button put it
   away (remembered); otherwise it slides over the page. Phones get a bottom bar. */
const DOCK_MIN = 1100;
const VIEWS = { all: ['All documents', 'folder', '--c-blue'], expiring: ['To renew', 'timer', '--c-orange'], archived: ['Archived', 'archive', '--c-slate'] };
const viewCount = (k) => ({ all: S.counts.documents, expiring: (S.counts.soon || 0) + (S.counts.expired || 0), archived: S.counts.archived }[k] || null);
const kindOf = (k) => S.kinds.find((x) => x.key === k) || { key: k, label: k, plural: k, icon: 'file' };
function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label) => h('div', { class: 'navsec' }, h('span', null, label));
  const folded = new Set((store.get('navfold') || '').split(',').filter(Boolean));
  const fold = (key, label, n) => h('div', { class: `navsec${folded.has(key) ? ' folded' : ''}` },
    h('button', { class: 'fold', 'aria-expanded': String(!folded.has(key)), title: folded.has(key) ? `Show the ${label.toLowerCase()}` : `Fold the ${label.toLowerCase()} away`,
      onclick: () => { folded.has(key) ? folded.delete(key) : folded.add(key); store.set('navfold', [...folded].join(',')); drawNav(); } },
    icon('next', 's'), h('span', null, label), folded.has(key) && n ? h('span', { class: 'fn' }, n) : null));
  const shown = (key, list, on) => folded.has(key) ? list.filter(on) : list;
  const kinds = S.kinds.filter((k) => S.counts.kinds && S.counts.kinds[k.key]);
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Docs')];
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'All documents' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'All documents' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    Object.entries(VIEWS).map(([k, [label, ic, hv]]) => link(k, `#/${k}`, ic, label, viewCount(k), r.view === k, hv)),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    S.family.length ? [h('div', { class: 'navgap' }), fold('family', 'Family', S.family.length),
      shown('family', S.family, (m) => r.view === 'person' && r.id === m.id).map((m) => h('a', { href: `#/person/${m.id}`, 'data-v': 'person', class: `who${r.view === 'person' && r.id === m.id ? ' on' : ''}`, title: `${possessive(m.displayName)} documents` },
        memberBadge(m, true), h('span', { class: 'nl' }, m.displayName), m.count ? h('span', { class: 'n' }, m.count) : null))] : null,
    kinds.length ? [h('div', { class: 'navgap' }), fold('kinds', 'Kinds', kinds.length),
      shown('kinds', kinds, (k) => r.view === 'kind' && r.id === k.key).map((k) => link('kind', `#/kind/${k.key}`, k.icon, k.plural, S.counts.kinds[k.key], r.view === 'kind' && r.id === k.key, '--c-indigo'))] : null,
    canAdd() ? [h('div', { class: 'navgap' }), sec('Add'),
      link('scan', '#/scan', 'camera', 'From a scan or photo', null, r.view === 'scan', '--c-teal'),
      link('new', '#/new', 'add', 'Type one in', null, r.view === 'new', '--c-blue')] : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['kind', 'person', 'new', 'scan', 'settings', 'search'].includes(r.view));
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

/** Phones: what the bottom bar has no room for (the family, the kinds, adding, settings). */
function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    canAdd() ? [tile('#/scan', 'camera', 'From a scan', 'var(--c-teal)', r.view === 'scan'), tile('#/new', 'add', 'Type one in', 'var(--c-blue)', r.view === 'new')] : null,
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'),
    S.family.map((m) => h('a', { href: `#/person/${m.id}`, class: r.view === 'person' && r.id === m.id ? 'on' : null, style: { '--hue': m.color } },
      h('span', { class: 'sic' }, memberBadge(m, true)), h('span', null, m.displayName))),
    S.kinds.filter((k) => S.counts.kinds && S.counts.kinds[k.key]).map((k) => tile(`#/kind/${k.key}`, k.icon, k.plural, 'var(--c-indigo)', r.view === 'kind' && r.id === k.key)));
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
  if (a === 'kind' && b) return { view: 'kind', id: b };
  if (a === 'person' && b) return { view: 'person', id: +b };
  if (a === 'search') return { view: 'search', q: b || '' };
  if (a === 'doc' && b) return { view: c === 'edit' ? 'edit' : 'doc', id: +b };
  if (a === 'new') return { view: 'new' };
  if (a === 'scan') return { view: 'scan' };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  return { view: 'all' };
}
const LIST_VIEWS = ['all', 'expiring', 'archived', 'kind', 'person', 'search'];

async function onRoute() {
  const r = route();
  const main = $('#main');
  closeMenu();
  try {
    const page = h('div', { class: 'page' });
    if (LIST_VIEWS.includes(r.view)) await drawDocs(page, r);
    else await ({ doc: showDoc, edit: showForm, new: showForm, scan: showScan, settings: showSettings })[r.view](page, r);
    main.replaceChildren(page);
    main.scrollTop = 0;
  } catch (e) { main.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'empty' }, icon('folder'), h('p', null, e.message || String(e)), h('p', null, h('a', { class: 'lnk', href: '#/' }, 'All documents'))))); }
  drawNav();
}

// ------------------------------------------------------------------ the documents, as cards or as a table
const SORTS = { expires: 'Expiring first', title: 'A to Z', kind: 'By kind', new: 'Newest first', updated: 'Last changed' };
async function fetchDocs(r) {
  const q = new URLSearchParams();
  if (r.view === 'archived') q.set('status', 'archived');
  if (r.view === 'expiring') q.set('status', 'expiring');
  if (r.view === 'kind') q.set('kind', r.id);
  if (r.view === 'person') q.set('person', r.id);
  if (r.view === 'search') { q.set('q', r.q); q.set('status', 'all'); }
  if (SORTS[S.settings.sort] && S.settings.sort !== 'expires' && r.view !== 'expiring') q.set('sort', S.settings.sort);
  return (await api(`api/documents?${q}`)).items;
}
/** "Expires in 40 days", "Expired 3 days ago", "Valid until 14 Mar 2031". */
function expiryWords(e, short = false) {
  if (!e) return '';
  if (e.days < 0) return e.days === -1 ? 'Expired yesterday' : `Expired ${short ? '' : `on ${fmtDay(e.on)}, `}${-e.days} days ago`.replace(/\s+,/, ',');
  if (e.state === 'soon') return `Expires ${dueWords(e.days)}`;
  return short ? `Until ${fmtDay(e.on)}` : `Valid until ${fmtDay(e.on)}`;
}
function expiryBadge(e, short = true) {
  if (!e) return null;
  const cls = e.state === 'expired' ? 'off' : e.state === 'soon' ? 'warn' : 'ok';
  return h('span', { class: `badge ${cls}` }, icon(e.state === 'ok' ? 'check' : 'timer', 'xs'), expiryWords(e, short));
}
const VIS = { family: ['Everyone here', 'people', 'Everyone with a role in ioDocs sees it.'],
  people: ['Its people and the grown-ups', 'lock', 'The people it is for, whoever added it, and the editors and admins.'],
  private: ['Private', 'lockFill', 'Only the people it is for and whoever added it: nobody else, not even an admin.'] };
function card(x) {
  const k = kindOf(x.kind);
  return h('a', { class: `rcard dcard${x.archived ? ' gone' : ''}`, href: `#/doc/${x.id}` },
    x.cover ? h('img', { class: 'rpic', src: `${x.cover}?size=small`, alt: '', loading: 'lazy' })
      : h('span', { class: 'rpic none', style: { '--h': hue(x.kind) } }, icon(k.icon)),
    h('span', { class: 'rbody' },
      h('span', { class: 'rtitle' }, x.title),
      h('span', { class: 'rmeta' }, icon(k.icon, 'xs'), [k.label, x.issuer].filter(Boolean).join(' · ')),
      x.expiry ? expiryBadge(x.expiry) : h('span', { class: 'badge none' }, 'Does not expire'),
      x.people.length || x.visibility !== 'people' ? h('span', { class: 'labs' }, x.people.map((m) => memberBadge(m, true)),
        x.visibility !== 'people' ? h('span', { class: 'vis', title: VIS[x.visibility][2] }, icon(VIS[x.visibility][1], 'xs'), VIS[x.visibility][0]) : null) : null));
}
function table(items) {
  return h('div', { class: 'tablewrap' }, h('table', { class: 'things' },
    h('thead', null, h('tr', null, ['Title', 'Kind', 'Whose', 'Issued by', 'Expires', ''].map((t) => h('th', null, t)))),
    h('tbody', null, items.map((x) => h('tr', { onclick: () => { location.hash = `#/doc/${x.id}`; } },
      h('td', null, h('a', { href: `#/doc/${x.id}`, class: 'lnk' }, x.title)), h('td', null, kindOf(x.kind).label),
      h('td', null, h('span', { class: 'ppl' }, x.people.map((m) => memberBadge(m, true)))),
      h('td', null, x.issuer || ''), h('td', null, x.expiresOn ? fmtDay(x.expiresOn) : ''),
      h('td', null, x.expiry && x.expiry.state !== 'ok' ? expiryBadge(x.expiry) : ''))))));
}
async function drawDocs(page, r) {
  const items = await fetchDocs(r);
  const who = r.view === 'person' ? personOf(r.id) : null;
  const k = r.view === 'kind' ? kindOf(r.id) : null;
  if (r.view === 'person' && !who) throw new Error('No one in the family by that number');
  const title = who ? `${possessive(who.displayName)} documents` : k ? k.plural : r.view === 'search' ? `“${r.q}”` : VIEWS[r.view][0];
  if (who || k) document.title = `${title} · ioDocs`;
  page.classList.add('wide');
  const asTable = S.settings.layout === 'table';
  const sort = r.view === 'expiring' ? null : h('select', { class: 't sortsel', title: 'In what order', 'aria-label': 'In what order', onchange: async (e) => { await saveSettings({ sort: e.target.value }); onRoute(); } },
    Object.entries(SORTS).map(([key, l]) => h('option', { value: key, selected: key === (S.settings.sort || 'expires') ? true : null }, l)));
  const layout = h('button', { class: 'iconbtn', title: asTable ? 'As cards' : 'As a table', onclick: async () => { await saveSettings({ layout: asTable ? 'cards' : 'table' }); onRoute(); } }, icon(asTable ? 'grid' : 'list'));
  put(page, h('div', { class: 'pagehead' }, h('h1', null, title), h('span', { class: 'count' }, items.length || ''), h('span', { class: 'grow' }),
    items.length > 1 ? sort : null, items.length ? layout : null));
  if (r.view === 'expiring') put(page, h('p', { class: 'muted bookabout' }, 'The documents that have expired, or will within their reminder: nine months for a passport, two for a license, one for a policy (each document can have its own).'));
  if (r.view === 'all' && items.length) {
    const c = S.counts;
    put(page, h('div', { class: 'facts' },
      h('span', { class: 'fact' }, icon('folder', 's'), h('span', null, h('small', null, 'Documents'), String(c.documents))),
      h('a', { class: `fact${c.soon ? ' w-soon' : ''}`, href: '#/expiring' }, icon('timer', 's'), h('span', null, h('small', null, 'To renew soon'), String(c.soon || 'None'))),
      h('a', { class: `fact${c.expired ? ' w-expired' : ''}`, href: '#/expiring' }, icon('alert', 's'), h('span', null, h('small', null, 'Expired'), String(c.expired || 'None')))));
  }
  if (!items.length) {
    const first = r.view === 'all';
    put(page, h('div', { class: 'empty' }, icon(r.view === 'archived' ? 'archive' : r.view === 'expiring' ? 'check' : 'folder'),
      h('p', null, r.view === 'search' ? 'Nothing has those words.' : r.view === 'archived' ? 'Nothing archived: an old passport or a policy that ended goes here when the new one comes.'
        : r.view === 'expiring' ? 'Nothing to renew: no document expires within its reminder.' : r.view === 'kind' ? 'None of this kind.'
          : r.view === 'person' ? `No document is marked as ${possessive(who.displayName)} yet (or none you may see).`
          : 'No documents yet. Take a photo of a passport, a license or a policy: ioDocs reads it and fills the details in.'),
      first && canAdd() ? h('p', { class: 'emptybtns' }, h('a', { class: 'pillbtn primary', href: '#/scan' }, icon('camera', 's'), 'From a scan or photo'),
        h('a', { class: 'pillbtn', href: '#/new' }, icon('add', 's'), 'Type one in')) : null));
    return;
  }
  put(page, asTable ? table(items) : h('div', { class: 'rgrid' }, items.map(card)));
}

// ------------------------------------------------------------------ adding from a scan
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
const SCANS = 'image/*,application/pdf';
const sendFile = (id, file, read = true) => api(`api/documents/${id}/files?${new URLSearchParams({ name: file.name, read: read ? 'true' : 'false' })}`,
  { method: 'POST', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' } });
/** Send the files to the document, each read on the way; what was read, together. */
async function sendScans(id, picked, note) {
  const got = { filled: new Set(), differs: [], read: 0, errors: [], unread: new Set() };
  let n = 0;
  for (const f of picked) {
    n += 1;
    if (note) note(picked.length > 1 ? `Reading ${n} of ${picked.length}…` : 'Reading the scan…');
    try {
      const r = await sendFile(id, f);
      (r.filled || []).forEach((x) => got.filled.add(x));
      (r.unread || []).forEach((x) => got.unread.add(x));
      got.differs.push(...(r.differs || []));
      if (r.found && Object.keys(r.found).length) got.read += 1;
      if (r.error) got.errors.push(r.error);
    } catch (e) { got.errors.push(e.message || String(e)); }
  }
  got.unread = [...got.unread].filter((x) => !got.filled.has(x));
  return got;
}
async function showScan(page) {
  if (!canAdd()) throw new Error('A viewer only looks: a member or more adds documents.');
  page.classList.add('form');
  const status = h('p', { class: 'muted' });
  const go = async (picked) => {
    if (!picked.length) return;
    status.textContent = 'Making the document…';
    try {
      const d = await api('api/documents', { method: 'POST', json: {} });
      const got = await sendScans(d.id, picked, (t) => { status.textContent = t; });
      await refreshAround();
      store.set(`read.${d.id}`, JSON.stringify({ filled: [...got.filled], differs: got.differs, read: got.read, errors: got.errors, unread: got.unread }));
      location.hash = `#/doc/${d.id}/edit`;
    } catch (e) { status.textContent = ''; fail(e); }
  };
  const drop = h('button', { class: 'scandrop', onclick: async () => go(await pickFiles(SCANS)),
    ondragover: (e) => { e.preventDefault(); e.currentTarget.classList.add('drop'); }, ondragleave: (e) => e.currentTarget.classList.remove('drop'),
    ondrop: (e) => { e.preventDefault(); e.currentTarget.classList.remove('drop'); go([...e.dataTransfer.files]); } },
  icon('camera'), h('b', null, 'Take a photo or pick a scan'), h('span', null, 'A passport’s photo page, both sides of a license or an ID card, a policy’s PDF. Drop files here too.'));
  const reads = S.reads || {};
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Add from a scan or photo')), drop, status,
    h('div', { class: 'box' }, h('h2', null, icon('ai'), 'What ioDocs reads'),
      h('ul', { class: 'reads' },
        h('li', null, h('b', null, 'Passports, ID cards and visas: '), 'the two or three lines of ‹‹‹ at the bottom of the photo page give the number, the name, the nationality, the birth date and the expiry date, each checked. The issue date is only in the printed words: it is filled in when every reading agrees on it, else left for you to type in.'),
        h('li', null, h('b', null, 'US and Canadian driver’s licenses and state IDs: '), 'the barcode on the back holds every field exactly. Add a photo of the back as well as the front.'),
        h('li', null, h('b', null, 'Anything else: '), 'the words on it, searched for its number and dates (“Policy number…”, “Policy period 01/01/2026 to 01/01/2027”, “Expires…”), and they are found by the search.')),
      h('p', { class: 'muted small' }, 'It is all read on your server: no scan leaves it. ',
        reads.ocr ? null : h('b', { class: 'warnc' }, 'This server cannot read text yet: it needs Tesseract (apt install tesseract-ocr). '),
        reads.barcodes ? null : 'License barcodes need the zxing-cpp package.')));
}
/** What a scan said: the fields it filled in, and what it says otherwise, to take or leave. */
function readBox(x, got, onDone) {
  if (!got || (!got.filled.length && !got.differs.length && !got.errors?.length && !got.unread?.length && got.read === undefined)) return null;
  const rows = got.differs.filter((d, i, a) => a.findIndex((y) => y.field === d.field && String(y.value) === String(d.value)) === i);
  const use = async (d, btn) => {
    try { await api(`api/documents/${x.id}`, { method: 'PATCH', json: { [d.field]: d.value } }); btn.replaceWith(h('span', { class: 'badge ok' }, icon('check', 'xs'), 'Used')); if (onDone) onDone(); } catch (e) { fail(e); }
  };
  const shown = (d) => (d.field.endsWith('On') ? fmtDay(d.value) : d.shown || d.value);
  return h('div', { class: 'box readbox' }, h('h2', null, icon('ai'), 'Read from the scan'),
    got.filled.length ? h('p', null, 'Filled in: ', h('b', null, got.filled.join(', ').replace(/,([^,]*)$/, ' and$1')), '. Check them before saving.')
      : got.read ? h('p', { class: 'muted' }, 'Nothing new to fill in.')
        : h('p', { class: 'muted' }, 'Nothing could be read off it. A sharper, straighter photo in good light helps; for a license, add the back with its barcode.'),
    got.unread?.length ? h('p', { class: 'note' }, 'Not read for sure: ', h('b', null, got.unread.map((u) => ({ Number: 'the number', 'Issued on': 'the issue date', 'Expires on': 'the expiry date' }[u] || u)).join(', ').replace(/,([^,]*)$/, ' and$1')),
      '. Type ', got.unread.length > 1 ? 'them' : 'it', ' in from the page: rather than guess, ioDocs leaves ', got.unread.length > 1 ? 'them' : 'it', ' empty.') : null,
    rows.length ? [h('p', { class: 'muted small' }, 'The scan says otherwise here:'),
      rows.map((d) => h('div', { class: 'differ' }, h('span', { class: 'k' }, d.label), h('span', { class: 'v' }, h('b', null, shown(d)), h('span', { class: 'muted' }, ` instead of ${d.field.endsWith('On') ? fmtDay(d.current) : d.current}`)),
        h('button', { type: 'button', class: 'pillbtn noic', onclick: (e) => use(d, e.currentTarget) }, 'Use it')))] : null,
    (got.errors || []).map((e) => h('p', { class: 'warn small' }, e)));
}

// ------------------------------------------------------------------ one document
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
  const back = h('div', { class: 'lightbox', onclick: (e) => { if (e.target === back) close(); } },
    img,
    h('div', { class: 'lbbar' }, count, h('span', { class: 'grow' }),
      h('a', { class: 'pillbtn', href: '#', onclick: (e) => { e.preventDefault(); open(pics[i].url, '_blank', 'noopener'); } }, icon('open', 's'), 'Open'),
      h('button', { class: 'iconbtn', title: 'Close', onclick: close }, icon('close'))),
    pics.length > 1 ? [h('button', { class: 'iconbtn lbnav prev', title: 'The one before', onclick: () => go(-1) }, icon('prev')),
      h('button', { class: 'iconbtn lbnav next', title: 'The next', onclick: () => go(1) }, icon('next'))] : null);
  show();
  document.body.append(back);
  document.addEventListener('keydown', key, true);
}
const kv = (k, v) => (v == null || v === '' || v === false ? null : h('div', { class: 'kv' }, h('span', { class: 'k' }, k), h('span', { class: 'v' }, v)));
/** A number shown as •••• 4567 until it is asked for (someone may be looking over a shoulder); then copied too. */
function secret(v) {
  if (!v) return null;
  const masked = v.length > 4 ? `•••• ${v.slice(-4)}` : '••••';
  const el = h('span', { class: 'secret' });
  const draw = (open) => fill(el, h('code', null, open ? v : masked),
    h('button', { class: 'iconbtn', title: open ? 'Hide it' : 'Show it', 'aria-label': open ? 'Hide the number' : 'Show the number', onclick: () => draw(!open) }, icon(open ? 'eyeOff' : 'eye', 's')),
    open ? h('button', { class: 'iconbtn', title: 'Copy', 'aria-label': 'Copy the number', onclick: () => { navigator.clipboard?.writeText(v).then(() => toast('Copied'), () => {}); } }, icon('copy', 's')) : null);
  draw(false);
  return el;
}

async function showDoc(page, r) {
  const x = await api(`api/documents/${r.id}`);
  document.title = `${x.title} · ioDocs`;
  const k = kindOf(x.kind);
  const pics = x.files.filter((f) => f.thumb);
  const more = h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
    x.writable && !x.archived ? ['history', 'Renewed: add the new one', () => renewDialog(x)] : null,
    x.writable ? ['archive', x.archived ? 'Not archived' : 'Archive (an old one)', async () => { try { await api(`api/documents/${x.id}`, { method: 'PATCH', json: { archived: !x.archived } }); await refreshAround(); onRoute(); } catch (err) { fail(err); } }] : null,
    ['print', 'Print', () => print()],
    x.writable ? ['delete', 'Delete', () => removeDoc(x)] : null]) }, icon('more'));
  const e = x.expiry;
  const facts = h('div', { class: 'facts' },
    e ? h('span', { class: `fact w-${e.state}` }, icon('timer', 's'), h('span', null, h('small', null, e.days < 0 ? 'Expired' : 'Expires'), `${fmtDay(x.expiresOn)}`, h('em', null, e.days < 0 ? ` (${-e.days} days ago)` : ` (${dueWords(e.days)})`)))
      : h('span', { class: 'fact' }, icon('check', 's'), h('span', null, h('small', null, 'Expires'), 'Never')),
    x.issuedOn ? h('span', { class: 'fact' }, icon('calendar', 's'), h('span', null, h('small', null, 'Issued'), fmtDay(x.issuedOn))) : null,
    e && e.remindFrom ? h('span', { class: 'fact' }, icon('bell', 's'), h('span', null, h('small', null, 'Reminder'), e.days > 0 && e.remindFrom > today() ? `From ${fmtDay(e.remindFrom)}` : 'On')) : null);
  const details = [kv('Number', secret(x.number)), kv('Issued by', x.issuer), kv('Country', x.country),
    ...x.fields.map((f) => kv(f.name, f.value))].filter(Boolean);
  const read = (() => { try { return JSON.parse(store.get(`read.${x.id}`) || 'null'); } catch { return null; } })();
  if (read) store.set(`read.${x.id}`, '');
  page.classList.add('item');
  put(page,
    h('div', { class: 'pagehead' }, h('h1', null, x.title), x.archived ? h('span', { class: 'badge off' }, icon('archive', 'xs'), 'Archived') : null,
      h('span', { class: 'grow' }),
      x.writable ? h('a', { class: 'pillbtn', href: `#/doc/${x.id}/edit` }, icon('edit', 's'), 'Edit') : null, more),
    h('div', { class: 'chiprow labels' },
      h('a', { class: 'chip', href: `#/kind/${x.kind}` }, icon(k.icon, 's'), k.label),
      x.people.map((m) => h('a', { class: 'chip mchip', href: `#/person/${m.id}`, title: `${possessive(m.displayName)} documents` }, memberBadge(m, true), m.displayName)),
      h('span', { class: 'chip vis', title: VIS[x.visibility][2] }, icon(VIS[x.visibility][1], 's'), VIS[x.visibility][0])),
    x.renewedBy ? h('p', { class: 'note' }, icon('history', 's'), 'Renewed: ', h('a', { class: 'lnk', href: `#/doc/${x.renewedBy}` }, 'see the new one')) : null,
    read ? readBox(x, { ...read, filled: read.filled || [] }, () => {}) : null,
    h('div', { class: 'itemtop' },
      pics.length ? h('div', { class: 'gallery' }, h('img', { class: 'hero', src: pics[0].mime === 'application/pdf' ? `${pics[0].url}?size=small` : pics[0].url, alt: '', onclick: () => (pics[0].mime === 'application/pdf' ? open(pics[0].url, '_blank', 'noopener') : lightbox(pics.filter((p) => p.mime !== 'application/pdf'), 0, x)) }),
        pics.length > 1 ? h('div', { class: 'thumbs' }, pics.slice(1, 9).map((p) => h('img', { src: `${p.url}?size=small`, alt: '', loading: 'lazy',
          onclick: () => (p.mime === 'application/pdf' ? open(p.url, '_blank', 'noopener') : lightbox(pics.filter((q) => q.mime !== 'application/pdf'), pics.filter((q) => q.mime !== 'application/pdf').indexOf(p), x)) }))) : null)
        : x.writable ? h('button', { class: 'gallery nophoto', onclick: () => addScans(x) }, icon('camera'), h('span', null, 'Add a scan or photo')) : null,
      h('div', { class: 'itemfacts' }, facts, details.length ? h('div', { class: 'kvs' }, details) : null)),
    h('div', { class: 'cols2' },
      h('section', null, filesBox(x),
        x.renews.length ? h('div', { class: 'box' }, h('h2', null, icon('history'), 'In place of'), x.renews.map((o) => h('div', { class: 'kv' }, h('a', { class: 'lnk', href: `#/doc/${o.id}` }, o.title), h('span', { class: 'muted' }, o.expiresOn ? `expired ${fmtDay(o.expiresOn)}` : '')))) : null),
      h('section', null,
        x.notes ? h('div', { class: 'box' }, h('h2', null, icon('text'), 'Notes'), h('p', { class: 'notes' }, x.notes)) : null,
        linkedBox(x.id))),
    h('p', { class: 'muted small source' }, `Added on ${fmtDay(x.created)}`));
}
async function addScans(x, given) {
  const picked = given || await pickFiles(SCANS);
  if (!picked.length) return;
  toast(picked.length > 1 ? `Reading ${picked.length} files…` : 'Reading the scan…');
  const got = await sendScans(x.id, picked);
  store.set(`read.${x.id}`, JSON.stringify({ filled: [...got.filled], differs: got.differs, read: got.read, errors: got.errors, unread: got.unread }));
  await refreshAround(); onRoute();
}
function filesBox(x) {
  const row = (f) => h('div', { class: 'filerow' },
    h('a', { class: 'fileic', href: f.url, target: '_blank', rel: 'noopener' }, f.thumb ? h('img', { src: `${f.url}?size=small`, alt: '' }) : icon(f.mime === 'application/pdf' ? 'pdf' : 'file')),
    h('span', { class: 'filetxt' }, h('a', { class: 'filename lnk', href: f.url, target: '_blank', rel: 'noopener' }, f.name),
      h('span', { class: 'muted small' }, sizeWords(f.size), f.read ? (f.found && f.found.source ? ` · read (${{ mrz: 'machine-readable zone', barcode: 'barcode', text: 'text' }[f.found.source]})` : ' · read') : '')),
    h('a', { class: 'iconbtn', href: `${f.url}?download=true`, title: 'Download', download: f.name }, icon('download', 's')),
    h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
      f.hasText ? ['text', 'What was read off it', async () => {
        try { const t = (await api(`api/documents/${x.id}/files/${f.id}/text`)).text; dialog(f.name, h('pre', { class: 'ocrtext' }, t || '(nothing)')); } catch (err) { fail(err); }
      }] : null,
      x.writable && (f.thumb || f.mime === 'application/pdf') ? ['ai', f.read ? 'Read it again' : 'Read it', async () => {
        toast('Reading…');
        try {
          const got = await api(`api/documents/${x.id}/files/${f.id}/read`, { method: 'POST' });
          store.set(`read.${x.id}`, JSON.stringify({ filled: got.filled || [], differs: got.differs || [], read: got.found && Object.keys(got.found).length ? 1 : 0, unread: got.unread || [] }));
          await refreshAround(); onRoute();
        } catch (err) { fail(err); }
      }] : null,
      x.writable && f.thumb ? ['star', 'Show on the card', async () => { try { await api(`api/documents/${x.id}/files/${f.id}`, { method: 'PATCH', json: { first: true } }); onRoute(); } catch (err) { fail(err); } }] : null,
      x.writable ? ['edit', 'Rename', async () => {
        const n = h('input', { class: 't', value: f.name });
        if (!await dialog('Rename the file', n, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
        try { await api(`api/documents/${x.id}/files/${f.id}`, { method: 'PATCH', json: { name: n.value } }); onRoute(); } catch (err) { fail(err); }
      }] : null,
      x.writable ? ['delete', 'Remove', async () => { if (!await confirmDialog('Remove this file?', `“${f.name}” goes for good.`, 'Remove', true)) return; try { await api(`api/documents/${x.id}/files/${f.id}`, { method: 'DELETE' }); onRoute(); } catch (err) { fail(err); } }] : null]) }, icon('more', 's')));
  const drops = x.writable ? {
    ondragover: (e) => { if ([...e.dataTransfer.types].includes('Files')) { e.preventDefault(); e.currentTarget.classList.add('drop'); } },
    ondragleave: (e) => e.currentTarget.classList.remove('drop'),
    ondrop: (e) => { e.preventDefault(); e.currentTarget.classList.remove('drop'); addScans(x, [...e.dataTransfer.files]); },
  } : {};
  return h('div', { class: 'box files', ...drops }, h('h2', null, icon('file'), 'Scans and files', h('span', { class: 'grow' }),
    x.writable ? h('button', { class: 'iconbtn', title: 'Add a scan or a file', onclick: () => addScans(x) }, icon('add')) : null),
  x.files.length ? x.files.map(row) : h('p', { class: 'muted' }, x.writable ? 'Add a photo of each side, or its PDF: they are read to fill the details in, and kept here.' : 'No files.'));
}
/** "Linked" under a document: the events, tasks, notes, contacts and things of the other apps linked to it. */
let linkUi = null;
function linkedBox(id) {
  const el = h('div', { class: 'linked' });
  (async () => {
    try { linkUi = linkUi || await import(new URL('api/related/ui.js', document.baseURI).href); } catch (e) { return; }
    linkUi.mount(el, { kind: 'document', id, toast });
  })();
  return el;
}
async function removeDoc(x) {
  if (!await confirmDialog('Delete this document?', `“${x.title}” goes for good, with its scans. Archive an old one instead to keep it.`, 'Delete', true)) return;
  try { await api(`api/documents/${x.id}`, { method: 'DELETE' }); toast('Deleted'); await refreshAround(); location.hash = '#/'; } catch (e) { fail(e); }
}
async function renewDialog(x) {
  const num = h('input', { class: 't', placeholder: 'The new number' });
  const iss = h('input', { class: 't', type: 'date', value: today() });
  const exp = h('input', { class: 't', type: 'date' });
  const ok = await dialog(`The new ${kindOf(x.kind).label.toLowerCase()}`, h('div', null,
    h('p', { class: 'muted' }, 'It takes this one’s place, with the same title, people and reminder; this one is archived. Add the new scan on its page (it fills the rest in).'),
    h('div', { class: 'grid' }, fld('Number', num), fld('Issued on', iss), fld('Expires on', exp))),
  [{ label: 'Cancel', value: false }, { label: 'Add the new one', value: true, primary: true }]);
  if (!ok) return;
  try {
    const d = await api(`api/documents/${x.id}/renew`, { method: 'POST', json: { number: num.value || null, issuedOn: iss.value || null, expiresOn: exp.value || null } });
    await refreshAround(); location.hash = `#/doc/${d.id}`;
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ one document: the form
async function showForm(page, r) {
  const x = r.view === 'edit' ? await api(`api/documents/${r.id}`) : { kind: 'passport', people: [], fields: [], visibility: 'people', remindDays: null };
  if (r.view === 'edit' && !x.writable) { location.hash = `#/doc/${x.id}`; return; }
  if (r.view === 'new' && !canAdd()) throw new Error('A viewer only looks: a member or more adds documents.');
  const back = x.id ? `#/doc/${x.id}` : '#/';
  const inp = (v, attrs = {}) => h('input', { class: 't', value: v == null ? '' : v, ...attrs });
  const area = (v, attrs = {}) => h('textarea', { class: 't', ...attrs }, v || '');
  const f = {
    title: inp(x.title === 'New document' ? '' : x.title, { class: 't big', placeholder: 'What it is (Riley’s passport)', maxlength: 255 }),
    number: inp(x.number, { autocomplete: 'off', spellcheck: 'false' }), issuer: inp(x.issuer, { placeholder: 'U.S. Department of State, Oregon DMV, the insurer' }),
    country: inp(x.country, { placeholder: 'United States' }),
    issuedOn: inp(x.issuedOn, { type: 'date' }), expiresOn: inp(x.expiresOn, { type: 'date' }),
    notes: area(x.notes, { rows: 4, placeholder: 'Where the original is kept, who to call…' }),
  };
  const kind = h('select', { class: 't' }, S.kinds.map((k) => h('option', { value: k.key, selected: k.key === x.kind ? true : null }, k.label)));
  const remindSel = h('select', { class: 't' });
  const remindN = inp(x.remindDays || '', { type: 'number', min: 1, max: 1000, placeholder: 'days', style: { maxWidth: '110px' } });
  const usual = () => { const k = kindOf(kind.value); return k.remind ? `The usual: ${k.remind >= 60 ? `${Math.round(k.remind / 30)} months` : `${k.remind} days`} before` : 'The usual: none (it does not expire)'; };
  const drawRemind = () => {
    const v = remindSel.value || (x.remindDays == null ? 'usual' : x.remindDays === 0 ? 'none' : 'own');
    fill(remindSel, h('option', { value: 'usual' }, usual()), h('option', { value: 'own' }, 'Days before, my own…'), h('option', { value: 'none' }, 'No reminder'));
    remindSel.value = v; remindN.hidden = v !== 'own';
  };
  remindSel.onchange = drawRemind; kind.onchange = drawRemind; drawRemind();
  const whose = new Set(x.people.map((m) => m.id));
  const peopleBox = h('div', { class: 'chiprow' });
  const drawPeople = () => fill(peopleBox, S.family.map((m) =>
    h('button', { type: 'button', class: `chip mchip toggle${whose.has(m.id) ? ' on' : ''}`, 'aria-pressed': String(whose.has(m.id)),
      onclick: () => { if (whose.has(m.id)) whose.delete(m.id); else whose.add(m.id); drawPeople(); } }, memberBadge(m, true), m.displayName)));
  drawPeople();
  let vis = x.visibility;
  const visBox = h('div', { class: 'vischoice' });
  const drawVis = () => fill(visBox, Object.entries(VIS).map(([key, [label, ic, hint]]) => h('button', { type: 'button', class: `vopt${vis === key ? ' on' : ''}`, 'aria-pressed': String(vis === key), onclick: () => { vis = key; drawVis(); } },
    icon(ic, 's'), h('span', null, h('b', null, label), h('small', null, hint)))));
  drawVis();
  const fieldRows = h('div', { class: 'ownfields' });
  const addField = (n = '', v = '') => fieldRows.append(h('div', { class: 'ownfield' }, inp(n, { placeholder: 'Name (Nationality, Class, Claims phone)' }), inp(v, { placeholder: 'Value' }),
    h('button', { type: 'button', class: 'iconbtn', title: 'Remove', onclick: (e) => e.currentTarget.parentElement.remove() }, icon('close', 's'))));
  x.fields.forEach((o) => addField(o.name, o.value));
  const archived = h('input', { type: 'checkbox', checked: !!x.archived });
  const read = x.id ? (() => { try { return JSON.parse(store.get(`read.${x.id}`) || 'null'); } catch { return null; } })() : null;
  if (read) store.set(`read.${x.id}`, '');
  const save = async () => {
    const json = Object.fromEntries(Object.entries(f).map(([key, el]) => [key, el.value]));
    json.kind = kind.value; json.visibility = vis; json.archived = archived.checked;
    json.remindDays = remindSel.value === 'usual' ? null : remindSel.value === 'none' ? 0 : (+remindN.value || null);
    if (S.family.length) json.people = [...whose];
    if (!json.title.trim()) json.title = x.id && x.title !== 'New document' ? x.title : kindOf(json.kind).label;
    json.fields = [...fieldRows.children].map((row) => { const [a, b] = row.querySelectorAll('input'); return { name: a.value, value: b.value }; }).filter((o) => o.name.trim() && o.value.trim());
    try {
      const got = await api(x.id ? `api/documents/${x.id}` : 'api/documents', { method: x.id ? 'PATCH' : 'POST', json });
      await refreshAround(); location.hash = `#/doc/${got.id}`;
    } catch (e) { fail(e); }
  };
  const sec = (ic, label) => h('div', { class: 'fsec' }, icon(ic), label);
  page.classList.add('form');
  const pics = (x.files || []).filter((p) => p.thumb);
  put(page, h('form', { onsubmit: (e) => { e.preventDefault(); save(); } },
    h('div', { class: 'pagehead' }, h('h1', null, x.id ? (read || x.title === 'New document' ? 'Check what was read' : 'Change') : 'New document')),
    read ? readBox(x, { ...read, filled: read.filled || [] }, null) : null,
    pics.length ? h('div', { class: 'formscans' }, pics.slice(0, 4).map((p) => h('a', { href: p.url, target: '_blank', rel: 'noopener' }, h('img', { src: `${p.url}?size=small`, alt: '' })))) : null,
    f.title,
    h('div', { class: 'grid', style: { marginTop: '10px' } }, fld('Kind', kind)),
    S.family.length ? [sec('people', 'Whose it is'), peopleBox, h('p', { class: 'muted small' }, 'The people it belongs to. None: the household’s (the house insurance).')] : null,
    sec('info', 'What it says'),
    h('div', { class: 'grid' }, fld('Number', f.number), fld('Issued by', f.issuer), fld('Country', f.country)),
    sec('timer', 'Dates'),
    h('div', { class: 'grid' }, fld('Issued on', f.issuedOn), fld('Expires on', f.expiresOn),
      h('label', { class: 'field' }, h('span', null, 'Reminder'), h('span', { class: 'remind' }, remindSel, remindN))),
    sec('lock', 'Who sees it'), visBox,
    sec('tune', 'Its own details'), fieldRows, h('button', { type: 'button', class: 'lnk small', onclick: () => addField() }, 'Add a detail…'),
    sec('text', 'Notes'), f.notes,
    x.id ? [sec('archive', 'Old'), h('label', { class: 'check' }, archived, h('span', null, 'Archived: replaced by a new one, or no longer in use'))] : null,
    h('div', { class: 'formbar' }, h('button', { class: 'pillbtn primary noic', type: 'submit' }, x.id ? 'Save' : 'Add'), h('a', { class: 'pillbtn noic', href: back }, 'Cancel'),
      !x.id ? h('span', { class: 'muted small' }, 'Scans come next, on its page (or add it from a scan: ioDocs fills it in).') : null)));
  if (!x.id || !read) setTimeout(() => f.title.focus(), 0);
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'],
    ...(adm ? [['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, server: setServer, security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
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
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Documents'), h('div', { class: 'grid' }, fld('Open on', sv))));
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
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Docs'))),
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
  nb.onclick = () => { location.hash = '#/scan'; };
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
    else if (e.key === 'n' && canAdd()) location.hash = '#/scan';
  });
  addEventListener('hashchange', () => { document.title = 'ioDocs'; onRoute(); });
  try { around(await api('api/summary')); } catch { /* the page says so */ }
  await onRoute();
  loadSuite();
}
start().catch(fail);
