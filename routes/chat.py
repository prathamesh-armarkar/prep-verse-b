from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from services.chat_service import CareerAssistantError, CareerAssistantService

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.route("/send", methods=["POST"])
@jwt_required()
def send_message():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"success": False, "message": "Message is required."}), 400
    if len(message) > 2000:
        return jsonify({"success": False, "message": "Message must be under 2000 characters."}), 400

    if not CareerAssistantService.is_enabled():
        return jsonify({
            "success": False,
            "message": "AI assistant is not configured. Please set up GROQ_API_KEY.",
        }), 503

    try:
        result = CareerAssistantService.chat(user_id, message)
        return jsonify({
            "success": True,
            "data": result,
        }), 200
    except CareerAssistantError as exc:
        current_app.logger.warning("Career assistant error: %s", exc)
        return jsonify({
            "success": False,
            "message": str(exc),
        }), 502


@chat_bp.route("/history", methods=["GET"])
@jwt_required()
def get_history():
    user_id = get_jwt_identity()
    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(200, limit))
    history = CareerAssistantService.get_history(user_id, limit)
    return jsonify({
        "success": True,
        "data": {"history": history},
    }), 200


@chat_bp.route("/clear", methods=["DELETE"])
@jwt_required()
def clear_history():
    user_id = get_jwt_identity()
    success = CareerAssistantService.clear_history(user_id)
    return jsonify({
        "success": success,
        "message": "Chat history cleared." if success else "Failed to clear history.",
    }), 200 if success else 500

