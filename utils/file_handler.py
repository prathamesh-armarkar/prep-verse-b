"""Safe, reusable helpers for resume file validation and storage."""

import os
import uuid
import zipfile

from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE = 5 * 1024 * 1024


class FileValidationError(ValueError):
    pass


def validate_resume_file(uploaded_file):
    if uploaded_file is None or not uploaded_file.filename:
        raise FileValidationError("Resume file missing.")
    original_name = secure_filename(uploaded_file.filename)
    if not original_name:
        raise FileValidationError("The uploaded file name is invalid.")
    extension = os.path.splitext(original_name)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise FileValidationError("Unsupported file type.")
    stream = uploaded_file.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size <= 0:
        raise FileValidationError("The uploaded resume is empty.")
    if size > MAX_FILE_SIZE:
        raise FileValidationError("Resume file must not exceed 5 MB.")
    header = stream.read(8)
    stream.seek(0)
    if extension == ".pdf" and not header.startswith(b"%PDF-"):
        raise FileValidationError("The uploaded PDF file is invalid.")
    if extension == ".docx":
        try:
            if not zipfile.is_zipfile(stream):
                raise FileValidationError("The uploaded DOCX file is invalid.")
        finally:
            stream.seek(0)
    return original_name, extension.lstrip("."), size


def save_resume_file(uploaded_file, upload_root, file_type):
    directory = os.path.join(upload_root, "resumes")
    os.makedirs(directory, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.{file_type}"
    file_path = os.path.join(directory, stored_name)
    uploaded_file.save(file_path)
    return stored_name, file_path


def remove_file_if_exists(file_path):
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)


# ============================================================
# Profile photo helpers
# ============================================================

ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB


class ProfilePhotoError(ValueError):
    pass


def validate_profile_photo(uploaded_file):
    """Validate a profile photo upload. Returns (original_name, extension, size)."""
    if uploaded_file is None or not uploaded_file.filename:
        raise ProfilePhotoError("Profile photo is missing.")

    original_name = secure_filename(uploaded_file.filename)
    if not original_name:
        raise ProfilePhotoError("The uploaded photo name is invalid.")

    extension = os.path.splitext(original_name)[1].lower()
    if extension not in ALLOWED_PHOTO_EXTENSIONS:
        raise ProfilePhotoError("Unsupported file type. Use JPG, PNG or WEBP.")

    stream = uploaded_file.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)

    if size <= 0:
        raise ProfilePhotoError("The uploaded photo is empty.")

    if size > MAX_PHOTO_SIZE:
        raise ProfilePhotoError("Profile photo must not exceed 5 MB.")

    return original_name, extension.lstrip("."), size


def save_profile_photo(uploaded_file, upload_root, file_type):
    """Save a profile photo and return (stored_name, absolute_file_path)."""
    directory = os.path.join(upload_root, "profile_photos")
    os.makedirs(directory, exist_ok=True)
    stored_name = f"profile_{uuid.uuid4().hex}.{file_type}"
    file_path = os.path.join(directory, stored_name)
    uploaded_file.save(file_path)
    return stored_name, file_path
