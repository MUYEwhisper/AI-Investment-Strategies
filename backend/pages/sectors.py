from flask import Blueprint, jsonify, request

from utils.sectors.service import SectorServiceError, get_sector_overview

sectors_page = Blueprint("sectors", __name__)


@sectors_page.route("/overview", methods=["POST"])
def sector_overview():
    data = request.get_json(silent=True) or {}
    stock_codes = data.get("stockCodes") or []

    try:
        payload = get_sector_overview(stock_codes)
        return jsonify({"success": True, **payload})
    except SectorServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"success": False, "error": f"板块分析生成失败：{exc}"}), 500
