import json
import os
import sqlite3
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "hangar.db"))
API_KEY = os.environ.get("HANGAR_API_KEY", "")

MENU = [
    ("wings12", "12 Piece Wings", 1),
    ("beef_tacos", "Beef Taco Platter", 1),
    ("chicken_tacos", "Chicken Taco Platter", 1),
    ("hookah_session", "Hookah Session", 1),
]


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return int(time.time())


def make_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def init_db():
    with db() as conn:
        conn.executescript(
            """
            create table if not exists menu_items (
                id text primary key,
                name text not null,
                price_linden integer not null,
                available integer not null default 1
            );
            create table if not exists carts (
                id text primary key,
                table_id text not null,
                avatar_id text not null,
                avatar_name text,
                status text not null,
                created_at integer not null
            );
            create table if not exists cart_items (
                id text primary key,
                cart_id text not null,
                item_id text not null,
                name text not null,
                price_linden integer not null
            );
            create table if not exists bills (
                id text primary key,
                payment_id text unique not null,
                cart_id text not null,
                table_id text not null,
                avatar_id text not null,
                avatar_name text,
                amount_linden integer not null,
                status text not null,
                transaction_id text,
                created_at integer not null
            );
            create table if not exists kitchen_tickets (
                id text primary key,
                bill_id text unique not null,
                table_id text not null,
                avatar_id text not null,
                avatar_name text,
                items text not null,
                amount_linden integer not null,
                status text not null,
                claimed_by text,
                created_at integer not null
            );
            """
        )
        ensure_column(conn, "carts", "avatar_name", "text")
        ensure_column(conn, "bills", "avatar_name", "text")
        ensure_column(conn, "kitchen_tickets", "avatar_name", "text")
        for item_id, name, price in MENU:
            conn.execute(
                """
                insert into menu_items (id, name, price_linden, available)
                values (?, ?, ?, 1)
                on conflict(id) do update set
                    name = excluded.name,
                    price_linden = excluded.price_linden,
                    available = excluded.available
                """,
                (item_id, name, price),
            )


def ensure_column(conn, table_name, column_name, column_type):
    columns = [row["name"] for row in conn.execute(f"pragma table_info({table_name})")]
    if column_name not in columns:
        conn.execute(f"alter table {table_name} add column {column_name} {column_type}")


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def read_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length).decode("utf-8") if length else "{}"
    return json.loads(raw or "{}")


def ok(payload=None, status=200):
    data = {"ok": True}
    if payload:
        data.update(payload)
    return status, data


def err(message, status=400):
    return status, {"ok": False, "error": message}


def check_api_key(handler):
    if not API_KEY:
        return True
    return handler.headers.get("X-Hangar-Key") == API_KEY


def get_or_create_cart(conn, table_id, avatar_id, avatar_name):
    cart = conn.execute(
        "select * from carts where table_id = ? and avatar_id = ? and status = 'cart'",
        (table_id, avatar_id),
    ).fetchone()
    if cart:
        if avatar_name:
            conn.execute("update carts set avatar_name = ? where id = ?", (avatar_name, cart["id"]))
        return cart["id"]
    cart_id = make_id("cart")
    conn.execute(
        "insert into carts (id, table_id, avatar_id, avatar_name, status, created_at) values (?, ?, ?, ?, 'cart', ?)",
        (cart_id, table_id, avatar_id, avatar_name, now()),
    )
    return cart_id


def cart_items(conn, cart_id):
    return rows_to_dicts(conn.execute("select item_id, name, price_linden from cart_items where cart_id = ?", (cart_id,)))


def create_ticket(conn, bill):
    existing = conn.execute("select * from kitchen_tickets where bill_id = ?", (bill["id"],)).fetchone()
    if existing:
        return dict(existing)
    items = cart_items(conn, bill["cart_id"])
    ticket_id = make_id("kit")
    conn.execute(
        """
        insert into kitchen_tickets
        (id, bill_id, table_id, avatar_id, avatar_name, items, amount_linden, status, claimed_by, created_at)
        values (?, ?, ?, ?, ?, ?, ?, 'open', null, ?)
        """,
        (
            ticket_id,
            bill["id"],
            bill["table_id"],
            bill["avatar_id"],
            bill["avatar_name"] or bill["avatar_id"],
            json.dumps(items),
            bill["amount_linden"],
            now(),
        ),
    )
    return dict(conn.execute("select * from kitchen_tickets where id = ?", (ticket_id,)).fetchone())


def api_menu(_query, _body):
    with db() as conn:
        items = rows_to_dicts(conn.execute("select * from menu_items where available = 1 order by rowid"))
    return ok({"menu_version": 1, "items": items})


def api_cart_add(_query, body):
    table_id = body.get("table_id")
    avatar_id = body.get("avatar_id")
    avatar_name = body.get("avatar_name") or avatar_id
    item_id = body.get("item_id")
    if not table_id or not avatar_id or not item_id:
        return err("table_id, avatar_id, and item_id are required")
    with db() as conn:
        item = conn.execute("select * from menu_items where id = ? and available = 1", (item_id,)).fetchone()
        if not item:
            return err("menu item is unavailable", 404)
        cart_id = get_or_create_cart(conn, table_id, avatar_id, avatar_name)
        conn.execute(
            "insert into cart_items (id, cart_id, item_id, name, price_linden) values (?, ?, ?, ?, ?)",
            (make_id("ci"), cart_id, item["id"], item["name"], item["price_linden"]),
        )
        items = cart_items(conn, cart_id)
    return ok({"cart": {"id": cart_id, "table_id": table_id, "avatar_id": avatar_id, "avatar_name": avatar_name, "items": items}})


def api_order_place(_query, body):
    table_id = body.get("table_id")
    avatar_id = body.get("avatar_id")
    if not table_id or not avatar_id:
        return err("table_id and avatar_id are required")
    with db() as conn:
        pending = conn.execute(
            "select * from bills where table_id = ? and avatar_id = ? and status = 'pending_payment'",
            (table_id, avatar_id),
        ).fetchone()
        if pending:
            return ok({"bill": dict(pending)})
        cart = conn.execute(
            "select * from carts where table_id = ? and avatar_id = ? and status = 'cart'",
            (table_id, avatar_id),
        ).fetchone()
        if not cart:
            return err("cart is empty", 404)
        items = cart_items(conn, cart["id"])
        if not items:
            return err("cart is empty", 404)
        amount = sum(item["price_linden"] for item in items)
        bill_id = make_id("bill")
        payment_id = make_id("pay")
        conn.execute("update carts set status = 'pending_payment' where id = ?", (cart["id"],))
        conn.execute(
            """
            insert into bills
            (id, payment_id, cart_id, table_id, avatar_id, avatar_name, amount_linden, status, created_at)
            values (?, ?, ?, ?, ?, ?, ?, 'pending_payment', ?)
            """,
            (bill_id, payment_id, cart["id"], table_id, avatar_id, cart["avatar_name"] or avatar_id, amount, now()),
        )
        bill = dict(conn.execute("select * from bills where id = ?", (bill_id,)).fetchone())
    return ok({"bill": bill})


def api_pay_pending(query, _body):
    avatar_id = query.get("avatar_id", [""])[0]
    if not avatar_id:
        return err("avatar_id is required")
    with db() as conn:
        bills = rows_to_dicts(
            conn.execute(
                "select payment_id, table_id, avatar_id, amount_linden, status from bills where avatar_id = ? and status = 'pending_payment'",
                (avatar_id,),
            )
        )
    return ok({"bills": bills})


def api_pay_confirm(_query, body):
    payment_id = body.get("payment_id")
    table_id = body.get("table_id")
    avatar_id = body.get("avatar_id")
    amount = body.get("amount_linden")
    transaction_id = body.get("transaction_id", "")
    if not payment_id or not table_id or not avatar_id or amount is None:
        return err("payment_id, table_id, avatar_id, and amount_linden are required")
    with db() as conn:
        bill = conn.execute("select * from bills where payment_id = ?", (payment_id,)).fetchone()
        if not bill:
            return err("pending bill was not found", 404)
        bill = dict(bill)
        if bill["table_id"] != table_id or bill["avatar_id"] != avatar_id:
            return err("payment context does not match bill", 403)
        if int(amount) != int(bill["amount_linden"]):
            return err("payment amount does not match bill", 409)
        if bill["status"] != "paid":
            conn.execute(
                "update bills set status = 'paid', transaction_id = ? where payment_id = ?",
                (transaction_id, payment_id),
            )
            conn.execute("update carts set status = 'paid' where id = ?", (bill["cart_id"],))
            bill["status"] = "paid"
            bill["transaction_id"] = transaction_id
        ticket = create_ticket(conn, bill)
    return ok({"bill": bill, "ticket": ticket})


def api_tickets(_query, _body):
    with db() as conn:
        tickets = rows_to_dicts(conn.execute("select * from kitchen_tickets order by created_at desc"))
    for ticket in tickets:
        ticket["items"] = json.loads(ticket["items"])
    return ok({"tickets": tickets})


def api_claim(_query, body):
    ticket_id = body.get("ticket_id")
    staff_avatar_id = body.get("staff_avatar_id", "web-staff")
    with db() as conn:
        ticket = conn.execute("select * from kitchen_tickets where id = ?", (ticket_id,)).fetchone()
        if not ticket:
            return err("ticket was not found", 404)
        if ticket["claimed_by"] and ticket["claimed_by"] != staff_avatar_id:
            return err("ticket is already claimed", 409)
        conn.execute(
            "update kitchen_tickets set status = 'claimed', claimed_by = ? where id = ?",
            (staff_avatar_id, ticket_id),
        )
    return ok()


def api_complete(_query, body):
    ticket_id = body.get("ticket_id")
    staff_avatar_id = body.get("staff_avatar_id", "web-staff")
    with db() as conn:
        ticket = conn.execute("select * from kitchen_tickets where id = ?", (ticket_id,)).fetchone()
        if not ticket:
            return err("ticket was not found", 404)
        if ticket["claimed_by"] and ticket["claimed_by"] != staff_avatar_id:
            return err("only the claiming staff avatar can complete this ticket", 403)
        conn.execute("update kitchen_tickets set status = 'complete' where id = ?", (ticket_id,))
    return ok()


def kitchen_page():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>The Hangar Kitchen Board</title>
  <style>
    body { margin:0; font-family:Arial, Helvetica, sans-serif; background:#090909; color:#f5efe6; }
    header { padding:18px 24px; border-bottom:2px solid #b9822d; display:flex; justify-content:space-between; align-items:center; }
    h1 { margin:0; font-size:28px; letter-spacing:2px; color:#f0b45f; }
    main { padding:18px; display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }
    .ticket { border:1px solid #b9822d; background:#171717; border-radius:8px; padding:16px; }
    .top { display:flex; justify-content:space-between; gap:12px; align-items:start; }
    .table { font-size:24px; font-weight:700; color:#fff; }
    .status { color:#101010; background:#f0b45f; padding:5px 8px; border-radius:999px; font-size:12px; text-transform:uppercase; }
    .items { margin:14px 0; font-size:20px; line-height:1.35; }
    .meta { color:#c9bba8; font-size:13px; }
    button { background:#f0b45f; border:0; color:#111; border-radius:6px; padding:9px 12px; font-weight:700; cursor:pointer; margin-right:7px; }
    button.done { background:#79d098; }
    .empty { grid-column:1/-1; text-align:center; color:#c9bba8; font-size:28px; padding:90px 20px; }
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
    function itemText(ticket) {
      return ticket.items.map(item => item.name).join(", ");
    }
    async function action(path, ticketId) {
      await fetch(path, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ticket_id: ticketId, staff_avatar_id: staff})
      });
      load();
    }
    async function load() {
      document.getElementById("clock").textContent = new Date().toLocaleTimeString();
      const res = await fetch("/api/kitchen/tickets");
      const data = await res.json();
      const tickets = (data.tickets || []).filter(t => t.status !== "complete");
      const board = document.getElementById("board");
      if (!tickets.length) {
        board.innerHTML = '<div class="empty">No paid orders waiting.</div>';
        return;
      }
      board.innerHTML = tickets.map(t => `
        <section class="ticket">
          <div class="top"><div class="table">${t.table_id}</div><div class="status">${t.status}</div></div>
          <div class="items">${itemText(t)}</div>
          <div class="meta">Guest: ${t.avatar_name || t.avatar_id}<br>L$${t.amount_linden}</div>
          <p>
            ${t.status === "open" ? `<button onclick="action('/api/kitchen/claim','${t.id}')">Claim</button>` : ""}
            <button class="done" onclick="action('/api/kitchen/complete','${t.id}')">Complete</button>
          </p>
        </section>`).join("");
    }
    load();
    setInterval(load, 4000);
  </script>
</body>
</html>"""


ROUTES = {
    ("GET", "/menu"): api_menu,
    ("POST", "/cart/add"): api_cart_add,
    ("POST", "/order/place"): api_order_place,
    ("GET", "/pay/pending"): api_pay_pending,
    ("POST", "/pay/confirm"): api_pay_confirm,
    ("GET", "/api/kitchen/tickets"): api_tickets,
    ("POST", "/api/kitchen/claim"): api_claim,
    ("POST", "/api/kitchen/complete"): api_complete,
}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_html(self, html):
        raw = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def handle_request(self, method):
        parsed = urlparse(self.path)
        if method == "GET" and parsed.path in ("/", "/kitchen"):
            self.send_html(kitchen_page())
            return
        if method == "GET" and parsed.path == "/health":
            self.send_json(200, {"ok": True, "service": "hangar-kiosk"})
            return
        route = ROUTES.get((method, parsed.path))
        if not route:
            self.send_json(404, {"ok": False, "error": "route not found"})
            return
        if method == "POST" and not check_api_key(self):
            self.send_json(401, {"ok": False, "error": "missing or invalid API key"})
            return
        try:
            body = read_body(self) if method == "POST" else {}
            status, payload = route(parse_qs(parsed.query), body)
            self.send_json(status, payload)
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": str(exc)})

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Hangar kiosk running on port {port}")
    server.serve_forever()
