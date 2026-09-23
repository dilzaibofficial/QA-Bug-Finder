from flask import Blueprint, request, jsonify
from datetime import datetime
import bcrypt, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, is_user_verified
import config

from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

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
            "id"         : str(user["_id"]),
            "name"       : user.get("name", ""),
            "email"      : user.get("email", ""),
            "role"       : user.get("role", "QA Engineer"),
            "is_verified": is_user_verified(db, str(user["_id"])),
            "avatar_url" : user.get("avatar_url", ""),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/auth/google ─────────────────────────────────────────────────────
# Verifies a Google Identity Services ID token and logs the user in, creating
# an account on first sign-in (same response shape as /login and /signup so
# the frontend can treat it identically).
@auth_bp.route("/google", methods=["POST"])
def google_login():
    try:
        if not config.GOOGLE_CLIENT_ID:
            return jsonify({"error": "Google sign-in is not configured on the server"}), 503

        data       = request.get_json() or {}
        credential = data.get("credential", "")
        if not credential:
            return jsonify({"error": "Missing Google credential"}), 400

        try:
            payload = google_id_token.verify_oauth2_token(
                credential, google_requests.Request(), config.GOOGLE_CLIENT_ID
            )
        except ValueError:
            return jsonify({"error": "Invalid Google credential"}), 401

        email = (payload.get("email", "") or "").strip().lower()
        if not email or not payload.get("email_verified", False):
            return jsonify({"error": "Google account email is not verified"}), 401

        name    = payload.get("name") or email.split("@")[0]
        picture = payload.get("picture", "")

        db   = get_db()
        user = db.users.find_one({"email": email})

        if not user:
            random_hash = bcrypt.hashpw(os.urandom(24), bcrypt.gensalt()).decode()
            result = db.users.insert_one({
                "name"         : name,
                "email"        : email,
                "password"     : random_hash,
                "role"         : "QA Engineer",
                "auth_provider": "google",
                "avatar_url"   : picture,
                "created_at"   : datetime.utcnow().isoformat(),
            })
            user = db.users.find_one({"_id": result.inserted_id})
        elif picture and not user.get("avatar_url"):
            db.users.update_one({"_id": user["_id"]}, {"$set": {"avatar_url": picture}})
            user["avatar_url"] = picture

        return jsonify({
            "id"         : str(user["_id"]),
            "name"       : user.get("name", ""),
            "email"      : user.get("email", ""),
            "role"       : user.get("role", "QA Engineer"),
            "is_verified": is_user_verified(db, str(user["_id"])),
            "avatar_url" : user.get("avatar_url", ""),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _send_otp_email(to_email, otp):
    """Sends the OTP over SMTP if configured. Returns True if actually sent."""
    if not (config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASS):
        return False
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(
        f"Your Bug Detector password reset code is: {otp}\n\n"
        f"This code expires in 10 minutes. If you didn't request this, you can ignore this email."
    )
    msg["Subject"] = "Bug Detector — Password Reset Code"
    msg["From"]    = config.SMTP_FROM
    msg["To"]      = to_email

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASS)
        server.sendmail(config.SMTP_FROM, [to_email], msg.as_string())
    return True


# ── POST /api/auth/forgot-password ───────────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        import random

        data  = request.get_json() or {}
        email = (data.get("email", "") or "").strip().lower()

        if not email:
            return jsonify({"error": "Email required"}), 400

        db   = get_db()
        user = db.users.find_one({"email": email})
        if not user:
            return jsonify({"error": "No account found with this email"}), 404

        otp = f"{random.randint(0, 999999):06d}"
        db.password_resets.update_one(
            {"email": email},
            {"$set": {
                "email"     : email,
                "otp"       : otp,
                "verified"  : False,
                "expires_at": datetime.utcnow().timestamp() + 600,  # 10 minutes
            }},
            upsert=True,
        )

        try:
            email_sent = _send_otp_email(email, otp)
        except Exception:
            email_sent = False

        resp = {"message": "OTP sent" if email_sent else "OTP generated", "email_sent": email_sent}
        if not email_sent:
            # No SMTP configured — hand the OTP back so the flow is still usable/demoable.
            resp["otp"] = otp
        return jsonify(resp), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/auth/verify-otp ─────────────────────────────────────────────────
@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    try:
        data  = request.get_json() or {}
        email = (data.get("email", "") or "").strip().lower()
        otp   = (data.get("otp", "") or "").strip()

        if not email or not otp:
            return jsonify({"error": "Email and code are required"}), 400

        db  = get_db()
        rec = db.password_resets.find_one({"email": email})

        if not rec or rec.get("otp") != otp:
            return jsonify({"error": "Invalid verification code"}), 400
        if rec.get("expires_at", 0) < datetime.utcnow().timestamp():
            return jsonify({"error": "Code expired — request a new one"}), 400

        db.password_resets.update_one({"email": email}, {"$set": {"verified": True}})
        return jsonify({"message": "OTP verified"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/auth/reset-password ─────────────────────────────────────────────
@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    try:
        data         = request.get_json() or {}
        email        = (data.get("email", "") or "").strip().lower()
        new_password = data.get("new_password", "")

        if not email or not new_password:
            return jsonify({"error": "Email and new password required"}), 400
        if len(new_password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400

        db  = get_db()
        rec = db.password_resets.find_one({"email": email})
        if not rec or not rec.get("verified"):
            return jsonify({"error": "Please verify your code before resetting the password"}), 401
        if rec.get("expires_at", 0) < datetime.utcnow().timestamp():
            return jsonify({"error": "Verification expired — request a new code"}), 400

        user = db.users.find_one({"email": email})
        if not user:
            return jsonify({"error": "User not found"}), 404

        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        db.users.update_one({"email": email}, {"$set": {"password": hashed}})
        db.password_resets.delete_one({"email": email})  # single-use
        return jsonify({"message": "Password reset successful"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
