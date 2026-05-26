from flask import Blueprint, request, jsonify
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db

history_bp = Blueprint("history", __name__)


# ── GET /api/history?user_id=xxx ─────────────────────────────────────────────
@history_bp.route("", methods=["GET"])
def get_history():
    try:
        user_id   = request.args.get("user_id", "demo_user")
        status    = request.args.get("status")
        file_type = request.args.get("type")
        search    = request.args.get("search", "")

        db    = get_db()
        query = {"user_id": user_id}
        if status    and status    != "All Statuses": query["status"]    = status
        if file_type and file_type != "All Types"   : query["file_type"] = file_type
        if search:
            query["filename"] = {"$regex": search, "$options": "i"}

        records = list(db.history.find(query).sort("analyzed_on", -1))
        for r in records:
            r["_id"] = str(r["_id"])
            r.setdefault("filename",     "—")
            r.setdefault("file_type",    "")
            r.setdefault("total_bugs",   0)
            r.setdefault("critical_bugs", 0)
            r.setdefault("status",       "completed")
            r.setdefault("starred",      False)

        return jsonify({"history": records, "total": len(records)}), 200

    except Exception as e:
        return jsonify({"error": str(e), "history": [], "total": 0}), 500


# ── DELETE /api/history/<history_id> ─────────────────────────────────────────
@history_bp.route("/<history_id>", methods=["DELETE"])
def delete_history(history_id):
    try:
        from bson import ObjectId
        db = get_db()
        result = db.history.delete_one({"_id": ObjectId(history_id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Record not found"}), 404
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/history/stats?user_id=xxx ───────────────────────────────────────
@history_bp.route("/stats", methods=["GET"])
def history_stats():
    try:
        user_id = request.args.get("user_id", "demo_user")
        db      = get_db()

        total    = db.history.count_documents({"user_id": user_id})
        starred  = db.history.count_documents({"user_id": user_id, "starred": True})
        comments = db.notes.count_documents({"user_id": user_id}) if "notes" in db.list_collection_names() else 0

        return jsonify({
            "total_files"   : total,
            "starred_files" : starred,
            "deleted_files" : 0,
            "notes_comments": comments,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e), "total_files": 0, "starred_files": 0, "deleted_files": 0, "notes_comments": 0}), 500


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
