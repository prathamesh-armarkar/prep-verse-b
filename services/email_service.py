from flask import current_app
from flask_mail import Message

from database.mail import mail


class EmailService:

    @staticmethod
    def send_otp(email, otp):

        print("Sending Email...")
        print(f"Recipient: {email}")
        print(f"OTP: {otp}")

        html = f"""
        <div style="margin:0;padding:0;background:#f4f7fb;font-family:Arial,sans-serif;">
            <div style="max-width:620px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,0.08);">
                <div style="background:linear-gradient(90deg,#2563eb,#3b82f6);padding:28px 32px;">
                    <h2 style="margin:0;color:#ffffff;font-size:24px;">PrepVerse AI</h2>
                    <p style="margin:8px 0 0;color:#dbeafe;font-size:14px;">Your learning journey starts here</p>
                </div>
                <div style="padding:32px;">
                    <p style="margin:0 0 12px;color:#0f172a;font-size:16px;">Hello,</p>
                    <p style="margin:0 0 16px;color:#334155;font-size:15px;">
                        Thank you for joining PrepVerse AI. To secure your account, please use the verification code below.
                    </p>
                    <div style="margin:24px 0;padding:18px 24px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;text-align:center;">
                        <p style="margin:0 0 8px;color:#475569;font-size:13px;text-transform:uppercase;letter-spacing:1.5px;">Your OTP</p>
                        <div style="font-size:36px;font-weight:700;letter-spacing:8px;color:#2563eb;">{otp}</div>
                    </div>
                    <p style="margin:0 0 10px;color:#334155;font-size:15px;">
                        This code is valid for <strong>5 minutes</strong>.
                    </p>
                    <p style="margin:0 0 20px;color:#64748b;font-size:13px;">
                        For your security, do not share this code with anyone.
                    </p>
                    <hr style="border:0;border-top:1px solid #e2e8f0;margin:24px 0;" />
                    <p style="margin:0;color:#94a3b8;font-size:12px;">
                        If you did not create this account, please ignore this email.
                    </p>
                </div>
                <div style="background:#f8fafc;padding:20px 32px;text-align:center;color:#64748b;font-size:12px;">
                    © 2026 PrepVerse AI. All rights reserved.
                </div>
            </div>
        </div>
        """

        message = Message(
            subject="PrepVerse AI - Email Verification OTP",
            recipients=[email],
            html=html,
            sender=current_app.config.get("MAIL_USERNAME")
        )

        try:
            mail.send(message)
            print("Email Sent Successfully")
            return True
        except Exception as exc:
            print("Email send failed")
            print(exc)
            raise exc