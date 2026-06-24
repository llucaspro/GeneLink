"""
Chat routes using Firestore for real-time messaging.

Firestore collection structure:
  chat_messages/{auto_id}
    - user_id: int (PostgreSQL user id)
    - username: str
    - avatar_initials: str
    - message: str
    - created_at: Firestore SERVER_TIMESTAMP

The client can listen to the collection in real-time using the Firebase JS SDK,
so polling is no longer needed. These REST endpoints are kept for server-side
access and admin tools.
"""

from flask import Blueprint, request, jsonify
from firebase.client import get_firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP, Query
from routes.auth import token_required
from db.connection import get_connection

chat_bp = Blueprint("chat", __name__)

COLLECTION = "chat_messages"


@chat_bp.route("/chat/messages", methods=["GET"])
@token_required
def get_messages():
    limit = min(int(request.args.get("limit", 50)), 200)
    after_id = request.args.get("after_id")

    db = get_firestore()
    query = db.collection(COLLECTION).order_by("created_at", direction=Query.DESCENDING).limit(limit)

    if after_id:
        doc_ref = db.collection(COLLECTION).document(after_id)
        doc = doc_ref.get()
        if doc.exists:
            query = (
                db.collection(COLLECTION)
                .order_by("created_at", direction=Query.ASCENDING)
                .start_after(doc)
                .limit(limit)
            )

    docs = query.stream()
    messages = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else str(d["created_at"])
        messages.append(d)

    if not after_id:
        messages = list(reversed(messages))

    return jsonify({"messages": messages})


@chat_bp.route("/chat/messages", methods=["POST"])
@token_required
def send_message():
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
        cur.close()
        conn.close()
    except Exception:
        return jsonify({"error": "Failed to fetch user"}), 500

    if not user:
        return jsonify({"error": "Usuário não encontrado"}), 404

    db = get_firestore()
    doc_ref = db.collection(COLLECTION).document()
    payload = {
        "user_id": request.user_id,
        "username": user["username"],
        "avatar_initials": user["avatar_initials"] or "",
        "message": message,
        "created_at": SERVER_TIMESTAMP,
    }
    doc_ref.set(payload)

    return jsonify({
        "id": doc_ref.id,
        "username": user["username"],
        "avatar_initials": user["avatar_initials"],
        "message": message,
    }), 201
