from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
from pathlib import Path
import sys, os, uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, get_my_teams, push_notification, is_user_verified, hydrate_sender_info
from socketio_instance import socketio
from flask_socketio import join_room, emit

chat_bp = Blueprint("chat", __name__)

CHAT_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chat_uploads")
os.makedirs(CHAT_UPLOAD_DIR, exist_ok=True)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
GIF_EXT   = {".gif"}


def _user_or_none(db, user_id):
    from bson import ObjectId
    try:
        return db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def _ensure_channel(db, channel_id, ctype, name):
    db.channels.update_one(
        {"_id": channel_id},
        {"$setOnInsert": {"_id": channel_id, "type": ctype, "name": name, "created_at": datetime.utcnow().isoformat()}},
        upsert=True,
    )


def _unread_count(db, user_id, channel_id):
    read = db.chat_reads.find_one({"user_id": user_id, "channel_id": channel_id})
    since = read["last_read_at"] if read else "0000"
    return db.chat_messages.count_documents({
        "channel_id": channel_id,
        "created_at": {"$gt": since},
        "sender_id": {"$ne": user_id},
    })


# ── GET /api/chat/channels?user_id=xxx ────────────────────────────────────────
# Public Channel + one auto-created group per project the user belongs to +
# their personal Help & Support thread. Regardless of the active project.
@chat_bp.route("/channels", methods=["GET"])
def get_channels():
    try:
        user_id = request.args.get("user_id")
        db = get_db()

        _ensure_channel(db, "public", "public", "Public Channel")
        support_id = f"support:{user_id}"
        _ensure_channel(db, support_id, "support", "Help & Support")

        channels = [{"id": "public", "type": "public", "name": "Public Channel"}]

        for t in get_my_teams(db, user_id):
            cid = f"team:{t['team_id']}"
            _ensure_channel(db, cid, "team", t["name"])
            channels.append({"id": cid, "type": "team", "name": t["name"]})

        channels.append({"id": support_id, "type": "support", "name": "Help & Support"})

        for ch in channels:
            ch["unread"] = _unread_count(db, user_id, ch["id"])

        return jsonify({"channels": channels}), 200

    except Exception as e:
        return jsonify({"error": str(e), "channels": []}), 500


def _serialize_msg(m):
    m["_id"] = str(m["_id"])
    m.setdefault("reactions", {})
    m.setdefault("reply_preview", None)
    m.setdefault("attachment_url", "")
    m.setdefault("attachment_name", "")
    return m


# ── GET /api/chat/messages?channel_id=&user_id=&limit=50 ─────────────────────
@chat_bp.route("/messages", methods=["GET"])
def get_messages():
    try:
        channel_id = request.args.get("channel_id")
        user_id    = request.args.get("user_id")
        limit      = min(int(request.args.get("limit", 50)), 200)
        if not channel_id:
            return jsonify({"error": "channel_id is required", "messages": []}), 400

        db = get_db()
        msgs = list(
            db.chat_messages.find({"channel_id": channel_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        msgs.reverse()
        msgs = [_serialize_msg(m) for m in msgs]
        hydrate_sender_info(db, msgs, "sender_id", "sender_avatar", "sender_verified", "sender_is_admin")

        if user_id:
            db.chat_reads.update_one(
                {"user_id": user_id, "channel_id": channel_id},
                {"$set": {"last_read_at": datetime.utcnow().isoformat()}},
                upsert=True,
            )

        return jsonify({"messages": msgs}), 200

    except Exception as e:
        return jsonify({"error": str(e), "messages": []}), 500


# ── POST /api/chat/upload  (multipart: file, user_id) ─────────────────────────
@chat_bp.route("/upload", methods=["POST"])
def upload_chat_file():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "Empty filename"}), 400

        ext = Path(file.filename).suffix.lower()
        safe_name = f"{uuid.uuid4().hex}{ext}"
        save_path = os.path.join(CHAT_UPLOAD_DIR, safe_name)
        file.save(save_path)

        if ext in GIF_EXT:
            kind = "gif"
        elif ext in IMAGE_EXT:
            kind = "image"
        else:
            kind = "file"

        return jsonify({
            "url" : f"/api/chat/file/{safe_name}",
            "name": file.filename,
            "kind": kind,
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/chat/file/<filename> ─────────────────────────────────────────────
@chat_bp.route("/file/<filename>", methods=["GET"])
def get_chat_file(filename):
    path = os.path.join(CHAT_UPLOAD_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    return send_file(path)


# ════════════════════════════════════════════════════════════════════════════
#  SOCKET.IO — real-time send/receive, typing, reactions
# ════════════════════════════════════════════════════════════════════════════

@socketio.on("join")
def handle_join(data):
    for cid in data.get("channel_ids", []):
        join_room(cid)


@socketio.on("send_message")
def handle_send_message(data):
    db = get_db()
    channel_id = data.get("channel_id")
    sender_id  = data.get("sender_id")
    sender_name = data.get("sender_name", "Someone")
    sender_user = _user_or_none(db, sender_id)

    reply_preview = None
    reply_to = data.get("reply_to")
    if reply_to:
        from bson import ObjectId
        try:
            original = db.chat_messages.find_one({"_id": ObjectId(reply_to)})
            if original:
                reply_preview = {
                    "sender_name": original.get("sender_name", ""),
                    "content": (original.get("content") or original.get("attachment_name") or "")[:120],
                }
        except Exception:
            pass

    msg = {
        "channel_id"     : channel_id,
        "sender_id"      : sender_id,
        "sender_name"    : sender_name,
        "sender_verified": is_user_verified(db, sender_id),
        "sender_is_admin": bool(sender_user.get("is_admin", False)) if sender_user else False,
        "sender_avatar"  : sender_user.get("avatar_url", "") if sender_user else "",
        "type"           : data.get("type", "text"),
        "content"        : data.get("content", ""),
        "attachment_url" : data.get("attachment_url", ""),
        "attachment_name": data.get("attachment_name", ""),
        "reply_to"       : reply_to,
        "reply_preview"  : reply_preview,
        "reactions"      : {},
        "created_at"     : datetime.utcnow().isoformat(),
    }
    result = db.chat_messages.insert_one(msg)
    msg["_id"] = str(result.inserted_id)

    emit("new_message", msg, room=channel_id)

    # Ping teammates for group chats (skip Public — too noisy).
    if channel_id.startswith("team:"):
        team_id = channel_id.split(":", 1)[1]
        for m in db.team_memberships.find({"team_id": team_id, "user_id": {"$ne": sender_id}}):
            push_notification(
                db, m["user_id"], "chat_message",
                f"{sender_name}",
                msg["content"][:100] if msg["content"] else f"sent a {msg['type']}",
                {"channel_id": channel_id},
            )

    # A user messaging their personal Help & Support channel — every admin
    # gets notified so it reaches a real inbox, not just an empty room.
    elif channel_id.startswith("support:"):
        for admin in db.users.find({"is_admin": True}):
            admin_id = str(admin["_id"])
            if admin_id == sender_id:
                continue
            push_notification(
                db, admin_id, "support_message",
                f"Help & Support — {sender_name}",
                msg["content"][:100] if msg["content"] else f"sent a {msg['type']}",
                {"channel_id": channel_id},
            )


@socketio.on("typing")
def handle_typing(data):
    emit(
        "user_typing",
        {"channel_id": data.get("channel_id"), "user_id": data.get("user_id"), "user_name": data.get("user_name")},
        room=data.get("channel_id"),
        include_self=False,
    )


@socketio.on("stop_typing")
def handle_stop_typing(data):
    emit(
        "user_stopped_typing",
        {"channel_id": data.get("channel_id"), "user_id": data.get("user_id")},
        room=data.get("channel_id"),
        include_self=False,
    )


@socketio.on("react_message")
def handle_react(data):
    from bson import ObjectId
    db = get_db()
    message_id = data.get("message_id")
    user_id    = data.get("user_id")
    emoji      = data.get("emoji")
    channel_id = data.get("channel_id")

    msg = db.chat_messages.find_one({"_id": ObjectId(message_id)})
    if not msg:
        return

    reactions = msg.get("reactions", {})
    users = reactions.get(emoji, [])
    if user_id in users:
        users.remove(user_id)
    else:
        users.append(user_id)

    if users:
        reactions[emoji] = users
    elif emoji in reactions:
        del reactions[emoji]

    db.chat_messages.update_one({"_id": ObjectId(message_id)}, {"$set": {"reactions": reactions}})
    emit("message_reacted", {"message_id": message_id, "reactions": reactions}, room=channel_id)


@socketio.on("mark_read")
def handle_mark_read(data):
    db = get_db()
    db.chat_reads.update_one(
        {"user_id": data.get("user_id"), "channel_id": data.get("channel_id")},
        {"$set": {"last_read_at": datetime.utcnow().isoformat()}},
        upsert=True,
    )
