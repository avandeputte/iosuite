"""MariaDB access: one short connection per unit of work, and the schema (created at start)."""

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import db as shared_db, schema

SCHEMA_VERSION = 1  # recorded in mny_schema_version; the tables are made as SCHEMA says (pre-release: no upgrade steps)
PREFIX = "mny"

# Every table is mny_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
# Amounts are DECIMAL, never floats.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS mny_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite-shared, app/auth.py)
    # An account is anything with a value: a bank account, a card, a brokerage account, a loan, and also the house and
    # the cars (kind property / vehicle), so the net worth is one sum. owner_id NULL: the household's (everyone with a
    # role here sees it); otherwise the private account of that person. source: manual (kept here) or monarch (Monarch
    # Money's, refreshed by the sync; external_id is Monarch's id). balance: what it holds or is worth, or what is owed
    # on a card or a loan (a positive number; is_asset says which). details: JSON, what a house or a car is (address,
    # year, make, model, VIN, mileage, bought on, bought for) and yearly_rate, the change a year used to estimate its
    # value between two valuations (3 for a house going up 3% a year, -15 for a car). loan_id: the loan or mortgage
    # against a house or a car, for its equity.
    """CREATE TABLE IF NOT EXISTS mny_accounts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        source VARCHAR(16) NOT NULL DEFAULT 'manual',
        external_id VARCHAR(64) NULL,
        name VARCHAR(255) NOT NULL,
        institution VARCHAR(255) NULL,
        kind VARCHAR(24) NOT NULL,
        subtype VARCHAR(64) NULL,
        is_asset TINYINT(1) NOT NULL DEFAULT 1,
        balance DECIMAL(18,2) NOT NULL DEFAULT 0,
        currency CHAR(3) NOT NULL DEFAULT 'USD',
        balance_at DATETIME NULL,
        in_net_worth TINYINT(1) NOT NULL DEFAULT 1,
        hidden TINYINT(1) NOT NULL DEFAULT 0,
        closed TINYINT(1) NOT NULL DEFAULT 0,
        mask VARCHAR(8) NULL,
        details MEDIUMTEXT NULL,
        loan_id INT NULL,
        track VARCHAR(12) NOT NULL DEFAULT 'transactions',
        position INT NOT NULL DEFAULT 0,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_mny_accounts_ext (source, external_id),
        KEY idx_mny_accounts_owner (owner_id, kind)
    )""",
    # an account's value day by day (the net worth over time): what the sync saw, a valuation typed in for the house
    # or a car (note), or the day's estimate from its yearly rate. One row per account and day; the last word wins.
    """CREATE TABLE IF NOT EXISTS mny_balances (
        account_id INT NOT NULL,
        day DATE NOT NULL,
        balance DECIMAL(18,2) NOT NULL,
        source VARCHAR(16) NOT NULL DEFAULT 'sync',
        note VARCHAR(255) NULL,
        PRIMARY KEY (account_id, day),
        KEY idx_mny_balances_day (day),
        CONSTRAINT fk_mny_balances_account FOREIGN KEY (account_id) REFERENCES mny_accounts(id) ON DELETE CASCADE
    )""",
    # transactions: amount < 0 money out, > 0 money in (as Monarch has them). merchant is the name to show, description
    # the bank's own text. edited: category, notes or hidden were changed here, and the sync leaves them as they are.
    # words: everything a search looks in, in lower case.
    """CREATE TABLE IF NOT EXISTS mny_transactions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        account_id INT NOT NULL,
        source VARCHAR(16) NOT NULL DEFAULT 'manual',
        external_id VARCHAR(64) NULL,
        day DATE NOT NULL,
        amount DECIMAL(18,2) NOT NULL,
        merchant VARCHAR(255) NULL,
        description VARCHAR(255) NULL,
        category VARCHAR(128) NULL,
        category_group VARCHAR(128) NULL,
        notes TEXT NULL,
        tags TEXT NULL,
        pending TINYINT(1) NOT NULL DEFAULT 0,
        hidden TINYINT(1) NOT NULL DEFAULT 0,
        recurring TINYINT(1) NOT NULL DEFAULT 0,
        edited TINYINT(1) NOT NULL DEFAULT 0,
        words TEXT NOT NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_mny_transactions_ext (source, external_id),
        KEY idx_mny_transactions_day (day),
        KEY idx_mny_transactions_account (account_id, day),
        CONSTRAINT fk_mny_transactions_account FOREIGN KEY (account_id) REFERENCES mny_accounts(id) ON DELETE CASCADE
    )""",
    # what an investment account holds: shares of a symbol (as Yahoo Finance names it: AAPL, VWCE.DE, BTC-USD).
    # cost_basis: what was paid for all of them, when known. price: the price to use when there is no quote (a fund
    # without a symbol, or Monarch's last closing price), with price_at.
    """CREATE TABLE IF NOT EXISTS mny_holdings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        account_id INT NOT NULL,
        source VARCHAR(16) NOT NULL DEFAULT 'manual',
        external_id VARCHAR(64) NULL,
        symbol VARCHAR(32) NULL,
        name VARCHAR(255) NULL,
        kind VARCHAR(24) NOT NULL DEFAULT 'stock',
        shares DECIMAL(24,8) NOT NULL DEFAULT 0,
        cost_basis DECIMAL(18,2) NULL,
        price DECIMAL(18,6) NULL,
        price_at DATETIME NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_mny_holdings_ext (source, external_id),
        KEY idx_mny_holdings_account (account_id),
        KEY idx_mny_holdings_symbol (symbol),
        CONSTRAINT fk_mny_holdings_account FOREIGN KEY (account_id) REFERENCES mny_accounts(id) ON DELETE CASCADE
    )""",
    # the last quote of each symbol held (app/quotes.py), and its closing prices day by day
    """CREATE TABLE IF NOT EXISTS mny_quotes (
        symbol VARCHAR(32) PRIMARY KEY,
        name VARCHAR(255) NULL,
        currency CHAR(3) NULL,
        price DECIMAL(18,6) NULL,
        previous_close DECIMAL(18,6) NULL,
        market_time DATETIME NULL,
        fetched_at DATETIME NULL,
        error VARCHAR(255) NULL
    )""",
    """CREATE TABLE IF NOT EXISTS mny_prices (
        symbol VARCHAR(32) NOT NULL,
        day DATE NOT NULL,
        close DECIMAL(18,6) NOT NULL,
        PRIMARY KEY (symbol, day)
    )""",
    # the recurring transactions the household keeps (app/recurring.py): a bill or money that comes in regularly, found
    # in the transactions or added by hand. pattern: words its payee or bank's text has; account_id: that account only
    # (none: any); flow: out or in; amount: the usual one (positive; approximate: it varies); frequency: weekly,
    # biweekly, semimonthly, monthly, quarterly, yearly; day: a day it fell on (the dates follow from it).
    """CREATE TABLE IF NOT EXISTS mny_recurring (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        pattern VARCHAR(255) NOT NULL,
        account_id INT NULL,
        flow VARCHAR(3) NOT NULL DEFAULT 'out',
        amount DECIMAL(18,2) NOT NULL,
        approximate TINYINT(1) NOT NULL DEFAULT 0,
        frequency VARCHAR(16) NOT NULL DEFAULT 'monthly',
        day DATE NOT NULL,
        category VARCHAR(128) NULL,
        subscription TINYINT(1) NOT NULL DEFAULT 0,
        source VARCHAR(8) NOT NULL DEFAULT 'hand',
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_mny_recurring_account FOREIGN KEY (account_id) REFERENCES mny_accounts(id) ON DELETE CASCADE
    )""",
    # what was found to look recurring and a person said is not: account:flow:pattern, not offered again
    """CREATE TABLE IF NOT EXISTS mny_recurring_nots (
        k VARCHAR(300) PRIMARY KEY,
        at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    # a flag on a recurring transaction (missed: none seen since its payment of that day; changed: the payment of that
    # day had another amount) someone looked at and set aside: not shown again for that day
    """CREATE TABLE IF NOT EXISTS mny_recurring_ok (
        recurring_id INT NOT NULL,
        kind VARCHAR(8) NOT NULL,
        day DATE NOT NULL,
        at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (recurring_id, kind, day),
        CONSTRAINT fk_mny_recurring_ok_item FOREIGN KEY (recurring_id) REFERENCES mny_recurring(id) ON DELETE CASCADE
    )""",
    # the household's categories (app/categories.py): those added here, and those renamed or regrouped here, with
    # their group. Those only in the transactions (Monarch's) are categories too, without a row.
    """CREATE TABLE IF NOT EXISTS mny_categories (
        name VARCHAR(128) PRIMARY KEY,
        grp VARCHAR(128) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    # a category renamed, merged into another or deleted here: what a sync brings in under the old name goes under the
    # new one (none: no category)
    """CREATE TABLE IF NOT EXISTS mny_category_alias (
        old VARCHAR(128) PRIMARY KEY,
        new VARCHAR(128) NULL
    )""",
    # the household's rules for transactions: when the payee or the bank's text matches (contains, is, starts with;
    # field: payee, bank's text, or either), optionally only in one account and between two amounts (money out or in,
    # as a positive number), the payee is renamed, the category set, or the transaction hidden. In position order;
    # for each of the three, the first rule that matches and sets it wins. A transaction changed by hand (edited) is
    # left as it is.
    """CREATE TABLE IF NOT EXISTS mny_rules (
        id INT AUTO_INCREMENT PRIMARY KEY,
        position INT NOT NULL DEFAULT 0,
        enabled TINYINT(1) NOT NULL DEFAULT 1,
        field VARCHAR(16) NOT NULL DEFAULT 'either',
        how VARCHAR(16) NOT NULL DEFAULT 'contains',
        pattern VARCHAR(255) NOT NULL,
        account_id INT NULL,
        flow VARCHAR(8) NULL,
        amount_min DECIMAL(18,2) NULL,
        amount_max DECIMAL(18,2) NULL,
        set_merchant VARCHAR(255) NULL,
        set_category VARCHAR(128) NULL,
        set_hidden TINYINT(1) NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_mny_rules_position (position),
        CONSTRAINT fk_mny_rules_account FOREIGN KEY (account_id) REFERENCES mny_accounts(id) ON DELETE CASCADE
    )""",
    # transfers between the household's own accounts: the money out of one account (out_id) and the same money into
    # another (in_id), linked (app/transfers.py). how: auto (found by the amount, the days and the payee), rule (a
    # transfer rule found it) or hand. A linked pair is neither spending nor income.
    """CREATE TABLE IF NOT EXISTS mny_transfers (
        out_id INT NOT NULL PRIMARY KEY,
        in_id INT NOT NULL,
        how VARCHAR(8) NOT NULL DEFAULT 'auto',
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_mny_transfers_in (in_id),
        CONSTRAINT fk_mny_transfers_out FOREIGN KEY (out_id) REFERENCES mny_transactions(id) ON DELETE CASCADE,
        CONSTRAINT fk_mny_transfers_in FOREIGN KEY (in_id) REFERENCES mny_transactions(id) ON DELETE CASCADE
    )""",
    # two transactions unlinked by hand: never linked again by themselves
    """CREATE TABLE IF NOT EXISTS mny_transfer_nots (
        out_id INT NOT NULL,
        in_id INT NOT NULL,
        PRIMARY KEY (out_id, in_id),
        CONSTRAINT fk_mny_transfer_nots_out FOREIGN KEY (out_id) REFERENCES mny_transactions(id) ON DELETE CASCADE,
        CONSTRAINT fk_mny_transfer_nots_in FOREIGN KEY (in_id) REFERENCES mny_transactions(id) ON DELETE CASCADE
    )""",
    # transfer rules: a transaction in account_id whose payee or bank's text contains pattern is a transfer with
    # other_id, its other half the same amount the other way within days. source: learned (made when a transfer was
    # found by itself, so the next one is found surely) or hand.
    """CREATE TABLE IF NOT EXISTS mny_transfer_rules (
        id INT AUTO_INCREMENT PRIMARY KEY,
        account_id INT NOT NULL,
        pattern VARCHAR(255) NOT NULL,
        other_id INT NOT NULL,
        days INT NOT NULL DEFAULT 5,
        source VARCHAR(8) NOT NULL DEFAULT 'hand',
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_mny_transfer_rules (account_id, other_id, pattern),
        CONSTRAINT fk_mny_transfer_rules_account FOREIGN KEY (account_id) REFERENCES mny_accounts(id) ON DELETE CASCADE,
        CONSTRAINT fk_mny_transfer_rules_other FOREIGN KEY (other_id) REFERENCES mny_accounts(id) ON DELETE CASCADE
    )""",
    # a transaction checked against the bank's statement: reconciled (by whom, when); the sync leaves it as it is
    """CREATE TABLE IF NOT EXISTS mny_reconciled (
        transaction_id INT PRIMARY KEY,
        by_user INT NULL,
        at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_mny_reconciled_tx FOREIGN KEY (transaction_id) REFERENCES mny_transactions(id) ON DELETE CASCADE
    )""",
    # what the household keeps about an account to deal with its bank (account and routing numbers, IBAN, customer
    # service): a JSON object of known fields, apart from the account so that it goes into no list, summary or MCP tool
    """CREATE TABLE IF NOT EXISTS mny_account_info (
        account_id INT PRIMARY KEY,
        info MEDIUMTEXT NOT NULL,
        updated_by INT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_mny_account_info_account FOREIGN KEY (account_id) REFERENCES mny_accounts(id) ON DELETE CASCADE
    )""",
    # an account Monarch Money reports that ioMoney did not know, after the first sync: held until an admin says whether
    # it is new or the new id of an account here (one deleted and made again in Monarch when its bank link broke);
    # decision 'new' lets the next sync add it. Its transactions wait with it.
    """CREATE TABLE IF NOT EXISTS mny_monarch_new (
        external_id VARCHAR(64) PRIMARY KEY,
        data LONGTEXT NOT NULL,
        first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        decision VARCHAR(8) NULL,
        decided_by INT NULL
    )""",
    # an account here given a new Monarch id: the next sync matches the transactions Monarch sends under the new
    # account with the ones kept under the old (same amount, a day or two apart), so none is there twice
    """CREATE TABLE IF NOT EXISTS mny_monarch_moves (
        account_id INT PRIMARY KEY,
        old_external_id VARCHAR(64) NULL,
        new_external_id VARCHAR(64) NOT NULL,
        moved_by INT NULL,
        moved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        done_at DATETIME NULL,
        matched INT NOT NULL DEFAULT 0,
        CONSTRAINT fk_mny_monarch_moves_account FOREIGN KEY (account_id) REFERENCES mny_accounts(id) ON DELETE CASCADE
    )""",
    # what Monarch Money said of an account's link to its bank at the last sync (times in UTC): linked, the account is
    # kept up to date from a bank (not typed in at Monarch, not a value Monarch looks up, its updates not turned off);
    # when Monarch last heard from the bank, whether the bank sign-in there needs fixing, when the link was cut. quiet:
    # someone asked not to flag this account (the syncs leave it as it is)
    """CREATE TABLE IF NOT EXISTS mny_bank_links (
        account_id INT PRIMARY KEY,
        linked TINYINT(1) NOT NULL DEFAULT 0,
        refreshed_at DATETIME NULL,
        update_required TINYINT(1) NOT NULL DEFAULT 0,
        disconnected_at DATETIME NULL,
        institution_status VARCHAR(32) NULL,
        seen_at DATETIME NOT NULL,
        quiet TINYINT(1) NOT NULL DEFAULT 0,
        CONSTRAINT fk_mny_bank_links_account FOREIGN KEY (account_id) REFERENCES mny_accounts(id) ON DELETE CASCADE
    )""",
    # each Monarch Money sync: when, how it went, what came in
    """CREATE TABLE IF NOT EXISTS mny_syncs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        started_at DATETIME NOT NULL,
        finished_at DATETIME NULL,
        ok TINYINT(1) NOT NULL DEFAULT 0,
        message VARCHAR(1024) NULL,
        accounts INT NOT NULL DEFAULT 0,
        transactions INT NOT NULL DEFAULT 0,
        holdings INT NOT NULL DEFAULT 0,
        by_user INT NULL,
        KEY idx_mny_syncs_started (started_at)
    )""",
]

def connect(database: str | None = None):
    return pymysql.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER, password=config.DB_PASSWORD,
                           database=database if database is not None else config.DB_NAME, charset="utf8mb4",
                           cursorclass=DictCursor, autocommit=True, connect_timeout=8)


# The pool, the transaction nested calls share, and q / one / ex / many are the suite's (iosuite_shared.db.Database):
# a statement on its own is one round trip, tx() is one transaction (committed on success, rolled back on error), and
# q / one / ex inside a `with tx():` block run in it.
_db = shared_db.Database(connect)
tx, q, one, ex, many = _db.tx, _db.q, _db.one, _db.ex, _db.many


def marks(n: int) -> str:
    return ",".join(["%s"] * n) if n else "NULL"


def get_setting(k: str, default: str | None = None) -> str | None:
    r = one("SELECT value FROM mny_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM mny_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO mny_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


def schema_version() -> int:
    with tx() as con, con.cursor() as cur:
        return schema.current_version(cur, PREFIX)


def ensure_database() -> None:
    """Create the database when it is missing and the user may (CREATE privilege); otherwise leave it to the admin."""
    try:
        connect().close()
        return
    except pymysql.err.OperationalError as e:
        if e.args[0] != 1049:  # anything but "unknown database"
            raise
    con = connect(database="")
    try:
        with con.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        con.close()


def migrate() -> None:
    ensure_database()
    with tx() as con, con.cursor() as cur:
        for stmt in SCHEMA:
            cur.execute(stmt + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
        schema.ensure_version_table(cur, PREFIX)
        schema.record_version(cur, PREFIX, SCHEMA_VERSION)


def reset_all() -> None:
    """Tests only: drop every table of this app (mny_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_"):
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
