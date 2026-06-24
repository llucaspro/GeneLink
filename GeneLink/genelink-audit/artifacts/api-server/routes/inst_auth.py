"""
Institution authentication — migrated to Firebase Auth.

Institutions authenticate via Firebase (email/password).
After Firebase auth, the server validates the token and checks
if the institution record is verified in PostgreSQL.

The institution must be pre-registered in the DB with their
firebase_uid set by an admin (or via the registration flow).
"""

import os
from functools import wraps
from flask import Blueprint, request, jsonify, make_response
from db.connection import get_connection
from firebase.client import verify_firebase_token

inst_auth_bp = Blueprint("inst_auth", __name__)

INST_COOKIE = "gl_inst_session"
COOKIE_MAX_AGE = 24 * 60 * 60  # 24 horas


def inst_token_required(f):
    """Decorator: requires a valid Firebase ID token belonging to an institution account."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(INST_COOKIE, "")
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        if not token:
            return jsonify({"error": "Institution login required"}), 401
        try:
            decoded = verify_firebase_token(token)
            firebase_uid = decoded.get("uid")
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, is_verified FROM institutions WHERE firebase_uid = %s",
                (firebase_uid,),
            )
            inst = cur.fetchone()
            cur.close()
            conn.close()
        except Exception:
            return jsonify({"error": "Authentication service unavailable"}), 500
        if not inst:
            return jsonify({"error": "Institution not found"}), 401
        if not inst["is_verified"]:
            return jsonify({"error": "Instituicao aguardando aprovacao"}), 403
        request.inst_id = inst["id"]
        request.firebase_uid = firebase_uid
        return f(*args, **kwargs)
    return decorated


@inst_auth_bp.route("/institutions/login", methods=["POST"])
def inst_login():
    """
    Validate a Firebase ID token for an institution account.
    The client authenticates with Firebase first, then sends the ID token here.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Firebase ID token required"}), 401
    id_token = auth_header[7:]

    try:
        decoded = verify_firebase_token(id_token)
        firebase_uid = decoded["uid"]
    except Exception as e:
        return jsonify({"error": f"Invalid Firebase token: {e}"}), 401

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, name, short_name, email_domain, logo_initials, city, state,
                      type, is_verified, cnpj, website
               FROM institutions WHERE firebase_uid = %s""",
            (firebase_uid,),
        )
        inst = cur.fetchone()
        cur.close()
        conn.close()
    except Exception:
        return jsonify({"error": "Servico indisponivel. Tente novamente."}), 500

    if not inst:
        return jsonify({"error": "Instituicao nao encontrada. Contate o suporte."}), 404

    if not inst["is_verified"]:
        return jsonify({"error": "Instituicao aguardando aprovacao. Voce recebera um e-mail quando for aprovada."}), 403

    inst_dict = {
        "id": inst["id"],
        "name": inst["name"],
        "short_name": inst["short_name"],
        "email_domain": inst["email_domain"],
        "logo_initials": inst["logo_initials"],
        "city": inst["city"],
        "state": inst["state"],
        "type": inst["type"],
        "is_verified": True,
        "cnpj": inst["cnpj"],
        "website": inst["website"],
    }
    resp = make_response(jsonify({"institution": inst_dict}))
    resp.set_cookie(
        INST_COOKIE, id_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )
    return resp


@inst_auth_bp.route("/institutions/me", methods=["GET"])
@inst_token_required
def inst_me():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT i.id, i.name, i.short_name, i.cnpj, i.email_domain, i.logo_initials,
                      i.city, i.state, i.type, i.is_verified, i.website, i.description,
                      (SELECT COUNT(*) FROM institution_members m WHERE m.institution_id = i.id) AS member_count,
                      (SELECT COUNT(*) FROM partnerships p WHERE p.institution_id = i.id AND p.is_active = TRUE) AS active_partnerships
               FROM institutions i WHERE i.id = %s""",
            (request.inst_id,),
        )
        inst = cur.fetchone()
        cur.close()
        conn.close()
        if not inst:
            return jsonify({"error": "Instituicao nao encontrada"}), 404
        d = dict(inst)
        if isinstance(d.get("is_verified"), int):
            d["is_verified"] = bool(d["is_verified"])
        return jsonify(d)
    except Exception:
        return jsonify({"error": "Erro ao carregar dados da instituicao"}), 500


@inst_auth_bp.route("/institutions/logout", methods=["POST"])
def inst_logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(INST_COOKIE)
    return resp
