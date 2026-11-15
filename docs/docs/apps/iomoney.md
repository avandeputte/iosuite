---
description: ioMoney, the household's finances in the ioThing suite.
---

# ioMoney <small>household finances</small>

The household's money in one place: the accounts and transactions copied in from Monarch Money, a portfolio with its
quotes, and what the house and the cars are worth after their loans.

## What it does

- **Monarch Money**: every account Monarch has (bank accounts, credit cards, investments, loans, the house it values
  from Zillow, the cars) with its balance history, two years of transactions, the holdings and the coming bills,
  copied in every six hours. ioMoney only reads: nothing is changed in Monarch. A sync runs in the background and the
  page shows how far it is (the first one, with two years of transactions, takes minutes).
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
- **Transactions** to search and correct, one row each (date, payee, notes, category, amount): a category, a payee or a
  note changed here stays through later syncs.
- **Transfers** between your own accounts (to savings, a card's payment, a loan's payment) are linked: the two halves
  have the same amount, are a few days apart, and the payee or category says so. Each transfer found teaches a rule,
  so the next is found even later; link or unlink one by hand, and add or change transfer rules on the Rules page.
  **Link transfers** in Settings › Money goes through every transaction (card payments, bank transfers, loan
  payments), then lists what still looks like a transfer, with why it was not linked, to link in one click.
- **Reconciled**: tick each transaction as checked against the bank's statement, filter on it, or tick every one shown.
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
- **ioCalendar**: the coming bills from Monarch Money show on the day they are due, to the people with a role in ioMoney.
- **Linked items**: link the house or a car to the events, tasks, notes, contacts and photos about it.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iomoney/proxmox/ct/iomoney.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iomoney/docker-compose.yml): the image `ghcr.io/avandeputte/iosuite/iomoney` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iosuite && cd iosuite/iomoney && ./setup.sh` |
| Port | 8710 |
| Source | [iosuite/iomoney](https://github.com/avandeputte/iosuite/tree/main/iomoney) |
