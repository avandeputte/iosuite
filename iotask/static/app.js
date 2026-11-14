/* ioTask web app: no build step. The modules in js/, one per page (lists.js: the task lists; task.js: the task form;
   activity.js with import; settings.js) beside core.js (helpers, dates and state), shell.js (the sidebar, the suite
   menu, sign-in) and main.js (the routes and the start). The smart lists (Today, Scheduled, All, Completed) and the
   lists to pick in the sidebar; a list of tasks with a box to tick each off, a new-task line that reads plain
   English, subtasks under their task, postponing, the order by hand (drag); the task form (due date and time,
   repeat, alert, priority, the family members it is for, notes, link); the activity log with undo, templates, a
   print view; search, import, and settings (account, display, apps and devices, lists, and for admins family and
   server, and for suite admins security and global settings), laid out as in the other ioThing apps. */
import './js/main.js';
