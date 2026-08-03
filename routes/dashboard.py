from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from services.dashboard_service import DashboardService

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.route("", methods=["GET"])
@jwt_required()
def get_dashboard():
    """Return aggregated dashboard data for the authenticated user."""
    user_id = get_jwt_identity()
    data = DashboardService.get_dashboard(user_id)

    if data is None:
        return jsonify({
            "success": False,
            "message": "Could not load dashboard data.",
        }), 500

    return jsonify({
        "success": True,
        "data": data,
    }), 200
