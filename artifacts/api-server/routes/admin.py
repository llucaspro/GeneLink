from flask import Blueprint, request, jsonify
from routes.auth import token_required
from db.connection import get_connection
from datetime import datetime, timezone
import os

admin_bp = Blueprint("admin", __name__)


def _require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT is_admin FROM users WHERE id=%s", (request.user_id,))
            user = cur.fetchone()
            cur.close(); conn.close()
            if not user or not user["is_admin"]:
                return jsonify({"error": "Admin access required"}), 403
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/admin/stats", methods=["GET"])
@token_required
@_require_admin
def admin_stats():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM users")
        users = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM institutions")
        institutions = cur.fetchone()["total"]
        try:
            cur.execute("SELECT COUNT(*) AS total FROM institutions WHERE is_verified=TRUE")
            verified_insts = cur.fetchone()["total"]
        except Exception:
            verified_insts = 0
        try:
            cur.execute("SELECT COUNT(*) AS total FROM users WHERE is_verified=TRUE")
            verified_users = cur.fetchone()["total"]
        except Exception:
            verified_users = 0
        cur.execute("SELECT COUNT(*) AS total FROM posts")
        posts = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM gene_searches")
        searches = cur.fetchone()["total"]
        try:
            cur.execute("SELECT COUNT(*) AS total FROM preprints")
            preprints = cur.fetchone()["total"]
        except Exception:
            preprints = 0
        cur.execute("SELECT COUNT(*) AS total FROM users WHERE created_at >= NOW() - INTERVAL '7 days'")
        new_users = cur.fetchone()["total"]
        cur.close(); conn.close()
        return jsonify({
            "users": users,
            "institutions": institutions,
            "verified_institutions": verified_insts,
            "verified_users": verified_users,
            "posts": posts,
            "gene_searches": searches,
            "preprints": preprints,
            "new_users": new_users,
        })
    except Exception as e:
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS total FROM users")
            users = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS total FROM institutions")
            institutions = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS total FROM posts")
            posts = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS total FROM gene_searches")
            searches = cur.fetchone()["total"]
            cur.close(); conn.close()
            return jsonify({
                "users": users,
                "institutions": institutions,
                "verified_institutions": 0,
                "verified_users": 0,
                "posts": posts,
                "gene_searches": searches,
                "preprints": 0,
                "new_users": 0,
            })
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500


@admin_bp.route("/admin/institutions", methods=["GET"])
@token_required
@_require_admin
def admin_list_institutions():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT i.*,
               (SELECT COUNT(*) FROM institution_members m WHERE m.institution_id = i.id) AS member_count,
               u.username AS creator_name
               FROM institutions i
               LEFT JOIN users u ON u.id = i.created_by
               ORDER BY i.created_at DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        for r in rows:
            for k in ('is_verified',):
                if k in r and isinstance(r[k], int):
                    r[k] = bool(r[k])
        return jsonify({"institutions": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/institutions/<int:inst_id>/verify", methods=["POST"])
@token_required
@_require_admin
def verify_institution(inst_id):
    data = request.get_json() or {}
    verified = bool(data.get("verified", True))
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, short_name, email FROM institutions WHERE id=%s", (inst_id,))
        inst = cur.fetchone()
        if not inst:
            cur.close(); conn.close()
            return jsonify({"error": "Institution not found"}), 404
        if verified:
            cur.execute(
                "UPDATE institutions SET is_verified=TRUE, verified_at=%s WHERE id=%s",
                (now, inst_id),
            )
        else:
            cur.execute(
                "UPDATE institutions SET is_verified=FALSE, verified_at=NULL WHERE id=%s",
                (inst_id,),
            )
        conn.commit()
        cur.close(); conn.close()

        # Send approval email notification
        if verified and inst.get("email"):
            try:
                from routes.email_utils import send_institution_approval_email
                base_url = os.environ.get("BASE_URL", "https://genelink.app")
                send_institution_approval_email(
                    inst_name=inst["name"],
                    inst_short=inst["short_name"] or inst["name"],
                    to_email=inst["email"],
                    login_url=f"{base_url}/login#instituicao",
                )
            except Exception as mail_err:
                print(f"[GeneLink] Email notification failed: {mail_err}")

        return jsonify({"ok": True, "verified": verified})
    except Exception as e:
        try:
            conn = get_connection()
            cur = conn.cursor()
            v = 1 if verified else 0
            vt = now if verified else None
            cur.execute(
                "UPDATE institutions SET is_verified=%s, verified_at=%s WHERE id=%s",
                (v, vt, inst_id),
            )
            conn.commit()
            cur.close(); conn.close()
            return jsonify({"ok": True, "verified": verified})
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500


@admin_bp.route("/admin/users", methods=["GET"])
@token_required
@_require_admin
def admin_list_users():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 30
    offset = (page - 1) * per_page
    search   = request.args.get("search", "").strip()
    verified = request.args.get("verified", "")
    only_admin = request.args.get("admin", "")
    try:
        conn = get_connection()
        cur = conn.cursor()
        conditions = []
        params = []
        if search:
            conditions.append("(username ILIKE %s OR email ILIKE %s)")
            params += [f"%{search}%", f"%{search}%"]
        if verified == "1":
            conditions.append("is_verified = TRUE")
        elif verified == "0":
            conditions.append("is_verified = FALSE")
        if only_admin == "1":
            conditions.append("is_admin = TRUE")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cur.execute(
            f"""SELECT id, username, email, full_name, institution, research_area,
                      is_verified, is_admin, created_at
               FROM users {where} ORDER BY created_at DESC LIMIT %s OFFSET %s""",
            params + [per_page, offset],
        )
        users = [dict(r) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) AS total FROM users {where}", params)
        total = cur.fetchone()["total"]
        cur.close(); conn.close()
        for u in users:
            u["created_at"] = str(u.get("created_at") or "")
            for k in ("is_verified", "is_admin"):
                if k in u and isinstance(u[k], int):
                    u[k] = bool(u[k])
        return jsonify({"users": users, "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users/<int:user_id>/verify", methods=["POST"])
@token_required
@_require_admin
def verify_user(user_id):
    data = request.get_json() or {}
    verified = bool(data.get("verified", True))
    try:
        conn = get_connection()
        cur = conn.cursor()
        v = True if verified else False
        try:
            cur.execute("UPDATE users SET is_verified=%s WHERE id=%s", (v, user_id))
        except Exception:
            cur.execute("UPDATE users SET is_verified=%s WHERE id=%s", (1 if verified else 0, user_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "verified": verified})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users/<int:user_id>/admin", methods=["POST"])
@token_required
@_require_admin
def set_admin(user_id):
    data = request.get_json() or {}
    is_admin = bool(data.get("admin", True))
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE users SET is_admin=%s WHERE id=%s", (is_admin, user_id))
        except Exception:
            cur.execute("UPDATE users SET is_admin=%s WHERE id=%s", (1 if is_admin else 0, user_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "admin": is_admin})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/institutions/<int:inst_id>", methods=["DELETE"])
@token_required
@_require_admin
def delete_institution(inst_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM institutions WHERE id=%s", (inst_id,))
        inst = cur.fetchone()
        if not inst:
            cur.close(); conn.close()
            return jsonify({"error": "Instituição não encontrada"}), 404
        cur.execute("DELETE FROM institution_members WHERE institution_id=%s", (inst_id,))
        cur.execute("DELETE FROM partnerships WHERE institution_id=%s", (inst_id,))
        cur.execute("DELETE FROM institutions WHERE id=%s", (inst_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "deleted": inst_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/posts", methods=["GET"])
@token_required
@_require_admin
def admin_list_posts():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 30
    offset = (page - 1) * per_page
    search = request.args.get("search", "").strip()
    try:
        conn = get_connection()
        cur = conn.cursor()
        conditions = []
        params = []
        if search:
            conditions.append("(p.title ILIKE %s OR u.username ILIKE %s)")
            params += [f"%{search}%", f"%{search}%"]
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cur.execute(
            f"""SELECT p.id, p.title, p.category, p.created_at,
                      u.username, u.id AS user_id,
                      (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count
               FROM posts p JOIN users u ON p.user_id = u.id
               {where}
               ORDER BY p.created_at DESC LIMIT %s OFFSET %s""",
            params + [per_page, offset],
        )
        posts = [dict(r) for r in cur.fetchall()]
        cur.execute(
            f"""SELECT COUNT(*) AS total FROM posts p JOIN users u ON p.user_id = u.id {where}""",
            params,
        )
        total = cur.fetchone()["total"]
        cur.close(); conn.close()
        for p in posts:
            p["created_at"] = str(p.get("created_at") or "")
        return jsonify({"posts": posts, "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/posts/<int:post_id>", methods=["DELETE"])
@token_required
@_require_admin
def delete_post(post_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM posts WHERE id=%s", (post_id,))
        post = cur.fetchone()
        if not post:
            cur.close(); conn.close()
            return jsonify({"error": "Post não encontrado"}), 404
        cur.execute("DELETE FROM comments WHERE post_id=%s", (post_id,))
        cur.execute("DELETE FROM posts WHERE id=%s", (post_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "deleted": post_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users/<int:user_id>", methods=["DELETE"])
@token_required
@_require_admin
def delete_user(user_id):
    if user_id == request.user_id:
        return jsonify({"error": "Você não pode excluir sua própria conta pelo painel admin"}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, is_admin FROM users WHERE id=%s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.close(); conn.close()
            return jsonify({"error": "Usuário não encontrado"}), 404
        cur.execute("DELETE FROM gene_searches WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM chat_messages WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM partnership_applications WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM institution_members WHERE user_id=%s", (user_id,))
        try:
            cur.execute("DELETE FROM preprint_reviews WHERE user_id=%s", (user_id,))
            cur.execute("DELETE FROM preprints WHERE author_id=%s", (user_id,))
        except Exception:
            pass
        cur.execute("DELETE FROM comments WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM posts WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "deleted": user_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/preprints", methods=["GET"])
@token_required
@_require_admin
def admin_list_preprints():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 30
    offset = (page - 1) * per_page
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT p.id, p.title, p.type, p.status, p.created_at,
                      u.username, u.id AS user_id,
                      (SELECT COUNT(*) FROM preprint_reviews r WHERE r.preprint_id = p.id) AS review_count
               FROM preprints p JOIN users u ON p.author_id = u.id
               ORDER BY p.created_at DESC LIMIT %s OFFSET %s""",
            (per_page, offset),
        )
        preprints = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) AS total FROM preprints")
        total = cur.fetchone()["total"]
        cur.close(); conn.close()
        for p in preprints:
            p["created_at"] = str(p.get("created_at") or "")
        return jsonify({"preprints": preprints, "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/preprints/<int:preprint_id>", methods=["DELETE"])
@token_required
@_require_admin
def admin_delete_preprint(preprint_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM preprints WHERE id=%s", (preprint_id,))
        preprint = cur.fetchone()
        if not preprint:
            cur.close(); conn.close()
            return jsonify({"error": "Pré-publicação não encontrada"}), 404
        cur.execute("DELETE FROM preprint_reviews WHERE preprint_id=%s", (preprint_id,))
        cur.execute("DELETE FROM preprints WHERE id=%s", (preprint_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "deleted": preprint_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/preprints/<int:preprint_id>/status", methods=["POST"])
@token_required
@_require_admin
def admin_set_preprint_status(preprint_id):
    data = request.get_json() or {}
    status = data.get("status", "")
    valid = {"draft", "submitted", "under_review", "published"}
    if status not in valid:
        return jsonify({"error": "Status inválido"}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE preprints SET status=%s WHERE id=%s", (status, preprint_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "status": status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/activity", methods=["GET"])
@token_required
@_require_admin
def admin_activity():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, email, created_at FROM users ORDER BY created_at DESC LIMIT 5"
        )
        recent_users = [dict(r) for r in cur.fetchall()]
        for r in recent_users:
            r["created_at"] = str(r.get("created_at") or "")

        cur.execute(
            """SELECT p.id, p.title, p.category, p.created_at, u.username
               FROM posts p JOIN users u ON p.user_id = u.id
               ORDER BY p.created_at DESC LIMIT 5"""
        )
        recent_posts = [dict(r) for r in cur.fetchall()]
        for r in recent_posts:
            r["created_at"] = str(r.get("created_at") or "")

        try:
            cur.execute(
                """SELECT p.id, p.title, p.type, p.created_at, u.username
                   FROM preprints p JOIN users u ON p.author_id = u.id
                   ORDER BY p.created_at DESC LIMIT 5"""
            )
            recent_preprints = [dict(r) for r in cur.fetchall()]
            for r in recent_preprints:
                r["created_at"] = str(r.get("created_at") or "")
        except Exception:
            recent_preprints = []

        cur.execute("SELECT COUNT(*) AS total FROM users WHERE created_at >= NOW() - INTERVAL '7 days'")
        try:
            new_users_week = cur.fetchone()["total"]
        except Exception:
            new_users_week = 0

        try:
            cur.execute("SELECT COUNT(*) AS total FROM preprints")
            total_preprints = cur.fetchone()["total"]
        except Exception:
            total_preprints = 0

        cur.close(); conn.close()
        return jsonify({
            "recent_users": recent_users,
            "recent_posts": recent_posts,
            "recent_preprints": recent_preprints,
            "new_users_week": new_users_week,
            "total_preprints": total_preprints,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@token_required
@_require_admin
def admin_reset_password(user_id):
    data = request.get_json() or {}
    new_password = data.get("password", "").strip()
    if len(new_password) < 6:
        return jsonify({"error": "A senha deve ter ao menos 6 caracteres"}), 400
    try:
        import bcrypt as _bcrypt
        hashed = _bcrypt.hashpw(new_password.encode(), _bcrypt.gensalt()).decode()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hashed, user_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
