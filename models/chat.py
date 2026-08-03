"""Chat history document helpers for MongoDB.

Documents live in the ``chat_history`` collection::

    {
        "_id": ObjectId,
        "user_id": str (user ObjectId),
        "role": str ("user" | "assistant"),
        "message": str,
        "created_at": datetime,
    }
"""

from datetime import datetime


class ChatHistory:
    COLLECTION = "chat_history"

    @staticmethod
    def create(user_id, role, message):
        from database.db import db

        doc = {
            "user_id": user_id,
            "role": role,
            "message": message,
            "created_at": datetime.utcnow(),
        }
        result = db.collection(ChatHistory.COLLECTION).insert_one(doc)
        return str(result.inserted_id)

    @staticmethod
    def find_recent_by_user(user_id, limit):
        from database.db import db

        cursor = db.collection(ChatHistory.COLLECTION).find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(limit)
        return list(cursor)

    @staticmethod
    def count_by_user(user_id):
        from database.db import db

        return db.collection(ChatHistory.COLLECTION).count_documents({"user_id": user_id})

    @staticmethod
    def count_user_messages(user_id):
        from database.db import db

        return db.collection(ChatHistory.COLLECTION).count_documents(
            {"user_id": user_id, "role": "user"}
        )

    @staticmethod
    def clear_by_user(user_id):
        from database.db import db

        db.collection(ChatHistory.COLLECTION).delete_many({"user_id": user_id})

    @staticmethod
    def delete_by_user(user_id):
        from database.db import db

        db.collection(ChatHistory.COLLECTION).delete_many({"user_id": user_id})

