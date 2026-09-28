"""Small session-based authentication and role helpers for the Flask prototype."""

from functools import wraps

from flask import g, session
from werkzeug.security import check_password_hash, generate_password_hash

from app.database import get_db_connection


VALID_ROLES = frozenset({"USER", "ADMIN"})


def validate_role(role):
    if role not in VALID_ROLES:
        raise ValueError("role must be USER or ADMIN")
    return role


def create_password_hash(password):
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    return generate_password_hash(password)


def create_user(connection, username, password, role):
    if not isinstance(username, str) or not username.strip():
        raise ValueError("username must be a non-empty string")
    validate_role(role)
    cursor = connection.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username.strip(), create_password_hash(password), role),
    )
    return cursor.lastrowid


def authenticate(username, password, connection=None):
    if not isinstance(username, str) or not isinstance(password, str):
        return None

    owns_connection = connection is None
    connection = connection or get_db_connection()
    try:
        user = connection.execute(
            "SELECT id, username, password_hash, role, is_active "
            "FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        if user is None or not user["is_active"]:
            return None
        if not check_password_hash(user["password_hash"], password):
            return None
        return user
    finally:
        if owns_connection:
            connection.close()


def current_user():
    if "current_user" in g:
        return g.current_user

    user_id = session.get("user_id")
    if user_id is None:
        g.current_user = None
        return None

    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT id, username, role, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        connection.close()

    if user is None or not user["is_active"] or user["role"] not in VALID_ROLES:
        session.clear()
        user = None
    g.current_user = user
    return user


def user_public_dict(user):
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
    }


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from flask import jsonify

        user = current_user()
        if user is None:
            return jsonify({
                "success": False,
                "error": "AUTHENTICATION_REQUIRED",
                "message": "Authentication is required",
            }), 401
        return view(*args, **kwargs)

    return wrapped


def require_role(role):
    validate_role(role)

    def decorator(view):
        @wraps(view)
        @require_auth
        def wrapped(*args, **kwargs):
            from flask import jsonify

            if current_user()["role"] != role:
                return jsonify({
                    "success": False,
                    "error": "FORBIDDEN",
                    "message": "Insufficient permissions",
                }), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator
