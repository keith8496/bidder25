# realtime.py
import logging
from flask_socketio import SocketIO

logger = logging.getLogger("auction")


def init_socketio(server) -> SocketIO:
    """
    Initialize Socket.IO for the given Flask server.
    Keep this in one place so app.py is just wiring.
    """
    return SocketIO(server, cors_allowed_origins="*")


def broadcast_snapshot(socketio: SocketIO, snapshot: dict) -> None:
    """
    Broadcast a snapshot to all connected clients.
    Call this after any state mutation.
    """
    try:
        socketio.emit("snapshot", snapshot, broadcast=True)
    except Exception:
        logger.exception("Error broadcasting snapshot via Socket.IO")