"""
VitalGuard — Configuration Manager
Loads environment variables for Twilio, patient, and emergency contact settings.
"""

import os


TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

EMERGENCY_CONTACT_PHONE = os.getenv("EMERGENCY_CONTACT_PHONE", "")
EMERGENCY_CONTACT_NAME = os.getenv("EMERGENCY_CONTACT_NAME", "Emergency Contact")

PATIENT_PHONE = os.getenv("PATIENT_PHONE", "")
PATIENT_NAME = os.getenv("PATIENT_NAME", "Patient")

TWILIO_ENABLED = os.getenv("TWILIO_ENABLED", "false").lower() == "true"


def is_twilio_configured() -> bool:
    """Check if all required Twilio credentials are set."""
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER)
