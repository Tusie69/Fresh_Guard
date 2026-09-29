from pathlib import Path
import logging
import os
import secrets

from flask import Flask, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv


def create_app():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    # Dashboard assets are served explicitly from dashboard/static below.
    app = Flask(__name__, static_folder=None)
    app.logger.setLevel(logging.INFO)
    # Upgrade existing databases and seed newly introduced rules on every
    # startup. init_db is idempotent and preserves configured rule values.
    from app.init_db import init_db

    init_db()
    app.config["SECRET_KEY"] = os.environ.get(
        "FRESHGUARD_SECRET_KEY", secrets.token_hex(32)
    )
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    dashboard_dir = Path(__file__).resolve().parents[2] / "dashboard"
    dashboard_static_dir = dashboard_dir / "static"

    @app.get("/static/<path:filename>")
    def dashboard_static(filename):
        return send_from_directory(dashboard_static_dir, filename)

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

    # Delivery is optional and runs outside request/reading transactions.
    # Werkzeug's reloader only starts the worker in its serving process.
    from app.services.telegram_notifier import start_telegram_worker
    if os.environ.get("WERKZEUG_RUN_MAIN", "true") == "true":
        start_telegram_worker(app)

    app.register_blueprint(readings_bp, url_prefix="/api/v1")
    app.register_blueprint(events_bp, url_prefix="/api/v1")
    app.register_blueprint(auth_bp, url_prefix="/api/v1")
    app.register_blueprint(admin_bp, url_prefix="/api/v1")
    app.register_blueprint(freshness_rules_bp, url_prefix="/api/v1")

    return app
