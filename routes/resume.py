from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from services.resume_service import ResumeService


resume_bp = Blueprint("resume", __name__, url_prefix="/api/resume")


@resume_bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_resume():
    user_id = get_jwt_identity()
    uploaded_file = request.files.get("resume")
    target_role = (request.form.get("target_role") or "").strip()
    job_description = (request.form.get("job_description") or "").strip()
    if not target_role:
        return jsonify({"success": False, "message": "Target role is required."}), 400
    current_app.logger.warning(
        "Resume upload debug | request_content_type=%s | request_file_keys=%s | "
        "request_form_keys=%s | jwt_user_id=%s | target_role=%s | job_description_length=%s | "
        "file_object=%r | filename=%s | content_type=%s",
        request.content_type,
        list(request.files.keys()),
        list(request.form.keys()),
        user_id,
        target_role,
        len(job_description),
        uploaded_file,
        getattr(uploaded_file, "filename", None),
        getattr(uploaded_file, "content_type", None),
    )
    response, status = ResumeService.upload_resume(
        user_id=user_id,
        uploaded_file=uploaded_file,
        target_role=target_role,
        job_description=job_description,
    )
    current_app.logger.warning("Resume upload debug | final_response_status=%s | response=%s", status, response)
    return jsonify(response), status


@resume_bp.route("/latest", methods=["GET"])
@jwt_required()
def get_latest_resume():
    response, status = ResumeService.get_latest_resume(get_jwt_identity())
    return jsonify(response), status


@resume_bp.route("/history", methods=["GET"])
@jwt_required()
def get_resume_history():
    response, status = ResumeService.get_resume_history(get_jwt_identity())
    return jsonify(response), status
