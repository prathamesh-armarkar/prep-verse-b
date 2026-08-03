"""Resume document helpers for MongoDB.

Documents live in the ``resumes`` collection::

    {
        "_id": ObjectId,
        "user_id": str (user ObjectId),
        "original_name": str,
        "stored_name": str,
        "file_path": str,
        "file_size": int,
        "file_type": str,
        "extracted_text": str,
        "parsed_data_json": dict|None,
        "analysis_json": dict|None,
        "target_role": str|None,
        "job_description": str|None,
        "created_at": datetime,
        "updated_at": datetime,
    }
"""

from datetime import datetime


class Resume:
    COLLECTION = "resumes"

    @staticmethod
    def create(data):
        from database.db import db

        now = datetime.utcnow()
        doc = {
            "user_id": data["user_id"],
            "original_name": data["original_name"],
            "stored_name": data["stored_name"],
            "file_path": data["file_path"],
            "file_size": data["file_size"],
            "file_type": data["file_type"],
            "extracted_text": data.get("extracted_text", ""),
            "parsed_data_json": None,
            "analysis_json": None,
            "target_role": data.get("target_role"),
            "job_description": data.get("job_description"),
            "created_at": now,
            "updated_at": now,
        }
        result = db.collection(Resume.COLLECTION).insert_one(doc)
        return str(result.inserted_id)

    @staticmethod
    def update(resume_id, fields):
        from database.db import db
        from bson import ObjectId

        db.collection(Resume.COLLECTION).update_one(
            {"_id": ObjectId(resume_id)},
            {"$set": {**fields, "updated_at": datetime.utcnow()}},
        )

    @staticmethod
    def find_latest_by_user(user_id):
        from database.db import db

        return db.collection(Resume.COLLECTION).find_one(
            {"user_id": user_id}, sort=[("created_at", -1), ("_id", -1)]
        )

    @staticmethod
    def find_all_by_user(user_id):
        from database.db import db

        cursor = db.collection(Resume.COLLECTION).find(
            {"user_id": user_id}
        ).sort([("created_at", -1), ("_id", -1)])
        return list(cursor)

    @staticmethod
    def find_by_id(resume_id):
        from database.db import db
        from bson import ObjectId

        return db.collection(Resume.COLLECTION).find_one({"_id": ObjectId(resume_id)})

    @staticmethod
    def count_by_user(user_id):
        from database.db import db

        return db.collection(Resume.COLLECTION).count_documents({"user_id": user_id})

    @staticmethod
    def delete_by_user(user_id):
        from database.db import db

        db.collection(Resume.COLLECTION).delete_many({"user_id": user_id})


def serialize_resume(resume):
    """Convert a resumes document to a JSON-safe dict."""
    return {
        "id": str(resume["_id"]),
        "file_name": resume.get("original_name", ""),
        "file_type": resume.get("file_type", ""),
        "file_size": resume.get("file_size", 0),
        "uploaded_at": resume.get("created_at").isoformat() if resume.get("created_at") else None,
        "updated_at": resume.get("updated_at").isoformat() if resume.get("updated_at") else None,
        "extracted_text_length": len(resume.get("extracted_text") or ""),
        "ats_score": (resume.get("analysis_json") or {}).get("ats_score"),
        "target_role": resume.get("target_role"),
        "parsed_data": resume.get("parsed_data_json"),
        "analysis": resume.get("analysis_json"),
    }

