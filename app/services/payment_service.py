import stripe
from fastapi import HTTPException, status

from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(order) -> str:
    """
    Returns the Stripe-hosted checkout page URL to redirect the buyer to.
    We never touch card details ourselves — Stripe Checkout is a page
    Stripe hosts entirely, which is also what keeps this out of PCI scope.
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Card payments aren't configured yet. Set STRIPE_SECRET_KEY in the backend's .env.",
        )

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": settings.STRIPE_CURRENCY,
                    "unit_amount": int(order.total * 100),  # smallest currency unit
                    "product_data": {"name": f"Smart Click order #{str(order.id)[:8]}"},
                },
                "quantity": 1,
            }],
            metadata={"order_id": str(order.id)},
            success_url=f"{settings.FRONTEND_URL}/orders/{order.id}?payment=success",
            cancel_url=f"{settings.FRONTEND_URL}/orders/{order.id}?payment=cancelled",
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Stripe error: {str(e)}")

    return session.id, session.url


def verify_webhook_event(payload: bytes, signature: str):
    """
    Raises if the signature doesn't check out — this is what stops anyone
    from just POSTing a fake "payment succeeded" event at our webhook URL
    and getting an order marked paid for free. Only Stripe, holding the
    matching webhook secret, can produce a signature that verifies here.
    """
    try:
        return stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature.")
