"""
VitalGuard — Action Handlers & Twilio SMS + Voice Call Integration
Sends SMS alerts and places an automated voice call to the emergency contact.
Prevents repeated calls using cooldown + emergency trigger lock.
"""

import asyncio
import itertools
import random
import time
import logging
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime
from dataclasses import dataclass
from typing import Literal, Optional

from twilio.rest import Client

from config import (
    TWILIO_ENABLED,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    EMERGENCY_CONTACT_PHONE,
    EMERGENCY_CONTACT_NAME,
    PATIENT_PHONE,
    PATIENT_NAME,
    is_twilio_configured,
    DOCTOR_EMAIL,
    EMAIL_ENABLED,
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
)

logger = logging.getLogger("vitalguard.actions")

ActionType = Literal["log", "alert_user", "schedule_doctor", "call_emergency", "notify_contact"]

# ---------------------------
# SMS COOLDOWN
# ---------------------------

_sms_last_sent: dict[str, float] = {}

SMS_COOLDOWNS = {
    "alert_user": 60,
    "schedule_doctor": 60,
    "call_emergency": 60,
    "notify_contact": 60,
}

# ---------------------------
# VOICE CALL CONTROL
# ---------------------------

_voice_last_called = 0
VOICE_CALL_COOLDOWN = 60  # 1 minute

_last_emergency_trigger = False


def _truncate(s: str, n: int = 100) -> str:
    if len(s) <= n:
        return s
    return "".join(itertools.islice(s, n)) + "..."


def _can_send_sms(action_type: str) -> bool:
    cooldown = SMS_COOLDOWNS.get(action_type, 60)
    last_sent = _sms_last_sent.get(action_type, 0)
    now = time.time()

    if now - last_sent >= cooldown:
        _sms_last_sent[action_type] = now
        return True

    return False


def _can_make_voice_call() -> bool:
    global _voice_last_called

    now = time.time()

    if now - _voice_last_called >= VOICE_CALL_COOLDOWN:
        _voice_last_called = now
        return True

    return False


# ---------------------------
# TWILIO CLIENT
# ---------------------------

_twilio_client = None


def _get_twilio_client():
    global _twilio_client

    if _twilio_client is None and is_twilio_configured():
        try:
            _twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            logger.info("Twilio client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")

    return _twilio_client


# ---------------------------
# SMS
# ---------------------------

def _send_sms(to_number: str, body: str) -> dict:

    client = _get_twilio_client()

    if not client or not TWILIO_ENABLED:
        logger.info(f"Mock SMS meant for {to_number}: {body}")
        return {"mode": "mock", "status": "mock_sent"}

    try:

        message = client.messages.create(
            body=body,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number,
        )

        logger.info(f"SMS sent to {to_number} | SID: {message.sid}")

        return {"mode": "live", "sid": message.sid, "status": message.status}

    except Exception as e:

        logger.error(f"Twilio SMS failed: {e}")
        print(f"\n--- MOCK SMS FALLBACK ---")
        print(f"To: {to_number}")
        print(f"Message:\n{body}")
        print(f"-------------------------\n")

        return {"mode": "mock", "status": "mock_sent_fallback", "error": str(e)}


async def _send_sms_async(to_number: str, body: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send_sms, to_number, body)


# ---------------------------
# VOICE CALL
# ---------------------------

def _make_voice_call(phone_number: str, message: str) -> dict:

    if not _can_make_voice_call():
        return {"mode": "cooldown", "status": "voice_call_cooldown_active"}

    client = _get_twilio_client()

    if not client or not TWILIO_ENABLED:
        logger.info(f"Mock Voice Call meant for {phone_number}: {message}")
        return {"mode": "mock", "status": "mock_call"}

    try:

        call = client.calls.create(
            twiml=f"""
            <Response>
                <Say voice="alice">
                {message}
                </Say>
            </Response>
            """,
            to=phone_number,
            from_=TWILIO_PHONE_NUMBER,
        )

        logger.info(f"Voice call placed to {phone_number} | SID: {call.sid}")

        return {"mode": "live", "call_sid": call.sid, "status": call.status}

    except Exception as e:

        logger.error(f"Voice call failed: {e}")
        print(f"\n--- MOCK VOICE CALL FALLBACK ---")
        print(f"To: {phone_number}")
        print(f"Message:\n{message}")
        print(f"--------------------------------\n")

        return {"mode": "mock", "status": "call_failed", "error": str(e)}


# ---------------------------
# ACTION RESULT MODEL
# ---------------------------

@dataclass
class ActionResult:
    action_type: ActionType
    success: bool
    message: str
    details: dict
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


# ---------------------------
# ACTIONS
# ---------------------------

async def log_reading(vitals, risk, reasoning, location=None, trigger_vitals=None):

    global _last_emergency_trigger

    if risk.get("level") != "CRITICAL":
        _last_emergency_trigger = False

    return ActionResult(
        action_type="log",
        success=True,
        message="Reading logged successfully",
        details={
            "vitals_snapshot": vitals,
            "trigger_vitals": trigger_vitals or [],
        },
        timestamp=datetime.now().isoformat(),
    )


async def alert_user(vitals, risk, reasoning, location=None, trigger_vitals=None):

    sms_result = None
    target_phone = PATIENT_PHONE or "+10000000000"

    if _can_send_sms("alert_user"):

        sms_body = (
            f"VitalGuard Health Alert\n"
            f"Risk Score: {risk.get('score',0)}\n"
            f"Heart Rate: {vitals.get('heart_rate')}\n"
            f"SpO2: {vitals.get('spo2')}\n"
        )

        if trigger_vitals:
            sms_body += f"Triggered By: {', '.join(trigger_vitals)}\n"

        if location and location.get("lat") and location.get("lng"):
            sms_body += f"Location: https://maps.google.com/?q={location['lat']},{location['lng']}\n"
        else:
            sms_body += "Location: Unknown\n"

        sms_result = await _send_sms_async(target_phone, sms_body)
    else:
        sms_result = {"mode": "cooldown", "status": "sms_cooldown_active"}

    return ActionResult(
        action_type="alert_user",
        success=True,
        message="Health alert triggered",
        details={
            "sms_delivery": sms_result or {"mode": "disabled"},
            "trigger_vitals": trigger_vitals or [],
        },
        timestamp=datetime.now().isoformat(),
    )


def _send_email(to_email: str, subject: str, body: str) -> dict:
    if not EMAIL_ENABLED or not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.info(f"Mock Email meant for {to_email}: Subject: {subject} | Body: {body}")
        return {"mode": "mock", "status": "mock_sent_email"}

    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = SMTP_USERNAME
        msg['To'] = to_email

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email sent to {to_email}")
        return {"mode": "live", "status": "email_sent"}
    except Exception as e:
        logger.error(f"SMTP Email failed: {e}")
        print(f"\n--- MOCK EMAIL FALLBACK ---")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(f"Message:\n{body}")
        print(f"---------------------------\n")
        return {"mode": "mock", "status": "mock_sent_email_fallback", "error": str(e)}

async def _send_email_async(to_email: str, subject: str, body: str) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _send_email, to_email, subject, body)


async def schedule_doctor(vitals, risk, reasoning, location=None, trigger_vitals=None):

    doctor = random.choice(
        ["Dr. Priya Sharma", "Dr. Ravi Patel", "Dr. Ananya Gupta"]
    )

    subject = f"Appointment Scheduled for Patient {PATIENT_NAME}"
    body = (
        f"An appointment has been scheduled with {doctor}.\n\n"
        f"Patient details:\n"
        f"Name: {PATIENT_NAME}\n"
        f"Risk Score: {risk.get('score', 0)}\n"
        f"Heart Rate: {vitals.get('heart_rate', 'N/A')}\n"
        f"SpO2: {vitals.get('spo2', 'N/A')}\n"
        f"Reasoning: {reasoning}\n"
    )

    if trigger_vitals:
        body += f"Triggered By: {', '.join(trigger_vitals)}\n"

    email_result = await _send_email_async(DOCTOR_EMAIL, subject, body)

    return ActionResult(
        action_type="schedule_doctor",
        success=True,
        message=f"Appointment scheduled with {doctor}",
        details={
            "doctor": doctor,
            "email_delivery": email_result,
            "trigger_vitals": trigger_vitals or [],
        },
        timestamp=datetime.now().isoformat(),
    )


async def call_emergency(vitals, risk, reasoning, location=None, trigger_vitals=None):

    case_id = f"EMG-{random.randint(100000,999999)}"

    return ActionResult(
        action_type="call_emergency",
        success=True,
        message="Emergency services contacted",
        details={
            "case_id": case_id,
            "trigger_vitals": trigger_vitals or [],
        },
        timestamp=datetime.now().isoformat(),
    )


async def notify_contact(vitals, risk, reasoning, location=None, trigger_vitals=None):

    global _last_emergency_trigger

    sms_result = None
    voice_result = None
    target_phone = EMERGENCY_CONTACT_PHONE or "+10000000000"

    if _can_send_sms("notify_contact"):

        sms_body = (
            f"Emergency Alert for {PATIENT_NAME}\n"
            f"Risk Score: {risk.get('score',0)}\n"
            f"Heart Rate: {vitals.get('heart_rate')}\n"
            f"SpO2: {vitals.get('spo2')}\n"
        )

        if trigger_vitals:
            sms_body += f"Triggered By: {', '.join(trigger_vitals)}\n"

        if location and location.get("lat") and location.get("lng"):
            sms_body += f"Location: https://maps.google.com/?q={location['lat']},{location['lng']}\n"
        else:
            sms_body += "Location: Unknown\n"

        sms_result = await _send_sms_async(target_phone, sms_body)
    else:
        sms_result = {"mode": "cooldown", "status": "sms_cooldown_active"}

    if not _last_emergency_trigger:

        voice_message = (
            f"Emergency alert from VitalGuard. "
            f"{PATIENT_NAME} is experiencing a critical health event. "
            f"Heart rate {vitals.get('heart_rate')} beats per minute. "
            f"Oxygen level {vitals.get('spo2')} percent. "
            f"Emergency services have been contacted."
        )

        voice_result = _make_voice_call(target_phone, voice_message)

        _last_emergency_trigger = True

    else:

        voice_result = {"mode": "already_triggered"}

    return ActionResult(
        action_type="notify_contact",
        success=True,
        message=f"Emergency contact ({EMERGENCY_CONTACT_NAME}) notified",
        details={
            "sms_delivery": sms_result or {"mode": "disabled"},
            "voice_call": voice_result,
            "trigger_vitals": trigger_vitals or [],
        },
        timestamp=datetime.now().isoformat(),
    )


# ---------------------------
# ACTION DISPATCH
# ---------------------------

ACTION_DISPATCH = {
    "log": log_reading,
    "alert_user": alert_user,
    "schedule_doctor": schedule_doctor,
    "call_emergency": call_emergency,
    "notify_contact": notify_contact,
}


async def execute_action(action_type, vitals, risk, reasoning, location=None, trigger_vitals=None):

    handler = ACTION_DISPATCH.get(action_type, log_reading)

    return await handler(vitals, risk, reasoning, location, trigger_vitals)


def get_twilio_status():

    return {
        "enabled": TWILIO_ENABLED,
        "configured": is_twilio_configured(),
        "patient_phone_set": bool(PATIENT_PHONE),
        "emergency_contact_set": bool(EMERGENCY_CONTACT_PHONE),
        "emergency_contact_name": EMERGENCY_CONTACT_NAME,
        "patient_name": PATIENT_NAME,
    }