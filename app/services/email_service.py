import httpx

from app.core.config import settings


def send_email(to: str, subject: str, html_body: str) -> bool:
    """
    Sends a real email via the Resend HTTP API. Returns False (never raises)
    on failure — email is a side effect, not something that should ever take
    down the request that triggered it.
    """
    if not settings.RESEND_API_KEY:
        # No Resend key configured — fall back to printing, same as the
        # original dev stub, so local development still works without
        # real credentials.
        print(f"[dev] Email to {to}: {subject}\n{html_body}")
        return True

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "html": html_body,
            },
            timeout=10,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        print(f"[email] Failed to send to {to}: {e.response.status_code} {e.response.text}")
        return False
    except Exception as e:
        print(f"[email] Failed to send to {to}: {e}")
        return False

def send_order_confirmation_email(user_email: str, order) -> None:
    items_html = "".join(
        f"<tr><td>{item['title']} × {item['quantity']}</td>"
        f"<td>Rs. {float(item['unit_price']) * item['quantity']:,.0f}</td></tr>"
        for item in order.items
    )
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <h2>Order confirmed</h2>
      <p>Order #{str(order.id)[:8]} — thanks for shopping with Smart Click.</p>
      <table style="width:100%; border-collapse: collapse;">{items_html}</table>
      <p><strong>Total: Rs. {float(order.total):,.0f}</strong></p>
      <p>Shipping to: {order.shipping_name}, {order.shipping_address}, {order.shipping_city}</p>
      <p style="color:#888; font-size:13px;">Status: {order.status.value.replace('_', ' ')}</p>
    </div>
    """
    send_email(user_email, f"Order confirmed — #{str(order.id)[:8]}", html)


def send_payment_received_email(user_email: str, order) -> None:
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <h2>Payment received</h2>
      <p>We've received your payment of Rs. {float(order.total):,.0f} for order #{str(order.id)[:8]}. We'll start preparing it for shipping.</p>
    </div>
    """
    send_email(user_email, f"Payment received — #{str(order.id)[:8]}", html)


def send_order_ready_to_ship_email(user_email: str, order) -> None:
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <h2>Your order is ready to ship</h2>
      <p>Order #{str(order.id)[:8]} is packed and about to be handed off for delivery.</p>
      <p>Shipping to: {order.shipping_name}, {order.shipping_address}, {order.shipping_city}</p>
    </div>
    """
    send_email(user_email, f"Order ready to ship — #{str(order.id)[:8]}", html)


def send_order_shipped_email(user_email: str, order) -> None:
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <h2>Your order has shipped</h2>
      <p>Order #{str(order.id)[:8]} is on its way to you.</p>
      <p>Shipping to: {order.shipping_name}, {order.shipping_address}, {order.shipping_city}</p>
    </div>
    """
    send_email(user_email, f"Your order has shipped — #{str(order.id)[:8]}", html)


def send_order_delivered_email(user_email: str, order) -> None:
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <h2>Your order has arrived</h2>
      <p>Order #{str(order.id)[:8]} has been delivered. We'd love to hear what you think — you can now leave a rating and review for the items in this order.</p>
    </div>
    """
    send_email(user_email, f"Your order has arrived — #{str(order.id)[:8]}", html)


def send_admin_new_order_email(order) -> None:
    if not settings.ADMIN_NOTIFICATION_EMAIL:
        return
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <h2>New order received</h2>
      <p>Order #{str(order.id)[:8]} — total Rs. {float(order.total):,.0f}</p>
      <p>Shipping to: {order.shipping_name}, {order.shipping_city}</p>
    </div>
    """
    send_email(settings.ADMIN_NOTIFICATION_EMAIL, f"New order — #{str(order.id)[:8]}", html)


def send_verification_email(to: str, verify_url: str) -> None:
    html = f"""
    <div style="font-family: sans-serif;">
      <h2>Verify your email</h2>
      <p><a href="{verify_url}">Click here to verify your Smart Click account</a></p>
    </div>
    """
    send_email(to, "Verify your Smart Click account", html)


def send_password_reset_email(to: str, reset_url: str) -> None:
    html = f"""
    <div style="font-family: sans-serif;">
      <h2>Reset your password</h2>
      <p><a href="{reset_url}">Click here to reset your password</a> — this link expires soon.</p>
    </div>
    """
    send_email(to, "Reset your Smart Click password", html)