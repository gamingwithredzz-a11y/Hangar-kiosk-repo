import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo


# ============================================================
# THE HANGAR KIOSK BACKEND
# TABLE-SPECIFIC TAP-TO-PAY VERSION
# ============================================================

BASE_DIR = Path(os.environ.get("HANGAR_BASE_DIR", ".")).resolve()

DB_PATH = Path(
    os.environ.get(
        "DATABASE_PATH",
        str(BASE_DIR / "hangar.db")
    )
)

API_KEY = os.environ.get("HANGAR_API_KEY", "")
OWNER_ACCESS_CODE = os.environ.get("HANGAR_OWNER_CODE", "")

PACIFIC = ZoneInfo("America/Los_Angeles")


# ============================================================
# MENU
# ============================================================

MENU = [
    ("wings_magnum_jerk", "12 Piece Wings - Magnum Jerk", 900),
    ("wings_hot_honey", "12 Piece Wings - Hot Honey", 900),
    ("wings_buffalo", "12 Piece Wings - Buffalo", 900),

    ("beef_tacos", "Beef Taco Platter", 650),
    ("chicken_tacos", "Chicken Taco Platter", 750),
    ("oxtail_tacos", "Oxtail Taco Platter", 950),
    ("breakfast_tacos", "Breakfast Taco Platter", 700),

    ("water", "Water", 200),
    ("peach_tea", "Peach Tea", 200),
    ("lemonade", "Lemonade", 200),

    ("abg_strawberry_hennessy", "ABG-Strawberry Hennessy-Tray", 1000),
    ("abg_pink_jalapeno_kiss", "ABG-Pink Jalapeno Kiss [RLV]-Tray", 1000),
    ("abg_pineapple_margarita", "ABG-Pineapple Margarita Tray", 1000),
    ("abg_pineapple_martini", "ABG-Pineapple-Martini Tray", 1000),
    ("abg_strawberry_margarita", "ABG-Strawberry Margarita Tray", 1000),
    ("abg_strawberry_martini", "ABG-StrawBerry-Martini Tray", 1000),

    ("hookah_mint", "Hookah Session - Mint", 600),
    ("hookah_blueberry", "Hookah Session - Blueberry", 600),
    ("hookah_watermelon", "Hookah Session - Watermelon", 600),
    ("hookah_peach", "Hookah Session - Peach", 600),
    ("hookah_grape", "Hookah Session - Grape", 600),
    ("hookah_double_apple", "Hookah Session - Double Apple", 600),
    ("hookah_strawberry", "Hookah Session - Strawberry", 600),
    ("hookah_mango", "Hookah Session - Mango", 600),
]


# ============================================================
# DATABASE
# ============================================================

def db():
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


def now():
    return int(time.time())


def pacific_time(timestamp):
    dt = datetime.fromtimestamp(
        timestamp,
        timezone.utc
    ).astimezone(PACIFIC)

    return dt.strftime(
        "%Y-%m-%d %I:%M:%S %p %Z"
    )


def make_id(prefix):
    return (
        prefix
        + "_"
        + uuid.uuid4().hex[:12]
    )


# ============================================================
# DATABASE COLUMN UPGRADE
# ============================================================

def ensure_column(
    conn,
    table_name,
    column_name,
    column_type
):
    columns = [
        row["name"]
        for row in conn.execute(
            f"PRAGMA table_info({table_name})"
        )
    ]

    if column_name not in columns:
        conn.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name} {column_type}
            """
        )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    with db() as conn:

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS menu_items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price_linden INTEGER NOT NULL,
                available INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS carts (
                id TEXT PRIMARY KEY,
                table_id TEXT NOT NULL,
                avatar_id TEXT NOT NULL,
                avatar_name TEXT,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cart_items (
                id TEXT PRIMARY KEY,
                cart_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                name TEXT NOT NULL,
                price_linden INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bills (
                id TEXT PRIMARY KEY,
                payment_id TEXT UNIQUE NOT NULL,
                cart_id TEXT NOT NULL,
                table_id TEXT NOT NULL,
                avatar_id TEXT NOT NULL,
                avatar_name TEXT,
                amount_linden INTEGER NOT NULL,
                status TEXT NOT NULL,
                transaction_id TEXT,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kitchen_tickets (
                id TEXT PRIMARY KEY,
                bill_id TEXT UNIQUE NOT NULL,
                table_id TEXT NOT NULL,
                avatar_id TEXT NOT NULL,
                avatar_name TEXT,
                items TEXT NOT NULL,
                amount_linden INTEGER NOT NULL,
                status TEXT NOT NULL,
                claimed_by TEXT,
                claimed_by_name TEXT,
                claimed_at INTEGER,
                completed_by TEXT,
                completed_by_name TEXT,
                completed_at INTEGER,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS inventory_items (
                item_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                category TEXT NOT NULL,
                count INTEGER NOT NULL,
                source_id TEXT,
                source_name TEXT,
                updated_at INTEGER NOT NULL
            );
            """
        )

        # ----------------------------------------------------
        # Existing database upgrades
        # ----------------------------------------------------

        ensure_column(
            conn,
            "carts",
            "avatar_name",
            "TEXT"
        )

        ensure_column(
            conn,
            "bills",
            "avatar_name",
            "TEXT"
        )

        ensure_column(
            conn,
            "kitchen_tickets",
            "avatar_name",
            "TEXT"
        )

        ensure_column(
            conn,
            "kitchen_tickets",
            "claimed_by_name",
            "TEXT"
        )

        ensure_column(
            conn,
            "kitchen_tickets",
            "claimed_at",
            "INTEGER"
        )

        ensure_column(
            conn,
            "kitchen_tickets",
            "completed_by",
            "TEXT"
        )

        ensure_column(
            conn,
            "kitchen_tickets",
            "completed_by_name",
            "TEXT"
        )

        ensure_column(
            conn,
            "kitchen_tickets",
            "completed_at",
            "INTEGER"
        )

        # ----------------------------------------------------
        # Menu
        # ----------------------------------------------------

        conn.execute(
            """
            UPDATE menu_items
            SET available = 0
            """
        )

        for item_id, name, price in MENU:

            conn.execute(
                """
                INSERT INTO menu_items
                (id, name, price_linden, available)
                VALUES (?, ?, ?, 1)

                ON CONFLICT(id)
                DO UPDATE SET
                    name = excluded.name,
                    price_linden = excluded.price_linden,
                    available = excluded.available
                """,
                (
                    item_id,
                    name,
                    price
                )
            )


# ============================================================
# GENERAL HELPERS
# ============================================================

def rows_to_dicts(rows):
    return [
        dict(row)
        for row in rows
    ]


def read_body(handler):

    length = int(
        handler.headers.get(
            "Content-Length",
            "0"
        )
    )

    if length <= 0:
        return {}

    raw = handler.rfile.read(
        length
    ).decode(
        "utf-8"
    )

    if not raw:
        return {}

    return json.loads(raw)


def ok(payload=None, status=200):

    data = {
        "ok": True
    }

    if payload:
        data.update(payload)

    return status, data


def err(
    message,
    status=400
):
    return status, {
        "ok": False,
        "error": message
    }


def check_api_key(handler):

    if not API_KEY:
        return True

    return (
        handler.headers.get(
            "X-Hangar-Key"
        )
        == API_KEY
    )


# ============================================================
# CART
# ============================================================

def get_or_create_cart(
    conn,
    table_id,
    avatar_id,
    avatar_name
):

    cart = conn.execute(
        """
        SELECT *
        FROM carts
        WHERE table_id = ?
        AND avatar_id = ?
        AND status = 'cart'
        """,
        (
            table_id,
            avatar_id
        )
    ).fetchone()

    if cart:

        if avatar_name:

            conn.execute(
                """
                UPDATE carts
                SET avatar_name = ?
                WHERE id = ?
                """,
                (
                    avatar_name,
                    cart["id"]
                )
            )

        return cart["id"]

    cart_id = make_id(
        "cart"
    )

    conn.execute(
        """
        INSERT INTO carts
        (
            id,
            table_id,
            avatar_id,
            avatar_name,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, 'cart', ?)
        """,
        (
            cart_id,
            table_id,
            avatar_id,
            avatar_name,
            now()
        )
    )

    return cart_id


def cart_items(
    conn,
    cart_id
):

    return rows_to_dicts(
        conn.execute(
            """
            SELECT
                item_id,
                name,
                price_linden
            FROM cart_items
            WHERE cart_id = ?
            """,
            (cart_id,)
        )
    )


# ============================================================
# KITCHEN TICKET
# ============================================================

def create_ticket(
    conn,
    bill
):

    existing = conn.execute(
        """
        SELECT *
        FROM kitchen_tickets
        WHERE bill_id = ?
        """,
        (bill["id"],)
    ).fetchone()

    if existing:
        return dict(existing)

    items = cart_items(
        conn,
        bill["cart_id"]
    )

    ticket_id = make_id(
        "kit"
    )

    conn.execute(
        """
        INSERT INTO kitchen_tickets
        (
            id,
            bill_id,
            table_id,
            avatar_id,
            avatar_name,
            items,
            amount_linden,
            status,
            claimed_by,
            claimed_by_name,
            claimed_at,
            completed_by,
            completed_by_name,
            completed_at,
            created_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            'open',
            NULL, NULL, NULL,
            NULL, NULL, NULL,
            ?
        )
        """,
        (
            ticket_id,
            bill["id"],
            bill["table_id"],
            bill["avatar_id"],
            bill["avatar_name"]
                or bill["avatar_id"],
            json.dumps(items),
            bill["amount_linden"],
            now()
        )
    )

    return dict(
        conn.execute(
            """
            SELECT *
            FROM kitchen_tickets
            WHERE id = ?
            """,
            (ticket_id,)
        ).fetchone()
    )


# ============================================================
# MENU API
# ============================================================

def api_menu(
    _query,
    _body
):

    with db() as conn:

        items = rows_to_dicts(
            conn.execute(
                """
                SELECT *
                FROM menu_items
                WHERE available = 1
                ORDER BY rowid
                """
            )
        )

    return ok(
        {
            "menu_version": 1,
            "items": items
        }
    )


# ============================================================
# ADD TO CART
# ============================================================

def api_cart_add(
    _query,
    body
):

    table_id = body.get(
        "table_id"
    )

    avatar_id = body.get(
        "avatar_id"
    )

    avatar_name = (
        body.get("avatar_name")
        or avatar_id
    )

    item_id = body.get(
        "item_id"
    )

    if not table_id:
        return err(
            "table_id is required"
        )

    if not avatar_id:
        return err(
            "avatar_id is required"
        )

    if not item_id:
        return err(
            "item_id is required"
        )

    with db() as conn:

        item = conn.execute(
            """
            SELECT *
            FROM menu_items
            WHERE id = ?
            AND available = 1
            """,
            (item_id,)
        ).fetchone()

        if not item:
            return err(
                "menu item is unavailable",
                404
            )

        cart_id = get_or_create_cart(
            conn,
            table_id,
            avatar_id,
            avatar_name
        )

        conn.execute(
            """
            INSERT INTO cart_items
            (
                id,
                cart_id,
                item_id,
                name,
                price_linden
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                make_id("ci"),
                cart_id,
                item["id"],
                item["name"],
                item["price_linden"]
            )
        )

        items = cart_items(
            conn,
            cart_id
        )

    return ok(
        {
            "cart": {
                "id": cart_id,
                "table_id": table_id,
                "avatar_id": avatar_id,
                "avatar_name": avatar_name,
                "items": items
            }
        }
    )


# ============================================================
# PLACE ORDER
# ============================================================

def api_order_place(
    _query,
    body
):

    table_id = body.get(
        "table_id"
    )

    avatar_id = body.get(
        "avatar_id"
    )

    avatar_name = (
        body.get("avatar_name")
        or avatar_id
    )

    if not table_id:
        return err(
            "table_id is required"
        )

    if not avatar_id:
        return err(
            "avatar_id is required"
        )

    with db() as conn:

        # ----------------------------------------------------
        # Prevent duplicate pending payment for same
        # customer/table.
        # ----------------------------------------------------

        pending = conn.execute(
            """
            SELECT *
            FROM bills
            WHERE table_id = ?
            AND avatar_id = ?
            AND status = 'pending_payment'
            """,
            (
                table_id,
                avatar_id
            )
        ).fetchone()

        if pending:

            return ok(
                {
                    "bill": dict(
                        pending
                    )
                }
            )

        cart = conn.execute(
            """
            SELECT *
            FROM carts
            WHERE table_id = ?
            AND avatar_id = ?
            AND status = 'cart'
            """,
            (
                table_id,
                avatar_id
            )
        ).fetchone()

        if not cart:
            return err(
                "cart is empty",
                404
            )

        items = cart_items(
            conn,
            cart["id"]
        )

        if not items:
            return err(
                "cart is empty",
                404
            )

        amount = sum(
            int(item["price_linden"])
            for item in items
        )

        bill_id = make_id(
            "bill"
        )

        payment_id = make_id(
            "pay"
        )

        conn.execute(
            """
            UPDATE carts
            SET status = 'pending_payment'
            WHERE id = ?
            """,
            (cart["id"],)
        )

        conn.execute(
            """
            INSERT INTO bills
            (
                id,
                payment_id,
                cart_id,
                table_id,
                avatar_id,
                avatar_name,
                amount_linden,
                status,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                'pending_payment',
                ?
            )
            """,
            (
                bill_id,
                payment_id,
                cart["id"],
                table_id,
                avatar_id,
                cart["avatar_name"]
                    or avatar_name
                    or avatar_id,
                amount,
                now()
            )
        )

        bill = dict(
            conn.execute(
                """
                SELECT *
                FROM bills
                WHERE id = ?
                """,
                (bill_id,)
            ).fetchone()
        )

    return ok(
        {
            "bill": bill
        }
    )


# ============================================================
# PAY PENDING
#
# IMPORTANT:
# avatar_id AND table_id are BOTH REQUIRED.
#
# This prevents a Table-05 bill from appearing on the
# Table-02 Tap-to-Pay.
# ============================================================

def api_pay_pending(
    query,
    _body
):

    avatar_id = query.get(
        "avatar_id",
        [""]
    )[0]

    table_id = query.get(
        "table_id",
        [""]
    )[0]

    if not avatar_id:
        return err(
            "avatar_id is required"
        )

    if not table_id:
        return err(
            "table_id is required"
        )

    with db() as conn:

        bills = rows_to_dicts(
            conn.execute(
                """
                SELECT
                    payment_id,
                    table_id,
                    avatar_id,
                    amount_linden,
                    status
                FROM bills
                WHERE avatar_id = ?
                AND table_id = ?
                AND status = 'pending_payment'
                ORDER BY created_at ASC
                """,
                (
                    avatar_id,
                    table_id
                )
            )
        )

    return ok(
        {
            "table_id": table_id,
            "bills": bills
        }
    )


# ============================================================
# CONFIRM PAYMENT
#
# IMPORTANT:
# The backend verifies:
#   payment ID
#   avatar ID
#   table ID
#   payment amount
#
# This prevents a payment selected on one table's terminal
# from being submitted against another table's bill.
# ============================================================

def api_pay_confirm(
    _query,
    body
):

    payment_id = body.get(
        "payment_id"
    )

    table_id = body.get(
        "table_id"
    )

    avatar_id = body.get(
        "avatar_id"
    )

    amount = body.get(
        "amount_linden"
    )

    transaction_id = body.get(
        "transaction_id",
        ""
    )

    if not payment_id:
        return err(
            "payment_id is required"
        )

    if not table_id:
        return err(
            "table_id is required"
        )

    if not avatar_id:
        return err(
            "avatar_id is required"
        )

    if amount is None:
        return err(
            "amount_linden is required"
        )

    with db() as conn:

        bill = conn.execute(
            """
            SELECT *
            FROM bills
            WHERE payment_id = ?
            """,
            (payment_id,)
        ).fetchone()

        if not bill:
            return err(
                "pending bill was not found",
                404
            )

        bill = dict(bill)

        # ----------------------------------------------------
        # CUSTOMER CHECK
        # ----------------------------------------------------

        if bill["avatar_id"] != avatar_id:
            return err(
                "payment customer does not match bill",
                403
            )

        # ----------------------------------------------------
        # TABLE CHECK
        # ----------------------------------------------------

        if bill["table_id"] != table_id:
            return err(
                "payment table does not match bill",
                403
            )

        # ----------------------------------------------------
        # AMOUNT CHECK
        # ----------------------------------------------------

        if int(amount) != int(
            bill["amount_linden"]
        ):
            return err(
                "payment amount does not match bill",
                409
            )

        # ----------------------------------------------------
        # Already paid?
        # ----------------------------------------------------

        if bill["status"] != "paid":

            conn.execute(
                """
                UPDATE bills
                SET
                    status = 'paid',
                    transaction_id = ?
                WHERE payment_id = ?
                """,
                (
                    transaction_id,
                    payment_id
                )
            )

            conn.execute(
                """
                UPDATE carts
                SET status = 'paid'
                WHERE id = ?
                """,
                (
                    bill["cart_id"],
                )
            )

            bill["status"] = "paid"
            bill["transaction_id"] = transaction_id

        # ----------------------------------------------------
        # CREATE KITCHEN TICKET
        # ----------------------------------------------------

        ticket = create_ticket(
            conn,
            bill
        )

    return ok(
        {
            "bill": bill,
            "ticket": ticket
        }
    )


# ============================================================
# SERIALIZE KITCHEN TICKET
# ============================================================

def serialize_ticket(ticket):

    ticket = dict(ticket)

    try:
        ticket["items"] = json.loads(
            ticket["items"]
        )
    except Exception:
        ticket["items"] = []

    ticket[
        "created_at_pacific"
    ] = pacific_time(
        ticket["created_at"]
    )

    if ticket.get("claimed_at"):

        ticket[
            "claimed_at_pacific"
        ] = pacific_time(
            ticket["claimed_at"]
        )

    else:

        ticket[
            "claimed_at_pacific"
        ] = None

    if ticket.get("completed_at"):

        ticket[
            "completed_at_pacific"
        ] = pacific_time(
            ticket["completed_at"]
        )

    else:

        ticket[
            "completed_at_pacific"
        ] = None

    # Don't expose SL UUIDs to kitchen UI.
    ticket.pop(
        "avatar_id",
        None
    )

    ticket.pop(
        "claimed_by",
        None
    )

    ticket.pop(
        "completed_by",
        None
    )

    return ticket


def serialize_controller_ticket(ticket):

    ticket = dict(ticket)

    return {
        "id":
            ticket.get(
                "id",
                ""
            ),

        "table_id":
            ticket.get(
                "table_id",
                ""
            ),

        "avatar_name":
            ticket.get(
                "avatar_name",
                ""
            ),

        "status":
            ticket.get(
                "status",
                ""
            ),

        "claimed_by_name":
            ticket.get(
                "claimed_by_name",
                ""
            ),
    }


# ============================================================
# OWNER OPERATIONS
# ============================================================

def owner_today_start():

    local_now = datetime.now(
        PACIFIC
    )

    local_start = local_now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    return int(
        local_start.timestamp()
    )


def check_owner_access(query):

    if not OWNER_ACCESS_CODE:
        return True

    return (
        query.get(
            "owner_code",
            [""]
        )[0]
        == OWNER_ACCESS_CODE
    )


def scalar(
    conn,
    sql,
    params=()
):

    value = conn.execute(
        sql,
        params
    ).fetchone()[0]

    if value is None:
        return 0

    return value


def api_owner_operations(
    query,
    _body
):

    if not check_owner_access(query):
        return err(
            "missing or invalid owner code",
            401
        )

    today_start = owner_today_start()

    with db() as conn:

        active_carts = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM carts
            WHERE status = 'cart'
            """
        )

        pending_bills = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM bills
            WHERE status = 'pending_payment'
            """
        )

        pending_linden = scalar(
            conn,
            """
            SELECT SUM(amount_linden)
            FROM bills
            WHERE status = 'pending_payment'
            """
        )

        open_tickets = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM kitchen_tickets
            WHERE status = 'open'
            """
        )

        claimed_tickets = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM kitchen_tickets
            WHERE status = 'claimed'
            """
        )

        kitchen_linden = scalar(
            conn,
            """
            SELECT SUM(amount_linden)
            FROM kitchen_tickets
            WHERE status != 'complete'
            """
        )

        completed_today = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM kitchen_tickets
            WHERE status = 'complete'
            AND completed_at >= ?
            """,
            (
                today_start,
            )
        )

        sales_today = scalar(
            conn,
            """
            SELECT SUM(amount_linden)
            FROM kitchen_tickets
            WHERE status = 'complete'
            AND completed_at >= ?
            """,
            (
                today_start,
            )
        )

        paid_today = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM bills
            WHERE status = 'paid'
            AND created_at >= ?
            """,
            (
                today_start,
            )
        )

        active_tables = [
            row["table_id"]
            for row in conn.execute(
                """
                SELECT DISTINCT table_id
                FROM (
                    SELECT table_id
                    FROM carts
                    WHERE status = 'cart'

                    UNION

                    SELECT table_id
                    FROM bills
                    WHERE status = 'pending_payment'

                    UNION

                    SELECT table_id
                    FROM kitchen_tickets
                    WHERE status != 'complete'
                )
                ORDER BY table_id
                LIMIT 12
                """
            )
        ]

        inventory_rows = rows_to_dicts(
            conn.execute(
                """
                SELECT
                    item_id,
                    label,
                    category,
                    count,
                    source_name,
                    updated_at
                FROM inventory_items
                ORDER BY category, label
                """
            )
        )

        inventory_total = sum(
            row["count"]
            for row in inventory_rows
        )

        low_inventory = [
            row["label"]
            + ": "
            + str(row["count"])
            for row in inventory_rows
            if row["count"] <= 2
        ]

    return ok(
        {
            "updated_at_pacific":
                pacific_time(
                    now()
                ),

            "active_carts":
                active_carts,

            "pending_bills":
                pending_bills,

            "pending_linden":
                pending_linden,

            "open_tickets":
                open_tickets,

            "claimed_tickets":
                claimed_tickets,

            "kitchen_linden":
                kitchen_linden,

            "completed_today":
                completed_today,

            "sales_today":
                sales_today,

            "paid_bills_today":
                paid_today,

            "active_tables":
                ", ".join(
                    active_tables
                )
                if active_tables
                else "none",

            "inventory_total":
                inventory_total,

            "inventory_low":
                ", ".join(
                    low_inventory[:8]
                )
                if low_inventory
                else "none",

            "inventory_items":
                inventory_rows,
        }
    )


# ============================================================
# INVENTORY
# ============================================================

def api_inventory_snapshot(
    _query,
    body
):

    source_id = body.get(
        "source_id",
        ""
    )

    source_name = body.get(
        "source_name",
        ""
    )

    items = body.get(
        "items",
        []
    )

    if not isinstance(items, list):
        return err(
            "items must be a list"
        )

    updated_at = now()

    with db() as conn:

        for item in items:

            item_id = item.get(
                "item_id",
                ""
            )

            label = item.get(
                "label",
                item_id
            )

            category = item.get(
                "category",
                "inventory"
            )

            count = int(
                item.get(
                    "count",
                    0
                )
                or 0
            )

            if not item_id:
                continue

            conn.execute(
                """
                INSERT INTO inventory_items
                (
                    item_id,
                    label,
                    category,
                    count,
                    source_id,
                    source_name,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(item_id)
                DO UPDATE SET
                    label = excluded.label,
                    category = excluded.category,
                    count = excluded.count,
                    source_id = excluded.source_id,
                    source_name = excluded.source_name,
                    updated_at = excluded.updated_at
                """,
                (
                    item_id,
                    label,
                    category,
                    count,
                    source_id,
                    source_name,
                    updated_at
                )
            )

    return ok(
        {
            "updated_at":
                updated_at,

            "updated_at_pacific":
                pacific_time(
                    updated_at
                ),

            "items_received":
                len(items),
        }
    )


def api_inventory_status(
    query,
    _body
):

    if not check_owner_access(query):
        return err(
            "missing or invalid owner code",
            401
        )

    with db() as conn:

        items = rows_to_dicts(
            conn.execute(
                """
                SELECT
                    item_id,
                    label,
                    category,
                    count,
                    source_name,
                    updated_at
                FROM inventory_items
                ORDER BY category, label
                """
            )
        )

    return ok(
        {
            "items":
                items,

            "total":
                sum(
                    item["count"]
                    for item in items
                ),
        }
    )


def delete_cart_data(
    conn,
    cart_ids
):

    if not cart_ids:
        return

    placeholders = ",".join(
        "?"
        for _cart_id in cart_ids
    )

    conn.execute(
        f"""
        DELETE FROM cart_items
        WHERE cart_id IN ({placeholders})
        """,
        cart_ids
    )

    conn.execute(
        f"""
        DELETE FROM carts
        WHERE id IN ({placeholders})
        """,
        cart_ids
    )


def api_owner_clear_active_tables(
    query,
    _body
):

    if not check_owner_access(query):
        return err(
            "missing or invalid owner code",
            401
        )

    with db() as conn:

        cart_ids = [
            row["id"]
            for row in conn.execute(
                """
                SELECT id
                FROM carts
                WHERE status = 'cart'
                """
            )
        ]

        pending_bill_rows = rows_to_dicts(
            conn.execute(
                """
                SELECT id, cart_id
                FROM bills
                WHERE status = 'pending_payment'
                """
            )
        )

        for row in pending_bill_rows:

            if row["cart_id"] not in cart_ids:
                cart_ids.append(
                    row["cart_id"]
                )

        active_cart_count = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM carts
            WHERE status = 'cart'
            """
        )

        pending_bill_count = len(
            pending_bill_rows
        )

        conn.execute(
            """
            DELETE FROM bills
            WHERE status = 'pending_payment'
            """
        )

        delete_cart_data(
            conn,
            cart_ids
        )

    return ok(
        {
            "cleared_carts":
                active_cart_count,

            "cleared_pending_bills":
                pending_bill_count,

            "kitchen_orders_preserved":
                True,
        }
    )


# ============================================================
# KITCHEN TICKETS
# ============================================================

def api_tickets(
    query,
    _body
):

    page = int(
        query.get(
            "page",
            ["1"]
        )[0]
        or "1"
    )

    limit = int(
        query.get(
            "limit",
            ["50"]
        )[0]
        or "50"
    )

    view = (
        query.get(
            "view",
            [""]
        )[0]
        or ""
    ).lower()

    if page < 1:
        page = 1

    if limit < 1:
        limit = 50

    if limit > 50:
        limit = 50

    offset = (
        page - 1
    ) * limit

    with db() as conn:

        total = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM kitchen_tickets
            WHERE status != 'complete'
            """
        ).fetchone()["count"]

        tickets = conn.execute(
            """
            SELECT *
            FROM kitchen_tickets
            WHERE status != 'complete'
            ORDER BY created_at ASC
            LIMIT ?
            OFFSET ?
            """,
            (
                limit,
                offset
            )
        ).fetchall()

    pages = (
        total + limit - 1
    ) // limit

    if pages < 1:
        pages = 1

    if view == "controller":

        ticket_list = [
            serialize_controller_ticket(ticket)
            for ticket in tickets
        ]

    else:

        ticket_list = [
            serialize_ticket(ticket)
            for ticket in tickets
        ]

    return ok(
        {
            "timezone":
                "America/Los_Angeles",

            "page":
                page,

            "limit":
                limit,

            "total":
                total,

            "pages":
                pages,

            "tickets":
                ticket_list
        }
    )


# ============================================================
# CLAIM
# ============================================================

def api_claim(
    _query,
    body
):

    ticket_id = body.get(
        "ticket_id"
    )

    staff_avatar_id = body.get(
        "staff_avatar_id"
    )

    staff_avatar_name = (
        body.get(
            "staff_avatar_name"
        )
        or staff_avatar_id
    )

    if not ticket_id:
        return err(
            "ticket_id is required"
        )

    if not staff_avatar_id:
        return err(
            "staff_avatar_id is required"
        )

    with db() as conn:

        ticket = conn.execute(
            """
            SELECT *
            FROM kitchen_tickets
            WHERE id = ?
            """,
            (ticket_id,)
        ).fetchone()

        if not ticket:
            return err(
                "ticket was not found",
                404
            )

        if ticket["status"] == "complete":
            return err(
                "ticket is already complete",
                409
            )

        if (
            ticket["claimed_by"]
            and
            ticket["claimed_by"]
            != staff_avatar_id
        ):
            return err(
                "ticket is already claimed by "
                + (
                    ticket["claimed_by_name"]
                    or "another staff member"
                ),
                409
            )

        conn.execute(
            """
            UPDATE kitchen_tickets
            SET
                status = 'claimed',
                claimed_by = ?,
                claimed_by_name = ?,
                claimed_at = ?
            WHERE id = ?
            """,
            (
                staff_avatar_id,
                staff_avatar_name,
                now(),
                ticket_id
            )
        )

        updated = conn.execute(
            """
            SELECT *
            FROM kitchen_tickets
            WHERE id = ?
            """,
            (ticket_id,)
        ).fetchone()

    return ok(
        {
            "ticket":
                serialize_ticket(updated)
        }
    )


# ============================================================
# COMPLETE
# ============================================================

def api_complete(
    _query,
    body
):

    ticket_id = body.get(
        "ticket_id"
    )

    staff_avatar_id = body.get(
        "staff_avatar_id"
    )

    staff_avatar_name = (
        body.get(
            "staff_avatar_name"
        )
        or staff_avatar_id
    )

    if not ticket_id:
        return err(
            "ticket_id is required"
        )

    if not staff_avatar_id:
        return err(
            "staff_avatar_id is required"
        )

    with db() as conn:

        ticket = conn.execute(
            """
            SELECT *
            FROM kitchen_tickets
            WHERE id = ?
            """,
            (ticket_id,)
        ).fetchone()

        if not ticket:
            return err(
                "ticket was not found",
                404
            )

        if ticket["status"] == "complete":

            return ok(
                {
                    "ticket":
                        serialize_ticket(ticket)
                }
            )

        if (
            ticket["claimed_by"]
            and
            ticket["claimed_by"]
            != staff_avatar_id
        ):
            return err(
                "only "
                + (
                    ticket["claimed_by_name"]
                    or "the claiming staff member"
                )
                + " can complete this ticket",
                403
            )

        conn.execute(
            """
            UPDATE kitchen_tickets
            SET
                status = 'complete',
                completed_by = ?,
                completed_by_name = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (
                staff_avatar_id,
                staff_avatar_name,
                now(),
                ticket_id
            )
        )

        updated = conn.execute(
            """
            SELECT *
            FROM kitchen_tickets
            WHERE id = ?
            """,
            (ticket_id,)
        ).fetchone()

    return ok(
        {
            "ticket":
                serialize_ticket(updated)
        }
    )


# ============================================================
# CLEAR COMPLETED
# ============================================================

def api_clear_completed(
    _query,
    _body
):

    with db() as conn:

        count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM kitchen_tickets
            WHERE status = 'complete'
            """
        ).fetchone()["count"]

        conn.execute(
            """
            DELETE FROM kitchen_tickets
            WHERE status = 'complete'
            """
        )

    return ok(
        {
            "deleted": count
        }
    )


# ============================================================
# KITCHEN WEB PAGE
# ============================================================

def kitchen_page():

    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>The Hangar Kitchen</title>

<style>

body{
margin:0;
font-family:Arial,Helvetica,sans-serif;
background:#090909;
color:#f5efe6;
}

header{
padding:18px 24px;
border-bottom:2px solid #b9822d;
display:flex;
justify-content:space-between;
align-items:center;
}

h1{
margin:0;
font-size:28px;
letter-spacing:2px;
color:#f0b45f;
}

#clock{
font-size:15px;
color:#c9bba8;
}

main{
padding:18px;
display:grid;
grid-template-columns:
repeat(auto-fit,minmax(300px,1fr));
gap:14px;
}

.ticket{
border:1px solid #b9822d;
background:#171717;
border-radius:8px;
padding:16px;
}

.top{
display:flex;
justify-content:space-between;
gap:12px;
align-items:start;
}

.table{
font-size:24px;
font-weight:700;
color:#fff;
}

.status{
color:#101010;
background:#f0b45f;
padding:5px 8px;
border-radius:999px;
font-size:12px;
text-transform:uppercase;
}

.items{
margin:14px 0;
font-size:20px;
line-height:1.35;
}

.meta{
color:#c9bba8;
font-size:13px;
line-height:1.55;
}

.claimed{
margin-top:8px;
color:#f0b45f;
font-weight:700;
}

.empty{
grid-column:1/-1;
text-align:center;
color:#c9bba8;
font-size:28px;
padding:90px 20px;
}

button{
background:#f0b45f;
border:0;
color:#111;
border-radius:6px;
padding:9px 12px;
font-weight:700;
cursor:pointer;
margin-right:7px;
}

button.done{
background:#79d098;
}

</style>
</head>

<body>

<header>

<h1>THE HANGAR KITCHEN</h1>

<div id="clock"></div>

</header>

<main id="board"></main>

<script>

const staff = "web-staff";

function escapeHtml(value){

    return String(value ?? "")
        .replaceAll("&","&amp;")
        .replaceAll("<","&lt;")
        .replaceAll(">","&gt;")
        .replaceAll('"',"&quot;")
        .replaceAll("'","&#039;");

}

function itemText(ticket){

    return (ticket.items || [])
        .map(item => item.name)
        .join(", ");

}

async function action(path,ticketId){

    try{

        const response =
            await fetch(
                path,
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                        "application/json"
                    },

                    body:JSON.stringify({
                        ticket_id:ticketId,
                        staff_avatar_id:staff,
                        staff_avatar_name:
                        "Kitchen Board"
                    })
                }
            );

        const data =
            await response.json();

        if(!data.ok){

            alert(
                data.error ||
                "Action failed"
            );

        }

    }
    catch(error){

        alert(
            "Kitchen server error."
        );

    }

    load();

}

async function load(){

    document
        .getElementById("clock")
        .textContent =
        new Intl.DateTimeFormat(
            "en-US",
            {
                timeZone:
                "America/Los_Angeles",

                dateStyle:"medium",
                timeStyle:"medium"
            }
        ).format(new Date())
        + " PT";

    try{

        const response =
            await fetch(
                "/api/kitchen/tickets"
            );

        const data =
            await response.json();

        if(!data.ok){

            throw new Error(
                data.error ||
                "Invalid response"
            );

        }

        const tickets =
            (data.tickets || [])
            .filter(
                ticket =>
                ticket.status !==
                "complete"
            );

        const board =
            document.getElementById(
                "board"
            );

        if(!tickets.length){

            board.innerHTML =
                '<div class="empty">' +
                'No paid orders waiting.' +
                '</div>';

            return;

        }

        board.innerHTML =
            tickets.map(ticket => {

                const safeId =
                    escapeHtml(ticket.id);

                const safeTable =
                    escapeHtml(ticket.table_id);

                const safeStatus =
                    escapeHtml(ticket.status);

                const safeItems =
                    escapeHtml(itemText(ticket));

                const safeGuest =
                    escapeHtml(
                        ticket.avatar_name ||
                        "Guest"
                    );

                const safeAmount =
                    escapeHtml(ticket.amount_linden);

                const safeReceived =
                    escapeHtml(ticket.created_at_pacific);

                const safeClaimedBy =
                    escapeHtml(ticket.claimed_by_name || "");

                const safeClaimedAt =
                    escapeHtml(ticket.claimed_at_pacific || "");

                return `

                <section class="ticket">

                    <div class="top">

                        <div class="table">
                            TABLE
                            ${safeTable}
                        </div>

                        <div class="status">
                            ${safeStatus}
                        </div>

                    </div>

                    <div class="items">
                        ${safeItems}
                    </div>

                    <div class="meta">

                        Guest:
                        ${safeGuest}

                        <br>

                        Amount:
                        L$${safeAmount}

                        <br>

                        Received:
                        ${safeReceived}

                    </div>

                    ${
                        ticket.claimed_by_name
                        ?
                        `<div class="claimed">
                            Claimed by:
                            ${safeClaimedBy}
                            <br>
                            Claimed:
                            ${safeClaimedAt}
                        </div>`
                        :
                        ""
                    }

                    <p>

                        ${
                            ticket.status ===
                            "open"
                            ?
                            `<button
                                data-action="claim"
                                data-ticket-id="${safeId}">
                                Claim
                            </button>`
                            :
                            ""
                        }

                        <button
                            class="done"
                            data-action="complete"
                            data-ticket-id="${safeId}">

                            Complete

                        </button>

                    </p>

                </section>

            `;

            }).join("");

    }
    catch(error){

        document
            .getElementById("board")
            .innerHTML =
            '<div class="empty">' +
            'Kitchen server returned ' +
            'an invalid response.' +
            '</div>';

    }

}

load();

document
    .getElementById("board")
    .addEventListener(
        "click",
        event => {

            const button =
                event.target.closest("button");

            if(!button){
                return;
            }

            const ticketId =
                button.dataset.ticketId;

            const actionName =
                button.dataset.action;

            if(!ticketId || !actionName){
                return;
            }

            if(actionName === "claim"){
                action(
                    "/api/kitchen/claim",
                    ticketId
                );
                return;
            }

            if(actionName === "complete"){
                action(
                    "/api/kitchen/complete",
                    ticketId
                );
            }

        }
    );

setInterval(
    load,
    5000
);

</script>

</body>
</html>"""


# ============================================================
# OWNER WEB PAGE
# ============================================================

def owner_page():

    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>The Hangar Owner Ops</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,Helvetica,sans-serif;
background:#080808;
color:#f8efe0;
}

header{
padding:14px 18px;
border-bottom:2px solid #b9822d;
display:flex;
justify-content:space-between;
align-items:center;
gap:12px;
}

h1{
margin:0;
font-size:22px;
letter-spacing:1px;
color:#f0b45f;
}

#updated{
font-size:12px;
color:#c8b79d;
text-align:right;
}

main{
padding:14px;
display:grid;
grid-template-columns:repeat(4,minmax(120px,1fr));
gap:10px;
}

.metric{
border:1px solid #80591f;
background:#151515;
border-radius:8px;
padding:12px;
min-height:86px;
}

.label{
font-size:12px;
color:#c8b79d;
text-transform:uppercase;
letter-spacing:1px;
}

.value{
margin-top:8px;
font-size:30px;
font-weight:700;
color:#fff;
line-height:1;
}

.wide{
grid-column:span 2;
}

.tables{
font-size:20px;
line-height:1.25;
}

.status{
padding:0 14px 14px;
font-size:12px;
color:#c8b79d;
}

.actions{
padding:0 14px 14px;
display:flex;
gap:8px;
}

button{
background:#f0b45f;
border:0;
border-radius:6px;
color:#111;
font-weight:700;
padding:9px 12px;
cursor:pointer;
}

.error{
color:#ff9b9b;
}

@media (max-width: 720px){
main{
grid-template-columns:repeat(2,minmax(120px,1fr));
}

.wide{
grid-column:span 2;
}
}

</style>
</head>

<body>

<header>
<h1>THE HANGAR OPS</h1>
<div id="updated">Loading...</div>
</header>

<main>
<section class="metric">
<div class="label">Active Carts</div>
<div class="value" id="active_carts">0</div>
</section>

<section class="metric">
<div class="label">Pending Bills</div>
<div class="value" id="pending_bills">0</div>
</section>

<section class="metric">
<div class="label">Pending L$</div>
<div class="value" id="pending_linden">0</div>
</section>

<section class="metric">
<div class="label">Kitchen L$</div>
<div class="value" id="kitchen_linden">0</div>
</section>

<section class="metric">
<div class="label">Open Tickets</div>
<div class="value" id="open_tickets">0</div>
</section>

<section class="metric">
<div class="label">Claimed</div>
<div class="value" id="claimed_tickets">0</div>
</section>

<section class="metric">
<div class="label">Completed Today</div>
<div class="value" id="completed_today">0</div>
</section>

<section class="metric">
<div class="label">Sales Today</div>
<div class="value" id="sales_today">0</div>
</section>

<section class="metric wide">
<div class="label">Paid Bills Today</div>
<div class="value" id="paid_bills_today">0</div>
</section>

<section class="metric wide">
<div class="label">Active Tables</div>
<div class="value tables" id="active_tables">none</div>
</section>

<section class="metric">
<div class="label">Inventory Total</div>
<div class="value" id="inventory_total">0</div>
</section>

<section class="metric wide">
<div class="label">Low Inventory</div>
<div class="value tables" id="inventory_low">none</div>
</section>
</main>

<div class="actions">
<button id="clear_active">Clear Active Tables</button>
</div>

<div class="status" id="status">Live refresh every 5 seconds.</div>

<script>

function setText(id,value){
    document
        .getElementById(id)
        .textContent =
        value ?? "0";
}

async function load(){

    const status =
        document.getElementById("status");

    try{

        const response =
            await fetch(
                "/api/owner/operations" +
                window.location.search,
                {
                    cache:"no-store"
                }
            );

        const data =
            await response.json();

        if(!data.ok){
            throw new Error(
                data.error ||
                "Owner data unavailable"
            );
        }

        setText("active_carts", data.active_carts);
        setText("pending_bills", data.pending_bills);
        setText("pending_linden", "L$" + data.pending_linden);
        setText("kitchen_linden", "L$" + data.kitchen_linden);
        setText("open_tickets", data.open_tickets);
        setText("claimed_tickets", data.claimed_tickets);
        setText("completed_today", data.completed_today);
        setText("sales_today", "L$" + data.sales_today);
        setText("paid_bills_today", data.paid_bills_today);
        setText("active_tables", data.active_tables || "none");
        setText("inventory_total", data.inventory_total);
        setText("inventory_low", data.inventory_low || "none");

        document
            .getElementById("updated")
            .textContent =
            data.updated_at_pacific || "Live";

        status.className = "status";
        status.textContent =
            "Live refresh every 5 seconds.";

    }
    catch(error){

        status.className =
            "status error";

        status.textContent =
            "Owner dashboard could not load: " +
            error.message;

    }
}

load();

setInterval(
    load,
    5000
);

document
    .getElementById("clear_active")
    .addEventListener(
        "click",
        async () => {

            if(!confirm(
                "Clear unpaid carts and pending bills? Paid kitchen orders will stay."
            )){
                return;
            }

            const status =
                document.getElementById("status");

            try{

                const response =
                    await fetch(
                        "/api/owner/clear-active-tables" +
                        window.location.search,
                        {
                            method:"POST",
                            headers:{
                                "Content-Type":"application/json"
                            },
                            body:"{}"
                        }
                    );

                const data =
                    await response.json();

                if(!data.ok){
                    throw new Error(
                        data.error ||
                        "Clear failed"
                    );
                }

                status.className = "status";
                status.textContent =
                    "Cleared "
                    + data.cleared_carts
                    + " carts and "
                    + data.cleared_pending_bills
                    + " pending bills.";

                load();

            }
            catch(error){

                status.className =
                    "status error";

                status.textContent =
                    "Could not clear active tables: "
                    + error.message;

            }
        }
    );

</script>

</body>
</html>"""


# ============================================================
# ROUTES
# ============================================================

ROUTES = {

    ("GET", "/menu"):
        api_menu,

    ("POST", "/cart/add"):
        api_cart_add,

    ("POST", "/order/place"):
        api_order_place,

    ("GET", "/pay/pending"):
        api_pay_pending,

    ("POST", "/pay/confirm"):
        api_pay_confirm,

    ("GET", "/api/kitchen/tickets"):
        api_tickets,

    ("GET", "/api/owner/operations"):
        api_owner_operations,

    ("POST", "/api/owner/clear-active-tables"):
        api_owner_clear_active_tables,

    ("POST", "/api/inventory/snapshot"):
        api_inventory_snapshot,

    ("GET", "/api/inventory/status"):
        api_inventory_status,

    ("POST", "/api/kitchen/claim"):
        api_claim,

    ("POST", "/api/kitchen/complete"):
        api_complete,

    ("POST", "/api/kitchen/clear-completed"):
        api_clear_completed,
}


# ============================================================
# HTTP HANDLER
# ============================================================

class Handler(
    BaseHTTPRequestHandler
):

    def send_json(
        self,
        status,
        payload
    ):

        raw = json.dumps(
            payload
        ).encode(
            "utf-8"
        )

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            "application/json"
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )

        self.send_header(
            "Content-Length",
            str(len(raw))
        )

        self.end_headers()

        self.wfile.write(
            raw
        )

    def send_html(
        self,
        html
    ):

        raw = html.encode(
            "utf-8"
        )

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )

        self.send_header(
            "Content-Length",
            str(len(raw))
        )

        self.end_headers()

        self.wfile.write(
            raw
        )

    def handle_request(
        self,
        method
    ):

        parsed = urlparse(
            self.path
        )

        # ----------------------------------------------------
        # Web pages
        # ----------------------------------------------------

        if (
            method == "GET"
            and parsed.path
            in ("/", "/kitchen", "/owner")
        ):

            html = kitchen_page()

            if parsed.path == "/owner":
                html = owner_page()

            self.send_html(
                html
            )

            return

        # ----------------------------------------------------
        # Health
        # ----------------------------------------------------

        if (
            method == "GET"
            and parsed.path == "/health"
        ):

            self.send_json(
                200,
                {
                    "ok": True,
                    "service":
                        "hangar-kiosk",
                    "table_specific_payments":
                        True
                }
            )

            return

        # ----------------------------------------------------
        # Route
        # ----------------------------------------------------

        route = ROUTES.get(
            (
                method,
                parsed.path
            )
        )

        if not route:

            self.send_json(
                404,
                {
                    "ok": False,
                    "error":
                        "route not found"
                }
            )

            return

        # ----------------------------------------------------
        # API key
        # ----------------------------------------------------

        if (
            method == "POST"
            and not check_api_key(self)
        ):

            self.send_json(
                401,
                {
                    "ok": False,
                    "error":
                        "missing or invalid API key"
                }
            )

            return

        try:

            body = (
                read_body(self)
                if method == "POST"
                else {}
            )

            status, payload = route(
                parse_qs(
                    parsed.query
                ),
                body
            )

            self.send_json(
                status,
                payload
            )

        except Exception as exc:

            self.send_json(
                500,
                {
                    "ok": False,
                    "error":
                        str(exc)
                }
            )

    def do_GET(self):

        self.handle_request(
            "GET"
        )

    def do_POST(self):

        self.handle_request(
            "POST"
        )

    def log_message(
        self,
        *_args
    ):
        return


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    init_db()

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            port
        ),
        Handler
    )

    print(
        "The Hangar kiosk backend "
        "running on port "
        + str(port)
    )

    server.serve_forever()
