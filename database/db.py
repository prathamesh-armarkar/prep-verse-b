"""MongoDB database wrapper.

Provides a Flask-style ``db`` object so services can access collections with
``db.collection("users")``. Initialization happens once in ``app.py`` via
``db.init_app(app)`` using the app config (``MONGO_URI`` / ``MONGO_DBNAME``).
"""

from pymongo import MongoClient


class MongoDatabase:
    """Thin, app-aware wrapper around PyMongo."""

    _client = None
    _db = None

    @classmethod
    def init_app(cls, app):
        """Connect to MongoDB and ensure indexes exist."""
        cls._client = MongoClient(
            app.config["MONGO_URI"],
            serverSelectionTimeoutMS=5000,
        )
        cls._db = cls._client[app.config["MONGO_DBNAME"]]
        # Fail fast if the cluster is unreachable.
        cls._db.command("ping")
        cls._ensure_indexes()
        return cls._db

    @classmethod
    def close(cls):
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._db = None

    @classmethod
    def get_db(cls):
        if cls._db is None:
            raise RuntimeError("MongoDB has not been initialized.")
        return cls._db

    @classmethod
    def collection(cls, name):
        """Return a PyMongo collection by name."""
        return cls.get_db()[name]

    @classmethod
    def _ensure_indexes(cls):
        """Create the indexes required by the application queries."""
        users = cls._db["users"]
        otps = cls._db["otp_verifications"]
        profiles = cls._db["profiles"]
        resumes = cls._db["resumes"]
        roadmaps = cls._db["roadmaps"]
        chats = cls._db["chat_history"]

        users.create_index("email", unique=True)
        otps.create_index([("email", 1)])
        otps.create_index([("user_id", 1)])
        profiles.create_index("user_id", unique=True)
        resumes.create_index([("user_id", 1)])
        roadmaps.create_index([("user_id", 1)])
        chats.create_index([("user_id", 1)])


# Singleton used across the application.
db = MongoDatabase()

