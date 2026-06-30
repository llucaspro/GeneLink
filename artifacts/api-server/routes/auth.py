import os
import time
import jwt
import bcrypt
import logging
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, redirect, make_response
from db.connection import get_connection, DB_TYPE
from security.middleware import (
    login_guard, register_guard,
    sanitize_string, validate_email, validate_password,
    get_remote_ip,
)

auth_bp = Blueprint("auth", __name__)
_log = logging.getLogger("genelink.auth")
SECRET_KEY = os.environ.get("SESSION_SECRET", "dev-only-insecure-secret-do-not-use-in-prod")

_IS_PROD = bool(os.environ.get("RENDER") or os.environ.get("PRODUCTION"))

ADMIN_EMAILS = {"lucaspr1305@gmail.com"}

SESSION_COOKIE = "gl_session"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60


def generate_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _set_session_cookie(resp, token: str):
    resp.set_cookie(
        SESSION_COOKIE, token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=_IS_PROD,
    )


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization token missing"}), 401
        token = auth_header[7:]
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user_id = data["user_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired, please log in again"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid session"}), 401
        return f(*args, **kwargs)
    return decorated


def page_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(SESSION_COOKIE, "")
        if not token:
            return redirect("/login?clear=1")
        try:
            jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            resp = make_response(redirect("/login?clear=1"))
            resp.delete_cookie(SESSION_COOKIE)
            return resp
        return f(*args, **kwargs)
    return decorated


# ── Register ──────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
def register():
    ip = get_remote_ip()
    blocked, wait = register_guard.is_blocked(ip, ip)
    if blocked:
        return jsonify({"error": f"Too many registrations. Try again in {wait}s."}), 429

    data = request.get_json(silent=True) or {}
    raw_email = (data.get("email") or "").strip().lower()
    raw_username = (data.get("username") or "").strip()
    raw_password = data.get("password") or ""
    raw_full_name = (data.get("full_name") or "").strip()
    raw_institution = (data.get("institution") or "").strip()
    raw_research_area = (data.get("research_area") or "").strip()

    # Validate inputs
    try:
        email = validate_email(raw_email)
        if len(raw_username) < 3 or len(raw_username) > 50:
            return jsonify({"error": "Username must be 3–50 characters"}), 400
        username = sanitize_string(raw_username, max_len=50)
        validate_password(raw_password, min_len=8)
        full_name = sanitize_string(raw_full_name, max_len=255) if raw_full_name else ""
        institution = sanitize_string(raw_institution, max_len=255) if raw_institution else ""
        research_area = sanitize_string(raw_research_area, max_len=255) if raw_research_area else ""
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    if not email or not username or not raw_password:
        return jsonify({"error": "Email, username and password are required"}), 400

    initials = "".join(p[0].upper() for p in (full_name or username).split()[:2]) or username[:2].upper()
    password_hash = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    is_admin = email in ADMIN_EMAILS

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO users
               (email, username, password_hash, full_name, institution,
                research_area, avatar_initials, is_admin)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, username, email, full_name, institution,
                         research_area, avatar_initials, bio, is_admin,
                         is_verified, created_at""",
            (email, username, password_hash, full_name, institution,
             research_area, initials, is_admin),
        )
        user = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        err = str(e).lower()
        if "unique" in err and "email" in err:
            return jsonify({"error": "Este e-mail já está cadastrado."}), 409
        if "unique" in err and "username" in err:
            return jsonify({"error": "Este nome de usuário já está em uso."}), 409
        return jsonify({"error": "Registration failed. Please try again."}), 500

    register_guard.record_failure(ip, ip)  # mild counter to slow mass registrations
    token = generate_token(user["id"])
    user_dict = dict(user)
    user_dict["created_at"] = str(user_dict.get("created_at") or "")

    try:
        from routes.email_utils import send_researcher_welcome_email
        base_url = os.environ.get("BASE_URL", "https://genelink.app")
        threading.Thread(
            target=send_researcher_welcome_email,
            args=(user_dict["username"], user_dict.get("full_name", ""), email,
                  f"{base_url}/gl/dashboard"),
            daemon=True,
        ).start()
    except Exception:
        pass

    resp = make_response(jsonify({"token": token, "user": user_dict}), 201)
    _set_session_cookie(resp, token)
    return resp


# ── Firebase REST API fallback ────────────────────────────────────────────────

def _try_firebase_login(email: str, password: str):
    """
    Verify credentials via Firebase REST API (no client-side Firebase needed).
    If Firebase confirms the credentials, find or create the user in DB and
    return a ready Flask response. Returns None if Firebase is not configured
    or credentials are wrong.
    """
    import urllib.request as _req
    import urllib.error as _err
    import json as _json

    api_key = os.environ.get("FIREBASE_API_KEY", "").strip()
    if not api_key:
        return None

    # Call Firebase signInWithPassword REST endpoint
    try:
        payload = _json.dumps({
            "email": email,
            "password": password,
            "returnSecureToken": True,
        }).encode("utf-8")
        http_req = _req.Request(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _req.urlopen(http_req, timeout=8) as r:
            fb_data = _json.loads(r.read())
    except _err.HTTPError as _fe:
        # Wrong credentials or Firebase error → treat as auth failure
        try:
            _body = _fe.read().decode("utf-8", errors="ignore")
        except Exception:
            _body = ""
        _log.warning("_try_firebase_login: Firebase REST error %s %s for %s", _fe.code, _body[:120], email)
        return None
    except Exception as _ex:
        _log.warning("_try_firebase_login: unexpected error for %s: %s", email, _ex)
        return None

    if not fb_data.get("idToken"):
        return None

    fb_email = (fb_data.get("email") or email).strip().lower()
    fb_name  = fb_data.get("displayName") or ""

    # Find or create the user in DB
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (fb_email,))
        user = cur.fetchone()

        if not user:
            # User exists in Firebase but never in DB — create them now
            username_base = fb_email.split("@")[0].replace(".", "").replace("+", "").lower()[:20]
            username = username_base
            suffix   = 1
            while True:
                cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                if not cur.fetchone():
                    break
                username = f"{username_base}{suffix}"
                suffix  += 1

            full_name = fb_name or username
            initials  = (
                "".join(p[0].upper() for p in full_name.split()[:2])
                or username[:2].upper()
            )
            pw_hash  = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            is_admin = fb_email in ADMIN_EMAILS

            cur.execute(
                """INSERT INTO users
                   (username, email, password_hash, full_name, avatar_initials, is_admin)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING id, username, email, full_name, avatar_initials, institution,
                             research_area, bio, is_verified, is_admin, created_at""",
                (username, fb_email, pw_hash, full_name, initials, is_admin),
            )
            user = cur.fetchone()
            conn.commit()
        else:
            # User exists but might have a Firebase dummy hash — update to real hash
            user = dict(user)
            if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
                pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (pw_hash, fb_email))
                conn.commit()

        cur.close()
        conn.close()
    except Exception:
        return None

    user_dict   = dict(user)
    token       = generate_token(user_dict["id"])
    is_verified = bool(user_dict.get("is_verified", False))
    is_admin    = bool(user_dict.get("is_admin", False)) or fb_email in ADMIN_EMAILS
    user_dict["created_at"] = str(user_dict.get("created_at") or "")

    resp = make_response(jsonify({
        "token": token,
        "user": {
            "id":            user_dict["id"],
            "username":      user_dict["username"],
            "email":         user_dict["email"],
            "full_name":     user_dict.get("full_name") or "",
            "institution":   user_dict.get("institution") or "",
            "research_area": user_dict.get("research_area") or "",
            "avatar_initials": user_dict.get("avatar_initials") or "",
            "bio":           user_dict.get("bio") or "",
            "is_verified":   is_verified,
            "is_admin":      is_admin,
            "created_at":    user_dict["created_at"],
        },
    }))
    _set_session_cookie(resp, token)
    return resp


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    ip = get_remote_ip()
    data = request.get_json(silent=True) or {}
    raw_email = (data.get("email") or "").strip().lower()
    raw_password = data.get("password") or ""

    if not raw_email or not raw_password:
        return jsonify({"error": "Email and password are required"}), 400

    # Brute-force gate
    blocked, wait = login_guard.is_blocked(ip, raw_email)
    if blocked:
        return jsonify({"error": f"Too many failed attempts. Try again in {wait}s."}), 429

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (raw_email,))
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        return jsonify({"error": "Authentication service unavailable"}), 500

    # Uniform "wrong credentials" — no user enumeration
    _WRONG = "Invalid email or password"
    if not user:
        _log.warning("LOGIN FAIL – email not in DB: %s", raw_email)
        # Timing-safe dummy check
        bcrypt.checkpw(b"dummy", bcrypt.hashpw(b"dummy", bcrypt.gensalt()))
        # Fallback: user might exist in Firebase but not in DB
        _log.info("LOGIN – trying Firebase fallback for missing user: %s", raw_email)
        fb_resp = _try_firebase_login(raw_email, raw_password)
        if fb_resp is not None:
            _log.info("LOGIN – Firebase fallback SUCCESS (user created): %s", raw_email)
            login_guard.record_success(ip, raw_email)
            return fb_resp
        _log.warning("LOGIN – Firebase fallback also failed for: %s", raw_email)
        login_guard.record_failure(ip, raw_email)
        return jsonify({"error": _WRONG}), 401

    _log.info("LOGIN – user found in DB: %s  |  hash prefix: %.7s", raw_email, user["password_hash"])
    hash_ok = bcrypt.checkpw(raw_password.encode("utf-8"), user["password_hash"].encode("utf-8"))
    _log.info("LOGIN – bcrypt check result: %s for %s", hash_ok, raw_email)

    if not hash_ok:
        _log.warning("LOGIN – bcrypt mismatch, trying Firebase fallback: %s", raw_email)
        # Fallback: user in DB but has a Firebase dummy hash — verify via Firebase
        fb_resp = _try_firebase_login(raw_email, raw_password)
        if fb_resp is not None:
            _log.info("LOGIN – Firebase fallback SUCCESS (hash updated): %s", raw_email)
            login_guard.record_success(ip, raw_email)
            return fb_resp
        _log.warning("LOGIN – Firebase fallback also failed for: %s", raw_email)
        login_guard.record_failure(ip, raw_email)
        return jsonify({"error": _WRONG}), 401

    login_guard.record_success(ip, raw_email)

    # Auto-promote admin on login (handles pre-existing accounts)
    if raw_email in ADMIN_EMAILS and not user.get("is_admin"):
        try:
            conn2 = get_connection()
            cur2 = conn2.cursor()
            cur2.execute("UPDATE users SET is_admin = TRUE WHERE email = %s", (raw_email,))
            conn2.commit()
            cur2.close()
            conn2.close()
            user["is_admin"] = True
        except Exception:
            pass

    token = generate_token(user["id"])
    is_verified = bool(user.get("is_verified", False)) if not isinstance(user.get("is_verified"), bool) else user["is_verified"]
    is_admin = bool(user.get("is_admin", False)) if not isinstance(user.get("is_admin"), bool) else user["is_admin"]

    resp = make_response(jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "full_name": user["full_name"],
            "institution": user["institution"],
            "research_area": user["research_area"],
            "avatar_initials": user["avatar_initials"],
            "bio": user["bio"],
            "is_verified": is_verified,
            "is_admin": is_admin,
            "created_at": str(user.get("created_at") or ""),
        },
    }))
    _set_session_cookie(resp, token)
    return resp


# ── Admin Recovery (TEMPORARY — remove after use) ─────────────────────────────

@auth_bp.route("/admin-recovery", methods=["POST"])
def admin_recovery():
    """
    TEMPORARY ENDPOINT — lets an admin reset their own password directly in the
    DB without knowing the old password.  Gated by ADMIN_EMAILS; remove this
    route once the admin has regained access.
    """
    data = request.get_json(silent=True) or {}
    email       = (data.get("email") or "").strip().lower()
    new_password = data.get("new_password") or ""

    if email not in ADMIN_EMAILS:
        return jsonify({"error": "Unauthorized"}), 403
    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    pw_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE email = %s RETURNING id, email",
            (pw_hash, email),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        _log.exception("admin-recovery DB error")
        return jsonify({"error": f"DB error: {exc}"}), 500

    if not row:
        return jsonify({"error": "User not found in database"}), 404

    _log.warning("ADMIN RECOVERY used for %s — password hash updated in DB", email)
    return jsonify({"ok": True, "message": f"Password updated for {email}. Log in now."})


# ── Forgot Password ───────────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """
    Backend fallback for sending a Firebase password reset email when the
    client-side Firebase SDK is unavailable. Uses the Firebase REST API.
    """
    import urllib.request as _req
    import urllib.error as _err
    import json as _json

    data = request.get_json(silent=True) or {}
    raw_email = (data.get("email") or "").strip().lower()
    if not raw_email:
        return jsonify({"error": "E-mail obrigatório"}), 400

    api_key = os.environ.get("FIREBASE_API_KEY", "").strip()
    if not api_key:
        return jsonify({"error": "Redefinição de senha não configurada. Contate o administrador."}), 503

    try:
        payload = _json.dumps({
            "requestType": "PASSWORD_RESET",
            "email": raw_email,
        }).encode("utf-8")
        http_req = _req.Request(
            f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={api_key}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _req.urlopen(http_req, timeout=8) as r:
            r.read()
    except _err.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        _log.warning("forgot-password Firebase error: %s %s", e.code, body)
        # Don't reveal whether the email is registered
    except Exception as e:
        _log.warning("forgot-password error: %s", e)

    # Always return success to prevent email enumeration
    return jsonify({"ok": True, "message": "Se o e-mail estiver cadastrado, você receberá um link de redefinição."})


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
def logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ── Current User ──────────────────────────────────────────────────────────────

@auth_bp.route("/user", methods=["GET"])
@token_required
def get_user():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, username, email, full_name, institution, research_area,
                      bio, avatar_initials, is_verified, is_admin, institution_id, created_at
               FROM users WHERE id = %s""",
            (request.user_id,),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        return jsonify({"error": "Failed to fetch user"}), 500

    if not user:
        return jsonify({"error": "User not found"}), 404
    d = dict(user)
    d["created_at"] = str(d.get("created_at") or "")
    for k in ("is_verified", "is_admin"):
        if k in d and isinstance(d[k], int):
            d[k] = bool(d[k])
    return jsonify(d)


# ── Update Profile ────────────────────────────────────────────────────────────

@auth_bp.route("/user/profile", methods=["PUT"])
@token_required
def update_profile():
    data = request.get_json(silent=True) or {}
    try:
        full_name = sanitize_string((data.get("full_name") or "").strip(), max_len=255)
        institution = sanitize_string((data.get("institution") or "").strip(), max_len=255)
        research_area = sanitize_string((data.get("research_area") or "").strip(), max_len=255)
        bio = sanitize_string((data.get("bio") or "").strip(), max_len=1000)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    initials = "".join(p[0].upper() for p in full_name.split()[:2]) if full_name else None
    try:
        conn = get_connection()
        cur = conn.cursor()
        if initials:
            cur.execute(
                "UPDATE users SET full_name=%s, institution=%s, research_area=%s, bio=%s, avatar_initials=%s WHERE id=%s",
                (full_name, institution, research_area, bio, initials, request.user_id),
            )
        else:
            cur.execute(
                "UPDATE users SET full_name=%s, institution=%s, research_area=%s, bio=%s WHERE id=%s",
                (full_name, institution, research_area, bio, request.user_id),
            )
        cur.execute(
            "SELECT id, username, email, full_name, institution, research_area, bio, avatar_initials FROM users WHERE id=%s",
            (request.user_id,),
        )
        user = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(dict(user))
    except Exception:
        return jsonify({"error": "Failed to update profile"}), 500


# ── User Search ───────────────────────────────────────────────────────────────

@auth_bp.route("/users/search", methods=["GET"])
@token_required
def search_users():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"error": "Query must be at least 2 characters"}), 400
    q = q[:100]
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, username, full_name, institution, research_area,
                      avatar_initials, is_verified, created_at
               FROM users
               WHERE username ILIKE %s OR full_name ILIKE %s OR institution ILIKE %s
               ORDER BY CASE WHEN username ILIKE %s THEN 0 ELSE 1 END, username
               LIMIT 30""",
            (f"%{q}%", f"%{q}%", f"%{q}%", f"{q}%"),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        users = []
        for r in rows:
            d = dict(r)
            d["created_at"] = str(d.get("created_at") or "")
            if isinstance(d.get("is_verified"), int):
                d["is_verified"] = bool(d["is_verified"])
            users.append(d)
        return jsonify({"users": users, "total": len(users)})
    except Exception:
        return jsonify({"error": "Search failed"}), 500


# ── Public Profile ────────────────────────────────────────────────────────────

@auth_bp.route("/users/<username>/profile", methods=["GET"])
@token_required
def get_user_public_profile(username):
    username = username[:50]
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, username, full_name, institution, research_area,
                      bio, avatar_initials, is_verified, created_at
               FROM users WHERE username = %s""",
            (username,),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        return jsonify({"error": "Failed to fetch profile"}), 500

    if not user:
        return jsonify({"error": "User not found"}), 404
    d = dict(user)
    d["created_at"] = str(d.get("created_at") or "")
    if isinstance(d.get("is_verified"), int):
        d["is_verified"] = bool(d["is_verified"])
    return jsonify(d)


# ── Availability Check (rate-limited, anti-enumeration) ──────────────────────

@auth_bp.route("/check-availability", methods=["GET"])
def check_availability():
    username = (request.args.get("username") or "").strip()[:50]
    email = (request.args.get("email") or "").strip().lower()[:255]

    if not username and not email:
        return jsonify({"error": "username or email required"}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        result = {}
        if username:
            cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
            result["username_taken"] = cur.fetchone() is not None
        if email:
            cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            result["email_taken"] = cur.fetchone() is not None
        cur.close()
        conn.close()
        return jsonify(result)
    except Exception:
        return jsonify({"error": "Service unavailable"}), 500
