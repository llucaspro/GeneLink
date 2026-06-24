"""
Direct Messages routes using Firestore for real-time messaging.

Firestore collection structure:
  dm_conversations/{conv_id}          (conv_id = sorted uid pair: "uid1_uid2")
    - participants: [user_id_1, user_id_2]
    - created_at: timestamp
    messages/{auto_id}
      - sender_id: int
      - content: str
      - is_flagged: bool
      - read_at: timestamp | null
      - created_at: SERVER_TIMESTAMP

PostgreSQL keeps the conversation index for listing/search.
Firestore holds the actual messages for real-time delivery.
"""

from flask import Blueprint, request, jsonify
from firebase.client import get_firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP, Query
from routes.auth import token_required
from db.connection import get_connection

dm_bp = Blueprint("dm", __name__)


def _conv_id(user_a: int, user_b: int) -> str:
    return f"{min(user_a, user_b)}_{max(user_a, user_b)}"


@dm_bp.route("/dm/conversations", methods=["GET"])
@token_required
def list_conversations():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT pc.id, pc.user1_id, pc.user2_id, pc.created_at,
                      u1.username AS user1_username, u1.avatar_initials AS user1_initials,
                      u2.username AS user2_username, u2.avatar_initials AS user2_initials
               FROM private_conversations pc
               JOIN users u1 ON u1.id = pc.user1_id
               JOIN users u2 ON u2.id = pc.user2_id
               WHERE pc.user1_id = %s OR pc.user2_id = %s
               ORDER BY pc.created_at DESC""",
            (request.user_id, request.user_id),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        convs = []
        for r in rows:
            d = dict(r)
            d["created_at"] = str(d.get("created_at") or "")
            d["firestore_conv_id"] = _conv_id(d["user1_id"], d["user2_id"])
            convs.append(d)
        return jsonify({"conversations": convs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dm_bp.route("/dm/conversations/<int:other_user_id>", methods=["POST"])
@token_required
def get_or_create_conversation(other_user_id: int):
    """Get or create a conversation between the current user and another user."""
    me = request.user_id
    u1, u2 = min(me, other_user_id), max(me, other_user_id)
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM private_conversations WHERE user1_id=%s AND user2_id=%s",
            (u1, u2),
        )
        row = cur.fetchone()
        if row:
            cur.close()
            conn.close()
            return jsonify({"id": row["id"], "firestore_conv_id": _conv_id(u1, u2)})
        cur.execute(
            "INSERT INTO private_conversations (user1_id, user2_id) VALUES (%s, %s) RETURNING id",
            (u1, u2),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"id": new_id, "firestore_conv_id": _conv_id(u1, u2)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dm_bp.route("/dm/messages/<string:firestore_conv_id>", methods=["GET"])
@token_required
def get_dm_messages(firestore_conv_id: str):
    limit = min(int(request.args.get("limit", 50)), 200)
    db = get_firestore()
    docs = (
        db.collection("dm_conversations")
        .document(firestore_conv_id)
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
            d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else str(d["created_at"])
        messages.append(d)
    return jsonify({"messages": list(reversed(messages))})


@dm_bp.route("/dm/messages/<string:firestore_conv_id>", methods=["POST"])
@token_required
def send_dm_message(firestore_conv_id: str):
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Mensagem não pode estar vazia"}), 400
    if len(content) > 4000:
        return jsonify({"error": "Mensagem muito longa (máx 4000 caracteres)"}), 400

    db = get_firestore()
    conv_ref = db.collection("dm_conversations").document(firestore_conv_id)
    msg_ref = conv_ref.collection("messages").document()
    msg_ref.set({
        "sender_id": request.user_id,
        "content": content,
        "is_flagged": False,
        "read_at": None,
        "created_at": SERVER_TIMESTAMP,
    })
    return jsonify({"id": msg_ref.id}), 201
