import random
from datetime import datetime, timedelta

from database.db import db
from models.otp import OTPVerification


class OTPService:

    @staticmethod
    def generate_otp():
        print("OTP Generated")
        return str(random.randint(100000, 999999))

    @staticmethod
    def save_otp(user_id, email, otp):
        print("Saving OTP...")

        # Remove any existing OTPs for this user first.
        OTPVerification.delete_for_user(user_id)

        otp_id = OTPVerification.create(user_id, email, otp)

        print("OTP Saved Successfully")
        return OTPVerification.find_latest_by_email(email)

