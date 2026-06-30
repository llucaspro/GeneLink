from flask import Blueprint, request, jsonify
from routes.auth import token_required
from db.connection import get_connection

channels_bp = Blueprint("channels", __name__)


def _check_member(cur, inst_id, user_id):
    cur.execute(
        "SELECT role FROM institution_members WHERE institution_id=%s AND user_id=%s",
        (inst_id, user_id),
    )
    return cur.fetchone()


@channels_bp.route("/institutions/<int:inst_id>/channels", methods=["GET"])
@token_required
def list_channels(inst_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        membership = _check_member(cur, inst_id, request.user_id)
        if not membership:
            cur.execute(
                "SELECT id, name, description FROM institution_channels WHERE institution_id=%s AND is_public=TRUE",
                (inst_id,),
            )
        else:
            cur.execute(
                "SELECT id, name, description, is_public FROM institution_channels WHERE institution_id=%s ORDER BY name",
                (inst_id,),
            )
        channels = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({"channels": channels, "is_member": bool(membership)})
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


@channels_bp.route("/channels/<int:channel_id>/messages", methods=["GET"])
@token_required
def get_messages(channel_id):
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    offset = (page - 1) * per_page
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT institution_id, is_public FROM institution_channels WHERE id=%s",
            (channel_id,),
        )
        channel = cur.fetchone()
        if not channel:
            cur.close(); conn.close()
            return jsonify({"error": "Canal não encontrado"}), 404

        inst_id = channel["institution_id"]
        is_public = channel["is_public"]

        if not is_public:
            membership = _check_member(cur, inst_id, request.user_id)
            if not membership:
                cur.close(); conn.close()
                return jsonify({"error": "Acesso restrito a membros"}), 403

        cur.execute(
            """SELECT cm.id, cm.content, cm.created_at, cm.username,
                      u.avatar_initials, u.is_verified
               FROM channel_messages cm
               JOIN users u ON u.id = cm.user_id
               WHERE cm.channel_id=%s
               ORDER BY cm.created_at DESC LIMIT %s OFFSET %s""",
            (channel_id, per_page, offset),
        )
        messages = list(reversed([dict(r) for r in cur.fetchall()]))
        cur.execute("SELECT COUNT(*) AS total FROM channel_messages WHERE channel_id=%s", (channel_id,))
        total = cur.fetchone()["total"]
        cur.close(); conn.close()
        for m in messages:
            if isinstance(m.get("is_verified"), int):
                m["is_verified"] = bool(m["is_verified"])
        return jsonify({"messages": messages, "total": total})
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


@channels_bp.route("/channels/<int:channel_id>/messages", methods=["POST"])
@token_required
def post_message(channel_id):
    data = request.get_json()
    content = (data.get("content") or "").strip()
    if not content or len(content) > 2000:
        return jsonify({"error": "Mensagem inválida"}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT institution_id, is_public FROM institution_channels WHERE id=%s",
            (channel_id,),
        )
        channel = cur.fetchone()
        if not channel:
            cur.close(); conn.close()
            return jsonify({"error": "Canal não encontrado"}), 404

        membership = _check_member(cur, channel["institution_id"], request.user_id)
        if not membership:
            cur.close(); conn.close()
            return jsonify({"error": "Apenas membros podem enviar mensagens"}), 403

        cur.execute("SELECT username, avatar_initials FROM users WHERE id=%s", (request.user_id,))
        user = cur.fetchone()
        cur.execute(
            """INSERT INTO channel_messages (channel_id, user_id, username, content)
               VALUES (%s,%s,%s,%s) RETURNING id, created_at""",
            (channel_id, request.user_id, user["username"], content),
        )
        msg = cur.fetchone()
        conn.commit()
        cur.close(); conn.close()
        return jsonify({
            "id": msg["id"],
            "content": content,
            "username": user["username"],
            "avatar_initials": user["avatar_initials"],
            "created_at": str(msg["created_at"]),
        }), 201
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


@channels_bp.route("/institutions/<int:inst_id>/channels", methods=["POST"])
@token_required
def create_channel(inst_id):
    data = request.get_json()
    name = (data.get("name") or "").strip().lower().replace(" ", "-")
    description = (data.get("description") or "").strip()
    is_public = bool(data.get("is_public", False))

    if not name:
        return jsonify({"error": "Nome do canal é obrigatório"}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        membership = _check_member(cur, inst_id, request.user_id)
        if not membership or membership["role"] not in ("admin", "moderator"):
            cur.close(); conn.close()
            return jsonify({"error": "Apenas admins podem criar canais"}), 403

        cur.execute(
            """INSERT INTO institution_channels (institution_id, name, description, is_public, created_by)
               VALUES (%s,%s,%s,%s,%s) RETURNING id, name, description, is_public""",
            (inst_id, name, description, is_public, request.user_id),
        )
        channel = cur.fetchone()
        conn.commit()
        cur.close(); conn.close()
        return jsonify(dict(channel)), 201
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500
