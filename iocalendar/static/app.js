/* ioCalendar web app: no build step. The modules in js/, one per page (views.js: month, week, day and agenda;
   event.js, edit.js, search.js with import and export, settings.js) beside core.js (helpers, dates and state),
   shell.js (the sidebar, the suite menu, sign-in) and main.js (the routes and the start). Views: month, week, day
   and agenda, with the calendars to show in the sidebar; the event form (repeating events, people from ioContact,
   reminders), search, import/export, settings (account, display, apps and devices, calendars, holidays and
   birthdays, and for admins family, storage and backups, server, and for suite admins security and global
   settings), laid out as in the other ioThing apps. Events can be tagged with the family members they are for, and
   the sidebar filters the calendar by member. weather.js puts the next days' forecast on the day headers and the
   weather at an event's place on the event. */
import './js/main.js';
