
# === Chel Massage Backend Plan ===
import base64
import datetime
import os
import threading
from urllib.parse import urlencode
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image
from flask import Flask, request, jsonify, render_template, url_for
from zoneinfo import ZoneInfo
from google.auth.transport.requests import Request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCredentials
import io
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from datetime import timezone, timedelta


app = Flask(__name__, template_folder='templates', static_folder='static')


# --- Google Calendar Integration ---
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/spreadsheets'
]
SERVICE_ACCOUNT_FILE = 'key.json'
CALENDAR_ID = 'cvlmt101@gmail.com'
SPREADSHEET_ID = '1lcTDwJ33soNj90bohmKOJ9_qSXl0EnbaIZQZbf3pCn4'

LOCAL_TIMEZONE = "America/New_York"
# --- Email Configuration (SMTP with App Password) ---
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "").strip()
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()

# --- Startup Configuration Checks ---
if not SENDER_EMAIL or not APP_PASSWORD:
    print("SYSTEM WARNING: SENDER_EMAIL or APP_PASSWORD not set. Emails will NOT send.")
else:
    print(f"SYSTEM: Email configuration loaded for {SENDER_EMAIL}")

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    print(f"SYSTEM WARNING: {SERVICE_ACCOUNT_FILE} not found. Calendar/Sheets integration will fail.")

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

def get_gmail_service():
    """Authenticates and returns a Google Gmail API service object."""
    # 1. Try OAuth2 User Token (token.json) - Required for @gmail.com addresses
    if os.path.exists('token.json'):
        try:
            creds = UserCredentials.from_authorized_user_file('token.json', SCOPES)
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            print(f"Error loading token.json: {e}")

    creds = None
    try:
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    except FileNotFoundError:
        print(f"Error: The service account key file was not found at '{SERVICE_ACCOUNT_FILE}'.")
        return None
    except Exception as e:
        print(f"An error occurred loading credentials for Gmail: {e}")
        return None

    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        print(f"An error occurred building the Gmail service: {e}")
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

def send_email(receiver_email, subject, body_html, attachment_data=None, attachment_filename=None):
    """Sends an email using the Google Gmail API (Port 443)."""
    
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
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment_data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {attachment_filename}")
        message.attach(part)

    # Encode the message for the Gmail API
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {'raw': raw_message}

    try:
        # userId='me' refers to the service account itself
        sent_message = service.users().messages().send(userId='me', body=body).execute()
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
        total_block_duration = service_duration + 10

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
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        all_events = events_result.get('items', [])

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

        valid_start_times = []
        time_slot_interval = timedelta(minutes=15)

        for window in open_windows:
            potential_start = window['start']
            while potential_start < window['end']:
                potential_end = potential_start + timedelta(minutes=total_block_duration)

                if potential_end > window['end']:
                    break

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
        buffer = 10
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
                result = sheets_service.spreadsheets().values().get(
                    spreadsheetId=SPREADSHEET_ID,
                    range='Clients!C:C'
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
                        data.get('address', '')
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
        email_sent, _ = send_email(
            receiver_email=admin_email,
            subject=email_subject,
            body_html=email_body_html,
            attachment_data=pdf_output,
            attachment_filename=attachment_filename
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
        def write_line(label, value, is_multiline=False):
            if not value: return
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
        if isinstance(conditions, list): conditions = ', '.join(conditions)
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
                if not b64_string or 'base64,' not in b64_string: return
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
        pdf_output = pdf.output()

        # --- Start Background Tasks ---
        threading.Thread(target=_handle_intake_submission_background, args=(data, pdf_output)).start()

        return jsonify({"message": "Intake form submitted successfully."}), 200

    except Exception as e:
        print(f"ERROR: /api/submit-intake: {e}")
        return jsonify({"error": "Server error while processing the form."}), 500

# --- Main Execution ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)