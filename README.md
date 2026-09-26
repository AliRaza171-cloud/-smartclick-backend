# Smart Click — Auth Backend (Phase 1)

FastAPI + PostgreSQL. This is the authentication foundation the rest of
Smart Click builds on.

## Run it

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real secrets
# create the Postgres DB, then create tables (swap for Alembic migrations
# once the schema stabilizes):
python -c "from app.db.session import Base, engine; from app.models import user, product, order, category, notification, wishlist, analytics; Base.metadata.create_all(engine)"

# Phase 6 and 7 added columns to the already-existing orders table, which
# create_all above does NOT alter — run these once via psql if you haven't:
#   CREATE TYPE fulfillmentstatus AS ENUM ('pending', 'ready_to_ship', 'shipped');
#   ALTER TABLE orders ADD COLUMN fulfillment_status fulfillmentstatus NOT NULL DEFAULT 'pending';
#   CREATE TYPE paymentmethod AS ENUM ('cod', 'easypaisa', 'jazzcash', 'card');
#   ALTER TABLE orders ADD COLUMN payment_method paymentmethod NOT NULL DEFAULT 'cod';
#   ALTER TABLE orders ADD COLUMN cod_fee NUMERIC(10,2) NOT NULL DEFAULT 0;
#   ALTER TABLE orders ADD COLUMN stripe_checkout_session_id VARCHAR;
#   ALTER TYPE paymentmethod ADD VALUE 'safepay';
#   ALTER TABLE orders ADD COLUMN safepay_token VARCHAR;
#   ALTER TABLE vouchers ADD COLUMN applicable_product_ids UUID[];
#   ALTER TABLE vouchers ADD COLUMN grants_free_shipping BOOLEAN NOT NULL DEFAULT false;
# wishlist_items and analytics_events are brand-new tables (not altering
# existing ones), so the normal create_all command above handles them —
# no manual SQL needed for those two.
uvicorn app.main:app --reload
```

## Endpoints

| Method | Path                   | Notes                                   |
|--------|------------------------|------------------------------------------|
| POST   | /auth/register         | Rate-limited, password strength enforced |
| POST   | /auth/login             | Rate-limited, account lockout on repeated failures |
| POST   | /auth/refresh           | Reads httpOnly cookie, rotates token, CSRF-checked |
| POST   | /auth/logout            | Revokes the refresh token, CSRF-checked |
| GET    | /auth/me                | Requires Bearer access token |
| POST   | /auth/verify-email      | Consumes a signed, expiring token |
| POST   | /auth/forgot-password   | Always 204 — doesn't reveal if the email exists |
| POST   | /auth/reset-password    | Consumes a signed, expiring token |
| GET    | /auth/google/login      | Starts the OAuth redirect flow |
| GET    | /auth/google/callback   | Exchanges the code server-side |
| POST   | /categories             | Admin-only. Create a category on the fly |
| GET    | /categories             | Public. List all categories |
| POST   | /products/analyze       | Admin-only. Proxies images to the AI Agent service (Phase 4) |
| POST   | /products               | Admin-only. Publishes a real listing (multipart: images + fields) |
| GET    | /products               | Public. `?category=Electronics` to filter |
| GET    | /products/{id}          | Public |
| PATCH  | /products/{id}          | Admin-only. Partial update (price, discount, active/inactive, etc.) |
| POST   | /vouchers               | Admin-only. Create a voucher |
| GET    | /vouchers               | Admin-only. List all vouchers |
| PATCH  | /vouchers/{code}/deactivate | Admin-only |
| GET    | /vouchers/{code}/check  | Public. Buyer-facing validity check for checkout (Phase 6) |
| POST   | /orders                 | Requires login. Places an order — all prices recalculated server-side |
| GET    | /orders                 | Requires login. Lists the current user's own orders |
| GET    | /orders/{id}            | Requires login. Own orders only — admins can view ANY order (labels, support) |
| PATCH  | /orders/{id}/status     | Admin-only. Advances fulfillment_status (pending → ready_to_ship → shipped) |
| GET    | /store-info             | Public. Store's own name/address/phone — the "from" side of shipping labels |
| GET    | /notifications          | Requires login. Current user's own, newest first, capped at 30 |
| GET    | /notifications/unread-count | Requires login |
| PATCH  | /notifications/{id}/read | Requires login. Own notifications only |
| PATCH  | /notifications/read-all | Requires login |
| POST   | /wishlist/{product_id}  | Requires login. Idempotent — adding twice is a no-op |
| DELETE | /wishlist/{product_id}  | Requires login |
| GET    | /wishlist                | Requires login. Current user's saved products |
| GET    | /wishlist/check/{product_id} | Requires login |
| POST   | /analytics/track         | Public. Works for anonymous visitors via a long-lived cookie |
| GET    | /analytics/summary       | Admin-only. Visitor counts + top products by view/cart/wishlist |

## Security measures and why

- **Passwords**: bcrypt via passlib. Never logged, never stored reversibly.
  Server-side strength check in `core/security.is_password_strong` — never
  trust client-side validation alone.
- **Access tokens**: short-lived (15 min) JWTs. The frontend keeps this in a
  JS variable, **never localStorage/sessionStorage** — an XSS payload that
  reads localStorage would otherwise get a long-lived, directly usable token.
- **Refresh tokens**: opaque `selector.verifier` strings, not JWTs. The
  selector is indexed plaintext (fast lookup); only the verifier's hash is
  stored, so a DB leak alone doesn't hand out usable sessions. Stored in an
  **httpOnly, Secure, SameSite=strict** cookie — unreadable by JS.
- **Rotation + reuse detection**: every `/auth/refresh` call revokes the old
  token and issues a new one in the same "family." If a revoked token is
  ever presented again, the whole family is revoked — that pattern only
  happens if a token was stolen and used after the real user already moved
  past it.
- **CSRF**: double-submit cookie pattern on the two endpoints that trust a
  cookie directly (`/auth/refresh`, `/auth/logout`). Combined with
  `SameSite=strict`, which already blocks the cookie being sent cross-site
  in most browsers — this is defense in depth, not the only layer.
- **Rate limiting**: per-IP limits on register/login/forgot-password via
  slowapi, to blunt brute-force and credential-stuffing.
- **Account lockout**: temporary lock after `MAX_FAILED_LOGIN_ATTEMPTS`,
  independent of rate limiting (protects a single targeted account even from
  a distributed/slow attack that rate limiting alone wouldn't catch).
- **No user enumeration**: login and forgot-password return the same
  response shape regardless of whether the email exists.
- **Security headers**: HSTS (prod only), X-Content-Type-Options, X-Frame-
  Options, a baseline CSP, and a restrictive Permissions-Policy, applied
  globally via middleware.
- **CORS**: explicit origin allow-list from env — never `*`, especially
  since `allow_credentials=True` is required for the cookie flow.
- **SQL injection**: not reachable — every query goes through the SQLAlchemy
  ORM with parameter binding, no raw string-built SQL anywhere.
- **Google OAuth**: standard authorization-code flow, exchanged server-side.
  We never accept a client-supplied ID token as proof of identity, since a
  compromised frontend could otherwise hand us a token for any account.

## AI Agent service (Phase 4)

`/products/analyze` requires an admin-authenticated user and forwards
uploaded images to a **separate** service (`smartclick-ai-service`, run on
its own port — see its own README). This backend never calls OpenAI
directly; it proxies with a timeout (`AI_SERVICE_TIMEOUT_SECONDS`) and
returns a clean `503` if that service is down or slow, so an AI outage never
blocks someone from creating a listing manually. Requires
`AI_SERVICE_URL` and `INTERNAL_AI_SERVICE_KEY` in `.env` — the latter must
exactly match the AI service's own `INTERNAL_API_KEY`.

## Becoming an admin (until Phase 8's admin panel exists)

Every new registration defaults to the `buyer` role — there's no promote-to-
admin UI yet. To test the admin upload flow, manually update your own user
row via `psql` or pgAdmin:

```sql
UPDATE users SET role = 'admin' WHERE email = 'your@email.com';
```

Log out and back in afterward so the new role shows up on the frontend
(the role is embedded in the access token issued at login).

## Product management (Phase 5)

- `/products` (POST) is a **separate call from `/products/analyze`** —
  the AI draft is never auto-published. The frontend calls `/analyze` first,
  shows the admin an editable draft, and only calls `POST /products` once
  they've reviewed/edited it and filled in price, discount, voucher, and
  free-shipping.
- Images save to a local `uploads/` folder and are served at `/static/...`.
  This is a **local-disk simplification for development only** — it won't
  survive a redeploy on most hosts and doesn't scale past one server. Swap
  for S3 or Cloudflare R2 before deploying anywhere beyond localhost.
- **Categories are now a real table** (`app/models/category.py`), not a
  fixed list — an admin can add one on the fly via `POST /categories` (from
  the product upload page) when a new product doesn't fit anything
  existing. `POST /products` validates `category` against this table.
  The AI Agent service receives the CURRENT category list on every
  `/analyze` call (fetched fresh from this table), so a newly-added
  category is immediately something the model can pick — nothing to
  redeploy or keep in sync manually anymore.
- A voucher is looked up by its `code` as a natural key (not a separate
  UUID) — simple for a single-store setup, revisit if vouchers ever need to
  be renamed after creation.
- `ai_generated` / `ai_flagged_needs_review` are stored on the product even
  after the seller edits the draft — useful later for an admin view of which
  listings the AI was less confident about.

## Cart & checkout (Phase 6)

- **The cart itself lives in the frontend's browser storage, not the
  database** — the backend only sees a cart at the moment of `POST /orders`
  (a list of `{product_id, quantity}`).
- **Every price is recalculated server-side** from the current `Product`
  rows — the request body's job is only to say *what* and *how many*, never
  *how much*. This is what stops a tampered request from buying something
  at a fake price.
- **Order items are a JSONB snapshot**, not a live join to `products` — so
  a price change or a deleted product afterward never rewrites a past
  order's history.
- **Voucher redemption**: validity (`is_valid`), minimum order value, and
  usage-limit incrementing all happen inside `POST /orders` itself, in the
  same transaction as creating the order — a voucher's `used_count` only
  increments once an order is actually placed with it.
- **No payment yet** — every order is created with `status: pending_payment`.
  Phase 7 (Stripe + local gateways) is what actually processes payment and
  moves an order to `paid`.
- **Shipping cost isn't modeled** — `free_shipping` is a boolean on the
  order (true if any line item's product has it), but there's no flat
  shipping fee charged when it's false. Add a shipping-fee field if that
  matters before this goes further.

## Email notifications

`app/services/email_service.py` sends real email via SMTP for: order
confirmation (to the buyer), new-order notification (to
`ADMIN_NOTIFICATION_EMAIL`), and the verification/password-reset links from
Phase 1 (previously just printed to console). With `SMTP_HOST` left blank in
`.env`, it falls back to printing instead of sending — so local development
works with zero email setup. For real sending, Gmail works fine for
development: use `smtp.gmail.com`, port `587`, and an **App Password**
(myaccount.google.com/apppasswords) — not your normal Google password, which
Gmail will reject for SMTP.

Email failures never fail the request that triggered them — an order still
succeeds even if its confirmation email fails to send; the failure is only
printed to the console.

## Shipping labels

Set `STORE_NAME`, `STORE_ADDRESS`, `STORE_CITY`, `STORE_PHONE` in `.env` —
that's the "from" side of every printable shipping label (frontend's
`/admin/orders/[id]/label`). `GET /orders/{id}` now lets an admin view ANY
order, not just their own, since printing a label for a customer's order is
exactly this kind of legitimate admin need.

## Order fulfillment tracking

`Order.fulfillment_status` (pending → ready_to_ship → shipped) is
**deliberately separate** from `Order.status` (pending_payment/paid/
cancelled) — they're two different dimensions of an order's life, not one
combined state. `PATCH /orders/{id}/status` (admin-only) advances it; moving
to `shipped` sends the buyer a "your order has shipped" email (moving to
`ready_to_ship` doesn't — that's an internal step, not something worth
emailing a buyer about). The admin new-order email also now includes a
direct "Print shipping label" button.

**This required a manual SQL migration**, not just the usual table-creation
command — `fulfillment_status` was added to an existing table
(`Base.metadata.create_all` only creates missing tables, it doesn't alter
existing ones). This project doesn't have real migrations (Alembic) set up
yet; that's worth adding before this schema needs to change again.

## In-app notifications

`app/models/notification.py` — a plain per-user notification row (`type`,
`title`, `message`, `link`, `is_read`). Created for every admin when an
order is placed (`notify_admins_new_order`), and for the buyer when their
order ships (`notify_buyer_order_shipped`) — alongside the equivalent
emails, not instead of them. These are plain REST endpoints
(`/notifications`), so a future mobile app (Phase 8, not built yet) uses
this exact same API — nothing here is web-specific.

**No real-time push** — the frontend polls `/notifications/unread-count`
every 30 seconds rather than using WebSockets or Server-Sent Events. Fine
for a single-admin store's volume; worth revisiting if this needs to feel
instant at higher order volume.

## Payments (Phase 7 — Stripe)

Cash on Delivery (`payment_method: "cod"`) has always worked with no
external dependency — it just adds a flat Rs. 30 handling fee at order
creation. Card payments now go through **Stripe Checkout**:

| Method | Path |
|---|---|
| POST | /orders/{id}/checkout-session | Requires login, must be the order's own buyer. Only valid when `payment_method == "card"` and `status == "pending_payment"`. Returns `{checkout_url}` to redirect the buyer to. |
| POST | /webhooks/stripe | Public, but signature-verified. **This is the only place an order is ever marked `paid`.** |

**Why the webhook, not the redirect**: Stripe redirects the buyer's browser
back to `success_url` regardless of whether the payment actually completed
in every edge case (closed tab, network blip) — and a malicious client
could hit that URL directly without paying anything. The webhook is signed
by Stripe using `STRIPE_WEBHOOK_SECRET`; only a request carrying a valid
signature can mark an order paid. `verify_webhook_event()` in
`payment_service.py` rejects anything else with a 400.

### Setting this up

1. Create a free Stripe account at stripe.com — test-mode API keys are
   available immediately, no business verification needed to start.
2. Dashboard → Developers → API keys → copy the **Secret key** (starts
   `sk_test_...`) into `STRIPE_SECRET_KEY`.
3. **Testing the webhook locally** needs the Stripe CLI, since Stripe's
   servers can't reach `localhost` directly:
   - Install it: stripe.com/docs/stripe-cli
   - Run `stripe login` once
   - Run `stripe listen --forward-to localhost:8000/webhooks/stripe` — it
     prints a webhook signing secret (`whsec_...`); put that in
     `STRIPE_WEBHOOK_SECRET`
   - Leave that `stripe listen` command running in its own terminal
     whenever you're testing a payment — it's what actually delivers
     Stripe's webhook events to your local backend.
4. `STRIPE_CURRENCY` defaults to `pkr`. If PKR charges fail on your
   account (support can depend on account region/activation), switch this
   to `usd` and adjust how `order.total` is converted before charging.

### Safepay (Pakistani cards + JazzCash + EasyPaisa)

`payment_method: "safepay"` routes to `app/services/safepay_service.py` —
one hosted checkout page where the buyer picks between a Pakistani
bank-issued card, JazzCash, or EasyPaisa, settled directly in PKR. This
**replaces** the old separate `"easypaisa"`/`"jazzcash"` checkout options
(still valid enum values on the model for legacy rows, but no longer
offered at checkout) — those two wallets are chosen on Safepay's own page,
not as separate top-level buttons on ours.

| Method | Path |
|---|---|
| POST | /orders/{id}/safepay-checkout-session | Requires login, own order only. Only valid when `payment_method == "safepay"` and `status == "pending_payment"`. |
| POST | /webhooks/safepay | Public, signature-verified. Only place a safepay order is ever marked `paid`. |

**Setup**: sign up free at getsafepay.com, grab your sandbox `apiKey` and
`v1Secret` from the dashboard, no business verification needed until you
switch to production.

**Important honesty note**: unlike the Stripe integration above, Safepay's
public documentation is thinner, so two details in `safepay_service.py`
are implemented using their most consistently-documented pattern across
official SDKs (Node/PHP/.NET) rather than 100%-confirmed specifics:
- The webhook payload's exact field name for the order id (tries `order_id`,
  `orderId`, falls back to matching on `safepay_token`)
- The exact webhook signature algorithm (implemented as HMAC-SHA256 over
  the raw body)

Confirm both against your own sandbox's actual webhook payload/dashboard
docs before trusting this with real transactions — the signature check
itself is never skipped or weakened, but which exact bytes it's checking
against is worth a real test to confirm.

## Analytics

`app/models/analytics.py` — every event (`page_view`, `product_view`,
`add_to_cart`, `add_to_wishlist`) is logged with an anonymous session-cookie
identifier (`smartclick_session`), so unique visitor counting works even for
buyers who never log in. If a request does carry a valid access token, the
event is also tagged with that user — but this is never required. Admin's
`/analytics/summary` aggregates visitor counts and the top 10 products by
each event type.

**No PII collected beyond what the cookie inherently is** — no IP logging,
no fingerprinting beyond the session cookie itself.

## Wishlist

Plain per-user saved-products list (`app/models/wishlist.py`), unlike the
cart which lives in the browser only — a wishlist is something a buyer
reasonably expects to survive across devices, so it's tied to their account
and requires login.

## Voucher scoping (product-specific + free-shipping-granting)

`Voucher.applicable_product_ids` (nullable array) — when set, the discount
in `create_order` is calculated only against the subtotal of matching line
items, never the whole cart, even though `min_order_value` is still checked
against the full cart total. Null/empty means store-wide, same as before.

`Voucher.grants_free_shipping` — independent of any product's own
`free_shipping` flag. A voucher can grant free shipping with no discount at
all (`discount_value: 0` is allowed specifically when this is `true` — the
schema's `must_do_something` validator ensures a voucher can never do
literally nothing).

## Known simplifications (fix before real users touch this)

- Email sending is stubbed to `print()` — wire up a real provider (SES,
  Postmark, Resend) before verification/reset links matter.
- Table creation uses `Base.metadata.create_all` for now — switch to Alembic
  migrations once the schema is stable, same as the ShopAI project.
- The Google OAuth callback redirects with cookies already set — in a
  stricter production setup, hand the frontend a one-time exchange code
  instead of relying on the redirect alone.
- Password reset doesn't yet revoke existing sessions — add that so a leaked
  session can't survive the user resetting their password.