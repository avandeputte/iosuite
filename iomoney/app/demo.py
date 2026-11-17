"""Demo data (iosuite_shared.demo): the Calloways' finances, entered by hand (no Monarch Money). A checking and a savings
account, a credit card, a retirement account and a college fund with holdings, the house and its mortgage, the car
and its loan. Six months of transactions (two salaries, the mortgage, the bills, groceries, the children's lessons,
streaming subscriptions, the card paid off from checking), so the spending, cash flow, recurring and net worth pages
have something to show, with the balances day by day. Every name, number and amount is made up."""
import datetime as dt
import random
from decimal import Decimal

from iosuite_shared import demo

from app import categories, model, recurring, users

DAYS = 182  # how far back the transactions go
BANK = "Cascade Valley Credit Union"  # made up, as is every institution here


def _month_days(day_of_month: int):
    """Every date in the last DAYS days that falls on that day of the month (or the month's last day)."""
    start, today = demo.day(-DAYS), demo.today()
    d = start.replace(day=1)
    while d <= today:
        last = ((d.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)).day
        x = d.replace(day=min(day_of_month, last))
        if start <= x <= today:
            yield x
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def seed(people: dict) -> None:
    m = users.get(people["morgan"]["id"])
    rnd = random.Random(42)
    start = demo.day(-DAYS)

    def acct(**b):
        return model.create_account(m, {"household": True, **b})

    checking = acct(name="Joint checking", institution=BANK, kind="cash", subtype="checking", mask="4821", balance="6200.00",
                    details={"floor": 1500})
    savings = acct(name="Rainy day savings", institution=BANK, kind="cash", subtype="savings", mask="7730", balance="18500.00")
    card = acct(name="Rewards Visa", institution="Evergreen Card Services", kind="credit", subtype="credit_card", mask="0094",
                balance="1200.00")
    retire = acct(name="Retirement (401k)", institution="Summit Retirement Plans", kind="investment", subtype="401k", balance="0")
    college = acct(name="Ava and Theo college fund", institution="Summit Retirement Plans", kind="investment", subtype="529", balance="0")
    house_loan = acct(name="Mortgage", institution=BANK, kind="loan", subtype="mortgage", balance="286400.00",
                      details={"rate": 4.125, "payment": 2150})
    car_loan = acct(name="Car loan", institution=BANK, kind="loan", subtype="auto", balance="9800.00",
                    details={"rate": 3.9, "payment": 410})
    house = acct(name="42 Juniper Lane", kind="property", balance="512000.00", loanId=house_loan["id"],
                 details={"address": f"{demo.HOME['street']}, {demo.HOME['city']}, {demo.HOME['region']}", "boughtOn": "2016-06-15",
                          "boughtFor": 389000, "yearlyRate": 3.5})
    car = acct(name="Family car", kind="vehicle", balance="21500.00", loanId=car_loan["id"],
               details={"year": "2023", "make": "Aurora Motors", "model": "Wayfarer Hybrid", "mileage": "28400",
                        "boughtOn": demo.day(-1100).isoformat(), "boughtFor": 32500, "yearlyRate": -12})
    m_info = {"accountNumber": "000123454821", "routingNumber": "000000000", "phone": "+1 541 555 0170",
              "website": "https://bank.example.com", "notes": "Demo account: all numbers are made up."}
    model.set_account_info(m, checking, m_info)

    for name, grp in [("Paychecks", "Income"), ("Groceries", "Food & Dining"), ("Restaurants", "Food & Dining"),
                      ("Coffee Shops", "Food & Dining"), ("Mortgage", "Housing"), ("Electric", "Bills & Utilities"),
                      ("Water", "Bills & Utilities"), ("Internet", "Bills & Utilities"), ("Phone", "Bills & Utilities"),
                      ("Gas", "Auto & Transport"), ("Auto Payment", "Auto & Transport"), ("Kids Activities", "Children"),
                      ("Streaming", "Entertainment"), ("Pets", "Pets"), ("Shopping", "Shopping"), ("Medical", "Health"),
                      ("Insurance", "Insurance"), ("Credit Card Payment", "Transfers"), ("Transfer", "Transfers")]:
        try:
            categories.add(m, {"name": name, "group": grp})
        except Exception:  # noqa: BLE001 - there already
            pass

    txs = []  # (account, day, amount, merchant, category, group)

    def add(a, d, amount, merchant, cat, grp):
        txs.append((a, d, Decimal(str(amount)).quantize(Decimal("0.01")), merchant, cat, grp))

    for d in _month_days(1):
        add(checking, d, -2150.00, "Cascade Valley CU Mortgage", "Mortgage", "Housing")
    for d in _month_days(15):
        add(checking, d, 2452.30, "Greenline Studio Payroll", "Paychecks", "Income")
        add(checking, d, -410.00, "Cascade Valley CU Auto Loan", "Auto Payment", "Auto & Transport")
    for d in _month_days(28):
        add(checking, d, 2452.30, "Greenline Studio Payroll", "Paychecks", "Income")
        add(checking, d, 2318.12, "Juniper Hill School District", "Paychecks", "Income")
        add(checking, d, -500.00, "Transfer to savings", "Transfer", "Transfers")
        add(savings, d, 500.00, "Transfer from checking", "Transfer", "Transfers")
    for d in _month_days(5):
        add(checking, d, -238.00, "Harborline Insurance", "Insurance", "Insurance")
        add(checking, d, -420.00, "Bright Minds Afterschool", "Kids Activities", "Children")
    for d in _month_days(8):
        add(checking, d, -round(rnd.uniform(85, 160), 2), "Willamette Power", "Electric", "Bills & Utilities")
        add(checking, d, -79.99, "Riverlink Fiber", "Internet", "Bills & Utilities")
    for d in _month_days(20):
        add(checking, d, -round(rnd.uniform(40, 70), 2), "City of Eugene Water", "Water", "Bills & Utilities")
        add(card, d, -95.00, "Harmony Music School", "Kids Activities", "Children")
    for d in _month_days(3):
        add(card, d, -15.49, "StreamFlix", "Streaming", "Entertainment")
        add(card, d, -10.99, "Tunewave Music", "Streaming", "Entertainment")
        add(card, d, -120.00, "Mobilia Wireless", "Phone", "Bills & Utilities")
    for d in _month_days(12):
        add(card, d, -7.99, "KidsPlay Games", "Streaming", "Entertainment")

    d = start
    while d <= demo.today():
        wd = d.weekday()
        if wd == 5:
            add(card, d, -round(rnd.uniform(140, 230), 2), rnd.choice(["Fresh Basket Market", "Valley Co-op Grocery"]), "Groceries", "Food & Dining")
        if wd == 2 and rnd.random() < 0.8:
            add(card, d, -round(rnd.uniform(25, 60), 2), "Fresh Basket Market", "Groceries", "Food & Dining")
        if wd in (4, 6) and rnd.random() < 0.55:
            add(card, d, -round(rnd.uniform(38, 95), 2), rnd.choice(["Luigi's Pizzeria", "Taqueria Sol", "Golden Lotus", "The Burger Barn"]),
                "Restaurants", "Food & Dining")
        if wd < 5 and rnd.random() < 0.3:
            add(card, d, -round(rnd.uniform(4.5, 9), 2), "Bean There Coffee", "Coffee Shops", "Food & Dining")
        if wd == 0 and rnd.random() < 0.7:
            add(card, d, -round(rnd.uniform(42, 68), 2), "Pacific Fuel", "Gas", "Auto & Transport")
        if rnd.random() < 0.06:
            add(card, d, -round(rnd.uniform(20, 140), 2), rnd.choice(["ShopRight Online", "Target Corner", "BookNook"]), "Shopping", "Shopping")
        d += dt.timedelta(days=1)
    for n, (amount, merchant, cat, grp) in enumerate([(-65.00, "Riverside Youth Soccer", "Kids Activities", "Children"),
                                                      (-48.20, "Pawsome Pet Supply", "Pets", "Pets"),
                                                      (-180.00, "Willow Creek Animal Clinic", "Pets", "Pets"),
                                                      (-35.00, "Bright Smiles Dental", "Medical", "Health"),
                                                      (-129.00, "Science Corner", "Shopping", "Shopping")]):
        add(card, demo.day(-150 + n * 31), amount, merchant, cat, grp)

    # the card is paid off from checking every month: what was spent on it the month before
    for d in _month_days(25):
        spent = -sum(t[2] for t in txs if t[0] is card and t[2] < 0 and d - dt.timedelta(days=31) < t[1] <= d - dt.timedelta(days=3))
        if spent > 0:
            add(checking, d, -spent, "Evergreen Card Payment", "Credit Card Payment", "Transfers")
            add(card, d, spent, "Payment, thank you", "Credit Card Payment", "Transfers")

    txs.sort(key=lambda t: t[1])
    opening = {checking["id"]: Decimal("6200.00"), savings["id"]: Decimal("18500.00"), card["id"]: Decimal("-1200.00")}
    for a, d, amount, merchant, cat, grp in txs:
        model.create_transaction(m, a, {"day": d.isoformat(), "amount": str(amount), "merchant": merchant, "category": cat, "group": grp})

    # the balances day by day, from the opening balance and the transactions
    for a in (checking, savings, card):
        bal = opening[a["id"]]
        by_day: dict = {}
        for t in txs:
            if t[0] is a:
                by_day[t[1]] = by_day.get(t[1], Decimal(0)) + t[2]
        d = start
        while d <= demo.today():
            bal += by_day.get(d, Decimal(0))
            model.set_balance(a["id"], d, -bal if a["kind"] == "credit" else bal, "manual")
            d += dt.timedelta(days=1)

    # the values that move slowly, week by week
    def trend(a, now_value, yearly_pct, wobble=0.0):
        n = DAYS // 7
        for i in range(n, -1, -1):
            d = demo.day(-i * 7)
            v = now_value * (1 + yearly_pct / 100) ** (-i * 7 / 365) * (1 + rnd.uniform(-wobble, wobble))
            model.set_balance(a["id"], d, Decimal(str(round(v, 2))), "manual")

    trend(house, 512000, 3.5)
    trend(car, 21500, -12)
    trend(house_loan, 286400, -2.4)
    trend(car_loan, 9800, -45)
    for a, rows in ((retire, [("VTI", "etf", "Total US stock market ETF", 410, 268.40), ("VXUS", "etf", "International stock ETF", 520, 64.10),
                              ("BND", "etf", "US bond market ETF", 300, 72.80)]),
                    (college, [("VT", "etf", "Total world stock ETF", 160, 118.20)])):
        total = 0.0
        for sym, kind, name, shares, price in rows:
            model.create_holding(m, a, {"symbol": sym, "kind": kind, "name": name, "shares": shares, "price": price,
                                        "costBasis": round(shares * price * 0.82, 2)})
            total += shares * price
        trend(a, total, 9, 0.02)
    model.revalue_manual_investments()

    for name, pattern, account, amount, freq, day, cat, sub in [
        ("Mortgage", "cascade valley cu mortgage", checking, "2150.00", "monthly", 1, "Mortgage", False),
        ("StreamFlix", "streamflix", card, "15.49", "monthly", 3, "Streaming", True),
        ("Tunewave Music", "tunewave", card, "10.99", "monthly", 3, "Streaming", True),
        ("Internet", "riverlink fiber", checking, "79.99", "monthly", 8, "Internet", False),
        ("Piano lessons", "harmony music school", card, "95.00", "monthly", 20, "Kids Activities", False),
    ]:
        last = max(x for x in _month_days(day))
        recurring.create(m, {"name": name, "pattern": pattern, "accountId": account["id"], "flow": "out", "amount": amount,
                             "frequency": freq, "day": last.isoformat(), "category": cat, "subscription": sub})
    model.create_rule(m, {"pattern": "bean there", "setMerchant": "Bean There Coffee", "setCategory": "Coffee Shops"})
