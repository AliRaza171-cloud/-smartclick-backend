import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    is_password_strong,
    generate_refresh_token,
    hash_token,
    verify_token_hash,
)
from app.models.user import User, RefreshToken
from app.schemas.auth import RegisterRequest


def register_user(db: Session, data: RegisterRequest) -> User:
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        # Same generic message whether the email exists or not would leak less,
        # but for a real product, a clear "already registered" is usually the
        # better UX trade-off. Never leak *why* a login failed though (see below).
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An account with this email already exists.")

    ok, reason = is_password_strong(data.password)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, reason)

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()

    # Deliberately generic error for "no such user" AND "wrong password" —
    # a distinct message for each lets an attacker enumerate valid emails.
    generic_error = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")

    if not user or not user.hashed_password:
        raise generic_error

    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Account temporarily locked due to repeated failed attempts. "
            f"Try again after {user.locked_until.strftime('%H:%M UTC')}.",
        )

    if not verify_password(password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
            user.failed_login_attempts = 0
        db.commit()
        raise generic_error

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated.")

    # Success — reset lockout counters
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    return user


def issue_refresh_token(
    db: Session, user: User, family_id: uuid.UUID | None = None,
    user_agent: str | None = None, ip_address: str | None = None,
) -> tuple[str, RefreshToken]:
    raw_token, selector, verifier = generate_refresh_token()
    record = RefreshToken(
        user_id=user.id,
        selector=selector,
        verifier_hash=hash_token(verifier),
        family_id=family_id or uuid.uuid4(),
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return raw_token, record


def _lookup_refresh_token(db: Session, raw_token: str) -> RefreshToken | None:
    try:
        selector, verifier = raw_token.split(".", 1)
    except ValueError:
        return None
    record = db.query(RefreshToken).filter(RefreshToken.selector == selector).first()
    if not record or record.expires_at <= datetime.utcnow():
        return None
    if not verify_token_hash(verifier, record.verifier_hash):
        return None
    return record


def rotate_refresh_token(db: Session, raw_token: str, user_agent: str | None, ip_address: str | None):
    """
    Validate + rotate. Raises 401 if the token is invalid/expired.
    If the token was already revoked (reuse of an old token in a rotation
    chain — a strong signal of theft), revokes the whole family and forces
    the legitimate user to log in again everywhere.
    """
    matched = _lookup_refresh_token(db, raw_token)

    if not matched:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session. Please log in again.")

    if matched.revoked:
        # Reuse detected — nuke the whole family
        db.query(RefreshToken).filter(RefreshToken.family_id == matched.family_id).update({"revoked": True})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalidated. Please log in again.")

    matched.revoked = True
    db.commit()

    user = db.query(User).filter(User.id == matched.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account unavailable.")

    return issue_refresh_token(db, user, family_id=matched.family_id, user_agent=user_agent, ip_address=ip_address)


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    matched = _lookup_refresh_token(db, raw_token)
    if matched:
        matched.revoked = True
        db.commit()
