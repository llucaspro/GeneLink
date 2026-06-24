"""
Channel messages — migrated to Firestore for real-time delivery.
Channel metadata (name, description, permissions) stays in PostgreSQL.

Firestore structure:
  channel_messages/{channel_id}/messages/{auto_id}
    - user_id: int
    - username: str
    - avatar_initials: str
    - content: str
    - created_at: SERVER_TIMESTAMP
"""

from flask import Blueprint, request, jsonify
from routes.auth import token_required
from db.connection import get_connection
from firebase.client import get_firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP, Query

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
                "SELECT id, name, description FROM institution_channels WHERE institution_id=%s AND is_public=1",
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
        return jsonify({"error": str(e)}), 500


@channels_bp.route("/channels/<int:channel_id>/messages", methods=["GET"])
@token_required
def get_messages(channel_id):
    """Fetch channel messages from Firestore (real-time capable on the client)."""
    limit = min(int(request.args.get("limit", 50)), 200)
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
        cur.close(); conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    db = get_firestore()
    docs = (
        db.collection("channel_messages")
        .document(str(channel_id))
        .collection("messages")
        .order_by("created_at", direction=Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    messages = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        if d.get("created_at"):
            d["created_at"] = (
                d["created_at"].isoformat()
                if hasattr(d["created_at"], "isoformat")
                else str(d["created_at"])
            )
        messages.append(d)
    return jsonify({"messages": list(reversed(messages))})


@channels_bp.route("/channels/<int:channel_id>/messages", methods=["POST"])
@token_required
def post_message(channel_id):
    """Send a channel message to Firestore."""
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    if not content or len(content) > 4000:
        return jsonify({"error": "Mensagem inválida (máx 4000 caracteres)"}), 400
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
        cur.close(); conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not user:
        return jsonify({"error": "Usuário não encontrado"}), 404

    db = get_firestore()
    msg_ref = (
        db.collection("channel_messages")
        .document(str(channel_id))
        .collection("messages")
        .document()
    )
    msg_ref.set({
        "user_id": request.user_id,
        "username": user["username"],
        "avatar_initials": user["avatar_initials"] or "",
        "content": content,
        "created_at": SERVER_TIMESTAMP,
    })
    return jsonify({
        "id": msg_ref.id,
        "content": content,
        "username": user["username"],
        "avatar_initials": user["avatar_initials"],
    }), 201


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
        return jsonify({"error": str(e)}), 500
