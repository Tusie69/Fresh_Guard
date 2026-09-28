from flask import Blueprint, jsonify, request, session

from app.services.auth import authenticate, current_user, user_public_dict


auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/auth/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "INVALID_JSON",
            "message": "Request body must be a JSON object",
        }), 400

    username = data.get("username", data.get("email"))
    password = data.get("password")
    user = authenticate(username, password)
    if user is None:
        return jsonify({
            "success": False,
            "error": "INVALID_CREDENTIALS",
            "message": "Invalid username or password",
        }), 401

    session.clear()
    session["user_id"] = user["id"]
    session.permanent = False
    return jsonify({"success": True, "user": user_public_dict(user)}), 200


@auth_bp.get("/auth/me")
def me():
    user = current_user()
    if user is None:
        return jsonify({
            "success": False,
            "error": "AUTHENTICATION_REQUIRED",
            "message": "Authentication is required",
        }), 401
    return jsonify({"success": True, "user": user_public_dict(user)}), 200


@auth_bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out"}), 200
