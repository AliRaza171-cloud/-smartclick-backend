from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.core.config import settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PATHS = {"/auth/register", "/auth/login", "/auth/google/login", "/auth/google/callback"}
# register/login are exempt because the user doesn't have a CSRF cookie yet
# at that point — they're protected by rate limiting + credentials instead.


DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

        # FastAPI's own /docs (Swagger UI) and /redoc pages load their JS/CSS
        # from a CDN — the strict CSP below would silently block them,
        # rendering a blank page with no console error. Real API responses
        # (JSON) don't execute scripts at all, so they don't need this CSP
        # protecting them the way an HTML page does; skip it only for the
        # docs routes rather than loosening it site-wide.
        if not request.url.path.startswith(DOCS_PATHS):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; frame-ancestors 'none'; base-uri 'self'"
            )
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Double-submit cookie check for any state-changing request that relies on
    the refresh-token cookie. Requests that use the Bearer access token
    (most authenticated API calls) don't need this — a cookie isn't being
    trusted there, so there's nothing for CSRF to forge. This matters
    specifically for /auth/refresh and /auth/logout, which read the
    httpOnly cookie directly.
    """
    async def dispatch(self, request: Request, call_next):
        if request.method not in SAFE_METHODS and request.url.path not in CSRF_EXEMPT_PATHS:
            if request.url.path.startswith("/auth/refresh") or request.url.path.startswith("/auth/logout"):
                refresh_cookie = request.cookies.get("smartclick_refresh")
                # No refresh cookie at all means there's no session to protect —
                # let it through so the route can return its normal "no
                # session found" response, instead of a misleading 403 that
                # looks like a blocked attack on every first-ever page load.
                if refresh_cookie:
                    cookie_token = request.cookies.get("smartclick_csrf")
                    header_token = request.headers.get("x-csrf-token")
                    if not cookie_token or not header_token or cookie_token != header_token:
                        return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid."})
        return await call_next(request)