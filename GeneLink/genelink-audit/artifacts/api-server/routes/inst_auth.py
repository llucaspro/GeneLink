import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, make_response
from db.connection import get_connection

inst_auth_bp = Blueprint("inst_auth", __name__)

SECRET_KEY = os.environ.get("SESSION_SECRET", "genelink-dev-secret")
INST_COOKIE = "gl_inst_session"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60


def generate_inst_token(inst_id):
    payload = {
        "inst_id": inst_id,
        "account_type": "institution",
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def inst_token_required(f):
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
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            if data.get("account_type") != "institution":
                return jsonify({"error": "Not an institution token"}), 403
            request.inst_id = data["inst_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


@inst_auth_bp.route("/institutions/login", methods=["POST"])
def inst_login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return jsonify({"error": "E-mail e senha são obrigatórios"}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, short_name, email_domain, logo_initials, city, state, type, is_verified, cnpj, website, password_hash FROM institutions WHERE LOWER(email) = %s OR LOWER(email_domain) = %s",
            (email, email.split("@")[-1] if "@" in email else email),
        )
        inst = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": "Serviço indisponível"}), 500

    if not inst:
        return jsonify({"error": "Instituição não encontrada com este e-mail"}), 401

    if not inst["password_hash"]:
        return jsonify({"error": "Senha não configurada. Contate o administrador do GeneLink."}), 401

    if not bcrypt.checkpw(password.encode("utf-8"), inst["password_hash"].encode("utf-8")):
        return jsonify({"error": "E-mail ou senha incorretos"}), 401

    if not inst["is_verified"]:
        return jsonify({"error": "Instituição aguardando aprovação pelo GeneLink. Você receberá um e-mail quando for aprovada."}), 403

    token = generate_inst_token(inst["id"])
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
    resp = make_response(jsonify({"token": token, "institution": inst_dict}))
    resp.set_cookie(INST_COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="Lax")
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
            return jsonify({"error": "Instituição não encontrada"}), 404
        d = dict(inst)
        if isinstance(d.get("is_verified"), int):
            d["is_verified"] = bool(d["is_verified"])
        return jsonify(d)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@inst_auth_bp.route("/institutions/logout", methods=["POST"])
def inst_logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(INST_COOKIE)
    return resp
