from flask import Blueprint, request, jsonify
from routes.auth import token_required
from db.connection import get_connection

preprints_bp = Blueprint("preprints", __name__)

VALID_TYPES = ["Hipótese", "Artigo Preliminar", "Revisão", "Experimento"]
VALID_STATUSES = ["draft", "submitted", "under_review", "published"]


@preprints_bp.route("/preprints", methods=["GET"])
def list_preprints():
    type_filter = request.args.get("type", "").strip()
    status_filter = request.args.get("status", "submitted").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    offset = (page - 1) * per_page

    try:
        conn = get_connection()
        cur = conn.cursor()

        conditions = []
        params = []

        if status_filter and status_filter != "all":
            conditions.append("p.status = %s")
            params.append(status_filter)
        else:
            conditions.append("p.status != 'draft'")

        if type_filter:
            conditions.append("p.type = %s")
            params.append(type_filter)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cur.execute(
            f"""SELECT p.id, p.title, p.abstract, p.type, p.status, p.keywords,
                      p.created_at, p.updated_at,
                      u.username AS author_username, u.avatar_initials AS author_initials,
                      u.institution AS author_institution,
                      (SELECT COUNT(*) FROM preprint_reviews r WHERE r.preprint_id = p.id) AS review_count
               FROM preprints p JOIN users u ON p.author_id = u.id
               {where}
               ORDER BY p.created_at DESC LIMIT %s OFFSET %s""",
            params + [per_page, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]

        cur.execute(f"SELECT COUNT(*) AS total FROM preprints p {where}", params)
        total = cur.fetchone()["total"]

        cur.close(); conn.close()
        for r in rows:
            r["created_at"] = str(r.get("created_at") or "")
            r["updated_at"] = str(r.get("updated_at") or "")
        return jsonify({"preprints": rows, "total": total, "page": page})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@preprints_bp.route("/preprints/mine", methods=["GET"])
@token_required
def my_preprints():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT p.id, p.title, p.abstract, p.type, p.status, p.keywords,
                      p.created_at, p.updated_at,
                      (SELECT COUNT(*) FROM preprint_reviews r WHERE r.preprint_id = p.id) AS review_count
               FROM preprints p
               WHERE p.author_id = %s
               ORDER BY p.created_at DESC""",
            (request.user_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        for r in rows:
            r["created_at"] = str(r.get("created_at") or "")
            r["updated_at"] = str(r.get("updated_at") or "")
        return jsonify({"preprints": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@preprints_bp.route("/preprints/<int:preprint_id>", methods=["GET"])
def get_preprint(preprint_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT p.id, p.title, p.abstract, p.content, p.type, p.status,
                      p.keywords, p.doi, p.created_at, p.updated_at,
                      p.author_id,
                      u.username AS author_username, u.avatar_initials AS author_initials,
                      u.institution AS author_institution, u.research_area AS author_research_area
               FROM preprints p JOIN users u ON p.author_id = u.id
               WHERE p.id = %s""",
            (preprint_id,),
        )
        preprint = cur.fetchone()
        if not preprint:
            cur.close(); conn.close()
            return jsonify({"error": "Pré-publicação não encontrada"}), 404

        cur.execute(
            """SELECT r.id, r.content, r.rating, r.created_at,
                      u.username AS reviewer_username, u.avatar_initials AS reviewer_initials,
                      u.institution AS reviewer_institution
               FROM preprint_reviews r JOIN users u ON r.user_id = u.id
               WHERE r.preprint_id = %s ORDER BY r.created_at ASC""",
            (preprint_id,),
        )
        reviews = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()

        result = dict(preprint)
        result["created_at"] = str(result.get("created_at") or "")
        result["updated_at"] = str(result.get("updated_at") or "")
        for rev in reviews:
            rev["created_at"] = str(rev.get("created_at") or "")
        result["reviews"] = reviews
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@preprints_bp.route("/preprints", methods=["POST"])
@token_required
def create_preprint():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    abstract = (data.get("abstract") or "").strip()
    content = (data.get("content") or "").strip()
    ptype = (data.get("type") or "").strip()
    keywords = (data.get("keywords") or "").strip()
    status = (data.get("status") or "submitted").strip()

    if not title or len(title) < 5:
        return jsonify({"error": "Título deve ter ao menos 5 caracteres"}), 400
    if not abstract or len(abstract) < 20:
        return jsonify({"error": "Resumo deve ter ao menos 20 caracteres"}), 400
    if not content or len(content) < 50:
        return jsonify({"error": "Conteúdo deve ter ao menos 50 caracteres"}), 400
    if ptype not in VALID_TYPES:
        return jsonify({"error": f"Tipo inválido. Use: {', '.join(VALID_TYPES)}"}), 400
    if status not in ("draft", "submitted"):
        status = "submitted"

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO preprints (author_id, title, abstract, content, type, keywords, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, title, type, status, created_at""",
            (request.user_id, title, abstract, content, ptype, keywords, status),
        )
        row = dict(cur.fetchone())
        conn.commit()
        cur.close(); conn.close()
        row["created_at"] = str(row.get("created_at") or "")
        return jsonify(row), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@preprints_bp.route("/preprints/<int:preprint_id>", methods=["PUT"])
@token_required
def update_preprint(preprint_id):
    data = request.get_json() or {}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT author_id, status FROM preprints WHERE id=%s", (preprint_id,))
        preprint = cur.fetchone()
        if not preprint:
            cur.close(); conn.close()
            return jsonify({"error": "Pré-publicação não encontrada"}), 404
        if preprint["author_id"] != request.user_id:
            cur.close(); conn.close()
            return jsonify({"error": "Sem permissão para editar esta pré-publicação"}), 403

        title = (data.get("title") or "").strip()
        abstract = (data.get("abstract") or "").strip()
        content = (data.get("content") or "").strip()
        ptype = (data.get("type") or "").strip()
        keywords = (data.get("keywords") or "").strip()
        status = (data.get("status") or preprint["status"]).strip()

        if not title or not abstract or not content or ptype not in VALID_TYPES:
            cur.close(); conn.close()
            return jsonify({"error": "Dados inválidos"}), 400

        cur.execute(
            """UPDATE preprints SET title=%s, abstract=%s, content=%s, type=%s,
               keywords=%s, status=%s, updated_at=NOW()
               WHERE id=%s""",
            (title, abstract, content, ptype, keywords, status, preprint_id),
        )
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@preprints_bp.route("/preprints/<int:preprint_id>", methods=["DELETE"])
@token_required
def delete_preprint(preprint_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT author_id FROM preprints WHERE id=%s", (preprint_id,))
        preprint = cur.fetchone()
        if not preprint:
            cur.close(); conn.close()
            return jsonify({"error": "Pré-publicação não encontrada"}), 404
        if preprint["author_id"] != request.user_id:
            cur.close(); conn.close()
            return jsonify({"error": "Sem permissão"}), 403
        cur.execute("DELETE FROM preprint_reviews WHERE preprint_id=%s", (preprint_id,))
        cur.execute("DELETE FROM preprints WHERE id=%s", (preprint_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@preprints_bp.route("/preprints/<int:preprint_id>/reviews", methods=["POST"])
@token_required
def add_review(preprint_id):
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    rating = data.get("rating")

    if not content or len(content) < 10:
        return jsonify({"error": "Revisão deve ter ao menos 10 caracteres"}), 400

    try:
        rating_val = int(rating) if rating is not None else None
        if rating_val is not None and not (1 <= rating_val <= 5):
            return jsonify({"error": "Avaliação deve ser entre 1 e 5"}), 400
    except (ValueError, TypeError):
        rating_val = None

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, author_id, status FROM preprints WHERE id=%s", (preprint_id,))
        preprint = cur.fetchone()
        if not preprint:
            cur.close(); conn.close()
            return jsonify({"error": "Pré-publicação não encontrada"}), 404
        if preprint["author_id"] == request.user_id:
            cur.close(); conn.close()
            return jsonify({"error": "Você não pode revisar sua própria pré-publicação"}), 400

        cur.execute(
            """INSERT INTO preprint_reviews (preprint_id, user_id, content, rating)
               VALUES (%s, %s, %s, %s) RETURNING id, created_at""",
            (preprint_id, request.user_id, content, rating_val),
        )
        row = dict(cur.fetchone())
        conn.commit()
        cur.close(); conn.close()
        row["created_at"] = str(row.get("created_at") or "")
        return jsonify(row), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
