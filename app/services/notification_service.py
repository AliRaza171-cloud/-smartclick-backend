from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User, UserRole


def notify_admins_new_order(db: Session, order) -> None:
    """Every admin user gets this — there's no per-admin routing yet since
    this is a single-store setup, not a multi-vendor marketplace."""
    admins = db.query(User).filter(User.role == UserRole.admin).all()
    for admin in admins:
        db.add(Notification(
            user_id=admin.id,
            type="new_order",
            title="New order received",
            message=f"Order #{str(order.id)[:8]} — Rs. {float(order.total):,.0f}",
            link=f"/orders/{order.id}",
        ))
    db.commit()


def notify_buyer_payment_received(db: Session, order) -> None:
    db.add(Notification(
        user_id=order.user_id,
        type="payment_received",
        title="Payment received",
        message=f"Order #{str(order.id)[:8]} — Rs. {float(order.total):,.0f} received.",
        link=f"/orders/{order.id}",
    ))
    db.commit()


def notify_buyer_order_ready_to_ship(db: Session, order) -> None:
    db.add(Notification(
        user_id=order.user_id,
        type="order_ready_to_ship",
        title="Your order is ready to ship",
        message=f"Order #{str(order.id)[:8]} is packed and about to be handed off for delivery.",
        link=f"/orders/{order.id}",
    ))
    db.commit()
def notify_admins_cancellation_requested(db: Session, order) -> None:
    admins = db.query(User).filter(User.role == UserRole.admin).all()
    for admin in admins:
        db.add(Notification(
            user_id=admin.id,
            type="cancellation_requested",
            title="Order cancellation requested",
            message=f"Buyer requested cancellation for order #{str(order.id)[:8]}.",
            link=f"/orders/{order.id}",
        ))
    db.commit()


def notify_buyer_cancellation_decision(db: Session, order, approved: bool) -> None:
    db.add(Notification(
        user_id=order.user_id,
        type="cancellation_decision",
        title="Cancellation approved" if approved else "Cancellation request declined",
        message=(
            f"Order #{str(order.id)[:8]} has been cancelled."
            if approved
            else f"Your cancellation request for order #{str(order.id)[:8]} was declined — it's already on its way."
        ),
        link=f"/orders/{order.id}",
    ))
    db.commit()


def notify_admins_new_order_message(db: Session, order) -> None:
    admins = db.query(User).filter(User.role == UserRole.admin).all()
    for admin in admins:
        db.add(Notification(
            user_id=admin.id,
            type="order_message",
            title="New message from buyer",
            message=f"New message on order #{str(order.id)[:8]}.",
            link=f"/orders/{order.id}",
        ))
    db.commit()


def notify_buyer_new_order_message(db: Session, order) -> None:
    db.add(Notification(
        user_id=order.user_id,
        type="order_message",
        title="New message about your order",
        message=f"Support replied on order #{str(order.id)[:8]}.",
        link=f"/orders/{order.id}",
    ))
    db.commit()
def notify_admins_new_question(db: Session, question, product_title: str) -> None:
    admins = db.query(User).filter(User.role == UserRole.admin).all()
    for admin in admins:
        db.add(Notification(
            user_id=admin.id,
            type="new_question",
            title="New product question",
            message=f'On "{product_title}": {question.question[:80]}',
            link=f"/product/{question.product_id}",
        ))
    db.commit()


def notify_buyer_question_answered(db: Session, question, product_title: str) -> None:
    db.add(Notification(
        user_id=question.user_id,
        type="question_answered",
        title="Your question was answered",
        message=f'On "{product_title}": {question.answer[:80]}',
        link=f"/product/{question.product_id}",
    ))
    db.commit()

def notify_buyer_order_shipped(db: Session, order) -> None:
    db.add(Notification(
        user_id=order.user_id,
        type="order_shipped",
        title="Your order has shipped",
        message=f"Order #{str(order.id)[:8]} is on its way.",
        link=f"/orders/{order.id}",
    ))
    db.commit()
def notify_buyer_order_delivered(db: Session, order) -> None:
    db.add(Notification(
        user_id=order.user_id,
        type="order_delivered",
        title="Your order has arrived",
        message=f"Order #{str(order.id)[:8]} has been delivered.",
        link=f"/orders/{order.id}",
    ))
    db.commit()