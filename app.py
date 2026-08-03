import os

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import Config
from database.db import db
from database.mail import mail

# Import Blueprints
from routes.auth import auth_bp
from routes.profile import profile_bp
from routes.resume import resume_bp
from routes.chat import chat_bp
from routes.roadmap import roadmap_bp
from routes.dashboard import dashboard_bp


def create_app():

    app = Flask(__name__)

    # ==========================================
    # Load Configuration
    # ==========================================

    app.config.from_object(Config)

    # ==========================================
    # Enable CORS
    # ==========================================

    # Allow any origin; the frontend uses JWT Bearer tokens (Authorization
    # header), not cookies, so no credentials are required.
    CORS(
        app,
        resources={r"/*": {"origins": "*"}},
        supports_credentials=False,  # Must be False when using "*"
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )

    # ==========================================
    # Initialize Extensions
    # ==========================================

    jwt = JWTManager(app)
    mail.init_app(app)

    # Initialize MongoDB connection (creates indexes, fails fast if unreachable).
    try:
        db.init_app(app)
        print("MongoDB Connected Successfully")
    except Exception as exc:
        print("MongoDB Connection Failed")
        print(exc)
        # Re-raise so the app does not start in a broken state.
        raise

    @jwt.unauthorized_loader
    def missing_jwt(reason):
        app.logger.warning("JWT rejected: %s", reason)
        return jsonify({"success": False, "message": "Authentication token is missing."}), 401

    @jwt.invalid_token_loader
    def invalid_jwt(reason):
        app.logger.warning("JWT rejected: %s", reason)
        return jsonify({"success": False, "message": "Authentication token is invalid. Please log in again."}), 401

    @jwt.expired_token_loader
    def expired_jwt(_header, _payload):
        app.logger.warning("JWT rejected: access token expired")
        return jsonify({"success": False, "message": "Your session has expired. Please log in again."}), 401

    # ==========================================
    # Register Blueprints
    # ==========================================

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(resume_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(roadmap_bp)
    app.register_blueprint(dashboard_bp)

    @app.errorhandler(413)
    def request_entity_too_large(_error):
        return jsonify({"success": False, "message": "Resume file must not exceed 5 MB."}), 413

    # ==========================================
    # Serve uploaded profile photos
    # ==========================================

    profile_photo_dir = os.path.join(app.config["UPLOAD_FOLDER"], "profile_photos")
    os.makedirs(profile_photo_dir, exist_ok=True)

    @app.route("/uploads/profile_photos/<path:filename>")
    def serve_profile_photo(filename):
        return send_from_directory(profile_photo_dir, filename)

    # ==========================================
    # Root Route
    # ==========================================

    @app.route("/")
    def home():
        return jsonify({
            "success": True,
            "message": "Welcome to PrepVerse AI Backend 🚀",
            "version": "1.0.0",
        })

    # ==========================================
    # Health Check
    # ==========================================

    @app.route("/api/health")
    def health():
        return jsonify({
            "success": True,
            "status": "Running",
            "database": "Connected",
            "mail": "Configured",
            "message": "PrepVerse AI Backend is running successfully.",
        })

    return app


app = create_app()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )

