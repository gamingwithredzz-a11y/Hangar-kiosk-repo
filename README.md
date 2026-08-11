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
HANGAR_API_KEY=choose-a-secret-key
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
- `GET /pay/pending?avatar_id=...`
- `POST /pay/confirm`
- `GET /api/kitchen/tickets`
- `POST /api/kitchen/claim`
- `POST /api/kitchen/complete`

Current test prices are L$1 for each base item.
