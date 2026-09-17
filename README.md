# The Hangar Kiosk Render App

Backend for The Hangar Bar & Lounge Second Life ordering system.

This folder is the Render web service. It serves the menu, carts, bills,
Tap-to-Pay flow, and kitchen dashboard used by the in-world scripts.

Current live service:

```text
https://hangar-kiosk-repo.onrender.com
```

## What This Backend Supports

- 20+ table tablets, each using its own table ID.
- Multiple customers ordering from the same table tablet at the same time.
- One private cart/bill per customer avatar.
- Table-specific Tap-to-Pay, so customers only see their own pending bills.
- Server Order HUD orders, using the same backend cart and bill flow.
- Kitchen TV dashboard at `/kitchen`.
- Second Life kitchen controller using compact JSON from `view=controller`.
- Owner Operations HUD summary at `/api/owner/operations`.
- Kitchen dispenser live inventory through `/api/inventory/snapshot`.
- Paid-only kitchen tickets. Orders are not shown to kitchen until payment clears.

## Render Settings

Create a Python Web Service on Render with this folder.

```text
Build Command: pip install -r requirements.txt
Start Command: python app.py
```

Recommended environment variables:

```text
DATABASE_PATH=/data/hangar.db
```

For SQLite persistence on Render, add a persistent disk:

```text
Mount Path: /data
```

Do not set `HANGAR_API_KEY` right now. The current Second Life scripts do not
send custom HTTP headers because some SL environments reject `HTTP_CUSTOM_HEADER`.
If `HANGAR_API_KEY` is set, POST routes expect an `X-Hangar-Key` header and the
in-world objects will fail unless the auth approach is changed.

Owner dashboard protection:

```text
HANGAR_OWNER_CODE=your-private-owner-code
```

If this is set, the owner dashboard data endpoint requires the same code. Use the
dashboard URL `/owner?owner_code=your-private-owner-code` and put the same value
in the Owner HUD script's `OWNER_CODE` variable.

## Pages

- `GET /health` - service check.
- `GET /kitchen` - kitchen TV dashboard for a browser/media screen.
- `GET /owner` - owner operations dashboard for browser or HUD media prim.

## API Routes

- `GET /menu`
- `POST /cart/add`
- `POST /order/place`
- `GET /pay/pending?avatar_id=...&table_id=...`
- `POST /pay/confirm`
- `GET /api/kitchen/tickets?page=1&limit=6`
- `GET /api/kitchen/tickets?page=1&limit=6&view=controller`
- `GET /api/owner/operations`
- `POST /api/inventory/snapshot`
- `GET /api/inventory/status`
- `POST /api/kitchen/claim`
- `POST /api/kitchen/complete`
- `POST /api/kitchen/clear-completed`

## Second Life Scripts That Use This Backend

Use the Render versions of the scripts:

- `outputs/sl_table_tablet_render.lsl`
- `outputs/sl_tap_to_pay_render.lsl`
- `outputs/sl_kitchen_controller_render_fixed.lsl`
- `outputs/sl_server_order_hud_render.lsl`
- `outputs/sl_owner_operations_hud_render.lsl`
- `outputs/sl_kitchen_dispenser_inventory_render.lsl`

All four scripts must point at the same Render backend URL.

## Current Menu

The backend currently keeps every item at L$1 for testing.

### Wings

- 12 Piece Wings - Magnum Jerk
- 12 Piece Wings - Hot Honey
- 12 Piece Wings - Buffalo

### Tacos

- Beef Taco Platter
- Chicken Taco Platter
- Oxtail Taco Platter
- Breakfast Taco Platter

### Jerk Trays

- Jerk Pepper Shrimp Tray
- Jerk Salmon Fillets Tray
- Jerk Ribs Tray
- Jerk Leg and Thigh Tray
- Jerk Wings Tray

### Regular Drinks

- Water
- Peach Tea
- Lemonade

### ABG Drink Trays

- ABG-Strawberry Hennessy-Tray
- ABG-Pink Jalapeno Kiss [RLV]-Tray
- ABG-Pineapple Margarita Tray
- ABG-Pineapple-Martini Tray
- ABG-Strawberry Margarita Tray
- ABG-StrawBerry-Martini Tray

### Hookah

- Hookah Session - Mint
- Hookah Session - Blueberry
- Hookah Session - Watermelon
- Hookah Session - Peach
- Hookah Session - Grape
- Hookah Session - Double Apple
- Hookah Session - Strawberry
- Hookah Session - Mango

## Kitchen Controller Notes

- Use `/api/kitchen/tickets?page=1&limit=6&view=controller` for the in-world
  kitchen controller.
- `view=controller` returns a smaller response to avoid Second Life HTTP
  truncation and invalid JSON errors.
- Completed tickets are hidden from normal ticket responses.
- The kitchen dashboard and controller show customer/staff names instead of
  avatar keys.
- The controller claims and completes tickets through the backend API.

## Tap-to-Pay Notes

- Tap-to-Pay checks pending bills by both `avatar_id` and `table_id`.
- Bills can come from either the table tablet or the server HUD.
- The Tap-to-Pay object does not need to know which object created the bill.
- Each customer pays only their selected bill.
- Kitchen tickets are created only after payment confirmation.

## Server HUD Notes

- The server HUD has the same menu categories as the table tablet.
- The server enters the customer's legacy name.
- The HUD resolves that name to an avatar key with `llRequestUserKey`.
- The server must set the correct table ID before placing the bill.
- The customer still pays through the table Tap-to-Pay object.

## Owner HUD Notes

- The Owner Operations HUD uses `/api/owner/operations`.
- It is read-only and shows active carts, pending bills, kitchen counts,
  completed orders today, sales today, and active tables.
- The web dashboard is available at `/owner` and refreshes every 5 seconds.
- It also shows kitchen dispenser inventory total and low-stock items.
- If `HANGAR_OWNER_CODE` is set on Render, set the same value in the HUD script's
  `OWNER_CODE` variable, or open `/owner?owner_code=YOUR_CODE`.

## Kitchen Dispenser Inventory Notes

- The kitchen dispenser posts exact inventory snapshots to
  `/api/inventory/snapshot`.
- Inventory is not deducted when orders are paid.
- Inventory is deducted only when the item is actually removed from the dispenser
  inventory, such as when the dispenser gives the item to staff.
- The backend stores the latest count for each tracked dispenser item.

## Updating Prices

Prices are controlled in the `MENU` list inside `app.py`.

After editing prices or menu items:

1. Upload the updated `app.py` to the GitHub/Render repo.
2. Redeploy the Render service, or wait for auto-deploy.
3. Test with the table tablet, server HUD, Tap-to-Pay, and kitchen board.

The Second Life scripts use static item IDs, so if a menu item ID changes in
`app.py`, update the matching ID in both the table tablet and server HUD scripts.
