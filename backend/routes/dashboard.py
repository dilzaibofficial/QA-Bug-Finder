from flask import Blueprint, request, jsonify
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, scope_query, is_team_member

dashboard_bp = Blueprint("dashboard", __name__)


# ── GET /api/dashboard/stats?user_id=xxx&team_id=yyy ──────────────────────────
# team_id omitted/empty = the user's personal bucket. team_id set = that
# project's shared stats (every member sees the same numbers).
@dashboard_bp.route("/stats", methods=["GET"])
def get_stats():
    try:
        user_id = request.args.get("user_id", "demo_user")
        team_id = request.args.get("team_id") or None
        db      = get_db()

        if team_id and not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of this project"}), 403

        query = scope_query(user_id, team_id)

        total_uploads = db.uploads.count_documents(query)

        analyses  = [str(a["_id"]) for a in db.analysis.find(query)]
        all_bugs  = list(db.bugs.find({"analysis_id": {"$in": analyses}})) if analyses else []

        total_bugs    = len(all_bugs)
        critical_bugs = sum(1 for b in all_bugs if b.get("severity") == "Critical")

        fixed       = sum(1 for b in all_bugs if b.get("status") == "Fixed")
        in_progress = sum(1 for b in all_bugs if b.get("status") == "In Progress")
        pending     = sum(1 for b in all_bugs if b.get("status") == "Open")

        def pct(n): return round(n / max(1, total_bugs) * 100)

        return jsonify({
            "total_uploads": total_uploads,
            "total_bugs"   : total_bugs,
            "critical_bugs": critical_bugs,
            "bug_status"   : {"fixed": fixed, "in_progress": in_progress, "pending": pending},
            "progress"     : {
                "uploads" : min(pct(total_uploads) * 2, 100),
                "bugs"    : pct(total_bugs),
                "critical": pct(critical_bugs),
            },
        }), 200

    except Exception as e:
        return jsonify({
            "error"        : str(e),
            "total_uploads": 0,
            "total_bugs"   : 0,
            "critical_bugs": 0,
            "bug_status"   : {"fixed": 0, "in_progress": 0, "pending": 0},
            "progress"     : {"uploads": 0, "bugs": 0, "critical": 0},
        }), 500
