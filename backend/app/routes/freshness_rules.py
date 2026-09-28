from flask import Blueprint, jsonify

from app.database import get_db_connection
from app.services.auth import require_auth
from app.services.rule_provider import FreshnessRuleProviderError, get_freshness_rules, rules_as_dict


freshness_rules_bp = Blueprint("freshness_rules", __name__)


@freshness_rules_bp.get("/freshness-rules")
@require_auth
def get_rules():
    connection = get_db_connection()
    try:
        rules = get_freshness_rules(connection)
    except FreshnessRuleProviderError:
        return jsonify({
            "success": False,
            "error": "FRESHNESS_RULES_UNAVAILABLE",
            "message": "Freshness rules are unavailable",
        }), 503
    finally:
        connection.close()
    return jsonify({"success": True, "rules": rules_as_dict(rules)}), 200
