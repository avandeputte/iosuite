"""The money tools, with the same permissions as the web app: nobody without a role in ioMoney sees anything, a
viewer only reads, a member keeps private accounts of their own, editors and admins change the household's."""
import datetime as dt
from typing import Literal, Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import (__version__, balancecheck, config, duplicates, forecast, model, monarch, payees as payee_list, payoff, quotes,
                 recurring, review, splits, tags as tag_store, transfers)
from app.mcp.base import ADDS, DELETES, READ_ONLY, WRITES, clamp, find_account, guard, link, need_admin, server, who


def _need_role(u: dict) -> None:
    if model.role_rank(u) < 1:
        raise ToolError("You have no role in ioMoney: a suite admin gives one (Settings › Security)")


def _acct(u: dict, a: dict) -> dict:
    j = model.account_public(a, u)
    j["youCanChange"] = j.pop("writable")
    if link(f"account/{a['id']}"):
        j["webUrl"] = link(f"account/{a['id']}")
    return {k: v for k, v in j.items() if v not in (None, "", [], {}) or k in ("balance", "value")}


@server.tool(annotations=READ_ONLY)
def overview() -> dict:
    """Who you are, the household's currency, the net worth now (assets, what is owed, by kind), the accounts with
    their balances, when Monarch Money was last synced, and banksBehind: the accounts whose link to the bank Monarch
    reports as broken or more than two days behind (check them in Monarch Money). Start here."""
    u = who()
    _need_role(u)
    return {"you": {"name": u["name"], "role": u.get("role")}, "currency": model.home_currency(),
            "netWorth": model.net_worth(u), "accounts": [_acct(u, a) for a in model.accounts(u)],
            "monarchLastSync": monarch.status()["lastGood"], "banksBehind": model.stale_accounts(u),
            "version": __version__, "webApp": config.PUBLIC_URL or None}


@server.tool(annotations=READ_ONLY)
def net_worth_history(days: int = 365, kind: Optional[str] = None, account: Optional[str] = None) -> list:
    """The net worth day by day over the past days (weekly beyond three months, monthly beyond two years), in the
    household's currency. kind: one kind's value only (cash, investment, property, vehicle, credit, loan, ...);
    account: one account's (its id or name)."""
    u = who()
    _need_role(u)
    aid = find_account(u, account)["id"] if account else None
    return model.history(u, clamp(days, 7, 3660), kind=kind, account_id=aid)


@server.tool(annotations=READ_ONLY)
def bank_contact(account: str) -> dict:
    """How to reach an account's bank, as the household keeps it in its Bank details: phone (customer service),
    phoneAbroad, website, email, address, swift, openedOn. Account and routing numbers, the IBAN, the sign-in name and
    the notes are never given here (they are on the account's page)."""
    u = who()
    _need_role(u)
    info = model.account_info(u, find_account(u, account))
    return {k: v for k, v in info.items() if k not in (*model.INFO_SECRET, "username", "notes")}


@server.tool(annotations=READ_ONLY)
def search_transactions(query: Optional[str] = None, account: Optional[str] = None, category: Optional[str] = None,
                        start: Optional[str] = None, end: Optional[str] = None, flow: Optional[Literal["in", "out"]] = None,
                        reconciled: Optional[bool] = None, amount: Optional[str] = None, receipt: Optional[bool] = None,
                        tag: Optional[str] = None, needs_look: Optional[bool] = None, limit: int = 50) -> dict:
    """Transactions, the newest first: query (words in the payee, the bank's text, the category, the notes),
    account (id or name), category (exact name), start and end (YYYY-MM-DD), flow (out: money out; in: money in),
    reconciled (true: only those reconciled; false: only those not), amount (money out or in alike: "280" exactly, or
    a range "100-200", ">500", "<20"), receipt (true: only those with a receipt kept; false: only those without),
    tag (one tag, Monarch's or set in ioMoney), needs_look (true: only those nobody looked at yet: new ones and
    those without a category). With how many match and their sum. Each has splits (its parts, when it is split over categories) and receipts
    (the files kept with it: their names, not their content)."""
    u = who()
    _need_role(u)
    aid = find_account(u, account)["id"] if account else None
    rec = None if reconciled is None else ("yes" if reconciled else "no")
    has = None if receipt is None else ("yes" if receipt else "no")
    r = guard(model.find_transactions, u, query or "", aid, category, start, end, flow, clamp(limit, 1, 500), 0, False, rec, amount, has,
              tag, "yes" if needs_look else None)
    for t in r["items"]:
        for k in ("writable", "edited", "source"):
            t.pop(k, None)
        t["receipts"] = [{"name": x["name"], "type": x["mime"], "size": x["size"]} for x in t.get("receipts") or []]
    return r


@server.tool(annotations=READ_ONLY)
def spending(month: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None) -> dict:
    """Money out and in by category for a month (YYYY-MM; this month as left out) or between start and end
    (YYYY-MM-DD), in the household's currency; transfers between the household's own accounts left out."""
    u = who()
    _need_role(u)
    if not (start and end):
        from app.api import _month_bounds
        start, end = guard(_month_bounds, month)
    return guard(model.spending, u, start, end)


@server.tool(annotations=READ_ONLY)
def cash_flow(months: int = 12) -> list:
    """Money in, money out and what was left, month by month, the current month last."""
    u = who()
    _need_role(u)
    return model.cash_flow(u, clamp(months, 1, 60))


@server.tool(annotations=READ_ONLY)
def categories() -> list:
    """The categories (those in use and those added in ioMoney), with their group and how many transactions have each."""
    u = who()
    _need_role(u)
    return model.categories(u)


@server.tool(annotations=READ_ONLY)
def data_checks() -> dict:
    """What there is to put in order in the data: needsLook (how many transactions nobody looked at yet;
    search_transactions(needs_look=true) lists them), likelyDuplicates (groups of transactions that look like one
    kept twice: the same account and amount within three days, with why), and balanceCheck (for each cash account
    and card from Monarch Money: whether its balance moved by what its transactions add up to over the past 90 days,
    the gap when not, the weeks in which it appeared, and waiting: the past week's transactions that are not in the
    bank's balance yet, when they are the whole of the gap). Nothing is changed."""
    u = who()
    _need_role(u)
    dup = [{"why": g["whyText"], "transactions": [{k: t[k] for k in ("id", "account", "day", "amount", "merchant", "description", "source")}
                                                   for t in g["items"]]} for g in duplicates.groups(u, 50)]
    return {"needsLook": review.count(u), "likelyDuplicates": dup, "balanceCheck": balancecheck.check(u)["items"]}


@server.tool(annotations=READ_ONLY)
def payees(query: Optional[str] = None, limit: int = 100) -> dict:
    """The payees of the transactions, the most used first: how many transactions and how much each has, the last
    day, its most common category and how many different categories it has (more than one often means some are
    wrong). query: words in the name."""
    u = who()
    _need_role(u)
    return payee_list.items(u, query or "", clamp(limit, 1, 500))


@server.tool(annotations=WRITES)
def update_transaction(transaction_id: int, category: Optional[str] = None, notes: Optional[str] = None,
                       hidden: Optional[bool] = None, merchant: Optional[str] = None, reconciled: Optional[bool] = None,
                       tags: Optional[list[str]] = None, reviewed: Optional[bool] = None) -> dict:
    """Change a transaction: its category, notes, payee name, hidden (left out of the sums), reconciled (checked
    against the statement), tags (its own tags, all of them: the ones Monarch sends stay) or reviewed (looked at: off
    the Needs a look list). Kept as changed here, also by the next Monarch sync (Monarch itself is not changed), and
    kept in the transaction's history, where it can be taken back."""
    u = who()
    b = {k: v for k, v in {"category": category, "notes": notes, "hidden": hidden, "merchant": merchant,
                           "reconciled": reconciled, "tags": tags, "reviewed": reviewed}.items() if v is not None}
    t = guard(model.update_transaction, u, guard(model.transaction, u, transaction_id), b)
    return tag_store.mark([model.tx_public(t)])[0]


@server.tool(annotations=WRITES)
def split_transaction(transaction_id: int, parts: list[dict]) -> dict:
    """Split a transaction over categories (one warehouse or online order with groceries, clothes and a gift): parts
    [{amount, category, notes}], two and more, each amount its share as a positive number, together the whole amount.
    The spending by category then counts the parts in its place. An empty list makes it whole again."""
    u = who()
    t = guard(splits.put, u, guard(model.transaction, u, transaction_id), parts)
    return splits.mark([model.tx_public(t)])[0]


@server.tool(annotations=ADDS)
def add_transaction(account: str, amount: float, day: Optional[str] = None, merchant: Optional[str] = None,
                    category: Optional[str] = None, notes: Optional[str] = None) -> dict:
    """A transaction in a manual account (id or name): amount negative for money out; day YYYY-MM-DD (today as left out)."""
    u = who()
    a = find_account(u, account)
    t = guard(model.create_transaction, u, a, {"amount": amount, "day": day, "merchant": merchant, "category": category, "notes": notes})
    return model.tx_public(t)


@server.tool(annotations=READ_ONLY)
def rules() -> dict:
    """The household's rules for transactions, in the order they are tried: when the payee or the bank's text matches
    (contains, is, starts), the payee is renamed, the category set or the transaction hidden."""
    u = who()
    _need_role(u)
    return {"items": [model.rule_public(r, u) for r in model.rules(u)]}


@server.tool(annotations=ADDS)
def add_rule(pattern: str, rename_to: Optional[str] = None, category: Optional[str] = None, hide: Optional[bool] = None,
             field: Literal["either", "merchant", "description"] = "either", how: Literal["contains", "is", "starts"] = "contains",
             account: Optional[str] = None, flow: Optional[Literal["out", "in"]] = None, amount_min: Optional[float] = None,
             amount_max: Optional[float] = None, apply_now: bool = True) -> dict:
    """A rule (editors): the transactions whose payee (field merchant), bank's text (description) or either
    contains / is / starts with pattern (any case), optionally only in one account (id or name), money out or in,
    between two amounts, get the payee rename_to, the category, and/or are hidden. apply_now: also over the
    transactions there are now (those changed by hand stay as they are). Try it first with test_rule."""
    u = who()
    b = {"pattern": pattern, "field": field, "how": how, "flow": flow, "amountMin": amount_min, "amountMax": amount_max,
         "setMerchant": rename_to, "setCategory": category, "setHidden": hide}
    if account:
        b["accountId"] = find_account(u, account)["id"]
    r = guard(model.create_rule, u, b)
    out = model.rule_public(r, u)
    if apply_now:
        out["changed"] = model.apply_rules()
    return out


@server.tool(annotations=READ_ONLY)
def test_rule(pattern: str, field: Literal["either", "merchant", "description"] = "either",
              how: Literal["contains", "is", "starts"] = "contains", account: Optional[str] = None,
              flow: Optional[Literal["out", "in"]] = None, amount_min: Optional[float] = None, amount_max: Optional[float] = None) -> dict:
    """Which transactions a rule would match, without keeping it: how many, how many of them were changed by hand
    (a rule leaves those), and the newest few."""
    u = who()
    _need_role(u)
    b = {"pattern": pattern, "field": field, "how": how, "flow": flow, "amountMin": amount_min, "amountMax": amount_max}
    if account:
        b["accountId"] = find_account(u, account)["id"]
    return guard(model.try_rule, u, b)


@server.tool(annotations=WRITES)
def update_rule(rule_id: int, pattern: Optional[str] = None, rename_to: Optional[str] = None, category: Optional[str] = None,
                hide: Optional[bool] = None, enabled: Optional[bool] = None, position: Optional[int] = None,
                apply_now: bool = False) -> dict:
    """Change a rule (its id, from rules): only what is given changes; rename_to or category '' takes that action
    away. position: where it is tried (1 first)."""
    u = who()
    b = {k: v for k, v in {"pattern": pattern, "setMerchant": rename_to, "setCategory": category, "setHidden": hide,
                           "enabled": enabled, "position": position}.items() if v is not None}
    r = guard(model.update_rule, u, guard(model.rule, u, rule_id), b)
    out = model.rule_public(r, u)
    if apply_now:
        out["changed"] = model.apply_rules()
    return out


@server.tool(annotations=DELETES)
def delete_rule(rule_id: int) -> dict:
    """Remove a rule (its id, from rules). The transactions it changed keep their payee and category until Monarch
    sends them again. Ask first."""
    u = who()
    r = guard(model.rule, u, rule_id)
    guard(model.delete_rule, u, r)
    return {"deleted": r["pattern"]}


@server.tool(annotations=WRITES)
def apply_rules() -> dict:
    """Run every rule over every transaction (except those changed by hand): how many changed (editors)."""
    u = who()
    return {"changed": guard(model.apply_all_rules, u)}


@server.tool(annotations=WRITES)
def link_transfers() -> dict:
    """Find the transfers between the household's own accounts among the transactions not linked yet (the same
    amount out of one and into another a few days apart, with a transfer category, a payee naming the other account,
    or a transfer rule, or a payee like "Payment - thank you" or "Online transfer") and link them, so they are neither
    spending nor income (editors). How many were linked and the pairs left unsure (as likely as another): link one with
    link_transaction."""
    u = who()
    r = guard(transfers.link_all, u)
    if isinstance(r, dict) and "possible" in r:
        r["possibleCount"], r["possible"] = len(r["possible"]), r["possible"][:50]
    return r


@server.tool(annotations=READ_ONLY)
def possible_transfers(limit: int = 50) -> list[dict]:
    """Debits and credits of the same amount in two of the household's accounts, at most two weeks apart, that are
    not linked as a transfer: each {out, in, why} (why it was not linked by itself), the nearest days first. Link
    one with link_transaction."""
    u = who()
    _need_role(u)
    return transfers.possible(u, limit=clamp(limit, 1, 200))


@server.tool(annotations=WRITES)
def link_transaction(transaction_id: int, with_transaction_id: Optional[int] = None) -> dict:
    """Link a transaction to the other half of its transfer (with_transaction_id: the same amount the other way, in
    another account), or, without with_transaction_id, show its transfer and the candidates. unlink_transaction
    takes a link away."""
    u = who()
    t = guard(model.transaction, u, transaction_id)
    if with_transaction_id is not None:
        guard(transfers.connect, u, t, with_transaction_id)
    other = transfers.other_half(u, t)
    return {"other": other, "candidates": [] if other else transfers.candidates(u, t)}


@server.tool(annotations=WRITES)
def unlink_transaction(transaction_id: int) -> dict:
    """Unlink a transaction's transfer, for good (the two are not linked again by themselves)."""
    u = who()
    guard(transfers.disconnect, u, guard(model.transaction, u, transaction_id))
    return {"unlinked": transaction_id}


@server.tool(annotations=READ_ONLY)
def transfer_rules() -> dict:
    """The transfer rules: in an account, a payee or bank's text with these words is a transfer with another account
    (source learned: made when such a transfer was found by itself)."""
    u = who()
    _need_role(u)
    return {"items": [transfers.rule_public(r, u) for r in transfers.rules(u)]}


@server.tool(annotations=ADDS)
def add_transfer_rule(account: str, pattern: str, other_account: str, days: int = 5) -> dict:
    """A transfer rule (editors): in account (id or name), a transaction whose payee or bank's text contains pattern
    is a transfer with other_account, its other half the same amount the other way within days. Links what it finds."""
    u = who()
    b = {"accountId": find_account(u, account)["id"], "otherId": find_account(u, other_account)["id"], "pattern": pattern, "days": days}
    r = guard(transfers.create_rule, u, b)
    return {**transfers.rule_public(r, u), "linked": transfers.link()}


@server.tool(annotations=DELETES)
def delete_transfer_rule(rule_id: int) -> dict:
    """Remove a transfer rule (its id, from transfer_rules). Transfers already linked stay linked. Ask first."""
    u = who()
    r = guard(transfers.rule, u, rule_id)
    guard(transfers.delete_rule, u, r)
    return {"deleted": r["pattern"]}


@server.tool(annotations=READ_ONLY)
def portfolio(account: Optional[str] = None) -> dict:
    """Every holding, priced with the latest quote: shares, price, value, the day's change, the gain over the cost
    basis; the totals; the same symbol added up across accounts; the allocation by kind. account: one account only."""
    u = who()
    _need_role(u)
    aid = find_account(u, account)["id"] if account else None
    return model.portfolio(u, aid)


@server.tool(annotations=READ_ONLY)
def get_quote(symbol: str) -> dict:
    """The latest price of a symbol as Yahoo Finance writes it (AAPL, VWCE.DE, BTC-USD, EURUSD=X), with the previous
    close and the day's change; asked of Yahoo when the one kept is more than 15 minutes old."""
    u = who()
    _need_role(u)
    s = guard(model.symbol, symbol)
    if not s:
        raise ToolError("Name a symbol")
    return quotes.quote(s)


@server.tool(annotations=ADDS)
def add_holding(account: str, symbol: Optional[str] = None, shares: float = 0, cost_basis: Optional[float] = None,
                name: Optional[str] = None, kind: Optional[str] = None, price: Optional[float] = None) -> dict:
    """Add a holding to a manual investment account (id or name): symbol as Yahoo Finance writes it, shares, and
    cost_basis (what was paid for all of them). Something without a symbol: a name and a price. kind: stock, etf,
    fund, bond, crypto, cash, option or other."""
    u = who()
    a = find_account(u, account)
    b = {"symbol": symbol, "shares": shares, "costBasis": cost_basis, "name": name, "kind": kind or "stock"}
    if price is not None:
        b["price"] = price
    h = guard(model.create_holding, u, a, b)
    if h["symbol"]:
        quotes.refresh(symbols=[h["symbol"]])
    model.revalue_manual_investments()
    return next((p for p in model.portfolio(u, a["id"])["items"] if p["id"] == h["id"]), {"id": h["id"]})


@server.tool(annotations=WRITES)
def update_holding(holding_id: int, shares: Optional[float] = None, cost_basis: Optional[float] = None,
                   price: Optional[float] = None, name: Optional[str] = None) -> dict:
    """Change a manual holding (its id, from portfolio): only what is given changes."""
    u = who()
    b = {k: v for k, v in {"shares": shares, "costBasis": cost_basis, "price": price, "name": name}.items() if v is not None}
    h = guard(model.update_holding, u, guard(model.holding, u, holding_id), b)
    model.revalue_manual_investments()
    return {"id": h["id"], "shares": float(h["shares"])}


@server.tool(annotations=DELETES)
def delete_holding(holding_id: int) -> dict:
    """Remove a manual holding (its id, from portfolio). Ask first."""
    u = who()
    h = guard(model.holding, u, holding_id)
    guard(model.delete_holding, u, h)
    model.revalue_manual_investments(h["account_id"])
    return {"deleted": h["symbol"] or h["name"]}


@server.tool(annotations=ADDS)
def add_account(name: str, kind: str, balance: float = 0, currency: Optional[str] = None, institution: Optional[str] = None,
                household: Optional[bool] = None, yearly_rate: Optional[float] = None, track: Optional[str] = None) -> dict:
    """A manual account: kind cash, investment, property (a house), vehicle (a car), other_asset, credit, loan or
    other_liability; track 'value' (its balance or value alone) or 'transactions' (its transactions move the balance;
    left out, transactions for cash and credit cards, the value for the rest); balance (for a house or a car, what it is worth; for a loan, what is owed); currency (the
    household's as left out); household true for the household's (editors), false for your own. yearly_rate: for a
    house or a car, the change a year in percent used to estimate its value between valuations (3, or -15)."""
    u = who()
    b = {"name": name, "kind": kind, "balance": balance, "currency": currency, "institution": institution, "track": track}
    if household is not None:
        b["household"] = household
    if yearly_rate is not None:
        b["details"] = {"yearlyRate": yearly_rate}
    return _acct(u, guard(model.create_account, u, b))


@server.tool(annotations=WRITES)
def update_account(account: str, name: Optional[str] = None, hidden: Optional[bool] = None, in_net_worth: Optional[bool] = None,
                   balance: Optional[float] = None, loan: Optional[str] = None, yearly_rate: Optional[float] = None,
                   track: Optional[str] = None, interest_rate: Optional[float] = None, monthly_payment: Optional[float] = None,
                   lowest_balance: Optional[float] = None) -> dict:
    """Change an account (id or name): its name, hidden, counted in the net worth, the balance (manual accounts),
    the loan against a house or a car (the loan's id or name; '' for none), its yearly change in percent, what
    is followed: track 'value' (the balance or value alone, its transactions out of sight) or 'transactions'; a
    loan's interest_rate (percent a year) and monthly_payment (for loan_payoff); a cash account's lowest_balance
    (cash_forecast warns under it)."""
    u = who()
    a = find_account(u, account)
    b = {}
    for k, v in (("name", name), ("hidden", hidden), ("inNetWorth", in_net_worth), ("balance", balance), ("track", track)):
        if v is not None:
            b[k] = v
    if loan is not None:
        b["loanId"] = find_account(u, loan)["id"] if loan else None
    details = {k: v for k, v in (("yearlyRate", yearly_rate), ("rate", interest_rate), ("payment", monthly_payment),
                                 ("floor", lowest_balance)) if v is not None}
    if details:
        b["details"] = details
    return _acct(u, guard(model.update_account, u, a, b))


@server.tool(annotations=WRITES)
def add_valuation(account: str, value: float, day: Optional[str] = None, note: Optional[str] = None) -> dict:
    """What a manual house, car or other asset (id or name) was worth on a day (YYYY-MM-DD, today as left out), e.g.
    from an appraisal or a price guide. Accounts from Monarch Money get their value from Monarch."""
    u = who()
    a = find_account(u, account)
    guard(model.add_valuation, u, a, {"value": value, "day": day, "note": note})
    return _acct(u, model.account(u, a["id"]))


@server.tool(annotations=READ_ONLY)
def bills(start: Optional[str] = None, end: Optional[str] = None) -> list:
    """The dates the household's recurring transactions fall on between start and end (YYYY-MM-DD; today to a month
    ahead as left out): day, name, amount (money out negative), the account, paid or not."""
    u = who()
    _need_role(u)
    s = guard(model.day, start) if start else dt.date.today()
    e = guard(model.day, end) if end else s + dt.timedelta(days=31)
    return recurring.bills(u, s, e)


@server.tool(annotations=READ_ONLY)
def recurring_transactions() -> dict:
    """The household's recurring transactions (bills, subscriptions, paychecks): name, account, amount, how often,
    the next date, the last payment, its flag (missed: no payment came when its pace says one should have; changed:
    the latest payment had another amount), what it costs a month (perMonth) and whether it is a subscription to a service
    (Netflix, Spotify, iCloud...); and found: what looks recurring in the transactions and is not in the list yet (a
    person adds it on the Recurring page)."""
    u = who()
    _need_role(u)
    return {"items": recurring.items(u), "found": recurring.found(u)}


@server.tool(annotations=READ_ONLY)
def loan_payoff(account: str, extra_per_month: float = 0) -> dict:
    """When a loan (id or name) is paid off and the interest still to pay, from its interest rate and monthly payment
    (set with update_account: interest_rate, monthly_payment; the payment is worked out from how the balance went
    down when not given); with extra_per_month, what paying that much more a month saves (months and interest).
    needs says what is missing (rate, payment)."""
    u = who()
    a = find_account(u, account)
    if a["is_asset"]:
        raise ToolError("A payoff is for what is owed: a loan or a card")
    return guard(payoff.payoff, u, a, extra_per_month or None)


@server.tool(annotations=READ_ONLY)
def cash_forecast(account: Optional[str] = None, days: int = 60) -> dict:
    """Where a cash account's balance goes over the coming days, from the recurring transactions kept for it (bills,
    subscriptions, paychecks) and the transfers it makes at a steady pace (a card paid monthly): each event with the
    balance after it, the lowest point, and whether it goes under the balance it should not go under (floor; zero
    without one). Everyday spending is not counted. account: its id or name; left out: the cash accounts that would go
    under in that time (warnings)."""
    u = who()
    _need_role(u)
    days = clamp(days, 7, 366)
    if not account:
        return {"warnings": forecast.warnings(u, days), "accounts": [{"id": a["id"], "name": a["name"]} for a in forecast.accounts(u)]}
    f = forecast.forecast(u, find_account(u, account), days)
    f.pop("points")
    return f


@server.tool(annotations=WRITES)
def sync_monarch(account: Optional[str] = None, years: int = 2) -> dict:
    """Admins: copy Monarch Money in now (accounts, balances, transactions, holdings) and say how it went; with
    account (id or name of one from Monarch), that account's transactions of the past years again (years: 2 as left
out; 0: all Monarch has). A long one (the first,
    with two years of transactions) goes on in the background: then running is true, and diagnostics or this tool
    again says how it goes."""
    u = who()
    need_admin()
    only = None
    if account:
        a = find_account(u, account)
        if a.get("source") != "monarch":
            raise ValueError("That account is not one from Monarch Money")
        only = a["id"]
    return monarch.start(u["id"], wait=45, only=only, years=max(0, min(int(years), 30)))


@server.tool(annotations=READ_ONLY)
def monarch_new_accounts() -> list[dict]:
    """Admins: the accounts Monarch Money reported that ioMoney did not know. Each waits, with its transactions, until
    an admin says whether it is new or an account here made again in Monarch under a new id (when its bank link broke);
    candidates are the accounts here it could be, likeliest first."""
    who()
    need_admin()
    return monarch.held()


@server.tool(annotations=WRITES)
def resolve_new_account(external_id: str, is_new: bool, account_id: int | None = None) -> dict:
    """Admins: say what a waiting Monarch account is (external_id from monarch_new_accounts): is_new true (it comes in
    as a new account), or false with account_id, the account here it is (that account takes the new id and its
    transactions are matched, so none is there twice). A sync starts right away."""
    u = who()
    need_admin()
    r = monarch.decide(external_id, "new" if is_new else "existing", account_id, u["id"])
    r["sync"] = monarch.start(u["id"], wait=45)
    return r
