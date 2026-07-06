"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

SERVICE_COLOR_MAPPING = {
    "Deep Tissue": "3",
    "Swedish": "7",
    "Prenatal": "6",
    "Myofascial Release (MFR)": "10",
}

WAITLIST_EVENT_COLOR_ID = "5"

SHEET_INSERT_START_INDEX = 4
SHEET_INSERT_END_INDEX = 5
SHEET_START_ROW_REF = "5"

SOAP_FORM_BASE = (
    "https://docs.google.com/forms/d/1maaknBVFgUMKRQQ1Sc47wOhNc99j77icwZG-jDK_I90/viewform"
)

WAITLIST_SERVICE_LABELS = {
    "deep-tissue": "Deep Tissue",
    "swedish": "Swedish",
    "prenatal": "Prenatal",
    "mfr": "Myofascial Release (MFR)",
}


@dataclass
class BusinessConfig:
    """Per-tenant business configuration (SaaS-ready)."""

    tenant_id: str = "default"
    sender_email: str = ""
    calendar_ids: list[str] = field(default_factory=list)
    primary_calendar_id: str = "primary"
    spreadsheet_id: str = ""
    drive_folder_id: str = ""
    local_timezone: str = "America/New_York"
    square_app_id: str = ""
    square_location_id: str = ""
    square_environment: str = "sandbox"
    textbee_webhook_secret: str = ""
    cron_secret_key: str = ""
    sms_provider: str = "none"
    service_account_file: str = "key.json"


def _parse_calendar_ids(raw: str) -> list[str]:
    return [cid.strip() for cid in raw.split(",") if cid.strip()]


def load_business_config(tenant_id: str = "default") -> BusinessConfig:
    """Load business config for a tenant. Single-tenant for now."""
    calendar_ids = _parse_calendar_ids(os.getenv("CALENDAR_ID", "primary"))
    return BusinessConfig(
        tenant_id=tenant_id,
        sender_email=os.getenv("SENDER_EMAIL", "").strip(),
        calendar_ids=calendar_ids or ["primary"],
        primary_calendar_id=calendar_ids[0] if calendar_ids else "primary",
        spreadsheet_id=os.getenv("SPREADSHEET_ID", "").strip(),
        drive_folder_id=os.getenv("DRIVE_FOLDER_ID", "").strip(),
        local_timezone=os.getenv("LOCAL_TIMEZONE", "America/New_York").strip(),
        square_app_id=os.getenv("SQUARE_APPLICATION_ID", "").strip(),
        square_location_id=os.getenv("SQUARE_LOCATION_ID", "").strip(),
        square_environment=os.getenv("SQUARE_ENVIRONMENT", "sandbox").strip().lower(),
        textbee_webhook_secret=os.getenv("TEXTBEE_WEBHOOK_SECRET", "").strip(),
        cron_secret_key=os.getenv("CRON_SECRET_KEY", "").strip(),
        sms_provider=os.getenv("SMS_PROVIDER", "none").strip().lower(),
        service_account_file="key.json",
    )


def get_square_credentials() -> tuple[str, str, str]:
    """Return Square access token, location ID, and environment."""
    return (
        os.getenv("SQUARE_ACCESS_TOKEN", "").strip(),
        os.getenv("SQUARE_LOCATION_ID", "").strip(),
        os.getenv("SQUARE_ENVIRONMENT", "sandbox").strip().lower(),
    )
