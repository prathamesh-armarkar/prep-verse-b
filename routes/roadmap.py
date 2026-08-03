from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from services.roadmap_service import RoadmapGenerationError, RoadmapService

roadmap_bp = Blueprint("roadmap", __name__, url_prefix="/api/roadmap")


@roadmap_bp.route("/generate", methods=["POST"])
@jwt_required()
def generate_roadmap():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    career_goal = (data.get("career_goal") or "").strip()
    current_level = (data.get("current_level") or "").strip().lower()

    if not career_goal:
        return jsonify({"success": False, "message": "Career goal is required."}), 400
    if current_level not in ("beginner", "intermediate", "advanced"):
        return jsonify({
            "success": False,
            "message": "Current level must be 'beginner', 'intermediate', or 'advanced'.",
        }), 400
    if len(career_goal) > 200:
        return jsonify({"success": False, "message": "Career goal must be under 200 characters."}), 400

    if not RoadmapService.is_enabled():
        return jsonify({
            "success": False,
            "message": "Roadmap generation is not configured. Please set up GROQ_API_KEY.",
        }), 503

    try:
        roadmap = RoadmapService.generate(user_id, career_goal, current_level)
        return jsonify({
            "success": True,
            "data": {"roadmap": roadmap},
        }), 201
    except RoadmapGenerationError as exc:
        current_app.logger.warning("Roadmap generation error: %s", exc)
        return jsonify({
            "success": False,
            "message": str(exc),
        }), 502


@roadmap_bp.route("/latest", methods=["GET"])
@jwt_required()
def get_latest_roadmap():
    user_id = get_jwt_identity()
    roadmap = RoadmapService.get_latest(user_id)
    return jsonify({
        "success": True,
        "data": {"roadmap": roadmap},
    }), 200


@roadmap_bp.route("/all", methods=["GET"])
@jwt_required()
def get_all_roadmaps():
    user_id = get_jwt_identity()
    roadmaps = RoadmapService.get_all(user_id)
    return jsonify({
        "success": True,
        "data": {"roadmaps": roadmaps},
    }), 200


@roadmap_bp.route("/progress", methods=["PUT"])
@jwt_required()
def update_progress():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    roadmap_id = data.get("roadmap_id")
    completion = data.get("completion_percentage")
    if not roadmap_id or completion is None:
        return jsonify({
            "success": False,
            "message": "roadmap_id and completion_percentage are required.",
        }), 400
    try:
        roadmap_id = str(roadmap_id)
        completion = float(completion)
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid roadmap_id or completion_percentage.",
        }), 400
    success = RoadmapService.update_progress(user_id, roadmap_id, completion)
    return jsonify({
        "success": success,
        "message": "Progress updated." if success else "Roadmap not found.",
    }), 200 if success else 404


@roadmap_bp.route("/<roadmap_id>", methods=["DELETE"])
@jwt_required()
def delete_roadmap(roadmap_id):
    user_id = get_jwt_identity()
    success = RoadmapService.delete(user_id, roadmap_id)
    return jsonify({
        "success": success,
        "message": "Roadmap deleted." if success else "Roadmap not found.",
    }), 200 if success else 404

