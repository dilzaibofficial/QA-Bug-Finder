from flask import Blueprint, request, jsonify
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db

notifications_bp = Blueprint("notifications", __name__)


# ── GET /api/notifications?user_id=xxx&limit=20 ──────────────────────────────
# Polled every few seconds by the frontend bell for near-real-time updates.
@notifications_bp.route("", methods=["GET"])
def get_notifications():
    try:
        user_id = request.args.get("user_id")
        limit   = min(int(request.args.get("limit", 20)), 50)
        if not user_id:
            return jsonify({"notifications": [], "unread_count": 0}), 200

        db = get_db()
        items = list(
            db.notifications.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
        )

        # For invite notifications, always report the *current* status of the
        # underlying invite — not just this notification's read flag — so
        # Accept/Reject disappear for good once acted on, even if a poll
        # refetches this notification or a duplicate one exists.
        from bson import ObjectId
        for n in items:
            n["_id"] = str(n["_id"])
            if n.get("type") == "team_invite":
                invite_id = n.get("data", {}).get("invite_id")
                status = "pending"
                if invite_id:
                    try:
                        invite = db.team_invites.find_one({"_id": ObjectId(invite_id)})
                        if invite:
                            status = invite.get("status", "pending")
                    except Exception:
                        pass
                n.setdefault("data", {})["invite_status"] = status

        unread_count = db.notifications.count_documents({"user_id": user_id, "read": False})

        return jsonify({"notifications": items, "unread_count": unread_count}), 200

    except Exception as e:
        return jsonify({"error": str(e), "notifications": [], "unread_count": 0}), 500


# ── POST /api/notifications/<id>/read ────────────────────────────────────────
@notifications_bp.route("/<notif_id>/read", methods=["POST"])
def mark_read(notif_id):
    try:
        from bson import ObjectId
        db = get_db()
        db.notifications.update_one({"_id": ObjectId(notif_id)}, {"$set": {"read": True}})
        return jsonify({"message": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/notifications/read-all ─────────────────────────────────────────
@notifications_bp.route("/read-all", methods=["POST"])
def mark_all_read():
    try:
        data    = request.get_json() or {}
        user_id = data.get("user_id")
        db      = get_db()
        db.notifications.update_many({"user_id": user_id, "read": False}, {"$set": {"read": True}})
        return jsonify({"message": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
