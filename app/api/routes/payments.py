import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.services.payment_service import create_checkout_session, verify_webhook_event
from app.services import safepay_service
from app.services.email_service import send_payment_received_email
from app.services.notification_service import notify_buyer_payment_received

router = APIRouter(tags=["payments"])


@router.post("/orders/{order_id}/checkout-session")
def start_checkout_session(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if order.payment_method != "card":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order isn't set up for card payment.")
    if order.status != OrderStatus.pending_payment:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This order is already {order.status.value}.")

    session_id, checkout_url = create_checkout_session(order)
    order.stripe_checkout_session_id = session_id
    db.commit()

    return {"checkout_url": checkout_url}


@router.post("/orders/{order_id}/safepay-checkout-session")
def start_safepay_checkout_session(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if order.payment_method != "safepay":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order isn't set up for Safepay.")
    if order.status != OrderStatus.pending_payment:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This order is already {order.status.value}.")

    token, checkout_url = safepay_service.create_checkout_session(order)
    order.safepay_token = token
    db.commit()

    return {"checkout_url": checkout_url}


@router.post("/webhooks/safepay")
async def safepay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Same rule as the Stripe webhook: this is the ONLY place a safepay order
    is ever marked paid. The redirect the buyer's browser lands on proves
    nothing by itself — only a signature-verified event does.
    """
    payload = await request.body()
    signature = request.headers.get("x-sfpy-signature", "")

    if not safepay_service.verify_webhook_signature(payload, signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature.")

    print(f"[safepay webhook] Received event: {json.dumps(event, indent=2)}")

    order_id = event.get("order_id") or event.get("orderId") or event.get("data", {}).get("order_id")
    token = event.get("token") or event.get("data", {}).get("token")

    order = None
    if order_id:
        order = db.query(Order).filter(Order.id == order_id).first()
    if not order and token:
        order = db.query(Order).filter(Order.safepay_token == token).first()

    if order and order.status != OrderStatus.paid:
        order.status = OrderStatus.paid
        db.commit()

        try:
            send_payment_received_email(order.user.email, order)
        except Exception as e:
            print(f"[payments] Safepay payment-received email failed for order {order.id}: {e}")

        try:
            notify_buyer_payment_received(db, order)
        except Exception as e:
            print(f"[payments] In-app Safepay payment-received notification failed for order {order.id}: {e}")

    return {"received": True}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    This is the ONLY place an order is ever marked paid. Never trust the
    buyer's browser redirecting to a "success" URL — that tells us nothing
    except that Stripe sent them somewhere; only a signature-verified event
    straight from Stripe proves the charge actually went through.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    event = verify_webhook_event(payload, signature)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("metadata", {}).get("order_id")

        if order_id:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order and order.status != OrderStatus.paid:
                order.status = OrderStatus.paid
                db.commit()

                try:
                    buyer_email = order.user.email
                    send_payment_received_email(buyer_email, order)
                except Exception as e:
                    print(f"[payments] Payment-received email failed for order {order.id}: {e}")

                try:
                    notify_buyer_payment_received(db, order)
                except Exception as e:
                    print(f"[payments] In-app payment-received notification failed for order {order.id}: {e}")

    return {"received": True}