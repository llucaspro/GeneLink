import os
import jwt
import bcrypt
import logging
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, make_response
from db.connection import get_connection
from routes.security import (
    limiter,
    get_lockout_seconds,
    record_failed_login,
    clear_failed_logins,
)

_log = logging.getLogger("genelink.inst_auth")

inst_auth_bp = Blueprint("inst_auth", __name__)

SECRET_KEY = os.environ.get("SESSION_SECRET", "genelink-dev-secret")
_IS_PRODUCTION = bool(os.environ.get("RENDER") or os.environ.get("PRODUCTION"))
INST_COOKIE = "gl_inst_session"
COOKIE_MAX_AGE = 24 * 60 * 60  # 24 horas


def generate_inst_token(inst_id):
    payload = {
        "inst_id": inst_id,
        "account_type": "institution",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def inst_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(INST_COOKIE, "")
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        if not token:
            return jsonify({"error": "Institution login required"}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            if data.get("account_type") != "institution":
                return jsonify({"error": "Not an institution token"}), 403
            request.inst_id = data["inst_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Institution Register ──────────────────────────────────────────────────────

@inst_auth_bp.route("/institutions/register", methods=["POST"])
@limiter.limit("5 per minute;10 per hour")
def inst_register():
    data = request.get_json(silent=True) or {}

    name         = (data.get("name")         or "").strip()
    short_name   = (data.get("short_name")   or "").strip()
    cnpj         = (data.get("cnpj")         or "").strip() or None
    email        = (data.get("email")        or "").strip().lower()
    email_domain = (data.get("email_domain") or "").strip().lower() or None
    password     = (data.get("password")     or "").strip()
    inst_type    = (data.get("type")         or "").strip()
    description  = (data.get("description")  or "").strip()
    website      = (data.get("website")      or "").strip() or None
    city         = (data.get("city")         or "").strip()
    state        = (data.get("state")        or "").strip()

    if not name:
        return jsonify({"error": "Nome da instituição é obrigatório"}), 400
    if not email or "@" not in email:
        return jsonify({"error": "E-mail institucional é obrigatório"}), 400
    if not password or len(password) < 8:
        return jsonify({"error": "Senha deve ter pelo menos 8 caracteres"}), 400
    if not city or not state:
        return jsonify({"error": "Cidade e estado são obrigatórios"}), 400

    logo_initials = (
        "".join(w[0].upper() for w in (short_name or name).split()[:2])
        or name[:2].upper()
    )
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    try:
        conn = get_connection()
        cur = conn.cursor()

        # Duplicate checks
        if cnpj:
            cur.execute("SELECT id FROM institutions WHERE cnpj = %s", (cnpj,))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({"error": "CNPJ já cadastrado"}), 409

        cur.execute(
            "SELECT id FROM institutions WHERE LOWER(email) = %s", (email,)
        )
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({"error": "E-mail já cadastrado"}), 409

        cur.execute(
            """INSERT INTO institutions
               (name, short_name, cnpj, email, email_domain, password_hash,
                description, website, city, state, type, logo_initials,
                is_verified, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, NOW())
               RETURNING id, name, short_name, email""",
            (name, short_name or None, cnpj, email, email_domain,
             password_hash, description or None, website,
             city, state, inst_type or None, logo_initials),
        )
        inst = dict(cur.fetchone())
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        _log.exception("inst_register DB error")
        return jsonify({"error": "Erro ao cadastrar instituição. Tente novamente."}), 500

    # Send "aguardando aprovação" e-mail in background
    try:
        from routes.email_utils import send_institution_pending_email
        base_url = os.environ.get("BASE_URL", "https://genelink-fcz4.onrender.com")
        threading.Thread(
            target=send_institution_pending_email,
            args=(name, cnpj or "N/A", email, base_url),
            daemon=True,
        ).start()
        _log.info("Pending-approval email queued for institution '%s' -> %s", name, email)
    except Exception:
        _log.warning("Could not queue pending-approval email for '%s'", name)

    return jsonify({"ok": True, "institution": inst}), 201


# ── Institution Login ─────────────────────────────────────────────────────────

@inst_auth_bp.route("/institutions/login", methods=["POST"])
@limiter.limit("5 per minute;15 per hour")
def inst_login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return jsonify({"error": "E-mail e senha sao obrigatorios"}), 400

    lockout_key = f"inst:{email}"
    lockout = get_lockout_seconds(lockout_key)
    if lockout > 0:
        mins = (lockout + 59) // 60
        return jsonify({"error": f"Conta temporariamente bloqueada. Tente novamente em {mins} minuto(s)."}), 429

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, short_name, email_domain, logo_initials, city, state, type, is_verified, cnpj, website, password_hash FROM institutions WHERE LOWER(email) = %s OR LOWER(email_domain) = %s",
            (email, email.split("@")[-1] if "@" in email else email),
        )
        inst = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        return jsonify({"error": "Servico indisponivel. Tente novamente."}), 500

    if not inst or not inst["password_hash"]:
        record_failed_login(lockout_key)
        return jsonify({"error": "E-mail ou senha incorretos"}), 401

    if not bcrypt.checkpw(password.encode("utf-8"), inst["password_hash"].encode("utf-8")):
        record_failed_login(lockout_key)
        return jsonify({"error": "E-mail ou senha incorretos"}), 401

    if not inst["is_verified"]:
        return jsonify({"error": "Instituicao aguardando aprovacao. Voce recebera um e-mail quando for aprovada."}), 403

    clear_failed_logins(lockout_key)

    token = generate_inst_token(inst["id"])
    inst_dict = {
        "id": inst["id"],
        "name": inst["name"],
        "short_name": inst["short_name"],
        "email_domain": inst["email_domain"],
        "logo_initials": inst["logo_initials"],
        "city": inst["city"],
        "state": inst["state"],
        "type": inst["type"],
        "is_verified": True,
        "cnpj": inst["cnpj"],
        "website": inst["website"],
    }
    resp = make_response(jsonify({"token": token, "institution": inst_dict}))
    resp.set_cookie(
        INST_COOKIE, token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=_IS_PRODUCTION,
        samesite="Strict" if _IS_PRODUCTION else "Lax",
    )
    return resp


# ── Institution Me ────────────────────────────────────────────────────────────

@inst_auth_bp.route("/institutions/me", methods=["GET"])
@inst_token_required
def inst_me():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT i.id, i.name, i.short_name, i.cnpj, i.email_domain, i.logo_initials,
                      i.city, i.state, i.type, i.is_verified, i.website, i.description,
                      (SELECT COUNT(*) FROM institution_members m WHERE m.institution_id = i.id) AS member_count,
                      (SELECT COUNT(*) FROM partnerships p WHERE p.institution_id = i.id AND p.is_active = TRUE) AS active_partnerships
               FROM institutions i WHERE i.id = %s""",
            (request.inst_id,),
        )
        inst = cur.fetchone()
        cur.close()
        conn.close()
        if not inst:
            return jsonify({"error": "Instituicao nao encontrada"}), 404
        d = dict(inst)
        if isinstance(d.get("is_verified"), int):
            d["is_verified"] = bool(d["is_verified"])
        return jsonify(d)
    except Exception:
        return jsonify({"error": "Erro ao carregar dados da instituicao"}), 500


# ── Institution Logout ────────────────────────────────────────────────────────

@inst_auth_bp.route("/institutions/logout", methods=["POST"])
def inst_logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(INST_COOKIE)
    return resp
