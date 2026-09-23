from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
from pathlib import Path
import os, sys, uuid, shutil, zipfile, tempfile, io

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "model_training"))

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


def _run_analysis(file_path: str, filename: str, analysis_id: str, use_claude: bool = False,
                   extract_to: str = None, overwrite: bool = True):
    """
    Run ML predictor on uploaded file and store results in MongoDB.
    extract_to/overwrite are forwarded to the zip extractor — a re-run
    (overwrite=False) re-scans the existing working copy instead of
    clobbering it, so edits made via the in-app editor or an external
    editor (VS Code) survive a "Re-run Analysis".
    """
    db = get_db()
    db.analysis.update_one({"_id": analysis_id},
                           {"$set": {"status": "processing"}})
    try:
        from predictor import BugPredictor
        predictor = BugPredictor()

        ext = Path(filename).suffix.lower()
        if ext == ".zip":
            raw_bugs = predictor.analyze_zip(file_path, extract_to=extract_to, overwrite=overwrite)
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


def _persist_bug_docs(db, analysis_id, raw_bugs, file_path, use_claude=False):
    """
    Build+insert bug docs for ONE already-resolved file (single-file
    reanalysis — no zip handling needed, the caller already picked the
    exact on-disk file). Mirrors _run_analysis's bug_doc shape so reports
    and the code viewer read identically either way.
    """
    def _read_line(line_no):
        if line_no <= 0:
            return ""
        try:
            with open(file_path, encoding="utf-8", errors="replace") as fh:
                for idx, line in enumerate(fh, start=1):
                    if idx == line_no:
                        return line.rstrip()
        except Exception:
            pass
        return ""

    bugs_inserted = []
    for i, bug in enumerate(raw_bugs, start=1):
        bug_doc = {
            "analysis_id"       : analysis_id,
            "bug_id"            : bug.get("bug_id", f"BUG-{str(i).zfill(3)}"),
            "type"              : bug.get("type", "Logical"),
            "severity"          : bug.get("severity", "Medium"),
            "file"              : bug.get("file", ""),
            "line_number"       : bug.get("line_number", 0),
            "description"       : bug.get("description", ""),
            "ai_reason"         : bug.get("ai_reason", ""),
            "suggested_fix"     : bug.get("suggested_fix", ""),
            "code_snippet"      : _read_line(bug.get("line_number", 0)),
            "assigned_to"       : bug.get("assigned_to", "Developer"),
            "status"            : "Open",
            "defect_probability": bug.get("defect_probability", 0),
            "type_confidence"   : bug.get("type_confidence", 0),
            "created_at"        : datetime.utcnow().isoformat(),
            "claude_enhanced"   : False,
        }
        if use_claude:
            bug_doc.update(_claude_enhance(bug_doc))
        r = db.bugs.insert_one(bug_doc)
        bug_doc["_id"] = str(r.inserted_id)
        bugs_inserted.append(bug_doc)
    return bugs_inserted


def _canonical_unzip_dir(rec):
    """
    The one stable extraction folder for a zip upload — same path
    BugPredictor.analyze_zip() uses by default (UPLOAD_DIR/<saved_as
    minus .zip>_unzipped), so viewing, editing and reanalyzing a zip
    member all read/write the exact same working copy.
    """
    return os.path.join(config.UPLOAD_DIR, f"{Path(rec['saved_as']).stem}_unzipped")


def _resolve_edit_path(rec, upload_id, req_path):
    """
    Resolve (abs_path, display_name, error) for a file inside an upload,
    on disk. For a zip member this extracts (once — reused after that)
    into the canonical working copy, so a save here is a save an editor
    or a later reanalysis will also see.
    Returns (abs_path, display_name, None) or (None, None, error_message).
    """
    file_path = rec.get("file_path", "")
    file_type = rec.get("file_type", "").upper()

    if file_type == "ZIP":
        if not os.path.exists(file_path):
            return None, None, "Original zip no longer available"
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            target = req_path if req_path in names else None
            if not target:
                base = Path(req_path).name
                for n in names:
                    if Path(n).name == base:
                        target = n
                        break
            if not target:
                return None, None, "File not found in archive"

            extract_dir  = _canonical_unzip_dir(rec)
            extract_path = os.path.join(extract_dir, *target.split("/"))
            os.makedirs(os.path.dirname(extract_path), exist_ok=True)
            if not os.path.exists(extract_path):
                raw = zf.read(target)
                with open(extract_path, "wb") as out:
                    out.write(raw)
        return os.path.abspath(extract_path), target, None
    else:
        if not os.path.exists(file_path):
            return None, None, "Original file no longer available"
        return os.path.abspath(file_path), rec["filename"], None


# ── POST /api/upload ─────────────────────────────────────────────────────────
@upload_bp.route("", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file      = request.files["file"]
    user_id   = request.form.get("user_id", "demo_user")
    team_id   = request.form.get("team_id") or None
    use_claude = request.form.get("use_claude", "false").lower() == "true"

    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    if not _allowed(file.filename):
        return jsonify({"error": f"File type not supported. Use: {', '.join(config.ALLOWED_EXT)}"}), 400

    db = get_db()
    if team_id:
        from db import is_team_member
        if not is_team_member(db, user_id, team_id):
            return jsonify({"error": "You are not a member of that project"}), 403

    # Save file
    safe_name   = f"{uuid.uuid4().hex}_{file.filename}"
    save_path   = os.path.join(config.UPLOAD_DIR, safe_name)
    file.save(save_path)

    file_size = os.path.getsize(save_path)
    if file_size > config.MAX_FILE_MB * 1024 * 1024:
        os.remove(save_path)
        return jsonify({"error": f"File too large (max {config.MAX_FILE_MB}MB)"}), 413

    analysis_id = str(uuid.uuid4())

    # Save upload record
    upload_doc = {
        "user_id"    : user_id,
        "team_id"    : team_id,
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
        "team_id"     : team_id,
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
            "team_id"        : team_id,
            "upload_id"      : upload_id,
            "analysis_id"    : analysis_id,
            "filename"       : file.filename,
            "file_type"      : Path(file.filename).suffix.upper().lstrip("."),
            "file_path"      : f"/uploads/{safe_name}",
            "file_size"      : file_size,
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


def _bug_counts_by_file(db, analysis_id):
    """basename -> bug count, for annotating a file tree."""
    counts = {}
    if not analysis_id:
        return counts
    for b in db.bugs.find({"analysis_id": analysis_id}, {"file": 1}):
        key = Path(b.get("file", "")).name
        counts[key] = counts.get(key, 0) + 1
    return counts


# ── GET /api/upload/tree/<upload_id> ──────────────────────────────────────────
# Real file structure of the uploaded file (zip contents, or the single
# uploaded file), annotated with how many bugs the ML model found per file.
@upload_bp.route("/tree/<upload_id>", methods=["GET"])
def get_upload_tree(upload_id):
    try:
        from bson import ObjectId
        db  = get_db()
        rec = db.uploads.find_one({"_id": ObjectId(upload_id)})
        if not rec:
            return jsonify({"error": "Upload not found"}), 404

        bug_counts = _bug_counts_by_file(db, rec.get("analysis_id"))
        file_path  = rec.get("file_path", "")
        file_type  = rec.get("file_type", "").upper()

        if file_type == "ZIP" and os.path.exists(file_path):
            root = {"name": rec["filename"], "type": "folder", "path": "", "children": []}
            node_index = {"": root}

            with zipfile.ZipFile(file_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    parts = [p for p in info.filename.replace("\\", "/").split("/") if p]
                    if not parts:
                        continue

                    cur_path = ""
                    for i, part in enumerate(parts):
                        parent_path = cur_path
                        cur_path = f"{cur_path}/{part}" if cur_path else part
                        is_last = i == len(parts) - 1

                        if cur_path in node_index:
                            continue

                        node = {
                            "name": part,
                            "path": cur_path,
                            "type": "file" if is_last else "folder",
                        }
                        if is_last:
                            node["size"]     = info.file_size
                            node["bugCount"] = bug_counts.get(part, 0)
                        else:
                            node["children"] = []

                        node_index[cur_path] = node
                        node_index[parent_path]["children"].append(node)

            tree = root["children"]
        else:
            tree = [{
                "name"    : rec["filename"],
                "path"    : rec["filename"],
                "type"    : "file",
                "size"    : rec.get("file_size", 0),
                "bugCount": bug_counts.get(Path(rec["filename"]).name, 0),
            }]

        return jsonify({
            "filename"   : rec["filename"],
            "file_type"  : rec.get("file_type", ""),
            "size"       : rec.get("file_size", 0),
            "upload_date": rec.get("upload_date", ""),
            "analysis_id": rec.get("analysis_id", ""),
            "tree"       : tree,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/upload/content/<upload_id>?path=... ──────────────────────────────
# Real source content of one file inside the upload (zip member or the
# uploaded file itself), plus the bugs the ML model found in it.
@upload_bp.route("/content/<upload_id>", methods=["GET"])
def get_upload_content(upload_id):
    try:
        from bson import ObjectId
        db   = get_db()
        rec  = db.uploads.find_one({"_id": ObjectId(upload_id)})
        if not rec:
            return jsonify({"error": "Upload not found"}), 404

        req_path  = request.args.get("path", "")
        MAX_BYTES = 300_000

        abs_path, display_name, err = _resolve_edit_path(rec, upload_id, req_path)
        if err:
            return jsonify({"error": err}), 404

        with open(abs_path, "rb") as fh:
            raw = fh.read()

        truncated = len(raw) > MAX_BYTES
        content   = raw[:MAX_BYTES].decode("utf-8", errors="replace")

        basename = Path(display_name).name
        bugs = list(db.bugs.find({
            "analysis_id": rec.get("analysis_id"),
            "file": {"$regex": f"(^|/){basename}$"},
        }))
        for b in bugs:
            b["_id"] = str(b["_id"])

        return jsonify({
            "filename" : display_name,
            "content"  : content,
            "truncated": truncated,
            "bugs"     : bugs,
            "abs_path" : abs_path,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/upload/abs-path/<upload_id>?path=... ─────────────────────────────
# Just the on-disk path — for the "Open in VS Code" button on screens that
# don't otherwise need the file's content (the file list, file structure).
@upload_bp.route("/abs-path/<upload_id>", methods=["GET"])
def get_abs_path(upload_id):
    try:
        from bson import ObjectId
        db  = get_db()
        rec = db.uploads.find_one({"_id": ObjectId(upload_id)})
        if not rec:
            return jsonify({"error": "Upload not found"}), 404

        req_path = request.args.get("path", "")

        # No specific member requested on a zip upload — open the whole
        # extracted project folder in VS Code rather than erroring.
        if not req_path and rec.get("file_type", "").upper() == "ZIP":
            file_path = rec.get("file_path", "")
            if not os.path.exists(file_path):
                return jsonify({"error": "Original zip no longer available"}), 404
            extract_dir = _canonical_unzip_dir(rec)
            os.makedirs(extract_dir, exist_ok=True)
            if not os.listdir(extract_dir):
                with zipfile.ZipFile(file_path, "r") as zf:
                    zf.extractall(extract_dir)
            return jsonify({"abs_path": os.path.abspath(extract_dir), "filename": rec["filename"]}), 200

        abs_path, display_name, err = _resolve_edit_path(rec, upload_id, req_path)
        if err:
            return jsonify({"error": err}), 404

        return jsonify({"abs_path": abs_path, "filename": display_name}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _log_activity(db, upload_id, analysis_id, user_id, user_name, action, file,
                   bugs_before, bugs_after, total_bugs, critical_bugs):
    db.file_activity.insert_one({
        "upload_id"    : upload_id,
        "analysis_id"  : analysis_id,
        "user_id"      : user_id,
        "user_name"    : user_name or "Someone",
        "action"       : action,
        "file"         : file,
        "bugs_before"  : bugs_before,
        "bugs_after"   : bugs_after,
        "total_bugs"   : total_bugs,
        "critical_bugs": critical_bugs,
        "created_at"   : datetime.utcnow().isoformat(),
    })


# ── POST /api/upload/<upload_id>/reanalyze-file ───────────────────────────────
# Save edited content for ONE file in the upload and re-run the ML model on
# just that file — the in-app "fix the bug, then reanalyze" loop.
@upload_bp.route("/<upload_id>/reanalyze-file", methods=["POST"])
def reanalyze_file(upload_id):
    try:
        from bson import ObjectId
        data     = request.get_json() or {}
        user_id  = data.get("user_id", "demo_user")
        user_name = data.get("user_name", "Someone")
        req_path = data.get("path", "")
        content  = data.get("content", "")

        db  = get_db()
        rec = db.uploads.find_one({"_id": ObjectId(upload_id)})
        if not rec:
            return jsonify({"error": "Upload not found"}), 404

        analysis_id = rec.get("analysis_id")
        abs_path, display_name, err = _resolve_edit_path(rec, upload_id, req_path)
        if err:
            return jsonify({"error": err}), 404

        with open(abs_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)

        basename = Path(display_name).name
        bugs_before = db.bugs.count_documents({"analysis_id": analysis_id, "file": basename})

        from predictor import BugPredictor
        raw_bugs = BugPredictor().analyze_file(abs_path)

        db.bugs.delete_many({"analysis_id": analysis_id, "file": basename})
        new_bugs = _persist_bug_docs(db, analysis_id, raw_bugs, abs_path, use_claude=False)

        total_bugs    = db.bugs.count_documents({"analysis_id": analysis_id})
        critical_bugs = db.bugs.count_documents({"analysis_id": analysis_id, "severity": "Critical"})
        db.analysis.update_one({"_id": analysis_id}, {"$set": {
            "total_bugs": total_bugs, "critical_bugs": critical_bugs,
        }})
        db.history.update_one({"analysis_id": analysis_id}, {"$set": {
            "total_bugs": total_bugs, "critical_bugs": critical_bugs,
        }})

        _log_activity(db, upload_id, analysis_id, user_id, user_name, "reanalyze_file",
                      basename, bugs_before, len(new_bugs), total_bugs, critical_bugs)

        return jsonify({
            "bugs"         : new_bugs,
            "bugs_before"  : bugs_before,
            "bugs_after"   : len(new_bugs),
            "total_bugs"   : total_bugs,
            "critical_bugs": critical_bugs,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/upload/<upload_id>/reanalyze ────────────────────────────────────
# Re-run the FULL upload (all files, for a zip) against whatever is
# currently on disk — picks up edits made via the in-app editor OR an
# external editor like VS Code (doesn't re-extract over them).
@upload_bp.route("/<upload_id>/reanalyze", methods=["POST"])
def reanalyze_upload(upload_id):
    try:
        from bson import ObjectId
        data      = request.get_json() or {}
        user_id   = data.get("user_id", "demo_user")
        user_name = data.get("user_name", "Someone")

        db  = get_db()
        rec = db.uploads.find_one({"_id": ObjectId(upload_id)})
        if not rec:
            return jsonify({"error": "Upload not found"}), 404

        file_path = rec.get("file_path", "")
        if not os.path.exists(file_path):
            return jsonify({"error": "Original file no longer available"}), 404

        old_analysis_id = rec.get("analysis_id")
        bugs_before = db.bugs.count_documents({"analysis_id": old_analysis_id}) if old_analysis_id else 0

        new_analysis_id = str(uuid.uuid4())
        db.analysis.insert_one({
            "_id"          : new_analysis_id,
            "upload_id"    : upload_id,
            "user_id"      : rec.get("user_id"),
            "team_id"      : rec.get("team_id"),
            "filename"     : rec["filename"],
            "start_time"   : datetime.utcnow().isoformat(),
            "status"       : "queued",
            "total_bugs"   : 0,
            "critical_bugs": 0,
        })

        total, critical = _run_analysis(file_path, rec["filename"], new_analysis_id,
                                         use_claude=False, overwrite=False)

        # This new run is now "the" analysis for this upload — TLU/History/
        # Reports should all point at it from here on.
        db.uploads.update_one({"_id": ObjectId(upload_id)}, {"$set": {"analysis_id": new_analysis_id}})
        db.history.update_one({"upload_id": upload_id}, {"$set": {
            "analysis_id": new_analysis_id, "total_bugs": total, "critical_bugs": critical,
            "analyzed_on": datetime.utcnow().isoformat(), "status": "completed",
        }})

        _log_activity(db, upload_id, new_analysis_id, user_id, user_name, "reanalyze_full",
                      None, bugs_before, total, total, critical)

        return jsonify({
            "analysis_id"  : new_analysis_id,
            "total_bugs"   : total,
            "critical_bugs": critical,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/upload/<upload_id>/activity?path=... ─────────────────────────────
# Who reanalyzed / edited this file (or the whole upload) and when — the
# audit trail shown on the code viewer's History panel.
@upload_bp.route("/<upload_id>/activity", methods=["GET"])
def get_activity(upload_id):
    try:
        from db import hydrate_sender_info
        req_path = request.args.get("path", "")
        basename = Path(req_path).name if req_path else None

        db = get_db()
        query = {"upload_id": upload_id}
        if basename:
            query["file"] = {"$in": [basename, None]}
        items = list(db.file_activity.find(query).sort("created_at", -1).limit(50))
        for a in items:
            a["_id"] = str(a["_id"])
        hydrate_sender_info(db, items, "user_id", "user_avatar", "user_verified")

        return jsonify({"activity": items}), 200

    except Exception as e:
        return jsonify({"error": str(e), "activity": []}), 500


# ── GET /api/upload/download/<upload_id>?path=... ────────────────────────────
# Real file download — the whole upload, or (for a zip) one file inside it.
@upload_bp.route("/download/<upload_id>", methods=["GET"])
def download_upload(upload_id):
    try:
        from bson import ObjectId
        db   = get_db()
        rec  = db.uploads.find_one({"_id": ObjectId(upload_id)})
        if not rec:
            return jsonify({"error": "Upload not found"}), 404

        req_path  = request.args.get("path", "")
        file_path = rec.get("file_path", "")
        file_type = rec.get("file_type", "").upper()

        if req_path and file_type == "ZIP":
            if not os.path.exists(file_path):
                return jsonify({"error": "Original zip no longer available"}), 404
            with zipfile.ZipFile(file_path, "r") as zf:
                names = zf.namelist()
                target = req_path if req_path in names else None
                if not target:
                    base = Path(req_path).name
                    for n in names:
                        if Path(n).name == base:
                            target = n
                            break
                if not target:
                    return jsonify({"error": "File not found in archive"}), 404
                raw = zf.read(target)
            return send_file(
                io.BytesIO(raw),
                as_attachment=True,
                download_name=Path(target).name,
            )

        if not os.path.exists(file_path):
            return jsonify({"error": "Original file no longer available"}), 404
        return send_file(file_path, as_attachment=True, download_name=rec["filename"])

    except Exception as e:
        return jsonify({"error": str(e)}), 500
