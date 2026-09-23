from flask import Blueprint, request, jsonify, send_file
import bcrypt, sys, os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, is_user_verified
import config

settings_bp = Blueprint("settings", __name__)

AVATAR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
AVATAR_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


DEFAULT_TERMS = """Last updated: September 2026

1. ACCEPTANCE OF TERMS
By creating an account or uploading a file to Bug Detector ("the Platform"), you agree to be bound by these Terms & Conditions. If you do not agree, please do not use the Platform.

2. WHAT THE PLATFORM DOES
Bug Detector accepts source code files, log files and archives that you upload, runs them through an automated machine-learning pipeline to estimate the likelihood of defects, classify probable bug types, and suggest fixes. Results are AI-generated estimates, not a guarantee of code correctness or security. You remain responsible for reviewing and testing any code before relying on it.

3. YOUR ACCOUNT
You are responsible for keeping your login credentials confidential and for all activity under your account. Notify us immediately if you suspect unauthorized access.

4. TEAMS AND SHARED PROJECTS
If you create or join a Team (Project), files, bug reports, notes and chat messages you post inside that project become visible to every member of that project for as long as you remain a member. Removing yourself, being removed, or a project owner disbanding the project returns your data to your Personal workspace; it is not deleted.

5. UPLOADED CONTENT
You retain ownership of any code or files you upload. You grant the Platform a limited license to store and process that content solely to provide the analysis, chat, and collaboration features you use. Do not upload content you do not have the right to share, or content containing secrets/credentials you would not want other project members to see.

6. ACCEPTABLE USE
You agree not to: upload malicious files intended to damage the Platform or other users; use the chat or public channel to harass others or share unlawful content; attempt to bypass authentication or access another user's private data.

7. AVAILABILITY
This is a locally-hosted development/academic platform provided "as is," without uptime guarantees. Features, models and analysis accuracy may change as the Platform is improved.

8. LIMITATION OF LIABILITY
The Platform and its bug-detection results are provided without warranty of any kind. We are not liable for decisions made, or damages incurred, based on the AI's suggestions.

9. CHANGES TO THESE TERMS
We may update these Terms from time to time. Continued use of the Platform after changes are posted means you accept the revised Terms.

10. CONTACT
Questions about these Terms can be sent through the Help & Support chat inside the Platform."""

DEFAULT_PRIVACY = """Last updated: September 2026

1. INFORMATION WE COLLECT
- Account information: name, email address, and a securely hashed password.
- Uploaded content: source code files, logs and archives you submit for analysis, and the bug reports generated from them.
- Collaboration content: team/project membership, notes, comments and chat messages you post.
- Usage data: timestamps of uploads, logins, and feature usage needed to operate the Platform (e.g. read status of notifications).

2. HOW WE USE YOUR INFORMATION
We use the information above strictly to operate the Platform: running the ML bug-detection pipeline on your uploads, showing your results and history, enabling team collaboration features (shared projects, notes, chat), and sending in-app notifications (invites, replies, mentions).

3. WHO CAN SEE YOUR DATA
- Personal-scope uploads, notes and files are visible only to you.
- Project-scope uploads, notes, bug reports and the project's group chat are visible to every current member of that project.
- The Public Channel is visible to every user of the Platform — do not post anything there you want to keep private.
- Help & Support conversations are intended to be reviewed by the Platform's administrators to provide support.

4. THIRD-PARTY PROCESSING
If Claude AI–enhanced analysis is turned on in Settings, the specific bug details for that analysis are sent to Anthropic's Claude API to generate a richer explanation and suggested fix. No data is sent to any third party unless this mode is explicitly enabled.

5. DATA RETENTION
Your data is retained until you delete it. Deleting a file first moves it to Deleted Files (recoverable); permanently deleting it, or emptying the trash, removes the file, its analysis and its bug records from our systems.

6. YOUR CHOICES
You can rename, star, move (assign to a different project), or delete your files at any time from Uploaded Logs and History. You can leave a project at any time from the Team page.

7. SECURITY
Passwords are stored using industry-standard hashing (bcrypt) and are never stored or transmitted in plain text.

8. CHANGES TO THIS POLICY
We may update this Privacy Policy as the Platform evolves. Continued use after an update means you accept the revised policy.

9. CONTACT
Questions about this Policy can be sent through the Help & Support chat inside the Platform."""


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
            "id"         : str(user["_id"]),
            "name"       : user.get("name", ""),
            "email"      : user.get("email", ""),
            "role"       : user.get("role", "QA Engineer"),
            "is_verified": is_user_verified(db, user_id),
            "avatar_url" : user.get("avatar_url", ""),
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


# ── POST /api/settings/avatar  (multipart: file, user_id) ─────────────────────
@settings_bp.route("/avatar", methods=["POST"])
def upload_avatar():
    try:
        from bson import ObjectId
        user_id = request.form.get("user_id")
        if not user_id or "file" not in request.files:
            return jsonify({"error": "user_id and file are required"}), 400

        file = request.files["file"]
        ext  = Path(file.filename or "").suffix.lower()
        if ext not in AVATAR_EXT:
            return jsonify({"error": "Use PNG, JPG, WEBP or GIF"}), 400

        # Fixed filename per user (overwrite on re-upload) so the URL never changes.
        safe_name = f"{user_id}{ext}"
        for old_ext in AVATAR_EXT:
            old_path = os.path.join(AVATAR_DIR, f"{user_id}{old_ext}")
            if os.path.exists(old_path) and old_ext != ext:
                os.remove(old_path)

        save_path = os.path.join(AVATAR_DIR, safe_name)
        file.save(save_path)

        avatar_url = f"/api/settings/avatar/{safe_name}?v={int(datetime.utcnow().timestamp())}"

        db = get_db()
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"avatar_url": avatar_url}})

        return jsonify({"avatar_url": avatar_url}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/settings/avatar/<filename> ────────────────────────────────────────
@settings_bp.route("/avatar/<filename>", methods=["GET"])
def get_avatar(filename):
    path = os.path.join(AVATAR_DIR, filename.split("?")[0])
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    return send_file(path)


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

        if enabled and not is_user_verified(db, user_id):
            return jsonify({
                "error": "Claude AI Enhanced Analysis is a Bug Plus feature. Upgrade to turn it on.",
                "upgrade_required": True,
            }), 402

        db.user_settings.update_one(
            {"user_id": user_id},
            {"$set": {"claude_mode": enabled}},
            upsert=True
        )
        return jsonify({"message": "Claude mode updated", "claude_mode": enabled}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/settings/theme?user_id=xxx ──────────────────────────────────────
@settings_bp.route("/theme", methods=["GET"])
def get_theme():
    try:
        user_id = request.args.get("user_id")
        if not user_id or user_id == "undefined":
            return jsonify({"theme": "system"}), 200
        db  = get_db()
        rec = db.user_settings.find_one({"user_id": user_id}) or {}
        return jsonify({"theme": rec.get("theme", "system")}), 200
    except Exception:
        return jsonify({"theme": "system"}), 200


# ── PUT /api/settings/theme ───────────────────────────────────────────────────
@settings_bp.route("/theme", methods=["PUT"])
def set_theme():
    try:
        data    = request.get_json() or {}
        user_id = data.get("user_id")
        theme   = data.get("theme", "system")
        if theme not in ("light", "dark", "system"):
            return jsonify({"error": "theme must be light, dark or system"}), 400
        if not user_id or user_id == "undefined":
            return jsonify({"error": "user_id required"}), 400
        db = get_db()
        db.user_settings.update_one(
            {"user_id": user_id}, {"$set": {"theme": theme}}, upsert=True
        )
        return jsonify({"message": "Theme updated", "theme": theme}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/settings/file-support ────────────────────────────────────────────
# Straight from config.py so this list can never drift from what the upload
# endpoint actually accepts.
@settings_bp.route("/file-support", methods=["GET"])
def get_file_support():
    return jsonify({
        "allowed_extensions": sorted(config.ALLOWED_EXT),
        "max_file_mb"       : config.MAX_FILE_MB,
    }), 200


# ── GET /api/settings/legal ────────────────────────────────────────────────────
@settings_bp.route("/legal", methods=["GET"])
def get_legal():
    try:
        db  = get_db()
        doc = db.site_content.find_one({"_id": "legal"})
        if not doc:
            doc = {
                "_id"    : "legal",
                "terms"  : DEFAULT_TERMS,
                "privacy": DEFAULT_PRIVACY,
                "updated_at": datetime.utcnow().isoformat(),
            }
            db.site_content.insert_one(doc)
        return jsonify({"terms": doc["terms"], "privacy": doc["privacy"], "updated_at": doc.get("updated_at")}), 200
    except Exception as e:
        return jsonify({"error": str(e), "terms": DEFAULT_TERMS, "privacy": DEFAULT_PRIVACY}), 200


# ── PUT /api/settings/legal ────────────────────────────────────────────────────
# No admin UI yet, but the data model is ready for one: whoever manages the
# Platform can update these via this endpoint (or directly in Mongo) without
# a code change.
@settings_bp.route("/legal", methods=["PUT"])
def update_legal():
    try:
        data   = request.get_json() or {}
        fields = {}
        if "terms" in data:
            fields["terms"] = data["terms"]
        if "privacy" in data:
            fields["privacy"] = data["privacy"]
        if not fields:
            return jsonify({"error": "Nothing to update"}), 400
        fields["updated_at"] = datetime.utcnow().isoformat()

        db = get_db()
        db.site_content.update_one({"_id": "legal"}, {"$set": fields}, upsert=True)
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
