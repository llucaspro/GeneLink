import re
import os
import logging
import threading
import bcrypt
import requests as http_req
from flask import Blueprint, request, jsonify
from routes.auth import token_required
from db.connection import get_connection
from security.middleware import is_safe_external_url, sanitize_string

_log = logging.getLogger("genelink.institutions")

institutions_bp = Blueprint("institutions", __name__)

CNPJ_RE = re.compile(r'^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$')
_CNPJ_WS_HOST = "publica.cnpj.ws"


def _fmt_cnpj(cnpj):
    digits = re.sub(r'\D', '', cnpj or '')
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return cnpj


def _institution_to_dict(row):
    d = dict(row)
    for k in ('is_verified', 'is_public'):
        if k in d and isinstance(d[k], int):
            d[k] = bool(d[k])
    return d


def _cnpj_type_hint(nat_desc: str) -> str:
    nd = nat_desc.lower()
    if "federal" in nd:       return "Universidade Federal"
    if "estadual" in nd:      return "Universidade Estadual"
    if "privad" in nd:        return "Universidade Particular"
    if "hospital" in nd:      return "Hospital Universitário"
    if "pesquisa" in nd or "científica" in nd: return "Instituto de Pesquisa"
    if "faculdade" in nd:     return "Faculdade"
    if "instituto" in nd:     return "Instituto Federal"
    return ""


# ── CNPJ Lookup (SSRF-protected) ──────────────────────────────────────────────

@institutions_bp.route("/cnpj/<cnpj_raw>", methods=["GET"])
@token_required
def lookup_cnpj(cnpj_raw):
    """Consulta CNPJ via cnpj.ws. Requires auth. SSRF protection: only hits whitelisted host."""
    digits = re.sub(r'\D', '', cnpj_raw)
    if not re.fullmatch(r'\d{14}', digits):
        return jsonify({"error": "CNPJ deve ter 14 dígitos"}), 400

    target_url = f"https://{_CNPJ_WS_HOST}/cnpj/{digits}"
    if not is_safe_external_url(target_url):
        _log.warning("SSRF: blocked request to %s", target_url)
        return jsonify({"error": "External request not permitted"}), 403

    try:
        resp = http_req.get(
            target_url,
            timeout=8,
            headers={"Accept": "application/json", "User-Agent": "GeneLink/1.0"},
            allow_redirects=False,
        )
        if resp.status_code == 429:
            return jsonify({"error": "Limite de consultas atingido. Tente em instantes."}), 429
        if resp.status_code == 404:
            return jsonify({"error": "CNPJ não encontrado na Receita Federal"}), 404
        if resp.status_code != 200:
            return jsonify({"error": "Não foi possível consultar o CNPJ agora"}), 502
        d = resp.json()
        estab  = d.get("estabelecimento") or {}
        cidade = estab.get("cidade") or {}
        estado = estab.get("estado") or {}
        nature = d.get("natureza_juridica") or {}
        tipo   = _cnpj_type_hint(nature.get("descricao") or "")
        return jsonify({
            "cnpj"      : _fmt_cnpj(digits),
            "name"      : (d.get("razao_social") or "").title(),
            "short_name": d.get("nome_fantasia") or "",
            "type_hint" : tipo,
            "city"      : (cidade.get("nome") or "").title(),
            "state"     : estado.get("sigla") or "",
            "website"   : estab.get("website") or "",
            "valid"     : True,
        })
    except http_req.exceptions.Timeout:
        return jsonify({"error": "Timeout ao consultar CNPJ"}), 504
    except http_req.exceptions.ConnectionError:
        return jsonify({"error": "Não foi possível alcançar o serviço de CNPJ"}), 502
    except Exception:
        _log.exception("lookup_cnpj error digits=%s", digits)
        return jsonify({"error": "Erro ao consultar CNPJ"}), 502


# ── List Public Institutions ──────────────────────────────────────────────────

@institutions_bp.route("/institutions", methods=["GET"])
def list_institutions():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    offset = (page - 1) * per_page
    search = (request.args.get("search") or "").strip()[:100]
    inst_type = (request.args.get("type") or "").strip()[:50]

    try:
        conn = get_connection()
        cur = conn.cursor()
        conditions = ["i.is_verified = TRUE"]
        params: list = []
        if search:
            conditions.append("(i.name ILIKE %s OR i.short_name ILIKE %s OR i.city ILIKE %s)")
            params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        if inst_type:
            conditions.append("i.type = %s")
            params.append(inst_type)
        where = "WHERE " + " AND ".join(conditions)
        cur.execute(
            f"""SELECT i.id, i.name, i.short_name, i.type, i.city, i.state,
                       i.description, i.website, i.avatar_initials, i.is_verified,
                       (SELECT COUNT(*) FROM institution_members m WHERE m.institution_id = i.id) AS member_count
               FROM institutions i {where}
               ORDER BY i.name ASC LIMIT %s OFFSET %s""",
            params + [per_page, offset],
        )
        rows = [_institution_to_dict(r) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) AS total FROM institutions i {where}", params)
        total = cur.fetchone()["total"]
        cur.close(); conn.close()
        return jsonify({"institutions": rows, "total": total, "page": page})
    except Exception:
        _log.exception("list_institutions error")
        return jsonify({"error": "Could not load institutions"}), 500


@institutions_bp.route("/institutions/<int:inst_id>", methods=["GET"])
def get_institution(inst_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT i.*,
                      (SELECT COUNT(*) FROM institution_members m WHERE m.institution_id = i.id) AS member_count
               FROM institutions i WHERE i.id = %s""",
            (inst_id,),
        )
        inst = cur.fetchone()
        if not inst:
            cur.close(); conn.close()
            return jsonify({"error": "Institution not found"}), 404
        cur.execute(
            """SELECT u.id, u.username, u.full_name, u.avatar_initials,
                      u.research_area, m.role, m.joined_at
               FROM institution_members m
               JOIN users u ON u.id = m.user_id
               WHERE m.institution_id = %s
               ORDER BY m.joined_at ASC LIMIT 20""",
            (inst_id,),
        )
        members = [dict(r) for r in cur.fetchall()]
        for m in members:
            m["joined_at"] = str(m.get("joined_at") or "")
        cur.close(); conn.close()
        d = _institution_to_dict(inst)
        d["members"] = members
        return jsonify(d)
    except Exception:
        _log.exception("get_institution error id=%d", inst_id)
        return jsonify({"error": "Could not load institution"}), 500


@institutions_bp.route("/institutions/<int:inst_id>/members", methods=["GET"])
def get_institution_members(inst_id):
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    offset = (page - 1) * per_page
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT u.id, u.username, u.full_name, u.avatar_initials,
                      u.research_area, u.is_verified, m.role, m.joined_at
               FROM institution_members m
               JOIN users u ON u.id = m.user_id
               WHERE m.institution_id = %s
               ORDER BY m.joined_at ASC LIMIT %s OFFSET %s""",
            (inst_id, per_page, offset),
        )
        members = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT COUNT(*) AS total FROM institution_members WHERE institution_id=%s", (inst_id,)
        )
        total = cur.fetchone()["total"]
        cur.close(); conn.close()
        for m in members:
            m["joined_at"] = str(m.get("joined_at") or "")
            if isinstance(m.get("is_verified"), int):
                m["is_verified"] = bool(m["is_verified"])
        return jsonify({"members": members, "total": total})
    except Exception:
        _log.exception("get_institution_members error id=%d", inst_id)
        return jsonify({"error": "Could not load members"}), 500


@institutions_bp.route("/institutions", methods=["POST"])
@token_required
def create_institution():
    data = request.get_json(silent=True) or {}
    try:
        name = sanitize_string((data.get("name") or "").strip(), max_len=255)
        short_name = sanitize_string((data.get("short_name") or "").strip(), max_len=50)
        inst_type = sanitize_string((data.get("type") or "").strip(), max_len=100)
        city = sanitize_string((data.get("city") or "").strip(), max_len=100)
        state = sanitize_string((data.get("state") or "").strip(), max_len=50)
        description = sanitize_string((data.get("description") or "").strip(), max_len=2000)
        website = sanitize_string((data.get("website") or "").strip(), max_len=255)
        email = sanitize_string((data.get("email") or "").strip(), max_len=255)
        cnpj = sanitize_string((data.get("cnpj") or "").strip(), max_len=20)
        is_public = bool(data.get("is_public", True))
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    if not name:
        return jsonify({"error": "Institution name is required"}), 400

    initials = "".join(w[0].upper() for w in (short_name or name).split()[:2]) or name[:2].upper()

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO institutions
               (name, short_name, type, city, state, description, website, email, cnpj,
                is_public, avatar_initials, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (name, short_name, inst_type, city, state, description, website, email, cnpj,
             is_public, initials, request.user_id),
        )
        inst = cur.fetchone()
        cur.execute(
            "INSERT INTO institution_members (institution_id, user_id, role) VALUES (%s, %s, 'admin')",
            (inst["id"], request.user_id),
        )
        conn.commit()
        cur.close(); conn.close()
        return jsonify(_institution_to_dict(inst)), 201
    except Exception:
        _log.exception("create_institution error")
        return jsonify({"error": "Could not create institution"}), 500


@institutions_bp.route("/institutions/<int:inst_id>", methods=["PUT"])
@token_required
def update_institution(inst_id):
    data = request.get_json(silent=True) or {}
    try:
        name = sanitize_string((data.get("name") or "").strip(), max_len=255)
        short_name = sanitize_string((data.get("short_name") or "").strip(), max_len=50)
        inst_type = sanitize_string((data.get("type") or "").strip(), max_len=100)
        city = sanitize_string((data.get("city") or "").strip(), max_len=100)
        state = sanitize_string((data.get("state") or "").strip(), max_len=50)
        description = sanitize_string((data.get("description") or "").strip(), max_len=2000)
        website = sanitize_string((data.get("website") or "").strip(), max_len=255)
        email = sanitize_string((data.get("email") or "").strip(), max_len=255)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, created_by FROM institutions WHERE id=%s", (inst_id,)
        )
        inst = cur.fetchone()
        if not inst:
            cur.close(); conn.close()
            return jsonify({"error": "Institution not found"}), 404

        cur.execute(
            "SELECT is_admin FROM users WHERE id=%s", (request.user_id,)
        )
        caller = cur.fetchone()
        is_admin = caller and bool(caller["is_admin"])
        is_owner = inst["created_by"] == request.user_id

        if not is_admin and not is_owner:
            cur.close(); conn.close()
            return jsonify({"error": "Not authorized"}), 403

        cur.execute(
            """UPDATE institutions
               SET name=%s, short_name=%s, type=%s, city=%s, state=%s,
                   description=%s, website=%s, email=%s
               WHERE id=%s RETURNING *""",
            (name, short_name, inst_type, city, state, description, website, email, inst_id),
        )
        updated = cur.fetchone()
        conn.commit()
        cur.close(); conn.close()
        return jsonify(_institution_to_dict(updated))
    except Exception:
        _log.exception("update_institution error id=%d", inst_id)
        return jsonify({"error": "Could not update institution"}), 500


@institutions_bp.route("/institutions/<int:inst_id>/join", methods=["POST"])
@token_required
def join_institution(inst_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM institutions WHERE id=%s AND is_verified=TRUE", (inst_id,))
        if not cur.fetchone():
            cur.close(); conn.close()
            return jsonify({"error": "Institution not found"}), 404
        cur.execute(
            "SELECT id FROM institution_members WHERE institution_id=%s AND user_id=%s",
            (inst_id, request.user_id),
        )
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({"error": "Already a member"}), 409
        cur.execute(
            "INSERT INTO institution_members (institution_id, user_id, role) VALUES (%s, %s, 'member')",
            (inst_id, request.user_id),
        )
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True}), 201
    except Exception:
        _log.exception("join_institution error id=%d", inst_id)
        return jsonify({"error": "Could not join institution"}), 500


@institutions_bp.route("/institutions/<int:inst_id>/leave", methods=["POST"])
@token_required
def leave_institution(inst_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM institution_members WHERE institution_id=%s AND user_id=%s",
            (inst_id, request.user_id),
        )
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True})
    except Exception:
        _log.exception("leave_institution error id=%d", inst_id)
        return jsonify({"error": "Could not leave institution"}), 500


@institutions_bp.route("/institutions/my", methods=["GET"])
@token_required
def my_institutions():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT i.id, i.name, i.short_name, i.type, i.city, i.state,
                      i.avatar_initials, i.is_verified, m.role
               FROM institution_members m
               JOIN institutions i ON i.id = m.institution_id
               WHERE m.user_id = %s
               ORDER BY m.joined_at DESC""",
            (request.user_id,),
        )
        rows = [_institution_to_dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({"institutions": rows})
    except Exception:
        _log.exception("my_institutions error")
        return jsonify({"error": "Could not load your institutions"}), 500
