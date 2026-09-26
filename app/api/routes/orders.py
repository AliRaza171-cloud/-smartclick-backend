import uuid
from decimal import Decimal
from datetime import datetime
from types import SimpleNamespace
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.models.user import User, UserRole
from app.models.product import Product
from app.models.order import Order, OrderStatus, FulfillmentStatus, OrderMessage
from app.models.product import Voucher
from app.schemas.order import OrderCreate, OrderOut, FulfillmentStatusUpdate
from app.schemas.order_message import OrderMessageCreate, OrderMessageOut, CancellationDecision
from app.services.email_service import (
    send_order_confirmation_email,
    send_admin_new_order_email,
    send_order_ready_to_ship_email,
    send_order_shipped_email,
    send_order_delivered_email,
)
from app.services.notification_service import (
    notify_admins_new_order,
    notify_buyer_order_ready_to_ship,
    notify_buyer_order_shipped,
    notify_buyer_order_delivered,
    notify_admins_cancellation_requested,
    notify_buyer_cancellation_decision,
    notify_admins_new_order_message,
    notify_buyer_new_order_message,
)

router = APIRouter(prefix="/orders", tags=["orders"])


def _unit_price(product: Product) -> Decimal:
    # Same convention as the frontend/Phase 5: `price` is the admin-entered
    # ORIGINAL price; discount_pct (if set) determines what the buyer pays.
    if product.discount_pct:
        return (product.price * (Decimal(100) - product.discount_pct) / Decimal(100)).quantize(Decimal("0.01"))
    return product.price


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Every price here is recalculated server-side from the database — the
    cart on the frontend is just a list of (product_id, quantity); a client
    could send anything, but what they're actually charged always comes from
    what's currently in the database, never from the request body.
    """
    order_items = []
    subtotal = Decimal("0")
    any_free_shipping = False

    for line in data.items:
        product = db.query(Product).filter(Product.id == line.product_id, Product.is_active == True).first()  # noqa: E712
        if not product:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Product {line.product_id} is no longer available.")

        unit_price = _unit_price(product)
        subtotal += unit_price * line.quantity
        if product.free_shipping:
            any_free_shipping = True

        order_items.append({
            "product_id": str(product.id),
            "title": product.title,
            "unit_price": str(unit_price),
            "quantity": line.quantity,
            "image_url": product.image_urls[0] if product.image_urls else None,
        })

    discount_amount = Decimal("0")
    voucher_code = None

    if data.voucher_code:
        voucher = db.query(Voucher).filter(Voucher.code == data.voucher_code.upper()).first()
        if not voucher or not voucher.is_valid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This voucher code is invalid or has expired.")
        if voucher.min_order_value and subtotal < voucher.min_order_value:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"This voucher requires a minimum order of Rs. {voucher.min_order_value}.",
            )

        # If scoped to specific products, the discount only ever applies to
        # THOSE line items' subtotal — never the whole cart — even though
        # min_order_value above is still checked against the full cart.
        if voucher.applicable_product_ids:
            applicable_ids = {str(pid) for pid in voucher.applicable_product_ids}
            discount_base = sum(
                (Decimal(item["unit_price"]) * item["quantity"] for item in order_items
                 if item["product_id"] in applicable_ids),
                Decimal("0"),
            )
            if discount_base == 0:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "This voucher doesn't apply to anything in your cart."
                )
        else:
            discount_base = subtotal

        if voucher.discount_type == "percent":
            discount_amount = (discount_base * voucher.discount_value / Decimal(100)).quantize(Decimal("0.01"))
        else:
            discount_amount = min(voucher.discount_value, discount_base)

        if voucher.grants_free_shipping:
            any_free_shipping = True

        voucher.used_count += 1
        voucher_code = voucher.code

    # Rs. 30 flat surcharge for cash-on-delivery, covering the extra
    # handling a cash pickup requires versus a prepaid order.
    COD_FEE = Decimal("30")
    cod_fee = COD_FEE if data.payment_method == "cod" else Decimal("0")

    total = max(subtotal - discount_amount, Decimal("0")) + cod_fee

    order = Order(
        user_id=user.id,
        items=order_items,
        subtotal=subtotal,
        voucher_code=voucher_code,
        discount_amount=discount_amount,
        free_shipping=any_free_shipping,
        total=total,
        payment_method=data.payment_method,
        cod_fee=cod_fee,
        shipping_name=data.shipping_name,
        shipping_phone=data.shipping_phone,
        shipping_address=data.shipping_address,
        shipping_city=data.shipping_city,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # Email failures never fail the order itself — the purchase already
    # succeeded in the database by this point; a notification email is a
    # side effect, not a condition of the order being valid.
    # Snapshot everything the emails need as plain values now, while the
    # session is still open — the background task runs after the response
    # is sent, by which point the DB session (and any lazy-loaded
    # attributes on `order`/`user`) may no longer be usable.
    order_snapshot = SimpleNamespace(
        id=order.id,
        items=order.items,
        total=order.total,
        status=order.status,
        shipping_name=order.shipping_name,
        shipping_address=order.shipping_address,
        shipping_city=order.shipping_city,
    )
    user_email = user.email

    def _send_order_emails():
        try:
            send_order_confirmation_email(user_email, order_snapshot)
            send_admin_new_order_email(order_snapshot)
        except Exception as e:
            print(f"[orders] Notification email failed for order {order_snapshot.id}: {e}")

    background_tasks.add_task(_send_order_emails)

    try:
        notify_admins_new_order(db, order)
    except Exception as e:
        print(f"[orders] In-app admin notification failed for order {order.id}: {e}")

    return order


@router.get("", response_model=list[OrderOut])
def list_my_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")

    order = db.query(Order).filter(Order.id == order_id).first()
    # Admins can look up any order (needed for shipping labels, support,
    # fulfillment) — everyone else only their own.
    if not order or (order.user_id != user.id and user.role != UserRole.admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_fulfillment_status(
    order_id: str,
    data: FulfillmentStatusUpdate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")

    old_status = order.fulfillment_status.value
    order.fulfillment_status = data.fulfillment_status
    db.commit()
    db.refresh(order)

    buyer = db.query(User).filter(User.id == order.user_id).first()

    if data.fulfillment_status == "ready_to_ship" and old_status != "ready_to_ship":
        try:
            if buyer:
                send_order_ready_to_ship_email(buyer.email, order)
        except Exception as e:
            print(f"[orders] Ready-to-ship email failed for order {order.id}: {e}")
        try:
            notify_buyer_order_ready_to_ship(db, order)
        except Exception as e:
            print(f"[orders] In-app ready-to-ship notification failed for order {order.id}: {e}")

    if data.fulfillment_status == "shipped" and old_status != "shipped":
        try:
            if buyer:
                send_order_shipped_email(buyer.email, order)
        except Exception as e:
            print(f"[orders] Shipped notification email failed for order {order.id}: {e}")
        try:
            notify_buyer_order_shipped(db, order)
        except Exception as e:
            print(f"[orders] In-app shipped notification failed for order {order.id}: {e}")

    if data.fulfillment_status == "delivered" and old_status != "delivered":
        try:
            if buyer:
                send_order_delivered_email(buyer.email, order)
        except Exception as e:
            print(f"[orders] Delivered notification email failed for order {order.id}: {e}")
        try:
            notify_buyer_order_delivered(db, order)
        except Exception as e:
            print(f"[orders] In-app delivered notification failed for order {order.id}: {e}")

    return order


def _get_order_for_access(order_id: str, user: User, db: Session) -> Order:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or (order.user_id != user.id and user.role != UserRole.admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    return order


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Buyer-initiated direct cancellation — only while the order is still
    'pending' (i.e. before the seller has started preparing it). Once it's
    ready_to_ship or beyond, use /request-cancellation instead, which
    requires admin approval since work may already be underway.
    """
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if order.status == OrderStatus.cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order is already cancelled.")
    if order.fulfillment_status != FulfillmentStatus.pending:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This order is already being prepared — request a cancellation instead.",
        )
    order.status = OrderStatus.cancelled
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/request-cancellation", response_model=OrderOut)
def request_cancellation(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if order.status == OrderStatus.cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order is already cancelled.")
    if order.fulfillment_status == FulfillmentStatus.pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use the direct cancel option for this order.")
    if order.cancellation_requested:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A cancellation request is already pending.")

    order.cancellation_requested = True
    db.add(OrderMessage(
        order_id=order.id,
        sender_id=user.id,
        sender_role="system",
        message="Buyer requested cancellation of this order.",
    ))
    db.commit()
    db.refresh(order)

    try:
        notify_admins_cancellation_requested(db, order)
    except Exception as e:
        print(f"[orders] Cancellation-requested notification failed for order {order.id}: {e}")

    return order


@router.patch("/{order_id}/cancellation-decision", response_model=OrderOut)
def decide_cancellation(
    order_id: str,
    data: CancellationDecision,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if not order.cancellation_requested:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No cancellation request is pending on this order.")

    order.cancellation_requested = False
    if data.approve:
        order.status = OrderStatus.cancelled

    db.add(OrderMessage(
        order_id=order.id,
        sender_id=order.user_id,
        sender_role="system",
        message="Cancellation approved — order cancelled." if data.approve else "Cancellation request declined.",
    ))
    db.commit()
    db.refresh(order)

    try:
        notify_buyer_cancellation_decision(db, order, data.approve)
    except Exception as e:
        print(f"[orders] Cancellation-decision notification failed for order {order.id}: {e}")

    return order


@router.get("/{order_id}/messages", response_model=list[OrderMessageOut])
def list_order_messages(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = _get_order_for_access(order_id, user, db)
    messages = (
        db.query(OrderMessage)
        .filter(OrderMessage.order_id == order.id)
        .order_by(OrderMessage.created_at.asc())
        .all()
    )
    for m in messages:
        m.sender_name = "Smart Click Support" if m.sender_role in ("admin", "system") else m.sender.full_name
    # Mark the other party's messages as read now that this user has fetched
    # the thread — mirrors typical chat "seen" behavior.
    other_role = "admin" if user.role != UserRole.admin else "buyer"
    db.query(OrderMessage).filter(
        OrderMessage.order_id == order.id, OrderMessage.sender_role == other_role, OrderMessage.is_read == False  # noqa: E712
    ).update({"is_read": True})
    db.commit()
    return messages


@router.post("/{order_id}/messages", response_model=OrderMessageOut, status_code=status.HTTP_201_CREATED)
def send_order_message(
    order_id: str,
    data: OrderMessageCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = _get_order_for_access(order_id, user, db)
    sender_role = "admin" if user.role == UserRole.admin else "buyer"
    msg = OrderMessage(order_id=order.id, sender_id=user.id, sender_role=sender_role, message=data.message)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    msg.sender_name = "Smart Click Support" if sender_role == "admin" else user.full_name

    try:
        if sender_role == "buyer":
            notify_admins_new_order_message(db, order)
        else:
            notify_buyer_new_order_message(db, order)
    except Exception as e:
        print(f"[orders] New-message notification failed for order {order.id}: {e}")

    return msg