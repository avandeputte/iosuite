# ioMoney

*The household's finances, in the ioThing suite (with [ioPix](https://github.com/avandeputte/iosuite/tree/main/iopix), [ioNote](https://github.com/avandeputte/iosuite/tree/main/ionote), [ioContact](https://github.com/avandeputte/iosuite/tree/main/iocontact), [ioCalendar](https://github.com/avandeputte/iosuite/tree/main/iocalendar), [ioTask](https://github.com/avandeputte/iosuite/tree/main/iotask), [ioRecipe](https://github.com/avandeputte/iosuite/tree/main/iorecipe), [ioThings](https://github.com/avandeputte/iosuite/tree/main/iothings), [ioHealth](https://github.com/avandeputte/iosuite/tree/main/iohealth) and the [ioStart](https://github.com/avandeputte/iosuite/tree/main/iostart) start page).*

A self-hosted overview of the household's money: the accounts, balances and transactions copied in from Monarch Money,
the portfolio with its quotes from Yahoo Finance, and what the house and the cars are worth after their loans. FastAPI
and a single-page vanilla JS app, with everything stored in MariaDB / MySQL, and the suite's shared library
(`iosuite-shared`, in [iosuite-shared](https://github.com/avandeputte/iosuite/tree/main/shared)).

## What it does

- **Monarch Money**: every account Monarch has (bank accounts, credit cards, investments, loans, and the house from
  Zillow and the cars it values) with its balance history, the transactions of the past two years, the holdings of the
  investment accounts, copied in every six hours and on **Sync now**. ioMoney only reads: nothing
  is changed in Monarch. Monarch has no public API; ioMoney uses the community's Python library
  ([`monarchmoneycommunity`](https://pypi.org/project/monarchmoneycommunity/)), which speaks to the API Monarch's web
  app uses. A sync runs in the background: Sync now waits a few seconds, then the page follows it (its stage and count
  every two seconds) and says how it went at the end, so a long first sync is no longer reported as failed.
- **One account synced again** (admins, an account's menu › Sync this account again): its transactions of the past
  two years, five years or all Monarch has fetched again, with its history and holdings; changes made here stay,
  what Monarch no longer has or hides goes. The regular sync's window is not moved by it.
- **Values over time**: Monarch's own history when an account first comes in (asked again, and taking over the daily
  copies, when the account is synced again); afterwards a value every sync. An account Monarch keeps without a bank
  (typed in there, or its updates turned off) that follows its transactions and holds nothing has its values worked
  out from its transactions instead, back from today's balance, at every sync: a transaction added in Monarch with an
  earlier date then moves the chart on its own date, not on the day it was added.
- **Bank links behind**: each sync keeps what Monarch says of every account's link to its bank (when Monarch last
  heard from the bank, whether the bank sign-in needs fixing there, whether the link was cut). An account Monarch has
  not heard from in more than 48 hours (by the time of the sync), or whose link is cut or needs its sign-in fixed, is
  flagged: a banner on the overview, a warning mark in the sidebar and on its row, a note on its page. Not flagged:
  closed accounts, ones typed in at Monarch or valued by it (a house), ones whose updates are turned off there, and
  ones someone asked not to flag (an account's menu › Don't flag its bank link). In the API: an account's `bank`,
  `monarch.stale` in /api/summary; in MCP: `banksBehind` in overview.
- **A new account in Monarch**: after the first sync, an account Monarch reports that ioMoney does not know is held,
  with its transactions, until an admin says (on the overview's banner or in Settings › Money) whether it is new or an
  account here that was deleted and made again in Monarch, as is often needed when a bank's link breaks. The
  likeliest account is picked (no longer in Monarch, the same last digits or a like name). An existing one takes the
  new Monarch id; the next sync matches the transactions Monarch sends under it with those kept (the same amount, at
  most three days apart, the same payee first), so none is there twice and what was changed here stays. An account
  typed in by hand can be picked too.
- **Accounts by hand** beside Monarch's: a savings account elsewhere, an investment account with what it holds, a car
  with its value. A house or a car typed in can follow a yearly change (3 % up for a house, 15 % down for a car)
  between the values you give it, marked as an estimate.
- **Its value only, or its transactions**: each account says what is followed. *Its transactions* (the usual for bank
  accounts and credit cards): they are listed, searched and counted in the spending, and in an account kept by hand
  each one moves the balance. *Its value only* (the usual for the rest): the balance or value alone, typed in now and
  then or as Monarch has it, and the account's transactions stay out of the lists and the spending. Changed in the
  account's Edit, also for Monarch's accounts, and kept through the syncs.
- **Five groups**: the accounts are shown, added up and listed in the sidebar as Cash (bank accounts), Investments,
  Credit cards, Loans, and Assets (real estate, vehicles and other things of value). The sidebar lists them close
  together in a smaller type. **Rename** (the pencil by the account's name) works for Monarch's accounts too.
- **The net worth**: what the household owns less what it owes, now and day by day (a month, three, a year, five),
  by kind of account. An account or a holding in another currency is converted at the day's rate.
- **Transactions**: one row each (date, payee, notes, category or where a transfer went, account, amount; on a phone the
  category goes under the payee; the bank's own text as a column of its own with "At the bank column", remembered in
  the browser), searched by words, account, category, month, direction and amount (money out or in alike: 280
  exactly, 100-200, >500 or <20, in the Amount box or in the search as $280, 12.50 or 100-200; a bare number there
  is the amount or words that have it, such as an account's last digits); a category, a payee,
  notes or hidden changed here stays as changed through later syncs (Monarch itself is not changed). A
  transaction hidden in Monarch ("Hide from reports", often a duplicate) is not brought in at all, and the sync
  removes it here when it was (Sync two years again cleans the past two years). Whether Monarch calls a
  transaction pending is not kept (it says so of payments the bank took weeks ago): every transaction it sends counts
  alike. Each sync looks 45 days back, so one Monarch sends again under a new id (a card's hold that posted) does
  not stay here beside the new one. One hidden here, by a rule or by hand,
  is left out of the lists, the sums and the transfer matching; the list shows those, dimmed, with "With the hidden".
- **Transfers**: money that leaves one of the household's accounts and arrives in another (to savings, a card's payment,
  a loan's payment) is one transfer: its two halves are linked, shown as "To Savings" / "From Checking", and left out
  of the spending and the cash flow. Two transactions are linked when they are the same amount out and in, in two
  accounts, at most seven days apart, and something says it is a transfer: the payee or the bank's text names the
  other account (its name, its bank, or its last digits as in "PAYMENT TO *2530"), the category of either half is a
  transfer or a card's payment, or the text reads like one ("Payment - thank you", "autopay", "online transfer", "ACH",
  "loan", "mortgage"); money from a bank account into a card or a loan counts for more. Each transaction goes with one
  other at most, the best and nearest pairs first, so the same payment every month pairs with its own; when two
  candidates are equally good and would link different accounts, neither is taken (two payments of the same amount
  between the same two accounts pair up either way). A transfer rule (in this account, a payee like this is a transfer
  with that account, up to N days apart) weighs most; a transfer whose text names the other account teaches one
  (Learned, ten days, from the bank's text without its dates and numbers).
  A transaction's dialog links one by hand among the candidates, or unlinks it (never linked again by itself); the
  Rules page lists, adds and changes the transfer rules. **Link transfers** (the maintenance in Settings › Money, and
  on the Rules page) goes through every transaction, links what it can, and then opens **Transfers to check**
  (#/transfers), a full-width page of what still looks like a transfer (the same amount out of one account and into
  another within two weeks): both sides in full (account, day, category, payee and the bank's text), how many days
  apart and why it was not linked (as likely as another, nothing says it is a transfer, too many days apart), with
  **Link** and **Not a transfer** (off the list for good), a search, and filters by account and reason. Pairs that
  share a transaction are shown together as one choice, and two identical transactions on one side are pointed out
  as a likely duplicate.
- **Split**: a transaction can be split over categories (a warehouse club's bill: groceries, clothes, a gift), from
  its dialog: two parts and more, each with its share, a category and a note, together the whole amount. The
  transaction stays one line in its account; the spending by category counts its parts, a search by category or by a
  note's words finds it, and the list shows its categories with a split mark. If its amount changes later, what the
  parts no longer cover counts under its own category. `PUT /api/transactions/{id}/splits`; MCP `split_transaction`.
- **Receipts**: a transaction keeps its receipts: pictures (JPEG, PNG, WebP, GIF, HEIC) and PDFs, up to 20 MB each
  and 20 for one transaction, added from its dialog (picked, taken with the phone's camera, or dropped on it). A
  large photo is made smaller in the browser before it is sent. They are kept in the database (`mny_receipts`), so
  the suite's backup holds them; whoever sees the transaction sees them, whoever may change it adds and removes
  them. The list marks a transaction that has one and filters on it (`receipt=yes|no`). A receipt goes with its
  transaction; when Monarch gives a transaction a new id (a card's hold that posted), the sync moves its receipts, its links,
  its split and that it was looked at to the new one (same account, within ten days, the same amount, or the same payee and nearly the
  amount). `POST /api/transactions/{id}/receipts` (the file as the body), `GET`, `DELETE /api/receipts/{id}`.
- **Linked to a thing**: a transaction can be linked to the items of the other apps (the suite's linked items, kind
  `transaction`): the thing it paid for in ioThings, so the price sits beside the thing's warranty; a note, a
  contact, an event. The picker in the transaction's dialog opens on the things; in ioThings the thing lists the
  transaction, and a click opens it here (`#/transaction/{id}`).
- **Reconciled**: each transaction can be ticked as reconciled with the bank's statement (the tick at the end of its
  row, or its dialog); the list filters on it, and **Mark these reconciled** ticks every one shown. The sync leaves it
  as it is, and it does not count as a change to the transaction.
- **Bank details** on each account's page (from Monarch Money too): account and routing numbers, IBAN, SWIFT/BIC,
  customer service phone (and from abroad), website, email, sign-in name, opened on, mailing address and notes. The
  numbers show as •••• and their last four digits until shown, with a copy button; whoever sees the account sees
  them, whoever may change it changes them. They are kept apart from the account (mny_account_info), so no list,
  summary or MCP tool carries them; the MCP tool `bank_contact` gives the phone, website, email and address only.
- **Transactions by hand** in any account that follows its transactions, one from Monarch too (a cash payment, one
  the bank has not sent yet): kept through the syncs, and in an account kept by hand each one moves the balance (on a card or a
  loan, money out makes what is owed go up).
- **Tidy up**: one page for what keeps the transactions right, each with how much there is to do: the ones that need
  a look, likely duplicates, transfers to check, the balance check, the payees, the categories and tags, the rules,
  the recent changes, reconciling against a statement and importing a bank file. The sidebar shows how many need a look.
- **Many at once**: tick transactions in the list (or all shown) and give them a category, a payee or tags, hide or
  show them, or mark them reconciled, in one go (up to 2000). **Undo** in the note that follows takes it all back.
- **Needs a look**: the transactions that came in since the list was first opened and nobody looked at yet (what was
  there before counts as seen), and the ones without a category (not a split one or half of a transfer; not the
  hidden ones). Saving a change takes one off the list; so does its tick, **All looked at**, or the bar
  for the ones ticked. The Transactions page filters on it too.
- **Payees**: everyone the transactions were paid to or came from, with how many, how much, the last day and the
  category (and a mark when its transactions are in several). Editors rename a payee, give it the name of another to
  make the two one, and set its usual category (for those not changed by hand, or all of them). Each is kept as a
  rule, so what comes in later follows; a rule that looks at the payee is for the name a rule gave it too.
- **Tags**: a transaction has the household's own tags (trip, reimbursable, tax) beside the ones Monarch Money sends,
  which stay Monarch's. Typed in the transaction's dialog or given to many at once; the list filters on a tag, and
  the Categories page lists every tag with its count and total, where editors rename, merge and delete their own.
- **Likely duplicates**: transactions in one account, of the same amount, at most three days apart, that look like
  one kept twice (the same payee or bank's text; one added here and one from Monarch).
  Keep one and hide the other (one added here can be deleted), or say they are different: not shown again.
- **Reconcile with a statement** (an account's menu): the statement's first and last day and the balance at its start
  and its end; tick the transactions it shows (the hidden ones too; the earlier ones the statement before left open
  come first). When the ticked ones add up to what the balance moved by, **Finish** marks them reconciled and keeps
  the statement, so the next one starts where it ended. It can be finished with a difference, which is then kept with it.
  **Compare with the bank's file** does the ticking: give it the statement's PDF, or the CSV, OFX or QFX file from the
  bank's website. Its days and its two balances are filled in (a file without a balance: the account's balance on the
  day before plus the file's lines), each of its lines is looked for in the account (the same amount on the nearest
  day within five; which way the money went counts where the file says it, and a file that writes money out as a
  positive number is turned around), and what was found is ticked. What differs is listed: the lines the account
  does not have (**Add** one, or all of them; with the transaction of another amount that looks like it, when
  there is one), the lines it has under a day outside the statement, and the transactions of those
  days the bank does not show (marked in the list, left unticked). Nothing is finished until **Finish**; the file is
  read on the server and not kept. A PDF is read as text, in whatever form the bank laid it out: the days from "…
  through …", the balances after "beginning balance", "new balance" and their like, every line that starts with a
  date and holds an amount. A scanned statement (pictures of its pages) cannot be read, and a layout it does not
  make sense of reads short: when the lines read add up to the statement's two balances, the page says so.
- **Balance check**: for each cash account and card from Monarch Money with a bank behind it, whether its balance
  moved over the past 90 days by what its transactions add up to. Where it did not: by how much, whether money out or
  money in is missing (or kept twice), and between which days the gap appeared, with the way to that month's
  transactions. Every transaction counts, whatever Monarch calls it. Where the gap is exactly what some of the
  past week's transactions add up to (a card's purchase the bank's balance does not show yet), those are named and
  the account is not flagged. A day's balance may not hold that day's transactions yet, so the check
  starts up to three days earlier or later where its first week then agrees, and weeks whose gaps cancel out (a
  transaction dated a day off) are left out of where the gap appeared. A gap looked at can be accepted, and is
  flagged again once it changes.
- **Rules kept in order**: the Rules page says for each rule how many transactions of the past two years it is for
  and the last one, and marks a rule that matches nothing or that an earlier rule always decides before. When the
  same payee was given the same category by hand three times and more and no rule does it, the rule is offered
  (**Add the rule**, or **No thanks**: not offered again).
- **History and undo**: what a person changes on a transaction (payee, category, notes, tags, hidden; date and amount
  in an account kept by hand) is kept for 400 days with who and when. A transaction's dialog shows its history, each
  change with **Undo**; **Recent changes** lists them all, a change to many as one line. A transaction from Monarch
  Money that was changed here can go **Back to Monarch's own**: the next sync refreshes it and the rules apply again.
  What the rules and the syncs change is not kept.
- **Saved searches**: the filters of the Transactions page kept under a name (**Save this search**), for each person
  their own, listed above the filters and in the sidebar under Transactions. What is kept is the search, not what
  it found.
- **Import a bank file** into an account kept by hand (its menu): CSV, OFX or QFX. A CSV file's columns are found
  from their headings or their content (date, amount or money out and money in, payee, notes, category) and can be
  set by hand, as can the order of day and month and whether money out is written as a positive number. What the
  account has already is left out (the bank's own id in OFX; otherwise the same day and amount), unless asked. The
  rules apply, transfers are linked, and the balance moves by what came in, stays, or becomes the file's.
- **Recurring**: the bills, subscriptions and paychecks, found by ioMoney itself (Monarch's recurring transactions are
  not brought in) in the past two years: the same payee in the same account, money out or in, at least three times (a
  yearly one twice) at a steady pace (every week, two weeks, twice a month, monthly, every two months, every three
  months, every six months, yearly), the last one recent enough. A payee is known by its name or by the bank's text, so
  one Monarch renamed stays one (its recurring transaction remembers every name, "aes loan|aes student loans"); one
  payee's payments are split by amount, so two loans paid to the same bank are two; most of the gaps must be in the
  band and most of the amounts near the usual one, so a bonus, a late payment or a price change does not spoil it, and
  a utility whose amount swings is found as one that varies. A payment to a loan or an investment account (the car
  loan, the mortgage, a 529) counts even when linked as a transfer; a card's payment does not. What is found is offered on the Recurring page: **Add**, or **Not
  recurring** (not offered again); one is also added by hand (its name, the words its payee has, the account, the usual
  amount and whether it varies, how often, a day it falls on, a category), changed or removed. Editors change the
  household's; a member those of their own accounts. In the transaction list a recurring one has a small icon by its
  payee; **Make recurring** in a transaction's dialog opens one to add, its pace and usual amount taken from the
  transactions like it (or the one it already is).
- **Missed and changed**: a recurring transaction whose payment did not come for longer than its pace allows (a
  paycheck two days late, a monthly bill five) is flagged as missed; one whose latest payment had another amount (a
  fixed one off by more than a quarter or 1%, one that varies by more than a third; also a payment with its words,
  when one was due, between half and twice the amount) as changed. Flagged ones are listed first on the Recurring
  page (To check: Use the new amount, Dismiss, It stopped), counted in the sidebar and on the overview, and carry
  `flag` in the API and MCP. A flag goes when the next payment comes, the amount is updated or it is dismissed.
- **Cash forecast**: on a cash account's page, its balance over the next 30, 60 or 90 days from what is known to
  come: the recurring transactions kept for that account, and the transfers it makes at a steady pace (a card paid
  every month, money moved to savings; the middle amount of the last three), each on the days its pace gives from
  its last payment. One a few days late is expected today; one whose payment did not come is left out and named.
  With a lowest balance for the account (zero without one), the forecast says when it would go under it, there and
  on the overview. Everyday spending and the recurring transactions kept for any account are not counted.
  `GET /api/accounts/{id}/forecast`, `GET /api/forecast`; MCP `cash_forecast`.
- **Loan payoff**: on a loan's page, from its interest rate (percent a year) and monthly payment (given, or worked
  out from how the balance went down over the past three months plus a month's interest): when it is paid off, the
  interest still to pay, and what paying more a month saves (months and interest). Interest is counted by the month
  on what is owed. `GET /api/accounts/{id}/payoff?extra=`; MCP `loan_payoff`.
- **Subscriptions**: Netflix, Max, YouTube, Spotify, Disney+, iCloud, Amazon Prime and other services (or a category
  like Streaming or Subscriptions) are marked as subscriptions, found after two payments already; the Recurring page
  shows them in a section of their own with what they cost a month and a year. Any recurring one can be marked or
  unmarked by hand.
- **Categories**: every category by group, with how many transactions have it: add one, rename it (into one there is:
  merged), move it to another group, or delete it (its transactions moved to another category or left without one).
  The transactions, rules and recurring transactions follow, and so does what Monarch sends later under the old name
  (Monarch itself is not changed). Editors change them.
- **Rules**: the household's rules rename the payee, set the category or hide a transaction when the payee or the
  bank's own text contains, is or starts with some words (optionally only in one account, money out or in, between two
  amounts). They run over what each sync brings and over a transaction added by hand; **Apply now** runs them over the
  transactions there are. They are tried from the top, and for each of the three the first that matches wins. As a rule
  is typed, the transactions it matches are shown; **Make a rule** on a transaction starts one from it. A transaction
  changed by hand is left as it is. Everyone with a role sees them; editors change them.
- **Spending**: a month by category, and twelve months of money in and out (transfers between your own accounts are
  left out).
- **Portfolio**: every holding with its price, today's change, its value and its gain over what it cost, by account or
  by symbol, and the allocation. Quotes come from Yahoo Finance, without a key or an account: a symbol as Yahoo writes
  it (AAPL, VWCE.DE on Xetra, VOD.L in London, BTC-USD), asked at most every fifteen minutes and only for what somebody
  holds.
- **Assets**: the house and the cars, each with its value, its loan and the equity left, its details (address; year, make, model,
  mileage; what it cost), the values it had and the items of the other apps linked to it.
- **Who sees it**: only the people given a role in ioMoney; others are told they have none. Viewers read; members keep
  their own private accounts; editors and admins change the household's. Settings › Money (admins) has the
  household's currency and Monarch Money.
- **Bills in ioCalendar**: the recurring transactions show on the day they are due in ioCalendar (paid once a payment
  like it is a few days from it), to the people with a role in ioMoney (asked as them, so nobody else sees them).
- **Everywhere**: a REST API with OpenAPI docs at `/api/docs`, and an MCP server for AI assistants.

## Monarch Money's sign-in

The sign-in is kept with the suite's keys and tokens (**Settings › Global settings › Keys and tokens**, ioMoney, suite
admins), never in a config file:

| Key | What it is |
| --- | --- |
| `monarch_email`, `monarch_password` | how you sign in to Monarch Money |
| `monarch_mfa_secret` | the authenticator key: the text under the QR code Monarch shows when you set up an authenticator app (Monarch › Settings › Security). With it ioMoney makes the six-digit code itself, as your authenticator app does |
| `monarch_token` | the session Monarch gives on sign-in, kept by ioMoney: later syncs use it and sign in again only when Monarch no longer takes it |

Without an authenticator key, Settings › Money takes the code your authenticator app shows, once. When Monarch refuses
the sign-in (it can ask for a CAPTCHA), the sync says so in Settings › Money; sign in at monarch.com from the same
network, then Sync now.

## Run

ioMoney needs Python 3.10+ and a MariaDB or MySQL database. Give it its own database and user, for example:

```sql
CREATE DATABASE iomoney CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'iomoney'@'app-host' IDENTIFIED BY 'a-long-random-password';
GRANT ALL ON iomoney.* TO 'iomoney'@'app-host';
```

`app-host` is the machine the app runs on (`localhost` when MariaDB is on the same machine). The accounts and the
suite-wide settings live in the Shared ioSuite database (`iosuite`, user `iosuite`; the one every app of the suite
uses). The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iomoney/proxmox/ct/iomoney.sh)"
```

It asks for the money database, the Shared ioSuite database, the web port (8710), the time zone, the public address
(optional), the domain the sign-in is shared on (optional) and the admin account, and which other apps of the suite go
in the same container; then the framework's own questions. For unattended runs set `IOMONEY_DB` and `IOMONEY_SUITE_DB`
(`host:port/db:user:password`), `IOMONEY_ADMIN` (`name:password`), `IOMONEY_PORT`, `IOMONEY_TIMEZONE`,
`IOMONEY_PUBLIC_URL` and `IOMONEY_COOKIE_DOMAIN`.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iosuite/iomoney`) holds no data: everything is in the database.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite/iomoney
./setup.sh          # asks for the databases, port, time zone and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

Its last step is the list of the suite's apps on this machine, to add or remove others beside ioMoney (the
[one-line installer](../README.md#install) does the same from anywhere). `setup.sh` takes the same flags as every app
of the suite (`--db`, `--suite-db`, `--db-admin`, `--admin`, `--port`, `--public-url`, `--cookie-domain`, `--service`,
`--also`, `--yes`). From a shell: `python -m app.cli sync` (`--full`: two years of transactions again), `quotes` and
`check`.

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment,
which wins:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database (`iomoney`) |
| `IOSUITE_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the Shared ioSuite database (`iosuite`, on `DB_HOST` unless set) |
| `COOKIE_DOMAIN` | the domain the session cookie is shared on (`example.com`) |
| `HOST`, `PORT` | where the server listens (all addresses, 8710) |
| `TLS_CERT_FILE`, `TLS_KEY_FILE` | serve HTTPS directly instead of behind a reverse proxy |
| `TZ` | the time zone the server log is written in |
| `PUBLIC_URL` | the address people use (behind a proxy), for the links the MCP tools give |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `SYNC` | `0`: no Monarch sync and no quotes in the background (Sync now and Quotes still work) |
| `MCP` | `1` keeps the MCP server on, whatever the setting says |
| `MCP_USER` | the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `DATA_DIR`, `LOG_FILE` | where the app writes on its own (`data/`), and the server log (`DATA_DIR/iomoney.log`) |

Updates, releases, the reverse proxy and Cloudflare Access work as in every app of the suite (see
[ioRecipe's README](../iorecipe/README.md#updates)).

## API

| For | Where |
| --- | --- |
| The net worth now and day by day, by kind | `GET /api/summary`, `GET /api/networth?days=365` |
| Accounts: list, one, add, change, delete (by hand), history, values | `/api/accounts`, `/api/accounts/{id}`, `/api/accounts/{id}/history`, `/api/accounts/{id}/values` |
| An account's bank details: read, change (the fields given; empty removes) | `GET`, `PUT /api/accounts/{id}/info` |
| Transactions: search, add (by hand), change, delete | `GET /api/transactions?q=&account=&category=&month=&flow=&amount=`, `POST /api/accounts/{id}/transactions`, `/api/transactions/{id}` |
| Spending and cash flow | `GET /api/spending?month=2026-11`, `GET /api/cashflow?months=12`, `GET /api/categories` |
| Transfers: one transaction's other half and candidates, link, unlink; link all; what is left | `GET/PUT/DELETE /api/transactions/{id}/transfer`, `POST /api/transfers/link`, `GET /api/transfers/possible` |
| One transaction | `GET /api/transactions/{id}` |
| Receipts: add (the file as the request body), open, remove; filter | `POST /api/transactions/{id}/receipts?name=`, `GET`, `DELETE /api/receipts/{id}`, `GET /api/transactions?receipt=yes\|no` |
| Reconciled: filter, mark | `GET /api/transactions?reconciled=yes\|no`, `PATCH /api/transactions/{id}` (`reconciled`), `POST /api/transactions/reconcile` (`{ids, reconciled}`) |
| Not a transfer (off the list to check, never linked by itself) | `POST /api/transfers/not` (`{outId, inId}`) |
| Transfer rules: list, add, change, delete | `/api/transfer-rules`, `/api/transfer-rules/{id}` |
| Rules: list, add, try, apply, order, change, delete | `/api/rules`, `POST /api/rules/test`, `POST /api/rules/apply`, `PUT /api/rules/order`, `/api/rules/{id}` |
| The portfolio and quotes | `GET /api/portfolio`, `POST /api/accounts/{id}/holdings`, `/api/holdings/{id}`, `GET /api/quotes/{symbol}`, `POST /api/quotes/refresh` |
| Recurring: list and found, add (or add what was found), not recurring, change, remove | `GET`, `POST /api/recurring` (`{found: key}` or the fields), `POST /api/recurring/not` (`{key}`), `PATCH`, `DELETE /api/recurring/{id}` |
| One transaction's recurring one, or one to add from it | `GET /api/transactions/{id}/recurring` |
| Bills: each date a recurring transaction falls on, paid or not | `GET /api/bills?start=&end=` |
| Categories: list, add, rename / merge / regroup, delete | `GET`, `POST`, `PUT /api/categories` (`{name, newName?, group?}`), `POST /api/categories/delete` (`{name, moveTo?}`) |
| Monarch Money (admins) | `GET /api/monarch` (with the running sync's progress), `POST /api/monarch/sync` (`{full, accountId, years, wait}`), `POST /api/monarch/code`, `DELETE /api/monarch/session` |
| Accounts Monarch reports as new (admins) | `GET /api/monarch/new`, `POST /api/monarch/new/{monarch id}` (`{as: "new"}` or `{as: "existing", accountId}`) |
| Many at once (`set`: category, merchant, notes, hidden, reconciled, reviewed, addTags, removeTags) | `POST /api/transactions/bulk` (`{ids, set}`) |
| Needs a look: filter, mark (`{all: true}`: every one) | `GET /api/transactions?review=yes`, `POST /api/transactions/review` (`{ids, reviewed}`) |
| What there is to tidy up, in numbers | `GET /api/tidy` |
| Payees: list, rename or merge, usual category | `GET /api/payees?q=`, `POST /api/payees/rename` (`{name, newName}`), `POST /api/payees/category` (`{name, category, all?}`) |
| Tags: list, filter, set on a transaction, rename or merge, delete | `GET /api/tags`, `GET /api/transactions?tag=`, `PATCH /api/transactions/{id}` (`tags`), `PUT /api/tags` (`{name, newName}`), `POST /api/tags/delete` (`{name}`) |
| Likely duplicates: list, not duplicates | `GET /api/duplicates`, `POST /api/duplicates/not` (`{ids}`) |
| Statements: list and where the next starts, the lines to tick, finish, forget | `GET /api/accounts/{id}/statements`, `GET /api/accounts/{id}/statement?start=&end=`, `POST /api/accounts/{id}/statements` (`{start, end, opening, closing, ids, anyway?}`), `DELETE /api/statements/{id}` |
| The bank's file held against the account (the PDF, CSV, OFX or QFX file as the request body, up to 20 MB; nothing changed or kept) | `POST /api/accounts/{id}/statement/read?name=&order=&flip=` → `{kind, start, end, opening, closing, worked, adds, total, sum, matched, missing, elsewhere, extra, dateOrder, guessed, flipped}` |
| The balance check; accept a gap (`{gap: null}`: flag it again) | `GET /api/balance-check?days=90`, `POST /api/balance-check/{id}/ok` (`{gap}`) |
| What each rule does, suggested rules; not this one | `GET /api/rules/upkeep`, `POST /api/rules/suggestions/not` (`{key}`) |
| History: of a transaction, recent, undo, back to Monarch's own | `GET /api/transactions/{id}/changes`, `GET /api/changes`, `POST /api/changes/undo` (`{id}` or `{batch}`), `POST /api/transactions/{id}/reset` |
| Saved searches (your own): list, keep, change, forget | `GET`, `POST /api/searches` (`{name, query}`), `PATCH`, `DELETE /api/searches/{id}` |
| Import a bank file (`preview: true` adds nothing) | `POST /api/accounts/{id}/import` (`{text, name?, mapping?, dateOrder?, flip?, duplicates?, balance?, preview?}`) |
| The household's currency, the automatic sync | `GET /api/settings`, `PUT /api/settings` (admins) |

Amounts are signed as Monarch signs them: money out is negative. Settings › Account makes **app passwords** for the
REST API (HTTP Basic, or `Authorization: Bearer <app password>`) and for MCP.

```sh
curl -u alex:APP-PASSWORD "https://money.example.com/api/networth?days=90"
curl -u alex:APP-PASSWORD "https://money.example.com/api/transactions?q=grocer&month=2026-11"
curl -u alex:APP-PASSWORD -X PATCH -H 'Content-Type: application/json' -d '{"category": "Party", "notes": "birthday"}' https://money.example.com/api/transactions/812
```

## MCP server

Off until an admin turns it on in **Settings › Server**. The tools: `overview`, `net_worth_history`,
`search_transactions` (by tag and needing a look too), `data_checks`, `payees`, `bank_contact`, `spending`, `cash_flow`, `categories`, `update_transaction` (its tags and reviewed too), `add_transaction`, `rules`, `add_rule`,
`test_rule`, `update_rule`, `delete_rule`, `apply_rules`, `link_transfers`, `possible_transfers`, `link_transaction`, `unlink_transaction`,
`transfer_rules`, `add_transfer_rule`, `delete_transfer_rule`, `portfolio`,
`get_quote`, `add_holding`, `update_holding`, `delete_holding`, `add_account`, `update_account`, `add_valuation`,
`bills`, `recurring_transactions`, `sync_monarch`; and for admins `diagnostics`, `monarch_new_accounts`, `resolve_new_account`.

```sh
claude mcp add --transport http iomoney https://money.example.com/mcp --header "Authorization: Bearer APP-PASSWORD"
```

## Tests

```sh
pip install -e '.[test]'
python -m pytest tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: roles (none, viewer, member, editor), private and household accounts, the net worth and its history,
accounts followed by their value or their transactions and the five groups, transactions and their search, rules (tried,
kept, ordered, applied, run by the sync), transfers (found by a named payee, a transfer category or a payment's payee, a card's and a loan's
payment, not without evidence, a tie left for a person, learned and typed rules, unlinked for good, linked by hand, the
maintenance's list of what is left and why), reconciled (marked, filtered, in bulk, not by a viewer), bank details (kept, changed, removed, not in the account
or by a viewer), spending and cash flow without transfers, the portfolio with a holding in another
currency, a house's estimate and its equity after the mortgage, recurring transactions (found, added, not recurring, by hand,
whose they are) and subscriptions, the bills, transactions by hand in a Monarch account, categories (renamed, merged,
deleted, with their rules and what a sync brings later), the Monarch sync against a stand-in for the
library (first sync, later syncs keeping local changes, a session Monarch no longer takes, a wrong sign-in, a code by
hand, an account made again in Monarch matched with its transactions none twice, a new one held until said), the MCP server and a person's data deleted;
and putting the data in order: many transactions changed at once and taken back, needing a look, the payees (renamed,
merged, their category), own tags, likely duplicates, a statement reconciled, the balance check, what each rule does
and the rules suggested, a transaction's history and back to Monarch's own, saved searches, and a bank file imported
(CSV and OFX, what is there already left out); and the bank's file held against an account (`test_statementfile.py`):
a statement's text read in three made-up layouts, a PDF built in the test, a CSV with and without a balance, a card's
file turned around, an OFX file, and what comes back (found, missing, of another amount, outside the days, not shown).

## Layout

```
app/main.py        the application: start-up, the background chores (Monarch sync, quotes, estimates), routes
app/api.py         the REST API
app/model.py       accounts, balances, transactions and holdings in MariaDB: who sees and changes what, the sums
app/monarch.py     Monarch Money: the sign-in (from the suite's keys and tokens) and the sync, accounts it reports as new
app/recurring.py   recurring transactions and subscriptions: found in the transactions, the household's list, the bills' dates
app/categories.py  the categories: added, renamed, merged, regrouped, deleted, and what a sync brings later under the old name
app/transfers.py   transfers between the household's own accounts: found, linked, unlinked, and their rules
app/forecast.py    the cash forecast of an account: what is known to come, day by day
app/payoff.py      a loan's payoff from its rate and its payment
app/splits.py      a transaction split over categories
app/review.py      needs a look: the transactions nobody looked at yet
app/payees.py      the payees: counted, renamed, merged, their usual category
app/tags.py        the household's own tags on transactions, beside Monarch's
app/duplicates.py  likely duplicates: the same transaction kept twice
app/statements.py  an account reconciled against the bank's statement
app/statementfile.py  the bank's file (PDF, CSV, OFX, QFX) held against the account: what to tick, what differs
app/statementpdf.py   a statement's PDF read: its days, its two balances, its lines
app/balancecheck.py  whether an account's balance agrees with its transactions
app/rulecheck.py   what each rule does, the ones that do nothing, the rules missing
app/history.py     what was changed by hand on a transaction, and the way back
app/searches.py    a person's saved searches of the transactions
app/importer.py    a bank's file (CSV, OFX, QFX) into an account kept by hand
app/receipts.py    the receipts kept with a transaction, and what follows a transaction to its new id
app/quotes.py      quotes and exchange rates from Yahoo Finance
app/persondata.py  what a person keeps here, for the suite's delete-a-person
app/mcp/           the MCP server: money and admin tools
static/            the web app (index.html, app.js, app.css, icons)
proxmox/           the community-scripts LXC installer      setup.sh, run.sh, update.sh, Dockerfile
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later).
