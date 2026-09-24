from flask import Blueprint, request, jsonify, send_file
from datetime import datetime, timedelta
from pathlib import Path
import sys, os, bcrypt, shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, is_user_verified, push_notification
from socketio_instance import socketio
import config

admin_bp = Blueprint("admin", __name__)

PLANS = {
    "3m" : {"key": "3m",  "label": "3 Months", "months": 3,  "usd": 20,  "pkr": 5500},
    "6m" : {"key": "6m",  "label": "6 Months", "months": 6,  "usd": 40,  "pkr": 11000},
    "12m": {"key": "12m", "label": "1 Year",   "months": 12, "usd": 100, "pkr": 28000},
}


def _oid(id_str):
    from bson import ObjectId
    return ObjectId(id_str)


def _user_or_none(db, user_id):
    try:
        return db.users.find_one({"_id": _oid(user_id)})
    except Exception:
        return None


def _require_admin(db):
    """Every admin route is gated on this. Returns (admin_user, None) or (None, error_response)."""
    admin_id = request.args.get("admin_id") or (request.get_json(silent=True) or {}).get("admin_id")
    admin = _user_or_none(db, admin_id) if admin_id else None
    if not admin or not admin.get("is_admin"):
        return None, (jsonify({"error": "Admin access required"}), 403)
    return admin, None


def _public_user(db, u):
    uid = str(u["_id"])
    return {
        "id"         : uid,
        "name"       : u.get("name", ""),
        "email"      : u.get("email", ""),
        "role"       : u.get("role", "QA Engineer"),
        "avatar_url" : u.get("avatar_url", ""),
        "is_admin"   : bool(u.get("is_admin", False)),
        "is_verified": is_user_verified(db, uid),
        "created_at" : u.get("created_at", ""),
        "team_count" : db.team_memberships.count_documents({"user_id": uid}),
        "upload_count": db.uploads.count_documents({"user_id": uid}),
    }


# ── POST /api/admin/login ──────────────────────────────────────────────────
@admin_bp.route("/login", methods=["POST"])
def admin_login():
    try:
        data     = request.get_json() or {}
        email    = (data.get("email", "") or "").strip().lower()
        password = data.get("password", "") or ""

        db   = get_db()
        user = db.users.find_one({"email": email})
        if not user or not bcrypt.checkpw(password.encode(), user["password"].encode()):
            return jsonify({"error": "Invalid email or password"}), 401
        if not user.get("is_admin"):
            return jsonify({"error": "This account does not have admin access"}), 403

        return jsonify({
            "id"   : str(user["_id"]),
            "name" : user.get("name", ""),
            "email": user.get("email", ""),
            "avatar_url": user.get("avatar_url", ""),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/admin/stats?admin_id= ─────────────────────────────────────────
@admin_bp.route("/stats", methods=["GET"])
def admin_stats():
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        total_users   = db.users.count_documents({})
        total_teams   = db.teams.count_documents({})
        total_uploads = db.uploads.count_documents({})
        total_bugs    = db.bugs.count_documents({})
        total_messages = db.chat_messages.count_documents({})

        active_subs = list(db.subscriptions.find({"status": "active"}))
        # self-heal any that lapsed since last check, same rule as is_user_verified
        now_iso = datetime.utcnow().isoformat()
        active_subs = [s for s in active_subs if s.get("expires_at", "") >= now_iso]

        revenue_by_currency = {}
        for s in db.subscriptions.find({"status": {"$in": ["active", "expired"]}}):
            cur = s.get("currency", "usd")
            revenue_by_currency[cur] = revenue_by_currency.get(cur, 0) + s.get("amount", 0)

        # signups over the last 14 days, for a small chart
        signups_by_day = {}
        since = datetime.utcnow() - timedelta(days=14)
        for u in db.users.find({}, {"created_at": 1}):
            c = u.get("created_at", "")
            if not c:
                continue
            try:
                d = datetime.fromisoformat(c)
            except Exception:
                continue
            if d < since:
                continue
            key = d.strftime("%Y-%m-%d")
            signups_by_day[key] = signups_by_day.get(key, 0) + 1

        return jsonify({
            "total_users"        : total_users,
            "total_teams"        : total_teams,
            "total_uploads"      : total_uploads,
            "total_bugs"         : total_bugs,
            "total_messages"     : total_messages,
            "active_subscriptions": len(active_subs),
            "revenue_by_currency": revenue_by_currency,
            "signups_by_day"     : signups_by_day,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════════════════════

@admin_bp.route("/users", methods=["GET"])
def list_users():
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        search = (request.args.get("search", "") or "").strip()
        page   = max(1, int(request.args.get("page", 1)))
        limit  = min(100, int(request.args.get("limit", 25)))

        query = {}
        if search:
            query = {"$or": [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
            ]}

        total = db.users.count_documents(query)
        users = list(db.users.find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit))
        return jsonify({"users": [_public_user(db, u) for u in users], "total": total, "page": page, "limit": limit}), 200

    except Exception as e:
        return jsonify({"error": str(e), "users": [], "total": 0}), 500


@admin_bp.route("/users/<user_id>", methods=["GET"])
def get_user(user_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        user = _user_or_none(db, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        teams = []
        for m in db.team_memberships.find({"user_id": user_id}):
            t = db.teams.find_one({"_id": _oid(m["team_id"])}) if m.get("team_id") else None
            teams.append({"id": m["team_id"], "name": m.get("team_name", ""), "role": m.get("role", ""),
                          "owner_id": t.get("owner_id", "") if t else ""})

        subs = list(db.subscriptions.find({"user_id": user_id}).sort("started_at", -1))
        for s in subs:
            s["_id"] = str(s["_id"])

        return jsonify({"user": _public_user(db, user), "teams": teams, "subscriptions": subs}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users", methods=["POST"])
def create_user():
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        data     = request.get_json() or {}
        name     = (data.get("name", "") or "").strip()
        email    = (data.get("email", "") or "").strip().lower()
        password = data.get("password", "") or ""
        is_admin = bool(data.get("is_admin", False))

        if not name or not email or not password:
            return jsonify({"error": "name, email and password are required"}), 400
        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400
        if db.users.find_one({"email": email}):
            return jsonify({"error": "Email already registered"}), 409

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        result = db.users.insert_one({
            "name": name, "email": email, "password": hashed,
            "role": data.get("role", "QA Engineer") or "QA Engineer",
            "is_admin": is_admin,
            "created_at": datetime.utcnow().isoformat(),
        })
        return jsonify({"id": str(result.inserted_id)}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users/<user_id>", methods=["PUT"])
def update_user(user_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        user = _user_or_none(db, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json() or {}
        updates = {}
        for field in ("name", "role"):
            if field in data:
                updates[field] = (data[field] or "").strip()
        if "email" in data:
            new_email = (data["email"] or "").strip().lower()
            if new_email != user.get("email") and db.users.find_one({"email": new_email}):
                return jsonify({"error": "Email already in use"}), 409
            updates["email"] = new_email
        if "is_admin" in data:
            updates["is_admin"] = bool(data["is_admin"])
        if "password" in data and data["password"]:
            if len(data["password"]) < 6:
                return jsonify({"error": "Password must be at least 6 characters"}), 400
            updates["password"] = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()

        if updates:
            db.users.update_one({"_id": _oid(user_id)}, {"$set": updates})

        return jsonify({"message": "User updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users/<user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        db = get_db()
        admin, err = _require_admin(db)
        if err: return err
        if admin and str(admin["_id"]) == user_id:
            return jsonify({"error": "You can't delete your own admin account"}), 400

        user = _user_or_none(db, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        if db.teams.count_documents({"owner_id": user_id}) > 0:
            return jsonify({"error": "This user owns one or more projects — disband those projects first"}), 409

        db.users.delete_one({"_id": _oid(user_id)})
        db.team_memberships.delete_many({"user_id": user_id})
        db.subscriptions.delete_many({"user_id": user_id})
        db.notifications.delete_many({"user_id": user_id})
        # Personal-scope data only — team-scoped records stay with the team.
        db.uploads.delete_many({"user_id": user_id, "team_id": None})
        db.history.delete_many({"user_id": user_id, "team_id": None})
        db.analysis.delete_many({"user_id": user_id, "team_id": None})
        db.notes.delete_many({"scope_key": f"personal:{user_id}"})

        # If this user is currently online, kick them out in real time —
        # their account no longer exists.
        socketio.emit("force_logout", {"reason": "account_deleted"}, room=f"user:{user_id}")

        return jsonify({"message": "User deleted"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
#  TEAMS
# ═══════════════════════════════════════════════════════════════════════════

@admin_bp.route("/teams", methods=["GET"])
def list_teams():
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        search = (request.args.get("search", "") or "").strip()
        query = {"name": {"$regex": search, "$options": "i"}} if search else {}

        teams = []
        for t in db.teams.find(query).sort("created_at", -1):
            tid = str(t["_id"])
            owner = _user_or_none(db, t.get("owner_id", ""))
            teams.append({
                "id"          : tid,
                "name"        : t.get("name", ""),
                "owner_id"    : t.get("owner_id", ""),
                "owner_name"  : owner.get("name", "Unknown") if owner else "Unknown",
                "created_at"  : t.get("created_at", ""),
                "member_count": db.team_memberships.count_documents({"team_id": tid}),
                "upload_count": db.uploads.count_documents({"team_id": tid}),
            })

        return jsonify({"teams": teams, "total": len(teams)}), 200

    except Exception as e:
        return jsonify({"error": str(e), "teams": []}), 500


@admin_bp.route("/teams/<team_id>", methods=["GET"])
def get_team(team_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        team = db.teams.find_one({"_id": _oid(team_id)})
        if not team:
            return jsonify({"error": "Team not found"}), 404

        members = []
        for m in db.team_memberships.find({"team_id": team_id}):
            u = _user_or_none(db, m["user_id"])
            members.append({
                "id": m["user_id"], "name": u.get("name", "Unknown") if u else "Unknown",
                "email": u.get("email", "") if u else "", "role": m.get("role", ""),
                "avatar_url": u.get("avatar_url", "") if u else "",
            })

        return jsonify({
            "team": {
                "id": team_id, "name": team.get("name", ""), "owner_id": team.get("owner_id", ""),
                "created_at": team.get("created_at", ""), "members": members,
                "upload_count": db.uploads.count_documents({"team_id": team_id}),
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/teams/<team_id>", methods=["PUT"])
def update_team(team_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        data = request.get_json() or {}
        name = (data.get("name", "") or "").strip()
        if not name:
            return jsonify({"error": "name is required"}), 400

        result = db.teams.update_one({"_id": _oid(team_id)}, {"$set": {"name": name}})
        if result.matched_count == 0:
            return jsonify({"error": "Team not found"}), 404
        db.team_memberships.update_many({"team_id": team_id}, {"$set": {"team_name": name}})

        return jsonify({"message": "Team updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/teams/<team_id>", methods=["DELETE"])
def delete_team(team_id):
    """Disband — same rule as a normal owner leaving: every member's data for
    this team reverts to personal so nothing is silently lost."""
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        team = db.teams.find_one({"_id": _oid(team_id)})
        if not team:
            return jsonify({"error": "Team not found"}), 404

        for m in db.team_memberships.find({"team_id": team_id}):
            push_notification(
                db, m["user_id"], "team_disbanded", "Team Disbanded",
                f"\"{team.get('name','')}\" was disbanded by an admin. Your data from this project is now personal.",
                {"team_id": team_id},
            )

        db.team_memberships.delete_many({"team_id": team_id})
        db.teams.delete_one({"_id": _oid(team_id)})
        db.uploads.update_many({"team_id": team_id}, {"$set": {"team_id": None}})
        db.history.update_many({"team_id": team_id}, {"$set": {"team_id": None}})
        db.analysis.update_many({"team_id": team_id}, {"$set": {"team_id": None}})
        db.notes.update_many({"scope_key": f"team:{team_id}"}, {"$set": {"scope_key": f"personal:{team.get('owner_id','')}"}})

        return jsonify({"message": "Team disbanded"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
#  SUBSCRIPTIONS / PAYMENTS (Bug Plus)
# ═══════════════════════════════════════════════════════════════════════════

@admin_bp.route("/subscriptions", methods=["GET"])
def list_subscriptions():
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        status = request.args.get("status", "")
        query = {"status": status} if status else {}

        subs = []
        for s in db.subscriptions.find(query).sort("started_at", -1):
            u = _user_or_none(db, s.get("user_id", ""))
            subs.append({
                "id"        : str(s["_id"]),
                "user_id"   : s.get("user_id", ""),
                "user_name" : u.get("name", "Unknown") if u else "Unknown",
                "user_email": u.get("email", "") if u else "",
                "plan"      : s.get("plan", ""),
                "currency"  : s.get("currency", ""),
                "amount"    : s.get("amount", 0),
                "status"    : s.get("status", ""),
                "started_at": s.get("started_at", ""),
                "expires_at": s.get("expires_at", ""),
                "stripe_session_id": s.get("stripe_session_id", ""),
            })

        return jsonify({"subscriptions": subs, "total": len(subs)}), 200

    except Exception as e:
        return jsonify({"error": str(e), "subscriptions": []}), 500


@admin_bp.route("/subscriptions", methods=["POST"])
def grant_subscription():
    """Admin manually grants Bug Plus — e.g. a support gesture or promo, no payment."""
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        data     = request.get_json() or {}
        user_id  = data.get("user_id")
        plan_key = data.get("plan", "3m")

        user = _user_or_none(db, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if plan_key not in PLANS:
            return jsonify({"error": "Invalid plan"}), 400

        plan = PLANS[plan_key]
        now = datetime.utcnow()
        expires = now + timedelta(days=30 * plan["months"])

        db.subscriptions.insert_one({
            "user_id": user_id, "plan": plan_key, "currency": "usd", "amount": 0,
            "stripe_session_id": None, "started_at": now.isoformat(), "expires_at": expires.isoformat(),
            "status": "active", "granted_by_admin": True,
        })
        db.users.update_one({"_id": _oid(user_id)}, {"$set": {"is_verified": True}})
        push_notification(db, user_id, "subscription_granted", "Bug Plus Activated",
                          f"An admin granted you Bug Plus ({plan['label']}).", {})

        return jsonify({"message": "Subscription granted", "expires_at": expires.isoformat()}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/subscriptions/<sub_id>", methods=["PUT"])
def update_subscription(sub_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        sub = db.subscriptions.find_one({"_id": _oid(sub_id)})
        if not sub:
            return jsonify({"error": "Subscription not found"}), 404

        data = request.get_json() or {}
        updates = {}
        if "status" in data and data["status"] in ("active", "expired", "cancelled"):
            updates["status"] = data["status"]
        if "expires_at" in data and data["expires_at"]:
            updates["expires_at"] = data["expires_at"]

        if updates:
            db.subscriptions.update_one({"_id": _oid(sub_id)}, {"$set": updates})
            if updates.get("status") == "active":
                db.users.update_one({"_id": _oid(sub["user_id"])}, {"$set": {"is_verified": True}})
            elif updates.get("status") in ("expired", "cancelled"):
                db.users.update_one({"_id": _oid(sub["user_id"])}, {"$set": {"is_verified": False}})

        return jsonify({"message": "Subscription updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/subscriptions/<sub_id>", methods=["DELETE"])
def delete_subscription(sub_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        sub = db.subscriptions.find_one({"_id": _oid(sub_id)})
        if not sub:
            return jsonify({"error": "Subscription not found"}), 404

        db.subscriptions.delete_one({"_id": _oid(sub_id)})
        # Re-check verification in case another active subscription still covers them.
        if not is_user_verified(db, sub["user_id"]):
            db.users.update_one({"_id": _oid(sub["user_id"])}, {"$set": {"is_verified": False}})

        return jsonify({"message": "Subscription removed"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
#  CHAT MODERATION
# ═══════════════════════════════════════════════════════════════════════════

@admin_bp.route("/channels", methods=["GET"])
def list_channels():
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        channels = []
        for c in db.channels.find({}).sort("created_at", -1):
            cid = c["_id"]
            channels.append({
                "id": cid, "type": c.get("type", ""), "name": c.get("name", ""),
                "created_at": c.get("created_at", ""),
                "message_count": db.chat_messages.count_documents({"channel_id": cid}),
            })

        return jsonify({"channels": channels}), 200

    except Exception as e:
        return jsonify({"error": str(e), "channels": []}), 500


@admin_bp.route("/channels/<path:channel_id>", methods=["DELETE"])
def delete_channel(channel_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err
        if channel_id == "public":
            return jsonify({"error": "The Public Channel can't be deleted"}), 400

        db.channels.delete_one({"_id": channel_id})
        db.chat_messages.delete_many({"channel_id": channel_id})
        return jsonify({"message": "Channel deleted"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/messages", methods=["GET"])
def list_messages():
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        channel_id = request.args.get("channel_id", "")
        limit = min(200, int(request.args.get("limit", 100)))
        query = {"channel_id": channel_id} if channel_id else {}

        msgs = list(db.chat_messages.find(query).sort("created_at", -1).limit(limit))
        for m in msgs:
            m["_id"] = str(m["_id"])

        return jsonify({"messages": msgs}), 200

    except Exception as e:
        return jsonify({"error": str(e), "messages": []}), 500


@admin_bp.route("/messages/<message_id>", methods=["DELETE"])
def delete_message(message_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        result = db.chat_messages.delete_one({"_id": _oid(message_id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Message not found"}), 404

        return jsonify({"message": "Message deleted"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
#  FILES / UPLOADS
# ═══════════════════════════════════════════════════════════════════════════

@admin_bp.route("/uploads", methods=["GET"])
def list_uploads():
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        search = (request.args.get("search", "") or "").strip()
        page   = max(1, int(request.args.get("page", 1)))
        limit  = min(100, int(request.args.get("limit", 25)))

        query = {"filename": {"$regex": search, "$options": "i"}} if search else {}
        total = db.uploads.count_documents(query)

        uploads = []
        for u in db.uploads.find(query).sort("upload_date", -1).skip((page - 1) * limit).limit(limit):
            owner = _user_or_none(db, u.get("user_id", ""))
            analysis = db.analysis.find_one({"_id": u.get("analysis_id")}) if u.get("analysis_id") else None
            team = db.teams.find_one({"_id": _oid(u["team_id"])}) if u.get("team_id") else None
            uploads.append({
                "id"          : str(u["_id"]),
                "filename"    : u.get("filename", ""),
                "file_type"   : u.get("file_type", ""),
                "file_size"   : u.get("file_size", 0),
                "upload_date" : u.get("upload_date", ""),
                "owner_name"  : owner.get("name", "Unknown") if owner else "Unknown",
                "owner_email" : owner.get("email", "") if owner else "",
                "team_name"   : team.get("name", "") if team else "",
                "total_bugs"  : analysis.get("total_bugs", 0) if analysis else 0,
                "critical_bugs": analysis.get("critical_bugs", 0) if analysis else 0,
                "status"      : analysis.get("status", "") if analysis else "",
            })

        return jsonify({"uploads": uploads, "total": total, "page": page, "limit": limit}), 200

    except Exception as e:
        return jsonify({"error": str(e), "uploads": []}), 500


@admin_bp.route("/uploads/<upload_id>", methods=["GET"])
def get_upload_detail(upload_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        rec = db.uploads.find_one({"_id": _oid(upload_id)})
        if not rec:
            return jsonify({"error": "Upload not found"}), 404

        owner = _user_or_none(db, rec.get("user_id", ""))
        bugs = list(db.bugs.find({"analysis_id": rec.get("analysis_id")}))
        for b in bugs:
            b["_id"] = str(b["_id"])

        return jsonify({
            "upload": {
                "id": upload_id, "filename": rec.get("filename", ""), "file_type": rec.get("file_type", ""),
                "file_size": rec.get("file_size", 0), "upload_date": rec.get("upload_date", ""),
                "owner_name": owner.get("name", "Unknown") if owner else "Unknown",
                "owner_email": owner.get("email", "") if owner else "",
            },
            "bugs": bugs,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/uploads/<upload_id>", methods=["DELETE"])
def delete_upload(upload_id):
    try:
        db = get_db()
        _, err = _require_admin(db)
        if err: return err

        rec = db.uploads.find_one({"_id": _oid(upload_id)})
        if not rec:
            return jsonify({"error": "Upload not found"}), 404

        file_path = rec.get("file_path", "")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        unzipped_dir = os.path.join(config.UPLOAD_DIR, f"{Path(rec.get('saved_as','')).stem}_unzipped")
        if os.path.isdir(unzipped_dir):
            shutil.rmtree(unzipped_dir, ignore_errors=True)

        analysis_id = rec.get("analysis_id")
        db.uploads.delete_one({"_id": _oid(upload_id)})
        db.history.delete_many({"upload_id": upload_id})
        if analysis_id:
            db.analysis.delete_one({"_id": analysis_id})
            db.bugs.delete_many({"analysis_id": analysis_id})
            db.file_activity.delete_many({"upload_id": upload_id})

        return jsonify({"message": "Upload deleted"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
