import base64
import os
import re

from bson import ObjectId
from flask import current_app

from database.db import db
from models.user import User
from models.profile import Profile
from utils.file_handler import (
    ProfilePhotoError,
    remove_file_if_exists,
    save_profile_photo,
    validate_profile_photo,
)

# ============================================================
# Completion calculator configuration
# ============================================================
COMPLETION_SECTIONS = [
    {"key": "photo", "label": "Photo"},
    {"key": "phone", "label": "Phone"},
    {"key": "college", "label": "College"},
    {"key": "degree", "label": "Degree"},
    {"key": "specialization", "label": "Specialization"},
    {"key": "graduation", "label": "Graduation"},
    {"key": "bio", "label": "Bio"},
    {"key": "linkedin", "label": "LinkedIn"},
    {"key": "skills", "label": "Skills"},
    {"key": "target_role", "label": "Target Role"},
]

PHONE_PATTERN = re.compile(r"^\+?[0-9\s\-()]{10,20}$")
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"^(19[5-9]\d|20[0-2]\d|2100)$")
CGPA_PATTERN = re.compile(r"^\d{1,2}(\.\d{1,2})?$")


class ProfileService:

    # ============================================================
    # Getters
    # ============================================================

    @staticmethod
    def get_profile(user_id):
        """Return the full profile payload for the authenticated user."""
        try:
            user_id = str(user_id)
            user = User.find_by_id(user_id)
        except Exception:
            current_app.logger.exception("Unable to load user for profile")
            return {"success": False, "message": "Profile could not be loaded."}, 500

        if user is None:
            return {"success": False, "message": "User not found."}, 404

        try:
            profile = Profile.find_by_user_id(user_id)
        except Exception:
            current_app.logger.exception("Unable to load profile for user %s", user_id)
            return {"success": False, "message": "Profile could not be loaded."}, 500

        if profile is None:
            try:
                profile = Profile.create_empty(user_id)
            except Exception:
                current_app.logger.exception("Unable to create empty profile for user %s", user_id)
                return {"success": False, "message": "Profile could not be loaded."}, 500

        payload = ProfileService._serialize_profile(user, profile)
        return {"success": True, "profile": payload}, 200

    # ============================================================
    # Updates
    # ============================================================

    @staticmethod
    def update_profile(user_id, data):
        """Update every editable profile field with validation."""
        if data is None:
            data = {}

        try:
            user_id = str(user_id)
            user = User.find_by_id(user_id)
        except Exception:
            current_app.logger.exception("Unable to load user for profile update")
            return {"success": False, "message": "Profile could not be updated."}, 500

        if user is None:
            return {"success": False, "message": "User not found."}, 404

        validation_error = ProfileService._validate_update_payload(data)
        if validation_error:
            return {"success": False, "message": validation_error}, 400

        try:
            # Identity (full name is stored as first/last name)
            first_name = (data.get("first_name") or user.get("first_name") or "").strip()
            last_name = (data.get("last_name") or user.get("last_name") or "").strip()
            if not first_name:
                return {"success": False, "message": "First name is required."}, 400

            User.update(user_id, {"first_name": first_name, "last_name": last_name})

            profile_fields = {
                "phone": (data.get("phone") or "").strip() or None,
                "city": (data.get("city") or "").strip() or None,
                "state": (data.get("state") or "").strip() or None,
                "college_name": (data.get("college") or "").strip() or None,
                "degree": (data.get("degree") or "").strip() or None,
                "branch": (data.get("specialization") or "").strip() or None,
                "graduation_year": (data.get("graduation_year") or "").strip() or None,
                "current_semester": (data.get("current_semester") or "").strip() or None,
                "cgpa": (data.get("cgpa") or "").strip() or None,
                "target_role": (data.get("target_role") or "").strip() or None,
                "bio": (data.get("bio") or "").strip() or None,
                "skills": ProfileService._normalize_list(data.get("skills")),
                "interests": ProfileService._normalize_list(data.get("interests")),
                "linkedin": ProfileService._clean_url(data.get("linkedin_url")),
                "github": ProfileService._clean_url(data.get("github_url")),
                "portfolio": ProfileService._clean_url(data.get("portfolio_url")),
                "gender": (data.get("gender") or "").strip() or None,
                "date_of_birth": ProfileService._parse_date(data.get("date_of_birth")),
            }

            required = [
                profile_fields["college_name"], profile_fields["degree"],
                profile_fields["branch"], profile_fields["graduation_year"],
                profile_fields["phone"], profile_fields["target_role"],
            ]
            profile_completed = all(bool(value) for value in required)
            User.update(user_id, {"profile_completed": profile_completed})

            Profile.upsert(user_id, profile_fields)
        except Exception:
            current_app.logger.exception("Unexpected profile update failure")
            return {"success": False, "message": "Profile could not be saved."}, 500

        user = User.find_by_id(user_id)
        profile = Profile.find_by_user_id(user_id)
        payload = ProfileService._serialize_profile(user, profile)
        return {
            "success": True,
            "message": "Profile updated successfully.",
            "profile": payload,
        }, 200

    # ============================================================
    # Photo
    # ============================================================

    @staticmethod
    def update_photo(user_id, uploaded_file):
        """Validate, save, and attach a new profile photo."""
        try:
            user_id = str(user_id)
            user = User.find_by_id(user_id)
        except Exception:
            current_app.logger.exception("Unable to load user for photo update")
            return {"success": False, "message": "Profile photo could not be updated."}, 500

        if user is None:
            return {"success": False, "message": "User not found."}, 404

        try:
            _original_name, file_type, _size = validate_profile_photo(uploaded_file)
        except ProfilePhotoError as exc:
            return {"success": False, "message": str(exc)}, 400

        saved_path = None
        try:
            stored_name, saved_path = save_profile_photo(
                uploaded_file, current_app.config["UPLOAD_FOLDER"], file_type
            )
        except OSError as exc:
            current_app.logger.exception("Profile photo save failed")
            return {"success": False, "message": "Failed to save profile photo.", "error": str(exc)}, 500

        profile = Profile.find_by_user_id(user_id)
        old_photo = profile.get("profile_image") if profile else None

        try:
            Profile.upsert(user_id, {"profile_image": f"/uploads/profile_photos/{stored_name}"})
        except Exception:
            remove_file_if_exists(saved_path)
            current_app.logger.exception("Profile photo DB update failed")
            return {"success": False, "message": "Profile photo could not be saved."}, 500

        ProfileService._remove_stored_photo(old_photo)

        user = User.find_by_id(user_id)
        profile = Profile.find_by_user_id(user_id)
        payload = ProfileService._serialize_profile(user, profile)
        return {
            "success": True,
            "message": "Profile photo updated successfully.",
            "profile": payload,
        }, 200

    @staticmethod
    def delete_photo(user_id):
        """Delete the user's profile photo."""
        try:
            user_id = str(user_id)
            user = User.find_by_id(user_id)
        except Exception:
            current_app.logger.exception("Unable to load user for photo delete")
            return {"success": False, "message": "Profile photo could not be deleted."}, 500

        if user is None:
            return {"success": False, "message": "User not found."}, 404

        profile = Profile.find_by_user_id(user_id)
        if profile is None:
            return {"success": True, "message": "No profile photo to delete."}, 200

        old_photo = profile.get("profile_image")
        try:
            Profile.update(user_id, {"profile_image": None})
        except Exception:
            current_app.logger.exception("Profile photo delete DB failed")
            return {"success": False, "message": "Profile photo could not be deleted."}, 500

        ProfileService._remove_stored_photo(old_photo)

        user = User.find_by_id(user_id)
        profile = Profile.find_by_user_id(user_id)
        payload = ProfileService._serialize_profile(user, profile)
        return {
            "success": True,
            "message": "Profile photo removed successfully.",
            "profile": payload,
        }, 200

    # ============================================================
    # Delete account
    # ============================================================

    @staticmethod
    def delete_account(user_id):
        """Permanently delete the user and all associated data."""
        try:
            user_id = str(user_id)
            user = User.find_by_id(user_id)
        except Exception:
            current_app.logger.exception("Unable to load user for account deletion")
            return {"success": False, "message": "Account could not be deleted."}, 500

        if user is None:
            return {"success": False, "message": "User not found."}, 404

        # Collect files to remove BEFORE deleting the user.
        photo_to_remove = None
        resume_files = []
        profile = Profile.find_by_user_id(user_id)
        if profile and profile.get("profile_image"):
            photo_to_remove = profile["profile_image"]

        from models.resume import Resume
        resumes = Resume.find_all_by_user(user_id)
        resume_files = [r.get("file_path") for r in resumes if r.get("file_path")]

        # Delete all dependent documents.
        from models.otp import OTPVerification
        from models.roadmap import Roadmap
        from models.chat import ChatHistory
        try:
            Profile.delete_by_user_id(user_id)
            Resume.delete_by_user(user_id)
            Roadmap.delete_by_user(user_id)
            ChatHistory.delete_by_user(user_id)
            OTPVerification.delete_for_user(user_id)
            User.delete(user_id)
        except Exception:
            current_app.logger.exception("Account deletion DB failed for user %s", user_id)
            return {"success": False, "message": "Account could not be deleted."}, 500

        if photo_to_remove:
            ProfileService._remove_stored_photo(photo_to_remove)
        for file_path in resume_files:
            try:
                full_path = os.path.join(current_app.root_path, file_path)
                remove_file_if_exists(full_path)
            except Exception:
                current_app.logger.warning("Could not remove resume file %s", file_path)

        return {
            "success": True,
            "message": "Your account has been permanently deleted.",
        }, 200

    # ============================================================
    # Completion calculator
    # ============================================================

    @staticmethod
    def calculate_completion(profile):
        """Return (percentage, completed_count, total_sections)."""
        if profile is None:
            return 0, 0, len(COMPLETION_SECTIONS)

        def is_filled(value):
            if value is None:
                return False
            if isinstance(value, str):
                return bool(value.strip()) and not value.startswith("data:image")
            if isinstance(value, list):
                return len([item for item in value if str(item).strip()]) > 0
            return bool(value)

        checks = {
            "photo": is_filled(profile.get("profile_image")),
            "phone": is_filled(profile.get("phone")),
            "college": is_filled(profile.get("college_name")),
            "degree": is_filled(profile.get("degree")),
            "specialization": is_filled(profile.get("branch")),
            "graduation": is_filled(profile.get("graduation_year")),
            "bio": is_filled(profile.get("bio")),
            "linkedin": is_filled(profile.get("linkedin")),
            "skills": is_filled(profile.get("skills")),
            "target_role": is_filled(profile.get("target_role")),
        }

        total = len(COMPLETION_SECTIONS)
        completed = sum(1 for section in COMPLETION_SECTIONS if checks.get(section["key"]))
        percentage = int(round((completed / total) * 100)) if total else 0
        return percentage, completed, total

    # ============================================================
    # Serialization
    # ============================================================

    @staticmethod
    def _serialize_profile(user, profile):
        completion_percent, completed_sections, total_sections = ProfileService.calculate_completion(profile)
        return {
            "id": str(user["_id"]),
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "full_name": " ".join(
                part for part in (user.get("first_name", ""), user.get("last_name", "")) if part
            ).strip() or user["email"],
            "email_verified": bool(user.get("email_verified", False)),
            "profile_completed": bool(user.get("profile_completed", False)),

            # Contact
            "phone": profile.get("phone") or "",
            "city": profile.get("city") or "",
            "state": profile.get("state") or "",

            # Education
            "college": profile.get("college_name") or "",
            "degree": profile.get("degree") or "",
            "specialization": profile.get("branch") or "",
            "graduation_year": profile.get("graduation_year") or "",
            "current_semester": profile.get("current_semester") or "",
            "cgpa": profile.get("cgpa") or "",

            # Career
            "target_role": profile.get("target_role") or "",
            "bio": profile.get("bio") or "",
            "skills": profile.get("skills") or [],
            "interests": profile.get("interests") or [],

            # Social
            "linkedin_url": profile.get("linkedin") or "",
            "github_url": profile.get("github") or "",
            "portfolio_url": profile.get("portfolio") or "",

            # Personal
            "gender": profile.get("gender") or "",
            "date_of_birth": profile.get("date_of_birth") or "",

            # Photo
            "profile_photo": ProfileService._photo_url(profile.get("profile_image")),

            # Meta
            "created_at": profile.get("created_at").isoformat() if profile.get("created_at") else None,
            "updated_at": profile.get("updated_at").isoformat() if profile.get("updated_at") else None,

            # Completion
            "completion": {
                "percentage": completion_percent,
                "completed_sections": completed_sections,
                "total_sections": total_sections,
                "sections": [
                    {
                        "key": section["key"],
                        "label": section["label"],
                        "completed": bool(ProfileService._section_value(profile, section["key"])),
                    }
                    for section in COMPLETION_SECTIONS
                ],
            },
        }

    @staticmethod
    def _section_value(profile, key):
        """Return the underlying value used to decide section completion."""
        profile_image = profile.get("profile_image")
        if key == "photo":
            return bool(profile_image and not str(profile_image).startswith("data:image"))
        if key == "skills":
            return bool(profile.get("skills"))
        mapping = {
            "phone": "phone",
            "college": "college_name",
            "degree": "degree",
            "specialization": "branch",
            "graduation": "graduation_year",
            "bio": "bio",
            "linkedin": "linkedin",
            "target_role": "target_role",
        }
        return profile.get(mapping.get(key, key))

    @staticmethod
    def _photo_url(profile_image):
        """Return a renderable, absolute URL for the stored profile photo."""
        if not profile_image:
            return ""
        value = str(profile_image)
        if value.startswith("data:"):
            return value
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if value.startswith("/uploads/"):
            # Frontend lives on a different domain; prefix with backend base URL.
            return f"{current_app.config['PUBLIC_BASE_URL']}{value}"
        if "profile_" in value:
            return f"{current_app.config['PUBLIC_BASE_URL']}/uploads/profile_photos/{value}"
        return value

    @staticmethod
    def _remove_stored_photo(profile_image):
        """Best-effort removal of a stored photo file on disk."""
        if not profile_image:
            return
        value = str(profile_image)
        if value.startswith("data:") or value.startswith("http"):
            return
        name = value.rsplit("/", 1)[-1] if "/" in value else value
        full_path = os.path.join(
            current_app.config["UPLOAD_FOLDER"], "profile_photos", name
        )
        try:
            remove_file_if_exists(full_path)
        except Exception:
            current_app.logger.warning("Could not remove old profile photo %s", full_path)

    # ============================================================
    # Validation helpers
    # ============================================================

    @staticmethod
    def _validate_update_payload(data):
        phone = data.get("phone")
        if phone and not PHONE_PATTERN.match(str(phone)):
            return "Phone number must contain 10-15 digits and only +, space, dash or parentheses."

        for field in ("linkedin_url", "github_url", "portfolio_url"):
            value = data.get(field)
            if value and not URL_PATTERN.match(str(value)):
                return "Social links must start with http:// or https://."

        graduation_year = data.get("graduation_year")
        if graduation_year and not YEAR_PATTERN.match(str(graduation_year)):
            return "Graduation year must be a valid 4-digit year between 1950 and 2100."

        cgpa = data.get("cgpa")
        if cgpa and not CGPA_PATTERN.match(str(cgpa)):
            return "CGPA must be a number between 0 and 10 (up to 2 decimal places)."

        try:
            cgpa_value = float(cgpa)
            if not (0.0 <= cgpa_value <= 10.0):
                return "CGPA must be between 0 and 10."
        except (TypeError, ValueError):
            if cgpa:
                return "CGPA must be a number between 0 and 10."

        for field in ("skills", "interests"):
            value = data.get(field)
            if value is not None and not isinstance(value, list):
                return f"{field.title()} must be a list."

        return None

    @staticmethod
    def _normalize_list(value):
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _clean_url(value):
        if not value:
            return None
        value = str(value).strip()
        return value if value else None

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return str(value)[:10]
        except (TypeError, ValueError):
            return None

    # ============================================================
    # Legacy complete_profile (used by the signup flow)
    # ============================================================

    @staticmethod
    def complete_profile(data):
        email = (data.get("email") or "").strip().lower()

        if not email:
            return {"success": False, "message": "Email is required."}, 400

        user = User.find_by_email(email)
        if not user:
            return {"success": False, "message": "User not found."}, 404

        user_id = str(user["_id"])
        college_name = (data.get("college") or "").strip()
        degree = (data.get("degree") or "").strip()
        graduation_year = (data.get("year") or "").strip()
        career_goal = (data.get("careerGoal") or "").strip()
        skills = data.get("skills") or []
        profile_image = data.get("profileImage") or ""

        if not college_name or not degree or not graduation_year or not career_goal:
            return {"success": False, "message": "Please complete all required profile fields."}, 400

        if not isinstance(skills, list):
            skills = []
        skills = [str(skill).strip() for skill in skills if str(skill).strip()]

        try:
            profile = Profile.find_by_user_id(user_id)
            if not profile:
                profile = Profile.create_empty(user_id)

            fields = {
                "college_name": college_name,
                "degree": degree,
                "graduation_year": graduation_year,
                "skills": skills,
                "target_role": career_goal,
            }

            if profile_image and str(profile_image).startswith("data:"):
                stored_path = ProfileService._save_base64_photo(profile_image)
                if stored_path:
                    fields["profile_image"] = stored_path
            elif profile_image and not profile.get("profile_image"):
                fields["profile_image"] = profile_image

            Profile.upsert(user_id, fields)
            User.update(user_id, {"profile_completed": True})

            user = User.find_by_id(user_id)
            profile = Profile.find_by_user_id(user_id)
            return {
                "success": True,
                "message": "Profile completed successfully.",
                "profile": ProfileService._serialize_profile(user, profile),
            }, 200

        except Exception as exc:
            return {
                "success": False,
                "message": "Profile could not be saved right now.",
                "error": str(exc),
            }, 500

    @staticmethod
    def _save_base64_photo(data_url):
        """Persist a base64 data URL to the profile_photos folder."""
        try:
            if "," not in data_url:
                return None
            header, b64data = data_url.split(",", 1)

            ext_match = re.search(r"image/(\w+)", header)
            ext = ext_match.group(1).lower() if ext_match else "png"
            if ext not in ("jpg", "jpeg", "png", "webp"):
                ext = "png"
            if ext == "jpeg":
                ext = "jpg"

            raw = base64.b64decode(b64data)
            directory = os.path.join(current_app.config["UPLOAD_FOLDER"], "profile_photos")
            os.makedirs(directory, exist_ok=True)

            import uuid as _uuid
            stored_name = f"profile_{_uuid.uuid4().hex}.{ext}"
            file_path = os.path.join(directory, stored_name)
            with open(file_path, "wb") as handle:
                handle.write(raw)
            return f"/uploads/profile_photos/{stored_name}"
        except Exception:
            current_app.logger.exception("Failed to persist base64 profile photo")
            return None

