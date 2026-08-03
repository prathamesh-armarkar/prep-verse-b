"""User document helpers for MongoDB.

Documents live in the ``users`` collection and use the schema::

    {
        "_id": ObjectId,
        "first_name": str,
        "last_name": str,
        "email": str (unique),
        "password": str (bcrypt hash),
        "email_verified": bool,
        "profile_completed": bool,
        "created_at": datetime,
    }
"""

from datetime import datetime

from bson import ObjectId


class User:
    COLLECTION = "users"

    @staticmethod
    def create(data):
        """Insert a new user document and return its ObjectId as a string."""
        from database.db import db

        doc = {
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "email": data["email"],
            "password": data["password"],
            "email_verified": False,
            "profile_completed": False,
            "created_at": datetime.utcnow(),
        }
        result = db.collection(User.COLLECTION).insert_one(doc)
        return str(result.inserted_id)

    @staticmethod
    def find_by_email(email):
        from database.db import db

        return db.collection(User.COLLECTION).find_one({"email": email})

    @staticmethod
    def find_by_id(user_id):
        from database.db import db

        return db.collection(User.COLLECTION).find_one({"_id": ObjectId(user_id)})

    @staticmethod
    def update(user_id, fields):
        from database.db import db

        db.collection(User.COLLECTION).update_one(
            {"_id": ObjectId(user_id)}, {"$set": fields}
        )

    @staticmethod
    def delete(user_id):
        from database.db import db

        db.collection(User.COLLECTION).delete_one({"_id": ObjectId(user_id)})


def serialize_user(user):
    """Convert a users document to a public JSON-safe dict."""
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
    }

