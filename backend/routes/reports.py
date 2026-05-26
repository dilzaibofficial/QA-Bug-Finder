from flask import Blueprint, request, jsonify
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db

reports_bp = Blueprint("reports", __name__)


def _safe(doc):
    doc["_id"] = str(doc["_id"])
    return doc


# ── GET /api/reports?user_id=xxx ─────────────────────────────────────────────
@reports_bp.route("", methods=["GET"])
def get_reports():
    try:
        user_id     = request.args.get("user_id", "demo_user")
        analysis_id = request.args.get("analysis_id")
        severity    = request.args.get("severity")
        bug_type    = request.args.get("type")
        status      = request.args.get("status")

        db    = get_db()
        query = {}

        if analysis_id:
            query["analysis_id"] = analysis_id
        else:
            latest = db.analysis.find_one(
                {"user_id": user_id, "status": "completed"},
                sort=[("start_time", -1)]
            )
            if not latest:
                return jsonify({"bugs": [], "total": 0, "analysis": None}), 200
            query["analysis_id"] = str(latest["_id"])

        if severity and severity != "All Severities":
            query["severity"] = severity
        if bug_type and bug_type != "All Types":
            query["type"] = bug_type
        if status and status != "All Statuses":
            query["status"] = status

        bugs = list(db.bugs.find(query))
        for b in bugs:
            b["_id"] = str(b["_id"])
            # ensure all expected fields exist
            b.setdefault("bug_id",             "—")
            b.setdefault("type",               "Unknown")
            b.setdefault("severity",           "Medium")
            b.setdefault("file",               "—")
            b.setdefault("line_number",        0)
            b.setdefault("description",        "")
            b.setdefault("ai_reason",          "")
            b.setdefault("suggested_fix",      "")
            b.setdefault("code_snippet",          "")
            b.setdefault("claude_enhanced",       False)
            b.setdefault("claude_description",    "")
            b.setdefault("claude_reason",         "")
            b.setdefault("claude_corrected_code", "")
            b.setdefault("claude_fix_explanation","")
            b.setdefault("assigned_to",           "Developer")
            b.setdefault("status",             "Open")
            b.setdefault("defect_probability", 0)
            b.setdefault("type_confidence",    0)

        # Analysis info
        aid = query.get("analysis_id", "")
        analysis_doc = db.analysis.find_one({"_id": aid}) if aid else None
        analysis_info = None
        if analysis_doc:
            upload = db.uploads.find_one({"analysis_id": aid})
            analysis_info = {
                "analysis_id"  : str(analysis_doc["_id"]),
                "filename"     : analysis_doc.get("filename", ""),
                "start_time"   : analysis_doc.get("start_time", ""),
                "end_time"     : analysis_doc.get("end_time", ""),
                "total_bugs"   : analysis_doc.get("total_bugs", 0),
                "critical_bugs": analysis_doc.get("critical_bugs", 0),
                "status"       : analysis_doc.get("status", ""),
                "file_size"    : upload.get("file_size", 0) if upload else 0,
            }

        return jsonify({"bugs": bugs, "total": len(bugs), "analysis": analysis_info}), 200

    except Exception as e:
        return jsonify({"error": str(e), "bugs": [], "total": 0, "analysis": None}), 500


# ── PUT /api/reports/bug/<bug_doc_id>/status ─────────────────────────────────
@reports_bp.route("/bug/<bug_doc_id>/status", methods=["PUT"])
def update_bug_status(bug_doc_id):
    try:
        from bson import ObjectId
        data       = request.get_json() or {}
        new_status = data.get("status")
        allowed    = {"Open", "In Progress", "Fixed", "Reopened", "Close"}

        if new_status not in allowed:
            return jsonify({"error": f"Invalid status. Choose: {sorted(allowed)}"}), 400

        db = get_db()
        result = db.bugs.update_one(
            {"_id": ObjectId(bug_doc_id)},
            {"$set": {"status": new_status, "updated_at": datetime.utcnow().isoformat()}}
        )
        if result.matched_count == 0:
            return jsonify({"error": "Bug not found"}), 404
        return jsonify({"message": "Status updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/reports/summary?user_id=xxx ─────────────────────────────────────
@reports_bp.route("/summary", methods=["GET"])
def get_summary():
    try:
        user_id = request.args.get("user_id", "demo_user")
        db      = get_db()

        latest = db.analysis.find_one(
            {"user_id": user_id, "status": "completed"},
            sort=[("start_time", -1)]
        )
        if not latest:
            return jsonify({"total_bugs": 0, "critical": 0, "by_type": {}, "by_severity": {}, "by_status": {}}), 200

        bugs = list(db.bugs.find({"analysis_id": str(latest["_id"])}))

        by_type     = {}
        by_severity = {}
        by_status   = {}
        for b in bugs:
            bt = b.get("type", "Unknown")
            bs = b.get("severity", "Medium")
            bst = b.get("status", "Open")
            by_type[bt]     = by_type.get(bt, 0) + 1
            by_severity[bs] = by_severity.get(bs, 0) + 1
            by_status[bst]  = by_status.get(bst, 0) + 1

        return jsonify({
            "total_bugs" : len(bugs),
            "critical"   : sum(1 for b in bugs if b.get("severity") == "Critical"),
            "by_type"    : by_type,
            "by_severity": by_severity,
            "by_status"  : by_status,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
