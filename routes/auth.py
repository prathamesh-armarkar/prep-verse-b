from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token

from services.auth_service import AuthService
from services.email_service import EmailService

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth"
)


@auth_bp.route("/test", methods=["GET"])
def test():

    return jsonify({
        "success": True,
        "message": "Authentication Module Working Successfully"
    })


@auth_bp.route("/register", methods=["POST"])
def register():

    data = request.get_json()

    response, status = AuthService.register_user(data)

    return jsonify(response), status


@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():

    data = request.get_json()

    response, status = AuthService.verify_otp(data)

    return jsonify(response), status


@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():

    data = request.get_json()

    response, status = AuthService.resend_otp(data)

    return jsonify(response), status


@auth_bp.route("/login", methods=["POST"])
def login():

    data = request.get_json()

    response, status = AuthService.login_user(data)

    return jsonify(response), status


@auth_bp.route("/test-email", methods=["GET"])
def test_email():

    try:
        EmailService.send_otp("prepverseofficial@gmail.com", "123456")
        return jsonify({
            "success": True,
            "message": "Test email sent."
        }), 200
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500