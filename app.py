
# === Chel Massage Backend Plan ===
# This backend will be built using Python (likely with Flask or FastAPI)
# and will use a Google Service Account for authentication.
import base64
import datetime
import os
import threading
from urllib.parse import urlencode
import smtplib
import ssl
from fpdf.enums import XPos, YPos
from flask import Flask, request, jsonify, render_template, url_for
from zoneinfo import ZoneInfo
from google.auth.transport.requests import Request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from datetime import timezone, timedelta

# --- Core Dependencies ---
# - google-auth-httplib2
# - google-auth-oauthlib
# - A web framework (e.g., flask)
# - A PDF generation library (e.g., fpdf2)

# --- Booking Workflow ---
# 1. [API: Google Calendar] A client requests available time slots.
#    - The backend queries the admin's calendar for free/busy periods to determine availability.
# 2. [API: Google Calendar] A client confirms a booking.
#
#    - The backend creates a new event in the admin's calendar.
#    - The event duration will be the service length + a 10-minute buffer.
#    - Logic will be in place to prevent any double-bookings (race conditions).
# 3. [API: Google Sheets] Client information is recorded.
#    - Immutable data (name, DOB) is appended to the 'Client Characteristics' Google Sheet.
#    - Visit-specific data (address, reason for visit) is appended to the 'Client Visit Log' Google Sheet.
# 4. [API: Gmail] Confirmation emails are sent.
#
#    - An email is sent to the client with booking details and a link to the intake form.
#    - A notification email is sent to the admin about the new booking.

# --- Intake Form Workflow ---
# 1. A client submits the web-based intake form.
# 2. The backend receives the form data.
#
# 3. [PDF Library] A PDF document is generated from the submitted data.
# 4. [API: Gmail] An email is sent to the admin with the client's data and the PDF as an attachment.
#
# --- Flask App Setup ---
app = Flask(__name__, template_folder='templates', static_folder='static')


# --- Google Calendar Integration ---
# Define the scopes for Google Calendar API
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/spreadsheets' # Added scope for Google Sheets
]
SERVICE_ACCOUNT_FILE = 'key.json'  # Path to your service account key file
# TODO: Replace this with your actual Google Calendar ID.
# This is typically your email address for your primary calendar.
# Find it in your calendar's "Settings and sharing" > "Integrate calendar".
CALENDAR_ID = 'cvlmt101@gmail.com'  # Or the specific calendar ID
# TODO: Replace this with the ID of your Google Sheet.
# You can find this in the URL of your sheet (e.g., docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit)
SPREADSHEET_ID = '1lcTDwJ33soNj90bohmKOJ9_qSXl0EnbaIZQZbf3pCn4' # Placeholder - REPLACE THIS

LOCAL_TIMEZONE = "America/New_York" # IMPORTANT: Change to your local timezone, e.g., "America/Chicago"
# --- Email Configuration (SMTP with App Password) ---
# IMPORTANT: For better security, store these in environment variables instead of hardcoding.
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "cvlmt101@gmail.com").strip()
# IMPORTANT: Paste the 16-digit App Password you generated here.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "cpdw khsp sqes krye").strip()

def get_calendar_service():
    """Authenticates and returns a Google Calendar API service object."""
    creds = None
    try:
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    except FileNotFoundError:
        print(f"Error: The service account key file was not found at '{SERVICE_ACCOUNT_FILE}'.")
        print("Please make sure the file is in the correct directory and the path is correct.")
        return None
    except Exception as e:
        print(f"An error occurred loading credentials: {e}")
        return None

    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"An error occurred building the service: {e}")
        return None

def get_sheets_service():
    """Authenticates and returns a Google Sheets API service object."""
    creds = None
    try:
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    except FileNotFoundError:
        print(f"Error: The service account key file was not found at '{SERVICE_ACCOUNT_FILE}'.")
        return None
    except Exception as e:
        print(f"An error occurred loading credentials for Sheets: {e}")
        return None

    try:
        service = build('sheets', 'v4', credentials=creds)
        return service
    except Exception as e:
        print(f"An error occurred building the Sheets service: {e}")
        return None

def get_free_busy(service, start_time, end_time, calendar_ids):
    """
    Retrieves free/busy information for a given calendar.
    """
    try:
        body = {
            "timeMin": start_time,
            "timeMax": end_time,
            "items": [{"id": calendar_ids}]
        }
        eventsResult = service.freebusy().query(body=body).execute()
        return eventsResult["calendars"][calendar_ids]["busy"]
    except HttpError as error:
        print(F'An error occurred: {error}')
        return None

def create_event(service, summary, start_time, end_time, description="", calendar_id='primary'):
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
    }

    try:
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"Event created: {created_event.get('htmlLink')}")
        return created_event
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

def send_smtp_email(receiver_email, subject, body_html, attachment_data=None, attachment_filename=None):
    """Sends an email using smtplib and an App Password."""
    message = MIMEMultipart()
    message["Subject"] = subject
    message["From"] = SENDER_EMAIL
    message["To"] = receiver_email
    message.attach(MIMEText(body_html, "html"))

    if attachment_data and attachment_filename:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment_data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {attachment_filename}")
        message.attach(part)

    # Create a secure SSL context
    context = ssl.create_default_context()

    # Ensure password has no spaces (Google App Passwords often have spaces for readability)
    final_password = APP_PASSWORD.replace(" ", "")

    try:
        # Attempt 1: Port 465 (SSL) - Preferred for background tasks
        print(f"Attempting to send email to {receiver_email} via Port 465...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SENDER_EMAIL, final_password)
            server.sendmail(SENDER_EMAIL, receiver_email, message.as_string())
        print("Email sent successfully via Port 465!")
        return True
    except Exception as e_ssl:
        print(f"Port 465 failed: {e_ssl}. Retrying with Port 587...")
        try:
            # Attempt 2: Port 587 (STARTTLS) - Fallback
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(SENDER_EMAIL, final_password)
                server.sendmail(SENDER_EMAIL, receiver_email, message.as_string())
            print("Email sent successfully via Port 587!")
            return True
        except Exception as e_tls:
            print(f"CRITICAL: Both Port 465 and 587 failed. Last error: {e_tls}")
            return False


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

@app.route('/IntakeConfirm.html')
def intake_confirmation_page():
    """Serves the intake form confirmation page."""
    return render_template('IntakeConfirm.html')

def _get_available_dates_list(days_to_scan=90):
    """
    Internal helper to get a list of dates with "open for bookings" events.
    Returns a list of strings in 'YYYY-MM-DD' format.
    """
    start_date = datetime.datetime.now(timezone.utc)
    end_date = start_date + timedelta(days=days_to_scan)

    service = get_calendar_service()
    if not service:
        print("DEBUG: _get_available_dates_list: Could not get calendar service.")
        return []

    try:
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_date.isoformat(),
            timeMax=end_date.isoformat(),
            singleEvents=True
        ).execute()
        all_events = events_result.get('items', [])

        available_dates = set()
        for event in all_events:
            if event.get('summary', '').lower() == 'open for bookings':
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
    """
    Scans a date range and returns a list of dates ('YYYY-MM-DD')
    that have at least one "open for bookings" event.
    """
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
        # The total time blocked on the calendar includes a 10-minute buffer.
        total_block_duration = service_duration + 10

        # Define the time window for the entire day in UTC
        start_of_day = datetime.datetime.fromisoformat(date_str).replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)
    except (ValueError, TypeError):
        return jsonify({
            "error": "Invalid date or duration format. Date should be YYYY-MM-DD and duration should be an integer."
        }), 400

    service = get_calendar_service()
    if not service:
        return jsonify({"error": "Could not connect to Google Calendar service."}), 500

    try:
        # 1. Get all events for the day
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        all_events = events_result.get('items', [])

        # 2. Parse all 'open' and 'busy' slots into datetime objects
        open_windows = []
        for event in all_events:
            if event.get('summary', '').lower() == 'open for bookings' and 'dateTime' in event['start']:
                open_windows.append({
                    'start': datetime.datetime.fromisoformat(event['start']['dateTime']),
                    'end': datetime.datetime.fromisoformat(event['end']['dateTime'])
                })

        busy_slots = []
        for event in all_events:
            if event.get('summary', '').lower() != 'open for bookings' and 'dateTime' in event['start']:
                busy_slots.append({
                    'start': datetime.datetime.fromisoformat(event['start']['dateTime']),
                    'end': datetime.datetime.fromisoformat(event['end']['dateTime'])
                })

        # 3. Generate all possible start times and validate them
        valid_start_times = []
        time_slot_interval = timedelta(minutes=15) # Generate slots every 15 minutes

        for window in open_windows:
            potential_start = window['start']
            while potential_start < window['end']:
                potential_end = potential_start + timedelta(minutes=total_block_duration)

                # Ensure the entire appointment (including buffer) fits within the open window
                if potential_end > window['end']:
                    break # This slot won't fit, and no later ones will either

                # Check for overlap with any busy slots
                is_valid = True
                for busy in busy_slots:
                    # Overlap condition: (StartA < EndB) and (EndA > StartB)
                    if potential_start < busy['end'] and potential_end > busy['start']:
                        is_valid = False
                        break # Overlaps with a busy slot

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
        buffer = 10 # 10 minute buffer
        end_time = start_time + timedelta(minutes=duration + buffer)
        summary = data['summary']
        description = data.get('description', '')
        client_info = data.get('client', {})
    except (KeyError, TypeError, ValueError) as e:
        return jsonify({"error": f"Invalid or missing data in request: {e}"}), 400

    service = get_calendar_service()
    if not service:
        return jsonify({"error": "Could not connect to Google Calendar service."}), 500

    # --- Overlap Prevention Logic ---
    # 1. Define a small window around the event to check for overlaps, just in case.
    check_start = start_time - timedelta(hours=1)
    check_end = end_time + timedelta(hours=1)

    try:
        # 2. Get all events in that window
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=check_start.isoformat(),
            timeMax=check_end.isoformat(),
            singleEvents=True
        ).execute()
        all_events = events_result.get('items', [])

        # 3. Find all "Busy" events (anything not marked as "open for bookings")
        busy_slots = [
            event for event in all_events
            if event.get('summary', '').lower() != 'open for bookings' and 'dateTime' in event['start']
        ]

        # 4. Check for overlaps
        for busy_event in busy_slots:
            busy_start = datetime.datetime.fromisoformat(busy_event['start']['dateTime'])
            busy_end = datetime.datetime.fromisoformat(busy_event['end']['dateTime'])
            # Overlap condition: (StartA < EndB) and (EndA > StartB)
            if start_time < busy_end and end_time > busy_start:
                return jsonify({"error": "The selected time slot is no longer available. Please choose another time."}), 409 # 409 Conflict

    except Exception as e:
        print(f"ERROR: /api/book: Failed during overlap check: {e}")
        return jsonify({"error": "Could not verify appointment availability. Please try again."}), 500

    # Add client details to the event description
    # This was previously handled in the frontend, but now we're reverting to the backend handling it.
    # The description from the frontend already contains client info.
    full_description = description # Revert to original description


    created_event = create_event(service, summary, start_time, end_time, full_description, CALENDAR_ID)

    if not created_event:
        return jsonify({"error": "Failed to create calendar event."}), 500

    # --- Prepare Data for Emails ---
    client_email = client_info.get('email')
    local_tz = ZoneInfo(LOCAL_TIMEZONE)
    local_start_time = start_time.astimezone(local_tz)
    booking_date_formatted = local_start_time.strftime('%B %d, %Y')
    booking_time_formatted = local_start_time.strftime('%I:%M %p')
    client_first_name = client_info.get('first_name', 'Valued Client')

    # Build the dynamic URL for the intake form (must be done in main thread)
    intake_params = {
        'firstName': client_info.get('first_name'),
        'lastName': client_info.get('last_name'),
        'email': client_email,
        'phone': client_info.get('phone'),
        'comments': data.get('description', '').replace('Comments: ', '')
    }
    intake_url = url_for('intake_page', _external=True) + '?' + urlencode(intake_params)

    # --- Define Async Email Task ---
    def send_emails_background():
        # 1. Client Email
        print(f"BACKGROUND_TASK: Starting to send emails for booking. Client email is: {client_email}")
        if client_email:
            email_subject = "Your Massage Appointment is Confirmed!"
            email_body_html = f"""
            <p>Hi {client_first_name},</p>
            <p>Thank you for booking your appointment! We look forward to seeing you on <strong>{booking_date_formatted}</strong> at <strong>{booking_time_formatted}</strong>.</p>
            <p>As a next step, if you have not already, please complete our secure client intake form by clicking the link below:</p>
            <p><a href="{intake_url}" style="padding: 10px 15px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;">Complete Intake Form</a></p>
            <p>Thank you,<br>Chelsea Vaccaro Massage Therapy</p>
            """
            client_email_sent = send_smtp_email(client_email, email_subject, email_body_html)
            if client_email_sent:
                print("BACKGROUND_TASK: Successfully sent confirmation email to client.")
            else:
                # This will now appear in Render logs if it fails
                print("BACKGROUND_TASK: WARNING: Failed to send confirmation email to client.")

        # 2. Admin Email
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
            admin_email_sent = send_smtp_email(admin_email, admin_subject, admin_body_html)
            if admin_email_sent:
                print("BACKGROUND_TASK: Successfully sent notification email to admin.")
            else:
                print("BACKGROUND_TASK: WARNING: Failed to send notification email to admin.")
        except Exception as e:
            print(f"CRITICAL: Failed to send admin notification email for booking. Error: {e}")

    # --- Start Background Thread ---
    threading.Thread(target=send_emails_background).start()

    return jsonify({
        "message": "Booking successful!",
        "event_link": created_event.get('htmlLink')
    })

def _handle_intake_submission_background(data, pdf_output):
    """Handles slow tasks (Sheets, Email) for intake form in the background."""
    client_name = f"{data.get('firstName', 'N/A')} {data.get('lastName', 'N/A')}"
    # --- 3. Update Google Sheets ---
    try:
        sheets_service = get_sheets_service()
        if sheets_service:
            # --- Part A: Update "Clients" sheet (if new client) ---
            client_email = data.get('email')
            if client_email:
                # Read the email column from the "Clients" sheet to check for existence
                result = sheets_service.spreadsheets().values().get(
                    spreadsheetId=SPREADSHEET_ID,
                    range='Clients!C:C' # Assuming Email is in Column C
                ).execute()
                existing_emails = [item for sublist in result.get('values', []) for item in sublist]

                if client_email not in existing_emails:
                    print(f"BACKGROUND_TASK: New client detected: {client_email}. Adding to 'Clients' sheet.")
                    client_row = [
                        data.get('firstName', ''),
                        data.get('lastName', ''),
                        client_email,
                        data.get('phone', ''),
                        data.get('dob', ''),
                        data.get('address', '') # Now pulling address from form data
                    ]
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=SPREADSHEET_ID,
                        range='Clients!A1',
                        valueInputOption='USER_ENTERED',
                        body={'values': [client_row]}
                    ).execute()

            # --- Part B: Always append to "Intake Forms" sheet ---
            intake_row = [
                datetime.datetime.now(ZoneInfo(LOCAL_TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S'),
                client_name,
                data.get('reason', ''),
                data.get('conditions', ''),
                data.get('allergies', '')
            ]
            sheets_service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range='Intake Forms!A1',
                valueInputOption='USER_ENTERED',
                body={'values': [intake_row]}
            ).execute()
            print("BACKGROUND_TASK: Successfully updated Google Sheets.")
    except Exception as sheets_e:
        print(f"ERROR (background): Failed to update Google Sheets: {sheets_e}")

    # --- 4. Send Email to Admin ---
    try:
        admin_email = SENDER_EMAIL
        email_subject = f"New Intake Form Submitted by {client_name}"
        email_body_html = f"""
        <p>A new client intake form has been submitted.</p>
        <p><strong>Client:</strong> {client_name}</p>
        <p><strong>Email:</strong> {data.get('email', 'N/A')}</p>
        <p><strong>Original Booking:</strong> {data.get('bookingDate', 'N/A')} at {data.get('bookingTime', 'N/A')}</p>
        <p>The completed form is attached as a PDF.</p>
        """
        attachment_filename = f"IntakeForm_{data.get('lastName', '')}_{data.get('firstName', '')}.pdf"
        email_sent = send_smtp_email(
            receiver_email=admin_email,
            subject=email_subject,
            body_html=email_body_html,
            attachment_data=pdf_output,
            attachment_filename=attachment_filename
        )
        if email_sent:
            print("BACKGROUND_TASK: Successfully sent intake form email to admin.")
        else:
            raise Exception("send_smtp_email returned False for intake form.")
    except Exception as e:
        print(f"ERROR (background): Failed to send intake form email: {e}")

@app.route('/api/submit-intake', methods=['POST'])
def submit_intake():
    """
    API endpoint to receive intake form data, generate a PDF,
    and email it to the admin.
    """
    from fpdf import FPDF
    from PIL import Image # For handling PNG transparency
    import io

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
        def write_line(label, value, is_multiline=False):
            if not value: return # Don't write empty fields
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
        # Restore the logic for medical history fields
        conditions = data.get('conditions')
        # The form sends a single string of comma-separated values, not a list.
        # So we don't need to join it, just use it as is.
        if isinstance(conditions, list): conditions = ', '.join(conditions) # Safety check
        write_line("Conditions:", conditions)
        write_line("Allergies:", data.get('allergies', 'N/A'), is_multiline=True)
        pdf.ln(5) # Add some space before the images

        # --- Embed Body Chart Images Side-by-Side and Scaled ---
        front_image_data = data.get('drawingFront')
        back_image_data = data.get('drawingBack')

        if front_image_data or back_image_data:
            pdf.set_font("Helvetica", "B", size=14)
            pdf.cell(0, 10, "Problem Areas", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2) # Small space after title

            page_width = pdf.w - 2 * pdf.l_margin
            image_width = page_width / 2 - 5 # Half page width, with a small gap

            # Determine max available height for images on the current page
            # Subtract bottom margin and some extra padding for safety
            max_image_height_on_page = pdf.h - pdf.get_y() - pdf.b_margin - 15 # Revert to original padding

            current_y_for_images = pdf.get_y()
            max_drawn_height = 0 # To track the height of the tallest image placed

            def embed_image(b64_string, x_pos):
                nonlocal max_drawn_height # Allow modifying max_drawn_height from outer scope
                if not b64_string or 'base64,' not in b64_string: return
                try:
                    image_data = base64.b64decode(b64_string.split('base64,')[1])
                    img = Image.open(io.BytesIO(image_data))
                    original_width, original_height = img.size

                    # Calculate scaling factor to fit within the bounding box (image_width, max_image_height_on_page)
                    width_ratio = image_width / original_width
                    height_ratio = max_image_height_on_page / original_height
                    scale_ratio = min(width_ratio, height_ratio)

                    final_width = original_width * scale_ratio
                    final_height = original_height * scale_ratio

                    if final_height <= 0: # Avoid division by zero or invalid image size
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
                    max_drawn_height = max(max_drawn_height, 10) # Account for error message height

            # Embed Front Image on the left
            embed_image(front_image_data, pdf.l_margin)
            # Embed Back Image on the right
            embed_image(back_image_data, pdf.l_margin + image_width + 10)

            # Advance the cursor after images are drawn
            pdf.set_y(current_y_for_images + max_drawn_height + 10) # 10 for padding below images

        # Get PDF data as bytes
        pdf_output = pdf.output()

        # --- Start Background Tasks ---
        # Move the slow operations (Google Sheets update, email sending) to a background thread
        # to avoid client-side timeouts.
        threading.Thread(target=_handle_intake_submission_background, args=(data, pdf_output)).start()

        return jsonify({"message": "Intake form submitted successfully."}), 200

    except Exception as e:
        print(f"ERROR: /api/submit-intake: {e}")
        return jsonify({"error": "Server error while processing the form."}), 500


# --- Main Execution ---
if __name__ == '__main__':
    # The 'debug=True' flag enables auto-reloading when you save the file.
    app.run(debug=True, port=5000)