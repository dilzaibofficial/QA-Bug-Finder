from flask import Blueprint, request, jsonify
from datetime import datetime
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, scope_query, is_team_member

history_bp = Blueprint("history", __name__)


def _serialize(r):
    r["_id"] = str(r["_id"])
    r.setdefault("filename",     "—")
    r.setdefault("file_type",    "")
    r.setdefault("total_bugs",   0)
    r.setdefault("critical_bugs", 0)
    r.setdefault("status",       "completed")
    r.setdefault("starred",      False)
    r.setdefault("file_size",    0)
    r.setdefault("upload_id",    "")
    r.setdefault("analysis_id",  "")
    r.setdefault("team_id",      None)
    r.setdefault("deleted",      False)
    return r


# ── GET /api/history?user_id=xxx&team_id=yyy ─────────────────────────────────
@history_bp.route("", methods=["GET"])
def get_history():
    try:
        user_id   = request.args.get("user_id", "demo_user")
        team_id   = request.args.get("team_id") or None
        status    = request.args.get("status")
        file_type = request.args.get("type")
        search    = request.args.get("search", "")

        db = get_db()
        if team_id and not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of this project"}), 403

        query = scope_query(user_id, team_id)
        query["deleted"] = {"$ne": True}
        if status    and status    != "All Statuses": query["status"]    = status
        if file_type and file_type != "All Types"   : query["file_type"] = file_type
        if search:
            query["filename"] = {"$regex": search, "$options": "i"}

        records = [_serialize(r) for r in db.history.find(query).sort("analyzed_on", -1)]
        return jsonify({"history": records, "total": len(records)}), 200

    except Exception as e:
        return jsonify({"error": str(e), "history": [], "total": 0}), 500


# ── GET /api/history/deleted?user_id=xxx&team_id=yyy ──────────────────────────
# The trash — files removed via the Delete action, kept until restored or
# permanently removed.
@history_bp.route("/deleted", methods=["GET"])
def get_deleted():
    try:
        user_id = request.args.get("user_id", "demo_user")
        team_id = request.args.get("team_id") or None

        db = get_db()
        if team_id and not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of this project"}), 403

        query = scope_query(user_id, team_id)
        query["deleted"] = True

        records = [_serialize(r) for r in db.history.find(query).sort("deleted_at", -1)]
        return jsonify({"history": records, "total": len(records)}), 200

    except Exception as e:
        return jsonify({"error": str(e), "history": [], "total": 0}), 500


# ── DELETE /api/history/<history_id> ─────────────────────────────────────────
# Soft delete — moves the file to the trash (Deleted Files). Use /permanent
# to actually remove it.
@history_bp.route("/<history_id>", methods=["DELETE"])
def delete_history(history_id):
    try:
        from bson import ObjectId
        db = get_db()
        result = db.history.update_one(
            {"_id": ObjectId(history_id)},
            {"$set": {"deleted": True, "deleted_at": datetime.utcnow().isoformat()}}
        )
        if result.matched_count == 0:
            return jsonify({"error": "Record not found"}), 404
        return jsonify({"message": "Moved to trash"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/history/<history_id>/restore ────────────────────────────────────
@history_bp.route("/<history_id>/restore", methods=["POST"])
def restore_history(history_id):
    try:
        from bson import ObjectId
        db = get_db()
        result = db.history.update_one(
            {"_id": ObjectId(history_id)},
            {"$set": {"deleted": False}, "$unset": {"deleted_at": ""}}
        )
        if result.matched_count == 0:
            return jsonify({"error": "Record not found"}), 404
        return jsonify({"message": "Restored"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── DELETE /api/history/<history_id>/permanent ────────────────────────────────
# Actually removes the file: history entry, upload record + the file on
# disk, analysis record and its bugs. Cannot be undone.
@history_bp.route("/<history_id>/permanent", methods=["DELETE"])
def permanent_delete(history_id):
    try:
        from bson import ObjectId
        db  = get_db()
        rec = db.history.find_one({"_id": ObjectId(history_id)})
        if not rec:
            return jsonify({"error": "Record not found"}), 404

        upload_id   = rec.get("upload_id")
        analysis_id = rec.get("analysis_id")

        if upload_id:
            try:
                upload = db.uploads.find_one({"_id": ObjectId(upload_id)})
                if upload and upload.get("file_path") and os.path.exists(upload["file_path"]):
                    os.remove(upload["file_path"])
                db.uploads.delete_one({"_id": ObjectId(upload_id)})
            except Exception:
                pass

        if analysis_id:
            db.bugs.delete_many({"analysis_id": analysis_id})
            db.analysis.delete_one({"_id": analysis_id})

        db.history.delete_one({"_id": ObjectId(history_id)})
        return jsonify({"message": "Permanently deleted"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/history/empty-trash ─────────────────────────────────────────────
@history_bp.route("/empty-trash", methods=["POST"])
def empty_trash():
    try:
        from bson import ObjectId
        data    = request.get_json() or {}
        user_id = data.get("user_id", "demo_user")
        team_id = data.get("team_id") or None

        db = get_db()
        if team_id and not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of this project"}), 403

        query = scope_query(user_id, team_id)
        query["deleted"] = True
        records = list(db.history.find(query))

        for rec in records:
            upload_id   = rec.get("upload_id")
            analysis_id = rec.get("analysis_id")
            if upload_id:
                try:
                    upload = db.uploads.find_one({"_id": ObjectId(upload_id)})
                    if upload and upload.get("file_path") and os.path.exists(upload["file_path"]):
                        os.remove(upload["file_path"])
                    db.uploads.delete_one({"_id": ObjectId(upload_id)})
                except Exception:
                    pass
            if analysis_id:
                db.bugs.delete_many({"analysis_id": analysis_id})
                db.analysis.delete_one({"_id": analysis_id})
            db.history.delete_one({"_id": rec["_id"]})

        return jsonify({"message": "Trash emptied", "count": len(records)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── PUT /api/history/<history_id>/rename ─────────────────────────────────────
# Renames the file everywhere it's referenced (history, uploads, analysis)
# so the new name shows up consistently across every dashboard screen.
@history_bp.route("/<history_id>/rename", methods=["PUT"])
def rename_history(history_id):
    try:
        from bson import ObjectId
        data     = request.get_json() or {}
        new_name = (data.get("filename", "") or "").strip()
        if not new_name:
            return jsonify({"error": "filename is required"}), 400

        db  = get_db()
        rec = db.history.find_one({"_id": ObjectId(history_id)})
        if not rec:
            return jsonify({"error": "Record not found"}), 404

        db.history.update_one({"_id": ObjectId(history_id)}, {"$set": {"filename": new_name}})

        upload_id = rec.get("upload_id")
        if upload_id:
            try:
                db.uploads.update_one({"_id": ObjectId(upload_id)}, {"$set": {"filename": new_name}})
            except Exception:
                pass

        analysis_id = rec.get("analysis_id")
        if analysis_id:
            db.analysis.update_one({"_id": analysis_id}, {"$set": {"filename": new_name}})

        return jsonify({"message": "Renamed", "filename": new_name}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── PUT /api/history/<history_id>/assign-team ─────────────────────────────────
# Moves a file into a project (team_id) or back to Personal (team_id: null).
# Keeps history/uploads/analysis in sync so every screen agrees on where the
# file lives.
@history_bp.route("/<history_id>/assign-team", methods=["PUT"])
def assign_team(history_id):
    try:
        from bson import ObjectId
        data      = request.get_json() or {}
        user_id   = data.get("user_id")
        team_id   = data.get("team_id") or None

        db = get_db()
        if team_id and not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of that project"}), 403

        rec = db.history.find_one({"_id": ObjectId(history_id)})
        if not rec:
            return jsonify({"error": "Record not found"}), 404

        db.history.update_one({"_id": ObjectId(history_id)}, {"$set": {"team_id": team_id}})

        upload_id = rec.get("upload_id")
        if upload_id:
            try:
                db.uploads.update_one({"_id": ObjectId(upload_id)}, {"$set": {"team_id": team_id}})
            except Exception:
                pass

        analysis_id = rec.get("analysis_id")
        if analysis_id:
            db.analysis.update_one({"_id": analysis_id}, {"$set": {"team_id": team_id}})

        return jsonify({"message": "Moved", "team_id": team_id}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/history/stats?user_id=xxx&team_id=yyy ───────────────────────────
@history_bp.route("/stats", methods=["GET"])
def history_stats():
    try:
        user_id = request.args.get("user_id", "demo_user")
        team_id = request.args.get("team_id") or None
        db      = get_db()
        if team_id and not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of this project"}), 403

        base    = scope_query(user_id, team_id)
        total   = db.history.count_documents({**base, "deleted": {"$ne": True}})
        starred = db.history.count_documents({**base, "deleted": {"$ne": True}, "starred": True})
        deleted = db.history.count_documents({**base, "deleted": True})

        scope_key = f"team:{team_id}" if team_id else f"personal:{user_id}"
        notes_comments = db.notes.count_documents({"scope_key": scope_key})

        return jsonify({
            "total_files"   : total,
            "starred_files" : starred,
            "deleted_files" : deleted,
            "notes_comments": notes_comments,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e), "total_files": 0, "starred_files": 0, "deleted_files": 0}), 500


# ── PUT /api/history/<history_id>/star ───────────────────────────────────────
@history_bp.route("/<history_id>/star", methods=["PUT"])
def toggle_star(history_id):
    try:
        from bson import ObjectId
        db  = get_db()
        rec = db.history.find_one({"_id": ObjectId(history_id)})
        if not rec:
            return jsonify({"error": "Not found"}), 404
        new_val = not rec.get("starred", False)
        db.history.update_one({"_id": ObjectId(history_id)}, {"$set": {"starred": new_val}})
        return jsonify({"starred": new_val}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
