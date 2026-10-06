from flask import Blueprint, jsonify, request

from utils.auth.context import require_auth
from utils.workbench.service import WorkbenchServiceError, get_investor_profile, save_investor_profile

profile_page = Blueprint("profile", __name__)


@profile_page.route("", methods=["GET"])
@require_auth
def get_profile():
    try:
        return jsonify({"success": True, "profile": get_investor_profile()})
    except Exception as exc:
        return jsonify({"success": False, "error": f"投资者画像读取失败：{exc}"}), 500


@profile_page.route("/evaluate", methods=["POST"])
@require_auth
def evaluate_profile():
    data = request.get_json(silent=True) or {}
    answers = data.get("answers") or {}
    try:
        profile = save_investor_profile(answers)
        return jsonify({"success": True, "profile": profile})
    except WorkbenchServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"投资者画像生成失败：{exc}"}), 500
