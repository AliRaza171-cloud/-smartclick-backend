import os
import mimetypes

# Windows' registry-based mimetype lookup sometimes doesn't know .webp
# should be served as image/webp — without this, StaticFiles below sends
# the wrong Content-Type, so the browser renders it as raw text/garbage
# instead of an image, even though the file itself is perfectly fine.
mimetypes.add_type("image/webp", ".webp")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.middleware.security import SecurityHeadersMiddleware, CSRFMiddleware
from app.api.routes import auth, products, vouchers, orders, categories, store, notifications, payments, wishlist, analytics, hero_images, reviews, questions, campaigns, newsletter, listing_api

app = FastAPI(title=settings.APP_NAME)

# --- Rate limiting ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS: explicit allow-list from env, credentials allowed for cookies ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(vouchers.router)
app.include_router(orders.router)
app.include_router(categories.router)
app.include_router(store.router)
app.include_router(notifications.router)
app.include_router(payments.router)
app.include_router(wishlist.router)
app.include_router(analytics.router)
app.include_router(hero_images.router)
app.include_router(reviews.router)
app.include_router(questions.router)
app.include_router(campaigns.router)
app.include_router(newsletter.router)
app.include_router(listing_api.router)
app.include_router(listing_api.connect_router)

# Local dev image storage — see UPLOAD_DIR in core/config.py for why this
# gets swapped for real object storage before deploying anywhere.
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}