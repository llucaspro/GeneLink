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


@app.route("/inst-candidates")
def inst_candidates():
    return render_template("inst_candidates.html")


@app.route("/parcerias")
def parcerias():
    return render_template("parcerias.html")


@app.route("/preprints")
@page_login_required
def preprints():
    return render_template("preprints.html")


@app.route("/preprints/criar")
@page_login_required
def preprint_criar():
    return render_template("preprint_criar.html")


@app.route("/preprint/<int:preprint_id>")
@page_login_required
def preprint_view(preprint_id):
    return render_template("preprint.html")


# ── Chat REST API (polling-based, reliable on all hosting) ──────────────────

@app.route("/api/chat/messages", methods=["GET"])
@token_required
def chat_get_messages():
    after_id = request.args.get("after", 0, type=int)
    limit = request.args.get("limit", 50, type=int)
    try:
        conn = get_connection()
        cur = conn.cursor()
        if after_id:
            cur.execute(
                """SELECT cm.id, cm.message, cm.created_at, cm.username,
                          u.avatar_initials
                   FROM chat_messages cm
                   LEFT JOIN users u ON u.id = cm.user_id
                   WHERE cm.id > %s
                   ORDER BY cm.id ASC LIMIT %s""",
                (after_id, limit),
            )
        else:
            cur.execute(
                """SELECT cm.id, cm.message, cm.created_at, cm.username,
                          u.avatar_initials
                   FROM chat_messages cm
                   LEFT JOIN users u ON u.id = cm.user_id
                   ORDER BY cm.id DESC LIMIT %s""",
                (limit,),
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        messages = [dict(r) for r in rows]
        if not after_id:
            messages = list(reversed(messages))
        for m in messages:
            if m.get("created_at"):
                m["created_at"] = str(m["created_at"])
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/messages", methods=["POST"])
@token_required
def chat_send_message():
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Mensagem não pode estar vazia"}), 400
    if len(message) > 2000:
        return jsonify({"error": "Mensagem muito longa (máx 2000 caracteres)"}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT username, avatar_initials FROM users WHERE id=%s", (request.user_id,))
        user = cur.fetchone()
        if not user:
            cur.close(); conn.close()
            return jsonify({"error": "Usuário não encontrado"}), 404
        cur.execute(
            """INSERT INTO chat_messages (user_id, username, message)
               VALUES (%s, %s, %s)
               RETURNING id, created_at""",
            (request.user_id, user["username"], message),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({
            "id": row["id"],
            "username": user["username"],
            "avatar_initials": user["avatar_initials"],
            "message": message,
            "created_at": str(row["created_at"]),
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Health check ────────────────────────────────────────────────────────────

@app.route("/api/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "GeneLink API"})


# ── DB init (runs on every worker startup, safe with IF NOT EXISTS) ──────────

init_db()


# ── Entrypoint (dev only — production uses gunicorn) ─────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[GeneLink] Starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
