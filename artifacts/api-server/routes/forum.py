from flask import Blueprint, request, jsonify
from routes.auth import token_required
from db.connection import get_connection
from security.middleware import sanitize_string

forum_bp = Blueprint("forum", __name__)


@forum_bp.route("/posts", methods=["GET"])
def get_posts():
    category = request.args.get("category", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    offset = (page - 1) * per_page

    try:
        conn = get_connection()
        cur = conn.cursor()
        if category:
            cur.execute(
                """SELECT p.id, p.title, p.content, p.category, p.created_at, p.updated_at,
                          u.username, u.avatar_initials, u.institution,
                          (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count
                   FROM posts p JOIN users u ON p.user_id = u.id
                   WHERE p.category = %s
                   ORDER BY p.created_at DESC LIMIT %s OFFSET %s""",
                (category, per_page, offset),
            )
        else:
            cur.execute(
                """SELECT p.id, p.title, p.content, p.category, p.created_at, p.updated_at,
                          u.username, u.avatar_initials, u.institution,
                          (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count
                   FROM posts p JOIN users u ON p.user_id = u.id
                   ORDER BY p.created_at DESC LIMIT %s OFFSET %s""",
                (per_page, offset),
            )
        rows = cur.fetchall()
        if category:
            cur.execute("SELECT COUNT(*) AS total FROM posts WHERE category=%s", (category,))
        else:
            cur.execute("SELECT COUNT(*) AS total FROM posts")
        total = cur.fetchone()["total"]
        cur.close()
        conn.close()
        return jsonify({"posts": [dict(r) for r in rows], "total": total, "page": page})
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


@forum_bp.route("/posts/<int:post_id>", methods=["GET"])
def get_post(post_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT p.id, p.title, p.content, p.category, p.created_at, p.updated_at,
                      u.id AS author_id, u.username, u.avatar_initials, u.institution, u.research_area
               FROM posts p JOIN users u ON p.user_id = u.id
               WHERE p.id = %s""",
            (post_id,),
        )
        post = cur.fetchone()
        if not post:
            cur.close()
            conn.close()
            return jsonify({"error": "Post not found"}), 404
        cur.execute(
            """SELECT c.id, c.content, c.created_at, u.username, u.avatar_initials, u.institution
               FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.post_id = %s ORDER BY c.created_at ASC""",
            (post_id,),
        )
        comments = cur.fetchall()
        cur.close()
        conn.close()
        result = dict(post)
        result["comments"] = [dict(c) for c in comments]
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


@forum_bp.route("/posts", methods=["POST"])
@token_required
def create_post():
    data = request.get_json()
    title = sanitize_string((data.get("title") or "").strip(), max_len=500)
    content = sanitize_string((data.get("content") or "").strip(), max_len=5000)
    category = (data.get("category") or "General").strip()

    if not title or not content:
        return jsonify({"error": "Title and content are required"}), 400
    if len(title) > 500:
        return jsonify({"error": "Title too long (max 500 chars)"}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO posts (user_id, title, content, category)
               VALUES (%s, %s, %s, %s)
               RETURNING id, title, category, created_at""",
            (request.user_id, title, content, category),
        )
        post = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(dict(post)), 201
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


@forum_bp.route("/posts/<int:post_id>/comments", methods=["POST"])
@token_required
def add_comment(post_id):
    data = request.get_json()
    content = sanitize_string((data.get("content") or "").strip(), max_len=5000)
    if not content:
        return jsonify({"error": "Comment content is required"}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM posts WHERE id = %s", (post_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"error": "Post not found"}), 404
        cur.execute(
            """INSERT INTO comments (post_id, user_id, content)
               VALUES (%s, %s, %s)
               RETURNING id, content, created_at""",
            (post_id, request.user_id, content),
        )
        comment = cur.fetchone()
        cur.execute("SELECT username, avatar_initials FROM users WHERE id=%s", (request.user_id,))
        user = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        result = dict(comment)
        result.update(dict(user))
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


@forum_bp.route("/posts/<int:post_id>", methods=["DELETE"])
@token_required
def delete_post(post_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM posts WHERE id=%s", (post_id,))
        post = cur.fetchone()
        if not post:
            cur.close()
            conn.close()
            return jsonify({"error": "Post not found"}), 404
        if post["user_id"] != request.user_id:
            cur.close()
            conn.close()
            return jsonify({"error": "Not authorized to delete this post"}), 403
        cur.execute("DELETE FROM posts WHERE id=%s", (post_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Post deleted"})
    except Exception as e:
        return jsonify({"error": "Erro interno. Tente novamente."}), 500


@forum_bp.route("/categories", methods=["GET"])
def get_categories():
    return jsonify([
        "Geral",
        "Genômica",
        "Proteômica",
        "Bioinformática",
        "Genética Clínica",
        "Biologia do Câncer",
        "Epigenética",
        "Biologia Estrutural",
        "Neurociência",
        "Imunologia",
    ])
