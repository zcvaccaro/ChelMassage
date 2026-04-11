# === Chel Massage Backend Plan ===
import base64
import datetime
from datetime import timezone, timedelta
import io
import os
import threading
from urllib.parse import urlencode
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, url_for
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# 1. Load environment variables from .env file immediately
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')

# --- Configuration ---
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]
SERVICE_ACCOUNT_FILE = 'key.json'
CALENDAR_ID = (os.getenv("CALENDAR_ID") or "primary").strip() or "primary"
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "").strip()
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "").strip()
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "America/New_York").strip()

# --- Google Calendar Event Color Mapping ---
# Map service names to Google Calendar's color IDs (1-11).
# See: https://developers.google.com/calendar/api/v3/reference/colors
SERVICE_COLOR_MAPPING = {
    "Deep Tissue": "3",               # Grape (Purple)
    "Swedish": "7",                   # Peacock (Blue)
    "Prenatal": "6",                  # Banana (Yellow)
    "Myofascial Release (MFR)": "10",  # Basil (Green)
}

# --- Email Configuration ---
# Ensure we pull the email from the environment (loaded via dotenv above)
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "").strip()

# --- Startup Checks ---
if not SENDER_EMAIL:
    print("!!! CRITICAL SYSTEM WARNING: SENDER_EMAIL is not found in .env or system environment. Emails will fail.")
else:
    print("--- STARTUP SYSTEM CHECK ---")
    print(f"  > Email Service:  '{SENDER_EMAIL}'")
    print(f"  > Calendar ID:    '{CALENDAR_ID}'")
    print(f"  > Spreadsheet ID: '{SPREADSHEET_ID if SPREADSHEET_ID else 'MISSING'}'")
    print(f"  > Drive Folder:   '{DRIVE_FOLDER_ID if DRIVE_FOLDER_ID else 'MISSING'}'")
    print(f"  > Timezone:       '{LOCAL_TIMEZONE}'")
    print("----------------------------")

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    print(f"SYSTEM WARNING: {SERVICE_ACCOUNT_FILE} not found. Calendar/Sheets integration will fail.")

def get_google_service(service_name, version):
    """Unified helper to get a Google API service using token.json (User) or key.json (Service Account)."""
    creds = None
    script_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(script_dir, 'token.json')

    # 1. Try OAuth2 User Token (token.json) - Preferred for User's Drive/Calendar/Gmail
    if os.path.exists(token_path):
        try:
            creds = UserCredentials.from_authorized_user_file(token_path, SCOPES)
            if creds and not creds.valid:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())
            if creds and creds.valid:
                print(f"DEBUG: Using OAuth User Token for {service_name}")
                return build(service_name, version, credentials=creds)
        except Exception as e:
            print(f"DEBUG: User OAuth failed for {service_name}: {e}")
            creds = None

    # 2. Fallback to Service Account (key.json)
    print(f"DEBUG: Falling back to Service Account for {service_name}")
    if not creds:
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            try:
                creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
                return build(service_name, version, credentials=creds)
            except Exception as e:
                print(f"ERROR: Service account failed for {service_name}: {e}")
        else:
            print(f"ERROR: No valid credentials for {service_name}")
    return None

def get_calendar_service():
    return get_google_service('calendar', 'v3')

def get_sheets_service():
    return get_google_service('sheets', 'v4')

def get_drive_service():
    return get_google_service('drive', 'v3')

def get_gmail_service():
    return get_google_service('gmail', 'v1')

def create_event(service, summary, start_time, end_time, description="", calendar_id='primary', color_id: Optional[str] = None):
    """Creates a new event on the specified calendar."""
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'UTC', # It's best practice to work in UTC
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'UTC',
        },
        'colorId': color_id,
    }

    try:
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"Event created: {created_event.get('htmlLink')}")
        return created_event
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

def send_email(receiver_email, subject, body_html, attachment_data=None, attachment_filename=None):
    """Sends an email using the Google Gmail API (Port 443)."""

    if not receiver_email:
        error_msg = "ERROR: send_email: Receiver email address is required but was empty."
        print(error_msg)
        return False, error_msg

    service = get_gmail_service()
    if not service:
        print("CRITICAL ERROR: Could not build Gmail service.")
        return False, "Could not build Gmail service."

    message = MIMEMultipart()
    message["Subject"] = subject
    message["From"] = SENDER_EMAIL
    message["To"] = receiver_email
    # Ensure replies go to the business email, even if sent by the service account
    message["Reply-To"] = SENDER_EMAIL

    message.attach(MIMEText(body_html, "html"))

    if attachment_data and attachment_filename:
        part = MIMEBase("application", "pdf")
        part.set_payload(attachment_data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename=\"{attachment_filename}\"")
        message.attach(part)

    # Encode the message for the Gmail API
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {'raw': raw_message}

    try:
        # Use SENDER_EMAIL as userId to ensure the Gmail API sends from the correct Workspace account
        sent_message = service.users().messages().send(userId=SENDER_EMAIL, body=body).execute()
        print(f"Email sent successfully! Message ID: {sent_message['id']}")
        return True, None
    except HttpError as error:
        error_msg = f'An error occurred sending email: {error}'
        print(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error sending email: {e}"
        print(error_msg)
        return False, error_msg


# --- Frontend Routes ---

@app.route('/')
def home():
    """Serves the main homepage."""
    return render_template('index.html')

@app.route('/Booking.html')
def booking_page():
    """Serves the booking page."""
    return render_template('Booking.html')

@app.route('/intake.html')
def intake_page():
    """Serves the client intake form page."""
    return render_template('intake.html')

@app.route('/BookingConfirm.html')
def booking_confirmation_page():
    """Serves the booking confirmation page."""
    return render_template('BookingConfirm.html')

@app.route('/OnSiteRequest.html')
def onsite_request_page():
    """Serves the on-site treatment request form."""
    return render_template('OnSiteRequest.html')

@app.route('/RequestConfirm.html')
def request_confirm_page():
    """Serves the on-site request confirmation page."""
    return render_template('RequestConfirm.html')

@app.route('/IntakeConfirm.html')
def intake_confirmation_page():
    """Serves the intake form confirmation page."""
    return render_template('IntakeConfirm.html')

def _get_available_dates_list(days_to_scan=90):
    """Internal helper to get a list of dates with "open for bookings" events."""
    start_date = datetime.datetime.now(timezone.utc)
    end_date = start_date + timedelta(days=days_to_scan)

    service = get_calendar_service()
    if not service:
        print("DEBUG: _get_available_dates_list: Could not get calendar service.")
        return []

    # Final safety check to prevent 404 // malformed URLs
    target_id = CALENDAR_ID if CALENDAR_ID and CALENDAR_ID.strip() else "primary"

    try:
        events_result = service.events().list(
            calendarId=target_id,
            timeMin=start_date.isoformat(),
            timeMax=end_date.isoformat(),
            singleEvents=True
        ).execute()
        all_events = events_result.get('items', [])

        if not all_events:
            print(f"DEBUG: _get_available_dates_list: No events found on calendar {target_id} for the next {days_to_scan} days.")

        available_dates = set()
        for event in all_events:
            # Added .strip() to handle accidental leading/trailing spaces in Calendar event titles
            if event.get('summary', '').strip().lower() == 'open for bookings':
                if 'dateTime' in event['start']:
                    available_dates.add(event['start']['dateTime'].split('T')[0])
                elif 'date' in event['start']:
                    available_dates.add(event['start']['date'])
        return sorted(list(available_dates))
    except Exception as e:
        print(f"ERROR: _get_available_dates_list: Failed to retrieve calendar events: {e}")
        return []


# --- API Endpoints ---

@app.route('/api/available-days', methods=['GET'])
def get_available_days():
    """Scans a date range and returns a list of dates ('YYYY-MM-DD')."""
    available_dates = _get_available_dates_list()
    return jsonify(available_dates)

@app.route('/api/availability', methods=['GET'])
def get_availability():
    """
    API endpoint to get available start times for a given date and service duration.
    Expects 'date' (YYYY-MM-DD) and 'duration' (in minutes) query parameters.
    """
    date_str = request.args.get('date')
    duration_str = request.args.get('duration')

    if not date_str or not duration_str:
        return jsonify({"error": "Both 'date' and 'duration' query parameters are required."}), 400

    # --- New Availability Logic ---
    try:
        service_duration = int(duration_str)
        total_block_duration = service_duration + 15 # Increased buffer from 10 to 15 minutes
        start_of_day = datetime.datetime.fromisoformat(date_str).replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)
    except (ValueError, TypeError):
        return jsonify({
            "error": "Invalid date or duration format. Date should be YYYY-MM-DD and duration should be an integer."
        }), 400

    service = get_calendar_service()
    if not service:
        return jsonify({"error": "Could not connect to Google Calendar service."}), 500

    target_id = CALENDAR_ID if CALENDAR_ID and CALENDAR_ID.strip() else "primary"

    try:
        events_result = service.events().list(
            calendarId=target_id,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        all_events = events_result.get('items', [])

        open_windows = []
        for event in all_events:
            if event.get('summary', '').strip().lower() == 'open for bookings' and 'dateTime' in event['start']:
                open_windows.append({
                    'start': datetime.datetime.fromisoformat(event['start']['dateTime']),
                    'end': datetime.datetime.fromisoformat(event['end']['dateTime'])
                })

        busy_slots = []
        for event in all_events:
            if event.get('summary', '').strip().lower() != 'open for bookings' and 'dateTime' in event['start']:
                busy_slots.append({
                    'start': datetime.datetime.fromisoformat(event['start']['dateTime']),
                    'end': datetime.datetime.fromisoformat(event['end']['dateTime'])
                })

        valid_start_times = []
        time_slot_interval = timedelta(minutes=15)
        now = datetime.datetime.now(timezone.utc)

        for window in open_windows:
            potential_start = window['start']
            while potential_start < window['end']:
                potential_end = potential_start + timedelta(minutes=total_block_duration)

                if potential_end > window['end']:
                    break

                # Skip times that have already passed if booking for today
                if potential_start <= now:
                    potential_start += time_slot_interval
                    continue

                is_valid = True
                for busy in busy_slots:
                    if potential_start < busy['end'] and potential_end > busy['start']:
                        is_valid = False
                        break

                if is_valid:
                    valid_start_times.append(potential_start.isoformat())

                potential_start += time_slot_interval

        return jsonify(valid_start_times)

    except Exception as e:
        return jsonify({"error": f"Failed to retrieve calendar events: {e}"}), 500


@app.route('/api/book', methods=['POST'])
def book_appointment():
    """
    API endpoint to create a new booking event.
    Expects a JSON payload with start_time, service_duration, summary, and description.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload."}), 400

    try:
        start_time = datetime.datetime.fromisoformat(data['start_time'])
        duration = int(data['service_duration'])
        buffer = 15 # Increased buffer from 10 to 15 minutes
        end_time = start_time + timedelta(minutes=duration + buffer)
        summary = data['summary']
        description = data.get('description', '')
        service_type = data.get('service_type') # New: Get service type from frontend
        client_info = data.get('client', {})
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": f"Invalid or missing data in request: {e}"}), 400

    service = get_calendar_service()
    if not service:
        return jsonify({"error": "Could not connect to Google Calendar service."}), 500

    # Determine event color based on service type
    event_color_id = SERVICE_COLOR_MAPPING.get(service_type)

    # --- Overlap Prevention Logic ---
    check_start = start_time - timedelta(hours=1)
    check_end = end_time + timedelta(hours=1)
    try:
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=check_start.isoformat(),
            timeMax=check_end.isoformat(),
            singleEvents=True
        ).execute()
        all_events = events_result.get('items', [])

        busy_slots = [
            event for event in all_events
            if event.get('summary', '').lower() != 'open for bookings' and 'dateTime' in event['start']
        ]

        for busy_event in busy_slots:
            busy_start = datetime.datetime.fromisoformat(busy_event['start']['dateTime'])
            busy_end = datetime.datetime.fromisoformat(busy_event['end']['dateTime'])
            if start_time < busy_end and end_time > busy_start:
                return jsonify({"error": "The selected time slot is no longer available. Please choose another time."}), 409

    except Exception as e:
        print(f"ERROR: /api/book: Failed during overlap check: {e}")
        return jsonify({"error": "Could not verify appointment availability. Please try again."}), 500

    full_description = description

    # Pass the determined color ID to the create_event function
    created_event = create_event(service, summary, start_time, end_time, full_description, CALENDAR_ID, color_id=event_color_id)

    if not created_event:
        return jsonify({"error": "Failed to create calendar event."}), 500

    calendar_event_id = created_event.get('id')

    # --- Generate Pre-filled SOAP Note URL ---
    local_tz = ZoneInfo(LOCAL_TIMEZONE)
    local_start_time = start_time.astimezone(local_tz)
    booking_date_formatted = local_start_time.strftime('%B %d, %Y')
    booking_time_formatted = local_start_time.strftime('%I:%M %p')

    soap_form_base = "https://docs.google.com/forms/d/1maaknBVFgUMKRQQ1Sc47wOhNc99j77icwZG-jDK_I90/viewform" # Ensure this is the correct form ID
    soap_query = {
        'entry.971462728': summary, # Use the full summary (Service for Client Name)
        'entry.353806943': f"{booking_date_formatted} {booking_time_formatted}",
        'entry.804944025': description.replace('Comments: ', ''),
        'entry.175378350': calendar_event_id
    }
    soap_url = f"{soap_form_base}?{urlencode(soap_query)}"

    # Update the Calendar Event description with the SOAP link
    try:
        updated_desc = f"{description}\n\n--- ADMIN: SOAP NOTE LINK ---\n{soap_url}"
        service.events().patch(calendarId=CALENDAR_ID, eventId=calendar_event_id, body={'description': updated_desc}).execute()
    except Exception as e:
        print(f"ERROR: Failed to update calendar event with SOAP link: {e}")

    # --- Prepare Data for Emails ---
    client_email = client_info.get('email')
    client_first_name = client_info.get('first_name', 'Valued Client')

    intake_params = {
        'firstName': client_info.get('first_name'),
        'lastName': client_info.get('last_name'),
        'date': booking_date_formatted, # Add booking date
        'time': booking_time_formatted, # Add booking time
        'email': client_email,
        'phone': client_info.get('phone'),
        'comments': data.get('description', '').replace('Comments: ', ''),
        'calendarId': calendar_event_id
    }
    intake_url = url_for('intake_page', _external=True) + '?' + urlencode(intake_params)

    # --- Define Async Email Task ---
    def _handle_booking_background():
        # 1. Update "Clients" Sheet immediately upon booking
        try:
            sheets_service = get_sheets_service()
            if sheets_service and client_email:
                # Normalize for comparison
                normalized_email = client_email.strip().lower()

                # Check for existing client
                result = sheets_service.spreadsheets().values().get(
                    spreadsheetId=SPREADSHEET_ID,
                    range='Clients!C:C'
                ).execute()

                existing_emails = [
                    item.strip().lower() for sublist in result.get('values', [])
                    for item in sublist if item and isinstance(item, str)
                ]

                if normalized_email not in existing_emails:
                    print(f"BACKGROUND_TASK: New client booking: {client_email}. Adding to 'Clients' sheet.")
                    # Fetch sheet ID for prepend
                    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
                    client_sheet_metadata = next(s for s in spreadsheet.get('sheets', []) if s['properties']['title'] == 'Clients')
                    client_sheet_id = client_sheet_metadata['properties']['sheetId']

                    client_row = [
                        client_info.get('first_name', ''),
                        client_info.get('last_name', ''),
                        client_email,
                        client_info.get('phone', ''),
                        '',  # DOB (Collected at intake)
                        ''   # Address (Collected at intake)
                    ]

                    # Always insert a new row at Row 2 (index 1) to push existing data down
                    request_body = {
                        "requests": [{
                            "insertDimension": {
                                "range": {"sheetId": client_sheet_id, "dimension": "ROWS", "startIndex": 1, "endIndex": 2},
                                "inheritFromBefore": False
                            }
                        }]
                    }
                    sheets_service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=request_body).execute()

                    sheets_service.spreadsheets().values().update(
                        spreadsheetId=SPREADSHEET_ID,
                        range='Clients!A2',
                        valueInputOption='USER_ENTERED',
                        body={'values': [client_row]}
                    ).execute()
                else:
                    print(f"BACKGROUND_TASK: Existing client {client_email} booked. Skipping 'Clients' sheet update.")
        except Exception as sheet_e:
            print(f"ERROR (background): Failed to update Clients sheet during booking: {sheet_e}")

        # 2. Send Emails
        print(f"BACKGROUND_TASK: Starting email delivery for: {client_email}")
        if client_email:
            email_subject = "Your Massage Appointment is Confirmed!"
            # (Existing email body logic stays exactly as is)
            email_body_html = f"""
            <html>
            <head>
                <style>
                    .email-cta:hover {{
                        background-color: #ffffff !important;
                        color: #000000 !important;
                    }}
                </style>
            </head>
            <body>
            <p>Hi {client_first_name},</p>
            <p>Thank you for booking your appointment! We look forward to seeing you on <strong>{booking_date_formatted}</strong> at <strong>{booking_time_formatted}</strong>.</p>
            <p>As a next step, if you have not already, please complete our secure client intake form by clicking the link below:</p>
            <p><a href="{intake_url}" class="email-cta" style="display: inline-block; padding: 12px 24px; border: 1px solid #000; background-color: #000; color: #fff; font-size: 1rem; font-weight: bold; text-decoration: none; border-radius: 50px; transition: background-color 0.3s ease, color 0.3s ease;">Complete Intake Form</a></p>
            <p>High Five!<br>Chelsea Vaccaro <br> Therapeutic Massage</p>
            </body>
            </html>
            """
            client_email_sent, _ = send_email(client_email, email_subject, email_body_html)
            if client_email_sent:
                print("BACKGROUND_TASK: Successfully sent confirmation email to client.")
            else:
                print("BACKGROUND_TASK: WARNING: Failed to send confirmation email to client.")

        print("BACKGROUND_TASK: Starting to send admin notification email.")
        try:
            admin_email = SENDER_EMAIL
            admin_subject = f"New Booking: {summary}"
            admin_body_html = f"""
            <p><strong>You have a new booking!</strong></p>
            <p><strong>Client:</strong> {client_info.get('first_name')} {client_info.get('last_name')}</p>
            <p><strong>Service:</strong> {summary}</p>
            <p><strong>When:</strong> {local_start_time.strftime('%A, %B %d, %Y at %I:%M %p')}</p>
            <p><strong>Client Email:</strong> {client_info.get('email')}</p>
            <p><strong>Client Phone:</strong> {client_info.get('phone')}</p>
            <p><strong>Comments:</strong> {data.get('description', '').replace('Comments: ', '')}</p>
            <p>The event has been added to your Google Calendar.</p>
            """
            admin_email_sent, _ = send_email(admin_email, admin_subject, admin_body_html)
            if admin_email_sent:
                print("BACKGROUND_TASK: Successfully sent notification email to admin.")
            else:
                print("BACKGROUND_TASK: WARNING: Failed to send notification email to admin.")
        except Exception as e:
            print(f"CRITICAL: Failed to send admin notification email for booking. Error: {e}")

    # --- Start Background Thread ---
    threading.Thread(target=_handle_booking_background).start()

    return jsonify({
        "message": "Booking successful!",
        "event_link": created_event.get('htmlLink'),
        "calendar_event_id": calendar_event_id
    })

def _handle_intake_submission_background(data, pdf_output):
    """Handles slow tasks (Sheets, Email) for intake form in the background."""
    client_name = f"{data.get('firstName', 'N/A')} {data.get('lastName', 'N/A')}"
    drive_link = "Link failed to generate"

    # --- 1. Construct Filename ---
    booking_date_raw = data.get('bookingDate')
    booking_time_raw = data.get('bookingTime')
    client_first_name = data.get('firstName', 'N/A')
    client_last_name = data.get('lastName', 'N/A')

    filename_date = 'UnknownDate'
    filename_time = 'UnknownTime'

    if booking_date_raw and booking_time_raw:
        try:
            parsed_date_time = datetime.datetime.strptime(f"{booking_date_raw} {booking_time_raw}", '%B %d, %Y %I:%M %p')
            filename_date = parsed_date_time.strftime('%m-%d-%Y')
            filename_time = parsed_date_time.strftime('%I%M%p')
        except ValueError:
            # Fallback if parsing fails, but data is present
            filename_date = booking_date_raw.replace(' ', '-').replace(',', '')
            filename_time = booking_time_raw.replace(':', '').replace(' ', '')
    else:
        # If date/time are missing, use current timestamp for uniqueness
        now_utc = datetime.datetime.now(timezone.utc)
        filename_date = now_utc.strftime('%m-%d-%Y')
        filename_time = now_utc.strftime('%H%M%S')

    attachment_filename = f"{filename_date}_{filename_time}_{client_first_name}_{client_last_name}.pdf"

    # --- 2. Upload PDF to Google Drive ---
    try:
        drive_service = get_drive_service()
        if drive_service:
            parent_id = None

            # 1. Try to use a hardcoded Folder ID first (Most reliable)
            if DRIVE_FOLDER_ID:
                parent_id = DRIVE_FOLDER_ID
            else:
                # 2. Fallback to searching by name with broader permissions
                query = "name = 'Client Intake Forms' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                response = drive_service.files().list(
                    q=query,
                    spaces='drive',
                    fields='files(id)',
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True
                ).execute()
                folders = response.get('files', [])

                if folders:
                    parent_id = folders[0]['id']
                else:
                    print("BACKGROUND_TASK: Folder 'Client Intake Forms' not found via search. Uploading to root.")

            file_metadata = {'name': attachment_filename}
            if parent_id:
                file_metadata['parents'] = [parent_id]

            media = MediaIoBaseUpload(io.BytesIO(pdf_output), mimetype='application/pdf')
            uploaded_file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True, # Required for Workspace Shared Drives
                fields='id, webViewLink'
            ).execute()

            drive_link = uploaded_file.get('webViewLink')
            print(f"BACKGROUND_TASK: PDF uploaded to Drive successfully: {drive_link}")
    except Exception as drive_e:
        print(f"ERROR (background): Failed to upload PDF to Drive: {drive_e}")

    # --- 3. Update Google Sheets (including the Drive Link) ---
    try:
        sheets_service = get_sheets_service()
        if sheets_service:
            # Fetch spreadsheet metadata to get sheet IDs for the prepend operation
            spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
            intake_sheet_metadata = next(s for s in spreadsheet.get('sheets', []) if s['properties']['title'] == 'Intake Forms')
            intake_sheet_id = intake_sheet_metadata['properties']['sheetId']

            intake_row = [
                datetime.datetime.now(ZoneInfo(LOCAL_TIMEZONE)).strftime('%Y-%m-%d %I:%M:%S %p'),
                f"{data.get('serviceType', 'N/A')} on {data.get('bookingDate', 'N/A')} at {data.get('bookingTime', 'N/A')}", # Column B
                client_name,        # Column C
                data.get('reason', ''),
                data.get('conditions', ''),
                data.get('allergies', ''),
                drive_link,         # Column G: PDF Drive Link
                '',                 # Column H: SOAP Notes (Placeholder)
                data.get('calendarId', '') # Column I: Calendar ID
            ]

            if intake_sheet_id is not None:
                # Always insert a new row at Row 2 (index 1) to push existing data down
                request_body = {
                    "requests": [{
                        "insertDimension": {
                            "range": {"sheetId": intake_sheet_id, "dimension": "ROWS", "startIndex": 1, "endIndex": 2},
                            "inheritFromBefore": False
                        }
                    }]
                }
                sheets_service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=request_body).execute()

                # Write the new intake data into the now-empty Row 2
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range='Intake Forms!A2',
                    valueInputOption='USER_ENTERED',
                    body={'values': [intake_row]}
                ).execute()
            print("BACKGROUND_TASK: Successfully updated Google Sheets.")
    except Exception as sheets_e:
        print(f"ERROR (background): Failed to update Google Sheets: {sheets_e}")

    # --- 3.5 Update "Clients" tab with DOB and Address ---
    try:
        client_email = data.get('email')
        if sheets_service and client_email:
            normalized_email = client_email.strip().lower()
            # Fetch all emails from the Clients sheet (Column C)
            client_data_result = sheets_service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range='Clients!C:C'
            ).execute()
            client_rows = client_data_result.get('values', [])

            # Find the row index where the email matches
            target_row_index = -1
            for idx, row_val in enumerate(client_rows):
                if row_val and row_val[0].strip().lower() == normalized_email:
                    target_row_index = idx + 1 # Sheets is 1-indexed
                    break

            if target_row_index != -1:
                # Update DOB (Col E) and Address (Col F) for that specific row
                update_range = f'Clients!E{target_row_index}:F{target_row_index}'
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=update_range,
                    valueInputOption='USER_ENTERED',
                    body={'values': [[data.get('dob', ''), data.get('address', '')]]}
                ).execute()
                print(f"BACKGROUND_TASK: Enriched client profile (DOB/Address) for {client_email}")
    except Exception as e:
        print(f"ERROR (background): Failed to enrichment client data in Clients sheet: {e}")

    # --- 4. Send Email to Admin ---
    try:
        admin_email = SENDER_EMAIL
        email_subject = f"New Intake Form Submitted by {client_name}"
        email_body_html = f"""
        <p>A new client intake form has been submitted.</p>
        <p><strong>Client:</strong> {client_name}</p>
        <p><strong>Email:</strong> {data.get('email', 'N/A')}</p>
        <p><strong>Original Booking:</strong> {data.get('bookingDate', 'N/A')} at {data.get('bookingTime', 'N/A')}</p>
        <p><strong>Google Drive Backup:</strong> <a href="{drive_link}">View PDF in Drive</a></p>
        """

        email_sent, _ = send_email(
            receiver_email=admin_email,
            subject=email_subject,
            body_html=email_body_html
        )
        if email_sent:
            print("BACKGROUND_TASK: Successfully sent intake form email to admin.")
        else:
            raise Exception("send_email returned False for intake form.")
    except Exception as e:
        print(f"ERROR (background): Failed to send intake form email: {e}")

@app.route('/api/submit-intake', methods=['POST'])
def submit_intake():
    """
    API endpoint to receive intake form data, generate a PDF,
    and email it to the admin.
    """

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload."}), 400

    try:
        client_name = f"{data.get('firstName', 'N/A')} {data.get('lastName', 'N/A')}"

        # --- 1. Generate PDF ---
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)

        # --- PDF Helper Functions ---
        def write_line(label: str, value: str, is_multiline: bool = False) -> None:
            if not value:
                return
            pdf.set_font("Helvetica", "B", size=12)
            pdf.cell(40, 7, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_font("Helvetica", "", size=12)
            if is_multiline:
                pdf.multi_cell(0, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.cell(0, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        def write_section_header(title):
            pdf.ln(5)
            pdf.set_font("Helvetica", "B", size=14)
            pdf.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
            pdf.ln(2)

        pdf.set_font("Helvetica", "B", size=18)
        pdf.cell(0, 8, f"Client Intake Form: {client_name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(5)

        # --- Personal Information ---
        write_section_header("Personal Information")
        write_line("Name:", client_name)
        write_line("DOB:", data.get('dob', 'N/A'))

        # --- Booking & Visit Information ---
        write_section_header("Visit Information")
        write_line("Booking:", f"{data.get('bookingDate', 'N/A')} at {data.get('bookingTime', 'N/A')}")
        write_line("Email:", data.get('email', 'N/A'))
        write_line("Phone:", data.get('phone', 'N/A'))
        write_line("Reason for Visit:", data.get('reason', 'No comments provided.'), is_multiline=True)

        # --- Medical History ---
        write_section_header("Medical History")
        conditions = data.get('conditions')
        if isinstance(conditions, list):
            conditions = ', '.join(conditions)
        write_line("Conditions:", conditions)
        write_line("Allergies:", data.get('allergies', 'N/A'), is_multiline=True)
        pdf.ln(5)

        # --- Embed Body Chart Images Side-by-Side and Scaled ---
        front_image_data = data.get('drawingFront')
        back_image_data = data.get('drawingBack')

        if front_image_data or back_image_data:
            pdf.set_font("Helvetica", "B", size=14)
            pdf.cell(0, 10, "Problem Areas", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)

            page_width = pdf.w - 2 * pdf.l_margin
            image_width = page_width / 2 - 5

            max_image_height_on_page = pdf.h - pdf.get_y() - pdf.b_margin - 15

            current_y_for_images = pdf.get_y()
            max_drawn_height = 0

            def embed_image(b64_string, x_pos):
                nonlocal max_drawn_height
                if not b64_string or 'base64,' not in b64_string:
                    return
                try:
                    image_data = base64.b64decode(b64_string.split('base64,')[1])
                    img = Image.open(io.BytesIO(image_data))
                    original_width, original_height = img.size

                    width_ratio = image_width / original_width
                    height_ratio = max_image_height_on_page / original_height
                    scale_ratio = min(width_ratio, height_ratio)

                    final_width = original_width * scale_ratio
                    final_height = original_height * scale_ratio

                    if final_height <= 0:
                        raise ValueError("Calculated image height is zero or negative.")

                    with io.BytesIO() as output_stream:
                        img.save(output_stream, format="PNG")
                        output_stream.seek(0)
                        pdf.image(output_stream, x=x_pos, y=current_y_for_images, w=final_width, h=final_height)

                    max_drawn_height = max(max_drawn_height, final_height)

                except Exception as img_e:
                    print(f"ERROR: Could not process an image: {img_e}")
                    pdf.set_xy(x_pos, current_y_for_images)
                    pdf.set_font("Helvetica", "", size=8)
                    pdf.multi_cell(image_width, 10, "[Image could not be rendered]", border=1, align='C')
                    max_drawn_height = max(max_drawn_height, 10)

            embed_image(front_image_data, pdf.l_margin)
            embed_image(back_image_data, pdf.l_margin + image_width + 10)

            pdf.set_y(current_y_for_images + max_drawn_height + 10)

        # Get PDF data as bytes
        pdf_output: bytes = bytes(pdf.output())

        # --- Start Background Tasks ---
        threading.Thread(
            target=_handle_intake_submission_background,
            kwargs={'data': data, 'pdf_output': pdf_output},
        ).start()

        return jsonify({"message": "Intake form submitted successfully."}), 200

    except Exception as e:
        print(f"ERROR: /api/submit-intake: {e}")
        return jsonify({"error": "Server error while processing the form."}), 500

@app.route('/api/request-onsite', methods=['POST'])
def request_onsite():
    """
    API endpoint to handle on-site treatment requests.
    Sends emails to admin and client in the background.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload."}), 400

    # Start the background task to send emails
    threading.Thread(target=_handle_onsite_request_background, args=(data,)).start()

    return jsonify({"message": "On-site request submitted successfully."}), 200

def _handle_onsite_request_background(data):
    """Background task to send notification emails for on-site requests."""
    first_name = data.get('firstName', 'Valued Client')
    last_name = data.get('lastName', '')
    full_name = f"{first_name} {last_name}".strip()
    client_email = data.get('email')

    num_clients = int(data.get('numberOfClients', 1))
    # 1. Notify Admin
    try:
        admin_email = SENDER_EMAIL
        admin_subject = f"New On-Site Request: {full_name}"

        # Build requested times summary
        times = []
        for i in range(1, 4):
            d = data.get(f'date{i}')
            t = data.get(f'time{i}')
            if d and t:
                times.append(f"<li>{d} at {t}</li>")
        times_html = f"<ul>{''.join(times)}</ul>" if times else "<p>No specific times provided.</p>"

        client_services_html = ""
        client_services_list = [] # This will store strings like "Client Name (Service)"
        for i in range(1, num_clients + 1):
            client_name_i = data.get(f'clientName_{i}', f'Client {i}')
            treatment_type_i = data.get(f'treatmentType_{i}', 'Not specified')
            client_services_html += f"<li><strong>{client_name_i}:</strong> {treatment_type_i}</li>"
            client_services_list.append(f"{client_name_i} ({treatment_type_i})")

        admin_body_html = f"""
        <h3>New On-Site Treatment Request</h3>
        <p><strong>Client:</strong> {full_name}</p>
        <p><strong>Number of Clients:</strong> {num_clients}</p>
        <p><strong>Services Requested:</strong><ul>{client_services_html}</ul></p>
        <p><strong>Email:</strong> {client_email}</p>
        <p><strong>Phone:</strong> {data.get('phone')}</p>
        <p><strong>Address:</strong> {data.get('address')}</p>
        <p><strong>Requested Times:</strong></p>
        {times_html}
        <p><strong>Preferred Contact:</strong> {data.get('contactMethod')}</p>
        <p><strong>Additional Details:</strong> {data.get('details') or 'None'}</p>
        """
        send_email(admin_email, admin_subject, admin_body_html)
        print(f"BACKGROUND_TASK: Admin notified of on-site request from {full_name}")
    except Exception as e:
        print(f"ERROR: Failed to send admin on-site request notification: {e}")

    # 2. Confirm to Client
    if client_email:
        try:
            client_subject = "Your On-Site Treatment Request - Chelsea Vaccaro"

            # Construct a human-friendly list of dates
            date_list = []
            for i in range(1, 4):
                d = data.get(f'date{i}')
                t = data.get(f'time{i}')
                if d and t:
                    date_list.append(f"{d} at {t}")

            times_sentence = " or ".join([", ".join(date_list[:-1]), date_list[-1]]) if len(date_list) > 1 else (date_list[0] if date_list else "your requested times")

            all_client_services_summary = ", ".join(client_services_list)

            client_body_html = f"""
            <p>Hi {first_name},</p>
            <p>Thank you for requesting an on-site treatment with Chelsea Vaccaro Therapeutic Massage!</p>
            <p>We have received your request for <strong>{all_client_services_summary}</strong> at <strong>{data.get('address')}</strong> on <strong>{times_sentence}</strong>.</p>
            <p>We will check our schedules and reach out to you via <strong>{data.get('contactMethod').lower()}</strong> as soon as possible with options and pricing to finalize your appointment.</p>
            <p>We look forward to helping you heal and refresh in the comfort of your home!</p>
            <p>High Five!<br>Chelsea Vaccaro <br> Therapeutic Massage</p>
            """
            send_email(client_email, client_subject, client_body_html)
            print(f"BACKGROUND_TASK: Confirmation email sent to client {client_email}")
        except Exception as e:
            print(f"ERROR: Failed to send client on-site request confirmation: {e}")

    # 3. Update Google Sheets
    try:
        sheets_service = get_sheets_service()
        if sheets_service:
            spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
            # Note: I used "On-Site Requests" here; please ensure the tab name matches exactly.
            target_tab = "On-Site Requests"

            # Construct the Dates @ Times summary string
            date_time_entries = []
            for i in range(1, 4):
                d = data.get(f'date{i}')
                t = data.get(f'time{i}')
                if d and t:
                    date_time_entries.append(f"{d} at {t}")
            date_time_summary = " | ".join(date_time_entries)
            
            all_client_services_summary = " | ".join(client_services_list)

            row_data = [
                full_name,
                client_email,
                data.get('phone', ''),
                data.get('address', ''),
                all_client_services_summary, # Column E: Treatments
                num_clients,                 # Column F: Number of clients
                date_time_summary,
                data.get('details', '')
            ]

            sheet_metadata = next((s for s in spreadsheet.get('sheets', []) if s['properties']['title'] == target_tab), None)
            if sheet_metadata:
                sheet_id = sheet_metadata['properties']['sheetId']
                # Always insert a new row at Row 2 (index 1) to push existing data down
                request_body = {
                    "requests": [{
                        "insertDimension": {
                            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 1, "endIndex": 2},
                            "inheritFromBefore": False
                        }
                    }]
                }
                sheets_service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=request_body).execute()

                # Write the new request data into Row 2
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"'{target_tab}'!A2",
                    valueInputOption='USER_ENTERED',
                    body={'values': [row_data]}
                ).execute()
                print(f"BACKGROUND_TASK: Logged on-site request for {full_name} to Google Sheets.")
            else:
                print(f"BACKGROUND_TASK WARNING: Tab '{target_tab}' not found in the spreadsheet.")
    except Exception as e:
        print(f"ERROR: Failed to update Google Sheets for on-site request: {e}")

# --- Main Execution ---
if __name__ == '__main__':
    # For deployment, Render sets the PORT environment variable.
    # We default to 5000 for local development.
    port = int(os.environ.get('PORT', '5000'))
    # Bind to '0.0.0.0' to be accessible in a containerized environment.
    app.run(host='0.0.0.0', port=port, debug=False)