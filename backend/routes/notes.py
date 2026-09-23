from flask import Blueprint, request, jsonify
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, is_team_member, push_notification, is_user_verified, hydrate_sender_info

notes_bp = Blueprint("notes", __name__)


def _scope_key(user_id, team_id):
    return f"team:{team_id}" if team_id else f"personal:{user_id}"


def _user_or_none(db, user_id):
    from bson import ObjectId
    try:
        return db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def _serialize(n):
    n["_id"] = str(n["_id"])
    n.setdefault("pinned", False)
    n.setdefault("parent_id", None)
    n.setdefault("file", "")
    n.setdefault("path", "")
    n.setdefault("bug", "")
    return n


# ── GET /api/notes?user_id=xxx&team_id=yyy ───────────────────────────────────
# Flat list (notes + comments + replies) for the current scope. Polled every
# few seconds by the frontend for near-real-time collaboration.
@notes_bp.route("", methods=["GET"])
def get_notes():
    try:
        user_id = request.args.get("user_id")
        team_id = request.args.get("team_id") or None

        db = get_db()
        if team_id and not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of this project"}), 403

        scope_key = _scope_key(user_id, team_id)
        items = list(db.notes.find({"scope_key": scope_key}).sort("created_at", -1))
        items = [_serialize(n) for n in items]
        hydrate_sender_info(db, items, "author_id", "author_avatar", "author_verified")

        return jsonify({"notes": items, "total": len(items)}), 200

    except Exception as e:
        return jsonify({"error": str(e), "notes": [], "total": 0}), 500


# ── POST /api/notes ────────────────────────────────────────────────────────────
@notes_bp.route("", methods=["POST"])
def create_note():
    try:
        data    = request.get_json() or {}
        user_id = data.get("user_id")
        team_id = data.get("team_id") or None

        db = get_db()
        if team_id and not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of this project"}), 403

        user = _user_or_none(db, user_id)
        title   = (data.get("title", "") or "").strip()
        content = (data.get("content", "") or "").strip()
        if not title or not content:
            return jsonify({"error": "title and content are required"}), 400

        note = {
            "scope_key" : _scope_key(user_id, team_id),
            "type"      : data.get("type") if data.get("type") in ("note", "comment") else "note",
            "title"     : title,
            "content"   : content,
            "file"      : (data.get("file", "") or "").strip(),
            "path"      : (data.get("path", "") or "").strip(),
            "bug"       : (data.get("bug", "") or "").strip(),
            "pinned"    : bool(data.get("pinned", False)),
            "parent_id" : None,
            "author_id" : user_id,
            "author_name": user.get("name", "Someone") if user else "Someone",
            "author_verified": is_user_verified(db, user_id),
            "author_avatar": user.get("avatar_url", "") if user else "",
            "created_at": datetime.utcnow().isoformat(),
        }
        result = db.notes.insert_one(note)
        note["_id"] = str(result.inserted_id)

        # Notify the rest of the team a new note/comment landed.
        if team_id:
            team = db.teams.find_one({"_id": __import__("bson").ObjectId(team_id)})
            teammates = db.team_memberships.find({"team_id": team_id, "user_id": {"$ne": user_id}})
            for m in teammates:
                push_notification(
                    db, m["user_id"], "note_created",
                    "New Note" if note["type"] == "note" else "New Comment",
                    f"{note['author_name']} added a {note['type']}: \"{title}\"",
                    {"note_id": note["_id"], "team_id": team_id},
                )

        return jsonify(note), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/notes/<id>/reply ────────────────────────────────────────────────
@notes_bp.route("/<note_id>/reply", methods=["POST"])
def reply_note(note_id):
    try:
        from bson import ObjectId
        data    = request.get_json() or {}
        user_id = data.get("user_id")
        content = (data.get("content", "") or "").strip()
        if not content:
            return jsonify({"error": "content is required"}), 400

        db     = get_db()
        parent = db.notes.find_one({"_id": ObjectId(note_id)})
        if not parent:
            return jsonify({"error": "Note not found"}), 404

        user = _user_or_none(db, user_id)
        reply = {
            "scope_key" : parent["scope_key"],
            "type"      : "comment",
            "title"     : "",
            "content"   : content,
            "file"      : parent.get("file", ""),
            "path"      : parent.get("path", ""),
            "bug"       : parent.get("bug", ""),
            "pinned"    : False,
            "parent_id" : str(parent["_id"]),
            "author_id" : user_id,
            "author_name": user.get("name", "Someone") if user else "Someone",
            "author_verified": is_user_verified(db, user_id),
            "author_avatar": user.get("avatar_url", "") if user else "",
            "created_at": datetime.utcnow().isoformat(),
        }
        result = db.notes.insert_one(reply)
        reply["_id"] = str(result.inserted_id)

        if parent.get("author_id") and parent["author_id"] != user_id:
            push_notification(
                db, parent["author_id"], "note_reply",
                "New Reply",
                f"{reply['author_name']} replied to \"{parent.get('title') or parent.get('content','')[:40]}\"",
                {"note_id": str(parent["_id"])},
            )

        return jsonify(reply), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── PUT /api/notes/<id> ────────────────────────────────────────────────────────
@notes_bp.route("/<note_id>", methods=["PUT"])
def update_note(note_id):
    try:
        from bson import ObjectId
        data   = request.get_json() or {}
        fields = {}
        for key in ("title", "content", "file", "path", "bug", "type"):
            if key in data:
                fields[key] = data[key]
        if not fields:
            return jsonify({"error": "Nothing to update"}), 400

        db = get_db()
        result = db.notes.update_one({"_id": ObjectId(note_id)}, {"$set": fields})
        if result.matched_count == 0:
            return jsonify({"error": "Note not found"}), 404
        return jsonify({"message": "Updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── PUT /api/notes/<id>/pin ───────────────────────────────────────────────────
@notes_bp.route("/<note_id>/pin", methods=["PUT"])
def toggle_pin(note_id):
    try:
        from bson import ObjectId
        db  = get_db()
        rec = db.notes.find_one({"_id": ObjectId(note_id)})
        if not rec:
            return jsonify({"error": "Note not found"}), 404
        new_val = not rec.get("pinned", False)
        db.notes.update_one({"_id": ObjectId(note_id)}, {"$set": {"pinned": new_val}})
        return jsonify({"pinned": new_val}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── DELETE /api/notes/<id> ────────────────────────────────────────────────────
@notes_bp.route("/<note_id>", methods=["DELETE"])
def delete_note(note_id):
    try:
        from bson import ObjectId
        db = get_db()
        result = db.notes.delete_one({"_id": ObjectId(note_id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Note not found"}), 404
        db.notes.delete_many({"parent_id": note_id})
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
