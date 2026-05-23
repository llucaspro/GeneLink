import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify
from db.connection import get_connection

auth_bp = Blueprint("auth", __name__)
SECRET_KEY = os.environ.get("SESSION_SECRET", "genelink-dev-secret")


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
        user_dict["created_at"] = str(user_dict.get("created_at", ""))
        return jsonify({"token": token, "user": user_dict}), 201
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
    return jsonify({
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
            "created_at": str(user["created_at"] or ""),
        },
    })


@auth_bp.route("/user", methods=["GET"])
@token_required
def get_user():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, email, full_name, institution, research_area, bio, avatar_initials, created_at FROM users WHERE id = %s",
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
    user_dict["created_at"] = str(user_dict.get("created_at", ""))
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
                """UPDATE users SET full_name=%s, institution=%s, research_area=%s, bio=%s, avatar_initials=%s
                   WHERE id=%s RETURNING id, username, email, full_name, institution, research_area, bio, avatar_initials""",
                (full_name, institution, research_area, bio, initials, request.user_id),
            )
        else:
            cur.execute(
                """UPDATE users SET full_name=%s, institution=%s, research_area=%s, bio=%s
                   WHERE id=%s RETURNING id, username, email, full_name, institution, research_area, bio, avatar_initials""",
                (full_name, institution, research_area, bio, request.user_id),
            )
        user = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(dict(user))
    except Exception:
        return jsonify({"error": "Failed to update profile"}), 500
