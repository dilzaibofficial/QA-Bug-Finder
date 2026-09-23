from flask_socketio import SocketIO

# threading mode needs no eventlet/gevent — plays nicely with the existing
# Werkzeug dev server on Windows.
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")
