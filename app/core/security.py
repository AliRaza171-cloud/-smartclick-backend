"""
Security primitives. Every password-handling and token-handling function
the rest of the app uses lives here, so there's exactly one place to audit.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal

from jose import jwt, JWTError
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.core.config import settings

# --- Password hashing ---
# bcrypt: adaptive cost, industry standard, resistant to GPU cracking far better
# than a fast hash like SHA-256 would be. Never store or log raw passwords.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def is_password_strong(password: str) -> tuple[bool, Optional[str]]:
    """Server-side password policy — never trust client-side validation alone."""
    if len(password) < 10:
        return False, "Password must be at least 10 characters."
    if not any(c.isupper() for c in password):
        return False, "Password must include an uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must include a lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must include a number."
    return True, None


# --- JWT access tokens ---
# Short-lived (15 min default) and stateless: the frontend keeps this in memory
# (a JS variable), NEVER in localStorage/sessionStorage, so it isn't readable
# by an injected script that persists across reloads.
def create_access_token(subject: str, extra_claims: Optional[dict] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


# --- Refresh tokens ---
# Opaque random strings, NOT JWTs — we store a hash of each one server-side
# (see RefreshToken model) so a single token can be revoked individually,
# and rotate on every use so a stolen-but-unused-yet token becomes worthless
# the moment the legitimate user refreshes again (reuse = we revoke the whole family).
def generate_refresh_token() -> tuple[str, str, str]:
    """
    Returns (raw_token_for_cookie, selector, verifier).
    Selector: random, stored PLAINTEXT and indexed — lets the DB look up the
    right row in O(1) instead of hash-comparing against every stored token.
    Verifier: random, only its HASH is stored — this is the actual secret;
    a DB leak exposes selectors (harmless on their own) but not usable tokens.
    """
    selector = secrets.token_urlsafe(12)
    verifier = secrets.token_urlsafe(36)
    raw_token = f"{selector}.{verifier}"
    return raw_token, selector, verifier


def hash_token(token: str) -> str:
    # Refresh tokens are hashed before storage, same principle as passwords —
    # a DB leak shouldn't hand out usable session tokens.
    return pwd_context.hash(token)


def verify_token_hash(token: str, token_hash: str) -> bool:
    return pwd_context.verify(token, token_hash)


# --- Signed, expiring tokens for email verification / password reset ---
def _serializer(purpose: Literal["email-verify", "password-reset"]) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.EMAIL_TOKEN_SECRET, salt=purpose)


def create_email_verification_token(email: str) -> str:
    return _serializer("email-verify").dumps(email)


def verify_email_verification_token(token: str) -> Optional[str]:
    try:
        return _serializer("email-verify").loads(
            token, max_age=settings.EMAIL_TOKEN_EXPIRE_HOURS * 3600
        )
    except (BadSignature, SignatureExpired):
        return None


def create_password_reset_token(email: str) -> str:
    return _serializer("password-reset").dumps(email)


def verify_password_reset_token(token: str) -> Optional[str]:
    try:
        return _serializer("password-reset").loads(
            token, max_age=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES * 60
        )
    except (BadSignature, SignatureExpired):
        return None


# --- CSRF (double-submit cookie pattern) ---
# The refresh-token cookie is httpOnly (JS can't read it), so we pair it with
# a second, readable CSRF cookie. The frontend echoes that value back in a
# custom header on state-changing requests; a cross-site form/script can set
# cookies on the victim's browser but can't READ this one to put it in the
# header, so the request gets rejected.
def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
