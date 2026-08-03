"""Roadmap document helpers for MongoDB.

Documents live in the ``roadmaps`` collection::

    {
        "_id": ObjectId,
        "user_id": str (user ObjectId),
        "career_goal": str,
        "current_level": str,
        "roadmap_json": dict,
        "completion_percentage": float,
        "created_at": datetime,
        "updated_at": datetime,
    }
"""

from datetime import datetime


class Roadmap:
    COLLECTION = "roadmaps"

    @staticmethod
    def create(data):
        from database.db import db

        now = datetime.utcnow()
        doc = {
            "user_id": data["user_id"],
            "career_goal": data["career_goal"],
            "current_level": data["current_level"],
            "roadmap_json": data.get("roadmap_json", {}),
            "completion_percentage": float(data.get("completion_percentage", 0.0)),
            "created_at": now,
            "updated_at": now,
        }
        result = db.collection(Roadmap.COLLECTION).insert_one(doc)
        return str(result.inserted_id)

    @staticmethod
    def find_latest_by_user(user_id):
        from database.db import db

        return db.collection(Roadmap.COLLECTION).find_one(
            {"user_id": user_id}, sort=[("created_at", -1), ("_id", -1)]
        )

    @staticmethod
    def find_all_by_user(user_id):
        from database.db import db

        cursor = db.collection(Roadmap.COLLECTION).find(
            {"user_id": user_id}
        ).sort([("created_at", -1), ("_id", -1)])
        return list(cursor)

    @staticmethod
    def find_by_id_and_user(roadmap_id, user_id):
        from database.db import db
        from bson import ObjectId

        try:
            oid = ObjectId(roadmap_id)
        except Exception:
            return None
        return db.collection(Roadmap.COLLECTION).find_one(
            {"_id": oid, "user_id": user_id}
        )

    @staticmethod
    def count_by_user(user_id):
        from database.db import db

        return db.collection(Roadmap.COLLECTION).count_documents({"user_id": user_id})

    @staticmethod
    def update_progress(roadmap_id, user_id, completion_percentage):
        from database.db import db
        from bson import ObjectId

        result = db.collection(Roadmap.COLLECTION).update_one(
            {"_id": ObjectId(roadmap_id), "user_id": user_id},
            {
                "$set": {
                    "completion_percentage": max(0.0, min(100.0, float(completion_percentage))),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.matched_count > 0

    @staticmethod
    def delete(roadmap_id, user_id):
        from database.db import db
        from bson import ObjectId

        result = db.collection(Roadmap.COLLECTION).delete_one(
            {"_id": ObjectId(roadmap_id), "user_id": user_id}
        )
        return result.deleted_count > 0

    @staticmethod
    def delete_by_user(user_id):
        from database.db import db

        db.collection(Roadmap.COLLECTION).delete_many({"user_id": user_id})


def serialize_roadmap(roadmap):
    """Convert a roadmaps document to a JSON-safe dict."""
    return {
        "id": str(roadmap["_id"]),
        "career_goal": roadmap.get("career_goal", ""),
        "current_level": roadmap.get("current_level", ""),
        "roadmap": roadmap.get("roadmap_json", {}),
        "completion_percentage": roadmap.get("completion_percentage", 0.0),
        "created_at": roadmap.get("created_at").isoformat() if roadmap.get("created_at") else None,
        "updated_at": roadmap.get("updated_at").isoformat() if roadmap.get("updated_at") else None,
    }

