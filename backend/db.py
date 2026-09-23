from pymongo import MongoClient
import config

_client = None
_db     = None

def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(config.MONGO_URI)
        _db     = _client[config.DB_NAME]
        # Indexes for fast queries
        _db.users.create_index("email", unique=True)
        _db.bugs.create_index("analysis_id")
        _db.history.create_index([("user_id", 1), ("analyzed_on", -1)])
        _db.history.create_index("team_id")
        _db.analysis.create_index([("user_id", 1), ("start_time", -1)])
        _db.analysis.create_index("team_id")
        _db.uploads.create_index("team_id")
        _db.teams.create_index("owner_id")
        _db.team_memberships.create_index([("user_id", 1)])
        _db.team_memberships.create_index([("team_id", 1), ("user_id", 1)], unique=True)
        _db.team_invites.create_index([("invited_email", 1), ("status", 1)])
        _db.team_invites.create_index("team_id")
        _db.notifications.create_index([("user_id", 1), ("created_at", -1)])
        _db.notes.create_index([("scope_key", 1), ("created_at", -1)])
        _db.notes.create_index("parent_id")
        _db.subscriptions.create_index([("user_id", 1), ("status", 1)])
        _db.file_activity.create_index([("upload_id", 1), ("created_at", -1)])
    return _db


def push_notification(db, user_id, ntype, title, message, data=None):
    """Create a notification doc for one user. Polled by the frontend bell."""
    from datetime import datetime
    db.notifications.insert_one({
        "user_id"   : user_id,
        "type"      : ntype,
        "title"     : title,
        "message"   : message,
        "data"      : data or {},
        "read"      : False,
        "created_at": datetime.utcnow().isoformat(),
    })


# ── Multi-team helpers ─────────────────────────────────────────────────────
# A user can belong to many teams (one per project). Every upload/history/
# analysis/note record carries its own `team_id` (None = personal). "Scope"
# means: which bucket (Personal, or one specific team/project) is currently
# being viewed — the frontend sends it explicitly, it's never inferred from
# "the user's one team" anymore.

def get_my_teams(db, user_id):
    """All teams this user belongs to, with their role in each."""
    memberships = list(db.team_memberships.find({"user_id": user_id}))
    teams = []
    for m in memberships:
        teams.append({
            "team_id": m["team_id"],
            "name"   : m.get("team_name", ""),
            "role"   : m.get("role", "member"),
        })
    teams.sort(key=lambda t: t["name"].lower())
    return teams


def is_team_member(db, user_id, team_id):
    return db.team_memberships.find_one({"team_id": team_id, "user_id": user_id}) is not None


def team_role(db, user_id, team_id):
    m = db.team_memberships.find_one({"team_id": team_id, "user_id": user_id})
    return m.get("role") if m else None


# ── Bug Plus subscription ────────────────────────────────────────────────
def is_user_verified(db, user_id):
    """
    True if the user has an active, unexpired Bug Plus subscription.
    Lazily flips a lapsed subscription to 'expired' and clears the user's
    cached is_verified flag the moment anyone checks it — no cron needed.
    """
    from bson import ObjectId
    from datetime import datetime

    sub = db.subscriptions.find_one({"user_id": user_id, "status": "active"}, sort=[("expires_at", -1)])
    if not sub:
        return False
    if sub["expires_at"] < datetime.utcnow().isoformat():
        db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"status": "expired"}})
        try:
            db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_verified": False}})
        except Exception:
            pass
        return False
    return True


def hydrate_sender_info(db, docs, id_key, avatar_key, verified_key, admin_key=None):
    """
    Chat messages / notes store the sender's avatar+verified badge at write
    time (avoids a join on every poll), but that means a profile-picture
    change never shows up on messages sent before the change. This overlays
    each doc's avatar/verified (and optionally admin) fields with the
    sender's CURRENT values so history always reflects the latest profile,
    not what it was back then.
    """
    from bson import ObjectId

    ids = {d.get(id_key) for d in docs if d.get(id_key)}
    if not ids:
        return docs

    object_ids = []
    for i in ids:
        try:
            object_ids.append(ObjectId(i))
        except Exception:
            pass
    users_by_id = {str(u["_id"]): u for u in db.users.find({"_id": {"$in": object_ids}})}

    info_cache = {}
    for uid in ids:
        u = users_by_id.get(uid)
        info_cache[uid] = {
            "avatar": u.get("avatar_url", "") if u else "",
            "verified": is_user_verified(db, uid) if u else False,
            "is_admin": bool(u.get("is_admin", False)) if u else False,
        }

    for d in docs:
        info = info_cache.get(d.get(id_key))
        if info:
            d[avatar_key] = info["avatar"]
            d[verified_key] = info["verified"]
            if admin_key:
                d[admin_key] = info["is_admin"]
    return docs


def scope_query(user_id, team_id):
    """
    Mongo filter for "records in this scope". Pass team_id=None (or "")
    for the personal bucket, or a real team_id string for a project.
    Caller is responsible for checking membership before using a team_id.
    """
    if team_id:
        return {"team_id": team_id}
    return {"user_id": user_id, "team_id": {"$in": [None, ""]}}
