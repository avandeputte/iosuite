# ioContact

ioContact is the address book of the ioThing suite. Linked to it, iopix knows the birthdays of the people named in your library. It turns on by itself when ioContact is part of the suite.

## What it adds

- **Birthdays on the People page.** The birthdays in the next month are listed at the top, today's first, with the age each person turns. Click one to see their photos.
- **Ages in the photo info.** Under **People**, each person with a known birth year shows how old they were in that photo. When the photo's date is only known to the year (or to the month of their birthday), it says both possible ages, such as "33 or 34".
- **Better date suggestions.** **Date suggestions** use the birth years from ioContact, as if you had entered them. A birth year you enter in iopix still wins.

Birthdays are shown to signed-in accounts only (or to everyone while iopix has no accounts). iopix never writes to ioContact.

## Which contact belongs to which person

iopix uses the links you make in ioContact: a contact's **ioPix person** (in ioContact, **Link to ioPix** on a contact, or **Link by name** on its ioPix people page). iopix keeps no mapping of its own. Only linked contacts with a birthday count, so to add someone or fix a match, link the contact in ioContact.

## Setting it up

Nothing to set up. When ioContact runs in the same suite (the same Shared ioSuite database), iopix finds it by itself and reads the contacts with its own read-only app password, which Settings › Security › App passwords lists. Its server reads ioContact, never your browser, and does so again every ten minutes. When ioContact can't be reached, pages carry on with the birthdays from the last good read (none just after iopix restarts), and the server log says what went wrong.
