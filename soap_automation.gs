/**
 * Trigger: On Form Submit
 * Objective: Generate PDF of SOAP note and link to Intake Forms tab using Calendar ID.
 */
function onFormSubmit(e) {
  const SOAP_FOLDER_ID = "1szsvDDwve5h5cISTExHKadk6r2ALVeA8";
  const TAB_NAME = "Intake Forms";
  const CAL_ID_COL_INDEX = 8; // Column I (0-indexed)
  const SOAP_LINK_COL_INDEX = 7; // Column H (0-indexed)

  console.log("Form submission received. Starting SOAP automation...");

  const responses = e.namedValues; // Case-sensitive keys based on Form Question titles

  // Robust key matching: normalizes both the target and the form keys to find matches 
  // even if there are weird spaces, ampersands, or casing differences.
  const getVal = (targetName) => {
    const normalizedTarget = targetName.toLowerCase().replace(/[^a-z0-9]/g, '');
    const key = Object.keys(responses).find(k => k.toLowerCase().replace(/[^a-z0-9]/g, '') === normalizedTarget);
    return (key && responses[key]) ? responses[key][0] : null;
  };

  const clientName = getVal('Treatment/Client') || "Client";
  const calendarId = getVal('Appointment_ID');

  if (!calendarId) {
    console.error("CRITICAL ERROR: No Calendar ID found in submission. Available keys: " + Object.keys(responses).join(", "));
    return;
  }

  console.log("Generating PDF for Client: " + clientName + " (ID: " + calendarId + ")");

  // 1. Create a temporary document to generate PDF content
  const doc = DocumentApp.create('SOAP Note - ' + clientName);
  const body = doc.getBody();

  // Set the title as a simple header to avoid redundancy with the Treatment/Client field
  body.appendParagraph('SOAP Note for ' + clientName).setHeading(DocumentApp.ParagraphHeading.HEADING1);
  body.appendParagraph('Submitted: ' + new Date().toLocaleString());
  body.appendHorizontalRule();

  const fieldOrder = [
    'Treatment/Client',
    'Date & Time',
    'Reason For Visit',
    'Chief Complaints',
    'Assessment & Plan',
    'Reassessment',
    'Future Treatment Plan',
    'Appointment_ID',
    'Digital Signature'
  ];

  // Add fields in the specified order
  fieldOrder.forEach(field => {
    const value = getVal(field);
    if (value !== null) {
      body.appendParagraph(field + ': ').setBold(true)
          .appendText(value).setBold(false);
    }
  });
  doc.saveAndClose();

  // 2. Convert to PDF and save to the specific SOAP Forms folder
  const docFile = DriveApp.getFileById(doc.getId());
  const pdfBlob = docFile.getAs('application/pdf');

  // Construct the desired PDF filename: month-day-year_Time of service Client name SOAP
  const dateTimeString = getVal('Date & Time'); // e.g., "April 06, 2026 03:30 PM"
  let formattedDate = 'UnknownDate';
  let formattedTime = 'UnknownTime'; 

  if (dateTimeString) {
    try {
      // Use Utilities.parseDate for the specific "Month dd, yyyy hh:mm a" format
      const dateObj = Utilities.parseDate(dateTimeString, Session.getScriptTimeZone(), "MMMM dd, yyyy hh:mm a");
      formattedDate = Utilities.formatDate(dateObj, Session.getScriptTimeZone(), 'MM-dd-yyyy');
      formattedTime = Utilities.formatDate(dateObj, Session.getScriptTimeZone(), 'hhmm a').replace(' ', '').toUpperCase(); // e.g. 0330PM
    } catch (e) {
      console.warn("Could not parse Date/Time string for filename: " + dateTimeString + " Error: " + e);
    }
  }
  // Ensure the filename uses underscores and follows the month-day-year_Time_Name format
  const cleanClientName = clientName.replace(/[^a-zA-Z0-9 ]/g, '').trim().replace(/\s+/g, '_');
  const newFilename = `${formattedDate}_${formattedTime}_${cleanClientName}_SOAP.pdf`;

  const folder = DriveApp.getFolderById(SOAP_FOLDER_ID);
  const pdfFile = folder.createFile(pdfBlob);
  pdfFile.setName(newFilename);

  console.log("PDF Created successfully: " + pdfFile.getUrl());

  // Cleanup: Delete the temporary Google Doc
  docFile.setTrashed(true);

  // 3. Find the row in "Intake Forms" and update Column G
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(TAB_NAME);

  if (!sheet) {
    console.error("ERROR: Sheet '" + TAB_NAME + "' not found. Check your tab names.");
    return;
  }

  const data = sheet.getDataRange().getValues();
  let foundMatch = false;

  for (let i = 1; i < data.length; i++) {
    // Use String conversion and trim to ensure a robust match between the sheet and form response
    if (String(data[i][CAL_ID_COL_INDEX]).trim() === String(calendarId).trim()) {
      console.log("Match found on row " + (i + 1) + ". Updating SOAP Notes link...");
      sheet.getRange(i + 1, SOAP_LINK_COL_INDEX + 1).setValue(pdfFile.getUrl());
      foundMatch = true;
      break;
    }
  }

  if (!foundMatch) {
    console.warn("No match found in '" + TAB_NAME + "' for Calendar ID: " + calendarId);
  }
}