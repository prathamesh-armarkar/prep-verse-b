import os
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:

    # ==========================================
    # Flask Configuration
    # ==========================================

    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    # Flask-JWT-Extended defaults to only 15 minutes. Use an explicit session
    # lifetime so normal dashboard activity does not invalidate its token.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)

    # ==========================================
    # MongoDB Configuration
    # ==========================================

    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/prepverse")
    MONGO_DBNAME = os.getenv("MONGO_DBNAME", "prepverse")

    # ==========================================
    # File Uploads
    # ==========================================

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # Public base URL used to build absolute URLs for stored files. Because the
    # frontend and backend live on different domains, relative /uploads/ paths
    # must be prefixed with this value so the browser can load them.
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://prep-verse-b.onrender.com")

    # ==========================================
    # Flask Mail Configuration
    # ==========================================

    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False

    MAIL_USERNAME = os.getenv("MAIL_EMAIL", "").strip()
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "").strip().replace(" ", "")

    MAIL_DEFAULT_SENDER = os.getenv("MAIL_EMAIL", "").strip()

    # ==========================================
    # Groq AI Configuration (Resume Analysis)
    # ==========================================

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.2"))
    GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "2400"))
    GROQ_INPUT_CHARS = int(os.getenv("GROQ_INPUT_CHARS", "7000"))
    GROQ_CACHE_TTL = int(os.getenv("GROQ_CACHE_TTL", "3600"))

