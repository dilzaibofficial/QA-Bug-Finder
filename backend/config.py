import os

MONGO_URI   = "mongodb://localhost:27017"
DB_NAME     = "bug_detector"
UPLOAD_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
SECRET_KEY  = "fyp_bug_detector_secret_2026"
MAX_FILE_MB = 50

ALLOWED_EXT = {'.zip', '.java', '.py', '.js', '.ts',
               '.log', '.txt', '.cpp', '.c', '.cs'}

# Load .env manually (no python-dotenv needed)
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

os.makedirs(UPLOAD_DIR, exist_ok=True)
