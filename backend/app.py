import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from flask import Flask
from flask_cors import CORS

from routes.auth     import auth_bp
from routes.upload   import upload_bp
from routes.reports  import reports_bp
from routes.dashboard import dashboard_bp
from routes.history  import history_bp
from routes.settings import settings_bp

app = Flask(__name__)
CORS(app,
     supports_credentials=True,
     origins=["http://localhost:3000",
              "https://qa-bug-finder.vercel.app",
              "https://qa-bug-finder-rmeblt60y-dil-zaibs-projects.vercel.app"])

app.register_blueprint(auth_bp,      url_prefix="/api/auth")
app.register_blueprint(upload_bp,    url_prefix="/api/upload")
app.register_blueprint(reports_bp,   url_prefix="/api/reports")
app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
app.register_blueprint(history_bp,   url_prefix="/api/history")
app.register_blueprint(settings_bp,  url_prefix="/api/settings")


@app.route("/api/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__), "uploads"), exist_ok=True)
    print("Backend running on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
