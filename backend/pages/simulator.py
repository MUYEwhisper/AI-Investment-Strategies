from flask import Blueprint, jsonify, request

from utils.auth.context import require_auth
from utils.workbench.service import (
    WorkbenchServiceError,
    create_sim_trade,
    create_trade_review,
    delete_trade_review,
    get_simulation_account,
    list_trade_reviews,
    reset_simulation_account,
)

simulator_page = Blueprint("simulator", __name__)


@simulator_page.route("/account", methods=["GET"])
@require_auth
def get_account():
    try:
        return jsonify({"success": True, "snapshot": get_simulation_account()})
    except Exception as exc:
        return jsonify({"success": False, "error": f"模拟账户读取失败：{exc}"}), 500


@simulator_page.route("/reset", methods=["POST"])
@require_auth
def reset_account():
    data = request.get_json(silent=True) or {}
    initial_cash = data.get("initialCash") or 100000
    try:
        return jsonify({"success": True, "snapshot": reset_simulation_account(float(initial_cash))})
    except Exception as exc:
        return jsonify({"success": False, "error": f"模拟账户重置失败：{exc}"}), 500


@simulator_page.route("/trade", methods=["POST"])
@require_auth
def submit_trade():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({"success": True, "snapshot": create_sim_trade(data)})
    except WorkbenchServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"模拟交易失败：{exc}"}), 500


@simulator_page.route("/review", methods=["POST"])
@require_auth
def create_review():
    data = request.get_json(silent=True) or {}
    stock_code = str(data.get("stockCode") or "").strip()
    try:
        return jsonify({"success": True, "review": create_trade_review(stock_code)})
    except WorkbenchServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"AI 复盘生成失败：{exc}"}), 500


@simulator_page.route("/reviews", methods=["GET"])
@require_auth
def get_reviews():
    try:
        return jsonify({"success": True, "reviews": list_trade_reviews()})
    except Exception as exc:
        return jsonify({"success": False, "error": f"历史复盘读取失败：{exc}"}), 500


@simulator_page.route("/reviews/<int:review_id>", methods=["DELETE"])
@require_auth
def remove_review(review_id: int):
    try:
        delete_trade_review(review_id)
        return jsonify({"success": True})
    except WorkbenchServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"历史复盘删除失败：{exc}"}), 500
