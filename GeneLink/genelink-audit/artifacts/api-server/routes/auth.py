"""
Authentication routes — Firebase Auth + PostgreSQL.

Flow:
  1. Client authenticates with Firebase (email/password, Google, etc.)
  2. Client sends Firebase ID token in Authorization: Bearer <token>
  3. Server verifies the token with Firebase Admin SDK
  4. Server looks up / creates the user record in PostgreSQL
  5. Server returns user data from PostgreSQL

Legacy JWT login/register endpoints are removed.
The /api/register endpoint now only creates the PostgreSQL record
after the client has already created the Firebase user.
"""

import os
from functools import wraps
from flask import Blueprint, request, jsonify, redirect, make_response
from db.connection import get_connection
from firebase.client import verify_firebase_token

auth_bp = Blueprint("auth", __name__)


def _get_firebase_uid_from_request() -> str | None:
    """Extract and verify the Firebase ID token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    id_token = auth_header[7:]
    try:
        decoded = verify_firebase_token(id_token)
        return decoded.get("uid")
    except Exception:
        return None


def token_required(f):
    """Decorator: requires a valid Firebase ID token in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = _get_firebase_uid_from_request()
        if not uid:
            return jsonify({"error": "Authorization token missing or invalid"}), 401
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE firebase_uid = %s", (uid,))
            row = cur.fetchone()
            cur.close()
            conn.close()
        except Exception:
            return jsonify({"error": "Authentication service unavailable"}), 500
        if not row:
            return jsonify({"error": "User not found in database. Please complete registration."}), 401
        request.user_id = row["id"]
        request.firebase_uid = uid
        return f(*args, **kwargs)
    return decorated


def page_login_required(f):
    """Server-side guard for HTML page routes. Validates Firebase token via cookie."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("gl_session", "")
        if not token:
            return redirect("/login?clear=1")
        try:
            decoded = verify_firebase_token(token)
            if not decoded:
                raise ValueError("Invalid token")
        except Exception:
            resp = make_response(redirect("/login?clear=1"))
            resp.delete_cookie("gl_session")
            return resp
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Create a PostgreSQL user record after Firebase user creation.
    The client must:
      1. Create the user in Firebase (client SDK)
      2. Send the Firebase ID token + profile data here
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Firebase ID token required"}), 401
    id_token = auth_header[7:]

    try:
        decoded = verify_firebase_token(id_token)
        firebase_uid = decoded["uid"]
        firebase_email = decoded.get("email", "")
    except Exception as e:
        return jsonify({"error": f"Invalid Firebase token: {e}"}), 401

    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    full_name = (data.get("full_name") or "").strip()
    institution = (data.get("institution") or "").strip()
    research_area = (data.get("research_area") or "").strip()
    email = (data.get("email") or firebase_email).strip().lower()

    if not username or len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if not email:
        return jsonify({"error": "Email is required"}), 400

    initials = (
        "".join(p[0].upper() for p in (full_name or username).split()[:2])
        or username[:2].upper()
    )

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO users
               (firebase_uid, email, username, full_name, institution, research_area, avatar_initials)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (firebase_uid) DO UPDATE
               SET email = EXCLUDED.email
               RETURNING id, username, email, full_name, institution, research_area, avatar_initials, bio, created_at""",
            (firebase_uid, email, username, full_name, institution, research_area, initials),
        )
        user = dict(cur.fetchone())
        conn.commit()
        cur.close()
        conn.close()
        user["created_at"] = str(user.get("created_at") or "")
        return jsonify({"user": user}), 201
    except Exception as e:
        err = str(e)
        if "unique" in err.lower() and "email" in err.lower():
            return jsonify({"error": "Email already registered"}), 409
        if "unique" in err.lower() and "username" in err.lower():
            return jsonify({"error": "Username already taken"}), 409
        return jsonify({"error": "Registration failed. Please try again."}), 500


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Sync Firebase user into PostgreSQL on first login.
    Client sends Firebase ID token; server returns the DB user record.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Firebase ID token required"}), 401
    id_token = auth_header[7:]

    try:
        decoded = verify_firebase_token(id_token)
        firebase_uid = decoded["uid"]
        firebase_email = decoded.get("email", "")
    except Exception as e:
        return jsonify({"error": f"Invalid Firebase token: {e}"}), 401

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, username, email, full_name, institution, research_area,
                      bio, avatar_initials, is_verified, is_admin, institution_id, created_at
               FROM users WHERE firebase_uid = %s""",
            (firebase_uid,),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        return jsonify({"error": "Authentication service unavailable"}), 500

    if not user:
        return jsonify({
            "error": "User not found in database. Please register first.",
            "needs_registration": True,
        }), 404

    user_dict = dict(user)
    user_dict["created_at"] = str(user_dict.get("created_at") or "")
    resp = make_response(jsonify({"user": user_dict}))
    resp.set_cookie(
        "gl_session", id_token, max_age=7 * 24 * 60 * 60, httponly=True, samesite="Lax"
    )
    return resp


@auth_bp.route("/logout", methods=["POST"])
def logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie("gl_session")
    return resp


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

    user_dict = dict(user)
    user_dict["created_at"] = str(user_dict.get("created_at") or "")
    return jsonify(user_dict)


@auth_bp.route("/user/profile", methods=["PUT"])
@token_required
def update_profile():
    data = request.get_json() or {}
    full_name = (data.get("full_name") or "").strip()
    institution = (data.get("institution") or "").strip()
    research_area = (data.get("research_area") or "").strip()
    bio = (data.get("bio") or "").strip()
    initials = (
        "".join(p[0].upper() for p in full_name.split()[:2]) if full_name else None
    )
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
    return jsonify(d)


@auth_bp.route("/check-availability", methods=["GET"])
def check_availability():
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
