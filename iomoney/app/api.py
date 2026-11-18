"""The REST API (JSON) the web app uses. OpenAPI docs at /api/docs. Who may call a route is declared on it
(app/access.py); what an account may see and change is the account's business (app/model.py): nobody without a role
in ioMoney gets anything but empty lists.

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`.
"""
import datetime as dt
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from iosuite_shared import users as shared_users
from iosuite_shared.access import json_body
from iosuite_shared.errors import Invalid

from app import (access, balancecheck, categories, db, duplicates, forecast, history, importer, model, monarch, payees, payoff,
                 quotes, receipts, recurring, review, rulecheck, searches, splits, statementfile, statements, tags, transfers)

router = APIRouter()


def _u(request: Request) -> dict:
    return request.state.user


def _month_bounds(month: str | None) -> tuple[dt.date, dt.date]:
    today = dt.date.today()
    if month:
        try:
            y, m = (int(x) for x in month.split("-")[:2])
            first = dt.date(y, m, 1)
        except (ValueError, TypeError):
            raise Invalid("month: YYYY-MM")
    else:
        first = today.replace(day=1)
    nxt = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return first, nxt - dt.timedelta(days=1)


# ------------------------------------------------------------------ around everything

@router.get("/api/summary", dependencies=[access.signed_in])
def summary(request: Request):
    """What the pages need around them: the net worth now, how many accounts, transactions and holdings this person
    sees, the household's currency, the kinds of accounts, whether Monarch Money is set up (with the accounts whose link to
    the bank it reports as broken or more than two days behind: monarch.stale), how many transactions need a look
    (review), and what this person may do."""
    u = _u(request)
    return {"netWorth": model.net_worth(u), "counts": model.counts(u), "currency": model.home_currency(),
            "kinds": [{"kind": k, "label": v[0], "isAsset": v[1], "group": model.GROUP_OF.get(k, "asset"),
                       "track": model.TRACK_DEFAULT.get(k, "value")} for k, v in model.KINDS.items()],
            "groups": [{"group": g, "label": name, "kinds": list(kinds)} for g, name, kinds in model.GROUPS],
            "holdingKinds": list(model.HOLDING_KINDS),
            "monarch": {"configured": monarch.configured(), "lastGood": monarch.status()["lastGood"], "running": monarch.running(),
                        "newAccounts": monarch.held_count() if model.is_admin(u) else 0,
                        "stale": model.stale_accounts(u)} if model.role_rank(u) else None,
            "recurringFlags": len(recurring.flags(u)), "review": review.count(u),
            "may": {"read": model.role_rank(u) >= 1, "own": model.may_add(u, False), "household": model.may_add(u, True),
                    "admin": model.is_admin(u)}}


# ------------------------------------------------------------------ accounts

@router.get("/api/accounts", dependencies=[access.signed_in])
def list_accounts(request: Request, hidden: bool = False, kind: str = None, q: str = "", things: bool = False, limit: int = 500):
    """The accounts you see, the house and the cars among them. hidden: also the hidden ones; kind: one kind;
    things: only what has a value (real estate, vehicles, other assets); q: words in the name or the institution."""
    u = _u(request)
    rows = model.accounts(u, hidden=hidden, kind=kind)
    if things:
        rows = [a for a in rows if a["kind"] in model.THINGS]
    for w in q.lower().split():
        rows = [a for a in rows if w in f"{a['name']} {a['institution'] or ''} {a['subtype'] or ''}".lower()]
    rows = rows[:max(1, min(limit, 1000))]
    links = model.bank_links([a["id"] for a in rows if a["source"] == "monarch"])
    return {"items": [model.account_public(a, u, links=links) for a in rows]}


@router.post("/api/accounts", dependencies=[access.signed_in])
async def add_account(request: Request):
    """{name, kind (cash, investment, property, vehicle, other_asset, credit, loan, other_liability), balance?,
    currency?, institution?, subtype?, mask?, inNetWorth?, hidden?, details? (a house or a car: address, year, make,
    model, vin, mileage, boughtOn, boughtFor, yearlyRate, notes), loanId?, household? (true: the household's, editors;
    false: your own)}."""
    u = _u(request)
    b = await json_body(request)
    a = await run_in_threadpool(model.create_account, u, b)
    return JSONResponse(model.account_public(a, u), status_code=201)


@router.get("/api/accounts/{aid}", dependencies=[access.signed_in])
def get_account(aid: int, request: Request):
    u = _u(request)
    return model.account_public(model.account(u, aid), u)


@router.patch("/api/accounts/{aid}", dependencies=[access.signed_in])
async def change_account(aid: int, request: Request):
    """Change the fields given (as POST /api/accounts). An account from Monarch Money takes only its name, hidden, in
    the net worth, the details, the loan, household and flagStale (false: do not flag its link to the bank as behind)."""
    u = _u(request)
    b = await json_body(request)
    a = await run_in_threadpool(lambda: model.update_account(u, model.account(u, aid), b))
    return model.account_public(a, u)


@router.delete("/api/accounts/{aid}", dependencies=[access.signed_in])
def delete_account(aid: int, request: Request):
    u = _u(request)
    model.delete_account(u, model.account(u, aid))
    return {"ok": True}


@router.get("/api/accounts/{aid}/info", dependencies=[access.signed_in])
def get_account_info(aid: int, request: Request):
    """What is kept to deal with the account's bank: accountNumber, routingNumber, iban, swift, phone, phoneAbroad,
    website, email, address, username, openedOn, notes (those set only)."""
    u = _u(request)
    return model.account_info(u, model.account(u, aid))


@router.put("/api/accounts/{aid}/info", dependencies=[access.signed_in])
async def put_account_info(aid: int, request: Request):
    """Change the fields given (an empty one is removed); for whoever may change the account."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(lambda: model.set_account_info(u, model.account(u, aid), b))


@router.get("/api/accounts/{aid}/forecast", dependencies=[access.signed_in])
def account_forecast(aid: int, request: Request, days: int = forecast.DAYS):
    """The account's balance over the coming days (7 to 366), from its recurring transactions and the transfers it
    makes at a steady pace: the events with the balance after each, a point a day, the lowest point, and whether it
    goes under the balance it should not go under (details.floor, set with PATCH /api/accounts/{id}; zero without)."""
    u = _u(request)
    return forecast.forecast(u, model.account(u, aid), days)


@router.get("/api/accounts/{aid}/payoff", dependencies=[access.signed_in])
def account_payoff(aid: int, request: Request, extra: str = None):
    """A loan's payoff from its interest rate and monthly payment (details.rate in percent a year and details.payment,
    set with PATCH /api/accounts/{id}; the payment is worked out from the balance's history when not given): when it
    is paid off, the interest still to pay, and with extra (more paid a month) what that saves."""
    u = _u(request)
    a = model.account(u, aid)
    if a["is_asset"]:
        raise Invalid("A payoff is for what is owed: a loan or a card")
    return payoff.payoff(u, a, extra)


@router.get("/api/forecast", dependencies=[access.signed_in])
def forecast_warnings(request: Request, days: int = 30):
    """The cash accounts you see that would go under their lowest balance in the coming days (30 as left out)."""
    return {"items": forecast.warnings(_u(request), days)}


@router.get("/api/accounts/{aid}/history", dependencies=[access.signed_in])
def account_history(aid: int, request: Request, days: int = 365):
    """The account's value day by day, in the household's currency (a liability as a negative number)."""
    u = _u(request)
    a = model.account(u, aid)
    return {"items": model.history(u, days, account_id=a["id"])}


@router.get("/api/accounts/{aid}/values", dependencies=[access.signed_in])
def account_values(aid: int, request: Request):
    """The values kept for the account, the latest first: from Monarch, typed in (with a note), or estimated."""
    u = _u(request)
    a = model.account(u, aid)
    return {"items": model.valuations(u, a)}


@router.post("/api/accounts/{aid}/values", dependencies=[access.signed_in])
async def add_value(aid: int, request: Request):
    """{value, day? (today), note?}: what the house or the car (or any manual account) was worth on a day."""
    u = _u(request)
    b = await json_body(request)
    a = model.account(u, aid)
    await run_in_threadpool(model.add_valuation, u, a, b)
    return model.account_public(model.account(u, aid), u)


@router.delete("/api/accounts/{aid}/values/{day}", dependencies=[access.signed_in])
def remove_value(aid: int, day: str, request: Request):
    u = _u(request)
    model.remove_valuation(u, model.account(u, aid), day)
    return {"ok": True}


# ------------------------------------------------------------------ the net worth

@router.get("/api/networth", dependencies=[access.signed_in])
def networth(request: Request, days: int = 365, kind: str = None):
    """The net worth now (by kind) and day by day over the past days (kind: one kind's value only)."""
    u = _u(request)
    return {**model.net_worth(u), "history": model.history(u, days, kind=kind)}


# ------------------------------------------------------------------ transactions

@router.get("/api/transactions", dependencies=[access.signed_in])
def list_transactions(request: Request, q: str = "", account: int = None, category: str = None, month: str = None,
                      start: str = None, end: str = None, flow: str = None, hidden: bool = False, reconciled: str = None,
                      amount: str = None, receipt: str = None, tag: str = None, review: str = None, limit: int = 100,
                      offset: int = 0):
    """The transactions you see, the newest first. q: words (the payee, the bank's text, the category, the notes;
    $280, 12.50, 100-200, >500 are amounts); account; category ('-': none); month (YYYY-MM) or start and end
    (YYYY-MM-DD); flow: out or in; amount: an amount, money out or in alike (280), or a range (100-200, >500, <20);
    hidden: also those left out of the sums; reconciled: yes or no; receipt: yes (only those with a receipt kept) or
    no; tag: one tag (Monarch's or set here); review: yes (only those that need a look). With total (how many match)
    and sum."""
    u = _u(request)
    if month:
        start, end = _month_bounds(month)
    return model.find_transactions(u, q, account, category, start, end, flow, limit, offset, hidden, reconciled, amount, receipt, tag, review)


@router.post("/api/transactions/reconcile", dependencies=[access.signed_in])
async def reconcile_transactions(request: Request):
    """{ids: [...], reconciled: true|false}: mark transactions reconciled (checked against the statement) or not.
    How many were marked (those you may change)."""
    u = _u(request)
    b = await json_body(request)
    ids = b.get("ids") if isinstance(b.get("ids"), list) else []
    return {"changed": await run_in_threadpool(model.set_reconciled, u, ids, model.flag(b.get("reconciled", True)))}


@router.post("/api/transactions/bulk", dependencies=[access.signed_in])
async def change_transactions(request: Request):
    """{ids: [...], set: {category?, merchant?, notes?, hidden?, reconciled?, reviewed?, addTags?, removeTags?}}: the
    same change to many transactions at once (those you may change; at most 2000). {changed, skipped, batch}: the
    batch takes it all back as one (POST /api/changes/undo)."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(model.change_many, u, b.get("ids"), b.get("set") if isinstance(b.get("set"), dict) else {})


@router.post("/api/transactions/review", dependencies=[access.signed_in])
async def review_transactions(request: Request):
    """{ids: [...], reviewed: true|false} or {all: true}: mark transactions as looked at (off the Needs a look list)
    or not. {changed, left: how many still need a look}."""
    u = _u(request)
    b = await json_body(request)
    if b.get("all"):
        n = await run_in_threadpool(review.mark_all, u)
    else:
        ids = b.get("ids") if isinstance(b.get("ids"), list) else []
        n = await run_in_threadpool(review.mark, u, ids, bool(model.flag(b.get("reviewed", True))))
    return {"changed": n, "left": review.count(u)}


@router.post("/api/accounts/{aid}/transactions", dependencies=[access.signed_in])
async def add_transaction(aid: int, request: Request):
    """{day?, amount (negative: money out), merchant?, category?, group?, notes?}, in a manual account."""
    u = _u(request)
    b = await json_body(request)
    t = await run_in_threadpool(lambda: model.create_transaction(u, model.account(u, aid), b))
    return JSONResponse(model.with_transfers([model.tx_public(t, u)], u)[0], status_code=201)


@router.get("/api/transactions/{tid}", dependencies=[access.signed_in])
def get_transaction(tid: int, request: Request):
    """One transaction, as the list gives it (with its transfer, its recurring transaction, its splits, its receipts)."""
    u = _u(request)
    return model.with_transfers([model.tx_public(model.transaction(u, tid), u)], u)[0]


@router.patch("/api/transactions/{tid}", dependencies=[access.signed_in])
async def change_transaction(tid: int, request: Request):
    """{category?, group?, merchant?, notes?, hidden?, reconciled?, reviewed?, tags? (its own tags: a list)} (and day,
    amount in a manual account): kept as changed here, also by the next Monarch sync, and kept in its history."""
    u = _u(request)
    b = await json_body(request)
    t = await run_in_threadpool(lambda: model.update_transaction(u, model.transaction(u, tid), b))
    return model.with_transfers([model.tx_public(t, u)], u)[0]


@router.delete("/api/transactions/{tid}", dependencies=[access.signed_in])
def delete_transaction(tid: int, request: Request):
    u = _u(request)
    model.delete_transaction(u, model.transaction(u, tid))
    return {"ok": True}


@router.get("/api/categories", dependencies=[access.signed_in])
def list_categories(request: Request):
    """Every category (those the transactions have, those added here) with its group and how many transactions."""
    u = _u(request)
    return {"items": model.categories(u), "writable": shared_users.can_write(u)}


@router.post("/api/categories", dependencies=[access.signed_in])
async def add_category(request: Request):
    """{name, group?}: a new category."""
    u = _u(request)
    return JSONResponse(categories.add(u, await json_body(request)), status_code=201)


@router.put("/api/categories", dependencies=[access.signed_in])
async def change_category(request: Request):
    """{name, newName?, group?}: rename it (into one there is already: the two merged) or move it to another group;
    its transactions, rules and recurring transactions follow, and so does what Monarch sends later."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(categories.change, u, b)


@router.post("/api/categories/delete", dependencies=[access.signed_in])
async def delete_category(request: Request):
    """{name, moveTo?}: its transactions take moveTo, or no category."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(categories.delete, u, b)


# ------------------------------------------------------------------ transfers between the household's own accounts

@router.put("/api/transactions/{tid}/splits", dependencies=[access.signed_in])
async def split_transaction(tid: int, request: Request):
    """{items: [{amount, category?, notes?}]}: split the transaction over categories: two parts and more, each with
    its share (a positive number, or signed as the transaction), together the whole amount; the spending by category
    counts the parts in its place. {items: []}: whole again. The transaction comes back with its splits."""
    u = _u(request)
    b = await json_body(request)
    t = await run_in_threadpool(lambda: splits.put(u, model.transaction(u, tid), b.get("items")))
    return model.with_transfers([model.tx_public(t, u)], u)[0]


# ------------------------------------------------------------------ receipts

@router.post("/api/transactions/{tid}/receipts", dependencies=[access.signed_in])
async def add_receipt(tid: int, request: Request, name: str | None = None):
    """The receipt itself as the request body: a picture (JPEG, PNG, WebP, GIF, HEIC) or a PDF, up to 20 MB. name:
    its file name. The receipt as listed ({id, name, mime, size, url, added})."""
    u = _u(request)
    raw = await request.body()
    return JSONResponse(await run_in_threadpool(lambda: receipts.add(u, model.transaction(u, tid), raw, name)), status_code=201)


@router.get("/api/receipts/{rid}", dependencies=[access.signed_in])
def get_receipt(rid: int, request: Request, download: bool = False):
    """The receipt's file: shown in the browser (download=true: saved)."""
    body, mime, name = receipts.content(_u(request), rid)
    shown = mime in receipts.INLINE and not download
    headers = {"Cache-Control": "private, max-age=3600",
               "Content-Disposition": f"{'inline' if shown else 'attachment'}; filename*=UTF-8''{urllib.parse.quote(name)}"}
    if mime != "application/pdf":  # a browser's PDF viewer does not open in a sandbox; nothing else needs more than this
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return Response(body, media_type=mime if shown else "application/octet-stream", headers=headers)


@router.delete("/api/receipts/{rid}", dependencies=[access.signed_in])
def delete_receipt(rid: int, request: Request):
    receipts.remove(_u(request), rid)
    return {"ok": True}


@router.get("/api/transactions/{tid}/transfer", dependencies=[access.signed_in])
def transaction_transfer(tid: int, request: Request):
    """The other half of this transaction's transfer (other: {id, accountId, account, day, how}, or null), and the
    transactions you see that could be it (the same amount the other way, in another account, within two weeks)."""
    u = _u(request)
    t = model.transaction(u, tid)
    other = transfers.other_half(u, t)
    return {"other": other, "candidates": [] if other else transfers.candidates(u, t)}


@router.put("/api/transactions/{tid}/transfer", dependencies=[access.signed_in])
async def link_transfer(tid: int, request: Request):
    """{with: the other half's id}: link the two as one transfer, by hand."""
    u = _u(request)
    b = await json_body(request)
    await run_in_threadpool(lambda: transfers.connect(u, model.transaction(u, tid), b.get("with")))
    return {"other": transfers.other_half(u, model.transaction(u, tid))}


@router.delete("/api/transactions/{tid}/transfer", dependencies=[access.signed_in])
def unlink_transfer(tid: int, request: Request):
    """Unlink this transaction's transfer: the two are not linked again by themselves."""
    u = _u(request)
    transfers.disconnect(u, model.transaction(u, tid))
    return {"ok": True}


@router.get("/api/transfers/possible", dependencies=[access.signed_in])
def possible_transfers(request: Request):
    """The debits and credits of the same amount in two accounts, at most two weeks apart, not linked: each {out, in,
    why} (why it was not linked by itself), the nearest days first."""
    return {"items": transfers.possible(_u(request))}


@router.post("/api/transfers/not", dependencies=[access.signed_in])
async def not_a_transfer(request: Request):
    """{outId, inId}: these two are not one transfer; they leave the list of what to check and are never linked by
    themselves."""
    u = _u(request)
    b = await json_body(request)
    await run_in_threadpool(transfers.dismiss, u, b.get("outId"), b.get("inId"))
    return {"ok": True}


@router.post("/api/transfers/link", dependencies=[access.signed_in])
async def link_transfers(request: Request):
    """Go through every transaction not linked yet and link the transfers (editors): {linked, learned (transfer
    rules learned), unsure: [{out, in}] the pairs as likely as another, left for a person to link}."""
    u = _u(request)
    return await run_in_threadpool(transfers.link_all, u)


@router.get("/api/transfer-rules", dependencies=[access.signed_in])
def list_transfer_rules(request: Request):
    """The transfer rules: in an account, a payee (or bank's text) with these words is a transfer with that account.
    source learned: made when a transfer was found by itself."""
    u = _u(request)
    return {"items": [transfers.rule_public(r, u) for r in transfers.rules(u)], "writable": model.may_add(u, True)}


@router.post("/api/transfer-rules", dependencies=[access.signed_in])
async def add_transfer_rule(request: Request):
    """{accountId, pattern, otherId, days? (5)} (editors)."""
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(transfers.create_rule, u, b)
    linked = await run_in_threadpool(transfers.link)
    return JSONResponse({**transfers.rule_public(r, u), "linked": linked}, status_code=201)


@router.patch("/api/transfer-rules/{rid}", dependencies=[access.signed_in])
async def change_transfer_rule(rid: int, request: Request):
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(lambda: transfers.update_rule(u, transfers.rule(u, rid), b))
    return {**transfers.rule_public(r, u), "linked": await run_in_threadpool(transfers.link)}


@router.delete("/api/transfer-rules/{rid}", dependencies=[access.signed_in])
def delete_transfer_rule(rid: int, request: Request):
    u = _u(request)
    transfers.delete_rule(u, transfers.rule(u, rid))
    return {"ok": True}


# ------------------------------------------------------------------ rules

@router.get("/api/rules", dependencies=[access.signed_in])
def list_rules(request: Request):
    """The household's rules, in the order they are tried: each renames the payee, sets the category or hides the
    transactions whose payee or bank's text matches. Anyone with a role sees them; editors change them."""
    u = _u(request)
    return {"items": [model.rule_public(r, u) for r in model.rules(u)], "writable": model.may_add(u, True)}


@router.post("/api/rules", dependencies=[access.signed_in])
async def add_rule(request: Request):
    """{pattern, field? (either, merchant, description), how? (contains, is, starts), accountId?, flow? (out, in),
    amountMin?, amountMax?, setMerchant?, setCategory?, setHidden?, enabled?, apply? (true: run it over the
    transactions you have now, except those changed by hand)}."""
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(model.create_rule, u, b)
    out = model.rule_public(r, u)
    if b.get("apply"):
        out["changed"] = await run_in_threadpool(model.apply_rules)  # all of them, so their order holds
    return JSONResponse(out, status_code=201)


@router.post("/api/rules/test", dependencies=[access.signed_in])
async def test_rule(request: Request):
    """{pattern, field?, how?, accountId?, flow?, amountMin?, amountMax?}: the transactions it matches (count, how
    many of them were changed by hand and so stay as they are, and the newest few). Nothing is kept or changed."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(model.try_rule, u, b)


@router.post("/api/rules/apply", dependencies=[access.signed_in])
async def apply_rules(request: Request):
    """Every rule over every transaction (except those changed by hand): how many changed."""
    u = _u(request)
    return {"changed": await run_in_threadpool(model.apply_all_rules, u)}


@router.put("/api/rules/order", dependencies=[access.signed_in])
async def order_rules(request: Request):
    """{ids: [the rules' ids, in the order they are tried]}."""
    u = _u(request)
    b = await json_body(request)
    rs = await run_in_threadpool(model.order_rules, u, b.get("ids"))
    return {"items": [model.rule_public(r, u) for r in rs]}


@router.patch("/api/rules/{rid}", dependencies=[access.signed_in])
async def change_rule(rid: int, request: Request):
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(lambda: model.update_rule(u, model.rule(u, rid), b))
    out = model.rule_public(r, u)
    if b.get("apply"):
        out["changed"] = await run_in_threadpool(model.apply_rules)  # all of them, so their order holds
    return out


@router.delete("/api/rules/{rid}", dependencies=[access.signed_in])
def delete_rule(rid: int, request: Request):
    u = _u(request)
    model.delete_rule(u, model.rule(u, rid))
    return {"ok": True}


@router.get("/api/spending", dependencies=[access.signed_in])
def spending(request: Request, month: str = None, start: str = None, end: str = None):
    """Money out and in by category, for a month (YYYY-MM; this month as left out) or between start and end."""
    if not (start and end):
        start, end = _month_bounds(month)
    return model.spending(_u(request), start, end)


@router.get("/api/cashflow", dependencies=[access.signed_in])
def cashflow(request: Request, months: int = 12):
    """Money in and out month by month (transfers left out), the current month last."""
    return {"currency": model.home_currency(), "items": model.cash_flow(_u(request), months)}


# ------------------------------------------------------------------ holdings and quotes

@router.get("/api/portfolio", dependencies=[access.signed_in])
def portfolio(request: Request, account: int = None):
    """Every holding you see, priced, with the day's change, the gain over the cost basis, the totals, the same symbol
    added up across accounts, and the allocation by kind."""
    return model.portfolio(_u(request), account)


@router.post("/api/accounts/{aid}/holdings", dependencies=[access.signed_in])
async def add_holding(aid: int, request: Request):
    """{symbol (as Yahoo Finance writes it: AAPL, VWCE.DE, BTC-USD), shares, costBasis? (paid for all of them),
    kind?, name?, price? (for something without a symbol)}, in a manual investment account."""
    u = _u(request)
    b = await json_body(request)
    h = await run_in_threadpool(lambda: model.create_holding(u, model.account(u, aid), b))
    if h["symbol"]:
        await run_in_threadpool(quotes.refresh, False, [h["symbol"]])
        await run_in_threadpool(model.revalue_manual_investments)
    return JSONResponse({"id": h["id"]}, status_code=201)


@router.patch("/api/holdings/{hid}", dependencies=[access.signed_in])
async def change_holding(hid: int, request: Request):
    u = _u(request)
    b = await json_body(request)
    h = await run_in_threadpool(lambda: model.update_holding(u, model.holding(u, hid), b))
    if h["symbol"]:
        await run_in_threadpool(quotes.refresh, False, [h["symbol"]])
    await run_in_threadpool(model.revalue_manual_investments)
    return {"id": h["id"]}


@router.delete("/api/holdings/{hid}", dependencies=[access.signed_in])
def delete_holding(hid: int, request: Request):
    u = _u(request)
    h = model.holding(u, hid)
    model.delete_holding(u, h)
    model.revalue_manual_investments(h["account_id"])
    return {"ok": True}


@router.get("/api/quotes/{sym}", dependencies=[access.signed_in])
async def get_quote(sym: str, request: Request, days: int = 365):
    """One symbol's quote (asked of Yahoo Finance when it is not fresh) and its closing prices."""
    if model.role_rank(_u(request)) < 1:
        raise HTTPException(403, "You have no role in ioMoney")
    s = model.symbol(sym)
    if not s:
        raise Invalid("Name a symbol")
    q = await run_in_threadpool(quotes.quote, s)
    return {**q, "closes": quotes.closes(s, max(7, min(days, 400)))}


@router.post("/api/quotes/refresh", dependencies=[access.signed_in])
async def refresh_quotes(request: Request):
    """Ask Yahoo Finance again for every quote that is more than a minute old."""
    if model.role_rank(_u(request)) < 1:
        raise HTTPException(403, "You have no role in ioMoney")

    def go():
        old = quotes.QUOTE_S
        quotes.QUOTE_S = 60
        try:
            got = quotes.refresh()
        finally:
            quotes.QUOTE_S = old
        model.revalue_manual_investments()
        return got
    return await run_in_threadpool(go)


# ------------------------------------------------------------------ recurring transactions, and the bills ioCalendar shows

@router.get("/api/recurring", dependencies=[access.signed_in])
def list_recurring(request: Request):
    """The household's recurring transactions (each with its next date, the last payment and its flag: a payment
    missed, or one whose amount changed), and what was found in
    the transactions that looks recurring and is not in the list (found), with whether you may change them."""
    u = _u(request)
    return {"items": recurring.items(u), "found": recurring.found(u), "writable": shared_users.can_write(u),
            "frequencies": [{"value": f, "label": recurring.FREQ_LABEL[f]} for f in recurring.FREQS]}


@router.post("/api/recurring", dependencies=[access.signed_in])
async def add_recurring(request: Request):
    """{name, pattern (words its payee or bank's text has; the name as left out), accountId?, flow: out|in, amount,
    approximate?, frequency, day (a day it fell on), category?}; or {found: key}: what was found, added."""
    u = _u(request)
    b = await json_body(request)
    r = await run_in_threadpool(lambda: recurring.add_found(u, b["found"]) if b.get("found") else recurring.create(u, b))
    return JSONResponse(recurring.public(r, u), status_code=201)


@router.post("/api/recurring/not", dependencies=[access.signed_in])
async def not_recurring(request: Request):
    """{key}: what was found is not recurring; not offered again."""
    u = _u(request)
    b = await json_body(request)
    recurring.dismiss(u, b.get("key"))
    return {"ok": True}


@router.patch("/api/recurring/{rid}", dependencies=[access.signed_in])
async def change_recurring(rid: int, request: Request):
    u = _u(request)
    b = await json_body(request)
    return recurring.public(recurring.update(u, recurring.item(u, rid), b), u)


@router.post("/api/recurring/{rid}/ok", dependencies=[access.signed_in])
async def recurring_flag_ok(rid: int, request: Request):
    """{kind: missed|changed, day}: the item's flag (as its flag gives them) looked at: not shown again for that day."""
    u = _u(request)
    b = await json_body(request)
    r = recurring.item(u, rid)
    recurring.set_aside(u, r, b)
    return recurring.public(r, u)


@router.get("/api/transactions/{tid}/recurring", dependencies=[access.signed_in])
def transaction_recurring(tid: int, request: Request):
    """The recurring transaction this one is (item), or one to add from it (suggestion: how often and the usual
    amount from the transactions like it), with whether you may change it."""
    u = _u(request)
    t = model.transaction(u, tid)
    out = recurring.for_transaction(u, t)
    a = model.account_row(t["account_id"])
    out["writable"] = shared_users.can_write(u) if a["owner_id"] is None else model.can_write(u, a)
    out["frequencies"] = [{"value": f, "label": recurring.FREQ_LABEL[f]} for f in recurring.FREQS]
    return out


@router.delete("/api/recurring/{rid}", dependencies=[access.signed_in])
def remove_recurring(rid: int, request: Request):
    u = _u(request)
    recurring.delete(u, recurring.item(u, rid))
    return {"ok": True}


@router.get("/api/bills", dependencies=[access.signed_in])
def list_bills(request: Request, start: str = None, end: str = None):
    """Each date a recurring transaction falls on between start and end (YYYY-MM-DD; this month as left out), paid
    or not, those of your private accounts included: what ioCalendar shows on their days."""
    if not (start and end):
        start, end = _month_bounds(None)
    s, e = model.day(start), model.day(end)
    if (e - s).days > 400:
        raise Invalid("At most 400 days at a time")
    return {"currency": model.home_currency(), "items": recurring.bills(_u(request), s, e)}


# ------------------------------------------------------------------ putting the data in order

@router.get("/api/tidy", dependencies=[access.signed_in])
def tidy(request: Request):
    """What there is to put in order, in a few numbers: review (transactions that need a look), duplicates (likely
    ones), transfers (pairs to check), balanceGaps (accounts whose balance and transactions disagree), payees, tags,
    changes (kept changes of the past month)."""
    u = _u(request)
    if model.role_rank(u) < 1:
        return {"review": 0, "duplicates": 0, "transfers": 0, "balanceGaps": 0, "payees": 0, "tags": 0}
    return {"review": review.count(u), "duplicates": duplicates.count(u), "transfers": len(transfers.possible(u)),
            "balanceGaps": balancecheck.check(u)["gaps"], "payees": payees.items(u, limit=1)["total"], "tags": len(tags.items(u))}


@router.get("/api/payees", dependencies=[access.signed_in])
def list_payees(request: Request, q: str = "", limit: int = 500):
    """The payees of the transactions you see, the most used first: {payee, count, total, last, category (its most
    common one), categories (how many different ones), rule (the rule that sets its category)}. q: words in the name."""
    u = _u(request)
    return {**payees.items(u, q, limit), "writable": shared_users.can_write(u)}


@router.post("/api/payees/rename", dependencies=[access.signed_in])
async def rename_payee(request: Request):
    """{name, newName}: the payee under another name, in every transaction and from now on (a rule); a name another
    payee has merges the two (editors). {changed, rule}."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(payees.rename, u, b)


@router.post("/api/payees/category", dependencies=[access.signed_in])
async def payee_category(request: Request):
    """{name, category, all?}: the payee's usual category: a rule from now on, and its transactions there are (those
    not changed by hand; all: those too) (editors). {changed, rule}."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(payees.set_category, u, b)


@router.get("/api/tags", dependencies=[access.signed_in])
def list_tags(request: Request):
    """Every tag on the transactions you see: {tag, count, total, own (set here, not Monarch's)}."""
    u = _u(request)
    return {"items": tags.items(u), "writable": shared_users.can_write(u)}


@router.put("/api/tags", dependencies=[access.signed_in])
async def rename_tag(request: Request):
    """{name, newName}: one of the tags set here under another name (one there is: the two merged) (editors)."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(tags.rename, u, b)


@router.post("/api/tags/delete", dependencies=[access.signed_in])
async def delete_tag(request: Request):
    """{name}: one of the tags set here off every transaction (editors)."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(tags.delete, u, b)


@router.get("/api/duplicates", dependencies=[access.signed_in])
def likely_duplicates(request: Request):
    """Transactions that look like one kept twice: the same account and amount, at most three days apart, and alike.
    Each group {why, whyText, items}; keep one and hide or delete the other, or say they are two (POST
    /api/duplicates/not)."""
    return {"items": duplicates.groups(_u(request))}


@router.post("/api/duplicates/not", dependencies=[access.signed_in])
async def not_duplicates(request: Request):
    """{ids: [...]}: these are different transactions; not offered again."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(duplicates.dismiss, u, b.get("ids"))


@router.get("/api/accounts/{aid}/statements", dependencies=[access.signed_in])
def account_statements(aid: int, request: Request):
    """The statements the account was reconciled against, and where the next one starts (next: {start, opening})."""
    u = _u(request)
    return statements.of(u, model.account(u, aid))


@router.get("/api/accounts/{aid}/statement", dependencies=[access.signed_in])
def statement_lines(aid: int, request: Request, start: str, end: str):
    """The transactions to tick off against a statement from start to end (YYYY-MM-DD), the hidden ones too, and the
    earlier ones the statement before left open (earlier: true). sign: 1, or -1 for an account of what is owed (there
    money out makes the balance go up)."""
    u = _u(request)
    return statements.lines(u, model.account(u, aid), start, end)


@router.post("/api/accounts/{aid}/statement/read", dependencies=[access.signed_in])
async def read_statement(aid: int, request: Request, name: str | None = None, order: str | None = None, flip: str | None = None):
    """The bank's own file as the request body (up to 20 MB), held against the account: a statement's PDF, or the CSV,
    OFX or QFX file from the bank's website. Nothing is changed and the file is not kept. name: its file name;
    order: how day and month stand in its dates (mdy, dmy, ymd), when the guess is wrong; flip: 1 or 0, whether it
    writes money out as a positive number (as left out: whichever fits). {kind, start, end, opening, closing, worked,
    adds, total, sum, matched: the transactions found (to tick), missing: the lines the account does not have (with
    differs: the transaction of another amount that looks like it), elsewhere: the lines it has outside these days,
    extra: the transactions of these days the file does not show, dateOrder, guessed, flipped}."""
    u = _u(request)
    raw = await request.body()
    return await run_in_threadpool(lambda: statementfile.read(u, model.account(u, aid), raw, name, order, flip))


@router.post("/api/accounts/{aid}/statements", dependencies=[access.signed_in])
async def reconcile_statement(aid: int, request: Request):
    """{start, end, opening, closing, ids: the transactions ticked off, anyway?}: mark them reconciled and keep the
    statement. Refused while the ticked ones do not add up to closing minus opening, unless anyway."""
    u = _u(request)
    b = await json_body(request)
    return JSONResponse(await run_in_threadpool(lambda: statements.save(u, model.account(u, aid), b)), status_code=201)


@router.delete("/api/statements/{sid}", dependencies=[access.signed_in])
def delete_statement(sid: int, request: Request):
    """Forget a statement (its transactions stay reconciled)."""
    statements.remove(_u(request), sid)
    return {"ok": True}


@router.get("/api/balance-check", dependencies=[access.signed_in])
def balance_check(request: Request, days: int = balancecheck.DAYS):
    """For each cash account and card from Monarch Money with a bank behind it: whether its balance moved, over the
    past days, by what its transactions add up to (status ok, waiting, accepted, gap or unknown), the gap, and the
    weeks in which it appeared."""
    return balancecheck.check(_u(request), days)


@router.post("/api/balance-check/{aid}/ok", dependencies=[access.signed_in])
async def balance_gap_ok(aid: int, request: Request):
    """{gap}: the account's gap was looked at and is fine as it is: not flagged while it stays the same ({gap: null}:
    flag it again)."""
    u = _u(request)
    b = await json_body(request)
    return balancecheck.accept(u, model.account(u, aid), b)


@router.get("/api/rules/upkeep", dependencies=[access.signed_in])
def rules_upkeep(request: Request):
    """What each rule does to the transactions of the past two years (matched, decides, last, and note: never, behind
    an earlier rule, or off), and the rules suggested from what was categorized by hand again and again."""
    return rulecheck.upkeep(_u(request))


@router.post("/api/rules/suggestions/not", dependencies=[access.signed_in])
async def not_this_rule(request: Request):
    """{key}: a suggested rule is not wanted; not offered again (editors)."""
    u = _u(request)
    b = await json_body(request)
    return rulecheck.dismiss(u, b.get("key"))


@router.get("/api/transactions/{tid}/changes", dependencies=[access.signed_in])
def transaction_changes(tid: int, request: Request):
    """What was changed by hand on the transaction, the latest first: {id, what (hand, bulk, undo, reset), by, at,
    undone, fields: [{field, before, after}]}."""
    u = _u(request)
    return {"items": history.of(u, model.transaction(u, tid))}


@router.post("/api/transactions/{tid}/reset", dependencies=[access.signed_in])
async def reset_transaction(tid: int, request: Request):
    """A transaction from Monarch Money back to Monarch's own: what was changed here is undone (its own tags and its
    split go), the rules apply again and the next sync refreshes it. The transaction as it is then."""
    u = _u(request)
    await run_in_threadpool(lambda: history.reset(u, model.transaction(u, tid)))
    return model.with_transfers([model.tx_public(model.transaction(u, tid), u)], u)[0]


@router.get("/api/changes", dependencies=[access.signed_in])
def recent_changes(request: Request, limit: int = 100):
    """The latest changes made by hand to the transactions you see; the ones made together (many at once) as one."""
    return {"items": history.recent(_u(request), max(1, min(limit, 300)))}


@router.post("/api/changes/undo", dependencies=[access.signed_in])
async def undo_changes(request: Request):
    """{batch} or {id}: take back the changes made together, or one change: the fields as they were before."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(lambda: history.undo(u, b.get("id"), b.get("batch")))


@router.get("/api/searches", dependencies=[access.signed_in])
def list_searches(request: Request):
    """Your saved searches of the transactions: {id, name, query (the filters, as the page's address has them)}."""
    return {"items": searches.items(_u(request))}


@router.post("/api/searches", dependencies=[access.signed_in])
async def add_search(request: Request):
    """{name, query}: keep a search under a name (a name you have already: that one is replaced)."""
    u = _u(request)
    return JSONResponse(searches.create(u, await json_body(request)), status_code=201)


@router.patch("/api/searches/{sid}", dependencies=[access.signed_in])
async def change_search(sid: int, request: Request):
    """{name?, query?, position?}."""
    u = _u(request)
    return searches.update(u, sid, await json_body(request))


@router.delete("/api/searches/{sid}", dependencies=[access.signed_in])
def delete_search(sid: int, request: Request):
    searches.delete(_u(request), sid)
    return {"ok": True}


@router.post("/api/accounts/{aid}/import", dependencies=[access.signed_in])
async def import_file(aid: int, request: Request):
    """A bank's file into an account kept by hand: {name?, text: the CSV, OFX or QFX file (up to 20 MB), preview?
    (true: add nothing, say what it holds), mapping? (CSV: which column is the date, the amount or debit and credit,
    type, payee, notes, category: numbers from 0), dateOrder? (mdy, dmy, ymd), flip? (money out is written as a
    positive number), duplicates? (true: add what the account has already too), balance? (move: the balance moves by
    what is added; keep; file: the balance an OFX file gives)}. What it holds: kind, columns, mapping, dateOrder,
    total, new, duplicates, problems, from, to, the first rows, and added (how many came in)."""
    u = _u(request)
    b = await json_body(request)
    return await run_in_threadpool(lambda: importer.run(u, model.account(u, aid), b))


# ------------------------------------------------------------------ Monarch Money and the settings (admins)

@router.get("/api/monarch", dependencies=[access.admin])
def monarch_status():
    """Whether the sign-in is kept (Keys and tokens; never the values), the last syncs and how they went."""
    return monarch.status()


@router.post("/api/monarch/sync", dependencies=[access.admin])
async def monarch_sync(request: Request):
    """{full?: true (the past two years of transactions again), accountId?: just this Monarch account's
    transactions again, years?: how far back for it (2 as left out; 0: all Monarch has), wait?: seconds (10 as left out, at most 60)}: start copying Monarch Money in, in the background. When it ends within wait: how it went ({ok, message, ...}); else
    {running: true, progress: {stage, count, started}}, and GET /api/monarch says how it goes and, at the end, how
    it went (last)."""
    b = await json_body(request) if (request.headers.get("content-length") or "0") != "0" else {}
    wait = max(0.0, min(float(b.get("wait", 10) or 0), 60.0))
    only = None
    if b.get("accountId"):
        a = model.account_row(b["accountId"])
        if not a or a["source"] != "monarch":
            raise Invalid("The account: one from Monarch Money")
        only = a["id"]
    try:
        years = max(0, min(int(b.get("years", 2)), 30))
    except (TypeError, ValueError):
        raise Invalid("How far back: a number of years, or 0 for all")
    return await run_in_threadpool(monarch.start, _u(request)["id"], bool(b.get("full")), wait, only, years)


@router.get("/api/monarch/new", dependencies=[access.admin])
def monarch_new():
    """The accounts Monarch Money reported that ioMoney did not know (after the first sync): they wait, with their
    transactions, until an admin says whether each is new or an account here made again in Monarch under a new id.
    Each comes with the accounts here it could be, likeliest first (candidates; likely: the id of a sure one)."""
    return {"items": monarch.held()}


@router.post("/api/monarch/new/{ext}", dependencies=[access.admin])
async def monarch_new_decide(ext: str, request: Request):
    """{as: 'new'} or {as: 'existing', accountId}, wait?: seconds: what a waiting account is. A sync starts right away
    (its result as it ends within wait, as for POST /api/monarch/sync): a new account comes in with its history; an
    existing one takes the new id, and its transactions are matched with those kept, so none is there twice."""
    b = await json_body(request)
    r = monarch.decide(ext, str(b.get("as") or ""), b.get("accountId"), _u(request)["id"])
    wait = max(0.0, min(float(b.get("wait", 0) or 0), 60.0))
    r["sync"] = await run_in_threadpool(monarch.start, _u(request)["id"], False, wait)
    return r


@router.post("/api/monarch/code", dependencies=[access.admin])
async def monarch_code(request: Request):
    """{code}: sign in to Monarch with a six-digit code from the authenticator app (when no authenticator key is kept)."""
    b = await json_body(request)
    try:
        await run_in_threadpool(monarch.sign_in_with_code, str(b.get("code") or ""))
    except monarch.NeedsSignIn as e:
        raise Invalid(str(e))
    return monarch.status()


@router.delete("/api/monarch/session", dependencies=[access.admin])
def monarch_forget():
    """Forget the kept Monarch session: the next sync signs in again."""
    monarch.forget_session()
    return monarch.status()


@router.get("/api/settings", dependencies=[access.signed_in])
def get_settings():
    """The household's currency (what the totals are in) and whether Monarch Money is synced on its own."""
    return {"currency": model.home_currency(), "monarchAuto": model.setting("monarch_auto", "1") == "1"}


@router.put("/api/settings", dependencies=[access.admin])
async def put_settings(request: Request):
    """{currency?: 'USD', monarchAuto?: bool} (admins)."""
    b = await json_body(request)
    if "currency" in b:
        cur = model.currency(b["currency"])
        db.set_setting("currency", cur)
        await run_in_threadpool(quotes.refresh)
    if "monarchAuto" in b:
        db.set_setting("monarch_auto", "1" if b["monarchAuto"] else "0")
    return get_settings()
