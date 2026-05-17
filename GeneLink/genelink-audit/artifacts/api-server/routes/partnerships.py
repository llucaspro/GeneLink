from flask import Blueprint, request, jsonify
from routes.auth import token_required
from routes.inst_auth import inst_token_required
from db.connection import get_connection
from datetime import datetime, timezone

partnerships_bp = Blueprint("partnerships", __name__)


# ── Partnerships / Oportunidades ─────────────────────────────────────────────

@partnerships_bp.route("/partnerships", methods=["GET"])
def list_partnerships():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    offset = (page - 1) * per_page
    tipo = request.args.get("type", "").strip()
    try:
        conn = get_connection()
        cur = conn.cursor()
        where = "WHERE p.is_active = TRUE"
        params = []
        if tipo:
            where += " AND p.type = %s"
            params.append(tipo)
        cur.execute(
            f"""SELECT p.*, i.name AS inst_name, i.short_name AS inst_short,
                       i.logo_initials, i.is_verified AS inst_verified,
                       i.city, i.state
                FROM partnerships p
                JOIN institutions i ON i.id = p.institution_id
                {where}
                ORDER BY p.created_at DESC LIMIT %s OFFSET %s""",
            params + [per_page, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) AS total FROM partnerships p JOIN institutions i ON i.id = p.institution_id {where}", params)
        total = cur.fetchone()["total"]
        cur.close(); conn.close()
        for r in rows:
            r["created_at"] = str(r.get("created_at") or "")
            if isinstance(r.get("inst_verified"), int):
                r["inst_verified"] = bool(r["inst_verified"])
        return jsonify({"partnerships": rows, "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@partnerships_bp.route("/partnerships", methods=["POST"])
@inst_token_required
def create_partnership():
    data = request.get_json() or {}
    title        = (data.get("title") or "").strip()
    description  = (data.get("description") or "").strip()
    p_type       = (data.get("type") or "Vaga de Pesquisa").strip()
    requirements = (data.get("requirements") or "").strip()
    location     = (data.get("location") or "").strip()
    deadline     = data.get("deadline")

    if not title or not description:
        return jsonify({"error": "Título e descrição são obrigatórios"}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO partnerships (institution_id, title, description, type, requirements, location, deadline, is_active)
               VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE)
               RETURNING id, title, type, created_at""",
            (request.inst_id, title, description, p_type, requirements or None, location or None, deadline or None),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close(); conn.close()
        d = dict(row)
        d["created_at"] = str(d.get("created_at") or "")
        return jsonify(d), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@partnerships_bp.route("/partnerships/<int:pid>", methods=["DELETE"])
@inst_token_required
def delete_partnership(pid):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE partnerships SET is_active=FALSE WHERE id=%s AND institution_id=%s", (pid, request.inst_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@partnerships_bp.route("/partnerships/<int:pid>/apply", methods=["POST"])
@token_required
def apply_partnership(pid):
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM partnership_applications WHERE partnership_id=%s AND user_id=%s", (pid, request.user_id))
        if cur.fetchone():
            cur.close(); conn.close()
            return jsonify({"error": "Você já se candidatou a esta vaga"}), 409
        cur.execute(
            "INSERT INTO partnership_applications (partnership_id, user_id, message) VALUES (%s,%s,%s)",
            (pid, request.user_id, message or None),
        )
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Institution Members ──────────────────────────────────────────────────────

@partnerships_bp.route("/inst/members", methods=["GET"])
@inst_token_required
def inst_members():
    try:
        conn = get_connection()
        cur = conn.cursor()
        # Get institution email domain
        cur.execute("SELECT email_domain FROM institutions WHERE id=%s", (request.inst_id,))
        inst = cur.fetchone()
        if not inst:
            cur.close(); conn.close()
            return jsonify({"error": "Instituição não encontrada"}), 404

        email_domain = inst["email_domain"] or ""
        # Members explicitly linked + researchers whose email matches domain
        cur.execute(
            """SELECT u.id, u.username, u.full_name, u.email, u.research_area,
                      u.avatar_initials, u.is_verified, u.created_at,
                      m.role, m.joined_at,
                      CASE WHEN m.user_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_member
               FROM users u
               LEFT JOIN institution_members m ON m.user_id = u.id AND m.institution_id = %s
               WHERE m.institution_id = %s
                  OR (u.email LIKE %s)
               ORDER BY is_member DESC, u.full_name ASC
               LIMIT 200""",
            (request.inst_id, request.inst_id, f"%@{email_domain}" if email_domain else "NOMATCH"),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        for r in rows:
            r["created_at"] = str(r.get("created_at") or "")
            r["joined_at"] = str(r.get("joined_at") or "")
            if isinstance(r.get("is_verified"), int): r["is_verified"] = bool(r["is_verified"])
            if isinstance(r.get("is_member"), int): r["is_member"] = bool(r["is_member"])
        return jsonify({"members": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@partnerships_bp.route("/inst/members/<int:user_id>/link", methods=["POST"])
@inst_token_required
def link_member(user_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO institution_members (institution_id, user_id, role) VALUES (%s,%s,'member') ON CONFLICT DO NOTHING",
            (request.inst_id, user_id),
        )
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@partnerships_bp.route("/inst/members/<int:user_id>/unlink", methods=["POST"])
@inst_token_required
def unlink_member(user_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM institution_members WHERE institution_id=%s AND user_id=%s", (request.inst_id, user_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Research Library ─────────────────────────────────────────────────────────

@partnerships_bp.route("/inst/library", methods=["GET"])
@inst_token_required
def inst_library():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT rl.*, u.username, u.avatar_initials
               FROM research_library rl
               LEFT JOIN users u ON u.id = rl.user_id
               WHERE rl.institution_id = %s
               ORDER BY rl.created_at DESC LIMIT 100""",
            (request.inst_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        for r in rows:
            r["created_at"] = str(r.get("created_at") or "")
        return jsonify({"items": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@partnerships_bp.route("/inst/library", methods=["POST"])
@inst_token_required
def create_library_item():
    data = request.get_json() or {}
    title       = (data.get("title") or "").strip()
    content     = (data.get("content") or "").strip()
    category    = (data.get("category") or "Dados de Pesquisa").strip()
    is_public   = bool(data.get("is_public", False))

    if not title:
        return jsonify({"error": "Título é obrigatório"}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO research_library (institution_id, title, content, category, is_public)
               VALUES (%s,%s,%s,%s,%s) RETURNING id, title, created_at""",
            (request.inst_id, title, content or None, category, is_public),
        )
        row = dict(cur.fetchone())
        row["created_at"] = str(row.get("created_at") or "")
        conn.commit()
        cur.close(); conn.close()
        return jsonify(row), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@partnerships_bp.route("/inst/library/<int:item_id>", methods=["DELETE"])
@inst_token_required
def delete_library_item(item_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM research_library WHERE id=%s AND institution_id=%s", (item_id, request.inst_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Public library (researchers see items from their institution) ─────────────

@partnerships_bp.route("/library/institution/<int:inst_id>", methods=["GET"])
@token_required
def public_library(inst_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        # Check if user is a member
        cur.execute("SELECT id FROM institution_members WHERE institution_id=%s AND user_id=%s", (inst_id, request.user_id))
        is_member = cur.fetchone() is not None
        if is_member:
            cur.execute(
                "SELECT rl.*, u.username FROM research_library rl LEFT JOIN users u ON u.id=rl.user_id WHERE rl.institution_id=%s ORDER BY rl.created_at DESC",
                (inst_id,),
            )
        else:
            cur.execute(
                "SELECT rl.*, u.username FROM research_library rl LEFT JOIN users u ON u.id=rl.user_id WHERE rl.institution_id=%s AND rl.is_public=TRUE ORDER BY rl.created_at DESC",
                (inst_id,),
            )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        for r in rows:
            r["created_at"] = str(r.get("created_at") or "")
        return jsonify({"items": rows, "is_member": is_member})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
