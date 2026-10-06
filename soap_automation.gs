/**
 * HARDENED SOAP AUTOMATION
 * More resilient against INTERNAL hangs / empty fields / concurrent submits.
 *
 * After linking the SOAP PDF to Intake Forms column H, refreshes "Previous SOAP Notes"
 * on this client's upcoming Google Calendar events (3 most recent PDF links).
 *
 * Script property (Project settings → Script properties):
 *   PRIMARY_CALENDAR_ID = same as CALENDAR_ID on Render
 */
function onFormSubmit(e) {
  const SOAP_FOLDER_ID = "1szsvDDwve5h5cISTExHKadk6r2ALVeA8";
  const TAB_NAME = "Intake Forms";
  const RESPONSE_TAB_NAME = "Form Responses 1";
  const CAL_ID_COL_INDEX = 8;   // Column I (0-based)
  const SOAP_LINK_COL_INDEX = 7; // Column H (0-based)
  const EMAIL_COL_INDEX = 9; // Column J
  const NAME_COL_INDEX = 2; // Column C
  const TABLE_INSERT_ROW = 5;

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) {
    console.error("Could not obtain script lock. Another run is in progress.");
    return;
  }

  try {
    console.log("1) Form submission received");

    if (!e || !e.namedValues) {
      console.error("No event payload (e.namedValues missing).");
      return;
    }

    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const respSheet = ss.getSheetByName(RESPONSE_TAB_NAME);
    if (!respSheet) {
      console.error("Missing sheet: " + RESPONSE_TAB_NAME);
      return;
    }

    const responses = e.namedValues;

    const getVal = (targetName) => {
      const normalizedTarget = targetName.toLowerCase().replace(/[^a-z0-9]/g, "");
      const key = Object.keys(responses).find(
        (k) => k.toLowerCase().replace(/[^a-z0-9]/g, "") === normalizedTarget
      );
      const value = key && responses[key] ? responses[key][0] : "";
      if (value === null || value === undefined) return "";
      return String(value).trim();
    };

    const clientRaw = getVal("Treatment/Client");
    const clientName = clientRaw || "Unnamed Client";
    const calendarId = getVal("Appointment_ID");

    console.log("2) Parsed client=" + clientName + " calendarId=" + calendarId);

    if (!calendarId) {
      console.error("CRITICAL: No Calendar ID found. Stopping.");
      return;
    }

    try {
      console.log("3) Reorganizing Form Responses sheet");
      const lastRow = respSheet.getLastRow();
      const lastCol = respSheet.getLastColumn();

      if (lastRow >= TABLE_INSERT_ROW && lastCol > 0) {
        const newRowData = respSheet.getRange(lastRow, 1, 1, lastCol).getValues();
        respSheet.insertRowBefore(TABLE_INSERT_ROW);
        respSheet.getRange(TABLE_INSERT_ROW, 1, 1, lastCol).setValues(newRowData);

        const bottomRow = respSheet.getLastRow();
        if (bottomRow > TABLE_INSERT_ROW) {
          respSheet.deleteRow(bottomRow);
        }

        const formula =
          '=IF($B$2="", TRUE, ISNUMBER(SEARCH($B$2, TEXTJOIN(" ", TRUE, A' +
          TABLE_INSERT_ROW +
          ":J" +
          TABLE_INSERT_ROW +
          "))))";
        respSheet.getRange(TABLE_INSERT_ROW, 11).setFormula(formula);
      }
      SpreadsheetApp.flush();
      console.log("4) Sheet reorganization done");
    } catch (sheetErr) {
      console.error("Sheet reorganization failed (continuing to PDF): " + sheetErr);
    }

    console.log("5) Creating SOAP Google Doc");
    const doc = DocumentApp.create("SOAP Note - " + clientName);
    const body = doc.getBody();

    body.appendParagraph("SOAP Note for " + clientName)
      .setHeading(DocumentApp.ParagraphHeading.HEADING1);
    body.appendParagraph("Submitted: " + new Date().toLocaleString());
    body.appendHorizontalRule();

    const fieldOrder = [
      "Treatment/Client",
      "Date & Time",
      "Reason For Visit",
      "Chief Complaints",
      "Assessment & Plan",
      "Reassessment",
      "Future Treatment Plan",
      "Appointment_ID",
      "Digital Signature",
    ];

    fieldOrder.forEach((field) => {
      let value = getVal(field) || " ";

      if (field === "Digital Signature") {
        if (!value || value === " ") {
          value = "Not provided";
        } else if (value.indexOf("http") === 0) {
          value = "Signed (file linked in Form Responses)";
        } else if (value.length > 200) {
          value = "Signed";
        } else {
          value = "Signed";
        }
      }

      const p = body.appendParagraph("");
      p.appendText(field + ": ").setBold(true);
      p.appendText(value).setBold(false);
    });

    doc.saveAndClose();
    console.log("6) Doc saved: " + doc.getId());

    const docFile = DriveApp.getFileById(doc.getId());
    const pdfBlob = docFile.getAs("application/pdf");
    const folder = DriveApp.getFolderById(SOAP_FOLDER_ID);
    const pdfFile = folder.createFile(pdfBlob).setName("SOAP Note - " + clientName + ".pdf");
    docFile.setTrashed(true);
    console.log("7) PDF created: " + pdfFile.getUrl());

    let matchedEmail = "";
    let matchedName = clientName;

    const intakeSheet = ss.getSheetByName(TAB_NAME);
    if (intakeSheet) {
      const data = intakeSheet.getDataRange().getValues();
      let linked = false;
      for (let i = 1; i < data.length; i++) {
        if (String(data[i][CAL_ID_COL_INDEX]).trim() === String(calendarId).trim()) {
          intakeSheet.getRange(i + 1, SOAP_LINK_COL_INDEX + 1).setValue(pdfFile.getUrl());
          matchedEmail = data[i][EMAIL_COL_INDEX] ? String(data[i][EMAIL_COL_INDEX]).trim() : "";
          matchedName = data[i][NAME_COL_INDEX] ? String(data[i][NAME_COL_INDEX]).trim() : clientName;
          console.log("8) Linked PDF on Intake Forms row " + (i + 1));
          linked = true;
          break;
        }
      }
      if (!linked) {
        console.warn("No Intake Forms row for Calendar ID " + calendarId + " — PDF not linked in column H.");
      }
    } else {
      console.error("Missing sheet: " + TAB_NAME);
    }

    try {
      const updated = syncPreviousSoapToFutureCalendarEvents_(matchedEmail, matchedName);
      console.log("9) Updated previous SOAP links on " + updated + " future calendar event(s).");
    } catch (syncErr) {
      console.error("Calendar sync failed (SOAP PDF was still saved): " + syncErr);
    }

    console.log("SUCCESS for " + clientName);
  } catch (err) {
    console.error("FATAL: " + err);
    console.error(err && err.stack ? err.stack : "no stack");
  } finally {
    lock.releaseLock();
  }
}

// --- Previous SOAP notes on upcoming calendar events (from Intake Forms col H) ---

const PREVIOUS_SOAP_NOTES_TAG = "--- ADMIN: PREVIOUS SOAP NOTES ---";
const PREVIOUS_SOAP_LIMIT = 3;
const FUTURE_DAYS = 180;

function getPrimaryCalendarId_() {
  const id = PropertiesService.getScriptProperties().getProperty("PRIMARY_CALENDAR_ID");
  if (!id) {
    throw new Error("Set Script property PRIMARY_CALENDAR_ID (same as CALENDAR_ID on Render).");
  }
  return id;
}

function normalizeEmail_(email) {
  return String(email || "").trim().toLowerCase();
}

function normalizeName_(name) {
  return String(name || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function fetchRecentSoapPdfEntries_(clientEmail, clientName, limit) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("Intake Forms");
  if (!sheet) return [];

  const data = sheet.getDataRange().getValues();
  const targetEmail = normalizeEmail_(clientEmail);
  const targetName = normalizeName_(clientName);
  const candidates = [];

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const soapUrl = row[7] ? String(row[7]).trim() : "";
    if (!soapUrl || soapUrl.toLowerCase().indexOf("http") !== 0) continue;

    const rowEmail = normalizeEmail_(row[9]);
    const rowName = normalizeName_(row[2]);
    let matched = false;
    if (targetEmail && rowEmail && rowEmail === targetEmail) matched = true;
    else if (targetName && rowName && rowName === targetName) matched = true;
    if (!matched) continue;

    let label = row[1] ? String(row[1]).trim() : "";
    if (!label) label = row[0] ? String(row[0]).trim() : "SOAP note";

    candidates.push({ url: soapUrl, label: label, sortKey: row[0] ? String(row[0]) : "" });
  }

  candidates.sort(function (a, b) {
    return parseIntakeTimestamp_(b.sortKey) - parseIntakeTimestamp_(a.sortKey);
  });

  const seen = {};
  const entries = [];
  for (let j = 0; j < candidates.length; j++) {
    const url = candidates[j].url;
    if (seen[url]) continue;
    seen[url] = true;
    entries.push({ url: url, label: candidates[j].label });
    if (entries.length >= limit) break;
  }
  return entries;
}

function parseIntakeTimestamp_(value) {
  if (!value) return 0;
  try {
    return Utilities.parseDate(String(value), Session.getScriptTimeZone(), "yyyy-MM-dd hh:mm:ss a").getTime();
  } catch (e1) {
    try {
      return new Date(value).getTime();
    } catch (e2) {
      return 0;
    }
  }
}

function escapeHtml_(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildPreviousSoapNotesHtml_(entries) {
  if (!entries.length) return "";
  const lines = [];
  for (let i = 0; i < entries.length; i++) {
    const label = escapeHtml_(entries[i].label || "SOAP note");
    const url = escapeHtml_(entries[i].url || "");
    if (!url) continue;
    lines.push('<a href="' + url + '">' + label + '</a>');
  }
  return lines.join("<br>");
}

function upsertPreviousSoapNotesInDescription_(description, entries) {
  let desc = String(description || "").replace(/\s+$/, "");
  const content = buildPreviousSoapNotesHtml_(entries);

  const lines = desc.split("\n");
  const cleaned = [];
  let skipping = false;
  for (let i = 0; i < lines.length; i++) {
    const stripped = lines[i].trim();
    if (stripped === PREVIOUS_SOAP_NOTES_TAG || stripped.indexOf(PREVIOUS_SOAP_NOTES_TAG) === 0) {
      skipping = true;
      continue;
    }
    if (skipping && stripped.indexOf("--- ADMIN:") === 0) {
      skipping = false;
      cleaned.push(lines[i]);
      continue;
    }
    if (skipping) continue;
    cleaned.push(lines[i]);
  }
  desc = cleaned.join("\n").replace(/\s+$/, "");

  if (!content) return desc;
  const block = PREVIOUS_SOAP_NOTES_TAG + "\n" + content;
  return desc ? desc + "\n\n" + block : block;
}

function eventBelongsToClient_(event, clientEmail, clientName) {
  const title = event.getTitle() || "";
  const lowerTitle = title.toLowerCase();
  if (lowerTitle === "open for bookings" || title.indexOf("WAITLIST:") === 0) return false;

  const desc = event.getDescription() || "";
  const emailMatch = desc.match(/email:\s*([^\s<\n\r]+)/i);
  const eventEmail = emailMatch ? normalizeEmail_(emailMatch[1]) : "";
  const targetEmail = normalizeEmail_(clientEmail);
  if (targetEmail && eventEmail && eventEmail === targetEmail) return true;

  const targetName = normalizeName_(clientName);
  if (targetName && lowerTitle.indexOf(targetName) !== -1) return true;
  return false;
}

function syncPreviousSoapToFutureCalendarEvents_(clientEmail, clientName) {
  const calendarId = getPrimaryCalendarId_();
  const calendar = CalendarApp.getCalendarById(calendarId);
  if (!calendar) {
    throw new Error("Could not open calendar: " + calendarId);
  }

  const entries = fetchRecentSoapPdfEntries_(clientEmail, clientName, PREVIOUS_SOAP_LIMIT);
  const now = new Date();
  const end = new Date(now.getTime() + FUTURE_DAYS * 24 * 60 * 60 * 1000);
  const events = calendar.getEvents(now, end);

  let updated = 0;
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    if (!eventBelongsToClient_(ev, clientEmail, clientName)) continue;

    const oldDesc = ev.getDescription() || "";
    const newDesc = upsertPreviousSoapNotesInDescription_(oldDesc, entries);
    if (newDesc !== oldDesc) {
      ev.setDescription(newDesc);
      updated++;
    }
  }
  return updated;
}
