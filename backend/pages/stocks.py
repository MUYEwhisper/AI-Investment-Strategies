from flask import Blueprint, jsonify, request

from utils.stocks.service import StockResolveError, StockServiceError, get_stock_detail, get_watchlist_stock

stocks_page = Blueprint("stocks", __name__)


@stocks_page.route("/watchlist", methods=["POST"])
def watchlist_stock():
    data = request.get_json(silent=True) or {}
    query = str(data.get("query") or "").strip()
    if not query:
        return jsonify({"success": False, "error": "股票名称或代码不能为空。"}), 400

    try:
        payload = get_watchlist_stock(query)
        return jsonify({"success": True, **payload})
    except StockResolveError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except StockServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"success": False, "error": f"股票卡片生成失败：{exc}"}), 500


@stocks_page.route("/<stock_code>", methods=["GET"])
def stock_detail(stock_code: str):
    code = str(stock_code or "").strip()
    if not code:
        return jsonify({"success": False, "error": "股票代码不能为空。"}), 400

    try:
        payload = get_stock_detail(code)
        return jsonify({"success": True, **payload})
    except StockResolveError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except StockServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"success": False, "error": f"股票详情生成失败：{exc}"}), 500
