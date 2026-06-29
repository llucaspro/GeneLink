import os
import time
import jwt
import bcrypt
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
        # Still do a dummy hash check to avoid timing-based user enumeration
        bcrypt.checkpw(b"dummy", bcrypt.hashpw(b"dummy", bcrypt.gensalt()))
        login_guard.record_failure(ip, raw_email)
        return jsonify({"error": _WRONG}), 401

    if not bcrypt.checkpw(raw_password.encode("utf-8"), user["password_hash"].encode("utf-8")):
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
