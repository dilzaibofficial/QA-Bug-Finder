from flask import Blueprint, request, jsonify
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, push_notification, get_my_teams, is_team_member, team_role, is_user_verified

team_bp = Blueprint("team", __name__)

FREE_PROJECT_LIMIT = 1


def _user_or_none(db, user_id):
    from bson import ObjectId
    try:
        return db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def _public_member(db, membership):
    u = _user_or_none(db, membership["user_id"])
    return {
        "id"        : membership["user_id"],
        "name"      : u.get("name", "") if u else "Unknown",
        "email"     : u.get("email", "") if u else "",
        "role"      : u.get("role", "QA Engineer") if u else "",
        "team_role" : membership.get("role"),
        "is_verified": is_user_verified(db, membership["user_id"]) if u else False,
        "avatar_url": u.get("avatar_url", "") if u else "",
    }


# ── POST /api/team/create ─────────────────────────────────────────────────────
# Creates a new team/project. Free accounts get one owned project; creating
# a 2nd+ requires an active Bug Plus subscription.
@team_bp.route("/create", methods=["POST"])
def create_team():
    try:
        data      = request.get_json() or {}
        user_id   = data.get("user_id")
        team_name = (data.get("team_name", "") or "").strip()

        if not user_id or not team_name:
            return jsonify({"error": "user_id and team_name are required"}), 400

        db   = get_db()
        user = _user_or_none(db, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        owned_count = db.teams.count_documents({"owner_id": user_id})
        if owned_count >= FREE_PROJECT_LIMIT and not is_user_verified(db, user_id):
            return jsonify({
                "error": "Free accounts can create 1 project. Upgrade to Bug Plus for unlimited projects.",
                "upgrade_required": True,
            }), 402

        team = db.teams.insert_one({
            "name"      : team_name,
            "owner_id"  : user_id,
            "created_at": datetime.utcnow().isoformat(),
        })
        team_id = str(team.inserted_id)

        db.team_memberships.insert_one({
            "team_id"  : team_id,
            "team_name": team_name,
            "user_id"  : user_id,
            "role"     : "owner",
            "joined_at": datetime.utcnow().isoformat(),
        })

        # Every project automatically gets its own group chat.
        db.channels.update_one(
            {"_id": f"team:{team_id}"},
            {"$setOnInsert": {
                "_id": f"team:{team_id}", "type": "team", "name": team_name,
                "created_at": datetime.utcnow().isoformat(),
            }},
            upsert=True,
        )

        return jsonify({"team_id": team_id, "name": team_name}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/team/my-teams?user_id=xxx ────────────────────────────────────────
# Every project/team this user belongs to — powers the project switcher.
@team_bp.route("/my-teams", methods=["GET"])
def my_teams():
    try:
        user_id = request.args.get("user_id")
        db      = get_db()
        return jsonify({"teams": get_my_teams(db, user_id)}), 200
    except Exception as e:
        return jsonify({"error": str(e), "teams": []}), 500


# ── GET /api/team/info?user_id=xxx&team_id=yyy ────────────────────────────────
@team_bp.route("/info", methods=["GET"])
def team_info():
    try:
        from bson import ObjectId
        user_id = request.args.get("user_id")
        team_id = request.args.get("team_id")
        db      = get_db()

        if not team_id or not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of this team"}), 403

        team = db.teams.find_one({"_id": ObjectId(team_id)})
        if not team:
            return jsonify({"error": "Team not found"}), 404

        memberships = list(db.team_memberships.find({"team_id": team_id}))
        members = [_public_member(db, m) for m in memberships]
        members.sort(key=lambda m: 0 if m["team_role"] == "owner" else 1)

        return jsonify({
            "team": {
                "id"      : team_id,
                "name"    : team.get("name", ""),
                "owner_id": team.get("owner_id"),
                "members" : members,
                "my_role" : team_role(db, user_id, team_id),
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/team/invite ─────────────────────────────────────────────────────
@team_bp.route("/invite", methods=["POST"])
def invite_member():
    try:
        data    = request.get_json() or {}
        user_id = data.get("user_id")
        team_id = data.get("team_id")
        email   = (data.get("email", "") or "").strip().lower()

        if not user_id or not team_id or not email:
            return jsonify({"error": "user_id, team_id and email are required"}), 400

        db = get_db()
        if not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of this team"}), 403

        inviter = _user_or_none(db, user_id)
        team    = db.teams.find_one({"_id": __import__("bson").ObjectId(team_id)})

        target = db.users.find_one({"email": email})
        if not target:
            return jsonify({"error": "No account found with this email. Ask them to sign up first."}), 404
        if is_team_member(db, str(target["_id"]), team_id):
            return jsonify({"error": "This person is already in this team"}), 409

        existing = db.team_invites.find_one({
            "team_id"      : team_id,
            "invited_email": email,
            "status"       : "pending",
        })
        if existing:
            return jsonify({"error": "An invite is already pending for this email"}), 409

        invite = db.team_invites.insert_one({
            "team_id"        : team_id,
            "team_name"      : team.get("name", "") if team else "",
            "invited_email"  : email,
            "invited_by"     : user_id,
            "invited_by_name": inviter.get("name", "") if inviter else "",
            "status"         : "pending",
            "created_at"     : datetime.utcnow().isoformat(),
        })

        push_notification(
            db, str(target["_id"]), "team_invite",
            "Team Invite",
            f"{inviter.get('name', 'Someone') if inviter else 'Someone'} invited you to join \"{team.get('name', '') if team else ''}\"",
            {"invite_id": str(invite.inserted_id), "team_name": team.get("name", "") if team else ""},
        )

        return jsonify({"message": "Invite sent", "invite_id": str(invite.inserted_id)}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/team/invites?user_id=xxx ────────────────────────────────────────
# Pending invites addressed to the current user's email.
@team_bp.route("/invites", methods=["GET"])
def get_my_invites():
    try:
        user_id = request.args.get("user_id")
        db      = get_db()
        user    = _user_or_none(db, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        invites = list(db.team_invites.find({
            "invited_email": user.get("email", "").lower(),
            "status"       : "pending",
        }))
        for inv in invites:
            inv["_id"] = str(inv["_id"])

        return jsonify({"invites": invites}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/team/invites/<invite_id>/respond ───────────────────────────────
@team_bp.route("/invites/<invite_id>/respond", methods=["POST"])
def respond_invite(invite_id):
    try:
        from bson import ObjectId
        data    = request.get_json() or {}
        user_id = data.get("user_id")
        accept  = bool(data.get("accept"))

        db   = get_db()
        user = _user_or_none(db, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        invite = db.team_invites.find_one({"_id": ObjectId(invite_id)})
        if not invite or invite["status"] != "pending":
            return jsonify({"error": "Invite not found or already handled"}), 404
        if invite["invited_email"] != user.get("email", "").lower():
            return jsonify({"error": "This invite is not addressed to you"}), 403

        if accept:
            if is_team_member(db, user_id, invite["team_id"]):
                return jsonify({"error": "You already belong to this team"}), 409

            db.team_memberships.insert_one({
                "team_id"  : invite["team_id"],
                "team_name": invite.get("team_name", ""),
                "user_id"  : user_id,
                "role"     : "member",
                "joined_at": datetime.utcnow().isoformat(),
            })
            db.team_invites.update_one({"_id": ObjectId(invite_id)}, {"$set": {"status": "accepted"}})

            if invite.get("invited_by"):
                push_notification(
                    db, invite["invited_by"], "team_joined",
                    "New Team Member",
                    f"{user.get('name', 'Someone')} joined \"{invite.get('team_name', '')}\"",
                    {"team_id": invite["team_id"]},
                )
            return jsonify({"message": "Joined team", "team_id": invite["team_id"]}), 200
        else:
            db.team_invites.update_one({"_id": ObjectId(invite_id)}, {"$set": {"status": "declined"}})

            if invite.get("invited_by"):
                push_notification(
                    db, invite["invited_by"], "invite_declined",
                    "Invite Declined",
                    f"{user.get('name', 'Someone')} declined your invite to \"{invite.get('team_name', '')}\"",
                    {},
                )
            return jsonify({"message": "Invite declined"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── DELETE /api/team/members/<member_id>?user_id=&team_id= ───────────────────
@team_bp.route("/members/<member_id>", methods=["DELETE"])
def remove_member(member_id):
    try:
        requester_id = request.args.get("user_id")
        team_id      = request.args.get("team_id")

        db = get_db()
        if team_role(db, requester_id, team_id) != "owner":
            return jsonify({"error": "Only the team owner can remove members"}), 403
        if member_id == requester_id:
            return jsonify({"error": "Use Leave Team to remove yourself"}), 400
        if not is_team_member(db, member_id, team_id):
            return jsonify({"error": "Member not found in this team"}), 404

        team = db.teams.find_one({"_id": __import__("bson").ObjectId(team_id)})
        db.team_memberships.delete_one({"team_id": team_id, "user_id": member_id})

        push_notification(
            db, member_id, "member_removed",
            "Removed from Team",
            f"You were removed from \"{team.get('name', '') if team else ''}\"",
            {"team_id": team_id},
        )
        return jsonify({"message": "Member removed"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/team/leave ──────────────────────────────────────────────────────
# Member leaving: just removes that one membership, team carries on.
# Owner leaving: disbands the WHOLE team — every member is kicked back to
# personal, and every upload/history/analysis/note that belonged to this
# team reverts to personal (team_id cleared) so nothing is silently lost.
@team_bp.route("/leave", methods=["POST"])
def leave_team():
    try:
        data    = request.get_json() or {}
        user_id = data.get("user_id")
        team_id = data.get("team_id")

        db   = get_db()
        role = team_role(db, user_id, team_id)
        if not role:
            return jsonify({"error": "You are not in this team"}), 400

        if role == "owner":
            team = db.teams.find_one({"_id": __import__("bson").ObjectId(team_id)})
            team_name = team.get("name", "") if team else ""

            other_members = list(db.team_memberships.find({
                "team_id": team_id, "user_id": {"$ne": user_id}
            }))

            for m in other_members:
                push_notification(
                    db, m["user_id"], "team_disbanded",
                    "Team Disbanded",
                    f"\"{team_name}\" was disbanded because the owner switched to a personal account. "
                    f"Your data from this project is now personal.",
                    {"team_id": team_id},
                )

            db.team_memberships.delete_many({"team_id": team_id})
            db.teams.delete_one({"_id": __import__("bson").ObjectId(team_id)})

            # Revert every record that belonged to this team back to personal.
            db.uploads.update_many({"team_id": team_id}, {"$set": {"team_id": None}})
            db.history.update_many({"team_id": team_id}, {"$set": {"team_id": None}})
            db.analysis.update_many({"team_id": team_id}, {"$set": {"team_id": None}})
            db.notes.update_many({"scope_key": f"team:{team_id}"}, {"$set": {"scope_key": f"personal:{user_id}"}})

        else:
            db.team_memberships.delete_one({"team_id": team_id, "user_id": user_id})
            owner_m = db.team_memberships.find_one({"team_id": team_id, "role": "owner"})
            user = _user_or_none(db, user_id)
            if owner_m:
                push_notification(
                    db, owner_m["user_id"], "member_left",
                    "Member Left",
                    f"{user.get('name', 'Someone') if user else 'Someone'} left \"{owner_m.get('team_name', '')}\"",
                    {},
                )

        return jsonify({"message": "Left team"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
