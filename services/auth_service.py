import bcrypt
from datetime import datetime

from flask_jwt_extended import create_access_token

from database.db import db
from models.user import User, serialize_user
from models.otp import OTPVerification
from services.otp_service import OTPService
from services.email_service import EmailService


class AuthService:

    @staticmethod
    def register_user(data):
        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not first_name:
            return {"success": False, "message": "First name is required."}, 400
        if not last_name:
            return {"success": False, "message": "Last name is required."}, 400
        if not email:
            return {"success": False, "message": "Email is required."}, 400
        if not password:
            return {"success": False, "message": "Password is required."}, 400
        if len(password) < 8:
            return {"success": False, "message": "Password must be at least 8 characters."}, 400

        existing_user = User.find_by_email(email)
        if existing_user:
            return {"success": False, "message": "Email already registered."}, 409

        hashed_password = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        try:
            user_id = User.create({
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "password": hashed_password,
            })

            print("Sending OTP...")
            otp = OTPService.generate_otp()
            OTPService.save_otp(user_id, email, otp)

            try:
                EmailService.send_otp(email, otp)
            except Exception as exc:
                print(f"Registration failed: {exc}")
                return {
                    "success": False,
                    "message": "Registration failed. OTP email could not be sent.",
                    "error": str(exc),
                }, 500

            return {
                "success": True,
                "message": "Registration successful. OTP sent to your email.",
                "email": email,
            }, 201

        except Exception as exc:
            print(f"Registration failed: {exc}")
            return {
                "success": False,
                "message": "Registration failed. Please try again later.",
                "error": str(exc),
            }, 500

    @staticmethod
    def verify_otp(data):
        email = data.get("email", "").strip().lower()
        otp = data.get("otp", "").strip()

        if not email:
            return {"success": False, "message": "Email is required."}, 400
        if not otp:
            return {"success": False, "message": "OTP is required."}, 400

        user = User.find_by_email(email)
        if not user:
            return {"success": False, "message": "User not found."}, 404

        otp_record = OTPVerification.find_latest_by_email(email)
        if not otp_record:
            return {"success": False, "message": "Invalid OTP."}, 404

        if otp_record["expires_at"] < datetime.utcnow():
            return {"success": False, "message": "OTP expired."}, 400

        if otp_record["otp"] != otp:
            return {"success": False, "message": "Invalid OTP."}, 400

        try:
            user_id = str(user["_id"])
            OTPVerification.mark_verified(str(otp_record["_id"]))
            User.update(user_id, {"email_verified": True})
            OTPVerification.delete_others(user_id, str(otp_record["_id"]))

            return {"success": True, "message": "Email verified successfully."}, 200

        except Exception:
            return {
                "success": False,
                "message": "OTP verification failed. Please try again later.",
            }, 500

    @staticmethod
    def resend_otp(data):
        email = data.get("email", "").strip().lower()

        if not email:
            return {"success": False, "message": "Email is required."}, 400

        user = User.find_by_email(email)
        if not user:
            return {"success": False, "message": "User not found."}, 404

        try:
            print("Sending OTP...")
            otp = OTPService.generate_otp()
            OTPService.save_otp(str(user["_id"]), email, otp)

            try:
                EmailService.send_otp(email, otp)
            except Exception as exc:
                print(f"OTP resend failed: {exc}")
                return {
                    "success": False,
                    "message": "OTP email could not be sent.",
                    "error": str(exc),
                }, 500

            return {"success": True, "message": "OTP sent successfully."}, 200

        except Exception as exc:
            print(f"OTP resend failed: {exc}")
            return {
                "success": False,
                "message": "Failed to resend OTP. Please try again later.",
                "error": str(exc),
            }, 500

    @staticmethod
    def login_user(data):
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email:
            return {"success": False, "message": "Email is required."}, 400
        if not password:
            return {"success": False, "message": "Password is required."}, 400

        user = User.find_by_email(email)
        if not user:
            return {"success": False, "message": "Invalid email or password."}, 401

        if not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
            return {"success": False, "message": "Invalid email or password."}, 401

        user_id = str(user["_id"])
        access_token = create_access_token(
            identity=user_id,
            additional_claims={
                "email": user["email"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
            },
        )

        return {
            "success": True,
            "message": "Login successful.",
            "token": access_token,
            "user": serialize_user(user),
        }, 200

