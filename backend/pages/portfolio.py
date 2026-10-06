from flask import Blueprint, jsonify, request

from utils.auth.context import require_auth
from utils.workbench.service import WorkbenchServiceError, get_portfolio_health

portfolio_page = Blueprint("portfolio", __name__)


@portfolio_page.route("/health", methods=["POST"])
@require_auth
def portfolio_health():
    data = request.get_json(silent=True) or {}
    watchlist = data.get("watchlist") or []
    try:
        return jsonify({"success": True, "report": get_portfolio_health(watchlist)})
    except WorkbenchServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"组合体检失败：{exc}"}), 500
