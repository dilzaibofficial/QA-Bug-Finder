import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from flask import Flask
from flask_cors import CORS

from socketio_instance import socketio

from routes.auth     import auth_bp
from routes.upload   import upload_bp
from routes.reports  import reports_bp
from routes.dashboard import dashboard_bp
from routes.history  import history_bp
from routes.settings import settings_bp
from routes.team     import team_bp
from routes.notifications import notifications_bp
from routes.notes    import notes_bp
from routes.chat      import chat_bp  # also registers the socket.io event handlers
from routes.billing   import billing_bp
from routes.admin     import admin_bp

app = Flask(__name__)
CORS(app, supports_credentials=True)
socketio.init_app(app)

app.register_blueprint(auth_bp,      url_prefix="/api/auth")
app.register_blueprint(upload_bp,    url_prefix="/api/upload")
app.register_blueprint(reports_bp,   url_prefix="/api/reports")
app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
app.register_blueprint(history_bp,   url_prefix="/api/history")
app.register_blueprint(settings_bp,  url_prefix="/api/settings")
app.register_blueprint(team_bp,      url_prefix="/api/team")
app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
app.register_blueprint(notes_bp,     url_prefix="/api/notes")
app.register_blueprint(chat_bp,      url_prefix="/api/chat")
app.register_blueprint(billing_bp,   url_prefix="/api/billing")
app.register_blueprint(admin_bp,     url_prefix="/api/admin")


@app.route("/api/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__), "uploads"), exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    print(f"Backend running on http://localhost:{port} (Socket.IO enabled)")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
