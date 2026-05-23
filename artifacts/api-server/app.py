import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, jsonify, request
import requests as http_requests
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from db.init_db import init_db
from db.connection import get_connection
from routes.auth import auth_bp, token_required
from routes.genes import genes_bp
from routes.forum import forum_bp

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SESSION_SECRET", "genelink-dev-secret-2024")

CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", logger=False, engineio_logger=False)

app.register_blueprint(auth_bp, url_prefix="/api")
app.register_blueprint(genes_bp, url_prefix="/api")
app.register_blueprint(forum_bp, url_prefix="/api")


# ── Frontend page routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/search")
def search():
    return render_template("search.html")


@app.route("/profile")
def profile():
    return render_template("profile.html")


@app.route("/forum")
def forum():
    return render_template("forum.html")


@app.route("/forum/<int:post_id>")
def forum_post(post_id):
    return render_template("forum_post.html")


@app.route("/chat")
def chat():
    return render_template("chat.html")


# ── Chat WebSocket ──────────────────────────────────────────────────────────

def _get_recent_messages(limit=50):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT cm.id, cm.message, cm.created_at, cm.username
               FROM chat_messages cm
               ORDER BY cm.created_at DESC LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return list(reversed([dict(r) for r in rows]))
    except Exception:
        return []


@socketio.on("connect")
def handle_connect():
    messages = _get_recent_messages()
    emit("history", {"messages": messages})


@socketio.on("send_message")
def handle_message(data):
    token = data.get("token", "")
    message = (data.get("message") or "").strip()
    if not message or len(message) > 2000:
        return

    import jwt as pyjwt
    SECRET_KEY = os.environ.get("SESSION_SECRET", "genelink-dev-secret-2024")
    try:
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload["user_id"]
    except Exception:
        emit("error", {"message": "Authentication required to send messages"})
        return

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT username, avatar_initials FROM users WHERE id=%s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.close()
            conn.close()
            return
        cur.execute(
            "INSERT INTO chat_messages (user_id, username, message) VALUES (%s, %s, %s) RETURNING id, created_at",
            (user_id, user["username"], message),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        socketio.emit("new_message", {
            "id": row["id"],
            "username": user["username"],
            "avatar_initials": user["avatar_initials"],
            "message": message,
            "created_at": str(row["created_at"]),
        })
    except Exception as e:
        emit("error", {"message": "Failed to send message"})


@socketio.on("disconnect")
def handle_disconnect():
    pass


# ── Firebase Config ──────────────────────────────────────────────────────────

@app.route("/api/firebase-config")
def firebase_config():
    api_key = os.environ.get("FIREBASE_API_KEY", "")
    auth_domain = os.environ.get("FIREBASE_AUTH_DOMAIN", "")
    project_id = os.environ.get("FIREBASE_PROJECT_ID", "")
    storage_bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", "")
    messaging_sender_id = os.environ.get("FIREBASE_MESSAGING_SENDER_ID", "")
    app_id = os.environ.get("FIREBASE_APP_ID", "")
    measurement_id = os.environ.get("FIREBASE_MEASUREMENT_ID", "")

    if not api_key or not project_id:
        return jsonify({"error": "Firebase não configurado"}), 404

    return jsonify({
        "apiKey": api_key,
        "authDomain": auth_domain,
        "projectId": project_id,
        "storageBucket": storage_bucket,
        "messagingSenderId": messaging_sender_id,
        "appId": app_id,
        "measurementId": measurement_id,
    })


# ── Firebase Auth — verifica ID token e sincroniza usuário ──────────────────

@app.route("/api/firebase-auth", methods=["POST"])
def firebase_auth_route():
    import jwt as pyjwt
    import bcrypt

    data = request.get_json() or {}
    id_token = data.get("id_token", "")
    display_name = data.get("display_name", "")
    email_hint = data.get("email", "")

    if not id_token:
        return jsonify({"error": "ID token obrigatório"}), 400

    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth, credentials as fb_creds

        # Inicializa o SDK apenas uma vez
        if not firebase_admin._apps:
            cred = fb_creds.Certificate({
                "type": "service_account",
                "project_id": os.environ.get("FIREBASE_PROJECT_ID", ""),
                "private_key_id": os.environ.get("FIREBASE_PRIVATE_KEY_ID", ""),
                "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
                "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL", ""),
                "client_id": os.environ.get("FIREBASE_CLIENT_ID", ""),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            })
            firebase_admin.initialize_app(cred)

        decoded = fb_auth.verify_id_token(id_token)
        uid = decoded.get("uid", "")
        email = decoded.get("email", email_hint or "")
        name = decoded.get("name", display_name or "")

        if not email:
            return jsonify({"error": "E-mail não disponível na conta"}), 400

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone()

        if not user:
            # Gera username a partir da parte local do e-mail
            username_base = email.split("@")[0].replace(".", "").replace("+", "").lower()[:20]
            username = username_base
            suffix = 1
            while True:
                cur.execute("SELECT id FROM users WHERE username=%s", (username,))
                if not cur.fetchone():
                    break
                username = f"{username_base}{suffix}"
                suffix += 1

            full_name = name or username
            avatar_initials = (full_name[:2] if full_name else username[:2]).upper()
            dummy_hash = bcrypt.hashpw(uid.encode(), bcrypt.gensalt()).decode()

            cur.execute(
                """INSERT INTO users (username, email, password_hash, full_name, avatar_initials)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id, username, email, full_name, avatar_initials, institution, research_area, bio, created_at""",
                (username, email, dummy_hash, full_name, avatar_initials),
            )
            user = cur.fetchone()
            conn.commit()

        cur.close()
        conn.close()

        user_dict = dict(user)
        SECRET_KEY = os.environ.get("SESSION_SECRET", "genelink-dev-secret-2024")
        import datetime
        token = pyjwt.encode(
            {"user_id": user_dict["id"], "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)},
            SECRET_KEY, algorithm="HS256"
        )
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        user_dict["created_at"] = str(user_dict.get("created_at", ""))
        return jsonify({"token": token, "user": user_dict})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Health check ────────────────────────────────────────────────────────────

@app.route("/api/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "GeneLink API"})


# ── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8080))
    print(f"[GeneLink] Starting on port {port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
