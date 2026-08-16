# Hangar Kiosk Render App

Deploy this folder as a Render Python Web Service.

Render settings:

```text
Build Command: pip install -r requirements.txt
Start Command: python app.py
```

Recommended environment variables:

```text
DATABASE_PATH=/data/hangar.db
```

If using SQLite persistence on Render, add a persistent disk:

```text
Mount Path: /data
```

Pages:

- `/health` - service check
- `/kitchen` - kitchen TV dashboard

API routes:

- `GET /menu`
- `POST /cart/add`
- `POST /order/place`
- `GET /pay/pending?avatar_id=...&table_id=...`
- `POST /pay/confirm`
- `GET /api/kitchen/tickets?page=1&limit=6`
- `POST /api/kitchen/claim`
- `POST /api/kitchen/complete`
- `POST /api/kitchen/clear-completed`

Kitchen controller notes:

- The kitchen controller expects paginated ticket responses with `page`, `limit`, `total`, `pages`, and `tickets`.
- Completed tickets are hidden from regular ticket responses.
- Customer and staff UUIDs are not exposed on the kitchen dashboard; display names are used instead.
- `pay/pending` is table-specific, so a Tap-to-Pay object must send both `avatar_id` and `table_id`.

Security note:

- The current Second Life scripts do not send custom HTTP headers, because some SL environments reject `HTTP_CUSTOM_HEADER`.
- Leave `HANGAR_API_KEY` unset on Render unless authentication is later changed to query-string or body-based auth.

Current test prices are L$1 for each base item.
