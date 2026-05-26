from flask import Blueprint, request, jsonify
import bcrypt, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db

settings_bp = Blueprint("settings", __name__)


# ── GET /api/settings/profile?user_id=xxx ────────────────────────────────────
@settings_bp.route("/profile", methods=["GET"])
def get_profile():
    try:
        from bson import ObjectId
        user_id = request.args.get("user_id")
        if not user_id or user_id == "undefined":
            return jsonify({"error": "user_id required"}), 400

        db   = get_db()
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404

        return jsonify({
            "id"   : str(user["_id"]),
            "name" : user.get("name", ""),
            "email": user.get("email", ""),
            "role" : user.get("role", "QA Engineer"),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── PUT /api/settings/profile ────────────────────────────────────────────────
@settings_bp.route("/profile", methods=["PUT"])
def update_profile():
    try:
        from bson import ObjectId
        data    = request.get_json() or {}
        user_id = data.get("user_id")
        name    = (data.get("name", "") or "").strip()
        email   = (data.get("email", "") or "").strip().lower()
        role    = data.get("role", "QA Engineer")

        if not user_id or user_id == "undefined":
            return jsonify({"error": "user_id required"}), 400

        db = get_db()
        db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"name": name, "email": email, "role": role}}
        )
        return jsonify({"message": "Profile updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── PUT /api/settings/password ───────────────────────────────────────────────
@settings_bp.route("/password", methods=["PUT"])
def update_password():
    try:
        from bson import ObjectId
        data         = request.get_json() or {}
        user_id      = data.get("user_id")
        current_pass = data.get("current_password", "")
        new_pass     = data.get("new_password", "")

        if not user_id or user_id == "undefined":
            return jsonify({"error": "user_id required"}), 400
        if not current_pass or not new_pass:
            return jsonify({"error": "All fields required"}), 400

        db   = get_db()
        user = db.users.find_one({"_id": ObjectId(user_id)})

        if not user:
            return jsonify({"error": "User not found"}), 404

        if not bcrypt.checkpw(current_pass.encode(), user["password"].encode()):
            return jsonify({"error": "Current password is incorrect"}), 401

        hashed = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"password": hashed}})
        return jsonify({"message": "Password updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/settings/claude-mode?user_id=xxx ────────────────────────────────
@settings_bp.route("/claude-mode", methods=["GET"])
def get_claude_mode():
    try:
        user_id = request.args.get("user_id")
        if not user_id or user_id == "undefined":
            return jsonify({"claude_mode": False}), 200
        db  = get_db()
        rec = db.user_settings.find_one({"user_id": user_id}) or {}
        return jsonify({"claude_mode": rec.get("claude_mode", False)}), 200
    except Exception as e:
        return jsonify({"claude_mode": False}), 200


# ── PUT /api/settings/claude-mode ────────────────────────────────────────────
@settings_bp.route("/claude-mode", methods=["PUT"])
def set_claude_mode():
    try:
        data    = request.get_json() or {}
        user_id = data.get("user_id")
        enabled = bool(data.get("claude_mode", False))
        if not user_id or user_id == "undefined":
            return jsonify({"error": "user_id required"}), 400
        db = get_db()
        db.user_settings.update_one(
            {"user_id": user_id},
            {"$set": {"claude_mode": enabled}},
            upsert=True
        )
        return jsonify({"message": "Claude mode updated", "claude_mode": enabled}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
