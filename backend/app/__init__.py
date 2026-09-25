from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS


def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    dashboard_dir = Path(__file__).resolve().parents[2] / "dashboard"

    @app.get("/")
    def dashboard():
        return send_from_directory(dashboard_dir, "index.html")

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    from app.routes.readings import readings_bp
    from app.routes.events import events_bp

    app.register_blueprint(readings_bp, url_prefix="/api/v1")
    app.register_blueprint(events_bp, url_prefix="/api/v1")

    return app
