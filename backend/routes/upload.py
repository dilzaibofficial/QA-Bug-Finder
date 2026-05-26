from flask import Blueprint, request, jsonify
from datetime import datetime
from pathlib import Path
import os, sys, uuid, shutil, zipfile, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, r"d:\Zainab FYP\model_training")

from db import get_db
import config

upload_bp = Blueprint("upload", __name__)


def _allowed(filename):
    return Path(filename).suffix.lower() in config.ALLOWED_EXT


def _claude_enhance(bug_doc: dict) -> dict:
    """Call Claude API to enhance a single bug's analysis. Returns extra fields."""
    if not config.CLAUDE_API_KEY or config.CLAUDE_API_KEY == "your_claude_api_key_here":
        return {}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

        snippet_line = bug_doc.get("code_snippet", "").strip()
        snippet_block = f"\nActual code at line {bug_doc.get('line_number', '?')}:\n```\n{snippet_line}\n```" if snippet_line else ""

        prompt = f"""You are a senior software engineer reviewing a bug detected by an ML model.

File: {bug_doc.get('file', 'unknown')}
Bug Type: {bug_doc.get('type', 'Unknown')} | Severity: {bug_doc.get('severity', 'Medium')}{snippet_block}

ML Model found:
- Description: {bug_doc.get('description', '')}
- AI Reason: {bug_doc.get('ai_reason', '')}
- Suggested Fix: {bug_doc.get('suggested_fix', '')}

Your task — respond ONLY with valid JSON (no markdown, no explanation outside the JSON):
{{
  "enhanced_description": "Clear 2-sentence explanation of what this bug is and why it matters",
  "enhanced_reason": "Technical explanation of why the AI flagged this, referencing code metrics or patterns",
  "corrected_code": "The actual corrected version of the buggy line/block (real code, not a description)",
  "fix_explanation": "Brief explanation of what you changed and why (2-3 sentences)"
}}"""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        import json as _json
        text = msg.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
            text = text.rsplit("```", 1)[0].strip()
        data = _json.loads(text)
        return {
            "claude_enhanced"    : True,
            "claude_description" : data.get("enhanced_description", ""),
            "claude_reason"      : data.get("enhanced_reason", ""),
            "claude_corrected_code" : data.get("corrected_code", ""),
            "claude_fix_explanation": data.get("fix_explanation", ""),
        }
    except Exception as ex:
        return {"claude_enhanced": False, "claude_error": str(ex)}


def _run_analysis(file_path: str, filename: str, analysis_id: str, use_claude: bool = False):
    """Run ML predictor on uploaded file and store results in MongoDB."""
    db = get_db()
    db.analysis.update_one({"_id": analysis_id},
                           {"$set": {"status": "processing"}})
    try:
        from predictor import BugPredictor
        predictor = BugPredictor()

        ext = Path(filename).suffix.lower()
        if ext == ".zip":
            raw_bugs = predictor.analyze_zip(file_path)
        else:
            raw_bugs = predictor.analyze_file(file_path)

        import re as _re

        def _clean_fname(raw, original):
            """Remove UUID prefix like 'abc123_file.py' → 'file.py'"""
            cleaned = _re.sub(r'^[a-f0-9]{32}_', '', str(raw))
            return cleaned if cleaned else original

        # For ZIP: extract to temp dir so we can read individual file lines
        is_zip = Path(filename).suffix.lower() == ".zip"
        zip_tmpdir = None
        zip_file_map = {}  # basename -> full path inside tmpdir
        if is_zip:
            zip_tmpdir = tempfile.mkdtemp(prefix="bugdet_")
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    zf.extractall(zip_tmpdir)
                for root, _, files in os.walk(zip_tmpdir):
                    for f in files:
                        zip_file_map[f] = os.path.join(root, f)
                        # also store relative path key for deeper paths
                        rel = os.path.relpath(os.path.join(root, f), zip_tmpdir)
                        zip_file_map[rel.replace("\\", "/")] = os.path.join(root, f)
            except Exception:
                pass

        def _read_line(bug_filename: str, line_no: int) -> str:
            """Return the actual source line at line_no, stripped."""
            if line_no <= 0:
                return ""
            try:
                if is_zip:
                    # try exact name match, then basename match
                    target = zip_file_map.get(bug_filename) or \
                             zip_file_map.get(Path(bug_filename).name)
                    if not target:
                        return ""
                    src = target
                else:
                    src = file_path

                ext = Path(src).suffix.lower()
                if ext in (".zip",):
                    return ""
                with open(src, encoding="utf-8", errors="replace") as fh:
                    for idx, line in enumerate(fh, start=1):
                        if idx == line_no:
                            return line.rstrip()
            except Exception:
                pass
            return ""

        # Save each bug to DB
        bugs_inserted = []
        for i, bug in enumerate(raw_bugs, start=1):
            clean_file = _clean_fname(bug.get("file", filename), filename)
            line_no    = bug.get("line_number", 0)
            snippet    = _read_line(clean_file, line_no)

            bug_doc = {
                "analysis_id"       : analysis_id,
                "bug_id"            : bug.get("bug_id", f"BUG-{str(i).zfill(3)}"),
                "type"              : bug.get("type", "Logical"),
                "severity"          : bug.get("severity", "Medium"),
                "file"              : clean_file,
                "line_number"       : line_no,
                "description"       : bug.get("description", ""),
                "ai_reason"         : bug.get("ai_reason", ""),
                "suggested_fix"     : bug.get("suggested_fix", ""),
                "code_snippet"      : snippet,
                "assigned_to"       : bug.get("assigned_to", "Developer"),
                "status"            : "Open",
                "defect_probability": bug.get("defect_probability", 0),
                "type_confidence"   : bug.get("type_confidence", 0),
                "created_at"        : datetime.utcnow().isoformat(),
                "claude_enhanced"   : False,
            }

            # Claude enhancement (if enabled)
            if use_claude:
                claude_data = _claude_enhance(bug_doc)
                bug_doc.update(claude_data)

            r = db.bugs.insert_one(bug_doc)
            bug_doc["_id"] = str(r.inserted_id)
            bugs_inserted.append(bug_doc)

        # Cleanup temp dir for ZIP
        if zip_tmpdir:
            try:
                shutil.rmtree(zip_tmpdir, ignore_errors=True)
            except Exception:
                pass

        total    = len(bugs_inserted)
        critical = sum(1 for b in bugs_inserted if b["severity"] == "Critical")

        db.analysis.update_one({"_id": analysis_id}, {"$set": {
            "status"       : "completed",
            "total_bugs"   : total,
            "critical_bugs": critical,
            "end_time"     : datetime.utcnow().isoformat(),
        }})
        return total, critical

    except Exception as e:
        db.analysis.update_one({"_id": analysis_id},
                               {"$set": {"status": "failed", "error": str(e)}})
        raise e


# ── POST /api/upload ─────────────────────────────────────────────────────────
@upload_bp.route("", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file      = request.files["file"]
    user_id   = request.form.get("user_id", "demo_user")
    use_claude = request.form.get("use_claude", "false").lower() == "true"

    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    if not _allowed(file.filename):
        return jsonify({"error": f"File type not supported. Use: {', '.join(config.ALLOWED_EXT)}"}), 400

    # Save file
    safe_name   = f"{uuid.uuid4().hex}_{file.filename}"
    save_path   = os.path.join(config.UPLOAD_DIR, safe_name)
    file.save(save_path)

    file_size = os.path.getsize(save_path)
    if file_size > config.MAX_FILE_MB * 1024 * 1024:
        os.remove(save_path)
        return jsonify({"error": f"File too large (max {config.MAX_FILE_MB}MB)"}), 413

    db = get_db()
    analysis_id = str(uuid.uuid4())

    # Save upload record
    upload_doc = {
        "user_id"    : user_id,
        "filename"   : file.filename,
        "saved_as"   : safe_name,
        "file_path"  : save_path,
        "file_size"  : file_size,
        "file_type"  : Path(file.filename).suffix.upper().lstrip("."),
        "upload_date": datetime.utcnow().isoformat(),
        "analysis_id": analysis_id,
        "status"     : "uploaded",
    }
    upload_result = db.uploads.insert_one(upload_doc)
    upload_id     = str(upload_result.inserted_id)

    # Create analysis record
    db.analysis.insert_one({
        "_id"         : analysis_id,
        "upload_id"   : upload_id,
        "user_id"     : user_id,
        "filename"    : file.filename,
        "start_time"  : datetime.utcnow().isoformat(),
        "status"      : "queued",
        "total_bugs"  : 0,
        "critical_bugs": 0,
    })

    # Run analysis (synchronous for now)
    try:
        total, critical = _run_analysis(save_path, file.filename, analysis_id, use_claude)
        progress = 75 if total > 0 else 100

        # Save to history
        db.history.insert_one({
            "user_id"        : user_id,
            "upload_id"      : upload_id,
            "analysis_id"    : analysis_id,
            "filename"       : file.filename,
            "file_type"      : Path(file.filename).suffix.upper().lstrip("."),
            "file_path"      : f"/uploads/{safe_name}",
            "analyzed_on"    : datetime.utcnow().isoformat(),
            "total_bugs"     : total,
            "critical_bugs"  : critical,
            "status"         : "completed",
            "progress"       : progress,
        })

        return jsonify({
            "message"     : "File uploaded and analyzed successfully",
            "upload_id"   : upload_id,
            "analysis_id" : analysis_id,
            "filename"    : file.filename,
            "total_bugs"  : total,
            "critical_bugs": critical,
        }), 200

    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


# ── GET /api/upload/status/<analysis_id> ─────────────────────────────────────
@upload_bp.route("/status/<analysis_id>", methods=["GET"])
def get_status(analysis_id):
    db  = get_db()
    rec = db.analysis.find_one({"_id": analysis_id})
    if not rec:
        return jsonify({"error": "Analysis not found"}), 404
    rec.pop("_id", None)
    return jsonify(rec), 200
