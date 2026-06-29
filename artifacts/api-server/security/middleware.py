"""
GeneLink Security Middleware
============================
Defense-in-depth: headers, brute-force, SSRF, input validation.
"""

import os
import re
import time
import ipaddress
import threading
from collections import defaultdict
from urllib.parse import urlparse

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_REQUEST_BYTES = 1 * 1024 * 1024          # 1 MB hard limit
_MAX_STRING_DEFAULT = 2000

_IS_PROD = bool(os.environ.get("RENDER") or os.environ.get("PRODUCTION"))

# Allowed origins for CORS — add your Cloudflare/custom domain here
_ALLOWED_ORIGINS = {o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS",
    "https://genelink-fcz4.onrender.com,http://localhost:3000,http://localhost:10000"
).split(",") if o.strip()}

# External hosts whitelisted for server-side requests (SSRF protection)
_SAFE_EXTERNAL_HOSTS = {
    "publica.cnpj.ws",
    "eutils.ncbi.nlm.nih.gov",
    "www.ncbi.nlm.nih.gov",
}

# Private / link-local ranges that must never be reached via SSRF
_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

# ── Security Headers ──────────────────────────────────────────────────────────

_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://www.gstatic.com https://apis.google.com "
    "https://www.googleapis.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://firebaseinstallations.googleapis.com "
    "https://identitytoolkit.googleapis.com https://securetoken.googleapis.com "
    "https://www.googleapis.com https://eutils.ncbi.nlm.nih.gov; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)


def apply_security_headers(response):
    """Attach all OWASP-recommended security headers to every response."""
    h = response.headers

    # Transport Security
    if _IS_PROD:
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    # Content / framing
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["X-XSS-Protection"] = "0"                # modern browsers: rely on CSP instead
    h["Content-Security-Policy"] = _CSP

    # Referrer / permissions
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=(), usb=(), "
        "interest-cohort=()"
    )

    # Cache: never cache API responses
    if response.content_type and "json" in response.content_type:
        h["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        h["Pragma"] = "no-cache"
        h["Expires"] = "0"

    # Remove server fingerprinting
    h.pop("Server", None)
    h.pop("X-Powered-By", None)

    return response


def build_cors_headers(request_origin: str, response):
    """Apply CORS headers based on the allowlist (replaces flask-cors wildcard)."""
    if request_origin in _ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


# ── Brute-Force Protection ────────────────────────────────────────────────────

class BruteForceProtection:
    """
    In-memory sliding-window brute-force tracker.
    Thread-safe. Tracks by IP and by identifier (email).
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,     # 5 minutes
        lockout_seconds: int = 900,    # 15 minutes
    ):
        self._max = max_attempts
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def _key(self, ip: str, identifier: str) -> list[str]:
        return [f"ip:{ip}", f"id:{identifier}"]

    def is_blocked(self, ip: str, identifier: str) -> tuple[bool, int]:
        """Returns (blocked, seconds_remaining)."""
        now = time.monotonic()
        with self._lock:
            for key in self._key(ip, identifier):
                until = self._locked_until.get(key, 0)
                if now < until:
                    return True, int(until - now)
        return False, 0

    def record_failure(self, ip: str, identifier: str) -> bool:
        """Record a failed attempt. Returns True if now locked out."""
        now = time.monotonic()
        locked = False
        with self._lock:
            for key in self._key(ip, identifier):
                attempts = self._attempts[key]
                # Prune old entries outside the window
                self._attempts[key] = [t for t in attempts if now - t < self._window]
                self._attempts[key].append(now)
                if len(self._attempts[key]) >= self._max:
                    self._locked_until[key] = now + self._lockout
                    self._attempts[key] = []
                    locked = True
        return locked

    def record_success(self, ip: str, identifier: str):
        """Clear attempt history on successful auth."""
        with self._lock:
            for key in self._key(ip, identifier):
                self._attempts.pop(key, None)
                self._locked_until.pop(key, None)

    def cleanup(self):
        """Remove stale entries (call periodically if needed)."""
        now = time.monotonic()
        with self._lock:
            self._locked_until = {k: v for k, v in self._locked_until.items() if v > now}
            self._attempts = defaultdict(list, {
                k: [t for t in v if now - t < self._window]
                for k, v in self._attempts.items()
                if any(now - t < self._window for t in v)
            })


# Singleton used by auth routes
login_guard = BruteForceProtection(max_attempts=5, window_seconds=300, lockout_seconds=900)
register_guard = BruteForceProtection(max_attempts=10, window_seconds=3600, lockout_seconds=3600)

# ── Input Validation / Sanitisation ──────────────────────────────────────────

_DANGEROUS_PATTERNS = re.compile(
    r"(<script|javascript:|vbscript:|on\w+\s*=|data:text/html)",
    re.IGNORECASE,
)

_NULL_BYTES = re.compile(r"\x00")


def sanitize_string(value: str, max_len: int = _MAX_STRING_DEFAULT) -> str:
    """
    Strip null bytes, truncate, and reject obvious XSS payloads.
    Returns cleaned string or raises ValueError.
    """
    if not isinstance(value, str):
        raise ValueError("Expected string input")
    value = _NULL_BYTES.sub("", value)
    if len(value) > max_len:
        value = value[:max_len]
    if _DANGEROUS_PATTERNS.search(value):
        raise ValueError("Input contains disallowed content")
    return value


def validate_email(email: str) -> str:
    """Basic RFC-5322-ish email validation."""
    email = email.strip().lower()
    if not re.match(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$", email):
        raise ValueError("Invalid email address")
    return email


def validate_password(password: str, min_len: int = 8) -> None:
    if len(password) < min_len:
        raise ValueError(f"Password must be at least {min_len} characters")
    if len(password) > 128:
        raise ValueError("Password too long")


# ── SSRF Protection ───────────────────────────────────────────────────────────

def is_safe_external_url(url: str, extra_allowed: set | None = None) -> bool:
    """
    Returns True only when `url` targets an explicitly whitelisted hostname
    and does not resolve to a private/loopback address (best-effort).
    """
    allowed = _SAFE_EXTERNAL_HOSTS | (extra_allowed or set())
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        # Block private IPs directly embedded in the URL
        try:
            addr = ipaddress.ip_address(hostname)
            if any(addr in net for net in _PRIVATE_RANGES):
                return False
        except ValueError:
            pass  # hostname is a domain name — that's fine
        return hostname in allowed
    except Exception:
        return False


# ── Safe Error Responses ──────────────────────────────────────────────────────

_GENERIC_ERROR = "An internal error occurred. Please try again."


def safe_error(msg: str = _GENERIC_ERROR, status: int = 500, log_detail: str = ""):
    """
    Return a generic error response without exposing internal details.
    Optionally log the real detail server-side.
    """
    from flask import jsonify
    import logging
    if log_detail:
        logging.getLogger("genelink.security").error("safe_error [%d]: %s", status, log_detail)
    return jsonify({"error": msg}), status


# ── Rate-Limit Key Helpers ────────────────────────────────────────────────────

def get_remote_ip() -> str:
    """Return the real client IP, respecting Cloudflare / Render proxy headers."""
    from flask import request
    # Cloudflare sets CF-Connecting-IP
    cf_ip = request.headers.get("CF-Connecting-IP", "").strip()
    if cf_ip:
        return cf_ip
    # Render / generic reverse proxy
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")
    if forwarded and forwarded[0].strip():
        return forwarded[0].strip()
    return request.remote_addr or "unknown"
