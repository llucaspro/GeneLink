"""GeneLink – Módulo de Segurança Centralizado

Camadas implementadas:
  1. Rate limiting (Flask-Limiter)   – evita brute-force e DDoS
  2. Account lockout (in-memory)     – bloqueia após tentativas excessivas
  3. Security headers                – HSTS, CSP, X-Frame-Options, etc.
  4. Input sanitization              – previne XSS e injection
  5. Safe error messages             – sem vazamento de stack trace
"""

import re, html, time, os, traceback
from collections import defaultdict
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute", "2000 per hour"],
    storage_uri="memory://",
    strategy="fixed-window",
)

# ── Account Lockout (in-memory; resets se o servidor reiniciar) ───────────────
_failed_logins: dict = defaultdict(list)
_LOCKOUT_WINDOW    = 600   # rastreia tentativas nos últimos 10 min
_LOCKOUT_THRESHOLD = 5     # bloqueia após 5 falhas
_LOCKOUT_DURATION  = 900   # bloqueio de 15 min

def get_lockout_seconds(identifier: str) -> int:
    """Retorna segundos restantes no bloqueio, ou 0 se liberado."""
    now = time.time()
    attempts = _failed_logins[identifier]
    attempts[:] = [t for t in attempts if now - t < _LOCKOUT_WINDOW]
    if len(attempts) >= _LOCKOUT_THRESHOLD:
        wait = int(_LOCKOUT_DURATION - (now - min(attempts)))
        return max(wait, 0)
    return 0

def record_failed_login(identifier: str) -> None:
    _failed_logins[identifier].append(time.time())

def clear_failed_logins(identifier: str) -> None:
    _failed_logins[identifier].clear()

# ── Sanitização de Inputs ─────────────────────────────────────────────────────
def sanitize(value, max_length: int = 500) -> str:
    if not value:
        return ""
    return str(value).strip()[:max_length]

def sanitize_html(value, max_length: int = 5000) -> str:
    """Escapa HTML para prevenir XSS quando conteúdo é renderizado diretamente."""
    if not value:
        return ""
    return html.escape(str(value).strip()[:max_length], quote=True)

# ── Headers de Segurança ──────────────────────────────────────────────────────
def apply_security_headers(response):
    """Adiciona headers de segurança padrão da indústria em toda resposta HTTP."""
    h = response.headers

    # Impede MIME-sniffing
    h["X-Content-Type-Options"] = "nosniff"

    # Protege contra clickjacking
    h["X-Frame-Options"] = "DENY"

    # Filtro XSS para browsers legados
    h["X-XSS-Protection"] = "0"

    # Limita vazamento de referrer
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Desativa recursos desnecessários do browser
    h["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"

    # HSTS: força HTTPS por 2 anos (apenas quando já estiver em HTTPS)
    from flask import request as flask_request
    proto = flask_request.headers.get("X-Forwarded-Proto", "")
    if flask_request.is_secure or proto == "https":
        h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

    # Content Security Policy
    h["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://*.googleapis.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com; "
        "frame-ancestors 'none';"
    )

    # Remove fingerprint do servidor
    h.pop("Server", None)
    return response

# ── Mensagens de Erro Seguras ─────────────────────────────────────────────────
_IS_PRODUCTION = bool(os.environ.get("RENDER") or os.environ.get("PRODUCTION"))

def safe_error(exc: Exception, public_msg: str = "Erro interno. Tente novamente.") -> str:
    """Loga o erro real no servidor; retorna mensagem segura ao cliente."""
    print(f"[GeneLink][ERROR] {traceback.format_exc()}")
    if not _IS_PRODUCTION:
        return str(exc)
    return public_msg
