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
  removes it here when it was (Sync two years again cleans the past two years). A pending one is asked about again on
  every sync until it posts (up to four months back), so it does not stay pending here, nor stay beside the posted one
  Monarch sends under a new id. One hidden here, by a rule or by hand,
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
- **Reconciled**: each transaction can be ticked as reconciled with the bank's statement (the tick at the end of its
  row, or its dialog); the list filters on it, and **Mark these reconciled** ticks every one shown. The sync leaves it
  as it is, and it does not count as a change to the transaction.
- **Bank details** on each account's page (from Monarch Money too): account and routing numbers, IBAN, SWIFT/BIC,
  customer service phone (and from abroad), website, email, sign-in name, opened on, mailing address and notes. The
  numbers show as •••• and their last four digits until shown, with a copy button; whoever sees the account sees
  them, whoever may change it changes them. They are kept apart from the account (mny_account_info), so no list,
  summary or MCP tool carries them; the MCP tool `bank_contact` gives the phone, website, email and address only.
- **Transactions by hand** in any account that follows its transactions, one from Monarch too (a cash payment, one
  the bank has not sent yet): kept through the syncs, and in an account kept by hand each one moves the balance.
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
`search_transactions`, `bank_contact`, `spending`, `cash_flow`, `categories`, `update_transaction`, `add_transaction`, `rules`, `add_rule`,
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
hand, an account made again in Monarch matched with its transactions none twice, a new one held until said), the MCP server and a person's data deleted.

## Layout

```
app/main.py        the application: start-up, the background chores (Monarch sync, quotes, estimates), routes
app/api.py         the REST API
app/model.py       accounts, balances, transactions and holdings in MariaDB: who sees and changes what, the sums
app/monarch.py     Monarch Money: the sign-in (from the suite's keys and tokens) and the sync, accounts it reports as new
app/recurring.py   recurring transactions and subscriptions: found in the transactions, the household's list, the bills' dates
app/categories.py  the categories: added, renamed, merged, regrouped, deleted, and what a sync brings later under the old name
app/transfers.py   transfers between the household's own accounts: found, linked, unlinked, and their rules
app/quotes.py      quotes and exchange rates from Yahoo Finance
app/persondata.py  what a person keeps here, for the suite's delete-a-person
app/mcp/           the MCP server: money and admin tools
static/            the web app (index.html, app.js, app.css, icons)
proxmox/           the community-scripts LXC installer      setup.sh, run.sh, update.sh, Dockerfile
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later).
