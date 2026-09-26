"""
Safepay integration — Pakistani cards + JazzCash + EasyPaisa via one hosted
checkout page, settled in PKR.

Honesty note (unlike the Stripe integration, where every detail below was
confirmed against Stripe's own extensive docs): Safepay's public
documentation is thinner, so two specific details here are implemented
using their most consistently-documented pattern across their official
SDKs, but should be double-checked against your own sandbox dashboard
before this goes anywhere near real money:
  1. The exact webhook payload shape (which field carries our order id back
     to us) — implemented reading `order_id`/`orderId` with a fallback to
     looking the order up by the stored `safepay_token`.
  2. The exact webhook signature algorithm — implemented as HMAC-SHA256
     over the raw request body, which is the standard pattern their other
     official SDKs (Node, PHP, .NET) describe, but confirm this against
     the "Webhooks" section of your own Safepay dashboard once you have
     sandbox access, and adjust `_compute_signature` below if it differs.
"""
import asyncio
import hmac
import hashlib

from safepay_python.safepay import Safepay
from fastapi import HTTPException, status

from app.core.config import settings


def _ensure_event_loop() -> None:
    """
    The safepay-python SDK uses asyncio internally, but FastAPI runs a
    regular (non-async def) route in a worker thread that has no event
    loop set up by default — calling the SDK there raises "There is no
    current event loop in thread ...". This creates one for the current
    thread if none exists yet, which the SDK can then find and use.
    """
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


def _client() -> Safepay:
    if not settings.SAFEPAY_API_KEY:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Safepay isn't configured yet. Set SAFEPAY_API_KEY (and the other SAFEPAY_* settings) in the backend's .env.",
        )
    return Safepay({
        "environment": settings.SAFEPAY_ENVIRONMENT,
        "apiKey": settings.SAFEPAY_API_KEY,
        "v1Secret": settings.SAFEPAY_V1_SECRET,
        "webhookSecret": settings.SAFEPAY_WEBHOOK_SECRET,
    })


def create_checkout_session(order) -> tuple[str, str]:
    """Returns (token, checkout_url). token is stored on the order so the
    webhook handler can match an incoming event back to this order even if
    the payload's order-id field turns out to be named differently than
    expected."""
    _ensure_event_loop()
    env = _client()

    # Smallest currency unit (paisa), matching the pattern their Node/Python
    # SDK examples show (amount: 10000 for what reads as Rs. 100) — the same
    # convention Stripe uses. Confirm against a real sandbox transaction.
    amount_smallest_unit = int(order.total * 100)

    try:
        payment_response = env.set_payment_details({
            "amount": amount_smallest_unit,
            "currency": settings.SAFEPAY_CURRENCY,
        })
        print(f"[safepay] set_payment_details raw response: {payment_response!r}")
        token = payment_response["data"]["token"]

        checkout_url = env.get_checkout_url({
            "beacon": token,
            "orderId": str(order.id),
            "cancelUrl": f"{settings.FRONTEND_URL}/orders/{order.id}?payment=cancelled",
            "redirectUrl": f"{settings.FRONTEND_URL}/orders/{order.id}?payment=success",
            "source": "custom",
            "webhooks": True,
        })
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Safepay error: {str(e)}")

    return token, checkout_url


def _compute_signature(raw_body: bytes) -> str:
    return hmac.new(
        settings.SAFEPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()


def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Constant-time comparison — this is what stops anyone from POSTing a
    fake "payment succeeded" event at our webhook URL. Returns False (never
    raises) so the route can decide how to respond; an order is only ever
    marked paid when this returns True.
    """
    if not settings.SAFEPAY_WEBHOOK_SECRET or not signature_header:
        return False
    expected = _compute_signature(raw_body)
    return hmac.compare_digest(expected, signature_header)