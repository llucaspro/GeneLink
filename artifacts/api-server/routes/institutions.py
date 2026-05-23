import re
import os
import threading
import bcrypt
import requests as http_req
from flask import Blueprint, request, jsonify
from routes.auth import token_required
from db.connection import get_connection

institutions_bp = Blueprint("institutions", __name__)

CNPJ_RE = re.compile(r'^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$')


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


@institutions_bp.route("/cnpj/<cnpj_raw>", methods=["GET"])
def lookup_cnpj(cnpj_raw):
    """Consulta dados de um CNPJ na API pública da Receita Federal (cnpj.ws)."""
    digits = re.sub(r'\D', '', cnpj_raw)
    if len(digits) != 14:
        return jsonify({"error": "CNPJ deve ter 14 dígitos"}), 400
    try:
        resp = http_req.get(
            f"https://publica.cnpj.ws/cnpj/{digits}",
            timeout=8,
            headers={"Accept": "application/json", "User-Agent": "GeneLink/1.0"},
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
    except Exception as exc:
        return jsonify({"error": f"Erro ao consultar CNPJ: {exc}"}), 502


@institutions_bp.route("/institutions", methods=["GET"])
def list_institutions():
    verified_only = request.args.get("verified") == "1"
    search = (request.args.get("q") or "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    offset = (page - 1) * per_page

    try:
        conn = get_connection()
        cur = conn.cursor()
        conditions = []
        params = []
        if verified_only:
            conditions.append("i.is_verified = TRUE" if "postgres" in str(type(conn)) else "i.is_verified = 1")
        if search:
            conditions.append("(i.name ILIKE %s OR i.short_name ILIKE %s OR i.city ILIKE %s)" if True else "(i.name LIKE %s OR i.short_name LIKE %s OR i.city LIKE %s)")
            params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cur.execute(
            f"""SELECT i.*, 
                (SELECT COUNT(*) FROM institution_members m WHERE m.institution_id = i.id) AS member_count
                FROM institutions i {where}
                ORDER BY i.is_verified DESC, i.name ASC
                LIMIT %s OFFSET %s""",
            params + [per_page, offset],
        )
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*) AS total FROM institutions i {where}", params)
        total = cur.fetchone()["total"]
        cur.close()
        conn.close()
        return jsonify({"institutions": [_institution_to_dict(r) for r in rows], "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
            """SELECT u.id, u.username, u.full_name, u.avatar_initials, u.research_area, u.is_verified,
                      m.role, m.joined_at
               FROM institution_members m
               JOIN users u ON u.id = m.user_id
               WHERE m.institution_id = %s
               ORDER BY m.role DESC, m.joined_at ASC LIMIT 50""",
            (inst_id,),
        )
        members = cur.fetchall()
        cur.execute(
            "SELECT id, name, description, is_public FROM institution_channels WHERE institution_id = %s ORDER BY name",
            (inst_id,),
        )
        channels = cur.fetchall()
        cur.close(); conn.close()
        result = _institution_to_dict(inst)
        result["members"] = [_institution_to_dict(m) for m in members]
        result["channels"] = [_institution_to_dict(c) for c in channels]
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@institutions_bp.route("/institutions/register", methods=["POST"])
def register_institution_public():
    """Public endpoint — no login required. Submits institution for admin review."""
    data = request.get_json() or {}
    name        = (data.get("name") or "").strip()
    short_name  = (data.get("short_name") or "").strip()
    cnpj        = (data.get("cnpj") or "").strip()
    description = (data.get("description") or "").strip()
    website     = (data.get("website") or "").strip()
    email_domain= (data.get("email_domain") or "").strip().lower()
    city        = (data.get("city") or "").strip()
    state       = (data.get("state") or "").strip()
    inst_type   = (data.get("type") or "Universidade").strip()
    email       = (data.get("email") or "").strip().lower()
    password    = (data.get("password") or "").strip()

    if not name or not short_name or not email or not city or not state:
        return jsonify({"error": "Preencha todos os campos obrigatórios"}), 400
    if not cnpj or not CNPJ_RE.match(cnpj):
        return jsonify({"error": "CNPJ inválido"}), 400
    if not password or len(password) < 8:
        return jsonify({"error": "A senha deve ter pelo menos 8 caracteres"}), 400

    logo_initials = "".join(w[0].upper() for w in (short_name or name).split()[:3])[:4]
    cnpj_fmt      = _fmt_cnpj(cnpj)
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    if not email_domain and "@" in email:
        email_domain = email.split("@")[1].lower()

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO institutions
               (name, short_name, cnpj, email, password_hash, description, website, email_domain,
                logo_initials, city, state, type, is_verified)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)""",
            (name, short_name, cnpj_fmt, email, password_hash,
             description or None, website or None, email_domain or None,
             logo_initials, city, state, inst_type),
        )
        conn.commit()
        cur.close(); conn.close()

        # Send pending-review email in background (non-blocking)
        try:
            from routes.email_utils import send_institution_pending_email
            base_url = os.environ.get("BASE_URL", "https://genelink.app")
            threading.Thread(
                target=send_institution_pending_email,
                args=(name, cnpj_fmt, email, base_url),
                daemon=True,
            ).start()
        except Exception as mail_err:
            print(f"[GeneLink] Institution pending email error: {mail_err}")

        return jsonify({"message": "Instituição cadastrada e aguardando verificação"}), 201
    except Exception as e:
        err = str(e)
        if "unique" in err.lower() and "cnpj" in err.lower():
            return jsonify({"error": "Este CNPJ já está cadastrado no GeneLink"}), 409
        if "unique" in err.lower() and "email" in err.lower():
            return jsonify({"error": "Este e-mail já está cadastrado"}), 409
        return jsonify({"error": f"Falha ao cadastrar: {err}"}), 500


@institutions_bp.route("/institutions", methods=["POST"])
@token_required
def create_institution():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    short_name = (data.get("short_name") or "").strip()
    cnpj = (data.get("cnpj") or "").strip()
    description = (data.get("description") or "").strip()
    website = (data.get("website") or "").strip()
    email_domain = (data.get("email_domain") or "").strip().lower()
    city = (data.get("city") or "").strip()
    state = (data.get("state") or "").strip()
    inst_type = (data.get("type") or "Universidade").strip()

    if not name:
        return jsonify({"error": "Institution name is required"}), 400
    if cnpj and not CNPJ_RE.match(cnpj):
        return jsonify({"error": "CNPJ inválido"}), 400

    logo_initials = "".join(w[0].upper() for w in (short_name or name).split()[:3])[:4]
    cnpj_fmt = _fmt_cnpj(cnpj) if cnpj else None

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO institutions (name, short_name, cnpj, description, website, email_domain,
               logo_initials, city, state, type, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id, name, short_name, logo_initials, is_verified, created_at""",
            (name, short_name, cnpj_fmt, description, website, email_domain,
             logo_initials, city, state, inst_type, request.user_id),
        )
        inst = cur.fetchone()
        inst_id = inst["id"]
        cur.execute(
            "INSERT INTO institution_members (institution_id, user_id, role) VALUES (%s,%s,'admin')",
            (inst_id, request.user_id),
        )
        cur.execute(
            "INSERT INTO institution_channels (institution_id, name, description, is_public, created_by) VALUES (%s,'geral','Canal geral da instituição',1,%s)",
            (inst_id, request.user_id),
        )
        cur.execute(
            "INSERT INTO institution_channels (institution_id, name, description, is_public, created_by) VALUES (%s,'pesquisa','Discussões de pesquisa',0,%s)",
            (inst_id, request.user_id),
        )
        conn.commit()
        cur.close(); conn.close()
        return jsonify(_institution_to_dict(inst)), 201
    except Exception as e:
        err = str(e)
        if "unique" in err.lower() and "cnpj" in err.lower():
            return jsonify({"error": "CNPJ já cadastrado"}), 409
        return jsonify({"error": f"Falha ao criar instituição: {err}"}), 500


@institutions_bp.route("/institutions/<int:inst_id>/join", methods=["POST"])
@token_required
def join_institution(inst_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, is_verified FROM institutions WHERE id=%s", (inst_id,))
        inst = cur.fetchone()
        if not inst:
            cur.close(); conn.close()
            return jsonify({"error": "Institution not found"}), 404
        cur.execute(
            "INSERT OR IGNORE INTO institution_members (institution_id, user_id) VALUES (%s,%s)",
            (inst_id, request.user_id),
        )
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO institution_members (institution_id, user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (inst_id, request.user_id),
            )
            conn.commit()
            cur.close(); conn.close()
            return jsonify({"ok": True})
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500


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
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@institutions_bp.route("/my-institution", methods=["GET"])
@token_required
def my_institution():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT i.*, m.role
               FROM institution_members m
               JOIN institutions i ON i.id = m.institution_id
               WHERE m.user_id = %s
               ORDER BY m.joined_at DESC LIMIT 1""",
            (request.user_id,),
        )
        inst = cur.fetchone()
        cur.close(); conn.close()
        if not inst:
            return jsonify(None)
        return jsonify(_institution_to_dict(inst))
    except Exception as e:
        return jsonify(None)
