"""The MCP server instance (iosuite_shared.mcp: who is asking, the annotations, the limits) and what every tool module
shares: finding an account."""
from mcp.server.mcpserver.exceptions import ToolError

from iosuite_shared import mcp as shared_mcp
from iosuite_shared.mcp import ADDS, DELETES, READ_ONLY, UPDATES, WRITES, clamp, current_user, need_admin, who

from app import __version__, config, model

# what the tool modules take from here: the suite's pieces (iosuite_shared.mcp) and ioMoney's own helpers
__all__ = ["server", "ADDS", "DELETES", "READ_ONLY", "UPDATES", "WRITES", "clamp", "current_user", "need_admin", "who",
           "find_account", "guard", "link"]

server = shared_mcp.make_server(
    config.APP, "ioMoney", __version__,
    instructions=(
        "The household's finances (ioMoney): accounts (bank, cards, investments, loans, and the house and the cars, "
        "which are accounts too, so the net worth is one sum), their transactions, the portfolio with live quotes, and "
        "the bills to come. Start with overview: the net worth by kind and the accounts. Amounts are in the account's "
        "currency; totals are in the household's currency (overview says which). A transaction's amount is negative for "
        "money out. Most of it comes from Monarch Money (synced every few hours; sync_monarch for admins); a manual "
        "account, its transactions and its holdings are kept here. Transfers between the household's own accounts are "
        "left out of spending. A symbol is as Yahoo Finance writes it (AAPL, VWCE.DE, BTC-USD, EURUSD=X). "
        "Ask before deleting anything."
    ),
)


def link(path: str) -> str | None:
    return f"{config.PUBLIC_URL}/#/{path}" if config.PUBLIC_URL else None


def guard(fn, *a, **kw):
    """The model's refusals as tool errors the assistant can read."""
    try:
        return fn(*a, **kw)
    except (model.Forbidden, model.NotFound, ValueError) as e:
        raise ToolError(str(e))


def find_account(u: dict, ref, hidden: bool = True) -> dict:
    """An account by id, or by a name that matches exactly one."""
    s = str(ref).strip()
    if not s:
        raise ToolError("Name an account (its id or its name)")
    rows = model.accounts(u, hidden=hidden)
    found = [a for a in rows if str(a["id"]) == s] or [a for a in rows if a["name"].lower() == s.lower()] or \
        [a for a in rows if s.lower() in f"{a['name']} {a['institution'] or ''}".lower()]
    if len(found) != 1:
        raise ToolError((f"No account matches '{s}'. " if not found else f"'{s}' matches several accounts. ")
                        + "The accounts: " + ("; ".join(f"{a['name']} (id {a['id']})" for a in rows[:40]) or "none yet"))
    return found[0]
