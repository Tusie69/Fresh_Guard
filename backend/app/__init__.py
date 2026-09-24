from flask import Flask
from flask_cors import CORS


def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    from app.routes.readings import readings_bp
    from app.routes.events import events_bp

    app.register_blueprint(readings_bp, url_prefix="/api/v1")
    app.register_blueprint(events_bp, url_prefix="/api/v1")

    return app
