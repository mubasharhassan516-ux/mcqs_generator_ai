"""
form_creator.py
===============
Creates a Google Form from MCQ data and links responses to a Google Sheet.

Setup (one-time):
    1. Go to https://console.cloud.google.com/
    2. Create a project and enable:
       - Google Forms API
       - Google Sheets API
       - Google Drive API
    3. Create a Service Account, download the JSON key file.
    4. Set the environment variable:
          GOOGLE_SERVICE_ACCOUNT_FILE = /path/to/service-account.json
       OR place the file at:  config/service_account.json

    5. Share your Google Drive folder with the service account email
       (so it can create files in your Drive).

Environment variables:
    GOOGLE_SERVICE_ACCOUNT_FILE  – path to service-account JSON key
    GOOGLE_DRIVE_FOLDER_ID       – (optional) folder ID to place the form in
"""

import os
import json
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

SERVICE_ACCOUNT_FILE = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    "config/service_account.json",
)
DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")

SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────

def _get_credentials():
    """Build Google service-account credentials."""
    try:
        from google.oauth2 import service_account
    except ImportError:
        raise ImportError(
            "google-auth is required. Run: pip install google-auth google-auth-httplib2 google-api-python-client"
        )

    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        # Try to find the file in common locations
        alt_paths = [
            os.path.join(os.path.dirname(__file__), "config", "service_account.json"),
            os.path.join(os.path.expanduser("~"), "service_account.json"),
            os.path.join(os.getcwd(), "service_account.json"),
        ]
        
        for alt_path in alt_paths:
            if os.path.exists(alt_path):
                logger.info(f"Found service account file at: {alt_path}")
                SERVICE_ACCOUNT_FILE = alt_path
                break
        else:
            raise FileNotFoundError(
                f"Service account file not found. Looked in:\n"
                f"  - {SERVICE_ACCOUNT_FILE}\n"
                f"  - " + "\n  - ".join(alt_paths) + "\n"
                "Set GOOGLE_SERVICE_ACCOUNT_FILE env variable or place the key in one of these locations."
            )

    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )


def _build_services():
    """Return authenticated Forms, Drive, and Sheets service clients."""
    from googleapiclient.discovery import build

    creds = _get_credentials()
    forms_service = build("forms", "v1", credentials=creds, cache_discovery=False)
    drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    sheets_service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return forms_service, drive_service, sheets_service


# ─────────────────────────────────────────────
#  FORM BUILDER HELPERS (Enhanced)
# ─────────────────────────────────────────────

def _build_question_item(mcq: dict, index: int) -> dict:
    """Convert an MCQ dict to a Google Forms API request item with enhanced formatting."""
    options = [{"value": opt} for opt in mcq.get("options", [])]

    # Get metadata with fallbacks
    chapter = mcq.get("chapter", "General")
    difficulty = mcq.get("difficulty", "Medium")
    topic = mcq.get("topic", chapter)
    
    # Format the question with metadata
    question_text = mcq.get("question", "")
    
    # Add metadata prefix for better organization
    metadata_prefix = f"[{difficulty}]"
    if chapter and chapter != "General":
        metadata_prefix = f"[{chapter} | {difficulty}]"
    
    # Check if question already has the answer format (for frontend display)
    if "Correct:" in question_text:
        # This is from the frontend - clean it up
        question_text = question_text.split("Correct:")[0].strip()
    
    title = f"Q{index + 1}: {question_text}\n{metadata_prefix}"

    return {
        "createItem": {
            "item": {
                "title": title,
                "description": f"Difficulty: {difficulty} | Topic: {topic}",
                "questionItem": {
                    "question": {
                        "required": True,
                        "choiceQuestion": {
                            "type": "RADIO",
                            "options": options,
                            "shuffle": False,
                        }
                    }
                }
            },
            "location": {"index": index}
        }
    }


def _build_answer_key_item(mcq: dict, index: int) -> dict:
    """Create a separate item for the answer key (optional)."""
    correct_answer = mcq.get("correct_answer", "")
    explanation = mcq.get("explanation", "")
    
    # Extract just the letter if it's in "A. ..." format
    if correct_answer and ". " in correct_answer:
        correct_letter = correct_answer[0]
    else:
        correct_letter = "A"
    
    answer_text = f"Correct Answer: {correct_answer}\n\nExplanation: {explanation}"
    
    return {
        "createItem": {
            "item": {
                "title": f"Answer Key for Q{index + 1}",
                "description": answer_text,
                "questionItem": {
                    "question": {
                        "required": False,
                        "textQuestion": {
                            "paragraph": True
                        }
                    }
                }
            },
            "location": {"index": index * 2 + 1}  # Place after each question
        }
    }


# ─────────────────────────────────────────────
#  SHEET FORMATTING HELPERS
# ─────────────────────────────────────────────

def _format_sheet(sheets_service, spreadsheet_id: str, mcqs: list[dict]):
    """Format the response sheet with headers and metadata."""
    
    # Prepare headers
    headers = ["Timestamp", "Respondent Email", "Score"] + [f"Q{i+1} Answer" for i in range(len(mcqs))]
    
    # Add answer key row
    answer_key_row = ["ANSWER KEY", "", ""] + [mcq.get("correct_answer", "") for mcq in mcqs]
    
    # Prepare batch update
    requests = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": 0,
                    "title": "MCQ Responses",
                    "gridProperties": {
                        "frozenRowCount": 2,
                        "rowCount": 1000,
                        "columnCount": len(headers)
                    }
                },
                "fields": "title,gridProperties.frozenRowCount,gridProperties.rowCount,gridProperties.columnCount"
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(headers)
                },
                "cell": {
                    "userEnteredValue": {"stringValue": "MCQ Quiz Responses"},
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "fontSize": 14},
                        "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
                    }
                },
                "fields": "userEnteredValue,userEnteredFormat"
            }
        }
    ]
    
    # Add headers
    for i, header in enumerate(headers):
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": i,
                    "endColumnIndex": i + 1
                },
                "cell": {
                    "userEnteredValue": {"stringValue": header},
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": {"red": 0.8, "green": 0.8, "blue": 0.9}
                    }
                },
                "fields": "userEnteredValue,userEnteredFormat"
            }
        })
    
    # Add answer key row
    for i, value in enumerate(answer_key_row):
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startRowIndex": 2,
                    "endRowIndex": 3,
                    "startColumnIndex": i,
                    "endColumnIndex": i + 1
                },
                "cell": {
                    "userEnteredValue": {"stringValue": str(value)},
                    "userEnteredFormat": {
                        "textFormat": {"italic": True},
                        "backgroundColor": {"red": 0.9, "green": 1.0, "blue": 0.9}
                    }
                },
                "fields": "userEnteredValue,userEnteredFormat"
            }
        })
    
    # Add column widths
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": 0,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": 1
            },
            "properties": {
                "pixelSize": 180
            },
            "fields": "pixelSize"
        }
    })
    
    for i in range(3, len(headers)):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": 0,
                    "dimension": "COLUMNS",
                    "startIndex": i,
                    "endIndex": i + 1
                },
                "properties": {
                    "pixelSize": 300
                },
                "fields": "pixelSize"
            }
        })
    
    # Apply all formatting
    if requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()


# ─────────────────────────────────────────────
#  STUB FORM (enhanced)
# ─────────────────────────────────────────────

def _stub_form_result(mcqs: list[dict], title: str, include_answers: bool = True) -> dict:
    """Return a fake result dict when Google credentials are absent."""
    logger.warning(
        "Google credentials not configured – returning stub form result."
    )
    
    # Generate a demo form ID based on timestamp
    demo_id = f"DEMO_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Create sample URLs
    base_url = f"https://docs.google.com/forms/d/{demo_id}"
    
    result = {
        "form_url": f"{base_url}/edit",
        "prefill_url": f"{base_url}/viewform",
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{demo_id}_sheet/edit",
        "form_id": demo_id,
        "sheet_id": f"{demo_id}_sheet",
        "title": title,
        "question_count": len(mcqs),
        "demo": True,
        "message": "This is a demo form. Configure Google service account to create real forms."
    }
    
    # Add answer key if requested
    if include_answers and mcqs:
        result["answer_key"] = [
            {
                "question": mcq.get("question", ""),
                "correct_answer": mcq.get("correct_answer", ""),
                "explanation": mcq.get("explanation", "")
            }
            for mcq in mcqs
        ]
    
    return result


# ─────────────────────────────────────────────
#  PUBLIC API (Enhanced)
# ─────────────────────────────────────────────

def create_google_form(mcqs: list[dict], title: str = "MCQ Quiz", 
                      include_answer_key: bool = True,
                      format_sheet: bool = True) -> dict:
    """
    Create a Google Form populated with the given MCQs.
    
    Args:
        mcqs: List of MCQ dictionaries
        title: Form title
        include_answer_key: Whether to add answer key section
        format_sheet: Whether to format the response sheet
    
    Returns a dict with:
        form_url      – edit URL for the form owner
        prefill_url   – respondent-facing URL
        sheet_url     – linked Google Sheet URL
        form_id       – Google Form ID
        sheet_id      – Google Sheet ID
        title         – form title
        question_count
        answer_key    – (optional) answer key if requested
    """
    
    # Validate input
    if not mcqs:
        return _stub_form_result([], title)
    
    # Check for service account
    service_account_path = SERVICE_ACCOUNT_FILE
    if not os.path.exists(service_account_path):
        # Try to find in common locations
        alt_paths = [
            os.path.join(os.path.dirname(__file__), "config", "service_account.json"),
            os.path.join(os.path.expanduser("~"), "service_account.json"),
            os.path.join(os.getcwd(), "service_account.json"),
        ]
        
        for path in alt_paths:
            if os.path.exists(path):
                service_account_path = path
                logger.info(f"Found service account at: {path}")
                break
        else:
            logger.warning("No service account file found")
            return _stub_form_result(mcqs, title, include_answer_key)

    try:
        # Pass the found path to _build_services
        forms_service, drive_service, sheets_service = _build_services_with_path(service_account_path)
    except Exception as e:
        logger.error("Failed to authenticate with Google APIs: %s", e)
        return _stub_form_result(mcqs, title, include_answer_key)

    # ── 1. Create the form shell ──────────────────────────────────────────
    form_body = {
        "info": {
            "title": title,
            "documentTitle": title,
            "description": f"Generated by AI MCQ Generator Pro on {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                          f"Total Questions: {len(mcqs)}"
        }
    }
    
    try:
        form = forms_service.forms().create(body=form_body).execute()
        form_id = form["formId"]
        logger.info("Created Google Form with ID: %s", form_id)
    except Exception as e:
        logger.error("Failed to create form: %s", e)
        return _stub_form_result(mcqs, title, include_answer_key)

    # ── 2. Add questions via batchUpdate ─────────────────────────────────
    requests = []
    
    # Add main questions
    for i, mcq in enumerate(mcqs):
        requests.append(_build_question_item(mcq, i))
    
    # Add answer key items if requested
    if include_answer_key:
        for i, mcq in enumerate(mcqs):
            requests.append(_build_answer_key_item(mcq, i))

    if requests:
        try:
            forms_service.forms().batchUpdate(
                formId=form_id,
                body={"requests": requests}
            ).execute()
            logger.info("Added %d question(s) to form.", len(requests))
        except Exception as e:
            logger.error("Failed to add questions: %s", e)

    # ── 3. Enable quiz mode and collect emails ───────────────────────────
    try:
        forms_service.forms().batchUpdate(
            formId=form_id,
            body={
                "requests": [
                    {
                        "updateSettings": {
                            "settings": {
                                "quizSettings": {"isQuiz": True},
                                "emailCollectionType": "COLLECT_ALWAYS"
                            },
                            "updateMask": "quizSettings.isQuiz,emailCollectionType"
                        }
                    }
                ]
            }
        ).execute()
    except Exception as e:
        logger.warning("Failed to enable quiz settings: %s", e)

    # ── 4. Link responses to a Google Sheet ──────────────────────────────
    sheet_title = f"{title} – Responses"
    try:
        spreadsheet = sheets_service.spreadsheets().create(
            body={
                "properties": {"title": sheet_title},
                "sheets": [{"properties": {"title": "MCQ Responses"}}]
            }
        ).execute()
        sheet_id = spreadsheet["spreadsheetId"]
        logger.info("Created Google Sheet with ID: %s", sheet_id)

        # Format the sheet
        if format_sheet:
            try:
                _format_sheet(sheets_service, sheet_id, mcqs)
            except Exception as e:
                logger.warning("Failed to format sheet: %s", e)

        # Connect form responses to sheet
        drive_service.files().update(
            fileId=form_id,
            addParents=sheet_id,
            fields="id, parents"
        ).execute()

    except Exception as e:
        logger.error("Failed to create/link sheet: %s", e)
        sheet_id = None
        sheet_url = None

    # ── 5. Move to specified Drive folder ─────────────────────────────────
    if DRIVE_FOLDER_ID:
        try:
            drive_service.files().update(
                fileId=form_id,
                addParents=DRIVE_FOLDER_ID,
                removeParents="root",
                fields="id, parents"
            ).execute()
            
            if sheet_id:
                drive_service.files().update(
                    fileId=sheet_id,
                    addParents=DRIVE_FOLDER_ID,
                    removeParents="root",
                    fields="id, parents"
                ).execute()
        except Exception as e:
            logger.warning("Failed to move files to folder: %s", e)

    # ── 6. Build response ─────────────────────────────────────────────────
    form_url = f"https://docs.google.com/forms/d/{form_id}/edit"
    prefill_url = f"https://docs.google.com/forms/d/{form_id}/viewform"
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit" if sheet_id else None

    result = {
        "form_url": form_url,
        "prefill_url": prefill_url,
        "sheet_url": sheet_url,
        "form_id": form_id,
        "sheet_id": sheet_id,
        "title": title,
        "question_count": len(mcqs),
        "demo": False,
        "created_at": datetime.now().isoformat()
    }
    
    # Add answer key if requested
    if include_answer_key:
        result["answer_key"] = [
            {
                "question_number": i + 1,
                "question": mcq.get("question", ""),
                "correct_answer": mcq.get("correct_answer", ""),
                "explanation": mcq.get("explanation", ""),
                "difficulty": mcq.get("difficulty", "Medium")
            }
            for i, mcq in enumerate(mcqs)
        ]

    return result


# Add this helper function
def _build_services_with_path(service_account_path: str):
    """Build services with a specific service account path."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    creds = service_account.Credentials.from_service_account_file(
        service_account_path, scopes=SCOPES
    )
    forms_service = build("forms", "v1", credentials=creds, cache_discovery=False)
    drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    sheets_service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return forms_service, drive_service, sheets_service


def get_form_responses(form_id: str, sheet_id: str = None) -> list[dict]:
    """Retrieve responses from a form (requires sheet access)."""
    if not form_id or "DEMO" in form_id:
        return []
    
    try:
        _, _, sheets_service = _build_services()
        
        if not sheet_id:
            # Try to find linked sheet
            drive_service = _build_services()[1]
            results = drive_service.files().list(
                q=f"'{form_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet'",
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            if files:
                sheet_id = files[0]['id']
            else:
                return []
        
        # Fetch responses from sheet
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="MCQ Responses!A:Z"
        ).execute()
        
        values = result.get('values', [])
        if len(values) < 3:  # Need at least headers and answer key
            return []
        
        # Parse responses
        headers = values[1]  # Second row is headers
        responses = []
        
        for row in values[3:]:  # Skip header rows
            if row:
                response = dict(zip(headers, row))
                responses.append(response)
        
        return responses
        
    except Exception as e:
        logger.error(f"Failed to fetch responses: {e}")
        return []