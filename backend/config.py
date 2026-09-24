import os

MONGO_URI   = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME     = "bug_detector"
UPLOAD_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
SECRET_KEY  = os.environ.get("SECRET_KEY", "fyp_bug_detector_secret_2026")
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
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# Where Stripe Checkout redirects the browser back to after payment. Must be
# the real deployed frontend URL in production (e.g. https://qa-bug-finder.
# vercel.app) — Render never sets this by itself, it has to be added there.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# Optional — password-reset emails. Leave unset in dev: forgot-password then
# returns the OTP directly in the API response instead of emailing it.
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "") or SMTP_USER

os.makedirs(UPLOAD_DIR, exist_ok=True)
