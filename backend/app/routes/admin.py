import sqlite3

from flask import Blueprint, jsonify, request

from app.database import get_db_connection
from app.services.auth import current_user, require_role
from app.services.auth import create_user, validate_role
from app.services.rule_admin import (
    RuleUpdateError,
    metadata_for_rules,
    reset_editable_rules,
    validate_rule_changes,
)
from app.services.rule_provider import FreshnessRuleProviderError, get_freshness_rules
from app.services.rule_admin import EDITABLE_RULE_KEYS, LOCKED_RULE_KEYS
from app.services.rule_provider import RULE_KEYS
from app.services.state_reset import reset_state_for_rule_keys


admin_bp = Blueprint("admin", __name__)


def _user_dict(row):
    return {
        "id": row["id"], "username": row["username"], "role": row["role"],
        "is_active": bool(row["is_active"]), "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _active_admin_count(connection):
    return connection.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'ADMIN' AND is_active = 1"
    ).fetchone()[0]


def _protect_admin_change(connection, actor, target, changes):
    role = changes.get("role", target["role"])
    is_active = changes.get("is_active", bool(target["is_active"]))
    removes_admin = target["role"] == "ADMIN" and (role != "ADMIN" or not is_active)
    if target["id"] == actor["id"] and removes_admin:
        raise ValueError("LAST_ACTIVE_ADMIN")
    if removes_admin and target["is_active"] and _active_admin_count(connection) <= 1:
        raise ValueError("LAST_ACTIVE_ADMIN")


def _insert_user_audit(connection, actor, target, action, old_value, new_value, reason=None):
    connection.execute(
        "INSERT INTO user_management_audit "
        "(actor_user_id, actor_username, actor_role, target_user_id, target_username, action, old_value, new_value, reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (actor["id"], actor["username"], actor["role"], target["id"],
         target["username"], action, old_value, new_value, reason),
    )


@admin_bp.get("/admin/status")
@require_role("ADMIN")
def admin_status():
    return jsonify({
        "success": True,
        "message": "Admin authorization is active",
    }), 200


@admin_bp.get("/admin/overview")
@require_role("ADMIN")
def admin_overview():
    connection = get_db_connection()
    try:
        users = connection.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active, "
            "SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS inactive, "
            "SUM(CASE WHEN role = 'ADMIN' THEN 1 ELSE 0 END) AS admins, "
            "SUM(CASE WHEN role = 'USER' THEN 1 ELSE 0 END) AS regular_users FROM users"
        ).fetchone()
        latest_reading = connection.execute(
            "SELECT timestamp, freshness_status FROM sensor_readings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        reading_total = connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
        foods = connection.execute("SELECT COUNT(*) FROM food_items").fetchone()[0]
        events = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        latest_change = connection.execute(
            "SELECT changed_at FROM freshness_rule_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    return jsonify({
        "success": True,
        "users": {
            "total": users["total"] or 0,
            "active": users["active"] or 0,
            "inactive": users["inactive"] or 0,
            "admins": users["admins"] or 0,
            "regular_users": users["regular_users"] or 0,
        },
        "readings": {
            "total": reading_total,
            "latest_timestamp": latest_reading["timestamp"] if latest_reading else None,
            "latest_freshness_status": latest_reading["freshness_status"] if latest_reading else None,
        },
        "foods": {"total": foods},
        "events": {"total": events},
        "freshness_rules": {
            "total": len(RULE_KEYS),
            "editable": len(EDITABLE_RULE_KEYS),
            "locked": len(LOCKED_RULE_KEYS),
            "latest_change_at": latest_change["changed_at"] if latest_change else None,
        },
    }), 200


@admin_bp.get("/admin/users")
@require_role("ADMIN")
def list_users():
    connection = get_db_connection()
    try:
        rows = connection.execute(
            "SELECT id, username, role, is_active, created_at, updated_at "
            "FROM users ORDER BY id ASC"
        ).fetchall()
    finally:
        connection.close()
    return jsonify({"success": True, "users": [_user_dict(row) for row in rows]}), 200


@admin_bp.get("/admin/users/<int:user_id>")
@require_role("ADMIN")
def get_user(user_id):
    connection = get_db_connection()
    try:
        row = connection.execute(
            "SELECT id, username, role, is_active, created_at, updated_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return jsonify({"success": False, "error": "USER_NOT_FOUND"}), 404
    return jsonify({"success": True, "user": _user_dict(row)}), 200


@admin_bp.post("/admin/users")
@require_role("ADMIN")
def create_admin_user():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "INVALID_JSON"}), 400
    allowed = {"username", "password", "role", "reason"}
    if set(payload) - allowed:
        return jsonify({"success": False, "error": "UNSUPPORTED_FIELD"}), 400
    username, password, role = payload.get("username"), payload.get("password"), payload.get("role")
    if not isinstance(username, str) or not username.strip():
        return jsonify({"success": False, "error": "INVALID_USERNAME"}), 400
    if not isinstance(password, str) or not password:
        return jsonify({"success": False, "error": "INVALID_PASSWORD"}), 400
    try:
        validate_role(role)
    except ValueError:
        return jsonify({"success": False, "error": "INVALID_ROLE"}), 400
    connection = get_db_connection()
    try:
        connection.execute("BEGIN")
        user_id = create_user(connection, username, password, role)
        row = connection.execute(
            "SELECT id, username, role, is_active, created_at, updated_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        _insert_user_audit(
            connection, current_user(), row, "CREATE_USER", None,
            '{"role":"%s","is_active":true}' % role, payload.get("reason"),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        return jsonify({"success": False, "error": "USERNAME_ALREADY_EXISTS"}), 409
    except Exception:
        connection.rollback()
        return jsonify({"success": False, "error": "USER_CREATE_FAILED"}), 500
    finally:
        connection.close()
    return jsonify({"success": True, "user": _user_dict(row)}), 201


@admin_bp.patch("/admin/users/<int:user_id>")
@require_role("ADMIN")
def update_admin_user(user_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        return jsonify({"success": False, "error": "INVALID_JSON"}), 400
    if set(payload) - {"role", "is_active", "reason"}:
        return jsonify({"success": False, "error": "UNSUPPORTED_FIELD"}), 400
    if "role" in payload:
        try:
            validate_role(payload["role"])
        except ValueError:
            return jsonify({"success": False, "error": "INVALID_ROLE"}), 400
    if "is_active" in payload and not isinstance(payload["is_active"], bool):
        return jsonify({"success": False, "error": "INVALID_STATUS"}), 400
    actor = current_user()
    connection = get_db_connection()
    try:
        connection.execute("BEGIN")
        target = connection.execute(
            "SELECT id, username, role, is_active, created_at, updated_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if target is None:
            connection.rollback()
            return jsonify({"success": False, "error": "USER_NOT_FOUND"}), 404
        role_changed = "role" in payload and payload["role"] != target["role"]
        status_changed = "is_active" in payload and bool(payload["is_active"]) != bool(target["is_active"])
        if (role_changed or status_changed) and (
            not isinstance(payload.get("reason"), str) or not payload["reason"].strip()
        ):
            connection.rollback()
            return jsonify({"success": False, "error": "REASON_REQUIRED", "message": "A reason is required"}), 400
        try:
            _protect_admin_change(connection, actor, target, payload)
        except ValueError as exc:
            connection.rollback()
            return jsonify({"success": False, "error": str(exc)}), 400
        assignments, values = [], []
        if "role" in payload:
            assignments.append("role = ?"); values.append(payload["role"])
        if "is_active" in payload:
            assignments.append("is_active = ?"); values.append(int(payload["is_active"]))
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        values.append(user_id)
        connection.execute(f"UPDATE users SET {', '.join(assignments)} WHERE id = ?", values)
        row = connection.execute(
            "SELECT id, username, role, is_active, created_at, updated_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        reason = payload.get("reason", "").strip() or None
        if role_changed:
            _insert_user_audit(connection, actor, row, "ROLE_CHANGED", target["role"], row["role"], reason)
        if status_changed:
            action = "USER_ACTIVATED" if row["is_active"] else "USER_DEACTIVATED"
            _insert_user_audit(connection, actor, row, action, str(bool(target["is_active"])).lower(), str(bool(row["is_active"])).lower(), reason)
        connection.commit()
    except Exception:
        connection.rollback()
        return jsonify({"success": False, "error": "USER_UPDATE_FAILED"}), 500
    finally:
        connection.close()
    return jsonify({"success": True, "user": _user_dict(row)}), 200


@admin_bp.get("/admin/users/history")
@require_role("ADMIN")
def user_management_history():
    limit = request.args.get("limit", default=100, type=int)
    limit = min(max(limit, 1), 500)
    connection = get_db_connection()
    try:
        rows = connection.execute(
            "SELECT id, created_at, actor_user_id, actor_username, actor_role, "
            "target_user_id, target_username, action, old_value, new_value, reason "
            "FROM user_management_audit ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        connection.close()
    return jsonify({"success": True, "history": [dict(row) for row in rows]}), 200


@admin_bp.get("/admin/freshness-rules")
@require_role("ADMIN")
def admin_freshness_rules():
    connection = get_db_connection()
    try:
        rules = get_freshness_rules(connection)
    except FreshnessRuleProviderError:
        return jsonify({"success": False, "error": "FRESHNESS_RULES_UNAVAILABLE"}), 503
    finally:
        connection.close()
    return jsonify({"success": True, "rules": metadata_for_rules(rules)}), 200


@admin_bp.put("/admin/freshness-rules")
@require_role("ADMIN")
def update_admin_freshness_rules():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
        return jsonify({"success": False, "error": "INVALID_REASON", "message": "A reason is required"}), 400
    changes = payload.get("rules")
    connection = get_db_connection()
    try:
        connection.execute("BEGIN")
        validated = validate_rule_changes(connection, changes)
        actor = current_user()
        changed = []
        for key, old_value, new_value in validated:
            if old_value == new_value:
                continue
            value_type = "float_pct" if key == "gas.anomaly_increase_pct" else (
                "float" if key.startswith("humidity.") else "int"
            )
            connection.execute(
                "UPDATE freshness_rules SET rule_value = ?, updated_at = CURRENT_TIMESTAMP, updated_by_user_id = ? WHERE rule_key = ?",
                (str(new_value), actor["id"], key),
            )
            connection.execute(
                "INSERT INTO freshness_rule_audit "
                "(actor_user_id, actor_username, actor_role, rule_key, old_value, new_value, value_type, reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (actor["id"], actor["username"], actor["role"], key, str(old_value), str(new_value), value_type, payload["reason"].strip()),
            )
            changed.append(key)
        reset_state_for_rule_keys(connection, changed)
        connection.commit()
    except RuleUpdateError as exc:
        connection.rollback()
        return jsonify({"success": False, "error": exc.code, "message": str(exc)}), 400
    except Exception:
        connection.rollback()
        return jsonify({"success": False, "error": "RULE_UPDATE_FAILED", "message": "Rules were not changed"}), 500
    finally:
        connection.close()
    return jsonify({"success": True, "changed_count": len(changed), "changed_rules": changed}), 200


@admin_bp.post("/admin/freshness-rules/reset")
@require_role("ADMIN")
def reset_admin_freshness_rules():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
        return jsonify({"success": False, "error": "REASON_REQUIRED", "message": "A reason is required"}), 400
    connection = get_db_connection()
    actor = current_user()
    try:
        connection.execute("BEGIN")
        changes = reset_editable_rules(connection)
        for key, old_value, new_value, value_type in changes:
            connection.execute(
                "UPDATE freshness_rules SET rule_value = ?, updated_at = CURRENT_TIMESTAMP, updated_by_user_id = ? WHERE rule_key = ?",
                (new_value, actor["id"], key),
            )
            connection.execute(
                "INSERT INTO freshness_rule_audit "
                "(actor_user_id, actor_username, actor_role, rule_key, old_value, new_value, value_type, reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (actor["id"], actor["username"], actor["role"], key, old_value, new_value, value_type, payload["reason"].strip()),
            )
        connection.commit()
    except RuleUpdateError as exc:
        connection.rollback()
        return jsonify({"success": False, "error": exc.code, "message": str(exc)}), 503
    except Exception:
        connection.rollback()
        return jsonify({"success": False, "error": "RULE_RESET_FAILED", "message": "Rules were not reset"}), 500
    finally:
        connection.close()
    return jsonify({"success": True, "changed_count": len(changes)}), 200


@admin_bp.get("/admin/freshness-rules/history")
@require_role("ADMIN")
def freshness_rule_history():
    limit = request.args.get("limit", default=100, type=int)
    limit = min(max(limit, 1), 500)
    connection = get_db_connection()
    try:
        rows = connection.execute(
            "SELECT id, changed_at, actor_user_id, actor_username, actor_role, rule_key, old_value, new_value, reason "
            "FROM freshness_rule_audit ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        connection.close()
    return jsonify({"success": True, "history": [dict(row) for row in rows]}), 200
