"""The MCP server at /mcp: off until switched on, signed in with an app password, acting as that account; nothing for an account without a role here."""
import json

H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client, method, params=None, auth=None, id=1):
    r = client.post("/mcp", headers={**H, **(auth or {})}, json={"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})
    if r.status_code != 200:
        return r.status_code, r.text
    text = r.text
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        text = next(line[5:].strip() for line in text.splitlines() if line.startswith("data:"))
    return 200, json.loads(text)


def call(client, auth, tool, **args):
    code, msg = rpc(client, "tools/call", {"name": tool, "arguments": args}, auth)
    assert code == 200, msg
    res = msg["result"]
    if res.get("isError"):
        return {"error": res["content"][0]["text"]}
    if res.get("structuredContent") is not None:
        sc = res["structuredContent"]
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    content = res["content"]
    return json.loads(content[0]["text"]) if content else []


def test_mcp_money(client, as_user):
    from app import quotes
    from test_api import PRICES
    quotes.fetcher = lambda sym, rng: PRICES.get(sym) or {"chart": {"result": None, "error": {"description": "unknown"}}}
    secret = client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]
    auth = {"Authorization": f"Bearer {secret}"}
    assert rpc(client, "tools/list", auth=auth)[0] == 404  # off on a fresh install
    client.post("/api/server", json={"mcpEnabled": True})
    client.cookies.clear()
    assert rpc(client, "tools/list")[0] == 401
    names = {t["name"] for t in rpc(client, "tools/list", auth=auth)[1]["result"]["tools"]}
    assert {"overview", "net_worth_history", "search_transactions", "spending", "cash_flow", "categories", "update_transaction",
            "add_transaction", "portfolio", "get_quote", "add_holding", "update_holding", "delete_holding", "add_account",
            "update_account", "add_valuation", "bills", "recurring_transactions", "sync_monarch", "diagnostics", "rules", "add_rule", "test_rule", "update_rule",
            "delete_rule", "apply_rules", "link_transfers", "link_transaction", "unlink_transaction", "transfer_rules",
            "add_transfer_rule", "delete_transfer_rule", "monarch_new_accounts", "resolve_new_account"} <= names
    a = call(client, auth, "add_account", name="Checking", kind="cash", balance=1200)
    assert a["name"] == "Checking" and a["youCanChange"] is True and a["household"] is True
    from app import db
    db.ex("INSERT INTO mny_account_info (account_id, info) VALUES (%s, %s)",
          (a["id"], json.dumps({"accountNumber": "000123456789", "routingNumber": "043000096", "phone": "1-888-762-2265", "notes": "PIN 1234"})))
    assert call(client, auth, "bank_contact", account="Checking") == {"phone": "1-888-762-2265"}  # never the numbers or the notes
    assert "000123456789" not in json.dumps(call(client, auth, "overview"))
    car = call(client, auth, "add_account", name="Family car", kind="vehicle", balance=20000, yearly_rate=-15)
    assert car["details"]["yearlyRate"] == -15
    assert call(client, auth, "add_account", name="Car loan", kind="loan", balance=8000)["kind"] == "loan"
    assert call(client, auth, "update_account", account="family car", loan="Car loan")["equity"] == 12000
    assert call(client, auth, "add_valuation", account="Family car", value=19000, note="KBB")["balance"] == 19000
    t = call(client, auth, "add_transaction", account="Checking", amount=-25, merchant="Bakery", category="Groceries")
    assert t["amount"] == -25
    assert call(client, auth, "update_transaction", transaction_id=t["id"], category="Dining")["category"] == "Dining"
    s = call(client, auth, "search_transactions", query="bakery")
    assert s["total"] == 1 and s["items"][0]["category"] == "Dining"
    assert call(client, auth, "spending")["spent"] == 25
    assert call(client, auth, "add_account", name="Brokerage", kind="investment")["kind"] == "investment"
    h = call(client, auth, "add_holding", account="Brokerage", symbol="AAPL", shares=3, cost_basis=450)
    assert h["value"] == 600 and h["gain"] == 150
    assert call(client, auth, "portfolio")["value"] == 600
    assert call(client, auth, "get_quote", symbol="aapl")["price"] == 200
    assert call(client, auth, "update_holding", holding_id=h["id"], shares=4)["shares"] == 4
    assert call(client, auth, "delete_holding", holding_id=h["id"]) == {"deleted": "AAPL"}
    o = call(client, auth, "overview")
    assert o["netWorth"]["netWorth"] == 1200 - 25 + 19000 - 8000  # the checking account follows its transactions
    # rules: tried first, then kept and applied to what is there
    tried = call(client, auth, "test_rule", pattern="BAKE")
    assert tried["count"] == 1 and tried["edited"] == 1  # changed by hand above: a rule leaves it
    t2 = call(client, auth, "add_transaction", account="Checking", amount=-4, merchant="TST* CORNER BAKERY 0042")
    r = call(client, auth, "add_rule", pattern="corner bakery", rename_to="Corner Bakery", category="Dining")
    assert r["setMerchant"] == "Corner Bakery" and r["changed"] == 1  # t2, there before the rule
    t3 = call(client, auth, "add_transaction", account="Checking", amount=-6, merchant="TST* CORNER BAKERY 0042")
    assert t3["merchant"] == "Corner Bakery" and t3["category"] == "Dining"  # a new one goes through the rules
    assert [x["pattern"] for x in call(client, auth, "rules")["items"]] == ["corner bakery"]
    assert call(client, auth, "update_rule", rule_id=r["id"], category="Coffee", apply_now=True)["changed"] == 2
    assert {x["category"] for x in call(client, auth, "search_transactions", query="corner")["items"]} == {"Coffee"}
    assert t2["id"] and call(client, auth, "delete_rule", rule_id=r["id"]) == {"deleted": "corner bakery"}
    assert call(client, auth, "apply_rules") == {"changed": 0}
    # an account followed by its value alone: no transactions to add, and its own are out of sight
    assert call(client, auth, "update_account", account="Checking", track="value")["track"] == "value"
    assert "error" in call(client, auth, "add_transaction", account="Checking", amount=-1)
    assert call(client, auth, "search_transactions", query="bakery")["total"] == 0
    assert call(client, auth, "update_account", account="Checking", track="transactions")["track"] == "transactions"
    assert len(call(client, auth, "net_worth_history", days=30)) >= 1
    assert "error" in call(client, auth, "update_account", account="nothing like it", name="x")
    assert call(client, auth, "diagnostics")["database"]["accounts"] == 4
    assert "error" in call(client, auth, "sync_monarch") or call(client, auth, "sync_monarch")["ok"] is False
    assert call(client, auth, "monarch_new_accounts") == []
    assert "error" in call(client, auth, "resolve_new_account", external_id="nope", is_new=True)
    # a viewer reads and changes nothing
    from conftest import sign_in
    sign_in(client, "alex")
    as_user("viv", "viewer")
    vauth = {"Authorization": "Bearer " + client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]}
    client.cookies.clear()
    assert call(client, vauth, "overview")["netWorth"]["netWorth"] == 1200 - 35 + 11000
    assert "error" in call(client, vauth, "add_account", name="Mine", kind="cash")
    assert "error" in call(client, vauth, "sync_monarch")
    assert "error" in call(client, vauth, "monarch_new_accounts")
    quotes.fetcher = None
