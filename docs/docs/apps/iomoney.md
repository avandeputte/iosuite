---
description: ioMoney, the household's finances in the ioThing suite.
---

# ioMoney <small>household finances</small>

The household's money in one place: the accounts and transactions copied in from Monarch Money, a portfolio with its
quotes, and what the house and the cars are worth after their loans.

[The ioMoney page on the website, with more screenshots →](https://iosuite.iothing.net/ioMoney/)
{ .md-button }

![ioMoney's overview: net worth over the year, and every account by group](../img/iomoney.jpg)

## What it does

- **Monarch Money**: every account Monarch has (bank accounts, credit cards, investments, loans, the house it values
  from Zillow, the cars) with its balance history, two years of transactions and the holdings,
  copied in every six hours. ioMoney only reads: nothing is changed in Monarch. A sync runs in the background and the
  page shows how far it is (the first one, with two years of transactions, takes minutes).
- **Missed a paycheck, or a price went up?** A recurring transaction whose payment did not come when its pace says
  it should have, or whose latest payment had another amount, is flagged: on the overview, in the sidebar and first
  on the Recurring page, where you take the new amount, dismiss the flag or remove what stopped.
- **Cash forecast**: each cash account shows where its balance goes over the coming weeks, from the bills,
  subscriptions and paychecks kept for it and the transfers it makes regularly (the card's payment). Set a lowest
  balance and ioMoney warns, on the account and the overview, when it would go under it.
- **Loan payoff**: give a loan its interest rate (and its monthly payment, or let ioMoney work it out from the
  balance) and its page shows when it is paid off, the interest still to pay, and what paying a little more each
  month would save.
- **A bank link behind?** When Monarch has not heard from an account's bank in more than two days, or says the
  link was cut or the bank sign-in needs fixing, ioMoney flags the account (on the overview, in the sidebar and on its
  page) so you can check its connection in Monarch. An account that rarely changes can be left out from its menu
  (Don't flag its bank link).
- **A new account in Monarch?** When Monarch reports an account ioMoney does not know, ioMoney asks whether it is new
  or an account you have that was deleted and made again in Monarch (often needed when a bank's link breaks), with the
  likeliest one picked. An existing one keeps its name and history, and its transactions are matched, so none is there
  twice and your changes stay.
- **Accounts by hand** beside Monarch's, for what Monarch does not have: a savings account, an investment account with
  what it holds, a car with its value. A house or a car can follow a yearly change between the values you give it.
- **Its value only, or its transactions**, for each account: a bank account or a card usually follows its
  transactions (in an account kept by hand, each one moves the balance); a savings account elsewhere can follow just its
  balance, typed in now and then, with its transactions out of the way.
- **Five groups**: Cash, Investments, Credit cards, Loans and Assets (real estate, vehicles), in a compact list in the
  sidebar. Rename any account (one from Monarch too) with the pencil by its name.
- **The net worth**, now and over a month, three, a year or five, by kind of account.
- **Transactions** to search (words, or an amount: 280 exactly or 100-200) and correct, one row each (date, payee,
  notes, category, amount, and the bank's own text if you turn that column on): a category, a payee or a
  note changed here stays through later syncs. What is hidden in Monarch ("Hide from reports") is not brought in;
  what is hidden here is left out of the list unless it is set to show them.
- **Transfers** between your own accounts (to savings, a card's payment, a loan's payment) are linked: the two halves
  have the same amount, are a few days apart, and the payee, the bank's text (the other account's name, bank or last
  digits) or the category says so; each pairs with the nearest of its kind. A transfer that names the other account
  teaches a rule, so the next is found even later; link or unlink one by hand, and add or change transfer rules on the Rules page.
  **Link transfers** in Settings › Money goes through every transaction (card payments, bank transfers, loan
  payments), then opens Transfers to check, a full-width page of what still looks like a transfer, both sides in full, with
  why it was not linked: Link, or Not a transfer; ties are grouped and likely duplicates pointed out.
- **Transactions by hand** in any account that follows its transactions, one from Monarch too: a cash payment, or one
  the bank has not sent yet.
- **Recurring**: ioMoney finds the bills and paychecks itself in the past two years (the same payee at a steady pace,
  every week to every year; a bonus, a renamed payee or a price change does not throw it off, and two loans at the same
  bank are two, loan payments included) and offers them: add the ones that are, say "Not recurring" to the others, or add
  one by hand, or choose **Make recurring** on a transaction. Each shows when it is next due and the last payment, and
  the transaction list marks the ones that are recurring.
- **Subscriptions**: Netflix, Max, YouTube, Spotify, Disney+, iCloud, Amazon Prime and other services get a section of
  their own on the Recurring page, with what they cost a month and a year.
- **Categories**: add, rename, merge, move to another group or delete a category; its transactions and rules follow,
  and so does what Monarch sends later under the old name.
- **Split a transaction** over several categories (one big-store bill: groceries, clothes, a gift): open it, choose
  Split over categories and give each part its share. The spending by category then counts the parts.
- **Receipts**: keep the receipt with its transaction. Open the transaction and add a picture (on a phone, take it
  with the camera) or a PDF, up to 20 MB each. The list marks the transactions that have one, and can show only those
  with or without. Whoever sees the transaction sees its receipts. A receipt is deleted with its transaction; when
  a pending transaction posts, its receipts move to the posted one.
- **Reconciled**: tick each transaction as checked against the bank's statement, filter on it, or tick every one shown.
- **Bank details** on each account: account and routing numbers (hidden until shown, with copy), IBAN, customer
  service phone, website, address and notes, to have at hand. AI assistants only get the phone, website and address.
- **Rules** that rename the payee, set the category or hide a transaction when its payee or the bank's text matches,
  run on every sync; you see what a rule matches as you type it, and can start one from a transaction.
- **Spending** by category for a month, and money in and out over twelve months, without the transfers between your
  own accounts.
- **Portfolio**: each holding's price, today's change, value and gain, with quotes from Yahoo Finance (no key needed).
- **Assets**: the house and the cars, with the value, the loan and the equity left, the details and the values over the years.
- **Any currency**: an account or a holding in another currency is converted at the day's rate.
- **Who sees it**: only the people given a role in ioMoney. Members keep private accounts of their own; editors change
  the household's.
- **Everywhere**: a REST API with OpenAPI docs at `/api/docs`, and an MCP server for AI assistants.

## Monarch Money's sign-in

The Monarch email, password and authenticator key go in **Settings › Global settings › Keys and tokens** (suite
admins), with the rest of the suite's keys: never in a config file. The authenticator key is the text under the QR code
Monarch shows when you set up an authenticator app; with it ioMoney makes the six-digit code itself. Settings › Money
shows what is set, the last syncs and **Sync now**.

## On its own

ioMoney needs its database and the Shared ioSuite database, and nothing else. Without Monarch Money it is a net worth
and portfolio tracker for accounts you keep by hand.

## With the other apps

- **ioStart**: a tile on the start page, and one sign-in for all the apps.
- **ioCalendar**: the recurring bills and paychecks show on the day they are due (ticked once paid), to the people with a role in ioMoney.
- **Linked items**: link the house or a car to the events, tasks, notes, contacts and photos about it.
- **ioThings**: link a transaction to the thing it paid for. The transaction then shows the thing with its warranty,
  and the thing shows what was paid, when and from which account. Open the transaction, choose Link and find the thing.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iomoney/proxmox/ct/iomoney.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iomoney/docker-compose.yml): the image `ghcr.io/avandeputte/iosuite/iomoney` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iosuite && cd iosuite/iomoney && ./setup.sh` |
| Port | 8710 |
| Source | [iosuite/iomoney](https://github.com/avandeputte/iosuite/tree/main/iomoney) |
