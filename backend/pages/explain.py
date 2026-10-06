from flask import Blueprint, jsonify

from utils.workbench.service import WorkbenchServiceError, explain_stock_anomaly

explain_page = Blueprint("explain", __name__)


@explain_page.route("/anomaly/<stock_code>", methods=["GET"])
def explain_anomaly(stock_code: str):
    try:
        return jsonify({"success": True, "report": explain_stock_anomaly(stock_code)})
    except WorkbenchServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"异动原因解释失败：{exc}"}), 500
