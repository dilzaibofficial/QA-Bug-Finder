from flask import Blueprint, request, jsonify
from datetime import datetime
import bcrypt, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db

auth_bp = Blueprint("auth", __name__)


# ── POST /api/auth/signup ─────────────────────────────────────────────────────
@auth_bp.route("/signup", methods=["POST"])
def signup():
    try:
        data     = request.get_json() or {}
        name     = (data.get("name", "") or "").strip()
        email    = (data.get("email", "") or "").strip().lower()
        password = (data.get("password", "") or "")

        if not name or not email or not password:
            return jsonify({"error": "All fields are required"}), 400
        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400

        db = get_db()
        if db.users.find_one({"email": email}):
            return jsonify({"error": "Email already registered"}), 409

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        result = db.users.insert_one({
            "name"      : name,
            "email"     : email,
            "password"  : hashed,
            "role"      : "QA Engineer",
            "created_at": datetime.utcnow().isoformat(),
        })
        return jsonify({
            "id"   : str(result.inserted_id),
            "name" : name,
            "email": email,
            "role" : "QA Engineer",
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/auth/login ──────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    try:
        data     = request.get_json() or {}
        email    = (data.get("email", "") or "").strip().lower()
        password = (data.get("password", "") or "")

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        db   = get_db()
        user = db.users.find_one({"email": email})

        if not user or not bcrypt.checkpw(password.encode(), user["password"].encode()):
            return jsonify({"error": "Invalid email or password"}), 401

        return jsonify({
            "id"   : str(user["_id"]),
            "name" : user.get("name", ""),
            "email": user.get("email", ""),
            "role" : user.get("role", "QA Engineer"),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/auth/forgot-password ───────────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        data  = request.get_json() or {}
        email = (data.get("email", "") or "").strip().lower()

        if not email:
            return jsonify({"error": "Email required"}), 400

        db   = get_db()
        user = db.users.find_one({"email": email})
        if not user:
            return jsonify({"error": "No account found with this email"}), 404

        return jsonify({"message": "OTP sent", "otp": "123456"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/auth/verify-otp ─────────────────────────────────────────────────
@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    try:
        data = request.get_json() or {}
        otp  = data.get("otp", "")
        if otp == "123456":
            return jsonify({"message": "OTP verified"}), 200
        return jsonify({"error": "Invalid OTP"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/auth/reset-password ─────────────────────────────────────────────
@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    try:
        data        = request.get_json() or {}
        email       = (data.get("email", "") or "").strip().lower()
        new_password = data.get("new_password", "")

        if not email or not new_password:
            return jsonify({"error": "Email and new password required"}), 400
        if len(new_password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400

        db     = get_db()
        user   = db.users.find_one({"email": email})
        if not user:
            return jsonify({"error": "User not found"}), 404

        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        db.users.update_one({"email": email}, {"$set": {"password": hashed}})
        return jsonify({"message": "Password reset successful"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
