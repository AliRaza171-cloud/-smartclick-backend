"""
Central configuration. Everything secret comes from environment variables —
never hardcoded, never committed. See .env.example for the full list.
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # --- App ---
    ENV: str = "development"  # "production" in prod — flips secure cookie flags on
    APP_NAME: str = "Smart Click"

    # --- Database ---
    DATABASE_URL: str

    # --- JWT ---
    JWT_SECRET_KEY: str          # generate with: openssl rand -hex 32
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- CORS: explicit allow-list, never "*" ---
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REGISTER: str = "3/minute"
    RATE_LIMIT_PASSWORD_RESET: str = "3/minute"

    # --- Account lockout ---
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15

    # --- Email verification / password reset tokens ---
    EMAIL_TOKEN_SECRET: str      # separate secret from JWT_SECRET_KEY
    EMAIL_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # --- Cookies ---
    COOKIE_DOMAIN: str = "localhost"

    # --- Stripe (real card payment processing) ---
    # Test-mode keys from dashboard.stripe.com/test/apikeys — get you a
    # fully working sandbox with zero business verification. Live keys need
    # your Stripe account activated for real charges.
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""  # from the Stripe CLI or your webhook endpoint's settings
    # Charge currency — PKR support on Stripe depends on your account's
    # region/activation. If PKR charges fail on your real account, switch
    # this to "usd" and convert order.total accordingly.
    STRIPE_CURRENCY: str = "pkr"

    # --- Safepay (Pakistani cards + JazzCash + EasyPaisa, one hosted checkout) ---
    # Free sandbox credentials from your Safepay dashboard (getsafepay.com) —
    # no business KYC needed until you switch to production/live payments.
    SAFEPAY_ENVIRONMENT: str = "sandbox"  # "sandbox" or "production"
    SAFEPAY_API_KEY: str = ""
    SAFEPAY_V1_SECRET: str = ""
    SAFEPAY_WEBHOOK_SECRET: str = ""
    SAFEPAY_CURRENCY: str = "PKR"

    # --- Frontend URL, for links inside emails ---
    FRONTEND_URL: str = "http://localhost:3000"
    # --- Safepay (Pakistani cards + JazzCash + EasyPaisa, one hosted checkout) ---
    # Free sandbox credentials from your Safepay dashboard (getsafepay.com) —
    # no business KYC needed until you switch to production/live payments.
    SAFEPAY_ENVIRONMENT: str = "sandbox"  # "sandbox" or "production"
    SAFEPAY_API_KEY: str = ""
    SAFEPAY_V1_SECRET: str = ""
    SAFEPAY_WEBHOOK_SECRET: str = ""
    SAFEPAY_CURRENCY: str = "PKR"

    # --- Store / sender info (for shipping labels) ---
    STORE_NAME: str = "Smart Click"
    STORE_ADDRESS: str = "Set STORE_ADDRESS in .env"
    STORE_CITY: str = "Set STORE_CITY in .env"
    STORE_PHONE: str = "Set STORE_PHONE in .env"

    # --- Email (order confirmations, admin notifications, verify/reset) ---
    # Leave SMTP_HOST blank for local dev — email_service falls back to
    # printing instead of sending, so you don't need real credentials to
    # test the rest of the app. For real sending: Gmail (smtp.gmail.com,
    # port 587, an App Password — not your normal password), or any
    # provider's SMTP details (Mailtrap for dev testing, SendGrid, etc).
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = "noreply@smartclick.local"
    RESEND_API_KEY: str = ""
    ADMIN_NOTIFICATION_EMAIL: str = ""  # where "new order" emails go

    # --- AI Agent service (separate FastAPI service, Phase 4) ---
    AI_SERVICE_URL: str = "http://localhost:8001"
    INTERNAL_AI_SERVICE_KEY: str = ""  # must match the AI service's INTERNAL_API_KEY exactly
    AI_SERVICE_TIMEOUT_SECONDS: float = 35.0

    # --- Local file storage (Phase 5, dev only) ---
    UPLOAD_DIR: str = "uploads"
    MAX_PRODUCT_IMAGES: int = 6

    # --- Cloudinary (persistent image/video storage for deployment) ---
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    @property
    def use_cloudinary(self) -> bool:
        return bool(self.CLOUDINARY_CLOUD_NAME)

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    class Config:
        env_file = ".env"


settings = Settings()