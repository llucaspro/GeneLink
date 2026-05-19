import os
import jwt
import bcrypt
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, redirect, url_for, make_response
from db.connection import get_connection, DB_TYPE

auth_bp = Blueprint("auth", __name__)
SECRET_KEY = os.environ.get("SESSION_SECRET", "genelink-dev-secret")

SESSION_COOKIE = "gl_session"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds


def generate_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


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
            return jsonify({"error": "Token expired, please log in again"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


def page_login_required(f):
    """Server-side guard for HTML page routes.
    Reads the HttpOnly session cookie; redirects to /login?clear=1 if missing or invalid
    so the client can purge any stale localStorage token and avoid redirect loops."""
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


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    institution = (data.get("institution") or "").strip()
    research_area = (data.get("research_area") or "").strip()

    if not email or not username or not password:
        return jsonify({"error": "Email, username and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400

    initials = "".join(p[0].upper() for p in (full_name or username).split()[:2]) or username[:2].upper()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO users (email, username, password_hash, full_name, institution, research_area, avatar_initials)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, username, email, full_name, institution, research_area, avatar_initials, bio, created_at""",
            (email, username, password_hash, full_name, institution, research_area, initials),
        )
        user = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        token = generate_token(user["id"])
        user_dict = dict(user)
        user_dict["created_at"] = str(user_dict.get("created_at") or "")

        # Send welcome email in background (non-blocking)
        try:
            from routes.email_utils import send_researcher_welcome_email
            base_url = os.environ.get("BASE_URL", "https://genelink.app")
            dashboard_url = f"{base_url}/gl/dashboard"
            threading.Thread(
                target=send_researcher_welcome_email,
                args=(user_dict["username"], user_dict.get("full_name", ""), email, dashboard_url),
                daemon=True,
            ).start()
        except Exception as mail_err:
            print(f"[GeneLink] Welcome email error: {mail_err}")

        resp = make_response(jsonify({"token": token, "user": user_dict}), 201)
        resp.set_cookie(SESSION_COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="Lax")
        return resp
    except Exception as e:
        err = str(e)
        if "unique" in err.lower() and "email" in err.lower():
            return jsonify({"error": "Email already registered"}), 409
        if "unique" in err.lower() and "username" in err.lower():
            return jsonify({"error": "Username already taken"}), 409
        return jsonify({"error": "Registration failed. Please try again."}), 500


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        return jsonify({"error": "Authentication service unavailable"}), 500

    if not user:
        return jsonify({"error": "Invalid email or password"}), 401
    if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        return jsonify({"error": "Invalid email or password"}), 401

    token = generate_token(user["id"])
    is_verified = user.get("is_verified", False)
    is_admin = user.get("is_admin", False)
    if isinstance(is_verified, int): is_verified = bool(is_verified)
    if isinstance(is_admin, int): is_admin = bool(is_admin)
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
            "created_at": str(user["created_at"] or ""),
        },
    }))
    resp.set_cookie(SESSION_COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="Lax")
    return resp


@auth_bp.route("/logout", methods=["POST"])
def logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@auth_bp.route("/user", methods=["GET"])
@token_required
def get_user():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, email, full_name, institution, research_area, bio, avatar_initials, is_verified, is_admin, institution_id, created_at FROM users WHERE id = %s",
            (request.user_id,),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, username, email, full_name, institution, research_area, bio, avatar_initials, created_at FROM users WHERE id = %s",
                (request.user_id,),
            )
            user = cur.fetchone()
            cur.close(); conn.close()
        except Exception:
            return jsonify({"error": "Failed to fetch user"}), 500

    if not user:
        return jsonify({"error": "User not found"}), 404
    user_dict = dict(user)
    user_dict["created_at"] = str(user_dict.get("created_at") or "")
    for k in ("is_verified", "is_admin"):
        if k in user_dict and isinstance(user_dict[k], int):
            user_dict[k] = bool(user_dict[k])
    return jsonify(user_dict)


@auth_bp.route("/user/profile", methods=["PUT"])
@token_required
def update_profile():
    data = request.get_json()
    full_name = (data.get("full_name") or "").strip()
    institution = (data.get("institution") or "").strip()
    research_area = (data.get("research_area") or "").strip()
    bio = (data.get("bio") or "").strip()

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


@auth_bp.route("/users/search", methods=["GET"])
@token_required
def search_users():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"error": "Query must be at least 2 characters"}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, username, full_name, institution, research_area,
                      avatar_initials, is_verified, created_at
               FROM users
               WHERE username ILIKE %s OR full_name ILIKE %s OR institution ILIKE %s
               ORDER BY
                 CASE WHEN username ILIKE %s THEN 0 ELSE 1 END,
                 username
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@auth_bp.route("/users/<username>/profile", methods=["GET"])
@token_required
def get_user_public_profile(username):
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


@auth_bp.route("/check-availability", methods=["GET"])
def check_availability():
    """Verifica se username ou email já está em uso (sem autenticação)."""
    username = (request.args.get("username") or "").strip()
    email = (request.args.get("email") or "").strip().lower()

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
    except Exception as e:
        return jsonify({"error": str(e)}), 500
