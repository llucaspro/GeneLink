"""
Admin routes — protected by token_required + _require_admin.
All DB interactions use parameterized queries.
Error responses never expose internal exception details.
"""

import os
import logging
import threading
from flask import Blueprint, request, jsonify
from routes.auth import token_required
from db.connection import get_connection
from datetime import datetime, timezone

_log = logging.getLogger("genelink.admin")

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
        except Exception:
            return jsonify({"error": "Authorization check failed"}), 500
        return f(*args, **kwargs)
    return decorated


# ── Stats ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/stats", methods=["GET"])
@token_required
@_require_admin
def admin_stats():
    try:
        conn = get_connection()
        cur = conn.cursor()

        def _count(query, params=()):
            cur.execute(query, params)
            row = cur.fetchone()
            return row["total"] if row else 0

        users = _count("SELECT COUNT(*) AS total FROM users")
        institutions = _count("SELECT COUNT(*) AS total FROM institutions")
        verified_insts = _count("SELECT COUNT(*) AS total FROM institutions WHERE is_verified=TRUE")
        verified_users = _count("SELECT COUNT(*) AS total FROM users WHERE is_verified=TRUE")
        posts = _count("SELECT COUNT(*) AS total FROM posts")
        searches = _count("SELECT COUNT(*) AS total FROM gene_searches")
        new_users = _count(
            "SELECT COUNT(*) AS total FROM users WHERE created_at >= NOW() - INTERVAL '7 days'"
        )
        preprints = 0
        try:
            preprints = _count("SELECT COUNT(*) AS total FROM preprints")
        except Exception:
            pass

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
    except Exception:
        _log.exception("admin_stats error")
        return jsonify({"error": "Could not load stats"}), 500


# ── Institutions ──────────────────────────────────────────────────────────────

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
            if "is_verified" in r and isinstance(r["is_verified"], int):
                r["is_verified"] = bool(r["is_verified"])
        return jsonify({"institutions": rows})
    except Exception:
        _log.exception("admin_list_institutions error")
        return jsonify({"error": "Could not load institutions"}), 500


@admin_bp.route("/admin/institutions/<int:inst_id>/verify", methods=["POST"])
@token_required
@_require_admin
def verify_institution(inst_id):
    data = request.get_json(silent=True) or {}
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

        # ── Send approval e-mail in background thread ──────────────────────────
        if verified and inst.get("email"):
            base_url = os.environ.get("BASE_URL", "https://genelink-fcz4.onrender.com")
            inst_name  = inst["name"]
            inst_short = inst["short_name"] or inst["name"]
            to_email   = inst["email"]
            login_url  = f"{base_url}/login#instituicao"
            try:
                from routes.email_utils import send_institution_approval_email
                threading.Thread(
                    target=send_institution_approval_email,
                    kwargs={
                        "inst_name" : inst_name,
                        "inst_short": inst_short,
                        "to_email"  : to_email,
                        "login_url" : login_url,
                    },
                    daemon=True,
                ).start()
                _log.info(
                    "Approval email queued for institution %d ('%s') -> %s",
                    inst_id, inst_name, to_email,
                )
            except Exception:
                _log.exception(
                    "Failed to queue approval email for institution %d ('%s')",
                    inst_id, inst_name,
                )

        return jsonify({"ok": True, "verified": verified})
    except Exception:
        _log.exception("verify_institution error id=%d", inst_id)
        return jsonify({"error": "Could not update institution"}), 500


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/users", methods=["GET"])
@token_required
@_require_admin
def admin_list_users():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 30
    offset = (page - 1) * per_page
    search = (request.args.get("search") or "").strip()[:100]
    verified = request.args.get("verified", "")
    only_admin = request.args.get("admin", "")

    try:
        conn = get_connection()
        cur = conn.cursor()

        # Build parameterized WHERE — no raw user input is ever interpolated into SQL
        conditions: list[str] = []
        params: list = []
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
            "SELECT id, username, email, full_name, institution, research_area, "
            f"is_verified, is_admin, created_at FROM users {where} "
            "ORDER BY created_at DESC LIMIT %s OFFSET %s",
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
    except Exception:
        _log.exception("admin_list_users error")
        return jsonify({"error": "Could not load users"}), 500


@admin_bp.route("/admin/users/<int:user_id>/verify", methods=["POST"])
@token_required
@_require_admin
def verify_user(user_id):
    data = request.get_json(silent=True) or {}
    verified = bool(data.get("verified", True))
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_verified=%s WHERE id=%s", (verified, user_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "verified": verified})
    except Exception:
        _log.exception("verify_user error id=%d", user_id)
        return jsonify({"error": "Could not update user"}), 500


@admin_bp.route("/admin/users/<int:user_id>/admin", methods=["POST"])
@token_required
@_require_admin
def set_admin(user_id):
    data = request.get_json(silent=True) or {}
    is_admin = bool(data.get("admin", True))
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_admin=%s WHERE id=%s", (is_admin, user_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "admin": is_admin})
    except Exception:
        _log.exception("set_admin error id=%d", user_id)
        return jsonify({"error": "Could not update user"}), 500


@admin_bp.route("/admin/users/<int:user_id>", methods=["DELETE"])
@token_required
@_require_admin
def delete_user(user_id):
    if user_id == request.user_id:
        return jsonify({"error": "Cannot delete your own account via admin panel"}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username FROM users WHERE id=%s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.close(); conn.close()
            return jsonify({"error": "User not found"}), 404
        for stmt in [
            "DELETE FROM gene_searches WHERE user_id=%s",
            "DELETE FROM chat_messages WHERE user_id=%s",
            "DELETE FROM partnership_applications WHERE user_id=%s",
            "DELETE FROM institution_members WHERE user_id=%s",
            "DELETE FROM comments WHERE user_id=%s",
            "DELETE FROM posts WHERE user_id=%s",
        ]:
            cur.execute(stmt, (user_id,))
        for stmt in [
            "DELETE FROM preprint_reviews WHERE user_id=%s",
            "DELETE FROM preprints WHERE author_id=%s",
        ]:
            try:
                cur.execute(stmt, (user_id,))
            except Exception:
                pass
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        cur.close(); conn.close()
        _log.info("Admin %d deleted user %d (%s)", request.user_id, user_id, user["username"])
        return jsonify({"ok": True, "deleted": user_id})
    except Exception:
        _log.exception("delete_user error id=%d", user_id)
        return jsonify({"error": "Could not delete user"}), 500


@admin_bp.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@token_required
@_require_admin
def admin_reset_password(user_id):
    data = request.get_json(silent=True) or {}
    new_password = (data.get("password") or "").strip()
    if len(new_password) < 12:
        return jsonify({"error": "Password must be at least 12 characters"}), 400
    if len(new_password) > 128:
        return jsonify({"error": "Password too long"}), 400
    try:
        import bcrypt as _bcrypt
        hashed = _bcrypt.hashpw(new_password.encode(), _bcrypt.gensalt()).decode()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hashed, user_id))
        conn.commit()
        cur.close(); conn.close()
        _log.info("Admin %d reset password for user %d", request.user_id, user_id)
        return jsonify({"ok": True})
    except Exception:
        _log.exception("admin_reset_password error id=%d", user_id)
        return jsonify({"error": "Could not reset password"}), 500


# ── Institutions (delete) ─────────────────────────────────────────────────────

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
            return jsonify({"error": "Institution not found"}), 404
        for stmt in [
            "DELETE FROM institution_members WHERE institution_id=%s",
            "DELETE FROM partnerships WHERE institution_id=%s",
            "DELETE FROM institutions WHERE id=%s",
        ]:
            cur.execute(stmt, (inst_id,))
        conn.commit()
        cur.close(); conn.close()
        _log.info("Admin %d deleted institution %d", request.user_id, inst_id)
        return jsonify({"ok": True, "deleted": inst_id})
    except Exception:
        _log.exception("delete_institution error id=%d", inst_id)
        return jsonify({"error": "Could not delete institution"}), 500


# ── Posts ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/posts", methods=["GET"])
@token_required
@_require_admin
def admin_list_posts():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 30
    offset = (page - 1) * per_page
    search = (request.args.get("search") or "").strip()[:100]

    try:
        conn = get_connection()
        cur = conn.cursor()
        conditions: list[str] = []
        params: list = []
        if search:
            conditions.append("(p.title ILIKE %s OR u.username ILIKE %s)")
            params += [f"%{search}%", f"%{search}%"]
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        cur.execute(
            "SELECT p.id, p.title, p.category, p.created_at, "
            "u.username, u.id AS user_id, "
            "(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count "
            f"FROM posts p JOIN users u ON p.user_id = u.id {where} "
            "ORDER BY p.created_at DESC LIMIT %s OFFSET %s",
            params + [per_page, offset],
        )
        posts = [dict(r) for r in cur.fetchall()]

        cur.execute(
            f"SELECT COUNT(*) AS total FROM posts p JOIN users u ON p.user_id = u.id {where}",
            params,
        )
        total = cur.fetchone()["total"]
        cur.close(); conn.close()

        for p in posts:
            p["created_at"] = str(p.get("created_at") or "")
        return jsonify({"posts": posts, "total": total})
    except Exception:
        _log.exception("admin_list_posts error")
        return jsonify({"error": "Could not load posts"}), 500


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
            return jsonify({"error": "Post not found"}), 404
        cur.execute("DELETE FROM comments WHERE post_id=%s", (post_id,))
        cur.execute("DELETE FROM posts WHERE id=%s", (post_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "deleted": post_id})
    except Exception:
        _log.exception("delete_post error id=%d", post_id)
        return jsonify({"error": "Could not delete post"}), 500


# ── Preprints ─────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/preprints", methods=["GET"])
@token_required
@_require_admin
def admin_list_preprints():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
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
    except Exception:
        _log.exception("admin_list_preprints error")
        return jsonify({"error": "Could not load preprints"}), 500


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
            return jsonify({"error": "Preprint not found"}), 404
        cur.execute("DELETE FROM preprint_reviews WHERE preprint_id=%s", (preprint_id,))
        cur.execute("DELETE FROM preprints WHERE id=%s", (preprint_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "deleted": preprint_id})
    except Exception:
        _log.exception("admin_delete_preprint error id=%d", preprint_id)
        return jsonify({"error": "Could not delete preprint"}), 500


@admin_bp.route("/admin/preprints/<int:preprint_id>/status", methods=["POST"])
@token_required
@_require_admin
def admin_set_preprint_status(preprint_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status", "")
    valid = {"draft", "submitted", "under_review", "published"}
    if status not in valid:
        return jsonify({"error": "Invalid status"}), 400
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE preprints SET status=%s WHERE id=%s", (status, preprint_id))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"ok": True, "status": status})
    except Exception:
        _log.exception("admin_set_preprint_status error id=%d", preprint_id)
        return jsonify({"error": "Could not update status"}), 500


# ── Activity Feed ─────────────────────────────────────────────────────────────

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

        recent_preprints: list = []
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
            pass

        cur.execute(
            "SELECT COUNT(*) AS total FROM users WHERE created_at >= NOW() - INTERVAL '7 days'"
        )
        new_users_week = cur.fetchone()["total"] or 0

        total_preprints = 0
        try:
            cur.execute("SELECT COUNT(*) AS total FROM preprints")
            total_preprints = cur.fetchone()["total"] or 0
        except Exception:
            pass

        cur.close(); conn.close()
        return jsonify({
            "recent_users": recent_users,
            "recent_posts": recent_posts,
            "recent_preprints": recent_preprints,
            "new_users_week": new_users_week,
            "total_preprints": total_preprints,
        })
    except Exception:
        _log.exception("admin_activity error")
        return jsonify({"error": "Could not load activity"}), 500
