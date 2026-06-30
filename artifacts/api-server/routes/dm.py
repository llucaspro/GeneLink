"""
GeneLink Private DMs (Direct Messages)
Endpoints para conversas privadas entre pesquisadores.
"""

from flask import Blueprint, jsonify, request
from db.connection import get_connection
from routes.auth import token_required
from routes.moderation import check_content, flag_message

dm_bp = Blueprint("dm", __name__)


# ── Listar conversas do usuário ───────────────────────────────────────────────

@dm_bp.route("/dm/conversations", methods=["GET"])
@token_required
def list_conversations():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                pc.id,
                pc.created_at,
                CASE WHEN pc.user1_id = %s THEN pc.user2_id ELSE pc.user1_id END AS other_id,
                u.username  AS other_username,
                u.full_name AS other_fullname,
                u.avatar_initials AS other_initials,
                (
                  SELECT pm.content FROM private_messages pm
                  WHERE pm.conversation_id = pc.id
                  ORDER BY pm.id DESC LIMIT 1
                ) AS last_message,
                (
                  SELECT pm.created_at FROM private_messages pm
                  WHERE pm.conversation_id = pc.id
                  ORDER BY pm.id DESC LIMIT 1
                ) AS last_at,
                (
                  SELECT COUNT(*) FROM private_messages pm
                  WHERE pm.conversation_id = pc.id
                    AND pm.sender_id != %s
                    AND pm.read_at IS NULL
                ) AS unread
            FROM private_conversations pc
            JOIN users u ON u.id = CASE WHEN pc.user1_id = %s THEN pc.user2_id ELSE pc.user1_id END
            WHERE pc.user1_id = %s OR pc.user2_id = %s
            ORDER BY last_at DESC NULLS LAST, pc.created_at DESC
            """,
            (request.user_id, request.user_id, request.user_id, request.user_id, request.user_id),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["created_at"] = str(d["created_at"]) if d.get("created_at") else None
            d["last_at"]    = str(d["last_at"])    if d.get("last_at")    else None
            result.append(d)
        return jsonify({"conversations": result})
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


# ── Iniciar / obter conversa com um usuário ───────────────────────────────────

@dm_bp.route("/dm/start", methods=["POST"])
@token_required
def start_conversation():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"error": "username obrigatório"}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, username, full_name, avatar_initials FROM users WHERE username=%s",
            (username,),
        )
        other = cur.fetchone()
        if not other:
            cur.close(); conn.close()
            return jsonify({"error": "Usuário não encontrado"}), 404

        other_id = other["id"]
        if other_id == request.user_id:
            cur.close(); conn.close()
            return jsonify({"error": "Você não pode conversar consigo mesmo"}), 400

        u1, u2 = sorted([request.user_id, other_id])

        cur.execute(
            "SELECT id FROM private_conversations WHERE user1_id=%s AND user2_id=%s",
            (u1, u2),
        )
        conv = cur.fetchone()
        if conv:
            conv_id = conv["id"]
        else:
            cur.execute(
                "INSERT INTO private_conversations (user1_id, user2_id) VALUES (%s, %s) RETURNING id",
                (u1, u2),
            )
            row = cur.fetchone()
            conv_id = row["id"]
            conn.commit()

        cur.close()
        conn.close()
        return jsonify({"conversation_id": conv_id, "other": dict(other)}), 200
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


# ── Mensagens de uma conversa ─────────────────────────────────────────────────

@dm_bp.route("/dm/conversations/<int:conv_id>/messages", methods=["GET"])
@token_required
def get_messages(conv_id):
    after_id = request.args.get("after", 0, type=int)
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM private_conversations WHERE id=%s AND (user1_id=%s OR user2_id=%s)",
            (conv_id, request.user_id, request.user_id),
        )
        if not cur.fetchone():
            cur.close(); conn.close()
            return jsonify({"error": "Conversa não encontrada"}), 404

        if after_id:
            cur.execute(
                """SELECT pm.id, pm.sender_id, pm.content, pm.created_at, pm.is_flagged,
                          u.username, u.avatar_initials
                   FROM private_messages pm
                   JOIN users u ON u.id = pm.sender_id
                   WHERE pm.conversation_id=%s AND pm.id > %s
                   ORDER BY pm.id ASC LIMIT 100""",
                (conv_id, after_id),
            )
            messages = [dict(r) for r in cur.fetchall()]
        else:
            cur.execute(
                """SELECT pm.id, pm.sender_id, pm.content, pm.created_at, pm.is_flagged,
                          u.username, u.avatar_initials
                   FROM private_messages pm
                   JOIN users u ON u.id = pm.sender_id
                   WHERE pm.conversation_id=%s
                   ORDER BY pm.id DESC LIMIT 80""",
                (conv_id,),
            )
            messages = list(reversed([dict(r) for r in cur.fetchall()]))

        for m in messages:
            m["created_at"] = str(m["created_at"]) if m.get("created_at") else None
            m["is_mine"] = (m["sender_id"] == request.user_id)

        cur.execute(
            """UPDATE private_messages
               SET read_at = NOW()
               WHERE conversation_id=%s AND sender_id != %s AND read_at IS NULL""",
            (conv_id, request.user_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


# ── Enviar mensagem ───────────────────────────────────────────────────────────

@dm_bp.route("/dm/conversations/<int:conv_id>/messages", methods=["POST"])
@token_required
def send_message(conv_id):
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Mensagem não pode estar vazia"}), 400
    if len(content) > 3000:
        return jsonify({"error": "Mensagem muito longa (máx 3000 caracteres)"}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM private_conversations WHERE id=%s AND (user1_id=%s OR user2_id=%s)",
            (conv_id, request.user_id, request.user_id),
        )
        if not cur.fetchone():
            cur.close(); conn.close()
            return jsonify({"error": "Conversa não encontrada"}), 404

        cur.execute(
            "SELECT username, avatar_initials FROM users WHERE id=%s",
            (request.user_id,),
        )
        user = cur.fetchone()

        mod = check_content(content)
        is_flagged = mod["flagged"]

        cur.execute(
            """INSERT INTO private_messages (conversation_id, sender_id, content, is_flagged)
               VALUES (%s, %s, %s, %s) RETURNING id, created_at""",
            (conv_id, request.user_id, content, is_flagged),
        )
        row = cur.fetchone()
        msg_id = row["id"]
        conn.commit()
        cur.close()
        conn.close()

        if is_flagged:
            flag_message(request.user_id, content, "dm", msg_id, mod["reasons"])

        return jsonify({
            "id": msg_id,
            "sender_id": request.user_id,
            "username": user["username"] if user else "",
            "avatar_initials": user["avatar_initials"] if user else "",
            "content": content,
            "created_at": str(row["created_at"]),
            "is_mine": True,
            "is_flagged": is_flagged,
        }), 201
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


# ── Total de mensagens não lidas ──────────────────────────────────────────────

@dm_bp.route("/dm/unread", methods=["GET"])
@token_required
def unread_count():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT COUNT(*) AS total
               FROM private_messages pm
               JOIN private_conversations pc ON pc.id = pm.conversation_id
               WHERE (pc.user1_id=%s OR pc.user2_id=%s)
                 AND pm.sender_id != %s
                 AND pm.read_at IS NULL""",
            (request.user_id, request.user_id, request.user_id),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return jsonify({"unread": row["total"] if row else 0})
    except Exception as e:
        return jsonify({"unread": 0})


# ── Perfil público de um usuário ──────────────────────────────────────────────

@dm_bp.route("/users/<username>/profile", methods=["GET"])
@token_required
def public_profile(username):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, username, full_name, institution, research_area,
                      bio, avatar_initials, is_verified, created_at
               FROM users WHERE username=%s""",
            (username,),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
        if not user:
            return jsonify({"error": "Usuário não encontrado"}), 404
        d = dict(user)
        d["created_at"] = str(d["created_at"]) if d.get("created_at") else None
        return jsonify(d)
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


# ── Alertas de moderação (somente admin) ─────────────────────────────────────

@dm_bp.route("/admin/flags", methods=["GET"])
@token_required
def admin_flags():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT is_admin FROM users WHERE id=%s", (request.user_id,))
        u = cur.fetchone()
        if not u or not u["is_admin"]:
            cur.close(); conn.close()
            return jsonify({"error": "Acesso negado"}), 403
        resolved = request.args.get("resolved", "false") == "true"
        cur.execute(
            """SELECT af.id, af.type, af.content, af.reason, af.resolved, af.created_at,
                      u.username AS sender_username
               FROM admin_flags af
               LEFT JOIN users u ON u.id = af.sender_id
               WHERE af.resolved=%s
               ORDER BY af.created_at DESC LIMIT 100""",
            (resolved,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        flags = []
        for r in rows:
            d = dict(r)
            d["created_at"] = str(d["created_at"]) if d.get("created_at") else None
            flags.append(d)
        return jsonify({"flags": flags})
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


@dm_bp.route("/admin/flags/<int:flag_id>/resolve", methods=["POST"])
@token_required
def resolve_flag(flag_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT is_admin FROM users WHERE id=%s", (request.user_id,))
        u = cur.fetchone()
        if not u or not u["is_admin"]:
            cur.close(); conn.close()
            return jsonify({"error": "Acesso negado"}), 403
        cur.execute("UPDATE admin_flags SET resolved=TRUE WHERE id=%s", (flag_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500
