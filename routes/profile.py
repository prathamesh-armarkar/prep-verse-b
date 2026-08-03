from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from services.profile_service import ProfileService

profile_bp = Blueprint(
    "profile",
    __name__,
    url_prefix="/api/profile"
)


@profile_bp.route("", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = get_jwt_identity()
    response, status = ProfileService.get_profile(user_id)
    return jsonify(response), status


@profile_bp.route("", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    response, status = ProfileService.update_profile(user_id, data)
    return jsonify(response), status


@profile_bp.route("/photo", methods=["PATCH"])
@jwt_required()
def update_photo():
    user_id = get_jwt_identity()
    uploaded_file = request.files.get("photo")
    response, status = ProfileService.update_photo(user_id, uploaded_file)
    return jsonify(response), status


@profile_bp.route("/photo", methods=["DELETE"])
@jwt_required()
def delete_photo():
    user_id = get_jwt_identity()
    response, status = ProfileService.delete_photo(user_id)
    return jsonify(response), status


@profile_bp.route("/delete", methods=["DELETE"])
@jwt_required()
def delete_account():
    user_id = get_jwt_identity()
    response, status = ProfileService.delete_account(user_id)
    return jsonify(response), status


@profile_bp.route("/complete", methods=["POST"])
def complete_profile():
    data = request.get_json()
    response, status = ProfileService.complete_profile(data)
    return jsonify(response), status

