import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


class PrefixMiddleware:
    """Strip the /gl path prefix so Flask routes work without modification.
    The Replit shared proxy mounts this app at /gl but does NOT rewrite paths,
    so Flask would receive /gl/login instead of /login. This middleware corrects that."""

    def __init__(self, wsgi_app, prefix="/gl"):
        self.app = wsgi_app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path.startswith(self.prefix):
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + self.prefix
        return self.app(environ, start_response)

from flask import Flask, render_template, jsonify, request, make_response
import requests as http_requests
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from db.init_db import init_db
from db.connection import get_connection
from routes.auth import auth_bp, token_required, page_login_required
from routes.genes import genes_bp
from routes.forum import forum_bp
from routes.institutions import institutions_bp
from routes.channels import channels_bp
from routes.admin import admin_bp
from routes.inst_auth import inst_auth_bp
from routes.partnerships import partnerships_bp
from routes.preprints import preprints_bp

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SESSION_SECRET", "genelink-dev-secret-2024")

CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", logger=False, engineio_logger=False)

app.register_blueprint(auth_bp, url_prefix="/api")
app.register_blueprint(genes_bp, url_prefix="/api")
app.register_blueprint(forum_bp, url_prefix="/api")
app.register_blueprint(institutions_bp, url_prefix="/api")
app.register_blueprint(channels_bp, url_prefix="/api")
app.register_blueprint(admin_bp, url_prefix="/api")
app.register_blueprint(inst_auth_bp, url_prefix="/api")
app.register_blueprint(partnerships_bp, url_prefix="/api")
app.register_blueprint(preprints_bp, url_prefix="/api")

app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix="/gl")


# ── Frontend page routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login_page():
    clear_storage = request.args.get("clear") == "1"
    resp = make_response(render_template("login.html", clear_storage=clear_storage))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@app.route("/dashboard")
@page_login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/search")
@page_login_required
def search():
    return render_template("search.html")


@app.route("/profile")
@page_login_required
def profile():
    return render_template("profile.html")


@app.route("/forum")
@page_login_required
def forum():
    return render_template("forum.html")


@app.route("/forum/<int:post_id>")
@page_login_required
def forum_post(post_id):
    return render_template("forum_post.html")


@app.route("/chat")
@page_login_required
def chat():
    return render_template("chat.html")


@app.route("/institucional")
@page_login_required
def institucional():
    return render_template("institucional.html")


@app.route("/instituicao/<int:inst_id>")
@page_login_required
def instituicao(inst_id):
    return render_template("instituicao.html")


@app.route("/canais")
@page_login_required
def canais():
    return render_template("canais.html")


@app.route("/canal/<int:channel_id>")
@page_login_required
def canal(channel_id):
    return render_template("canal.html")


@app.route("/recursos")
@page_login_required
def recursos():
    return render_template("recursos.html")


@app.route("/admin")
@page_login_required
def admin_panel():
    return render_template("admin.html")


@app.route("/inst-dashboard")
def inst_dashboard():
    return render_template("inst_dashboard.html")


@app.route("/parcerias")
def parcerias():
    return render_template("parcerias.html")


@app.route("/preprints")
@page_login_required
def preprints():
    return render_template("preprints.html")


@app.route("/preprint/<int:preprint_id>")
@page_login_required
def preprint_view(preprint_id):
    return render_template("preprint.html")


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
    import jwt as pyjwt
    token = data.get("token", "")
    message = (data.get("message") or "").strip()
    if not message or len(message) > 2000:
        return

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
            """INSERT INTO chat_messages (user_id, username, message)
               VALUES (%s, %s, %s)
               RETURNING id, created_at""",
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
    except Exception:
        emit("error", {"message": "Failed to send message"})


@socketio.on("disconnect")
def handle_disconnect():
    pass


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
