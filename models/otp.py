"""OTP verification document helpers for MongoDB.

Documents live in the ``otp_verifications`` collection::

    {
        "_id": ObjectId,
        "user_id": str (user ObjectId),
        "email": str,
        "otp": str (6 digits),
        "verified": bool,
        "expires_at": datetime,
        "created_at": datetime,
    }
"""

from datetime import datetime, timedelta


class OTPVerification:
    COLLECTION = "otp_verifications"

    @staticmethod
    def delete_for_user(user_id):
        from database.db import db

        db.collection(OTPVerification.COLLECTION).delete_many({"user_id": user_id})

    @staticmethod
    def create(user_id, email, otp):
        from database.db import db

        doc = {
            "user_id": user_id,
            "email": email,
            "otp": otp,
            "verified": False,
            "expires_at": datetime.utcnow() + timedelta(minutes=5),
            "created_at": datetime.utcnow(),
        }
        result = db.collection(OTPVerification.COLLECTION).insert_one(doc)
        return str(result.inserted_id)

    @staticmethod
    def find_latest_by_email(email):
        from database.db import db

        return db.collection(OTPVerification.COLLECTION).find_one(
            {"email": email},
            sort=[("created_at", -1)],
        )

    @staticmethod
    def mark_verified(otp_id):
        from database.db import db
        from bson import ObjectId

        db.collection(OTPVerification.COLLECTION).update_one(
            {"_id": ObjectId(otp_id)}, {"$set": {"verified": True}}
        )

    @staticmethod
    def delete_others(user_id, keep_id):
        from database.db import db
        from bson import ObjectId

        db.collection(OTPVerification.COLLECTION).delete_many(
            {"user_id": user_id, "_id": {"$ne": ObjectId(keep_id)}}
        )

