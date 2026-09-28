from pathlib import Path
import os
import secrets

from flask import Flask, send_from_directory
from flask_cors import CORS


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get(
        "FRESHGUARD_SECRET_KEY", secrets.token_hex(32)
    )
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    dashboard_dir = Path(__file__).resolve().parents[2] / "dashboard"

    @app.get("/")
    def dashboard():
        return send_from_directory(dashboard_dir, "index.html")

    @app.get("/admin")
    def admin_dashboard():
        return send_from_directory(dashboard_dir, "admin.html")

    @app.get("/login")
    def login_page():
        return send_from_directory(dashboard_dir, "login.html")

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    from app.routes.readings import readings_bp
    from app.routes.events import events_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.freshness_rules import freshness_rules_bp

    app.register_blueprint(readings_bp, url_prefix="/api/v1")
    app.register_blueprint(events_bp, url_prefix="/api/v1")
    app.register_blueprint(auth_bp, url_prefix="/api/v1")
    app.register_blueprint(admin_bp, url_prefix="/api/v1")
    app.register_blueprint(freshness_rules_bp, url_prefix="/api/v1")

    return app
