"""Profile document helpers for MongoDB.

Documents live in the ``profiles`` collection (one per user)::

    {
        "_id": ObjectId,
        "user_id": str (user ObjectId, unique),
        "phone": str|None,
        "city": str|None,
        "state": str|None,
        "college_name": str|None,
        "degree": str|None,
        "branch": str|None,
        "graduation_year": str|None,
        "current_semester": str|None,
        "cgpa": str|None,
        "target_role": str|None,
        "bio": str|None,
        "skills": [str],
        "interests": [str],
        "linkedin": str|None,
        "github": str|None,
        "portfolio": str|None,
        "date_of_birth": str|None (YYYY-MM-DD),
        "gender": str|None,
        "profile_image": str|None,
        "created_at": datetime,
        "updated_at": datetime,
    }
"""

from datetime import datetime


class Profile:
    COLLECTION = "profiles"

    @staticmethod
    def create_empty(user_id):
        from database.db import db

        now = datetime.utcnow()
        doc = {
            "user_id": user_id,
            "phone": None,
            "city": None,
            "state": None,
            "college_name": None,
            "degree": None,
            "branch": None,
            "graduation_year": None,
            "current_semester": None,
            "cgpa": None,
            "target_role": None,
            "bio": None,
            "skills": [],
            "interests": [],
            "linkedin": None,
            "github": None,
            "portfolio": None,
            "date_of_birth": None,
            "gender": None,
            "profile_image": None,
            "created_at": now,
            "updated_at": now,
        }
        db.collection(Profile.COLLECTION).insert_one(doc)
        return doc

    @staticmethod
    def find_by_user_id(user_id):
        from database.db import db

        return db.collection(Profile.COLLECTION).find_one({"user_id": user_id})

    @staticmethod
    def upsert(user_id, fields):
        from database.db import db

        db.collection(Profile.COLLECTION).update_one(
            {"user_id": user_id},
            {"$set": {**fields, "updated_at": datetime.utcnow()}},
            upsert=True,
        )

    @staticmethod
    def update(user_id, fields):
        from database.db import db

        db.collection(Profile.COLLECTION).update_one(
            {"user_id": user_id},
            {"$set": {**fields, "updated_at": datetime.utcnow()}},
        )

    @staticmethod
    def delete_by_user_id(user_id):
        from database.db import db

        db.collection(Profile.COLLECTION).delete_one({"user_id": user_id})

