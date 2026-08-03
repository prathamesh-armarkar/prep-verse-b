import os

from flask import current_app

from models.resume import Resume, serialize_resume
from services.ai_service import AIAnalysisError, ResumeAIAnalysisService
from services.resume_analysis_service import ResumeAnalysisService
from utils.docx_parser import extract_docx_text
from utils.file_handler import (
    FileValidationError,
    remove_file_if_exists,
    save_resume_file,
    validate_resume_file,
)
from utils.pdf_parser import DocumentParsingError, extract_pdf_text
from utils.resume_parser import parse_resume


class ResumeService:
    """Coordinates upload persistence, text extraction, and deterministic parsing."""

    CURRENT_ANALYSIS_MARKER = "overview"

    @staticmethod
    def upload_resume(user_id, uploaded_file, target_role="", job_description=""):
        if not target_role or not target_role.strip():
            return {"success": False, "message": "Target role is required."}, 400
        try:
            original_name, file_type, file_size = validate_resume_file(uploaded_file)
        except FileValidationError as exc:
            current_app.logger.warning("Resume upload debug | validation_failed=%s", exc)
            return {"success": False, "message": str(exc)}, 400

        saved_path = None
        try:
            user_id = str(user_id)
        except (TypeError, ValueError):
            current_app.logger.warning("Resume upload debug | invalid_jwt_user_id=%r", user_id)
            return {"success": False, "message": "Invalid authenticated user."}, 401

        current_app.logger.warning(
            "Resume upload debug | jwt_user_id=%s | filename=%s | file_size=%s | file_type=%s",
            user_id, original_name, file_size, file_type,
        )
        try:
            stored_name, saved_path = save_resume_file(
                uploaded_file, current_app.config["UPLOAD_FOLDER"], file_type
            )
            current_app.logger.warning("Resume upload debug | upload_path=%s | file_save_status=success", saved_path)
        except OSError as exc:
            current_app.logger.exception("Resume upload debug | file_save_status=failed")
            return {
                "success": False,
                "message": "Failed to save uploaded file.",
                "error": str(exc),
            }, 500

        try:
            resume_id = Resume.create({
                "user_id": user_id,
                "original_name": original_name,
                "stored_name": stored_name,
                "file_path": os.path.relpath(saved_path, current_app.root_path).replace("\\", "/"),
                "file_size": file_size,
                "file_type": file_type,
                "target_role": target_role,
                "job_description": job_description or None,
            })
            current_app.logger.warning("Resume upload debug | database_insert_status=success | resume_id=%s", resume_id)
        except Exception as exc:
            remove_file_if_exists(saved_path)
            current_app.logger.exception("Resume upload debug | database_insert_status=failed")
            return {
                "success": False,
                "message": "Database insert failed.",
                "error": str(exc),
            }, 500

        parsing_warning = None
        parsed_data = None
        analysis = None
        try:
            if file_type == "pdf":
                extracted_text = extract_pdf_text(saved_path)
            else:
                extracted_text = extract_docx_text(saved_path)
            current_app.logger.warning(
                "Resume upload debug | text_extraction_status=success | extracted_text_length=%s",
                len(extracted_text),
            )
        except DocumentParsingError as exc:
            if file_type != "pdf":
                remove_file_if_exists(saved_path)
                current_app.logger.exception("Resume upload debug | text_extraction_status=failed")
                return {
                    "success": False,
                    "message": f"{exc.document_type} parsing failed.",
                    "error": exc.detail,
                }, 422
            extracted_text = ""
            parsing_warning = "The PDF was uploaded, but no extractable text was found."
            current_app.logger.warning(
                "Resume upload debug | text_extraction_status=unavailable | parser_error=%s",
                exc.detail,
            )

        ai_warning = None
        try:
            parsed_data = parse_resume(extracted_text)
            analysis = ResumeAnalysisService.generate_analysis(parsed_data)

            try:
                ai_analysis = ResumeAIAnalysisService.analyze(
                    parsed_data, extracted_text,
                    target_role=target_role,
                    job_description=job_description,
                )
                if ai_analysis:
                    analysis = {**analysis, **ai_analysis}
                else:
                    ai_warning = "AI analysis returned no data; showing deterministic analysis."
            except AIAnalysisError as exc:
                ai_warning = "AI analysis is currently unavailable; showing deterministic analysis."
                current_app.logger.warning("Resume upload debug | ai_analysis_status=failed | error=%s", exc)

            Resume.update(resume_id, {
                "extracted_text": extracted_text,
                "parsed_data_json": parsed_data,
                "analysis_json": analysis,
            })
            current_app.logger.warning("Resume upload debug | database_update_status=success")
        except Exception as exc:
            remove_file_if_exists(saved_path)
            current_app.logger.exception("Resume upload debug | unexpected_upload_failure")
            return {
                "success": False,
                "message": "Resume upload processing failed.",
                "error": str(exc),
            }, 500

        resume_doc = Resume.find_by_id(resume_id)
        response = {
            "success": True,
            "message": "Resume uploaded and parsed successfully.",
            "resume": {
                "id": resume_id,
                "file_name": original_name,
                "uploaded_at": resume_doc["created_at"].isoformat(),
                "file_type": file_type,
                "file_size": file_size,
                "extracted_text_length": len(extracted_text),
            },
            "parsed_data": parsed_data,
            "analysis": analysis,
        }
        if parsing_warning:
            response["parsing_warning"] = parsing_warning
        if ai_warning:
            response["ai_warning"] = ai_warning
        return response, 201

    @staticmethod
    def get_latest_resume(user_id):
        try:
            user_id = str(user_id)
            resume = Resume.find_latest_by_user(user_id)
        except Exception:
            current_app.logger.exception("Unable to retrieve latest resume")
            return {"success": False, "message": "Resume could not be retrieved."}, 500

        if resume is None:
            return {"success": True, "resume": None, "message": "No resume found."}, 200

        return {"success": True, "resume": ResumeService._serialize_resume(resume)}, 200

    @staticmethod
    def get_resume_history(user_id):
        try:
            user_id = str(user_id)
            resumes = Resume.find_all_by_user(user_id)
        except Exception:
            current_app.logger.exception("Unable to retrieve resume history")
            return {"success": False, "message": "Resume history could not be retrieved."}, 500

        return {
            "success": True,
            "resumes": [ResumeService._serialize_resume(resume) for resume in resumes],
        }, 200

    @staticmethod
    def _serialize_resume(resume):
        """Return public resume metadata without exposing the server file path."""
        parsed_data, analysis = ResumeService._ensure_current_analysis(resume)
        payload = serialize_resume(resume)
        payload["parsed_data"] = parsed_data
        payload["analysis"] = analysis
        return payload

    @staticmethod
    def _ensure_current_analysis(resume):
        """Return (parsed_data, analysis), upgrading legacy rows to the current format."""
        analysis = resume.get("analysis_json") or {}
        parsed_data = resume.get("parsed_data_json") or {}
        current = (
            resume.get("analysis_json")
            and ResumeService.CURRENT_ANALYSIS_MARKER in resume.get("analysis_json")
            and bool(resume.get("extracted_text"))
        )
        if current:
            return parsed_data, analysis

        try:
            text = resume.get("extracted_text") or ""
            if not text:
                text = ResumeService._recover_text_from_file(resume)
            if not text:
                return parsed_data, analysis
            parsed_data = parse_resume(text)
            analysis = ResumeAnalysisService.generate_analysis(parsed_data)
            Resume.update(str(resume["_id"]), {
                "extracted_text": text,
                "parsed_data_json": parsed_data,
                "analysis_json": analysis,
            })
        except Exception:
            current_app.logger.exception(
                "Unable to upgrade resume %s analysis; returning stored data.", resume.get("_id")
            )
        return parsed_data, analysis

    @staticmethod
    def _recover_text_from_file(resume):
        """Extract text from the stored upload when the saved text is missing."""
        try:
            stored_path = os.path.join(current_app.root_path, resume["file_path"])
            if not os.path.isfile(stored_path):
                return ""
            if resume["file_type"] == "pdf":
                return extract_pdf_text(stored_path)
            return extract_docx_text(stored_path)
        except Exception:
            current_app.logger.exception(
                "Unable to re-extract text for resume %s.", resume.get("_id")
            )
            return ""

