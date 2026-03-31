"""
app.py
======
AI Document to MCQ Generator Pro – Main Flask Application

Run locally:
    pip install -r requirements.txt
    python app.py

Environment variables (add to a .env file or export before running):
    ANTHROPIC_API_KEY            – Anthropic Claude API key
    GOOGLE_SERVICE_ACCOUNT_FILE  – path to Google service-account JSON
    GOOGLE_DRIVE_FOLDER_ID       – (optional) Drive folder ID for the form
    TWILIO_ACCOUNT_SID           – Twilio Account SID
    TWILIO_AUTH_TOKEN            – Twilio Auth Token
    TWILIO_WHATSAPP_FROM         – Twilio WhatsApp sender number
    SECRET_KEY                   – Flask session secret (random string)
    MAX_UPLOAD_MB                – max upload size in MB (default 50)
"""

import os
import json
import uuid
import logging
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from current directory
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_from_directory,
)
from werkzeug.utils import secure_filename

# ── Local modules ─────────────────────────────────────────────────────────────
from doc_reader import extract_chapters, distribute_mcq_count
from mcq_generator import generate_all_mcqs
from form_creator import create_google_form
from whatsapp_sender import send_whatsapp_message

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())

# Upload size limit
MAX_MB = int(os.environ.get("MAX_UPLOAD_MB", 50))
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
UPLOAD_FOLDER = Path(tempfile.gettempdir()) / "mcq_uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _error(message: str, status: int = 400) -> tuple:
    return jsonify({"success": False, "error": message}), status


# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    """
    POST /generate
    Form fields:
        file          – uploaded .docx or .pdf
        num_mcqs      – integer, total MCQs to generate
        quiz_title    – optional quiz title
        whatsapp      – optional recipient WhatsApp number
    """
    # ── 1. Validate file ──────────────────────────────────────────────────
    if "file" not in request.files:
        return _error("No file uploaded. Please attach a .docx or .pdf file.")

    file = request.files["file"]
    if file.filename == "":
        return _error("No file selected.")

    filename = secure_filename(file.filename)
    if not _allowed_file(filename):
        return _error("Invalid file type. Only .docx and .pdf are supported.")

    # ── 2. Validate MCQ count ─────────────────────────────────────────────
    try:
        num_mcqs = int(request.form.get("num_mcqs", 10))
        if not 1 <= num_mcqs <= 200:
            raise ValueError
    except (ValueError, TypeError):
        return _error("Number of MCQs must be an integer between 1 and 200.")

    quiz_title = request.form.get("quiz_title", "").strip() or f"Quiz – {filename}"
    whatsapp_number = request.form.get("whatsapp", "").strip()

    # ── 3. Save uploaded file ─────────────────────────────────────────────
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    save_path = UPLOAD_FOLDER / unique_name
    file.save(str(save_path))
    logger.info("File saved: %s", save_path)

    try:
        # ── 4. Extract chapters ───────────────────────────────────────────
        chapters = extract_chapters(str(save_path))
        logger.info("Chapters found: %d", len(chapters))

        if not chapters:
            return _error("Could not extract any readable text from the document.")

        # ── 5. Distribute MCQ count across chapters ───────────────────────
        chapters = distribute_mcq_count(chapters, num_mcqs)

        # ── 6. Generate MCQs via AI ───────────────────────────────────────
        mcqs = generate_all_mcqs(chapters)
        logger.info("Total MCQs generated: %d", len(mcqs))

        if not mcqs:
            return _error("MCQ generation failed. Please try again.")

        # ── 7. Create Google Form ─────────────────────────────────────────
        form_result = create_google_form(mcqs, title=quiz_title)
        logger.info("Google Form result: %s", form_result)

        # ── 8. Send WhatsApp notification ─────────────────────────────────
        whatsapp_result = None
        if whatsapp_number:
            whatsapp_result = send_whatsapp_message(
                to_phone=whatsapp_number,
                form_url=form_result.get("prefill_url", ""),
                form_title=quiz_title,
                question_count=len(mcqs),
            )

        # ── 9. Build chapter summary ──────────────────────────────────────
        chapter_summary = []
        seen = {}
        for mcq in mcqs:
            ch = mcq.get("chapter", "Unknown")
            seen[ch] = seen.get(ch, 0) + 1
        for ch, count in seen.items():
            chapter_summary.append({"chapter": ch, "count": count})

        # ── 10. Return response ───────────────────────────────────────────
        return jsonify({
            "success": True,
            "quiz_title": quiz_title,
            "total_mcqs": len(mcqs),
            "chapters_detected": len(chapters),
            "chapter_summary": chapter_summary,
            "form_url": form_result.get("prefill_url"),
            "form_edit_url": form_result.get("form_url"),
            "sheet_url": form_result.get("sheet_url"),
            "form_demo": form_result.get("demo", False),
            "whatsapp": whatsapp_result,
            "mcqs": mcqs,
        })

    except ValueError as e:
        logger.warning("Validation error: %s", e)
        return _error(str(e))

    except Exception as e:
        logger.exception("Unexpected error during generation")
        return _error(f"An unexpected error occurred: {e}", status=500)

    finally:
        # Clean up the uploaded temp file
        try:
            save_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "AI MCQ Generator Pro"})


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting AI MCQ Generator Pro on http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)