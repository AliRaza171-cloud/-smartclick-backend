import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    verify_email_verification_token,
    create_password_reset_token,
    verify_password_reset_token,
    hash_password,
    is_password_strong,
    generate_csrf_token,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    RegisterRequest, LoginRequest, AccessTokenResponse, UserOut,
    ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest,
)
from app.services import auth_service
from app.services.email_service import send_verification_email, send_password_reset_email
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

REFRESH_COOKIE_NAME = "smartclick_refresh"
CSRF_COOKIE_NAME = "smartclick_csrf"


def _set_auth_cookies(response: Response, refresh_token: str):
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        domain=settings.COOKIE_DOMAIN,
        path="/auth",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=generate_csrf_token(),
        httponly=False,
        secure=settings.is_production,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def _clear_auth_cookies(response: Response):
    response.delete_cookie(REFRESH_COOKIE_NAME, domain=settings.COOKIE_DOMAIN, path="/auth")
    response.delete_cookie(CSRF_COOKIE_NAME, domain=settings.COOKIE_DOMAIN, path="/")


def _is_mobile(request: Request) -> bool:
    return request.headers.get("x-client-type") == "mobile"


def _access_response(user: User, refresh_token: str | None = None) -> AccessTokenResponse:
    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})
    return AccessTokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
        refresh_token=refresh_token,
    )


@router.post("/register", response_model=AccessTokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def register(request: Request, response: Response, data: RegisterRequest, db: Session = Depends(get_db)):
    user = auth_service.register_user(db, data)

    verify_token = create_email_verification_token(user.email)
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={verify_token}"
    try:
        send_verification_email(user.email, verify_url)
    except Exception as e:
        print(f"[auth] Verification email failed for {user.email}: {e}")

    raw_refresh, _ = auth_service.issue_refresh_token(
        db, user, user_agent=request.headers.get("user-agent"), ip_address=get_remote_address(request)
    )
    if _is_mobile(request):
        return _access_response(user, refresh_token=raw_refresh)
    _set_auth_cookies(response, raw_refresh)
    return _access_response(user)


@router.post("/login", response_model=AccessTokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(request: Request, response: Response, data: LoginRequest, db: Session = Depends(get_db)):
    user = auth_service.authenticate_user(db, data.email, data.password)
    raw_refresh, _ = auth_service.issue_refresh_token(
        db, user, user_agent=request.headers.get("user-agent"), ip_address=get_remote_address(request)
    )
    if _is_mobile(request):
        return _access_response(user, refresh_token=raw_refresh)
    _set_auth_cookies(response, raw_refresh)
    return _access_response(user)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    is_mobile = _is_mobile(request)
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)

    if not raw_refresh and is_mobile:
        try:
            body = await request.json()
            raw_refresh = body.get("refresh_token")
        except Exception:
            raw_refresh = None

    if not raw_refresh:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No session found.")

    new_raw_refresh, record = auth_service.rotate_refresh_token(
        db, raw_refresh, user_agent=request.headers.get("user-agent"), ip_address=get_remote_address(request)
    )
    user = db.query(User).filter(User.id == record.user_id).first()

    if is_mobile:
        return _access_response(user, refresh_token=new_raw_refresh)
    _set_auth_cookies(response, new_raw_refresh)
    return _access_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh and _is_mobile(request):
        try:
            body = await request.json()
            raw_refresh = body.get("refresh_token")
        except Exception:
            raw_refresh = None
    if raw_refresh:
        auth_service.revoke_refresh_token(db, raw_refresh)
    _clear_auth_cookies(response)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    email = verify_email_verification_token(data.token)
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification link.")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    user.is_email_verified = True
    db.commit()


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def forgot_password(request: Request, data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if user:
        reset_token = create_password_reset_token(user.email)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        try:
            send_password_reset_email(user.email, reset_url)
        except Exception as e:
            print(f"[auth] Password reset email failed for {user.email}: {e}")


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = verify_password_reset_token(data.token)
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link.")

    ok, reason = is_password_strong(data.new_password)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, reason)

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

    user.hashed_password = hash_password(data.new_password)
    db.commit()


@router.get("/google/login")
def google_login():
    params = (
        f"client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
        f"&response_type=code&scope=openid%20email%20profile&access_type=offline"
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google/callback")
def google_callback(code: str, request: Request, response: Response, db: Session = Depends(get_db)):
    token_res = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    if token_res.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google authentication failed.")
    id_token_claims = httpx.get(
        "https://www.googleapis.com/oauth2/v3/tokeninfo",
        params={"id_token": token_res.json()["id_token"]},
    ).json()

    google_id = id_token_claims["sub"]
    email = id_token_claims["email"]

    user = db.query(User).filter(User.google_id == google_id).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.google_id = google_id
        else:
            user = User(email=email, google_id=google_id, full_name=id_token_claims.get("name"),
                        is_email_verified=True)
            db.add(user)
        db.commit()
        db.refresh(user)

    raw_refresh, _ = auth_service.issue_refresh_token(
        db, user, user_agent=request.headers.get("user-agent"), ip_address=get_remote_address(request)
    )
    _set_auth_cookies(response, raw_refresh)
    return RedirectResponse(f"{settings.FRONTEND_URL}/auth/callback")